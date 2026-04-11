"""FastAPI endpoints for Clinical Documentation AI."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.responses import JSONResponse
from typing import Optional
import uuid
import time
from datetime import datetime

from app.models.schemas import (
    VoiceSession, SessionStatus, TranscriptionResponse,
    SOAPGenerationRequest, SOAPGenerationResponse
)
from app.core.asr_pipeline import get_asr_pipeline
from app.core.nlp_pipeline import get_nlp_pipeline
from app.core.llm_service import get_llm_service
from app.db.mongodb import get_db
import structlog

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1", tags=["clinical-doc"])


@router.post("/sessions", response_model=VoiceSession)
async def create_session(
    patient_id: str,
    provider_id: str,
    encounter_id: Optional[str] = None
):
    """Create a new voice documentation session."""
    session = VoiceSession(
        session_id=str(uuid.uuid4()),
        patient_id=patient_id,
        provider_id=provider_id,
        encounter_id=encounter_id,
        status=SessionStatus.PENDING,
        created_at=datetime.utcnow()
    )
    
    await get_db().create_session(session)
    return session


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket for real-time audio streaming.
    Receives audio chunks, returns live transcription.
    """
    await websocket.accept()
    logger.info("websocket_connected", session_id=session_id)
    
    audio_buffer = bytearray()
    
    try:
        while True:
            message = await websocket.receive()
            
            if "bytes" in message:
                # Audio chunk received
                audio_buffer.extend(message["bytes"])
                await websocket.send_json({
                    "type": "ack",
                    "bytes_received": len(message["bytes"])
                })
                
            elif "text" in message:
                # Control message
                data = message["text"]
                
                if data == "END_RECORDING":
                    # Process complete audio
                    await websocket.send_json({
                        "type": "processing",
                        "message": "Transcribing audio..."
                    })
                    
                    # Run ASR
                    start_time = time.time()
                    asr_result = await get_asr_pipeline().transcribe(
                        bytes(audio_buffer),
                        sample_rate=16000
                    )
                    
                    # Update session
                    await get_db().update_session(session_id, {
                        "status": SessionStatus.PROCESSING,
                        "transcript": asr_result["transcript"],
                        "audio_duration_seconds": len(audio_buffer) / 32000  # Approximate
                    })
                    
                    await websocket.send_json({
                        "type": "transcription",
                        "transcript": asr_result["transcript"],
                        "confidence": asr_result["confidence"],
                        "processing_time_ms": int((time.time() - start_time) * 1000)
                    })
                    
                    # Extract entities
                    entities = await get_nlp_pipeline().extract_entities(
                        asr_result["transcript"]
                    )
                    
                    await websocket.send_json({
                        "type": "entities",
                        "entities": [e.model_dump() for e in entities]
                    })
                    
                    # Generate SOAP note
                    soap_note = await get_llm_service().generate_soap_note(
                        transcript=asr_result["transcript"],
                        entities=entities
                    )
                    
                    # Save to DB
                    await get_db().update_session(session_id, {
                        "status": SessionStatus.COMPLETED,
                        "soap_note": soap_note.model_dump(),
                        "completed_at": datetime.utcnow()
                    })
                    
                    await get_db().save_soap_note(session_id, soap_note)
                    
                    await websocket.send_json({
                        "type": "soap_note",
                        "soap_note": soap_note.model_dump()
                    })
                    
                    break
                    
    except WebSocketDisconnect:
        logger.info("websocket_disconnected", session_id=session_id)
        await get_db().update_session(session_id, {
            "status": SessionStatus.ERROR
        })
    except Exception as e:
        logger.error("websocket_error", session_id=session_id, error=str(e))
        await websocket.send_json({
            "type": "error",
            "message": str(e)
        })


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(
    session_id: str,
    audio: UploadFile = File(...),
    background_tasks: BackgroundTasks = None
):
    """
    HTTP endpoint for audio file transcription.
    Use WebSocket for real-time streaming.
    """
    audio_data = await audio.read()
    
    start_time = time.time()
    result = await get_asr_pipeline().transcribe(audio_data)
    
    # Update session in background
    if background_tasks:
        background_tasks.add_task(
            get_db().update_session,
            session_id,
            {
                "transcript": result["transcript"],
                "status": SessionStatus.PROCESSING
            }
        )
    
    return TranscriptionResponse(
        session_id=session_id,
        transcript=result["transcript"],
        segments=result["segments"],
        language=result["language"],
        confidence=result["confidence"]
    )


@router.post("/generate-soap", response_model=SOAPGenerationResponse)
async def generate_soap(request: SOAPGenerationRequest):
    """Generate SOAP note from transcript."""
    start_time = time.time()
    
    # Extract entities
    entities = await get_nlp_pipeline().extract_entities(request.transcript)
    
    # Generate SOAP
    soap = await get_llm_service().generate_soap_note(
        transcript=request.transcript,
        entities=entities,
        patient_context=request.patient_context
    )
    
    # Save
    await get_db().save_soap_note(request.session_id, soap)
    
    processing_time = int((time.time() - start_time) * 1000)
    
    return SOAPGenerationResponse(
        session_id=request.session_id,
        soap_note=soap,
        processing_time_ms=processing_time,
        model_version="llama3-70b"
    )


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session details including transcript and SOAP note."""
    session = await get_db().get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/patients/{patient_id}/notes")
async def get_patient_notes(patient_id: str, limit: int = 10):
    """Get all SOAP notes for a patient."""
    notes = await get_db().get_patient_notes(patient_id, limit)
    return {"patient_id": patient_id, "notes": notes}
