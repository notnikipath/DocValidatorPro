from __future__ import annotations

from collections import defaultdict
from math import exp


def validation_accuracy(total_checks: int, failed_checks: int) -> float:
    if total_checks <= 0:
        return 1.0
    passed = max(total_checks - failed_checks, 0)
    return round(passed / total_checks, 4)


def error_recall(true_positives: int, false_negatives: int) -> float:
    denominator = true_positives + false_negatives
    if denominator <= 0:
        return 1.0
    return round(true_positives / denominator, 4)


def docs_per_hour(total_docs: int, elapsed_seconds: float) -> float:
    if elapsed_seconds <= 0:
        return 0.0
    return round(total_docs / elapsed_seconds * 3600, 2)


def non_payment_risk_score(amount: float, delay_days: int, historical_failures: int, counterparty_risk: float) -> float:
    amount_factor = min(max(amount / 1_000_000, 0.0), 1.0)
    delay_factor = min(max(delay_days / 90, 0.0), 1.0)
    failure_factor = min(max(historical_failures / 5, 0.0), 1.0)
    external = min(max(counterparty_risk, 0.0), 1.0)
    weighted = amount_factor * 0.22 + delay_factor * 0.31 + failure_factor * 0.27 + external * 0.2
    return round(min(max(weighted, 0.0), 1.0), 4)


def fraud_probability(anomaly_score: float, suspicious_change_score: float, metadata_flags: int) -> float:
    flags_score = min(metadata_flags / 5, 1.0)
    linear = anomaly_score * 1.4 + suspicious_change_score * 1.8 + flags_score * 1.2 - 1.5
    probability = 1 / (1 + exp(-linear))
    return round(min(max(probability, 0.0), 1.0), 4)


def aggregate_amounts(records: list[dict]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for row in records:
        period = str(row.get("period") or "unknown")
        amount = float(row.get("amount") or 0.0)
        totals[period] += amount
    return {period: round(value, 2) for period, value in totals.items()}


def parallel_batch_plan(document_count: int, max_workers: int = 16) -> dict[str, int]:
    workers = max(1, min(max_workers, max(1, document_count // 100)))
    batch_size = max(10, document_count // workers if document_count else 10)
    return {
        "workers": workers,
        "batch_size": batch_size,
        "document_count": document_count,
    }
