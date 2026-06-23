from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from api.deps import get_assistant
from api.schemas import (
    RagMetricsResponse,
    RagPrometheusSummary,
    TenantProfileResponse,
    TenantProfileUpdateRequest,
    TimingDistributionBucket,
    TimingLlmSummary,
    TimingMetricSummary,
    TimingOperationSummary,
    TimingStatsResponse,
)
from api.tenant_profile_service import (
    get_tenant_profile_response,
    put_tenant_profile_response,
    resolve_tenant_id,
)
from rag.assistant import EMBEDDING_MODEL, LLM_MODEL
from rag.knowledge_bases import get_label, validate_collection_name
from rag.metrics import get_process_started_at_dt, get_system_snapshot, get_totals, get_uptime_seconds
from rag.rerank_local import RERANK_ENABLED
from db.session import get_db
from db.timing_repository import TimingRepository
from rag.telemetry import collect_summary, get_build_version

router = APIRouter(prefix="/admin", tags=["admin"])


def _timing_metric_from_dict(data: dict) -> TimingMetricSummary:
    return TimingMetricSummary(
        avg_ms=data.get("avg_ms"),
        p50_ms=data.get("p50_ms"),
        p90_ms=data.get("p90_ms"),
        count=data.get("count", 0),
        distribution=[
            TimingDistributionBucket(bucket=item["bucket"], count=item["count"])
            for item in data.get("distribution", [])
        ],
    )


@router.get("/metrics", response_model=RagMetricsResponse)
def rag_metrics(request: Request, collection: str | None = None) -> RagMetricsResponse:
    try:
        collection_name = validate_collection_name(collection)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    tenant_id = resolve_tenant_id(request)
    assistant = get_assistant(request.app, collection_name)
    totals = get_totals(tenant_id)
    document_count = assistant.collection.count()
    summary_data = collect_summary(tenant_id)

    return RagMetricsResponse(
        llm_requests_total=totals["llm_requests_total"],
        embedding_requests_total=totals["embedding_requests_total"],
        rerank_requests_total=totals["rerank_requests_total"],
        tool_calls_total=totals.get("tool_calls_total", 0),
        tavily_calls_total=totals.get("tavily_calls_total", 0),
        tavily_calls_ok=totals.get("tavily_calls_ok", 0),
        tavily_calls_empty=totals.get("tavily_calls_empty", 0),
        tavily_calls_error=totals.get("tavily_calls_error", 0),
        collection={
            "name": collection_name,
            "label": get_label(collection_name),
            "document_count": document_count,
        },
        config={
            "llm_model": LLM_MODEL,
            "embedding_model": EMBEDDING_MODEL,
            "rerank_enabled": RERANK_ENABLED,
        },
        system=get_system_snapshot(),
        uptime_seconds=get_uptime_seconds(),
        collected_at=datetime.now(timezone.utc),
        process_started_at=get_process_started_at_dt(),
        build_version=get_build_version(),
        summary=RagPrometheusSummary(**summary_data),
    )


@router.get("/timing-stats", response_model=TimingStatsResponse)
def timing_stats(request: Request, days: int = 7) -> TimingStatsResponse:
    if days < 1 or days > 90:
        raise HTTPException(status_code=400, detail="days 必须在 1-90 之间")
    tenant_id = resolve_tenant_id(request)
    try:
        with get_db() as session:
            stats = TimingRepository(session).aggregate_timing_stats(tenant_id, days=days)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="耗时统计暂不可用") from exc

    llm_data = stats.get("llm", {})
    by_operation = {
        op: TimingOperationSummary(count=item.get("count", 0), avg_ms=item.get("avg_ms"))
        for op, item in llm_data.get("by_operation", {}).items()
    }
    llm_summary = TimingLlmSummary(
        avg_ms=llm_data.get("avg_ms"),
        p50_ms=llm_data.get("p50_ms"),
        p90_ms=llm_data.get("p90_ms"),
        count=llm_data.get("count", 0),
        distribution=[
            TimingDistributionBucket(bucket=item["bucket"], count=item["count"])
            for item in llm_data.get("distribution", [])
        ],
        by_operation=by_operation,
    )

    return TimingStatsResponse(
        tenant_id=tenant_id,
        period_days=days,
        total_runs=stats.get("total_runs", 0),
        collected_at=datetime.now(timezone.utc),
        overall=_timing_metric_from_dict(stats.get("overall", {})),
        embedding=_timing_metric_from_dict(stats.get("embedding", {})),
        chroma=_timing_metric_from_dict(stats.get("chroma", {})),
        rerank=_timing_metric_from_dict(stats.get("rerank", {})),
        llm=llm_summary,
    )


@router.get("/tenant-profile", response_model=TenantProfileResponse)
def get_tenant_profile(request: Request) -> TenantProfileResponse:
    return get_tenant_profile_response(resolve_tenant_id(request))


@router.put("/tenant-profile", response_model=TenantProfileResponse)
def put_tenant_profile(
    request: Request,
    body: TenantProfileUpdateRequest,
) -> TenantProfileResponse:
    return put_tenant_profile_response(resolve_tenant_id(request), body)
