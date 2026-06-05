from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

from langchain_core.messages import HumanMessage, SystemMessage

from rag.knowledge_bases import get_domain_hint
from rag.metrics import record_llm
from rag.telemetry import span

if TYPE_CHECKING:
    from rag.assistant import CarSafetyWhitepaperAssistant

RouteType = Literal["direct", "rag", "tool", "web"]

_WEB_INTENT_PATTERNS = (
    r"联网",
    r"网上搜索",
    r"网络搜索",
    r"搜索一下",
    r"搜一下",
    r"查一下最新",
    r"最新.*情况",
    r"实时",
    r"上网查",
    r"在线搜索",
    r"互联网",
)

ROUTER_SYSTEM = """你是{domain_hint}助手的意图路由器。
根据用户问题，只输出以下四个标签之一（不要输出其他文字）：
- direct：纯闲聊、问候、感谢、与业务无关的寒暄
- rag：需要查本地知识库文档内容的问题（半导体工艺、器件、测试、标准等专业问题）
- web：需联网获取的实时/公开信息（公司财报、组织架构、行业动态、股价、新闻等），或本地知识库无法覆盖的事实性问题
- tool：明确需要统计、配额、按页码精确查 chunk、或探索集合元数据

用户问题：{query}"""


def detect_web_intent(query: str) -> bool:
    text = (query or "").strip()
    if not text:
        return False
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in _WEB_INTENT_PATTERNS)


def classify_route(assistant: CarSafetyWhitepaperAssistant, query: str) -> RouteType:
    web_by_keyword = detect_web_intent(query)
    if web_by_keyword:
        from rag.debug_trace import debug_log

        debug_log(
            "router.py:classify_route",
            "web route by keyword",
            {"query": query, "web_by_keyword": True},
            "A",
        )
        return "web"

    domain_hint = get_domain_hint(assistant.collection_name)
    with span("rag.llm.invoke", {"rag.operation": "router"}):
        record_llm()
        response = assistant.router_llm.invoke(
            [
                SystemMessage(content="只输出 direct、rag、tool 或 web 其中一个词。"),
                HumanMessage(content=ROUTER_SYSTEM.format(domain_hint=domain_hint, query=query)),
            ]
        )
    text = (response.content or "").strip().lower()
    if "web" in text:
        route: RouteType = "web"
    elif "direct" in text:
        route = "direct"
    elif "tool" in text:
        route = "tool"
    else:
        route = "rag"
    from rag.debug_trace import debug_log

    debug_log(
        "router.py:classify_route",
        "router llm result",
        {"query": query, "llm_text": text, "route": route},
        "B",
    )
    return route
