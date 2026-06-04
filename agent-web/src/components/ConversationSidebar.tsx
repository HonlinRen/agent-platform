import type { ConversationSummary } from '../types/chat'

interface ConversationSidebarProps {
  conversations: ConversationSummary[]
  activeThreadId: string
  isLoading: boolean
  disabled?: boolean
  onSelect: (threadId: string) => void
  onNewChat: () => void
  onDelete: (threadId: string) => void
}

function formatTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return ''
  }
  return date.toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function ConversationSidebar({
  conversations,
  activeThreadId,
  isLoading,
  disabled = false,
  onSelect,
  onNewChat,
  onDelete,
}: ConversationSidebarProps) {
  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="border-b border-slate-200 p-4">
        <button
          type="button"
          onClick={onNewChat}
          disabled={disabled}
          className="w-full rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          新建对话
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {isLoading ? <p className="px-2 py-3 text-sm text-slate-500">加载会话中…</p> : null}
        {!isLoading && conversations.length === 0 ? (
          <p className="px-2 py-3 text-sm text-slate-500">暂无历史会话</p>
        ) : null}

        <ul className="space-y-1">
          {conversations.map((item) => {
            const isActive = item.thread_id === activeThreadId
            const title = item.title?.trim() || '新对话'
            return (
              <li key={item.thread_id}>
                <div
                  className={`group flex items-start gap-2 rounded-lg px-2 py-2 ${
                    isActive ? 'bg-slate-100' : 'hover:bg-slate-50'
                  }`}
                >
                  <button
                    type="button"
                    disabled={disabled}
                    onClick={() => onSelect(item.thread_id)}
                    className="min-w-0 flex-1 text-left disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <p className="truncate text-sm font-medium text-slate-900">{title}</p>
                    <p className="mt-0.5 text-xs text-slate-500">
                      {formatTime(item.updated_at)} · {item.message_count} 条
                    </p>
                  </button>
                  <button
                    type="button"
                    disabled={disabled}
                    onClick={() => onDelete(item.thread_id)}
                    title="删除会话"
                    className="rounded px-1.5 py-0.5 text-xs text-slate-400 opacity-0 transition hover:bg-red-50 hover:text-red-600 group-hover:opacity-100 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    删
                  </button>
                </div>
              </li>
            )
          })}
        </ul>
      </div>
    </aside>
  )
}
