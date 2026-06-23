from __future__ import annotations

from rag.telemetry import (
    _histogram_avg_for_tenant,
    collect_summary,
    RAG_CHROMA_QUERY_DURATION,
)


def test_histogram_avg_for_fast_chroma_queries():
    """Chroma queries are often <5ms; avg must not read +Inf bucket count (often 0)."""
    RAG_CHROMA_QUERY_DURATION.labels(tenant="default_tenant", collection="semiconductor").observe(0.005)
    avg = _histogram_avg_for_tenant(RAG_CHROMA_QUERY_DURATION, "default_tenant")
    assert avg == 0.005
    summary = collect_summary("default_tenant")
    assert summary["chroma_query_avg_seconds"] == 0.005
