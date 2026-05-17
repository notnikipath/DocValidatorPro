from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from .schemas import AuditEvent, Role


def build_audit_event(
    actor_id: str,
    actor_role: Role | str,
    action: str,
    object_type: str,
    object_id: str,
    details: dict | None = None,
) -> AuditEvent:
    return AuditEvent(
        event_id=str(uuid4()),
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        object_type=object_type,
        object_id=object_id,
        details=details or {},
        created_at=datetime.now(UTC),
    )
