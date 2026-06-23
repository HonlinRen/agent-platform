from __future__ import annotations

import contextvars
from dataclasses import dataclass, field
from typing import Any, Literal

TimingPhase = Literal["main", "post_turn"]

_timing_var: contextvars.ContextVar[RequestTiming | None] = contextvars.ContextVar("request_timing", default=None)
_append_run_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("timing_append_run_id", default=None)
_pending_timing_var: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "pending_timing_persist", default=None
)


@dataclass
class LlmCallRecord:
    operation: str
    duration_ms: int
    tokens_used: int = 0
    phase: TimingPhase = "main"
    sequence: int = 0


@dataclass
class RequestTiming:
    tenant_id: str
    thread_id: str
    embedding_ms: int = 0
    embedding_count: int = 0
    chroma_ms: int = 0
    chroma_count: int = 0
    rerank_ms: int = 0
    rerank_count: int = 0
    _llm_calls: list[LlmCallRecord] = field(default_factory=list)
    _llm_sequence: int = 0

    def record_embedding(self, ms: int) -> None:
        self.embedding_ms += max(0, ms)
        self.embedding_count += 1

    def record_chroma(self, ms: int) -> None:
        self.chroma_ms += max(0, ms)
        self.chroma_count += 1

    def record_rerank(self, ms: int) -> None:
        self.rerank_ms += max(0, ms)
        self.rerank_count += 1

    def record_llm(
        self,
        operation: str,
        duration_ms: int,
        tokens_used: int = 0,
        *,
        phase: TimingPhase = "main",
    ) -> None:
        self._llm_sequence += 1
        self._llm_calls.append(
            LlmCallRecord(
                operation=operation,
                duration_ms=max(0, duration_ms),
                tokens_used=tokens_used,
                phase=phase,
                sequence=self._llm_sequence,
            )
        )

    @property
    def llm_calls(self) -> list[LlmCallRecord]:
        return list(self._llm_calls)

    def main_llm_total_ms(self) -> int:
        return sum(c.duration_ms for c in self._llm_calls if c.phase == "main")

    def main_llm_call_count(self) -> int:
        return sum(1 for c in self._llm_calls if c.phase == "main")

    def snapshot(self) -> dict[str, Any]:
        return {
            "embedding_ms": self.embedding_ms,
            "embedding_count": self.embedding_count,
            "chroma_ms": self.chroma_ms,
            "chroma_count": self.chroma_count,
            "rerank_ms": self.rerank_ms,
            "rerank_count": self.rerank_count,
            "llm_total_ms": self.main_llm_total_ms(),
            "llm_call_count": self.main_llm_call_count(),
            "llm_calls": [
                {
                    "operation": c.operation,
                    "duration_ms": c.duration_ms,
                    "tokens_used": c.tokens_used,
                    "phase": c.phase,
                    "sequence": c.sequence,
                }
                for c in self._llm_calls
            ],
        }


def begin_request_timing(tenant_id: str, thread_id: str) -> RequestTiming:
    timing = RequestTiming(tenant_id=tenant_id, thread_id=thread_id)
    _timing_var.set(timing)
    return timing


def end_request_timing(tenant_id: str, thread_id: str) -> None:
    current = _timing_var.get()
    if current is not None and current.tenant_id == tenant_id and current.thread_id == thread_id:
        _timing_var.set(None)


def get_request_timing(thread_id: str | None = None) -> RequestTiming | None:
    timing = _timing_var.get()
    if timing is not None:
        return timing
    from rag.request_budget import get_request_budget

    budget = get_request_budget(thread_id)
    if budget is not None and budget.timing is not None:
        return budget.timing
    return None


def set_timing_append_run_id(run_id: str | None) -> None:
    _append_run_id_var.set(run_id)


def get_timing_append_run_id() -> str | None:
    return _append_run_id_var.get()


def clear_timing_append_run_id() -> None:
    _append_run_id_var.set(None)


def stash_pending_timing(
    *,
    tenant_id: str,
    thread_id: str,
    trace_run_id: str,
    route: str,
    timing_snapshot: dict[str, Any],
    elapsed_ms: int,
) -> None:
    _pending_timing_var.set(
        {
            "tenant_id": tenant_id,
            "thread_id": thread_id,
            "trace_run_id": trace_run_id,
            "route": route,
            "timing_snapshot": timing_snapshot,
            "elapsed_ms": elapsed_ms,
        }
    )


def pop_pending_timing(tenant_id: str, thread_id: str) -> dict[str, Any] | None:
    pending = _pending_timing_var.get()
    if pending is None:
        return None
    if pending.get("tenant_id") != tenant_id or pending.get("thread_id") != thread_id:
        return None
    _pending_timing_var.set(None)
    return pending


def clear_pending_timing(tenant_id: str, thread_id: str) -> None:
    pending = _pending_timing_var.get()
    if pending is None:
        return
    if pending.get("tenant_id") == tenant_id and pending.get("thread_id") == thread_id:
        _pending_timing_var.set(None)
