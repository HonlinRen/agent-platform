from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from langchain_core.messages import HumanMessage, SystemMessage

from rag.metrics import record_llm
from rag.telemetry import span

if TYPE_CHECKING:
    from rag.assistant import CarSafetyWhitepaperAssistant

RouteType = Literal["direct", "rag", "tool"]

ROUTER_SYSTEM = """你是汽车安全白皮书助手的意图路由器。
根据用户问题，只输出以下三个标签之一（不要输出其他文字）：
- direct：闲聊、问候、与白皮书无关的一般问题
- rag：需要查白皮书文档内容的问题
- tool：明确需要统计、配额、按页码精确查 chunk、或探索集合元数据

用户问题：{query}"""


def classify_route(assistant: CarSafetyWhitepaperAssistant, query: str) -> RouteType:
    with span("rag.llm.invoke", {"rag.operation": "router"}):
        record_llm()
        response = assistant.router_llm.invoke(
            [
                SystemMessage(content="只输出 direct、rag 或 tool 其中一个词。"),
                HumanMessage(content=ROUTER_SYSTEM.format(query=query)),
            ]
        )
    text = (response.content or "").strip().lower()
    if "direct" in text:
        return "direct"
    if "tool" in text:
        return "tool"
    return "rag"
