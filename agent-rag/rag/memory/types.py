from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class MemoryContext:
    recent_messages: list[dict[str, str]] = field(default_factory=list)
    recent_messages_text: str = "无历史对话"
    conversation_summary: str = ""
    tenant_profile_summary: str = ""
    window_size: int = 5

    def to_metadata(self) -> dict:
        return {
            "window_size": self.window_size,
            "recent_message_count": len(self.recent_messages),
            "has_summary": bool(self.conversation_summary),
            "has_tenant_profile": bool(self.tenant_profile_summary),
        }


@dataclass
class MemoryContextData:
    conversation_id: int | None
    message_count: int
    summary: str | None
    summary_up_to_sequence: int
    recent_messages: list[dict[str, str]]
    tenant_profile_summary: str | None
    tenant_profile_source: str | None


def get_window_size() -> int:
    return int(os.environ.get("CHAT_WINDOW_SIZE", "5"))
