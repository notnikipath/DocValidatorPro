# Algorithms

## 1) Format validation

- Date parsing against multiple templates (`YYYY-MM-DD`, `DD.MM.YYYY`, `DD/MM/YYYY`)
- Numeric normalization (`12 345,67` -> `12345.67`)
- INN checksum validation for 10 and 12 digit formats
- Phone validation with international normalization

## 2) Logical validation

- `subtotal + tax_amount == total_amount` tolerance check
- `quantity * unit_price == total_amount` check
- Date ordering checks: `issue_date <= due_date`, `start_date <= end_date`

## 3) Semantic validation

- Contract subject completeness checks for legal docs
- HR profile completeness checks
- Medical diagnosis/conclusion coherence checks
- Suspicious keyword detection (`fake`, `forged`, etc.)

## 4) Anomaly and fraud signals

- Outlier detection based on historical amount distribution
- Metadata tampering flags (`edited_after_signing`, source mismatch)
- Suspicious change scoring from diff severity
- Fraud probability estimation via weighted logistic-style score

## 5) Business risk forecast

- Non-payment risk score combines:
  - amount scale
  - payment delay profile
  - historical failure rate
  - counterparty risk

## 6) Quality metrics

- Validation accuracy estimate
- Error recall estimate
- Processing throughput (docs/hour)
