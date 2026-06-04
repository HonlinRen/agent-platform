from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from mcp.server.fastmcp import FastMCP

from rag.assistant import CarSafetyWhitepaperAssistant

mcp = FastMCP("whitepaper")
_assistant: CarSafetyWhitepaperAssistant | None = None


def _get_assistant() -> CarSafetyWhitepaperAssistant:
    global _assistant
    if _assistant is None:
        _assistant = CarSafetyWhitepaperAssistant()
    return _assistant


@mcp.tool()
def search_whitepaper(query: str) -> str:
    """向量检索白皮书内容并 rerank。"""
    assistant = _get_assistant()
    ranked = assistant.retrieve_and_rank(query)
    reject, msg = assistant.check_retrieval_quality(ranked)
    if reject:
        return json.dumps({"status": "reject", "message": msg, "chunks": []}, ensure_ascii=False)
    chunks = []
    for item in ranked:
        metadata = item.get("metadata") or {}
        chunks.append(
            {
                "text": item.get("text", ""),
                "source": metadata.get("source", "unknown"),
                "page": metadata.get("page", metadata.get("page_number", "?")),
                "rerank_score": item.get("rerank_score"),
            }
        )
    return json.dumps({"status": "ok", "chunks": chunks}, ensure_ascii=False)


@mcp.tool()
def get_chunk_by_source(source: str, page: int) -> str:
    """按 source 与 page 精确获取 chunk。"""
    assistant = _get_assistant()
    chunks = assistant.get_chunk_by_source(source, page)
    return json.dumps({"chunks": chunks}, ensure_ascii=False, default=str)


@mcp.tool()
def list_collection_stats() -> str:
    """列出集合文档数与来源。"""
    assistant = _get_assistant()
    return json.dumps(assistant.list_collection_stats(), ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
