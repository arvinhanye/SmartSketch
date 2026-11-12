import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { CHAT_STREAM_CLIENT_KEY } from '../../src/frontend/src/api/chatStream'
import { PUBLISHED_GRAPH_API_KEY } from '../../src/frontend/src/api/graph'
import GraphPreviewCard from '../../src/frontend/src/components/GraphPreviewCard.vue'
import { CHAT_ROUTE, COURSE_ROUTE } from '../../src/frontend/src/router/index.ts'
import ChatView from '../../src/frontend/src/views/ChatView.vue'
import { prerequisiteWouldCycle } from '../../src/frontend/src/graph/cycle'
import { nodeAt, type NodeAnchor } from '../../src/frontend/src/graph/hitTest'

/**
 * UI-GRAPH-EDIT-02：画布直接操作用到的纯函数（成环预判、节点命中）。
 * 组件与页面流程见 canvas-edit-layer.test.ts 与 h14.test.ts。
 */
type E = { type: string; from_id: string; to_id: string; status: string }
const pre = (from: string, to: string, status = 'approved'): E => ({ type: 'PREREQUISITE', from_id: from, to_id: to, status })

describe('prerequisiteWouldCycle：新增「起点 → 目标」前置关系是否成环', () => {
  // a → b → c，d 孤立
  const edges = [pre('a', 'b'), pre('b', 'c')]

  it('目标沿前置关系能回到起点就会成环（含多跳）；反之不会', () => {
    expect(prerequisiteWouldCycle(edges, 'c', 'a')).toBe(true)
    expect(prerequisiteWouldCycle(edges, 'b', 'a')).toBe(true)
    expect(prerequisiteWouldCycle(edges, 'a', 'c')).toBe(false)
    expect(prerequisiteWouldCycle(edges, 'd', 'a')).toBe(false)
    expect(prerequisiteWouldCycle(edges, 'c', 'd')).toBe(false)
  })

  it('起点与目标相同视为成环', () => {
    expect(prerequisiteWouldCycle(edges, 'a', 'a')).toBe(true)
  })

  it('只看未驳回的前置关系：其他类型、已驳回的不参与', () => {
    const mixed = [{ type: 'CONTAINS', from_id: 'a', to_id: 'b', status: 'approved' }, pre('b', 'c', 'rejected'), pre('c', 'd', 'low_confidence')]
    expect(prerequisiteWouldCycle(mixed, 'b', 'a')).toBe(false)
    expect(prerequisiteWouldCycle(mixed, 'c', 'b')).toBe(false)
    expect(prerequisiteWouldCycle(mixed, 'd', 'c')).toBe(true)
  })

  it('图里本来就有环时不会死循环', () => {
    const loop = [pre('a', 'b'), pre('b', 'a'), pre('b', 'c')]
    expect(prerequisiteWouldCycle(loop, 'x', 'a')).toBe(false)
    expect(prerequisiteWouldCycle(loop, 'c', 'a')).toBe(true)
  })
})

describe('nodeAt：指针落在哪个节点上', () => {
  const anchors: NodeAnchor[] = [
    { kpId: 'a', x: 100, y: 100, r: 18 },
    { kpId: 'b', x: 130, y: 100, r: 18 },
    { kpId: 'c', x: 300, y: 300, r: 10 },
  ]

  it('在半径加容差之内命中；两个都覆盖时取圆心更近的；之外为 null', () => {
    expect(nodeAt(anchors, 100, 100)?.kpId).toBe('a')
    expect(nodeAt(anchors, 118, 100)?.kpId).toBe('b')
    expect(nodeAt(anchors, 112, 100)?.kpId).toBe('a')
    expect(nodeAt(anchors, 313, 300)?.kpId).toBe('c')
    expect(nodeAt(anchors, 320, 300)).toBe(null)
    expect(nodeAt([], 0, 0)).toBe(null)
  })

  it('可排除某个节点（连线时的起点）', () => {
    expect(nodeAt(anchors, 96, 100, { exclude: 'a' })).toBe(null)
    expect(nodeAt(anchors, 114, 100, { exclude: 'a' })?.kpId).toBe('b')
  })
})

// ---------------------------------------------------------------- 学生页：预览卡“就此提问”

describe('预览卡“就此提问”', () => {
  const base = { name: '循环队列', type: 'concept' as const, chapter: '第三章', masteryText: '学习中', mastery: 'learning' as const, prerequisites: 1, unlocks: 2, localActive: false }
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('只在问答页可用时出现；点击发出 ask，不影响原有两个按钮', async () => {
    const without = mount(GraphPreviewCard, { props: base })
    expect(without.find('[data-test="gw-preview-ask"]').exists()).toBe(false)
    const w = mount(GraphPreviewCard, { props: { ...base, canAsk: true } })
    await w.get('[data-test="gw-preview-ask"]').trigger('click')
    expect(w.emitted('ask')).toHaveLength(1)
    expect(w.emitted('open')).toBeUndefined()
    expect(w.find('[data-test="gw-preview-open"]').exists()).toBe(true)
    expect(w.find('[data-test="gw-preview-local"]').exists()).toBe(true)
  })

  async function mountChat(path: string) {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/courses/:cid', name: COURSE_ROUTE, component: { render: () => null } },
        { path: '/courses/:cid/chat', name: CHAT_ROUTE, component: ChatView },
      ],
    })
    await router.push(path)
    await router.isReady()
    const ask = vi.fn()
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(ChatView, {
      attachTo: document.body,
      global: {
        plugins: [pinia, router],
        provide: {
          [CHAT_STREAM_CLIENT_KEY as symbol]: { ask, stop: vi.fn() } as never,
          [PUBLISHED_GRAPH_API_KEY as symbol]: { getPublished: vi.fn() } as never,
        },
      },
    })
    await flushPromises()
    return { wrapper, router, ask }
  }

  it('问答页按 ?about= 预填问题、光标进输入框、不自动发送；用过就从地址里拿掉', async () => {
    const { wrapper, router, ask } = await mountChat('/courses/c1/chat?about=%E5%BE%AA%E7%8E%AF%E9%98%9F%E5%88%97')
    const box = wrapper.get('textarea').element as HTMLTextAreaElement
    expect(box.value).toBe('请讲解一下「循环队列」')
    expect(document.activeElement).toBe(box)
    expect(ask).not.toHaveBeenCalled()
    expect(wrapper.findAll('.question')).toHaveLength(0)
    expect(router.currentRoute.value.query.about).toBeUndefined()
  })

  it('没有 about、或只有空白时不预填', async () => {
    expect(((await mountChat('/courses/c1/chat')).wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('')
    expect(((await mountChat('/courses/c1/chat?about=%20%20')).wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('')
  })
})
