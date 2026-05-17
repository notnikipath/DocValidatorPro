from __future__ import annotations

import json
from pathlib import Path

import httpx

GATEWAY_URL = "http://localhost:8500"
INGESTION_URL = "http://localhost:8501"


def load_samples(limit: int = 5) -> list[dict]:
    root = Path(__file__).resolve().parents[1]
    sample_path = root / "data" / "samples" / "documents_annotated.json"
    payload = json.loads(sample_path.read_text(encoding="utf-8"))
    return payload["items"][:limit]


def to_ingestion_payload(sample: dict) -> dict:
    source = sample["source"]
    payload_json = sample["payload"] if source != "manual" else None
    manual_fields = sample["payload"] if source == "manual" else None
    return {
        "client_id": sample["client_id"],
        "project_id": sample["project_id"],
        "document_type": sample["document_type"],
        "source": source,
        "language": sample["language"],
        "payload_json": payload_json,
        "manual_fields": manual_fields,
        "metadata": sample.get("metadata", {}),
        "actor_id": "DEMO-ADMIN",
        "actor_role": "admin",
        "auto_validate": True,
    }


def main() -> None:
    samples = load_samples()
    print(f"Running demo pipeline for {len(samples)} documents")

    with httpx.Client(timeout=90.0) as client:
        for index, sample in enumerate(samples, start=1):
            payload = to_ingestion_payload(sample)
            response = client.post(f"{INGESTION_URL}/ingestion/import", json=payload)
            response.raise_for_status()
            result = response.json()
            workflow = result.get("workflow") or {}
            validation = workflow.get("validation") or {}
            print(
                f"{index}. doc_id={result['document']['document_id']} "
                f"type={result['document']['document_type']} "
                f"status={validation.get('status', 'unknown')} "
                f"issues={len(validation.get('issues', []))}"
            )

        dashboard = client.get(f"{GATEWAY_URL}/dashboard/overview", params={"actor_role": "analyst"})
        dashboard.raise_for_status()
        payload = dashboard.json()
        print("Dashboard summary:")
        print(json.dumps(payload.get("summary", {}), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
