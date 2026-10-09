import { describe, expect, it } from 'vitest'
import {
  COMPACT_OPTIONS,
  computeLayout,
  layoutMetrics,
  prefersRadial,
  radialEngine,
  type LayoutEdge,
  type LayoutNode,
  type Positions,
} from '../../src/frontend/src/graph/chapterLayout'

/** 一棵三层的包含树：根 → 6 个小节 → 每节 8 个知识点（共 55 个节点） */
function bigTree(): { nodes: LayoutNode[]; edges: LayoutEdge[] } {
  const nodes: LayoutNode[] = [{ id: 'root', chapter: 'c1' }]
  const edges: LayoutEdge[] = []
  for (let s = 0; s < 6; s += 1) {
    nodes.push({ id: `s${s}`, chapter: 'c1' })
    edges.push({ id: `e-s${s}`, source: 'root', target: `s${s}`, type: 'CONTAINS' })
    for (let k = 0; k < 8; k += 1) {
      nodes.push({ id: `s${s}k${k}`, chapter: 'c1' })
      edges.push({ id: `e-s${s}k${k}`, source: `s${s}`, target: `s${s}k${k}`, type: 'CONTAINS' })
    }
  }
  return { nodes, edges }
}

const dist = (pos: Positions, a: string, b: string) => Math.hypot(pos.get(a)!.x - pos.get(b)!.x, pos.get(a)!.y - pos.get(b)!.y)

describe('径向布局引擎', () => {
  it('单根树：根在原点，每个节点的半径随深度递增，且位置确定（同输入同输出）', async () => {
    const { nodes, edges } = bigTree()
    const ids = nodes.map((n) => n.id)
    const pos = await radialEngine(ids, edges, COMPACT_OPTIONS)
    expect(pos.size).toBe(ids.length)
    expect(pos.get('root')).toEqual({ x: 0, y: 0 })
    const r = (id: string) => Math.hypot(pos.get(id)!.x, pos.get(id)!.y)
    expect(r('s0')).toBeGreaterThan(0)
    expect(r('s0k0')).toBeGreaterThan(r('s0'))
    const again = await radialEngine(ids, edges, COMPACT_OPTIONS)
    expect([...again]).toEqual([...pos])
  })

  it('任意两个节点不重叠（中心距不小于节点直径 36），整体是接近宽画布的椭圆（约 1.9:1）而不是 10:1 的长条', async () => {
    const { nodes, edges } = bigTree()
    const pos = await computeLayout(nodes, edges, 'chapter', ['c1'], {}, radialEngine)
    const m = layoutMetrics(pos, nodes, edges)
    expect(m.minNodeDist).toBeGreaterThanOrEqual(36)
    expect(m.aspect).toBeGreaterThan(1.0)
    expect(m.aspect).toBeLessThan(2.6)
  })

  it('子树占据连续的扇区：同一父节点的孩子比别的小节的孩子彼此更近', async () => {
    const { nodes, edges } = bigTree()
    const pos = await radialEngine(nodes.map((n) => n.id), edges, COMPACT_OPTIONS)
    expect(dist(pos, 's0k0', 's0k1')).toBeLessThan(dist(pos, 's0k0', 's3k0'))
  })

  it('多个根：没有中心节点，根排在第一圈；有交叉的多父节点只按一棵生成树摆放，但每个节点都有位置', async () => {
    const edges: LayoutEdge[] = [
      { id: '1', source: 'a', target: 'c', type: 'PREREQUISITE' },
      { id: '2', source: 'b', target: 'c', type: 'PREREQUISITE' },
      { id: '3', source: 'c', target: 'd', type: 'PREREQUISITE' },
    ]
    const pos = await radialEngine(['a', 'b', 'c', 'd'], edges, COMPACT_OPTIONS)
    expect(pos.size).toBe(4)
    const r = (id: string) => Math.hypot(pos.get(id)!.x, pos.get(id)!.y)
    expect(r('a')).toBeGreaterThan(0)
    expect(r('b')).toBeGreaterThan(0)
    expect(r('c')).toBeGreaterThan(r('a'))
    expect(r('d')).toBeGreaterThan(r('c'))
  })

  it('空输入与单节点；含环的坏数据不会死循环', async () => {
    expect((await radialEngine([], [], COMPACT_OPTIONS)).size).toBe(0)
    expect((await radialEngine(['x'], [], COMPACT_OPTIONS)).get('x')).toEqual({ x: 0, y: 0 })
    const cyc = await radialEngine(['a', 'b'], [
      { source: 'a', target: 'b' },
      { source: 'b', target: 'a' },
    ], COMPACT_OPTIONS)
    expect(cyc.size).toBe(2)
  })
})

describe('prefersRadial：什么时候默认推荐径向', () => {
  const grid = (n: number, w: number, h: number): Positions =>
    new Map(Array.from({ length: n }, (_, i) => [`n${i}`, { x: (i % 8) * (w / 8), y: Math.floor(i / 8) * (h / Math.ceil(n / 8)) }]))
  it('节点多且层次布局被拉成长条（宽高比 > 3）时推荐', () => {
    expect(prefersRadial(grid(64, 6000, 400))).toBe(true)
  })
  it('节点少、或形状本来就紧凑时不推荐', () => {
    expect(prefersRadial(grid(10, 6000, 400))).toBe(false)
    expect(prefersRadial(grid(64, 1200, 900))).toBe(false)
  })
})
