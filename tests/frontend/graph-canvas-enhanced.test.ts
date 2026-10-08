import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, ref, type Ref } from 'vue'
import GraphCanvas from '../../src/frontend/src/components/GraphCanvas.vue'
import type { Positions } from '../../src/frontend/src/graph/chapterLayout'
import {
  GRAPH_FACTORY_KEY,
  type CanvasEdge,
  type CanvasGraphFactory,
  type CanvasNode,
  type GraphCanvasData,
  type GraphLayoutName,
} from '../../src/frontend/src/graph/lifecycle'
import { FakeEnhancedGraph } from './fakeEnhancedGraph'

function kp(id: string, states?: CanvasNode['states']): CanvasNode {
  return {
    id: `kp:${id}`,
    data: { kpId: id, name: `知识点${id}`, type: 'concept', level: 1, chapterId: 'c1', status: 'approved', confidence: 1, source: 'ai', locked: false },
    ...(states === undefined ? {} : { states }),
  }
}
const edge: CanvasEdge = {
  id: 'rel:r1',
  source: 'kp:a',
  target: 'kp:b',
  data: { relationId: 'r1', type: 'PREREQUISITE', directed: true, status: 'approved', confidence: 1, source: 'ai', downgraded: false },
  style: { stroke: '#5145CD', lineWidth: 2, lineDash: [], endArrow: true, labelText: '前置' },
}
const sample = (): GraphCanvasData => ({ nodes: [kp('a', ['mastered']), kp('b')], edges: [edge] })
const positionsA: Positions = new Map([['a', { x: 0, y: 0 }], ['b', { x: 100, y: 100 }]])
const positionsB: Positions = new Map([['a', { x: 5, y: 5 }], ['b', { x: 50, y: 50 }]])

async function settle(): Promise<void> {
  for (let i = 0; i < 10; i += 1) await Promise.resolve()
  await new Promise((resolve) => setTimeout(resolve, 5))
}

/** jsdom 不排版：画布容器给 800×600，其他元素为 0 */
function sizeStages(): () => void {
  for (const [key, value] of [['clientWidth', 800], ['clientHeight', 600]] as const) {
    Object.defineProperty(HTMLElement.prototype, key, {
      configurable: true,
      get(this: HTMLElement) {
        return this.classList.contains('graph-canvas__stage') ? value : 0
      },
    })
  }
  return () => {
    for (const key of ['clientWidth', 'clientHeight']) delete (HTMLElement.prototype as unknown as Record<string, unknown>)[key]
  }
}

class NoopResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

function setup(props: { enhanced?: boolean | Ref<boolean>; positions?: Ref<Positions | null>; layout?: Ref<GraphLayoutName>; scope?: Ref<string[] | null> } = {}) {
  const graphs: FakeEnhancedGraph[] = []
  const factory: CanvasGraphFactory = (init) => {
    const g = new FakeEnhancedGraph({}, init)
    graphs.push(g)
    return g
  }
  const clicked: string[] = []
  const blank = vi.fn()
  const positions = props.positions ?? ref<Positions | null>(positionsA)
  const layout = props.layout ?? ref<GraphLayoutName>('hierarchical')
  const scope = props.scope ?? ref<string[] | null>(null)
  const Host = defineComponent({
    setup() {
      return () =>
        h(GraphCanvas, {
          graph: sample(),
          enhanced: typeof props.enhanced === 'object' ? props.enhanced.value : props.enhanced ?? true,
          positions: positions.value,
          layout: layout.value,
          scope: scope.value,
          onNodeClick: (id: string) => clicked.push(id),
          onBlankClick: blank,
        })
    },
  })
  const wrapper = mount(Host, { attachTo: document.body, global: { provide: { [GRAPH_FACTORY_KEY as symbol]: factory } } })
  return { wrapper, graphs, clicked, blank, positions, layout, scope }
}

let restoreSize: () => void
beforeEach(() => {
  restoreSize = sizeStages()
  vi.stubGlobal('ResizeObserver', NoopResizeObserver)
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
    cb(0)
    return 0
  })
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  restoreSize()
})

describe('GraphCanvas 增强模式', () => {
  it('章节布局失败的基础模式恢复后重建增强生命周期，控件可以缩放', async () => {
    const enhanced = ref(false), positions = ref<Positions|null>(null)
    const { wrapper, graphs } = setup({ enhanced, positions })
    await settle();expect(graphs).toHaveLength(1)
    enhanced.value = true;await settle()
    positions.value = positionsA;await settle()
    expect(graphs).toHaveLength(2)
    expect(graphs[1]!.init!.positions).toBe(positionsA)
    await wrapper.get('[aria-label="放大"]').trigger('click');await settle()
    expect(graphs[1]!.calls).toContain('zoomBy 1.25')
    enhanced.value=false;await settle();expect(graphs).toHaveLength(3)
    expect(wrapper.find('[aria-label="放大"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('位置还在计算（null）时只显示加载，不建图；位置到达后用同一份位置建图并带上小地图容器', async () => {
    const positions = ref<Positions | null>(null)
    const { wrapper, graphs } = setup({ positions })
    await settle()
    expect(graphs).toHaveLength(0)
    expect(wrapper.get('[role="status"]').text()).toContain('加载中')
    positions.value = positionsA
    await settle()
    expect(graphs).toHaveLength(1)
    expect(graphs[0]!.init!.positions).toBe(positionsA)
    expect(graphs[0]!.init!.minimap?.container).toBe(wrapper.get('.gw-mini').element)
    wrapper.unmount()
  })

  it('力导向布局不需要位置，直接建图', async () => {
    const { graphs, wrapper } = setup({ positions: ref<Positions | null>(null), layout: ref<GraphLayoutName>('force') })
    await settle()
    expect(graphs).toHaveLength(1)
    expect(graphs[0]!.init!.positions).toBeNull()
    wrapper.unmount()
  })

  it('地图与缩放控件：小地图开关、放大、缩小、适应画布都有可访问名称并转发给画布', async () => {
    const { wrapper, graphs } = setup()
    await settle()
    const group = wrapper.get('[role="group"][aria-label="地图与缩放"]')
    const names = group.findAll('button').map((b) => b.attributes('aria-label'))
    expect(names).toEqual(['收起小地图', '放大', '缩小', '适应画布'])
    await group.get('[aria-label="放大"]').trigger('click')
    await group.get('[aria-label="缩小"]').trigger('click')
    await group.get('[aria-label="适应画布"]').trigger('click')
    await settle()
    expect(graphs[0]!.calls).toContain('zoomBy 1.25')
    expect(graphs[0]!.calls).toContain('zoomBy 0.8')
    expect(graphs[0]!.calls).toContain('translateBy')
    await group.get('[aria-label="收起小地图"]').trigger('click')
    expect(group.get('[aria-pressed]').attributes('aria-pressed')).toBe('false')
    expect(wrapper.get('.gw-mini').isVisible()).toBe(false)
    wrapper.unmount()
  })

  it('点击节点与点击空白处分别向页面发事件', async () => {
    const { wrapper, graphs, clicked, blank } = setup()
    await settle()
    graphs[0]!.emit('node:click', { target: { id: 'kp:a' } })
    graphs[0]!.emit('canvas:click')
    expect(clicked).toEqual(['a'])
    expect(blank).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('位置变化（换版本重算）重建画布；增强模式切换布局同样重建', async () => {
    const positions = ref<Positions | null>(positionsA)
    const layout = ref<GraphLayoutName>('hierarchical')
    const { wrapper, graphs } = setup({ positions, layout })
    await settle()
    expect(graphs).toHaveLength(1)
    positions.value = positionsB
    await settle()
    expect(graphs).toHaveLength(2)
    expect(graphs[1]!.init!.positions).toBe(positionsB)
    layout.value = 'force'
    await settle()
    expect(graphs).toHaveLength(3)
    expect(graphs[2]!.init!.positions).toBeNull()
    wrapper.unmount()
  })

  it('位置重新计算（位置 → null）时拆掉旧画布并显示加载，新位置到了再重建，且回到最近一次聚焦的节点', async () => {
    const positions = ref<Positions | null>(positionsA)
    const { wrapper, graphs } = setup({ positions })
    await settle()
    wrapper.findComponent(GraphCanvas).vm.focus('b')
    await settle()
    positions.value = null
    await settle()
    expect(graphs).toHaveLength(1)
    expect(wrapper.get('[role="status"]').text()).toContain('加载中')
    positions.value = positionsB
    await settle()
    expect(graphs).toHaveLength(2)
    expect(graphs[1]!.calls.filter((c) => c === 'render')).toHaveLength(1)
    expect(graphs[1]!.focusCalls.map(([id]) => id)).toContain('kp:b')
    wrapper.unmount()
  })

  it('章节外框成员（scope）变化时画出/隐藏外框', async () => {
    const scope = ref<string[] | null>(null)
    const { wrapper, graphs } = setup({ scope })
    await settle()
    scope.value = ['a', 'b']
    await settle()
    expect(graphs[0]!.pluginsAdded).toHaveLength(1)
    scope.value = null
    await settle()
    expect(graphs[0]!.pluginUpdates.at(-1)).toMatchObject({ key: 'chapter-hull', visibility: 'hidden' })
    wrapper.unmount()
  })

  it('悬停 300ms 后显示名称与掌握状态文字的 tooltip，移开即消失', async () => {
    const { wrapper, graphs } = setup()
    await settle()
    vi.useFakeTimers()
    graphs[0]!.emit('node:pointerenter', { target: { id: 'kp:a' }, pointerType: 'mouse', client: { x: 30, y: 40 } })
    vi.advanceTimersByTime(299)
    await nextTick()
    expect(wrapper.find('[role="tooltip"]').exists()).toBe(false)
    vi.advanceTimersByTime(2)
    await nextTick()
    expect(wrapper.get('[role="tooltip"]').text()).toBe('知识点a（已掌握）')
    graphs[0]!.emit('node:pointerleave')
    await nextTick()
    expect(wrapper.find('[role="tooltip"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('画布加载与错误状态沿用 H04：无障碍标签说明规模，带 data-zoom', async () => {
    const { wrapper } = setup()
    await settle()
    expect(wrapper.get('.graph-canvas__stage').attributes('aria-label')).toBe('课程知识图谱：2 个知识点，1 条关系')
    expect(wrapper.get('[data-test="graph-canvas"]').attributes('data-zoom')).toBe('1')
    wrapper.unmount()
  })
})

describe('GraphCanvas 普通模式（教师页沿用）', () => {
  it('没有地图控件与 tooltip，不用位置，行为与 H04 一致', async () => {
    const { wrapper, graphs } = setup({ enhanced: false })
    await settle()
    expect(graphs).toHaveLength(1)
    expect(graphs[0]!.init!.positions).toBeNull()
    expect(graphs[0]!.init!.minimap).toBeUndefined()
    expect(wrapper.find('.gw-map').exists()).toBe(false)
    wrapper.unmount()
  })
  it('切换布局在原图上进行，不重建', async () => {
    const layout = ref<GraphLayoutName>('hierarchical')
    const { wrapper, graphs } = setup({ enhanced: false, layout })
    await settle()
    layout.value = 'force'
    await settle()
    expect(graphs).toHaveLength(1)
    wrapper.unmount()
  })
})
