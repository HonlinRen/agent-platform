from __future__ import annotations

import os


def estimate_tokens(text: str) -> int:
    """Heuristic token estimate (chars/4), aligned with gateway TPM."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def estimate_messages_tokens(messages: list[dict[str, str]]) -> int:
    return sum(estimate_tokens(f"{item.get('role', '')}: {item.get('content', '')}") for item in messages)


def get_summary_trigger_rounds() -> int:
    return int(os.environ.get("CHAT_SUMMARY_TRIGGER_ROUNDS", "10"))


def get_summary_trigger_tokens() -> int:
    return int(os.environ.get("CHAT_SUMMARY_TRIGGER_TOKENS", "3000"))


def get_summary_max_chars() -> int:
    return int(os.environ.get("CHAT_SUMMARY_MAX_CHARS", "500"))


def get_recent_max_tokens() -> int:
    return int(os.environ.get("CHAT_RECENT_MAX_TOKENS", "0"))
