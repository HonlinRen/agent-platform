export type ChatRole = 'user' | 'assistant'

export interface ChatMessage {
  role: ChatRole
  content: string
}

export interface Citation {
  source: string
  page: string | number
  url?: string
  type?: 'local' | 'web'
}

export interface ToolCallRecord {
  name?: string
  args?: Record<string, unknown>
  status?: 'start' | 'end'
  result?: unknown
}

export interface TurnMetadata {
  rewrittenQuery?: string
  route?: 'rag' | 'direct' | 'tool' | 'web'
  toolCalls?: ToolCallRecord[]
  nodes?: string[]
  runId?: string
  citations?: Citation[]
  contextSource?: 'local' | 'web'
  stopped?: boolean
}

export interface DisplayMessage extends ChatMessage {
  id: string
  streaming?: boolean
  metadata?: TurnMetadata
}

export type StreamStage =
  | 'rewrite'
  | 'retrieve'
  | 'generate'
  | 'router'
  | 'agent'
  | 'tools'
  | 'direct'

export interface StreamStatusEvent {
  stage: StreamStage
  node?: string
  tool_name?: string
}

export interface StreamTokenEvent {
  content: string
}

export interface StreamToolCallEvent {
  name?: string
  args?: Record<string, unknown>
  status?: 'start' | 'end'
  result?: unknown
}

export interface StreamDoneEvent {
  content: string
  rewritten_query: string
  thread_id?: string
  route?: 'rag' | 'direct' | 'tool' | 'web'
  tool_calls?: ToolCallRecord[]
  run_id?: string
  citations?: Citation[]
  context_source?: 'local' | 'web'
}

export interface StreamErrorEvent {
  message: string
}

export interface StreamCancelledEvent {
  content: string
  thread_id?: string
  stopped?: boolean
  request_id?: string
}

export type StreamEvent =
  | { type: 'status'; data: StreamStatusEvent }
  | { type: 'token'; data: StreamTokenEvent }
  | { type: 'tool_call'; data: StreamToolCallEvent }
  | { type: 'done'; data: StreamDoneEvent }
  | { type: 'cancelled'; data: StreamCancelledEvent }
  | { type: 'error'; data: StreamErrorEvent }

export interface ConversationSummary {
  thread_id: string
  title: string | null
  collection_name: string | null
  message_count: number
  updated_at: string
}

export interface HistoryMessage {
  id: string
  role: ChatRole
  content: string
  metadata?: Record<string, unknown> | null
}
