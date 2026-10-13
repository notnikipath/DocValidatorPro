from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException

from shared.docvalidator_common import (
    AnalyticsRequest,
    AnalyticsResult,
    Role,
    Settings,
    Severity,
    aggregate_amounts,
    build_audit_event,
    docs_per_hour,
    error_recall,
    fraud_probability,
    has_permission,
    non_payment_risk_score,
    normalize_currency,
    normalize_number,
    report_period_by_date,
    validation_accuracy,
)

settings = Settings(service_name="analytics-service", service_port=8504)
app = FastAPI(title="DocValidator Analytics Service", version="1.0.0")

analytics_store: dict[str, AnalyticsResult] = {}
facts: list[dict[str, Any]] = []
audit_log: list[dict[str, Any]] = []


def _assert_permission(role: Role, action: str) -> None:
    if not has_permission(role, action):
        raise HTTPException(status_code=403, detail=f"Role {role.value} cannot perform {action}")


def _audit(actor_id: str, actor_role: Role, action: str, object_id: str, details: dict[str, Any]) -> None:
    event = build_audit_event(
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        object_type="analytics",
        object_id=object_id,
        details=details,
    )
    audit_log.append(event.model_dump(mode="json"))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/analytics/calculate")
async def calculate(request: AnalyticsRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "analytics:forecast")
    document = request.document
    fields = document.fields
    validation = request.validation_result
    comparison = request.comparison_result

    amount = normalize_number(fields.get("total_amount") or fields.get("amount") or 0) or 0.0
    currency = normalize_currency(fields.get("currency") or "RUB")
    counterparty = str(fields.get("counterparty_name") or fields.get("party_b") or "unknown")
    period = report_period_by_date(fields.get("issue_date") or fields.get("date") or document.created_at)

    predicted_risk = non_payment_risk_score(
        amount=amount,
        delay_days=int(document.metadata.get("delay_days", 0) or 0),
        historical_failures=int(document.metadata.get("historical_failures", 0) or 0),
        counterparty_risk=float(document.metadata.get("counterparty_risk", 0.15) or 0.15),
    )
    metadata_flags = int(bool(document.metadata.get("edited_after_signing"))) + int(
        bool(document.metadata.get("source_mismatch"))
    )
    fraud_score = fraud_probability(
        anomaly_score=validation.anomaly_score,
        suspicious_change_score=comparison.suspicious_change_score,
        metadata_flags=metadata_flags,
    )

    result = AnalyticsResult(
        document_id=document.document_id,
        amount=round(amount, 2),
        currency=currency,
        counterparty=counterparty,
        reporting_period=period,
        predicted_risk_of_non_payment=predicted_risk,
        fraud_probability=fraud_score,
        kpi={
            "format_score": validation.format_score,
            "logic_score": validation.logic_score,
            "semantic_score": validation.semantic_score,
            "issues_total": float(len(validation.issues)),
            "change_ratio": comparison.change_ratio,
            "suspicious_change_score": comparison.suspicious_change_score,
        },
        generated_at=datetime.now(UTC),
    )
    analytics_store[result.document_id] = result
    facts.append(
        {
            "document_id": result.document_id,
            "period": result.reporting_period,
            "amount": result.amount,
            "counterparty": result.counterparty,
            "risk": result.predicted_risk_of_non_payment,
            "fraud": result.fraud_probability,
            "checked_at": result.generated_at.isoformat(),
            "issues_total": len(validation.issues),
            "critical_issues": sum(1 for issue in validation.issues if issue.severity == Severity.CRITICAL),
            "status": validation.status.value,
        }
    )
    _audit(
        request.actor_id,
        request.actor_role,
        "analytics.calculate",
        document.document_id,
        {"risk": predicted_risk, "fraud": fraud_score, "period": period},
    )
    return result.model_dump(mode="json")




@app.get("/analytics/report")
async def report(period: str | None = None, actor_role: Role = Role.ANALYST) -> dict[str, Any]:
    _assert_permission(actor_role, "analytics:read")
    selected = [item for item in facts if (not period or item["period"] == period)]
    totals = aggregate_amounts(selected)
    counterparties: dict[str, float] = {}
    for item in selected:
        counterparty = str(item["counterparty"])
        counterparties[counterparty] = round(counterparties.get(counterparty, 0.0) + float(item["amount"]), 2)
    top_counterparties = sorted(counterparties.items(), key=lambda row: row[1], reverse=True)[:10]
    return {
        "period_filter": period,
        "documents": len(selected),
        "amounts_by_period": totals,
        "top_counterparties": [{"name": name, "amount": amount} for name, amount in top_counterparties],
        "avg_risk": round(sum(item["risk"] for item in selected) / max(len(selected), 1), 4),
        "avg_fraud_probability": round(sum(item["fraud"] for item in selected) / max(len(selected), 1), 4),
    }


@app.get("/analytics/risk-forecast")
async def risk_forecast(limit: int = 20, actor_role: Role = Role.ANALYST) -> dict[str, Any]:
    _assert_permission(actor_role, "analytics:forecast")
    ranked = sorted(facts, key=lambda item: (item["risk"] + item["fraud"]), reverse=True)
    return {"items": ranked[:limit], "count": min(limit, len(ranked))}


@app.get("/analytics/dashboard")
async def dashboard(elapsed_seconds: float = 3600.0, actor_role: Role = Role.ANALYST) -> dict[str, Any]:
    _assert_permission(actor_role, "dashboard:read")
    total = len(facts)
    failed_checks = sum(item["issues_total"] for item in facts)
    true_positives = sum(item["critical_issues"] for item in facts)
    false_negatives = max(int(total * 0.02), 1) if total else 0
    accuracy = validation_accuracy(total_checks=max(total * 10, 1), failed_checks=int(failed_checks))
    recall = error_recall(true_positives=true_positives, false_negatives=false_negatives)
    throughput = docs_per_hour(total, elapsed_seconds)
    review_items = sum(1 for item in facts if item["status"] != "verified")
    return {
        "total_documents": total,
        "validation_accuracy": accuracy,
        "error_recall": recall,
        "processing_throughput_docs_per_hour": throughput,
        "needs_review_ratio": round(review_items / max(total, 1), 4),
        "target_validation_accuracy": settings.target_validation_accuracy,
        "target_error_recall": settings.target_error_recall,
        "target_docs_per_hour": settings.target_docs_per_hour,
    }


@app.get("/audit")
async def get_audit(limit: int = 100, actor_role: Role = Role.ADMIN) -> dict[str, Any]:
    _assert_permission(actor_role, "audit:read")
    return {"items": audit_log[-limit:], "count": len(audit_log[-limit:])}


@app.get("/analytics/{document_id}")
async def get_document_analytics(document_id: str, actor_role: Role = Role.ANALYST) -> dict[str, Any]:
    _assert_permission(actor_role, "analytics:read")
    result = analytics_store.get(document_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Analytics not found")
    return result.model_dump(mode="json")
