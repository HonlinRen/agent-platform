from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import ToolNode

from rag.assistant import MAX_RETRIEVE_RETRIES, MAX_TOOL_ROUNDS, llm_output_to_text
from rag.metrics import record_llm
from rag.reject import needs_web_supplement, reject_reason
from rag.telemetry import record_reject, span
from rag.router import classify_route
from rag.graph.state import AgentState
from rag.tools.registry import build_tools
from rag.tools.tavily_search import ensure_web_disclaimer, is_tavily_enabled, search_web

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

    def _web_search_failure(state: AgentState, result: dict[str, Any], is_supplement: bool) -> dict[str, Any]:
        from rag.debug_trace import debug_log

        error = str(result.get("error") or "")
        route = state.get("route", "rag")
        debug_log(
            "nodes.py:web_search_node",
            "web search failed",
            {"route": route, "error": error, "is_supplement": is_supplement, "status": result.get("status")},
            "C",
        )
        if is_supplement:
            return {"context_source": "local"}
        if error == "tavily_disabled":
            return {
                "reject_message": "联网搜索功能未配置，请在服务端环境变量中设置 TAVILY_KEY 后重启服务。",
                "context_source": "local",
            }
        if "No module named 'tavily'" in error:
            return {
                "reject_message": "联网搜索依赖未安装，请在 agent-rag 虚拟环境中执行：pip install tavily-python",
                "context_source": "local",
            }
        if result.get("status") == "empty":
            return {
                "reject_message": "联网搜索未找到相关内容，请换一种问法或缩小范围后重试。",
                "context_source": "local",
            }
        return {
            "reject_message": "联网搜索暂时不可用，请稍后重试。",
            "context_source": "local",
        }

    def web_search_node(state: AgentState) -> dict[str, Any]:
        from rag.debug_trace import debug_log

        query = state.get("rewritten_query") or state["user_query"]
        local_context = (state.get("context") or "").strip()
        is_supplement = bool(local_context) and state.get("route") != "web"
        debug_log(
            "nodes.py:web_search_node",
            "web search start",
            {
                "route": state.get("route"),
                "query": query,
                "is_supplement": is_supplement,
                "tavily_enabled": is_tavily_enabled(),
            },
            "A",
        )
        result = search_web(query)
        if result.get("status") == "ok":
            web_ctx = result.get("context") or ""
            web_citations = result.get("citations") or []
            if is_supplement:
                existing_citations = state.get("citations") or []
                return {
                    "web_context": web_ctx,
                    "citations": existing_citations + web_citations,
                    "context_source": "hybrid",
                    "reject_message": "",
                }
            return {
                "context": web_ctx,
                "citations": web_citations,
                "context_source": "web",
                "reject_message": "",
            }
        return _web_search_failure(state, result, is_supplement)

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

        context_source = state.get("context_source", "local")
        chat_history = assistant.get_chat_history_text(history)
        with span("rag.llm.invoke", {"rag.operation": "generate"}):
            record_llm()
            if context_source == "hybrid":
                chain = assistant.hybrid_prompt | assistant.llm
                response = chain.invoke(
                    {
                        "human_input": state["user_query"],
                        "local_context": context,
                        "web_context": state.get("web_context") or "",
                        "chat_history": chat_history,
                    }
                )
            elif context_source == "web":
                chain = assistant.web_prompt | assistant.llm
                response = chain.invoke(
                    {
                        "human_input": state["user_query"],
                        "context": context,
                        "chat_history": chat_history,
                    }
                )
            else:
                chain = assistant.prompt | assistant.llm
                response = chain.invoke(
                    {
                        "human_input": state["user_query"],
                        "context": context,
                        "chat_history": chat_history,
                    }
                )
        answer = llm_output_to_text(response)
        if context_source in {"web", "hybrid"}:
            answer = ensure_web_disclaimer(answer)
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
        msg = state.get("reject_message") or "本地知识库上下文中未找到充分依据。"
        ranked = state.get("documents") or []
        record_reject(reject_reason(ranked), tenant_id)
        return {"answer": msg, "messages": [AIMessage(content=msg)]}

    return {
        "router": router_node,
        "rewrite": rewrite_node,
        "retrieve": retrieve_node,
        "grade_documents": grade_documents_node,
        "web_search": web_search_node,
        "agent": agent_node,
        "tools": tools_wrapper,
        "generate": generate_node,
        "direct_reply": direct_reply_node,
        "reject": reject_node,
        "tool_node": tool_node,
        "tools_list": tools,
    }


def route_after_router(state: AgentState) -> Literal["direct_reply", "rewrite", "agent", "web_search"]:
    route = state.get("route", "rag")
    if route == "direct":
        return "direct_reply"
    if route == "web":
        return "web_search"
    if route == "tool":
        return "agent"
    return "rewrite"


def route_after_grade(state: AgentState) -> Literal["reject", "generate", "agent", "web_search"]:
    if state.get("reject_message"):
        if is_tavily_enabled():
            return "web_search"
        return "reject"
    if is_tavily_enabled() and needs_web_supplement(state.get("documents") or []):
        return "web_search"
    route = state.get("route", "rag")
    if route == "tool":
        return "agent"
    return "generate"


def route_after_web_search(state: AgentState) -> Literal["generate", "reject"]:
    from rag.debug_trace import debug_log

    context_source = state.get("context_source", "local")
    decision = "reject"
    if context_source == "hybrid" and state.get("web_context"):
        decision = "generate"
    elif context_source == "web" and state.get("context"):
        decision = "generate"
    elif context_source == "local" and state.get("context"):
        decision = "generate"
    debug_log(
        "nodes.py:route_after_web_search",
        "route decision",
        {
            "decision": decision,
            "context_source": context_source,
            "has_context": bool(state.get("context")),
            "has_web_context": bool(state.get("web_context")),
            "reject_message": state.get("reject_message"),
            "route": state.get("route"),
        },
        "D",
    )
    return decision


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
