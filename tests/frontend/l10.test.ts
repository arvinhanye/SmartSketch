import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import { ApiError } from '../../src/frontend/src/api/http'
import { MODEL_CONFIG_API_KEY, type ModelConfigApi } from '../../src/frontend/src/api/modelConfig'
import { createAppRouter, SETTINGS_ROUTE } from '../../src/frontend/src/router/index.ts'
import { useRuntimeStore } from '../../src/frontend/src/stores/runtime'
import { useSessionStore } from '../../src/frontend/src/stores/session'
import ModelSettingsView from '../../src/frontend/src/views/ModelSettingsView.vue'
import { CHAT_STREAM_CLIENT_KEY, type ChatStreamClient } from '../../src/frontend/src/api/chatStream'
import { COURSES_API_KEY, type CoursesApi } from '../../src/frontend/src/api/courses'
import { MATERIALS_API_KEY, TASK_EVENTS_CLIENT_KEY, type MaterialsApi } from '../../src/frontend/src/api/materials'
import type { TaskEventsClient } from '../../src/frontend/src/api/taskEvents'
import { CHAT_ROUTE, COURSE_ROUTE, MATERIALS_ROUTE } from '../../src/frontend/src/router/index.ts'
import ChatView from '../../src/frontend/src/views/ChatView.vue'
import MaterialsView from '../../src/frontend/src/views/MaterialsView.vue'

type ModelConfig = components['schemas']['ModelConfig']
const KEY = 'sk-live-AAAABBBBCCCC1234'
const SAVED: ModelConfig = {
  runtime_mode: 'personal', configured: true, base_url: 'https://api.example.com/v1', model: 'm1',
  key_hint: '1234', version: 1, updated_at: '2026-10-03T00:00:00Z',
}
const EMPTY: ModelConfig = { runtime_mode: 'personal', configured: false }

function fakeApi(initial: ModelConfig, overrides: Partial<ModelConfigApi> = {}) {
  return {
    get: vi.fn<ModelConfigApi['get']>(overrides.get ?? (async () => initial)),
    save: vi.fn<ModelConfigApi['save']>(overrides.save ?? (async (body) => ({ ...SAVED, base_url: body.base_url, model: body.model }))),
    clear: vi.fn<ModelConfigApi['clear']>(overrides.clear ?? (async () => undefined)),
    test: vi.fn<ModelConfigApi['test']>(overrides.test ?? (async () => ({ ok: true, latency_ms: 321 }))),
  }
}

let pinia: Pinia
beforeEach(() => {
  sessionStorage.clear()
  localStorage.clear()
  pinia = createPinia()
  setActivePinia(pinia)
  useSessionStore().signIn({ access_token: 't', token_type: 'bearer', expires_in: 3600,
    user: { id: 'u1', username: 'alice', role: 'student' } })
})

async function mountView(api: ReturnType<typeof fakeApi>) {
  const router = createAppRouter({ history: createMemoryHistory(), getAccountRole: () => 'student', settingsComponent: ModelSettingsView })
  await router.push({ name: SETTINGS_ROUTE })
  const wrapper = mount(ModelSettingsView, { global: { plugins: [pinia, router], provide: { [MODEL_CONFIG_API_KEY as symbol]: api } } })
  await flushPromises()
  return wrapper
}

describe('L10 模型 API 设置页', () => {
  it('未配置时提示并要求三项', async () => {
    const api = fakeApi(EMPTY)
    const wrapper = await mountView(api)
    expect(wrapper.find('[data-test="mc-status"]').text()).toContain('尚未配置')
    await wrapper.find('[data-test="mc-form"]').trigger('submit')
    expect(api.save).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="mc-error"]').text()).toContain('请填写')
    expect(useRuntimeStore().needsConfig).toBe(true)
  })

  it('保存后只显示脱敏状态，输入框清空，浏览器存储里没有密钥', async () => {
    const api = fakeApi(EMPTY)
    const wrapper = await mountView(api)
    await wrapper.find('[data-test="mc-base-url"]').setValue('https://api.example.com/v1')
    await wrapper.find('[data-test="mc-model"]').setValue('m1')
    await wrapper.find('[data-test="mc-api-key"]').setValue(KEY)
    await wrapper.find('[data-test="mc-form"]').trigger('submit')
    await flushPromises()
    expect(api.save).toHaveBeenCalledWith({ base_url: 'https://api.example.com/v1', model: 'm1', api_key: KEY }, expect.anything())
    expect(wrapper.find('[data-test="mc-status"]').text()).toContain('••••1234')
    expect((wrapper.find('[data-test="mc-api-key"]').element as HTMLInputElement).value).toBe('')
    expect(wrapper.html()).not.toContain(KEY)
    expect(JSON.stringify({ ...sessionStorage, ...localStorage })).not.toContain(KEY)
    expect(useRuntimeStore().needsConfig).toBe(false)
  })

  it('只改模型名可不填密钥；改地址必须重填', async () => {
    const api = fakeApi(SAVED)
    const wrapper = await mountView(api)
    await wrapper.find('[data-test="mc-model"]').setValue('m2')
    await wrapper.find('[data-test="mc-form"]').trigger('submit')
    await flushPromises()
    expect(api.save).toHaveBeenLastCalledWith({ base_url: 'https://api.example.com/v1', model: 'm2' }, expect.anything())
    await wrapper.find('[data-test="mc-base-url"]').setValue('https://other.example.com/v1')
    await wrapper.find('[data-test="mc-form"]').trigger('submit')
    await flushPromises()
    expect(api.save).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[data-test="mc-error"]').text()).toContain('重新填写密钥')
  })

  it('地址被拒时给出对应文案，不回显服务端 message', async () => {
    const api = fakeApi(EMPTY, {
      save: async () => { throw new ApiError(422, { code: 'VALIDATION_ERROR', message: '服务端原文', details: { fields: [{ in: 'body', field: 'base_url', reason: 'private_address' }] } }) },
    })
    const wrapper = await mountView(api)
    await wrapper.find('[data-test="mc-base-url"]').setValue('https://intranet.example.com/v1')
    await wrapper.find('[data-test="mc-model"]').setValue('m1')
    await wrapper.find('[data-test="mc-api-key"]').setValue(KEY)
    await wrapper.find('[data-test="mc-form"]').trigger('submit')
    await flushPromises()
    const text = wrapper.find('[data-test="mc-error"]').text()
    expect(text).toContain('内网')
    expect(text).not.toContain('服务端原文')
  })

  it('测试连接显示成败与分类', async () => {
    const api = fakeApi(SAVED, { test: async () => ({ ok: false, latency_ms: 80, error_class: 'auth' }) })
    const wrapper = await mountView(api)
    await wrapper.find('[data-test="mc-test"]').trigger('click')
    await flushPromises()
    expect(api.test).toHaveBeenCalledWith(undefined, expect.anything())
    expect(wrapper.find('[data-test="mc-test-result"]').text()).toContain('密钥被拒绝')
  })

  it('清除后回到未配置', async () => {
    const api = fakeApi(SAVED)
    const wrapper = await mountView(api)
    await wrapper.find('[data-test="mc-clear"]').trigger('click')
    await wrapper.find('[data-test="mc-clear-confirm"]').trigger('click')
    await flushPromises()
    expect(api.clear).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[data-test="mc-status"]').text()).toContain('尚未配置')
    expect(useRuntimeStore().needsConfig).toBe(true)
  })

  it('演示模式下说明个人配置不生效', async () => {
    const wrapper = await mountView(fakeApi({ runtime_mode: 'demo', configured: false }))
    expect(wrapper.find('[data-test="mc-demo"]').text()).toContain('演示模式')
    expect(useRuntimeStore().isDemo).toBe(true)
    expect(useRuntimeStore().needsConfig).toBe(false)
  })

  it('连接结果弹窗复用个人测试结果，编辑表单后结果过期并不再展示', async () => {
    const api = fakeApi(SAVED)
    const wrapper = await mountView(api)
    const dialog = wrapper.get('[data-test="mc-test-dialog"]').element as HTMLDialogElement
    // jsdom 不实现原生 dialog 的开关行为，这里只给该元素装替身；真实焦点与 Esc 行为在浏览器复核
    dialog.showModal = () => { dialog.open = true }
    dialog.close = () => { dialog.open = false }

    await wrapper.get('[data-test="mc-test"]').trigger('click')
    await flushPromises()
    expect(api.test).toHaveBeenCalledTimes(1)
    expect(dialog.open).toBe(true)
    expect(wrapper.get('[data-test="mc-dialog-result"]').text()).toContain('321')
    // 弹窗不展示密钥、原始请求或服务端原文
    expect(wrapper.html()).not.toContain(KEY)

    await wrapper.get('[data-test="mc-model"]').setValue('m2')
    expect(dialog.open).toBe(false)
    expect(wrapper.find('[data-test="mc-test-result"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="mc-test-stale"]').text()).toContain('请重新测试当前配置')
  })

  it('已填密钥时切换服务商预设：地址被替换且未提交密钥被清空，保存要求重填', async () => {
    const api = fakeApi(EMPTY)
    const wrapper = await mountView(api)
    await wrapper.get('[data-test="mc-base-url"]').setValue('https://custom.example.com/v1')
    await wrapper.get('[data-test="mc-model"]').setValue('m1')
    await wrapper.get('[data-test="mc-api-key"]').setValue(KEY)
    // 换成服务商预设：地址被替换，未提交的密钥随之作废
    await wrapper.get('[data-test="mc-provider"]').setValue('deepseek')
    expect((wrapper.get('[data-test="mc-base-url"]').element as HTMLInputElement).value).toBe('https://api.deepseek.com/v1')
    expect((wrapper.get('[data-test="mc-api-key"]').element as HTMLInputElement).value).toBe('')
    await wrapper.get('[data-test="mc-form"]').trigger('submit')
    await flushPromises()
    expect(api.save).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="mc-error"]').text()).toContain('请填写密钥')
  })

  it('未填密钥测试已保存配置：不打开弹窗的编造结果，仍给出明确提示', async () => {
    // 地址与模型都改过、密钥留空：不能拿旧配置的结果冒充新值
    const api = fakeApi(SAVED)
    const wrapper = await mountView(api)
    await wrapper.get('[data-test="mc-base-url"]').setValue('https://other.example.com/v1')
    await wrapper.get('[data-test="mc-test"]').trigger('click')
    await flushPromises()
    expect(api.test).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="mc-error"]').text()).toContain('请先保存')
  })
})

// ---------------------------------------------------------------- 上传页与问答页的未配置引导

type Course = components['schemas']['Course']
const STUB = { render: () => null }

function teacherCourse(): Course {
  return {
    id: 'c1', name: '数据结构', description: null, status: 'draft', my_role: 'teacher', teacher_id: 'u1',
    kp_count: 0, published_version: null, created_at: '2026-10-03T00:00:00Z',
  }
}

async function mountMaterials() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/courses/:cid', name: COURSE_ROUTE, component: STUB },
      { path: '/courses/:cid/materials', name: MATERIALS_ROUTE, component: MaterialsView },
      { path: '/settings/model', name: SETTINGS_ROUTE, component: STUB },
    ],
  })
  await router.push('/courses/c1/materials')
  await router.isReady()
  const materials = {
    list: vi.fn<MaterialsApi['list']>(async () => []),
    upload: vi.fn<MaterialsApi['upload']>(async () => ({ task_id: 't1', document_id: 'd1' })),
    cancelTask: vi.fn<MaterialsApi['cancelTask']>(),
    deleteDocument: vi.fn<MaterialsApi['deleteDocument']>(),
    uploadPolicy: vi.fn<MaterialsApi['uploadPolicy']>(async () => ({ max_bytes: 52_428_800 })),
  }
  const courses: CoursesApi = { list: async () => [teacherCourse()], create: async () => teacherCourse(), get: async () => teacherCourse() }
  const events = { subscribe: vi.fn() } as unknown as TaskEventsClient
  const wrapper = mount(MaterialsView, {
    global: {
      plugins: [pinia, router],
      provide: { [MATERIALS_API_KEY as symbol]: materials, [COURSES_API_KEY as symbol]: courses, [TASK_EVENTS_CLIENT_KEY as symbol]: events },
    },
  })
  await flushPromises()
  return wrapper
}

async function mountChatPage(send: ChatStreamClient['send']) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/courses/:cid', name: COURSE_ROUTE, component: STUB },
      { path: '/courses/:cid/chat', name: CHAT_ROUTE, component: ChatView },
      { path: '/settings/model', name: SETTINGS_ROUTE, component: STUB },
    ],
  })
  await router.push('/courses/c1/chat')
  await router.isReady()
  const wrapper = mount(ChatView, {
    global: { plugins: [pinia, router], provide: { [CHAT_STREAM_CLIENT_KEY as symbol]: { send } } },
  })
  await flushPromises()
  return wrapper
}

describe('L10 未配置个人模型 API 的引导', () => {
  it('上传页：未配置时显示引导并禁用上传，配置后恢复', async () => {
    useRuntimeStore().apply({ runtime_mode: 'personal', configured: false })
    const wrapper = await mountMaterials()
    expect(wrapper.find('[data-test="model-config-required"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="upload-submit"]').attributes('disabled')).toBeDefined()
    useRuntimeStore().apply({ runtime_mode: 'personal', configured: true })
    await flushPromises()
    expect(wrapper.find('[data-test="model-config-required"]').exists()).toBe(false)
  })

  it('问答页：未配置时显示引导、禁用发送，键盘提交也不发请求', async () => {
    useRuntimeStore().apply({ runtime_mode: 'personal', configured: false })
    const send = vi.fn<ChatStreamClient['send']>()
    const wrapper = await mountChatPage(send)
    expect(wrapper.find('[data-test="model-config-required"]').exists()).toBe(true)
    await wrapper.get('textarea').setValue('什么是栈？')
    expect(wrapper.get('[data-test="chat-send"]').attributes('disabled')).toBeDefined()
    await wrapper.get('form').trigger('submit')
    await wrapper.get('textarea').trigger('keydown', { key: 'Enter', ctrlKey: true })
    await flushPromises()
    expect(send).not.toHaveBeenCalled()
  })

  it('演示模式不显示引导', async () => {
    useRuntimeStore().apply({ runtime_mode: 'demo', configured: false })
    const wrapper = await mountChatPage(vi.fn<ChatStreamClient['send']>())
    expect(wrapper.find('[data-test="model-config-required"]').exists()).toBe(false)
  })
})
