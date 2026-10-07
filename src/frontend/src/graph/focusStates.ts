/**
 * 聚焦状态（设计规格 §3.4、§3.4a、§4.2、§7）。纯函数，不依赖 G6 与 Vue。
 *
 * 持久状态（预览/选中、章节聚焦）由 `applyFocusStates` 写进元素的 `states`，随数据交给画布；
 * 瞬时状态（悬停）由画布生命周期用 `hoverStateMap` 现算，只调 `setElementState`，不重绘数据。
 *
 * 状态只带名字，颜色只在 `buildGraphOptions` 定义一处。所有函数都不修改输入。
 */

/** 节点上由聚焦逻辑产生的状态（`selected` 沿用既有名字） */
export type FocusNodeState = 'selected' | 'neighbor' | 'dimmed' | 'faded' | 'match' | 'hovered' | 'hoverRelated' | 'hoverFaded'
/** 边上由聚焦逻辑产生的状态 */
export type FocusEdgeState = 'active' | 'scoped' | 'faded' | 'hoverFaded'

export interface FocusNodeLike {
  id: string
  states?: string[]
}
export interface FocusEdgeLike {
  id: string
  source: string
  target: string
  states?: string[]
}

export interface FocusInput {
  /** 被预览或选中的节点元素 id；没有则为 null */
  selectedId: string | null
  /** 搜索命中的节点元素 id */
  matchedIds: ReadonlySet<string>
  /** 定位的章节的节点元素 id；没有则为 null */
  chapterIds: ReadonlySet<string> | null
  /**
   * 预览/选中时非相关内容的淡化强度：
   * standard 只降填充饱和度（持久状态，边框与标签仍满足对比度，默认）；
   * strong 为 Obsidian 式（退成近画布色小点），仅供对比，持久状态默认不用。
   */
  fade: 'standard' | 'strong'
}

/** 一个节点的一阶邻居与相关边（不分方向） */
export function neighborsOf(
  edges: ReadonlyArray<{ id: string; source: string; target: string }>,
  nodeId: string,
): { nodes: Set<string>; edges: Set<string> } {
  const nodes = new Set<string>()
  const edgeIds = new Set<string>()
  for (const e of edges) {
    if (e.source === nodeId || e.target === nodeId) {
      edgeIds.add(e.id)
      nodes.add(e.source === nodeId ? e.target : e.source)
    }
  }
  nodes.delete(nodeId)
  return { nodes, edges: edgeIds }
}

/** 追加状态并去重，保持已有顺序 */
function withStates(existing: readonly string[] | undefined, extra: readonly string[]): string[] {
  const out = [...(existing ?? [])]
  for (const s of extra) if (!out.includes(s)) out.push(s)
  return out
}

/**
 * 把预览/选中、章节聚焦写进 `states`。
 * - 有预览/选中：节点 `selected`；一阶邻居 `neighbor`；其余 `dimmed`（standard）或 `faded`（strong）；
 *   相关边 `active`，strong 下其余边 `faded`。
 * - 没有预览/选中、有章节聚焦：非本章节点 `dimmed`；与本章节点相连的边 `scoped`（恢复正常粗细）。
 * - 搜索命中与章节成员都带 `match`。
 */
export function applyFocusStates<N extends FocusNodeLike, E extends FocusEdgeLike>(
  graph: { nodes: readonly N[]; edges: readonly E[] },
  focus: FocusInput,
): { nodes: N[]; edges: E[] } {
  const sel = focus.selectedId
  const around = sel === null ? null : neighborsOf(graph.edges, sel)
  const scope = focus.chapterIds

  const nodes = graph.nodes.map((n) => {
    const extra: string[] = []
    if (sel !== null) {
      if (n.id === sel) extra.push('selected')
      else if (around!.nodes.has(n.id)) extra.push('neighbor')
      else extra.push(focus.fade === 'strong' ? 'faded' : 'dimmed')
    } else if (scope !== null && !scope.has(n.id)) {
      extra.push('dimmed')
    }
    if ((scope !== null && scope.has(n.id)) || focus.matchedIds.has(n.id)) extra.push('match')
    return extra.length === 0 ? n : { ...n, states: withStates(n.states, extra) }
  })

  const edges = graph.edges.map((e) => {
    const extra: string[] = []
    if (sel !== null) {
      if (around!.edges.has(e.id)) extra.push('active')
      else if (focus.fade === 'strong') extra.push('faded')
    } else if (scope !== null && (scope.has(e.source) || scope.has(e.target))) {
      extra.push('scoped')
    }
    return extra.length === 0 ? e : { ...e, states: withStates(e.states, extra) }
  })
  return { nodes, edges }
}

/**
 * 悬停（瞬时强淡化，Obsidian 式）：返回「基础状态 + 悬停状态」的完整表，直接交给 `setElementState`。
 * 悬停状态排在基础状态之后，所以悬停时它赢；被预览/选中的节点即使与悬停节点无关也保留，用户不会丢掉自己的焦点。
 * `hoverId` 为 null 时只返回基础状态（用于悬停结束后恢复）。
 */
export function hoverStateMap(input: {
  nodes: readonly FocusNodeLike[]
  edges: readonly FocusEdgeLike[]
  hoverId: string | null
  selectedId: string | null
}): Record<string, string[]> {
  const { nodes, edges, hoverId, selectedId } = input
  const around = hoverId === null ? null : neighborsOf(edges, hoverId)
  const out: Record<string, string[]> = {}
  for (const n of nodes) {
    const extra: string[] = []
    if (around !== null) {
      if (n.id === hoverId) extra.push('hovered')
      else if (around.nodes.has(n.id)) extra.push('hoverRelated')
      else if (n.id !== selectedId) extra.push('hoverFaded')
    }
    out[n.id] = withStates(n.states, extra)
  }
  for (const e of edges) {
    const extra: string[] = []
    if (around !== null) extra.push(around.edges.has(e.id) ? 'active' : 'hoverFaded')
    out[e.id] = withStates(e.states, extra)
  }
  return out
}

/**
 * 标签优先级（`planLabels` 的排序依据）：预览/选中 > 搜索命中与章节成员 > 推荐项 > 选中节点的邻居 > importance。
 * 分数是累加的，所以**不能**用分数阈值判断「强制显示」：强制只看 `states` 是否含 `selected`。
 */
export function labelScore(input: {
  states: readonly string[]
  /** 契约的 importance（0–1）；缺省视为 0 */
  importance?: number
  /** 推荐序号（1 起）；没有则为 undefined */
  pathOrder?: number
}): number {
  const { states } = input
  let score = (input.importance ?? 0) * 100
  if (input.pathOrder !== undefined) score += 300
  if (states.includes('match')) score += 500
  if (states.includes('neighbor')) score += 200
  if (states.includes('selected')) score += 1000
  return score
}

/** 强制显示标签：只有被预览/选中的那个节点 */
export function isForcedLabel(states: readonly string[]): boolean {
  return states.includes('selected')
}
