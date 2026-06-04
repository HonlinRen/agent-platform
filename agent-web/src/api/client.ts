const REQUEST_ID_HEADER = 'X-Request-Id'

export function newRequestId(): string {
  return crypto.randomUUID()
}

export function buildHeaders(
  extra: Record<string, string> = {},
  requestId?: string,
): Record<string, string> {
  return {
    [REQUEST_ID_HEADER]: requestId ?? newRequestId(),
    ...extra,
  }
}

export function readRequestId(response: Response): string | undefined {
  return response.headers.get(REQUEST_ID_HEADER) ?? undefined
}

export function parseErrorRequestId(body: string): string | undefined {
  try {
    const parsed = JSON.parse(body) as { error?: { request_id?: string } }
    return parsed.error?.request_id
  } catch {
    return undefined
  }
}

export function formatErrorWithRequestId(message: string, requestId?: string): string {
  if (!requestId) {
    return message
  }
  return `${message}（请求 ID: ${requestId}）`
}
