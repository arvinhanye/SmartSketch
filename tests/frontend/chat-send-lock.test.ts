import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, h, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CHAT_STREAM_CLIENT_KEY, type ChatSendOptions, type ChatStreamClient, type ChatStreamOutcome } from '../../src/frontend/src/api/chatStream'
import { AbortedError } from '../../src/frontend/src/api/http'
import { useChat } from '../../src/frontend/src/composables/useChat'
import { CHAT_ROUTE, COURSE_ROUTE, SETTINGS_ROUTE } from '../../src/frontend/src/router/index.ts'
import { useRuntimeStore } from '../../src/frontend/src/stores/runtime'
import ChatView from '../../src/frontend/src/views/ChatView.vue'

// 冲刺设计 §3.7：发送期间禁止普通再次提交（按钮、Enter、逻辑入口），不再隐式停止上一问并再次计费；
// 显式「停止」仍可用，停止后可以再发。

const DONE: ChatStreamOutcome = {
  kind: 'done',
  final: { status: 'answered', answer: '栈后进先出[1]', citations: [{ index: 1, chunk_id: 'c1', document_id: 'd1', page: 1, text: '原文' }], graph_version: 1, request_id: 'r' },
}

/** 每次 send 挂起，直到测试结束它；被中止时按真实客户端抛 AbortedError。 */
function pendingClient() {
  const sends: Array<{ question: string; signal?: AbortSignal; finish: (outcome: ChatStreamOutcome) => void }> = []
  const send = vi.fn<ChatStreamClient['send']>((_cid, request, options?: ChatSendOptions) => new Promise((resolve, reject) => {
    options?.signal?.addEventListener('abort', () => reject(new AbortedError()))
    sends.push({ question: request.question, signal: options?.signal, finish: resolve })
  }))
  return { client: { send } as ChatStreamClient, send, sends }
}

let pinia: Pinia
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  useRuntimeStore().apply({ runtime_mode: 'personal', configured: true })
})

describe('§3.7 发送期间防重复提交（逻辑层）', () => {
  function mountChat(client: ChatStreamClient) {
    let chat!: ReturnType<typeof useChat>
    const wrapper = mount(defineComponent({ setup() { chat = useChat(client, ref('course-1')); return () => h('div') } }),
      { global: { plugins: [pinia] } })
    return { chat: () => chat, wrapper }
  }

  it('在途时再次 ask 不发请求、不中止上一问', async () => {
    const { client, send, sends } = pendingClient()
    const { chat, wrapper } = mountChat(client)
    const first = chat().ask('第一问')
    await flushPromises()
    await chat().ask('第二问')
    expect(send).toHaveBeenCalledTimes(1)
    expect(sends[0]!.signal?.aborted).toBe(false)
    expect(chat().entries.value).toHaveLength(1)
    sends[0]!.finish(DONE)
    await first
    expect(chat().entries.value[0]!.status).toBe('answered')
    wrapper.unmount()
  })

  it('显式停止后可以再发', async () => {
    const { client, send, sends } = pendingClient()
    const { chat, wrapper } = mountChat(client)
    void chat().ask('第一问')
    await flushPromises()
    chat().stop()
    await flushPromises()
    expect(sends[0]!.signal?.aborted).toBe(true)
    expect(chat().entries.value[0]!.status).toBe('aborted')
    void chat().ask('第二问')
    await flushPromises()
    expect(send).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })
})

describe('§3.7 发送期间防重复提交（页面）', () => {
  async function mountPage(client: ChatStreamClient) {
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
    const wrapper = mount(ChatView, { global: { plugins: [pinia, router], provide: { [CHAT_STREAM_CLIENT_KEY as symbol]: client } } })
    await flushPromises()
    return wrapper
  }

  it('在途时可输入新文本，但按钮禁用、Enter 与重复点击都不发送', async () => {
    const { client, send, sends } = pendingClient()
    const wrapper = await mountPage(client)
    await wrapper.get('textarea').setValue('第一问')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(send).toHaveBeenCalledTimes(1)

    await wrapper.get('textarea').setValue('第二问')
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).disabled).toBe(false)
    expect(wrapper.get('[data-test="chat-send"]').attributes('disabled')).toBeDefined()
    await wrapper.get('textarea').trigger('keydown', { key: 'Enter', ctrlKey: true })
    await wrapper.get('form').trigger('submit')
    await wrapper.get('[data-test="chat-send"]').trigger('click')
    await flushPromises()
    expect(send).toHaveBeenCalledTimes(1)
    expect(sends[0]!.signal?.aborted).toBe(false)

    sends[0]!.finish(DONE)
    await flushPromises()
    expect(wrapper.get('[data-test="chat-send"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(send).toHaveBeenCalledTimes(2)
    expect(sends[1]!.question).toBe('第二问')
    wrapper.unmount()
  })

  it('点「停止」后可以再发', async () => {
    const { client, send } = pendingClient()
    const wrapper = await mountPage(client)
    await wrapper.get('textarea').setValue('第一问')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    await wrapper.get('[data-test="chat-stop"]').trigger('click')
    await flushPromises()
    await wrapper.get('textarea').setValue('第二问')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(send).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })
})
