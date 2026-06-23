from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


@patch("api.admin.get_db")
def test_timing_stats_endpoint(mock_get_db, client: TestClient):
    mock_session = MagicMock()
    mock_get_db.return_value.__enter__.return_value = mock_session
    mock_get_db.return_value.__exit__.return_value = None

    aggregate = {
        "tenant_id": "default_tenant",
        "period_days": 7,
        "total_runs": 2,
        "overall": {
            "avg_ms": 1200,
            "p50_ms": 1100,
            "p90_ms": 1500,
            "count": 2,
            "distribution": [{"bucket": "0-500ms", "count": 0}, {"bucket": "500ms-1s", "count": 0}],
        },
        "embedding": {"avg_ms": 100, "p50_ms": 100, "p90_ms": 100, "count": 2, "distribution": []},
        "chroma": {"avg_ms": 40, "p50_ms": 40, "p90_ms": 40, "count": 2, "distribution": []},
        "rerank": {"avg_ms": 80, "p50_ms": 80, "p90_ms": 80, "count": 2, "distribution": []},
        "llm": {
            "avg_ms": 900,
            "p50_ms": 900,
            "p90_ms": 900,
            "count": 4,
            "distribution": [],
            "by_operation": {
                "router": {"count": 2, "avg_ms": 200},
                "generate": {"count": 2, "avg_ms": 700},
            },
        },
    }

    with patch("api.admin.TimingRepository") as mock_repo_cls:
        mock_repo_cls.return_value.aggregate_timing_stats.return_value = aggregate
        response = client.get("/admin/timing-stats?days=7")

    assert response.status_code == 200
    data = response.json()
    assert data["tenant_id"] == "default_tenant"
    assert data["total_runs"] == 2
    assert data["overall"]["avg_ms"] == 1200
    assert data["llm"]["by_operation"]["router"]["count"] == 2


def test_timing_stats_invalid_days(client: TestClient):
    response = client.get("/admin/timing-stats?days=0")
    assert response.status_code == 400
