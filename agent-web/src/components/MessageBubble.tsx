import ReactMarkdown from 'react-markdown'

import { langsmithRunUrl } from '../api/auth'
import type { DisplayMessage } from '../types/chat'
import { AgentTrace } from './AgentTrace'
import { CitationList } from './CitationList'
import { ToolCallPanel } from './ToolCallPanel'

interface MessageBubbleProps {
  message: DisplayMessage
  onFeedback?: (messageId: string, rating: 'up' | 'down') => void
}

export function MessageBubble({ message, onFeedback }: MessageBubbleProps) {
  const isUser = message.role === 'user'
  const metadata = message.metadata

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-6 shadow-sm ${
          isUser ? 'bg-blue-600 text-white' : 'border border-slate-200 bg-white text-slate-800'
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : (
          <>
            <div className="prose prose-sm max-w-none prose-p:my-2 prose-ul:my-2 prose-ol:my-2">
              {message.content ? (
                <ReactMarkdown>{message.content}</ReactMarkdown>
              ) : message.streaming ? (
                <span className="text-slate-400">…</span>
              ) : null}
              {message.streaming ? <span className="ml-1 inline-block animate-pulse text-blue-500">▍</span> : null}
            </div>
            {!message.streaming && metadata ? (
              <div className="not-prose">
                {metadata.rewrittenQuery ? (
                  <p className="mt-2 text-xs text-slate-500">改写检索：{metadata.rewrittenQuery}</p>
                ) : null}
                {metadata.route ? <p className="mt-1 text-xs text-slate-500">路由：{metadata.route}</p> : null}
                {metadata.stopped ? (
                  <p className="mt-1 text-xs text-amber-600">已手动停止生成</p>
                ) : null}
                <ToolCallPanel toolCalls={metadata.toolCalls ?? []} />
                <AgentTrace nodes={metadata.nodes ?? []} />
                <CitationList citations={metadata.citations ?? []} contextSource={metadata.contextSource} />
                {metadata.runId ? (
                  <a
                    href={langsmithRunUrl(metadata.runId)}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-2 inline-block text-xs text-blue-600 hover:underline"
                  >
                    查看 LangSmith Trace
                  </a>
                ) : null}
                {onFeedback ? (
                  <div className="mt-2 flex gap-2">
                    <button
                      type="button"
                      onClick={() => onFeedback(message.id, 'up')}
                      className="rounded border border-slate-200 px-2 py-1 text-xs hover:bg-slate-50"
                    >
                      👍
                    </button>
                    <button
                      type="button"
                      onClick={() => onFeedback(message.id, 'down')}
                      className="rounded border border-slate-200 px-2 py-1 text-xs hover:bg-slate-50"
                    >
                      👎
                    </button>
                  </div>
                ) : null}
              </div>
            ) : null}
          </>
        )}
      </div>
    </div>
  )
}
