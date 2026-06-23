from __future__ import annotations

import contextvars
import os
import time
from dataclasses import dataclass, field
from typing import Any, Literal

BudgetStopReason = Literal["tokens", "tool_rounds", "timeout"]

_CHARS_PER_TOKEN = 4

_budget_var: contextvars.ContextVar[RequestBudget | None] = contextvars.ContextVar("request_budget", default=None)
# LangGraph 节点可能在未继承 contextvars 的线程中执行；用 thread_id 回退查找同请求的 budget。
_budget_by_thread: dict[str, RequestBudget] = {}

MAX_REQUEST_TOKENS = int(os.environ.get("MAX_REQUEST_TOKENS", "12000"))
MAX_TOOL_ROUNDS_LIMIT = int(os.environ.get("MAX_TOOL_ROUNDS", "3"))
MAX_GRAPH_RUNTIME_SECONDS = float(os.environ.get("MAX_GRAPH_RUNTIME_SECONDS", "90"))


def _env_limit(value: int | float) -> int | float | None:
    """0 or negative disables the check."""
    if value <= 0:
        return None
    return value


def estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _extract_usage_tokens(response: Any) -> int | None:
    usage = getattr(response, "usage_metadata", None)
    if isinstance(usage, dict):
        input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
        output_tokens = usage.get("output_tokens") or usage.get("completion_tokens") or 0
        total = int(input_tokens) + int(output_tokens)
        return total if total > 0 else None

    meta = getattr(response, "response_metadata", None) or {}
    if isinstance(meta, dict):
        token_usage = meta.get("token_usage") or meta.get("usage") or {}
        if isinstance(token_usage, dict):
            input_tokens = token_usage.get("prompt_tokens") or token_usage.get("input_tokens") or 0
            output_tokens = token_usage.get("completion_tokens") or token_usage.get("output_tokens") or 0
            total = int(input_tokens) + int(output_tokens)
            return total if total > 0 else None
    return None


def _fallback_tokens(response: Any, fallback_text: str) -> int:
    if isinstance(response, str):
        return estimate_text_tokens(response or fallback_text)
    content = getattr(response, "content", None)
    if isinstance(content, str) and content.strip():
        return estimate_text_tokens(content)
    if fallback_text.strip():
        return estimate_text_tokens(fallback_text)
    return 1


@dataclass
class RequestBudget:
    tenant_id: str
    thread_id: str
    max_tokens: int | None = field(default_factory=lambda: _env_limit(MAX_REQUEST_TOKENS))  # type: ignore[arg-type]
    max_tool_rounds: int | None = field(default_factory=lambda: _env_limit(MAX_TOOL_ROUNDS_LIMIT))  # type: ignore[arg-type]
    max_runtime_seconds: float | None = field(default_factory=lambda: _env_limit(MAX_GRAPH_RUNTIME_SECONDS))  # type: ignore[arg-type]
    total_tokens_used: int = 0
    stop_reason: BudgetStopReason | None = None
    started_at: float = field(default_factory=time.perf_counter)
    _stop_recorded: bool = False
    timing: Any = None

    def _set_stop_reason(self, reason: BudgetStopReason) -> None:
        if self.stop_reason is None:
            self.stop_reason = reason
            self._record_stop_metric(reason)

    def _record_stop_metric(self, reason: BudgetStopReason) -> None:
        if self._stop_recorded:
            return
        self._stop_recorded = True
        try:
            from rag.telemetry import RAG_BUDGET_STOP_TOTAL

            RAG_BUDGET_STOP_TOTAL.labels(reason=reason, tenant=self.tenant_id).inc()
        except Exception:
            pass

    def track_llm_response(self, response: Any, *, fallback_text: str = "") -> int:
        tokens = _extract_usage_tokens(response)
        if tokens is None:
            tokens = _fallback_tokens(response, fallback_text)
        self.total_tokens_used += tokens
        if self.max_tokens is not None and self.total_tokens_used >= self.max_tokens:
            self._set_stop_reason("tokens")
        return tokens

    def check_tool_rounds(self, tool_rounds: int) -> None:
        if self.max_tool_rounds is not None and tool_rounds >= self.max_tool_rounds:
            self._set_stop_reason("tool_rounds")

    def check_runtime(self) -> None:
        if self.max_runtime_seconds is None:
            return
        elapsed = time.perf_counter() - self.started_at
        if elapsed >= self.max_runtime_seconds:
            self._set_stop_reason("timeout")

    def should_force_generate(self) -> bool:
        return self.stop_reason is not None

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.started_at) * 1000)


def begin_request_budget(tenant_id: str, thread_id: str) -> RequestBudget:
    from rag.request_timing import RequestTiming, _timing_var

    timing = RequestTiming(tenant_id=tenant_id, thread_id=thread_id)
    budget = RequestBudget(tenant_id=tenant_id, thread_id=thread_id, timing=timing)
    _budget_var.set(budget)
    _timing_var.set(timing)
    _budget_by_thread[thread_id] = budget
    return budget


def end_request_budget(tenant_id: str, thread_id: str) -> None:
    from rag.request_timing import _timing_var

    current = _budget_var.get()
    if current is not None and current.tenant_id == tenant_id and current.thread_id == thread_id:
        _budget_var.set(None)
        _timing_var.set(None)
    _budget_by_thread.pop(thread_id, None)


def get_request_budget(thread_id: str | None = None) -> RequestBudget | None:
    budget = _budget_var.get()
    if budget is not None:
        return budget
    if thread_id:
        return _budget_by_thread.get(thread_id)
    return None


def track_llm_response(response: Any, *, fallback_text: str = "", thread_id: str | None = None) -> int:
    budget = get_request_budget(thread_id)
    if budget is None:
        return 0
    return budget.track_llm_response(response, fallback_text=fallback_text)


def should_force_generate(thread_id: str | None = None) -> bool:
    budget = get_request_budget(thread_id)
    return budget.should_force_generate() if budget is not None else False


def get_budget_stop_reason(thread_id: str | None = None) -> BudgetStopReason | None:
    budget = get_request_budget(thread_id)
    return budget.stop_reason if budget is not None else None


def get_total_tokens_used(thread_id: str | None = None) -> int:
    budget = get_request_budget(thread_id)
    return budget.total_tokens_used if budget is not None else 0
