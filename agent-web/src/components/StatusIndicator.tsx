import type { StreamStage } from '../types/chat'

const STAGE_LABELS: Record<StreamStage, string> = {
  rewrite: '正在改写问题…',
  retrieve: '正在检索知识库…',
  generate: '正在生成回答…',
  router: '正在路由意图…',
  agent: 'Agent 正在决策…',
  tools: '正在调用工具…',
  direct: '正在直接回答…',
}

interface StatusIndicatorProps {
  stage: StreamStage | null
  toolName?: string | null
  isLoading: boolean
}

export function StatusIndicator({ stage, toolName, isLoading }: StatusIndicatorProps) {
  if (!isLoading) {
    return null
  }

  let label = stage ? STAGE_LABELS[stage] : '正在处理…'
  if (toolName) {
    label = `正在调用 ${toolName}…`
  }

  return (
    <div className="flex items-center gap-2 px-4 py-2 text-sm text-slate-500">
      <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-blue-500" />
      <span>{label}</span>
    </div>
  )
}
