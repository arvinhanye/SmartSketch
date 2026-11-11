import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { G6EdgeData, G6NodeData } from '../../src/frontend/src/graph/adapter'
import { createEnhancer, type EnhanceOptions, zoomOf } from '../../src/frontend/src/graph/enhancer'
import type { CanvasEdge, CanvasElementState, CanvasNode } from '../../src/frontend/src/graph/lifecycle'
import { GRAPH_COLORS } from '../../src/frontend/src/graph/theme'
import { FakeEnhancedGraph as FakeGraph } from './fakeEnhancedGraph'

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

function kp(id: string, extra: Partial<G6NodeData> = {}): CanvasNode {
  return {
    id: `kp:${id}`,
    data: { kpId: id, name: `知识点${id}`, type: 'concept', level: 1, chapterId: 'c1', status: 'approved', confidence: 1, source: 'ai', locked: false, ...extra },
  }
}
/** 带状态的节点 */
function st(node: CanvasNode, ...states: CanvasElementState[]): CanvasNode {
  return { ...node, states }
}
function rel(id: string, from: string, to: string, type: G6EdgeData['type'] = 'PREREQUISITE'): CanvasEdge {
  return {
    id: `rel:${id}`,
    source: `kp:${from}`,
    target: `kp:${to}`,
    data: { relationId: id, type, directed: true, status: 'approved', confidence: 1, source: 'ai', downgraded: false },
    style: { stroke: '#5145CD', lineWidth: 2, lineDash: [], endArrow: true, labelText: '前置' },
  }
}

type Pos = Record<string, [number, number]>
const DEFAULT_POS: Pos = { 'kp:a': [100, 100], 'kp:b': [100, 100], 'kp:c': [600, 400] }

function setup(over: Partial<EnhanceOptions> = {}, pos: Pos = DEFAULT_POS, size: [number, number] = [800, 600]) {
  const graph = new FakeGraph(pos)
  const queue: Array<() => Promise<void>> = []
  const zooms: number[] = []
  let alive = true
  const enhancer = createEnhancer({
    graph: () => graph,
    size: () => size,
    enqueue: (task) => {
      queue.push(task)
    },
    alive: () => alive,
    onZoom: (zoom) => zooms.push(zoom),
    options: { measure: (text, px) => text.length * px, labelDelayMs: 0, ...over },
  })
  const drain = async () => {
    while (queue.length > 0) await queue.shift()!()
  }
  return {
    graph,
    enhancer,
    drain,
    zooms,
    kill: () => {
      alive = false
    },
  }
}

beforeEach(() => {
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    callback(0)
    return 0
  })
})
afterEach(() => vi.unstubAllGlobals())

describe('decorate', () => {
  it('返回装饰后的副本（标签放大 1、全部显示），不修改输入', () => {
    const { enhancer } = setup()
    const input = { nodes: [kp('a'), kp('b')], edges: [rel('r1', 'a', 'b')] }
    const out = enhancer.decorate(input)
    expect(out.nodes[0]!.data).toMatchObject({ k: 1, nk: 1, labelOn: true, mastery: 'unknown' })
    expect(out.edges[0]!.data).toMatchObject({ showLabel: false, cross: false })
    expect(input.nodes[0]!.data).not.toHaveProperty('k')
  })
  it('跨章边被识别并画 1px', () => {
    const { enhancer } = setup()
    const out = enhancer.decorate({ nodes: [kp('a'), kp('b', { chapterId: 'c2' })], edges: [rel('r1', 'a', 'b')] })
    expect(out.edges[0]!.data.cross).toBe(true)
    expect(out.edges[0]!.style.lineWidth).toBe(1)
  })
})

describe('语义缩放', () => {
  it('缩小到 0.2：标签放大 5 倍、节点与线宽有屏幕下限，随后重写元素状态', async () => {
    const { graph, enhancer, zooms } = setup()
    enhancer.decorate({ nodes: [kp('a'), kp('b')], edges: [rel('r1', 'a', 'b')] })
    graph.zoom = 0.2
    await enhancer.afterRender()
    expect(enhancer.view.labelK).toBe(5)
    expect(enhancer.view.floors.nodeK).toBeGreaterThan(1)
    expect(graph.nodeUpdates.at(-1)![0]!.data).toMatchObject({ k: 5 })
    expect(graph.edgeUpdates.at(-1)![0]!.data.lw).toBe(enhancer.view.floors.lwMin)
    expect(graph.calls).toContain('draw')
    expect(graph.stateCalls.length).toBe(1)
    expect(zooms.at(-1)).toBe(0.2)
  })
  it('缩放档位不变时不重绘（滚轮缩放不会每帧重绘）', async () => {
    const { graph, enhancer, drain } = setup()
    enhancer.decorate({ nodes: [kp('a')], edges: [] })
    enhancer.attach()
    await enhancer.afterRender()
    await sleep(10)
    await drain() // 先让首次标签排布落地，再量基线
    const draws = graph.calls.filter((c) => c === 'draw').length
    graph.emit('aftertransform')
    await sleep(10)
    await drain()
    expect(graph.calls.filter((c) => c === 'draw').length).toBe(draws)
  })
  it('zoomOf 读不到时返回 null（初始化或销毁中 getZoom 会抛）', () => {
    const g = new FakeGraph({})
    g.getZoom = () => {
      throw new Error('not ready')
    }
    expect(zoomOf(g)).toBeNull()
    expect(zoomOf(null)).toBeNull()
  })
})

describe('标签排布', () => {
  it('两个节点重叠时只保留优先级高的（搜索命中 > 普通）', async () => {
    const { graph, enhancer, drain } = setup()
    enhancer.decorate({ nodes: [st(kp('a'), 'match'), kp('b')], edges: [] })
    await enhancer.afterRender()
    await sleep(10)
    await drain()
    const last = new Map(graph.nodeUpdates.at(-1)!.map((n) => [n.id, n.data.labelOn]))
    expect(last.get('kp:a')).toBe(true)
    expect(last.get('kp:b')).toBe(false)
  })
  it('被预览/选中的节点强制显示，但落在浮层下面时仍不显示', async () => {
    const hard: Array<[number, number, number, number]> = [[0, 0, 400, 400]]
    const { graph, enhancer, drain } = setup({ obstacles: () => ({ hard, soft: [] }) })
    enhancer.decorate({ nodes: [st(kp('a'), 'selected'), kp('c')], edges: [] })
    await enhancer.afterRender()
    await sleep(10)
    await drain()
    const last = new Map(graph.nodeUpdates.at(-1)!.map((n) => [n.id, n.data.labelOn]))
    expect(last.get('kp:a')).toBe(false) // 在障碍物下
    expect(last.get('kp:c')).toBe(true)
  })
  it('浮层变化后 relayoutLabels 重新排布', async () => {
    let hard: Array<[number, number, number, number]> = []
    const { graph, enhancer, drain } = setup({ obstacles: () => ({ hard, soft: [] }) })
    enhancer.decorate({ nodes: [kp('a')], edges: [] })
    await enhancer.afterRender()
    await sleep(10)
    await drain()
    const before = graph.nodeUpdates.length
    hard = [[0, 0, 400, 400]]
    enhancer.relayoutLabels()
    await sleep(10)
    await drain()
    expect(graph.nodeUpdates.length).toBeGreaterThan(before)
    expect(graph.nodeUpdates.at(-1)![0]!.data.labelOn).toBe(false)
  })
})

describe('整组适应 fitTo', () => {
  it('把一组节点整体放进视口，且落在边距内', async () => {
    const pos: Pos = { 'kp:a': [0, 0], 'kp:b': [1600, 0], 'kp:c': [0, 1200] }
    const { graph, enhancer } = setup({}, pos)
    enhancer.decorate({ nodes: [kp('a'), kp('b'), kp('c')], edges: [] })
    await enhancer.fitTo()
    expect(graph.calls).toContain('translateBy')
    for (const id of Object.keys(pos)) {
      const [x, y] = graph.getViewportByCanvas(graph.getElementPosition(id))
      expect(x).toBeGreaterThanOrEqual(56)
      expect(x).toBeLessThanOrEqual(800 - 96)
      expect(y).toBeGreaterThanOrEqual(104)
      expect(y).toBeLessThanOrEqual(600 - 96)
    }
  })
  it('只适应指定的知识点；不在图中的忽略；缩放不超过 1.2', async () => {
    const pos: Pos = { 'kp:a': [0, 0], 'kp:b': [100, 0], 'kp:c': [5000, 5000] }
    const { graph, enhancer } = setup({}, pos)
    enhancer.decorate({ nodes: [kp('a'), kp('b'), kp('c')], edges: [] })
    await enhancer.fitTo(['a', 'b', 'nope'])
    expect(graph.zoom).toBeGreaterThan(1)
    expect(graph.zoom).toBeLessThanOrEqual(1.2)
  })
  it('没有可用节点时不动镜头', async () => {
    const { graph, enhancer } = setup()
    enhancer.decorate({ nodes: [], edges: [] })
    await enhancer.fitTo()
    expect(graph.calls).toEqual([])
  })
})

describe('ensureVisible / zoomBy', () => {
  it('节点在视口内不移动镜头，在视口外才聚焦；减少动效时关闭动画', async () => {
    const { graph, enhancer } = setup({ reduceMotion: () => true }, { 'kp:a': [100, 100], 'kp:c': [5000, 5000] })
    enhancer.decorate({ nodes: [kp('a'), kp('c')], edges: [] })
    await enhancer.ensureVisible('a')
    expect(graph.focusCalls).toEqual([])
    await enhancer.ensureVisible('c')
    expect(graph.focusCalls).toEqual([['kp:c', false]])
  })
  it('zoomBy 上报缩放', async () => {
    const { graph, enhancer, zooms } = setup()
    await enhancer.zoomBy(2)
    expect(graph.zoom).toBe(2)
    expect(zooms.at(-1)).toBe(2)
  })
})

describe('悬停强淡化（瞬时）', () => {
  const data = () => ({ nodes: [st(kp('a'), 'mastered'), kp('b'), kp('c')], edges: [rel('r1', 'a', 'b')] })
  const enter = (graph: FakeGraph, id = 'a') => graph.emit('node:pointerenter', { target: { id: `kp:${id}` }, pointerType: 'mouse', client: { x: 10, y: 20 } })
  function hoverSetup(over: Partial<EnhanceOptions> = {}) {
    const h = setup(over)
    h.graph.setData(h.enhancer.decorate(data()))
    h.enhancer.attach()
    return h
  }
  async function elapse(h: ReturnType<typeof hoverSetup>, ms: number) {
    await vi.advanceTimersByTimeAsync(ms)
    await h.drain()
  }

  beforeEach(() => vi.useFakeTimers())
  afterEach(() => {
    vi.clearAllTimers()
    vi.useRealTimers()
  })

  it('悬停节点与相邻保持清楚，其余退后；持久状态保留；移开 60ms 后恢复', async () => {
    const hovers: unknown[] = []
    const h = hoverSetup({ onHover: (info) => hovers.push(info) })
    enter(h.graph)
    // tooltip 的 300ms 计时仍从 pointerenter 开始，不叠加悬停淡化阈值。
    expect(hovers.at(-1)).toEqual({ kpId: 'a', clientX: 10, clientY: 20 })
    await elapse(h, 120)
    expect(h.graph.elementStates['kp:a']).toEqual(['mastered', 'hovered'])
    expect(h.graph.elementStates['kp:b']).toEqual(['hoverRelated'])
    expect(h.graph.elementStates['kp:c']).toEqual(['hoverFaded'])
    expect(h.graph.elementStates['rel:r1']).toEqual(['active'])
    h.graph.emit('node:pointerleave')
    expect(hovers.at(-1)).toBeNull()
    await elapse(h, 59)
    expect(h.graph.elementStates['kp:a']).toEqual(['mastered', 'hovered'])
    await elapse(h, 1)
    expect(h.graph.elementStates['kp:a']).toEqual(['mastered'])
    expect(h.graph.elementStates['kp:c']).toEqual([])
  })
  it('触屏没有悬停效果', async () => {
    const h = hoverSetup()
    h.graph.emit('node:pointerenter', { target: { id: 'kp:a' }, pointerType: 'touch' })
    await elapse(h, 180)
    expect(h.graph.stateCalls).toEqual([])
  })
  it('停留未满 120ms 不更新图谱，满阈值后才淡化', async () => {
    const h = hoverSetup()
    enter(h.graph)
    await elapse(h, 119)
    expect(h.graph.stateCalls).toEqual([])
    await elapse(h, 1)
    expect(h.graph.elementStates['kp:a']).toEqual(['mastered', 'hovered'])
    expect(h.graph.elementStates['kp:c']).toEqual(['hoverFaded'])
  })
  it('快速划过节点不会发出淡化或恢复状态写入', async () => {
    const h = hoverSetup()
    enter(h.graph)
    await elapse(h, 119)
    h.graph.emit('node:pointerleave')
    await elapse(h, 181)
    expect(h.graph.stateCalls).toEqual([])
    expect(h.graph.elementStates['kp:a']).toEqual(['mastered'])
  })
  it('快速移到相邻节点时不闪：进入新节点会取消恢复', async () => {
    const h = hoverSetup()
    enter(h.graph)
    await elapse(h, 120)
    const calls = h.graph.stateCalls.length
    h.graph.emit('node:pointerleave')
    await elapse(h, 30)
    enter(h.graph, 'b')
    await elapse(h, 90)
    expect(h.graph.stateCalls.slice(calls).some((state) => state['kp:c']?.length === 0)).toBe(false)
    await elapse(h, 30)
    expect(h.graph.elementStates['kp:b']).toEqual(['hovered'])
    expect(h.graph.elementStates['kp:c']).toEqual(['hoverFaded'])
  })
  it('相邻节点间转换仅发送真正变化的节点，不重发不变的边与背景节点', async () => {
    const h = hoverSetup()
    enter(h.graph)
    await elapse(h, 120)
    const calls = h.graph.stateCalls.length
    h.graph.emit('node:pointerleave')
    enter(h.graph, 'b')
    await elapse(h, 120)
    expect(h.graph.stateCalls.slice(calls)).toEqual([{
      'kp:a': ['mastered', 'hoverRelated'],
      'kp:b': ['hovered'],
    }])
    expect(h.graph.elementStates['kp:c']).toEqual(['hoverFaded'])
    expect(h.graph.elementStates['rel:r1']).toEqual(['active'])
  })
  it('同一节点的重复进入不重发状态，也不延后首次停留阈值', async () => {
    const h = hoverSetup()
    enter(h.graph)
    await elapse(h, 100)
    enter(h.graph)
    await elapse(h, 20)
    expect(h.graph.elementStates['kp:a']).toEqual(['mastered', 'hovered'])
    const calls = h.graph.stateCalls.length
    enter(h.graph)
    await elapse(h, 120)
    expect(h.graph.stateCalls).toHaveLength(calls)
  })
  it('兜底：画布空白处移动、进入边也结束悬停', async () => {
    const h = hoverSetup()
    for (const event of ['canvas:pointermove', 'edge:pointerenter']) {
      enter(h.graph)
      await elapse(h, 120)
      h.graph.emit(event)
      await elapse(h, 60)
      expect(h.graph.elementStates['kp:a']).toEqual(['mastered'])
    }
  })
  it('兜底：指针离开整个画布容器也结束悬停；没有悬停时是空操作', async () => {
    const h = hoverSetup()
    h.enhancer.leaveHover()
    expect(h.graph.stateCalls).toEqual([])
    enter(h.graph)
    await elapse(h, 120)
    h.enhancer.leaveHover()
    await elapse(h, 60)
    expect(h.graph.elementStates['kp:a']).toEqual(['mastered'])
  })
  it.each(['canvas:pointermove', 'edge:pointerenter', 'container:pointerleave'])('候选停留期间的 %s 也取消淡化计时', async (event) => {
    const hovers: unknown[] = []
    const h = hoverSetup({ onHover: (info) => hovers.push(info) })
    enter(h.graph)
    await elapse(h, 100)
    if (event === 'container:pointerleave') h.enhancer.leaveHover()
    else h.graph.emit(event)
    await elapse(h, 200)
    expect(h.graph.stateCalls).toEqual([])
    expect(hovers.at(-1)).toBeNull()
  })
  it('持续空白移动不会不断延后 60ms 恢复截止时间', async () => {
    const h = hoverSetup()
    enter(h.graph)
    await elapse(h, 120)
    h.graph.emit('canvas:pointermove')
    await elapse(h, 30)
    h.graph.emit('canvas:pointermove')
    await elapse(h, 30)
    expect(h.graph.elementStates['kp:a']).toEqual(['mastered'])
  })
  it('预览/选中的节点即使与悬停节点无关也保留外环', async () => {
    const h = hoverSetup()
    h.graph.setData(h.enhancer.decorate({ nodes: [kp('a'), st(kp('c'), 'selected')], edges: [] }))
    enter(h.graph)
    await elapse(h, 120)
    expect(h.graph.elementStates['kp:c']).toEqual(['selected'])
  })
  it('预览更新触发 setData/render 后恢复悬停，移开保留最新选中与学习状态', async () => {
    const h = hoverSetup()
    await h.enhancer.afterRender()
    await elapse(h, 0)
    enter(h.graph)
    await elapse(h, 120)
    h.graph.setData(h.enhancer.decorate({
      nodes: [st(kp('a'), 'learning', 'dimmed'), st(kp('b'), 'dimmed'), st(kp('c'), 'selected', 'mastered')],
      edges: [rel('r1', 'a', 'b')],
    }))
    await h.graph.render()
    await h.enhancer.afterRender()
    await h.drain()
    expect(h.graph.elementStates['kp:a']).toEqual(['learning', 'dimmed', 'hovered'])
    expect(h.graph.elementStates['kp:c']).toEqual(['selected', 'mastered'])
    h.enhancer.leaveHover()
    await elapse(h, 60)
    expect(h.graph.elementStates['kp:a']).toEqual(['learning', 'dimmed'])
    expect(h.graph.elementStates['kp:b']).toEqual(['dimmed'])
    expect(h.graph.elementStates['kp:c']).toEqual(['selected', 'mastered'])
  })
  it('语义缩放重绘后保留悬停，后续差分仍能恢复全部状态', async () => {
    const h = hoverSetup()
    enter(h.graph)
    await elapse(h, 120)
    h.graph.zoom = 0.2
    h.graph.emit('aftertransform')
    await h.drain()
    expect(h.graph.calls).toContain('draw')
    expect(h.graph.elementStates['kp:a']).toEqual(['mastered', 'hovered'])
    expect(h.graph.elementStates['kp:c']).toEqual(['hoverFaded'])
    h.enhancer.leaveHover()
    await elapse(h, 60)
    expect(h.graph.elementStates).toEqual({ 'kp:a': ['mastered'], 'kp:b': [], 'kp:c': [], 'rel:r1': [] })
  })
  it('停留候选被新图数据移除后不再淡化剩余节点', async () => {
    const h = hoverSetup()
    enter(h.graph)
    await elapse(h, 100)
    h.graph.setData(h.enhancer.decorate({ nodes: [kp('b'), kp('c')], edges: [] }))
    await h.graph.render()
    await h.enhancer.afterRender()
    await elapse(h, 200)
    expect(h.graph.elementStates).toEqual({ 'kp:b': [], 'kp:c': [] })
    expect(h.graph.stateCalls.every((call) => !Object.hasOwn(call, 'kp:a'))).toBe(true)
  })
  it('已悬停节点被新图数据移除后清除瞬时淡化', async () => {
    const h = hoverSetup()
    enter(h.graph)
    await elapse(h, 120)
    h.graph.setData(h.enhancer.decorate({ nodes: [kp('b'), kp('c')], edges: [] }))
    await h.graph.render()
    await h.enhancer.afterRender()
    await elapse(h, 120)
    expect(h.graph.elementStates).toEqual({ 'kp:b': [], 'kp:c': [] })
  })
  it.each(['detach', 'kill'] as const)('%s 后的停留计时与已排队状态写入都不生效', async (kind) => {
    const h = hoverSetup()
    enter(h.graph)
    await vi.advanceTimersByTimeAsync(120)
    if (kind === 'detach') h.enhancer.detach()
    else h.kill()
    await h.drain()
    await elapse(h, 200)
    expect(h.graph.stateCalls).toEqual([])
  })
  it('异步状态写入经生命周期队列串行执行，旧操作不会覆盖新悬停', async () => {
    const h = hoverSetup()
    const write = h.graph.setElementState.bind(h.graph)
    let release!: () => void
    const blocked = new Promise<void>((resolve) => { release = resolve })
    let started = 0
    h.graph.setElementState = async (state) => {
      started += 1
      if (started === 1) await blocked
      await write(state)
    }
    enter(h.graph)
    await vi.advanceTimersByTimeAsync(120)
    const draining = h.drain()
    await Promise.resolve()
    enter(h.graph, 'b')
    await vi.advanceTimersByTimeAsync(120)
    try {
      expect(started).toBe(1)
    } finally {
      release()
      await draining
      await h.drain()
    }
    expect(h.graph.elementStates['kp:a']).toEqual(['mastered', 'hoverRelated'])
    expect(h.graph.elementStates['kp:b']).toEqual(['hovered'])
    expect(h.graph.elementStates['kp:c']).toEqual(['hoverFaded'])
  })
})

describe('空白点击与销毁', () => {
  it('点击画布空白处通知页面取消预览；detach 后不再响应', () => {
    const onBlankClick = vi.fn()
    const { graph, enhancer } = setup({ onBlankClick })
    enhancer.attach()
    graph.emit('canvas:click')
    expect(onBlankClick).toHaveBeenCalledTimes(1)
    enhancer.detach()
    graph.emit('canvas:click')
    expect(onBlankClick).toHaveBeenCalledTimes(1)
  })
  it('生命周期销毁后（alive=false）事件被忽略', () => {
    const onBlankClick = vi.fn()
    const { graph, enhancer, kill } = setup({ onBlankClick })
    enhancer.attach()
    kill()
    graph.emit('canvas:click')
    graph.emit('aftertransform')
    expect(onBlankClick).not.toHaveBeenCalled()
  })
})

describe('章节外框（hull 插件）', () => {
  it('首次添加插件（zIndex -1、靛紫虚线），之后只更新成员与可见性，从不移除', () => {
    const { graph, enhancer } = setup()
    enhancer.decorate({ nodes: [kp('a'), kp('b'), kp('c')], edges: [] })
    enhancer.setScope(['a', 'b'])
    expect(graph.pluginsAdded).toHaveLength(1)
    expect(graph.pluginsAdded[0]![0]).toMatchObject({
      type: 'hull',
      key: 'chapter-hull',
      members: ['kp:a', 'kp:b'],
      zIndex: -1,
      stroke: GRAPH_COLORS.accent,
      fill: GRAPH_COLORS.hullFill,
    })
    expect(graph.drawHull).toHaveBeenCalled()
    enhancer.setScope(null)
    expect(graph.pluginUpdates.at(-1)).toMatchObject({ key: 'chapter-hull', members: [], visibility: 'hidden' })
    enhancer.setScope(['c'])
    expect(graph.pluginUpdates.at(-1)).toMatchObject({ members: ['kp:c'], visibility: 'visible' })
    expect(graph.pluginsAdded).toHaveLength(1)
  })
  it('没有章节范围时不添加插件；不在图中的成员被忽略；相同成员不重复更新', () => {
    const { graph, enhancer } = setup()
    enhancer.decorate({ nodes: [kp('a')], edges: [] })
    enhancer.setScope(null)
    enhancer.setScope(['zzz'])
    expect(graph.pluginsAdded).toHaveLength(0)
    enhancer.setScope(['a'])
    enhancer.setScope(['a'])
    expect(graph.pluginsAdded).toHaveLength(1)
    expect(graph.pluginUpdates).toHaveLength(0)
  })
})

describe('小地图着色', () => {
  it('当前高亮靛紫、已掌握绿、学习中琥珀、其余石板灰', () => {
    const { enhancer } = setup()
    enhancer.decorate({
      nodes: [st(kp('a'), 'selected', 'mastered'), st(kp('b'), 'mastered'), st(kp('c'), 'learning'), kp('d')],
      edges: [],
    })
    expect(enhancer.minimapColor('kp:a')).toBe(GRAPH_COLORS.accent)
    expect(enhancer.minimapColor('kp:b')).toBe(GRAPH_COLORS.ok)
    expect(enhancer.minimapColor('kp:c')).toBe(GRAPH_COLORS.warn)
    expect(enhancer.minimapColor('kp:d')).toBe(GRAPH_COLORS.nodeStroke)
  })
})
