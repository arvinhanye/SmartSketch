import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import DuplicateCompare from '../../src/frontend/src/components/review/DuplicateCompare.vue'
import MergePreviewGraph from '../../src/frontend/src/components/review/MergePreviewGraph.vue'
import { mergePreview } from '../../src/frontend/src/graph/mergePreview'

/**
 * UX-REVIEW-DEDUP-01：疑似重复展开后的并排对比与合并预览小图（组件层）。
 * 页面流程（连续处理、键盘）在 h09.test.ts；推算规则在 merge-preview.test.ts。
 */
type GraphExchange = components['schemas']['GraphExchange']
type KnowledgePoint = components['schemas']['KnowledgePoint']
type Relation = components['schemas']['Relation']
type SuspectedDuplicate = components['schemas']['SuspectedDuplicate']

function kp(id: string, over: Partial<KnowledgePoint> = {}): KnowledgePoint {
  return {
    id, course_id: 'c1', name: `知识点${id}`, type: 'concept', definition: `${id} 的定义`, level: 1, confidence: 0.9,
    status: 'approved', source: 'ai', locked: false, revision: 1, chapter_id: 'ch1', ...over,
  }
}
function rel(id: string, from: string, to: string, type: Relation['type'] = 'CONTAINS'): Relation {
  return { id, course_id: 'c1', type, from_id: from, to_id: to, confidence: 0.9, status: 'approved', source: 'ai', source_refs: [] } as Relation
}
const draft = (): GraphExchange =>
  ({
    format_version: '1.0', course_id: 'c1', graph_version: null, generated_at: '2026-11-11T00:00:00Z',
    chapters: [{ id: 'ch1', title: '第三章 栈与队列', order: 3 }],
    nodes: [
      kp('p', { name: '栈与队列' }),
      kp('a', { name: '队列', definition: '先进先出的线性表。', source_refs: [{ chunk_id: 'c1', document_id: 'd1', page: 2 }] as never }),
      kp('b', { name: '队列的定义', definition: '3.3.1 一节的主题。', aliases: ['FIFO 表'], type: 'method', chapter_id: null }),
      kp('x', { name: '入队' }), kp('z', { name: '队头', type: 'formula' }),
    ],
    edges: [rel('pa', 'p', 'a'), rel('pb', 'p', 'b'), rel('ax', 'a', 'x'), rel('bz', 'b', 'z', 'RELATED_TO')],
  }) as unknown as GraphExchange

const pair: SuspectedDuplicate = { candidates: [{ id: 'a', name: '队列', type: 'concept' }, { id: 'b', name: '队列的定义', type: 'method' }], similarity: 0.92, reason: 'containment' }

const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { render: () => null } }, { path: '/g', name: 'g', component: { render: () => null } }] })
function mountCompare(props: Record<string, unknown> = {}) {
  return mount(DuplicateCompare, {
    attachTo: document.body,
    global: { plugins: [router] },
    props: { pair, graph: draft(), primaryId: 'a', busy: false, error: null, radioName: 'primary-a|b', graphLink: null, ...props },
  })
}
afterEach(() => {
  document.body.innerHTML = ''
})

describe('DuplicateCompare：并排对比', () => {
  it('两张卡片显示名称、定义、类型与章节、别名、来源与关系数量；被选中的标“保留”，另一个标“并入”', () => {
    const w = mountCompare()
    const cards = w.findAll('[data-test="rv-dup-card"]')
    expect(cards).toHaveLength(2)
    const first = cards[0]!.text()
    expect(first).toContain('队列')
    expect(first).toContain('先进先出的线性表。')
    expect(first).toContain('概念 · 第三章 栈与队列')
    expect(first).toContain('来源 1 处 · 关系 2 条')
    expect(first).toContain('保留')
    const second = cards[1]!.text()
    expect(second).toContain('方法 · 未分章')
    expect(second).toContain('别名：FIFO 表')
    expect(second).toContain('并入')
    expect(cards[0]!.classes()).toContain('is-primary')
    expect((cards[0]!.get('input').element as HTMLInputElement).checked).toBe(true)
    w.unmount()
  })

  it('点另一张卡片的单选发出 choose；合并、不是重复、收起各发各的事件；主按钮写明并入谁', async () => {
    const w = mountCompare()
    await w.findAll('[data-test="rv-primary"]')[1]!.setValue(true)
    expect(w.emitted('choose')).toEqual([['b']])
    expect(w.get('[data-test="rv-merge-confirm"]').text()).toBe('合并到「队列」')
    await w.get('[data-test="rv-merge-confirm"]').trigger('click')
    await w.get('[data-test="rv-not-duplicate"]').trigger('click')
    await w.get('[data-test="rv-merge-cancel"]').trigger('click')
    expect(w.emitted('merge')).toHaveLength(1)
    expect(w.emitted('reject')).toHaveLength(1)
    expect(w.emitted('collapse')).toHaveLength(1)
    w.unmount()
  })

  it('切换保留对象后，“合并后”小图与文字说明随之变化', async () => {
    const w = mountCompare()
    expect(w.get('[data-test="rv-dup-facts"]').text()).toContain('改接到「队列」的关系 1 条')
    expect(w.get('[data-test="rv-dup-facts"]').text()).toContain('重复的关系合并掉 1 条')
    expect(w.get('[data-test="rv-dup-facts"]').text()).toContain('新增别名：队列的定义、FIFO 表')
    const afterIds = () => w.findAll('[data-test="rv-mini"]')[1]!.findAll('[data-test="rv-mini-node"]').map((n) => `${n.attributes('data-id')}:${n.attributes('data-role')}`).sort()
    expect(afterIds()).toEqual(['a:primary', 'p:neighbor', 'x:neighbor', 'z:neighbor'])
    await w.setProps({ primaryId: 'b' })
    expect(afterIds()).toEqual(['b:primary', 'p:neighbor', 'x:neighbor', 'z:neighbor'])
    expect(w.get('[data-test="rv-dup-facts"]').text()).toContain('改接到「队列的定义」的关系 1 条')
    expect(w.get('[data-test="rv-merge-summary"]').text()).toContain('「队列」将并入「队列的定义」')
    w.unmount()
  })

  it('草稿图读不到、或图里找不到这两个知识点时不显示对比细节与小图，但仍可操作', () => {
    const none = mountCompare({ graph: null })
    expect(none.find('[data-test="rv-dup-preview"]').exists()).toBe(false)
    expect(none.get('[data-test="rv-dup-no-preview"]').text()).toContain('草稿图谱暂时读取不到')
    expect(none.findAll('[data-test="rv-dup-card"]')).toHaveLength(2)
    expect(none.find('[data-test="rv-dup-definition"]').exists()).toBe(false)
    expect(none.get('[data-test="rv-merge-confirm"]').attributes('disabled')).toBeUndefined()
    none.unmount()

    const missing = mountCompare({ graph: { ...draft(), nodes: draft().nodes.filter((n) => n.id !== 'b') } })
    expect(missing.get('[data-test="rv-dup-no-preview"]').text()).toContain('找不到这两个知识点')
    missing.unmount()
  })

  it('合并成环的错误与环路显示在条目里；处理中时按钮与单选不可用', () => {
    const w = mountCompare({ busy: true, error: { key: 'a|b', message: '合并后前置关系会成环，未合并。', cycle: [{ kpId: 'p', name: '栈与队列' }, { kpId: 'a', name: '队列' }, { kpId: 'p', name: '栈与队列' }] } })
    expect(w.get('[data-test="rv-item-error"]').text()).toContain('会成环')
    expect(w.get('[data-test="rv-cycle"]').text().replace(/\s+/g, '')).toBe('环路：栈与队列→队列→栈与队列')
    expect(w.get('[data-test="rv-merge-confirm"]').attributes('disabled')).toBeDefined()
    expect(w.findAll('[data-test="rv-primary"]').every((r) => r.attributes('disabled') !== undefined)).toBe(true)
    w.unmount()
  })

  it('“在图谱中查看”只在给了去向时出现', () => {
    expect(mountCompare().find('[data-test="rv-dup-graph-link"]').exists()).toBe(false)
    const w = mountCompare({ graphLink: { name: 'g', query: { pair: 'a,b' } } })
    expect(w.get('[data-test="rv-dup-graph-link"]').attributes('href')).toBe('/g?pair=a,b')
    w.unmount()
  })
})

describe('MergePreviewGraph：小图', () => {
  const preview = () => mergePreview(draft(), ['a', 'b'], 'a')!

  it('画出全部节点与关系；节点带角色；有读屏说明；位置都在画布内', () => {
    const w = mount(MergePreviewGraph, { props: { graph: preview().before, label: '合并前' } })
    const nodes = w.findAll('[data-test="rv-mini-node"]')
    expect(nodes.map((n) => n.attributes('data-role')).sort()).toEqual(['merged', 'neighbor', 'neighbor', 'neighbor', 'primary'])
    expect(w.findAll('[data-test="rv-mini-edge"]')).toHaveLength(4)
    expect(w.findAll('[data-test="rv-mini-moved"]')).toHaveLength(0)
    expect(w.get('svg').attributes('aria-label')).toContain('合并前：队列 与 队列的定义')
    for (const circle of w.findAll('circle')) {
      const cx = Number(circle.attributes('cx'))
      const cy = Number(circle.attributes('cy'))
      expect(cx).toBeGreaterThan(0)
      expect(cx).toBeLessThan(360)
      expect(cy).toBeGreaterThan(0)
      expect(cy).toBeLessThan(216)
    }
    // 指向这两个知识点的（栈与队列）在上排，其余在下排
    const y = (id: string) => Number(w.get(`[data-id="${id}"] circle`).attributes('cy'))
    expect(y('p')).toBeLessThan(y('a'))
    expect(y('x')).toBeGreaterThan(y('a'))
    expect(y('a')).toBe(y('b'))
  })

  it('合并后改接的关系加强调底色；有方向的关系带箭头，“相关”不带', () => {
    const w = mount(MergePreviewGraph, { props: { graph: preview().after, label: '合并后（预计）' } })
    expect(w.findAll('[data-test="rv-mini-moved"]')).toHaveLength(1)
    const edges = w.findAll('[data-test="rv-mini-edge"]')
    expect(edges).toHaveLength(3)
    expect(edges.filter((e) => e.attributes('marker-end') !== undefined)).toHaveLength(2)
  })

  it('没画出来的相邻知识点有文字说明；长名称截断但完整名称留在 title 里', () => {
    const graph = { nodes: [{ id: 'a', name: '一个特别特别长的知识点名称用来测试截断', type: 'concept' as const, role: 'primary' as const, aliases: [], locked: false }], edges: [], hiddenNeighbors: 3 }
    const w = mount(MergePreviewGraph, { props: { graph, label: '合并后（预计）' } })
    expect(w.get('[data-test="rv-mini-more"]').text()).toBe('另有 3 个相邻知识点未画出')
    expect(w.get('.rv-mini__name').text().endsWith('…')).toBe(true)
    expect(w.get('title').text()).toBe('一个特别特别长的知识点名称用来测试截断')
  })
})
