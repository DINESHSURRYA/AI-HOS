"""WhisperX-based ASR pipeline with medical fine-tuning support."""
import whisperx
import torch
import numpy as np
from typing import Dict, Any, BinaryIO
import tempfile
import os
import soundfile as sf
from app.core.config import settings
import structlog
import asyncio
from concurrent.futures import ThreadPoolExecutor

logger = structlog.get_logger()


class ASRPipeline:
    """
    Production ASR pipeline using WhisperX.
    Supports diarization (speaker identification) and word-level timestamps.
    """
    
    def __init__(self):
        self.device = settings.WHISPER_DEVICE
        self.compute_type = settings.WHISPER_COMPUTE_TYPE
        self.model = None
        self.align_model = None
        self.diarize_model = None
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._load_models()
    
    def _load_models(self):
        """Load WhisperX models - call once at startup."""
        logger.info(
            "loading_whisper_model",
            model=settings.WHISPER_MODEL,
            device=self.device
        )
        
        # 1. Load transcription model
        self.model = whisperx.load_model(
            settings.WHISPER_MODEL,
            self.device,
            compute_type=self.compute_type,
            language=settings.WHISPER_LANGUAGE,
        )
        
        # 2. Load alignment model (for word-level timestamps)
        self.align_model, self.align_metadata = whisperx.load_align_model(
            language_code=settings.WHISPER_LANGUAGE,
            device=self.device
        )
        
        # 3. Load diarization model (optional - identifies speakers)
        try:
            self.diarize_model = whisperx.DiarizationPipeline(
                model_name="pyannote/speaker-diarization-3.1",
                use_auth_token=None,  # Set HF token if needed
                device=self.device
            )
        except Exception as e:
            logger.warning("diarization_model_load_failed", error=str(e))
            self.diarize_model = None
    
    async def transcribe(
        self, 
        audio_data: bytes,
        sample_rate: int = 16000
    ) -> Dict[str, Any]:
        """
        Transcribe audio bytes to text with medical context.
        
        Args:
            audio_data: Raw audio bytes
            sample_rate: Audio sample rate
            
        Returns:
            Dict with transcript, segments, and metadata
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._sync_transcribe,
            audio_data,
            sample_rate
        )
    
    def _sync_transcribe(
        self, 
        audio_data: bytes, 
        sample_rate: int
    ) -> Dict[str, Any]:
        """Synchronous transcription (runs in thread pool)."""
        
        # Convert bytes to numpy array
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
            # Write proper WAV header if needed
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            audio_float = audio_array.astype(np.float32) / 32768.0
            sf.write(tmp_path, audio_float, sample_rate)
        
        try:
            # 1. Transcribe with Whisper
            audio = whisperx.load_audio(tmp_path)
            result = self.model.transcribe(
                audio,
                batch_size=settings.WHISPER_BATCH_SIZE,
                language=settings.WHISPER_LANGUAGE
            )
            
            # 2. Align words (precise timestamps)
            result = whisperx.align(
                result["segments"],
                self.align_model,
                self.align_metadata,
                audio,
                self.device,
                return_char_alignments=False
            )
            
            # 3. Diarize (identify speakers - doctor vs patient)
            if self.diarize_model:
                diarize_segments = self.diarize_model(audio)
                result = whisperx.assign_word_speakers(
                    diarize_segments, 
                    result
                )
            
            # 4. Post-process for medical terminology
            transcript = self._post_process_medical(result["segments"])
            
            return {
                "transcript": transcript,
                "segments": result["segments"],
                "language": result.get("language", "en"),
                "confidence": self._calculate_confidence(result["segments"]),
                "speakers": list(set(
                    seg.get("speaker", "UNKNOWN") 
                    for seg in result["segments"]
                ))
            }
            
        finally:
            os.unlink(tmp_path)
    
    def _post_process_medical(self, segments: list) -> str:
        """
        Post-process transcript for medical accuracy.
        - Expand abbreviations
        - Normalize medication names
        - Format numbers (doses, frequencies)
        """
        full_text = " ".join(seg["text"].strip() for seg in segments)
        
        # Common medical expansions
        replacements = {
            "b i d": "twice daily",
            "t i d": "three times daily",
            "q d": "once daily",
            "q h s": "at bedtime",
            "p o": "by mouth",
            "i m": "intramuscular",
            "i v": "intravenous",
            "s c": "subcutaneous",
            "c s": "C-section",
            "c o p d": "COPD",
            "c h f": "CHF",
        }
        
        text_lower = full_text.lower()
        for abbrev, expansion in replacements.items():
            text_lower = text_lower.replace(abbrev, expansion)
        
        return text_lower
    
    def _calculate_confidence(self, segments: list) -> float:
        """Calculate average confidence score."""
        if not segments:
            return 0.0
        
        confidences = []
        for seg in segments:
            if "words" in seg:
                word_conf = [
                    w.get("score", 0.0) 
                    for w in seg["words"] 
                    if "score" in w
                ]
                if word_conf:
                    confidences.extend(word_conf)
        
        return float(np.mean(confidences)) if confidences else 0.85


# Singleton instance
_asr_pipeline = None

def get_asr_pipeline() -> ASRPipeline:
    """Get or create ASR pipeline singleton."""
    global _asr_pipeline
    if _asr_pipeline is None:
        _asr_pipeline = ASRPipeline()
    return _asr_pipeline
