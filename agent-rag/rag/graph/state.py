"""LangGraph 共享状态定义。

每个节点返回 dict 增量更新，LangGraph 按字段 merge 进全局 state。
带 Annotated reducer 的字段会「累加」而非覆盖（如 messages、tool_calls_log）。
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

# router 节点写入，route_after_router 读取，决定走哪条路径
RouteType = Literal["direct", "rag", "tool", "web"]
# generate 节点按此选择 prompt：本地 / 纯联网 / 本地+联网混合
ContextSourceType = Literal["local", "web", "hybrid"]


class AgentState(TypedDict, total=False):
    # --- LangChain 消息（agent↔tools 循环、最终 AIMessage）---
    # add_messages：新消息 append，不覆盖历史
    messages: Annotated[list[BaseMessage], add_messages]

    # --- 输入与检索 ---
    user_query: str  # 本轮原始问题（不变）
    rewritten_query: str  # rewrite 节点产出，供 retrieve 向量检索
    documents: list[dict[str, Any]]  # retrieve 召回 + rerank 后的 chunk 列表
    context: str  # 格式化后的本地/联网上下文，供 generate 注入 Prompt
    web_context: str  # hybrid 模式下单独的联网段落（与 context 本地段并存）

    # --- 路由与上下文来源 ---
    route: RouteType  # router 写入；条件边据此选下一跳
    context_source: ContextSourceType  # web_search 写入；generate 选哪套 Prompt

    # --- 工具与可观测 ---
    # operator.add：多轮 tool 调用的日志条目累加
    tool_calls_log: Annotated[list[dict[str, Any]], operator.add]
    citations: list[dict[str, Any]]  # 引用来源，done 事件回传前端

    # --- 输出与质量控制 ---
    answer: str  # generate / direct_reply / reject 的最终文本
    reject_message: str  # 检索质量不足时的拒答/澄清文案；也驱动重试与联网分支

    # --- 多轮 Memory（每轮从 MySQL 注入，跨轮不依赖 checkpoint messages）---
    conversation_summary: str
    recent_messages_text: str
    tenant_profile_summary: str

    # --- 运行上下文（每轮 _initial_state 重置检索相关字段，避免脏状态）---
    tenant_id: str
    thread_id: str  # 对应 checkpoint config.configurable.thread_id
    tool_rounds: int  # agent↔tools 循环计数，上限 MAX_TOOL_ROUNDS
    retrieve_retries: int  # retrieve 低分回 rewrite 的重试次数，上限 MAX_RETRIEVE_RETRIES
    run_id: str
    budget_stop_reason: str | None  # tokens | tool_rounds | timeout，超预算强制 generate 时写入
    total_tokens_used: int  # 单请求累计 LLM Token（input+output）
