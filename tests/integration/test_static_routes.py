from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.integration.helpers import load_module

ROOT = Path(__file__).resolve().parents[2]
module = load_module("static_route_regression", ROOT / "analytics-service/app/main.py")
client = TestClient(module.app)


@pytest.mark.parametrize(
    ("url", "expected_key"),
    [
        ("/analytics/report", "documents"),
        ("/analytics/risk-forecast", "items"),
        ("/analytics/dashboard", "total_documents"),
    ],
)
def test_static_endpoints_are_reachable(url: str, expected_key: str) -> None:
    response = client.get(url)
    assert response.status_code == 200, response.text
    assert expected_key in response.json()


def test_missing_record_still_returns_not_found() -> None:
    assert client.get("/analytics/missing-record").status_code == 404
