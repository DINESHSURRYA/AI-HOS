"""FastAPI endpoints for Prior Authorization Engine."""
from typing import List
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
import structlog

from app.db.store import get_store
from app.engine.rule_engine import get_rule_engine
from app.models.policy import (
    PayerPolicy,
    PriorAuthDecision,
    PriorAuthRequest,
    PriorAuthStats,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/prior-auth", tags=["prior-auth"])


@router.get("/policies", response_model=List[PayerPolicy])
async def list_all_policies() -> List[PayerPolicy]:
    """List all loaded payer policies across all payers."""
    engine = get_rule_engine()
    return sorted(engine.policies.values(), key=lambda p: (p.payer_id, p.policy_id))


@router.get("/policies/{payer_id}", response_model=List[PayerPolicy])
async def get_payer_policies(payer_id: str) -> List[PayerPolicy]:
    """Get all policies for a specific payer (case-insensitive)."""
    engine = get_rule_engine()
    target = payer_id.strip().upper()
    return [
        p for p in engine.policies.values() if p.payer_id.strip().upper() == target
    ]


@router.post("/policies", response_model=PayerPolicy)
async def create_policy(policy: PayerPolicy) -> PayerPolicy:
    """Create or update a payer policy and persist to SQLite."""
    get_rule_engine().load_policy(policy)
    await get_store().save_policy(policy)
    return policy


@router.delete("/policies/{policy_id}")
async def delete_policy(policy_id: str):
    """Remove a payer policy."""
    removed = get_rule_engine().remove_policy(policy_id)
    await get_store().delete_policy(policy_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Policy not found")
    return {"deleted": True, "policy_id": policy_id}


@router.post("/evaluate", response_model=PriorAuthDecision)
async def evaluate_request(
    request: PriorAuthRequest,
    background_tasks: BackgroundTasks = None,
) -> PriorAuthDecision:
    """
    Evaluate a prior authorization request against payer rules and clinical notes.
    Returns auto_approve, auto_deny, or escalate with explainable confidence score.
    """
    logger.info(
        "evaluating_request",
        request_id=request.request_id,
        payer=request.payer_id,
        procedure=request.procedure_code,
    )

    decision = get_rule_engine().evaluate_request(request)
    await get_store().record_decision(decision)

    if background_tasks is not None:
        background_tasks.add_task(_log_decision, decision)

    return decision


@router.post("/batch-evaluate", response_model=List[PriorAuthDecision])
async def batch_evaluate(requests: List[PriorAuthRequest]) -> List[PriorAuthDecision]:
    """Evaluate multiple prior authorization requests in one call."""
    engine = get_rule_engine()
    store = get_store()
    decisions: List[PriorAuthDecision] = []
    for req in requests:
        dec = engine.evaluate_request(req)
        await store.record_decision(dec)
        decisions.append(dec)
    return decisions


@router.get("/decisions", response_model=List[PriorAuthDecision])
async def list_decisions(limit: int = Query(default=50, ge=1, le=200)) -> List[PriorAuthDecision]:
    """Return recent prior authorization evaluation history."""
    return await get_store().list_decisions(limit=limit)


@router.get("/stats", response_model=PriorAuthStats)
async def get_prior_auth_stats() -> PriorAuthStats:
    """Return analytics metrics for the prior authorization dashboard."""
    engine = get_rule_engine()
    stats = await get_store().get_stats(list(engine.policies.values()))
    return PriorAuthStats(**stats)


async def _log_decision(decision: PriorAuthDecision) -> None:
    logger.info(
        "decision_logged",
        request_id=decision.request_id,
        decision=decision.decision.value,
        confidence=decision.confidence_score,
        policy=decision.matched_policy_id,
    )
