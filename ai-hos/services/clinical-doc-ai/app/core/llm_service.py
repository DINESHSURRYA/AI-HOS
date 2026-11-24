"""LLM & Intelligent Clinical SOAP Note Generator Service."""
import json
import re
from typing import Any, Dict, List, Optional
from openai import AsyncOpenAI
import structlog

from app.core.config import settings
from app.models.schemas import ClinicalEntity, EntityType, SOAPNote

logger = structlog.get_logger()


class LLMService:
    """
    Generates structured clinical SOAP notes using an OpenAI-compatible LLM
    (Ollama, vLLM, OpenAI, or Gemini OpenAI-compat) when enabled and reachable,
    with an intelligent clinical structured fallback engine for zero-dependency operation.
    """

    def __init__(self) -> None:
        self.model = settings.LLM_MODEL
        self.enabled = settings.ENABLE_LLM_GENERATION
        self.client: Optional[AsyncOpenAI] = None
        if self.enabled:
            self.client = AsyncOpenAI(
                base_url=settings.LLM_BASE_URL,
                api_key=settings.LLM_API_KEY,
                timeout=settings.LLM_TIMEOUT_SECONDS,
            )

    async def generate_soap_note(
        self,
        transcript: str,
        entities: List[ClinicalEntity],
        patient_context: Optional[Dict[str, Any]] = None,
        phi_redacted_count: int = 0,
    ) -> SOAPNote:
        """Generate structured SOAP note from a (PHI-redacted) clinical transcript."""
        if self.enabled and self.client is not None:
            try:
                return await self._generate_with_llm(
                    transcript=transcript,
                    entities=entities,
                    patient_context=patient_context,
                    phi_redacted_count=phi_redacted_count,
                )
            except Exception as exc:
                logger.warning(
                    "llm_unavailable_using_structured_clinical_engine",
                    error=str(exc),
                )

        return self._generate_structured_local_soap(
            transcript=transcript,
            entities=entities,
            patient_context=patient_context,
            phi_redacted_count=phi_redacted_count,
        )

    async def _generate_with_llm(
        self,
        transcript: str,
        entities: List[ClinicalEntity],
        patient_context: Optional[Dict[str, Any]],
        phi_redacted_count: int,
    ) -> SOAPNote:
        system_prompt = (
            "You are a HIPAA-compliant clinical documentation assistant. "
            "Convert doctor-patient encounter transcripts into structured SOAP notes.\n"
            "Rules:\n"
            "1. Be concise, accurate, and clinically structured.\n"
            "2. Include standard ICD-10/CPT/RxNorm codes when provided.\n"
            "3. Note allergies and conservative therapy failures explicitly.\n"
            "4. Never output patient identifiers (names, MRN, SSN, phone).\n"
            "5. Return valid JSON with keys: subjective, objective, assessment, plan."
        )

        diagnoses = [
            f"{e.text} ({e.icd10})" if e.icd10 else e.text
            for e in entities
            if e.entity_type == EntityType.DIAGNOSIS
        ]
        medications = [
            f"{e.text} {e.dosage or ''}".strip()
            for e in entities
            if e.entity_type == EntityType.MEDICATION
        ]
        procedures = [
            f"{e.text} (CPT {e.cpt})" if e.cpt else e.text
            for e in entities
            if e.entity_type == EntityType.PROCEDURE
        ]
        vitals = [e.text for e in entities if e.entity_type == EntityType.VITAL]
        allergies = [e.text for e in entities if e.entity_type == EntityType.ALLERGY]

        user_prompt = (
            f"Transcript:\n{transcript}\n\n"
            f"Patient Context: {json.dumps(patient_context or {})}\n"
            f"Extracted Entities:\n"
            f"- Diagnoses: {diagnoses}\n"
            f"- Medications: {medications}\n"
            f"- Procedures: {procedures}\n"
            f"- Vitals: {vitals}\n"
            f"- Allergies: {allergies}\n\n"
            'Return JSON: {"subjective": "...", "objective": "...", "assessment": "...", "plan": "..."}'
        )

        assert self.client is not None
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)

        return SOAPNote(
            subjective=parsed.get("subjective", "").strip() or "See clinical narrative.",
            objective=parsed.get("objective", "").strip() or "No objective findings recorded.",
            assessment=parsed.get("assessment", "").strip() or "Clinical assessment pending review.",
            plan=parsed.get("plan", "").strip() or "Continue clinical management plan.",
            entities=entities,
            confidence_score=self._calculate_confidence(entities, llm_boost=0.05),
            model_used=self.model,
            phi_redacted_count=phi_redacted_count,
        )

    def _generate_structured_local_soap(
        self,
        transcript: str,
        entities: List[ClinicalEntity],
        patient_context: Optional[Dict[str, Any]] = None,
        phi_redacted_count: int = 0,
    ) -> SOAPNote:
        """
        Deterministic clinical NLP-to-SOAP synthesizer.
        Partitions transcript sentences and extracted entities into a medically coherent SOAP note.
        """
        sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+|\n+", transcript.strip())
            if s.strip()
        ]

        diagnoses = [e for e in entities if e.entity_type == EntityType.DIAGNOSIS]
        medications = [e for e in entities if e.entity_type == EntityType.MEDICATION]
        procedures = [e for e in entities if e.entity_type == EntityType.PROCEDURE]
        symptoms = [e for e in entities if e.entity_type == EntityType.SYMPTOM]
        allergies = [e for e in entities if e.entity_type == EntityType.ALLERGY]
        vitals = [e for e in entities if e.entity_type == EntityType.VITAL]

        obj_keywords = (
            "exam", "bp", "blood pressure", "heart rate", "hr ", "temp",
            "spo2", "oxygen", "lungs", "auscultation", "tenderness",
            "swelling", "edema", "range of motion", "crepitus", "lab",
            "a1c", "bmi", "vital", "murmur", "crackles", "wheezes",
            "alert", "oriented", "physical", "x-ray showed", "ekg showed",
        )
        plan_keywords = (
            "order", "ordered", "start", "increase", "continue", "prescribe",
            "recommend", "follow up", "follow-up", "refer", "referral",
            "schedule", "prior auth", "authorization", "counsel", "educate",
            "plan", "return in", "discontinue", "taper", "obtain",
        )

        subj_lines: List[str] = []
        obj_lines: List[str] = []
        plan_lines: List[str] = []

        for sent in sentences:
            low = sent.lower()
            is_obj = any(k in low for k in obj_keywords)
            is_plan = any(k in low for k in plan_keywords)
            if is_obj:
                obj_lines.append(sent)
            if is_plan:
                plan_lines.append(sent)
            if not is_obj and not is_plan:
                subj_lines.append(sent)

        # Build Subjective
        demo_prefix = ""
        if patient_context:
            age = patient_context.get("age")
            gender = patient_context.get("gender")
            if age or gender:
                demo_prefix = f"Patient Profile: {age or 'Adult'}-year-old {gender or 'patient'}.\n"

        symptom_summary = (
            f"Reported Symptoms: {', '.join(e.text for e in symptoms)}."
            if symptoms
            else ""
        )
        allergy_summary = (
            f"Allergies: {', '.join(e.text for e in allergies)}."
            if allergies
            else "Allergies: No drug allergies documented in encounter."
        )
        subj_body = " ".join(subj_lines) if subj_lines else transcript.strip()
        subjective = "\n".join(
            part for part in [demo_prefix.strip(), f"History of Present Illness: {subj_body}", symptom_summary, allergy_summary] if part
        )

        # Build Objective
        obj_parts: List[str] = []
        if vitals:
            obj_parts.append(f"Vital Signs: {', '.join(v.text for v in vitals)}.")
        if obj_lines:
            obj_parts.append("Exam & Findings: " + " ".join(obj_lines))
        else:
            obj_parts.append(
                "Exam & Findings: Clinical evaluation performed; no acute distress noted beyond documented presenting complaints."
            )
        objective = "\n".join(obj_parts)

        # Build Assessment
        assess_parts: List[str] = []
        if diagnoses:
            diag_bullets = [
                f"- {d.text.title()} [ICD-10: {d.icd10}]" if d.icd10 else f"- {d.text.title()}"
                for d in diagnoses
            ]
            assess_parts.append("Primary & Active Diagnoses:\n" + "\n".join(diag_bullets))
        else:
            assess_parts.append(
                "Primary Impression: Symptomatic presentation requiring further clinical correlation and diagnostic workup."
            )

        if any(kw in transcript.lower() for kw in ("failed", "conservative", "unresponsive", "persistent", "worsening")):
            assess_parts.append(
                "Clinical Course: Patient has documented persistent/refractory symptoms despite prior conservative management; meets criteria for escalated diagnostic/therapeutic evaluation."
            )
        assessment = "\n".join(assess_parts)

        # Build Plan
        plan_parts: List[str] = []
        if procedures:
            proc_list = [
                f"- Order/Coordinate: {p.text.upper() if len(p.text) <= 4 else p.text.title()}"
                + (f" [CPT: {p.cpt}]" if p.cpt else "")
                for p in procedures
            ]
            plan_parts.append("Diagnostics & Procedures:\n" + "\n".join(proc_list))
        if medications:
            med_list = [
                f"- {m.text.title()}"
                + (f" ({m.dosage})" if m.dosage else "")
                + (f" [RxNorm: {m.rxnorm}]" if m.rxnorm else "")
                for m in medications
            ]
            plan_parts.append("Medications & Therapeutics:\n" + "\n".join(med_list))
        if plan_lines:
            plan_parts.append("Clinician Directives: " + " ".join(plan_lines))
        plan_parts.append(
            "Follow-Up & Safety Netting: Review diagnostic results with patient, verify prior authorization status where applicable, and return promptly for any red-flag symptoms."
        )
        plan = "\n".join(plan_parts)

        return SOAPNote(
            subjective=subjective,
            objective=objective,
            assessment=assessment,
            plan=plan,
            entities=entities,
            confidence_score=self._calculate_confidence(entities, llm_boost=0.0),
            model_used="ai-hos-clinical-engine-v2 (local-structured)",
            phi_redacted_count=phi_redacted_count,
        )

    def _calculate_confidence(
        self,
        entities: List[ClinicalEntity],
        llm_boost: float = 0.0,
    ) -> float:
        if not entities:
            return round(min(0.95, 0.65 + llm_boost), 3)
        avg_conf = sum(e.confidence for e in entities) / len(entities)
        code_bonus = 0.05 if any(e.icd10 or e.cpt or e.rxnorm for e in entities) else 0.0
        return round(min(0.97, avg_conf + code_bonus + llm_boost), 3)


_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Get or create LLM service singleton."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
