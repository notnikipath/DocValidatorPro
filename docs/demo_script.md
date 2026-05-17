# Demo Script

## Step 1: Start platform

```bash
docker compose up --build -d
```

## Step 2: Generate sample data

```bash
python scripts/generate_sample_data.py
```

## Step 3: Run demo pipeline

```bash
python scripts/demo_pipeline.py
```

Expected: each sample shows `document_id`, type, status, issues count.

## Step 4: Open frontend dashboard

- URL: `http://localhost:5177`
- Verify:
  - KPI cards (accuracy/recall/throughput/tasks)
  - Risk drill-down
  - Open quality tasks
  - Rule creation and CSV import

## Step 5: API walk-through

- `GET http://localhost:8500/services/health`
- `GET http://localhost:8500/dashboard/overview?actor_role=analyst`
- `POST http://localhost:8500/workflow/validate-document`

## Step 6: Show versioning

- Call manual correction endpoint:
  - `POST /workflow/{document_id}/manual-correction`
- Verify version history in storage:
  - `GET /documents/{new_document_id}/versions`
