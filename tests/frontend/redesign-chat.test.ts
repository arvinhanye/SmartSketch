import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CHAT_STREAM_CLIENT_KEY, type ChatStreamClient } from '../../src/frontend/src/api/chatStream'
import { PUBLISHED_GRAPH_API_KEY, type GraphExchange, type PublishedGraphApi } from '../../src/frontend/src/api/graph'
import { CHAT_ROUTE, COURSE_ROUTE } from '../../src/frontend/src/router/index.ts'
import ChatView from '../../src/frontend/src/views/ChatView.vue'

// 前端改版（方向 A）：问答页显示知识点名称而不是 kp_ 标识，出处只显示章节与页码
const KP_STACK = 'kp_cdb7ecdfc019be7f073224a43b00beb1'
const KP_MISSING = 'kp_not_in_graph'

function graph(version: number): GraphExchange {
  return {
    format_version: '1.0',
    course_id: 'c1',
    graph_version: version,
    generated_at: '2026-09-27T00:00:00Z',
    nodes: [{ id: KP_STACK, name: '栈' }],
    edges: [],
  } as unknown as GraphExchange
}

const chatClient: ChatStreamClient = {
  send: async () => ({
    kind: 'done',
    final: {
      status: 'answered',
      answer: '栈是只允许在一端插入和删除的线性表[1]。',
      citations: [{ index: 1, chunk_id: 'ch1', document_id: 'doc_a92d011b8b', section_path: '第3章 栈与队列 > 3.2 栈', page: 46, text: '栈（stack）是只允许在一端进行插入和删除操作的线性表。' }],
      related_kp_ids: [KP_STACK, KP_MISSING],
      graph_version: 3,
      request_id: 'r1',
    },
  }),
}

beforeEach(() => {
  setActivePinia(createPinia())
})

async function mountChat(graphApi: PublishedGraphApi) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/courses/:cid', name: COURSE_ROUTE, component: { render: () => null } },
      { path: '/courses/:cid/chat', name: CHAT_ROUTE, component: ChatView },
    ],
  })
  await router.push('/courses/c1/chat')
  await router.isReady()
  const wrapper = mount(ChatView, {
    global: {
      plugins: [router],
      provide: { [CHAT_STREAM_CLIENT_KEY as symbol]: chatClient, [PUBLISHED_GRAPH_API_KEY as symbol]: graphApi },
    },
  })
  await wrapper.get('textarea').setValue('什么是栈？')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  return wrapper
}

describe('问答页改版', () => {
  it('按回答的发布版本读取图谱，知识点显示名称；图谱里没有的退回标识', async () => {
    const getPublished = vi.fn<PublishedGraphApi['getPublished']>(async (_cid, version) => graph(version))
    const wrapper = await mountChat({ getPublished })
    expect(getPublished).toHaveBeenCalledWith('c1', 3, expect.anything())
    const chips = wrapper.findAll('[data-test="chat-kp"]').map((chip) => chip.text())
    expect(chips).toEqual(['栈', KP_MISSING])
  })

  it('图谱读取失败时仍显示回答，知识点退回标识', async () => {
    const wrapper = await mountChat({ getPublished: async () => Promise.reject(new Error('boom')) })
    expect(wrapper.text()).toContain('只允许在一端插入和删除')
    expect(wrapper.findAll('[data-test="chat-kp"]').map((chip) => chip.text())).toEqual([KP_STACK, KP_MISSING])
  })

  it('出处列出文件名、页码与章节，不显示文档标识；点开后显示原文', async () => {
    const wrapper = await mountChat({ getPublished: async (_cid, version) => graph(version) })
    const aside = wrapper.get('aside[aria-label="引用原文"]')
    // L12（ADR-085）：统一为「文件名 · 第 N 页 · 章节」；本用例的引用没有 document_name，写「资料不可用」
    expect(aside.text()).toContain('资料不可用 · 第 46 页 · 第3章 栈与队列 > 3.2 栈')
    expect(wrapper.text()).not.toContain('doc_a92d011b8b')
    expect(aside.find('blockquote').exists()).toBe(false)
    await aside.get('.source-list__item').trigger('click')
    expect(wrapper.get('aside blockquote').text()).toContain('只允许在一端进行插入和删除')
  })
})
