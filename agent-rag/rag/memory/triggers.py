from __future__ import annotations

from rag.memory.tokens import (
    estimate_messages_tokens,
    get_summary_trigger_rounds,
    get_summary_trigger_tokens,
)


def should_update_summary(message_count: int, unsummarized_messages: list[dict[str, str]]) -> bool:
    rounds = message_count // 2
    if rounds > get_summary_trigger_rounds():
        return True
    return estimate_messages_tokens(unsummarized_messages) > get_summary_trigger_tokens()
