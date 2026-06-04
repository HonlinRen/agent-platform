from __future__ import annotations

import logging
import os
import time
from typing import Any

import psutil

from rag.telemetry import (
    RAG_EMBEDDING_REQUESTS,
    RAG_LLM_REQUESTS,
    RAG_RERANK_REQUESTS,
    RAG_RETRIEVAL_SCORE,
    RAG_TOOL_CALLS,
    get_process_start_time,
    get_process_started_at,
    resolve_tenant_id,
)

logger = logging.getLogger(__name__)

_START_TIME = get_process_start_time()
_REDIS_CLIENT: Any | None = None


def _redis_key(tenant: str, metric: str) -> str:
    return f"metrics:rag:{tenant}:{metric}"


def _get_redis():
    global _REDIS_CLIENT
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT

    import redis

    host = os.environ.get("REDIS_HOST", "127.0.0.1")
    port = int(os.environ.get("REDIS_PORT", "6379"))
    db = int(os.environ.get("REDIS_DB", "0"))
    _REDIS_CLIENT = redis.Redis(host=host, port=port, db=db, decode_responses=True)
    return _REDIS_CLIENT


def _incr(key: str, amount: int = 1) -> None:
    try:
        _get_redis().incrby(key, amount)
    except Exception as exc:
        logger.warning("metrics redis incr failed (%s): %s", key, exc)


def _get_int(key: str) -> int:
    try:
        value = _get_redis().get(key)
        return int(value) if value is not None else 0
    except Exception as exc:
        logger.warning("metrics redis get failed (%s): %s", key, exc)
        return 0


def record_llm(count: int = 1, tenant: str | None = None) -> None:
    tenant_id = resolve_tenant_id(tenant)
    _incr(_redis_key(tenant_id, "llm_requests"), count)
    RAG_LLM_REQUESTS.labels(tenant=tenant_id).inc(count)


def record_embedding(count: int = 1, tenant: str | None = None) -> None:
    tenant_id = resolve_tenant_id(tenant)
    _incr(_redis_key(tenant_id, "embedding_requests"), count)
    RAG_EMBEDDING_REQUESTS.labels(tenant=tenant_id).inc(count)


def record_rerank(count: int = 1, tenant: str | None = None) -> None:
    tenant_id = resolve_tenant_id(tenant)
    _incr(_redis_key(tenant_id, "rerank_requests"), count)
    RAG_RERANK_REQUESTS.labels(tenant=tenant_id).inc(count)


def record_tool_call(tool: str = "unknown", count: int = 1, tenant: str | None = None) -> None:
    tenant_id = resolve_tenant_id(tenant)
    _incr(_redis_key(tenant_id, "tool_calls"), count)
    RAG_TOOL_CALLS.labels(tool=tool, tenant=tenant_id).inc(count)


def record_retrieval_score(score: float, tenant: str | None = None, collection: str | None = None) -> None:
    tenant_id = resolve_tenant_id(tenant)
    collection_name = collection or "unknown"
    RAG_RETRIEVAL_SCORE.labels(tenant=tenant_id, collection=collection_name).observe(score)


def get_totals(tenant: str | None = None) -> dict[str, int]:
    tenant_id = resolve_tenant_id(tenant)
    return {
        "llm_requests_total": _get_int(_redis_key(tenant_id, "llm_requests")),
        "embedding_requests_total": _get_int(_redis_key(tenant_id, "embedding_requests")),
        "rerank_requests_total": _get_int(_redis_key(tenant_id, "rerank_requests")),
        "tool_calls_total": _get_int(_redis_key(tenant_id, "tool_calls")),
    }


def get_uptime_seconds() -> int:
    return int(time.time() - _START_TIME)


def get_process_started_at_dt():
    return get_process_started_at()


def get_system_snapshot() -> dict[str, Any]:
    process = psutil.Process()
    memory_info = process.memory_info()
    virtual_memory = psutil.virtual_memory()

    cpu_system = psutil.cpu_percent(interval=None)
    cpu_process = process.cpu_percent(interval=None)

    snapshot: dict[str, Any] = {
        "process_memory_mb": round(memory_info.rss / (1024 * 1024), 1),
        "system_memory": {
            "total_mb": round(virtual_memory.total / (1024 * 1024), 1),
            "used_mb": round(virtual_memory.used / (1024 * 1024), 1),
            "percent": round(virtual_memory.percent, 1),
        },
        "cpu_percent": {
            "system": round(cpu_system, 1),
            "process": round(cpu_process, 1),
        },
        "gpu": _get_gpu_snapshot(),
    }
    return snapshot


def _get_gpu_snapshot() -> dict[str, Any]:
    try:
        import torch

        if not torch.cuda.is_available():
            return {"available": False}

        device_index = 0
        props = torch.cuda.get_device_properties(device_index)
        memory_total = props.total_memory
        memory_allocated = torch.cuda.memory_allocated(device_index)
        memory_reserved = torch.cuda.memory_reserved(device_index)
        memory_used = max(memory_allocated, memory_reserved)

        return {
            "available": True,
            "name": props.name,
            "memory_used_mb": round(memory_used / (1024 * 1024), 1),
            "memory_total_mb": round(memory_total / (1024 * 1024), 1),
            "utilization_percent": None,
        }
    except Exception:
        return {"available": False}
