from __future__ import annotations

import json

from eval.client import _parse_sse_events


def test_parse_sse_done_event():
    raw = (
        'event: status\n'
        'data: {"stage": "generate"}\n\n'
        'event: done\n'
        'data: {"content": "hello", "route": "rag", "citations": [], "rewritten_query": "q"}\n\n'
    )
    events = _parse_sse_events(raw)
    assert events[-1][0] == "done"
    assert events[-1][1]["content"] == "hello"


def test_parse_sse_error_event():
    raw = 'event: error\ndata: {"message": "bad request"}\n\n'
    events = _parse_sse_events(raw)
    assert events[0] == ("error", {"message": "bad request"})
