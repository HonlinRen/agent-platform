"""LangGraph 执行与 SSE 事件桥接层。

``api/chat.py`` 调用 ``stream_graph_response``，本模块负责：
1. 构造初始 ``AgentState``（每轮重置 documents/context 等，避免脏状态）
2. ``graph.stream(stream_mode=["updates", "messages"])`` 消费 LangGraph 双流
3. 映射为前端 SSE 事件：``status`` / ``token`` / ``tool_call`` / ``done`` / ``cancelled``

LangGraph stream_mode 含义：
- ``updates``：节点完成后的 state 增量 → 推 status、tool_call
- ``messages``：LLM token 流 → 推 token（仅 generate/direct_reply 节点）
"""

from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator, Iterator
from typing import Any

from rag.assistant import CarSafetyWhitepaperAssistant, chunk_to_text
from rag.cancellation import is_cancelled
from rag.graph.builder import build_graph
from rag.graph.state import AgentState
from rag.memory.types import MemoryContext
from rag.request_budget import (
    begin_request_budget,
    end_request_budget,
    get_budget_stop_reason,
    get_request_budget,
    get_total_tokens_used,
    should_force_generate,
)
from rag.request_timing import (
    end_request_timing,
    get_request_timing,
    stash_pending_timing,
)
from rag.telemetry import current_trace_id, observe_node_duration, span

# LangGraph 节点名 → 前端展示的 stage（grade_documents 归入 retrieve 阶段展示）
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

# 只有这两个节点的 LLM 输出会通过 stream_mode="messages" 逐 token 推送
TOKEN_STREAM_NODES = frozenset({"generate", "direct_reply"})

LANGSMITH_PROJECT = os.environ.get("LANGCHAIN_PROJECT", "agent-rag")


def _initial_state(
    message: str,
    memory: MemoryContext,
    thread_id: str,
    tenant_id: str,
) -> AgentState:
    """构造本轮图输入。跨轮上下文来自 MemoryContext；messages 仅用于当轮 agent↔tools。"""
    return AgentState(
        messages=[],
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
        budget_stop_reason=None,
        total_tokens_used=0,
        conversation_summary=memory.conversation_summary,
        recent_messages_text=memory.recent_messages_text,
        tenant_profile_summary=memory.tenant_profile_summary,
    )


def _configure_langsmith() -> None:
    if os.environ.get("LANGCHAIN_TRACING_V2", "").lower() in {"1", "true", "yes"}:
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")


def _normalize_stream_part(raw: Any) -> tuple[str, Any] | None:
    """兼容 LangGraph v1/v2 不同的 stream chunk 形状，统一为 (mode, data)。"""
    if isinstance(raw, dict) and "type" in raw and "data" in raw:
        return raw["type"], raw["data"]
    if isinstance(raw, tuple) and len(raw) == 2 and isinstance(raw[0], str):
        return raw[0], raw[1]
    if isinstance(raw, dict):
        return "updates", raw
    return None


def _graph_stream(graph: Any, inputs: AgentState, config: dict[str, Any]) -> Iterator[Any]:
    """执行已编译图。config.configurable.thread_id 供 checkpoint 关联同一会话。"""
    try:
        yield from graph.stream(
            inputs,
            config=config,
            stream_mode=["updates", "messages"],
            version="v2",
        )
    except TypeError:
        # 旧版 langgraph 无 version 参数时的回退
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
    timing_snapshot: dict[str, Any] | None = None,
    elapsed_ms: int | None = None,
) -> dict[str, Any]:
    payload = {
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
    if timing_snapshot:
        payload["timing_snapshot"] = timing_snapshot
    if elapsed_ms is not None:
        payload["elapsed_ms"] = elapsed_ms
    return payload


def _budget_metadata(final_state: dict[str, Any]) -> dict[str, Any]:
    budget = get_request_budget()
    reason = final_state.get("budget_stop_reason") or get_budget_stop_reason()
    tokens = final_state.get("total_tokens_used") or get_total_tokens_used()
    elapsed_ms = budget.elapsed_ms() if budget is not None else None
    meta: dict[str, Any] = {}
    if reason:
        meta["budget_stop_reason"] = reason
    if tokens:
        meta["total_tokens_used"] = tokens
    if elapsed_ms is not None:
        meta["elapsed_ms"] = elapsed_ms
    return meta


def _done_event(
    *,
    answer: str,
    message: str,
    final_state: dict[str, Any],
    thread_id: str,
    tool_calls_accum: list[dict[str, Any]],
    run_id: str,
    timing_snapshot: dict[str, Any] | None = None,
    elapsed_ms: int | None = None,
) -> dict[str, Any]:
    payload = {
        "type": "done",
        "content": answer,
        "rewritten_query": final_state.get("rewritten_query", message),
        "thread_id": thread_id,
        "route": final_state.get("route", "rag"),
        "tool_calls": tool_calls_accum,
        "run_id": run_id,
        "citations": final_state.get("citations", []),
        "context_source": final_state.get("context_source", "local"),
        **_budget_metadata(final_state),
    }
    if elapsed_ms is not None:
        payload["elapsed_ms"] = elapsed_ms
    if timing_snapshot:
        payload["timing_snapshot"] = timing_snapshot
    return payload


def _process_node_update(
    node_name: str,
    update: dict[str, Any],
    *,
    assistant: CarSafetyWhitepaperAssistant,
    final_state: dict[str, Any],
    tool_calls_accum: list[dict[str, Any]],
    any_token_emitted: bool,
) -> Iterator[dict[str, Any]]:
    """把单个节点的 updates 增量转为 SSE 事件，并累积 final_state 供 done 事件使用。"""
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
                    # reject 不走 messages 流式，若尚未发过 token 则整段推送
                    if not any_token_emitted:
                        yield {"type": "token", "content": answer}
                else:
                    final_state["route"] = final_state.get("route", "rag")
        if update.get("budget_stop_reason"):
            final_state["budget_stop_reason"] = update["budget_stop_reason"]
        if update.get("total_tokens_used") is not None:
            final_state["total_tokens_used"] = update["total_tokens_used"]


def stream_graph_response(
    assistant: CarSafetyWhitepaperAssistant,
    message: str,
    memory: MemoryContext,
    thread_id: str,
    tenant_id: str = "default_tenant",
) -> Iterator[dict[str, Any]]:
    """同步执行 LangGraph 并 yield SSE 事件字典；由 api/chat.py 包装为 text/event-stream。"""
    _configure_langsmith()
    graph = build_graph(assistant, tenant_id=tenant_id)
    config = {"configurable": {"thread_id": thread_id}}
    inputs = _initial_state(message, memory, thread_id, tenant_id)

    run_id = current_trace_id()
    budget = begin_request_budget(tenant_id, thread_id)
    budget_limit_notified = False
    # 预发 router status：图真正执行 router 时还会再发一次（前端轨迹可能出现两次 router）
    yield {"type": "status", "stage": "router", "node": "router"}

    final_state: dict[str, Any] = {}
    tool_calls_accum: list[dict[str, Any]] = []
    emitted_text = ""
    any_token_emitted = False
    timing_snapshot: dict[str, Any] = {}
    elapsed_ms_at_end: int | None = None

    try:
        with span("rag.graph.run", {"rag.collection": assistant.collection_name}):
            for raw in _graph_stream(graph, inputs, config):
                if is_cancelled(tenant_id, thread_id):
                    break

                budget.check_runtime()
                if should_force_generate(thread_id) and not budget_limit_notified:
                    budget_limit_notified = True
                    yield {
                        "type": "status",
                        "stage": "budget_limit",
                        "node": "budget_limit",
                        "budget_stop_reason": get_budget_stop_reason(thread_id),
                    }

                part = _normalize_stream_part(raw)
                if part is None:
                    continue

                mode, data = part

                if mode == "messages":
                    # LangGraph 透传 LLM 流式 chunk；metadata.langgraph_node 标明来源节点
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

                # updates 形如 { "router": {"route": "rag"}, "retrieve": {"context": "..."}, ... }
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
    finally:
        elapsed_ms_at_end = budget.elapsed_ms()
        timing = budget.timing or get_request_timing(thread_id)
        if timing is not None:
            timing_snapshot = timing.snapshot()
        stash_pending_timing(
            tenant_id=tenant_id,
            thread_id=thread_id,
            trace_run_id=run_id,
            route=final_state.get("route", "rag"),
            timing_snapshot=timing_snapshot,
            elapsed_ms=elapsed_ms_at_end,
        )
        end_request_timing(tenant_id, thread_id)
        end_request_budget(tenant_id, thread_id)

    if is_cancelled(tenant_id, thread_id):
        partial = emitted_text or final_state.get("answer", "") or final_state.get("reject_message", "")
        yield _cancelled_event(
            content=partial,
            message=message,
            final_state=final_state,
            thread_id=thread_id,
            tool_calls_accum=tool_calls_accum,
            run_id=run_id,
            timing_snapshot=timing_snapshot or None,
            elapsed_ms=elapsed_ms_at_end,
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
        timing_snapshot=timing_snapshot or None,
        elapsed_ms=elapsed_ms_at_end,
    )


async def astream_graph_response(
    assistant: CarSafetyWhitepaperAssistant,
    message: str,
    memory: MemoryContext,
    thread_id: str,
    tenant_id: str = "default_tenant",
) -> AsyncIterator[dict[str, Any]]:
    """异步包装：当前仍委托同步 stream_graph_response，供需要 AsyncIterator 的调用方使用。"""
    for item in stream_graph_response(assistant, message, memory, thread_id, tenant_id):
        yield item
