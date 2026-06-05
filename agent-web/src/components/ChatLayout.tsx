import { useEffect, useState } from 'react'



import { getAuthToken, setAuthToken } from '../api/auth'

import { checkHealth } from '../api/chatStream'

import {

  CHAT_KNOWLEDGE_BASE_OPTIONS,

  DEFAULT_KNOWLEDGE_BASE_ID,

  type KnowledgeBaseId,

} from '../constants/knowledgeBases'

import { useChatStream } from '../hooks/useChatStream'

import { ChatInput } from './ChatInput'

import { ConversationSidebar } from './ConversationSidebar'

import { MessageList } from './MessageList'

import { StatusIndicator } from './StatusIndicator'



const TENANT_OPTIONS = [

  { id: 'default_tenant', label: '默认租户', rpm: 60, tpm: 2000 },

  { id: 'default_tenant_test', label: '默认租户（测试）', rpm: 2, tpm: 2000 },

  { id: 'tenant_vip', label: 'VIP 租户', rpm: 10, tpm: 10000 },

  { id: 'tenant_vip_test', label: 'VIP 租户（测试）', rpm: 2, tpm: 10000 },

] as const



export function ChatLayout() {

  const [tenantId, setTenantId] = useState<string>(TENANT_OPTIONS[0].id)

  const [collectionName, setCollectionName] = useState<KnowledgeBaseId>(DEFAULT_KNOWLEDGE_BASE_ID)

  const {

    messages,

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

    removeConversation,

    sendFeedback,

  } = useChatStream(tenantId, collectionName)

  const [backendStatus, setBackendStatus] = useState<'checking' | 'online' | 'offline'>('checking')

  const [dbStatus, setDbStatus] = useState<string>('unknown')

  const [jwtToken, setJwtToken] = useState<string>(() => getAuthToken() ?? '')



  const selectedTenant = TENANT_OPTIONS.find((item) => item.id === tenantId) ?? TENANT_OPTIONS[0]



  useEffect(() => {

    let active = true

    setBackendStatus('checking')

    checkHealth(tenantId, jwtToken || null)

      .then((result) => {

        if (active) {

          setBackendStatus('online')

          setDbStatus(result.db ?? 'unknown')

        }

      })

      .catch(() => {

        if (active) {

          setBackendStatus('offline')

          setDbStatus('error')

        }

      })

    return () => {

      active = false

    }

  }, [tenantId, jwtToken])



  const handleDeleteConversation = (targetThreadId: string) => {

    void removeConversation(targetThreadId).catch((err: unknown) => {

      console.error(err)

    })

  }



  return (

    <div className="mx-auto flex h-full max-w-6xl overflow-hidden rounded-2xl border border-slate-200 bg-slate-50 shadow-sm">

      <ConversationSidebar

        conversations={conversations}

        activeThreadId={threadId}

        isLoading={isLoadingHistory}

        disabled={isLoading}

        onSelect={(id) => {

          void loadThread(id)

        }}

        onNewChat={clearChat}

        onDelete={handleDeleteConversation}

      />



      <div className="flex min-w-0 flex-1 flex-col">

        <header className="border-b border-slate-200 bg-white px-6 py-5">

          <div className="flex items-start justify-between gap-4">

            <div>

              <h1 className="text-xl font-semibold text-slate-900">多知识库 RAG Agent</h1>

              <p className="mt-1 text-sm text-slate-500">

                LangGraph 编排 + Tool Calling + RAG，按所选知识库检索并标注来源

              </p>

            </div>

            <div className="flex items-center gap-3">

              <a

                href="/admin"

                className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 transition hover:bg-slate-100"

              >

                管理看板

              </a>

              <span

                className={`rounded-full px-3 py-1 text-xs font-medium ${

                  backendStatus === 'online'

                    ? 'bg-green-100 text-green-700'

                    : backendStatus === 'offline'

                      ? 'bg-red-100 text-red-700'

                      : 'bg-slate-100 text-slate-600'

                }`}

              >

                {backendStatus === 'online' ? '后端在线' : backendStatus === 'offline' ? '后端离线' : '检查中…'}

              </span>

              {backendStatus === 'online' ? (

                <span

                  className={`rounded-full px-3 py-1 text-xs font-medium ${

                    dbStatus === 'ok' ? 'bg-blue-100 text-blue-700' : 'bg-amber-100 text-amber-700'

                  }`}

                >

                  DB {dbStatus === 'ok' ? '已连接' : '异常'}

                </span>

              ) : null}

              <button

                type="button"

                onClick={clearChat}

                disabled={isLoading}

                className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"

              >

                清空对话

              </button>

            </div>

          </div>

          <div className="mt-3 flex flex-wrap items-center gap-3">

            <label htmlFor="kb-select" className="text-sm text-slate-600">

              知识库

            </label>

            <select

              id="kb-select"

              value={collectionName}

              onChange={(event) => {

                const next = event.target.value as KnowledgeBaseId

                if (next !== collectionName) {

                  setCollectionName(next)

                  clearChat()

                }

              }}

              disabled={isLoading}

              className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 disabled:cursor-not-allowed disabled:opacity-50"

            >

              {CHAT_KNOWLEDGE_BASE_OPTIONS.map((kb) => (

                <option key={kb.id} value={kb.id}>

                  {kb.label}

                </option>

              ))}

            </select>

            <label htmlFor="tenant-select" className="text-sm text-slate-600">

              网关租户

            </label>

            <select

              id="tenant-select"

              value={tenantId}

              onChange={(event) => setTenantId(event.target.value)}

              disabled={isLoading}

              className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 disabled:cursor-not-allowed disabled:opacity-50"

            >

              {TENANT_OPTIONS.map((tenant) => (

                <option key={tenant.id} value={tenant.id}>

                  {tenant.label}

                </option>

              ))}

            </select>

            <p className="text-xs text-slate-500">

              RPM {selectedTenant.rpm}/min · TPM {selectedTenant.tpm.toLocaleString()}/min · thread{' '}

              {threadId.slice(0, 8)}

            </p>

          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">

            <label htmlFor="jwt-token" className="text-sm text-slate-600">

              JWT（可选）

            </label>

            <input

              id="jwt-token"

              type="text"

              value={jwtToken}

              onChange={(event) => setJwtToken(event.target.value)}

              onBlur={() => {

                if (jwtToken.trim()) {

                  setAuthToken(jwtToken.trim())

                }

              }}

              placeholder="Bearer token for gateway JWT bind"

              className="min-w-[240px] flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm"

            />

          </div>

          {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}

        </header>



        <MessageList

          messages={messages}

          onFeedback={(messageId, rating) => {

            void sendFeedback(messageId, rating)

          }}

        />

        <StatusIndicator stage={stage} toolName={toolName} isLoading={isLoading || isLoadingHistory} />

        <ChatInput
          disabled={isLoadingHistory || backendStatus === 'offline'}
          isStreaming={isLoading && !isLoadingHistory}
          onSend={sendMessage}
          onStop={stopGeneration}
        />

      </div>

    </div>

  )

}

