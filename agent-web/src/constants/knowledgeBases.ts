export const KNOWLEDGE_BASE_OPTIONS = [
  { id: 'white_paper_iot', label: '汽车安全' },
  { id: 'semiconductor', label: '半导体' },
] as const

export type KnowledgeBaseId = (typeof KNOWLEDGE_BASE_OPTIONS)[number]['id']

export const DEFAULT_KNOWLEDGE_BASE_ID: KnowledgeBaseId = 'white_paper_iot'

export function getKnowledgeBaseLabel(id: string): string {
  const found = KNOWLEDGE_BASE_OPTIONS.find((item) => item.id === id)
  return found?.label ?? id
}
