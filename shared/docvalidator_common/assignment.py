from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from statistics import mean, pstdev
from typing import Any

DATE_PATTERNS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y")
PHONE_PATTERN = re.compile(r"^\+?[1-9]\d{9,14}$")


def parse_date(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    text = str(value).strip()
    if not text:
        return None
    for pattern in DATE_PATTERNS:
        try:
            return datetime.strptime(text, pattern).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def normalize_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value).replace(" ", "").replace(",", ".").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def validate_phone(value: Any) -> bool:
    if value is None:
        return False
    compact = str(value).replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    return bool(PHONE_PATTERN.match(compact))


def validate_inn(value: Any) -> bool:
    if value is None:
        return False
    digits = re.sub(r"\D", "", str(value))
    if len(digits) == 10:
        weights = (2, 4, 10, 3, 5, 9, 4, 6, 8)
        checksum = sum(int(digits[idx]) * weights[idx] for idx in range(9))
        check_digit = (checksum % 11) % 10
        return check_digit == int(digits[9])
    if len(digits) == 12:
        weights_1 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
        checksum_1 = sum(int(digits[idx]) * weights_1[idx] for idx in range(10))
        check_digit_1 = (checksum_1 % 11) % 10
        if check_digit_1 != int(digits[10]):
            return False
        weights_2 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
        checksum_2 = sum(int(digits[idx]) * weights_2[idx] for idx in range(11))
        check_digit_2 = (checksum_2 % 11) % 10
        return check_digit_2 == int(digits[11])
    return False


def hash_document(fields: dict[str, Any], metadata: dict[str, Any] | None = None) -> str:
    payload = {
        "fields": fields,
        "metadata": metadata or {},
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_currency(value: Any) -> str:
    if value is None:
        return "RUB"
    currency = str(value).strip().upper()
    aliases = {"РУБ": "RUB", "RUR": "RUB", "DOLLAR": "USD", "EURO": "EUR"}
    return aliases.get(currency, currency or "RUB")


def report_period_by_date(date_value: Any) -> str:
    parsed = parse_date(date_value)
    if parsed is None:
        return "unknown"
    return f"{parsed.year}-{parsed.month:02d}"


def outlier_score(values: list[float], candidate: float) -> float:
    if not values:
        return 0.0
    avg = mean(values)
    deviation = pstdev(values)
    if deviation == 0:
        return 0.0 if abs(candidate - avg) < 1e-9 else 1.0
    z_value = abs(candidate - avg) / deviation
    return min(round(z_value / 4.0, 4), 1.0)


def flatten_dict(data: dict[str, Any], parent_key: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in data.items():
        item_key = f"{parent_key}.{key}" if parent_key else key
        if isinstance(value, dict):
            flat.update(flatten_dict(value, item_key))
        else:
            flat[item_key] = value
    return flat
