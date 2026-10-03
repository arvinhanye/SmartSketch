import { flushPromises } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { edgeElementId, nodeElementId, RELATION_STYLES, type G6Edge, type G6Node, type RelationType } from '../../src/frontend/src/graph/adapter'
import {
  createGraphLifecycle,
  READABLE_ZOOM,
  type CanvasGraph,
  type CanvasGraphInit,
  type GraphCanvasData,
} from '../../src/frontend/src/graph/lifecycle'

// L13-1（R06）：节点多时整图适配会把图缩成一条不可读的细线（L11 走查截图：129 个节点）。
// 初始视口不低于可读缩放并聚焦到入口节点；页面可按知识点聚焦（搜索、问答跳转用）。

class ZoomGraph implements CanvasGraph {
  destroyed = false
  calls: string[] = []
  zoom: number
  constructor(readonly init: CanvasGraphInit, zoomAfterFit: number) {
    this.zoom = zoomAfterFit
  }
  async render() { this.calls.push('render') }
  setData() { this.calls.push('setData') }
  setSize() { this.calls.push('setSize') }
  async fitView() { this.calls.push('fitView') }
  on() { return undefined }
  destroy() { this.destroyed = true }
  getZoom() { return this.zoom }
  async zoomTo(zoom: number) { this.calls.push(`zoomTo ${zoom}`); this.zoom = zoom }
  async focusElement(id: string) { this.calls.push(`focus ${id}`) }
}

/** 不实现可选视口方法的旧替身（H04 同款），确保兼容 */
class PlainGraph implements CanvasGraph {
  destroyed = false
  async render() {}
  setData() {}
  setSize() {}
  async fitView() {}
  on() { return undefined }
  destroy() { this.destroyed = true }
}

function container(): HTMLElement {
  const el = document.createElement('div')
  Object.defineProperty(el, 'clientWidth', { value: 800 })
  Object.defineProperty(el, 'clientHeight', { value: 600 })
  return el
}

function node(id: string): G6Node {
  return {
    id: nodeElementId(id),
    data: { kpId: id, name: id.toUpperCase(), type: 'concept', level: 0, chapterId: 'ch', status: 'approved',
            confidence: 0.9, source: 'ai', locked: false },
  } as G6Node
}

function edge(id: string, type: RelationType, from: string, to: string): G6Edge {
  const s = RELATION_STYLES[type]
  return {
    id: edgeElementId(id), source: nodeElementId(from), target: nodeElementId(to),
    data: { relationId: id, type, directed: s.directed, status: 'approved', confidence: 0.8, source: 'ai', downgraded: false },
    style: { stroke: s.stroke, lineWidth: s.lineWidth, lineDash: [...s.lineDash], endArrow: s.directed, labelText: s.label },
  } as G6Edge
}

// b 在数据里排第一，但 a 才是没有前置（入度为 0）的入口节点
const DATA: GraphCanvasData = {
  nodes: [node('b'), node('a'), node('c')],
  edges: [edge('r1', 'PREREQUISITE', 'a', 'b'), edge('r2', 'PREREQUISITE', 'b', 'c')],
}

function start(zoomAfterFit: number, onZoom?: (zoom: number) => void) {
  let graph!: ZoomGraph
  const life = createGraphLifecycle(container(), {
    data: DATA,
    factory: (init) => (graph = new ZoomGraph(init, zoomAfterFit)),
    onZoom,
  })
  return { life, graph: () => graph }
}

describe('L13-1 可读的初始视口', () => {
  it('整图适配后缩放低于可读值：放大到可读缩放并聚焦到第一个没有前置的节点', async () => {
    const zooms: number[] = []
    const { graph } = start(0.2, (z) => zooms.push(z))
    await flushPromises()
    expect(graph().calls).toEqual(['render', `zoomTo ${READABLE_ZOOM}`, `focus ${nodeElementId('a')}`])
    expect(zooms.at(-1)).toBe(READABLE_ZOOM)
  })

  it('本来就可读时不改缩放、不移动视口', async () => {
    const zooms: number[] = []
    const { graph } = start(1.2, (z) => zooms.push(z))
    await flushPromises()
    expect(graph().calls).toEqual(['render'])
    expect(zooms.at(-1)).toBe(1.2)
  })

  it('focus(kpId) 聚焦到对应节点；未知节点不动', async () => {
    const { life, graph } = start(1.2)
    await flushPromises()
    life.focus('c')
    life.focus('not-here')
    await flushPromises()
    expect(graph().calls).toEqual(['render', `focus ${nodeElementId('c')}`])
  })

  it('建图前请求的聚焦在首次渲染后落到该节点（取代入口节点）', async () => {
    let graph!: ZoomGraph
    const el = document.createElement('div')
    Object.defineProperty(el, 'clientWidth', { value: 0, configurable: true })
    Object.defineProperty(el, 'clientHeight', { value: 0, configurable: true })
    const life = createGraphLifecycle(el, { data: DATA, factory: (init) => (graph = new ZoomGraph(init, 0.2)) })
    life.focus('c')
    Object.defineProperty(el, 'clientWidth', { value: 800 })
    Object.defineProperty(el, 'clientHeight', { value: 600 })
    life.refreshSize()
    await new Promise((resolve) => setTimeout(resolve, 30))
    await flushPromises()
    expect(graph.calls).toEqual(['render', `zoomTo ${READABLE_ZOOM}`, `focus ${nodeElementId('c')}`])
  })

  it('替身不实现视口方法时照常渲染，不报错', async () => {
    const statuses: string[] = []
    const life = createGraphLifecycle(container(), {
      data: DATA, factory: () => new PlainGraph(), onStatus: (s) => statuses.push(s),
    })
    life.focus('a')
    await flushPromises()
    expect(statuses.at(-1)).toBe('ready')
  })
})

// ---------------------------------------------------------------- L13-2 搜索定位并选中

import { mount } from '@vue/test-utils'
import { effectScope } from 'vue'
import GraphToolbar from '../../src/frontend/src/components/GraphToolbar.vue'
import { defaultFilterState, locateNode, useGraphFilters } from '../../src/frontend/src/composables/useGraphFilters'

function named(id: string, name: string, type = 'concept'): G6Node {
  return { ...node(id), data: { ...node(id).data, name, type } } as G6Node
}

const SEARCH: GraphCanvasData = {
  nodes: [named('q', '循环队列'), named('d', '队列'), named('s', '栈'), named('x', '队列的应用', 'example')],
  edges: [],
}

describe('L13-2 搜索定位', () => {
  it('名称完全一致优先于包含匹配；忽略首尾空白与全半角', () => {
    expect(locateNode(SEARCH, defaultFilterState(), ' 队列 ')).toBe('d')
    expect(locateNode(SEARCH, defaultFilterState(), '循环')).toBe('q')
  })

  it('被筛选隐藏的节点不参与匹配；没有匹配返回 null', () => {
    const onlyConcepts = { ...defaultFilterState(), nodeTypes: ['concept'] } as ReturnType<typeof defaultFilterState>
    expect(locateNode(SEARCH, onlyConcepts, '应用')).toBe(null)
    expect(locateNode(SEARCH, defaultFilterState(), '不存在的知识点')).toBe(null)
    expect(locateNode(SEARCH, defaultFilterState(), '   ')).toBe(null)
  })

  it('filters.locate 命中即选中；未命中不清空当前选中', () => {
    const scope = effectScope()
    const filters = scope.run(() => useGraphFilters(() => SEARCH))!
    filters.select('s')
    expect(filters.locate('循环队列')).toBe('q')
    expect(filters.selected.value).toBe('q')
    expect(filters.locate('不存在')).toBe(null)
    expect(filters.selected.value).toBe('q')
    scope.stop()
  })

  it('工具栏在搜索框按回车时发出 locate（带当前关键字）', async () => {
    const wrapper = mount(GraphToolbar, {
      props: { modelValue: { ...defaultFilterState(), query: '队列' }, layout: 'hierarchical', chapters: [], summary: null, canClear: false },
    })
    await wrapper.get('input[type="search"]').trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('locate')).toEqual([['队列']])
  })
})

describe('L13-3 高级筛选折叠', () => {
  it('搜索框、关系图例与布局常显；类型、状态、章节收进默认收起的「更多筛选」', () => {
    const wrapper = mount(GraphToolbar, {
      props: { modelValue: defaultFilterState(), layout: 'hierarchical', chapters: [], summary: null, canClear: false },
    })
    const advanced = wrapper.get('[data-test="gt-advanced"]')
    expect(advanced.element.tagName).toBe('DETAILS')
    expect(advanced.attributes('open')).toBeUndefined()
    expect(advanced.get('summary').text()).toContain('更多筛选')
    expect(advanced.find('[data-node-type]').exists()).toBe(true)
    expect(advanced.find('[data-test="status-filter"]').exists()).toBe(true)
    expect(advanced.find('select').exists()).toBe(true)
    expect(advanced.find('input[type="search"]').exists()).toBe(false)
    expect(advanced.find('[data-test="relation-legend"]').exists()).toBe(false)
    expect(advanced.find('[role="radiogroup"]').exists()).toBe(false)
  })
})
