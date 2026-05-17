from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from shared.docvalidator_common import (
    ComparisonRequest,
    ComparisonResult,
    DocumentRecord,
    FieldDiff,
    Role,
    Settings,
    build_audit_event,
    flatten_dict,
    has_permission,
)

settings = Settings(service_name="comparison-service", service_port=8503)
app = FastAPI(title="DocValidator Comparison Service", version="1.0.0")

audit_log: list[dict[str, Any]] = []


class CompareByIdsRequest(BaseModel):
    document_id: str
    reference_document_id: str
    actor_id: str
    actor_role: Role


def _assert_permission(role: Role, action: str) -> None:
    if not has_permission(role, action):
        raise HTTPException(status_code=403, detail=f"Role {role.value} cannot perform {action}")


def _audit(actor_id: str, actor_role: Role, action: str, object_id: str, details: dict[str, Any]) -> None:
    event = build_audit_event(
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        object_type="comparison",
        object_id=object_id,
        details=details,
    )
    audit_log.append(event.model_dump(mode="json"))


async def _fetch_document(document_id: str) -> DocumentRecord:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            f"{settings.storage_service_url}/documents/{document_id}",
            params={"actor_role": "analyst"},
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return DocumentRecord(**response.json())


async def _fetch_reference(document: DocumentRecord) -> DocumentRecord | None:
    async with httpx.AsyncClient(timeout=20.0) as client:
        versions = await client.get(
            f"{settings.storage_service_url}/documents/{document.document_id}/versions",
            params={"actor_role": "analyst"},
        )
        if versions.status_code < 400:
            payload = versions.json()
            items = payload.get("items", [])
            if len(items) > 1:
                for item in items:
                    if item["document_id"] == document.document_id:
                        continue
                    if item["version"] < document.version:
                        return DocumentRecord(**item)
        duplicate = await client.get(
            f"{settings.storage_service_url}/documents/hash/{document.content_hash}",
            params={"actor_role": "analyst"},
        )
        if duplicate.status_code < 400:
            same = duplicate.json()
            if same.get("document_id") != document.document_id:
                return DocumentRecord(**same)
    return None


def _build_diff(
    current: DocumentRecord,
    reference: DocumentRecord | None,
) -> tuple[list[FieldDiff], float, float, str | None, str | None]:
    if reference is None:
        return [], 0.0, 0.0, None, None

    current_flat = flatten_dict(current.fields)
    reference_flat = flatten_dict(reference.fields)
    keys = sorted(set(current_flat.keys()) | set(reference_flat.keys()))
    diffs: list[FieldDiff] = []
    critical_changes = 0
    critical_markers = {"total_amount", "counterparty_inn", "beneficiary", "bank_account", "contract_subject"}

    for key in keys:
        old_value = reference_flat.get(key)
        new_value = current_flat.get(key)
        if old_value == new_value:
            continue
        diffs.append(FieldDiff(field_name=key, old_value=old_value, new_value=new_value, changed=True))
        if key in critical_markers:
            critical_changes += 1

    ratio = len(diffs) / max(len(keys), 1)
    metadata_flags = 1 if current.metadata.get("edited_after_signing") else 0
    suspicious = min(1.0, ratio * 0.6 + critical_changes * 0.2 + metadata_flags * 0.2)

    duplicate_of = reference.document_id if current.content_hash == reference.content_hash else None
    version_of = reference.document_id if current.content_hash != reference.content_hash else None
    return diffs, round(ratio, 4), round(suspicious, 4), duplicate_of, version_of


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/compare")
async def compare(request: ComparisonRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "comparison:run")
    document = request.document
    reference = request.reference_document or await _fetch_reference(document)
    diffs, change_ratio, suspicious_score, duplicate_of, version_of = _build_diff(document, reference)
    result = ComparisonResult(
        document_id=document.document_id,
        duplicate_of=duplicate_of,
        version_of=version_of,
        change_ratio=change_ratio,
        suspicious_change_score=suspicious_score,
        diffs=diffs,
        created_at=datetime.now(UTC),
    )
    _audit(
        request.actor_id,
        request.actor_role,
        "comparison.run",
        document.document_id,
        {
            "reference_document_id": reference.document_id if reference else None,
            "diffs": len(diffs),
            "change_ratio": result.change_ratio,
            "suspicious_change_score": result.suspicious_change_score,
        },
    )
    return result.model_dump(mode="json")


@app.post("/compare/by-ids")
async def compare_by_ids(request: CompareByIdsRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "comparison:run")
    document = await _fetch_document(request.document_id)
    reference = await _fetch_document(request.reference_document_id)
    wrapped = ComparisonRequest(
        document=document,
        reference_document=reference,
        actor_id=request.actor_id,
        actor_role=request.actor_role,
    )
    return await compare(wrapped)


@app.get("/audit")
async def get_audit(limit: int = 100, actor_role: Role = Role.ADMIN) -> dict[str, Any]:
    _assert_permission(actor_role, "audit:read")
    return {"items": audit_log[-limit:], "count": len(audit_log[-limit:])}
