import { describe, expect, it } from 'vitest'
import {
  COMPACT_OPTIONS,
  computeLayout,
  layoutMetrics,
  type DagreEngine,
  type LayoutEdge,
  type LayoutNode,
  type Positions,
} from '../../src/frontend/src/graph/chapterLayout'

/**
 * 每章 perChapter 个节点：
 * - n0…n(k-3) 是先修树（PREREQUISITE，节点 i 的先修是 floor((i-1)/2)，深度约 3，接近真实课程的章内结构）；
 * - n(k-2) 没有任何关系（孤立）；
 * - n(k-1) 是例题，经 EXAMPLE_OF 挂在 n1 上（卫星）；
 * 章与章之间：上一章最后一个链节点 → 下一章 n0 的先修边；n2 之间有相关边。
 */
function course(chapters: number, perChapter: number): { nodes: LayoutNode[]; edges: LayoutEdge[]; order: string[] } {
  const nodes: LayoutNode[] = []
  const edges: LayoutEdge[] = []
  const id = (c: number, i: number) => `c${c}n${i}`
  let e = 0
  for (let c = 0; c < chapters; c += 1) {
    for (let i = 0; i < perChapter; i += 1) nodes.push({ id: id(c, i), chapter: `ch${c}` })
    const chain = perChapter - 2
    for (let i = 1; i < chain; i += 1) edges.push({ id: `e${e++}`, source: id(c, Math.floor((i - 1) / 2)), target: id(c, i), type: 'PREREQUISITE' })
    edges.push({ id: `e${e++}`, source: id(c, perChapter - 1), target: id(c, 1), type: 'EXAMPLE_OF' })
    if (c + 1 < chapters) {
      edges.push({ id: `e${e++}`, source: id(c, chain - 1), target: id(c + 1, 0), type: 'PREREQUISITE' })
      edges.push({ id: `e${e++}`, source: id(c, 2), target: id(c + 1, 2), type: 'RELATED_TO' })
    }
  }
  return { nodes, edges, order: Array.from({ length: chapters }, (_, c) => `ch${c}`) }
}

function bboxOf(pos: Positions, ids: string[]) {
  const xs = ids.map((i) => pos.get(i)!.x)
  const ys = ids.map((i) => pos.get(i)!.y)
  return { x1: Math.min(...xs), x2: Math.max(...xs), y1: Math.min(...ys), y2: Math.max(...ys) }
}

describe('章节分区布局 computeLayout（真实 G6 dagre 引擎）', () => {
  const g = course(4, 8)

  it('每个节点都有有限的位置', async () => {
    const pos = await computeLayout(g.nodes, g.edges, 'chapter', g.order)
    expect(pos.size).toBe(g.nodes.length)
    for (const n of g.nodes) {
      const p = pos.get(n.id)!
      expect(Number.isFinite(p.x) && Number.isFinite(p.y), n.id).toBe(true)
    }
  })

  it('节点互不重叠：任意两节点中心距 ≥ 60', async () => {
    const pos = await computeLayout(g.nodes, g.edges, 'chapter', g.order)
    const m = layoutMetrics(pos, g.nodes, g.edges)
    expect(m.minNodeDist).toBeGreaterThanOrEqual(60)
  })

  it('章内先修边方向不变：全部向下', async () => {
    const pos = await computeLayout(g.nodes, g.edges, 'chapter', g.order)
    expect(layoutMetrics(pos, g.nodes, g.edges).prereqWithinDownShare).toBe(1)
  })

  it('各章的包围盒互不相交（章节是分区）', async () => {
    const pos = await computeLayout(g.nodes, g.edges, 'chapter', g.order)
    const boxes = g.order.map((c) => bboxOf(pos, g.nodes.filter((n) => n.chapter === c).map((n) => n.id)))
    for (let i = 0; i < boxes.length; i += 1) {
      for (let j = i + 1; j < boxes.length; j += 1) {
        const a = boxes[i]!
        const b = boxes[j]!
        const disjoint = a.x2 < b.x1 || b.x2 < a.x1 || a.y2 < b.y1 || b.y2 < a.y1
        expect(disjoint, `ch${i} 与 ch${j} 的包围盒相交`).toBe(true)
      }
    }
  })

  it('各章按课程顺序排列：行优先（先从左到右，再从上到下）', async () => {
    const pos = await computeLayout(g.nodes, g.edges, 'chapter', g.order)
    const boxes = g.order.map((c) => bboxOf(pos, g.nodes.filter((n) => n.chapter === c).map((n) => n.id)))
    for (let i = 0; i + 1 < boxes.length; i += 1) {
      const a = boxes[i]!
      const b = boxes[i + 1]!
      const nextRow = b.y1 > a.y1 + 1
      const sameRowRight = Math.abs(b.y1 - a.y1) <= 1 && b.x1 > a.x1
      expect(nextRow || sameRowRight, `ch${i + 1} 应在 ch${i} 之后`).toBe(true)
    }
  })

  it('例题（卫星）挨着它说明的知识点，不被甩到远处', async () => {
    const pos = await computeLayout(g.nodes, g.edges, 'chapter', g.order)
    for (let c = 0; c < 4; c += 1) {
      const example = pos.get(`c${c}n7`)!
      const concept = pos.get(`c${c}n1`)!
      expect(Math.hypot(example.x - concept.x, example.y - concept.y)).toBeLessThanOrEqual(COMPACT_OPTIONS.cellW * 3)
    }
  })

  it('没有任何关系的孤立节点也有位置，且不压在别的节点上', async () => {
    const pos = await computeLayout(g.nodes, g.edges, 'chapter', g.order)
    for (let c = 0; c < 4; c += 1) {
      const orphan = pos.get(`c${c}n6`)!
      expect(orphan).toBeDefined()
      for (const n of g.nodes) {
        if (n.id === `c${c}n6`) continue
        const p = pos.get(n.id)!
        expect(Math.hypot(p.x - orphan.x, p.y - orphan.y), `${n.id}`).toBeGreaterThan(40)
      }
    }
  })

  it('结果是确定的：同样输入得到同样位置', async () => {
    const a = await computeLayout(g.nodes, g.edges, 'chapter', g.order)
    const b = await computeLayout(g.nodes, g.edges, 'chapter', g.order)
    expect([...a]).toEqual([...b])
  })

  it('不修改输入', async () => {
    const nodes = JSON.stringify(g.nodes)
    const edges = JSON.stringify(g.edges)
    await computeLayout(g.nodes, g.edges, 'chapter', g.order)
    expect(JSON.stringify(g.nodes)).toBe(nodes)
    expect(JSON.stringify(g.edges)).toBe(edges)
  })
})

describe('章节分区布局：边界', () => {
  it('空图返回空', async () => {
    expect((await computeLayout([], [], 'chapter', [])).size).toBe(0)
  })

  it('章节不在目录里的节点不会消失；未归章节点归入最后一个分区', async () => {
    const nodes: LayoutNode[] = [
      { id: 'a', chapter: 'ch1' },
      { id: 'b', chapter: 'ch1' },
      { id: 'c', chapter: 'ghost' }, // 目录里没有
      { id: 'd', chapter: null }, // 未归章
    ]
    const edges: LayoutEdge[] = [{ id: 'e', source: 'a', target: 'b', type: 'PREREQUISITE' }]
    const pos = await computeLayout(nodes, edges, 'chapter', ['ch1'])
    expect([...pos.keys()].sort()).toEqual(['a', 'b', 'c', 'd'])
  })

  it('指向不存在节点的边被忽略，不影响布局', async () => {
    const nodes: LayoutNode[] = [{ id: 'a', chapter: 'x' }, { id: 'b', chapter: 'x' }]
    const edges: LayoutEdge[] = [
      { id: 'e1', source: 'a', target: 'b', type: 'PREREQUISITE' },
      { id: 'e2', source: 'a', target: 'missing', type: 'PREREQUISITE' },
    ]
    for (const mode of ['all', 'hier', 'chapter'] as const) {
      const pos = await computeLayout(nodes, edges, mode, ['x'])
      expect(pos.size, mode).toBe(2)
    }
  })

  it('没有任何先修关系（PDF 式）时也是接近横屏的紧凑网格，不会排成一条长带', async () => {
    const nodes: LayoutNode[] = []
    for (let c = 0; c < 8; c += 1) for (let i = 0; i < 12; i += 1) nodes.push({ id: `c${c}n${i}`, chapter: `ch${c}` })
    const order = Array.from({ length: 8 }, (_, c) => `ch${c}`)
    const pos = await computeLayout(nodes, [], 'chapter', order)
    const m = layoutMetrics(pos, nodes, [])
    expect(m.aspect).toBeGreaterThan(0.4)
    expect(m.aspect).toBeLessThan(3)
    expect(m.minNodeDist).toBeGreaterThanOrEqual(60)
  })
})

describe('章节分区布局：可替换引擎', () => {
  it('chapter 模式每章调用一次引擎，且只传该章的层级边（相关/应用实例关系不参与布局）', async () => {
    const calls: Array<{ ids: string[]; edges: Array<{ source: string; target: string }> }> = []
    const stack: DagreEngine = async (ids, edges) => {
      calls.push({ ids, edges })
      return new Map(ids.map((id, i) => [id, { x: 0, y: i * 150 }]))
    }
    const g = course(3, 8)
    await computeLayout(g.nodes, g.edges, 'chapter', g.order, {}, stack)
    expect(calls).toHaveLength(3)
    for (const [c, call] of calls.entries()) {
      for (const id of call.ids) expect(id.startsWith(`c${c}n`)).toBe(true)
      for (const e of call.edges) {
        expect(e.source.startsWith(`c${c}n`) && e.target.startsWith(`c${c}n`)).toBe(true)
      }
    }
  })

  it('hier 模式不把相关/应用实例边交给引擎；all 模式把全部边交给引擎', async () => {
    const seen: number[] = []
    const stub: DagreEngine = async (ids, edges) => {
      seen.push(edges.length)
      return new Map(ids.map((id, i) => [id, { x: i * 100, y: 0 }]))
    }
    const g = course(2, 8)
    await computeLayout(g.nodes, g.edges, 'hier', g.order, {}, stub)
    const hierCount = g.edges.filter((e) => e.type === 'PREREQUISITE' || e.type === 'CONTAINS').length
    expect(seen.at(-1)).toBe(hierCount)
    await computeLayout(g.nodes, g.edges, 'all', g.order, {}, stub)
    expect(seen.at(-1)).toBe(g.edges.length)
  })
})

describe('章节分区布局：对比现状（96 节点，8 章 × 12）', () => {
  const g = course(8, 12)

  it('每章都能放进可读缩放下的一屏；现状一章都放不下', async () => {
    const chapter = layoutMetrics(await computeLayout(g.nodes, g.edges, 'chapter', g.order), g.nodes, g.edges)
    expect(chapter.chapters.fitOneScreen).toBe(chapter.chapters.n)
    const all = layoutMetrics(await computeLayout(g.nodes, g.edges, 'all', g.order, { nodesep: 56, ranksep: 110 }), g.nodes, g.edges)
    expect(all.chapters.fitOneScreen).toBeLessThan(chapter.chapters.fitOneScreen)
  })

  it('适应一屏的缩放至少是现状的 2 倍，且画布接近横屏', async () => {
    const chapter = layoutMetrics(await computeLayout(g.nodes, g.edges, 'chapter', g.order), g.nodes, g.edges)
    const all = layoutMetrics(await computeLayout(g.nodes, g.edges, 'all', g.order, { nodesep: 56, ranksep: 110 }), g.nodes, g.edges)
    expect(chapter.fitZoom).toBeGreaterThan(all.fitZoom * 2)
    expect(chapter.aspect).toBeGreaterThan(0.5)
    expect(chapter.aspect).toBeLessThan(2.5)
  })
})
