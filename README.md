# DocValidator Pro

DocValidator Pro is a microservice platform for automated document verification, anomaly detection, version comparison, quality management, and business analytics.

## Supported document types

- Financial: invoices, acts, waybills
- Legal: contracts, agreements
- HR: resumes, HR orders
- Medical: certificates, conclusions
- Technical: specifications, operational documentation

## Services

- `api-gateway` - unified API, auth, workflow orchestration, dashboards
- `data-ingestion-service` - JSON/XML/manual import, OCR payload intake, auto pipeline trigger
- `validation-service` - format/logic/semantic validation, anomaly checks, correction suggestions
- `comparison-service` - duplicate search, version diff, suspicious change scoring
- `analytics-service` - aggregations, KPI, risk and fraud forecasting
- `quality-service` - issue triage, review tasks, OCR feedback loop
- `export-service` - ERP/CRM/docflow export, reconciliation acts, webhooks
- `storage-service` - metadata, rules, results, version history, audit events
- `notification-service` - critical and informational notifications
- `frontend` - interactive dashboard with drill-down and rules management

## Optional improvements implemented

- Fraud/falsification probability scoring
- Risk forecast for non-payment
- Automatic correction suggestions
- Webhook notification on verification completion
- Parallel batch processing for large arrays of documents
- Interactive drill-down dashboard
- Rule versioning and document version history

## Tech stack

- Backend: Python FastAPI (microservices)
- Storage: PostgreSQL, ClickHouse, MinIO
- Queue/Event: RabbitMQ, Redpanda (Kafka-compatible)
- Cache: Redis
- Analytics/ML logic: Pandas-compatible data flow + Scikit-learn style heuristics
- Frontend: React + Vite
- Integration: REST + Webhooks

## Quick start

```bash
cd d:\Шарага\Кинжа5\Task_5_DocValidatorPro
docker compose up --build -d
```

## Useful URLs

- Frontend: `http://localhost:5177`
- Gateway health: `http://localhost:8500/health`
- Services health: `http://localhost:8500/services/health`
- Gateway Swagger: `http://localhost:8500/docs`

## Validation and tests

```bash
python -m ruff check .
python -m pytest -q
docker compose config
```

## Sample data and demo

Generate 120 annotated sample documents:

```bash
python scripts/generate_sample_data.py
```

Run demo workflow:

```bash
python scripts/demo_pipeline.py
```
