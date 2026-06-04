import type { Citation } from '../types/chat'

interface CitationListProps {
  citations: Citation[]
}

export function CitationList({ citations }: CitationListProps) {
  if (!citations.length) {
    return null
  }

  return (
    <div className="mt-2 rounded-md border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
      <div className="font-medium">引用来源</div>
      <ul className="mt-1 list-disc pl-4">
        {citations.map((item, index) => (
          <li key={`${item.source}-${item.page}-${index}`}>
            {item.source} 第{item.page}页
          </li>
        ))}
      </ul>
    </div>
  )
}
