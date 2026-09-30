<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { createApiSettingsClient, type ConnectionResult } from '../api/apiSettings'
import { useSessionStore } from '../stores/session'
import ConnectionResultDialog from '../components/ConnectionResultDialog.vue'

type Kind = 'llm' | 'embedding'
const session = useSessionStore()
const router = useRouter()
const api = createApiSettingsClient(() => session.accessToken, () => { session.signOut(); void router.replace('/') })
const saving = ref(false)
const ready = ref(false)
const message = ref('')
const failed = ref(false)
const configured = reactive({ llm: false, embedding: false })
const active = ref('')
const form = reactive({ LLM_MODE: 'demo', LLM_BASE_URL: '', LLM_CHAT_MODEL: '', LLM_EXTRACTION_MODEL: '', LLM_PROVIDER_LABEL: '', LLM_API_KEY: '', EMBEDDING_MODE: 'demo', EMBEDDING_BASE_URL: '', EMBEDDING_MODEL: '', EMBEDDING_PROVIDER_LABEL: '', EMBEDDING_DIMENSIONS: 1024, EMBEDDING_API_KEY: '' })
const savedModels = reactive({ LLM_CHAT_MODEL: '', LLM_EXTRACTION_MODEL: '', EMBEDDING_MODEL: '' })
const testing = reactive({ llm: false, embedding: false })
const results = reactive<{ llm: ConnectionResult | null; embedding: ConnectionResult | null }>({ llm: null, embedding: null })
const dialog = reactive({ kind: null as Kind | null, elapsed: 0 })
const discovery = reactive({
  llm: { models: [] as string[], count: 0, done: false, error: '', latency: null as number | null, busy: false },
  embedding: { models: [] as string[], count: 0, done: false, error: '', latency: null as number | null, busy: false },
})
const timers: Partial<Record<Kind, ReturnType<typeof setInterval>>> = {}
const started = { llm: 0, embedding: 0 }
function showResult(kind: Kind) {
  dialog.kind = kind
  dialog.elapsed = testing[kind] ? performance.now() - started[kind] : 0
}
const blocks: { kind: Kind; title: string; prefix: 'LLM' | 'EMBEDDING' }[] = [
  { kind: 'llm', title: '大模型接口', prefix: 'LLM' }, { kind: 'embedding', title: '向量模型接口', prefix: 'EMBEDDING' },
]
const providers = [
  { label: 'DeepSeek', url: 'https://api.deepseek.com/v1' },
  { label: '阿里云百炼（通义）', url: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
  { label: 'OpenAI', url: 'https://api.openai.com/v1' },
  { label: '月之暗面 Kimi', url: 'https://api.moonshot.cn/v1' },
  { label: '智谱 GLM', url: 'https://open.bigmodel.cn/api/paas/v4' },
  { label: '硅基流动 SiliconFlow', url: 'https://api.siliconflow.cn/v1' },
  { label: '本地 Ollama', url: 'http://127.0.0.1:11434/v1' },
]
function candidates(field: keyof typeof savedModels, kind: Kind) {
  return [...new Set([form[field], savedModels[field], ...discovery[kind].models].filter(Boolean))]
}
const llmCandidates = computed(() => [...new Set([...candidates('LLM_CHAT_MODEL', 'llm'), ...candidates('LLM_EXTRACTION_MODEL', 'llm')])])
const embeddingCandidates = computed(() => candidates('EMBEDDING_MODEL', 'embedding'))
function payload(kind?: Kind): Record<string, unknown> {
  return Object.fromEntries(Object.entries(form).filter(([name, value]) => {
    if (kind && !name.startsWith(kind === 'llm' ? 'LLM_' : 'EMBEDDING_')) return false
    return !(/_MODEL$|_PROVIDER_LABEL$|_API_KEY$/.test(name) && typeof value === 'string' && !value.trim())
  }))
}
onMounted(async () => {
  try {
    const settings = await api.read()
    for (const name of Object.keys(form)) {
      if (!name.endsWith('API_KEY') && name in settings) Object.assign(form, { [name]: settings[name as keyof typeof settings] })
    }
    Object.assign(savedModels, { LLM_CHAT_MODEL: form.LLM_CHAT_MODEL, LLM_EXTRACTION_MODEL: form.LLM_EXTRACTION_MODEL, EMBEDDING_MODEL: form.EMBEDDING_MODEL })
    configured.llm = settings.LLM_API_KEY_configured
    configured.embedding = settings.EMBEDDING_API_KEY_configured
    active.value = `当前生效：大模型 ${settings.active?.LLM_MODE === 'live' ? '在线' : '演示'} · 向量 ${settings.active?.EMBEDDING_MODE === 'online' ? settings.active.EMBEDDING_MODEL : '演示'}`
    ready.value = true
  } catch (error) { failed.value = true; message.value = error instanceof Error ? error.message : '读取失败' }
})
onUnmounted(() => Object.values(timers).forEach(timer => clearInterval(timer)))
async function save() {
  saving.value = true; message.value = ''; failed.value = false
  try {
    const settings = await api.save(payload())
    configured.llm = settings.LLM_API_KEY_configured; configured.embedding = settings.EMBEDDING_API_KEY_configured
    for (const name of Object.keys(savedModels) as (keyof typeof savedModels)[]) { savedModels[name] = settings[name]; form[name] = settings[name] }
    form.LLM_API_KEY = ''; form.EMBEDDING_API_KEY = ''
    message.value = settings.message ?? '已保存，请重启软件使设置生效。'
  } catch (error) { failed.value = true; message.value = error instanceof Error ? error.message : '保存失败' }
  finally { saving.value = false }
}
async function discover(kind: Kind) {
  const state = discovery[kind]
  state.busy = true; state.error = ''
  try {
    const response = await api.models(payload(kind), kind)
    Object.assign(state, { models: response.models, count: response.count, done: true, latency: response.latency_ms, error: response.error ?? '' })
  } catch (error) { state.error = error instanceof Error ? error.message : '识别失败，可手动填写模型名' }
  finally { state.busy = false }
}
async function test(kind: Kind) {
  if (testing[kind]) return
  testing[kind] = true; results[kind] = null
  dialog.kind = kind; dialog.elapsed = 0; started[kind] = performance.now()
  timers[kind] = setInterval(() => { if (dialog.kind === kind) dialog.elapsed = performance.now() - started[kind] }, 100)
  try { results[kind] = await api.test(payload(kind), kind) }
  catch (error) { results[kind] = { kind, ok: false, latency_ms: null, http_status: null, detail: {}, provider: kind === 'llm' ? form.LLM_BASE_URL : form.EMBEDDING_BASE_URL, error: error instanceof Error ? error.message : '测试失败' } }
  finally { testing[kind] = false; clearInterval(timers[kind]); delete timers[kind] }
}
</script>

<template>
  <section class="api-settings">
    <header class="page-heading"><p class="eyebrow">接口与模型</p><h2>API 设置</h2><p>{{ active }}</p></header>
    <p class="note">设置由本机所有课程共用。密钥留空表示保留已保存的密钥；保存后重启软件生效。</p>
    <p class="note">外部服务要求 HTTPS，本机地址可用 HTTP。先填地址与密钥，再获取模型列表或手动填写模型名。</p>
    <p v-if="message" role="status" class="notice" :class="{ error: failed }">{{ message }}</p>
    <form @submit.prevent="save">
      <div class="interface-grid">
        <section v-for="block in blocks" :key="block.kind" :data-kind="block.kind" class="interface-card" :aria-labelledby="`${block.kind}-title`">
          <header class="card-heading"><h3 :id="`${block.kind}-title`">{{ block.title }}</h3><span class="key-status">{{ configured[block.kind] ? '密钥已配置' : '密钥未配置' }}</span></header>
          <fieldset :disabled="!ready || saving">
            <label>服务名称（可选）<input v-model="form[`${block.prefix}_PROVIDER_LABEL`]" placeholder="填写便于识别的名称" /></label>
            <label>运行模式<select v-model="form[`${block.prefix}_MODE`]"><option value="demo">演示模式</option><option :value="block.kind === 'llm' ? 'live' : 'online'">在线 API</option></select></label>
            <label>API 地址<input v-model="form[`${block.prefix}_BASE_URL`]" type="url" placeholder="https://服务地址/v1" /></label>
            <div class="provider-pills" aria-label="服务商地址快捷填写"><button v-for="provider in providers" :key="provider.label" type="button" class="pill" @click="form[`${block.prefix}_BASE_URL`] = provider.url">{{ provider.label }}</button></div>
            <label>API Key<input v-model="form[`${block.prefix}_API_KEY`]" type="password" autocomplete="new-password" :placeholder="configured[block.kind] ? '已配置，留空保留' : '请输入 API Key'" /></label>
            <div class="discovery-row"><button type="button" class="secondary" :disabled="discovery[block.kind].busy" @click="discover(block.kind)">{{ discovery[block.kind].busy ? '正在获取…' : '获取模型列表' }}</button></div>
            <p v-if="discovery[block.kind].error" class="warning" role="status">{{ discovery[block.kind].error }}；仍可手动填写模型名。</p>
            <p v-else-if="discovery[block.kind].done" class="note">识别到 {{ discovery[block.kind].count }} 个模型（{{ discovery[block.kind].latency }} ms），可直接下拉选择或手动输入其他名称</p>
            <template v-if="block.kind === 'llm'">
              <label>聊天模型<input v-model="form.LLM_CHAT_MODEL" list="llm-models" placeholder="获取模型列表后选择，或手动填写" data-test="chat-model" /></label>
              <label>知识抽取模型<input v-model="form.LLM_EXTRACTION_MODEL" list="llm-models" placeholder="获取模型列表后选择，或手动填写" data-test="extraction-model" /></label>
              <datalist id="llm-models"><option v-for="model in llmCandidates" :key="model" :value="model" /></datalist>
            </template>
            <template v-else>
              <label>向量模型<input v-model="form.EMBEDDING_MODEL" list="embedding-models" placeholder="获取模型列表后选择，或手动填写" data-test="embedding-model" /></label>
              <datalist id="embedding-models"><option v-for="model in embeddingCandidates" :key="model" :value="model" /></datalist>
              <label>向量维度<input :value="form.EMBEDDING_DIMENSIONS" readonly /></label>
              <p class="note">更换向量模型前需备份并离线迁移现有课程向量，不能直接混用。</p>
            </template>
            <div class="test-actions"><button type="button" class="primary" :disabled="testing[block.kind]" @click="test(block.kind)">{{ testing[block.kind] ? '测试中…' : '测试连接' }}</button><button v-if="results[block.kind] || testing[block.kind]" type="button" class="secondary" @click="showResult(block.kind)">查看测试结果</button></div>
          </fieldset>
          <ConnectionResultDialog :open="dialog.kind === block.kind" :title="form[`${block.prefix}_PROVIDER_LABEL`] || block.title" :pending="testing[block.kind]" :elapsed="dialog.elapsed" :result="results[block.kind]" @close="dialog.kind = null" />
        </section>
      </div>
      <footer class="save-row"><button type="submit" class="primary" :disabled="saving || !ready">{{ saving ? '保存中…' : '保存设置' }}</button><span class="note">模型留空保留原选择；设置保存后重启生效。</span></footer>
    </form>
  </section>
</template>

<style scoped>
.api-settings{--paper:#faf8f4;--panel:#fffdfa;--line:#e6e0d6;--line-soft:#ece6dc;--ink:#23201c;--ink-muted:#8b8175;--accent:#9c4a34;--accent-hover:#7f3a27;--accent-soft:#f6ece7;--pine:#3f6157;--warn-bg:#fdf7e8;--warn-line:#e9d8ac;--warn-ink:#8a6a1f;max-width:1160px;padding:clamp(18px,3vw,32px);background:var(--paper);color:var(--ink);border:1px solid var(--line);border-radius:8px}
.page-heading{margin-bottom:16px}.eyebrow{color:var(--accent);font-size:12px;letter-spacing:.12em}h2{font-size:26px}h3{font-size:18px;margin:0}.note{color:var(--ink-muted);font-size:13px;line-height:1.7}.interface-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px;margin-top:24px}.interface-card{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:22px}.card-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;padding-bottom:16px;border-bottom:1px solid var(--line-soft);margin-bottom:16px}.key-status{font-size:12px;color:var(--pine)}fieldset{border:0;padding:0;margin:0;display:grid;gap:14px;min-width:0}label{display:grid;gap:6px;font-size:14px}input,select{width:100%;padding:10px 12px;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:4px;font:inherit;min-width:0}input::placeholder{color:var(--ink-muted)}button{font:inherit;min-height:36px;padding:8px 14px;border-radius:4px;cursor:pointer;box-shadow:none;transition:background .15s}button.primary{background:var(--accent);border:1px solid var(--accent);color:#fff}button.primary:hover{background:var(--accent-hover);border-color:var(--accent-hover)}button.secondary,button.pill{background:var(--panel);color:var(--ink);border:1px solid var(--line)}button.secondary:hover,button.pill:hover{background:var(--accent-soft)}button:disabled{opacity:.55;cursor:wait}.provider-pills{display:flex;flex-wrap:wrap;gap:6px}button.pill{font-size:11px;padding:4px 8px;min-height:28px;border-radius:14px}.test-actions,.save-row{display:flex;align-items:center;flex-wrap:wrap;gap:10px}.test-actions{padding-top:12px;border-top:1px solid var(--line-soft)}.save-row{margin-top:24px;padding-top:20px;border-top:1px solid var(--line)}.warning{background:var(--warn-bg);border:1px solid var(--warn-line);color:var(--warn-ink);padding:10px;font-size:13px;border-radius:4px}.notice{color:var(--pine);padding:12px;border:1px solid var(--line);background:var(--panel)}.error{color:var(--accent)}input:focus,select:focus,button:focus-visible{outline:2px solid var(--accent-soft);outline-offset:2px;border-color:var(--accent)}
@media(max-width:850px){.interface-grid{grid-template-columns:1fr}.interface-card{padding:18px}}
</style>
