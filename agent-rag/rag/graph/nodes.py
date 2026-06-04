from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import ToolNode

from rag.assistant import MAX_RETRIEVE_RETRIES, MAX_TOOL_ROUNDS, llm_output_to_text
from rag.metrics import record_llm
from rag.reject import reject_reason
from rag.telemetry import record_reject, span
from rag.router import classify_route
from rag.graph.state import AgentState
from rag.tools.registry import build_tools

if TYPE_CHECKING:
    from rag.assistant import CarSafetyWhitepaperAssistant


def make_nodes(assistant: CarSafetyWhitepaperAssistant, tenant_id: str):
    tools = build_tools(assistant, tenant_id=tenant_id)
    tool_node = ToolNode(tools)
    llm_with_tools = assistant.chat_llm.bind_tools(tools)

    def router_node(state: AgentState) -> dict[str, Any]:
        route = classify_route(assistant, state["user_query"])
        return {"route": route}

    def rewrite_node(state: AgentState) -> dict[str, Any]:
        from rag.assistant import rebuild_history

        history_items = []
        for msg in state.get("messages", []):
            if isinstance(msg, HumanMessage):
                history_items.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                history_items.append({"role": "assistant", "content": msg.content})
        history = rebuild_history(history_items)
        rewritten = assistant.rewrite_query(state["user_query"], history)
        return {"rewritten_query": rewritten}

    def retrieve_node(state: AgentState) -> dict[str, Any]:
        query = state.get("rewritten_query") or state["user_query"]
        ranked = assistant.retrieve_and_rank(query)
        reject, msg = assistant.check_retrieval_quality(ranked)
        retries = state.get("retrieve_retries", 0)
        if reject:
            return {
                "documents": ranked,
                "reject_message": msg,
                "context": "",
                "retrieve_retries": retries + 1,
            }
        context = assistant.format_context(ranked)
        citations = assistant.extract_citations(ranked)
        return {
            "documents": ranked,
            "context": context,
            "citations": citations,
            "reject_message": "",
        }

    def grade_documents_node(state: AgentState) -> dict[str, Any]:
        ranked = state.get("documents") or []
        reject, msg = assistant.check_retrieval_quality(ranked)
        if reject:
            return {"reject_message": msg}
        return {"reject_message": ""}

    def agent_node(state: AgentState) -> dict[str, Any]:
        system = SystemMessage(
            content=(
                assistant.system_prompt
                + "\n\n你可以调用工具检索知识库。"
                "检索完成后请基于工具结果回答，并标注来源。"
            )
        )
        user = HumanMessage(content=state["user_query"])
        prior = state.get("messages") or []
        with span("rag.llm.invoke", {"rag.operation": "agent"}):
            record_llm()
            response = llm_with_tools.invoke([system, *prior, user])
        return {"messages": [response], "tool_rounds": state.get("tool_rounds", 0) + 1}

    def tools_wrapper(state: AgentState) -> dict[str, Any]:
        log_entries: list[dict[str, Any]] = []
        if state.get("messages"):
            last_ai = state["messages"][-1]
            if hasattr(last_ai, "tool_calls") and last_ai.tool_calls:
                for tc in last_ai.tool_calls:
                    log_entries.append(
                        {
                            "name": tc.get("name"),
                            "args": tc.get("args"),
                            "status": "start",
                        }
                    )
        result = tool_node.invoke(state)
        if state.get("messages"):
            last_ai = state["messages"][-1]
            if hasattr(last_ai, "tool_calls") and last_ai.tool_calls:
                last_message = result.get("messages", [])[-1] if result.get("messages") else None
                tc = last_ai.tool_calls[0]
                log_entries.append(
                    {
                        "name": tc.get("name"),
                        "args": tc.get("args"),
                        "status": "end",
                        "result": getattr(last_message, "content", None) if last_message else None,
                    }
                )
        return {**result, "tool_calls_log": log_entries}

    def generate_node(state: AgentState) -> dict[str, Any]:
        from rag.assistant import rebuild_history

        history_items = []
        for msg in state.get("messages", []):
            if isinstance(msg, HumanMessage):
                history_items.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
                history_items.append({"role": "assistant", "content": msg.content})
        history = rebuild_history(history_items)
        context = state.get("context") or ""
        if not context and state.get("messages"):
            for msg in reversed(state["messages"]):
                if isinstance(msg, ToolMessage):
                    context = str(msg.content)
                    break

        chain = assistant.prompt | assistant.llm
        with span("rag.llm.invoke", {"rag.operation": "generate"}):
            record_llm()
            response = chain.invoke(
                {
                    "human_input": state["user_query"],
                    "context": context,
                    "chat_history": assistant.get_chat_history_text(history),
                }
            )
        answer = llm_output_to_text(response)
        return {"answer": answer, "messages": [AIMessage(content=answer)]}

    def direct_reply_node(state: AgentState) -> dict[str, Any]:
        with span("rag.llm.invoke", {"rag.operation": "direct_reply"}):
            record_llm()
            response = assistant.chat_llm.invoke(
                [
                    SystemMessage(content=assistant.direct_system_prompt),
                    HumanMessage(content=state["user_query"]),
                ]
            )
        answer = (response.content or "").strip()
        return {"answer": answer, "route": "direct", "messages": [AIMessage(content=answer)]}

    def reject_node(state: AgentState) -> dict[str, Any]:
        msg = state.get("reject_message") or "知识库上下文中未找到充分依据。"
        ranked = state.get("documents") or []
        record_reject(reject_reason(ranked), tenant_id)
        return {"answer": msg, "messages": [AIMessage(content=msg)]}

    return {
        "router": router_node,
        "rewrite": rewrite_node,
        "retrieve": retrieve_node,
        "grade_documents": grade_documents_node,
        "agent": agent_node,
        "tools": tools_wrapper,
        "generate": generate_node,
        "direct_reply": direct_reply_node,
        "reject": reject_node,
        "tool_node": tool_node,
        "tools_list": tools,
    }


def route_after_router(state: AgentState) -> Literal["direct_reply", "rewrite", "agent"]:
    route = state.get("route", "rag")
    if route == "direct":
        return "direct_reply"
    if route == "tool":
        return "agent"
    return "rewrite"


def route_after_grade(state: AgentState) -> Literal["reject", "generate", "agent"]:
    if state.get("reject_message"):
        return "reject"
    route = state.get("route", "rag")
    if route == "tool":
        return "agent"
    return "generate"


def route_after_agent(state: AgentState) -> Literal["tools", "generate"]:
    messages = state.get("messages") or []
    if not messages:
        return "generate"
    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", None) or []
    if tool_calls and state.get("tool_rounds", 0) <= MAX_TOOL_ROUNDS:
        return "tools"
    return "generate"


def route_after_tools(state: AgentState) -> Literal["agent", "generate"]:
    if state.get("tool_rounds", 0) >= MAX_TOOL_ROUNDS:
        return "generate"
    return "agent"


def route_after_retrieve(state: AgentState) -> Literal["grade_documents", "rewrite"]:
    retries = state.get("retrieve_retries", 0)
    if state.get("reject_message") and retries <= MAX_RETRIEVE_RETRIES:
        return "rewrite"
    return "grade_documents"
