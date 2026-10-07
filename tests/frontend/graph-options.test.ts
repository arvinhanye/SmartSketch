import { describe, expect, it } from 'vitest'
import type { G6Edge, G6Node } from '../../src/frontend/src/graph/adapter'
import { buildGraphOptions, READABLE_ZOOM } from '../../src/frontend/src/graph/lifecycle'
import { GRAPH_COLORS, NODE_TYPE_FILL, NODE_TYPE_GLYPH } from '../../src/frontend/src/graph/theme'

type Fn = (d: unknown) => unknown
function options() {
  return buildGraphOptions({ container: document.createElement('div'), width: 100, height: 100, data: { nodes: [], edges: [] } }) as unknown as {
    node: { style: Record<string, Fn | unknown>; state: Record<string, Record<string, unknown>> }
    edge: { style: Record<string, Fn | unknown>; state: Record<string, Record<string, unknown>> }
  }
}
function node(extra: Partial<G6Node['data']> = {}): G6Node {
  return {
    id: 'kp:a',
    data: { kpId: 'a', name: '线性表', type: 'concept', level: 1, chapterId: 'c1', status: 'approved', confidence: 1, source: 'ai', locked: false, ...extra },
  }
}
const call = (fn: unknown, d: unknown) => (fn as Fn)(d)

describe('buildGraphOptions 新主题', () => {
  it('可读缩放常量是 0.9，并仍由 lifecycle 导出', () => {
    expect(READABLE_ZOOM).toBe(0.9)
  })

  it('节点：类型填充 + 单字标记，不只靠颜色', () => {
    const s = options().node.style
    expect(call(s.fill, node({ type: 'theorem' }))).toBe(NODE_TYPE_FILL.theorem)
    expect(call(s.iconText, node({ type: 'method' }))).toBe(NODE_TYPE_GLYPH.method)
    expect(s.stroke).toBe(GRAPH_COLORS.nodeStroke)
  })

  it('节点尺寸、字号、行高、折行宽度随展示字段放大，缺省时是基础值', () => {
    const s = options().node.style
    expect(call(s.size, node())).toBe(36)
    expect(call(s.size, node({ nk: 2.5 }))).toBe(90)
    expect(call(s.labelFontSize, node({ k: 5 }))).toBe(65)
    expect(call(s.labelLineHeight, node({ k: 2 }))).toBe(34)
    expect(call(s.labelWordWrapWidth, node({ k: 2 }))).toBe(224)
  })

  it('标签用布尔 label 开关（labelVisibility 无效），默认显示', () => {
    const s = options().node.style
    expect(call(s.label, node())).toBe(true)
    expect(call(s.label, node({ labelOn: false }))).toBe(false)
  })

  it('标签文本保持 L14 的「1. 名称」格式；掌握状态用角标', () => {
    const s = options().node.style
    expect(call(s.labelText, node({ pathOrder: 2, name: '栈' }))).toBe('2. 栈')
    expect(call(s.badges, node({ mastery: 'mastered' }))).toHaveLength(1)
    expect(call(s.badges, node())).toEqual([])
  })

  it('状态名清单：持久状态与悬停瞬时状态', () => {
    const o = options()
    expect(Object.keys(o.node.state).sort()).toEqual([
      'dimmed', 'faded', 'hoverFaded', 'hoverRelated', 'hovered', 'learning', 'lowConfidence', 'mastered', 'match',
      'neighbor', 'notStarted', 'pathPrereq', 'pathUnlock', 'recommended', 'rejected', 'selected',
    ])
    expect(Object.keys(o.edge.state).sort()).toEqual([
      'active', 'dimmed', 'faded', 'hoverFaded', 'lowConfidence', 'pathEdge', 'rejected', 'scoped',
    ])
  })

  it('标准淡化（dimmed）换填充与边框，不用整体 opacity；强淡化与悬停淡化隐去标签与角标', () => {
    const { node: n, edge: e } = options()
    expect(n.state.dimmed).toMatchObject({ fill: GRAPH_COLORS.dimmedFill, stroke: GRAPH_COLORS.dimmedStroke })
    expect(n.state.dimmed).not.toHaveProperty('opacity')
    expect(n.state.hoverFaded).toMatchObject({ fill: GRAPH_COLORS.fadedFill, stroke: GRAPH_COLORS.fadedStroke, label: false, badge: false })
    expect(e.state.hoverFaded).toMatchObject({ stroke: GRAPH_COLORS.fadedEdge, lineWidth: 1, halo: false })
    expect(e.state.dimmed).not.toHaveProperty('opacity')
  })

  it('选中与搜索命中用靛紫外环；边的 active 状态显式关闭 G6 自带的光晕', () => {
    const { node: n, edge: e } = options()
    expect(n.state.selected).toMatchObject({ stroke: GRAPH_COLORS.accent })
    expect(n.state.match).toMatchObject({ stroke: GRAPH_COLORS.accent, labelFill: GRAPH_COLORS.accent })
    expect(e.state.active).toMatchObject({ halo: false })
  })

  it('边：箭头大小随展示字段，关系名标签带不透明底', () => {
    const s = options().edge.style
    const edge = { data: { ak: 2 } } as unknown as G6Edge
    expect(call(s.endArrowSize, edge)).toBe(18)
    expect(s.labelBackground).toBe(true)
    expect(s.labelBackgroundOpacity).toBe(1)
  })
})
