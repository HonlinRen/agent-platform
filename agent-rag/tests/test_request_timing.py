from __future__ import annotations

import pytest

from rag.request_timing import (
    RequestTiming,
    begin_request_timing,
    end_request_timing,
    get_request_timing,
)


@pytest.fixture
def timing():
    ctx = begin_request_timing("tenant_a", "thread_1")
    yield ctx
    end_request_timing("tenant_a", "thread_1")


def test_record_embedding_accumulates(timing: RequestTiming):
    timing.record_embedding(120)
    timing.record_embedding(80)
    assert timing.embedding_ms == 200
    assert timing.embedding_count == 2


def test_record_chroma_and_rerank(timing: RequestTiming):
    timing.record_chroma(50)
    timing.record_rerank(30)
    snapshot = timing.snapshot()
    assert snapshot["chroma_ms"] == 50
    assert snapshot["rerank_ms"] == 30


def test_record_llm_main_vs_post_turn(timing: RequestTiming):
    timing.record_llm("router", 100, tokens_used=10, phase="main")
    timing.record_llm("summary_update", 200, tokens_used=20, phase="post_turn")
    assert timing.main_llm_total_ms() == 100
    assert timing.main_llm_call_count() == 1
    snapshot = timing.snapshot()
    assert snapshot["llm_total_ms"] == 100
    assert len(snapshot["llm_calls"]) == 2


def test_timing_context_lifecycle():
    begin_request_timing("tenant_b", "thread_2")
    assert get_request_timing() is not None
    end_request_timing("tenant_b", "thread_2")
    assert get_request_timing() is None
