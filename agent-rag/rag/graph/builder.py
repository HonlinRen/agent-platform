"""LangGraph StateGraph 拓扑定义与编译。

图结构概览（节点 = 干活，条件边 route_after_* = 读 state 选下一跳）::

    START → router
      ├─ direct  → direct_reply → END
      ├─ web     → web_search → generate/reject
      ├─ tool    → agent ↔ tools（循环）→ generate → END
      └─ rag     → rewrite → retrieve ↔ rewrite（低分重试）
                        → grade_documents → generate/agent/web_search/reject

LangChain 能力（LLM/Prompt/Tool）在 nodes.py 各节点内部调用，本文件只负责连线。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

from rag.checkpoint import get_checkpointer
from rag.graph.nodes import (
    make_nodes,
    route_after_agent,
    route_after_grade,
    route_after_retrieve,
    route_after_router,
    route_after_tools,
    route_after_web_search,
)
from rag.graph.state import AgentState

if TYPE_CHECKING:
    from rag.assistant import CarSafetyWhitepaperAssistant

# 按租户 + 知识库缓存已编译图，避免每次请求重复 bind_tools / add_node
_GRAPH_CACHE: dict[str, object] = {}


def build_graph(assistant: CarSafetyWhitepaperAssistant, tenant_id: str = "default_tenant"):
    cache_key = f"{tenant_id}:{assistant.collection_name}"
    if cache_key in _GRAPH_CACHE:
        return _GRAPH_CACHE[cache_key]

    nodes = make_nodes(assistant, tenant_id)
    graph = StateGraph(AgentState)

    # --- 注册节点（函数签名均为 state -> dict 增量更新）---
    graph.add_node("router", nodes["router"])  # 意图分流：direct/rag/tool/web
    graph.add_node("rewrite", nodes["rewrite"])  # 多轮指代消解，改写检索 query
    graph.add_node("retrieve", nodes["retrieve"])  # Chroma 召回 + Rerank + 拼 context
    graph.add_node("grade_documents", nodes["grade_documents"])  # 二次质量门控，决定拒答/联网/生成
    graph.add_node("web_search", nodes["web_search"])  # Tavily 联网（纯 web 或本地不足时补充）
    graph.add_node("agent", nodes["agent"])  # bind_tools 的 LLM，决定是否发起 tool_calls
    graph.add_node("tools", nodes["tools"])  # LangGraph ToolNode：执行 StructuredTool
    graph.add_node("generate", nodes["generate"])  # prompt|llm 最终作答（local/web/hybrid）
    graph.add_node("direct_reply", nodes["direct_reply"])  # 闲聊捷径，零检索
    graph.add_node("reject", nodes["reject"])  # 检索/联网均失败时的拒答

    # --- 固定边 ---
    graph.add_edge(START, "router")
    graph.add_edge("direct_reply", END)
    graph.add_edge("rewrite", "retrieve")  # rag 路径：先改写再检索
    graph.add_edge("reject", END)
    graph.add_edge("generate", END)

    # --- 条件边（读 state，不写 state）---
    graph.add_conditional_edges("router", route_after_router)  # 四路径分流入口
    graph.add_conditional_edges(
        "retrieve",
        route_after_retrieve,
        {"rewrite": "rewrite", "grade_documents": "grade_documents"},  # 低分重试环
    )
    graph.add_conditional_edges("grade_documents", route_after_grade)  # 拒答 / 联网补充 / 生成 / agent
    graph.add_conditional_edges("web_search", route_after_web_search)
    graph.add_conditional_edges("agent", route_after_agent)  # 有 tool_calls → tools，否则 → generate
    graph.add_conditional_edges("tools", route_after_tools)  # 未超轮次 → 回到 agent

    # checkpoint：Redis 优先，失败用 MemorySaver；thread_id 在 streaming 层传入 config
    checkpointer = get_checkpointer()
    if checkpointer is None:
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()

    compiled = graph.compile(checkpointer=checkpointer)
    _GRAPH_CACHE[cache_key] = compiled
    return compiled
