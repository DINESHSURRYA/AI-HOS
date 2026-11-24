"""Hybrid ASR pipeline supporting WhisperX (when installed) and safe local fallback."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import io
import os
import re
import tempfile
from typing import Any, Dict, List, Tuple
import wave
import structlog

from app.core.config import settings

logger = structlog.get_logger()

MEDICAL_ABBREVIATIONS: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bb\s*i\s*d\b", re.IGNORECASE), "twice daily"),
    (re.compile(r"\bt\s*i\s*d\b", re.IGNORECASE), "three times daily"),
    (re.compile(r"\bq\s*i\s*d\b", re.IGNORECASE), "four times daily"),
    (re.compile(r"\bq\s*d\b", re.IGNORECASE), "once daily"),
    (re.compile(r"\bq\s*h\s*s\b", re.IGNORECASE), "at bedtime"),
    (re.compile(r"\bp\s*r\s*n\b", re.IGNORECASE), "as needed"),
    (re.compile(r"\bp\s*o\b", re.IGNORECASE), "by mouth"),
    (re.compile(r"\bi\s*m\b", re.IGNORECASE), "intramuscular"),
    (re.compile(r"\bi\s*v\b", re.IGNORECASE), "intravenous"),
    (re.compile(r"\bs\s*c\b", re.IGNORECASE), "subcutaneous"),
    (re.compile(r"\bc\s*o\s*p\s*d\b", re.IGNORECASE), "COPD"),
    (re.compile(r"\bc\s*h\s*f\b", re.IGNORECASE), "CHF"),
    (re.compile(r"\be\s*k\s*g\b", re.IGNORECASE), "EKG"),
    (re.compile(r"\bm\s*r\s*i\b", re.IGNORECASE), "MRI"),
    (re.compile(r"\bh\s*t\s*n\b", re.IGNORECASE), "hypertension"),
    (re.compile(r"\bn\s*k\s*d\s*a\b", re.IGNORECASE), "no known drug allergies"),
]


class ASRPipeline:
    """
    Production ASR pipeline using optional WhisperX with safe local fallback.
    Handles WAV/WebM/MP3 uploads and medical abbreviation normalization.
    """

    def __init__(self) -> None:
        self.device = settings.WHISPER_DEVICE
        self.compute_type = settings.WHISPER_COMPUTE_TYPE
        self.model = None
        self.align_model = None
        self.align_metadata = None
        self.diarize_model = None
        self.engine_name = "local-fallback"
        self._whisperx = None
        self._executor = ThreadPoolExecutor(max_workers=2)
        if settings.ENABLE_WHISPERX:
            self._try_load_whisperx()

    def _try_load_whisperx(self) -> None:
        """Attempt to load WhisperX if installed in this environment."""
        try:
            import whisperx  # type: ignore

            logger.info(
                "loading_whisper_model",
                model=settings.WHISPER_MODEL,
                device=self.device,
            )
            self._whisperx = whisperx
            self.model = whisperx.load_model(
                settings.WHISPER_MODEL,
                self.device,
                compute_type=self.compute_type,
                language=settings.WHISPER_LANGUAGE,
            )
            self.align_model, self.align_metadata = whisperx.load_align_model(
                language_code=settings.WHISPER_LANGUAGE,
                device=self.device,
            )
            self.engine_name = f"whisperx-{settings.WHISPER_MODEL}"
            logger.info("whisperx_loaded", engine=self.engine_name)
        except Exception as exc:
            logger.warning(
                "whisperx_unavailable_using_fallback",
                error=str(exc),
            )
            self.model = None
            self.engine_name = "local-fallback"

    async def transcribe(
        self,
        audio_data: bytes,
        sample_rate: int = 16000,
        filename: str = "audio.webm",
    ) -> Dict[str, Any]:
        """Transcribe uploaded or streamed audio bytes."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            self._sync_transcribe,
            audio_data,
            sample_rate,
            filename,
        )

    def _sync_transcribe(
        self,
        audio_data: bytes,
        sample_rate: int,
        filename: str,
    ) -> Dict[str, Any]:
        if self.model is not None and self._whisperx is not None:
            return self._transcribe_with_whisperx(audio_data, filename)

        duration = self._estimate_duration(audio_data, sample_rate)
        fallback_transcript = (
            f"Audio encounter captured ({duration:.1f}s, {len(audio_data)} bytes). "
            "WhisperX GPU/CPU ASR is disabled in lightweight local mode. "
            "Use live browser dictation (Web Speech API) or paste/edit the clinical transcript "
            "directly to generate a coded SOAP note."
        )
        return {
            "transcript": fallback_transcript,
            "segments": [
                {
                    "start": 0.0,
                    "end": round(duration, 2),
                    "text": fallback_transcript,
                    "speaker": "CLINICIAN",
                }
            ],
            "language": settings.WHISPER_LANGUAGE,
            "confidence": 0.85,
            "speakers": ["CLINICIAN"],
            "engine": self.engine_name,
        }

    def _transcribe_with_whisperx(
        self,
        audio_data: bytes,
        filename: str,
    ) -> Dict[str, Any]:
        suffix = os.path.splitext(filename)[1] or ".webm"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_data)
            tmp_path = tmp.name

        try:
            audio = self._whisperx.load_audio(tmp_path)
            result = self.model.transcribe(
                audio,
                batch_size=settings.WHISPER_BATCH_SIZE,
                language=settings.WHISPER_LANGUAGE,
            )
            if self.align_model is not None:
                result = self._whisperx.align(
                    result["segments"],
                    self.align_model,
                    self.align_metadata,
                    audio,
                    self.device,
                    return_char_alignments=False,
                )

            segments = result.get("segments", [])
            transcript = self.post_process_medical(
                " ".join(seg.get("text", "").strip() for seg in segments)
            )
            return {
                "transcript": transcript,
                "segments": segments,
                "language": result.get("language", settings.WHISPER_LANGUAGE),
                "confidence": self._calculate_confidence(segments),
                "speakers": sorted(
                    {seg.get("speaker", "SPEAKER_00") for seg in segments}
                ),
                "engine": self.engine_name,
            }
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def post_process_medical(self, text: str) -> str:
        """Expand spaced clinical dictation abbreviations while preserving readability."""
        cleaned = re.sub(r"\s+", " ", text).strip()
        for pattern, replacement in MEDICAL_ABBREVIATIONS:
            cleaned = pattern.sub(replacement, cleaned)
        return cleaned

    def _estimate_duration(self, audio_data: bytes, sample_rate: int) -> float:
        if not audio_data:
            return 0.0
        # Check if valid WAV container
        if audio_data[:4] == b"RIFF":
            try:
                with wave.open(io.BytesIO(audio_data), "rb") as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate() or sample_rate
                    return frames / float(rate)
            except Exception:
                pass
        # Rough fallback estimate (~16 KB/sec for compressed WebM Opus or 32 KB/sec for 16kHz PCM)
        return max(1.0, len(audio_data) / 16000.0)

    def _calculate_confidence(self, segments: List[Dict[str, Any]]) -> float:
        scores: List[float] = []
        for seg in segments:
            for word in seg.get("words", []):
                if "score" in word:
                    scores.append(float(word["score"]))
        if not scores:
            return 0.88
        return round(sum(scores) / len(scores), 3)


_asr_pipeline: ASRPipeline | None = None


def get_asr_pipeline() -> ASRPipeline:
    """Get or create ASR pipeline singleton."""
    global _asr_pipeline
    if _asr_pipeline is None:
        _asr_pipeline = ASRPipeline()
    return _asr_pipeline
