from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from rag.graph.nodes import route_after_grade, route_after_router, route_after_web_search
from rag.reject import needs_web_supplement
from rag.router import classify_route, detect_web_intent


def test_detect_web_intent_keywords():
    assert detect_web_intent("联网搜索 查一下英伟达盈利能力") is True
    assert detect_web_intent("请网上搜索碳化硅最新进展") is True
    assert detect_web_intent("查一下最新行业动态") is True
    assert detect_web_intent("碳化硅功率器件可靠性测试方法") is False
    assert detect_web_intent("你好") is False


def test_needs_web_supplement_score_range():
    assert needs_web_supplement([{"rerank_score": 0.3}]) is True
    assert needs_web_supplement([{"rerank_score": 0.5}]) is False
    assert needs_web_supplement([{"rerank_score": 0.1}]) is False
    assert needs_web_supplement([]) is False


@patch("rag.router.timed_llm_invoke")
def test_classify_route_web_keyword_skips_llm(mock_timed_llm_invoke):
    assistant = MagicMock()
    route = classify_route(assistant, "联网搜索英伟达部门")
    assert route == "web"
    assistant.router_llm.invoke.assert_not_called()


@patch("rag.router.timed_llm_invoke")
def test_classify_route_parses_web_label(mock_timed_llm_invoke):
    assistant = MagicMock()
    assistant.collection_name = "semiconductor"
    mock_timed_llm_invoke.side_effect = lambda _op, fn, **_kw: fn()
    assistant.router_llm.invoke.return_value = MagicMock(content="web")
    route = classify_route(assistant, "英伟达有哪些部门")
    assert route == "web"


@patch("rag.router.timed_llm_invoke")
def test_classify_route_parses_direct_label(mock_timed_llm_invoke):
    assistant = MagicMock()
    assistant.collection_name = "semiconductor"
    mock_timed_llm_invoke.side_effect = lambda _op, fn, **_kw: fn()
    assistant.router_llm.invoke.return_value = MagicMock(content="direct")
    route = classify_route(assistant, "你好")
    assert route == "direct"


def test_route_after_router_web():
    assert route_after_router({"route": "web"}) == "web_search"
    assert route_after_router({"route": "direct"}) == "direct_reply"
    assert route_after_router({"route": "rag"}) == "rewrite"


@patch("rag.graph.nodes.is_tavily_enabled", return_value=True)
def test_route_after_grade_reject_triggers_web(mock_tavily):
    assert route_after_grade({"reject_message": "no results"}) == "web_search"


@patch("rag.graph.nodes.is_tavily_enabled", return_value=True)
def test_route_after_grade_supplement_triggers_web(mock_tavily):
    state = {
        "reject_message": "",
        "documents": [{"rerank_score": 0.3}],
        "route": "rag",
    }
    assert route_after_grade(state) == "web_search"


@patch("rag.graph.nodes.is_tavily_enabled", return_value=True)
def test_route_after_grade_high_score_generates(mock_tavily):
    state = {
        "reject_message": "",
        "documents": [{"rerank_score": 0.6}],
        "route": "rag",
    }
    assert route_after_grade(state) == "generate"


def test_route_after_web_search_hybrid():
    state = {"context_source": "hybrid", "web_context": "web results"}
    assert route_after_web_search(state) == "generate"


def test_route_after_web_search_local_fallback():
    state = {"context_source": "local", "context": "local results"}
    assert route_after_web_search(state) == "generate"


def test_route_after_web_search_reject():
    assert route_after_web_search({"context_source": "local"}) == "reject"
