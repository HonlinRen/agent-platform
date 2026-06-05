from __future__ import annotations

from unittest.mock import MagicMock, patch

import rag.tools.tavily_search as tavily_mod
from rag.tools.tavily_search import (
    ensure_web_disclaimer,
    extract_web_citations,
    format_web_context,
    is_tavily_enabled,
    search_web,
)


def test_is_tavily_enabled_requires_key(monkeypatch):
    monkeypatch.delenv("TAVILY_KEY", raising=False)
    monkeypatch.setattr(tavily_mod, "TAVILY_ENABLED", True)
    assert is_tavily_enabled() is False

    monkeypatch.setenv("TAVILY_KEY", "tvly-test")
    assert is_tavily_enabled() is True

    monkeypatch.setattr(tavily_mod, "TAVILY_ENABLED", False)
    assert is_tavily_enabled() is False


def test_format_web_context_and_citations():
    results = [
        {
            "title": "Example Site",
            "url": "https://example.com/a",
            "content": "Some web content",
        }
    ]
    context = format_web_context(results)
    assert "Example Site" in context
    assert "https://example.com/a" in context

    citations = extract_web_citations(results)
    assert citations == [
        {
            "source": "Example Site",
            "url": "https://example.com/a",
            "page": "web",
            "type": "web",
        }
    ]


@patch("rag.tools.tavily_search.record_tavily_search")
@patch("tavily.TavilyClient")
def test_search_web_success(mock_client_cls, mock_record, monkeypatch):
    monkeypatch.setenv("TAVILY_KEY", "tvly-test")
    monkeypatch.setattr(tavily_mod, "TAVILY_ENABLED", True)

    mock_client = MagicMock()
    mock_client.search.return_value = {
        "results": [
            {
                "title": "News",
                "url": "https://news.example.com",
                "content": "Breaking update",
                "score": 0.9,
            }
        ]
    }
    mock_client_cls.return_value = mock_client

    result = search_web("latest news")
    assert result["status"] == "ok"
    assert result["context"]
    assert result["citations"][0]["type"] == "web"
    mock_record.assert_called_once_with("ok")
    mock_client.search.assert_called_once_with(
        query="latest news",
        search_depth=tavily_mod.TAVILY_SEARCH_DEPTH,
        max_results=tavily_mod.TAVILY_MAX_RESULTS,
    )


@patch("rag.tools.tavily_search.record_tavily_search")
@patch("tavily.TavilyClient")
def test_search_web_empty(mock_client_cls, mock_record, monkeypatch):
    monkeypatch.setenv("TAVILY_KEY", "tvly-test")
    monkeypatch.setattr(tavily_mod, "TAVILY_ENABLED", True)
    mock_client_cls.return_value.search.return_value = {"results": []}

    result = search_web("nothing")
    assert result["status"] == "empty"
    mock_record.assert_called_once_with("empty")


@patch("rag.tools.tavily_search.record_tavily_search")
@patch("tavily.TavilyClient")
def test_search_web_api_error(mock_client_cls, mock_record, monkeypatch):
    monkeypatch.setenv("TAVILY_KEY", "tvly-test")
    monkeypatch.setattr(tavily_mod, "TAVILY_ENABLED", True)
    mock_client_cls.return_value.search.side_effect = RuntimeError("api down")

    result = search_web("fail")
    assert result["status"] == "error"
    mock_record.assert_called_once_with("error")


@patch("rag.tools.tavily_search.record_tavily_search")
def test_search_web_disabled_does_not_record(mock_record, monkeypatch):
    monkeypatch.delenv("TAVILY_KEY", raising=False)
    result = search_web("query")
    assert result["status"] == "error"
    assert result["error"] == "tavily_disabled"
    mock_record.assert_not_called()


@patch("rag.metrics.record_tool_call")
@patch("rag.tools.tavily_search.record_tavily_search")
@patch("tavily.TavilyClient")
def test_search_web_does_not_use_record_tool_call(mock_client_cls, _mock_record, mock_tool_call, monkeypatch):
    monkeypatch.setenv("TAVILY_KEY", "tvly-test")
    monkeypatch.setattr(tavily_mod, "TAVILY_ENABLED", True)
    mock_client_cls.return_value.search.return_value = {
        "results": [{"title": "A", "url": "https://a.com", "content": "text"}]
    }

    search_web("query")
    mock_tool_call.assert_not_called()


def test_ensure_web_disclaimer_prepends_when_missing():
    answer = ensure_web_disclaimer("这是回答。")
    assert answer.startswith("以下信息来自互联网公开检索")

    already = "以下信息来自互联网公开检索，非本地知识库内容。\n\n详情如下。"
    assert ensure_web_disclaimer(already) == already
