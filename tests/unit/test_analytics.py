from shared.docvalidator_common import (
    docs_per_hour,
    fraud_probability,
    non_payment_risk_score,
    parallel_batch_plan,
    validation_accuracy,
)


def test_validation_accuracy_bounds() -> None:
    assert validation_accuracy(100, 0) == 1.0
    assert 0 <= validation_accuracy(100, 15) <= 1


def test_non_payment_risk_increases_with_delay() -> None:
    low = non_payment_risk_score(amount=10000, delay_days=0, historical_failures=0, counterparty_risk=0.1)
    high = non_payment_risk_score(amount=10000, delay_days=45, historical_failures=0, counterparty_risk=0.1)
    assert high > low


def test_fraud_probability_bounds() -> None:
    score = fraud_probability(anomaly_score=0.7, suspicious_change_score=0.8, metadata_flags=3)
    assert 0 <= score <= 1


def test_throughput_and_parallel_plan() -> None:
    assert docs_per_hour(total_docs=20, elapsed_seconds=60) == 1200
    plan = parallel_batch_plan(document_count=1000, max_workers=16)
    assert plan["workers"] >= 1
    assert plan["batch_size"] >= 10
