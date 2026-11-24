"""FHIR-compatible Pydantic v2 schemas for clinical documentation."""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """Timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class SessionStatus(str, Enum):
    PENDING = "pending"
    RECORDING = "recording"
    PROCESSING = "processing"
    COMPLETED = "completed"
    APPROVED = "approved"
    ERROR = "error"


class EntityType(str, Enum):
    DIAGNOSIS = "diagnosis"
    PROCEDURE = "procedure"
    MEDICATION = "medication"
    SYMPTOM = "symptom"
    ALLERGY = "allergy"
    VITAL = "vital"


class ClinicalEntity(BaseModel):
    """Extracted clinical entity with standardized medical coding."""

    text: str
    entity_type: EntityType
    start: int = 0
    end: int = 0
    confidence: float = Field(..., ge=0.0, le=1.0)
    # Standardized terminology codes
    icd10: Optional[str] = None
    rxnorm: Optional[str] = None
    cpt: Optional[str] = None
    snomed: Optional[str] = None
    dosage: Optional[str] = None


class SOAPNote(BaseModel):
    """Structured clinical SOAP note output."""

    subjective: str = Field(..., description="Patient-reported symptoms and history")
    objective: str = Field(..., description="Physical exam findings, vitals, and observations")
    assessment: str = Field(..., description="Diagnoses and clinical reasoning")
    plan: str = Field(..., description="Treatment plan, orders, and follow-up")
    # Metadata
    entities: List[ClinicalEntity] = Field(default_factory=list)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    generated_at: datetime = Field(default_factory=utc_now)
    model_used: str = "ai-hos-clinical-engine-v2"
    phi_redacted_count: int = 0
    approved: bool = False
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None


class VoiceSession(BaseModel):
    """Voice/dictation clinical encounter session."""

    session_id: str = Field(..., description="UUID for the session")
    patient_id: str = Field(..., description="FHIR Patient ID")
    encounter_id: Optional[str] = None
    provider_id: str
    chief_complaint: Optional[str] = None
    status: SessionStatus = SessionStatus.PENDING
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    audio_duration_seconds: Optional[float] = None
    transcript: Optional[str] = None
    redacted_transcript: Optional[str] = None
    soap_note: Optional[SOAPNote] = None
    # Audit fields
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class CreateSessionRequest(BaseModel):
    """JSON body option for creating a session."""

    patient_id: str = Field(..., min_length=1)
    provider_id: str = Field(..., min_length=1)
    encounter_id: Optional[str] = None
    chief_complaint: Optional[str] = None


class TranscriptionRequest(BaseModel):
    """Request to transcribe audio."""

    session_id: str
    audio_format: Literal["wav", "mp3", "webm"] = "webm"
    sample_rate: int = 16000


class TranscriptionResponse(BaseModel):
    """ASR output."""

    session_id: str
    transcript: str
    segments: List[Dict[str, Any]]
    language: str
    confidence: float
    engine: str = "local-fallback"


class SOAPGenerationRequest(BaseModel):
    """Request to generate a structured SOAP note from a transcript."""

    session_id: str
    transcript: str = Field(..., min_length=5)
    patient_context: Optional[Dict[str, Any]] = None


class SOAPGenerationResponse(BaseModel):
    """Generated SOAP note with metadata and PHI redaction summary."""

    session_id: str
    soap_note: SOAPNote
    redacted_transcript: str
    phi_redactions: List[str] = Field(default_factory=list)
    processing_time_ms: int
    model_version: str


class SOAPUpdateRequest(BaseModel):
    """Update or approve an existing SOAP note."""

    subjective: str
    objective: str
    assessment: str
    plan: str
    approved: Optional[bool] = None
    approved_by: Optional[str] = None


class PHIRedactionRequest(BaseModel):
    """Test HIPAA Safe Harbor PHI redaction."""

    text: str


class PHIRedactionResponse(BaseModel):
    """Redacted output and detected PHI categories."""

    original_length: int
    redacted_text: str
    redaction_count: int
    categories_detected: List[str]


class ServiceStats(BaseModel):
    """Dashboard metrics for clinical documentation."""

    total_sessions: int
    completed_sessions: int
    approved_notes: int
    avg_confidence: float
    total_entities_extracted: int
    entity_breakdown: Dict[str, int]
    storage_backend: str
    llm_mode: str
