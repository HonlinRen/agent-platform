import {
  GRAFANA_DASHBOARD_URL,
  PROMETHEUS_URL,
  RAG_PROMETHEUS_METRICS_URL,
} from '../constants/observability'
import { useAdminMetrics } from '../hooks/useAdminMetrics'
import type { GatewayMetrics, RagMetrics, TimingMetricSummary, TimingStatsResponse } from '../types/admin'

function formatTimestamp(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString()
}

function formatSeconds(value: number | null | undefined): string {
  if (value == null) {
    return '—'
  }
  if (value < 1) {
    return `${(value * 1000).toFixed(0)} ms`
  }
  return `${value.toFixed(2)} s`
}

function formatMilliseconds(value: number | null | undefined): string {
  if (value == null) {
    return '—'
  }
  if (value < 1000) {
    return `${value} ms`
  }
  return `${(value / 1000).toFixed(2)} s`
}

function formatScore(value: number | null | undefined): string {
  if (value == null) {
    return '—'
  }
  return value.toFixed(3)
}

function formatUptime(seconds: number): string {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = seconds % 60
  if (hours > 0) {
    return `${hours} 小时 ${minutes} 分`
  }
  if (minutes > 0) {
    return `${minutes} 分 ${secs} 秒`
  }
  return `${secs} 秒`
}

function ProgressBar({ label, value, max, suffix }: { label: string; value: number; max: number; suffix?: string }) {
  const percent = max > 0 ? Math.min(100, (value / max) * 100) : 0
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-sm">
        <span className="text-slate-600">{label}</span>
        <span className="font-medium text-slate-900">
          {value.toFixed(1)}
          {suffix ?? ''} / {max.toFixed(1)}
          {suffix ?? ''} ({percent.toFixed(0)}%)
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-200">
        <div className="h-full rounded-full bg-blue-600 transition-all" style={{ width: `${percent}%` }} />
      </div>
    </div>
  )
}

function MetricCard({ title, value, subtitle }: { title: string; value: number | string; subtitle?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <p className="text-sm text-slate-500">{title}</p>
      <p className="mt-2 text-2xl font-semibold text-slate-900">{value}</p>
      {subtitle ? <p className="mt-1 text-xs text-slate-400">{subtitle}</p> : null}
    </div>
  )
}

function ObservabilityLinks({ rag }: { rag: RagMetrics | null }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <h3 className="font-medium text-slate-900">观测与 Prometheus</h3>
      <p className="mt-1 text-xs text-slate-500">
        时序曲线请用 Grafana；原始 /metrics 顶部有 ISO 注释，响应头含 X-Metrics-Scrape-At。
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <a
          href={GRAFANA_DASHBOARD_URL}
          target="_blank"
          rel="noreferrer"
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 transition hover:bg-slate-100"
        >
          Grafana 仪表盘
        </a>
        <a
          href={PROMETHEUS_URL}
          target="_blank"
          rel="noreferrer"
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 transition hover:bg-slate-100"
        >
          Prometheus
        </a>
        <a
          href={RAG_PROMETHEUS_METRICS_URL}
          target="_blank"
          rel="noreferrer"
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 transition hover:bg-slate-100"
        >
          RAG 原始 metrics
        </a>
      </div>
      {rag ? (
        <dl className="mt-4 grid gap-2 text-sm sm:grid-cols-2">
          <div className="flex justify-between gap-4 rounded-lg bg-slate-50 px-3 py-2">
            <dt className="text-slate-500">JSON 采集时间</dt>
            <dd className="font-medium text-slate-900">{formatTimestamp(rag.collected_at)}</dd>
          </div>
          <div className="flex justify-between gap-4 rounded-lg bg-slate-50 px-3 py-2">
            <dt className="text-slate-500">进程启动</dt>
            <dd className="font-medium text-slate-900">{formatTimestamp(rag.process_started_at)}</dd>
          </div>
          {rag.build_version ? (
            <div className="flex justify-between gap-4 rounded-lg bg-slate-50 px-3 py-2">
              <dt className="text-slate-500">构建版本</dt>
              <dd className="font-medium text-slate-900">{rag.build_version}</dd>
            </div>
          ) : null}
        </dl>
      ) : null}
    </div>
  )
}

function StatusBadge({ status }: { status: 'loading' | 'online' | 'offline' }) {
  const className =
    status === 'online'
      ? 'bg-green-100 text-green-700'
      : status === 'offline'
        ? 'bg-red-100 text-red-700'
        : 'bg-slate-100 text-slate-600'
  const label = status === 'online' ? '在线' : status === 'offline' ? '离线' : '加载中'
  return <span className={`rounded-full px-3 py-1 text-xs font-medium ${className}`}>{label}</span>
}

function RagDashboard({ metrics }: { metrics: RagMetrics | null }) {
  if (!metrics) {
    return <p className="text-sm text-slate-500">RAG 服务不可用</p>
  }

  const gpu = metrics.system.gpu
  const gpuPercent =
    gpu.available && gpu.memory_total_mb && gpu.memory_used_mb
      ? (gpu.memory_used_mb / gpu.memory_total_mb) * 100
      : 0
  const summary = metrics.summary
  const nodeAvgs = summary?.node_duration_avg_seconds ?? {}

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <MetricCard title="Qwen LLM 调用" value={metrics.llm_requests_total.toLocaleString()} subtitle="累计次数" />
        <MetricCard title="Embedding 调用" value={metrics.embedding_requests_total.toLocaleString()} subtitle="累计次数" />
        <MetricCard title="Rerank 重排序" value={metrics.rerank_requests_total.toLocaleString()} subtitle="累计次数" />
        <MetricCard
          title="Tool 调用"
          value={(metrics.tool_calls_total ?? 0).toLocaleString()}
          subtitle="Agent 工具累计"
        />
        <MetricCard
          title="Tavily 联网检索"
          value={(metrics.tavily_calls_total ?? 0).toLocaleString()}
          subtitle={`成功 ${metrics.tavily_calls_ok ?? 0} / 无结果 ${metrics.tavily_calls_empty ?? 0} / 失败 ${metrics.tavily_calls_error ?? 0}`}
        />
      </div>

      {summary ? (
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <h3 className="font-medium text-slate-900">Prometheus 观测摘要</h3>
          <p className="mt-1 text-xs text-slate-400">进程内 histogram 累计均值（非 rate）</p>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard
              title="端到端请求"
              value={formatSeconds(summary.agent_request_avg_seconds)}
              subtitle="agent_request 平均耗时"
            />
            <MetricCard
              title="Chroma 检索"
              value={formatSeconds(summary.chroma_query_avg_seconds)}
              subtitle="向量查询平均耗时"
            />
            <MetricCard
              title="Rerank"
              value={formatSeconds(summary.rerank_avg_seconds)}
              subtitle="重排序平均耗时"
            />
            <MetricCard
              title="Top-1 分数"
              value={formatScore(summary.retrieval_top1_score_avg)}
              subtitle="召回质量均值"
            />
          </div>
          {Object.keys(nodeAvgs).length > 0 ? (
            <dl className="mt-4 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
              {Object.entries(nodeAvgs).map(([node, avg]) => (
                <div key={node} className="flex justify-between gap-4 rounded-lg bg-slate-50 px-3 py-2">
                  <dt className="text-slate-500">{node}</dt>
                  <dd className="font-medium text-slate-900">{formatSeconds(avg)}</dd>
                </div>
              ))}
            </dl>
          ) : null}
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-4">
          <h3 className="font-medium text-slate-900">系统资源</h3>
          <ProgressBar
            label="系统内存"
            value={metrics.system.system_memory.used_mb}
            max={metrics.system.system_memory.total_mb}
            suffix=" MB"
          />
          <ProgressBar
            label="进程内存"
            value={metrics.system.process_memory_mb}
            max={metrics.system.system_memory.total_mb}
            suffix=" MB"
          />
          <ProgressBar label="系统 CPU" value={metrics.system.cpu_percent.system} max={100} suffix="%" />
          <ProgressBar label="进程 CPU" value={metrics.system.cpu_percent.process} max={100} suffix="%" />
          {gpu.available ? (
            <ProgressBar
              label={`GPU 显存 (${gpu.name ?? 'GPU'})`}
              value={gpu.memory_used_mb ?? 0}
              max={gpu.memory_total_mb ?? 1}
              suffix=" MB"
            />
          ) : (
            <p className="text-sm text-slate-500">GPU 不可用</p>
          )}
          {gpu.available ? <p className="text-xs text-slate-400">GPU 显存占用 {gpuPercent.toFixed(0)}%</p> : null}
        </div>

        <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-4">
          <h3 className="font-medium text-slate-900">服务信息</h3>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between gap-4">
              <dt className="text-slate-500">LLM 模型</dt>
              <dd className="font-medium text-slate-900">{metrics.config.llm_model}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-slate-500">Embedding 模型</dt>
              <dd className="font-medium text-slate-900">{metrics.config.embedding_model}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-slate-500">Rerank</dt>
              <dd className="font-medium text-slate-900">{metrics.config.rerank_enabled ? '已启用' : '未启用'}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-slate-500">运行时长</dt>
              <dd className="font-medium text-slate-900">{formatUptime(metrics.uptime_seconds)}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-slate-500">进程启动</dt>
              <dd className="font-medium text-slate-900">{formatTimestamp(metrics.process_started_at)}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-slate-500">服务端采集</dt>
              <dd className="font-medium text-slate-900">{formatTimestamp(metrics.collected_at)}</dd>
            </div>
            {metrics.build_version ? (
              <div className="flex justify-between gap-4">
                <dt className="text-slate-500">构建版本</dt>
                <dd className="font-medium text-slate-900">{metrics.build_version}</dd>
              </div>
            ) : null}
          </dl>
        </div>
      </div>
    </div>
  )
}

const OPERATION_LABELS: Record<string, string> = {
  router: '路由',
  rewrite: 'Query Rewrite',
  generate: '生成回答',
  agent: 'Agent',
  direct_reply: '直接回复',
  summary_update: '会话摘要（后置）',
  tenant_profile: '租户画像（后置）',
}

function DistributionChart({ title, metric }: { title: string; metric: TimingMetricSummary }) {
  const maxCount = Math.max(1, ...metric.distribution.map((item) => item.count))
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <h4 className="font-medium text-slate-900">{title}</h4>
      <p className="mt-1 text-xs text-slate-400">
        样本 {metric.count.toLocaleString()} · 平均 {formatMilliseconds(metric.avg_ms)} · P50{' '}
        {formatMilliseconds(metric.p50_ms)} · P90 {formatMilliseconds(metric.p90_ms)}
      </p>
      {metric.count === 0 ? (
        <p className="mt-3 text-sm text-slate-500">暂无数据</p>
      ) : (
        <div className="mt-4 space-y-2">
          {metric.distribution.map((item) => (
            <div key={item.bucket}>
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="text-slate-500">{item.bucket}</span>
                <span className="font-medium text-slate-700">{item.count}</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-slate-200">
                <div
                  className="h-full rounded-full bg-indigo-500 transition-all"
                  style={{ width: `${(item.count / maxCount) * 100}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function TimingDashboard({ metrics, status }: { metrics: TimingStatsResponse | null; status: 'loading' | 'online' | 'offline' }) {
  if (status === 'offline' || !metrics) {
    return <p className="text-sm text-slate-500">耗时统计不可用（需 MySQL 持久化与历史问答数据）</p>
  }

  const llmOps = Object.entries(metrics.llm.by_operation ?? {})

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3 text-sm text-slate-500">
        <span>租户：{metrics.tenant_id}</span>
        <span>·</span>
        <span>最近 {metrics.period_days} 天</span>
        <span>·</span>
        <span>问答轮次 {metrics.total_runs.toLocaleString()}</span>
        <span>·</span>
        <span>采集 {formatTimestamp(metrics.collected_at)}</span>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard title="整体耗时（平均）" value={formatMilliseconds(metrics.overall.avg_ms)} subtitle="单轮 SSE 应答完成" />
        <MetricCard title="Embedding（平均）" value={formatMilliseconds(metrics.embedding.avg_ms)} subtitle="DashScope 向量化" />
        <MetricCard title="Chroma 检索（平均）" value={formatMilliseconds(metrics.chroma.avg_ms)} subtitle="向量库 query" />
        <MetricCard title="Rerank（平均）" value={formatMilliseconds(metrics.rerank.avg_ms)} subtitle="BGE 重排序" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <DistributionChart title="整体耗时分布" metric={metrics.overall} />
        <DistributionChart title="Embedding 耗时分布" metric={metrics.embedding} />
        <DistributionChart title="Chroma 检索耗时分布" metric={metrics.chroma} />
        <DistributionChart title="Rerank 耗时分布" metric={metrics.rerank} />
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <h3 className="font-medium text-slate-900">Qwen 调用耗时</h3>
        <p className="mt-1 text-xs text-slate-400">
          每次 LLM invoke 单独计时；一轮 Agent 可能包含多次调用
        </p>
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <DistributionChart title="全部 LLM 调用分布" metric={metrics.llm} />
          <div className="overflow-hidden rounded-xl border border-slate-200">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-left text-slate-500">
                  <th className="px-4 py-3 font-medium">操作</th>
                  <th className="px-4 py-3 font-medium">次数</th>
                  <th className="px-4 py-3 font-medium">平均耗时</th>
                </tr>
              </thead>
              <tbody>
                {llmOps.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="px-4 py-3 text-slate-500">
                      暂无 LLM 调用记录
                    </td>
                  </tr>
                ) : (
                  llmOps.map(([operation, item]) => (
                    <tr key={operation} className="border-b border-slate-100">
                      <td className="px-4 py-3 font-medium text-slate-900">
                        {OPERATION_LABELS[operation] ?? operation}
                      </td>
                      <td className="px-4 py-3">{item.count.toLocaleString()}</td>
                      <td className="px-4 py-3">{formatMilliseconds(item.avg_ms)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}

function GatewayDashboard({ metrics }: { metrics: GatewayMetrics | null }) {
  if (!metrics || metrics.tenants.length === 0) {
    return <p className="text-sm text-slate-500">Gateway 服务不可用</p>
  }

  const tenantLabels: Record<string, string> = {
    default_tenant: '默认租户',
    default_tenant_test: '默认租户（测试）',
    tenant_vip: 'VIP 租户',
    tenant_vip_test: 'VIP 租户（测试）',
  }

  return (
    <div className="space-y-6">
      {metrics.tenants.map((tenant) => (
        <div key={tenant.tenant_id} className="overflow-hidden rounded-xl border border-slate-200 bg-white">
          <div className="border-b border-slate-200 bg-slate-50 px-4 py-3">
            <h3 className="font-medium text-slate-900">
              {tenantLabels[tenant.tenant_id] ?? tenant.tenant_id}
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-slate-500">
                  <th className="px-4 py-3 font-medium">维度</th>
                  <th className="px-4 py-3 font-medium">限额/分钟</th>
                  <th className="px-4 py-3 font-medium">当前剩余</th>
                  <th className="px-4 py-3 font-medium">累计通过/消耗</th>
                  <th className="px-4 py-3 font-medium">触发限流</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-slate-100">
                  <td className="px-4 py-3 font-medium text-slate-900">RPM</td>
                  <td className="px-4 py-3">{tenant.rpm.limit}</td>
                  <td className="px-4 py-3">{tenant.rpm.remaining}</td>
                  <td className="px-4 py-3">{tenant.rpm.allowed_total?.toLocaleString() ?? 0}</td>
                  <td className="px-4 py-3">
                    {tenant.rpm.rejected_total > 0 ? (
                      <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
                        {tenant.rpm.rejected_total}
                      </span>
                    ) : (
                      <span className="text-slate-400">0</span>
                    )}
                  </td>
                </tr>
                <tr className="border-b border-slate-100">
                  <td className="px-4 py-3 font-medium text-slate-900">TPM 输入</td>
                  <td className="px-4 py-3">{tenant.tpm_input.limit.toLocaleString()}</td>
                  <td className="px-4 py-3">{tenant.tpm_input.remaining.toLocaleString()}</td>
                  <td className="px-4 py-3">{tenant.tpm_input.tokens_total?.toLocaleString() ?? 0} tokens</td>
                  <td className="px-4 py-3">
                    {tenant.tpm_input.rejected_total > 0 ? (
                      <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
                        {tenant.tpm_input.rejected_total}
                      </span>
                    ) : (
                      <span className="text-slate-400">0</span>
                    )}
                  </td>
                </tr>
                <tr>
                  <td className="px-4 py-3 font-medium text-slate-900">TPM 输出</td>
                  <td className="px-4 py-3">{tenant.tpm_output.limit.toLocaleString()}</td>
                  <td className="px-4 py-3">{tenant.tpm_output.remaining.toLocaleString()}</td>
                  <td className="px-4 py-3">{tenant.tpm_output.tokens_total?.toLocaleString() ?? 0} tokens</td>
                  <td className="px-4 py-3">
                    {tenant.tpm_output.rejected_total > 0 ? (
                      <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
                        {tenant.tpm_output.rejected_total}
                      </span>
                    ) : (
                      <span className="text-slate-400">0</span>
                    )}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  )
}

export function AdminPage() {
  const { rag, gateway, timing, ragStatus, gatewayStatus, timingStatus, lastUpdated, refresh } = useAdminMetrics()

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="rounded-2xl border border-slate-200 bg-white px-6 py-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold text-slate-900">系统管理看板</h1>
            <p className="mt-1 text-sm text-slate-500">RAG 资源、问答耗时与 Gateway 限流统计，每 5 秒自动刷新</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <StatusBadge status={ragStatus} />
            <span className="text-xs text-slate-400">RAG</span>
            <StatusBadge status={gatewayStatus} />
            <span className="text-xs text-slate-400">Gateway</span>
            <StatusBadge status={timingStatus} />
            <span className="text-xs text-slate-400">耗时</span>
            <button
              type="button"
              onClick={() => void refresh()}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 transition hover:bg-slate-100"
            >
              立即刷新
            </button>
            <a
              href="/"
              className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-blue-700"
            >
              返回聊天
            </a>
          </div>
        </div>
        {lastUpdated ? (
          <p className="mt-3 text-xs text-slate-400">
            客户端刷新：{lastUpdated.toLocaleTimeString()}
            {rag?.collected_at ? ` · RAG 服务端采集：${formatTimestamp(rag.collected_at)}` : null}
            {gateway?.collected_at ? ` · Gateway 采集：${formatTimestamp(gateway.collected_at)}` : null}
          </p>
        ) : null}
      </div>

      <section className="rounded-2xl border border-slate-200 bg-slate-50 p-6 shadow-sm">
        <h2 className="mb-4 text-lg font-semibold text-slate-900">观测与 Prometheus</h2>
        <ObservabilityLinks rag={rag} />
      </section>

      <section className="rounded-2xl border border-slate-200 bg-slate-50 p-6 shadow-sm">
        <h2 className="mb-4 text-lg font-semibold text-slate-900">RAG 资源看板</h2>
        <RagDashboard metrics={rag} />
      </section>

      <section className="rounded-2xl border border-slate-200 bg-slate-50 p-6 shadow-sm">
        <h2 className="mb-4 text-lg font-semibold text-slate-900">问答耗时统计</h2>
        <TimingDashboard metrics={timing} status={timingStatus} />
      </section>

      <section className="rounded-2xl border border-slate-200 bg-slate-50 p-6 shadow-sm">
        <h2 className="mb-4 text-lg font-semibold text-slate-900">Gateway 限流看板</h2>
        <GatewayDashboard metrics={gateway} />
      </section>
    </div>
  )
}
