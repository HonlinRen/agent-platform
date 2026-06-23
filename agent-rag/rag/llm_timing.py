from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from rag.metrics import record_llm
from rag.request_budget import track_llm_response
from rag.request_timing import (
    TimingPhase,
    get_request_timing,
    get_timing_append_run_id,
)
from rag.telemetry import observe_embedding_duration, observe_llm_duration, resolve_tenant_id

T = TypeVar("T")


def timed_llm_invoke(
    operation: str,
    fn: Callable[[], T],
    *,
    fallback_text: str = "",
    phase: TimingPhase = "main",
    tenant: str | None = None,
    thread_id: str | None = None,
) -> T:
    """Time an LLM call, record to RequestTiming / Prometheus, and track tokens."""
    tenant_id = resolve_tenant_id(tenant)
    start = time.perf_counter()
    response = fn()
    duration_ms = int((time.perf_counter() - start) * 1000)
    observe_llm_duration(operation, tenant_id, duration_ms / 1000.0)
    tokens = track_llm_response(response, fallback_text=fallback_text, thread_id=thread_id)
    record_llm(tenant=tenant_id)

    timing = get_request_timing(thread_id)
    if timing is not None:
        timing.record_llm(operation, duration_ms, tokens, phase=phase)
    elif phase == "post_turn":
        trace_run_id = get_timing_append_run_id()
        if trace_run_id:
            from db.timing_repository import append_timing_llm_call_best_effort

            append_timing_llm_call_best_effort(
                tenant_id=tenant_id,
                trace_run_id=trace_run_id,
                operation=operation,
                duration_ms=duration_ms,
                tokens_used=tokens,
                phase="post_turn",
            )

    return response


def timed_embedding(
    fn: Callable[[], T],
    *,
    tenant: str | None = None,
    thread_id: str | None = None,
) -> T:
    """Time an embedding call and record to RequestTiming / Prometheus."""
    tenant_id = resolve_tenant_id(tenant)
    start = time.perf_counter()
    result = fn()
    duration_ms = int((time.perf_counter() - start) * 1000)
    observe_embedding_duration(tenant_id, duration_ms / 1000.0)
    timing = get_request_timing(thread_id)
    if timing is not None:
        timing.record_embedding(duration_ms)
    return result
