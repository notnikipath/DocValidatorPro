from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

DOCUMENT_TYPES = ["financial", "legal", "hr", "medical", "technical"]


def _random_date(days_back: int = 120) -> str:
    dt = datetime.now(UTC) - timedelta(days=random.randint(0, days_back))
    return dt.strftime("%Y-%m-%d")


def _financial_sample(with_error: bool) -> tuple[dict, list[str]]:
    subtotal = round(random.uniform(1500, 50000), 2)
    tax = round(subtotal * 0.2, 2)
    total = round(subtotal + tax, 2)
    errors: list[str] = []
    if with_error:
        total = round(total + random.uniform(5, 200), 2)
        errors.append("arithmetic_mismatch")
    payload = {
        "document_number": f"INV-{random.randint(1000, 9999)}",
        "issue_date": _random_date(),
        "due_date": _random_date(30),
        "counterparty_name": random.choice(["ООО Альфа", "ООО Бета", "АО Гамма", "Delta Ltd"]),
        "counterparty_inn": random.choice(["7707083893", "7707083890", "771596418012"]),
        "subtotal": subtotal,
        "tax_amount": tax,
        "total_amount": total,
        "currency": random.choice(["RUB", "USD", "РУБ"]),
        "phone": random.choice(["+79991234567", "8(999)-123-45-67"]),
    }
    if payload["counterparty_inn"] == "7707083890":
        errors.append("invalid_inn")
    if payload["phone"] == "8(999)-123-45-67":
        errors.append("phone_needs_normalization")
    return payload, errors


def _legal_sample(with_error: bool) -> tuple[dict, list[str]]:
    subject = random.choice(["Поставка оборудования", "Оказание услуг", "Сопровождение проекта"])
    errors: list[str] = []
    if with_error:
        subject = "Тест"
        errors.append("weak_subject")
    payload = {
        "contract_number": f"CTR-{random.randint(100, 999)}",
        "start_date": _random_date(200),
        "end_date": _random_date(40),
        "party_a": random.choice(["ООО Альфа", "АО Сфера"]),
        "party_b": random.choice(["ООО Альфа", "ООО Бета", "Sigma Corp"]),
        "contract_subject": subject,
        "counterparty_inn": random.choice(["7707083893", "1234567890"]),
    }
    if payload["party_a"] == payload["party_b"]:
        errors.append("identical_parties")
    if payload["counterparty_inn"] == "1234567890":
        errors.append("invalid_inn")
    return payload, errors


def _hr_sample(with_error: bool) -> tuple[dict, list[str]]:
    payload = {
        "full_name": random.choice(["Иванов Иван", "John Smith", "Петрова Анна"]),
        "position": random.choice(["Analyst", "QA Engineer", "HR Manager"]),
        "experience_years": random.randint(0, 15),
        "phone": random.choice(["+15551234567", "12345"]),
        "email": random.choice(["candidate@mail.com", "bad-email"]),
        "date": _random_date(400),
    }
    errors = []
    if payload["phone"] == "12345":
        errors.append("invalid_phone")
    if payload["email"] == "bad-email":
        errors.append("invalid_email_like")
    if with_error:
        payload["full_name"] = ""
        errors.append("missing_full_name")
    return payload, errors


def _medical_sample(with_error: bool) -> tuple[dict, list[str]]:
    payload = {
        "patient_id": f"PT-{random.randint(1000, 9999)}",
        "date": _random_date(60),
        "diagnosis": random.choice(["ОРВИ", "Гипертония", "Стресс"]),
        "conclusion": random.choice(["Амбулаторное наблюдение", "Рекомендована госпитализация"]),
        "doctor": random.choice(["Dr. Adams", "Иванова О.В."]),
    }
    errors = []
    if with_error:
        payload["conclusion"] = ""
        errors.append("missing_conclusion")
    return payload, errors


def _technical_sample(with_error: bool) -> tuple[dict, list[str]]:
    payload = {
        "spec_id": f"SPEC-{random.randint(100, 999)}",
        "version": random.choice(["1.0.0", "2.3.1", "draft"]),
        "release_date": _random_date(700),
        "component": random.choice(["pump", "controller", "gateway"]),
        "status": random.choice(["approved", "review", "draft"]),
    }
    errors = []
    if payload["version"] == "draft":
        errors.append("non_numeric_version")
    if with_error:
        payload["release_date"] = "99.99.2026"
        errors.append("invalid_date")
    return payload, errors


def _build_document(index: int) -> dict:
    doc_type = DOCUMENT_TYPES[index % len(DOCUMENT_TYPES)]
    with_error = random.random() < 0.55
    generator = {
        "financial": _financial_sample,
        "legal": _legal_sample,
        "hr": _hr_sample,
        "medical": _medical_sample,
        "technical": _technical_sample,
    }[doc_type]
    payload, expected_errors = generator(with_error=with_error)
    return {
        "sample_id": str(uuid4()),
        "client_id": random.choice(["client-a", "client-b", "client-c"]),
        "project_id": "demo-project",
        "document_type": doc_type,
        "source": random.choice(["json", "manual", "ocr_api"]),
        "language": random.choice(["ru", "en"]),
        "payload": payload,
        "expected_errors": expected_errors,
        "metadata": {
            "historical_amounts": [random.randint(2000, 35000) for _ in range(10)],
            "counterparty_risk": round(random.uniform(0.05, 0.75), 2),
            "delay_days": random.randint(0, 45),
            "historical_failures": random.randint(0, 4),
            "owner_email": random.choice(["owner@company.local", "audit@company.local"]),
        },
    }


def main() -> None:
    random.seed(42)
    samples = [_build_document(index) for index in range(120)]
    output = {
        "generated_at": datetime.now(UTC).isoformat(),
        "count": len(samples),
        "items": samples,
    }
    root = Path(__file__).resolve().parents[1]
    output_path = root / "data" / "samples" / "documents_annotated.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated {len(samples)} samples at {output_path}")


if __name__ == "__main__":
    main()
