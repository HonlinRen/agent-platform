from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from api.deps import get_assistant
from api.errors import sanitize_chat_error
from api.schemas import ChatStopRequest, ChatStopResponse, ChatStreamRequest
from db.repository import save_turn_best_effort
from db.timing_repository import save_timing_best_effort
from rag.assistant import CarSafetyWhitepaperAssistant
from rag.cancellation import begin_run, end_run, request_cancel
from rag.graph.streaming import stream_graph_response
from rag.knowledge_bases import validate_collection_name
from rag.memory.manager import MemoryManager
from rag.memory.summary import maybe_update_summary_best_effort
from rag.memory.tenant_profile import maybe_update_tenant_profile_best_effort
from rag.request_timing import (
    clear_pending_timing,
    clear_timing_append_run_id,
    pop_pending_timing,
    set_timing_append_run_id,
)
from rag.telemetry import (
    bind_request_context,
    current_trace_id,
    get_request_id,
    observe_agent_request,
    record_chat_request,
    span,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _resolve_thread_id(request: ChatStreamRequest, http_request: Request) -> str:
    if request.thread_id:
        return request.thread_id
    header_id = http_request.headers.get("X-Thread-Id")
    if header_id:
        return header_id
    return str(uuid.uuid4())


def _resolve_tenant_id(http_request: Request) -> str:
    return http_request.headers.get("X-Tenant-Id") or "default_tenant"


def _load_memory_context(
    tenant_id: str,
    thread_id: str,
    request: ChatStreamRequest,
):
    fallback = [{"role": item.role, "content": item.content} for item in request.history]
    return MemoryManager.load_best_effort(
        tenant_id,
        thread_id,
        fallback_messages=fallback,
    )


def _memory_metadata(memory) -> dict:
    return {"memory": memory.to_metadata()}


def _persist_timing_from_event(
    event: dict,
    *,
    tenant_id: str,
    thread_id: str,
    collection_name: str,
    status: str,
) -> str | None:
    timing_snapshot = event.get("timing_snapshot")
    elapsed_ms = event.get("elapsed_ms")
    run_id = event.get("run_id") or current_trace_id()
    if elapsed_ms is None or not timing_snapshot:
        pending = pop_pending_timing(tenant_id, thread_id)
        if pending:
            if elapsed_ms is None:
                elapsed_ms = pending.get("elapsed_ms")
            if not timing_snapshot:
                timing_snapshot = pending.get("timing_snapshot")
    if elapsed_ms is None:
        return run_id
    if not timing_snapshot:
        timing_snapshot = {}
    save_timing_best_effort(
        tenant_id=tenant_id,
        thread_id=thread_id,
        request_id=get_request_id(),
        trace_run_id=run_id,
        route=event.get("route") or "rag",
        status=status,
        total_ms=int(elapsed_ms),
        timing_snapshot=timing_snapshot,
        collection_name=collection_name,
    )
    clear_pending_timing(tenant_id, thread_id)
    return run_id


def _run_post_turn_updates(
    assistant: CarSafetyWhitepaperAssistant,
    tenant_id: str,
    thread_id: str,
    trace_run_id: str | None,
) -> None:
    if not trace_run_id:
        maybe_update_summary_best_effort(assistant, tenant_id, thread_id)
        maybe_update_tenant_profile_best_effort(assistant, tenant_id, thread_id)
        return
    set_timing_append_run_id(trace_run_id)
    try:
        maybe_update_summary_best_effort(assistant, tenant_id, thread_id)
        maybe_update_tenant_profile_best_effort(assistant, tenant_id, thread_id)
    finally:
        clear_timing_append_run_id()


def _stream_chat_events(
    assistant: CarSafetyWhitepaperAssistant,
    request: ChatStreamRequest,
    thread_id: str,
    tenant_id: str,
    collection_name: str,
) -> Iterator[str]:
    message = request.message.strip()
    if not message:
        record_chat_request("unknown", tenant_id, "error")
        yield _format_sse("error", {"message": "消息不能为空", "request_id": get_request_id()})
        return

    memory = _load_memory_context(tenant_id, thread_id, request)

    stream_start = time.perf_counter()
    final_route = "rag"
    cancelled = False

    begin_run(tenant_id, thread_id)
    try:
        with span("rag.chat.stream", {"rag.collection": collection_name}):
            for event in stream_graph_response(assistant, message, memory, thread_id, tenant_id):
                event_type = event.get("type")
                if event_type == "status":
                    payload: dict = {"stage": event.get("stage")}
                    if event.get("node"):
                        payload["node"] = event.get("node")
                    if event.get("tool_name"):
                        payload["tool_name"] = event.get("tool_name")
                    yield _format_sse("status", payload)
                elif event_type == "token":
                    yield _format_sse("token", {"content": event.get("content", "")})
                elif event_type == "tool_call":
                    yield _format_sse(
                        "tool_call",
                        {
                            "name": event.get("name"),
                            "args": event.get("args") or {},
                            "status": event.get("status", "start"),
                            "result": event.get("result"),
                        },
                    )
                elif event_type == "done":
                    content = event.get("content", "")
                    final_route = event.get("route") or "rag"
                    run_id = event.get("run_id") or current_trace_id()
                    metadata = {
                        "rewritten_query": event.get("rewritten_query", message),
                        "route": final_route,
                        "tool_calls": event.get("tool_calls") or [],
                        "run_id": run_id,
                        "citations": event.get("citations") or [],
                        "context_source": event.get("context_source", "local"),
                        **_memory_metadata(memory),
                    }
                    if event.get("budget_stop_reason"):
                        metadata["budget_stop_reason"] = event["budget_stop_reason"]
                    if event.get("total_tokens_used") is not None:
                        metadata["total_tokens_used"] = event["total_tokens_used"]
                    if event.get("elapsed_ms") is not None:
                        metadata["elapsed_ms"] = event["elapsed_ms"]
                    save_turn_best_effort(
                        tenant_id=tenant_id,
                        thread_id=thread_id,
                        collection_name=collection_name,
                        user_message=message,
                        assistant_message=content,
                        metadata=metadata,
                        user_message_id=request.user_message_id,
                        assistant_message_id=request.assistant_message_id,
                    )
                    trace_run_id = _persist_timing_from_event(
                        event,
                        tenant_id=tenant_id,
                        thread_id=thread_id,
                        collection_name=collection_name,
                        status="success",
                    )
                    _run_post_turn_updates(assistant, tenant_id, thread_id, trace_run_id)
                    yield _format_sse(
                        "done",
                        {
                            "content": content,
                            "rewritten_query": event.get("rewritten_query", message),
                            "thread_id": thread_id,
                            "route": final_route,
                            "tool_calls": event.get("tool_calls") or [],
                            "run_id": run_id,
                            "citations": event.get("citations") or [],
                            "context_source": event.get("context_source", "local"),
                            "budget_stop_reason": event.get("budget_stop_reason"),
                            "total_tokens_used": event.get("total_tokens_used"),
                            "elapsed_ms": event.get("elapsed_ms"),
                        },
                    )
                elif event_type == "cancelled":
                    cancelled = True
                    content = event.get("content", "")
                    final_route = event.get("route") or final_route
                    run_id = event.get("run_id") or current_trace_id()
                    metadata = {
                        "rewritten_query": event.get("rewritten_query", message),
                        "route": final_route,
                        "tool_calls": event.get("tool_calls") or [],
                        "run_id": run_id,
                        "citations": event.get("citations") or [],
                        "context_source": event.get("context_source", "local"),
                        "stopped": True,
                        **_memory_metadata(memory),
                    }
                    if content:
                        save_turn_best_effort(
                            tenant_id=tenant_id,
                            thread_id=thread_id,
                            collection_name=collection_name,
                            user_message=message,
                            assistant_message=content,
                            metadata=metadata,
                            user_message_id=request.user_message_id,
                            assistant_message_id=request.assistant_message_id,
                        )
                    _persist_timing_from_event(
                        event,
                        tenant_id=tenant_id,
                        thread_id=thread_id,
                        collection_name=collection_name,
                        status="cancelled",
                    )
                    yield _format_sse(
                        "cancelled",
                        {
                            "content": content,
                            "thread_id": thread_id,
                            "stopped": True,
                            "request_id": get_request_id(),
                        },
                    )
                    break
        if cancelled:
            observe_agent_request(final_route, tenant_id, time.perf_counter() - stream_start)
            record_chat_request(final_route, tenant_id, "cancelled")
        else:
            observe_agent_request(final_route, tenant_id, time.perf_counter() - stream_start)
            record_chat_request(final_route, tenant_id, "success")
    except Exception as exc:
        logger.exception("chat stream failed", extra={"request_id": get_request_id()})
        record_chat_request(final_route, tenant_id, "error")
        pending = pop_pending_timing(tenant_id, thread_id)
        if pending:
            save_timing_best_effort(
                tenant_id=tenant_id,
                thread_id=thread_id,
                request_id=get_request_id(),
                trace_run_id=pending["trace_run_id"],
                route=final_route or pending.get("route") or "rag",
                status="error",
                total_ms=int(pending["elapsed_ms"]),
                timing_snapshot=pending["timing_snapshot"],
                collection_name=collection_name,
            )
        yield _format_sse(
            "error",
            {"message": sanitize_chat_error(exc), "request_id": get_request_id()},
        )
    finally:
        end_run(tenant_id, thread_id)


@router.post("/stop", response_model=ChatStopResponse)
def chat_stop(request_body: ChatStopRequest, request: Request) -> ChatStopResponse:
    tenant_id = _resolve_tenant_id(request)
    thread_id = request_body.thread_id.strip()
    if not thread_id:
        raise HTTPException(status_code=400, detail="thread_id 不能为空")
    cancelled = request_cancel(tenant_id, thread_id)
    return ChatStopResponse(ok=True, cancelled=cancelled)


@router.post("/stream")
def chat_stream(request_body: ChatStreamRequest, request: Request) -> StreamingResponse:
    if not getattr(request.app.state, "assistants", None):
        raise HTTPException(status_code=503, detail="Assistant not initialized")

    try:
        collection_name = validate_collection_name(request_body.collection_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    assistant = get_assistant(request.app, collection_name)
    thread_id = _resolve_thread_id(request_body, request)
    tenant_id = _resolve_tenant_id(request)
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    bind_request_context(tenant_id=tenant_id, thread_id=thread_id, request_id=request_id)

    return StreamingResponse(
        _stream_chat_events(assistant, request_body, thread_id, tenant_id, collection_name),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Thread-Id": thread_id,
            "X-Request-Id": request_id,
        },
    )
