#!/usr/bin/env python3
"""Run eval questions against the assistant (offline smoke test)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval import load_questions
from rag.assistant import CarSafetyWhitepaperAssistant, rebuild_history
from rag.logging_config import configure_logging

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()
    questions = load_questions()
    if not questions:
        logger.warning("No eval questions found")
        return

    assistant = CarSafetyWhitepaperAssistant()
    history = rebuild_history([])
    passed = 0
    for idx, item in enumerate(questions, start=1):
        q = item["question"]
        answer = assistant.get_response(q, history)
        ok = bool(answer.strip())
        passed += int(ok)
        logger.info("[%d] %s -> %s... ok=%s", idx, q, answer[:120], ok)
    logger.info("Passed %d/%d", passed, len(questions))


if __name__ == "__main__":
    main()
