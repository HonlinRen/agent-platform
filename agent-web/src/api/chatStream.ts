import type { ChatMessage, StreamEvent } from '../types/chat'
import { buildHeaders, formatErrorWithRequestId, parseErrorRequestId, readRequestId } from './client'
import { toUserFacingError } from '../utils/userError'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

export interface ChatStreamPayload {
  message: string
  history: ChatMessage[]
  thread_id?: string
  collection_name?: string
  user_message_id?: string
  assistant_message_id?: string
}

function parseRateLimitError(detail: string, status: number, requestId?: string): string {
  try {
    const parsed = JSON.parse(detail) as { error?: { message?: string; type?: string; request_id?: string } }
    const rid = parsed.error?.request_id ?? requestId
    if (parsed.error?.type === 'rate_limit_exceeded') {
      return formatErrorWithRequestId('请求过于频繁或超出 Token 配额，请稍后再试', rid)
    }
    if (parsed.error?.message) {
      return formatErrorWithRequestId(toUserFacingError(parsed.error.message), rid)
    }
  } catch {
    // ignore non-JSON body
  }
  return formatErrorWithRequestId(toUserFacingError(detail) || `请求失败 (${status})`, requestId)
}

function parseSseBlock(block: string): StreamEvent | null {
  const lines = block.split('\n')
  let eventType = 'message'
  const dataLines: string[] = []

  for (const line of lines) {
    if (line.startsWith('event:')) {
      eventType = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim())
    }
  }

  if (dataLines.length === 0) {
    return null
  }

  const payload = JSON.parse(dataLines.join('\n')) as Record<string, unknown>

  switch (eventType) {
    case 'status':
      return { type: 'status', data: payload as StreamEvent extends { type: 'status' } ? StreamEvent['data'] : never }
    case 'token':
      return { type: 'token', data: payload as StreamEvent extends { type: 'token' } ? StreamEvent['data'] : never }
    case 'tool_call':
      return {
        type: 'tool_call',
        data: payload as StreamEvent extends { type: 'tool_call' } ? StreamEvent['data'] : never,
      }
    case 'done':
      return { type: 'done', data: payload as StreamEvent extends { type: 'done' } ? StreamEvent['data'] : never }
    case 'cancelled':
      return {
        type: 'cancelled',
        data: payload as StreamEvent extends { type: 'cancelled' } ? StreamEvent['data'] : never,
      }
    case 'error':
      return { type: 'error', data: payload as StreamEvent extends { type: 'error' } ? StreamEvent['data'] : never }
    default:
      return null
  }
}

export async function stopChat(
  threadId: string,
  tenantId: string,
  authToken?: string | null,
): Promise<{ ok: boolean; cancelled: boolean }> {
  const headers = buildHeaders({
    'Content-Type': 'application/json',
    'X-Tenant-Id': tenantId,
    'X-Thread-Id': threadId,
    ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
  })
  const response = await fetch(`${API_BASE}/api/chat/stop`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ thread_id: threadId }),
  })
  if (!response.ok) {
    throw new Error(formatErrorWithRequestId(`停止请求失败 (${response.status})`, readRequestId(response)))
  }
  return response.json()
}

export async function* streamChat(
  payload: ChatStreamPayload,
  tenantId: string,
  signal?: AbortSignal,
  authToken?: string | null,
): AsyncGenerator<StreamEvent> {
  const headers = buildHeaders(
    {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      'X-Tenant-Id': tenantId,
      ...(payload.thread_id ? { 'X-Thread-Id': payload.thread_id } : {}),
      ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    },
  )

  const response = await fetch(`${API_BASE}/api/chat/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
    signal,
  })

  const responseRequestId = readRequestId(response) ?? headers['X-Request-Id']

  if (!response.ok) {
    const detail = await response.text()
    const requestId = parseErrorRequestId(detail) ?? responseRequestId
    throw new Error(parseRateLimitError(detail, response.status, requestId))
  }

  if (!response.body) {
    throw new Error(formatErrorWithRequestId('响应体为空', responseRequestId))
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }

    buffer += decoder.decode(value, { stream: true })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''

    for (const block of blocks) {
      const trimmed = block.trim()
      if (!trimmed) {
        continue
      }
      const event = parseSseBlock(trimmed)
      if (event) {
        if (event.type === 'error') {
          const rid = (event.data as { request_id?: string }).request_id ?? responseRequestId
          throw new Error(formatErrorWithRequestId(toUserFacingError(event.data.message), rid))
        }
        yield event
      }
    }
  }

  const trailing = buffer.trim()
  if (trailing) {
    const event = parseSseBlock(trailing)
    if (event) {
      yield event
    }
  }
}

export async function checkHealth(tenantId: string, authToken?: string | null): Promise<{ status: string; collection: string; db?: string }> {
  const headers = buildHeaders({
    'X-Tenant-Id': tenantId,
    ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
  })
  const response = await fetch(`${API_BASE}/health`, { headers })
  if (!response.ok) {
    throw new Error(formatErrorWithRequestId(`健康检查失败 (${response.status})`, readRequestId(response)))
  }
  return response.json()
}

export async function submitFeedback(payload: {
  thread_id: string
  message_id: string
  rating: 'up' | 'down'
  comment?: string
}, tenantId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/chat/feedback`, {
    method: 'POST',
    headers: buildHeaders({
      'Content-Type': 'application/json',
      'X-Tenant-Id': tenantId,
    }),
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error(formatErrorWithRequestId('反馈提交失败', readRequestId(response)))
  }
}
