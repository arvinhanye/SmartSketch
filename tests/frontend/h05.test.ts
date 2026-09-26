import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, ref, shallowRef } from 'vue'
import GraphCanvas from '../../src/frontend/src/components/GraphCanvas.vue'
import GraphToolbar from '../../src/frontend/src/components/GraphToolbar.vue'
import {
  chapterOptions,
  defaultFilterState,
  filterGraph,
  useGraphFilters,
  type GraphFilterState,
} from '../../src/frontend/src/composables/useGraphFilters'
import {
  edgeElementId,
  nodeElementId,
  RELATION_STYLES,
  type G6Edge,
  type G6Node,
  type KnowledgePoint,
  type RelationType,
} from '../../src/frontend/src/graph/adapter'
import {
  buildGraphOptions,
  createGraphLifecycle,
  GRAPH_FACTORY_KEY,
  layoutOptions,
  type CanvasGraph,
  type CanvasGraphFactory,
  type CanvasGraphInit,
  type GraphCanvasData,
} from '../../src/frontend/src/graph/lifecycle'

// ---------- 数据 ----------

type Status = KnowledgePoint['status']
type KpType = KnowledgePoint['type']

const RELATION_TYPES: RelationType[] = ['CONTAINS', 'PREREQUISITE', 'RELATED_TO', 'EXAMPLE_OF']

function node(id: string, name: string, extra: { type?: KpType; status?: Status; chapterId?: string | null } = {}): G6Node {
  return {
    id: nodeElementId(id),
    data: {
      kpId: id,
      name,
      type: extra.type ?? 'concept',
      level: 0,
      chapterId: extra.chapterId === undefined ? 'ch1' : extra.chapterId,
      status: extra.status ?? 'approved',
      confidence: 0.9,
      source: 'ai',
      locked: false,
    },
  }
}

function edge(id: string, type: RelationType, from: string, to: string, status: Status = 'approved'): G6Edge {
  const s = RELATION_STYLES[type]
  return {
    id: edgeElementId(id),
    source: nodeElementId(from),
    target: nodeElementId(to),
    data: { relationId: id, type, directed: s.directed, status, confidence: 0.8, source: 'ai', downgraded: false },
    style: { stroke: s.stroke, lineWidth: s.lineWidth, lineDash: [...s.lineDash], endArrow: s.directed, labelText: s.label },
  }
}

/** 数据结构课程片段：两章、五类知识点、四类关系，含驳回与低置信度 */
function sample(): GraphCanvasData {
  return {
    nodes: [
      node('ds', '数据结构', { chapterId: 'ch1' }),
      node('stack', '栈', { chapterId: 'ch1' }),
      node('queue', '队列', { chapterId: 'ch1', status: 'low_confidence' }),
      node('avl', 'AVL 树', { chapterId: 'ch2', type: 'method' }),
      node('bst', '二叉搜索树', { chapterId: 'ch2', type: 'theorem' }),
      node('bracket', '括号匹配', { chapterId: 'ch1', type: 'example' }),
      node('heap', 'Heap 堆', { chapterId: null, status: 'rejected', type: 'formula' }),
    ],
    edges: [
      edge('e1', 'CONTAINS', 'ds', 'stack'),
      edge('e2', 'CONTAINS', 'ds', 'queue'),
      edge('e3', 'PREREQUISITE', 'bst', 'avl'),
      edge('e4', 'RELATED_TO', 'stack', 'queue', 'low_confidence'),
      edge('e5', 'EXAMPLE_OF', 'bracket', 'stack'),
      edge('e6', 'PREREQUISITE', 'stack', 'bst', 'rejected'),
      edge('e7', 'RELATED_TO', 'heap', 'bst'),
    ],
  }
}

function deepFreeze<T>(value: T): T {
  if (value !== null && typeof value === 'object') {
    for (const inner of Object.values(value)) deepFreeze(inner)
    Object.freeze(value)
  }
  return value
}

function ids(data: GraphCanvasData | null): { nodes: string[]; edges: string[] } {
  return { nodes: data?.nodes.map((n) => n.data.kpId) ?? [], edges: data?.edges.map((e) => e.data.relationId) ?? [] }
}

function expectNoDangling(data: GraphCanvasData): void {
  const present = new Set(data.nodes.map((n) => n.id))
  for (const e of data.edges) {
    expect(present.has(e.source), `${e.id} 起点 ${e.source}`).toBe(true)
    expect(present.has(e.target), `${e.id} 终点 ${e.target}`).toBe(true)
  }
}

function state(patch: Partial<GraphFilterState> = {}): GraphFilterState {
  return { ...defaultFilterState(), ...patch }
}

// ---------- 纯筛选 ----------

describe('H05 filterGraph', () => {
  it('默认条件显示全部节点与边，顺序与输入一致', () => {
    const out = filterGraph(sample(), defaultFilterState(), null)
    expect(ids(out)).toEqual(ids(sample()))
  })

  it('默认条件包含四类关系、五类知识点、四种状态与全部章节', () => {
    const s = defaultFilterState()
    expect([...s.relationTypes].sort()).toEqual([...RELATION_TYPES].sort())
    expect([...s.nodeTypes].sort()).toEqual(['concept', 'example', 'formula', 'method', 'theorem'])
    expect([...s.statuses].sort()).toEqual(['approved', 'draft', 'low_confidence', 'rejected'])
    expect(s.chapter).toEqual({ kind: 'all' })
    expect(s.query).toBe('')
  })

  it.each(RELATION_TYPES)('取消关系类型 %s 只隐藏该类边，不隐藏节点', (type) => {
    const out = filterGraph(sample(), state({ relationTypes: RELATION_TYPES.filter((t) => t !== type) }), null)
    expect(out.nodes).toHaveLength(sample().nodes.length)
    expect(out.edges.map((e) => e.data.type)).not.toContain(type)
    expect(out.edges).toHaveLength(sample().edges.filter((e) => e.data.type !== type).length)
  })

  it('按知识点类型筛选后没有悬空边', () => {
    const out = filterGraph(sample(), state({ nodeTypes: ['concept', 'theorem'] }), null)
    expect(ids(out).nodes).toEqual(['ds', 'stack', 'queue', 'bst'])
    expect(ids(out).edges).toEqual(['e1', 'e2', 'e4', 'e6'])
    expectNoDangling(out)
  })

  it('任意条件组合都不产生悬空边', () => {
    const data = sample()
    const queries = ['', '栈', 'avl', '树', '不存在']
    const chapters: GraphFilterState['chapter'][] = [{ kind: 'all' }, { kind: 'none' }, { kind: 'chapter', id: 'ch1' }, { kind: 'chapter', id: 'ch2' }]
    const statusSets: Status[][] = [['approved'], ['approved', 'low_confidence', 'draft'], ['rejected'], []]
    let checked = 0
    for (const query of queries)
      for (const chapter of chapters)
        for (const statuses of statusSets)
          for (let mask = 0; mask < 16; mask += 1) {
            const relationTypes = RELATION_TYPES.filter((_, i) => (mask >> i) & 1)
            const out = filterGraph(data, state({ query, chapter, statuses, relationTypes }), null)
            expectNoDangling(out)
            checked += 1
          }
    expect(checked).toBe(5 * 4 * 4 * 16)
  })

  it('搜索按名称包含匹配，忽略大小写、全角与首尾空白', () => {
    expect(ids(filterGraph(sample(), state({ query: '  avl ' }), null)).nodes).toEqual(['avl'])
    expect(ids(filterGraph(sample(), state({ query: 'ＨＥＡＰ' }), null)).nodes).toEqual(['heap'])
    const tree = filterGraph(sample(), state({ query: '树' }), null)
    expect(ids(tree)).toEqual({ nodes: ['avl', 'bst'], edges: ['e3'] })
  })

  it('搜索无匹配时返回空图；只有空白的搜索词等于未搜索', () => {
    expect(ids(filterGraph(sample(), state({ query: '红黑树' }), null))).toEqual({ nodes: [], edges: [] })
    expect(ids(filterGraph(sample(), state({ query: '   ' }), null))).toEqual(ids(sample()))
  })

  it('按章节筛选，「未分章」只留没有章节的知识点', () => {
    expect(ids(filterGraph(sample(), state({ chapter: { kind: 'chapter', id: 'ch2' } }), null))).toEqual({
      nodes: ['avl', 'bst'],
      edges: ['e3'],
    })
    expect(ids(filterGraph(sample(), state({ chapter: { kind: 'none' } }), null)).nodes).toEqual(['heap'])
  })

  it('取消「已驳回」同时隐藏驳回的节点与关系', () => {
    const out = filterGraph(sample(), state({ statuses: ['draft', 'low_confidence', 'approved'] }), null)
    expect(ids(out).nodes).not.toContain('heap')
    expect(ids(out).edges).not.toContain('e6')
    expect(ids(out).edges).not.toContain('e7')
    expectNoDangling(out)
  })

  it('只看低置信度：留下低置信度节点与关系，端点被隐藏的关系一并去掉', () => {
    const out = filterGraph(sample(), state({ statuses: ['low_confidence'] }), null)
    expect(ids(out)).toEqual({ nodes: ['queue'], edges: [] })
  })

  it('驳回与低置信度的元素带状态标记，供画布区分样式', () => {
    const out = filterGraph(sample(), defaultFilterState(), null)
    const nodeStates = Object.fromEntries(out.nodes.map((n) => [n.data.kpId, n.states ?? []]))
    expect(nodeStates.heap).toEqual(['rejected'])
    expect(nodeStates.queue).toEqual(['lowConfidence'])
    expect(nodeStates.stack).toEqual([])
    const edgeStates = Object.fromEntries(out.edges.map((e) => [e.data.relationId, e.states ?? []]))
    expect(edgeStates.e6).toEqual(['rejected'])
    expect(edgeStates.e4).toEqual(['lowConfidence'])
    expect(edgeStates.e1).toEqual([])
  })

  it('选中的知识点带 selected 状态，排在审核状态之后', () => {
    const out = filterGraph(sample(), defaultFilterState(), 'queue')
    expect(out.nodes.find((n) => n.data.kpId === 'queue')!.states).toEqual(['lowConfidence', 'selected'])
    expect(out.nodes.filter((n) => n.states?.includes('selected'))).toHaveLength(1)
  })

  it('不修改输入，也不修改筛选条件', () => {
    const data = deepFreeze(sample())
    const s = deepFreeze(state({ query: '栈', relationTypes: ['CONTAINS'] }))
    expect(() => filterGraph(data, s, 'stack')).not.toThrow()
    expect(data).toEqual(sample())
  })
})

describe('H05 chapterOptions', () => {
  it('按章节顺序给出标题，图中出现但目录没有的章节用 ID 兜底，未分章放最后', () => {
    const opts = chapterOptions(sample(), [
      { id: 'ch2', title: '树', order: 2 },
      { id: 'ch1', title: '线性表', order: 1 },
      { id: 'ch9', title: '图中没有', order: 9 },
    ])
    expect(opts).toEqual([
      { value: { kind: 'chapter', id: 'ch1' }, label: '线性表' },
      { value: { kind: 'chapter', id: 'ch2' }, label: '树' },
      { value: { kind: 'none' }, label: '未分章' },
    ])
    const fallback = chapterOptions({ nodes: [node('x', 'x', { chapterId: 'chZ' })], edges: [] })
    expect(fallback).toEqual([{ value: { kind: 'chapter', id: 'chZ' }, label: 'chZ' }])
  })
})

// ---------- 组合式 ----------

describe('H05 useGraphFilters', () => {
  it('source 为 null 时 visible 为 null；到达后按条件筛选', async () => {
    const source = shallowRef<GraphCanvasData | null>(null)
    const f = useGraphFilters(source)
    expect(f.visible.value).toBeNull()
    expect(f.summary.value).toBeNull()
    source.value = sample()
    await nextTick()
    expect(ids(f.visible.value)).toEqual(ids(sample()))
    expect(f.summary.value).toEqual({ nodes: 7, totalNodes: 7, edges: 7, totalEdges: 7 })
  })

  it('清空恢复：多项筛选后 clear 回到完整图，保留选中与布局', () => {
    const f = useGraphFilters(sample())
    const full = f.visible.value
    expect(f.isDefault.value).toBe(true)
    f.select('stack')
    f.layout.value = 'force'
    f.state.value = state({
      query: '栈',
      relationTypes: ['PREREQUISITE'],
      nodeTypes: ['concept'],
      statuses: ['approved'],
      chapter: { kind: 'chapter', id: 'ch1' },
    })
    expect(f.isDefault.value).toBe(false)
    expect(ids(f.visible.value)).toEqual({ nodes: ['stack'], edges: [] })
    f.clear()
    expect(f.isDefault.value).toBe(true)
    expect(ids(f.visible.value)).toEqual(ids(full))
    expect(f.selected.value).toBe('stack')
    expect(f.layout.value).toBe('force')
    expect(f.summary.value).toEqual({ nodes: 7, totalNodes: 7, edges: 7, totalEdges: 7 })
  })

  it('clear 回到调用方给定的初始条件（如默认隐藏驳回项）', () => {
    const f = useGraphFilters(sample(), { initial: { statuses: ['draft', 'low_confidence', 'approved'] } })
    expect(ids(f.visible.value).nodes).not.toContain('heap')
    expect(f.isDefault.value).toBe(true)
    f.state.value = state()
    expect(f.isDefault.value).toBe(false)
    f.clear()
    expect(ids(f.visible.value).nodes).not.toContain('heap')
  })

  it('clear 之后修改条件不会改到保存的初始条件', () => {
    const f = useGraphFilters(sample())
    f.clear()
    f.state.value.relationTypes.splice(0)
    f.clear()
    expect(f.state.value.relationTypes).toHaveLength(4)
  })

  it('切换布局不丢选中态，也不改可见集合', () => {
    const f = useGraphFilters(sample())
    f.select('bst')
    const before = f.visible.value
    f.layout.value = 'force'
    expect(f.selected.value).toBe('bst')
    expect(f.visible.value).toBe(before)
    f.layout.value = 'hierarchical'
    expect(f.selected.value).toBe('bst')
    expect(f.visible.value!.nodes.find((n) => n.data.kpId === 'bst')!.states).toContain('selected')
  })

  it('筛选隐藏选中节点时保留选中并报告 selectedHidden，清空后恢复高亮', () => {
    const f = useGraphFilters(sample())
    f.select('avl')
    expect(f.selectedHidden.value).toBe(false)
    f.state.value = state({ chapter: { kind: 'chapter', id: 'ch1' } })
    expect(f.selected.value).toBe('avl')
    expect(f.selectedHidden.value).toBe(true)
    f.clear()
    expect(f.selectedHidden.value).toBe(false)
    expect(f.visible.value!.nodes.find((n) => n.data.kpId === 'avl')!.states).toEqual(['selected'])
  })

  it('新图中已没有选中的知识点时清除选中；仍在则保留', async () => {
    const source = shallowRef<GraphCanvasData | null>(sample())
    const f = useGraphFilters(source)
    f.select('bst')
    source.value = { nodes: sample().nodes.filter((n) => n.data.kpId !== 'avl'), edges: [] }
    await nextTick()
    expect(f.selected.value).toBe('bst')
    source.value = { nodes: [node('stack', '栈')], edges: [] }
    await nextTick()
    expect(f.selected.value).toBeNull()
  })

  it('toggleRelationType 切换单个关系类型', () => {
    const f = useGraphFilters(sample())
    f.toggleRelationType('RELATED_TO')
    expect(f.state.value.relationTypes).not.toContain('RELATED_TO')
    expect(ids(f.visible.value).edges).toEqual(['e1', 'e2', 'e3', 'e5', 'e6'])
    f.toggleRelationType('RELATED_TO')
    expect(ids(f.visible.value).edges).toEqual(ids(sample()).edges)
  })
})

// ---------- 画布布局参数（H04 扩展） ----------

describe('H05 布局参数', () => {
  it('层次布局用 antv-dagre，力导向用 d3-force', () => {
    expect(layoutOptions('hierarchical')).toMatchObject({ type: 'antv-dagre' })
    expect(layoutOptions('force')).toMatchObject({ type: 'd3-force' })
    const el = document.createElement('div')
    const data = sample()
    expect(buildGraphOptions({ container: el, width: 1, height: 1, data }).layout).toEqual(layoutOptions('hierarchical'))
    expect(buildGraphOptions({ container: el, width: 1, height: 1, data, layout: 'force' }).layout).toEqual(layoutOptions('force'))
  })

  it('节点与边定义了选中、驳回、低置信度三种状态样式', () => {
    const el = document.createElement('div')
    const options = buildGraphOptions({ container: el, width: 1, height: 1, data: sample() })
    expect(Object.keys(options.node?.state ?? {}).sort()).toEqual(['lowConfidence', 'rejected', 'selected'])
    expect(Object.keys(options.edge?.state ?? {}).sort()).toEqual(['lowConfidence', 'rejected'])
  })
})

// ---------- 生命周期替身 ----------

class FakeGraph implements CanvasGraph {
  destroyed = false
  calls: string[] = []
  data: GraphCanvasData
  layoutConfig: unknown
  handlers = new Map<string, Array<(event: { target?: { id?: string } }) => void>>()
  holdLayout = false
  releaseLayout: (() => void) | null = null

  constructor(readonly init: CanvasGraphInit) {
    this.data = init.data
    this.layoutConfig = layoutOptions(init.layout ?? 'hierarchical')
  }
  render(): Promise<void> {
    this.calls.push('render')
    return Promise.resolve()
  }
  setData(data: GraphCanvasData): void {
    this.calls.push('setData')
    this.data = data
  }
  setSize(): void {
    this.calls.push('setSize')
  }
  fitView(): Promise<void> {
    this.calls.push('fitView')
    return Promise.resolve()
  }
  setLayout(layout: unknown): void {
    this.calls.push(`setLayout ${(layout as { type: string }).type}`)
    this.layoutConfig = layout
  }
  layout(): Promise<void> {
    this.calls.push('layout')
    if (!this.holdLayout) return Promise.resolve()
    return new Promise((resolve) => {
      this.releaseLayout = resolve
    })
  }
  on(event: string, handler: (event: { target?: { id?: string } }) => void): this {
    this.handlers.set(event, [...(this.handlers.get(event) ?? []), handler])
    return this
  }
  destroy(): void {
    this.calls.push('destroy')
    this.destroyed = true
  }
  click(id: string): void {
    for (const handler of this.handlers.get('node:click') ?? []) handler({ target: { id } })
  }
}

function fakeFactory(): { factory: CanvasGraphFactory; graphs: FakeGraph[]; hold: boolean; release: () => void } {
  const waiting: Array<() => void> = []
  const control = {
    graphs: [] as FakeGraph[],
    hold: false,
    release() {
      while (waiting.length > 0) waiting.shift()!()
    },
    factory: ((init: CanvasGraphInit) => {
      const make = () => {
        const g = new FakeGraph(init)
        control.graphs.push(g)
        return g
      }
      if (!control.hold) return make()
      return new Promise<CanvasGraph>((resolve) => waiting.push(() => resolve(make())))
    }) as CanvasGraphFactory,
  }
  return control
}

async function settle(): Promise<void> {
  for (let i = 0; i < 10; i += 1) await Promise.resolve()
  await new Promise((resolve) => setTimeout(resolve, 0))
}

function box(width = 800, height = 600): HTMLElement {
  const el = document.createElement('div')
  Object.defineProperty(el, 'clientWidth', { configurable: true, value: width })
  Object.defineProperty(el, 'clientHeight', { configurable: true, value: height })
  return el
}

class NoopResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', NoopResizeObserver)
  vi.stubGlobal('requestAnimationFrame', () => 0)
  vi.stubGlobal('cancelAnimationFrame', () => undefined)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('H05 生命周期布局切换', () => {
  it('建图时把布局交给工厂', async () => {
    const f = fakeFactory()
    createGraphLifecycle(box(), { data: sample(), factory: f.factory, layout: 'force' })
    await settle()
    expect(f.graphs[0]!.init.layout).toBe('force')
  })

  it('setLayout 在原图上重新布局并适应视口，不重建、不重设数据', async () => {
    const f = fakeFactory()
    const data = filterGraph(sample(), defaultFilterState(), 'stack')
    const life = createGraphLifecycle(box(), { data, factory: f.factory })
    await settle()
    life.setLayout('force')
    await settle()
    expect(f.graphs).toHaveLength(1)
    expect(f.graphs[0]!.calls).toEqual(['render', 'setLayout d3-force', 'layout', 'fitView'])
    expect(f.graphs[0]!.data.nodes.find((n) => n.data.kpId === 'stack')!.states).toEqual(['selected'])
    expect(life.status).toBe('ready')
  })

  it('布局相同时不动；销毁后忽略', async () => {
    const f = fakeFactory()
    const life = createGraphLifecycle(box(), { data: sample(), factory: f.factory })
    await settle()
    life.setLayout('hierarchical')
    await settle()
    expect(f.graphs[0]!.calls).toEqual(['render'])
    life.destroy()
    life.setLayout('force')
    await settle()
    expect(f.graphs[0]!.calls).toEqual(['render', 'destroy'])
  })

  it('G6 加载中切换布局：建好后补做一次重新布局', async () => {
    const f = fakeFactory()
    f.hold = true
    const life = createGraphLifecycle(box(), { data: sample(), factory: f.factory })
    await settle()
    life.setLayout('force')
    f.release()
    await settle()
    expect(f.graphs[0]!.init.layout).toBe('hierarchical')
    expect(f.graphs[0]!.calls).toEqual(['render', 'setLayout d3-force', 'layout', 'fitView'])
  })

  it('尚未建图（零尺寸）时切换，直接按新布局建图', async () => {
    const f = fakeFactory()
    const el = box(0, 0)
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      callback(0)
      return 1
    })
    const life = createGraphLifecycle(el, { data: sample(), factory: f.factory })
    life.setLayout('force')
    await settle()
    expect(f.graphs).toHaveLength(0)
    Object.defineProperty(el, 'clientWidth', { configurable: true, value: 640 })
    Object.defineProperty(el, 'clientHeight', { configurable: true, value: 480 })
    life.refreshSize()
    await settle()
    expect(f.graphs).toHaveLength(1)
    expect(f.graphs[0]!.init.layout).toBe('force')
    expect(f.graphs[0]!.calls).toEqual(['render'])
  })

  it('连续切换只停在最后一次布局', async () => {
    const f = fakeFactory()
    const life = createGraphLifecycle(box(), { data: sample(), factory: f.factory })
    await settle()
    f.graphs[0]!.holdLayout = true
    life.setLayout('force')
    await settle()
    life.setLayout('hierarchical')
    life.setLayout('force')
    life.setLayout('hierarchical')
    f.graphs[0]!.holdLayout = false
    f.graphs[0]!.releaseLayout!()
    await settle()
    expect(f.graphs[0]!.calls).toEqual([
      'render',
      'setLayout d3-force',
      'layout',
      'fitView',
      'setLayout antv-dagre',
      'layout',
      'fitView',
    ])
  })

  it('交给 G6 的节点与边保留状态标记的副本', async () => {
    const f = fakeFactory()
    const data = filterGraph(sample(), defaultFilterState(), 'queue')
    const life = createGraphLifecycle(box(), { data, factory: f.factory })
    await settle()
    const drawn = f.graphs[0]!.data
    const queue = drawn.nodes.find((n) => n.data.kpId === 'queue')!
    expect(queue.states).toEqual(['lowConfidence', 'selected'])
    expect(queue.states).not.toBe(data.nodes.find((n) => n.data.kpId === 'queue')!.states)
    expect(drawn.edges.find((e) => e.data.relationId === 'e6')!.states).toEqual(['rejected'])
    life.update(sample())
    await settle()
    expect(f.graphs[0]!.data.nodes.every((n) => n.states === undefined)).toBe(true)
  })
})

// ---------- 工具栏 ----------

function mountToolbar(props: Partial<InstanceType<typeof GraphToolbar>['$props']> = {}) {
  return mount(GraphToolbar, {
    props: {
      modelValue: defaultFilterState(),
      layout: 'hierarchical',
      chapters: chapterOptions(sample(), [
        { id: 'ch1', title: '线性表', order: 1 },
        { id: 'ch2', title: '树', order: 2 },
      ]),
      summary: { nodes: 7, totalNodes: 7, edges: 7, totalEdges: 7 },
      canClear: false,
      ...props,
    },
  })
}

function lastModel(wrapper: ReturnType<typeof mountToolbar>): GraphFilterState {
  const events = wrapper.emitted('update:modelValue') as GraphFilterState[][]
  return events.at(-1)![0]!
}

describe('H05 GraphToolbar', () => {
  it('关系图例列出四类关系的中文名、颜色与线型，并可逐类勾选', () => {
    const w = mountToolbar()
    const legend = w.get('[data-test="relation-legend"]')
    for (const type of RELATION_TYPES) {
      const item = legend.get(`[data-relation="${type}"]`)
      expect(item.text()).toContain(RELATION_STYLES[type].label)
      const input = item.get('input[type="checkbox"]')
      expect((input.element as HTMLInputElement).checked).toBe(true)
      const line = item.get('line')
      expect(line.attributes('stroke')).toBe(RELATION_STYLES[type].stroke)
      expect(line.attributes('stroke-dasharray') ?? '').toBe(RELATION_STYLES[type].lineDash.join(' '))
      expect(item.find('[data-test="arrow"]').exists()).toBe(RELATION_STYLES[type].directed)
    }
  })

  it('取消勾选一类关系发出新的筛选条件，不改动 props', async () => {
    const model = defaultFilterState()
    const w = mountToolbar({ modelValue: model })
    await w.get('[data-relation="PREREQUISITE"] input').setValue(false)
    expect(lastModel(w).relationTypes).toEqual(['CONTAINS', 'RELATED_TO', 'EXAMPLE_OF'])
    expect(model.relationTypes).toHaveLength(4)
  })

  it('搜索框输入发出查询词', async () => {
    const w = mountToolbar()
    const input = w.get('input[type="search"]')
    expect(input.attributes('aria-label')).toBe('搜索知识点')
    await input.setValue('栈')
    expect(lastModel(w).query).toBe('栈')
  })

  it('知识点类型、审核状态与章节可筛选', async () => {
    const w = mountToolbar()
    await w.get('[data-node-type="example"] input').setValue(false)
    expect(lastModel(w).nodeTypes).not.toContain('example')
    await w.get('[data-status="rejected"] input').setValue(false)
    expect(lastModel(w).statuses).toEqual(['draft', 'low_confidence', 'approved'])
    const select = w.get('select')
    const labels = select.findAll('option').map((o) => o.text())
    expect(labels).toEqual(['全部章节', '线性表', '树', '未分章'])
    await select.setValue(select.findAll('option')[2]!.element.value)
    expect(lastModel(w).chapter).toEqual({ kind: 'chapter', id: 'ch2' })
    await select.setValue(select.findAll('option')[3]!.element.value)
    expect(lastModel(w).chapter).toEqual({ kind: 'none' })
  })

  it('状态图例说明驳回与低置信度的样式', () => {
    const w = mountToolbar()
    expect(w.get('[data-status="rejected"]').text()).toContain('已驳回')
    expect(w.get('[data-status="low_confidence"]').text()).toContain('低置信度')
    expect(w.find('[data-status="rejected"] [data-test="swatch"]').classes()).toContain('graph-toolbar__node-swatch--rejected')
  })

  it('布局切换为单选组，发出 update:layout', async () => {
    const w = mountToolbar()
    const group = w.get('[role="radiogroup"]')
    expect(group.attributes('aria-label')).toBe('布局')
    const radios = group.findAll('input[type="radio"]')
    expect(radios.map((r) => (r.element as HTMLInputElement).checked)).toEqual([true, false])
    await radios[1]!.setValue(true)
    expect(w.emitted('update:layout')).toEqual([['force']])
  })

  it('清空按钮在默认条件下禁用，可用时发出 clear', async () => {
    const w = mountToolbar()
    expect(w.get('[data-test="clear"]').attributes('disabled')).toBeDefined()
    await w.setProps({ canClear: true })
    await w.get('[data-test="clear"]').trigger('click')
    expect(w.emitted('clear')).toHaveLength(1)
  })

  it('显示可见数量；选中项被隐藏或无匹配时提示', async () => {
    const w = mountToolbar({ summary: { nodes: 2, totalNodes: 7, edges: 1, totalEdges: 7 } })
    const status = w.get('[data-test="summary"]')
    expect(status.attributes('aria-live')).toBe('polite')
    expect(status.text()).toContain('2 / 7 个知识点')
    expect(status.text()).toContain('1 / 7 条关系')
    await w.setProps({ selectedHidden: true })
    expect(status.text()).toContain('选中的知识点已被筛选隐藏')
    await w.setProps({ summary: { nodes: 0, totalNodes: 7, edges: 0, totalEdges: 7 } })
    expect(status.text()).toContain('没有符合条件的知识点')
  })
})

// ---------- 端到端：工具栏 + 筛选 + 画布 ----------

describe('H05 工具栏、筛选与画布联动', () => {
  function harness(f: ReturnType<typeof fakeFactory>) {
    const Page = defineComponent({
      setup() {
        const source = shallowRef<GraphCanvasData | null>(sample())
        const { state, layout, selected, visible, summary, isDefault, selectedHidden, clear, select } =
          useGraphFilters(source)
        const chapters = chapterOptions(sample())
        const clicks = ref<string[]>([])
        return () =>
          h('div', [
            h(GraphToolbar, {
              modelValue: state.value,
              'onUpdate:modelValue': (next: GraphFilterState) => (state.value = next),
              layout: layout.value,
              'onUpdate:layout': (next: 'hierarchical' | 'force') => (layout.value = next),
              chapters,
              summary: summary.value,
              canClear: !isDefault.value,
              selectedHidden: selectedHidden.value,
              onClear: clear,
            }),
            h(GraphCanvas, {
              graph: visible.value,
              layout: layout.value,
              onNodeClick: (kpId: string) => {
                clicks.value.push(kpId)
                select(kpId)
              },
            }),
            h('output', { 'data-test': 'selected' }, selected.value ?? ''),
          ])
      },
    })
    return mount(Page, { attachTo: document.body, global: { provide: { [GRAPH_FACTORY_KEY as symbol]: f.factory } } })
  }

  beforeEach(() => {
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, get: () => 800 })
    Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, get: () => 600 })
  })

  afterEach(() => {
    delete (HTMLElement.prototype as { clientWidth?: number }).clientWidth
    delete (HTMLElement.prototype as { clientHeight?: number }).clientHeight
  })

  it('点击选中后切换力导向再切回层次，画布上的选中态一直在，数据不重设', async () => {
    const f = fakeFactory()
    const w = harness(f)
    await settle()
    const g = f.graphs[0]!
    g.click(nodeElementId('bst'))
    await settle()
    expect(w.get('[data-test="selected"]').text()).toBe('bst')
    const selectedOn = () => g.data.nodes.filter((n) => n.states?.includes('selected')).map((n) => n.data.kpId)
    expect(selectedOn()).toEqual(['bst'])
    const callsBeforeSwitch = g.calls.length

    const radios = w.findAll('[role="radiogroup"] input')
    await radios[1]!.setValue(true)
    await settle()
    expect(g.layoutConfig).toMatchObject({ type: 'd3-force' })
    await w.findAll('[role="radiogroup"] input')[0]!.setValue(true)
    await settle()
    expect(g.layoutConfig).toMatchObject({ type: 'antv-dagre' })

    expect(f.graphs).toHaveLength(1)
    expect(w.get('[data-test="selected"]').text()).toBe('bst')
    expect(selectedOn()).toEqual(['bst'])
    expect(g.calls.slice(callsBeforeSwitch)).toEqual([
      'setLayout d3-force',
      'layout',
      'fitView',
      'setLayout antv-dagre',
      'layout',
      'fitView',
    ])
  })

  it('经工具栏筛选后画布上无悬空边，清空后恢复完整图', async () => {
    const f = fakeFactory()
    const w = harness(f)
    await settle()
    const g = f.graphs[0]!
    await w.get('[data-node-type="concept"] input').setValue(false)
    await settle()
    expect(ids(g.data).nodes).toEqual(['avl', 'bst', 'bracket', 'heap'])
    expectNoDangling(g.data)
    await w.get('input[type="search"]').setValue('树')
    await settle()
    expect(ids(g.data)).toEqual({ nodes: ['avl', 'bst'], edges: ['e3'] })
    await w.get('[data-test="clear"]').trigger('click')
    await settle()
    expect(ids(g.data)).toEqual(ids(sample()))
    expect(w.get('[data-test="clear"]').attributes('disabled')).toBeDefined()
    expect((w.get('input[type="search"]').element as HTMLInputElement).value).toBe('')
  })
})
