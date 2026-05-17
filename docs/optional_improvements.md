# Optional Improvements Implemented

## Group A: Intelligent capabilities

1. Fraud/falsification probability scoring using metadata anomalies and suspicious diffs.
2. Risk forecast for non-payment based on historical features and document context.
3. Automatic correction suggestions (phone normalization, currency normalization, arithmetic hints).

## Group B: Integrations

4. Webhook notifications on verification completion (`export-service` webhook dispatcher).

## Group C: Performance

5. Parallel processing for large arrays of documents:
   - `POST /ingestion/batch`
   - `POST /workflow/batch-validate`

## Group D: UX

6. Interactive dashboard with drill-down into risky documents and rule management UI.
7. Document version history and rule versioning.
