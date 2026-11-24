"""Automated tests for Prior Authorization Engine (v2.0)."""
from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from app.db.store import reset_store
from app.engine.rule_engine import reset_rule_engine
from app.main import app


@pytest.fixture(autouse=True)
def isolated_engine(tmp_path: Path):
    reset_store(db_path=str(tmp_path / "test_prior_auth.db"))
    reset_rule_engine(load_defaults=True)
    yield


def test_health_and_default_policies_loaded():
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["loaded_policies"] >= 7

        policies = client.get("/api/v1/prior-auth/policies")
        assert policies.status_code == 200
        assert len(policies.json()) >= 7


def test_auto_approve_with_strong_medical_necessity():
    with TestClient(app) as client:
        res = client.post(
            "/api/v1/prior-auth/evaluate",
            json={
                "request_id": "PA-TEST-APPROVE",
                "patient_id": "PAT-1",
                "provider_id": "PROV-1",
                "payer_id": "UHC",
                "procedure_code": "73706",
                "diagnosis_codes": ["M17.12"],
                "patient_age": 68,
                "patient_gender": "F",
                "current_medications": ["ibuprofen", "meloxicam"],
                "clinical_notes": (
                    "Patient failed conservative therapy including 8 weeks of physical therapy "
                    "and ibuprofen for severe chronic left knee pain. Prior X-ray showed narrowing."
                ),
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["decision"] == "auto_approve"
        assert data["confidence_score"] >= 0.80
        assert data["matched_policy_id"] == "UHC-MRI-KNEE-001"
        assert len(data["failed_rules"]) == 0


def test_escalate_when_missing_clinical_evidence():
    with TestClient(app) as client:
        res = client.post(
            "/api/v1/prior-auth/evaluate",
            json={
                "request_id": "PA-TEST-ESC",
                "patient_id": "PAT-2",
                "provider_id": "PROV-1",
                "payer_id": "UHC",
                "procedure_code": "73706",
                "diagnosis_codes": ["M17.11"],
                "patient_age": 45,
                "patient_gender": "M",
                "clinical_notes": "Mild discomfort started yesterday.",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["decision"] == "escalate"
        assert len(data["required_documents"]) >= 2


def test_auto_deny_when_age_rule_fails_without_evidence():
    with TestClient(app) as client:
        res = client.post(
            "/api/v1/prior-auth/evaluate",
            json={
                "request_id": "PA-TEST-DENY",
                "patient_id": "PAT-3",
                "provider_id": "PROV-1",
                "payer_id": "Cigna",
                "procedure_code": "45378",
                "diagnosis_codes": ["Z12.11"],
                "patient_age": 25,
                "patient_gender": "F",
                "clinical_notes": "",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["decision"] == "auto_deny"
        assert data["confidence_score"] <= 0.35
        assert len(data["failed_rules"]) >= 1


def test_custom_policy_and_stats():
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/prior-auth/policies",
            json={
                "policy_id": "CUSTOM-TEST-001",
                "payer_id": "Humana",
                "payer_name": "Humana Health",
                "policy_title": "Brain MRI Policy",
                "procedure_codes": ["70551"],
                "diagnosis_codes": ["G43.909"],
                "rules": [
                    {"field": "age", "operator": "gte", "value": 18, "weight": 1.0}
                ],
                "auto_approve_threshold": 0.75,
                "auto_deny_threshold": 0.3,
            },
        )
        assert created.status_code == 200

        eval_res = client.post(
            "/api/v1/prior-auth/evaluate",
            json={
                "request_id": "PA-CUSTOM-1",
                "patient_id": "PAT-9",
                "provider_id": "PROV-9",
                "payer_id": "Humana",
                "procedure_code": "70551",
                "diagnosis_codes": ["G43.909"],
                "patient_age": 34,
                "patient_gender": "F",
                "clinical_notes": "Chronic severe migraine unresponsive to sumatriptan.",
            },
        )
        assert eval_res.status_code == 200
        assert eval_res.json()["decision"] == "auto_approve"

        stats = client.get("/api/v1/prior-auth/stats").json()
        assert stats["total_evaluations"] == 1
        assert stats["auto_approved"] == 1
