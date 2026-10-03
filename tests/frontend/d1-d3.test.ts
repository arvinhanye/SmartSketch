import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { beforeEach, describe, expect, it } from 'vitest'
import { parseChatEvent, type ChatStreamClient } from '../../src/frontend/src/api/chatStream'
import { ApiError } from '../../src/frontend/src/api/http'
import { useChat } from '../../src/frontend/src/composables/useChat'
import { useCourseStore } from '../../src/frontend/src/stores/course'

// ADR-082 决定 2/3：截断是生成故障（LLM_UNAVAILABLE / truncated），链路超时（任一环节）为 timeout；
// 两者都不是「资料未覆盖」，临时正文整段撤回。

function mountChat(client: ChatStreamClient) {
  let chat!: ReturnType<typeof useChat>
  const wrapper = mount(defineComponent({
    setup() { chat = useChat(client, ref('course-1')); return () => h('div') },
  }))
  return { chat, wrapper }
}

describe('D1/D3 问答故障分类（前端）', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('流解析接受 truncated 原因', () => {
    const parsed = parseChatEvent('error', JSON.stringify({
      event: 'error', error: { code: 'LLM_UNAVAILABLE', message: 'x', details: { reason: 'truncated', request_id: 'r1' } },
    }))
    expect(parsed.kind).toBe('event')
  })

  it('截断错误撤回临时正文、显示截断提示、不进历史', async () => {
    const client: ChatStreamClient = {
      async send(_cid, _request, options) {
        options?.onEvent?.({ kind: 'meta', data: { event: 'meta', status: 'answered', retrieved: 2, graph_version: 1, request_id: 'r1' } })
        options?.onEvent?.({ kind: 'delta', data: { event: 'delta', delta: '栈后进先出[1]。队列在一端' } })
        return { kind: 'error', error: { code: 'LLM_UNAVAILABLE', message: 'x', details: { reason: 'truncated', request_id: 'r1' } } }
      },
    }
    const { chat, wrapper } = mountChat(client)
    await chat.ask('栈和队列有什么区别？')
    const entry = chat.entries.value[0]
    expect(entry.status).toBe('error')
    expect(entry.answer).toContain('截断')
    expect(entry.answer).not.toContain('栈后进先出')
    expect(entry.answer).not.toContain('资料')
    expect(useCourseStore().chatHistory).toEqual([])
    wrapper.unmount()
  })

  it('开流前的 503 超时（准备阶段到期）按原因显示超时，而不是笼统不可用', async () => {
    const client: ChatStreamClient = {
      async send() {
        throw new ApiError(503, { code: 'LLM_UNAVAILABLE', message: 'x', details: { reason: 'timeout', request_id: 'r1' } })
      },
    }
    const { chat, wrapper } = mountChat(client)
    await chat.ask('什么是栈？')
    expect(chat.entries.value[0].status).toBe('error')
    expect(chat.entries.value[0].answer).toBe('回答超时，请稍后重试。')
    wrapper.unmount()
  })
})
