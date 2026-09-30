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

/** 一个可选模型：`id` 是实际调用用的标识，`name` 只是展示名（可能为空）。 */
export interface ModelOption {
  id: string
  name: string
}

export interface ConnectionResult {
  kind: string; ok: boolean; latency_ms: number | null; http_status: number | null
  detail: { model?: string; dimensions?: number }; provider: string; error: string | null
}

/** 模型列表发现结果；`model_options` 为规范化候选项，`models` 为兼容字段。 */
export interface ModelDiscovery {
  kind: string; ok: boolean; models: string[]; model_options?: ModelOption[]; count: number
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
