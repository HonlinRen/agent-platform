from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_CHECKPOINTER: Any | None = None
_CHECKPOINTER_ATTEMPTED = False

REDIS_CHECKPOINT_PREFIX = os.environ.get("REDIS_CHECKPOINT_PREFIX", "checkpoint:rag:")
CHECKPOINT_ENABLED = os.environ.get("CHECKPOINT_ENABLED", "true").lower() in {"1", "true", "yes"}


def _redis_url() -> str:
    host = os.environ.get("REDIS_HOST", "127.0.0.1")
    port = int(os.environ.get("REDIS_PORT", "6379"))
    db = int(os.environ.get("REDIS_DB", "0"))
    password = os.environ.get("REDIS_PASSWORD", "").strip()
    if password:
        return f"redis://:{password}@{host}:{port}/{db}"
    return f"redis://{host}:{port}/{db}"


def _redis_indexes_ready(saver: Any) -> bool:
    try:
        raw = saver._redis.execute_command("FT._LIST")
        names = {item.decode() if isinstance(item, bytes) else str(item) for item in (raw or [])}
        return saver._checkpoint_prefix in names and saver._checkpoint_write_prefix in names
    except Exception:
        return False


def _ensure_redis_indexes(saver: Any) -> None:
    if _redis_indexes_ready(saver):
        return
    saver.setup()
    if not _redis_indexes_ready(saver):
        raise RuntimeError(
            f"Redis RediSearch indexes missing after setup: "
            f"{saver._checkpoint_prefix}, {saver._checkpoint_write_prefix}"
        )


def get_checkpointer() -> Any | None:
    """Return Redis checkpointer when enabled; None falls back to in-memory."""
    global _CHECKPOINTER, _CHECKPOINTER_ATTEMPTED
    if _CHECKPOINTER_ATTEMPTED:
        if _CHECKPOINTER is not None:
            try:
                _ensure_redis_indexes(_CHECKPOINTER)
            except Exception as exc:
                logger.warning("Redis checkpoint index repair failed, using in-memory: %s", exc)
                _CHECKPOINTER = None
        return _CHECKPOINTER
    _CHECKPOINTER_ATTEMPTED = True

    if not CHECKPOINT_ENABLED:
        return None

    try:
        from langgraph.checkpoint.redis import RedisSaver

        prefix = REDIS_CHECKPOINT_PREFIX.rstrip(":")
        write_prefix = f"{prefix}_write" if prefix else "checkpoint_write"
        _CHECKPOINTER = RedisSaver(
            redis_url=_redis_url(),
            checkpoint_prefix=prefix or "checkpoint",
            checkpoint_write_prefix=write_prefix,
        )
        _ensure_redis_indexes(_CHECKPOINTER)
        logger.info(
            "Redis checkpointer enabled (prefix=%s, indexes=%s,%s)",
            REDIS_CHECKPOINT_PREFIX,
            prefix,
            write_prefix,
        )
        return _CHECKPOINTER
    except Exception as exc:
        logger.warning("Redis checkpointer unavailable, using in-memory: %s", exc)
        _CHECKPOINTER = None
        return None
