export interface ApiSettings {
  LLM_MODE: string
  LLM_BASE_URL: string
  LLM_CHAT_MODEL: string
  LLM_EXTRACTION_MODEL: string
  EMBEDDING_MODE: string
  EMBEDDING_BASE_URL: string
  EMBEDDING_MODEL: string
  EMBEDDING_DIMENSIONS: number
  LLM_API_KEY_configured: boolean
  EMBEDDING_API_KEY_configured: boolean
  active?: { LLM_MODE: string; EMBEDDING_MODE: string; EMBEDDING_MODEL: string }
}

export function createApiSettingsClient(token: () => string | null, expired: () => void) {
  async function request(method: string, path = '', body?: Record<string, unknown>): Promise<ApiSettings & { message?: string }> {
    const response = await fetch('/api/v1/api-settings' + path, {
      method,
      headers: { Authorization: `Bearer ${token() ?? ''}`, 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(25000),
    })
    const result = await response.json()
    if (response.status === 401) expired()
    if (!response.ok) throw new Error(result.message ?? '操作失败')
    return result
  }
  return {
    read: () => request('GET'),
    save: (body: Record<string, unknown>) => request('PUT', '', body),
    test: (body: Record<string, unknown>, kind: string) => request('POST', '/test', { ...body, kind }),
  }
}
