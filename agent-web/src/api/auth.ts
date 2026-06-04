const AUTH_TOKEN_KEY = 'agent_web_jwt'

export function getAuthToken(): string | null {
  return localStorage.getItem(AUTH_TOKEN_KEY)
}

export function setAuthToken(token: string): void {
  localStorage.setItem(AUTH_TOKEN_KEY, token)
}

export function clearAuthToken(): void {
  localStorage.removeItem(AUTH_TOKEN_KEY)
}

export function langsmithRunUrl(runId: string): string {
  const project = import.meta.env.VITE_LANGSMITH_PROJECT ?? 'agent-rag'
  return `https://smith.langchain.com/o/default/projects/p/${project}/r/${runId}`
}
