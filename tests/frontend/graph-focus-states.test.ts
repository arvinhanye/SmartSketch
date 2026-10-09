import { describe, expect, it } from 'vitest'
import {
  applyFocusStates,
  hoverStateMap,
  isForcedLabel,
  labelScore,
  neighborsOf,
  type FocusEdgeLike,
  type FocusInput,
  type FocusNodeLike,
} from '../../src/frontend/src/graph/focusStates'

const node = (id: string, states?: string[]): FocusNodeLike => (states ? { id, states } : { id })
const edge = (id: string, source: string, target: string, states?: string[]): FocusEdgeLike =>
  states ? { id, source, target, states } : { id, source, target }

//   a → b → c      d（孤立）
const nodes = [node('a'), node('b'), node('c'), node('d')]
const edges = [edge('ab', 'a', 'b'), edge('bc', 'b', 'c')]

const none: FocusInput = { selectedId: null, matchedIds: new Set(), chapterIds: null, fade: 'standard' }
const statesOf = (list: Array<{ id: string; states?: string[] }>) => Object.fromEntries(list.map((x) => [x.id, x.states ?? []]))

describe('neighborsOf', () => {
  it('一阶邻居与相关边，不分方向，不含自己', () => {
    const { nodes: n, edges: e } = neighborsOf(edges, 'b')
    expect([...n].sort()).toEqual(['a', 'c'])
    expect([...e].sort()).toEqual(['ab', 'bc'])
    expect(neighborsOf(edges, 'd').nodes.size).toBe(0)
  })
})

describe('applyFocusStates：预览/选中', () => {
  it('选中节点 selected，邻居 neighbor，其余 dimmed（标准淡化）；相关边 active，其余边不动', () => {
    const out = applyFocusStates({ nodes, edges }, { ...none, selectedId: 'a' })
    expect(statesOf(out.nodes)).toEqual({ a: ['selected'], b: ['neighbor'], c: ['dimmed'], d: ['dimmed'] })
    expect(statesOf(out.edges)).toEqual({ ab: ['active'], bc: [] })
  })

  it('强淡化（strong）：非相关节点与非相关边用 faded', () => {
    const out = applyFocusStates({ nodes, edges }, { ...none, selectedId: 'a', fade: 'strong' })
    expect(statesOf(out.nodes).c).toEqual(['faded'])
    expect(statesOf(out.edges)).toEqual({ ab: ['active'], bc: ['faded'] })
  })

  it('没有预览/选中、没有章节、没有命中时原样返回（同一个对象，不产生多余的重绘）', () => {
    const out = applyFocusStates({ nodes, edges }, none)
    expect(out.nodes[0]).toBe(nodes[0])
    expect(out.edges[0]).toBe(edges[0])
  })

  it('保留已有状态并追加在后面；不重复添加', () => {
    const out = applyFocusStates(
      { nodes: [node('a', ['mastered', 'selected']), node('b', ['learning'])], edges: [edge('ab', 'a', 'b')] },
      { ...none, selectedId: 'a' },
    )
    expect(statesOf(out.nodes)).toEqual({ a: ['mastered', 'selected'], b: ['learning', 'neighbor'] })
  })
})

describe('applyFocusStates：章节聚焦与搜索命中', () => {
  const chapter = new Set(['a', 'b'])

  it('非本章节点 dimmed，本章节点 match；与本章节点相连的边 scoped', () => {
    const out = applyFocusStates({ nodes, edges }, { ...none, chapterIds: chapter })
    expect(statesOf(out.nodes)).toEqual({ a: ['match'], b: ['match'], c: ['dimmed'], d: ['dimmed'] })
    expect(statesOf(out.edges)).toEqual({ ab: ['scoped'], bc: ['scoped'] })
  })

  it('有预览/选中时预览规则优先，章节成员仍带 match', () => {
    const out = applyFocusStates({ nodes, edges }, { ...none, chapterIds: chapter, selectedId: 'c' })
    const s = statesOf(out.nodes)
    expect(s.c).toEqual(['selected'])
    expect(s.a).toEqual(['dimmed', 'match'])
    expect(s.b).toEqual(['neighbor', 'match'])
  })

  it('搜索命中只加 match，不淡化其他节点', () => {
    const out = applyFocusStates({ nodes, edges }, { ...none, matchedIds: new Set(['c']) })
    expect(statesOf(out.nodes)).toEqual({ a: [], b: [], c: ['match'], d: [] })
  })

  it('不修改输入', () => {
    const snapshot = JSON.stringify({ nodes, edges })
    applyFocusStates({ nodes, edges }, { ...none, selectedId: 'a', chapterIds: chapter })
    expect(JSON.stringify({ nodes, edges })).toBe(snapshot)
  })
})

describe('hoverStateMap：悬停（瞬时强淡化）', () => {
  it('悬停节点 hovered，直接相邻 hoverRelated，其余 hoverFaded；相关边 active，其余边 hoverFaded', () => {
    const map = hoverStateMap({ nodes, edges, hoverId: 'a', selectedId: null })
    expect(map).toMatchObject({ a: ['hovered'], b: ['hoverRelated'], c: ['hoverFaded'], d: ['hoverFaded'], ab: ['active'], bc: ['hoverFaded'] })
  })

  it('悬停状态排在基础状态之后（悬停赢），基础状态保留', () => {
    const map = hoverStateMap({ nodes: [node('a', ['mastered']), node('b', ['dimmed'])], edges: [edge('ab', 'a', 'b')], hoverId: 'a', selectedId: null })
    expect(map.a).toEqual(['mastered', 'hovered'])
    expect(map.b).toEqual(['dimmed', 'hoverRelated'])
  })

  it('被预览/选中的节点即使与悬停节点无关也不被淡化（用户不会丢掉自己的焦点）', () => {
    const map = hoverStateMap({ nodes, edges, hoverId: 'a', selectedId: 'd' })
    expect(map.d).toEqual([])
    expect(map.c).toEqual(['hoverFaded'])
  })

  it('hoverId 为 null：只返回基础状态（用于悬停结束后恢复）', () => {
    const map = hoverStateMap({ nodes: [node('a', ['selected'])], edges: [edge('ab', 'a', 'b', ['active'])], hoverId: null, selectedId: 'a' })
    expect(map).toEqual({ a: ['selected'], ab: ['active'] })
  })

  it('不重复添加已有的 active', () => {
    const map = hoverStateMap({ nodes, edges: [edge('ab', 'a', 'b', ['active'])], hoverId: 'a', selectedId: null })
    expect(map.ab).toEqual(['active'])
  })
})

describe('labelScore 与强制显示', () => {
  it('预览/选中 > 搜索命中与章节成员 > 推荐项 > 邻居 > importance', () => {
    const selected = labelScore({ states: ['selected'] })
    const matched = labelScore({ states: ['match'] })
    const recommended = labelScore({ states: [], pathOrder: 1 })
    const neighbor = labelScore({ states: ['neighbor'] })
    const important = labelScore({ states: [], importance: 1 })
    expect(selected).toBeGreaterThan(matched)
    expect(matched).toBeGreaterThan(recommended)
    expect(recommended).toBeGreaterThan(neighbor)
    expect(neighbor).toBeGreaterThan(important)
  })

  it('分数是累加的：章节成员里的推荐项（match + 推荐）仍然低于被选中的节点', () => {
    const memberRecommended = labelScore({ states: ['match'], pathOrder: 2, importance: 1 })
    expect(memberRecommended).toBeLessThan(labelScore({ states: ['selected'] }))
  })

  it('强制显示只看是否被预览/选中，不看分数：高分的章节成员也不强制', () => {
    expect(isForcedLabel(['selected'])).toBe(true)
    expect(isForcedLabel(['match', 'neighbor'])).toBe(false)
    expect(isForcedLabel([])).toBe(false)
  })

  it('缺省值：没有 importance、没有推荐序号时为 0', () => {
    expect(labelScore({ states: [] })).toBe(0)
  })
})
