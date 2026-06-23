from __future__ import annotations

from rag.request_budget import _budget_var, begin_request_budget, end_request_budget, get_request_budget
from rag.request_timing import _timing_var, get_request_timing


def test_budget_lookup_by_thread_id_without_contextvar():
    budget = begin_request_budget("tenant_a", "thread_registry_test")
    budget.timing.record_chroma(42)
    budget.timing.record_rerank(18)

    # LangGraph 工作线程通常拿不到 contextvar，但 thread_id 仍可命中注册表。
    _budget_var.set(None)
    _timing_var.set(None)

    resolved_budget = get_request_budget("thread_registry_test")
    assert resolved_budget is budget
    timing = get_request_timing("thread_registry_test")
    assert timing is budget.timing
    assert timing.chroma_ms == 42
    assert timing.rerank_ms == 18

    end_request_budget("tenant_a", "thread_registry_test")
    assert get_request_budget("thread_registry_test") is None
