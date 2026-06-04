from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

USER_FRIENDLY_DEFAULT = "服务暂时不可用，请稍后重试"
USER_FRIENDLY_RATE_LIMIT = "请求过于频繁，请稍后再试"
USER_FRIENDLY_AUTH = "服务认证失败，请联系管理员"
USER_FRIENDLY_MODEL = "模型服务暂时不可用，请稍后重试"

_TECHNICAL_MARKERS = (
    "request_id",
    "status_code",
    "invalidparameter",
    "traceback",
    "exception",
    "url error",
    "dashscope",
    "openai",
    "httpx",
    "connection refused",
)


def _looks_technical(message: str) -> bool:
    lower = message.lower()
    if re.search(r"\b\d{3}\b", message) and any(
        token in lower for token in ("error", "failed", "invalid", "status_code")
    ):
        return True
    return any(marker in lower for marker in _TECHNICAL_MARKERS)


def sanitize_chat_error(exc: Exception) -> str:
    """Map internal/provider errors to safe user-facing messages."""
    raw = str(exc).strip()
    logger.error("Chat stream error: %s", raw or type(exc).__name__, exc_info=exc)

    if not raw:
        return USER_FRIENDLY_DEFAULT

    lower = raw.lower()
    if "rate_limit" in lower or "too many requests" in lower or "quota" in lower:
        return USER_FRIENDLY_RATE_LIMIT
    if any(token in lower for token in ("401", "403", "unauthorized", "api key", "authentication")):
        return USER_FRIENDLY_AUTH
    if "invalidparameter" in lower.replace(" ", "") or "url error" in lower:
        return USER_FRIENDLY_MODEL
    if _looks_technical(raw):
        return USER_FRIENDLY_DEFAULT

    # Short, already user-facing messages (e.g. validation errors).
    if len(raw) <= 80:
        return raw
    return USER_FRIENDLY_DEFAULT
