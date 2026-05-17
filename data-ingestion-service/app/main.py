from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4
from xml.etree import ElementTree

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from shared.docvalidator_common import (
    DocumentRecord,
    IngestionRequest,
    Role,
    Settings,
    ValidationStatus,
    build_audit_event,
    encrypt_text,
    has_permission,
    hash_document,
)

settings = Settings(service_name="data-ingestion-service", service_port=8501)
app = FastAPI(title="DocValidator Data Ingestion Service", version="1.0.0")

audit_log: list[dict[str, Any]] = []


class BatchIngestionRequest(BaseModel):
    items: list[IngestionRequest]
    max_parallel: int = Field(default=8, ge=1, le=32)
    auto_validate: bool = False
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
        object_type="document",
        object_id=object_id,
        details=details,
    )
    audit_log.append(event.model_dump(mode="json"))


def _parse_xml_payload(payload_xml: str) -> dict[str, Any]:
    root = ElementTree.fromstring(payload_xml)
    result: dict[str, Any] = {}
    for child in root:
        key = child.tag.strip().lower()
        text = child.text.strip() if child.text else ""
        result[key] = text
    return result


def _normalize_fields(raw_fields: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in raw_fields.items():
        normalized_key = str(key).strip().lower()
        if isinstance(value, str):
            normalized[normalized_key] = value.strip()
        else:
            normalized[normalized_key] = value
    return normalized


def _extract_fields(request: IngestionRequest) -> dict[str, Any]:
    if request.manual_fields:
        return _normalize_fields(request.manual_fields)
    if request.payload_json:
        return _normalize_fields(request.payload_json)
    if request.payload_xml:
        return _normalize_fields(_parse_xml_payload(request.payload_xml))
    return {}


def _encrypt_sensitive(fields: dict[str, Any]) -> dict[str, str]:
    encrypted: dict[str, str] = {}
    for key, value in fields.items():
        if key in {"inn", "counterparty_inn", "phone", "passport", "snils", "email"}:
            encrypted[key] = encrypt_text(str(value), settings.encryption_key)
    return encrypted


async def _save_document(document: DocumentRecord, actor_id: str, actor_role: Role) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            f"{settings.storage_service_url}/documents",
            json={"document": document.model_dump(mode="json"), "actor_id": actor_id, "actor_role": actor_role.value},
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


async def _run_auto_validation(document_id: str, actor_id: str, actor_role: Role) -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                f"{settings.api_gateway_url}/workflow/validate-document",
                json={
                    "document_id": document_id,
                    "actor_id": actor_id,
                    "actor_role": actor_role.value,
                    "export_target": "erp",
                },
            )
        if response.status_code >= 400:
            return {"status": "error", "detail": response.text}
        return response.json()
    except httpx.HTTPError as exc:
        return {"status": "error", "detail": str(exc)}


async def _ingest_item(item: IngestionRequest, force_auto_validate: bool | None = None) -> dict[str, Any]:
    fields = _extract_fields(item)
    encrypted_sensitive = _encrypt_sensitive(fields)
    metadata = {
        **item.metadata,
        "encrypted_sensitive_fields": encrypted_sensitive,
        "ingestion_timestamp": datetime.now(UTC).isoformat(),
    }
    document_id = str(uuid4())
    content_hash = hash_document(fields, metadata)
    document = DocumentRecord(
        document_id=document_id,
        client_id=item.client_id,
        project_id=item.project_id,
        document_type=item.document_type,
        source=item.source,
        language=item.language,
        external_id=item.external_id,
        version=1,
        status=ValidationStatus.NEW,
        fields=fields,
        metadata=metadata,
        content_hash=content_hash,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    saved = await _save_document(document, item.actor_id, item.actor_role)
    auto_validate = item.auto_validate if force_auto_validate is None else force_auto_validate
    workflow = None
    if auto_validate:
        workflow = await _run_auto_validation(document.document_id, item.actor_id, item.actor_role)
    _audit(
        item.actor_id,
        item.actor_role,
        "ingestion.import",
        document.document_id,
        {"auto_validate": auto_validate, "field_count": len(fields)},
    )
    return {"document": document.model_dump(mode="json"), "storage": saved, "workflow": workflow}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/ingestion/import")
async def import_document(request: IngestionRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "validation:run")
    return await _ingest_item(request)


@app.post("/ingestion/manual")
async def manual_import(request: IngestionRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "validation:run")
    if request.source.value != "manual":
        raise HTTPException(status_code=400, detail="Use source='manual' for manual import endpoint")
    return await _ingest_item(request)


@app.post("/ingestion/batch")
async def batch_import(request: BatchIngestionRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "validation:run")

    semaphore = asyncio.Semaphore(request.max_parallel)

    async def _task(item: IngestionRequest) -> dict[str, Any]:
        async with semaphore:
            cloned = item.model_copy(update={"actor_id": request.actor_id, "actor_role": request.actor_role})
            return await _ingest_item(cloned, force_auto_validate=request.auto_validate)

    started = datetime.now(UTC)
    results = await asyncio.gather(*[_task(item) for item in request.items], return_exceptions=True)
    ended = datetime.now(UTC)
    success: list[dict[str, Any]] = []
    errors: list[str] = []
    for item in results:
        if isinstance(item, Exception):
            errors.append(str(item))
        else:
            success.append(item)
    duration_seconds = max((ended - started).total_seconds(), 0.001)
    throughput = round(len(success) / duration_seconds * 3600, 2)
    _audit(
        request.actor_id,
        request.actor_role,
        "ingestion.batch",
        "batch",
        {
            "documents": len(request.items),
            "success": len(success),
            "failed": len(errors),
            "throughput_per_hour": throughput,
        },
    )
    return {
        "items": success,
        "errors": errors,
        "count": len(success),
        "failed_count": len(errors),
        "throughput_docs_per_hour": throughput,
    }


@app.post("/ingestion/parse-xml")
async def parse_xml_preview(payload: dict[str, str]) -> dict[str, Any]:
    xml_text = payload.get("xml", "")
    if not xml_text.strip():
        raise HTTPException(status_code=400, detail="xml is required")
    try:
        parsed = _parse_xml_payload(xml_text)
    except ElementTree.ParseError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid XML: {exc}") from exc
    return {"parsed": parsed}


@app.get("/audit")
async def get_audit(limit: int = 100, actor_role: Role = Role.ADMIN) -> dict[str, Any]:
    _assert_permission(actor_role, "audit:read")
    return {"items": audit_log[-limit:], "count": len(audit_log[-limit:])}
