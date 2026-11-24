"""Async SQLite persistence for payer policies and prior authorization audit history."""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import aiosqlite

from app.core.config import settings
from app.models.policy import Decision, PayerPolicy, PriorAuthDecision


class PriorAuthStore:
    """Persists custom payer policies and prior-auth evaluation history in SQLite."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or settings.SQLITE_DB_PATH
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS policies (
                    policy_id TEXT PRIMARY KEY,
                    payer_id TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    payer_id TEXT,
                    decision TEXT NOT NULL,
                    confidence_score REAL NOT NULL,
                    processed_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            await db.commit()
        self._initialized = True

    async def save_policy(self, policy: PayerPolicy) -> None:
        await self.initialize()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO policies (policy_id, payer_id, payload)
                VALUES (?, ?, ?)
                """,
                (policy.policy_id, policy.payer_id, json.dumps(policy.model_dump(mode="json"))),
            )
            await db.commit()

    async def delete_policy(self, policy_id: str) -> bool:
        await self.initialize()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM policies WHERE policy_id = ?", (policy_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def load_all_policies(self) -> List[PayerPolicy]:
        await self.initialize()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT payload FROM policies") as cursor:
                rows = await cursor.fetchall()
                return [PayerPolicy.model_validate(json.loads(r[0])) for r in rows]

    async def record_decision(self, decision: PriorAuthDecision) -> None:
        await self.initialize()
        serialized = decision.model_dump(mode="json")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO decisions (request_id, payer_id, decision, confidence_score, processed_at, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.request_id,
                    decision.payer_id,
                    decision.decision.value,
                    decision.confidence_score,
                    serialized["processed_at"],
                    json.dumps(serialized),
                ),
            )
            await db.commit()

    async def list_decisions(self, limit: int = 50) -> List[PriorAuthDecision]:
        await self.initialize()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT payload FROM decisions ORDER BY id DESC LIMIT ?", (limit,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [PriorAuthDecision.model_validate(json.loads(r[0])) for r in rows]

    async def get_stats(self, active_policies: List[PayerPolicy]) -> Dict[str, Any]:
        decisions = await self.list_decisions(limit=500)
        total = len(decisions)
        approved = sum(1 for d in decisions if d.decision == Decision.AUTO_APPROVE)
        denied = sum(1 for d in decisions if d.decision == Decision.AUTO_DENY)
        escalated = sum(1 for d in decisions if d.decision == Decision.ESCALATE)
        avg_conf = (
            round(sum(d.confidence_score for d in decisions) / total, 3)
            if total > 0
            else 0.0
        )
        approval_rate = round((approved / total) * 100.0, 1) if total > 0 else 0.0
        payers = sorted({p.payer_id for p in active_policies})

        return {
            "total_policies": len(active_policies),
            "total_evaluations": total,
            "auto_approved": approved,
            "auto_denied": denied,
            "escalated": escalated,
            "auto_approval_rate": approval_rate,
            "avg_confidence": avg_conf,
            "payers": payers,
        }


_store: Optional[PriorAuthStore] = None


def get_store() -> PriorAuthStore:
    global _store
    if _store is None:
        _store = PriorAuthStore()
    return _store


def reset_store(db_path: Optional[str] = None) -> PriorAuthStore:
    global _store
    _store = PriorAuthStore(db_path=db_path)
    return _store
