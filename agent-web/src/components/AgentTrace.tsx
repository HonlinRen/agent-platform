interface AgentTraceProps {
  nodes: string[]
}

export function AgentTrace({ nodes }: AgentTraceProps) {
  if (!nodes.length) {
    return null
  }

  return (
    <details className="mt-2 rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-800">
      <summary className="cursor-pointer font-medium">Agent 节点轨迹 ({nodes.length})</summary>
      <ol className="mt-2 list-decimal space-y-1 pl-4">
        {nodes.map((node, index) => (
          <li key={`${node}-${index}`}>{node}</li>
        ))}
      </ol>
    </details>
  )
}
