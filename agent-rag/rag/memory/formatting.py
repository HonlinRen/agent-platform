from __future__ import annotations

from rag.memory.types import MemoryContext, MemoryContextData, get_window_size

EMPTY_PLACEHOLDER = "无"


def format_memory_placeholder(value: str) -> str:
    return value.strip() if value and value.strip() else EMPTY_PLACEHOLDER


def format_messages_text(messages: list[dict[str, str]]) -> str:
    if not messages:
        return "无历史对话"
    parts: list[str] = []
    for item in messages:
        role = item.get("role", "")
        content = item.get("content", "")
        label = "Human" if role == "user" else "AI"
        parts.append(f"{label}: {content}")
    return "\n".join(parts)


def build_memory_context(data: MemoryContextData) -> MemoryContext:
    window_size = get_window_size()
    recent_text = format_messages_text(data.recent_messages)
    return MemoryContext(
        recent_messages=list(data.recent_messages),
        recent_messages_text=recent_text,
        conversation_summary=(data.summary or "").strip(),
        tenant_profile_summary=(data.tenant_profile_summary or "").strip(),
        window_size=window_size,
    )


def memory_context_from_fallback(
    fallback_messages: list[dict[str, str]],
) -> MemoryContext:
    window_size = get_window_size()
    limit = window_size * 2
    recent = fallback_messages[-limit:] if fallback_messages else []
    return MemoryContext(
        recent_messages=recent,
        recent_messages_text=format_messages_text(recent),
        conversation_summary="",
        tenant_profile_summary="",
        window_size=window_size,
    )
