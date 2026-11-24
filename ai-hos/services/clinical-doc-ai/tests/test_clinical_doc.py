"""Automated tests for Clinical Documentation AI Service (v2.0)."""
from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from app.db.mongodb import reset_db
from app.main import app


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path):
    db_file = str(tmp_path / "test_clinical.db")
    reset_db(db_path=db_file)
    yield


def test_health_endpoint():
    with TestClient(app) as client:
        res = client.get("/health")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "healthy"
        assert body["version"] == "2.0.0"
        assert body["phi_redaction_enabled"] is True


def test_phi_redaction_endpoint():
    with TestClient(app) as client:
        res = client.post(
            "/api/v1/redact-phi",
            json={
                "text": "Patient: John Smith, SSN 123-45-6789, phone 555-321-7788, MRN-99812, email john@example.com has hypertension."
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["redaction_count"] >= 5
        assert "123-45-6789" not in data["redacted_text"]
        assert "555-321-7788" not in data["redacted_text"]
        assert "john@example.com" not in data["redacted_text"]
        assert "John Smith" not in data["redacted_text"]
        assert "hypertension" in data["redacted_text"]


def test_full_clinical_doc_lifecycle():
    with TestClient(app) as client:
        # 1. Create session
        create_res = client.post(
            "/api/v1/sessions",
            json={"patient_id": "PAT-TEST-01", "provider_id": "PROV-TEST-01"},
        )
        assert create_res.status_code == 200
        session_id = create_res.json()["session_id"]

        # 2. Generate coded SOAP note with PHI redaction
        transcript = (
            "Patient: Jane Doe (MRN-112233) is a 68-year-old female with chronic left knee "
            "osteoarthritis and severe left knee pain for 6 months. Failed 8 weeks of physical therapy "
            "and ibuprofen 400 mg twice daily. Allergic to penicillin. BP 134/82 mmHg. "
            "Plan: Order MRI of the left knee and start meloxicam 15 mg once daily."
        )
        soap_res = client.post(
            "/api/v1/generate-soap",
            json={
                "session_id": session_id,
                "transcript": transcript,
                "patient_context": {"age": 68, "gender": "F"},
            },
        )
        assert soap_res.status_code == 200
        payload = soap_res.json()
        soap = payload["soap_note"]
        assert "Jane Doe" not in payload["redacted_transcript"]
        assert soap["confidence_score"] >= 0.8

        entity_types = {e["entity_type"] for e in soap["entities"]}
        assert "diagnosis" in entity_types
        assert "medication" in entity_types
        assert "procedure" in entity_types
        assert "allergy" in entity_types
        assert "vital" in entity_types

        icd_codes = {e["icd10"] for e in soap["entities"] if e.get("icd10")}
        cpt_codes = {e["cpt"] for e in soap["entities"] if e.get("cpt")}
        assert "M17.12" in icd_codes
        assert "73706" in cpt_codes

        # 3. Approve and persist clinician edits
        update_res = client.put(
            f"/api/v1/sessions/{session_id}/soap",
            json={
                "subjective": soap["subjective"],
                "objective": soap["objective"],
                "assessment": soap["assessment"],
                "plan": soap["plan"] + "\nReviewed and signed.",
                "approved": True,
                "approved_by": "PROV-TEST-01",
            },
        )
        assert update_res.status_code == 200
        assert update_res.json()["soap_note"]["approved"] is True

        # 4. Export HL7 FHIR R4 Bundle
        fhir_res = client.get(f"/api/v1/sessions/{session_id}/fhir")
        assert fhir_res.status_code == 200
        bundle = fhir_res.json()
        assert bundle["resourceType"] == "Bundle"
        assert bundle["type"] == "document"
        resource_types = {e["resource"]["resourceType"] for e in bundle["entry"]}
        assert {"Composition", "Condition", "MedicationRequest", "ServiceRequest"}.issubset(
            resource_types
        )

        # 5. Verify patient notes & stats
        notes_res = client.get("/api/v1/patients/PAT-TEST-01/notes")
        assert notes_res.status_code == 200
        assert notes_res.json()["count"] == 1

        stats_res = client.get("/api/v1/stats")
        assert stats_res.status_code == 200
        assert stats_res.json()["approved_notes"] == 1


def test_websocket_streaming_dictation():
    with TestClient(app) as client:
        session = client.post(
            "/api/v1/sessions?patient_id=PAT-WS&provider_id=PROV-WS"
        ).json()
        sid = session["session_id"]

        with client.websocket_connect(f"/api/v1/ws/{sid}") as ws:
            ws.send_json(
                {
                    "type": "live_transcript",
                    "text": "Patient with hypertension and type 2 diabetes on metformin 500 mg b i d. Order EKG.",
                }
            )
            ack = ws.receive_json()
            assert ack["type"] == "transcript_ack"

            ws.send_text("END_RECORDING")
            msg_types = []
            for _ in range(4):
                msg = ws.receive_json()
                msg_types.append(msg["type"])
                if msg["type"] == "soap_note":
                    assert msg["soap_note"]["confidence_score"] > 0.7
                    break
            assert "transcription" in msg_types
            assert "entities" in msg_types
            assert "soap_note" in msg_types
