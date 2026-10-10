<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import PageSheet from '../components/PageSheet.vue'
import PageHeader from '../components/PageHeader.vue'
import AppIcon from '../components/AppIcon.vue'
import ModelPicker from '../components/ModelPicker.vue'
import EmbeddingSettings from '../components/EmbeddingSettings.vue'
import { useSessionStore } from '../stores/session'
import { MODEL_CONFIG_API_KEY } from '../api/modelConfig'
import { MODEL_PROVIDERS, useModelDiscovery } from '../composables/useModelDiscovery'
import { useModelConfig } from '../composables/useModelConfig'
import { useRuntimeStore } from '../stores/runtime'

const api = inject(MODEL_CONFIG_API_KEY, null)
if (api === null) throw new Error('ModelSettingsView 需要注入 MODEL_CONFIG_API_KEY')

const runtime = useRuntimeStore()
const session = useSessionStore()
const isTeacher = computed(() => session.role === 'teacher')
const { status, saved, form, configured, keyRequired, busy, saving, testing, error, notice, testResult, load, save, test, clear } =
  useModelConfig({ api })
const discovery = useModelDiscovery(api, form, saved)
const {models,loading:discovering,message:discoveryMessage,provider,canDiscover,chooseProvider,refresh} = discovery
function changeProvider(event:Event) { chooseProvider((event.target as HTMLSelectElement).value) }
const confirmingClear = ref(false)
const baseInput = ref<HTMLInputElement | null>(null)
const lastTestTime = computed(() => {
  const value = saved.value?.last_test?.tested_at
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat('zh-CN', {year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}).format(date)
})

async function confirmClear(): Promise<void> {
  confirmingClear.value = false
  await clear()
}
</script>

<template>
 <PageSheet labelledby="mc-title" compact class="model-settings" :class="{ 'model-settings--teacher': isTeacher }" data-test="model-settings">
  <PageHeader id="mc-title" title="模型 API 设置" :description="isTeacher ? '管理用于图谱生成与课程问答的个人模型连接。' : '管理用于课程问答的个人模型连接。'" />
  <p v-if="runtime.isDemo" class="ui-notice" data-test="mc-demo" role="status">当前为演示模式：系统使用内置的演示模型，个人配置不生效。</p>
  <div class="model-settings__grid">
  <section class="model-settings__card" aria-labelledby="mc-card-title">
   <header class="model-settings__card-heading"><h3 id="mc-card-title">通用模型 API</h3><p>{{ isTeacher ? '用于知识图谱生成与课程问答' : '用于课程问答' }}</p></header>
  <div v-if="status === 'loading'" class="ui-state" data-test="mc-loading" role="status" aria-busy="true"><p>正在加载配置…</p><div class="ui-skeleton" aria-hidden="true" /></div>
  <div v-else-if="status === 'error'" class="ui-state"><p class="ui-notice ui-notice--danger" data-test="mc-error" role="alert">{{ error }}</p><button class="ui-btn" type="button" data-test="mc-retry" @click="load">重试</button></div>
  <template v-else>
   <section class="ui-config-status" aria-labelledby="mc-status-title">
    <span class="ui-config-status__icon" :class="{ 'is-configured': configured }"><AppIcon :name="configured ? 'check' : 'key'" :size="22" /></span>
    <div class="ui-config-status__body"><h3 id="mc-status-title">{{ configured ? '连接已配置' : '连接尚未配置' }}</h3><p data-test="mc-status"><template v-if="configured">已配置：{{ saved?.model }} · 密钥 ••••{{ saved?.key_hint }}</template><template v-else>{{ isTeacher ? '尚未配置。保存后才能上传资料生成图谱或提问。' : '尚未配置。保存后才能向课程助教提问。' }}</template></p><p v-if="saved?.last_test" data-test="mc-last-tested" :class="saved.last_test.ok ? 'ui-text-success' : 'ui-text-danger'">最近测试{{ saved.last_test.ok ? '成功' : '失败' }}<template v-if="lastTestTime"> · <time :datetime="saved.last_test.tested_at">{{ lastTestTime }}</time></template></p></div>
    <button v-if="!configured" type="button" class="ui-btn" data-test="mc-configure" @click="baseInput?.focus()">去配置<AppIcon name="chevron" :size="14" /></button>
   </section>
   <form class="ui-config-form" data-test="mc-form" novalidate :aria-busy="busy !== null" @submit.prevent="save">
    <section class="ui-config-section" aria-labelledby="mc-connection-title">
     <h3 id="mc-connection-title" class="sr-only">通用模型连接配置</h3>
     <div class="ui-field"><label for="mc-provider">模型供应商</label><select id="mc-provider" data-test="mc-provider" :value="provider" :disabled="busy !== null" @change="changeProvider"><option v-for="item in MODEL_PROVIDERS" :key="item.id" :value="item.id">{{ item.name }}</option></select><p>选择后带入默认地址，也可按所在地域或代理服务修改。</p></div>
     <div class="ui-field"><label for="mc-base-url">服务地址</label><input ref="baseInput" id="mc-base-url" v-model="form.baseUrl" data-test="mc-base-url" type="url" inputmode="url" placeholder="https://api.deepseek.com" autocomplete="off" spellcheck="false" aria-describedby="mc-base-hint" :disabled="busy !== null" /><p id="mc-base-hint">使用服务商提供的 HTTPS API 地址。</p></div>
     <div class="ui-field"><label for="mc-api-key">API Key{{ keyRequired ? '' : '（不改可留空）' }}</label><input id="mc-api-key" v-model="form.apiKey" data-test="mc-api-key" type="password" autocomplete="off" spellcheck="false" :aria-required="keyRequired" aria-describedby="mc-key-hint" :disabled="busy !== null" /><p id="mc-key-hint">填写后自动获取模型。密钥加密保存在服务端，保存后不再显示。</p></div>
     <div class="ui-model-directory"><button type="button" class="ui-btn" data-test="mc-refresh-models" aria-label="刷新模型列表（通用模型）" :disabled="!canDiscover || discovering || busy !== null" @click="refresh">{{ discovering ? '正在获取模型…' : '刷新模型列表' }}</button><p v-if="discovering || discoveryMessage" class="ui-muted" data-test="mc-discovery-status" role="status" :aria-busy="discovering">{{ discovering ? '正在查询供应商可用模型…' : discoveryMessage }}</p></div>
     <div class="ui-field"><label for="mc-model">&#27169;&#22411;&#21517;&#31216;</label><ModelPicker id="mc-model" v-model="form.model" :models="models" :disabled="busy !== null" test-prefix="mc" /></div>
     <div class="ui-thinking"><div class="ui-thinking__row"><label class="ui-switch" for="mc-thinking"><input id="mc-thinking" v-model="form.disableThinking" data-test="mc-disable-thinking" type="checkbox" role="switch" :aria-checked="form.disableThinking" aria-describedby="mc-disable-thinking-hint" :disabled="busy !== null" /><span class="ui-switch__track" aria-hidden="true" /><span>关闭模型思考</span></label></div><p id="mc-disable-thinking-hint">仅适用于支持 thinking 的接口，请先测试连接。</p></div>
    </section>
    <section class="ui-config-actions" aria-label="配置操作">
     <p v-if="error" class="ui-notice ui-notice--danger" data-test="mc-error" role="alert">{{ error }}</p>
     <p v-if="notice" class="ui-notice ui-notice--success" data-test="mc-notice" role="status">{{ notice }}</p>
     <p v-if="testResult" class="ui-notice" data-test="mc-test-result" :class="testResult.ok ? 'ui-notice--success' : 'ui-notice--danger'" role="status">{{ testResult.text }}</p>
     <div class="ui-actions"><button type="submit" class="ui-btn ui-btn--primary" data-test="mc-save" :disabled="busy !== null">{{ saving ? '正在保存…' : '保存' }}</button><button type="button" class="ui-btn" data-test="mc-test" aria-label="测试连接（通用模型）" :disabled="busy !== null" @click="test">{{ testing ? '正在测试…' : '测试连接' }}</button><button v-if="configured && !confirmingClear" type="button" class="ui-btn ui-btn--ghost ui-btn--danger ui-clear" data-test="mc-clear" :disabled="busy !== null" @click="confirmingClear = true">清除配置</button></div>
     <p class="ui-muted ui-cost-hint">测试连接会向你的服务发送一次极小的请求（输出 1 个 token），费用可忽略。</p>
     <div v-if="confirmingClear" class="ui-config-confirm" role="alertdialog" aria-labelledby="mc-clear-title"><p id="mc-clear-title">清除后，你尚未结束的图谱生成任务会终止，需要重新上传。确定清除？</p><div class="ui-actions"><button type="button" class="ui-btn ui-btn--danger" data-test="mc-clear-confirm" :disabled="busy !== null" @click="confirmClear">确定清除</button><button type="button" class="ui-btn" data-test="mc-clear-cancel" :disabled="busy !== null" @click="confirmingClear = false">取消</button></div></div>
    </section>
   </form>
  </template>
  </section>
  <EmbeddingSettings v-if="isTeacher" />
  </div>
  <details class="model-settings__help"><summary>密钥安全与接口说明</summary><p>使用供应商提供的 HTTPS 地址。输入 API Key 后自动获取模型，也可手动输入。密钥加密保存，不提供给其他用户。模型目录可能包含其他类型，请先测试确认模型能力与向量维度。</p><p>关闭思考适用于支持 thinking 字段的接口（如 DeepSeek），通常更快、更省 token，但复杂问题质量可能下降；其他接口可能不支持，请先测试。</p></details>
 </PageSheet>
</template>
