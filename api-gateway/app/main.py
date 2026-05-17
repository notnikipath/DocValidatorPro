from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from shared.docvalidator_common import (
    ExportTarget,
    Role,
    Settings,
    VerificationWorkflowResult,
    sign_token,
    verify_token,
)

settings = Settings(service_name="api-gateway", service_port=8500)
app = FastAPI(title="DocValidator Pro API Gateway", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5177",
        "http://127.0.0.1:5177",
        "http://localhost:5176",
        "http://127.0.0.1:5176",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuthRequest(BaseModel):
    user_id: str
    role: Role
    language: str = Field(default="ru", pattern="^(ru|en)$")


class WorkflowRequest(BaseModel):
    document_id: str
    actor_id: str
    actor_role: Role
    export_target: ExportTarget | None = None
    webhook_url: str | None = None


class BatchWorkflowRequest(BaseModel):
    document_ids: list[str]
    actor_id: str
    actor_role: Role
    parallelism: int = Field(default=8, ge=1, le=32)
    export_target: ExportTarget | None = None


class ManualCorrectionRequest(BaseModel):
    fields_patch: dict[str, Any]
    reason: str = "manual correction from gateway"
    actor_id: str
    actor_role: Role
    rerun_workflow: bool = True


class RuleCreateProxyRequest(BaseModel):
    name: str
    description: str = ""
    document_types: list[str] = Field(default_factory=list)
    rule_type: str
    target_field: str
    pattern: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    expression: str | None = None
    severity: str = "warning"
    enabled: bool = True
    actor_id: str
    actor_role: Role


class RuleImportProxyRequest(BaseModel):
    csv_text: str
    actor_id: str
    actor_role: Role


class RuleUpdateProxyRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    document_types: list[str] | None = None
    rule_type: str | None = None
    target_field: str | None = None
    pattern: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    expression: str | None = None
    severity: str | None = None
    enabled: bool | None = None
    actor_id: str
    actor_role: Role


def _service_urls() -> dict[str, str]:
    return {
        "data_ingestion": settings.data_ingestion_service_url,
        "validation": settings.validation_service_url,
        "comparison": settings.comparison_service_url,
        "analytics": settings.analytics_service_url,
        "quality": settings.quality_service_url,
        "export": settings.export_service_url,
        "storage": settings.storage_service_url,
        "notification": settings.notification_service_url,
    }


async def _post_json(client: httpx.AsyncClient, url: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = await client.post(url, json=payload)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


async def _get_json(client: httpx.AsyncClient, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = await client.get(url, params=params)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


async def _put_json(client: httpx.AsyncClient, url: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = await client.put(url, json=payload)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


async def _run_workflow(client: httpx.AsyncClient, request: WorkflowRequest) -> dict[str, Any]:
    document = await _get_json(
        client,
        f"{settings.storage_service_url}/documents/{request.document_id}",
        {"actor_role": request.actor_role.value},
    )
    rules_response = await _get_json(
        client,
        f"{settings.storage_service_url}/rules",
        {"document_type": document["document_type"], "actor_role": request.actor_role.value},
    )
    rules = rules_response.get("items", [])

    validation = await _post_json(
        client,
        f"{settings.validation_service_url}/validate",
        {
            "document": document,
            "rules": rules,
            "actor_id": request.actor_id,
            "actor_role": request.actor_role.value,
        },
    )
    comparison = await _post_json(
        client,
        f"{settings.comparison_service_url}/compare",
        {
            "document": document,
            "actor_id": request.actor_id,
            "actor_role": request.actor_role.value,
        },
    )
    analytics = await _post_json(
        client,
        f"{settings.analytics_service_url}/analytics/calculate",
        {
            "document": document,
            "validation_result": validation,
            "comparison_result": comparison,
            "actor_id": request.actor_id,
            "actor_role": request.actor_role.value,
        },
    )
    quality = await _post_json(
        client,
        f"{settings.quality_service_url}/quality/evaluate",
        {
            "document": document,
            "validation_result": validation,
            "comparison_result": comparison,
            "analytics_result": analytics,
            "actor_id": request.actor_id,
            "actor_role": request.actor_role.value,
        },
    )

    await _post_json(
        client,
        f"{settings.storage_service_url}/results/validation",
        {"result": validation, "actor_id": request.actor_id, "actor_role": request.actor_role.value},
    )
    await _post_json(
        client,
        f"{settings.storage_service_url}/results/comparison",
        {"result": comparison, "actor_id": request.actor_id, "actor_role": request.actor_role.value},
    )
    await _post_json(
        client,
        f"{settings.storage_service_url}/results/analytics",
        {"result": analytics, "actor_id": request.actor_id, "actor_role": request.actor_role.value},
    )
    if quality.get("task"):
        await _post_json(
            client,
            f"{settings.storage_service_url}/results/quality-task",
            {"task": quality["task"], "actor_id": request.actor_id, "actor_role": request.actor_role.value},
        )

    export_result: dict[str, Any] | None = None
    if request.export_target:
        export_result = await _post_json(
            client,
            f"{settings.export_service_url}/export",
            {
                "document_id": request.document_id,
                "target": request.export_target.value,
                "destination": f"{request.export_target.value}-integration",
                "payload": {
                    "document": document,
                    "validation": validation,
                    "comparison": comparison,
                    "analytics": analytics,
                },
                "actor_id": request.actor_id,
                "actor_role": request.actor_role.value,
            },
        )
        await _post_json(
            client,
            f"{settings.storage_service_url}/results/export",
            {"export": export_result, "actor_id": request.actor_id, "actor_role": request.actor_role.value},
        )

    if request.webhook_url:
        await _post_json(
            client,
            f"{settings.export_service_url}/export/webhooks",
            {"url": request.webhook_url, "actor_id": request.actor_id, "actor_role": request.actor_role.value},
        )
        await _post_json(
            client,
            f"{settings.export_service_url}/export/webhook/notify",
            {
                "url": request.webhook_url,
                "payload": {
                    "document_id": request.document_id,
                    "status": validation["status"],
                    "completed_at": datetime.now(UTC).isoformat(),
                },
                "actor_id": request.actor_id,
                "actor_role": request.actor_role.value,
            },
        )

    await _post_json(
        client,
        f"{settings.storage_service_url}/documents/{request.document_id}/status",
        {"status": validation["status"], "actor_id": request.actor_id, "actor_role": request.actor_role.value},
    )

    critical = validation["status"] == "rejected" or quality.get("priority") == "critical"
    if critical:
        await _post_json(
            client,
            f"{settings.notification_service_url}/notify/critical",
            {
                "recipient": document.get("metadata", {}).get("owner_email", "audit@docvalidator.local"),
                "subject": "Critical document verification issue",
                "body": f"Document {request.document_id} requires immediate attention.",
                "document_id": request.document_id,
                "actor_id": request.actor_id,
                "actor_role": request.actor_role.value,
            },
        )
    else:
        await _post_json(
            client,
            f"{settings.notification_service_url}/notify",
            {
                "channel": "system",
                "recipient": document.get("metadata", {}).get("owner_email", "analyst@docvalidator.local"),
                "subject": "Document validation completed",
                "body": f"Document {request.document_id} processed with status {validation['status']}.",
                "severity": "info",
                "document_id": request.document_id,
                "actor_id": request.actor_id,
                "actor_role": request.actor_role.value,
            },
        )

    workflow = VerificationWorkflowResult(
        document=document,
        validation=validation,
        comparison=comparison,
        analytics=analytics,
        quality_task=quality.get("task"),
        export=export_result,
        completed_at=datetime.now(UTC),
    ).model_dump(mode="json")
    await _post_json(
        client,
        f"{settings.storage_service_url}/results/workflow",
        {"workflow_result": workflow, "actor_id": request.actor_id, "actor_role": request.actor_role.value},
    )
    return workflow


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/auth/token")
async def issue_token(request: AuthRequest) -> dict[str, str]:
    token = sign_token(
        {"sub": request.user_id, "role": request.role.value, "language": request.language},
        settings.jwt_secret,
        exp_minutes=settings.token_exp_minutes,
    )
    return {"access_token": token, "token_type": "Bearer"}


@app.post("/auth/verify")
async def verify_auth(token: str) -> dict[str, Any]:
    payload = verify_token(token, settings.jwt_secret)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload


@app.get("/services/health")
async def services_health() -> dict[str, Any]:
    statuses: dict[str, Any] = {}
    async with httpx.AsyncClient(timeout=10.0) as client:
        for name, base_url in _service_urls().items():
            try:
                statuses[name] = await _get_json(client, f"{base_url}/health")
            except Exception as exc:  # noqa: BLE001
                statuses[name] = {"status": "error", "detail": str(exc)}
    return statuses


@app.post("/workflow/validate-document")
async def validate_document(request: WorkflowRequest) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=90.0) as client:
        return await _run_workflow(client, request)


@app.post("/workflow/batch-validate")
async def batch_validate(request: BatchWorkflowRequest) -> dict[str, Any]:
    started = datetime.now(UTC)
    semaphore = asyncio.Semaphore(request.parallelism)

    async def _task(document_id: str) -> dict[str, Any]:
        async with semaphore:
            workflow_request = WorkflowRequest(
                document_id=document_id,
                actor_id=request.actor_id,
                actor_role=request.actor_role,
                export_target=request.export_target,
            )
            async with httpx.AsyncClient(timeout=90.0) as client:
                return await _run_workflow(client, workflow_request)

    results = await asyncio.gather(
        *[_task(document_id) for document_id in request.document_ids],
        return_exceptions=True,
    )
    succeeded: list[dict[str, Any]] = []
    failed: list[str] = []
    for item in results:
        if isinstance(item, Exception):
            failed.append(str(item))
        else:
            succeeded.append(item)
    elapsed = max((datetime.now(UTC) - started).total_seconds(), 0.001)
    throughput = round(len(succeeded) / elapsed * 3600, 2)
    return {
        "items": succeeded,
        "errors": failed,
        "count": len(succeeded),
        "failed_count": len(failed),
        "throughput_docs_per_hour": throughput,
    }


@app.post("/workflow/{document_id}/manual-correction")
async def manual_correction(document_id: str, request: ManualCorrectionRequest) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        corrected = await _post_json(
            client,
            f"{settings.storage_service_url}/documents/{document_id}/corrections",
            {
                "fields_patch": request.fields_patch,
                "reason": request.reason,
                "actor_id": request.actor_id,
                "actor_role": request.actor_role.value,
            },
        )
        workflow = None
        if request.rerun_workflow:
            workflow = await _run_workflow(
                client,
                WorkflowRequest(
                    document_id=corrected["document_id"],
                    actor_id=request.actor_id,
                    actor_role=request.actor_role,
                ),
            )
    return {"corrected_document": corrected, "workflow": workflow}


@app.get("/rules")
async def list_rules(
    actor_role: Role = Role.ANALYST,
    document_type: str | None = None,
    enabled_only: bool = True,
) -> dict[str, Any]:
    params: dict[str, Any] = {"actor_role": actor_role.value, "enabled_only": str(enabled_only).lower()}
    if document_type:
        params["document_type"] = document_type
    async with httpx.AsyncClient(timeout=20.0) as client:
        return await _get_json(client, f"{settings.storage_service_url}/rules", params)


@app.post("/rules")
async def create_rule(request: RuleCreateProxyRequest) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        return await _post_json(client, f"{settings.storage_service_url}/rules", request.model_dump(mode="json"))


@app.put("/rules/{rule_id}")
async def update_rule(rule_id: str, request: RuleUpdateProxyRequest) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        return await _put_json(
            client,
            f"{settings.storage_service_url}/rules/{rule_id}",
            request.model_dump(mode="json"),
        )


@app.post("/rules/import/csv")
async def import_rules(request: RuleImportProxyRequest) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        return await _post_json(
            client,
            f"{settings.storage_service_url}/rules/import/csv",
            request.model_dump(mode="json"),
        )


@app.get("/dashboard/overview")
async def dashboard_overview(actor_role: Role = Role.ANALYST) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        summary = await _get_json(client, f"{settings.storage_service_url}/summary", {"actor_role": actor_role.value})
        analytics = await _get_json(
            client,
            f"{settings.analytics_service_url}/analytics/dashboard",
            {"actor_role": actor_role.value},
        )
        quality = await _get_json(
            client,
            f"{settings.quality_service_url}/quality/metrics",
            {"actor_role": actor_role.value},
        )
        tasks = await _get_json(
            client,
            f"{settings.quality_service_url}/quality/tasks",
            {"status": "open", "actor_role": actor_role.value},
        )
        notifications = await _get_json(
            client,
            f"{settings.notification_service_url}/notify/history",
            {"limit": 20, "actor_role": actor_role.value},
        )
        risk = await _get_json(
            client,
            f"{settings.analytics_service_url}/analytics/risk-forecast",
            {"limit": 10, "actor_role": actor_role.value},
        )
    return {
        "summary": summary,
        "analytics": analytics,
        "quality": quality,
        "open_tasks": tasks,
        "notifications": notifications,
        "risk_forecast": risk,
    }
