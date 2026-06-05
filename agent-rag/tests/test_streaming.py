from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from langchain_community.chat_message_histories import ChatMessageHistory

from rag.cancellation import begin_run, end_run
from rag.graph import streaming as streaming_mod
from rag.graph.streaming import (
    TOKEN_STREAM_NODES,
    _normalize_stream_part,
    stream_graph_response,
)


def test_normalize_stream_part_v2():
    assert _normalize_stream_part({"type": "updates", "data": {"router": {"route": "rag"}}}) == (
        "updates",
        {"router": {"route": "rag"}},
    )


def test_normalize_stream_part_v1_tuple():
    assert _normalize_stream_part(("messages", ("chunk", {"langgraph_node": "generate"}))) == (
        "messages",
        ("chunk", {"langgraph_node": "generate"}),
    )


def test_normalize_stream_part_v1_updates_dict():
    assert _normalize_stream_part({"router": {"route": "direct"}}) == (
        "updates",
        {"router": {"route": "direct"}},
    )


def _mock_assistant() -> MagicMock:
    assistant = MagicMock()
    assistant.collection_name = "test_collection"
    return assistant


def _collect_events(events: Iterator[dict]) -> list[dict]:
    return list(events)


def _fake_graph_stream(events: list) -> Iterator:
    yield from events


@patch.object(streaming_mod, "build_graph")
@patch.object(streaming_mod, "_graph_stream")
def test_generate_message_tokens_are_emitted(mock_graph_stream, mock_build_graph):
    mock_build_graph.return_value = MagicMock()
    mock_graph_stream.return_value = _fake_graph_stream(
        [
            {"type": "messages", "data": (SimpleNamespace(content="Hel"), {"langgraph_node": "rewrite"})},
            {"type": "messages", "data": (SimpleNamespace(content="lo"), {"langgraph_node": "generate"})},
            {"type": "updates", "data": {"generate": {"answer": "Hello"}}},
        ]
    )

    events = _collect_events(
        stream_graph_response(
            _mock_assistant(),
            "hi",
            ChatMessageHistory(),
            "thread-1",
            "tenant-1",
        )
    )

    token_events = [event for event in events if event["type"] == "token"]
    assert token_events == [{"type": "token", "content": "lo"}]
    assert events[-1]["type"] == "done"
    assert events[-1]["content"] == "Hello"


@patch.object(streaming_mod, "build_graph")
@patch.object(streaming_mod, "_graph_stream")
def test_direct_reply_message_tokens_are_emitted(mock_graph_stream, mock_build_graph):
    mock_build_graph.return_value = MagicMock()
    mock_graph_stream.return_value = _fake_graph_stream(
        [
            {"type": "messages", "data": (SimpleNamespace(content="Hi"), {"langgraph_node": "direct_reply"})},
            {"type": "updates", "data": {"direct_reply": {"answer": "Hi", "route": "direct"}}},
        ]
    )

    events = _collect_events(
        stream_graph_response(
            _mock_assistant(),
            "hello",
            ChatMessageHistory(),
            "thread-2",
            "tenant-1",
        )
    )

    assert [event for event in events if event["type"] == "token"] == [{"type": "token", "content": "Hi"}]
    assert events[-1]["route"] == "direct"


@patch.object(streaming_mod, "build_graph")
@patch.object(streaming_mod, "_graph_stream")
def test_reject_emits_static_answer_once(mock_graph_stream, mock_build_graph):
    mock_build_graph.return_value = MagicMock()
    reject_msg = "知识库上下文中未找到充分依据。"
    mock_graph_stream.return_value = _fake_graph_stream(
        [
            {"type": "updates", "data": {"reject": {"answer": reject_msg}}},
        ]
    )

    events = _collect_events(
        stream_graph_response(
            _mock_assistant(),
            "unknown",
            ChatMessageHistory(),
            "thread-3",
            "tenant-1",
        )
    )

    token_events = [event for event in events if event["type"] == "token"]
    assert token_events == [{"type": "token", "content": reject_msg}]
    assert events[-1]["content"] == reject_msg


@patch.object(streaming_mod, "build_graph")
@patch.object(streaming_mod, "_graph_stream")
def test_web_search_done_includes_context_source(mock_graph_stream, mock_build_graph):
    mock_build_graph.return_value = MagicMock()
    mock_graph_stream.return_value = _fake_graph_stream(
        [
            {
                "type": "updates",
                "data": {
                    "web_search": {
                        "context": "web ctx",
                        "citations": [{"source": "Example", "url": "https://example.com", "page": "web", "type": "web"}],
                        "context_source": "web",
                        "reject_message": "",
                    }
                },
            },
            {"type": "updates", "data": {"generate": {"answer": "Web answer"}}},
        ]
    )

    events = _collect_events(
        stream_graph_response(
            _mock_assistant(),
            "unknown topic",
            ChatMessageHistory(),
            "thread-web",
            "tenant-1",
        )
    )

    status_nodes = [event.get("node") for event in events if event.get("type") == "status"]
    assert "web_search" in status_nodes
    web_status = next(event for event in events if event.get("node") == "web_search")
    assert web_status["stage"] == "web"
    assert events[-1]["type"] == "done"
    assert events[-1]["context_source"] == "web"
    assert events[-1]["citations"][0]["type"] == "web"


@patch.object(streaming_mod, "build_graph")
@patch.object(streaming_mod, "_graph_stream")
@patch.object(streaming_mod, "is_cancelled")
def test_cancelled_uses_emitted_tokens(mock_is_cancelled, mock_graph_stream, mock_build_graph):
    mock_build_graph.return_value = MagicMock()
    mock_graph_stream.return_value = _fake_graph_stream(
        [
            {"type": "messages", "data": (SimpleNamespace(content="partial"), {"langgraph_node": "generate"})},
        ]
    )

    call_count = 0

    def cancelled_after_first_token(*_args, **_kwargs) -> bool:
        nonlocal call_count
        call_count += 1
        return call_count > 1

    mock_is_cancelled.side_effect = cancelled_after_first_token

    begin_run("tenant-1", "thread-4")
    try:
        events = _collect_events(
            stream_graph_response(
                _mock_assistant(),
                "question",
                ChatMessageHistory(),
                "thread-4",
                "tenant-1",
            )
        )
    finally:
        end_run("tenant-1", "thread-4")

    assert events[-1]["type"] == "cancelled"
    assert events[-1]["content"] == "partial"


def test_token_stream_nodes_whitelist():
    assert "generate" in TOKEN_STREAM_NODES
    assert "direct_reply" in TOKEN_STREAM_NODES
    assert "rewrite" not in TOKEN_STREAM_NODES
