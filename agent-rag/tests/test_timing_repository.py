from __future__ import annotations

from db.timing_repository import (
    DISTRIBUTION_BUCKETS,
    _build_distribution,
    _bucket_label,
    _metric_summary,
    _percentile,
)


def test_bucket_label_ranges():
    assert _bucket_label(100) == "0-500ms"
    assert _bucket_label(750) == "500ms-1s"
    assert _bucket_label(1500) == "1-2s"
    assert _bucket_label(3000) == "2-5s"
    assert _bucket_label(7000) == "5-10s"
    assert _bucket_label(15000) == "10s+"


def test_build_distribution_counts():
    values = [100, 600, 1500, 3000, 8000, 12000]
    dist = _build_distribution(values)
    assert len(dist) == len(DISTRIBUTION_BUCKETS)
    assert sum(item["count"] for item in dist) == len(values)


def test_metric_summary_empty():
    summary = _metric_summary([])
    assert summary["count"] == 0
    assert summary["avg_ms"] is None
    assert summary["p50_ms"] is None


def test_metric_summary_with_values():
    values = [100, 200, 300, 400, 500]
    summary = _metric_summary(values)
    assert summary["count"] == 5
    assert summary["avg_ms"] == 300
    assert summary["p50_ms"] == 300
    assert summary["p90_ms"] == _percentile(values, 90)


def test_percentile_single_value():
    assert _percentile([42], 90) == 42
