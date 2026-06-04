import { useEffect, useRef } from 'react'

import type { DisplayMessage } from '../types/chat'
import { MessageBubble } from './MessageBubble'

interface MessageListProps {
  messages: DisplayMessage[]
  onFeedback?: (messageId: string, rating: 'up' | 'down') => void
}

export function MessageList({ messages, onFeedback }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <div className="flex-1 space-y-4 overflow-y-auto px-4 py-6">
      {messages.length === 0 ? (
        <div className="flex h-full min-h-[320px] items-center justify-center text-center text-slate-500">
          <div>
            <p className="text-base font-medium text-slate-700">开始提问吧</p>
            <p className="mt-2 text-sm">例如：白皮书里对座舱安全有哪些要求？</p>
          </div>
        </div>
      ) : (
        messages.map((message) => <MessageBubble key={message.id} message={message} onFeedback={onFeedback} />)
      )}
      <div ref={bottomRef} />
    </div>
  )
}
