import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { beforeEach, describe, expect, it } from 'vitest'
import type { ChatStreamClient } from '../../src/frontend/src/api/chatStream'
import { useChat } from '../../src/frontend/src/composables/useChat'
import { useCourseStore } from '../../src/frontend/src/stores/course'

describe('J09 问答页状态', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('按 J08 send 事件显示临时正文，仅提交 done 历史，并撤回错误回合', async () => {
    let count = 0
    const client: ChatStreamClient = {
      async send(_cid, _request, options) {
        count++
        options?.onEvent?.({ kind: 'meta', data: { event: 'meta', status: 'answered', retrieved: 1, graph_version: 2, request_id: 'r1' } })
        options?.onEvent?.({ kind: 'delta', data: { event: 'delta', delta: '临时正文[1]' } })
        if (count === 1) return {
          kind: 'done',
          final: { status: 'answered', answer: '正式正文[1]', citations: [{ index: 1, chunk_id: 'c1', document_id: 'd1', page: 1, text: '原文' }], graph_version: 2, request_id: 'r1' },
        }
        return { kind: 'error', error: { code: 'LLM_UNAVAILABLE', message: '错误', details: { reason: 'stream_interrupted', request_id: 'r2' } } }
      },
    }
    let chat!: ReturnType<typeof useChat>
    const wrapper = mount(defineComponent({
      setup() { chat = useChat(client, ref('course-1')); return () => h('div') },
    }))

    await chat.ask('第一问')
    expect(chat.entries.value[0].answer).toBe('正式正文[1]')
    expect(chat.entries.value[0].status).toBe('answered')
    expect(useCourseStore().chatHistory).toEqual([
      { role: 'user', content: '第一问' },
      { role: 'assistant', content: '正式正文[1]' },
    ])

    await chat.ask('第二问')
    expect(chat.entries.value[1].answer).toBe('连接中断，回答已撤回。')
    expect(chat.entries.value[1].status).toBe('error')
    expect(useCourseStore().chatHistory).toHaveLength(2)
    wrapper.unmount()
  })
})
