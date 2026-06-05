import { useCallback, useEffect, useRef, useState } from 'react'

import { getAuthToken } from '../api/auth'
import { deleteConversation, getChatHistory, listConversations } from '../api/conversations'
import { stopChat, streamChat, submitFeedback } from '../api/chatStream'
import type {
  ChatMessage,
  ConversationSummary,
  DisplayMessage,
  HistoryMessage,
  StreamStage,
  ToolCallRecord,
  TurnMetadata,
} from '../types/chat'
import { toUserFacingError } from '../utils/userError'

const WINDOW_SIZE = 5
const ACTIVE_THREAD_KEY_PREFIX = 'agent_web:active_thread:'

function createId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

function createThreadId(): string {
  return crypto.randomUUID()
}

function trimHistory(history: ChatMessage[]): ChatMessage[] {
  return history.slice(-WINDOW_SIZE * 2)
}

function activeThreadKey(tenantId: string): string {
  return `${ACTIVE_THREAD_KEY_PREFIX}${tenantId}`
}

function readStoredThreadId(tenantId: string): string | null {
  try {
    return localStorage.getItem(activeThreadKey(tenantId))
  } catch {
    return null
  }
}

function writeStoredThreadId(tenantId: string, threadId: string): void {
  try {
    localStorage.setItem(activeThreadKey(tenantId), threadId)
  } catch {
    // ignore quota / private mode
  }
}

function metadataFromApi(raw: Record<string, unknown> | null | undefined): TurnMetadata | undefined {
  if (!raw) {
    return undefined
  }
  return {
    rewrittenQuery: (raw.rewritten_query as string | undefined) ?? (raw.rewrittenQuery as string | undefined),
    route: raw.route as TurnMetadata['route'],
    toolCalls: (raw.tool_calls as ToolCallRecord[] | undefined) ?? (raw.toolCalls as ToolCallRecord[] | undefined),
    runId: (raw.run_id as string | undefined) ?? (raw.runId as string | undefined),
    citations: raw.citations as TurnMetadata['citations'],
    contextSource:
      (raw.context_source as TurnMetadata['contextSource']) ??
      (raw.contextSource as TurnMetadata['contextSource']),
    stopped: raw.stopped as boolean | undefined,
  }
}

function historyToDisplayMessages(messages: HistoryMessage[]): { display: DisplayMessage[]; history: ChatMessage[] } {
  const display: DisplayMessage[] = messages.map((msg) => ({
    id: msg.id,
    role: msg.role,
    content: msg.content,
    metadata: metadataFromApi(msg.metadata ?? undefined),
  }))
  const history: ChatMessage[] = messages.map((msg) => ({ role: msg.role, content: msg.content }))
  return { display, history: trimHistory(history) }
}

export function useChatStream(tenantId: string, collectionName: string) {
  const [messages, setMessages] = useState<DisplayMessage[]>([])
  const [history, setHistory] = useState<ChatMessage[]>([])
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [stage, setStage] = useState<StreamStage | null>(null)
  const [toolName, setToolName] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isLoadingHistory, setIsLoadingHistory] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [threadId, setThreadId] = useState<string>(() => createThreadId())
  const abortRef = useRef<AbortController | null>(null)
  const activeAssistantIdRef = useRef<string | null>(null)
  const skipAbortFinalizeRef = useRef(false)
  const tenantIdRef = useRef(tenantId)

  const loadConversations = useCallback(async () => {
    try {
      const rows = await listConversations(tenantId)
      setConversations(rows)
      return rows
    } catch {
      setConversations([])
      return []
    }
  }, [tenantId])

  const loadThread = useCallback(
    async (nextThreadId: string) => {
      abortRef.current?.abort()
      abortRef.current = null
      setIsLoadingHistory(true)
      setError(null)
      try {
        const data = await getChatHistory(tenantId, nextThreadId)
        const { display, history: nextHistory } = historyToDisplayMessages(data.messages)
        setThreadId(nextThreadId)
        writeStoredThreadId(tenantId, nextThreadId)
        setMessages(display)
        setHistory(nextHistory)
      } catch (err) {
        const messageText = toUserFacingError(err instanceof Error ? err.message : undefined)
        setError(messageText)
        setThreadId(nextThreadId)
        writeStoredThreadId(tenantId, nextThreadId)
        setMessages([])
        setHistory([])
      } finally {
        setIsLoadingHistory(false)
        setStage(null)
        setToolName(null)
        setIsLoading(false)
      }
    },
    [tenantId],
  )

  const clearChat = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    const nextThreadId = createThreadId()
    setMessages([])
    setHistory([])
    setStage(null)
    setToolName(null)
    setIsLoading(false)
    setError(null)
    setThreadId(nextThreadId)
    writeStoredThreadId(tenantId, nextThreadId)
  }, [tenantId])

  const removeConversation = useCallback(
    async (targetThreadId: string) => {
      await deleteConversation(tenantId, targetThreadId)
      setConversations((prev) => prev.filter((item) => item.thread_id !== targetThreadId))
      if (targetThreadId === threadId) {
        clearChat()
      }
    },
    [clearChat, tenantId, threadId],
  )

  useEffect(() => {
    tenantIdRef.current = tenantId
    let active = true

    async function bootstrap() {
      const rows = await loadConversations()
      if (!active) {
        return
      }

      const storedThreadId = readStoredThreadId(tenantId)
      const candidate =
        storedThreadId && rows.some((item) => item.thread_id === storedThreadId)
          ? storedThreadId
          : rows[0]?.thread_id

      if (candidate) {
        await loadThread(candidate)
      } else {
        const nextThreadId = createThreadId()
        setThreadId(nextThreadId)
        writeStoredThreadId(tenantId, nextThreadId)
        setMessages([])
        setHistory([])
      }
    }

    void bootstrap()
    return () => {
      active = false
    }
  }, [tenantId, loadConversations, loadThread])

  const sendFeedback = useCallback(
    async (messageId: string, rating: 'up' | 'down') => {
      await submitFeedback({ thread_id: threadId, message_id: messageId, rating }, tenantId)
    },
    [tenantId, threadId],
  )

  const finalizeStoppedAssistant = useCallback(
    (assistantId: string, assistantContent: string, turnMetadata: TurnMetadata, userMessageContent: string) => {
      const content = assistantContent.trim()
      setMessages((prev) =>
        prev
          .map((item) =>
            item.id === assistantId
              ? {
                  ...item,
                  content: assistantContent,
                  streaming: false,
                  metadata: { ...turnMetadata, stopped: true },
                }
              : item,
          )
          .filter((item) => item.id !== assistantId || content.length > 0),
      )
      if (content) {
        setHistory((prev) =>
          trimHistory([
            ...prev,
            { role: 'user', content: userMessageContent },
            { role: 'assistant', content: assistantContent },
          ]),
        )
        void loadConversations()
      }
    },
    [loadConversations],
  )

  const stopGeneration = useCallback(() => {
    if (!abortRef.current) {
      return
    }
    skipAbortFinalizeRef.current = true
    const assistantId = activeAssistantIdRef.current
    abortRef.current.abort()
    abortRef.current = null
    void stopChat(threadId, tenantIdRef.current, getAuthToken()).catch(() => {
      // stream may already have ended
    })
    setIsLoading(false)
    setStage(null)
    setToolName(null)
    activeAssistantIdRef.current = null
    if (assistantId) {
      setMessages((prev) =>
        prev.map((item) =>
          item.id === assistantId && item.streaming
            ? { ...item, streaming: false, metadata: { ...item.metadata, stopped: true } }
            : item,
        ),
      )
    }
  }, [threadId])

  const sendMessage = useCallback(
    async (rawMessage: string) => {
      const message = rawMessage.trim()
      if (!message || isLoading) {
        return
      }

      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      const userMessage: DisplayMessage = {
        id: createId(),
        role: 'user',
        content: message,
      }
      const assistantId = createId()
      activeAssistantIdRef.current = assistantId
      const assistantPlaceholder: DisplayMessage = {
        id: assistantId,
        role: 'assistant',
        content: '',
        streaming: true,
        metadata: { toolCalls: [], nodes: [] },
      }

      setError(null)
      setIsLoading(true)
      setStage(null)
      setToolName(null)
      setMessages((prev) => [...prev, userMessage, assistantPlaceholder])

      let assistantContent = ''
      let turnMetadata: TurnMetadata = { toolCalls: [], nodes: [] }

      try {
        for await (const event of streamChat(
          {
            message,
            history,
            thread_id: threadId,
            collection_name: collectionName,
            user_message_id: userMessage.id,
            assistant_message_id: assistantId,
          },
          tenantId,
          controller.signal,
          getAuthToken(),
        )) {
          if (event.type === 'status') {
            setStage(event.data.stage)
            setToolName(event.data.tool_name ?? null)
            if (event.data.node) {
              turnMetadata = {
                ...turnMetadata,
                nodes: [...(turnMetadata.nodes ?? []), event.data.node],
              }
            }
          } else if (event.type === 'tool_call') {
            const record: ToolCallRecord = {
              name: event.data.name,
              args: event.data.args,
              status: event.data.status,
              result: event.data.result,
            }
            turnMetadata = {
              ...turnMetadata,
              toolCalls: [...(turnMetadata.toolCalls ?? []), record],
            }
            if (event.data.name) {
              setToolName(event.data.name)
            }
          } else if (event.type === 'token') {
            assistantContent += event.data.content
            setMessages((prev) =>
              prev.map((item) =>
                item.id === assistantId
                  ? { ...item, content: assistantContent, streaming: true, metadata: { ...turnMetadata } }
                  : item,
              ),
            )
          } else if (event.type === 'done') {
            assistantContent = event.data.content || assistantContent
            if (event.data.thread_id) {
              setThreadId(event.data.thread_id)
              writeStoredThreadId(tenantIdRef.current, event.data.thread_id)
            }
            turnMetadata = {
              ...turnMetadata,
              rewrittenQuery: event.data.rewritten_query,
              route: event.data.route,
              toolCalls: event.data.tool_calls ?? turnMetadata.toolCalls,
              runId: event.data.run_id,
              citations: event.data.citations,
              contextSource: event.data.context_source,
            }
            setMessages((prev) =>
              prev.map((item) =>
                item.id === assistantId
                  ? { ...item, content: assistantContent, streaming: false, metadata: { ...turnMetadata } }
                  : item,
              ),
            )
            setHistory((prev) =>
              trimHistory([...prev, { role: 'user', content: message }, { role: 'assistant', content: assistantContent }]),
            )
            void loadConversations()
            activeAssistantIdRef.current = null
          } else if (event.type === 'cancelled') {
            assistantContent = event.data.content || assistantContent
            if (event.data.thread_id) {
              setThreadId(event.data.thread_id)
              writeStoredThreadId(tenantIdRef.current, event.data.thread_id)
            }
            turnMetadata = { ...turnMetadata, stopped: true }
            finalizeStoppedAssistant(assistantId, assistantContent, turnMetadata, message)
            activeAssistantIdRef.current = null
          } else if (event.type === 'error') {
            throw new Error(event.data.message)
          }
        }
      } catch (err) {
        if (controller.signal.aborted) {
          if (!skipAbortFinalizeRef.current) {
            finalizeStoppedAssistant(assistantId, assistantContent, { ...turnMetadata, stopped: true }, message)
          }
          skipAbortFinalizeRef.current = false
          activeAssistantIdRef.current = null
          return
        }
        const messageText = toUserFacingError(err instanceof Error ? err.message : undefined)
        setError(messageText)
        setMessages((prev) =>
          prev
            .map((item) =>
              item.id === assistantId
                ? { ...item, content: assistantContent, streaming: false, metadata: { ...turnMetadata } }
                : item,
            )
            .filter((item) => item.id !== assistantId || item.content.trim().length > 0),
        )
      } finally {
        setIsLoading(false)
        setStage(null)
        setToolName(null)
        abortRef.current = null
        activeAssistantIdRef.current = null
      }
    },
    [collectionName, finalizeStoppedAssistant, history, isLoading, loadConversations, tenantId, threadId],
  )

  return {
    messages,
    history,
    conversations,
    stage,
    toolName,
    threadId,
    isLoading,
    isLoadingHistory,
    error,
    sendMessage,
    stopGeneration,
    clearChat,
    loadThread,
    loadConversations,
    removeConversation,
    sendFeedback,
  }
}
