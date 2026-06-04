from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

import httpx
from langchain_core.tools import StructuredTool

from rag.metrics import record_tool_call
from rag.reject import CLARIFY_MESSAGE, REJECT_MESSAGE
from rag.telemetry import inject_trace_headers, span
from rag.tools.mcp_client import load_mcp_tools

if TYPE_CHECKING:
    from rag.assistant import CarSafetyWhitepaperAssistant

logger = logging.getLogger(__name__)

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8080")
MCP_ENABLED = os.environ.get("MCP_ENABLED", "false").lower() in {"1", "true", "yes"}


def _wrap_tool(name: str, func):
    def wrapped(*args, **kwargs):
        with span(f"rag.tool.{name}"):
            record_tool_call(tool=name)
            return func(*args, **kwargs)

    wrapped.__name__ = func.__name__
    wrapped.__doc__ = func.__doc__
    return wrapped


def _local_chroma_tools(assistant: CarSafetyWhitepaperAssistant) -> list[StructuredTool]:
    def search_whitepaper(query: str) -> str:
        """向量检索白皮书内容并 rerank，返回结构化 chunk 列表。"""
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

    def get_chunk_by_source(source: str, page: int) -> str:
        """按文件名与页码精确获取 chunk。"""
        chunks = assistant.get_chunk_by_source(source, page)
        return json.dumps({"chunks": chunks}, ensure_ascii=False, default=str)

    def list_collection_stats() -> str:
        """列出集合文档数与来源文件。"""
        return json.dumps(assistant.list_collection_stats(), ensure_ascii=False)

    return [
        StructuredTool.from_function(
            func=_wrap_tool("search_whitepaper", search_whitepaper),
            name="search_whitepaper",
            description="在汽车安全白皮书向量库中检索与问题相关的文档片段。",
        ),
        StructuredTool.from_function(
            func=_wrap_tool("get_chunk_by_source", get_chunk_by_source),
            name="get_chunk_by_source",
            description="按 source 文件名和 page 页码精确获取白皮书 chunk。",
        ),
        StructuredTool.from_function(
            func=_wrap_tool("list_collection_stats", list_collection_stats),
            name="list_collection_stats",
            description="列出白皮书集合的文档数量与来源文件列表。",
        ),
    ]


def build_tools(assistant: CarSafetyWhitepaperAssistant, tenant_id: str = "default_tenant") -> list[StructuredTool]:
    if MCP_ENABLED:
        chroma_tools = load_mcp_tools()
        if not chroma_tools:
            logger.warning("MCP enabled but no tools loaded, falling back to local tools")
            chroma_tools = _local_chroma_tools(assistant)
    else:
        chroma_tools = _local_chroma_tools(assistant)

    def get_tenant_quota() -> str:
        """读取当前租户在 gateway 的 RPM/TPM 剩余配额（只读）。"""
        try:
            headers = inject_trace_headers({"X-Tenant-Id": tenant_id})
            response = httpx.get(
                f"{GATEWAY_BASE_URL}/admin/gateway/metrics",
                headers=headers,
                timeout=5.0,
            )
            response.raise_for_status()
            data = response.json()
            tenants = data.get("tenants") or []
            match = next((t for t in tenants if t.get("tenant_id") == tenant_id), None)
            if match:
                return json.dumps(match, ensure_ascii=False)
            return json.dumps({"tenant_id": tenant_id, "message": "未找到租户指标"}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    def reject_or_clarify(reason: str = "low_score") -> str:
        """检索质量不足时返回拒答或澄清提示。"""
        message = CLARIFY_MESSAGE if reason == "low_score" else REJECT_MESSAGE
        return json.dumps({"message": message}, ensure_ascii=False)

    local_only = [
        StructuredTool.from_function(
            func=_wrap_tool("get_tenant_quota", get_tenant_quota),
            name="get_tenant_quota",
            description="查询当前租户在 API 网关的 RPM/TPM 配额与剩余量。",
        ),
        StructuredTool.from_function(
            func=_wrap_tool("reject_or_clarify", reject_or_clarify),
            name="reject_or_clarify",
            description="当检索结果为空或相关度过低时，返回拒答或澄清提示。",
        ),
    ]
    return chroma_tools + local_only


def get_tools_by_name(tools: list[StructuredTool]) -> dict[str, StructuredTool]:
    return {tool.name: tool for tool in tools}
