from __future__ import annotations

import logging
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import QueryTimingLlmCall, QueryTimingRun

logger = logging.getLogger(__name__)

TimingPhase = Literal["main", "post_turn"]

DISTRIBUTION_BUCKETS: list[tuple[str, int, int | None]] = [
    ("0-500ms", 0, 500),
    ("500ms-1s", 500, 1000),
    ("1-2s", 1000, 2000),
    ("2-5s", 2000, 5000),
    ("5-10s", 5000, 10000),
    ("10s+", 10000, None),
]


def _bucket_label(ms: int) -> str:
    for label, low, high in DISTRIBUTION_BUCKETS:
        if high is None:
            if ms >= low:
                return label
        elif low <= ms < high:
            return label
    return DISTRIBUTION_BUCKETS[-1][0]


def _build_distribution(values: list[int]) -> list[dict[str, int | str]]:
    counts = {label: 0 for label, _, _ in DISTRIBUTION_BUCKETS}
    for value in values:
        counts[_bucket_label(value)] += 1
    return [{"bucket": label, "count": counts[label]} for label, _, _ in DISTRIBUTION_BUCKETS]


def _percentile(values: list[int], pct: float) -> int | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    sorted_vals = sorted(values)
    index = int(round((pct / 100.0) * (len(sorted_vals) - 1)))
    return sorted_vals[max(0, min(index, len(sorted_vals) - 1))]


def _metric_summary(values: list[int]) -> dict[str, Any]:
    if not values:
        return {
            "avg_ms": None,
            "p50_ms": None,
            "p90_ms": None,
            "count": 0,
            "distribution": _build_distribution([]),
        }
    return {
        "avg_ms": round(statistics.mean(values)),
        "p50_ms": _percentile(values, 50),
        "p90_ms": _percentile(values, 90),
        "count": len(values),
        "distribution": _build_distribution(values),
    }


class TimingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save_timing_run(
        self,
        *,
        tenant_id: str,
        thread_id: str,
        request_id: str | None,
        trace_run_id: str,
        route: str,
        status: str,
        total_ms: int,
        embedding_ms: int,
        embedding_count: int,
        chroma_ms: int,
        chroma_count: int,
        rerank_ms: int,
        rerank_count: int,
        llm_total_ms: int,
        llm_call_count: int,
        collection_name: str | None,
        llm_calls: list[dict[str, Any]],
    ) -> int:
        run = QueryTimingRun(
            tenant_id=tenant_id,
            thread_id=thread_id,
            request_id=request_id,
            run_id=trace_run_id,
            route=route,
            status=status,
            total_ms=total_ms,
            embedding_ms=embedding_ms,
            embedding_count=embedding_count,
            chroma_ms=chroma_ms,
            chroma_count=chroma_count,
            rerank_ms=rerank_ms,
            rerank_count=rerank_count,
            llm_total_ms=llm_total_ms,
            llm_call_count=llm_call_count,
            collection_name=collection_name,
        )
        self._session.add(run)
        self._session.flush()

        for call in llm_calls:
            if call.get("phase", "main") != "main":
                continue
            self._session.add(
                QueryTimingLlmCall(
                    run_id=run.id,
                    tenant_id=tenant_id,
                    operation=call["operation"],
                    sequence=call["sequence"],
                    duration_ms=call["duration_ms"],
                    tokens_used=call.get("tokens_used") or None,
                    phase="main",
                )
            )
        return run.id

    def append_llm_call(
        self,
        *,
        tenant_id: str,
        trace_run_id: str,
        operation: str,
        duration_ms: int,
        tokens_used: int = 0,
        phase: TimingPhase = "post_turn",
    ) -> bool:
        run = self._session.scalar(
            select(QueryTimingRun)
            .where(QueryTimingRun.tenant_id == tenant_id, QueryTimingRun.run_id == trace_run_id)
            .order_by(QueryTimingRun.id.desc())
            .limit(1)
        )
        if run is None:
            return False

        max_seq = self._session.scalar(
            select(func.max(QueryTimingLlmCall.sequence)).where(QueryTimingLlmCall.run_id == run.id)
        )
        sequence = (max_seq or 0) + 1
        self._session.add(
            QueryTimingLlmCall(
                run_id=run.id,
                tenant_id=tenant_id,
                operation=operation,
                sequence=sequence,
                duration_ms=duration_ms,
                tokens_used=tokens_used or None,
                phase=phase,
            )
        )
        return True

    def aggregate_timing_stats(self, tenant_id: str, days: int = 7) -> dict[str, Any]:
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
        runs = list(
            self._session.scalars(
                select(QueryTimingRun)
                .where(QueryTimingRun.tenant_id == tenant_id, QueryTimingRun.created_at >= since)
                .order_by(QueryTimingRun.created_at.desc())
            ).all()
        )

        total_values = [r.total_ms for r in runs]
        embedding_values = [r.embedding_ms for r in runs if r.embedding_count > 0]
        chroma_values = [r.chroma_ms for r in runs if r.chroma_count > 0]
        rerank_values = [r.rerank_ms for r in runs if r.rerank_count > 0]
        llm_values = [r.llm_total_ms for r in runs if r.llm_call_count > 0]

        llm_calls = list(
            self._session.scalars(
                select(QueryTimingLlmCall).where(
                    QueryTimingLlmCall.tenant_id == tenant_id,
                    QueryTimingLlmCall.created_at >= since,
                )
            ).all()
        )

        by_operation: dict[str, list[int]] = {}
        llm_call_durations: list[int] = []
        for call in llm_calls:
            llm_call_durations.append(call.duration_ms)
            by_operation.setdefault(call.operation, []).append(call.duration_ms)

        operation_stats = {
            op: {
                "count": len(durations),
                "avg_ms": round(statistics.mean(durations)) if durations else None,
            }
            for op, durations in sorted(by_operation.items())
        }

        return {
            "tenant_id": tenant_id,
            "period_days": days,
            "total_runs": len(runs),
            "overall": _metric_summary(total_values),
            "embedding": _metric_summary(embedding_values),
            "chroma": _metric_summary(chroma_values),
            "rerank": _metric_summary(rerank_values),
            "llm": {
                **_metric_summary(llm_call_durations if llm_call_durations else llm_values),
                "by_operation": operation_stats,
            },
        }


def save_timing_best_effort(
    *,
    tenant_id: str,
    thread_id: str,
    request_id: str | None,
    trace_run_id: str,
    route: str,
    status: str,
    total_ms: int,
    timing_snapshot: dict[str, Any],
    collection_name: str | None,
) -> None:
    try:
        from db.session import get_db

        with get_db() as session:
            TimingRepository(session).save_timing_run(
                tenant_id=tenant_id,
                thread_id=thread_id,
                request_id=request_id,
                trace_run_id=trace_run_id,
                route=route,
                status=status,
                total_ms=total_ms,
                embedding_ms=timing_snapshot.get("embedding_ms", 0),
                embedding_count=timing_snapshot.get("embedding_count", 0),
                chroma_ms=timing_snapshot.get("chroma_ms", 0),
                chroma_count=timing_snapshot.get("chroma_count", 0),
                rerank_ms=timing_snapshot.get("rerank_ms", 0),
                rerank_count=timing_snapshot.get("rerank_count", 0),
                llm_total_ms=timing_snapshot.get("llm_total_ms", 0),
                llm_call_count=timing_snapshot.get("llm_call_count", 0),
                collection_name=collection_name,
                llm_calls=timing_snapshot.get("llm_calls", []),
            )
    except Exception:
        logger.exception("Failed to persist query timing to MySQL")


def append_timing_llm_call_best_effort(
    *,
    tenant_id: str,
    trace_run_id: str,
    operation: str,
    duration_ms: int,
    tokens_used: int = 0,
    phase: TimingPhase = "post_turn",
) -> None:
    try:
        from db.session import get_db

        with get_db() as session:
            TimingRepository(session).append_llm_call(
                tenant_id=tenant_id,
                trace_run_id=trace_run_id,
                operation=operation,
                duration_ms=duration_ms,
                tokens_used=tokens_used,
                phase=phase,
            )
    except Exception:
        logger.exception("Failed to append post-turn LLM timing to MySQL")
