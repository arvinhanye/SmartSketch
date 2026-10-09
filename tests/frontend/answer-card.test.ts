import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'
import AnswerCard from '../../src/frontend/src/components/chat/AnswerCard.vue'
import type { ChatEntry } from '../../src/frontend/src/composables/useChat'
import { STUDENT_GRAPH_ROUTE } from '../../src/frontend/src/router/index.ts'

// UI-QA-01 F1/F3/F4：单条回答的状态标签、下一步、复制与重试。
const cite = { index: 1, chunk_id: 'k', document_id: 'd', page: 2, text: '原文', document_name: 'a.md' }
const base: ChatEntry = { id: 1, question: '问', answer: '正文[1]', status: 'answered', citations: [cite], relatedKpIds: [] }
const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/g/:cid', name: STUDENT_GRAPH_ROUTE, component: { render: () => null } }] })
function card(entry: Partial<ChatEntry>, props: Record<string, unknown> = {}) {
  return mount(AnswerCard, {
    props: { entry: { ...base, ...entry }, active: false, currentVersion: 1, courseId: 'c1', graphLinkAvailable: true, kpLabel: (id: string) => id, copyState: null, sending: false, ...props },
    global: { plugins: [router] },
  })
}

describe('AnswerCard', () => {
  it.each([
    ['streaming', '生成中'], ['answered', '已回答'], ['not_covered', '资料未覆盖'], ['error', '未完成'], ['aborted', '已停止'],
  ] as const)('%s 状态标签：文字与 data-status，非生成中带图标', (status, text) => {
    const w = card({ status })
    const tag = w.get('[data-test="answer-status"]')
    expect(tag.text()).toContain(text)
    expect(tag.attributes('data-status')).toBe(status)
    if (status !== 'streaming') expect(tag.find('svg').exists()).toBe(true)
  })
  it('已回答：有「查看 1 处出处」和复制按钮，点击分别发出事件', async () => {
    const w = card({})
    await w.get('[data-test="answer-sources-toggle"]').trigger('click')
    await w.get('[data-test="chat-copy"]').trigger('click')
    expect(w.get('[data-test="answer-sources-toggle"]').text()).toContain('1 处出处')
    expect(w.emitted('show-sources')).toHaveLength(1)
    expect(w.emitted('copy')).toHaveLength(1)
  })
  it('已回答：当前回答的出处按钮 aria-pressed=true', () => {
    expect(card({}, { active: true }).get('[data-test="answer-sources-toggle"]').attributes('aria-pressed')).toBe('true')
    expect(card({}).get('[data-test="answer-sources-toggle"]').attributes('aria-pressed')).toBe('false')
  })
  it('资料未覆盖：给下一步，没有出处与复制按钮，也不是错误卡', () => {
    const w = card({ status: 'not_covered', citations: [], answer: '课程资料不足。', relatedKpIds: ['kp_a'] })
    expect(w.get('[data-test="chat-nc-next"]').text()).toContain('换个问法')
    expect(w.find('[data-test="answer-sources-toggle"]').exists()).toBe(false)
    expect(w.find('[data-test="chat-copy"]').exists()).toBe(false)
    expect(w.find('[data-test="answer-error-reason"]').exists()).toBe(false)
  })
  it('未完成：原因只出现一次，role=alert，有重试；发送中重试禁用', async () => {
    const w = card({ status: 'error', citations: [], answer: '问答暂时失败，请稍后重试。' })
    expect(w.text().split('问答暂时失败').length - 1).toBe(1)
    expect(w.get('[data-test="answer-error-reason"]').attributes('role')).toBe('alert')
    expect(w.find('[data-test="chat-nc-next"]').exists()).toBe(false)
    await w.get('[data-test="answer-retry"]').trigger('click')
    expect(w.emitted('retry')).toHaveLength(1)
    const busy = card({ status: 'error', citations: [], answer: 'x' }, { sending: true })
    expect(busy.get('[data-test="answer-retry"]').attributes('disabled')).toBeDefined()
  })
  it('复制反馈：成功与失败文字，role=status', () => {
    expect(card({}, { copyState: { ok: true } }).get('[data-test="chat-copy-status"]').text()).toBe('已复制回答和出处。')
    const failed = card({}, { copyState: { ok: false } }).get('[data-test="chat-copy-status"]')
    expect(failed.text()).toContain('复制失败')
    expect(failed.attributes('role')).toBe('status')
  })
  it('版本不同时显示「基于第 N 版」', () => {
    expect(card({ graphVersion: 1 }, { currentVersion: 3 }).text()).toContain('基于第 1 版')
  })
  it('点正文引用编号发出 citation 事件', async () => {
    const w = card({})
    await w.get('.citation').trigger('click')
    expect(w.emitted('citation')?.[0]).toEqual([cite])
  })
})
