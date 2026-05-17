from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from shared.docvalidator_common import (
    NotificationChannel,
    NotificationEvent,
    Role,
    Settings,
    Severity,
    build_audit_event,
    has_permission,
)

settings = Settings(service_name="notification-service", service_port=8508)
app = FastAPI(title="DocValidator Notification Service", version="1.0.0")

events: list[NotificationEvent] = []
audit_log: list[dict[str, Any]] = []


class NotifyRequest(BaseModel):
    channel: NotificationChannel = NotificationChannel.SYSTEM
    recipient: str
    subject: str
    body: str
    severity: Severity = Severity.INFO
    document_id: str | None = None
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
        object_type="notification",
        object_id=object_id,
        details=details,
    )
    audit_log.append(event.model_dump(mode="json"))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/notify")
async def notify(request: NotifyRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "notification:send")
    event = NotificationEvent(
        event_id=str(uuid4()),
        channel=request.channel,
        recipient=request.recipient,
        subject=request.subject,
        body=request.body,
        severity=request.severity,
        document_id=request.document_id,
        created_at=datetime.now(UTC),
    )
    events.append(event)
    _audit(
        request.actor_id,
        request.actor_role,
        "notification.send",
        event.event_id,
        {"channel": event.channel.value, "severity": event.severity.value},
    )
    return event.model_dump(mode="json")


@app.post("/notify/critical")
async def critical(payload: dict[str, Any]) -> dict[str, Any]:
    request = NotifyRequest(
        channel=NotificationChannel(payload.get("channel", "system")),
        recipient=str(payload.get("recipient", "ops@company.local")),
        subject=str(payload.get("subject", "Critical validation issue")),
        body=str(payload.get("body", "Please review document immediately")),
        severity=Severity.CRITICAL,
        document_id=payload.get("document_id"),
        actor_id=str(payload.get("actor_id", "system")),
        actor_role=Role(payload.get("actor_role", "admin")),
    )
    return await notify(request)


@app.get("/notify/history")
async def history(limit: int = 200, actor_role: Role = Role.ANALYST) -> dict[str, Any]:
    _assert_permission(actor_role, "dashboard:read")
    items = [event.model_dump(mode="json") for event in events[-limit:]]
    return {"items": items, "count": len(items)}


@app.get("/audit")
async def get_audit(limit: int = 100, actor_role: Role = Role.ADMIN) -> dict[str, Any]:
    _assert_permission(actor_role, "audit:read")
    return {"items": audit_log[-limit:], "count": len(audit_log[-limit:])}
