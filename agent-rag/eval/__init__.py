"""Eval dataset loader for RAG quality checks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).resolve().parent
QUESTIONS_PATH = EVAL_DIR / "questions.jsonl"
GOLDEN_PATH = EVAL_DIR / "semiconductor_golden.jsonl"

REQUIRED_GOLDEN_FIELDS = (
    "question",
    "gold_answer",
    "reference_doc",
    "must_have_points",
    "collection_name",
)


@dataclass(frozen=True)
class GoldenQuestion:
    question: str
    gold_answer: str
    reference_doc: str
    must_have_points: list[str]
    collection_name: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GoldenQuestion:
        missing = [field for field in REQUIRED_GOLDEN_FIELDS if field not in data]
        if missing:
            raise ValueError(f"Golden question missing fields: {', '.join(missing)}")
        must_have_points = data["must_have_points"]
        if not isinstance(must_have_points, list) or not must_have_points:
            raise ValueError("must_have_points must be a non-empty list")
        return cls(
            question=str(data["question"]).strip(),
            gold_answer=str(data["gold_answer"]).strip(),
            reference_doc=str(data["reference_doc"]).strip(),
            must_have_points=[str(point).strip() for point in must_have_points if str(point).strip()],
            collection_name=str(data["collection_name"]).strip(),
        )


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    items: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def load_questions() -> list[dict[str, Any]]:
    return _load_jsonl(QUESTIONS_PATH)


def load_golden_dataset() -> list[GoldenQuestion]:
    return [GoldenQuestion.from_dict(item) for item in _load_jsonl(GOLDEN_PATH)]
