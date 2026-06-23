import type { GatewayMetrics, RagMetrics, TimingStatsResponse } from '../types/admin'
import { buildHeaders, formatErrorWithRequestId, readRequestId } from './client'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

export async function fetchRagMetrics(collectionName?: string): Promise<RagMetrics> {
  const params = collectionName ? `?collection=${encodeURIComponent(collectionName)}` : ''
  const response = await fetch(`${API_BASE}/admin/rag/metrics${params}`, {
    headers: buildHeaders(),
  })
  if (!response.ok) {
    throw new Error(formatErrorWithRequestId(`RAG metrics 请求失败 (${response.status})`, readRequestId(response)))
  }
  return response.json()
}

export async function fetchTimingStats(days = 7): Promise<TimingStatsResponse> {
  const response = await fetch(`${API_BASE}/admin/rag/timing-stats?days=${days}`, {
    headers: buildHeaders(),
  })
  if (!response.ok) {
    throw new Error(formatErrorWithRequestId(`Timing stats 请求失败 (${response.status})`, readRequestId(response)))
  }
  return response.json()
}

export async function fetchGatewayMetrics(): Promise<GatewayMetrics> {
  const response = await fetch(`${API_BASE}/admin/gateway/metrics`, {
    headers: buildHeaders(),
  })
  if (!response.ok) {
    throw new Error(formatErrorWithRequestId(`Gateway metrics 请求失败 (${response.status})`, readRequestId(response)))
  }
  return response.json()
}
