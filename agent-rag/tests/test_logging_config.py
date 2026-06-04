from __future__ import annotations

import json
import logging
import os

import pytest

from rag.logging_config import CONTEXT_FIELDS, ContextFilter, configure_logging
from rag.telemetry import bind_request_context


@pytest.fixture(autouse=True)
def reset_logging_config():
    import rag.logging_config as lc

    lc._CONFIGURED = False
    yield
    lc._CONFIGURED = False
    root = logging.getLogger()
    root.handlers.clear()
    root.filters.clear()


def test_configure_logging_is_idempotent():
    configure_logging()
    handlers_after_first = len(logging.getLogger().handlers)
    configure_logging()
    assert len(logging.getLogger().handlers) == handlers_after_first


def test_context_filter_injects_request_id():
    bind_request_context(request_id="req-123", tenant_id="t1", thread_id="th1")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    for key in CONTEXT_FIELDS:
        setattr(record, key, "")

    assert ContextFilter().filter(record) is True
    assert record.request_id == "req-123"
    assert record.tenant_id == "t1"
    assert record.thread_id == "th1"
    assert record.trace_id


def test_json_log_format(capsys):
    os.environ["LOG_FORMAT"] = "json"
    os.environ["LOG_LEVEL"] = "INFO"
    configure_logging(force=True)
    bind_request_context(request_id="req-json")

    logger = logging.getLogger("test.json")
    logger.info("json message")

    captured = capsys.readouterr().out.strip()
    payload = json.loads(captured)
    assert payload["message"] == "json message"
    assert payload["level"] == "INFO"
    assert payload["request_id"] == "req-json"

    os.environ.pop("LOG_FORMAT", None)


def test_text_log_format(capsys):
    os.environ["LOG_FORMAT"] = "text"
    os.environ["LOG_LEVEL"] = "INFO"
    configure_logging(force=True)

    logger = logging.getLogger("test.text")
    logger.info("text message")

    captured = capsys.readouterr().out
    assert "text message" in captured
    assert "[test.text]" in captured
