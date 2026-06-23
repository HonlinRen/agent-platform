from __future__ import annotations

import contextvars
import logging
import os
import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import inject
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.trace import Span, Status, StatusCode
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, Info, generate_latest

logger = logging.getLogger(__name__)

_tracer: trace.Tracer | None = None
_initialized = False

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
_tenant_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("tenant_id", default=None)
_thread_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("thread_id", default=None)

_PROCESS_START_TIME = time.time()

# Prometheus metrics
HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path", "status"],
)
AGENT_REQUEST_DURATION = Histogram(
    "agent_request_duration_seconds",
    "End-to-end chat request duration in seconds",
    ["route", "tenant"],
)
RAG_NODE_DURATION = Histogram(
    "rag_node_duration_seconds",
    "LangGraph node execution duration in seconds",
    ["node", "tenant"],
)
RAG_EMBEDDING_DURATION = Histogram(
    "rag_embedding_duration_seconds",
    "DashScope embedding duration in seconds",
    ["tenant"],
)
RAG_LLM_DURATION = Histogram(
    "rag_llm_duration_seconds",
    "LLM invocation duration in seconds",
    ["operation", "tenant"],
)
RAG_CHROMA_QUERY_DURATION = Histogram(
    "rag_chroma_query_duration_seconds",
    "Chroma vector query duration in seconds",
    ["tenant", "collection"],
)
RAG_RERANK_DURATION = Histogram(
    "rag_rerank_duration_seconds",
    "Local rerank duration in seconds",
    ["tenant", "collection"],
)
RAG_RETRIEVAL_CANDIDATES = Histogram(
    "rag_retrieval_candidates",
    "Number of candidates returned from vector recall",
    ["tenant", "collection"],
    buckets=(0, 1, 5, 10, 20, 40, 60, 100),
)
RAG_RETRIEVAL_SCORE = Histogram(
    "rag_retrieval_score",
    "Top-1 rerank score after retrieval",
    ["tenant", "collection"],
    buckets=(0.0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 0.7, 0.9, 1.0),
)
RAG_LLM_REQUESTS = Counter("rag_llm_requests_total", "Total LLM invocations", ["tenant"])
RAG_EMBEDDING_REQUESTS = Counter("rag_embedding_requests_total", "Total embedding invocations", ["tenant"])
RAG_RERANK_REQUESTS = Counter("rag_rerank_requests_total", "Total rerank invocations", ["tenant"])
RAG_TOOL_CALLS = Counter("rag_tool_calls_total", "Total tool invocations", ["tool", "tenant"])
RAG_TAVILY_SEARCH_TOTAL = Counter(
    "rag_tavily_search_total",
    "Total Tavily web search invocations",
    ["status", "tenant"],
)
RAG_BUDGET_STOP_TOTAL = Counter(
    "rag_budget_stop_total",
    "Requests that hit per-request budget limits",
    ["reason", "tenant"],
)
RAG_CHAT_REQUESTS = Counter(
    "rag_chat_requests_total",
    "Total chat stream requests",
    ["route", "tenant", "status"],
)
RAG_REJECT_TOTAL = Counter(
    "rag_reject_total",
    "Total retrieval rejections",
    ["reason", "tenant"],
)
RAG_FEEDBACK_TOTAL = Counter(
    "rag_feedback_total",
    "Total user feedback submissions",
    ["rating"],
)

RAG_BUILD_INFO = Info("rag_build", "Build information")
RAG_BUILD_INFO.info(
    {
        "version": os.environ.get("RAG_VERSION", "dev"),
        "service": "agent-rag",
    }
)
RAG_PROCESS_START_TIME = Gauge(
    "rag_process_start_time_seconds",
    "Unix timestamp when the RAG process started",
)
RAG_PROCESS_START_TIME.set(_PROCESS_START_TIME)
RAG_METRICS_SCRAPE_UNIXTIME = Gauge(
    "rag_metrics_scrape_unixtime_seconds",
    "Unix timestamp when /metrics was last generated",
)
RAG_SCRAPE_INFO = Info("rag_scrape", "Last scrape metadata (ISO8601 labels)")


def init_tracing(service_name: str | None = None) -> None:
    global _tracer, _initialized
    if _initialized:
        return

    name = service_name or os.environ.get("OTEL_SERVICE_NAME", "agent-rag")
    resource = Resource.create({"service.name": name})

    provider = TracerProvider(resource=resource)
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if endpoint:
        if not endpoint.endswith("/v1/traces"):
            endpoint = endpoint.rstrip("/") + "/v1/traces"
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    elif os.environ.get("OTEL_CONSOLE_EXPORTER", "").lower() in {"1", "true", "yes"}:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(name)
    _initialized = True
    logger.info("OpenTelemetry tracing initialized for service=%s endpoint=%s", name, endpoint or "none")


def init_instrumentation() -> None:
    """Auto-instrument FastAPI and httpx (call after init_tracing)."""
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
    except Exception as exc:
        logger.warning("httpx instrumentation skipped: %s", exc)


def instrument_fastapi(app: Any) -> None:
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
    except Exception as exc:
        logger.warning("FastAPI instrumentation skipped: %s", exc)


def get_tracer() -> trace.Tracer:
    global _tracer
    if _tracer is None:
        init_tracing()
    return _tracer or trace.get_tracer(__name__)


def bind_request_context(
    *,
    tenant_id: str | None = None,
    thread_id: str | None = None,
    request_id: str | None = None,
) -> None:
    if tenant_id is not None:
        _tenant_id.set(tenant_id)
    if thread_id is not None:
        _thread_id.set(thread_id)
    if request_id is not None:
        _request_id.set(request_id)


def get_request_id() -> str | None:
    return _request_id.get()


def get_tenant_id() -> str | None:
    return _tenant_id.get()


def resolve_tenant_id(tenant_id: str | None = None) -> str:
    return tenant_id or get_tenant_id() or "default_tenant"


def get_thread_id() -> str | None:
    return _thread_id.get()


def get_process_start_time() -> float:
    return _PROCESS_START_TIME


def get_process_started_at() -> datetime:
    return datetime.fromtimestamp(_PROCESS_START_TIME, tz=timezone.utc)


def resolve_request_id(header_value: str | None) -> str:
    rid = (header_value or "").strip()
    if not rid:
        rid = str(uuid.uuid4())
    _request_id.set(rid)
    return rid


def current_trace_id() -> str:
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid:
        return format(ctx.trace_id, "032x")
    return str(uuid.uuid4())


def log_extra() -> dict[str, str]:
    extra: dict[str, str] = {}
    rid = get_request_id()
    tid = get_tenant_id()
    thid = get_thread_id()
    if rid:
        extra["request_id"] = rid
    if tid:
        extra["tenant_id"] = tid
    if thid:
        extra["thread_id"] = thid
    trace_id = current_trace_id()
    if trace_id:
        extra["trace_id"] = trace_id
    return extra


def inject_trace_headers(headers: dict[str, str]) -> dict[str, str]:
    inject(headers)
    rid = get_request_id()
    if rid:
        headers.setdefault("X-Request-Id", rid)
    return headers


def get_build_version() -> str:
    return os.environ.get("RAG_VERSION", "dev")


def metrics_response() -> tuple[bytes, str, dict[str, str]]:
    now = time.time()
    scrape_dt = datetime.fromtimestamp(now, tz=timezone.utc)
    process_dt = get_process_started_at()
    RAG_METRICS_SCRAPE_UNIXTIME.set(now)
    RAG_SCRAPE_INFO.info(
        {
            "scrape_time_utc": scrape_dt.isoformat(),
            "process_started_utc": process_dt.isoformat(),
        }
    )
    header = (
        "# agent-rag metrics exposition\n"
        f"# scrape_time_utc: {scrape_dt.isoformat()}\n"
        f"# process_started_utc: {process_dt.isoformat()}\n"
    )
    body = header.encode() + generate_latest()
    response_headers = {
        "X-Metrics-Scrape-At": scrape_dt.isoformat(),
        "X-Process-Started-At": process_dt.isoformat(),
    }
    return body, CONTENT_TYPE_LATEST, response_headers


def _histogram_sum_count(metric: Histogram) -> tuple[float, float]:
    """Read histogram sum/count from a labeled child (prometheus_client >=0.21)."""
    total_sum = metric._sum.get()
    for sample in metric.collect()[0].samples:
        if sample.name.endswith("_count"):
            return total_sum, sample.value
    return total_sum, metric._buckets[-1].get()


def _histogram_avg_for_tenant(histogram: Histogram, tenant: str, **match_labels: str) -> float | None:
    total_sum = 0.0
    total_count = 0.0
    label_names = histogram._labelnames
    for labels, metric in histogram._metrics.items():
        label_dict = dict(zip(label_names, labels))
        if label_dict.get("tenant") != tenant:
            continue
        if any(label_dict.get(key) != value for key, value in match_labels.items()):
            continue
        sample_sum, sample_count = _histogram_sum_count(metric)
        total_sum += sample_sum
        total_count += sample_count
    if total_count > 0:
        return round(total_sum / total_count, 4)
    return None


def collect_summary(tenant: str = "default_tenant") -> dict[str, Any]:
    node_avgs: dict[str, float] = {}
    for labels, metric in RAG_NODE_DURATION._metrics.items():
        label_dict = dict(zip(RAG_NODE_DURATION._labelnames, labels))
        if label_dict.get("tenant") != tenant:
            continue
        node = label_dict.get("node")
        if not node:
            continue
        total_sum, count = _histogram_sum_count(metric)
        if count <= 0:
            continue
        node_avgs[node] = round(total_sum / count, 4)

    return {
        "agent_request_avg_seconds": _histogram_avg_for_tenant(AGENT_REQUEST_DURATION, tenant),
        "chroma_query_avg_seconds": _histogram_avg_for_tenant(RAG_CHROMA_QUERY_DURATION, tenant),
        "rerank_avg_seconds": _histogram_avg_for_tenant(RAG_RERANK_DURATION, tenant),
        "retrieval_top1_score_avg": _histogram_avg_for_tenant(RAG_RETRIEVAL_SCORE, tenant),
        "node_duration_avg_seconds": node_avgs,
    }


def record_chat_request(route: str, tenant: str, status: str) -> None:
    RAG_CHAT_REQUESTS.labels(route=route, tenant=tenant, status=status).inc()


def record_reject(reason: str, tenant: str | None = None) -> None:
    RAG_REJECT_TOTAL.labels(reason=reason, tenant=resolve_tenant_id(tenant)).inc()


def record_feedback(rating: str) -> None:
    RAG_FEEDBACK_TOTAL.labels(rating=rating).inc()


def normalize_http_path(request: Any) -> str:
    route = request.scope.get("route")
    if route is not None and getattr(route, "path", None):
        return route.path
    return request.url.path


def _base_attributes(**extra: Any) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    if get_tenant_id():
        attrs["tenant.id"] = get_tenant_id()
    if get_thread_id():
        attrs["thread.id"] = get_thread_id()
    if get_request_id():
        attrs["http.request_id"] = get_request_id()
    attrs.update(extra)
    return attrs


@contextmanager
def span(name: str, attributes: dict[str, Any] | None = None) -> Generator[Span, None, None]:
    tracer = get_tracer()
    attrs = _base_attributes(**(attributes or {}))
    with tracer.start_as_current_span(name, attributes=attrs) as current:
        try:
            yield current
        except Exception as exc:
            current.set_status(Status(StatusCode.ERROR, str(exc)))
            current.record_exception(exc)
            raise


def observe_node_duration(node: str, tenant: str, duration: float) -> None:
    RAG_NODE_DURATION.labels(node=node, tenant=tenant).observe(duration)


def observe_agent_request(route: str, tenant: str, duration: float) -> None:
    AGENT_REQUEST_DURATION.labels(route=route, tenant=tenant).observe(duration)


def observe_embedding_duration(tenant: str, duration: float) -> None:
    RAG_EMBEDDING_DURATION.labels(tenant=tenant).observe(duration)


def observe_llm_duration(operation: str, tenant: str, duration: float) -> None:
    RAG_LLM_DURATION.labels(operation=operation, tenant=tenant).observe(duration)
