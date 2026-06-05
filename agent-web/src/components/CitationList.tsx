import type { Citation } from '../types/chat'

interface CitationListProps {
  citations: Citation[]
  contextSource?: 'local' | 'web'
}

export function CitationList({ citations, contextSource }: CitationListProps) {
  if (!citations.length && contextSource !== 'web') {
    return null
  }

  return (
    <div className="mt-2 space-y-2">
      {contextSource === 'web' ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          本回答参考互联网公开信息，非本地知识库内容，请自行核实。
        </div>
      ) : null}
      {citations.length ? (
        <div className="rounded-md border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
          <div className="font-medium">{contextSource === 'web' ? '互联网来源' : '引用来源'}</div>
          <ul className="mt-1 list-disc pl-4">
            {citations.map((item, index) => (
              <li key={`${item.source}-${item.page}-${index}`}>
                {item.type === 'web' && item.url ? (
                  <a href={item.url} target="_blank" rel="noreferrer" className="text-blue-700 hover:underline">
                    {item.source}
                  </a>
                ) : (
                  <>
                    {item.source} 第{item.page}页
                  </>
                )}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
