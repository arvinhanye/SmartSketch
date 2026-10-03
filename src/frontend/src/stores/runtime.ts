import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { ModelConfig } from '../api/modelConfig'

/**
 * 服务端运行模式与「本人是否已配置模型 API」（L10）。只存非敏感状态，不持久化，不含地址、模型名与密钥。
 * 上传页与问答页据 `needsConfig` 显示引导；外壳据 `isDemo` 显示演示标识。
 */
export const useRuntimeStore = defineStore('runtime', () => {
  const runtimeMode = ref<ModelConfig['runtime_mode'] | null>(null)
  const configured = ref<boolean | null>(null)

  const needsConfig = computed(() => runtimeMode.value === 'personal' && configured.value === false)
  const isDemo = computed(() => runtimeMode.value === 'demo' || runtimeMode.value === 'fake')

  function apply(config: ModelConfig): void {
    runtimeMode.value = config.runtime_mode
    configured.value = config.configured
  }

  function reset(): void {
    runtimeMode.value = null
    configured.value = null
  }

  return { runtimeMode, configured, needsConfig, isDemo, apply, reset }
})
