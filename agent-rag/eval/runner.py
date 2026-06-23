"""Batch runner for RAG quality evaluation."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eval import GoldenQuestion, load_golden_dataset
from eval.client import DEFAULT_RAG_API_URL, RagAnswer, fetch_rag_answer
from eval.judge import JudgeResult, score_answer
from rag.assistant import CarSafetyWhitepaperAssistant, rebuild_history

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).resolve().parent / "reports"


@dataclass
class EvalCaseResult:
    question: str
    gold_answer: str
    reference_doc: str
    must_have_points: list[str]
    model_answer: str
    route: str
    citations: list[dict[str, Any]]
    latency_ms: int
    judge: JudgeResult

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["judge"] = self.judge.to_dict()
        return payload


@dataclass
class EvalReport:
    mode: str
    total: int
    average_score: float
    hallucination_rate: float
    point_hit_rate: float
    cases: list[EvalCaseResult]
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "total": self.total,
            "average_score": self.average_score,
            "hallucination_rate": self.hallucination_rate,
            "point_hit_rate": self.point_hit_rate,
            "generated_at": self.generated_at,
            "cases": [case.to_dict() for case in self.cases],
        }


def _point_hit_rate(case: EvalCaseResult) -> float:
    total_points = len(case.must_have_points)
    if total_points == 0:
        return 0.0
    return len(case.judge.hit_points) / total_points


def _build_summary(cases: list[EvalCaseResult]) -> tuple[float, float, float]:
    if not cases:
        return 0.0, 0.0, 0.0
    average_score = sum(case.judge.score for case in cases) / len(cases)
    hallucination_rate = sum(1 for case in cases if case.judge.hallucination) / len(cases)
    point_hit_rate = sum(_point_hit_rate(case) for case in cases) / len(cases)
    return average_score, hallucination_rate, point_hit_rate


def _answer_via_assistant(question: GoldenQuestion, assistant: CarSafetyWhitepaperAssistant) -> tuple[str, str, list[dict[str, Any]], int]:
    start = time.perf_counter()
    history = rebuild_history([])
    answer = assistant.get_response(question.question, history)
    latency_ms = int((time.perf_counter() - start) * 1000)
    return answer, "assistant", [], latency_ms


def _answer_via_api(question: GoldenQuestion, base_url: str) -> tuple[str, str, list[dict[str, Any]], int]:
    start = time.perf_counter()
    rag_answer: RagAnswer = fetch_rag_answer(
        question.question,
        collection_name=question.collection_name,
        base_url=base_url,
    )
    latency_ms = int((time.perf_counter() - start) * 1000)
    return rag_answer.content, rag_answer.route, rag_answer.citations, latency_ms


def evaluate_case(
    question: GoldenQuestion,
    answer_fn: Callable[[GoldenQuestion], tuple[str, str, list[dict[str, Any]], int]],
) -> EvalCaseResult:
    model_answer, route, citations, latency_ms = answer_fn(question)
    judge = score_answer(
        question.question,
        question.gold_answer,
        question.must_have_points,
        model_answer,
    )
    return EvalCaseResult(
        question=question.question,
        gold_answer=question.gold_answer,
        reference_doc=question.reference_doc,
        must_have_points=question.must_have_points,
        model_answer=model_answer,
        route=route,
        citations=citations,
        latency_ms=latency_ms,
        judge=judge,
    )


def run_evaluation(
    *,
    mode: str = "api",
    base_url: str | None = None,
    questions: list[GoldenQuestion] | None = None,
) -> EvalReport:
    dataset = questions or load_golden_dataset()
    if not dataset:
        raise RuntimeError("Golden dataset is empty")

    if mode == "assistant":
        assistant = CarSafetyWhitepaperAssistant(collection_name=dataset[0].collection_name)

        def answer_fn(question: GoldenQuestion) -> tuple[str, str, list[dict[str, Any]], int]:
            if question.collection_name != assistant.collection_name:
                local_assistant = CarSafetyWhitepaperAssistant(collection_name=question.collection_name)
                return _answer_via_assistant(question, local_assistant)
            return _answer_via_assistant(question, assistant)

    elif mode == "api":
        resolved_base = base_url or DEFAULT_RAG_API_URL

        def answer_fn(question: GoldenQuestion) -> tuple[str, str, list[dict[str, Any]], int]:
            return _answer_via_api(question, resolved_base)

    else:
        raise ValueError(f"Unsupported mode: {mode}")

    cases: list[EvalCaseResult] = []
    for index, question in enumerate(dataset, start=1):
        logger.info("[%d/%d] evaluating: %s", index, len(dataset), question.question)
        cases.append(evaluate_case(question, answer_fn))

    average_score, hallucination_rate, point_hit_rate = _build_summary(cases)
    return EvalReport(
        mode=mode,
        total=len(cases),
        average_score=average_score,
        hallucination_rate=hallucination_rate,
        point_hit_rate=point_hit_rate,
        cases=cases,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def save_report(report: EvalReport, output_dir: Path | None = None) -> Path:
    target_dir = output_dir or REPORTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = target_dir / f"quality_report_{timestamp}.json"
    path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def format_report_summary(report: EvalReport) -> str:
    lines = [
        f"mode={report.mode} total={report.total}",
        f"average_score={report.average_score:.2f}",
        f"hallucination_rate={report.hallucination_rate:.2%}",
        f"point_hit_rate={report.point_hit_rate:.2%}",
        "",
    ]
    for index, case in enumerate(report.cases, start=1):
        lines.append(
            f"[{index}] score={case.judge.score} hallucination={case.judge.hallucination} "
            f"latency_ms={case.latency_ms} route={case.route}"
        )
        lines.append(f"  Q: {case.question}")
        lines.append(f"  hit={case.judge.hit_points}")
        lines.append(f"  missing={case.judge.missing_points}")
        lines.append(f"  reason={case.judge.reason}")
    return "\n".join(lines)
