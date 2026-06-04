"""Eval dataset runner for citation accuracy."""

from __future__ import annotations

import json
from pathlib import Path

EVAL_PATH = Path(__file__).resolve().parents[1] / "eval" / "questions.jsonl"


def load_questions() -> list[dict]:
    if not EVAL_PATH.exists():
        return []
    items: list[dict] = []
    with open(EVAL_PATH, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items
