export interface ApiSettings {
  LLM_MODE: string
  LLM_BASE_URL: string
  LLM_CHAT_MODEL: string
  LLM_EXTRACTION_MODEL: string
  LLM_PROVIDER_LABEL: string
  EMBEDDING_MODE: string
  EMBEDDING_BASE_URL: string
  EMBEDDING_MODEL: string
  EMBEDDING_DIMENSIONS: number
  EMBEDDING_PROVIDER_LABEL: string
  LLM_API_KEY_configured: boolean
  EMBEDDING_API_KEY_configured: boolean
  active?: { LLM_MODE: string; EMBEDDING_MODE: string; EMBEDDING_MODEL: string }
}

export interface ConnectionResult {
  kind: string; ok: boolean; latency_ms: number | null; http_status: number | null
  detail: { model?: string; dimensions?: number }; provider: string; error: string | null
}
export interface ModelDiscovery {
  kind: string; ok: boolean; models: string[]; count: number
  latency_ms: number | null; provider: string; error: string | null
}

export function createApiSettingsClient(token: () => string | null, expired: () => void) {
  async function request<T>(method: string, path = '', body?: Record<string, unknown>): Promise<T> {
    const response = await fetch('/api/v1/api-settings' + path, {
      method,
      headers: { Authorization: `Bearer ${token() ?? ''}`, 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(30000),
    })
    const result = await response.json()
    if (response.status === 401) expired()
    if (!response.ok) throw new Error(result.message ?? '操作失败')
    return result
  }
  return {
    read: () => request<ApiSettings>('GET'),
    save: (body: Record<string, unknown>) => request<ApiSettings & { message?: string }>('PUT', '', body),
    test: (body: Record<string, unknown>, kind: string) => request<ConnectionResult>('POST', '/test', { ...body, kind }),
    models: (body: Record<string, unknown>, kind: string) => request<ModelDiscovery>('POST', '/models', { ...body, kind }),
  }
}
