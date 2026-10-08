import { computed, onScopeDispose, reactive, ref } from 'vue'
import { AbortedError, ApiError, NetworkError, TimeoutError } from '../api/http'
import type { ModelConfig, ModelConfigApi, ModelConfigTestResult } from '../api/modelConfig'
import { useRuntimeStore, type RuntimeTicket } from '../stores/runtime'

/**
 * 模型 API 设置页的状态（L10）。
 * - 密钥只存在于表单的 `apiKey` 里，保存或测试成功后立即清空；不写入任何存储。
 * - 错误只按错误码与 `details.fields[].reason` 给固定文案，不回显服务端 message。
 * - N03/N04/N05：操作互斥、结果按会话与卸载校验、测试结果注明测试的是哪份配置。
 */

const URL_REASON: Record<string, string> = {
  scheme: '地址必须以 https:// 开头。',
  credentials: '地址里不能包含用户名或密码。',
  query: '地址里不能包含 ? 或 # 之后的内容。',
  host: '地址缺少主机名。',
  port: '地址的端口不合法。',
  unresolvable: '无法解析该地址的域名，请检查拼写。',
  private_address: '该地址指向内网或本机，出于安全原因不允许。',
}
const KEY_REASON: Record<string, string> = {
  required_when_endpoint_changes: '首次保存或修改地址时需要重新填写密钥。',
  invalid_characters: '密钥只能包含可见的英文字符，不能有空格。',
}
const TEST_TEXT: Record<string, string> = {
  auth: '密钥被拒绝，请检查密钥是否正确、是否有余额。',
  timeout: '连接超时，请检查地址或稍后重试。',
  rate_limited: '供应商限流，请稍后重试。',
  connection: '无法连接到该地址。',
  invalid_request: '供应商不接受这个请求，请检查模型名称。',
  server: '供应商服务出错，请稍后重试。',
  malformed_response: '该地址的响应不是兼容的对话接口格式。',
  stream_interrupted: '连接中断，请重试。',
  blocked_address: '该地址指向内网或本机，或不是 https 地址。',
}

function fieldReason(cause: unknown): { field: string; reason: string } | null {
  if (!(cause instanceof ApiError) || cause.code !== 'VALIDATION_ERROR') return null
  const fields = cause.details?.fields
  if (!Array.isArray(fields) || fields.length === 0) return null
  const first = fields[0] as { field?: unknown; reason?: unknown }
  return typeof first.field === 'string' && typeof first.reason === 'string' ? { field: first.field, reason: first.reason } : null
}

function failureText(cause: unknown, fallback: string): string {
  const hit = fieldReason(cause)
  if (hit?.field === 'base_url') return URL_REASON[hit.reason] ?? '地址不符合要求。'
  if (hit?.field === 'api_key') return KEY_REASON[hit.reason] ?? '密钥不符合要求。'
  if (hit !== null) return '请检查填写的内容。'
  if (cause instanceof ApiError && cause.code === 'RATE_LIMITED') return '操作过于频繁，请稍后再试。'
  if (cause instanceof ApiError && cause.code === 'MODEL_CONFIG_REQUIRED') return '请先保存配置再测试。'
  if (cause instanceof ApiError && cause.code === 'STORAGE_UNAVAILABLE') return '服务端未启用个人模型凭据存储，请联系部署者。'
  if (cause instanceof ApiError && cause.status === 401) return '登录已失效，请重新登录。'
  if (cause instanceof NetworkError || cause instanceof TimeoutError) return '无法连接服务器，请检查网络后重试。'
  return fallback
}

type Busy = 'loading' | 'saving' | 'testing' | 'clearing'

export function useModelConfig({ api, syncRuntime = true }: { api: ModelConfigApi; syncRuntime?: boolean }) {
  const runtime = useRuntimeStore()
  const controller = new AbortController()
  let disposed = false
  onScopeDispose(() => {
    disposed = true
    controller.abort()
  })

  const status = ref<'loading' | 'ready' | 'error'>('loading')
  const saved = ref<ModelConfig | null>(null)
  // ADR-090：disableThinking 是「关闭模型思考」开关，与地址、模型一起保存
  const form = reactive({ baseUrl: '', model: '', apiKey: '', disableThinking: false })
  /** N04：加载、保存、测试、清除互斥；按钮与逻辑入口都据此拒绝第二个操作 */
  const busy = ref<Busy | null>(null)
  const saving = computed(() => busy.value === 'saving')
  const testing = computed(() => busy.value === 'testing')
  const clearing = computed(() => busy.value === 'clearing')
  const error = ref<string | null>(null)
  const notice = ref<string | null>(null)
  const testResult = ref<{ ok: boolean; text: string } | null>(null)

  const configured = computed(() => saved.value?.configured === true)
  /** 首次保存或地址与已存值不同：必须填密钥（与后端规则一致，避免已存密钥被改送到新主机） */
  const keyRequired = computed(() => !configured.value || form.baseUrl.trim() !== saved.value?.base_url)

  function adopt(config: ModelConfig): void {
    saved.value = config
    form.baseUrl = config.base_url ?? ''
    form.model = config.model ?? ''
    form.apiKey = ''
    form.disableThinking = config.disable_thinking ?? false
  }

  /** 开关与已存值不同才发送（省略即保留已存值；新建配置的已存值视为关闭） */
  function thinkingChange(): { disable_thinking?: boolean } {
    return form.disableThinking !== (saved.value?.disable_thinking ?? false) ? { disable_thinking: form.disableThinking } : {}
  }

  /** 结果是否仍属于本页面与发起时的会话（卸载或换号后一律丢弃，N03/N04） */
  function current(ticket: RuntimeTicket): boolean {
    return !disposed && ticket.owner === runtime.owner
  }

  async function load(): Promise<void> {
    if (busy.value !== null) return
    busy.value = 'loading'
    status.value = 'loading'
    const ticket = runtime.claim()
    try {
      const config = await api.get({ signal: controller.signal })
      if (!current(ticket)) return
      if (syncRuntime) runtime.commitRead(ticket, config)
      adopt(config)
      status.value = 'ready'
    } catch (cause) {
      if (cause instanceof AbortedError || !current(ticket)) return
      error.value = failureText(cause, '配置加载失败，请稍后重试。')
      status.value = 'error'
    } finally {
      if (busy.value === 'loading') busy.value = null
    }
  }

  async function save(): Promise<void> {
    if (busy.value !== null) return
    error.value = notice.value = null
    const baseUrl = form.baseUrl.trim()
    const model = form.model.trim()
    if (baseUrl === '' || model === '') {
      error.value = '请填写服务地址和模型名称。'
      return
    }
    if (keyRequired.value && form.apiKey === '') {
      error.value = configured.value ? '修改地址时需要重新填写密钥。' : '请填写密钥。'
      return
    }
    busy.value = 'saving'
    const ticket = runtime.claim()
    try {
      const body = form.apiKey === ''
        ? { base_url: baseUrl, model, ...thinkingChange() }
        : { base_url: baseUrl, model, api_key: form.apiKey, ...thinkingChange() }
      const config = await api.save(body, { signal: controller.signal })
      if (!current(ticket) || (syncRuntime && !runtime.commitWrite(ticket, config))) return
      adopt(config)
      testResult.value = null
      notice.value = '已保存。已创建的任务仍使用保存前的配置。'
    } catch (cause) {
      if (cause instanceof AbortedError || !current(ticket)) return
      error.value = failureText(cause, '保存失败，请稍后重试。')
    } finally {
      if (busy.value === 'saving') busy.value = null
    }
  }

  async function test(): Promise<void> {
    if (busy.value !== null) return
    error.value = null
    testResult.value = null
    const tested = { baseUrl: form.baseUrl.trim(), model: form.model.trim(), apiKey: form.apiKey,
      disableThinking: form.disableThinking }
    // N05：只有地址与模型都与已存值一致且密钥留空时，测试的才是「已保存的配置」；
    // 其余情况测试表单里这组完整的值，或要求先保存——不能让旧配置的结果冒充编辑中的新值。
    const usesForm = tested.apiKey !== ''
    if (!usesForm) {
      if (!configured.value) {
        error.value = '请先填写密钥，或保存配置后再测试。'
        return
      }
      if (tested.baseUrl !== saved.value?.base_url || tested.model !== saved.value?.model) {
        error.value = '地址或模型已修改：请先保存，或填写密钥后测试这组新值。'
        return
      }
      if (tested.disableThinking !== (saved.value?.disable_thinking ?? false)) {
        error.value = '「关闭模型思考」开关已修改：请先保存，或填写密钥后测试这组新值。'
        return
      }
    }
    const label = usesForm ? '表单中的配置（尚未保存）' : '已保存的配置'
    busy.value = 'testing'
    const ticket = runtime.claim()
    try {
      const body = usesForm
        ? { base_url: tested.baseUrl, model: tested.model, api_key: tested.apiKey,
            ...(tested.disableThinking ? { disable_thinking: true } : {}) }
        : undefined
      const result: ModelConfigTestResult = await api.test(body, { signal: controller.signal, timeoutMs: 30_000 })
      if (!current(ticket)) return
      const edited = usesForm
        && (form.baseUrl.trim() !== tested.baseUrl || form.model.trim() !== tested.model || form.apiKey !== tested.apiKey
          || form.disableThinking !== tested.disableThinking)
      if (edited) {
        testResult.value = { ok: false, text: '测试期间表单已修改，本次结果已作废，请重新测试。' }
        return
      }
      testResult.value = result.ok
        ? { ok: true, text: `${label}：连接成功（${result.latency_ms} 毫秒）。` }
        : { ok: false, text: `${label}：${TEST_TEXT[result.error_class ?? ''] ?? '连接失败。'}` }
    } catch (cause) {
      if (cause instanceof AbortedError || !current(ticket)) return
      error.value = failureText(cause, '测试失败，请稍后重试。')
    } finally {
      if (busy.value === 'testing') busy.value = null
    }
  }

  async function clear(): Promise<void> {
    if (busy.value !== null) return
    error.value = notice.value = null
    busy.value = 'clearing'
    const ticket = runtime.claim()
    try {
      await api.clear({ signal: controller.signal })
      const cleared: ModelConfig = { runtime_mode: saved.value?.runtime_mode ?? 'personal', configured: false }
      if (!current(ticket) || (syncRuntime && !runtime.commitWrite(ticket, cleared))) return
      adopt(cleared)
      testResult.value = null
      notice.value = '已清除。尚未结束的任务会终止，需要重新上传。'
    } catch (cause) {
      if (cause instanceof AbortedError || !current(ticket)) return
      error.value = failureText(cause, '清除失败，请稍后重试。')
    } finally {
      if (busy.value === 'clearing') busy.value = null
    }
  }

  void load()
  return { status, saved, form, configured, keyRequired, busy, saving, testing, clearing, error, notice, testResult, load, save, test, clear }
}
