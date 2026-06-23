from __future__ import annotations

import api.env  # noqa: F401 — load .env before DB and other config

import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from email.utils import format_datetime

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from api.admin import router as admin_router
from api.chat import router as chat_router
from api.conversations import router as conversations_router
from api.deps import get_default_assistant
from api.feedback import router as feedback_router
from api.profile import router as profile_router
from api.ingest import router as ingest_router
from api.schemas import HealthResponse, KnowledgeBasesResponse
from db.session import init_db, ping_db
from rag.logging_config import configure_logging
from rag.checkpoint import get_checkpointer
from rag.knowledge_bases import DEFAULT_COLLECTION, list_knowledge_bases
from rag.telemetry import (
    HTTP_REQUEST_DURATION,
    init_instrumentation,
    init_tracing,
    instrument_fastapi,
    metrics_response,
    normalize_http_path,
    resolve_request_id,
)

API_HOST = os.environ.get("API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("API_PORT", "8081"))
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if origin.strip()
]

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    init_tracing()
    init_instrumentation()
    app.state.assistants = {}
    get_checkpointer()
    try:
        init_db()
    except Exception:
        from db.config import get_mysql_password

        log = logging.getLogger(__name__)
        if not get_mysql_password():
            log.error(
                "MySQL init failed: MySql_Password is not set. "
                "Add it to agent-rag/.env and restart the server."
            )
        else:
            log.exception("MySQL init failed; conversation persistence disabled")
    app.state.assistant = get_default_assistant(app)
    yield


app = FastAPI(title="汽车安全白皮书助手 API", lifespan=lifespan)
instrument_fastapi(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    request_id = resolve_request_id(request.headers.get("X-Request-Id"))
    start = time.perf_counter()
    response: Response = await call_next(request)
    duration = time.perf_counter() - start
    path = normalize_http_path(request)
    status = str(response.status_code)
    HTTP_REQUEST_DURATION.labels(method=request.method, path=path, status=status).observe(duration)
    response.headers["X-Request-Id"] = request_id
    return response


app.include_router(chat_router)
app.include_router(conversations_router)
app.include_router(feedback_router)
app.include_router(profile_router)
app.include_router(admin_router)
app.include_router(ingest_router)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    db_status = "ok" if ping_db() else "error"
    return HealthResponse(status="ok", collection=DEFAULT_COLLECTION, db=db_status)


@app.get("/api/knowledge-bases", response_model=KnowledgeBasesResponse)
def knowledge_bases() -> KnowledgeBasesResponse:
    return KnowledgeBasesResponse(knowledge_bases=list_knowledge_bases())


@app.get("/metrics")
def prometheus_metrics() -> Response:
    body, content_type, metric_headers = metrics_response()
    headers = {
        "Date": format_datetime(datetime.now(timezone.utc), usegmt=True),
        **metric_headers,
    }
    return Response(content=body, media_type=content_type, headers=headers)
