import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { ModelConfig } from '../api/modelConfig'

/** 发起读取或写入时的身份与代际；结果回来时据此判断是否仍属于当前会话（N03）。 */
export interface RuntimeTicket {
  readonly owner: string | null
  readonly generation: number
}

/**
 * 服务端运行模式与「本人是否已配置模型 API」（L10）。只存非敏感状态，不持久化，不含地址、模型名与密钥。
 * 上传页与问答页据 `needsConfig` 显示引导；外壳据 `isDemo` 显示演示标识。
 *
 * N03：状态属于一个会话（`owner`，取登录令牌）。换号、退出即 `startSession` 重置并推进代际；
 * 读取结果只在会话与代际都未变时生效（`commitRead`），保存/清除结果只要会话未变即生效并推进代际
 * （`commitWrite`），因此晚到的旧读取不会覆盖刚写入的状态，旧账号的任何结果都不会写到新账号上。
 */
export const useRuntimeStore = defineStore('runtime', () => {
  const runtimeMode = ref<ModelConfig['runtime_mode'] | null>(null)
  const configured = ref<boolean | null>(null)
  const owner = ref<string | null>(null)
  let generation = 0

  const needsConfig = computed(() => runtimeMode.value === 'personal' && configured.value === false)
  const isDemo = computed(() => runtimeMode.value === 'demo' || runtimeMode.value === 'fake')

  function set(config: ModelConfig | null): void {
    runtimeMode.value = config?.runtime_mode ?? null
    configured.value = config?.configured ?? null
  }

  /** 无条件写入（测试与不涉及竞态的调用方）；推进代际，使在途读取作废。 */
  function apply(config: ModelConfig): void {
    generation++
    set(config)
  }

  function startSession(key: string | null): void {
    owner.value = key
    generation++
    set(null)
  }

  function reset(): void {
    startSession(null)
  }

  function claim(): RuntimeTicket {
    return { owner: owner.value, generation }
  }

  function commitRead(ticket: RuntimeTicket, config: ModelConfig): boolean {
    if (ticket.owner !== owner.value || ticket.generation !== generation) return false
    set(config)
    return true
  }

  function commitWrite(ticket: RuntimeTicket, config: ModelConfig): boolean {
    if (ticket.owner !== owner.value) return false
    generation++
    set(config)
    return true
  }

  return { runtimeMode, configured, owner, needsConfig, isDemo, apply, reset, startSession, claim, commitRead, commitWrite }
})
