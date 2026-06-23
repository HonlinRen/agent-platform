import { useCallback, useEffect, useState } from 'react'

import { fetchGatewayMetrics, fetchRagMetrics, fetchTimingStats } from '../api/adminMetrics'
import type { GatewayMetrics, RagMetrics, TimingStatsResponse } from '../types/admin'

const POLL_INTERVAL_MS = 5000

interface AdminMetricsState {
  rag: RagMetrics | null
  gateway: GatewayMetrics | null
  timing: TimingStatsResponse | null
  ragStatus: 'loading' | 'online' | 'offline'
  gatewayStatus: 'loading' | 'online' | 'offline'
  timingStatus: 'loading' | 'online' | 'offline'
  lastUpdated: Date | null
}

export function useAdminMetrics() {
  const [state, setState] = useState<AdminMetricsState>({
    rag: null,
    gateway: null,
    timing: null,
    ragStatus: 'loading',
    gatewayStatus: 'loading',
    timingStatus: 'loading',
    lastUpdated: null,
  })

  const refresh = useCallback(async () => {
    const [ragResult, gatewayResult, timingResult] = await Promise.allSettled([
      fetchRagMetrics(),
      fetchGatewayMetrics(),
      fetchTimingStats(7),
    ])

    setState({
      rag: ragResult.status === 'fulfilled' ? ragResult.value : null,
      gateway: gatewayResult.status === 'fulfilled' ? gatewayResult.value : null,
      timing: timingResult.status === 'fulfilled' ? timingResult.value : null,
      ragStatus: ragResult.status === 'fulfilled' ? 'online' : 'offline',
      gatewayStatus: gatewayResult.status === 'fulfilled' ? 'online' : 'offline',
      timingStatus: timingResult.status === 'fulfilled' ? 'online' : 'offline',
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
