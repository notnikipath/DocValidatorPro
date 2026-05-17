from shared.docvalidator_common import (
    hash_document,
    normalize_currency,
    normalize_number,
    outlier_score,
    parse_date,
    validate_inn,
    validate_phone,
)


def test_validate_inn() -> None:
    assert validate_inn("7707083893")
    assert not validate_inn("7707083890")


def test_validate_phone() -> None:
    assert validate_phone("+79991234567")
    assert not validate_phone("12345")


def test_date_and_number_parsing() -> None:
    assert parse_date("2026-05-01") is not None
    assert normalize_number("12 345,67") == 12345.67
    assert normalize_currency("руб") == "RUB"


def test_hash_stability_and_outlier() -> None:
    fields = {"a": 1, "b": "text"}
    metadata = {"k": "v"}
    assert hash_document(fields, metadata) == hash_document(fields, metadata)
    assert outlier_score([10, 12, 11, 10, 13], 200) > 0.8
