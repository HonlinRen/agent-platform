import { useCallback, useEffect, useState } from 'react'

import { fetchGatewayMetrics, fetchRagMetrics } from '../api/adminMetrics'
import type { GatewayMetrics, RagMetrics } from '../types/admin'

const POLL_INTERVAL_MS = 5000

interface AdminMetricsState {
  rag: RagMetrics | null
  gateway: GatewayMetrics | null
  ragStatus: 'loading' | 'online' | 'offline'
  gatewayStatus: 'loading' | 'online' | 'offline'
  lastUpdated: Date | null
}

export function useAdminMetrics() {
  const [state, setState] = useState<AdminMetricsState>({
    rag: null,
    gateway: null,
    ragStatus: 'loading',
    gatewayStatus: 'loading',
    lastUpdated: null,
  })

  const refresh = useCallback(async () => {
    const [ragResult, gatewayResult] = await Promise.allSettled([
      fetchRagMetrics(),
      fetchGatewayMetrics(),
    ])

    setState({
      rag: ragResult.status === 'fulfilled' ? ragResult.value : null,
      gateway: gatewayResult.status === 'fulfilled' ? gatewayResult.value : null,
      ragStatus: ragResult.status === 'fulfilled' ? 'online' : 'offline',
      gatewayStatus: gatewayResult.status === 'fulfilled' ? 'online' : 'offline',
      lastUpdated: new Date(),
    })
  }, [])

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => {
      void refresh()
    }, POLL_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [refresh])

  return { ...state, refresh }
}
