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

  it('悬停节点与相邻保持清楚，其余退后；持久状态保留；移开 60ms 后恢复', async () => {
    const hovers: unknown[] = []
    const { graph, enhancer } = setup({ onHover: (info) => hovers.push(info) })
    enhancer.decorate(data())
    enhancer.attach()
    graph.emit('node:pointerenter', { target: { id: 'kp:a' }, pointerType: 'mouse', client: { x: 10, y: 20 } })
    const during = graph.stateCalls.at(-1)!
    expect(during['kp:a']).toEqual(['mastered', 'hovered'])
    expect(during['kp:b']).toEqual(['hoverRelated'])
    expect(during['kp:c']).toEqual(['hoverFaded'])
    expect(during['rel:r1']).toEqual(['active'])
    expect(hovers.at(-1)).toEqual({ kpId: 'a', clientX: 10, clientY: 20 })
    graph.emit('node:pointerleave')
    expect(hovers.at(-1)).toBeNull()
    await sleep(90)
    const after = graph.stateCalls.at(-1)!
    expect(after['kp:a']).toEqual(['mastered'])
    expect(after['kp:c']).toEqual([])
  })
  it('触屏没有悬停效果', () => {
    const { graph, enhancer } = setup()
    enhancer.decorate(data())
    enhancer.attach()
    graph.emit('node:pointerenter', { target: { id: 'kp:a' }, pointerType: 'touch' })
    expect(graph.stateCalls).toEqual([])
  })
  it('快速移到相邻节点时不闪：进入新节点会取消恢复', async () => {
    const { graph, enhancer } = setup()
    enhancer.decorate(data())
    enhancer.attach()
    graph.emit('node:pointerenter', { target: { id: 'kp:a' }, pointerType: 'mouse' })
    graph.emit('node:pointerleave')
    graph.emit('node:pointerenter', { target: { id: 'kp:b' }, pointerType: 'mouse' })
    await sleep(90)
    expect(graph.stateCalls.at(-1)!['kp:b']).toEqual(['hovered'])
  })
  it('兜底：画布空白处移动、进入边也结束悬停', async () => {
    const { graph, enhancer } = setup()
    enhancer.decorate(data())
    enhancer.attach()
    graph.emit('node:pointerenter', { target: { id: 'kp:a' }, pointerType: 'mouse' })
    graph.emit('canvas:pointermove')
    await sleep(90)
    expect(graph.stateCalls.at(-1)!['kp:a']).toEqual(['mastered'])
    graph.emit('node:pointerenter', { target: { id: 'kp:a' }, pointerType: 'mouse' })
    graph.emit('edge:pointerenter')
    await sleep(90)
    expect(graph.stateCalls.at(-1)!['kp:a']).toEqual(['mastered'])
  })
  it('兜底：指针离开整个画布容器也结束悬停；没有悬停时是空操作', async () => {
    const { graph, enhancer } = setup()
    enhancer.decorate(data())
    enhancer.attach()
    enhancer.leaveHover()
    expect(graph.stateCalls).toEqual([])
    graph.emit('node:pointerenter', { target: { id: 'kp:a' }, pointerType: 'mouse' })
    enhancer.leaveHover()
    await sleep(90)
    expect(graph.stateCalls.at(-1)!['kp:a']).toEqual(['mastered'])
  })
  it('预览/选中的节点即使与悬停节点无关也保留外环', () => {
    const { graph, enhancer } = setup()
    enhancer.decorate({ nodes: [kp('a'), st(kp('c'), 'selected')], edges: [] })
    enhancer.attach()
    graph.emit('node:pointerenter', { target: { id: 'kp:a' }, pointerType: 'mouse' })
    expect(graph.stateCalls.at(-1)!['kp:c']).toEqual(['selected'])
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
