import type { ToolCallRecord } from '../types/chat'

interface ToolCallPanelProps {
  toolCalls: ToolCallRecord[]
}

export function ToolCallPanel({ toolCalls }: ToolCallPanelProps) {
  if (!toolCalls.length) {
    return null
  }

  return (
    <details className="mt-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
      <summary className="cursor-pointer font-medium text-slate-700">工具调用 ({toolCalls.length})</summary>
      <ul className="mt-2 space-y-2">
        {toolCalls.map((call, index) => (
          <li key={`${call.name}-${index}`} className="rounded border border-slate-100 bg-white p-2">
            <div className="font-medium text-slate-800">{call.name ?? 'unknown'}</div>
            {call.args && (
              <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-all text-[11px]">
                {JSON.stringify(call.args, null, 2)}
              </pre>
            )}
            {call.result !== undefined && (
              <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-all text-[11px] text-emerald-700">
                {typeof call.result === 'string' ? call.result : JSON.stringify(call.result, null, 2)}
              </pre>
            )}
          </li>
        ))}
      </ul>
    </details>
  )
}
