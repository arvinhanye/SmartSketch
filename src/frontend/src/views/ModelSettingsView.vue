<script setup lang="ts">
import { computed, inject, onBeforeUnmount, ref, watch } from 'vue'
import { MODEL_CONFIG_API_KEY } from '../api/modelConfig'
import { useModelConfig } from '../composables/useModelConfig'
import { useRuntimeStore } from '../stores/runtime'

/**
 * L10（ADR-080）：个人模型 API 设置页。
 *
 * 外观沿用改版设计（单张「我的模型 API」卡片、服务商地址预设、连接结果弹窗），
 * 数据与操作继续走 `useModelConfig` + `/api/v1/me/model-config`：
 * 只填地址与模型名，密钥经个人配置接口加密存服务端，不回显、不落浏览器存储。
 * 页面只保留「地址预设」这一项本地状态，不引入模型发现、向量设置或全局配置。
 */
const api = inject(MODEL_CONFIG_API_KEY, null)
if (api === null) throw new Error('ModelSettingsView 需要注入 MODEL_CONFIG_API_KEY')

const runtime = useRuntimeStore()
const { status, saved, form, configured, keyRequired, busy, saving, testing, error, notice, testResult, load, save, test, clear } =
  useModelConfig({ api })
const confirmingClear = ref(false)

/**
 * 服务商地址预设：只提供 HTTPS 地址，模型 ID 仍由用户手填。
 * 这些值是来源提交中的静态预设，本次没有逐家联网验证，页面不宣称全部已验证可用。
 * 不含本地 Ollama / 私网地址：目标 URL 校验会拒绝该类地址，放宽它属于后端任务。
 */
type ProviderPreset = { id: string; label: string; url: string }
const providerPresets: ProviderPreset[] = [
  { id: 'deepseek', label: 'DeepSeek', url: 'https://api.deepseek.com/v1' },
  { id: 'dashscope', label: '阿里云百炼（通义）', url: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
  { id: 'openai', label: 'OpenAI', url: 'https://api.openai.com/v1' },
  { id: 'moonshot', label: '月之暗面 Kimi', url: 'https://api.moonshot.cn/v1' },
  { id: 'zhipu', label: '智谱 GLM', url: 'https://open.bigmodel.cn/api/paas/v4' },
  { id: 'siliconflow', label: '硅基流动 SiliconFlow', url: 'https://api.siliconflow.cn/v1' },
  { id: 'openrouter', label: 'OpenRouter', url: 'https://openrouter.ai/api/v1' },
  { id: 'ark', label: '火山方舟', url: 'https://ark.cn-beijing.volces.com/api/v3' },
  { id: 'hunyuan', label: '腾讯混元', url: 'https://api.hunyuan.cloud.tencent.com/v1' },
  { id: 'qianfan', label: '百度千帆', url: 'https://qianfan.baidubce.com/v2' },
  { id: 'minimax-cn', label: 'MiniMax（国内）', url: 'https://api.minimax.chat/v1' },
  { id: 'minimax-intl', label: 'MiniMax（国际）', url: 'https://api.minimaxi.com/v1' },
]
const selectedProvider = computed(
  () => providerPresets.find((preset) => preset.url === form.baseUrl.trim())?.id ?? 'custom',
)
function chooseProvider(event: Event): void {
  const id = (event.target as HTMLSelectElement).value
  const preset = providerPresets.find((item) => item.id === id)
  if (preset === undefined) return
  // 换地址后原密钥不再适用：清掉未提交的输入，保存时会要求重新填写
  if (preset.url !== form.baseUrl.trim()) form.apiKey = ''
  form.baseUrl = preset.url
}

/** 连接结果弹窗：只承载展示，不改变测试请求本身的生命周期 */
const testDialog = ref<HTMLDialogElement | null>(null)
/** 表单已改动：当前显示的结果不再代表这次配置 */
const resultObsolete = ref(false)

function closeTestDialog(): void {
  const dialog = testDialog.value
  // 结果展示只是展示层：环境不支持原生 dialog 时不因此中断测试请求
  if (dialog !== null && dialog.open && typeof dialog.close === 'function') dialog.close()
}

async function runConnectionTest(): Promise<void> {
  if (busy.value !== null) return
  resultObsolete.value = false
  const dialog = testDialog.value
  if (dialog !== null && !dialog.open && typeof dialog.showModal === 'function') dialog.showModal()
  await test()
}

// 改表单立即作废旧结果并收起弹窗；关闭弹窗不等于取消后台测试请求
watch(
  [() => form.baseUrl, () => form.model, () => form.apiKey],
  () => {
    if (testing.value || testResult.value !== null) resultObsolete.value = true
    closeTestDialog()
  },
  { flush: 'sync' },
)
// 换号后旧会话的结果不再展示，也不重开弹窗
watch(() => runtime.owner, closeTestDialog, { flush: 'sync' })
onBeforeUnmount(closeTestDialog)

async function confirmClear(): Promise<void> {
  confirmingClear.value = false
  await clear()
}
</script>

<template>
  <div class="page model-settings" data-test="model-settings">
    <header class="model-settings__head">
      <h2 id="mc-title">模型 API 设置</h2>
      <p class="model-settings__lead">
        教师生成知识图谱、学生提问都使用你自己填写的模型 API。密钥加密保存在服务端，保存后不再显示，也不会提供给其他用户。
      </p>
    </header>

    <p v-if="runtime.isDemo" class="model-settings__demo" data-test="mc-demo" role="status">
      当前为演示模式：系统使用内置的演示模型，个人配置不生效。
    </p>

    <p v-if="status === 'loading'" data-test="mc-loading" role="status">正在加载配置…</p>
    <div v-else-if="status === 'error'" class="model-settings__error">
      <p data-test="mc-error" role="alert">{{ error }}</p>
      <button type="button" data-variant="secondary" data-test="mc-retry" @click="load">重试</button>
    </div>

    <section v-else class="surface-card model-card" aria-labelledby="mc-card-title">
      <header class="model-card__head">
        <h3 id="mc-card-title" class="model-card__title">我的模型 API</h3>
        <span class="model-card__badge" data-test="mc-status">
          <template v-if="configured">
            已配置：{{ saved?.model }} · 密钥 ••••{{ saved?.key_hint }}
            <template v-if="saved?.last_test"> · 最近测试{{ saved.last_test.ok ? '成功' : '失败' }}</template>
          </template>
          <template v-else>尚未配置。保存后才能上传资料生成图谱或提问。</template>
        </span>
      </header>

      <form class="model-card__form" data-test="mc-form" novalidate @submit.prevent="save">
        <fieldset :disabled="busy !== null">
          <label for="mc-provider">服务商地址预设</label>
          <select id="mc-provider" data-test="mc-provider" :value="selectedProvider" @change="chooseProvider">
            <option v-for="preset in providerPresets" :key="preset.id" :value="preset.id">{{ preset.label }}</option>
            <option value="custom">自定义地址</option>
          </select>
          <p class="model-card__note" data-test="mc-provider-note">
            地址预设只填写服务地址，模型名称仍需手填；这里不校验服务商当前可用性。
          </p>

          <label for="mc-base-url">服务地址</label>
          <input id="mc-base-url" v-model="form.baseUrl" data-test="mc-base-url" type="url" inputmode="url"
                 placeholder="https://api.deepseek.com/v1" autocomplete="off" spellcheck="false" />

          <label for="mc-model">模型名称</label>
          <input id="mc-model" v-model="form.model" data-test="mc-model" type="text" placeholder="deepseek-flash"
                 autocomplete="off" spellcheck="false" />

          <label for="mc-api-key">密钥{{ keyRequired ? '' : '（不改可留空）' }}</label>
          <input id="mc-api-key" v-model="form.apiKey" data-test="mc-api-key" type="password"
                 autocomplete="off" spellcheck="false" :aria-required="keyRequired" />

          <p v-if="error" class="model-card__alert" data-test="mc-error" role="alert">{{ error }}</p>
          <p v-if="notice" class="model-card__ok" data-test="mc-notice" role="status">{{ notice }}</p>
          <p v-if="resultObsolete" class="model-card__note" data-test="mc-test-stale" role="status">
            表单已修改，请重新测试当前配置
          </p>
          <p v-else-if="testResult" data-test="mc-test-result" :class="testResult.ok ? 'is-ok' : 'is-bad'" role="status">
            {{ testResult.text }}
          </p>

          <div class="model-card__actions">
            <button type="submit" data-test="mc-save" :disabled="busy !== null">{{ saving ? '正在保存…' : '保存' }}</button>
            <button type="button" data-variant="secondary" data-test="mc-test" :disabled="busy !== null" @click="runConnectionTest">
              {{ testing ? '正在测试…' : '测试连接' }}
            </button>
            <button v-if="configured && !confirmingClear" type="button" data-variant="secondary" data-test="mc-clear" :disabled="busy !== null"
                    @click="confirmingClear = true">清除配置</button>
          </div>
          <p class="model-card__note">测试连接会向你的服务发送一次极小的请求（输出 1 个 token），费用可忽略。</p>

          <div v-if="confirmingClear" class="model-card__confirm" role="alertdialog" aria-labelledby="mc-clear-title">
            <p id="mc-clear-title">清除后，你尚未结束的图谱生成任务会终止，需要重新上传。确定清除？</p>
            <div class="model-card__actions">
              <button type="button" data-test="mc-clear-confirm" :disabled="busy !== null" @click="confirmClear">确定清除</button>
              <button type="button" data-variant="secondary" data-test="mc-clear-cancel" @click="confirmingClear = false">取消</button>
            </div>
          </div>
        </fieldset>
      </form>
    </section>

    <!-- 连接结果弹窗：原生 dialog，Esc 与关闭按钮只收起展示，后台测试请求不受影响 -->
    <dialog ref="testDialog" class="model-dialog" data-test="mc-test-dialog" aria-labelledby="mc-dialog-title">
      <h3 id="mc-dialog-title" class="model-dialog__title">连接测试结果</h3>
      <p v-if="testing" class="model-dialog__status" role="status">正在测试连接…</p>
      <p v-else-if="error" class="model-dialog__error" role="alert">{{ error }}</p>
      <p v-else-if="testResult && !resultObsolete" class="model-dialog__result" data-test="mc-dialog-result" role="status">
        {{ testResult.text }}
      </p>
      <p v-else class="model-dialog__status" role="status">表单已修改，请重新测试当前配置</p>
      <div class="model-dialog__actions">
        <button type="button" autofocus data-test="mc-dialog-close" @click="closeTestDialog">关闭</button>
      </div>
    </dialog>
  </div>
</template>

<style scoped>
.model-settings {
  width: 100%;
  max-width: 44rem;
  margin-inline: auto;
  gap: 1.1rem;
}

.model-settings__head {
  display: grid;
  gap: 0.4rem;
}

.model-settings__head h2 {
  margin: 0;
  font-size: clamp(1.625rem, 2.2vw, 1.875rem);
  font-weight: 700;
  line-height: 1.25;
}

.model-settings__lead,
.model-card__note {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.8125rem;
  line-height: 1.7;
}

.model-settings__demo {
  margin: 0;
  padding: 0.6rem 0.85rem;
  border: 1px solid var(--color-warning-border);
  border-radius: var(--radius-sm);
  background: var(--color-warning-bg);
  color: var(--color-warning-text);
  font-size: 0.875rem;
}

.model-settings__error {
  display: grid;
  gap: 0.6rem;
  justify-items: start;
}

/* 单模型卡片：暖白底、细边框、轻阴影、12px 圆角 */
.model-card {
  display: grid;
  gap: 0.9rem;
  min-width: 0;
  padding: clamp(1.15rem, 2.2vw, 1.5rem);
  border-radius: 12px;
}

.model-card__head {
  display: grid;
  gap: 0.35rem;
}

.model-card__title {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 700;
}

.model-card__badge {
  color: var(--color-text-muted);
  font-size: 0.8125rem;
  line-height: 1.7;
}

.model-card__form fieldset {
  display: grid;
  gap: 0.55rem;
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 0;
  border: none;
  background: none;
}

.model-card__form label {
  color: var(--color-text);
  font-size: 0.875rem;
  font-weight: 500;
}

.model-card__form input,
.model-card__form select {
  width: 100%;
  min-height: 2.6rem;
  padding: 0.5rem 0.65rem;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  font: inherit;
}

.model-card__form input:focus-visible,
.model-card__form select:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.model-card__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  margin-top: 0.35rem;
}

.model-card__alert,
.model-card__ok {
  margin: 0;
  font-size: 0.875rem;
}

.model-card__alert {
  color: var(--color-danger-text);
}

.model-card__ok {
  color: var(--color-success-text);
}

.model-card__confirm {
  display: grid;
  gap: 0.6rem;
  margin-top: 0.35rem;
  padding: 0.85rem 1rem;
  border: 1px solid var(--color-danger-border);
  border-radius: 10px;
  background: var(--color-danger-bg);
}

.model-card__confirm p {
  margin: 0;
  color: var(--color-danger-text);
  font-size: 0.875rem;
}

.is-ok {
  color: var(--color-success-text);
}

.is-bad {
  color: var(--color-danger-text);
}

/* ---------------------------------------------------------------- 结果弹窗 */
.model-dialog {
  width: min(100%, 22rem);
  max-height: 90vh;
  overflow: auto;
  padding: 1.15rem;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: var(--color-surface);
  color: var(--color-text);
}

.model-dialog::backdrop {
  background: rgb(35 32 28 / 32%);
}

.model-dialog__title {
  margin: 0 0 0.6rem;
  font-size: 1.0625rem;
}

.model-dialog__status,
.model-dialog__result,
.model-dialog__error {
  margin: 0 0 0.6rem;
  font-size: 0.875rem;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.model-dialog__status {
  color: var(--color-text-muted);
}

.model-dialog__error {
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--color-danger-border);
  border-radius: var(--radius-sm);
  background: var(--color-danger-bg);
  color: var(--color-danger-text);
}

.model-dialog__actions {
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 480px) {
  .model-card__actions button {
    flex: 1 1 auto;
  }
}
</style>
