from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from rag.memory.formatting import build_memory_context, memory_context_from_fallback
from rag.memory.tokens import get_recent_max_tokens, estimate_messages_tokens
from rag.memory.types import MemoryContext, get_window_size

if TYPE_CHECKING:
    from db.repository import ConversationRepository

logger = logging.getLogger(__name__)


def _trim_recent_by_tokens(messages: list[dict[str, str]], max_tokens: int) -> list[dict[str, str]]:
    if max_tokens <= 0 or not messages:
        return messages
    trimmed: list[dict[str, str]] = []
    total = 0
    for item in reversed(messages):
        item_tokens = estimate_messages_tokens([item])
        if trimmed and total + item_tokens > max_tokens:
            break
        trimmed.insert(0, item)
        total += item_tokens
    return trimmed


class MemoryManager:
    @staticmethod
    def load(
        repo: ConversationRepository,
        tenant_id: str,
        thread_id: str,
        *,
        fallback_messages: list[dict[str, str]] | None = None,
    ) -> MemoryContext:
        window_size = get_window_size()
        limit = window_size * 2
        data = repo.load_memory_context(tenant_id, thread_id, limit=limit)

        if not data.recent_messages and fallback_messages:
            ctx = memory_context_from_fallback(fallback_messages)
            max_tokens = get_recent_max_tokens()
            if max_tokens > 0:
                trimmed = _trim_recent_by_tokens(ctx.recent_messages, max_tokens)
                from rag.memory.formatting import format_messages_text

                ctx.recent_messages = trimmed
                ctx.recent_messages_text = format_messages_text(trimmed)
            return ctx

        ctx = build_memory_context(data)
        max_tokens = get_recent_max_tokens()
        if max_tokens > 0 and ctx.recent_messages:
            trimmed = _trim_recent_by_tokens(ctx.recent_messages, max_tokens)
            from rag.memory.formatting import format_messages_text

            ctx.recent_messages = trimmed
            ctx.recent_messages_text = format_messages_text(trimmed)
        return ctx

    @staticmethod
    def load_best_effort(
        tenant_id: str,
        thread_id: str,
        *,
        fallback_messages: list[dict[str, str]] | None = None,
    ) -> MemoryContext:
        try:
            from db.repository import ConversationRepository
            from db.session import get_db

            with get_db() as session:
                return MemoryManager.load(
                    ConversationRepository(session),
                    tenant_id,
                    thread_id,
                    fallback_messages=fallback_messages,
                )
        except Exception:
            logger.exception("Failed to load memory context from MySQL, using fallback")
            return memory_context_from_fallback(fallback_messages or [])
