"""Persistent repository for clinical sessions & SOAP notes (SQLite default + optional MongoDB)."""
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import aiosqlite
import structlog

from app.core.config import settings
from app.models.schemas import SOAPNote, SessionStatus, VoiceSession

logger = structlog.get_logger()


class ClinicalNotesRepository:
    """
    Async persistence repository.
    Uses SQLite (`aiosqlite`) by default so the platform works immediately on any machine
    without requiring an external MongoDB server, while remaining compatible with MongoDB
    when STORAGE_BACKEND=mongodb.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.backend = settings.STORAGE_BACKEND.lower()
        self.db_path = db_path or settings.SQLITE_DB_PATH
        self._initialized = False
        self._mongo_client = None
        self._mongo_db = None

        if self.backend == "mongodb":
            try:
                from motor.motor_asyncio import AsyncIOMotorClient  # type: ignore

                self._mongo_client = AsyncIOMotorClient(
                    settings.MONGODB_URL, serverSelectionTimeoutMS=2500
                )
                self._mongo_db = self._mongo_client[settings.MONGODB_DB]
                logger.info("repository_configured", backend="mongodb")
            except Exception as exc:
                logger.warning(
                    "mongodb_unavailable_falling_back_to_sqlite",
                    error=str(exc),
                )
                self.backend = "sqlite"

    async def initialize(self) -> None:
        """Create SQLite tables if using SQLite backend."""
        if self._initialized:
            return
        if self.backend == "sqlite":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS voice_sessions (
                        session_id TEXT PRIMARY KEY,
                        patient_id TEXT NOT NULL,
                        provider_id TEXT NOT NULL,
                        encounter_id TEXT,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        payload TEXT NOT NULL
                    )
                    """
                )
                await db.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_sessions_patient
                    ON voice_sessions (patient_id, created_at DESC)
                    """
                )
                await db.commit()
        self._initialized = True

    async def create_session(self, session: VoiceSession) -> str:
        await self.initialize()
        now_iso = datetime.now(timezone.utc).isoformat()
        payload_dict = session.model_dump(mode="json")

        if self.backend == "mongodb" and self._mongo_db is not None:
            await self._mongo_db.voice_sessions.insert_one(dict(payload_dict))
        else:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    INSERT OR REPLACE INTO voice_sessions
                    (session_id, patient_id, provider_id, encounter_id, status, created_at, updated_at, payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session.session_id,
                        session.patient_id,
                        session.provider_id,
                        session.encounter_id,
                        session.status.value,
                        payload_dict["created_at"],
                        now_iso,
                        json.dumps(payload_dict),
                    ),
                )
                await db.commit()

        logger.info("session_created", session_id=session.session_id, backend=self.backend)
        return session.session_id

    async def update_session(
        self,
        session_id: str,
        updates: Dict[str, Any],
    ) -> Optional[VoiceSession]:
        await self.initialize()
        existing = await self.get_session(session_id)
        if existing is None:
            return None

        data = existing.model_dump(mode="json")
        for key, value in updates.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()
            elif isinstance(value, SessionStatus):
                data[key] = value.value
            elif isinstance(value, SOAPNote):
                data[key] = value.model_dump(mode="json")
            else:
                data[key] = value

        now_iso = datetime.now(timezone.utc).isoformat()
        data["updated_at"] = now_iso
        updated_session = VoiceSession.model_validate(data)
        serialized = updated_session.model_dump(mode="json")

        if self.backend == "mongodb" and self._mongo_db is not None:
            await self._mongo_db.voice_sessions.update_one(
                {"session_id": session_id},
                {"$set": serialized},
            )
        else:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    UPDATE voice_sessions
                    SET status = ?, updated_at = ?, payload = ?
                    WHERE session_id = ?
                    """,
                    (
                        updated_session.status.value,
                        now_iso,
                        json.dumps(serialized),
                        session_id,
                    ),
                )
                await db.commit()

        return updated_session

    async def get_session(self, session_id: str) -> Optional[VoiceSession]:
        await self.initialize()
        if self.backend == "mongodb" and self._mongo_db is not None:
            doc = await self._mongo_db.voice_sessions.find_one(
                {"session_id": session_id}, {"_id": 0}
            )
            return VoiceSession.model_validate(doc) if doc else None

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT payload FROM voice_sessions WHERE session_id = ?",
                (session_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return VoiceSession.model_validate(json.loads(row[0]))

    async def list_sessions(self, limit: int = 50) -> List[VoiceSession]:
        await self.initialize()
        if self.backend == "mongodb" and self._mongo_db is not None:
            cursor = (
                self._mongo_db.voice_sessions.find({}, {"_id": 0})
                .sort("created_at", -1)
                .limit(limit)
            )
            docs = await cursor.to_list(length=limit)
            return [VoiceSession.model_validate(d) for d in docs]

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT payload FROM voice_sessions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [VoiceSession.model_validate(json.loads(r[0])) for r in rows]

    async def delete_session(self, session_id: str) -> bool:
        await self.initialize()
        if self.backend == "mongodb" and self._mongo_db is not None:
            res = await self._mongo_db.voice_sessions.delete_one({"session_id": session_id})
            return res.deleted_count > 0

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM voice_sessions WHERE session_id = ?", (session_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def save_soap_note(
        self,
        session_id: str,
        note: SOAPNote,
        transcript: Optional[str] = None,
        redacted_transcript: Optional[str] = None,
    ) -> Optional[VoiceSession]:
        """Attach SOAP note to session (creating a session record if needed)."""
        existing = await self.get_session(session_id)
        if existing is None:
            session = VoiceSession(
                session_id=session_id,
                patient_id="PAT-UNKNOWN",
                provider_id="PROV-DEFAULT",
                status=SessionStatus.COMPLETED,
                transcript=transcript,
                redacted_transcript=redacted_transcript,
                soap_note=note,
                completed_at=datetime.now(timezone.utc),
            )
            await self.create_session(session)
            return session

        updates: Dict[str, Any] = {
            "soap_note": note,
            "status": SessionStatus.APPROVED if note.approved else SessionStatus.COMPLETED,
            "completed_at": datetime.now(timezone.utc),
        }
        if transcript is not None:
            updates["transcript"] = transcript
        if redacted_transcript is not None:
            updates["redacted_transcript"] = redacted_transcript
        return await self.update_session(session_id, updates)

    async def get_patient_notes(
        self,
        patient_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Retrieve all sessions with SOAP notes for a given patient."""
        sessions = await self.list_sessions(limit=200)
        notes = []
        for sess in sessions:
            if sess.patient_id == patient_id and sess.soap_note is not None:
                notes.append(
                    {
                        "session_id": sess.session_id,
                        "patient_id": sess.patient_id,
                        "provider_id": sess.provider_id,
                        "created_at": sess.created_at.isoformat(),
                        "status": sess.status.value,
                        "note": sess.soap_note.model_dump(mode="json"),
                    }
                )
            if len(notes) >= limit:
                break
        return notes

    async def get_stats(self) -> Dict[str, Any]:
        """Compute aggregate documentation metrics."""
        sessions = await self.list_sessions(limit=500)
        total = len(sessions)
        completed = [s for s in sessions if s.soap_note is not None]
        approved = [s for s in completed if s.soap_note and s.soap_note.approved]

        confidences = [s.soap_note.confidence_score for s in completed if s.soap_note]
        avg_conf = round(sum(confidences) / len(confidences), 3) if confidences else 0.0

        entity_breakdown: Dict[str, int] = {
            "diagnosis": 0,
            "medication": 0,
            "procedure": 0,
            "symptom": 0,
            "allergy": 0,
            "vital": 0,
        }
        total_entities = 0
        for s in completed:
            if s.soap_note:
                for ent in s.soap_note.entities:
                    key = ent.entity_type.value
                    entity_breakdown[key] = entity_breakdown.get(key, 0) + 1
                    total_entities += 1

        return {
            "total_sessions": total,
            "completed_sessions": len(completed),
            "approved_notes": len(approved),
            "avg_confidence": avg_conf,
            "total_entities_extracted": total_entities,
            "entity_breakdown": entity_breakdown,
            "storage_backend": self.backend,
            "llm_mode": settings.LLM_MODEL if settings.ENABLE_LLM_GENERATION else "local-clinical-engine-v2",
        }


_db: Optional[ClinicalNotesRepository] = None


def get_db() -> ClinicalNotesRepository:
    """Get database repository singleton."""
    global _db
    if _db is None:
        _db = ClinicalNotesRepository()
    return _db


def reset_db(db_path: Optional[str] = None) -> ClinicalNotesRepository:
    """Reset repository singleton (used in tests)."""
    global _db
    _db = ClinicalNotesRepository(db_path=db_path)
    return _db
