"""HL7 FHIR R4 Bundle exporter for clinical documentation sessions."""
from datetime import datetime, timezone
from typing import Any, Dict, List
import uuid

from app.models.schemas import EntityType, VoiceSession


def build_fhir_r4_bundle(session: VoiceSession) -> Dict[str, Any]:
    """
    Convert a completed VoiceSession + SOAPNote into an HL7 FHIR R4 Document Bundle
    (Composition + Condition + MedicationRequest + ServiceRequest + AllergyIntolerance).
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    bundle_id = str(uuid.uuid4())
    comp_id = f"comp-{session.session_id}"
    soap = session.soap_note

    entries: List[Dict[str, Any]] = []
    section_entries_refs: List[Dict[str, str]] = []

    if soap:
        for idx, ent in enumerate(soap.entities):
            if ent.entity_type == EntityType.DIAGNOSIS:
                cond_id = f"cond-{idx + 1}-{session.session_id[:8]}"
                coding = []
                if ent.icd10:
                    coding.append(
                        {
                            "system": "http://hl7.org/fhir/sid/icd-10-cm",
                            "code": ent.icd10,
                            "display": ent.text,
                        }
                    )
                entries.append(
                    {
                        "fullUrl": f"urn:uuid:{cond_id}",
                        "resource": {
                            "resourceType": "Condition",
                            "id": cond_id,
                            "clinicalStatus": {
                                "coding": [
                                    {
                                        "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                                        "code": "active",
                                    }
                                ]
                            },
                            "code": {"coding": coding, "text": ent.text},
                            "subject": {"reference": f"Patient/{session.patient_id}"},
                            "recordedDate": now_iso,
                        },
                    }
                )
                section_entries_refs.append({"reference": f"Condition/{cond_id}"})

            elif ent.entity_type == EntityType.MEDICATION:
                med_id = f"medreq-{idx + 1}-{session.session_id[:8]}"
                coding = []
                if ent.rxnorm:
                    coding.append(
                        {
                            "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                            "code": ent.rxnorm,
                            "display": ent.text,
                        }
                    )
                med_resource: Dict[str, Any] = {
                    "resourceType": "MedicationRequest",
                    "id": med_id,
                    "status": "active",
                    "intent": "order",
                    "medicationCodeableConcept": {
                        "coding": coding,
                        "text": f"{ent.text} {ent.dosage or ''}".strip(),
                    },
                    "subject": {"reference": f"Patient/{session.patient_id}"},
                    "authoredOn": now_iso,
                    "requester": {"reference": f"Practitioner/{session.provider_id}"},
                }
                if ent.dosage:
                    med_resource["dosageInstruction"] = [{"text": ent.dosage}]
                entries.append(
                    {"fullUrl": f"urn:uuid:{med_id}", "resource": med_resource}
                )
                section_entries_refs.append({"reference": f"MedicationRequest/{med_id}"})

            elif ent.entity_type == EntityType.PROCEDURE:
                srv_id = f"srvreq-{idx + 1}-{session.session_id[:8]}"
                coding = []
                if ent.cpt:
                    coding.append(
                        {
                            "system": "http://www.ama-assn.org/go/cpt",
                            "code": ent.cpt,
                            "display": ent.text,
                        }
                    )
                entries.append(
                    {
                        "fullUrl": f"urn:uuid:{srv_id}",
                        "resource": {
                            "resourceType": "ServiceRequest",
                            "id": srv_id,
                            "status": "active",
                            "intent": "order",
                            "code": {"coding": coding, "text": ent.text},
                            "subject": {"reference": f"Patient/{session.patient_id}"},
                            "authoredOn": now_iso,
                            "requester": {"reference": f"Practitioner/{session.provider_id}"},
                        },
                    }
                )
                section_entries_refs.append({"reference": f"ServiceRequest/{srv_id}"})

            elif ent.entity_type == EntityType.ALLERGY:
                alg_id = f"allergy-{idx + 1}-{session.session_id[:8]}"
                entries.append(
                    {
                        "fullUrl": f"urn:uuid:{alg_id}",
                        "resource": {
                            "resourceType": "AllergyIntolerance",
                            "id": alg_id,
                            "code": {"text": ent.text},
                            "patient": {"reference": f"Patient/{session.patient_id}"},
                            "recordedDate": now_iso,
                        },
                    }
                )

    composition = {
        "fullUrl": f"urn:uuid:{comp_id}",
        "resource": {
            "resourceType": "Composition",
            "id": comp_id,
            "status": "final" if (soap and soap.approved) else "preliminary",
            "type": {
                "coding": [
                    {
                        "system": "http://loinc.org",
                        "code": "11506-3",
                        "display": "Progress note",
                    }
                ]
            },
            "subject": {"reference": f"Patient/{session.patient_id}"},
            "date": now_iso,
            "author": [{"reference": f"Practitioner/{session.provider_id}"}],
            "title": f"AI-HOS SOAP Clinical Note ({session.session_id[:8]})",
            "section": [
                {
                    "title": "Subjective",
                    "code": {"coding": [{"system": "http://loinc.org", "code": "61150-9"}]},
                    "text": {"status": "generated", "div": f"<div>{soap.subjective if soap else ''}</div>"},
                },
                {
                    "title": "Objective",
                    "code": {"coding": [{"system": "http://loinc.org", "code": "61149-1"}]},
                    "text": {"status": "generated", "div": f"<div>{soap.objective if soap else ''}</div>"},
                },
                {
                    "title": "Assessment",
                    "code": {"coding": [{"system": "http://loinc.org", "code": "51848-0"}]},
                    "text": {"status": "generated", "div": f"<div>{soap.assessment if soap else ''}</div>"},
                    "entry": [r for r in section_entries_refs if r["reference"].startswith("Condition/")],
                },
                {
                    "title": "Plan",
                    "code": {"coding": [{"system": "http://loinc.org", "code": "18776-5"}]},
                    "text": {"status": "generated", "div": f"<div>{soap.plan if soap else ''}</div>"},
                    "entry": [
                        r
                        for r in section_entries_refs
                        if r["reference"].startswith(("MedicationRequest/", "ServiceRequest/"))
                    ],
                },
            ],
        },
    }

    return {
        "resourceType": "Bundle",
        "id": bundle_id,
        "type": "document",
        "timestamp": now_iso,
        "identifier": {
            "system": "urn:ai-hos:session",
            "value": session.session_id,
        },
        "entry": [composition, *entries],
    }
