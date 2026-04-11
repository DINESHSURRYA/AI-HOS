"""Clinical NLP pipeline for entity extraction using BioClinicalBERT."""
import spacy
import scispacy
from transformers import AutoTokenizer, AutoModelForTokenClassification
from transformers import pipeline
from typing import List, Dict, Any, Optional
import re
from app.models.schemas import ClinicalEntity, EntityType
from app.core.config import settings
import structlog
import asyncio
from concurrent.futures import ThreadPoolExecutor

logger = structlog.get_logger()


class ClinicalNLPPipeline:
    """
    Extracts clinical entities using:
    1. scispaCy for medical NER
    2. BioClinicalBERT for diagnosis coding
    3. Med7 for medication extraction
    4. Rule-based procedure detection
    """
    
    def __init__(self):
        self.nlp = None
        self.diagnosis_pipeline = None
        self.med7_nlp = None
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._load_models()
    
    def _load_models(self):
        """Load all NLP models."""
        logger.info("loading_nlp_models")
        
        # 1. scispaCy for general biomedical NER
        try:
            self.nlp = spacy.load("en_core_sci_sm")
            logger.info("scispacy_model_loaded")
        except Exception as e:
            logger.error("scispacy_load_failed", error=str(e))
            self.nlp = spacy.load("en_core_web_sm")
        
        # 2. BioClinicalBERT for diagnosis extraction
        try:
            self.diagnosis_pipeline = pipeline(
                "token-classification",
                model="samrawal/bert-base-uncased_clinical-ner",
                aggregation_strategy="simple",
                device=0 if settings.WHISPER_DEVICE == "cuda" else -1
            )
            logger.info("bioclinicalbert_loaded")
        except Exception as e:
            logger.error("bioclinicalbert_load_failed", error=str(e))
            self.diagnosis_pipeline = None
        
        # 3. Med7 for medications
        try:
            self.med7_nlp = spacy.load("en_core_med7_lg")
            logger.info("med7_loaded")
        except Exception as e:
            logger.warning("med7_load_failed", error=str(e))
            self.med7_nlp = None
    
    async def extract_entities(self, text: str) -> List[ClinicalEntity]:
        """
        Extract all clinical entities from text.
        
        Returns list of entities with standardized codes.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._sync_extract_entities,
            text
        )
    
    def _sync_extract_entities(self, text: str) -> List[ClinicalEntity]:
        """Synchronous entity extraction."""
        entities = []
        
        # 1. Extract diagnoses using BioClinicalBERT
        diagnoses = self._extract_diagnoses(text)
        entities.extend(diagnoses)
        
        # 2. Extract medications using Med7
        medications = self._extract_medications(text)
        entities.extend(medications)
        
        # 3. Extract procedures using rules
        procedures = self._extract_procedures(text)
        entities.extend(procedures)
        
        # 4. Extract symptoms using scispaCy
        symptoms = self._extract_symptoms(text)
        entities.extend(symptoms)
        
        # Deduplicate by position
        seen = set()
        unique_entities = []
        for ent in sorted(entities, key=lambda x: x.start):
            key = (ent.start, ent.end)
            if key not in seen:
                seen.add(key)
                unique_entities.append(ent)
        
        return unique_entities
    
    def _extract_diagnoses(self, text: str) -> List[ClinicalEntity]:
        """Extract diagnoses and map to ICD-10."""
        entities = []
        
        if self.diagnosis_pipeline:
            results = self.diagnosis_pipeline(text)
            for res in results:
                if res["entity_group"] in ["PROBLEM", "DIAGNOSIS"]:
                    entity = ClinicalEntity(
                        text=res["word"],
                        entity_type=EntityType.DIAGNOSIS,
                        start=res["start"],
                        end=res["end"],
                        confidence=res["score"],
                        icd10=self._map_to_icd10(res["word"])
                    )
                    entities.append(entity)
        
        # Fallback: Common diagnosis patterns
        patterns = [
            (r"\b(diabetes|type\s+\d\s+diabetes|diabetic)\b", "E11.9"),
            (r"\b(hypertension|high\s+blood\s+pressure)\b", "I10"),
            (r"\b(asthma)\b", "J45.9"),
            (r"\b(depression|major\s+depressive)\b", "F32.9"),
            (r"\b(anxiety|generalized\s+anxiety)\b", "F41.1"),
            (r"\b(copd|chronic\s+obstructive)\b", "J44.9"),
            (r"\b(chf|congestive\s+heart\s+failure)\b", "I50.9"),
            (r"\b(osteoarthritis|oa)\b", "M19.90"),
        ]
        
        for pattern, default_icd in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                # Check if not already extracted
                if not any(e.start == match.start() for e in entities):
                    entities.append(ClinicalEntity(
                        text=match.group(),
                        entity_type=EntityType.DIAGNOSIS,
                        start=match.start(),
                        end=match.end(),
                        confidence=0.8,
                        icd10=default_icd
                    ))
        
        return entities
    
    def _extract_medications(self, text: str) -> List[ClinicalEntity]:
        """Extract medications using Med7."""
        entities = []
        
        if self.med7_nlp:
            doc = self.med7_nlp(text)
            for ent in doc.ents:
                if ent.label_ in ["DRUG", "MEDICATION"]:
                    entities.append(ClinicalEntity(
                        text=ent.text,
                        entity_type=EntityType.MEDICATION,
                        start=ent.start_char,
                        end=ent.end_char,
                        confidence=0.9,
                        rxnorm=self._map_to_rxnorm(ent.text)
                    ))
        
        return entities
    
    def _extract_procedures(self, text: str) -> List[ClinicalEntity]:
        """Extract procedures using keyword matching."""
        entities = []
        
        procedure_keywords = {
            "mri": ("73706", "Imaging"),
            "ct scan": ("74150", "Imaging"),
            "x-ray": ("73060", "Imaging"),
            "ultrasound": ("76700", "Imaging"),
            "biopsy": ("11100", "Procedure"),
            "surgery": ("44970", "Surgery"),
            "laparoscopy": ("49320", "Surgery"),
            "colonoscopy": ("45378", "Procedure"),
            "endoscopy": ("43235", "Procedure"),
            "echocardiogram": ("93306", "Cardiology"),
            "eeg": ("95816", "Neurology"),
            "ekg": ("93000", "Cardiology"),
        }
        
        for keyword, (cpt, category) in procedure_keywords.items():
            for match in re.finditer(rf"\b{keyword}\w*\b", text, re.IGNORECASE):
                entities.append(ClinicalEntity(
                    text=match.group(),
                    entity_type=EntityType.PROCEDURE,
                    start=match.start(),
                    end=match.end(),
                    confidence=0.85,
                    cpt=cpt
                ))
        
        return entities
    
    def _extract_symptoms(self, text: str) -> List[ClinicalEntity]:
        """Extract symptoms using scispaCy."""
        entities = []
        
        doc = self.nlp(text)
        for ent in doc.ents:
            # Filter for symptom-like entities
            if any(term in ent.text.lower() for term in [
                "pain", "ache", "fever", "cough", "nausea", 
                "vomiting", "fatigue", "dizziness", "rash"
            ]):
                entities.append(ClinicalEntity(
                    text=ent.text,
                    entity_type=EntityType.SYMPTOM,
                    start=ent.start_char,
                    end=ent.end_char,
                    confidence=0.75
                ))
        
        return entities
    
    def _map_to_icd10(self, text: str) -> Optional[str]:
        """Map diagnosis text to ICD-10 code."""
        # Simplified mapping - in production use UMLS API
        mappings = {
            "diabetes": "E11.9",
            "hypertension": "I10",
            "asthma": "J45.9",
            "depression": "F32.9",
            "copd": "J44.9",
            "chf": "I50.9",
            "osteoarthritis": "M17.11",
        }
        text_lower = text.lower()
        for key, code in mappings.items():
            if key in text_lower:
                return code
        return None
    
    def _map_to_rxnorm(self, text: str) -> Optional[str]:
        """Map medication to RxNorm code."""
        # Simplified - use RxNorm API in production
        return None  # Placeholder


# Singleton
_nlp_pipeline = None

def get_nlp_pipeline() -> ClinicalNLPPipeline:
    """Get or create NLP pipeline."""
    global _nlp_pipeline
    if _nlp_pipeline is None:
        _nlp_pipeline = ClinicalNLPPipeline()
    return _nlp_pipeline
