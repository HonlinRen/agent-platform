from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator, Iterator
from typing import Any

from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.messages import HumanMessage

from rag.assistant import CarSafetyWhitepaperAssistant, chunk_to_text, rebuild_history
from rag.cancellation import is_cancelled
from rag.graph.builder import build_graph
from rag.graph.state import AgentState
from rag.telemetry import current_trace_id, observe_node_duration, span

STAGE_BY_NODE: dict[str, str] = {
    "router": "router",
    "rewrite": "rewrite",
    "retrieve": "retrieve",
    "grade_documents": "retrieve",
    "web_search": "web",
    "agent": "agent",
    "tools": "tools",
    "generate": "generate",
    "direct_reply": "direct",
    "reject": "generate",
}

TOKEN_STREAM_NODES = frozenset({"generate", "direct_reply"})

LANGSMITH_PROJECT = os.environ.get("LANGCHAIN_PROJECT", "agent-rag")


def _initial_state(
    message: str,
    history: ChatMessageHistory,
    thread_id: str,
    tenant_id: str,
) -> AgentState:
    messages = []
    for item in history.messages:
        if item.type == "human":
            messages.append(HumanMessage(content=item.content))
    return AgentState(
        messages=messages,
        user_query=message,
        rewritten_query="",
        documents=[],
        context="",
        web_context="",
        route="rag",
        tool_calls_log=[],
        citations=[],
        answer="",
        reject_message="",
        context_source="local",
        tenant_id=tenant_id,
        thread_id=thread_id,
        tool_rounds=0,
        retrieve_retries=0,
        run_id="",
    )


def _configure_langsmith() -> None:
    if os.environ.get("LANGCHAIN_TRACING_V2", "").lower() in {"1", "true", "yes"}:
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")


def _normalize_stream_part(raw: Any) -> tuple[str, Any] | None:
    if isinstance(raw, dict) and "type" in raw and "data" in raw:
        return raw["type"], raw["data"]
    if isinstance(raw, tuple) and len(raw) == 2 and isinstance(raw[0], str):
        return raw[0], raw[1]
    if isinstance(raw, dict):
        return "updates", raw
    return None


def _graph_stream(graph: Any, inputs: AgentState, config: dict[str, Any]) -> Iterator[Any]:
    try:
        yield from graph.stream(
            inputs,
            config=config,
            stream_mode=["updates", "messages"],
            version="v2",
        )
    except TypeError:
        yield from graph.stream(
            inputs,
            config=config,
            stream_mode=["updates", "messages"],
        )


def _cancelled_event(
    *,
    content: str,
    message: str,
    final_state: dict[str, Any],
    thread_id: str,
    tool_calls_accum: list[dict[str, Any]],
    run_id: str,
) -> dict[str, Any]:
    return {
        "type": "cancelled",
        "content": content,
        "rewritten_query": final_state.get("rewritten_query", message),
        "thread_id": thread_id,
        "route": final_state.get("route", "rag"),
        "tool_calls": tool_calls_accum,
        "run_id": run_id,
        "citations": final_state.get("citations", []),
        "context_source": final_state.get("context_source", "local"),
    }


def _done_event(
    *,
    answer: str,
    message: str,
    final_state: dict[str, Any],
    thread_id: str,
    tool_calls_accum: list[dict[str, Any]],
    run_id: str,
) -> dict[str, Any]:
    return {
        "type": "done",
        "content": answer,
        "rewritten_query": final_state.get("rewritten_query", message),
        "thread_id": thread_id,
        "route": final_state.get("route", "rag"),
        "tool_calls": tool_calls_accum,
        "run_id": run_id,
        "citations": final_state.get("citations", []),
        "context_source": final_state.get("context_source", "local"),
    }


def _process_node_update(
    node_name: str,
    update: dict[str, Any],
    *,
    assistant: CarSafetyWhitepaperAssistant,
    final_state: dict[str, Any],
    tool_calls_accum: list[dict[str, Any]],
    any_token_emitted: bool,
) -> Iterator[dict[str, Any]]:
    stage = STAGE_BY_NODE.get(node_name, node_name)
    route = update.get("route") or final_state.get("route", "rag")

    with span(
        f"rag.graph.{node_name}",
        {
            "rag.node": node_name,
            "rag.route": route,
            "rag.collection": assistant.collection_name,
        },
    ):
        yield {"type": "status", "stage": stage, "node": node_name}

        if node_name == "rewrite" and update.get("rewritten_query"):
            final_state["rewritten_query"] = update["rewritten_query"]
        if node_name == "router" and update.get("route"):
            final_state["route"] = update["route"]
        if node_name == "retrieve":
            if update.get("citations"):
                final_state["citations"] = update["citations"]
            if update.get("context"):
                final_state["context"] = update["context"]
            if update.get("reject_message"):
                final_state["reject_message"] = update["reject_message"]
        if node_name == "web_search":
            if update.get("context"):
                final_state["context"] = update["context"]
            if update.get("web_context"):
                final_state["web_context"] = update["web_context"]
            if update.get("citations"):
                final_state["citations"] = update["citations"]
            if update.get("context_source"):
                final_state["context_source"] = update["context_source"]
            if "reject_message" in update:
                final_state["reject_message"] = update["reject_message"]
        if node_name == "tools":
            for log in update.get("tool_calls_log") or []:
                tool_calls_accum.append(log)
                yield {
                    "type": "tool_call",
                    "name": log.get("name"),
                    "args": log.get("args") or {},
                    "status": log.get("status", "end"),
                    "result": log.get("result"),
                }
        if node_name in {"direct_reply", "reject", "generate"}:
            answer = update.get("answer")
            if answer:
                final_state["answer"] = answer
                if node_name == "direct_reply":
                    final_state["route"] = "direct"
                elif node_name == "reject":
                    if not any_token_emitted:
                        yield {"type": "token", "content": answer}
                else:
                    final_state["route"] = final_state.get("route", "rag")


def stream_graph_response(
    assistant: CarSafetyWhitepaperAssistant,
    message: str,
    history: ChatMessageHistory,
    thread_id: str,
    tenant_id: str = "default_tenant",
) -> Iterator[dict[str, Any]]:
    _configure_langsmith()
    graph = build_graph(assistant, tenant_id=tenant_id)
    config = {"configurable": {"thread_id": thread_id}}
    inputs = _initial_state(message, history, thread_id, tenant_id)

    run_id = current_trace_id()
    yield {"type": "status", "stage": "router", "node": "router"}

    final_state: dict[str, Any] = {}
    tool_calls_accum: list[dict[str, Any]] = []
    emitted_text = ""
    any_token_emitted = False

    with span("rag.graph.run", {"rag.collection": assistant.collection_name}):
        for raw in _graph_stream(graph, inputs, config):
            if is_cancelled(tenant_id, thread_id):
                break

            part = _normalize_stream_part(raw)
            if part is None:
                continue

            mode, data = part

            if mode == "messages":
                msg, metadata = data
                node_name = metadata.get("langgraph_node")
                if node_name not in TOKEN_STREAM_NODES:
                    continue
                text = chunk_to_text(msg)
                if not text:
                    continue
                any_token_emitted = True
                emitted_text += text
                yield {"type": "token", "content": text}
                continue

            if mode != "updates":
                continue

            for node_name, update in data.items():
                node_start = time.perf_counter()
                for event in _process_node_update(
                    node_name,
                    update,
                    assistant=assistant,
                    final_state=final_state,
                    tool_calls_accum=tool_calls_accum,
                    any_token_emitted=any_token_emitted,
                ):
                    if event.get("type") == "token":
                        any_token_emitted = True
                        emitted_text += event.get("content", "")
                    yield event
                observe_node_duration(node_name, tenant_id, time.perf_counter() - node_start)

    if is_cancelled(tenant_id, thread_id):
        partial = emitted_text or final_state.get("answer", "") or final_state.get("reject_message", "")
        yield _cancelled_event(
            content=partial,
            message=message,
            final_state=final_state,
            thread_id=thread_id,
            tool_calls_accum=tool_calls_accum,
            run_id=run_id,
        )
        return

    answer = final_state.get("answer", "")
    if not answer and final_state.get("reject_message"):
        answer = final_state["reject_message"]

    yield _done_event(
        answer=answer,
        message=message,
        final_state=final_state,
        thread_id=thread_id,
        tool_calls_accum=tool_calls_accum,
        run_id=run_id,
    )


async def astream_graph_response(
    assistant: CarSafetyWhitepaperAssistant,
    message: str,
    history: ChatMessageHistory,
    thread_id: str,
    tenant_id: str = "default_tenant",
) -> AsyncIterator[dict[str, Any]]:
    for item in stream_graph_response(assistant, message, history, thread_id, tenant_id):
        yield item
