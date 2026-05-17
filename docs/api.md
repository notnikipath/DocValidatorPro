# API Overview

Swagger is available for each service at `/docs`. Main entrypoint is Gateway:

- `http://localhost:8500/docs`

## Core workflow endpoints

### Ingestion

- `POST /ingestion/import` (data-ingestion-service)
- `POST /ingestion/batch` (parallel ingestion)
- `POST /ingestion/parse-xml` (XML parser preview)

### Verification pipeline

- `POST /workflow/validate-document` (gateway)
- `POST /workflow/batch-validate` (gateway)
- `POST /workflow/{document_id}/manual-correction` (gateway)

### Rules management

- `GET /rules` (gateway proxy)
- `POST /rules` (gateway proxy)
- `PUT /rules/{rule_id}` (gateway proxy)
- `POST /rules/import/csv` (gateway proxy)

### Dashboards and monitoring

- `GET /dashboard/overview` (gateway)
- `GET /services/health` (gateway)
- `GET /analytics/report` (analytics-service)
- `GET /quality/metrics` (quality-service)

### Export and notifications

- `POST /export` (export-service)
- `POST /export/reconciliation-act` (export-service)
- `POST /export/webhook/notify` (export-service)
- `POST /notify` and `POST /notify/critical` (notification-service)
