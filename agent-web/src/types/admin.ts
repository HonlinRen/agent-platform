export interface RagPrometheusSummary {

  agent_request_avg_seconds?: number | null

  chroma_query_avg_seconds?: number | null

  rerank_avg_seconds?: number | null

  retrieval_top1_score_avg?: number | null

  node_duration_avg_seconds?: Record<string, number>

}



export interface RagMetrics {

  llm_requests_total: number

  embedding_requests_total: number

  rerank_requests_total: number

  tool_calls_total?: number

  tavily_calls_total?: number

  tavily_calls_ok?: number

  tavily_calls_empty?: number

  tavily_calls_error?: number

  collection: {

    name: string

    label?: string

    document_count: number

  }

  config: {

    llm_model: string

    embedding_model: string

    rerank_enabled: boolean

  }

  system: {

    process_memory_mb: number

    system_memory: {

      total_mb: number

      used_mb: number

      percent: number

    }

    cpu_percent: {

      system: number

      process: number

    }

    gpu: {

      available: boolean

      name?: string

      memory_used_mb?: number

      memory_total_mb?: number

      utilization_percent?: number | null

    }

  }

  uptime_seconds: number

  collected_at: string

  process_started_at: string

  build_version?: string

  summary?: RagPrometheusSummary | null

}



export interface GatewayDimensionMetrics {

  limit: number

  remaining: number

  allowed_total?: number

  rejected_total: number

  tokens_total?: number

}



export interface GatewayTenantMetrics {

  tenant_id: string

  rpm: GatewayDimensionMetrics

  tpm_input: GatewayDimensionMetrics

  tpm_output: GatewayDimensionMetrics

}



export interface GatewayMetrics {

  collected_at?: string

  tenants: GatewayTenantMetrics[]

}



export interface TimingDistributionBucket {

  bucket: string

  count: number

}



export interface TimingMetricSummary {

  avg_ms?: number | null

  p50_ms?: number | null

  p90_ms?: number | null

  count: number

  distribution: TimingDistributionBucket[]

}



export interface TimingOperationSummary {

  count: number

  avg_ms?: number | null

}



export interface TimingLlmSummary extends TimingMetricSummary {

  by_operation: Record<string, TimingOperationSummary>

}



export interface TimingStatsResponse {

  tenant_id: string

  period_days: number

  total_runs: number

  collected_at: string

  overall: TimingMetricSummary

  embedding: TimingMetricSummary

  chroma: TimingMetricSummary

  rerank: TimingMetricSummary

  llm: TimingLlmSummary

}

