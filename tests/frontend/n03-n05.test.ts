import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import { defineComponent, h, nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import App from '../../src/frontend/src/App.vue'
import { ApiError, type RequestControl } from '../../src/frontend/src/api/http'
import { MODEL_CONFIG_API_KEY, type ModelConfigApi } from '../../src/frontend/src/api/modelConfig'
import { useModelConfig } from '../../src/frontend/src/composables/useModelConfig'
import { createAppRouter, SETTINGS_ROUTE } from '../../src/frontend/src/router/index.ts'
import { useRuntimeStore } from '../../src/frontend/src/stores/runtime'
import { useSessionStore } from '../../src/frontend/src/stores/session'
import ModelSettingsView from '../../src/frontend/src/views/ModelSettingsView.vue'

// N03：运行状态只属于当前账号会话；N04：保存/测试/清除互斥；N05：测试对象必须与显示一致。

type ModelConfig = components['schemas']['ModelConfig']
const SAVED: ModelConfig = {
  runtime_mode: 'personal', configured: true, base_url: 'https://api.example.com/v1', model: 'm1',
  key_hint: '1234', version: 1, updated_at: '2026-10-03T00:00:00Z',
}
const EMPTY: ModelConfig = { runtime_mode: 'personal', configured: false }
const KEY = 'sk-live-AAAABBBBCCCC1234'

interface Deferred<T> { promise: Promise<T>; resolve: (value: T) => void; reject: (cause: unknown) => void }
function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void
  let reject!: (cause: unknown) => void
  const promise = new Promise<T>((ok, fail) => { resolve = ok; reject = fail })
  return { promise, resolve, reject }
}

/** 每次调用都返回一个由测试控制的 Promise；被中止的请求也可能「晚到」，以模拟真实竞态。 */
function controllableApi() {
  const calls = { get: [] as Array<{ d: Deferred<ModelConfig>; control?: RequestControl }>,
    save: [] as Array<{ d: Deferred<ModelConfig>; body: unknown; control?: RequestControl }>,
    clear: [] as Array<{ d: Deferred<void>; control?: RequestControl }>,
    test: [] as Array<{ d: Deferred<components['schemas']['ModelConfigTestResult']>; body: unknown }> }
  const api: ModelConfigApi = {
    get: vi.fn((control?: RequestControl) => { const d = deferred<ModelConfig>(); calls.get.push({ d, control }); return d.promise }),
    save: vi.fn((body, control?: RequestControl) => { const d = deferred<ModelConfig>(); calls.save.push({ d, body, control }); return d.promise }),
    clear: vi.fn((control?: RequestControl) => { const d = deferred<void>(); calls.clear.push({ d, control }); return d.promise }),
    test: vi.fn((body) => { const d = deferred<components['schemas']['ModelConfigTestResult']>(); calls.test.push({ d, body }); return d.promise }),
  }
  return { api, calls }
}

function login(id: string, token: string, role: 'student' | 'teacher' = 'student') {
  useSessionStore().signIn({ access_token: token, token_type: 'bearer', expires_in: 3600, user: { id, username: id, role } })
}

let pinia: Pinia
beforeEach(() => {
  sessionStorage.clear()
  localStorage.clear()
  pinia = createPinia()
  setActivePinia(pinia)
})

// ---------------------------------------------------------------- N03

describe('N03 运行状态属于当前账号会话', () => {
  function mountShell(api: ModelConfigApi) {
    return mount(App, { global: { plugins: [pinia], provide: { [MODEL_CONFIG_API_KEY as symbol]: api } } })
  }

  it('A 的读取晚于 B 返回：被丢弃，旧请求已中止', async () => {
    const { api, calls } = controllableApi()
    login('alice', 'token-a')
    const wrapper = mountShell(api)
    await flushPromises()
    useSessionStore().signOut()
    await nextTick()
    login('bob', 'token-b')
    await flushPromises()
    expect(calls.get).toHaveLength(2)
    expect(calls.get[0]!.control?.signal?.aborted).toBe(true)
    calls.get[1]!.d.resolve(EMPTY)
    await flushPromises()
    calls.get[0]!.d.resolve(SAVED)            // A 的旧响应晚到
    await flushPromises()
    expect(useRuntimeStore().configured).toBe(false)
    expect(useRuntimeStore().needsConfig).toBe(true)
    wrapper.unmount()
  })

  it('同角色同步换号（角色不变）也重置并重新读取', async () => {
    const { api, calls } = controllableApi()
    login('alice', 'token-a')
    const wrapper = mountShell(api)
    await flushPromises()
    calls.get[0]!.d.resolve(SAVED)
    await flushPromises()
    expect(useRuntimeStore().configured).toBe(true)
    useSessionStore().signOut()
    login('bob', 'token-b')                   // 同一同步段内完成：role 始终是 student
    await flushPromises()
    expect(useRuntimeStore().configured).toBe(null)   // 立即重置，不沿用 A 的状态
    expect(calls.get).toHaveLength(2)
    calls.get[1]!.d.resolve(EMPTY)
    await flushPromises()
    expect(useRuntimeStore().needsConfig).toBe(true)
    wrapper.unmount()
  })

  it('退出后重新登录同一账号也重新读取', async () => {
    const { api, calls } = controllableApi()
    login('alice', 'token-a')
    const wrapper = mountShell(api)
    await flushPromises()
    calls.get[0]!.d.resolve(EMPTY)
    await flushPromises()
    useSessionStore().signOut()
    await flushPromises()
    expect(useRuntimeStore().configured).toBe(null)
    login('alice', 'token-a2')
    await flushPromises()
    expect(calls.get).toHaveLength(2)
    wrapper.unmount()
  })

  it.each([
    ['保存', SAVED, EMPTY, true],
    ['清除', EMPTY, SAVED, false],
  ] as const)('初始读取晚于设置页%s返回：不覆盖刚写入的状态', async (_label, written, stale, expected) => {
    const { api, calls } = controllableApi()
    login('alice', 'token-a')
    const wrapper = mountShell(api)
    await flushPromises()
    const runtime = useRuntimeStore()
    expect(runtime.commitWrite(runtime.claim(), written)).toBe(true)   // 设置页的保存/清除结果
    calls.get[0]!.d.resolve(stale)
    await flushPromises()
    expect(runtime.configured).toBe(expected)
    wrapper.unmount()
  })

  it('换号后，旧账号设置页的写入结果也被拒绝', () => {
    login('alice', 'token-a')
    const runtime = useRuntimeStore()
    runtime.startSession('token-a')
    const ticket = runtime.claim()
    runtime.startSession('token-b')
    expect(runtime.commitWrite(ticket, SAVED)).toBe(false)
    expect(runtime.configured).toBe(null)
  })
})

// ---------------------------------------------------------------- N04 / N05：组合式逻辑

function mountComposable(api: ModelConfigApi) {
  let state!: ReturnType<typeof useModelConfig>
  const wrapper = mount(defineComponent({ setup() { state = useModelConfig({ api }); return () => h('div') } }),
    { global: { plugins: [pinia] } })
  return { state: () => state, wrapper }
}

async function ready(api: ModelConfigApi, calls: ReturnType<typeof controllableApi>['calls'], initial: ModelConfig) {
  const mounted = mountComposable(api)
  calls.get[0]!.d.resolve(initial)
  await flushPromises()
  return mounted
}

describe('N04 保存、测试、清除互斥', () => {
  beforeEach(() => login('alice', 'token-a'))

  it('保存未返回时清除不发请求；保存晚到后状态与服务端顺序一致', async () => {
    const { api, calls } = controllableApi()
    const { state, wrapper } = await ready(api, calls, SAVED)
    state().form.model = 'm2'
    const saving = state().save()
    await nextTick()
    expect(state().busy.value).toBe('saving')
    await state().clear()
    await state().test()
    expect(api.clear).not.toHaveBeenCalled()
    expect(api.test).not.toHaveBeenCalled()
    calls.save[0]!.d.resolve({ ...SAVED, model: 'm2', version: 2 })
    await saving
    expect(state().configured.value).toBe(true)
    const clearing = state().clear()
    calls.clear[0]!.d.resolve()
    await clearing
    expect(state().configured.value).toBe(false)
    expect(useRuntimeStore().needsConfig).toBe(true)
    wrapper.unmount()
  })

  it('加载未完成时不能保存', async () => {
    const { api, calls } = controllableApi()
    const { state, wrapper } = mountComposable(api)
    state().form.baseUrl = SAVED.base_url!
    state().form.model = 'm1'
    state().form.apiKey = KEY
    await state().save()
    expect(api.save).not.toHaveBeenCalled()
    calls.get[0]!.d.resolve(EMPTY)
    await flushPromises()
    wrapper.unmount()
  })

  it('失败后释放互斥', async () => {
    const { api, calls } = controllableApi()
    const { state, wrapper } = await ready(api, calls, SAVED)
    state().form.model = 'm2'
    const first = state().save()
    calls.save[0]!.d.reject(new ApiError(503, { code: 'STORAGE_UNAVAILABLE', message: 'x' }))
    await first
    expect(state().busy.value).toBe(null)
    const clearing = state().clear()
    expect(api.clear).toHaveBeenCalledTimes(1)
    calls.clear[0]!.d.resolve()
    await clearing
    wrapper.unmount()
  })

  it('卸载中止在途请求，晚到的结果不改运行状态', async () => {
    const { api, calls } = controllableApi()
    const { state, wrapper } = await ready(api, calls, EMPTY)
    Object.assign(state().form, { baseUrl: SAVED.base_url, model: 'm1', apiKey: KEY })
    const saving = state().save()
    wrapper.unmount()
    expect(calls.save[0]!.control?.signal?.aborted).toBe(true)
    calls.save[0]!.d.resolve(SAVED)
    await saving
    expect(useRuntimeStore().configured).toBe(false)
  })
})

describe('N05 测试的对象与表单一致', () => {
  beforeEach(() => login('alice', 'token-a'))

  it('地址、模型都未改且密钥留空：测试已保存的配置，并注明', async () => {
    const { api, calls } = controllableApi()
    const { state, wrapper } = await ready(api, calls, SAVED)
    const testing = state().test()
    expect(calls.test[0]!.body).toBeUndefined()
    calls.test[0]!.d.resolve({ ok: true, latency_ms: 50 })
    await testing
    expect(state().testResult.value?.text).toContain('已保存的配置')
    wrapper.unmount()
  })

  it.each([
    ['只改模型', { model: 'nonexistent-model' }],
    ['只改地址', { baseUrl: 'https://other.example.com/v1' }],
  ])('%s且密钥留空：不发请求，要求先保存或填写完整密钥', async (_label, change) => {
    const { api, calls } = controllableApi()
    const { state, wrapper } = await ready(api, calls, SAVED)
    Object.assign(state().form, change)
    await state().test()
    expect(api.test).not.toHaveBeenCalled()
    expect(state().error.value).toMatch(/先保存|填写密钥/)
    expect(state().testResult.value).toBe(null)
    wrapper.unmount()
  })

  it('填写了密钥：测试表单里的这组值，并注明尚未保存', async () => {
    const { api, calls } = controllableApi()
    const { state, wrapper } = await ready(api, calls, SAVED)
    Object.assign(state().form, { model: 'm2', apiKey: KEY })
    const testing = state().test()
    expect(calls.test[0]!.body).toEqual({ base_url: SAVED.base_url, model: 'm2', api_key: KEY })
    calls.test[0]!.d.resolve({ ok: true, latency_ms: 50 })
    await testing
    expect(state().testResult.value?.text).toContain('尚未保存')
    wrapper.unmount()
  })

  it('测试期间改了表单：结果作废，不暗示新值已通过', async () => {
    const { api, calls } = controllableApi()
    const { state, wrapper } = await ready(api, calls, SAVED)
    Object.assign(state().form, { apiKey: KEY })
    const testing = state().test()
    state().form.model = 'edited-while-testing'
    calls.test[0]!.d.resolve({ ok: true, latency_ms: 50 })
    await testing
    expect(state().testResult.value?.ok).not.toBe(true)
    expect(state().testResult.value?.text ?? '').toContain('已修改')
    wrapper.unmount()
  })

  it('仅改模型时保存仍可不填密钥（已批准的保存规则）', async () => {
    const { api, calls } = controllableApi()
    const { state, wrapper } = await ready(api, calls, SAVED)
    state().form.model = 'm2'
    const saving = state().save()
    expect(calls.save[0]!.body).toEqual({ base_url: SAVED.base_url, model: 'm2' })
    calls.save[0]!.d.resolve({ ...SAVED, model: 'm2' })
    await saving
    wrapper.unmount()
  })
})

// ---------------------------------------------------------------- N04：按钮层

describe('N04 按钮层互斥', () => {
  it('任一操作进行中，保存/测试/清除按钮都禁用', async () => {
    login('alice', 'token-a')
    const { api, calls } = controllableApi()
    const router = createAppRouter({ history: createMemoryHistory(), getAccountRole: () => 'student', settingsComponent: ModelSettingsView })
    await router.push({ name: SETTINGS_ROUTE })
    const wrapper = mount(ModelSettingsView, { global: { plugins: [pinia, router], provide: { [MODEL_CONFIG_API_KEY as symbol]: api } } })
    calls.get[0]!.d.resolve(SAVED)
    await flushPromises()
    await wrapper.get('[data-test="mc-model"]').setValue('m2')
    await wrapper.get('[data-test="mc-form"]').trigger('submit')
    await nextTick()
    for (const name of ['mc-save', 'mc-test', 'mc-clear']) {
      expect(wrapper.get(`[data-test="${name}"]`).attributes('disabled'), name).toBeDefined()
    }
    calls.save[0]!.d.resolve({ ...SAVED, model: 'm2' })
    await flushPromises()
    for (const name of ['mc-save', 'mc-test', 'mc-clear']) {
      expect(wrapper.get(`[data-test="${name}"]`).attributes('disabled'), name).toBeUndefined()
    }
    wrapper.unmount()
  })
})
