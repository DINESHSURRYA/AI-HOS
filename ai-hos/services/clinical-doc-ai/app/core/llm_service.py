"""LLM service for SOAP note generation using local Llama 3."""
from openai import AsyncOpenAI
from typing import Dict, Any, List, Optional
from app.models.schemas import SOAPNote, ClinicalEntity
from app.core.config import settings
import structlog
import json

logger = structlog.get_logger()


class LLMService:
    """
    Generates SOAP notes using local LLM (Ollama/vLLM).
    Optimized for clinical accuracy and structured output.
    """
    
    def __init__(self):
        self.client = AsyncOpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY
        )
        self.model = settings.LLM_MODEL
    
    async def generate_soap_note(
        self,
        transcript: str,
        entities: List[ClinicalEntity],
        patient_context: Optional[Dict[str, Any]] = None
    ) -> SOAPNote:
        """
        Generate structured SOAP note from transcript.
        
        Args:
            transcript: Doctor-patient conversation
            entities: Extracted clinical entities
            patient_context: FHIR Patient resource data
            
        Returns:
            Structured SOAPNote object
        """
        
        # Build prompt with few-shot examples
        system_prompt = """You are a clinical documentation assistant. Your task is to convert doctor-patient conversation transcripts into structured SOAP notes.

Rules:
1. Be concise and clinically precise
2. Use standard medical terminology
3. Include all relevant diagnoses and medications mentioned
4. Note any allergies or contraindications
5. Format exactly as requested
6. Do NOT include patient identifiers (names, MRN, SSN)
7. Use third-person objective tone for Objective section"""

        # Format entities for context
        diagnoses = [e for e in entities if e.entity_type.value == "diagnosis"]
        medications = [e for e in entities if e.entity_type.value == "medication"]
        procedures = [e for e in entities if e.entity_type.value == "procedure"]
        
        user_prompt = f"""Transcript:
{transcript}

Extracted Information:
- Diagnoses: {[f"{d.text} ({d.icd10})" for d in diagnoses]}
- Medications: {[m.text for m in medications]}
- Procedures: {[p.text for p in procedures]}

Generate a SOAP note with these exact sections:

SUBJECTIVE:
[Patient's reported symptoms, history, concerns]

OBJECTIVE:
[Physical exam findings, vital signs, test results]

ASSESSMENT:
[Diagnoses with reasoning, differential diagnoses if relevant]

PLAN:
[Treatment plan, medications prescribed, follow-up instructions, patient education]

Output as JSON:
{{
    "subjective": "...",
    "objective": "...",
    "assessment": "...",
    "plan": "..."
}}"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            parsed = json.loads(content)
            
            # Validate and construct SOAP note
            soap = SOAPNote(
                subjective=parsed.get("subjective", ""),
                objective=parsed.get("objective", ""),
                assessment=parsed.get("assessment", ""),
                plan=parsed.get("plan", ""),
                entities=entities,
                confidence_score=self._calculate_confidence(entities)
            )
            
            logger.info(
                "soap_note_generated",
                model=self.model,
                confidence=soap.confidence_score
            )
            
            return soap
            
        except Exception as e:
            logger.error("soap_generation_failed", error=str(e))
            # Return fallback SOAP note
            return self._fallback_soap(transcript, entities)
    
    def _calculate_confidence(self, entities: List[ClinicalEntity]) -> float:
        """Calculate overall confidence based on entity extraction."""
        if not entities:
            return 0.5
        
        avg_conf = sum(e.confidence for e in entities) / len(entities)
        # Boost confidence if we have structured codes
        code_bonus = 0.1 if any(e.icd10 for e in entities) else 0
        return min(0.95, avg_conf + code_bonus)
    
    def _fallback_soap(
        self, 
        transcript: str, 
        entities: List[ClinicalEntity]
    ) -> SOAPNote:
        """Generate basic SOAP note if LLM fails."""
        return SOAPNote(
            subjective="See transcript for details.",
            objective="See transcript for details.",
            assessment="Clinical assessment based on patient presentation.",
            plan="Follow standard clinical protocols.",
            entities=entities,
            confidence_score=0.3
        )


# Singleton
_llm_service = None

def get_llm_service() -> LLMService:
    """Get or create LLM service."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
