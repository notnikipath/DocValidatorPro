from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from shared.docvalidator_common import (
    AnalyticsResult,
    ComparisonResult,
    DocumentRecord,
    DocumentType,
    Role,
    RuleDefinition,
    RuleImportRecord,
    RuleType,
    Settings,
    Severity,
    ValidationResult,
    ValidationStatus,
    build_audit_event,
    has_permission,
)

settings = Settings(service_name="storage-service", service_port=8507)
app = FastAPI(title="DocValidator Storage Service", version="1.0.0")


def _assert_permission(role: Role, action: str) -> None:
    if not has_permission(role, action):
        raise HTTPException(status_code=403, detail=f"Role {role.value} cannot perform {action}")


documents: dict[str, DocumentRecord] = {}
lineage_index: dict[str, list[str]] = {}
hash_index: dict[str, str] = {}
validation_results: dict[str, ValidationResult] = {}
comparison_results: dict[str, ComparisonResult] = {}
analytics_results: dict[str, AnalyticsResult] = {}
quality_tasks: dict[str, dict[str, Any]] = {}
export_results: dict[str, dict[str, Any]] = {}
workflow_results: dict[str, dict[str, Any]] = {}
audit_log: list[dict[str, Any]] = []
rules_registry: dict[str, list[RuleDefinition]] = {}
ocr_feedback: list[dict[str, Any]] = []


def _seed_rules() -> None:
    defaults = [
        RuleDefinition(
            rule_id="RULE-AMOUNT-POSITIVE",
            name="Amount must be positive",
            description="Financial amount fields must be >= 0",
            document_types=[DocumentType.FINANCIAL],
            rule_type=RuleType.FORMAT,
            target_field="total_amount",
            min_value=0,
            severity=Severity.CRITICAL,
        ),
        RuleDefinition(
            rule_id="RULE-INN-CHECKSUM",
            name="INN checksum validation",
            description="Validate INN checksum for counterparties",
            document_types=[DocumentType.FINANCIAL, DocumentType.LEGAL],
            rule_type=RuleType.FORMAT,
            target_field="counterparty_inn",
            severity=Severity.CRITICAL,
        ),
        RuleDefinition(
            rule_id="RULE-DATE-ORDER",
            name="Issue date before due date",
            description="issue_date should be less than or equal due_date",
            document_types=[DocumentType.FINANCIAL, DocumentType.LEGAL],
            rule_type=RuleType.LOGIC,
            target_field="issue_date",
            expression="issue_date <= due_date",
            severity=Severity.WARNING,
        ),
        RuleDefinition(
            rule_id="RULE-CONTRACT-SUBJECT",
            name="Contract subject completeness",
            description="Legal contracts should have explicit subject and party names",
            document_types=[DocumentType.LEGAL],
            rule_type=RuleType.SEMANTIC,
            target_field="contract_subject",
            severity=Severity.WARNING,
        ),
    ]
    for rule in defaults:
        rules_registry[rule.rule_id] = [rule]


_seed_rules()


class DocumentSaveRequest(BaseModel):
    document: DocumentRecord
    actor_id: str
    actor_role: Role


class DocumentStatusUpdateRequest(BaseModel):
    status: ValidationStatus
    actor_id: str
    actor_role: Role


class CorrectionRequest(BaseModel):
    fields_patch: dict[str, Any]
    reason: str = "manual correction"
    actor_id: str
    actor_role: Role


class RuleCreateRequest(BaseModel):
    name: str
    description: str = ""
    document_types: list[DocumentType] = Field(default_factory=list)
    rule_type: RuleType
    target_field: str
    pattern: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    expression: str | None = None
    severity: Severity = Severity.WARNING
    enabled: bool = True
    actor_id: str
    actor_role: Role


class RuleUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    document_types: list[DocumentType] | None = None
    rule_type: RuleType | None = None
    target_field: str | None = None
    pattern: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    expression: str | None = None
    severity: Severity | None = None
    enabled: bool | None = None
    actor_id: str
    actor_role: Role


class RuleImportCSVRequest(BaseModel):
    csv_text: str
    actor_id: str
    actor_role: Role


class SaveValidationRequest(BaseModel):
    result: ValidationResult
    actor_id: str
    actor_role: Role


class SaveComparisonRequest(BaseModel):
    result: ComparisonResult
    actor_id: str
    actor_role: Role


class SaveAnalyticsRequest(BaseModel):
    result: AnalyticsResult
    actor_id: str
    actor_role: Role


class SaveTaskRequest(BaseModel):
    task: dict[str, Any]
    actor_id: str
    actor_role: Role


class SaveExportRequest(BaseModel):
    export: dict[str, Any]
    actor_id: str
    actor_role: Role


class SaveWorkflowRequest(BaseModel):
    workflow_result: dict[str, Any]
    actor_id: str
    actor_role: Role


class SaveAuditRequest(BaseModel):
    action: str
    object_type: str
    object_id: str
    details: dict[str, Any] = Field(default_factory=dict)
    actor_id: str
    actor_role: Role


class FeedbackRequest(BaseModel):
    document_id: str
    feedback: str
    corrected_fields: dict[str, Any] = Field(default_factory=dict)
    actor_id: str
    actor_role: Role


for _model in (
    DocumentSaveRequest,
    DocumentStatusUpdateRequest,
    CorrectionRequest,
    RuleCreateRequest,
    RuleUpdateRequest,
    RuleImportCSVRequest,
    SaveValidationRequest,
    SaveComparisonRequest,
    SaveAnalyticsRequest,
    SaveTaskRequest,
    SaveExportRequest,
    SaveWorkflowRequest,
    SaveAuditRequest,
    FeedbackRequest,
):
    _model.model_rebuild()


def _audit(
    actor_id: str,
    actor_role: Role,
    action: str,
    object_type: str,
    object_id: str,
    details: dict[str, Any],
) -> None:
    audit_event = build_audit_event(
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        object_type=object_type,
        object_id=object_id,
        details=details,
    )
    audit_log.append(audit_event.model_dump(mode="json"))


def _lineage_for(document: DocumentRecord) -> str:
    marker = document.metadata.get("lineage_id")
    if marker:
        return str(marker)
    if document.external_id:
        return f"{document.client_id}:{document.external_id}"
    return f"{document.client_id}:{document.document_id}"


def _latest_rule(rule_id: str) -> RuleDefinition | None:
    versions = rules_registry.get(rule_id)
    if not versions:
        return None
    return versions[-1]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/documents")
async def save_document(request: DocumentSaveRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "validation:run")
    document = request.document
    if document.document_id in documents:
        raise HTTPException(status_code=409, detail="Document already exists")
    documents[document.document_id] = document
    lineage_id = _lineage_for(document)
    lineage_index.setdefault(lineage_id, []).append(document.document_id)
    hash_index.setdefault(document.content_hash, document.document_id)
    _audit(
        request.actor_id,
        request.actor_role,
        "document.save",
        "document",
        document.document_id,
        {"lineage_id": lineage_id, "version": document.version},
    )
    return {"document": document.model_dump(mode="json"), "lineage_id": lineage_id}


@app.get("/documents/{document_id}")
async def get_document(document_id: str, actor_role: Role = Role.ANALYST) -> dict[str, Any]:
    _assert_permission(actor_role, "document:read")
    document = documents.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document.model_dump(mode="json")


@app.get("/documents")
async def list_documents(
    client_id: str | None = None,
    status: ValidationStatus | None = None,
    document_type: DocumentType | None = None,
    limit: int = 200,
    actor_role: Role = Role.ANALYST,
) -> dict[str, Any]:
    _assert_permission(actor_role, "document:read")
    items = []
    for document in documents.values():
        if client_id and document.client_id != client_id:
            continue
        if status and document.status != status:
            continue
        if document_type and document.document_type != document_type:
            continue
        items.append(document.model_dump(mode="json"))
    items.sort(key=lambda row: row["created_at"], reverse=True)
    return {"items": items[:limit], "count": len(items)}


@app.get("/documents/{document_id}/versions")
async def get_versions(document_id: str, actor_role: Role = Role.ANALYST) -> dict[str, Any]:
    _assert_permission(actor_role, "document:read")
    document = documents.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    lineage_id = _lineage_for(document)
    ids = lineage_index.get(lineage_id, [])
    items = [documents[item_id].model_dump(mode="json") for item_id in ids if item_id in documents]
    return {"lineage_id": lineage_id, "items": items, "count": len(items)}


@app.post("/documents/{document_id}/status")
async def update_status(document_id: str, request: DocumentStatusUpdateRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "quality:task:update")
    document = documents.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    document.status = request.status
    document.updated_at = datetime.now(UTC)
    _audit(
        request.actor_id,
        request.actor_role,
        "document.status.update",
        "document",
        document_id,
        {"status": request.status.value},
    )
    return document.model_dump(mode="json")


@app.post("/documents/{document_id}/corrections")
async def apply_corrections(document_id: str, request: CorrectionRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "quality:task:update")
    current = documents.get(document_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Document not found")

    updated_fields = dict(current.fields)
    updated_fields.update(request.fields_patch)
    next_document = DocumentRecord(
        document_id=str(uuid4()),
        client_id=current.client_id,
        project_id=current.project_id,
        document_type=current.document_type,
        source=current.source,
        language=current.language,
        external_id=current.external_id,
        version=current.version + 1,
        status=ValidationStatus.NEEDS_REVIEW,
        fields=updated_fields,
        metadata={**current.metadata, "lineage_id": _lineage_for(current)},
        content_hash=current.content_hash,
        previous_version_id=current.document_id,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    documents[next_document.document_id] = next_document
    lineage_id = _lineage_for(next_document)
    lineage_index.setdefault(lineage_id, []).append(next_document.document_id)
    _audit(
        request.actor_id,
        request.actor_role,
        "document.corrected",
        "document",
        next_document.document_id,
        {"previous_document_id": document_id, "reason": request.reason},
    )
    return next_document.model_dump(mode="json")


@app.get("/documents/hash/{content_hash}")
async def find_by_hash(content_hash: str, actor_role: Role = Role.ANALYST) -> dict[str, Any]:
    _assert_permission(actor_role, "document:read")
    document_id = hash_index.get(content_hash)
    if document_id is None:
        raise HTTPException(status_code=404, detail="No document with this hash")
    return documents[document_id].model_dump(mode="json")


@app.post("/results/validation")
async def save_validation(request: SaveValidationRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "validation:run")
    validation_results[request.result.document_id] = request.result
    _audit(
        request.actor_id,
        request.actor_role,
        "result.validation.save",
        "validation_result",
        request.result.document_id,
        {"issues": len(request.result.issues)},
    )
    return request.result.model_dump(mode="json")


@app.get("/results/validation/{document_id}")
async def get_validation(document_id: str, actor_role: Role = Role.ANALYST) -> dict[str, Any]:
    _assert_permission(actor_role, "document:read")
    result = validation_results.get(document_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Validation result not found")
    return result.model_dump(mode="json")


@app.post("/results/comparison")
async def save_comparison(request: SaveComparisonRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "comparison:run")
    comparison_results[request.result.document_id] = request.result
    _audit(
        request.actor_id,
        request.actor_role,
        "result.comparison.save",
        "comparison_result",
        request.result.document_id,
        {"change_ratio": request.result.change_ratio},
    )
    return request.result.model_dump(mode="json")


@app.get("/results/comparison/{document_id}")
async def get_comparison(document_id: str, actor_role: Role = Role.ANALYST) -> dict[str, Any]:
    _assert_permission(actor_role, "document:read")
    result = comparison_results.get(document_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Comparison result not found")
    return result.model_dump(mode="json")


@app.post("/results/analytics")
async def save_analytics(request: SaveAnalyticsRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "analytics:forecast")
    analytics_results[request.result.document_id] = request.result
    _audit(
        request.actor_id,
        request.actor_role,
        "result.analytics.save",
        "analytics_result",
        request.result.document_id,
        {"risk": request.result.predicted_risk_of_non_payment},
    )
    return request.result.model_dump(mode="json")


@app.get("/results/analytics/{document_id}")
async def get_analytics(document_id: str, actor_role: Role = Role.ANALYST) -> dict[str, Any]:
    _assert_permission(actor_role, "analytics:read")
    result = analytics_results.get(document_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Analytics result not found")
    return result.model_dump(mode="json")


@app.post("/results/quality-task")
async def save_quality_task(request: SaveTaskRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "quality:task:create")
    task_id = str(request.task.get("task_id") or uuid4())
    task = dict(request.task)
    task["task_id"] = task_id
    task["updated_at"] = datetime.now(UTC).isoformat()
    quality_tasks[task_id] = task
    _audit(
        request.actor_id,
        request.actor_role,
        "quality.task.save",
        "quality_task",
        task_id,
        {"document_id": task.get("document_id")},
    )
    return task


@app.get("/quality/tasks")
async def list_tasks(status: str | None = None, actor_role: Role = Role.ANALYST) -> dict[str, Any]:
    _assert_permission(actor_role, "quality:task:read")
    items = []
    for task in quality_tasks.values():
        if status and task.get("status") != status:
            continue
        items.append(task)
    items.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    return {"items": items, "count": len(items)}


@app.patch("/quality/tasks/{task_id}")
async def update_task(task_id: str, patch: dict[str, Any], actor_id: str, actor_role: Role) -> dict[str, Any]:
    _assert_permission(actor_role, "quality:task:update")
    task = quality_tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    task.update(patch)
    task["updated_at"] = datetime.now(UTC).isoformat()
    _audit(actor_id, actor_role, "quality.task.update", "quality_task", task_id, {"patch": patch})
    return task


@app.post("/results/export")
async def save_export(request: SaveExportRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "quality:task:create")
    export_id = str(request.export.get("export_id") or uuid4())
    payload = dict(request.export)
    payload["export_id"] = export_id
    export_results[export_id] = payload
    _audit(
        request.actor_id,
        request.actor_role,
        "result.export.save",
        "export_result",
        export_id,
        {"document_id": payload.get("document_id")},
    )
    return payload


@app.post("/results/workflow")
async def save_workflow(request: SaveWorkflowRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "quality:task:create")
    document_id = str(request.workflow_result.get("document", {}).get("document_id", "unknown"))
    workflow_results[document_id] = request.workflow_result
    _audit(request.actor_id, request.actor_role, "workflow.save", "workflow", document_id, {})
    return request.workflow_result


@app.get("/results/workflow/{document_id}")
async def get_workflow(document_id: str, actor_role: Role = Role.ANALYST) -> dict[str, Any]:
    _assert_permission(actor_role, "document:read")
    payload = workflow_results.get(document_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Workflow result not found")
    return payload


@app.get("/rules")
async def list_rules(
    document_type: DocumentType | None = None,
    enabled_only: bool = True,
    actor_role: Role = Role.ANALYST,
) -> dict[str, Any]:
    _assert_permission(actor_role, "rule:read")
    items: list[dict[str, Any]] = []
    for versions in rules_registry.values():
        latest = versions[-1]
        if enabled_only and not latest.enabled:
            continue
        if document_type and latest.document_types and document_type not in latest.document_types:
            continue
        items.append(latest.model_dump(mode="json"))
    items.sort(key=lambda row: row["updated_at"], reverse=True)
    return {"items": items, "count": len(items)}


@app.post("/rules")
async def create_rule(request: RuleCreateRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "rule:read")
    rule = RuleDefinition(
        rule_id=str(uuid4()),
        name=request.name,
        description=request.description,
        document_types=request.document_types,
        rule_type=request.rule_type,
        target_field=request.target_field,
        pattern=request.pattern,
        min_value=request.min_value,
        max_value=request.max_value,
        expression=request.expression,
        severity=request.severity,
        enabled=request.enabled,
    )
    rules_registry[rule.rule_id] = [rule]
    _audit(request.actor_id, request.actor_role, "rule.create", "rule", rule.rule_id, {"version": rule.version})
    return rule.model_dump(mode="json")


@app.put("/rules/{rule_id}")
async def update_rule(rule_id: str, request: RuleUpdateRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "rule:read")
    current = _latest_rule(rule_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    updated = current.model_copy(
        update={
            "name": request.name if request.name is not None else current.name,
            "description": request.description if request.description is not None else current.description,
            "document_types": request.document_types if request.document_types is not None else current.document_types,
            "rule_type": request.rule_type if request.rule_type is not None else current.rule_type,
            "target_field": request.target_field if request.target_field is not None else current.target_field,
            "pattern": request.pattern if request.pattern is not None else current.pattern,
            "min_value": request.min_value if request.min_value is not None else current.min_value,
            "max_value": request.max_value if request.max_value is not None else current.max_value,
            "expression": request.expression if request.expression is not None else current.expression,
            "severity": request.severity if request.severity is not None else current.severity,
            "enabled": request.enabled if request.enabled is not None else current.enabled,
            "version": current.version + 1,
            "updated_at": datetime.now(UTC),
        }
    )
    rules_registry[rule_id].append(updated)
    _audit(request.actor_id, request.actor_role, "rule.update", "rule", rule_id, {"version": updated.version})
    return updated.model_dump(mode="json")


@app.post("/rules/import/csv")
async def import_rules(request: RuleImportCSVRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "rule:read")
    reader = csv.DictReader(io.StringIO(request.csv_text))
    created: list[dict[str, Any]] = []
    for row in reader:
        parsed = RuleImportRecord(
            name=str(row.get("name", "")).strip(),
            document_type=DocumentType(str(row.get("document_type", "financial")).strip()),
            rule_type=RuleType(str(row.get("rule_type", "format")).strip()),
            target_field=str(row.get("target_field", "")).strip(),
            pattern=(str(row.get("pattern", "")).strip() or None),
            min_value=float(row["min_value"]) if row.get("min_value") else None,
            max_value=float(row["max_value"]) if row.get("max_value") else None,
            severity=Severity(str(row.get("severity", "warning")).strip()),
            description=str(row.get("description", "")).strip(),
        )
        rule = RuleDefinition(
            rule_id=str(uuid4()),
            name=parsed.name,
            description=parsed.description,
            document_types=[parsed.document_type],
            rule_type=parsed.rule_type,
            target_field=parsed.target_field,
            pattern=parsed.pattern,
            min_value=parsed.min_value,
            max_value=parsed.max_value,
            severity=parsed.severity,
        )
        rules_registry[rule.rule_id] = [rule]
        created.append(rule.model_dump(mode="json"))
    _audit(request.actor_id, request.actor_role, "rule.import.csv", "rule", "bulk", {"count": len(created)})
    return {"items": created, "count": len(created)}


@app.post("/audit")
async def save_audit(request: SaveAuditRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "audit:read")
    _audit(
        request.actor_id,
        request.actor_role,
        request.action,
        request.object_type,
        request.object_id,
        request.details,
    )
    return {"status": "ok"}


@app.get("/audit")
async def get_audit(limit: int = 200, actor_role: Role = Role.ADMIN) -> dict[str, Any]:
    _assert_permission(actor_role, "audit:read")
    return {"items": audit_log[-limit:], "count": len(audit_log[-limit:])}


@app.post("/ocr/feedback")
async def save_feedback(request: FeedbackRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "quality:task:update")
    payload = {
        "feedback_id": str(uuid4()),
        "document_id": request.document_id,
        "feedback": request.feedback,
        "corrected_fields": request.corrected_fields,
        "created_at": datetime.now(UTC).isoformat(),
    }
    ocr_feedback.append(payload)
    _audit(request.actor_id, request.actor_role, "ocr.feedback.save", "ocr_feedback", payload["feedback_id"], {})
    return payload


@app.get("/summary")
async def summary(actor_role: Role = Role.ANALYST) -> dict[str, Any]:
    _assert_permission(actor_role, "dashboard:read")
    total = len(documents)
    verified = sum(1 for document in documents.values() if document.status == ValidationStatus.VERIFIED)
    review = sum(1 for document in documents.values() if document.status == ValidationStatus.NEEDS_REVIEW)
    rejected = sum(1 for document in documents.values() if document.status == ValidationStatus.REJECTED)
    return {
        "documents_total": total,
        "verified": verified,
        "needs_review": review,
        "rejected": rejected,
        "rules_total": len(rules_registry),
        "quality_tasks_open": sum(1 for task in quality_tasks.values() if task.get("status") == "open"),
        "audit_events": len(audit_log),
    }
