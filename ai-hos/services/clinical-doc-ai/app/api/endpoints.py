"""FastAPI endpoints for Clinical Documentation AI Service."""
from datetime import datetime, timezone
import json
import time
from typing import List, Optional
import uuid
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
import structlog

from app.core.asr_pipeline import get_asr_pipeline
from app.core.config import settings
from app.core.fhir_exporter import build_fhir_r4_bundle
from app.core.llm_service import get_llm_service
from app.core.nlp_pipeline import get_nlp_pipeline
from app.core.phi_redactor import redact_phi
from app.db.mongodb import get_db
from app.models.schemas import (
    CreateSessionRequest,
    PHIRedactionRequest,
    PHIRedactionResponse,
    SOAPGenerationRequest,
    SOAPGenerationResponse,
    SOAPUpdateRequest,
    ServiceStats,
    SessionStatus,
    TranscriptionResponse,
    VoiceSession,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1", tags=["clinical-doc"])


@router.post("/sessions", response_model=VoiceSession)
async def create_session(
    request: Request,
    patient_id: Optional[str] = Query(default=None),
    provider_id: Optional[str] = Query(default=None),
    encounter_id: Optional[str] = Query(default=None),
    body: Optional[CreateSessionRequest] = Body(default=None),
) -> VoiceSession:
    """
    Create a new voice/dictation clinical documentation session.
    Accepts either query params (backward-compatible) or JSON request body.
    """
    pid = body.patient_id if body else patient_id
    prov_id = body.provider_id if body else provider_id
    enc_id = body.encounter_id if body else encounter_id
    cc = body.chief_complaint if body else None

    if not pid or not prov_id:
        raise HTTPException(
            status_code=422,
            detail="patient_id and provider_id are required.",
        )

    session = VoiceSession(
        session_id=str(uuid.uuid4()),
        patient_id=pid,
        provider_id=prov_id,
        encounter_id=enc_id or f"ENC-{uuid.uuid4().hex[:8].upper()}",
        chief_complaint=cc,
        status=SessionStatus.PENDING,
        created_at=datetime.now(timezone.utc),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await get_db().create_session(session)
    return session


@router.get("/sessions", response_model=List[VoiceSession])
async def list_sessions(limit: int = Query(default=50, ge=1, le=200)) -> List[VoiceSession]:
    """List recent clinical documentation sessions."""
    return await get_db().list_sessions(limit=limit)


@router.get("/sessions/{session_id}", response_model=VoiceSession)
async def get_session(session_id: str) -> VoiceSession:
    """Get full session details including transcript and SOAP note."""
    session = await get_db().get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a documentation session."""
    deleted = await get_db().delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": True, "session_id": session_id}


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
    """
    WebSocket for real-time audio & live dictation streaming.
    Accepts:
      - binary audio frames (WebM/WAV chunks)
      - JSON or text control frames:
        - `{"type": "live_transcript", "text": "..."}` (from browser Web Speech API)
        - `"END_RECORDING"` or `{"type": "END_RECORDING", "transcript": "..."}`
    """
    await websocket.accept()
    logger.info("websocket_connected", session_id=session_id)

    audio_buffer = bytearray()
    live_transcript_parts: List[str] = []

    try:
        while True:
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                break

            if message.get("bytes") is not None:
                chunk = message["bytes"]
                audio_buffer.extend(chunk)
                await websocket.send_json(
                    {"type": "ack", "bytes_received": len(chunk)}
                )

            elif message.get("text") is not None:
                raw_text = message["text"]
                end_signal = False
                override_transcript = ""

                if raw_text == "END_RECORDING":
                    end_signal = True
                else:
                    try:
                        parsed = json.loads(raw_text)
                        if parsed.get("type") == "live_transcript" and parsed.get("text"):
                            live_transcript_parts.append(str(parsed["text"]).strip())
                            await websocket.send_json({"type": "transcript_ack"})
                        elif parsed.get("type") == "END_RECORDING":
                            end_signal = True
                            override_transcript = str(parsed.get("transcript", "")).strip()
                    except json.JSONDecodeError:
                        if raw_text.startswith("TRANSCRIPT:"):
                            live_transcript_parts.append(raw_text[11:].strip())

                if end_signal:
                    await websocket.send_json(
                        {"type": "processing", "message": "Transcribing and extracting clinical entities..."}
                    )
                    start_time = time.time()

                    # Prefer live browser dictation transcript if provided, otherwise run ASR pipeline
                    combined_live = override_transcript or " ".join(live_transcript_parts).strip()
                    if combined_live:
                        transcript = get_asr_pipeline().post_process_medical(combined_live)
                        asr_confidence = 0.93
                    else:
                        asr_result = await get_asr_pipeline().transcribe(
                            bytes(audio_buffer),
                            sample_rate=16000,
                        )
                        transcript = asr_result["transcript"]
                        asr_confidence = asr_result["confidence"]

                    redacted_text, phi_count, phi_cats = redact_phi(
                        transcript, enabled=settings.PHI_REDACTION_ENABLED
                    )

                    await get_db().update_session(
                        session_id,
                        {
                            "status": SessionStatus.PROCESSING,
                            "transcript": transcript,
                            "redacted_transcript": redacted_text,
                            "audio_duration_seconds": round(max(1.0, len(audio_buffer) / 16000.0), 2)
                            if audio_buffer
                            else None,
                        },
                    )

                    await websocket.send_json(
                        {
                            "type": "transcription",
                            "transcript": transcript,
                            "redacted_transcript": redacted_text,
                            "phi_redactions": phi_cats,
                            "confidence": asr_confidence,
                            "processing_time_ms": int((time.time() - start_time) * 1000),
                        }
                    )

                    entities = await get_nlp_pipeline().extract_entities(redacted_text)
                    await websocket.send_json(
                        {
                            "type": "entities",
                            "entities": [e.model_dump(mode="json") for e in entities],
                        }
                    )

                    soap_note = await get_llm_service().generate_soap_note(
                        transcript=redacted_text,
                        entities=entities,
                        phi_redacted_count=phi_count,
                    )

                    await get_db().save_soap_note(
                        session_id=session_id,
                        note=soap_note,
                        transcript=transcript,
                        redacted_transcript=redacted_text,
                    )

                    await websocket.send_json(
                        {
                            "type": "soap_note",
                            "soap_note": soap_note.model_dump(mode="json"),
                        }
                    )
                    break

    except WebSocketDisconnect:
        logger.info("websocket_disconnected", session_id=session_id)
    except Exception as exc:
        logger.error("websocket_error", session_id=session_id, error=str(exc))
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(
    session_id: str,
    audio: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
) -> TranscriptionResponse:
    """HTTP endpoint for audio file transcription."""
    audio_data = await audio.read()
    result = await get_asr_pipeline().transcribe(
        audio_data,
        filename=audio.filename or "audio.wav",
    )

    if background_tasks is not None:
        background_tasks.add_task(
            get_db().update_session,
            session_id,
            {
                "transcript": result["transcript"],
                "status": SessionStatus.PROCESSING,
            },
        )

    return TranscriptionResponse(
        session_id=session_id,
        transcript=result["transcript"],
        segments=result["segments"],
        language=result["language"],
        confidence=result["confidence"],
        engine=result.get("engine", "local-fallback"),
    )


@router.post("/generate-soap", response_model=SOAPGenerationResponse)
async def generate_soap(request: SOAPGenerationRequest) -> SOAPGenerationResponse:
    """Extract medical entities, redact PHI, and generate a structured SOAP note."""
    start_time = time.time()

    normalized = get_asr_pipeline().post_process_medical(request.transcript)
    redacted_text, phi_count, phi_categories = redact_phi(
        normalized, enabled=settings.PHI_REDACTION_ENABLED
    )

    entities = await get_nlp_pipeline().extract_entities(redacted_text)
    soap = await get_llm_service().generate_soap_note(
        transcript=redacted_text,
        entities=entities,
        patient_context=request.patient_context,
        phi_redacted_count=phi_count,
    )

    await get_db().save_soap_note(
        session_id=request.session_id,
        note=soap,
        transcript=normalized,
        redacted_transcript=redacted_text,
    )

    processing_time = int((time.time() - start_time) * 1000)
    return SOAPGenerationResponse(
        session_id=request.session_id,
        soap_note=soap,
        redacted_transcript=redacted_text,
        phi_redactions=phi_categories,
        processing_time_ms=processing_time,
        model_version=soap.model_used,
    )


@router.put("/sessions/{session_id}/soap", response_model=VoiceSession)
async def update_soap_note(
    session_id: str,
    payload: SOAPUpdateRequest,
) -> VoiceSession:
    """Save clinician edits and/or EHR approval status on a SOAP note."""
    session = await get_db().get_session(session_id)
    if not session or not session.soap_note:
        raise HTTPException(status_code=404, detail="Session or SOAP note not found")

    updated_soap = session.soap_note.model_copy(
        update={
            "subjective": payload.subjective,
            "objective": payload.objective,
            "assessment": payload.assessment,
            "plan": payload.plan,
        }
    )
    if payload.approved is True:
        updated_soap = updated_soap.model_copy(
            update={
                "approved": True,
                "approved_at": datetime.now(timezone.utc),
                "approved_by": payload.approved_by or session.provider_id,
            }
        )

    saved = await get_db().save_soap_note(session_id=session_id, note=updated_soap)
    if not saved:
        raise HTTPException(status_code=500, detail="Failed to persist SOAP update")
    return saved


@router.get("/sessions/{session_id}/fhir")
async def export_session_fhir(session_id: str):
    """Export the clinical documentation session as a valid HL7 FHIR R4 Bundle."""
    session = await get_db().get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return build_fhir_r4_bundle(session)


@router.get("/patients/{patient_id}/notes")
async def get_patient_notes(patient_id: str, limit: int = 20):
    """Get all SOAP notes for a specific patient."""
    notes = await get_db().get_patient_notes(patient_id, limit)
    return {"patient_id": patient_id, "count": len(notes), "notes": notes}


@router.post("/redact-phi", response_model=PHIRedactionResponse)
async def preview_phi_redaction(payload: PHIRedactionRequest) -> PHIRedactionResponse:
    """Preview HIPAA Safe Harbor PHI redaction on clinical text."""
    redacted, count, categories = redact_phi(payload.text, enabled=True)
    return PHIRedactionResponse(
        original_length=len(payload.text),
        redacted_text=redacted,
        redaction_count=count,
        categories_detected=categories,
    )


@router.get("/stats", response_model=ServiceStats)
async def get_service_stats() -> ServiceStats:
    """Dashboard metrics for clinical documentation."""
    return ServiceStats(**(await get_db().get_stats()))
