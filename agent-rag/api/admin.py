from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from api.deps import get_assistant
from api.schemas import RagMetricsResponse, RagPrometheusSummary
from rag.assistant import EMBEDDING_MODEL, LLM_MODEL
from rag.knowledge_bases import get_label, validate_collection_name
from rag.metrics import get_process_started_at_dt, get_system_snapshot, get_totals, get_uptime_seconds
from rag.rerank_local import RERANK_ENABLED
from rag.telemetry import collect_summary, get_build_version

router = APIRouter(prefix="/admin", tags=["admin"])


def _resolve_tenant_id(request: Request) -> str:
    return request.headers.get("X-Tenant-Id") or "default_tenant"


@router.get("/metrics", response_model=RagMetricsResponse)
def rag_metrics(request: Request, collection: str | None = None) -> RagMetricsResponse:
    try:
        collection_name = validate_collection_name(collection)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    tenant_id = _resolve_tenant_id(request)
    assistant = get_assistant(request.app, collection_name)
    totals = get_totals(tenant_id)
    document_count = assistant.collection.count()
    summary_data = collect_summary(tenant_id)

    return RagMetricsResponse(
        llm_requests_total=totals["llm_requests_total"],
        embedding_requests_total=totals["embedding_requests_total"],
        rerank_requests_total=totals["rerank_requests_total"],
        tool_calls_total=totals.get("tool_calls_total", 0),
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
