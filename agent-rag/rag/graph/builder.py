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
)
from rag.graph.state import AgentState

if TYPE_CHECKING:
    from rag.assistant import CarSafetyWhitepaperAssistant

_GRAPH_CACHE: dict[str, object] = {}


def build_graph(assistant: CarSafetyWhitepaperAssistant, tenant_id: str = "default_tenant"):
    cache_key = f"{tenant_id}:{assistant.collection_name}"
    if cache_key in _GRAPH_CACHE:
        return _GRAPH_CACHE[cache_key]

    nodes = make_nodes(assistant, tenant_id)
    graph = StateGraph(AgentState)

    graph.add_node("router", nodes["router"])
    graph.add_node("rewrite", nodes["rewrite"])
    graph.add_node("retrieve", nodes["retrieve"])
    graph.add_node("grade_documents", nodes["grade_documents"])
    graph.add_node("agent", nodes["agent"])
    graph.add_node("tools", nodes["tools"])
    graph.add_node("generate", nodes["generate"])
    graph.add_node("direct_reply", nodes["direct_reply"])
    graph.add_node("reject", nodes["reject"])

    graph.add_edge(START, "router")
    graph.add_conditional_edges("router", route_after_router)
    graph.add_edge("direct_reply", END)
    graph.add_edge("rewrite", "retrieve")
    graph.add_conditional_edges(
        "retrieve",
        route_after_retrieve,
        {"rewrite": "rewrite", "grade_documents": "grade_documents"},
    )
    graph.add_conditional_edges("grade_documents", route_after_grade)
    graph.add_edge("reject", END)
    graph.add_conditional_edges("agent", route_after_agent)
    graph.add_conditional_edges("tools", route_after_tools)
    graph.add_edge("generate", END)

    checkpointer = get_checkpointer()
    if checkpointer is None:
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()

    compiled = graph.compile(checkpointer=checkpointer)
    _GRAPH_CACHE[cache_key] = compiled
    return compiled
