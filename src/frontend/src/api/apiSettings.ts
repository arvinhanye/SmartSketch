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
  /** 待启用（目标）向量空间：保存后需完成离线迁移才生效，不改变运行时维度 */
  EMBEDDING_TARGET_MODEL: string
  EMBEDDING_TARGET_DIMENSIONS: number
  EMBEDDING_TARGET_ASSUME_DIMENSIONS: boolean
  LLM_API_KEY_configured: boolean
  EMBEDDING_API_KEY_configured: boolean
  /** active 是本次进程实际使用的配置；target 是页面上的目标配置 */
  active?: { LLM_MODE: string; EMBEDDING_MODE: string; EMBEDDING_MODEL: string; EMBEDDING_DIMENSIONS?: number }
  target?: { model: string; dimensions: number; assumed: boolean }
}

/** 配置状态：没配好时只引导用户去「API 设置」，不假装还能用。 */
export interface ApiSettingsStatus {
  ready: boolean
  configured: boolean
  restart_needed: boolean
  missing: string[]
  active: {
    LLM_MODE: string
    LLM_CHAT_MODEL: string
    EMBEDDING_MODE: string
    EMBEDDING_MODEL: string
    EMBEDDING_DIMENSIONS: number
  }
}

/** 向量模型能力：只来自后端能力表（已核对官方文档）；未登记即 known=false，不推测。 */
export interface EmbeddingCapability {
  known: boolean
  model: string
  dimensions: number[]
  default: number | null
  flexible: 'fixed' | 'flexible' | 'unknown'
  label: string
  source: string
  provider?: string
  base_url?: string
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
    status: () => request<ApiSettingsStatus>('GET', '/status'),
    save: (body: Record<string, unknown>) => request<ApiSettings & { message?: string }>('PUT', '', body),
    test: (body: Record<string, unknown>, kind: string) => request<ConnectionResult>('POST', '/test', { ...body, kind }),
    models: (body: Record<string, unknown>, kind: string) => request<ModelDiscovery>('POST', '/models', { ...body, kind }),
    capability: (body: Record<string, unknown>, kind: string) => request<EmbeddingCapability>('POST', '/capability', { ...body, kind }),
  }
}
