from __future__ import annotations

import logging
import os
from logging.config import dictConfig

_CONFIGURED = False

CONTEXT_FIELDS = ("request_id", "tenant_id", "thread_id", "trace_id")


class ContextFilter(logging.Filter):
    """Inject request/trace context from rag.telemetry onto each LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        from rag.telemetry import log_extra

        extras = log_extra()
        for key in CONTEXT_FIELDS:
            if key in extras:
                setattr(record, key, extras[key])
            elif not hasattr(record, key):
                setattr(record, key, "")
        return True


def _resolve_log_level() -> str:
    level = os.environ.get("LOG_LEVEL", "INFO").strip().upper()
    if level not in logging.getLevelNamesMapping():
        return "INFO"
    return level


def _resolve_log_format() -> str:
    fmt = os.environ.get("LOG_FORMAT", "text").strip().lower()
    return "json" if fmt == "json" else "text"


def configure_logging(*, force: bool = False) -> None:
    global _CONFIGURED
    if _CONFIGURED and not force:
        return

    level = _resolve_log_level()
    log_format = _resolve_log_format()

    if log_format == "json":
        formatter_cfg = {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "fmt": "%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s %(tenant_id)s %(thread_id)s %(trace_id)s",
            "rename_fields": {
                "asctime": "timestamp",
                "levelname": "level",
                "name": "logger",
            },
            "static_fields": {
                "service": os.environ.get("OTEL_SERVICE_NAME", "agent-rag"),
            },
        }
    else:
        formatter_cfg = {
            "format": (
                "%(asctime)s %(levelname)s [%(name)s] %(message)s"
                " | request_id=%(request_id)s tenant_id=%(tenant_id)s"
                " thread_id=%(thread_id)s trace_id=%(trace_id)s"
            ),
            "datefmt": "%Y-%m-%d %H:%M:%S",
        }

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "context": {
                "()": "rag.logging_config.ContextFilter",
            },
        },
        "formatters": {
            "standard": formatter_cfg,
        },
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "level": level,
                "formatter": "standard",
                "filters": ["context"],
            },
        },
        "root": {
            "level": level,
            "handlers": ["stdout"],
        },
        "loggers": {
            "uvicorn": {"level": level, "handlers": ["stdout"], "propagate": False},
            "uvicorn.error": {"level": level, "handlers": ["stdout"], "propagate": False},
            "uvicorn.access": {"level": level, "handlers": ["stdout"], "propagate": False},
            "opentelemetry": {"level": "ERROR", "handlers": ["stdout"], "propagate": False},
            "opentelemetry.context": {"level": "ERROR", "handlers": [], "propagate": False},
            "httpx": {"level": "WARNING", "handlers": ["stdout"], "propagate": False},
            "urllib3": {"level": "WARNING", "handlers": ["stdout"], "propagate": False},
        },
    }

    dictConfig(config)

    if os.environ.get("RAG_VERBOSE_RETRIEVAL", "false").lower() in {"1", "true", "yes"}:
        logging.getLogger("rag.assistant").setLevel(logging.DEBUG)

    _CONFIGURED = True
