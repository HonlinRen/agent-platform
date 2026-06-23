"""HTTP client for calling the RAG chat stream API."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_RAG_API_URL = os.environ.get("RAG_API_URL", "http://127.0.0.1:8081")
DEFAULT_TIMEOUT = float(os.environ.get("RAG_EVAL_TIMEOUT", "120"))


@dataclass
class RagAnswer:
    content: str
    route: str
    citations: list[dict[str, Any]]
    rewritten_query: str
    thread_id: str | None = None


def _parse_sse_events(raw: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for block in raw.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_name = "message"
        data_payload: dict[str, Any] = {}
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_text = line[len("data:") :].strip()
                if data_text:
                    data_payload = json.loads(data_text)
        events.append((event_name, data_payload))
    return events


def _consume_sse_stream(response: httpx.Response) -> RagAnswer:
    buffer = ""
    done_payload: dict[str, Any] | None = None
    error_message = ""

    for chunk in response.iter_text():
        buffer += chunk
        while "\n\n" in buffer:
            block, buffer = buffer.split("\n\n", 1)
            for event_name, payload in _parse_sse_events(block + "\n\n"):
                if event_name == "done":
                    done_payload = payload
                elif event_name == "error":
                    error_message = str(payload.get("message") or "unknown error")

    if buffer.strip():
        for event_name, payload in _parse_sse_events(buffer + "\n\n"):
            if event_name == "done":
                done_payload = payload
            elif event_name == "error":
                error_message = str(payload.get("message") or "unknown error")

    if error_message:
        raise RuntimeError(f"RAG API error: {error_message}")
    if not done_payload:
        raise RuntimeError("RAG API stream ended without done event")

    return RagAnswer(
        content=str(done_payload.get("content") or "").strip(),
        route=str(done_payload.get("route") or "unknown"),
        citations=list(done_payload.get("citations") or []),
        rewritten_query=str(done_payload.get("rewritten_query") or ""),
        thread_id=done_payload.get("thread_id"),
    )


def check_health(base_url: str = DEFAULT_RAG_API_URL, *, timeout: float = 10.0) -> bool:
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/health", timeout=timeout)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


def fetch_rag_answer(
    question: str,
    *,
    collection_name: str,
    base_url: str = DEFAULT_RAG_API_URL,
    timeout: float = DEFAULT_TIMEOUT,
) -> RagAnswer:
    payload = {
        "message": question,
        "collection_name": collection_name,
        "history": [],
    }
    url = f"{base_url.rstrip('/')}/api/chat/stream"
    logger.info("fetching RAG answer via API: %s", url)
    with httpx.Client(timeout=timeout) as client:
        with client.stream("POST", url, json=payload) as response:
            response.raise_for_status()
            return _consume_sse_stream(response)
