<script setup lang="ts">
import { inject, ref } from 'vue'
import { MODEL_CONFIG_API_KEY } from '../api/modelConfig'
import { useModelConfig } from '../composables/useModelConfig'
import { useRuntimeStore } from '../stores/runtime'

const api = inject(MODEL_CONFIG_API_KEY, null)
if (api === null) throw new Error('ModelSettingsView 需要注入 MODEL_CONFIG_API_KEY')

const runtime = useRuntimeStore()
const { status, saved, form, configured, keyRequired, busy, saving, testing, error, notice, testResult, load, save, test, clear } =
  useModelConfig({ api })
const confirmingClear = ref(false)

async function confirmClear(): Promise<void> {
  confirmingClear.value = false
  await clear()
}
</script>

<template>
  <section class="model-settings" data-test="model-settings" aria-labelledby="mc-title">
    <h2 id="mc-title">模型 API 设置</h2>
    <p class="model-settings__lead">
      教师生成知识图谱、学生提问都使用你自己填写的模型 API。密钥加密保存在服务端，保存后不再显示，也不会提供给其他用户。
      目前支持 OpenAI 兼容的对话接口（已验证：DeepSeek）。
    </p>

    <p v-if="runtime.isDemo" class="model-settings__demo" data-test="mc-demo" role="status">
      当前为演示模式：系统使用内置的演示模型，个人配置不生效。
    </p>

    <p v-if="status === 'loading'" data-test="mc-loading" role="status">正在加载配置…</p>
    <div v-else-if="status === 'error'">
      <p data-test="mc-error" role="alert">{{ error }}</p>
      <button type="button" data-test="mc-retry" @click="load">重试</button>
    </div>
    <template v-else>
      <p class="model-settings__status" data-test="mc-status">
        <template v-if="configured">
          已配置：{{ saved?.model }} · 密钥 ••••{{ saved?.key_hint }}
          <span v-if="saved?.last_test"> · 最近测试{{ saved.last_test.ok ? '成功' : '失败' }}</span>
        </template>
        <template v-else>尚未配置。保存后才能上传资料生成图谱或提问。</template>
      </p>

      <form class="model-settings__form" data-test="mc-form" novalidate @submit.prevent="save">
        <label for="mc-base-url">服务地址</label>
        <input id="mc-base-url" v-model="form.baseUrl" data-test="mc-base-url" type="url" inputmode="url"
               placeholder="https://api.deepseek.com" autocomplete="off" spellcheck="false" />

        <label for="mc-model">模型名称</label>
        <input id="mc-model" v-model="form.model" data-test="mc-model" type="text" placeholder="deepseek-flash"
               autocomplete="off" spellcheck="false" />

        <label for="mc-api-key">密钥{{ keyRequired ? '' : '（不改可留空）' }}</label>
        <input id="mc-api-key" v-model="form.apiKey" data-test="mc-api-key" type="password"
               autocomplete="off" spellcheck="false" :aria-required="keyRequired" />

        <p v-if="error" data-test="mc-error" role="alert">{{ error }}</p>
        <p v-if="notice" data-test="mc-notice" role="status">{{ notice }}</p>
        <p v-if="testResult" data-test="mc-test-result" :class="testResult.ok ? 'is-ok' : 'is-bad'" role="status">
          {{ testResult.text }}
        </p>

        <div class="model-settings__actions">
          <button type="submit" data-test="mc-save" :disabled="busy !== null">{{ saving ? '正在保存…' : '保存' }}</button>
          <button type="button" data-test="mc-test" :disabled="busy !== null" @click="test">
            {{ testing ? '正在测试…' : '测试连接' }}
          </button>
          <button v-if="configured && !confirmingClear" type="button" data-test="mc-clear" :disabled="busy !== null"
                  @click="confirmingClear = true">清除配置</button>
        </div>
        <p class="model-settings__hint">测试连接会向你的服务发送一次极小的请求（输出 1 个 token），费用可忽略。</p>

        <div v-if="confirmingClear" class="model-settings__confirm" role="alertdialog" aria-labelledby="mc-clear-title">
          <p id="mc-clear-title">清除后，你尚未结束的图谱生成任务会终止，需要重新上传。确定清除？</p>
          <button type="button" data-test="mc-clear-confirm" :disabled="busy !== null" @click="confirmClear">确定清除</button>
          <button type="button" data-test="mc-clear-cancel" @click="confirmingClear = false">取消</button>
        </div>
      </form>
    </template>
  </section>
</template>

<style scoped>
.model-settings { max-width: 40rem; }
.model-settings__lead,
.model-settings__hint { color: var(--color-text-muted); }
.model-settings__demo {
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-warning-border);
  border-radius: var(--radius-sm);
  background: var(--color-warning-bg);
  color: var(--color-warning-text);
}
.model-settings__status { font-weight: 600; }
.model-settings__form { display: grid; gap: 0.5rem; margin-top: 1rem; }
.model-settings__form input {
  padding: 0.5rem;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-sm);
  font: inherit;
}
.model-settings__actions { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem; }
.model-settings__confirm {
  padding: 0.75rem;
  border: 1px solid var(--color-danger-border);
  border-radius: var(--radius-sm);
  background: var(--color-danger-bg);
}
.is-ok { color: var(--color-success-text); }
.is-bad { color: var(--color-danger-text); }
</style>
