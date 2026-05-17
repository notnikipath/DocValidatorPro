from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from shared.docvalidator_common import (
    AnalyticsResult,
    ComparisonResult,
    DocumentRecord,
    QualityTask,
    Role,
    Settings,
    Severity,
    ValidationResult,
    build_audit_event,
    has_permission,
)

settings = Settings(service_name="quality-service", service_port=8505)
app = FastAPI(title="DocValidator Quality Service", version="1.0.0")

tasks: dict[str, QualityTask] = {}
feedback_log: list[dict[str, Any]] = []
audit_log: list[dict[str, Any]] = []


class QualityEvaluationRequest(BaseModel):
    document: DocumentRecord
    validation_result: ValidationResult
    comparison_result: ComparisonResult
    analytics_result: AnalyticsResult
    actor_id: str
    actor_role: Role


class TaskUpdateRequest(BaseModel):
    status: str
    assignee: str | None = None
    comment: str | None = None
    actor_id: str
    actor_role: Role


class FeedbackRequest(BaseModel):
    document_id: str
    feedback: str
    corrected_fields: dict[str, Any] = Field(default_factory=dict)
    actor_id: str
    actor_role: Role


for _model in (QualityEvaluationRequest, TaskUpdateRequest, FeedbackRequest):
    _model.model_rebuild()


def _assert_permission(role: Role, action: str) -> None:
    if not has_permission(role, action):
        raise HTTPException(status_code=403, detail=f"Role {role.value} cannot perform {action}")


def _audit(actor_id: str, actor_role: Role, action: str, object_id: str, details: dict[str, Any]) -> None:
    event = build_audit_event(
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        object_type="quality",
        object_id=object_id,
        details=details,
    )
    audit_log.append(event.model_dump(mode="json"))


async def _persist_task(task: QualityTask, actor_id: str, actor_role: Role) -> None:
    async with httpx.AsyncClient(timeout=20.0) as client:
        await client.post(
            f"{settings.storage_service_url}/results/quality-task",
            json={"task": task.model_dump(mode="json"), "actor_id": actor_id, "actor_role": actor_role.value},
        )


def _priority_from_result(
    validation: ValidationResult,
    comparison: ComparisonResult,
    analytics: AnalyticsResult,
) -> Severity:
    if (
        validation.status.value == "rejected"
        or comparison.suspicious_change_score >= 0.8
        or analytics.fraud_probability >= 0.8
    ):
        return Severity.CRITICAL
    if validation.issues or comparison.change_ratio > 0.2 or analytics.predicted_risk_of_non_payment >= 0.5:
        return Severity.WARNING
    return Severity.INFO


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/quality/evaluate")
async def evaluate(request: QualityEvaluationRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "quality:task:create")
    priority = _priority_from_result(request.validation_result, request.comparison_result, request.analytics_result)
    needs_task = priority in {Severity.WARNING, Severity.CRITICAL}

    task: QualityTask | None = None
    if needs_task:
        task = QualityTask(
            task_id=str(uuid4()),
            document_id=request.document.document_id,
            priority=priority,
            title=f"Manual review: {request.document.document_type.value}",
            description=(
                f"Issues={len(request.validation_result.issues)}, "
                f"suspicious_change_score={request.comparison_result.suspicious_change_score}, "
                f"fraud_probability={request.analytics_result.fraud_probability}"
            ),
            status="open",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        tasks[task.task_id] = task
        await _persist_task(task, request.actor_id, request.actor_role)

    _audit(
        request.actor_id,
        request.actor_role,
        "quality.evaluate",
        request.document.document_id,
        {"priority": priority.value, "task_created": bool(task)},
    )

    return {
        "document_id": request.document.document_id,
        "priority": priority.value,
        "task": task.model_dump(mode="json") if task else None,
        "quality_score": round(
            (
                request.validation_result.format_score
                + request.validation_result.logic_score
                + request.validation_result.semantic_score
                + (1 - request.comparison_result.suspicious_change_score)
            )
            / 4,
            4,
        ),
    }


@app.get("/quality/tasks")
async def list_tasks(status: str | None = None, actor_role: Role = Role.ANALYST) -> dict[str, Any]:
    _assert_permission(actor_role, "quality:task:read")
    items = []
    for task in tasks.values():
        if status and task.status != status:
            continue
        items.append(task.model_dump(mode="json"))
    items.sort(key=lambda item: item["updated_at"], reverse=True)
    return {"items": items, "count": len(items)}


@app.patch("/quality/tasks/{task_id}")
async def update_task(task_id: str, request: TaskUpdateRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "quality:task:update")
    task = tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = request.status
    task.assignee = request.assignee or task.assignee
    task.updated_at = datetime.now(UTC)
    _audit(
        request.actor_id,
        request.actor_role,
        "quality.task.update",
        task_id,
        {"status": request.status, "assignee": request.assignee, "comment": request.comment},
    )
    return task.model_dump(mode="json")


@app.post("/quality/feedback")
async def feedback(request: FeedbackRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "quality:task:update")
    payload = {
        "feedback_id": str(uuid4()),
        "document_id": request.document_id,
        "feedback": request.feedback,
        "corrected_fields": request.corrected_fields,
        "created_at": datetime.now(UTC).isoformat(),
    }
    feedback_log.append(payload)
    async with httpx.AsyncClient(timeout=15.0) as client:
        await client.post(
            f"{settings.storage_service_url}/ocr/feedback",
            json={
                "document_id": request.document_id,
                "feedback": request.feedback,
                "corrected_fields": request.corrected_fields,
                "actor_id": request.actor_id,
                "actor_role": request.actor_role.value,
            },
        )
    _audit(request.actor_id, request.actor_role, "quality.feedback", payload["feedback_id"], {})
    return payload


@app.get("/quality/metrics")
async def metrics(actor_role: Role = Role.ANALYST) -> dict[str, Any]:
    _assert_permission(actor_role, "quality:task:read")
    open_tasks = sum(1 for task in tasks.values() if task.status == "open")
    critical_tasks = sum(1 for task in tasks.values() if task.priority == Severity.CRITICAL and task.status == "open")
    resolved_tasks = sum(1 for task in tasks.values() if task.status == "resolved")
    return {
        "open_tasks": open_tasks,
        "critical_open_tasks": critical_tasks,
        "resolved_tasks": resolved_tasks,
        "feedback_items": len(feedback_log),
    }


@app.get("/audit")
async def get_audit(limit: int = 100, actor_role: Role = Role.ADMIN) -> dict[str, Any]:
    _assert_permission(actor_role, "audit:read")
    return {"items": audit_log[-limit:], "count": len(audit_log[-limit:])}
