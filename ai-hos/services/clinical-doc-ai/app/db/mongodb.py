"""MongoDB repository for clinical notes."""
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from app.models.schemas import VoiceSession, SOAPNote
from typing import Optional, Dict, Any
from datetime import datetime
import structlog

logger = structlog.get_logger()


class ClinicalNotesRepository:
    """Repository for voice sessions and clinical notes."""
    
    def __init__(self):
        self.client = AsyncIOMotorClient(settings.MONGODB_URL)
        self.db = self.client[settings.MONGODB_DB]
        self.sessions = self.db.voice_sessions
        self.notes = self.db.soap_notes
    
    async def create_session(self, session: VoiceSession) -> str:
        """Create new voice session."""
        doc = session.model_dump()
        await self.sessions.insert_one(doc)
        logger.info("session_created", session_id=session.session_id)
        return session.session_id
    
    async def update_session(
        self, 
        session_id: str, 
        updates: Dict[str, Any]
    ) -> bool:
        """Update session with transcription or SOAP note."""
        updates["updated_at"] = datetime.utcnow()
        result = await self.sessions.update_one(
            {"session_id": session_id},
            {"$set": updates}
        )
        return result.modified_count > 0
    
    async def get_session(self, session_id: str) -> Optional[VoiceSession]:
        """Retrieve session by ID."""
        doc = await self.sessions.find_one({"session_id": session_id})
        if doc:
            return VoiceSession(**doc)
        return None
    
    async def save_soap_note(
        self, 
        session_id: str, 
        note: SOAPNote
    ) -> str:
        """Save generated SOAP note."""
        doc = {
            "session_id": session_id,
            "note": note.model_dump(),
            "created_at": datetime.utcnow()
        }
        result = await self.notes.insert_one(doc)
        return str(result.inserted_id)
    
    async def get_patient_notes(
        self, 
        patient_id: str,
        limit: int = 10
    ) -> list:
        """Get all notes for a patient."""
        cursor = self.notes.find(
            {"note.patient_id": patient_id}
        ).sort("created_at", -1).limit(limit)
        
        return await cursor.to_list(length=limit)


# Singleton
_db = None

def get_db() -> ClinicalNotesRepository:
    """Get database repository."""
    global _db
    if _db is None:
        _db = ClinicalNotesRepository()
    return _db
