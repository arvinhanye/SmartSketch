<script setup lang="ts">
import { computed, inject, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { MODEL_CONFIG_API_KEY } from '../api/modelConfig'
import { useModelConfig } from '../composables/useModelConfig'
import { useRuntimeStore } from '../stores/runtime'

/**
 * L10（ADR-080）：个人模型 API 设置页。
 *
 * 视觉沿用来源 frontend-ui-revision 的 `ApiSettings.vue` 接口卡骨架：
 * `.page` 外层（透明，标题直接落在背景上）+ 一张 `.surface-card` 接口卡（卡头带分隔线、
 * 字段成组、卡片底部分隔的测试区）+ 卡片外的页尾保存区。
 *
 * 数据与操作继续走 `useModelConfig` + `/api/v1/me/model-config`：
 * 只保留一张真实的个人大模型卡，不恢复全局 API/向量配置、模型发现或本地 Ollama 能力；
 * 密钥经个人配置接口加密存服务端，不回显、不落浏览器存储。
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

/** 弹窗展示本次测试用到的配置：只保存真实值，不编造服务端字段 */
type TestDisplayContext = { baseUrl: string; model: string; providerLabel: string }
/**
 * 连接测试的展示快照：只描述「这一次测试」，与保存/清除共用的 `error` 完全分离。
 *
 * 这样做的原因（复审 R1/R2/R3）：
 * - 保存或清除失败会写入通用 `error`；若弹窗读它，会把「保存失败」显示成「连接失败」；
 * - 测试失败（429、超时、网络错误）时 composable 不会产出 testResult，必须靠快照保留
 *   本次测试的地址、模型与错误文本，否则弹窗会退回「等待测试」；
 * - 快照绑定发起时的 `runtime.owner`：换号后旧账号的结论不能重新生效。
 */
type TestSnapshotStatus = 'pending' | 'success' | 'failure'
interface TestSnapshot {
  owner: string | null
  baseUrl: string
  model: string
  providerLabel: string
  status: TestSnapshotStatus
  /** 成功/失败的健康文本，直接来自 composable 的真实现有字段 */
  text: string | null
  /** 测试本身抛错时的固定文案；保存/清除的错误不会进这里 */
  error: string | null
}

const testSnapshot = ref<TestSnapshot | null>(null)
const testDialog = ref<HTMLDialogElement | null>(null)
const testButton = ref<HTMLButtonElement | null>(null)
const viewResultButton = ref<HTMLButtonElement | null>(null)
/** 关闭弹窗是否由用户发起（Esc / ×）；只有这种关闭才把焦点还给触发按钮 */
let userInitiatedClose = false
/** 快照是否已被「表单改动」作废（保留快照本身，用于显示『请重新测试』并挡住重看入口） */
const snapshotStale = ref(false)
/** 正在进行的操作是否为测试：test() 失败时 busy 也会回到 null，据此区分「测试结束」与「保存/清除结束」 */
const testingInFlight = ref(false)

/** 快照不再代表当前配置：表单被改动，或已换号 */
const resultObsolete = computed(
  () => testSnapshot.value !== null && (snapshotStale.value || testSnapshot.value.owner !== runtime.owner),
)
/** 有可展示的、未失效的测试结论（含失败），用于重看入口与页面内提示 */
const snapshotAvailable = computed(
  () => testSnapshot.value !== null && !resultObsolete.value,
)

function providerLabelFor(url: string): string {
  return providerPresets.find((preset) => preset.url === url.trim())?.label ?? '自定义地址'
}

function dropTestSnapshot(): void {
  testSnapshot.value = null
  snapshotStale.value = false
}

function closeTestDialog(): void {
  const dialog = testDialog.value
  // 结果展示只是展示层：环境不支持原生 dialog 时不因此中断测试请求
  if (dialog !== null && dialog.open && typeof dialog.close === 'function') dialog.close()
}

/**
 * 用户用 Esc 关闭原生 dialog：cancel 早于 close 触发，在这里记下「这次是用户关闭」，
 * 随后的 close 事件据此把焦点还给可用的触发按钮（复审 R4）。
 */
function onDialogCancel(): void {
  userInitiatedClose = true
}

/** 用户点 × 关闭：closeTestDialog 之后原生 close 事件仍会触发，这里只需标记来源 */
function onDialogCloseButton(): void {
  userInitiatedClose = true
  closeTestDialog()
}

/**
 * 用户关闭弹窗（Esc 或 ×）后把焦点还给可用的触发按钮：
 * 测试结束后测试按钮恢复可用；进行中则用已出现的「查看测试结果」。
 * 编辑表单、换号、卸载等自动关闭不调用这里，因此不会抢新页面的焦点。
 */
function restoreDialogTriggerFocus(): void {
  void nextTick(() => {
    if (typeof document === 'undefined') return
    const candidates: Array<HTMLButtonElement | null> = [viewResultButton.value, testButton.value]
    const target = candidates.find(
      (element): element is HTMLButtonElement =>
        element !== null && !element.disabled && document.contains(element),
    )
    if (target !== undefined) target.focus()
  })
}

/** 原生 dialog 的 close 事件：Esc 与 × 都会触发，这里只处理用户发起的关闭 */
function onDialogClose(): void {
  if (!userInitiatedClose) return
  userInitiatedClose = false
  restoreDialogTriggerFocus()
}

/** 只负责把已有结果重新展示出来，不发起任何请求 */
function showTestResult(): void {
  const dialog = testDialog.value
  if (dialog !== null && !dialog.open && typeof dialog.showModal === 'function') dialog.showModal()
}

async function runConnectionTest(): Promise<void> {
  if (busy.value !== null) return
  // 先记录这次测试针对的配置，再发起请求：晚到的响应不会与编辑中的值混淆
  const baseUrl = form.baseUrl.trim()
  snapshotStale.value = false
  testSnapshot.value = {
    owner: runtime.owner,
    baseUrl,
    model: form.model.trim(),
    providerLabel: providerLabelFor(baseUrl),
    status: 'pending',
    text: null,
    error: null,
  }
  showTestResult()
  testingInFlight.value = true
  try {
    await test()
  } finally {
    testingInFlight.value = false
  }
  const snapshot = testSnapshot.value
  // 测试期间换号或快照已清理：不把这次结果写到新会话上
  if (snapshot === null || snapshot.owner !== runtime.owner) return
  if (error.value !== null) {
    // 测试阶段的 error 只可能来自 test() 本身（保存/清除的 error 不会进快照）
    testSnapshot.value = { ...snapshot, status: 'failure', text: null, error: error.value }
    return
  }
  const result = testResult.value
  testSnapshot.value = result === null
    ? { ...snapshot, status: 'failure', text: null, error: '测试未返回结果，请重试。' }
    : { ...snapshot, status: result.ok ? 'success' : 'failure', text: result.text, error: null }
}

/** 表单改动：把已有快照标记为作废（保留用于提示）并收起弹窗；关闭弹窗不等于取消后台测试请求 */
watch(
  [() => form.baseUrl, () => form.model, () => form.apiKey],
  () => {
    // 测试进行中的改动只收起弹窗，不清也是不废：本次测试的地址与模型仍要显示在弹窗里
    if (!testing.value && testSnapshot.value !== null) snapshotStale.value = true
    closeTestDialog()
  },
  { flush: 'sync' },
)

/**
 * 保存或清除成功会清空 testResult，此时才复位本地展示（避免残留『表单已修改』提示）。
 * 测试失败（test() 抛错）同样让 busy 回到 null，但它不是「配置已变更」，必须把失败快照留下，
 * 因此这里按 testingInFlight 区分两种结束，而不是只看 testResult 是否为空（复审 R3）。
 */
watch(
  busy,
  (operation) => {
    if (operation === null && !testingInFlight.value && testResult.value === null) dropTestSnapshot()
  },
  { flush: 'post' },
)

// 换号后清掉展示快照（旧账号的结论与作废标记都不再展示），并自动收起弹窗；不抢焦点
watch(
  () => runtime.owner,
  () => {
    closeTestDialog()
    dropTestSnapshot()
  },
  { flush: 'sync' },
)
onBeforeUnmount(() => closeTestDialog())

async function confirmClear(): Promise<void> {
  confirmingClear.value = false
  await clear()
}
</script>

<template>
  <div class="page api-settings" data-test="model-settings">
    <header class="page__heading">
      <h2 id="mc-title">API 设置</h2>
      <p class="page__lede">
        这里设置的是你自己的模型 API（当前账号的个人配置）：教师生成知识图谱、学生提问都使用它。
        密钥加密保存在服务端，保存后不再显示，也不会提供给其他用户。
      </p>
    </header>

    <p v-if="runtime.isDemo" class="api-settings__note" data-test="mc-demo" role="status">
      <strong>演示模式：</strong>系统使用内置的演示模型，个人配置不生效。
    </p>

    <p v-if="status === 'loading'" data-test="mc-loading" role="status">正在加载配置…</p>
    <div v-else-if="status === 'error'" class="api-settings__error">
      <p class="notice error" data-test="mc-error" role="alert">{{ error }}</p>
      <button type="button" data-variant="secondary" data-test="mc-retry" @click="load">重试</button>
    </div>

    <template v-else>
      <form id="mc-form" data-test="mc-form" novalidate @submit.prevent="save">
        <div class="interface-grid">
          <section class="surface-card interface-card" aria-labelledby="mc-card-title">
            <header class="card-heading">
              <h3 id="mc-card-title">我的模型 API</h3>
              <span class="key-status" data-test="mc-status">
                <template v-if="configured">
                  已配置：{{ saved?.model }} · 密钥 ••••{{ saved?.key_hint }}
                  <template v-if="saved?.last_test"> · 最近测试{{ saved.last_test.ok ? '成功' : '失败' }}</template>
                </template>
                <template v-else>尚未配置。保存后才能上传资料生成图谱或提问。</template>
              </span>
            </header>

            <fieldset :disabled="busy !== null">
              <div class="field">
                <label for="mc-provider">服务商地址预设</label>
                <select id="mc-provider" data-test="mc-provider" :value="selectedProvider" @change="chooseProvider">
                  <option v-for="preset in providerPresets" :key="preset.id" :value="preset.id">{{ preset.label }}</option>
                  <option value="custom">自定义地址</option>
                </select>
              </div>
              <p class="api-settings__note" data-test="mc-provider-note">
                地址预设只填写服务地址，模型名称仍需手填；这里不校验服务商当前可用性。
              </p>

              <div class="field">
                <label for="mc-base-url">服务地址</label>
                <input id="mc-base-url" v-model="form.baseUrl" data-test="mc-base-url" type="url" inputmode="url"
                       placeholder="https://api.deepseek.com/v1" autocomplete="off" spellcheck="false" />
              </div>

              <div class="field">
                <label for="mc-api-key"> API Key{{ keyRequired ? '' : '（不改可留空）' }}</label>
                <input id="mc-api-key" v-model="form.apiKey" data-test="mc-api-key" type="password"
                       autocomplete="off" spellcheck="false" :aria-required="keyRequired" />
              </div>

              <div class="field">
                <label for="mc-model">模型名称</label>
                <input id="mc-model" v-model="form.model" data-test="mc-model" type="text" placeholder="deepseek-chat"
                       autocomplete="off" spellcheck="false" />
              </div>
              <p class="api-settings__note">这张卡同时用于知识抽取与课程问答。</p>

              <p v-if="error" class="notice error" data-test="mc-error" role="alert">{{ error }}</p>
              <p v-if="notice" class="notice" data-test="mc-notice" role="status">{{ notice }}</p>
              <!-- 页面内只展示「本次测试」的结论：保存/清除的失败留在上面的 mc-error，不冒充测试结果 -->
              <p v-if="resultObsolete" class="api-settings__note" data-test="mc-test-stale" role="status">
                表单已修改，请重新测试当前配置
              </p>
              <p v-else-if="snapshotAvailable" class="notice" data-test="mc-test-result"
                 :class="{ error: testSnapshot?.status === 'failure' }" role="status">
                {{ testSnapshot?.error ?? testSnapshot?.text }}
              </p>

              <div class="test-actions">
                <button ref="testButton" type="button" class="primary" data-test="mc-test" :disabled="busy !== null" @click="runConnectionTest">
                  {{ testing ? '测试中…' : '测试连接' }}
                </button>
              </div>
            </fieldset>
          </section>
        </div>

        <footer class="save-row">
          <button type="submit" class="primary" data-test="mc-save" :disabled="busy !== null">
            {{ saving ? '正在保存…' : '保存设置' }}
          </button>
          <button v-if="testing || snapshotAvailable" ref="viewResultButton" type="button" class="secondary"
                  data-test="mc-view-result" @click="showTestResult">
            查看测试结果
          </button>
          <button v-if="configured && !confirmingClear" type="button" class="secondary" data-test="mc-clear" :disabled="busy !== null"
                  @click="confirmingClear = true">清除配置</button>
          <button v-if="confirmingClear" type="button" class="secondary" data-test="mc-clear-cancel" @click="confirmingClear = false">取消</button>
          <p class="api-settings__note save-row__hint">测试连接会向你的服务发送一次极小的请求（输出 1 个 token），费用可忽略。</p>
        </footer>

        <div v-if="confirmingClear" class="clear-confirm" role="alertdialog" aria-labelledby="mc-clear-title">
          <p id="mc-clear-title" class="clear-confirm__text">清除后，你尚未结束的图谱生成任务会终止，需要重新上传。确定清除？</p>
          <div class="clear-confirm__actions">
            <button type="button" class="primary" data-test="mc-clear-confirm" :disabled="busy !== null" @click="confirmClear">确定清除</button>
            <button type="button" class="secondary" data-test="mc-clear-cancel-2" @click="confirmingClear = false">取消</button>
          </div>
        </div>
      </form>
    </template>

    <!-- 连接结果弹窗：原生 dialog；Esc 与关闭按钮只收起展示，后台测试请求不受影响。
         弹窗内容只读本次测试的展示快照，因此保存/清除的失败不会串进来（复审 R1）。 -->
    <dialog
      ref="testDialog"
      class="result-dialog"
      data-test="mc-test-dialog"
      aria-labelledby="mc-dialog-title"
      @cancel="onDialogCancel"
      @close="onDialogClose"
    >
      <header class="result-dialog__head">
        <h3 id="mc-dialog-title" class="result-dialog__title">
          {{ testSnapshot?.providerLabel ?? '模型接口' }}测试结果
        </h3>
        <button type="button" class="result-dialog__close" aria-label="关闭测试结果" data-test="mc-dialog-close"
                @click="onDialogCloseButton">×</button>
      </header>

      <p v-if="testing || testSnapshot?.status === 'pending'" class="result-dialog__status" role="status">测试中…</p>
      <p v-else-if="resultObsolete" class="result-dialog__status" role="status">表单已修改，请重新测试当前配置</p>
      <template v-else-if="testSnapshot !== null">
        <p class="result-dialog__state"
           :class="testSnapshot.status === 'success' ? 'result-dialog__state--success' : 'result-dialog__state--failure'"
           role="status">
          {{ testSnapshot.status === 'success' ? '连接成功' : '连接失败' }}
        </p>
        <dl class="result-dialog__facts">
          <dt>接口地址</dt>
          <dd>{{ testSnapshot.baseUrl || '未填写' }}</dd>
          <dt>使用模型</dt>
          <dd>{{ testSnapshot.model || '未填写' }}</dd>
        </dl>
        <p v-if="testSnapshot.error" class="notice error" role="alert">{{ testSnapshot.error }}</p>
        <p v-else-if="testSnapshot.text" class="result-dialog__detail" data-test="mc-dialog-result" role="status">
          {{ testSnapshot.text }}
        </p>
      </template>
      <p v-else class="result-dialog__status" role="status">尚未发起连接测试。</p>

      <small class="result-dialog__footnote">测试只发送一次最小请求；这里不展示密钥与原始请求内容。</small>
    </dialog>
  </div>
</template>

<style scoped>
/* 页面外层、标题与卡片外观全部来自全局公共类（.page / .page__* / .surface-card）；
 * 这里只保留本页特有的表单、按钮与状态提示样式，避免再次出现两套风格。 */
.api-settings {
  max-width: 1160px;
  min-width: 0;
}

.api-settings__note {
  color: var(--color-text-muted);
  font-size: 13px;
  line-height: 1.7;
  margin: 0;
}

.api-settings__error {
  display: grid;
  gap: 0.6rem;
  justify-items: start;
}

/* 字段成组：标签在上一行，控件占满下一行 */
.field {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.field > label {
  font-size: 14px;
}

/* 来源是「大模型 / 向量」两张卡的两列网格；这里只保留一张真实的个人卡，右侧留白不补假卡 */
.interface-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
  align-items: start;
}

.interface-card {
  min-width: 0;
}

.card-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--color-border);
  margin-bottom: 16px;
}

.card-heading h3 {
  margin: 0;
  font-size: 1.05rem;
  color: var(--color-text);
}

.key-status {
  font-size: 12px;
  color: var(--color-success-text);
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.interface-card fieldset {
  border: 0;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 14px;
  min-width: 0;
}

.api-settings input,
.api-settings select {
  width: 100%;
  min-width: 0;
  padding: 10px 12px;
  background: var(--color-surface);
  color: var(--color-text);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-sm);
  font: inherit;
}

.api-settings input::placeholder {
  color: var(--color-text-muted);
}

.api-settings input:focus-visible,
.api-settings select:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 1px;
}

.api-settings button {
  font: inherit;
  min-height: 36px;
  padding: 8px 14px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  box-shadow: none;
  transition: background 0.15s;
}

.api-settings button.primary {
  background: var(--color-primary);
  border: 1px solid var(--color-primary);
  color: #fff;
}

.api-settings button.primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
  border-color: var(--color-primary-hover);
}

.api-settings button.secondary {
  background: var(--color-surface);
  color: var(--color-text);
  border: 1px solid var(--color-border-strong);
}

.api-settings button.secondary:hover:not(:disabled) {
  background: var(--color-primary-soft);
}

.api-settings button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

/* 测试区在卡片底部的分隔区；保存按钮在卡片外的页尾 */
.test-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding-top: 12px;
  border-top: 1px solid var(--color-border);
}

.save-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid var(--color-border);
}

.save-row__hint {
  flex-basis: 100%;
}

/* 保存结果提示：成功用松绿、失败用砖红，二者都保持可辨识 */
.notice {
  color: var(--color-success-text);
  padding: 12px;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  font-size: 13px;
  border-radius: var(--radius-sm);
  margin: 0;
}

.notice.error {
  color: var(--color-danger-text);
  border-color: var(--color-danger-border);
  background: var(--color-danger-bg);
}

.clear-confirm {
  display: grid;
  gap: 10px;
  margin-top: 14px;
  padding: 12px 14px;
  border: 1px solid var(--color-danger-border);
  border-radius: var(--radius-sm);
  background: var(--color-danger-bg);
}

.clear-confirm__text {
  margin: 0;
  color: var(--color-danger-text);
  font-size: 13px;
  line-height: 1.7;
}

.clear-confirm__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

/* ---------------------------------------------------------------- 结果弹窗 */
/* 尺寸与圆角按来源 ConnectionResultDialog：22rem / 8px（复审 R5） */
.result-dialog {
  width: min(100%, 22rem);
  max-height: 90vh;
  overflow: auto;
  padding: 20px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-surface);
  color: var(--color-text);
}

.result-dialog::backdrop {
  background: rgb(35 32 28 / 32%);
}

.result-dialog__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.result-dialog__title {
  margin: 0;
  font-size: 1.0625rem;
}

/* 顶部 ×：来源是 32px 高、3px 10px 内边距的小按钮。
 * 用 .api-settings .result-dialog__close 提高优先级，避免被上面的通用按钮规则覆盖（复审 R5）。 */
.api-settings .result-dialog__close {
  flex: none;
  min-height: 32px;
  padding: 3px 10px;
  background: var(--color-surface);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: 1.1rem;
  line-height: 1;
  cursor: pointer;
}

.result-dialog__state {
  margin: 14px 0 0;
  font-size: 14px;
  font-weight: 600;
}

.result-dialog__state--success {
  color: var(--color-success-text);
}

.result-dialog__state--failure {
  color: var(--color-danger-text);
}

.result-dialog__status {
  margin: 14px 0 0;
  color: var(--color-text-muted);
  font-size: 13px;
  line-height: 1.7;
}

.result-dialog__facts {
  display: grid;
  grid-template-columns: 6rem minmax(0, 1fr);
  gap: 10px;
  margin: 14px 0 0;
  font-size: 14px;
}

.result-dialog__facts dt {
  color: var(--color-text-muted);
}

.result-dialog__facts dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.result-dialog__detail {
  margin: 12px 0 0;
  font-size: 13px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.result-dialog__footnote {
  display: block;
  margin-top: 14px;
  color: var(--color-text-muted);
  font-size: 12px;
  line-height: 1.7;
}

@media (max-width: 850px) {
  .interface-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
