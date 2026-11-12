import { describe, expect, it } from 'vitest'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import { mergePreview, NEIGHBOR_LIMIT } from '../../src/frontend/src/graph/mergePreview'

/**
 * UX-REVIEW-DEDUP-01：合并前后局部图的前端推算（按 ADR-047 第 3、6 条）。
 * 规格见 specs/teacher-review-publish.md「疑似重复知识点：对比与合并预览」。
 */
type GraphExchange = components['schemas']['GraphExchange']
type KnowledgePoint = components['schemas']['KnowledgePoint']
type Relation = components['schemas']['Relation']

function kp(id: string, over: Partial<KnowledgePoint> = {}): KnowledgePoint {
  return {
    id, course_id: 'c1', name: `知识点${id}`, type: 'concept', definition: `${id} 的定义`, level: 1, confidence: 0.9,
    status: 'approved', source: 'ai', locked: false, revision: 1, chapter_id: 'ch1', ...over,
  }
}
function rel(id: string, from: string, to: string, type: Relation['type'] = 'CONTAINS', over: Partial<Relation> = {}): Relation {
  return { id, course_id: 'c1', type, from_id: from, to_id: to, confidence: 0.9, status: 'approved', source: 'ai', source_refs: [], ...over } as Relation
}
function graph(nodes: KnowledgePoint[], edges: Relation[]): GraphExchange {
  return { format_version: '1.0', course_id: 'c1', graph_version: null, generated_at: '2026-11-11T00:00:00Z', nodes, edges } as unknown as GraphExchange
}

// p（父）包含 a、b；a 包含 x、y；b 包含 z、w
const base = () =>
  graph(
    [kp('p'), kp('a', { name: '队列' }), kp('b', { name: '队列的定义', aliases: ['FIFO 表'] }), kp('x'), kp('y'), kp('z'), kp('w')],
    [rel('pa', 'p', 'a'), rel('pb', 'p', 'b'), rel('ax', 'a', 'x'), rel('ay', 'a', 'y'), rel('bz', 'b', 'z'), rel('bw', 'b', 'w')],
  )
const ids = (list: ReadonlyArray<{ id: string }>) => list.map((item) => item.id).sort()
const pairs = (list: ReadonlyArray<{ from: string; to: string; type: string }>) => list.map((e) => `${e.from}-${e.type}->${e.to}`).sort()

describe('mergePreview：合并前', () => {
  it('只含这两个知识点和与它们直接相连的知识点及关系，并标出角色', () => {
    const out = mergePreview(graph([...base().nodes, kp('far')], [...base().edges, rel('xfar', 'x', 'far')]), ['a', 'b'], 'a')!
    expect(ids(out.before.nodes)).toEqual(['a', 'b', 'p', 'w', 'x', 'y', 'z'])
    expect(out.before.nodes.find((n) => n.id === 'a')!.role).toBe('primary')
    expect(out.before.nodes.find((n) => n.id === 'b')!.role).toBe('merged')
    expect(out.before.nodes.find((n) => n.id === 'p')!.role).toBe('neighbor')
    expect(pairs(out.before.edges)).toEqual(['a-CONTAINS->x', 'a-CONTAINS->y', 'b-CONTAINS->w', 'b-CONTAINS->z', 'p-CONTAINS->a', 'p-CONTAINS->b'])
    expect(out.before.hiddenNeighbors).toBe(0)
  })

  it('知识点不在图里时返回 null；不修改输入', () => {
    const g = base()
    const snapshot = JSON.stringify(g)
    expect(mergePreview(g, ['a', 'nope'], 'a')).toBe(null)
    expect(mergePreview(g, ['a', 'b'], 'x')).toBe(null)
    mergePreview(g, ['a', 'b'], 'b')
    expect(JSON.stringify(g)).toBe(snapshot)
  })
})

describe('mergePreview：合并后（预计）', () => {
  it('被并入的一端改接到保留的知识点；重复的关系合为一条；保留的知识点获得别名并锁定', () => {
    const out = mergePreview(base(), ['a', 'b'], 'a')!
    expect(ids(out.after.nodes)).toEqual(['a', 'p', 'w', 'x', 'y', 'z'])
    expect(pairs(out.after.edges)).toEqual(['a-CONTAINS->w', 'a-CONTAINS->x', 'a-CONTAINS->y', 'a-CONTAINS->z', 'p-CONTAINS->a'])
    const moved = out.after.edges.filter((e) => e.moved)
    expect(pairs(moved)).toEqual(['a-CONTAINS->w', 'a-CONTAINS->z'])
    const primary = out.after.nodes.find((n) => n.id === 'a')!
    expect(primary.locked).toBe(true)
    expect(primary.aliases).toEqual(['队列的定义', 'FIFO 表'])
    expect(out.summary).toEqual({ moved: 2, deduplicated: 1, dropped: 0, addedAliases: ['队列的定义', 'FIFO 表'] })
  })

  it('换成保留另一个：方向相反', () => {
    const out = mergePreview(base(), ['a', 'b'], 'b')!
    expect(ids(out.after.nodes)).toEqual(['b', 'p', 'w', 'x', 'y', 'z'])
    expect(pairs(out.after.edges.filter((e) => e.moved))).toEqual(['b-CONTAINS->x', 'b-CONTAINS->y'])
    expect(out.after.nodes.find((n) => n.id === 'b')!.aliases).toEqual(['FIFO 表', '队列'])
    expect(out.summary.addedAliases).toEqual(['队列'])
  })

  it('两个知识点之间本来的关系在合并后去掉并计数', () => {
    const g = graph([kp('a'), kp('b'), kp('x')], [rel('ab', 'a', 'b', 'RELATED_TO'), rel('ba', 'b', 'a', 'PREREQUISITE'), rel('bx', 'b', 'x')])
    const out = mergePreview(g, ['a', 'b'], 'a')!
    expect(pairs(out.after.edges)).toEqual(['a-CONTAINS->x'])
    expect(out.summary).toMatchObject({ moved: 1, dropped: 2, deduplicated: 0 })
  })

  it('类型不同或方向不同的关系不算重复；已驳回的关系不参与', () => {
    const g = graph(
      [kp('a'), kp('b'), kp('x')],
      [rel('ax', 'a', 'x', 'CONTAINS'), rel('bx', 'b', 'x', 'PREREQUISITE'), rel('xb', 'x', 'b', 'CONTAINS'), rel('bx2', 'b', 'x', 'CONTAINS', { status: 'rejected' })],
    )
    const out = mergePreview(g, ['a', 'b'], 'a')!
    expect(pairs(out.before.edges)).toEqual(['a-CONTAINS->x', 'b-PREREQUISITE->x', 'x-CONTAINS->b'])
    expect(pairs(out.after.edges)).toEqual(['a-CONTAINS->x', 'a-PREREQUISITE->x', 'x-CONTAINS->a'])
    expect(out.summary.deduplicated).toBe(0)
  })

  it('别名精确去重，且不含保留知识点自己的名称', () => {
    const g = graph([kp('a', { name: '栈', aliases: ['堆栈'] }), kp('b', { name: '堆栈', aliases: ['栈', 'Stack'] })], [])
    const out = mergePreview(g, ['a', 'b'], 'a')!
    expect(out.after.nodes[0]!.aliases).toEqual(['堆栈', 'Stack'])
    expect(out.summary.addedAliases).toEqual(['Stack'])
  })
})

describe('mergePreview：相邻知识点很多时', () => {
  it(`最多画 ${NEIGHBOR_LIMIT} 个相邻知识点，其余计入 hiddenNeighbors；两张图画的是同一批`, () => {
    const many = Array.from({ length: NEIGHBOR_LIMIT + 5 }, (_, i) => kp(`n${String(i).padStart(2, '0')}`))
    const g = graph([kp('a'), kp('b'), ...many], many.map((n, i) => rel(`r${i}`, i % 2 === 0 ? 'a' : 'b', n.id)))
    const out = mergePreview(g, ['a', 'b'], 'a')!
    const neighborsBefore = out.before.nodes.filter((n) => n.role === 'neighbor')
    expect(neighborsBefore).toHaveLength(NEIGHBOR_LIMIT)
    expect(out.before.hiddenNeighbors).toBe(5)
    expect(out.after.hiddenNeighbors).toBe(5)
    expect(ids(out.after.nodes.filter((n) => n.role === 'neighbor'))).toEqual(ids(neighborsBefore))
    // 说明里的数量按全部关系算，不受“只画 8 个”影响
    expect(out.summary.moved).toBe(Math.floor((NEIGHBOR_LIMIT + 5) / 2))
    // 两个知识点都有相邻知识点被画出来，不会只画其中一个的
    expect(out.before.edges.some((e) => e.from === 'a')).toBe(true)
    expect(out.before.edges.some((e) => e.from === 'b')).toBe(true)
  })
})
