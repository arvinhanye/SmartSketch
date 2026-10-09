import { describe, expect, it } from 'vitest'
import { useLocalView, localKpIds, restrictGraph } from '../../src/frontend/src/composables/useLocalView'
import type { CanvasEdge, CanvasNode, GraphCanvasData } from '../../src/frontend/src/graph/lifecycle'

function node(id: string): CanvasNode {
  return {
    id: `kp:${id}`,
    data: { kpId: id, name: id, type: 'concept', level: 1, chapterId: 'c1', status: 'approved', confidence: 1, source: 'ai', locked: false },
  }
}
function edge(id: string, from: string, to: string): CanvasEdge {
  return {
    id: `rel:${id}`, source: `kp:${from}`, target: `kp:${to}`,
    data: { relationId: id, type: 'PREREQUISITE', directed: true, status: 'approved', confidence: 1, source: 'ai', downgraded: false },
    style: { stroke: '#000', lineWidth: 1, lineDash: [], endArrow: true, labelText: '前置' },
  }
}
// a→b→c→d，e 孤立
const graph: GraphCanvasData = {
  nodes: ['a', 'b', 'c', 'd', 'e'].map(node),
  edges: [edge('1', 'a', 'b'), edge('2', 'b', 'c'), edge('3', 'c', 'd')],
}

describe('localKpIds', () => {
  it('1 跳：中心与直接相邻（不分方向）', () => {
    expect([...localKpIds(graph, { id: 'b', hops: 1 })].sort()).toEqual(['a', 'b', 'c'])
  })
  it('2 跳：再向外一圈', () => {
    expect([...localKpIds(graph, { id: 'b', hops: 2 })].sort()).toEqual(['a', 'b', 'c', 'd'])
  })
  it('孤立节点只有自己', () => {
    expect([...localKpIds(graph, { id: 'e', hops: 2 })]).toEqual(['e'])
  })
  it('只在传入的图里找：被筛选隐藏的邻居不会被带回来', () => {
    const filtered = restrictGraph(graph, new Set(['a', 'b', 'd']))
    expect([...localKpIds(filtered, { id: 'b', hops: 2 })].sort()).toEqual(['a', 'b'])
  })
})

describe('restrictGraph', () => {
  it('保留范围内的节点与两端都在范围内的边，不修改输入', () => {
    const out = restrictGraph(graph, new Set(['a', 'b']))
    expect(out.nodes.map((n) => n.data.kpId)).toEqual(['a', 'b'])
    expect(out.edges.map((e) => e.id)).toEqual(['rel:1'])
    expect(graph.nodes).toHaveLength(5)
  })
})

describe('useLocalView', () => {
  it('toggle 开启 1 跳、再次对同一知识点调用关闭；setHops 切换范围；clear 恢复', () => {
    const lv = useLocalView(() => graph)
    expect(lv.ids.value).toBeNull()
    expect(lv.apply(graph)).toBe(graph)
    lv.toggle('b')
    expect(lv.view.value).toEqual({ id: 'b', hops: 1 })
    expect(lv.apply(graph)!.nodes).toHaveLength(3)
    lv.setHops(2)
    expect(lv.apply(graph)!.nodes).toHaveLength(4)
    lv.toggle('b')
    expect(lv.view.value).toBeNull()
    lv.toggle('c')
    lv.clear()
    expect(lv.ids.value).toBeNull()
  })
  it('没有开启时 setHops 无效；图为 null 时 apply 返回 null', () => {
    const lv = useLocalView(() => null)
    lv.setHops(2)
    expect(lv.view.value).toBeNull()
    expect(lv.apply(null)).toBeNull()
  })
})
