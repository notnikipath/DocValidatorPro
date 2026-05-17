from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class DocumentType(str, Enum):
    FINANCIAL = "financial"
    LEGAL = "legal"
    HR = "hr"
    MEDICAL = "medical"
    TECHNICAL = "technical"


class InputFormat(str, Enum):
    JSON = "json"
    XML = "xml"
    OCR_API = "ocr_api"
    MANUAL = "manual"


class ValidationStatus(str, Enum):
    NEW = "new"
    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    VERIFIED = "verified"
    REJECTED = "rejected"


class ValidationStage(str, Enum):
    FORMAT = "format"
    LOGIC = "logic"
    SEMANTIC = "semantic"
    ANOMALY = "anomaly"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class RuleType(str, Enum):
    FORMAT = "format"
    LOGIC = "logic"
    SEMANTIC = "semantic"


class Role(str, Enum):
    AUDITOR = "auditor"
    ANALYST = "analyst"
    ADMIN = "admin"


class ExportTarget(str, Enum):
    ERP = "erp"
    CRM = "crm"
    DOCFLOW = "docflow"
    WEBHOOK = "webhook"


class NotificationChannel(str, Enum):
    EMAIL = "email"
    WEBHOOK = "webhook"
    SYSTEM = "system"


class RuleDefinition(BaseModel):
    rule_id: str
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
    version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RuleImportRecord(BaseModel):
    name: str
    document_type: DocumentType
    rule_type: RuleType
    target_field: str
    pattern: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    severity: Severity = Severity.WARNING
    description: str = ""


class IngestionRequest(BaseModel):
    client_id: str = Field(min_length=2)
    project_id: str = Field(default="default")
    document_type: DocumentType
    source: InputFormat
    language: str = Field(default="ru", pattern="^(ru|en)$")
    external_id: str | None = None
    payload_json: dict[str, Any] | None = None
    payload_xml: str | None = None
    manual_fields: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    actor_id: str
    actor_role: Role
    auto_validate: bool = True

    @model_validator(mode="after")
    def validate_payload(self) -> IngestionRequest:
        content_count = 0
        if self.payload_json:
            content_count += 1
        if self.payload_xml:
            content_count += 1
        if self.manual_fields:
            content_count += 1
        if content_count == 0:
            raise ValueError("At least one payload source must be provided")
        return self


class DocumentRecord(BaseModel):
    document_id: str
    client_id: str
    project_id: str
    document_type: DocumentType
    source: InputFormat
    language: str
    external_id: str | None = None
    version: int = 1
    status: ValidationStatus = ValidationStatus.NEW
    fields: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str
    previous_version_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ValidationIssue(BaseModel):
    issue_id: str
    stage: ValidationStage
    message: str
    severity: Severity = Severity.WARNING
    field_name: str | None = None
    rule_id: str | None = None
    current_value: Any | None = None
    suggested_value: Any | None = None
    confidence: float = Field(default=0.8, ge=0, le=1)


class ValidationRequest(BaseModel):
    document: DocumentRecord
    rules: list[RuleDefinition] = Field(default_factory=list)
    actor_id: str
    actor_role: Role


class ValidationResult(BaseModel):
    document_id: str
    status: ValidationStatus
    format_score: float = Field(ge=0, le=1)
    logic_score: float = Field(ge=0, le=1)
    semantic_score: float = Field(ge=0, le=1)
    anomaly_score: float = Field(ge=0, le=1)
    issues: list[ValidationIssue] = Field(default_factory=list)
    auto_corrections: dict[str, Any] = Field(default_factory=dict)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ComparisonRequest(BaseModel):
    document: DocumentRecord
    reference_document: DocumentRecord | None = None
    actor_id: str
    actor_role: Role


class FieldDiff(BaseModel):
    field_name: str
    old_value: Any | None = None
    new_value: Any | None = None
    changed: bool = True


class ComparisonResult(BaseModel):
    document_id: str
    duplicate_of: str | None = None
    version_of: str | None = None
    change_ratio: float = Field(ge=0, le=1)
    suspicious_change_score: float = Field(ge=0, le=1)
    diffs: list[FieldDiff] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AnalyticsRequest(BaseModel):
    document: DocumentRecord
    validation_result: ValidationResult
    comparison_result: ComparisonResult
    actor_id: str
    actor_role: Role


class AnalyticsResult(BaseModel):
    document_id: str
    amount: float = 0
    currency: str = "RUB"
    counterparty: str | None = None
    reporting_period: str
    predicted_risk_of_non_payment: float = Field(ge=0, le=1)
    fraud_probability: float = Field(ge=0, le=1)
    kpi: dict[str, float] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class QualityTask(BaseModel):
    task_id: str
    document_id: str
    priority: Severity
    title: str
    description: str
    assignee: str | None = None
    status: str = "open"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExportRequest(BaseModel):
    document_id: str
    target: ExportTarget
    payload: dict[str, Any]
    destination: str
    actor_id: str
    actor_role: Role


class ExportResult(BaseModel):
    export_id: str
    document_id: str
    target: ExportTarget
    destination: str
    status: str
    payload_preview: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class NotificationEvent(BaseModel):
    event_id: str
    channel: NotificationChannel
    recipient: str
    subject: str
    body: str
    severity: Severity = Severity.INFO
    document_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuditEvent(BaseModel):
    event_id: str
    actor_id: str
    actor_role: Role | str
    action: str
    object_type: str
    object_id: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class VerificationWorkflowResult(BaseModel):
    document: DocumentRecord
    validation: ValidationResult
    comparison: ComparisonResult
    analytics: AnalyticsResult
    quality_task: QualityTask | None = None
    export: ExportResult | None = None
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
