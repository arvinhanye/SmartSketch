import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CHAT_STREAM_CLIENT_KEY, type ChatStreamClient } from '../../src/frontend/src/api/chatStream'
import { CHAT_ROUTE, COURSE_ROUTE, SETTINGS_ROUTE } from '../../src/frontend/src/router/index.ts'
import { useRuntimeStore } from '../../src/frontend/src/stores/runtime'
import ChatView from '../../src/frontend/src/views/ChatView.vue'

// 正式模式失败路径 M11/C2：契约把问题限制在 2000 字（超出返回 422）。输入框与契约同值，
// 用户在输入时就被拦住，而不是发出请求后才收到一个看不懂的错误。

beforeEach(() => {
  setActivePinia(createPinia())
  useRuntimeStore().apply({ runtime_mode: 'personal', configured: true })
})

describe('问题输入长度上限', () => {
  it('输入框带 maxlength，且与契约的 maxLength 一致', async () => {
    const stub = { render: () => null }
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/courses/:cid', name: COURSE_ROUTE, component: stub },
        { path: '/courses/:cid/chat', name: CHAT_ROUTE, component: ChatView },
        { path: '/settings/model', name: SETTINGS_ROUTE, component: stub },
      ],
    })
    await router.push('/courses/c1/chat')
    await router.isReady()
    const client = { send: vi.fn() } as unknown as ChatStreamClient
    const wrapper = mount(ChatView, { global: { plugins: [router], provide: { [CHAT_STREAM_CLIENT_KEY as symbol]: client } } })
    await flushPromises()
    const contract = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../../src/contracts/api.v1.yaml'), 'utf8')
    const declared = Number(/ChatRequest:[\s\S]*?question:[\s\S]*?maxLength: (\d+)/.exec(contract)?.[1])
    expect(declared).toBe(2000)
    expect(wrapper.get('textarea').attributes('maxlength')).toBe(String(declared))
    wrapper.unmount()
  })
})
