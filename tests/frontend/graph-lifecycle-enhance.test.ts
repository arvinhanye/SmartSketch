import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Positions } from '../../src/frontend/src/graph/chapterLayout'
import {
  buildGraphOptions,
  createGraphLifecycle,
  type CanvasEdge,
  type CanvasGraphFactory,
  type CanvasNode,
  type GraphCanvasData,
  type GraphLifecycleOptions,
} from '../../src/frontend/src/graph/lifecycle'
import { GRAPH_COLORS } from '../../src/frontend/src/graph/theme'
import { FakeEnhancedGraph } from './fakeEnhancedGraph'

function kp(id: string, chapterId: string, states?: CanvasNode['states']): CanvasNode {
  return {
    id: `kp:${id}`,
    data: { kpId: id, name: `知识点${id}`, type: 'concept', level: 1, chapterId, status: 'approved', confidence: 1, source: 'ai', locked: false },
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
const sample = (): GraphCanvasData => ({ nodes: [kp('a', 'c1'), kp('b', 'c2')], edges: [edge] })
const positions: Positions = new Map([
  ['a', { x: 10, y: 20 }],
  ['b', { x: 300, y: 400 }],
])
const measure = (text: string, px: number) => text.length * px

function box(width = 800, height = 600): HTMLElement {
  const el = document.createElement('div')
  Object.defineProperty(el, 'clientWidth', { configurable: true, value: width })
  Object.defineProperty(el, 'clientHeight', { configurable: true, value: height })
  return el
}
const resize = (el: HTMLElement, width: number, height = 600) => {
  Object.defineProperty(el, 'clientWidth', { configurable: true, value: width })
  Object.defineProperty(el, 'clientHeight', { configurable: true, value: height })
}

class FakeResizeObserver {
  static instances: FakeResizeObserver[] = []
  disconnected = false
  constructor(readonly callback: () => void) {
    FakeResizeObserver.instances.push(this)
  }
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {
    this.disconnected = true
  }
}

let frames: Array<() => void> = []
const flushFrames = () => {
  const run = frames
  frames = []
  run.forEach((fn) => fn())
}
async function settle(): Promise<void> {
  for (let i = 0; i < 10; i += 1) await Promise.resolve()
  await new Promise((resolve) => setTimeout(resolve, 5))
}

function make() {
  const graphs: FakeEnhancedGraph[] = []
  const factory: CanvasGraphFactory = (init) => {
    const g = new FakeEnhancedGraph({}, init)
    graphs.push(g)
    return g
  }
  return { graphs, factory }
}

beforeEach(() => {
  FakeResizeObserver.instances = []
  frames = []
  vi.stubGlobal('ResizeObserver', FakeResizeObserver)
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    frames.push(() => callback(0))
    return frames.length
  })
  vi.stubGlobal('cancelAnimationFrame', () => undefined)
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

const enhance = { measure, labelDelayMs: 0 }
function start(over: Partial<GraphLifecycleOptions> = {}, el = box()) {
  const m = make()
  const life = createGraphLifecycle(el, { data: sample(), factory: m.factory, enhance, ...over })
  return { ...m, life, el }
}

describe('章节布局位置', () => {
  it('位置随建图传给工厂，节点数据带坐标，G6 不再自己布局', async () => {
    const { graphs } = start({ positions })
    await settle()
    const init = graphs[0]!.init!
    expect(init.positions).toBe(positions)
    expect(init.data.nodes.map((n) => n.style)).toEqual([{ x: 10, y: 20 }, { x: 300, y: 400 }])
    const options = buildGraphOptions({ ...init, container: document.createElement('div') }) as unknown as { layout?: unknown; edge: { type?: string } }
    expect(options.layout).toBeUndefined()
    expect(options.edge.type).toBe('cubic-vertical')
  })
  it('力导向布局忽略位置，仍由 G6 布局', async () => {
    const { graphs } = start({ positions, layout: 'force' })
    await settle()
    const init = graphs[0]!.init!
    expect(init.positions).toBeNull()
    expect(init.data.nodes.every((n) => n.style === undefined)).toBe(true)
    const options = buildGraphOptions({ ...init, container: document.createElement('div') }) as unknown as { layout?: { type: string }; edge: { type?: string } }
    expect(options.layout?.type).toBe('d3-force')
    expect(options.edge.type).toBeUndefined()
  })
  it('更新数据后新节点同样带上坐标', async () => {
    const { graphs, life } = start({ positions })
    await settle()
    life.update({ nodes: [kp('b', 'c2')], edges: [] })
    await settle()
    const data = graphs[0]!.data as GraphCanvasData
    expect(data.nodes.map((n) => n.style)).toEqual([{ x: 300, y: 400 }])
  })
  it('不给位置、不开增强时与 H04 完全一致：数据没有坐标与展示字段', async () => {
    const m = make()
    createGraphLifecycle(box(), { data: sample(), factory: m.factory })
    await settle()
    const init = m.graphs[0]!.init!
    expect(init.positions).toBeNull()
    expect(init.minimap).toBeUndefined()
    expect(init.data.nodes[0]).not.toHaveProperty('style')
    expect(init.data.nodes[0]!.data).not.toHaveProperty('k')
  })
})

describe('增强模式的数据与事件', () => {
  it('数据带展示字段（标签放大 1、全部显示、掌握角标）', async () => {
    const m = make()
    createGraphLifecycle(box(), { data: { nodes: [kp('a', 'c1', ['mastered']), kp('b', 'c2')], edges: [edge] }, factory: m.factory, enhance })
    await settle()
    const [a] = m.graphs[0]!.init!.data.nodes
    expect(a!.data).toMatchObject({ k: 1, nk: 1, labelOn: true, mastery: 'mastered' })
    expect(m.graphs[0]!.init!.data.edges[0]!.data).toMatchObject({ cross: true, showLabel: false })
  })
  it('渲染后上报缩放；点击空白处通知页面', async () => {
    const zooms: number[] = []
    const onBlankClick = vi.fn()
    const { graphs } = start({ onZoom: (z) => zooms.push(z), enhance: { ...enhance, onBlankClick } })
    await settle()
    expect(zooms.at(-1)).toBe(1)
    graphs[0]!.emit('canvas:click')
    expect(onBlankClick).toHaveBeenCalledTimes(1)
  })
  it('小地图：容器与着色回调传给工厂', async () => {
    const mini = document.createElement('div')
    const m = make()
    createGraphLifecycle(box(), { data: { nodes: [kp('a', 'c1', ['selected']), kp('b', 'c2', ['mastered'])], edges: [] }, factory: m.factory, enhance: { ...enhance, minimap: mini } })
    await settle()
    const init = m.graphs[0]!.init!
    expect(init.minimap?.container).toBe(mini)
    expect(init.minimap?.color('kp:a')).toBe(GRAPH_COLORS.accent)
    expect(init.minimap?.color('kp:b')).toBe(GRAPH_COLORS.ok)
    const options = buildGraphOptions({ ...init, container: document.createElement('div') }) as unknown as { plugins: Array<Record<string, unknown>> }
    expect(options.plugins[0]).toMatchObject({ type: 'minimap', key: 'minimap', container: mini, size: [180, 120] })
  })
})

describe('容器尺寸变化策略（增强模式）', () => {
  it('面板开合（ResizeObserver）只 setSize，不整图重新适配；窗口缩放与 refreshSize 才重新适配', async () => {
    const { graphs, life, el } = start()
    await settle()
    const g = graphs[0]!
    g.calls.length = 0

    resize(el, 500)
    FakeResizeObserver.instances[0]!.callback()
    flushFrames()
    await settle()
    expect(g.calls).toContain('setSize 500x600')
    expect(g.calls).not.toContain('fitView')

    g.calls.length = 0
    resize(el, 600)
    window.dispatchEvent(new Event('resize'))
    FakeResizeObserver.instances[0]!.callback()
    flushFrames()
    await settle()
    expect(g.calls).toContain('fitView')

    // 窗口缩放之后的下一次面板开合又回到「只 setSize」
    g.calls.length = 0
    resize(el, 700)
    FakeResizeObserver.instances[0]!.callback()
    flushFrames()
    await settle()
    expect(g.calls).not.toContain('fitView')

    g.calls.length = 0
    resize(el, 650)
    life.refreshSize()
    flushFrames()
    await settle()
    expect(g.calls).toContain('fitView')
  })
  it('未开增强时每次尺寸变化都重新适配（H04 行为不变）', async () => {
    const m = make()
    const el = box()
    createGraphLifecycle(el, { data: sample(), factory: m.factory })
    await settle()
    m.graphs[0]!.calls.length = 0
    resize(el, 500)
    FakeResizeObserver.instances[0]!.callback()
    flushFrames()
    await settle()
    expect(m.graphs[0]!.calls).toContain('fitView')
  })
  it('销毁后移除窗口监听', async () => {
    const remove = vi.spyOn(window, 'removeEventListener')
    const { life } = start()
    await settle()
    life.destroy()
    expect(remove).toHaveBeenCalledWith('resize', expect.any(Function))
  })
})

describe('增强模式的视口方法', () => {
  it('fitTo 把一组知识点放进视口；zoomBy、ensureVisible 转发', async () => {
    const { graphs, life } = start({ positions })
    await settle()
    const g = graphs[0]!
    life.fitTo(['a', 'b'])
    life.zoomBy(2)
    await settle()
    expect(g.calls).toContain('translateBy')
    expect(g.calls).toContain('zoomBy 2')
    g.offset = [-5000, -5000]
    life.ensureVisible('a')
    await settle()
    expect(g.focusCalls.map(([id]) => id)).toEqual(['kp:a'])
  })
  it('setScope 在建图前后都能画出章节外框，null 只隐藏不移除', async () => {
    const { graphs, life } = start({ positions })
    life.setScope(['a'])
    await settle()
    flushFrames()
    expect(graphs[0]!.pluginsAdded).toHaveLength(1)
    life.setScope(null)
    await settle()
    expect(graphs[0]!.pluginUpdates.at(-1)).toMatchObject({ key: 'chapter-hull', visibility: 'hidden' })
    expect(graphs[0]!.pluginsAdded).toHaveLength(1)
  })
  it('未开增强时这些方法是空操作', async () => {
    const m = make()
    const life = createGraphLifecycle(box(), { data: sample(), factory: m.factory })
    await settle()
    life.fitTo(['a'])
    life.setScope(['a'])
    life.zoomBy(2)
    life.ensureVisible('a')
    life.relayoutLabels()
    life.leaveHover()
    await settle()
    expect(m.graphs[0]!.calls).toEqual(['render'])
  })
})

describe('销毁', () => {
  it('增强模式延后 400ms 销毁图实例（插件有延迟回调）；之后迟到的事件被忽略', async () => {
    const onBlankClick = vi.fn()
    const { graphs, life } = start({ enhance: { ...enhance, onBlankClick } })
    await settle()
    vi.useFakeTimers()
    life.destroy()
    expect(graphs[0]!.destroyed).toBe(false)
    graphs[0]!.emit('canvas:click')
    expect(onBlankClick).not.toHaveBeenCalled()
    vi.advanceTimersByTime(400)
    expect(graphs[0]!.destroyed).toBe(true)
  })
  it('未开增强时立即销毁', async () => {
    const m = make()
    const life = createGraphLifecycle(box(), { data: sample(), factory: m.factory })
    await settle()
    life.destroy()
    expect(m.graphs[0]!.destroyed).toBe(true)
  })
})

describe('首屏总览与径向布局的边', () => {
  /** 画布一开始处于很小的缩放：可读策略会把它放大到 READABLE_ZOOM；总览策略应改为整图适应 */
  function lowZoom() {
    const graphs: FakeEnhancedGraph[] = []
    const factory: CanvasGraphFactory = (init) => {
      const g = new FakeEnhancedGraph({}, init)
      g.zoom = 0.3
      graphs.push(g)
      return g
    }
    return { graphs, factory }
  }

  it('缺省（readable）：缩放过小时放大到可读缩放', async () => {
    const m = lowZoom()
    createGraphLifecycle(box(), { data: sample(), factory: m.factory, enhance, positions })
    await settle()
    expect(m.graphs[0]!.calls).toContain('zoomTo 0.9')
  })

  it('overview：首屏整图适应进视口，不再放大到可读缩放去聚焦入口节点', async () => {
    const m = lowZoom()
    createGraphLifecycle(box(), { data: sample(), factory: m.factory, enhance, positions, initialView: 'overview' })
    await settle()
    const calls = m.graphs[0]!.calls
    expect(calls).not.toContain('zoomTo 0.9')
    expect(calls).toContain('translateBy')
    expect(calls.some((c) => c.startsWith('zoomTo '))).toBe(true)
  })

  it('overview 下有待聚焦目标（搜索/跳转）时仍然聚焦目标', async () => {
    const m = lowZoom()
    const life = createGraphLifecycle(box(), { data: sample(), factory: m.factory, enhance, positions, initialView: 'overview' })
    life.focus('b')
    await settle()
    expect(m.graphs[0]!.calls).toContain('zoomTo 0.9')
  })

  it('overview 下定位到知识点：先放大到可读缩放再居中；可读模式的定位不改缩放', async () => {
    const m = lowZoom()
    const life = createGraphLifecycle(box(), { data: sample(), factory: m.factory, enhance, positions, initialView: 'overview' })
    await settle()
    const g = m.graphs[0]!
    g.calls.length = 0
    life.focus('b')
    await settle()
    expect(g.calls).toContain('zoomTo 0.9')
    const readable = lowZoom()
    const life2 = createGraphLifecycle(box(), { data: sample(), factory: readable.factory, enhance, positions })
    await settle()
    const g2 = readable.graphs[0]!
    g2.zoom = 0.3
    g2.calls.length = 0
    life2.focus('b')
    await settle()
    expect(g2.calls.some((c) => c.startsWith('zoomTo '))).toBe(false)
  })

  it('整组适应的留白可由页面收紧（教师页没有顶部浮层）', async () => {
    const wide = lowZoom()
    createGraphLifecycle(box(), { data: sample(), factory: wide.factory, enhance, positions, initialView: 'overview' })
    const tight = lowZoom()
    createGraphLifecycle(box(), { data: sample(), factory: tight.factory, enhance: { ...enhance, fitPads: { top: 0, left: 0, right: 0, bottom: 0 } }, positions, initialView: 'overview' })
    await settle()
    const zoomOf = (g: FakeEnhancedGraph) => Number(g.calls.filter((c) => c.startsWith('zoomTo ')).at(-1)!.split(' ')[1])
    expect(zoomOf(tight.graphs[0]!)).toBeGreaterThanOrEqual(zoomOf(wide.graphs[0]!))
  })

  it('径向布局给了位置时边画直线，层次布局仍是竖向曲线', async () => {
    const { graphs } = start({ positions, edgeStyle: 'straight' })
    await settle()
    const init = graphs[0]!.init!
    const options = buildGraphOptions({ ...init, container: document.createElement('div') }) as unknown as { edge: { type?: string } }
    expect(options.edge.type).toBe('line')
  })
})
