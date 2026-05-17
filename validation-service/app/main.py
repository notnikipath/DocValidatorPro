from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException

from shared.docvalidator_common import (
    DocumentRecord,
    DocumentType,
    Role,
    RuleDefinition,
    RuleType,
    Settings,
    Severity,
    ValidationIssue,
    ValidationRequest,
    ValidationResult,
    ValidationStage,
    ValidationStatus,
    build_audit_event,
    has_permission,
    normalize_currency,
    normalize_number,
    outlier_score,
    parse_date,
    validate_inn,
    validate_phone,
)

settings = Settings(service_name="validation-service", service_port=8502)
app = FastAPI(title="DocValidator Validation Service", version="1.0.0")

audit_log: list[dict[str, Any]] = []


def _assert_permission(role: Role, action: str) -> None:
    if not has_permission(role, action):
        raise HTTPException(status_code=403, detail=f"Role {role.value} cannot perform {action}")


def _audit(actor_id: str, actor_role: Role, action: str, object_id: str, details: dict[str, Any]) -> None:
    event = build_audit_event(
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        object_type="validation",
        object_id=object_id,
        details=details,
    )
    audit_log.append(event.model_dump(mode="json"))


def _issue(
    stage: ValidationStage,
    message: str,
    field_name: str | None = None,
    severity: Severity = Severity.WARNING,
    rule_id: str | None = None,
    current_value: Any | None = None,
    suggested_value: Any | None = None,
    confidence: float = 0.8,
) -> ValidationIssue:
    return ValidationIssue(
        issue_id=str(uuid4()),
        stage=stage,
        message=message,
        field_name=field_name,
        severity=severity,
        rule_id=rule_id,
        current_value=current_value,
        suggested_value=suggested_value,
        confidence=confidence,
    )


def _default_rules() -> list[RuleDefinition]:
    return [
        RuleDefinition(
            rule_id="RULE-DEFAULT-INN",
            name="INN checksum",
            description="INN must pass checksum validation",
            document_types=[DocumentType.FINANCIAL, DocumentType.LEGAL],
            rule_type=RuleType.FORMAT,
            target_field="counterparty_inn",
            severity=Severity.CRITICAL,
        ),
        RuleDefinition(
            rule_id="RULE-DEFAULT-AMOUNT",
            name="Amount must be positive",
            description="Total amount should be non-negative",
            document_types=[DocumentType.FINANCIAL],
            rule_type=RuleType.FORMAT,
            target_field="total_amount",
            min_value=0,
            severity=Severity.CRITICAL,
        ),
        RuleDefinition(
            rule_id="RULE-DEFAULT-DATE-ORDER",
            name="Issue date before due date",
            description="issue_date should be <= due_date",
            document_types=[DocumentType.FINANCIAL, DocumentType.LEGAL],
            rule_type=RuleType.LOGIC,
            target_field="issue_date",
            expression="issue_date <= due_date",
            severity=Severity.WARNING,
        ),
    ]


def _check_builtin_format(document: DocumentRecord) -> tuple[list[ValidationIssue], dict[str, Any]]:
    issues: list[ValidationIssue] = []
    auto_corrections: dict[str, Any] = {}
    fields = document.fields
    for key, value in fields.items():
        key_lower = key.lower()
        if "date" in key_lower:
            if parse_date(value) is None:
                issues.append(
                    _issue(
                        ValidationStage.FORMAT,
                        "Invalid date format",
                        field_name=key,
                        current_value=value,
                        severity=Severity.WARNING,
                    )
                )
        if any(marker in key_lower for marker in ["amount", "sum", "price", "total", "tax", "quantity"]):
            number = normalize_number(value)
            if number is None:
                issues.append(
                    _issue(
                        ValidationStage.FORMAT,
                        "Numeric field has invalid format",
                        field_name=key,
                        current_value=value,
                        severity=Severity.CRITICAL,
                    )
                )
            elif key_lower in {"total_amount", "amount", "sum"} and number < 0:
                issues.append(
                    _issue(
                        ValidationStage.FORMAT,
                        "Amount cannot be negative",
                        field_name=key,
                        current_value=value,
                        severity=Severity.CRITICAL,
                    )
                )
        if "inn" in key_lower and not validate_inn(value):
            issues.append(
                _issue(
                    ValidationStage.FORMAT,
                    "INN is invalid",
                    field_name=key,
                    current_value=value,
                    severity=Severity.CRITICAL,
                )
            )
        if "phone" in key_lower and not validate_phone(value):
            cleaned = re.sub(r"[^\d+]", "", str(value))
            issues.append(
                _issue(
                    ValidationStage.FORMAT,
                    "Phone number format is invalid",
                    field_name=key,
                    current_value=value,
                    suggested_value=cleaned,
                    severity=Severity.WARNING,
                    confidence=0.86,
                )
            )
            auto_corrections[key] = cleaned
    currency_value = fields.get("currency")
    if currency_value is not None:
        normalized_currency = normalize_currency(currency_value)
        if normalized_currency != str(currency_value).upper():
            issues.append(
                _issue(
                    ValidationStage.FORMAT,
                    "Currency was normalized",
                    field_name="currency",
                    current_value=currency_value,
                    suggested_value=normalized_currency,
                    severity=Severity.INFO,
                    confidence=0.95,
                )
            )
            auto_corrections["currency"] = normalized_currency
    return issues, auto_corrections


def _check_rule_format(document: DocumentRecord, rules: list[RuleDefinition]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for rule in rules:
        if not rule.enabled or rule.rule_type != RuleType.FORMAT:
            continue
        if rule.document_types and document.document_type not in rule.document_types:
            continue
        value = document.fields.get(rule.target_field)
        if value is None:
            continue
        if rule.pattern and not re.search(rule.pattern, str(value)):
            issues.append(
                _issue(
                    ValidationStage.FORMAT,
                    "Rule pattern validation failed",
                    field_name=rule.target_field,
                    rule_id=rule.rule_id,
                    current_value=value,
                    severity=rule.severity,
                )
            )
        numeric = normalize_number(value)
        if numeric is not None:
            if rule.min_value is not None and numeric < rule.min_value:
                issues.append(
                    _issue(
                        ValidationStage.FORMAT,
                        f"Value is below minimum {rule.min_value}",
                        field_name=rule.target_field,
                        rule_id=rule.rule_id,
                        current_value=value,
                        severity=rule.severity,
                    )
                )
            if rule.max_value is not None and numeric > rule.max_value:
                issues.append(
                    _issue(
                        ValidationStage.FORMAT,
                        f"Value is above maximum {rule.max_value}",
                        field_name=rule.target_field,
                        rule_id=rule.rule_id,
                        current_value=value,
                        severity=rule.severity,
                    )
                )
    return issues


def _check_logic(document: DocumentRecord, rules: list[RuleDefinition]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    fields = document.fields
    subtotal = normalize_number(fields.get("subtotal"))
    tax = normalize_number(fields.get("tax_amount"))
    total = normalize_number(fields.get("total_amount"))
    if subtotal is not None and tax is not None and total is not None:
        if abs((subtotal + tax) - total) > 1.0:
            issues.append(
                _issue(
                    ValidationStage.LOGIC,
                    "Arithmetic mismatch: subtotal + tax != total_amount",
                    field_name="total_amount",
                    severity=Severity.CRITICAL,
                    current_value=total,
                    suggested_value=round(subtotal + tax, 2),
                    confidence=0.98,
                )
            )
    quantity = normalize_number(fields.get("quantity"))
    unit_price = normalize_number(fields.get("unit_price"))
    if quantity is not None and unit_price is not None and total is not None:
        calculated = round(quantity * unit_price, 2)
        if abs(calculated - total) > 1.0:
            issues.append(
                _issue(
                    ValidationStage.LOGIC,
                    "Quantity * unit_price does not match total_amount",
                    field_name="total_amount",
                    severity=Severity.WARNING,
                    current_value=total,
                    suggested_value=calculated,
                    confidence=0.93,
                )
            )

    issue_date = parse_date(fields.get("issue_date"))
    due_date = parse_date(fields.get("due_date"))
    if issue_date and due_date and issue_date > due_date:
        issues.append(
            _issue(
                ValidationStage.LOGIC,
                "issue_date is later than due_date",
                field_name="issue_date",
                severity=Severity.WARNING,
            )
        )

    start_date = parse_date(fields.get("start_date"))
    end_date = parse_date(fields.get("end_date"))
    if start_date and end_date and start_date > end_date:
        issues.append(
            _issue(
                ValidationStage.LOGIC,
                "start_date is later than end_date",
                field_name="start_date",
                severity=Severity.WARNING,
            )
        )

    for rule in rules:
        if not rule.enabled or rule.rule_type != RuleType.LOGIC:
            continue
        if rule.document_types and document.document_type not in rule.document_types:
            continue
        if rule.expression == "issue_date <= due_date" and issue_date and due_date and issue_date > due_date:
            issues.append(
                _issue(
                    ValidationStage.LOGIC,
                    "Custom rule expression failed: issue_date <= due_date",
                    field_name=rule.target_field,
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                )
            )
    return issues


def _check_semantic(document: DocumentRecord, rules: list[RuleDefinition]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    fields = document.fields

    if document.document_type == DocumentType.LEGAL:
        subject = str(fields.get("contract_subject", "")).strip()
        party_a = str(fields.get("party_a", "")).strip()
        party_b = str(fields.get("party_b", "")).strip()
        if len(subject) < 8:
            issues.append(
                _issue(
                    ValidationStage.SEMANTIC,
                    "Contract subject is too short or missing",
                    field_name="contract_subject",
                    severity=Severity.WARNING,
                )
            )
        if party_a and party_b and party_a.lower() == party_b.lower():
            issues.append(
                _issue(
                    ValidationStage.SEMANTIC,
                    "Both legal parties look identical",
                    field_name="party_b",
                    severity=Severity.CRITICAL,
                )
            )

    if document.document_type == DocumentType.MEDICAL:
        if fields.get("diagnosis") and not fields.get("conclusion"):
            issues.append(
                _issue(
                    ValidationStage.SEMANTIC,
                    "Medical diagnosis without final conclusion",
                    field_name="conclusion",
                    severity=Severity.WARNING,
                )
            )

    if document.document_type == DocumentType.HR:
        if not fields.get("full_name"):
            issues.append(
                _issue(
                    ValidationStage.SEMANTIC,
                    "Resume missing full_name",
                    field_name="full_name",
                    severity=Severity.WARNING,
                )
            )

    text_blob = " ".join(str(value).lower() for value in fields.values() if value is not None)
    suspicious_markers = ("подделка", "fake", "forged", "xxxxx")
    if any(marker in text_blob for marker in suspicious_markers):
        issues.append(
            _issue(
                ValidationStage.SEMANTIC,
                "Suspicious wording found in document content",
                severity=Severity.CRITICAL,
                confidence=0.91,
            )
        )

    for rule in rules:
        if not rule.enabled or rule.rule_type != RuleType.SEMANTIC:
            continue
        if rule.document_types and document.document_type not in rule.document_types:
            continue
        value = document.fields.get(rule.target_field)
        if value is None:
            continue
        if rule.pattern and not re.search(rule.pattern, str(value), flags=re.IGNORECASE):
            issues.append(
                _issue(
                    ValidationStage.SEMANTIC,
                    "Semantic rule pattern mismatch",
                    field_name=rule.target_field,
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                )
            )
    return issues


def _check_anomaly(document: DocumentRecord) -> tuple[list[ValidationIssue], float]:
    issues: list[ValidationIssue] = []
    fields = document.fields
    amount = normalize_number(fields.get("total_amount") or fields.get("amount"))
    history_raw = document.metadata.get("historical_amounts", [])
    history = [number for number in [normalize_number(item) for item in history_raw] if number is not None]
    anomaly = 0.0
    if amount is not None and history:
        anomaly = outlier_score(history, amount)
        if anomaly >= 0.6:
            issues.append(
                _issue(
                    ValidationStage.ANOMALY,
                    "Document amount is an outlier compared to historical values",
                    field_name="total_amount",
                    severity=Severity.WARNING if anomaly < 0.8 else Severity.CRITICAL,
                    current_value=amount,
                    confidence=min(0.99, 0.65 + anomaly / 2),
                )
            )
    if document.metadata.get("edited_after_signing"):
        anomaly = max(anomaly, 0.85)
        issues.append(
            _issue(
                ValidationStage.ANOMALY,
                "Metadata indicates post-signing modifications",
                severity=Severity.CRITICAL,
                confidence=0.95,
            )
        )
    return issues, anomaly


def _score(issue_count: int, total_checks: int) -> float:
    if total_checks <= 0:
        return 1.0
    return round(max(0.0, 1 - issue_count / total_checks), 4)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.get("/rules/default")
async def default_rules() -> dict[str, Any]:
    items = [rule.model_dump(mode="json") for rule in _default_rules()]
    return {"items": items, "count": len(items)}


@app.post("/validate")
async def validate(request: ValidationRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "validation:run")
    document = request.document
    rules = request.rules or _default_rules()

    format_issues, auto_corrections = _check_builtin_format(document)
    format_issues.extend(_check_rule_format(document, rules))
    logic_issues = _check_logic(document, rules)
    semantic_issues = _check_semantic(document, rules)
    anomaly_issues, anomaly_score = _check_anomaly(document)

    issues = [*format_issues, *logic_issues, *semantic_issues, *anomaly_issues]
    critical_count = sum(1 for issue in issues if issue.severity == Severity.CRITICAL)
    status = ValidationStatus.VERIFIED if not issues else ValidationStatus.NEEDS_REVIEW
    if critical_count >= 2:
        status = ValidationStatus.REJECTED

    logic_rule_count = len([rule for rule in rules if rule.rule_type == RuleType.LOGIC])
    semantic_rule_count = len([rule for rule in rules if rule.rule_type == RuleType.SEMANTIC])

    result = ValidationResult(
        document_id=document.document_id,
        status=status,
        format_score=_score(len(format_issues), max(len(document.fields), 1) + max(len(rules), 1)),
        logic_score=_score(len(logic_issues), 4 + logic_rule_count),
        semantic_score=_score(len(semantic_issues), 4 + semantic_rule_count),
        anomaly_score=round(min(max(anomaly_score, 0.0), 1.0), 4),
        issues=issues,
        auto_corrections=auto_corrections,
        checked_at=datetime.now(UTC),
    )

    _audit(
        request.actor_id,
        request.actor_role,
        "validation.run",
        document.document_id,
        {
            "issues_total": len(issues),
            "critical": critical_count,
            "status": result.status.value,
            "format_score": result.format_score,
            "logic_score": result.logic_score,
            "semantic_score": result.semantic_score,
            "anomaly_score": result.anomaly_score,
        },
    )
    return result.model_dump(mode="json")


@app.get("/audit")
async def get_audit(limit: int = 100, actor_role: Role = Role.ADMIN) -> dict[str, Any]:
    _assert_permission(actor_role, "audit:read")
    return {"items": audit_log[-limit:], "count": len(audit_log[-limit:])}
