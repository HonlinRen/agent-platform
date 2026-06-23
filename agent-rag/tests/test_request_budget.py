from __future__ import annotations

import time
import pytest
from langchain_core.messages import AIMessage

from rag.graph.nodes import route_after_agent, route_after_grade, route_after_tools
from rag.request_budget import (
    RequestBudget,
    begin_request_budget,
    end_request_budget,
    estimate_text_tokens,
    get_request_budget,
    should_force_generate,
    track_llm_response,
)


@pytest.fixture
def budget():
    b = begin_request_budget("tenant_a", "thread_1")
    yield b
    end_request_budget("tenant_a", "thread_1")


def test_estimate_text_tokens():
    assert estimate_text_tokens("") == 0
    assert estimate_text_tokens("abcd") == 1
    assert estimate_text_tokens("a" * 8) == 2


def test_track_llm_response_usage_metadata(budget):
    response = AIMessage(
        content="ok",
        usage_metadata={"input_tokens": 10, "output_tokens": 5},
    )
    used = track_llm_response(response)
    assert used == 15
    assert budget.total_tokens_used == 15


def test_track_llm_response_fallback(budget):
    used = track_llm_response("hello world", fallback_text="hello world")
    assert used >= 1
    assert budget.total_tokens_used >= 1


def test_token_limit_triggers_force_generate(budget):
    budget.max_tokens = 100
    budget.track_llm_response(AIMessage(content="x" * 400, usage_metadata={"input_tokens": 50, "output_tokens": 60}))
    assert budget.stop_reason == "tokens"
    assert should_force_generate() is True


def test_tool_rounds_limit(budget):
    budget.max_tool_rounds = 2
    budget.check_tool_rounds(2)
    assert budget.stop_reason == "tool_rounds"
    assert should_force_generate() is True


def test_runtime_limit(budget):
    budget.max_runtime_seconds = 0.01
    time.sleep(0.02)
    budget.check_runtime()
    assert budget.stop_reason == "timeout"
    assert should_force_generate() is True


def test_end_request_budget_clears_context(budget):
    assert get_request_budget() is not None
    end_request_budget("tenant_a", "thread_1")
    assert get_request_budget() is None


def test_route_after_agent_respects_tool_rounds():
    last = AIMessage(content="", tool_calls=[{"name": "search_whitepaper", "args": {}, "id": "1"}])
    state = {"messages": [last], "tool_rounds": 3}
    assert route_after_agent(state) == "generate"

    state["tool_rounds"] = 1
    assert route_after_agent(state) == "tools"


def test_route_after_agent_force_generate(budget):
    budget.max_tokens = 10
    budget.track_llm_response(AIMessage(content="x" * 100, usage_metadata={"input_tokens": 8, "output_tokens": 5}))
    last = AIMessage(content="", tool_calls=[{"name": "t", "args": {}, "id": "1"}])
    state = {"messages": [last], "tool_rounds": 0}
    assert route_after_agent(state) == "generate"


def test_route_after_tools_force_generate(budget):
    budget.max_tool_rounds = 1
    budget.check_tool_rounds(1)
    assert route_after_tools({"tool_rounds": 1}) == "generate"


def test_route_after_tools_continues_agent():
    assert route_after_tools({"tool_rounds": 1}) == "agent"


def test_route_after_grade_force_generate(budget):
    budget.max_tokens = 5
    budget.track_llm_response(AIMessage(content="long", usage_metadata={"input_tokens": 3, "output_tokens": 3}))
    assert route_after_grade({"reject_message": "fail", "route": "rag"}) == "generate"


def test_zero_limit_disables_check():
    budget = RequestBudget(tenant_id="t", thread_id="th", max_tokens=0, max_tool_rounds=0, max_runtime_seconds=0)
    budget.track_llm_response(AIMessage(content="x" * 10000, usage_metadata={"input_tokens": 5000, "output_tokens": 5000}))
    budget.check_tool_rounds(99)
    budget.check_runtime()
    assert budget.stop_reason is None
