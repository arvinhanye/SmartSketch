<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { createApiSettingsClient } from '../api/apiSettings'
import { useSessionStore } from '../stores/session'

const session = useSessionStore()
const router = useRouter()
const api = createApiSettingsClient(() => session.accessToken, () => { session.signOut(); void router.replace('/') })
const busy = ref(false)
const ready = ref(false)
const message = ref('')
const failed = ref(false)
const configured = reactive({ llm: false, embedding: false })
const active = ref('')
const form = reactive({ LLM_MODE: 'demo', LLM_BASE_URL: 'https://api.deepseek.com/v1', LLM_CHAT_MODEL: 'deepseek-chat', LLM_EXTRACTION_MODEL: 'deepseek-chat', LLM_API_KEY: '', EMBEDDING_MODE: 'demo', EMBEDDING_BASE_URL: 'https://dashscope.aliyuncs.com/compatible-mode/v1', EMBEDDING_MODEL: 'text-embedding-v4', EMBEDDING_DIMENSIONS: 1024, EMBEDDING_API_KEY: '' })

async function run(action: () => Promise<void>) {
  busy.value = true
  message.value = ''
  failed.value = false
  try { await action() } catch (error) { failed.value = true; message.value = error instanceof Error ? error.message : '操作失败' }
  finally { busy.value = false }
}
onMounted(() => run(async () => {
  const settings = await api.read()
  for (const name of Object.keys(form)) {
    if (name.endsWith('API_KEY')) continue
    if (name in settings) Object.assign(form, { [name]: settings[name as keyof typeof settings] })
  }
  configured.llm = settings.LLM_API_KEY_configured
  configured.embedding = settings.EMBEDDING_API_KEY_configured
  active.value = `当前生效：大模型 ${settings.active?.LLM_MODE === 'live' ? '在线' : '演示'} · 向量 ${settings.active?.EMBEDDING_MODE === 'online' ? settings.active.EMBEDDING_MODEL : '演示'}`
  ready.value = true
}))
function save() { void run(async () => {
  const result = await api.save({ ...form })
  configured.llm = result.LLM_API_KEY_configured
  configured.embedding = result.EMBEDDING_API_KEY_configured
  form.LLM_API_KEY = ''; form.EMBEDDING_API_KEY = ''
  message.value = result.message ?? '已保存，请重启软件。'
}) }
function test(kind: string) { void run(async () => { message.value = (await api.test({ ...form }, kind)).message ?? '连接成功' }) }
</script>

<template>
  <section class="api-settings">
    <h2>API 设置</h2>
    <p>{{ active }}</p>
    <p class="api-note">设置由本机所有课程共用。密钥留空表示保留已保存的密钥；保存后重启软件生效。</p>
    <p v-if="message" role="status" :class="{ 'api-error': failed }">{{ message }}</p>
    <form @submit.prevent="save">
      <fieldset :disabled="busy || !ready">
        <legend>大模型 · DeepSeek</legend>
        <label>运行模式<select v-model="form.LLM_MODE"><option value="demo">演示模式</option><option value="live">在线 API</option></select></label>
        <label>API 地址<input v-model="form.LLM_BASE_URL" type="url" required /></label>
        <label>API Key<input v-model="form.LLM_API_KEY" type="password" autocomplete="new-password" :placeholder="configured.llm ? '已配置，留空保留' : '请输入 API Key'" /></label>
        <label>聊天模型<input v-model="form.LLM_CHAT_MODEL" required /></label>
        <label>知识抽取模型<input v-model="form.LLM_EXTRACTION_MODEL" required /></label>
        <button type="button" data-variant="secondary" @click="test('llm')">测试 DeepSeek 连接</button>
      </fieldset>
      <fieldset :disabled="busy || !ready">
        <legend>向量模型 · 通义</legend>
        <label>运行模式<select v-model="form.EMBEDDING_MODE"><option value="demo">演示模式</option><option value="online">在线 API</option></select></label>
        <label>API 地址<input v-model="form.EMBEDDING_BASE_URL" type="url" required /></label>
        <label>API Key<input v-model="form.EMBEDDING_API_KEY" type="password" autocomplete="new-password" :placeholder="configured.embedding ? '已配置，留空保留' : '请输入 API Key'" /></label>
        <label>模型名称<input v-model="form.EMBEDDING_MODEL" required /></label>
        <label>向量维度<input :value="form.EMBEDDING_DIMENSIONS" readonly /></label>
        <p class="api-note">更换向量模型前需备份并迁移现有课程向量，不能直接混用。测试连接会发送少量文本。</p>
        <button type="button" data-variant="secondary" @click="test('embedding')">测试通义连接</button>
      </fieldset>
      <button type="submit" :disabled="busy || !ready">{{ busy ? '处理中…' : '保存设置' }}</button>
    </form>
  </section>
</template>

<style scoped>
.api-settings{max-width:960px;padding:24px;background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius-lg);box-shadow:var(--shadow-card)}
form{display:grid;gap:20px;margin-top:20px}fieldset{border:1px solid var(--color-border);border-radius:10px;padding:20px;display:grid;gap:12px}legend{font-weight:600;padding:0 8px}label{display:grid;gap:4px}input,select{width:100%;padding:10px;border:1px solid var(--color-border-strong);border-radius:6px;font:inherit}button{justify-self:start}.api-note{color:var(--color-text-muted);font-size:14px}.api-error{color:var(--color-danger-text)}
</style>
