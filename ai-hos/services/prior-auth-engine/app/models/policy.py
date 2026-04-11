"""Prior authorization policy models."""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from enum import Enum


class Decision(str, Enum):
    AUTO_APPROVE = "auto_approve"
    AUTO_DENY = "auto_deny"
    ESCALATE = "escalate"


class PolicyRule(BaseModel):
    """Individual rule within a policy."""
    field: str  # e.g., "procedure_code", "age", "diagnosis"
    operator: Literal["eq", "ne", "gt", "lt", "gte", "lte", "in", "contains"]
    value: Any
    weight: float = 1.0  # Importance of this rule


class MedicalNecessityCriteria(BaseModel):
    """Criteria for medical necessity evaluation."""
    description: str
    required_evidence: List[str]  # e.g., ["failed_conservative_therapy"]
    duration_requirement: Optional[str] = None  # e.g., "6_weeks"


class PayerPolicy(BaseModel):
    """
    Payer-specific prior authorization policy.
    Stored as JSON in PostgreSQL + cached in Redis.
    """
    policy_id: str = Field(..., description="Unique policy identifier")
    payer_id: str = Field(..., description="Payer identifier (e.g., 'UHC', 'Aetna')")
    payer_name: str
    
    # Matching criteria
    procedure_codes: List[str]  # CPT codes
    diagnosis_codes: List[str]  # ICD-10 codes
    
    # Rules
    rules: List[PolicyRule]
    medical_necessity: Optional[MedicalNecessityCriteria] = None
    
    # Decision thresholds
    auto_approve_threshold: float = Field(0.85, ge=0.0, le=1.0)
    auto_deny_threshold: float = Field(0.3, ge=0.0, le=1.0)
    
    # Metadata
    version: str = "1.0"
    effective_date: datetime
    expiration_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PriorAuthRequest(BaseModel):
    """Incoming prior authorization request."""
    request_id: str
    patient_id: str
    provider_id: str
    payer_id: str
    
    # Clinical context
    procedure_code: str
    diagnosis_codes: List[str]
    patient_age: int
    patient_gender: Literal["M", "F", "O"]
    
    # Clinical history
    previous_procedures: List[str] = []
    current_medications: List[str] = []
    clinical_notes: Optional[str] = None  # For NLP analysis
    
    # Request metadata
    urgency: Literal["routine", "urgent", "emergent"] = "routine"
    requested_date: datetime = Field(default_factory=datetime.utcnow)


class PriorAuthDecision(BaseModel):
    """Decision output."""
    request_id: str
    decision: Decision
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    
    # Explanation
    matched_policy_id: Optional[str] = None
    matched_rules: List[str] = []
    reasoning: str
    
    # For escalations
    required_documents: List[str] = []
    suggested_diagnosis_codes: List[str] = []
    
    # Timing
    processed_at: datetime = Field(default_factory=datetime.utcnow)
    estimated_decision_time_hours: Optional[int] = None  # For escalations
