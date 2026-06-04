const DEFAULT_ERROR = '服务暂时不可用，请稍后重试'

const TECHNICAL_MARKERS = [
  'request_id',
  'status_code',
  'invalidparameter',
  'url error',
  'traceback',
  'dashscope',
  'openai',
  'httpx',
]

export function toUserFacingError(message: string | undefined | null): string {
  const raw = (message ?? '').trim()
  if (!raw) {
    return DEFAULT_ERROR
  }

  const lower = raw.toLowerCase()
  if (lower.includes('rate_limit') || lower.includes('too many requests') || lower.includes('quota')) {
    return '请求过于频繁，请稍后再试'
  }
  if (lower.includes('401') || lower.includes('403') || lower.includes('api key') || lower.includes('unauthorized')) {
    return '服务认证失败，请联系管理员'
  }
  if (lower.includes('invalidparameter') || lower.includes('url error')) {
    return '模型服务暂时不可用，请稍后重试'
  }
  if (TECHNICAL_MARKERS.some((marker) => lower.includes(marker))) {
    return DEFAULT_ERROR
  }
  if (raw.length <= 80) {
    return raw
  }
  return DEFAULT_ERROR
}
