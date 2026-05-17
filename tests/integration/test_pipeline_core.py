from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from shared.docvalidator_common import hash_document
from tests.integration.helpers import load_module

ROOT = Path(__file__).resolve().parents[2]

storage_module = load_module("storage_module", ROOT / "storage-service" / "app" / "main.py")
validation_module = load_module("validation_module", ROOT / "validation-service" / "app" / "main.py")
comparison_module = load_module("comparison_module", ROOT / "comparison-service" / "app" / "main.py")
analytics_module = load_module("analytics_module", ROOT / "analytics-service" / "app" / "main.py")
quality_module = load_module("quality_module", ROOT / "quality-service" / "app" / "main.py")
notification_module = load_module("notification_module", ROOT / "notification-service" / "app" / "main.py")

storage_client = TestClient(storage_module.app)
validation_client = TestClient(validation_module.app)
comparison_client = TestClient(comparison_module.app)
analytics_client = TestClient(analytics_module.app)
quality_client = TestClient(quality_module.app)
notification_client = TestClient(notification_module.app)


def _build_document(amount: float = 12000.0, inn: str = "7707083893") -> dict:
    total_amount = round(amount * 1.2, 2)
    fields = {
        "document_number": f"INV-{uuid4().hex[:6]}",
        "issue_date": "2026-05-01",
        "due_date": "2026-05-15",
        "counterparty_name": "ООО Альфа",
        "counterparty_inn": inn,
        "subtotal": amount,
        "tax_amount": round(amount * 0.2, 2),
        "total_amount": total_amount,
        "currency": "RUB",
        "phone": "+79991234567",
    }
    metadata = {
        "historical_amounts": [
            round(total_amount * 0.92, 2),
            round(total_amount * 0.95, 2),
            round(total_amount * 1.01, 2),
            round(total_amount * 1.04, 2),
            round(total_amount * 0.98, 2),
        ],
        "counterparty_risk": 0.2,
        "delay_days": 4,
        "historical_failures": 1,
        "owner_email": "owner@company.local",
    }
    return {
        "document_id": str(uuid4()),
        "client_id": "client-a",
        "project_id": "demo",
        "document_type": "financial",
        "source": "json",
        "language": "ru",
        "external_id": None,
        "version": 1,
        "status": "new",
        "fields": fields,
        "metadata": metadata,
        "content_hash": hash_document(fields, metadata),
        "previous_version_id": None,
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }


def test_end_to_end_verification_flow_without_gateway() -> None:
    document = _build_document()
    save_doc = storage_client.post(
        "/documents",
        json={"document": document, "actor_id": "AUD-001", "actor_role": "auditor"},
    )
    assert save_doc.status_code == 200

    rules_response = storage_client.get("/rules", params={"actor_role": "analyst", "enabled_only": True})
    assert rules_response.status_code == 200
    rules = rules_response.json()["items"]

    validation_response = validation_client.post(
        "/validate",
        json={
            "document": document,
            "rules": rules,
            "actor_id": "AUD-001",
            "actor_role": "auditor",
        },
    )
    assert validation_response.status_code == 200
    validation = validation_response.json()
    assert validation["format_score"] >= 0.9

    comparison_response = comparison_client.post(
        "/compare",
        json={
            "document": document,
            "reference_document": document,
            "actor_id": "AUD-001",
            "actor_role": "auditor",
        },
    )
    assert comparison_response.status_code == 200
    comparison = comparison_response.json()
    assert comparison["change_ratio"] == 0

    analytics_response = analytics_client.post(
        "/analytics/calculate",
        json={
            "document": document,
            "validation_result": validation,
            "comparison_result": comparison,
            "actor_id": "AUD-001",
            "actor_role": "admin",
        },
    )
    assert analytics_response.status_code == 200
    analytics = analytics_response.json()
    assert 0 <= analytics["predicted_risk_of_non_payment"] <= 1

    quality_response = quality_client.post(
        "/quality/evaluate",
        json={
            "document": document,
            "validation_result": validation,
            "comparison_result": comparison,
            "analytics_result": analytics,
            "actor_id": "AUD-001",
            "actor_role": "auditor",
        },
    )
    assert quality_response.status_code == 200
    quality = quality_response.json()
    assert "quality_score" in quality

    save_validation = storage_client.post(
        "/results/validation",
        json={"result": validation, "actor_id": "AUD-001", "actor_role": "auditor"},
    )
    assert save_validation.status_code == 200
    save_comparison = storage_client.post(
        "/results/comparison",
        json={"result": comparison, "actor_id": "AUD-001", "actor_role": "auditor"},
    )
    assert save_comparison.status_code == 200
    save_analytics = storage_client.post(
        "/results/analytics",
        json={"result": analytics, "actor_id": "AUD-001", "actor_role": "admin"},
    )
    assert save_analytics.status_code == 200

    status_update = storage_client.post(
        f"/documents/{document['document_id']}/status",
        json={"status": validation["status"], "actor_id": "AUD-001", "actor_role": "auditor"},
    )
    assert status_update.status_code == 200

    notification = notification_client.post(
        "/notify",
        json={
            "channel": "system",
            "recipient": "owner@company.local",
            "subject": "Validation complete",
            "body": "Document processed",
            "severity": "info",
            "document_id": document["document_id"],
            "actor_id": "AUD-001",
            "actor_role": "auditor",
        },
    )
    assert notification.status_code == 200

    summary = storage_client.get("/summary", params={"actor_role": "analyst"})
    assert summary.status_code == 200
    assert summary.json()["documents_total"] >= 1


def test_rule_import_and_document_versioning() -> None:
    csv_text = (
        "name,document_type,rule_type,target_field,pattern,min_value,max_value,severity,description\n"
        "Invoice code pattern,financial,format,document_number,^INV-,,,warning,Number must start with INV\n"
    )
    imported = storage_client.post(
        "/rules/import/csv",
        json={"csv_text": csv_text, "actor_id": "ADM-001", "actor_role": "admin"},
    )
    assert imported.status_code == 200
    assert imported.json()["count"] == 1

    document = _build_document(amount=7500.0)
    save_doc = storage_client.post(
        "/documents",
        json={"document": document, "actor_id": "AUD-002", "actor_role": "auditor"},
    )
    assert save_doc.status_code == 200

    correction = storage_client.post(
        f"/documents/{document['document_id']}/corrections",
        json={
            "fields_patch": {"total_amount": 9000.0},
            "reason": "manual fix",
            "actor_id": "AUD-002",
            "actor_role": "auditor",
        },
    )
    assert correction.status_code == 200
    corrected = correction.json()
    assert corrected["version"] == 2
    assert corrected["previous_version_id"] == document["document_id"]

    versions = storage_client.get(f"/documents/{corrected['document_id']}/versions", params={"actor_role": "analyst"})
    assert versions.status_code == 200
    assert versions.json()["count"] >= 2
