const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

export const GRAFANA_DASHBOARD_URL =
  import.meta.env.VITE_GRAFANA_URL ?? 'http://localhost:3000/d/agent-observability'

export const PROMETHEUS_URL = import.meta.env.VITE_PROMETHEUS_URL ?? 'http://localhost:9090'

export const RAG_PROMETHEUS_METRICS_URL = API_BASE
  ? `${API_BASE}/admin/rag/prometheus`
  : 'http://127.0.0.1:8080/admin/rag/prometheus'
