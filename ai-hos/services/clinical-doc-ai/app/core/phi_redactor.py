"""HIPAA Safe Harbor PHI redaction utilities."""
import re
from typing import List, Tuple


PHI_PATTERNS: List[Tuple[str, re.Pattern[str], str]] = [
    (
        "SSN",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "[REDACTED_SSN]",
    ),
    (
        "EMAIL",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "[REDACTED_EMAIL]",
    ),
    (
        "PHONE",
        re.compile(
            r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)"
        ),
        "[REDACTED_PHONE]",
    ),
    (
        "MRN",
        re.compile(r"\b(?:MRN|Medical Record(?: Number)?)[\s:#-]*[A-Z0-9-]{4,16}\b", re.IGNORECASE),
        "[REDACTED_MRN]",
    ),
    (
        "DOB",
        re.compile(
            r"\b(?:DOB|Date of Birth|born on)[\s:]*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
            re.IGNORECASE,
        ),
        "[REDACTED_DOB]",
    ),
    (
        "PATIENT_NAME",
        re.compile(
            r"\b(Patient(?:\s+name)?|Name)\s*:\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})"
        ),
        r"\1: [REDACTED_NAME]",
    ),
]


def redact_phi(text: str, enabled: bool = True) -> Tuple[str, int, List[str]]:
    """
    Redact common HIPAA Safe Harbor identifiers before LLM processing or logging.

    Returns:
        (redacted_text, total_redactions, sorted_categories_detected)
    """
    if not enabled or not text:
        return text, 0, []

    redacted = text
    total_count = 0
    categories: List[str] = []

    for label, pattern, replacement in PHI_PATTERNS:
        redacted, count = pattern.subn(replacement, redacted)
        if count > 0:
            total_count += count
            categories.append(label)

    return redacted, total_count, categories
