"""FHIR-compatible Pydantic schemas for clinical documentation."""
from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field
from enum import Enum


class SessionStatus(str, Enum):
    PENDING = "pending"
    RECORDING = "recording"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"


class EntityType(str, Enum):
    DIAGNOSIS = "diagnosis"
    PROCEDURE = "procedure"
    MEDICATION = "medication"
    SYMPTOM = "symptom"
    ALLERGY = "allergy"


class ClinicalEntity(BaseModel):
    """Extracted clinical entity with coding."""
    text: str
    entity_type: EntityType
    start: int
    end: int
    confidence: float = Field(..., ge=0.0, le=1.0)
    # Standardized codes
    icd10: Optional[str] = None
    rxnorm: Optional[str] = None
    cpt: Optional[str] = None
    snomed: Optional[str] = None


class SOAPNote(BaseModel):
    """Structured SOAP note output."""
    subjective: str = Field(..., description="Patient-reported symptoms and history")
    objective: str = Field(..., description="Physical exam findings and observations")
    assessment: str = Field(..., description="Diagnoses and clinical reasoning")
    plan: str = Field(..., description="Treatment plan and follow-up")
    # Metadata
    entities: List[ClinicalEntity] = []
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class VoiceSession(BaseModel):
    """Voice recording session metadata."""
    session_id: str = Field(..., description="UUID for the session")
    patient_id: str = Field(..., description="FHIR Patient ID")
    encounter_id: Optional[str] = None
    provider_id: str
    status: SessionStatus = SessionStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    audio_duration_seconds: Optional[float] = None
    transcript: Optional[str] = None
    soap_note: Optional[SOAPNote] = None
    # Audit fields
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class TranscriptionRequest(BaseModel):
    """Request to transcribe audio."""
    session_id: str
    audio_format: Literal["wav", "mp3", "webm"] = "webm"
    sample_rate: int = 16000


class TranscriptionResponse(BaseModel):
    """ASR output."""
    session_id: str
    transcript: str
    segments: List[Dict[str, Any]]  # Word-level timestamps
    language: str
    confidence: float


class SOAPGenerationRequest(BaseModel):
    """Request to generate SOAP note."""
    session_id: str
    transcript: str
    patient_context: Optional[Dict[str, Any]] = None  # FHIR Patient data


class SOAPGenerationResponse(BaseModel):
    """LLM-generated SOAP note."""
    session_id: str
    soap_note: SOAPNote
    processing_time_ms: int
    model_version: str
