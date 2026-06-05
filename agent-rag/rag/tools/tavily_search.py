from __future__ import annotations

import logging
import os
from typing import Any

from rag.metrics import record_tavily_search
from rag.telemetry import log_extra, resolve_tenant_id, span

logger = logging.getLogger(__name__)

TAVILY_ENABLED = os.environ.get("TAVILY_ENABLED", "true").lower() not in {"0", "false", "no"}
TAVILY_SEARCH_DEPTH = os.environ.get("TAVILY_SEARCH_DEPTH", "advanced")
TAVILY_MAX_RESULTS = int(os.environ.get("TAVILY_MAX_RESULTS", "5"))

WEB_DISCLAIMER = "以下信息来自互联网公开检索，非本地知识库内容，请自行核实。"


def _get_tavily_key() -> str:
    return os.environ.get("TAVILY_KEY", "").strip()


def is_tavily_enabled() -> bool:
    return bool(_get_tavily_key()) and TAVILY_ENABLED


def format_web_context(results: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for index, item in enumerate(results, start=1):
        title = str(item.get("title") or "未知来源").strip()
        url = str(item.get("url") or "").strip()
        content = str(item.get("content") or "").strip()
        parts.append(f"[{index}] 标题：{title}\nURL：{url}\n内容：{content}")
    return "\n\n".join(parts)


def extract_web_citations(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in results:
        url = str(item.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        title = str(item.get("title") or url).strip()
        citations.append(
            {
                "source": title,
                "url": url,
                "page": "web",
                "type": "web",
            }
        )
    return citations


def _normalize_results(raw: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in raw.get("results") or []:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        results.append(
            {
                "title": item.get("title") or "",
                "url": item.get("url") or "",
                "content": content,
                "score": item.get("score"),
            }
        )
    return results


def _record_and_return(base: dict[str, Any], status: str | None = None) -> dict[str, Any]:
    if status in {"ok", "empty", "error"}:
        record_tavily_search(status)
    return base


def search_web(query: str) -> dict[str, Any]:
    query = (query or "").strip()
    tenant_id = resolve_tenant_id()
    extra = log_extra()
    base: dict[str, Any] = {
        "status": "error",
        "query": query,
        "results": [],
        "context": "",
        "citations": [],
        "disclaimer": WEB_DISCLAIMER,
    }
    if not query:
        base["error"] = "empty_query"
        logger.info(
            "Tavily search skipped reason=empty_query tenant=%s",
            tenant_id,
            extra=extra,
        )
        return base
    if not is_tavily_enabled():
        base["error"] = "tavily_disabled"
        logger.info(
            "Tavily search skipped reason=tavily_disabled tenant=%s",
            tenant_id,
            extra=extra,
        )
        from rag.debug_trace import debug_log

        debug_log(
            "tavily_search.py:search_web",
            "tavily disabled",
            {"key_configured": bool(_get_tavily_key()), "enabled_flag": TAVILY_ENABLED},
            "A",
            run_id="post-fix",
        )
        return base

    with span("rag.web_search", {"rag.query_len": len(query)}):
        logger.info(
            "Tavily search start query=%s depth=%s max_results=%d tenant=%s",
            query,
            TAVILY_SEARCH_DEPTH,
            TAVILY_MAX_RESULTS,
            tenant_id,
            extra=extra,
        )
        try:
            from tavily import TavilyClient

            client = TavilyClient(_get_tavily_key())
            raw = client.search(
                query=query,
                search_depth=TAVILY_SEARCH_DEPTH,
                max_results=TAVILY_MAX_RESULTS,
            )
        except Exception as exc:
            logger.warning(
                "Tavily search error query=%s error=%s tenant=%s",
                query,
                exc,
                tenant_id,
                extra=extra,
            )
            base["error"] = str(exc)
            from rag.debug_trace import debug_log

            debug_log(
                "tavily_search.py:search_web",
                "tavily error",
                {"query": query, "error": str(exc)},
                "A",
                run_id="post-fix",
            )
            return _record_and_return(base, "error")

    results = _normalize_results(raw if isinstance(raw, dict) else {})
    if not results:
        logger.info(
            "Tavily search empty query=%s tenant=%s",
            query,
            tenant_id,
            extra=extra,
        )
        base["status"] = "empty"
        return _record_and_return(base, "empty")

    logger.info(
        "Tavily search ok query=%s result_count=%d tenant=%s",
        query,
        len(results),
        tenant_id,
        extra=extra,
    )
    from rag.debug_trace import debug_log

    debug_log(
        "tavily_search.py:search_web",
        "tavily ok",
        {"query": query, "result_count": len(results)},
        "A",
        run_id="post-fix",
    )
    return _record_and_return(
        {
            "status": "ok",
            "query": query,
            "results": results,
            "context": format_web_context(results),
            "citations": extract_web_citations(results),
            "disclaimer": WEB_DISCLAIMER,
        },
        "ok",
    )


def ensure_web_disclaimer(answer: str) -> str:
    text = (answer or "").strip()
    if not text:
        return WEB_DISCLAIMER
    keywords = ("互联网", "非本地知识库", "公开检索")
    if any(keyword in text for keyword in keywords):
        return text
    return f"{WEB_DISCLAIMER}\n\n{text}"
