<script setup lang="ts">
/**
 * 教师 API 设置页。
 *
 * - 大模型与向量接口各自独立：候选列表、请求状态、错误信息互不影响；
 * - 模型用可搜索选择器（ModelSelect）选择，展示名称与调用 ID 分开，保存与调用一律用 ID；
 * - 大模型一处配置即同时用于聊天与知识抽取（保存时写入 LLM_CHAT_MODEL 与 LLM_EXTRACTION_MODEL）；
 * - 页面不再提供「运行模式」下拉：大模型配置完整并保存后即为在线模式，缺失项给出明确提示；
 * - 向量接口只读展示当前生效状态，切换向量模型仍需离线迁移，页面不提供切换入口。
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { createApiSettingsClient, type ConnectionResult, type EmbeddingCapability, type ModelOption } from '../api/apiSettings'
import { refreshConfigStatus } from '../composables/useConfigStatus'
import { useSessionStore } from '../stores/session'
import ConnectionResultDialog from '../components/ConnectionResultDialog.vue'
import ModelSelect from '../components/ModelSelect.vue'

type Kind = 'llm' | 'embedding'

interface Provider {
  id: string
  label: string
  url: string
  /** 模型列表路径，缺省 /models */
  listPath?: string
  /** 需要用户补全（区域、账户或专属接入地址）时的提示 */
  note?: string
}

/** 服务商预设：只填地址（个别带模型列表路径），不预置任何模型或密钥。 */
const PROVIDERS: Provider[] = [
  { id: 'deepseek', label: 'DeepSeek', url: 'https://api.deepseek.com/v1' },
  { id: 'dashscope', label: '阿里云百炼（通义）', url: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
  { id: 'openai', label: 'OpenAI', url: 'https://api.openai.com/v1' },
  { id: 'moonshot', label: '月之暗面 Kimi', url: 'https://api.moonshot.cn/v1' },
  { id: 'zhipu', label: '智谱 GLM', url: 'https://open.bigmodel.cn/api/paas/v4' },
  { id: 'siliconflow', label: '硅基流动 SiliconFlow', url: 'https://api.siliconflow.cn/v1' },
  { id: 'openrouter', label: 'OpenRouter', url: 'https://openrouter.ai/api/v1' },
  {
    id: 'ark', label: '火山方舟', url: 'https://ark.cn-beijing.volces.com/api/v3',
    note: '方舟的模型 ID 通常是「推理接入点 ID」（ep-…）；华北以外的区域请按控制台地址改写主机名。',
  },
  { id: 'hunyuan', label: '腾讯混元', url: 'https://api.hunyuan.cloud.tencent.com/v1' },
  {
    id: 'qianfan', label: '百度千帆', url: 'https://qianfan.baidubce.com/v2',
    note: '千帆需使用 v2 的 API Key（Bearer），模型列表可能不可用，可在下方手动填写模型 ID。',
  },
  { id: 'minimax-cn', label: 'MiniMax（国内）', url: 'https://api.minimax.chat/v1' },
  { id: 'minimax-intl', label: 'MiniMax（国际）', url: 'https://api.minimaxi.com/v1' },
  { id: 'ollama', label: '本地 Ollama', url: 'http://127.0.0.1:11434/v1', note: '本机地址可用 HTTP，通常无需 API Key。' },
]

const session = useSessionStore()
const router = useRouter()
const route = useRoute()
const api = createApiSettingsClient(() => session.accessToken, () => { session.signOut(); void router.replace('/') })

const saving = ref(false)
const ready = ref(false)
const message = ref('')
const failed = ref(false)
const configured = reactive({ llm: false, embedding: false })
const runtime = reactive({ embeddingModel: '', embeddingDimensions: 0 })
/** 保存后还没重启：由后端比较「保存时间」与「本次启动时间」得出 */
const restartNeeded = ref(false)

const form = reactive({
  LLM_BASE_URL: '', LLM_MODEL: '', LLM_API_KEY: '',
  // 向量侧表单是「目标配置」：保存到 EMBEDDING_TARGET_*，不改变运行时 EMBEDDING_MODEL/DIMENSIONS
  EMBEDDING_BASE_URL: '', EMBEDDING_TARGET_MODEL: '', EMBEDDING_TARGET_DIMENSIONS: 0, EMBEDDING_API_KEY: '',
})
/** 已保存的地址与模型：用于判断「是否换了主机」「旧列表是否失效」 */
const saved = reactive({ llmHost: '', embeddingHost: '', llmModel: '', embeddingModel: '' })

/** 目标（待启用）向量模型的能力：来自后端能力表；未知即不提供候选维度 */
const embeddingCapability = ref<EmbeddingCapability | null>(null)
const capabilityLoading = ref(false)
const assumeDimensions = ref(false)
const manualDimension = ref<number | null>(null)
/** 向量维度的说明默认收起，点「!」按钮才展开 */
const helpOpen = ref(false)

const discovery = reactive({
  llm: { options: [] as ModelOption[], count: 0, done: false, error: '', latency: null as number | null, busy: false, stale: false, seq: 0, fetchedAt: 0 },
  embedding: { options: [] as ModelOption[], count: 0, done: false, error: '', latency: null as number | null, busy: false, stale: false, seq: 0, fetchedAt: 0 },
})
const testing = reactive({ llm: false, embedding: false })
const results = reactive<{ llm: ConnectionResult | null; embedding: ConnectionResult | null }>({ llm: null, embedding: null })
const dialog = reactive({ kind: null as Kind | null, elapsed: 0 })
const timers: Partial<Record<Kind, ReturnType<typeof setInterval>>> = {}
const started: Record<Kind, number> = { llm: 0, embedding: 0 }

const blocks = [
  { kind: 'llm' as Kind, title: '大模型接口', prefix: 'LLM' as const },
  { kind: 'embedding' as Kind, title: '向量模型接口', prefix: 'EMBEDDING' as const },
]

function hostOf(url: string): string {
  try { return new URL(url).host.toLowerCase() } catch { return '' }
}
const isLocalHost = (host: string) => /^(localhost|127\.0\.0\.1|\[::1\]|192\.168\.|10\.)/.test(host)

/**
 * API Key 的本机留存：只在**本浏览器**记住用户自己填过的密钥，重启软件或切换页面后自动带回，
 * 免得每次重新输入。它只在同一 API 主机下复用（换服务商立即清除），保存成功后也会清除；
 * 密钥不会进入接口响应、日志或后端明文回显，后端仍以 DPAPI 加密存储。
 */
const KEY_STORAGE = 'smartsketch.apiKeys'
const keyRestored = reactive({ llm: false, embedding: false })

function readStoredKeys(): Record<string, string> {
  try {
    const raw = window.localStorage.getItem(KEY_STORAGE)
    return raw ? JSON.parse(raw) as Record<string, string> : {}
  } catch { return {} }
}
function writeStoredKey(kind: Kind, key: string): void {
  try {
    const all = readStoredKeys()
    if (key) all[kind] = key
    else delete all[kind]
    window.localStorage.setItem(KEY_STORAGE, JSON.stringify(all))
  } catch { /* 隐私模式等场景下忽略：仅影响自动带回 */ }
}
function clearStoredKey(kind: Kind): void {
  writeStoredKey(kind, '')
}
function clearKeys(): void {
  keyRestored.llm = false
  keyRestored.embedding = false
  form.LLM_API_KEY = ''
  form.EMBEDDING_API_KEY = ''
  clearStoredKey('llm')
  clearStoredKey('embedding')
}
/** 挂载时把本机留存的密钥带回输入框（仅当主机与上次保存的一致） */
function restoreKeys(): void {
  const stored = readStoredKeys()
  for (const kind of ['llm', 'embedding'] as Kind[]) {
    const prefix = kind === 'llm' ? 'LLM' : 'EMBEDDING'
    const key = stored[kind] ?? ''
    const host = hostOf(form[`${prefix}_BASE_URL`])
    if (key && host && host === saved[`${kind}Host`]) {
      form[`${prefix}_API_KEY`] = key
      keyRestored[kind] = true
    } else if (key) {
      clearStoredKey(kind)   // 地址已换到别的主机：不把旧主机的密钥带过来
    }
  }
}
/** 地址改到别的主机时，立即丢掉自动带回的密钥，避免误发给另一个服务商 */
function dropKeyOnHostChange(kind: Kind): void {
  const prefix = kind === 'llm' ? 'LLM' : 'EMBEDDING'
  const host = hostOf(form[`${prefix}_BASE_URL`])
  if (!host || host === saved[`${kind}Host`]) return
  clearStoredKey(kind)
  if (keyRestored[kind]) {
    keyRestored[kind] = false
    form[`${prefix}_API_KEY`] = ''
  }
}
/** 目标向量模型的能力：已知时给出候选维度；未知时要求手动填写并确认 */
const capabilityKnown = computed(() => embeddingCapability.value?.known === true)
const dimensionOptions = computed(() => embeddingCapability.value?.dimensions ?? [])
const fixedDimension = computed(() => (capabilityKnown.value && dimensionOptions.value.length === 1 ? dimensionOptions.value[0] : null))
/** 能力行文案：加载中 / 固定维度 / 多档可选；用使用者能看懂的说法，不提参数名 */
const capabilityStateText = computed(() => {
  if (capabilityLoading.value) return '正在读取该模型支持的维度…'
  const capability = embeddingCapability.value
  if (!capability?.known) return ''
  if (fixedDimension.value !== null) return `${capability.label || capability.model}：该模型输出维度固定，只能使用 ${fixedDimension.value} 维。`
  const recommended = capability.default ? `，推荐默认 ${capability.default} 维` : ''
  return `${capability.label || capability.model}：可选 ${capability.dimensions.join(' / ')} 维${recommended}。`
})
/** 目标模型/维度与当前实际使用的不一致：需要重新处理资料后才生效 */
const targetDiffersFromActive = computed(() => (
  Boolean(form.EMBEDDING_TARGET_MODEL.trim() || form.EMBEDDING_TARGET_DIMENSIONS)
  && (form.EMBEDDING_TARGET_MODEL.trim() !== runtime.embeddingModel
    || (form.EMBEDDING_TARGET_DIMENSIONS || 0) !== (runtime.embeddingDimensions || 0))
))
const currentSpace = computed(() => `${runtime.embeddingModel || '未设置'} · ${runtime.embeddingDimensions || 0} 维`)
const targetSpace = computed(() => {
  const model = form.EMBEDDING_TARGET_MODEL.trim()
  const dimensions = form.EMBEDDING_TARGET_DIMENSIONS
  if (!model && !dimensions) return `${runtime.embeddingModel || '未设置'} · ${runtime.embeddingDimensions || 0} 维（未设置新目标）`
  return `${model || '未选择模型'} · ${dimensions ? `${dimensions} 维` : '未选择维度'}`
})

/** 选择目标向量模型后拉取该模型的能力（是否支持 dimensions、可选维度） */
async function loadCapability(): Promise<void> {
  const model = form.EMBEDDING_TARGET_MODEL.trim()
  if (!model) { embeddingCapability.value = null; return }
  capabilityLoading.value = true
  try {
    embeddingCapability.value = await api.capability(embeddingPayload(), 'embedding')
    const capability = embeddingCapability.value
    if (capability?.known) {
      // 换了模型后重新计算：原选择不受支持时清空，等用户重新选
      if (!capability.dimensions.includes(form.EMBEDDING_TARGET_DIMENSIONS)) {
        form.EMBEDDING_TARGET_DIMENSIONS = capability.default ?? 0
      }
      assumeDimensions.value = false
    }
  } catch {
    embeddingCapability.value = null
  } finally {
    capabilityLoading.value = false
  }
}


/** 大模型候选：进页面自动获取一次时用它判断是否具备条件（地址 + Key 或已保存 Key） */
const llmCandidatesReady = computed(() => Boolean(
  form.LLM_BASE_URL.trim()
  && (configured.llm || isLocalHost(hostOf(form.LLM_BASE_URL)) || Boolean(form.LLM_API_KEY.trim()))
  && !keyGuard('llm'),
))

/** 列表状态：只报数量，大模型与向量两块文案一致 */
function lastFetchLabel(kind: Kind): string {
  return `接口返回 ${discovery[kind].count} 个模型`
}

/** 换了主机又没提供新 Key：不要把原服务商的密钥发给另一个主机 */
function keyGuard(kind: Kind): string {
  const prefix = kind === 'llm' ? 'LLM' : 'EMBEDDING'
  const host = hostOf(form[`${prefix}_BASE_URL`])
  const changed = host !== '' && saved[`${kind}Host`] !== '' && host !== saved[`${kind}Host`]
  if (changed && !form[`${prefix}_API_KEY`].trim() && !isLocalHost(host)) {
    return 'API 主机已更换：请填写该服务商的 API Key 后再获取列表或测试（不会把原主机的密钥发给新主机）。'
  }
  return ''
}
function fieldWarning(kind: Kind): string {
  const prefix = kind === 'llm' ? 'LLM' : 'EMBEDDING'
  const base = form[`${prefix}_BASE_URL`].trim()
  const model = kind === 'llm' ? form.LLM_MODEL.trim() : form.EMBEDDING_TARGET_MODEL.trim()
  if (!base) return '请填写 API 地址。'
  if (!model && kind === 'llm') return '请获取可用模型并选择「大模型」，或手动填写模型名称。'
  const host = hostOf(base)
  if (!isLocalHost(host) && !form[`${prefix}_API_KEY`].trim() && !configured[kind]) return '请先填写该服务商的 API Key。'
  return ''
}

const modelOptions = computed<Record<Kind, ModelOption[]>>(() => ({
  llm: mergeOptions(discovery.llm.options, form.LLM_MODEL),
  embedding: mergeOptions(discovery.embedding.options, form.EMBEDDING_TARGET_MODEL),
}))
/** 当前选择不在已发现列表中时补齐一项，避免选择器显示为空 */
function mergeOptions(options: ModelOption[], current: string): ModelOption[] {
  if (!current || options.some((option) => option.id === current)) return options
  return [{ id: current, name: '' }, ...options]
}
const listPathFor = (kind: Kind): string => {
  const prefix = kind === 'llm' ? 'LLM' : 'EMBEDDING'
  const provider = PROVIDERS.find((item) => item.url === form[`${prefix}_BASE_URL`].trim())
  return provider?.listPath ?? '/models'
}

function llmPayload(): Record<string, unknown> {
  const body: Record<string, unknown> = {
    LLM_BASE_URL: form.LLM_BASE_URL.trim(),
    LLM_PROVIDER_LABEL: PROVIDERS.find((item) => item.url === form.LLM_BASE_URL.trim())?.label ?? '',
    list_path: listPathFor('llm'),
  }
  if (form.LLM_MODEL.trim()) body.LLM_CHAT_MODEL = form.LLM_MODEL.trim()
  if (form.LLM_API_KEY.trim()) body.LLM_API_KEY = form.LLM_API_KEY.trim()
  return body
}
function targetDimensions(): number {
  // 能力未知时以手动填写的维度为准（并要求勾选确认，后端同样校验）
  if (!capabilityKnown.value && manualDimension.value) return Number(manualDimension.value)
  return form.EMBEDDING_TARGET_DIMENSIONS || Number(manualDimension.value ?? 0) || 0
}

function embeddingPayload(): Record<string, unknown> {
  // 只提交「目标」字段：运行时 EMBEDDING_MODEL / EMBEDDING_DIMENSIONS 保持不变，
  // 迁移完成前重启也不会切换到不兼容的维度（启动门禁继续以运行时配置为准）。
  const body: Record<string, unknown> = {
    EMBEDDING_BASE_URL: form.EMBEDDING_BASE_URL.trim(),
    list_path: listPathFor('embedding'),
  }
  if (form.EMBEDDING_TARGET_MODEL.trim()) body.EMBEDDING_TARGET_MODEL = form.EMBEDDING_TARGET_MODEL.trim()
  const dimensions = targetDimensions()
  if (dimensions > 0) body.EMBEDDING_TARGET_DIMENSIONS = dimensions
  body.EMBEDDING_TARGET_ASSUME_DIMENSIONS = assumeDimensions.value
  if (form.EMBEDDING_API_KEY.trim()) body.EMBEDDING_API_KEY = form.EMBEDDING_API_KEY.trim()
  return body
}

onMounted(async () => {
  // 路由守卫把人送到这里时会带一句话，直接显示在页面上
  const notice = route.query.notice
  if (typeof notice === 'string' && notice.trim()) message.value = notice.trim()
  try {
    const settings = await api.read()
    form.LLM_BASE_URL = settings.LLM_BASE_URL
    // 旧配置可能只写了知识抽取模型：优先聊天模型，缺失时用知识抽取模型
    form.LLM_MODEL = settings.LLM_CHAT_MODEL || settings.LLM_EXTRACTION_MODEL
    form.EMBEDDING_BASE_URL = settings.EMBEDDING_BASE_URL
    // 目标配置：优先已保存的目标，缺失时回落到当前实际使用的模型与维度
    form.EMBEDDING_TARGET_MODEL = settings.EMBEDDING_TARGET_MODEL || settings.EMBEDDING_MODEL
    form.EMBEDDING_TARGET_DIMENSIONS = settings.EMBEDDING_TARGET_DIMENSIONS || settings.EMBEDDING_DIMENSIONS || 0
    assumeDimensions.value = Boolean(settings.EMBEDDING_TARGET_ASSUME_DIMENSIONS)
    configured.llm = settings.LLM_API_KEY_configured
    configured.embedding = settings.EMBEDDING_API_KEY_configured
    saved.llmHost = hostOf(form.LLM_BASE_URL)
    saved.embeddingHost = hostOf(form.EMBEDDING_BASE_URL)
    saved.llmModel = form.LLM_MODEL
    saved.embeddingModel = form.EMBEDDING_TARGET_MODEL
    runtime.embeddingModel = settings.active?.EMBEDDING_MODEL ?? settings.EMBEDDING_MODEL
    runtime.embeddingDimensions = settings.active?.EMBEDDING_DIMENSIONS ?? settings.EMBEDDING_DIMENSIONS
    restoreKeys()
    ready.value = true
    // 进页面自动拉一次大模型候选：条件具备（地址 + Key 或已保存 Key）且当前没有候选时
    // 向量接口保持手动（没配好之前列不出可用模型）
    if (llmCandidatesReady.value && !discovery.llm.options.length && !discovery.llm.busy) void discover('llm')
    // 目标模型已定时补一次能力，用于渲染维度候选（不触发任何保存）
    if (form.EMBEDDING_TARGET_MODEL.trim()) void loadCapability()
    // 是否还需要重启：由后端比较「保存时间」与「本次启动时间」，不在前端猜
    const status = await api.status()
    restartNeeded.value = Boolean(status.restart_needed)
  } catch (error) { failed.value = true; message.value = error instanceof Error ? error.message : '读取失败' }
})

// 地址或 Key 改变后，已获取的候选列表标记为失效，下次获取必须用新表单值
watch(() => form.LLM_BASE_URL, () => { discovery.llm.stale = discovery.llm.done; dropKeyOnHostChange('llm') })
watch(() => form.LLM_API_KEY, (value) => {
  discovery.llm.stale = discovery.llm.done
  if (!value.trim()) keyRestored.llm = false
  else if (!keyRestored.llm) writeStoredKey('llm', value.trim())
})
watch(() => form.EMBEDDING_BASE_URL, () => { discovery.embedding.stale = discovery.embedding.done; dropKeyOnHostChange('embedding') })
watch(() => form.EMBEDDING_API_KEY, (value) => {
  discovery.embedding.stale = discovery.embedding.done
  if (!value.trim()) keyRestored.embedding = false
  else if (!keyRestored.embedding) writeStoredKey('embedding', value.trim())
})
// 改选目标向量模型后重算维度候选；能力未知时清空，交由用户手动填写并确认
watch(() => form.EMBEDDING_TARGET_MODEL, () => {
  manualDimension.value = null
  void loadCapability()
})

async function discover(kind: Kind) {
  const state = discovery[kind]
  const guard = keyGuard(kind) || fieldWarning(kind)
  if (guard) { state.error = guard; state.done = true; state.stale = false; state.options = []; state.count = 0; return }
  const seq = ++state.seq
  state.busy = true; state.error = ''
  try {
    const payload = kind === 'llm' ? llmPayload() : embeddingPayload()
    const response = await api.models(payload, kind)
    if (seq !== state.seq) return          // 已有更新的请求，丢弃这次结果
    const options = response.model_options?.length ? response.model_options : response.models.map((id) => ({ id, name: '' }))
    Object.assign(state, {
      options, count: response.count ?? options.length, done: true,
      latency: response.latency_ms, error: response.ok ? '' : (response.error ?? '未能获取模型列表'),
      stale: false, fetchedAt: Date.now(),
    })
    // 接口没有返回任何模型时不算识别成功，提示手动填写
    if (response.ok && !options.length) state.error = '该地址未返回模型，请手动填写模型 ID。'
  } catch (error) {
    if (seq === state.seq) { state.error = error instanceof Error ? error.message : '获取模型列表失败，可手动填写模型 ID。'; state.done = true; state.stale = false }
  } finally {
    if (seq === state.seq) state.busy = false
  }
}

async function test(kind: Kind) {
  if (testing[kind]) return
  const guard = keyGuard(kind) || fieldWarning(kind)
  if (guard) { failed.value = true; message.value = guard; return }
  testing[kind] = true; results[kind] = null
  dialog.kind = kind; dialog.elapsed = 0; started[kind] = performance.now()
  timers[kind] = setInterval(() => { if (dialog.kind === kind) dialog.elapsed = performance.now() - started[kind] }, 100)
  try {
    const payload: Record<string, unknown> = { ...(kind === 'llm' ? llmPayload() : embeddingPayload()) }
    delete payload.list_path
    if (kind === 'llm' && form.LLM_MODEL.trim()) payload.LLM_CHAT_MODEL = form.LLM_MODEL.trim()
    results[kind] = await api.test(payload, kind)
  } catch (error) {
    results[kind] = {
      kind, ok: false, latency_ms: null, http_status: null, detail: {},
      provider: hostOf(form[kind === 'llm' ? 'LLM_BASE_URL' : 'EMBEDDING_BASE_URL']),
      error: error instanceof Error ? error.message : '测试失败',
    }
  } finally {
    testing[kind] = false
    if (timers[kind] !== undefined) { clearInterval(timers[kind]); delete timers[kind] }
  }
}

async function save() {
  saving.value = true; message.value = ''; failed.value = false
  try {
    // 只提交配置字段：list_path 是获取列表用的请求参数，不能写进配置
    const body: Record<string, unknown> = { ...llmPayload(), ...embeddingPayload() }
    delete body.list_path
    delete body.LLM_PROVIDER_LABEL
    delete body.LLM_CHAT_MODEL
    if (form.LLM_MODEL.trim()) {
      // 聊天与知识抽取共用同一个模型：两个字段一起写
      body.LLM_CHAT_MODEL = form.LLM_MODEL.trim()
      body.LLM_EXTRACTION_MODEL = form.LLM_MODEL.trim()
    }
    // 不提交向量模式：软件在启动时读取一次设置，切换向量模型仍需重新处理资料后生效
    const settings = await api.save(body)
    configured.llm = settings.LLM_API_KEY_configured
    configured.embedding = settings.EMBEDDING_API_KEY_configured
    form.LLM_MODEL = settings.LLM_CHAT_MODEL || settings.LLM_EXTRACTION_MODEL
    saved.llmModel = form.LLM_MODEL
    saved.llmHost = hostOf(form.LLM_BASE_URL)
    saved.embeddingHost = hostOf(form.EMBEDDING_BASE_URL)
    // 已写入本机加密配置：输入框与本机留存都清空，不让密钥长期停留在页面上
    clearKeys()
    // 本机软件启动时读取一次设置，所以保存后要重启才会用上新配置（是否需要由后端状态判定）
    const status = await refreshConfigStatus(session.accessToken, true)
    restartNeeded.value = Boolean(status?.restart_needed)
    message.value = restartNeeded.value ? '设置已保存，请重启软件后使用。' : '设置已保存'
  } catch (error) {
    failed.value = true; message.value = error instanceof Error ? error.message : '保存失败'
  } finally { saving.value = false }
}

function applyProvider(kind: Kind, provider: Provider): void {
  // 只改地址与提示：不填模型、不填 Key；已获取的列表由地址的 watch 标记为失效
  if (kind === 'llm') form.LLM_BASE_URL = provider.url
  else form.EMBEDDING_BASE_URL = provider.url
}
function selectProvider(kind: Kind, event: Event): void {
  const id = (event.target as HTMLSelectElement).value
  const provider = PROVIDERS.find((item) => item.id === id)
  if (provider) applyProvider(kind, provider)   // 「自定义地址」不修改当前地址，只保留输入框内容
}
const activeProviderId = (kind: Kind): string => {
  const prefix = kind === 'llm' ? 'LLM' : 'EMBEDDING'
  return PROVIDERS.find((item) => item.url === form[`${prefix}_BASE_URL`].trim())?.id ?? 'custom'
}
const activeProvider = (kind: Kind): Provider | undefined =>
  PROVIDERS.find((item) => item.id === activeProviderId(kind))

function showResult(kind: Kind) {
  dialog.kind = kind
  dialog.elapsed = testing[kind] ? performance.now() - started[kind] : 0
}
</script>

<template>
  <!-- 本页是整站视觉基准：外层 .page（米灰背景）+ 内容 .surface-card（暖白卡片），其余页面引用同一套公共类 -->
  <div class="page api-settings">
    <header class="page__heading">
      <h2>API 设置</h2>
    </header>
    <p v-if="message" role="status" class="notice" :class="{ error: failed }">{{ message }}</p>
    <p v-else-if="restartNeeded" role="status" class="notice" data-test="restart-needed">设置已保存，请重启软件后使用。</p>

    <form @submit.prevent="save">
      <div class="interface-grid">
        <section v-for="block in blocks" :key="block.kind" :data-kind="block.kind" class="surface-card interface-card" :aria-labelledby="`${block.kind}-title`">
          <header class="card-heading">
            <h3 :id="`${block.kind}-title`">{{ block.title }}</h3>
            <span class="key-status">{{ configured[block.kind] ? '已保存，留空可保留' : '请输入 API Key' }}</span>
          </header>
          <fieldset :disabled="!ready || saving">
            <label :for="`${block.kind}-provider`">API 服务预设
              <select
                :id="`${block.kind}-provider`"
                :value="activeProviderId(block.kind)"
                :data-test="`${block.kind}-provider`"
                @change="selectProvider(block.kind, $event)"
              >
                <option v-for="provider in PROVIDERS" :key="provider.id" :value="provider.id">{{ provider.label }}</option>
                <option value="custom">自定义地址</option>
              </select>
            </label>
            <p v-if="activeProvider(block.kind)?.note" class="api-settings__note" data-test="provider-note">{{ activeProvider(block.kind)?.note }}</p>

            <label :for="`${block.kind}-base-url`">API 地址
              <input
                :id="`${block.kind}-base-url`"
                v-model="form[`${block.prefix}_BASE_URL`]"
                type="url"
                class="url-input"
                placeholder="https://服务地址/v1"
                :data-test="`${block.kind}-base-url`"
              />
            </label>

            <label :for="`${block.kind}-api-key`">API Key
              <input
                :id="`${block.kind}-api-key`"
                v-model="form[`${block.prefix}_API_KEY`]"
                type="password"
                autocomplete="new-password"
                :placeholder="configured[block.kind] ? '已配置，留空保留（仅同一地址沿用）' : '请输入 API Key'"
                :data-test="`${block.kind}-api-key`"
              />
            </label>
            <p v-if="keyRestored[block.kind]" class="api-settings__note" data-test="key-restored">
              已自动带回本机保存的密钥（重启软件或切换页面后仍保留）；保存成功后该密钥会从页面与本机留存中清除。
            </p>

            <div class="discovery-row">
              <button type="button" class="secondary" :disabled="discovery[block.kind].busy" :data-test="`${block.kind}-discover`" @click="discover(block.kind)">
                {{ discovery[block.kind].busy ? '正在获取…' : (discovery[block.kind].done ? '重新获取' : '获取可用模型') }}
              </button>
              <span v-if="discovery[block.kind].done && discovery[block.kind].stale" class="api-settings__note" data-test="model-stale">地址或密钥已改动，当前列表已失效，请重新获取。</span>
            </div>
            <p class="api-settings__hint" data-test="discovery-count">{{ lastFetchLabel(block.kind) }}</p>
            <p v-if="discovery[block.kind].error" class="warning" role="status" data-test="discovery-error">{{ discovery[block.kind].error }}</p>

            <template v-if="block.kind === 'llm'">
              <label :for="'llm-model'">大模型</label>
              <ModelSelect
                v-model="form.LLM_MODEL"
                :options="modelOptions.llm"
                input-id="llm-model"
                test="llm-model"
                placeholder="获取模型列表后选择，或手动填写模型名称"
              />
              <p class="api-settings__note">用于聊天与知识抽取。</p>
            </template>
            <template v-else>
              <label :for="'embedding-target-model'">向量模型</label>
              <ModelSelect
                v-model="form.EMBEDDING_TARGET_MODEL"
                :options="modelOptions.embedding"
                input-id="embedding-target-model"
                test="embedding-model"
                placeholder="获取模型列表后选择，或手动填写模型名称"
              />

              <details class="advanced" data-test="advanced-settings">
                <summary>高级设置</summary>
                <p class="api-settings__note">通常保持默认值即可。</p>
                <div class="field">
                  <label :for="'embedding-target-dimensions'">向量维度</label>
                  <!-- 说明收进「!」按钮：默认只留一行状态，点开才展开给用户看的解释 -->
                  <button
                    type="button"
                    class="help-toggle"
                    :aria-expanded="helpOpen"
                    aria-controls="embedding-help"
                    aria-label="向量维度说明"
                    title="向量维度说明"
                    data-test="embedding-help-toggle"
                    @click="helpOpen = !helpOpen"
                  >
                    <span aria-hidden="true">!</span>
                  </button>
                  <select
                    v-if="capabilityKnown && !fixedDimension"
                    id="embedding-target-dimensions"
                    v-model.number="form.EMBEDDING_TARGET_DIMENSIONS"
                    data-test="embedding-dimensions"
                  >
                    <option v-for="value in dimensionOptions" :key="value" :value="value">
                      {{ value }}{{ value === embeddingCapability?.default ? '（推荐默认）' : '' }}
                    </option>
                  </select>
                  <input
                    v-else-if="fixedDimension"
                    id="embedding-target-dimensions"
                    :value="fixedDimension"
                    readonly
                    data-test="embedding-dimensions"
                  />
                  <input
                    v-else
                    id="embedding-target-dimensions"
                    v-model.number="manualDimension"
                    type="number"
                    min="1"
                    placeholder="手动填写维度"
                    data-test="embedding-dimensions-manual"
                  />
                  <div v-if="helpOpen" id="embedding-help" class="help-card" data-test="embedding-help">
                    <p class="help-card__title">关于向量维度</p>
                    <ul>
                      <li>维度表示每段文本生成的向量长度，需要与数据库索引保持一致。</li>
                      <li>换成别的维度后，原有课程内容需要重新生成向量，才能和新设置一起使用。</li>
                      <li v-if="capabilityKnown && !fixedDimension">不知道选哪个时，用带「推荐默认」的那一项就好。</li>
                      <li v-else-if="fixedDimension">该模型输出维度固定，这里只能用它自己的维度。</li>
                      <li v-else>这个模型我们没有它的维度说明：请按服务商给的值填写，并勾选下方「按该维度调用」确认。</li>
                    </ul>
                  </div>
                </div>
                <p v-if="capabilityStateText" class="api-settings__note" data-test="capability-state">{{ capabilityStateText }}</p>
                <div v-if="!capabilityKnown && form.EMBEDDING_TARGET_MODEL.trim()" class="api-settings__note" data-test="capability-unknown">
                  <p>这个模型的维度说明我们没有收录，请手动填写维度并确认后再保存。</p>
                  <label class="inline-check">
                    <input v-model="assumeDimensions" type="checkbox" data-test="assume-dimensions" />
                    按该维度调用（我已确认该模型支持此维度）
                  </label>
                </div>
              </details>

              <p class="api-settings__note" data-test="embedding-current">当前使用：{{ currentSpace }}</p>
              <p v-if="targetDiffersFromActive" class="api-settings__note" data-test="embedding-target">新设置：{{ targetSpace }}</p>
              <p v-if="targetDiffersFromActive" class="api-settings__pending" data-test="embedding-pending">
                新设置已保存。请在课程页点「重新处理资料」，处理完成后才会使用新的向量。
              </p>
            </template>

            <div class="test-actions">
              <button type="button" class="primary" :disabled="testing[block.kind]" :data-test="`${block.kind}-test`" @click="test(block.kind)">
                {{ testing[block.kind] ? '测试中…' : '测试连接' }}
              </button>
              <button v-if="results[block.kind] || testing[block.kind]" type="button" class="secondary" @click="showResult(block.kind)">查看测试结果</button>
            </div>
          </fieldset>
          <ConnectionResultDialog
            :open="dialog.kind === block.kind"
            :title="activeProvider(block.kind)?.label || block.title"
            :pending="testing[block.kind]"
            :elapsed="dialog.elapsed"
            :result="results[block.kind]"
            @close="dialog.kind = null"
          />
        </section>
      </div>

      <footer class="save-row">
        <button type="submit" class="primary" :disabled="saving || !ready">{{ saving ? '保存中…' : '保存设置' }}</button>
      </footer>
    </form>
  </div>
</template>

<style scoped>
/* 页面外层、标题与卡片外观全部来自全局公共类（.page / .page__* / .surface-card）；
 * 这里只保留本页特有的表单、按钮与状态提示样式，避免再次出现两套风格。 */
.api-settings{max-width:1160px;min-width:0}
.api-settings h2{margin:0}
.api-settings h3{margin:0}
.api-settings__note{color:var(--color-text-muted);font-size:13px;line-height:1.7;margin:0}
.api-settings__hint{color:var(--color-text);font-size:13px;line-height:1.7;margin:0}
.inline-check{display:flex;align-items:center;gap:8px;margin-top:8px;font-size:13px}
.inline-check input{width:auto;min-width:0}
/* 字段行：标签（可带「!」说明按钮）在上一行，控件占满下一行 */
.field{display:grid;grid-template-columns:auto 1fr;grid-template-areas:'label help' 'control control';align-items:center;gap:6px;min-width:0}
.field > label{grid-area:label}
.field > select,.field > input{grid-area:control}
.help-toggle{grid-area:help;justify-self:start;display:inline-grid;place-items:center;width:18px;height:18px;min-height:0;padding:0;border-radius:50%;font-size:12px;font-weight:700;line-height:1;background:var(--color-surface-muted);color:var(--color-text-muted);border:1px solid var(--color-border-strong);cursor:pointer}
.help-toggle:hover{background:var(--color-primary-soft);color:var(--color-primary);border-color:var(--color-primary)}
.help-toggle:focus-visible{outline:2px solid var(--color-primary);outline-offset:1px}
.help-card{grid-area:control;margin-top:8px;padding:12px 14px;background:var(--color-surface-muted);border:1px solid var(--color-border);border-radius:var(--radius-sm);color:var(--color-text);font-size:13px;line-height:1.7}
.help-card__title{margin:0 0 4px;font-weight:600}
.help-card ul{margin:0;padding-left:1.1rem;display:grid;gap:4px}
.api-settings__pending{margin:0;color:var(--color-warning-text);font-size:13px;line-height:1.7}
/* 高级设置：默认收起，避免普通用户被维度等Options干扰 */
.advanced{display:grid;gap:10px;border:1px solid var(--color-border);border-radius:var(--radius-sm);padding:10px 12px;background:var(--color-surface-muted)}
.advanced summary{cursor:pointer;font-size:14px;font-weight:600;color:var(--color-text)}
.advanced[open] summary{margin-bottom:8px}
.advanced .field{gap:8px}
.interface-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px;align-items:start}
/* 卡片外观来自全局 .surface-card；这里只声明一列不溢出 */
.interface-card{min-width:0}
.card-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;padding-bottom:16px;border-bottom:1px solid var(--color-border);margin-bottom:16px}
.key-status{font-size:12px;color:var(--color-success-text)}
fieldset{border:0;padding:0;margin:0;display:grid;gap:14px;min-width:0}
label{display:grid;gap:6px;font-size:14px}
input,select{width:100%;padding:10px 12px;background:var(--color-surface);color:var(--color-text);border:1px solid var(--color-border-strong);border-radius:var(--radius-sm);font:inherit;min-width:0}
input::placeholder{color:var(--color-text-muted)}
input:focus-visible,select:focus-visible{outline:2px solid var(--color-primary);outline-offset:1px}
button{font:inherit;min-height:36px;padding:8px 14px;border-radius:var(--radius-sm);cursor:pointer;box-shadow:none;transition:background .15s}
button.primary{background:var(--color-primary);border:1px solid var(--color-primary);color:#fff}
button.primary:hover{background:var(--color-primary-hover);border-color:var(--color-primary-hover)}
button.secondary{background:var(--color-surface);color:var(--color-text);border:1px solid var(--color-border-strong)}
button.secondary:hover{background:var(--color-primary-soft)}
button:disabled{opacity:.55;cursor:not-allowed}
.discovery-row{display:flex;align-items:center;flex-wrap:wrap;gap:10px}
.test-actions{display:flex;align-items:center;flex-wrap:wrap;gap:10px;padding-top:12px;border-top:1px solid var(--color-border)}
.save-row{display:flex;align-items:center;flex-wrap:wrap;gap:12px;padding-top:20px;border-top:1px solid var(--color-border)}
.warning{background:var(--color-warning-bg);border:1px solid var(--color-warning-border);color:var(--color-warning-text);padding:10px;font-size:13px;border-radius:var(--radius-sm)}
/* 保存结果提示：成功用松绿、失败用砖红，二者都保持可辨识 */
.notice{color:var(--color-success-text);padding:12px;border:1px solid var(--color-border);background:var(--color-surface);font-size:13px;border-radius:var(--radius-sm)}
.notice.error{color:var(--color-danger-text);border-color:var(--color-danger-border);background:var(--color-danger-bg)}
/* 窄屏：卡片单列，且表单控件不撑破容器（避免横向溢出） */
@media(max-width:850px){.interface-grid{grid-template-columns:minmax(0,1fr)}}
@media(max-width:480px){.api-settings{padding-inline:0}}
</style>
