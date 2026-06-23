from __future__ import annotations

from rag.graph.streaming import _done_event


def test_done_event_uses_explicit_elapsed_ms():
    event = _done_event(
        answer="ok",
        message="question",
        final_state={"route": "rag"},
        thread_id="t1",
        tool_calls_accum=[],
        run_id="run-1",
        timing_snapshot={"chroma_ms": 42, "chroma_count": 1, "rerank_ms": 10, "rerank_count": 1},
        elapsed_ms=1500,
    )
    assert event["elapsed_ms"] == 1500
    assert event["timing_snapshot"]["chroma_ms"] == 42
