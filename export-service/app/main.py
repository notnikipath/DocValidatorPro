from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from shared.docvalidator_common import (
    ExportRequest,
    ExportResult,
    ExportTarget,
    Role,
    Settings,
    build_audit_event,
    has_permission,
)

settings = Settings(service_name="export-service", service_port=8506)
app = FastAPI(title="DocValidator Export Service", version="1.0.0")

exports: dict[str, ExportResult] = {}
webhooks: list[str] = []
audit_log: list[dict[str, Any]] = []


class WebhookRegistrationRequest(BaseModel):
    url: str
    actor_id: str
    actor_role: Role


class WebhookNotificationRequest(BaseModel):
    url: str | None = None
    payload: dict[str, Any]
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
        object_type="export",
        object_id=object_id,
        details=details,
    )
    audit_log.append(event.model_dump(mode="json"))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/export")
async def export_document(request: ExportRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "quality:task:create")
    status = "queued"
    if request.target in {ExportTarget.ERP, ExportTarget.CRM, ExportTarget.DOCFLOW}:
        status = "sent"
    if request.target == ExportTarget.WEBHOOK:
        status = "scheduled"
    result = ExportResult(
        export_id=str(uuid4()),
        document_id=request.document_id,
        target=request.target,
        destination=request.destination,
        status=status,
        payload_preview={key: request.payload[key] for key in list(request.payload.keys())[:10]},
        created_at=datetime.now(UTC),
    )
    exports[result.export_id] = result
    _audit(
        request.actor_id,
        request.actor_role,
        "export.run",
        result.export_id,
        {"document_id": request.document_id, "target": request.target.value, "status": status},
    )
    return result.model_dump(mode="json")


@app.get("/export")
async def list_exports(document_id: str | None = None, actor_role: Role = Role.ANALYST) -> dict[str, Any]:
    _assert_permission(actor_role, "analytics:read")
    items = []
    for item in exports.values():
        if document_id and item.document_id != document_id:
            continue
        items.append(item.model_dump(mode="json"))
    items.sort(key=lambda row: row["created_at"], reverse=True)
    return {"items": items, "count": len(items)}


@app.post("/export/reconciliation-act")
async def reconciliation_act(payload: dict[str, Any]) -> dict[str, Any]:
    actor_role = Role(payload.get("actor_role", "analyst"))
    _assert_permission(actor_role, "analytics:read")
    client_id = str(payload.get("client_id", "unknown"))
    period = str(payload.get("period", "unknown"))
    doc_ids = payload.get("document_ids", [])
    total_amount = float(payload.get("total_amount", 0.0))
    act = {
        "act_id": str(uuid4()),
        "client_id": client_id,
        "period": period,
        "documents_count": len(doc_ids),
        "total_amount": round(total_amount, 2),
        "currency": payload.get("currency", "RUB"),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    _audit(
        str(payload.get("actor_id", "system")),
        actor_role,
        "export.reconciliation_act",
        act["act_id"],
        {"period": period, "documents_count": len(doc_ids)},
    )
    return act


@app.post("/export/webhooks")
async def register_webhook(request: WebhookRegistrationRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "notification:send")
    if request.url not in webhooks:
        webhooks.append(request.url)
    _audit(request.actor_id, request.actor_role, "export.webhook.register", request.url, {})
    return {"items": webhooks, "count": len(webhooks)}


@app.get("/export/webhooks")
async def list_webhooks(actor_role: Role = Role.ADMIN) -> dict[str, Any]:
    _assert_permission(actor_role, "audit:read")
    return {"items": webhooks, "count": len(webhooks)}


@app.post("/export/webhook/notify")
async def notify_webhook(request: WebhookNotificationRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "notification:send")
    targets = [request.url] if request.url else list(webhooks)
    if not targets:
        return {"sent": 0, "failed": 0, "details": []}
    details: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for target in targets:
            try:
                response = await client.post(target, json=request.payload)
                details.append({"url": target, "status_code": response.status_code})
            except httpx.HTTPError as exc:
                details.append({"url": target, "error": str(exc)})
    sent = sum(1 for item in details if "status_code" in item and item["status_code"] < 400)
    failed = len(details) - sent
    _audit(
        request.actor_id,
        request.actor_role,
        "export.webhook.notify",
        "bulk",
        {"sent": sent, "failed": failed},
    )
    return {"sent": sent, "failed": failed, "details": details}


@app.get("/audit")
async def get_audit(limit: int = 100, actor_role: Role = Role.ADMIN) -> dict[str, Any]:
    _assert_permission(actor_role, "audit:read")
    return {"items": audit_log[-limit:], "count": len(audit_log[-limit:])}
