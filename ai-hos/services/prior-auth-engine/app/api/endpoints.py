"""FastAPI endpoints for Prior Authorization Engine."""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List
from app.models.policy import (
    PayerPolicy, PriorAuthRequest, PriorAuthDecision
)
from app.engine.rule_engine import get_rule_engine
import structlog

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/prior-auth", tags=["prior-auth"])


@router.post("/policies", response_model=PayerPolicy)
async def create_policy(policy: PayerPolicy):
    """Create or update a payer policy."""
    get_rule_engine().load_policy(policy)
    return policy


@router.post("/evaluate", response_model=PriorAuthDecision)
async def evaluate_request(
    request: PriorAuthRequest,
    background_tasks: BackgroundTasks = None
):
    """
    Evaluate a prior authorization request.
    Returns auto-approve, auto-deny, or escalate decision.
    """
    logger.info(
        "evaluating_request",
        request_id=request.request_id,
        payer=request.payer_id,
        procedure=request.procedure_code
    )
    
    decision = get_rule_engine().evaluate_request(request)
    
    # In background: log to audit, update analytics
    if background_tasks:
        background_tasks.add_task(_log_decision, decision)
    
    return decision


@router.post("/batch-evaluate", response_model=List[PriorAuthDecision])
async def batch_evaluate(requests: List[PriorAuthRequest]):
    """Evaluate multiple requests (for bulk processing)."""
    return [get_rule_engine().evaluate_request(r) for r in requests]


@router.get("/policies/{payer_id}", response_model=List[PayerPolicy])
async def get_payer_policies(payer_id: str):
    """Get all policies for a payer."""
    engine = get_rule_engine()
    policies = [
        p for p in engine.policies.values() 
        if p.payer_id == payer_id
    ]
    return policies


async def _log_decision(decision: PriorAuthDecision):
    """Background audit logging."""
    logger.info(
        "decision_logged",
        request_id=decision.request_id,
        decision=decision.decision,
        confidence=decision.confidence_score
    )
3. Infrastructure & Deployment
