from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatStreamRequest(BaseModel):
    message: str
    history: list[ChatMessage] = Field(default_factory=list)
    thread_id: str | None = None
    collection_name: str | None = None
    user_message_id: str | None = None
    assistant_message_id: str | None = None


class ChatStopRequest(BaseModel):
    thread_id: str


class ChatStopResponse(BaseModel):
    ok: bool = True
    cancelled: bool = False


class ChatFeedbackRequest(BaseModel):
    thread_id: str
    message_id: str
    rating: Literal["up", "down"]
    comment: str = ""


class HealthResponse(BaseModel):
    status: str
    collection: str
    db: str = "unknown"


class ConversationSummary(BaseModel):
    thread_id: str
    title: str | None = None
    collection_name: str | None = None
    message_count: int
    updated_at: datetime


class ConversationsResponse(BaseModel):
    conversations: list[ConversationSummary]


class HistoryMessage(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    metadata: dict[str, Any] | None = None


class ChatHistoryResponse(BaseModel):
    thread_id: str
    collection_name: str | None = None
    conversation_summary: str | None = None
    messages: list[HistoryMessage]


class TenantProfileData(BaseModel):
    focus_domains: list[str] = Field(default_factory=list)
    preferred_answer_style: str = ""
    common_systems: list[str] = Field(default_factory=list)
    notes: str = ""


class TenantProfileResponse(BaseModel):
    tenant_id: str
    profile: TenantProfileData
    profile_summary: str | None = None
    source: Literal["auto", "manual"] = "auto"
    updated_at: datetime | None = None


class TenantProfileUpdateRequest(BaseModel):
    profile: TenantProfileData
    profile_summary: str | None = None


class KnowledgeBaseItem(BaseModel):
    id: str
    label: str


class KnowledgeBasesResponse(BaseModel):
    knowledge_bases: list[KnowledgeBaseItem]


class RagCollectionInfo(BaseModel):
    name: str
    document_count: int
    label: str | None = None


class RagConfigInfo(BaseModel):
    llm_model: str
    embedding_model: str
    rerank_enabled: bool


class RagSystemMemory(BaseModel):
    total_mb: float
    used_mb: float
    percent: float


class RagCpuInfo(BaseModel):
    system: float
    process: float


class RagGpuInfo(BaseModel):
    available: bool
    name: str | None = None
    memory_used_mb: float | None = None
    memory_total_mb: float | None = None
    utilization_percent: float | None = None


class RagSystemInfo(BaseModel):
    process_memory_mb: float
    system_memory: RagSystemMemory
    cpu_percent: RagCpuInfo
    gpu: RagGpuInfo


class RagPrometheusSummary(BaseModel):
    agent_request_avg_seconds: float | None = None
    chroma_query_avg_seconds: float | None = None
    rerank_avg_seconds: float | None = None
    retrieval_top1_score_avg: float | None = None
    node_duration_avg_seconds: dict[str, float] = Field(default_factory=dict)


class RagMetricsResponse(BaseModel):
    llm_requests_total: int
    embedding_requests_total: int
    rerank_requests_total: int
    tool_calls_total: int = 0
    tavily_calls_total: int = 0
    tavily_calls_ok: int = 0
    tavily_calls_empty: int = 0
    tavily_calls_error: int = 0
    collection: RagCollectionInfo
    config: RagConfigInfo
    system: RagSystemInfo
    uptime_seconds: int
    collected_at: datetime
    process_started_at: datetime
    build_version: str = "dev"
    summary: RagPrometheusSummary | None = None


class IngestJobResponse(BaseModel):
    job_id: str
    status: Literal["pending", "running", "completed", "failed"]
    message: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)


class TimingDistributionBucket(BaseModel):
    bucket: str
    count: int


class TimingMetricSummary(BaseModel):
    avg_ms: int | None = None
    p50_ms: int | None = None
    p90_ms: int | None = None
    count: int = 0
    distribution: list[TimingDistributionBucket] = Field(default_factory=list)


class TimingOperationSummary(BaseModel):
    count: int
    avg_ms: int | None = None


class TimingLlmSummary(TimingMetricSummary):
    by_operation: dict[str, TimingOperationSummary] = Field(default_factory=dict)


class TimingStatsResponse(BaseModel):
    tenant_id: str
    period_days: int
    total_runs: int
    collected_at: datetime
    overall: TimingMetricSummary
    embedding: TimingMetricSummary
    chroma: TimingMetricSummary
    rerank: TimingMetricSummary
    llm: TimingLlmSummary
