"""Hybrid Clinical NLP pipeline for medical entity extraction and coding (ICD-10, RxNorm, CPT)."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import re
from typing import Dict, List, Optional, Tuple
import structlog

from app.core.config import settings
from app.models.schemas import ClinicalEntity, EntityType

logger = structlog.get_logger()

# Curated ICD-10-CM diagnosis lexicon: (regex, icd10_code, confidence)
DIAGNOSIS_PATTERNS: List[Tuple[str, str, float]] = [
    (r"\b(?:left\s+knee\s+osteoarthritis|osteoarthritis\s+of\s+(?:the\s+)?left\s+knee)\b", "M17.12", 0.94),
    (r"\b(?:right\s+knee\s+osteoarthritis|osteoarthritis\s+of\s+(?:the\s+)?right\s+knee)\b", "M17.11", 0.94),
    (r"\b(?:knee\s+osteoarthritis|osteoarthritis|degenerative\s+joint\s+disease)\b", "M17.11", 0.90),
    (r"\b(?:lumbar\s+radiculopathy|lumbar\s+disc\s+herniation|sciatica)\b", "M54.16", 0.91),
    (r"\b(?:chronic\s+low\s+back\s+pain|low\s+back\s+pain|lumbago)\b", "M54.50", 0.89),
    (r"\b(?:type\s*2\s+diabetes(?:\s+mellitus)?|t2dm|diabetes\s+mellitus)\b", "E11.9", 0.94),
    (r"\b(?:type\s*1\s+diabetes(?:\s+mellitus)?|t1dm)\b", "E10.9", 0.94),
    (r"\b(?:diabetes|diabetic)\b", "E11.9", 0.88),
    (r"\b(?:essential\s+hypertension|hypertension|high\s+blood\s+pressure|htn)\b", "I10", 0.93),
    (r"\b(?:hyperlipidemia|dyslipidemia|high\s+cholesterol)\b", "E78.5", 0.91),
    (r"\b(?:congestive\s+heart\s+failure|heart\s+failure|chf|hfref|hfpef)\b", "I50.9", 0.94),
    (r"\b(?:atrial\s+fibrillation|a-?fib|afib)\b", "I48.91", 0.93),
    (r"\b(?:coronary\s+artery\s+disease|cad)\b", "I25.10", 0.92),
    (r"\b(?:copd\s+exacerbation|acute\s+exacerbation\s+of\s+copd)\b", "J44.1", 0.95),
    (r"\b(?:copd|chronic\s+obstructive\s+pulmonary\s+disease)\b", "J44.9", 0.93),
    (r"\b(?:asthma)\b", "J45.909", 0.91),
    (r"\b(?:pneumonia|community[- ]acquired\s+pneumonia)\b", "J18.9", 0.92),
    (r"\b(?:acute\s+bronchitis|bronchitis)\b", "J20.9", 0.89),
    (r"\b(?:obstructive\s+sleep\s+apnea|sleep\s+apnea|osa)\b", "G47.33", 0.92),
    (r"\b(?:major\s+depressive\s+disorder|depression)\b", "F32.9", 0.90),
    (r"\b(?:generalized\s+anxiety\s+disorder|anxiety)\b", "F41.1", 0.89),
    (r"\b(?:gerd|gastroesophageal\s+reflux(?:\s+disease)?|acid\s+reflux)\b", "K21.9", 0.91),
    (r"\b(?:migraine(?:\s+without\s+aura)?)\b", "G43.909", 0.91),
    (r"\b(?:urinary\s+tract\s+infection|uti)\b", "N39.0", 0.92),
    (r"\b(?:chronic\s+kidney\s+disease|ckd)\b", "N18.9", 0.92),
    (r"\b(?:hypothyroidism)\b", "E03.9", 0.92),
    (r"\b(?:anemia|iron\s+deficiency\s+anemia)\b", "D64.9", 0.89),
    (r"\b(?:meniscal\s+tear|torn\s+meniscus|acl\s+tear)\b", "S83.209A", 0.91),
    (r"\b(?:cholelithiasis|gallstones|cholecystitis)\b", "K80.20", 0.90),
    (r"\b(?:colorectal\s+polyp|rectal\s+bleeding|colon\s+cancer\s+screening)\b", "Z12.11", 0.89),
]

# Curated RxNorm medication dictionary: name -> rxnorm code
MEDICATION_LEXICON: Dict[str, str] = {
    "metformin": "6809",
    "lisinopril": "29046",
    "losartan": "52175",
    "amlodipine": "17767",
    "atorvastatin": "83367",
    "rosuvastatin": "301542",
    "ibuprofen": "5640",
    "naproxen": "7258",
    "meloxicam": "41493",
    "acetaminophen": "161",
    "tylenol": "161",
    "aspirin": "1191",
    "albuterol": "435",
    "tiotropium": "274766",
    "fluticasone": "41126",
    "budesonide": "19831",
    "prednisone": "8640",
    "furosemide": "4603",
    "lasix": "4603",
    "metoprolol": "6918",
    "carvedilol": "20352",
    "spironolactone": "9997",
    "apixaban": "1364430",
    "eliquis": "1364430",
    "warfarin": "11289",
    "clopidogrel": "32968",
    "omeprazole": "7646",
    "pantoprazole": "40790",
    "gabapentin": "25480",
    "duloxetine": "72625",
    "sertraline": "36437",
    "escitalopram": "321988",
    "levothyroxine": "10582",
    "insulin glargine": "274783",
    "insulin": "5856",
    "semaglutide": "1991302",
    "ozempic": "1991302",
    "empagliflozin": "1545653",
    "jardiance": "1545653",
    "amoxicillin": "723",
    "azithromycin": "18631",
    "doxycycline": "3640",
    "ciprofloxacin": "2551",
    "hydrochlorothiazide": "5487",
    "tramadol": "10689",
    "cyclobenzaprine": "21949",
    "sumatriptan": "37418",
}

# Curated CPT procedure patterns: (regex, cpt_code, confidence)
PROCEDURE_PATTERNS: List[Tuple[str, str, float]] = [
    (r"\b(?:mri\s+(?:of\s+(?:the\s+)?)?(?:left\s+|right\s+)?knee|knee\s+mri)\b", "73706", 0.95),
    (r"\b(?:mri\s+(?:of\s+(?:the\s+)?)?(?:lumbar\s+)?spine|lumbar\s+(?:spine\s+)?mri)\b", "72148", 0.95),
    (r"\b(?:brain\s+mri|mri\s+(?:of\s+(?:the\s+)?)?brain)\b", "70551", 0.94),
    (r"\b(?:mri)\b", "73706", 0.87),
    (r"\b(?:ct\s+(?:scan\s+)?(?:of\s+(?:the\s+)?)?chest|chest\s+ct)\b", "71250", 0.94),
    (r"\b(?:ct\s+(?:scan\s+)?(?:of\s+(?:the\s+)?)?abdomen|abdominal\s+ct|ct\s+scan)\b", "74150", 0.91),
    (r"\b(?:chest\s+x-?ray|cxr)\b", "71046", 0.93),
    (r"\b(?:knee\s+x-?ray|x-?ray)\b", "73560", 0.89),
    (r"\b(?:transthoracic\s+echocardiogram|echocardiogram|echo)\b", "93306", 0.94),
    (r"\b(?:electrocardiogram|ekg|ecg)\b", "93000", 0.93),
    (r"\b(?:colonoscopy)\b", "45378", 0.94),
    (r"\b(?:upper\s+endoscopy|endoscopy|egd)\b", "43235", 0.93),
    (r"\b(?:polysomnography|sleep\s+study)\b", "95810", 0.93),
    (r"\b(?:total\s+knee\s+arthroplasty|knee\s+replacement)\b", "27447", 0.94),
    (r"\b(?:physical\s+therapy|pt\s+sessions)\b", "97110", 0.88),
    (r"\b(?:ultrasound|sonogram)\b", "76700", 0.89),
    (r"\b(?:biopsy)\b", "11102", 0.89),
    (r"\b(?:comprehensive\s+metabolic\s+panel|cmp)\b", "80053", 0.91),
    (r"\b(?:complete\s+blood\s+count|cbc)\b", "85025", 0.91),
    (r"\b(?:hemoglobin\s+a1c|hba1c|a1c)\b", "83036", 0.92),
    (r"\b(?:lipid\s+panel)\b", "80061", 0.90),
    (r"\b(?:bnp|nt-probnp)\b", "83880", 0.90),
    (r"\b(?:eeg|electroencephalogram)\b", "95816", 0.91),
]

SYMPTOM_PATTERNS: List[Tuple[str, float]] = [
    (r"\b(?:(?:left|right|bilateral|chronic|acute|severe|sharp|dull)\s+)?(?:knee|back|chest|abdominal|joint|neck|shoulder|hip)\s+pain\b", 0.90),
    (r"\b(?:shortness\s+of\s+breath|dyspnea|orthopnea|wheezing)\b", 0.91),
    (r"\b(?:lower\s+extremity\s+edema|leg\s+swelling|ankle\s+swelling|edema|joint\s+swelling|swelling)\b", 0.88),
    (r"\b(?:joint\s+stiffness|morning\s+stiffness|stiffness|limited\s+range\s+of\s+motion)\b", 0.87),
    (r"\b(?:productive\s+cough|dry\s+cough|persistent\s+cough|cough)\b", 0.88),
    (r"\b(?:fever|chills|night\s+sweats)\b", 0.89),
    (r"\b(?:fatigue|weakness|malaise|lethargy)\b", 0.86),
    (r"\b(?:dizziness|lightheadedness|vertigo|syncope)\b", 0.88),
    (r"\b(?:nausea|vomiting|diarrhea|constipation|heartburn)\b", 0.88),
    (r"\b(?:headache|blurred\s+vision|palpitations|numbness|tingling|paresthesia)\b", 0.88),
    (r"\b(?:polyuria|polydipsia|weight\s+loss|weight\s+gain|insomnia|snoring)\b", 0.86),
    (r"\b(?:pain|ache|rash|crepitus)\b", 0.80),
]

ALLERGY_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"\b(?:allergic\s+to|allergy\s+to)\s+([a-zA-Z0-9\s-]{2,30}?)(?=[.,;]|$|\band\b)", re.IGNORECASE),
    re.compile(r"\b(penicillin|sulfa|latex|aspirin|codeine|shellfish|peanut|iodine)\s+allergy\b", re.IGNORECASE),
    re.compile(r"\b(no\s+known\s+drug\s+allergies|nkda)\b", re.IGNORECASE),
]

VITAL_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("BP", re.compile(r"\b(?:BP|blood\s+pressure)\s*(?:is|of|:)?\s*\d{2,3}\s*/\s*\d{2,3}(?:\s*mmHg)?\b", re.IGNORECASE)),
    ("HR", re.compile(r"\b(?:HR|heart\s+rate|pulse)\s*(?:is|of|:)?\s*\d{2,3}\s*(?:bpm)?\b", re.IGNORECASE)),
    ("Temp", re.compile(r"\b(?:Temp|temperature)\s*(?:is|of|:)?\s*\d{2,3}(?:\.\d)?\s*(?:°?[FC])?\b", re.IGNORECASE)),
    ("SpO2", re.compile(r"\b(?:SpO2|O2\s+sat(?:uration)?|oxygen\s+saturation)\s*(?:is|of|:)?\s*\d{2,3}\s*%\b", re.IGNORECASE)),
    ("RR", re.compile(r"\b(?:RR|respiratory\s+rate)\s*(?:is|of|:)?\s*\d{1,2}\b", re.IGNORECASE)),
    ("BMI", re.compile(r"\bBMI\s*(?:is|of|:)?\s*\d{2}(?:\.\d)?\b", re.IGNORECASE)),
]


class ClinicalNLPPipeline:
    """
    Extracts structured clinical entities (diagnoses w/ ICD-10, medications w/ RxNorm,
    procedures w/ CPT, symptoms, allergies, and vital signs).
    Uses optional scispaCy/BioClinicalBERT when enabled + rich deterministic clinical coding.
    """

    def __init__(self) -> None:
        self.nlp = None
        self.diagnosis_pipeline = None
        self.med7_nlp = None
        self.engine_name = "clinical-lexicon-ner-v2"
        self._executor = ThreadPoolExecutor(max_workers=2)
        if settings.ENABLE_TRANSFORMER_NER:
            self._try_load_transformer_models()

    def _try_load_transformer_models(self) -> None:
        try:
            import spacy  # type: ignore

            try:
                self.nlp = spacy.load("en_core_sci_sm")
                self.engine_name = "scispacy+clinical-lexicon-v2"
            except Exception:
                self.nlp = spacy.load("en_core_web_sm")
        except Exception as exc:
            logger.warning("spacy_unavailable", error=str(exc))

        try:
            from transformers import pipeline as hf_pipeline  # type: ignore

            self.diagnosis_pipeline = hf_pipeline(
                "token-classification",
                model="samrawal/bert-base-uncased_clinical-ner",
                aggregation_strategy="simple",
                device=0 if settings.WHISPER_DEVICE == "cuda" else -1,
            )
            self.engine_name = "bioclinicalbert+clinical-lexicon-v2"
        except Exception as exc:
            logger.warning("bioclinicalbert_unavailable", error=str(exc))

    async def extract_entities(self, text: str) -> List[ClinicalEntity]:
        """Extract all clinical entities asynchronously."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            self._sync_extract_entities,
            text,
        )

    def _sync_extract_entities(self, text: str) -> List[ClinicalEntity]:
        if not text:
            return []

        entities: List[ClinicalEntity] = []
        entities.extend(self._extract_diagnoses(text))
        entities.extend(self._extract_medications(text))
        entities.extend(self._extract_procedures(text))
        entities.extend(self._extract_allergies(text))
        entities.extend(self._extract_vitals(text))
        entities.extend(self._extract_symptoms(text))

        # Deduplicate overlapping spans (preferring longer/higher-confidence spans)
        entities.sort(key=lambda e: (e.start, -(e.end - e.start), -e.confidence))
        unique: List[ClinicalEntity] = []
        occupied: List[Tuple[int, int]] = []
        seen_normalized = set()

        for ent in entities:
            overlaps = any(
                not (ent.end <= s or ent.start >= e) for s, e in occupied
            )
            norm_key = (ent.entity_type, ent.text.lower().strip())
            if overlaps:
                continue
            if norm_key in seen_normalized:
                continue
            occupied.append((ent.start, ent.end))
            seen_normalized.add(norm_key)
            unique.append(ent)

        return unique

    def _extract_diagnoses(self, text: str) -> List[ClinicalEntity]:
        entities: List[ClinicalEntity] = []

        if self.diagnosis_pipeline is not None:
            try:
                for res in self.diagnosis_pipeline(text):
                    if res.get("entity_group") in {"PROBLEM", "DIAGNOSIS"}:
                        entities.append(
                            ClinicalEntity(
                                text=res["word"],
                                entity_type=EntityType.DIAGNOSIS,
                                start=int(res["start"]),
                                end=int(res["end"]),
                                confidence=round(float(res["score"]), 3),
                                icd10=self._map_to_icd10(res["word"]),
                            )
                        )
            except Exception as exc:
                logger.warning("diagnosis_pipeline_runtime_error", error=str(exc))

        for pattern, icd10, conf in DIAGNOSIS_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                entities.append(
                    ClinicalEntity(
                        text=match.group().strip(),
                        entity_type=EntityType.DIAGNOSIS,
                        start=match.start(),
                        end=match.end(),
                        confidence=conf,
                        icd10=icd10,
                    )
                )

        return entities

    def _extract_medications(self, text: str) -> List[ClinicalEntity]:
        entities: List[ClinicalEntity] = []
        dosage_re = re.compile(
            r"^\s+(\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|units|iu)(?:\s+(?:once|twice|three\s+times)?\s*(?:daily|bid|tid|qid|prn|at\s+bedtime|po|by\s+mouth))?)",
            re.IGNORECASE,
        )

        for med_name, rxnorm in MEDICATION_LEXICON.items():
            for match in re.finditer(rf"\b{re.escape(med_name)}\b", text, re.IGNORECASE):
                trailing = text[match.end() : match.end() + 45]
                dosage_match = dosage_re.match(trailing)
                dosage = dosage_match.group(1).strip() if dosage_match else None
                end_pos = match.end() + (dosage_match.end() if dosage_match else 0)
                entities.append(
                    ClinicalEntity(
                        text=match.group().strip(),
                        entity_type=EntityType.MEDICATION,
                        start=match.start(),
                        end=end_pos,
                        confidence=0.92,
                        rxnorm=rxnorm,
                        dosage=dosage,
                    )
                )
        return entities

    def _extract_procedures(self, text: str) -> List[ClinicalEntity]:
        entities: List[ClinicalEntity] = []
        for pattern, cpt, conf in PROCEDURE_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                entities.append(
                    ClinicalEntity(
                        text=match.group().strip(),
                        entity_type=EntityType.PROCEDURE,
                        start=match.start(),
                        end=match.end(),
                        confidence=conf,
                        cpt=cpt,
                    )
                )
        return entities

    def _extract_symptoms(self, text: str) -> List[ClinicalEntity]:
        entities: List[ClinicalEntity] = []
        for pattern, conf in SYMPTOM_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                entities.append(
                    ClinicalEntity(
                        text=match.group().strip(),
                        entity_type=EntityType.SYMPTOM,
                        start=match.start(),
                        end=match.end(),
                        confidence=conf,
                    )
                )
        return entities

    def _extract_allergies(self, text: str) -> List[ClinicalEntity]:
        entities: List[ClinicalEntity] = []
        for pattern in ALLERGY_PATTERNS:
            for match in re.finditer(pattern, text):
                entities.append(
                    ClinicalEntity(
                        text=match.group().strip(),
                        entity_type=EntityType.ALLERGY,
                        start=match.start(),
                        end=match.end(),
                        confidence=0.92,
                    )
                )
        return entities

    def _extract_vitals(self, text: str) -> List[ClinicalEntity]:
        entities: List[ClinicalEntity] = []
        for _label, pattern in VITAL_PATTERNS:
            for match in re.finditer(pattern, text):
                entities.append(
                    ClinicalEntity(
                        text=match.group().strip(),
                        entity_type=EntityType.VITAL,
                        start=match.start(),
                        end=match.end(),
                        confidence=0.95,
                    )
                )
        return entities

    def _map_to_icd10(self, text: str) -> Optional[str]:
        lowered = text.lower()
        for pattern, code, _ in DIAGNOSIS_PATTERNS:
            if re.search(pattern, lowered, re.IGNORECASE):
                return code
        return None


_nlp_pipeline: ClinicalNLPPipeline | None = None


def get_nlp_pipeline() -> ClinicalNLPPipeline:
    """Get or create NLP pipeline singleton."""
    global _nlp_pipeline
    if _nlp_pipeline is None:
        _nlp_pipeline = ClinicalNLPPipeline()
    return _nlp_pipeline
