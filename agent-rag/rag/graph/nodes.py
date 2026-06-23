"""LangGraph 节点实现与条件边路由函数。

职责划分：
- **节点**（``make_nodes`` 内闭包）：调用 LangChain（LLM / Prompt / Tool），写 state 增量
- **条件边**（``route_after_*``）：只读 state，返回下一节点名，不调用 LLM

LangChain 与 LangGraph 的配合示例：
- router/rewrite/generate → ``llm.invoke`` 或 ``prompt | llm``
- agent → ``chat_llm.bind_tools`` + ``ToolNode``
- retrieve → assistant 手写检索（Embedding + Chroma + Rerank），非 LangChain Retriever
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.prompts import PromptTemplate
from langgraph.prebuilt import ToolNode

from rag.assistant import MAX_RETRIEVE_RETRIES, MAX_TOOL_ROUNDS, llm_output_to_text
from rag.llm_timing import timed_llm_invoke
from rag.request_budget import (
    get_budget_stop_reason,
    get_request_budget,
    get_total_tokens_used,
    should_force_generate,
)
from rag.reject import needs_web_supplement, reject_reason
from rag.telemetry import record_reject, span
from rag.router import classify_route
from rag.graph.state import AgentState
from rag.tools.registry import build_tools
from rag.tools.tavily_search import ensure_web_disclaimer, is_tavily_enabled, search_web

if TYPE_CHECKING:
    from rag.assistant import CarSafetyWhitepaperAssistant

_BUDGET_GENERATE_NOTE = (
    "\n\n【预算提示】本次请求已达 Token/工具轮次/运行时间上限，"
    "请基于已有上下文给出尽量简短的回答，并说明已提前结束检索或工具调用。"
)


def _budget_generate_note(state: AgentState) -> str:
    thread_id = state.get("thread_id")
    if state.get("budget_stop_reason") or get_budget_stop_reason(thread_id):
        return _BUDGET_GENERATE_NOTE
    return ""


def _with_budget_note(prompt: PromptTemplate, note: str) -> PromptTemplate:
    if not note:
        return prompt
    return PromptTemplate(
        input_variables=prompt.input_variables,
        template=prompt.template + note,
    )


def _budget_state_patch(state: AgentState, patch: dict[str, Any]) -> dict[str, Any]:
    thread_id = state.get("thread_id")
    reason = state.get("budget_stop_reason") or get_budget_stop_reason(thread_id)
    if reason:
        patch = {**patch, "budget_stop_reason": reason}
    patch["total_tokens_used"] = get_total_tokens_used(thread_id)
    return patch


def make_nodes(assistant: CarSafetyWhitepaperAssistant, tenant_id: str):
    """为指定租户/知识库构建全部图节点闭包（含 tool 路径专用依赖）。"""
    tools = build_tools(assistant, tenant_id=tenant_id)
    tool_node = ToolNode(tools)  # LangGraph 预置：解析 AIMessage.tool_calls 并执行 StructuredTool
    llm_with_tools = assistant.chat_llm.bind_tools(tools)  # tool 路径：LLM 可返回 tool_calls

    def router_node(state: AgentState) -> dict[str, Any]:
        # Router 节点只负责把问题分到 direct/rag/tool/web 路径，后续边再决定下一个节点。
        route = classify_route(assistant, state["user_query"], thread_id=state["thread_id"])
        return {"route": route}

    def rewrite_node(state: AgentState) -> dict[str, Any]:
        rewritten = assistant.rewrite_query_with_memory(
            state["user_query"],
            tenant_profile_summary=state.get("tenant_profile_summary") or "",
            conversation_summary=state.get("conversation_summary") or "",
            recent_messages_text=state.get("recent_messages_text") or "无历史对话",
            thread_id=state["thread_id"],
        )
        return {"rewritten_query": rewritten}

    def retrieve_node(state: AgentState) -> dict[str, Any]:
        # Retrieve 节点在 Router 判定需要本地知识库后取证：用改写后的 query 检索、排序并准备上下文。
        query = state.get("rewritten_query") or state["user_query"]
        ranked = assistant.retrieve_and_rank(query, thread_id=state["thread_id"])
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
        # retrieve 之后的二次门控：即使 retrieve 未当场拒答，也在这里统一决定
        # 走 generate / web_search（联网补充）/ reject / agent（tool 路径转交）。
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
        # 两种模式：
        # 1) route=web：纯联网，context_source=web
        # 2) grade 后本地分低：在已有 local context 上补充，context_source=hybrid
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
        # tool 路径：LLM 自主决定何时调 search_whitepaper / get_tenant_quota 等。
        # 返回的 AIMessage 可能带 tool_calls，由 route_after_agent 决定是否进 tools 节点。
        thread_id = state["thread_id"]
        budget = get_request_budget(thread_id)
        if budget is not None:
            budget.check_tool_rounds(state.get("tool_rounds", 0))
        if should_force_generate(thread_id):
            return _budget_state_patch(state, {"messages": [AIMessage(content="")]})

        memory_suffix = ""
        recent_text = (state.get("recent_messages_text") or "").strip()
        if recent_text and recent_text != "无历史对话":
            memory_suffix = f"\n\n【最近对话】\n{recent_text}"
        summary = (state.get("conversation_summary") or "").strip()
        if summary:
            memory_suffix = f"\n\n【会话摘要】\n{summary}{memory_suffix}"
        profile = (state.get("tenant_profile_summary") or "").strip()
        if profile:
            memory_suffix = f"\n\n【租户背景】\n{profile}{memory_suffix}"

        system = SystemMessage(
            content=(
                assistant.system_prompt
                + "\n\n你可以调用工具检索知识库。"
                "检索完成后请基于工具结果回答，并标注来源。"
                + memory_suffix
            )
        )
        user = HumanMessage(content=state["user_query"])
        prior = state.get("messages") or []
        with span("rag.llm.invoke", {"rag.operation": "agent"}):
            response = timed_llm_invoke(
                "agent",
                lambda: llm_with_tools.invoke([system, *prior, user]),
                fallback_text=state["user_query"],
                thread_id=thread_id,
            )
        return _budget_state_patch(state, {"messages": [response]})

    def tools_wrapper(state: AgentState) -> dict[str, Any]:
        # 包装 ToolNode：执行工具的同时记录 tool_calls_log，供 streaming 推 SSE tool_call 事件。
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
        new_tool_rounds = state.get("tool_rounds", 0) + 1
        thread_id = state["thread_id"]
        budget = get_request_budget(thread_id)
        if budget is not None:
            budget.check_tool_rounds(new_tool_rounds)
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
        patch = {**result, "tool_calls_log": log_entries, "tool_rounds": new_tool_rounds}
        return _budget_state_patch(state, patch)

    def generate_node(state: AgentState) -> dict[str, Any]:
        thread_id = state["thread_id"]
        context = state.get("context") or ""
        if not context and state.get("messages"):
            for msg in reversed(state["messages"]):
                if isinstance(msg, ToolMessage):
                    context = str(msg.content)
                    break

        context_source = state.get("context_source", "local")
        memory_kwargs = {
            "tenant_profile_summary": state.get("tenant_profile_summary") or "",
            "conversation_summary": state.get("conversation_summary") or "",
            "recent_messages_text": state.get("recent_messages_text") or "无历史对话",
        }
        budget_note = _budget_generate_note(state)
        with span("rag.llm.invoke", {"rag.operation": "generate"}):
            if context_source == "hybrid":
                chain = _with_budget_note(assistant.hybrid_prompt, budget_note) | assistant.llm
                inputs = assistant.hybrid_prompt_inputs(
                    state["user_query"],
                    context,
                    state.get("web_context") or "",
                    **memory_kwargs,
                )
                response = timed_llm_invoke(
                    "generate",
                    lambda: chain.invoke(inputs),
                    fallback_text=state["user_query"],
                    thread_id=thread_id,
                )
            elif context_source == "web":
                chain = _with_budget_note(assistant.web_prompt, budget_note) | assistant.llm
                inputs = assistant.generate_prompt_inputs(
                    state["user_query"],
                    context,
                    **memory_kwargs,
                )
                response = timed_llm_invoke(
                    "generate",
                    lambda: chain.invoke(inputs),
                    fallback_text=state["user_query"],
                    thread_id=thread_id,
                )
            else:
                chain = _with_budget_note(assistant.prompt, budget_note) | assistant.llm
                inputs = assistant.generate_prompt_inputs(
                    state["user_query"],
                    context,
                    **memory_kwargs,
                )
                response = timed_llm_invoke(
                    "generate",
                    lambda: chain.invoke(inputs),
                    fallback_text=state["user_query"],
                    thread_id=thread_id,
                )
        answer = llm_output_to_text(response)
        if context_source in {"web", "hybrid"}:
            answer = ensure_web_disclaimer(answer)
        return _budget_state_patch(
            state,
            {"answer": answer, "messages": [AIMessage(content=answer)]},
        )

    def direct_reply_node(state: AgentState) -> dict[str, Any]:
        memory_suffix = ""
        recent_text = (state.get("recent_messages_text") or "").strip()
        if recent_text and recent_text != "无历史对话":
            lines = recent_text.splitlines()
            recent_snippet = "\n".join(lines[-4:])
            memory_suffix = f"\n\n【最近对话】\n{recent_snippet}"
        with span("rag.llm.invoke", {"rag.operation": "direct_reply"}):
            response = timed_llm_invoke(
                "direct_reply",
                lambda: assistant.chat_llm.invoke(
                    [
                        SystemMessage(content=assistant.direct_system_prompt + memory_suffix),
                        HumanMessage(content=state["user_query"]),
                    ]
                ),
                fallback_text=state["user_query"],
                thread_id=state["thread_id"],
            )
        answer = (response.content or "").strip()
        return _budget_state_patch(
            state,
            {"answer": answer, "route": "direct", "messages": [AIMessage(content=answer)]},
        )

    def reject_node(state: AgentState) -> dict[str, Any]:
        # 本地检索失败且无法联网（或未配置 Tavily）时的终态拒答。
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


# ---------------------------------------------------------------------------
# 条件边：只读 state["route"] 等字段，返回下一节点名（不写 state、不调 LLM）
# ---------------------------------------------------------------------------


def route_after_router(state: AgentState) -> Literal["direct_reply", "rewrite", "agent", "web_search", "generate"]:
    """router 节点之后：四路径分流。rag 默认走 rewrite（不直接 retrieve，需先改写 query）。"""
    if should_force_generate(state.get("thread_id")):
        return "generate"
    route = state.get("route", "rag")
    if route == "direct":
        return "direct_reply"
    if route == "web":
        return "web_search"
    if route == "tool":
        return "agent"
    return "rewrite"


def route_after_grade(state: AgentState) -> Literal["reject", "generate", "agent", "web_search"]:
    """grade 之后：拒答→联网兜底；中等相关度→联网补充；tool 路径→agent；否则 generate。"""
    if should_force_generate(state.get("thread_id")):
        return "generate"
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
    """联网后：有可用上下文则 generate，否则 reject（纯 web 失败或 supplement 也失败）。"""
    from rag.debug_trace import debug_log

    if should_force_generate(state.get("thread_id")):
        return "generate"
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
    """agent 输出含 tool_calls 且未超轮次 → tools；否则认为已可作答 → generate。"""
    if should_force_generate(state.get("thread_id")):
        return "generate"
    messages = state.get("messages") or []
    if not messages:
        return "generate"
    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", None) or []
    if tool_calls and state.get("tool_rounds", 0) < MAX_TOOL_ROUNDS:
        return "tools"
    return "generate"


def route_after_tools(state: AgentState) -> Literal["agent", "generate"]:
    """工具执行完：未达 MAX_TOOL_ROUNDS 则回到 agent 继续推理，否则强制 generate。"""
    if should_force_generate(state.get("thread_id")) or state.get("tool_rounds", 0) >= MAX_TOOL_ROUNDS:
        return "generate"
    return "agent"


def route_after_retrieve(state: AgentState) -> Literal["grade_documents", "rewrite"]:
    """检索低分且未超重试 → 回 rewrite 换 query 再检；否则进入 grade_documents。"""
    if should_force_generate(state.get("thread_id")):
        return "grade_documents"
    retries = state.get("retrieve_retries", 0)
    if state.get("reject_message") and retries <= MAX_RETRIEVE_RETRIES:
        return "rewrite"
    return "grade_documents"
