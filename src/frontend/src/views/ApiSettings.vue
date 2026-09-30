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
import { useRouter } from 'vue-router'
import { createApiSettingsClient, type ConnectionResult, type ModelOption } from '../api/apiSettings'
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
const api = createApiSettingsClient(() => session.accessToken, () => { session.signOut(); void router.replace('/') })

const saving = ref(false)
const ready = ref(false)
const message = ref('')
const failed = ref(false)
const configured = reactive({ llm: false, embedding: false })
const runtime = reactive({ llmMode: 'demo', embeddingMode: 'demo', embeddingModel: '' })

const form = reactive({
  LLM_BASE_URL: '', LLM_MODEL: '', LLM_API_KEY: '',
  EMBEDDING_BASE_URL: '', EMBEDDING_MODEL: '', EMBEDDING_DIMENSIONS: 1024, EMBEDDING_API_KEY: '',
})
/** 已保存的地址与模型：用于判断「是否换了主机」「旧列表是否失效」 */
const saved = reactive({ llmHost: '', embeddingHost: '', llmModel: '', embeddingModel: '' })

const discovery = reactive({
  llm: { options: [] as ModelOption[], count: 0, done: false, error: '', latency: null as number | null, busy: false, stale: false, seq: 0 },
  embedding: { options: [] as ModelOption[], count: 0, done: false, error: '', latency: null as number | null, busy: false, stale: false, seq: 0 },
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

/** 大模型是否配置完整：地址 + 模型 +（非本机时）Key */
const llmComplete = computed(() => {
  if (!form.LLM_BASE_URL.trim() || !form.LLM_MODEL.trim()) return false
  const host = hostOf(form.LLM_BASE_URL)
  return Boolean(form.LLM_API_KEY.trim()) || configured.llm || isLocalHost(host)
})

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
/** 保存后生效的模式：配置完整即在线的，否则仍是演示 */
const llmModeAfterSave = computed(() => (llmComplete.value ? 'live' : 'demo'))
const embeddingConfigured = computed(() => Boolean(form.EMBEDDING_BASE_URL.trim() && form.EMBEDDING_MODEL.trim()))
const embeddingDetail = computed(() => {
  if (runtime.embeddingMode === 'online') return `当前生效：在线 · ${runtime.embeddingModel || form.EMBEDDING_MODEL || '未命名模型'}`
  if (embeddingConfigured.value) return '当前生效：演示向量（配置已保存，尚未迁移到在线向量空间，页面不提供切换）'
  return '当前生效：演示向量（未配置在线向量模型）'
})
const statusLine = computed(() =>
  `当前生效：大模型 ${runtime.llmMode === 'live' ? '在线' : '演示'} · 向量 ${runtime.embeddingMode === 'online' ? '在线' : '演示'}`)

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
  const model = kind === 'llm' ? form.LLM_MODEL.trim() : form.EMBEDDING_MODEL.trim()
  if (!base) return '请先填写 API 地址。'
  if (!model && kind === 'llm') return '请先获取模型列表并选择「大模型」，或手动填写模型 ID。'
  const host = hostOf(base)
  if (!isLocalHost(host) && !form[`${prefix}_API_KEY`].trim() && !configured[kind]) return '请先填写该服务商的 API Key。'
  return ''
}

const modelOptions = computed<Record<Kind, ModelOption[]>>(() => ({
  llm: mergeOptions(discovery.llm.options, form.LLM_MODEL),
  embedding: mergeOptions(discovery.embedding.options, form.EMBEDDING_MODEL),
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
function embeddingPayload(): Record<string, unknown> {
  const body: Record<string, unknown> = {
    EMBEDDING_BASE_URL: form.EMBEDDING_BASE_URL.trim(),
    EMBEDDING_DIMENSIONS: form.EMBEDDING_DIMENSIONS,
    list_path: listPathFor('embedding'),
  }
  if (form.EMBEDDING_MODEL.trim()) body.EMBEDDING_MODEL = form.EMBEDDING_MODEL.trim()
  if (form.EMBEDDING_API_KEY.trim()) body.EMBEDDING_API_KEY = form.EMBEDDING_API_KEY.trim()
  return body
}

onMounted(async () => {
  try {
    const settings = await api.read()
    form.LLM_BASE_URL = settings.LLM_BASE_URL
    // 旧配置可能只写了知识抽取模型：优先聊天模型，缺失时用知识抽取模型
    form.LLM_MODEL = settings.LLM_CHAT_MODEL || settings.LLM_EXTRACTION_MODEL
    form.EMBEDDING_BASE_URL = settings.EMBEDDING_BASE_URL
    form.EMBEDDING_MODEL = settings.EMBEDDING_MODEL
    form.EMBEDDING_DIMENSIONS = settings.EMBEDDING_DIMENSIONS
    configured.llm = settings.LLM_API_KEY_configured
    configured.embedding = settings.EMBEDDING_API_KEY_configured
    saved.llmHost = hostOf(form.LLM_BASE_URL)
    saved.embeddingHost = hostOf(form.EMBEDDING_BASE_URL)
    saved.llmModel = form.LLM_MODEL
    saved.embeddingModel = form.EMBEDDING_MODEL
    runtime.llmMode = settings.active?.LLM_MODE ?? settings.LLM_MODE ?? 'demo'
    runtime.embeddingMode = settings.active?.EMBEDDING_MODE ?? settings.EMBEDDING_MODE ?? 'demo'
    runtime.embeddingModel = settings.active?.EMBEDDING_MODEL ?? ''
    restoreKeys()
    ready.value = true
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
      stale: false,
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
    const body: Record<string, unknown> = { ...llmPayload(), ...embeddingPayload(), LLM_MODE: llmModeAfterSave.value }
    delete body.list_path
    delete body.LLM_PROVIDER_LABEL
    delete body.LLM_CHAT_MODEL
    if (form.LLM_MODEL.trim()) {
      // 聊天与知识抽取共用同一个模型：两个字段一起写
      body.LLM_CHAT_MODEL = form.LLM_MODEL.trim()
      body.LLM_EXTRACTION_MODEL = form.LLM_MODEL.trim()
    }
    // 不提交 EMBEDDING_MODE：向量空间切换仍需离线迁移，页面不提供该入口
    const settings = await api.save(body)
    configured.llm = settings.LLM_API_KEY_configured
    configured.embedding = settings.EMBEDDING_API_KEY_configured
    form.LLM_MODEL = settings.LLM_CHAT_MODEL || settings.LLM_EXTRACTION_MODEL
    saved.llmModel = form.LLM_MODEL
    saved.llmHost = hostOf(form.LLM_BASE_URL)
    saved.embeddingHost = hostOf(form.EMBEDDING_BASE_URL)
    // 已写入本机加密配置：输入框与本机留存都清空，不让密钥长期停留在页面上
    clearKeys()
    const needsRestart = runtime.llmMode !== llmModeAfterSave.value
    message.value = settings.message ?? (needsRestart ? '已保存，需要重启智绘学途后生效。' : '已保存，配置未改变运行模式，无需重启。')
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
  <section class="api-settings">
    <header class="page-heading"><p class="eyebrow">接口与模型</p><h2>API 设置</h2><p>{{ statusLine }}</p></header>
    <p class="note">设置由本机所有课程共用。密钥留空表示保留已保存的密钥，保存后重启软件生效。</p>
    <p class="note">外部服务要求 HTTPS，本机地址可用 HTTP。先选服务商或填写地址，再获取模型列表并选择模型。</p>
    <p v-if="message" role="status" class="notice" :class="{ error: failed }">{{ message }}</p>

    <form @submit.prevent="save">
      <div class="interface-grid">
        <section v-for="block in blocks" :key="block.kind" :data-kind="block.kind" class="interface-card" :aria-labelledby="`${block.kind}-title`">
          <header class="card-heading">
            <h3 :id="`${block.kind}-title`">{{ block.title }}</h3>
            <span class="key-status">{{ configured[block.kind] ? '密钥已配置' : '密钥未配置' }}</span>
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
            <p v-if="activeProvider(block.kind)?.note" class="note" data-test="provider-note">{{ activeProvider(block.kind)?.note }}</p>

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
            <p v-if="keyRestored[block.kind]" class="note" data-test="key-restored">
              已自动带回本机保存的密钥（重启软件或切换页面后仍保留）；保存成功后该密钥会从页面与本机留存中清除。
            </p>

            <div class="discovery-row">
              <button type="button" class="secondary" :disabled="discovery[block.kind].busy" :data-test="`${block.kind}-discover`" @click="discover(block.kind)">
                {{ discovery[block.kind].busy ? '正在获取…' : '获取模型列表' }}
              </button>
              <span v-if="discovery[block.kind].done && discovery[block.kind].stale" class="note" data-test="model-stale">地址或密钥已改动，当前列表已失效，请重新获取。</span>
            </div>
            <p v-if="discovery[block.kind].error" class="warning" role="status" data-test="discovery-error">{{ discovery[block.kind].error }}</p>
            <p v-else-if="discovery[block.kind].done" class="note" data-test="discovery-ok">
              识别到 {{ discovery[block.kind].count }} 个模型（{{ discovery[block.kind].latency }} ms）。点击下方选择框可展开全部候选，也可手动填写模型 ID。
            </p>

            <template v-if="block.kind === 'llm'">
              <label :for="'llm-model'">大模型</label>
              <ModelSelect
                v-model="form.LLM_MODEL"
                :options="modelOptions.llm"
                input-id="llm-model"
                test="llm-model"
                placeholder="获取模型列表后选择，或手动填写模型 ID"
              />
              <p class="note">用于聊天与知识抽取。</p>
            </template>
            <template v-else>
              <label :for="'embedding-model'">向量模型</label>
              <ModelSelect
                v-model="form.EMBEDDING_MODEL"
                :options="modelOptions.embedding"
                input-id="embedding-model"
                test="embedding-model"
                placeholder="获取模型列表后选择，或手动填写模型 ID"
              />
              <label :for="'embedding-dimensions'">向量维度<input id="embedding-dimensions" :value="form.EMBEDDING_DIMENSIONS" readonly /></label>
              <p class="note" data-test="embedding-status">{{ embeddingDetail }}</p>
              <p class="note">更换向量模型前需备份并离线迁移现有课程向量，页面不会切换向量空间。</p>
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
        <span class="note">保存后大模型将使用：{{ llmModeAfterSave === 'live' ? '在线 API' : '演示模式（配置不完整）' }}；保存后{{ runtime.llmMode !== llmModeAfterSave ? '需要重启软件生效' : '无需重启' }}。</span>
      </footer>
    </form>
  </section>
</template>

<style scoped>
.api-settings{max-width:1160px;padding:clamp(18px,3vw,32px);background:var(--color-bg);color:var(--color-text);border:1px solid var(--color-border);border-radius:8px}
.page-heading{margin-bottom:16px}.eyebrow{color:var(--color-primary);font-size:12px;letter-spacing:.12em}h2{font-size:1.25rem}h3{font-size:1.05rem;margin:0}
.note{color:var(--color-text-muted);font-size:13px;line-height:1.7}
.interface-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px;margin-top:24px;align-items:start}
.interface-card{background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius-md);padding:22px}
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
.save-row{display:flex;align-items:center;flex-wrap:wrap;gap:12px;margin-top:24px;padding-top:20px;border-top:1px solid var(--color-border)}
.warning{background:var(--color-warning-bg);border:1px solid var(--color-warning-border);color:var(--color-warning-text);padding:10px;font-size:13px;border-radius:var(--radius-sm)}
.notice{color:var(--color-success-text);padding:12px;border:1px solid var(--color-border);background:var(--color-surface);font-size:13px;border-radius:var(--radius-sm)}
.notice.error{color:var(--color-danger-text);border-color:var(--color-danger-border);background:var(--color-danger-bg)}
@media(max-width:850px){.interface-grid{grid-template-columns:1fr}.interface-card{padding:18px}}
</style>
