import type { ConversationSummary, HistoryMessage } from '../types/chat'
import { buildHeaders, formatErrorWithRequestId, readRequestId } from './client'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

export async function listConversations(
  tenantId: string,
  limit = 50,
  offset = 0,
): Promise<ConversationSummary[]> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  const response = await fetch(`${API_BASE}/api/chat/conversations?${params}`, {
    headers: buildHeaders({ 'X-Tenant-Id': tenantId }),
  })
  if (!response.ok) {
    throw new Error(formatErrorWithRequestId(`加载会话列表失败 (${response.status})`, readRequestId(response)))
  }
  const data = (await response.json()) as { conversations: ConversationSummary[] }
  return data.conversations
}

export async function getChatHistory(tenantId: string, threadId: string): Promise<{
  thread_id: string
  collection_name: string | null
  messages: HistoryMessage[]
}> {
  const params = new URLSearchParams({ thread_id: threadId })
  const response = await fetch(`${API_BASE}/api/chat/history?${params}`, {
    headers: buildHeaders({ 'X-Tenant-Id': tenantId }),
  })
  if (response.status === 404) {
    throw new Error('会话不存在')
  }
  if (!response.ok) {
    throw new Error(formatErrorWithRequestId(`加载历史失败 (${response.status})`, readRequestId(response)))
  }
  return response.json()
}

export async function deleteConversation(tenantId: string, threadId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/chat/conversations/${threadId}`, {
    method: 'DELETE',
    headers: buildHeaders({ 'X-Tenant-Id': tenantId }),
  })
  if (response.status === 404) {
    throw new Error('会话不存在')
  }
  if (!response.ok) {
    throw new Error(formatErrorWithRequestId(`删除会话失败 (${response.status})`, readRequestId(response)))
  }
}
