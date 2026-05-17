# Presentation Outline

## 1. Problem and objective

- OCR extraction quality varies and creates operational risk.
- Need automatic and auditable verification pipeline with analytics.

## 2. Architecture

- 9 backend microservices + frontend dashboard.
- Storage stack: PostgreSQL, ClickHouse, MinIO.
- Async-ready integration stack: RabbitMQ, Redpanda, Redis.

## 3. End-to-end demo

- Import JSON/XML/manual document.
- Run `POST /workflow/validate-document`.
- Show validation issues, diff, analytics, quality task, export, notification.

## 4. Rule management

- Create rule in UI.
- Import bulk rules from CSV.
- Show rule versioning behavior.

## 5. KPI and quality dashboard

- Accuracy, recall, throughput.
- Open critical tasks.
- Risk forecast drill-down.

## 6. Optional enhancements

- Fraud probability scoring
- Risk prediction
- Auto-correction suggestions
- Webhook completion events
- Parallel batch processing
- Interactive drill-down dashboard

## 7. Roadmap

- Add external registries (EGRUL/EGRIP adapter)
- Replace heuristic models with fully trained ML pipelines
- Move from in-memory service state to persistent DB tables/events
