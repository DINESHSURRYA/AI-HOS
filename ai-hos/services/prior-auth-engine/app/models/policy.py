"""Prior authorization policy, request, and decision models (Pydantic v2)."""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Decision(str, Enum):
    AUTO_APPROVE = "auto_approve"
    AUTO_DENY = "auto_deny"
    ESCALATE = "escalate"


class PolicyRule(BaseModel):
    """Individual weighted rule within a payer policy."""

    field: str  # e.g., "procedure_code", "age", "diagnosis_codes", "urgency"
    operator: Literal["eq", "ne", "gt", "lt", "gte", "lte", "in", "contains"]
    value: Any
    weight: float = Field(1.0, gt=0.0)
    description: Optional[str] = None


class MedicalNecessityCriteria(BaseModel):
    """Criteria for clinical medical necessity evaluation."""

    description: str
    required_evidence: List[str] = Field(default_factory=list)
    duration_requirement: Optional[str] = None


class PayerPolicy(BaseModel):
    """Payer-specific prior authorization policy."""

    policy_id: str = Field(..., description="Unique policy identifier")
    payer_id: str = Field(..., description="Payer code (e.g. UHC, Aetna, BCBS, Cigna, Medicare)")
    payer_name: str
    policy_title: Optional[str] = None

    # Matching criteria
    procedure_codes: List[str]  # CPT codes
    diagnosis_codes: List[str]  # ICD-10 codes

    # Rules
    rules: List[PolicyRule] = Field(default_factory=list)
    medical_necessity: Optional[MedicalNecessityCriteria] = None

    # Decision thresholds
    auto_approve_threshold: float = Field(0.80, ge=0.0, le=1.0)
    auto_deny_threshold: float = Field(0.35, ge=0.0, le=1.0)

    # Metadata
    version: str = "2.0"
    effective_date: datetime = Field(default_factory=utc_now)
    expiration_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)


class PriorAuthRequest(BaseModel):
    """Incoming prior authorization request."""

    request_id: str
    patient_id: str
    provider_id: str
    payer_id: str

    # Clinical context
    procedure_code: str
    diagnosis_codes: List[str]
    patient_age: int = Field(..., ge=0, le=130)
    patient_gender: Literal["M", "F", "O"]

    # Clinical history
    previous_procedures: List[str] = Field(default_factory=list)
    current_medications: List[str] = Field(default_factory=list)
    clinical_notes: Optional[str] = None

    # Request metadata
    urgency: Literal["routine", "urgent", "emergent"] = "routine"
    requested_date: datetime = Field(default_factory=utc_now)


class RuleEvaluationDetail(BaseModel):
    """Transparent result for an individual policy rule."""

    rule: str
    passed: bool
    score: float
    weight: float
    description: Optional[str] = None


class PriorAuthDecision(BaseModel):
    """Explainable prior authorization decision output."""

    request_id: str
    payer_id: Optional[str] = None
    procedure_code: Optional[str] = None
    diagnosis_codes: List[str] = Field(default_factory=list)
    decision: Decision
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    rule_score: Optional[float] = None
    medical_necessity_score: Optional[float] = None

    # Explanation
    matched_policy_id: Optional[str] = None
    matched_policy_title: Optional[str] = None
    matched_rules: List[str] = Field(default_factory=list)
    failed_rules: List[str] = Field(default_factory=list)
    rule_results: List[RuleEvaluationDetail] = Field(default_factory=list)
    reasoning: str

    # Escalation & Guidance
    required_documents: List[str] = Field(default_factory=list)
    suggested_diagnosis_codes: List[str] = Field(default_factory=list)
    urgency_override: bool = False

    # Timing
    processed_at: datetime = Field(default_factory=utc_now)
    estimated_decision_time_hours: Optional[int] = None


class PriorAuthStats(BaseModel):
    """Analytics summary for prior authorization dashboard."""

    total_policies: int
    total_evaluations: int
    auto_approved: int
    auto_denied: int
    escalated: int
    auto_approval_rate: float
    avg_confidence: float
    payers: List[str]
