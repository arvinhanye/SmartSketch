import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CHAT_STREAM_CLIENT_KEY, type ChatStreamClient, type ChatStreamOutcome } from '../../src/frontend/src/api/chatStream'
import { CHAT_ROUTE, COURSE_ROUTE } from '../../src/frontend/src/router/index.ts'
import ChatView from '../../src/frontend/src/views/ChatView.vue'

// UI-QA-01（规格 grounded-qa「问答页前端呈现」F1–F5）：出处属于当前回答、状态标签、复制、固定输入区。
const cite = (index: number, name: string) => ({ index, chunk_id: `k${index}`, document_id: `d${index}`, page: index + 1, section_path: `第${index}章`, text: `原文${index}`, document_name: name })
const ANSWERED: ChatStreamOutcome = {
  kind: 'done',
  final: { status: 'answered', answer: '栈后进先出[1]，队列先进先出[2]。', citations: [cite(1, 'a.md'), cite(2, 'b.md')], related_kp_ids: [], graph_version: 1, request_id: 'r1' },
} as never
const NOT_COVERED: ChatStreamOutcome = {
  kind: 'done',
  final: { status: 'not_covered', answer: '课程资料中与这个问题相关的内容不够充分。', citations: [], related_kp_ids: [], graph_version: 1, request_id: 'r2', reason: 'below_similarity_threshold' },
} as never
const FAILED: ChatStreamOutcome = { kind: 'error', error: { code: 'INTERNAL_ERROR', message: 'x', details: {} } } as never

let writeText: ReturnType<typeof vi.fn>
beforeEach(() => {
  setActivePinia(createPinia())
  writeText = vi.fn(async () => undefined)
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
})
afterEach(() => vi.useRealTimers())

async function mountChat(outcomes: ChatStreamOutcome[]): Promise<{ wrapper: VueWrapper; ask: (q: string) => Promise<void>; send: ReturnType<typeof vi.fn> }> {
  const send = vi.fn(async () => outcomes.shift() ?? ANSWERED)
  const client = { send } as unknown as ChatStreamClient
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/courses/:cid', name: COURSE_ROUTE, component: { render: () => null } },
      { path: '/courses/:cid/chat', name: CHAT_ROUTE, component: ChatView },
    ],
  })
  await router.push('/courses/c1/chat')
  await router.isReady()
  const wrapper = mount(ChatView, { global: { plugins: [router], provide: { [CHAT_STREAM_CLIENT_KEY as symbol]: client } } })
  const ask = async (q: string) => {
    await wrapper.get('textarea').setValue(q)
    await wrapper.get('form').trigger('submit')
    await flushPromises()
  }
  return { wrapper, ask, send }
}
const panel = (w: VueWrapper) => w.get('aside[aria-label="引用原文"]')

describe('出处属于当前回答（F2）', () => {
  it('最后一条是资料未覆盖时，面板不显示上一条回答的出处，并写明原因', async () => {
    const { wrapper, ask } = await mountChat([ANSWERED, NOT_COVERED])
    await ask('什么是栈？')
    expect(panel(wrapper).findAll('.source-list__item')).toHaveLength(2)
    await ask('量子计算是什么？')
    expect(panel(wrapper).findAll('.source-list__item')).toHaveLength(0)
    expect(panel(wrapper).text()).toContain('这条回答没有出处')
  })
  it('点旧回答的「查看 2 处出处」后面板切到那一条；提新问题后回到最后一条', async () => {
    const { wrapper, ask } = await mountChat([ANSWERED, NOT_COVERED, NOT_COVERED])
    await ask('什么是栈？')
    await ask('量子计算是什么？')
    await wrapper.get('[data-test="answer-sources-toggle"]').trigger('click')
    expect(panel(wrapper).findAll('.source-list__item')).toHaveLength(2)
    expect(wrapper.get('[data-test="answer-sources-toggle"]').attributes('aria-pressed')).toBe('true')
    await ask('再问一个')
    expect(panel(wrapper).findAll('.source-list__item')).toHaveLength(0)
  })
  it('点旧回答正文里的编号：面板切到那一条并展开该条出处原文', async () => {
    const { wrapper, ask } = await mountChat([ANSWERED, NOT_COVERED])
    await ask('什么是栈？')
    await ask('量子计算是什么？')
    await wrapper.findAll('.citation')[1]!.trigger('click')
    expect(panel(wrapper).findAll('.source-list__item')).toHaveLength(2)
    expect(panel(wrapper).get('article.source').text()).toContain('出处 [2]')
    expect(panel(wrapper).get('[data-test="sv-document"]').text()).toBe('b.md')
  })
})

describe('状态与失败卡（F1/F3）', () => {
  it('三种结果各有状态标签文字与 data-status', async () => {
    const { wrapper, ask } = await mountChat([ANSWERED, NOT_COVERED, FAILED])
    await ask('一'); await ask('二'); await ask('三')
    const tags = wrapper.findAll('[data-test="answer-status"]')
    expect(tags.map((t) => t.attributes('data-status'))).toEqual(['answered', 'not_covered', 'error'])
    expect(tags.map((t) => t.text())).toEqual(['已回答', '资料未覆盖', '未完成'])
  })
  it('失败卡：原因只出现一次、有重试；点重试以原问题再发一次', async () => {
    const { wrapper, ask, send } = await mountChat([FAILED, ANSWERED])
    await ask('会失败的问题')
    expect(wrapper.text().split('问答暂时失败').length - 1).toBe(1)
    await wrapper.get('[data-test="answer-retry"]').trigger('click')
    await flushPromises()
    expect(send).toHaveBeenCalledTimes(2)
    expect((send.mock.calls[1] as unknown[])[1]).toMatchObject({ question: '会失败的问题' })
  })
  it('资料未覆盖有下一步、不是错误卡', async () => {
    const { wrapper, ask } = await mountChat([NOT_COVERED])
    await ask('量子计算是什么？')
    expect(wrapper.get('[data-test="chat-nc-next"]').text()).toContain('换个问法')
    expect(wrapper.find('[data-test="answer-error-reason"]').exists()).toBe(false)
  })
})

describe('复制回答（F4）', () => {
  it('复制正文与出处，显示已复制；资料未覆盖没有复制按钮', async () => {
    const { wrapper, ask } = await mountChat([ANSWERED, NOT_COVERED])
    await ask('什么是栈？')
    await wrapper.get('[data-test="chat-copy"]').trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('栈后进先出[1]，队列先进先出[2]。\n\n出处：\n[1] a.md · 第 2 页 · 第1章\n[2] b.md · 第 3 页 · 第2章')
    expect(wrapper.get('[data-test="chat-copy-status"]').text()).toBe('已复制回答和出处。')
    await ask('量子计算是什么？')
    expect(wrapper.findAll('[data-test="chat-copy"]')).toHaveLength(1)
  })
  it('写入被拒时显示失败提示，不显示成功', async () => {
    writeText.mockRejectedValueOnce(new Error('denied'))
    const { wrapper, ask } = await mountChat([ANSWERED])
    await ask('什么是栈？')
    await wrapper.get('[data-test="chat-copy"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="chat-copy-status"]').text()).toContain('复制失败')
    expect(wrapper.text()).not.toContain('已复制回答和出处')
  })
})

describe('页面结构（F5/页头）', () => {
  it('页头：标题、徽标与返回课程；输入区在最后一条回答之后，初始没有「回到最新」', async () => {
    const { wrapper, ask } = await mountChat([ANSWERED])
    expect(wrapper.get('h2#chat-title').text()).toBe('课程问答')
    expect(wrapper.text()).toContain('仅依据已发布资料回答')
    expect(wrapper.get('a[href="/courses/c1"]').text()).toContain('返回课程')
    await ask('什么是栈？')
    const html = wrapper.html()
    expect(html.indexOf('data-test="chat-compose"')).toBeGreaterThan(html.indexOf('data-test="answer-status"'))
    expect(wrapper.find('[data-test="chat-jump-latest"]').exists()).toBe(false)
  })
})
