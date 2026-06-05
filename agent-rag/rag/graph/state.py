from __future__ import annotations

import operator
from typing import Annotated, Any, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

RouteType = Literal["direct", "rag", "tool", "web"]
ContextSourceType = Literal["local", "web", "hybrid"]


class AgentState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    user_query: str
    rewritten_query: str
    documents: list[dict[str, Any]]
    context: str
    web_context: str
    route: RouteType
    tool_calls_log: Annotated[list[dict[str, Any]], operator.add]
    citations: list[dict[str, Any]]
    context_source: ContextSourceType
    answer: str
    reject_message: str
    tenant_id: str
    thread_id: str
    tool_rounds: int
    retrieve_retries: int
    run_id: str
