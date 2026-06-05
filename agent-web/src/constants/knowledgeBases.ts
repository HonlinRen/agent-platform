import kbConfig from '../../config/knowledge-bases.json'

export const KNOWLEDGE_BASE_CATALOG = [
  { id: 'white_paper_iot', label: '汽车安全' },
  { id: 'semiconductor', label: '半导体' },
] as const

export type CatalogKnowledgeBaseId = (typeof KNOWLEDGE_BASE_CATALOG)[number]['id']

type KnowledgeBasesConfig = {
  visibleInChat: string[]
  defaultChatCollection: string
}

const config = kbConfig as KnowledgeBasesConfig

function buildChatOptions() {
  const catalogById = new Map(KNOWLEDGE_BASE_CATALOG.map((item) => [item.id, item]))
  const options: { id: CatalogKnowledgeBaseId; label: string }[] = []

  for (const id of config.visibleInChat) {
    const entry = catalogById.get(id as CatalogKnowledgeBaseId)
    if (entry) {
      options.push({ id: entry.id, label: entry.label })
    } else {
      console.error(`[knowledge-bases] visibleInChat id "${id}" is not in KNOWLEDGE_BASE_CATALOG`)
    }
  }

  return options
}

export const CHAT_KNOWLEDGE_BASE_OPTIONS = buildChatOptions()

export type KnowledgeBaseId = (typeof CHAT_KNOWLEDGE_BASE_OPTIONS)[number]['id']

function resolveDefaultId(): KnowledgeBaseId {
  const preferred = config.defaultChatCollection
  const validIds = new Set(CHAT_KNOWLEDGE_BASE_OPTIONS.map((item) => item.id))

  if (preferred && validIds.has(preferred as KnowledgeBaseId)) {
    return preferred as KnowledgeBaseId
  }

  if (preferred) {
    console.error(
      `[knowledge-bases] defaultChatCollection "${preferred}" is invalid; falling back to first visible option`,
    )
  }

  const fallback = CHAT_KNOWLEDGE_BASE_OPTIONS[0]?.id
  if (!fallback) {
    throw new Error('[knowledge-bases] visibleInChat is empty or has no catalog matches')
  }

  return fallback
}

export const DEFAULT_KNOWLEDGE_BASE_ID = resolveDefaultId()

export function getKnowledgeBaseLabel(id: string): string {
  const found = KNOWLEDGE_BASE_CATALOG.find((item) => item.id === id)
  return found?.label ?? id
}
