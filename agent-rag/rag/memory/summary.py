from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langchain_core.prompts import PromptTemplate

from rag.memory.formatting import format_messages_text
from rag.memory.tokens import get_summary_max_chars
from rag.memory.triggers import should_update_summary
from rag.memory.types import get_window_size
from rag.llm_timing import timed_llm_invoke
from rag.telemetry import span

if TYPE_CHECKING:
    from rag.assistant import CarSafetyWhitepaperAssistant

logger = logging.getLogger(__name__)

SUMMARY_PROMPT = PromptTemplate(
    input_variables=["old_summary", "new_messages", "max_chars"],
    template=(
        "请更新企业知识库问答会话摘要。\n\n"
        "要求：\n"
        "1. 保留用户目标、业务背景、关键约束、已确认结论\n"
        "2. 删除寒暄、重复内容和无效尝试\n"
        "3. 摘要控制在 {max_chars} 字以内\n"
        "4. 只输出摘要正文，不要标题或解释\n\n"
        "【旧摘要】\n{old_summary}\n\n"
        "【新增对话】\n{new_messages}\n\n"
        "更新后的摘要："
    ),
)


def _messages_to_dicts(rows) -> list[dict[str, str]]:
    return [{"role": row.role, "content": row.content} for row in rows]


def update_conversation_summary(
    assistant: CarSafetyWhitepaperAssistant,
    tenant_id: str,
    thread_id: str,
) -> bool:
    from db.repository import ConversationRepository
    from db.session import get_db

    window_size = get_window_size()
    with get_db() as session:
        repo = ConversationRepository(session)
        conversation = repo.get_conversation(tenant_id, thread_id)
        if conversation is None:
            return False

        max_seq = repo.get_max_message_sequence(tenant_id, thread_id)
        keep_from = max(0, max_seq - window_size * 2)
        after_seq = conversation.summary_up_to_sequence or 0
        if keep_from <= after_seq:
            return False

        unsummarized_rows = repo.get_messages_for_summary(
            tenant_id,
            thread_id,
            after_sequence=after_seq,
            before_sequence=keep_from,
        )
        unsummarized = _messages_to_dicts(unsummarized_rows)
        if not unsummarized:
            return False
        if not should_update_summary(conversation.message_count, unsummarized):
            return False

        old_summary = (conversation.summary or "").strip() or "无"
        new_messages_text = format_messages_text(unsummarized)
        chain = SUMMARY_PROMPT | assistant.router_llm
        with span("rag.llm.invoke", {"rag.operation": "summary_update"}):
            result = timed_llm_invoke(
                "summary_update",
                lambda: chain.invoke(
                    {
                        "old_summary": old_summary,
                        "new_messages": new_messages_text,
                        "max_chars": get_summary_max_chars(),
                    }
                ),
                phase="post_turn",
            )
        from rag.assistant import llm_output_to_text

        summary_text = llm_output_to_text(result)
        if not summary_text:
            return False
        if len(summary_text) > get_summary_max_chars():
            summary_text = summary_text[: get_summary_max_chars()].rstrip()

        repo.update_conversation_summary(tenant_id, thread_id, summary_text, keep_from)
        logger.info(
            "Updated conversation summary tenant=%s thread=%s up_to=%d",
            tenant_id,
            thread_id,
            keep_from,
        )
        return True


def maybe_update_summary_best_effort(
    assistant: CarSafetyWhitepaperAssistant,
    tenant_id: str,
    thread_id: str,
) -> None:
    try:
        update_conversation_summary(assistant, tenant_id, thread_id)
    except Exception:
        logger.exception("Failed to update conversation summary")
