import type { GraphExchange, KnowledgePoint, Relation, RelationType } from './adapter'

/**
 * 合并两个知识点前后的局部图（UX-REVIEW-DEDUP-01）。纯函数，不依赖 G6 与 Vue，不修改输入。
 *
 * “合并后”是前端按 ADR-047 第 3、6 条推算的**预计**结果，不是服务端结果：
 * - 被并入知识点的一端改接到保留的知识点；两端都落在这两个知识点之内的关系去掉；
 * - 「类型 + 起点 + 终点」相同的关系合为一条（保留的知识点原有的那条胜出）；
 * - 保留的知识点获得对方的名称与别名（精确去重，不含自己的名称）并被锁定。
 * 已驳回的关系不参与。服务端另有不可见关系、来源迁移、修订号等规则，预览不体现。
 */

/** 局部图里最多画几个相邻知识点；其余只计数 */
export const NEIGHBOR_LIMIT = 8

export interface PreviewNode {
  id: string
  name: string
  type: KnowledgePoint['type']
  role: 'primary' | 'merged' | 'neighbor'
  aliases: string[]
  locked: boolean
}

export interface PreviewEdge {
  id: string
  type: RelationType
  from: string
  to: string
  /** 合并后由被并入的知识点改接过来的关系 */
  moved: boolean
}

export interface LocalGraph {
  nodes: PreviewNode[]
  edges: PreviewEdge[]
  /** 没画出来的相邻知识点数量 */
  hiddenNeighbors: number
}

export interface MergeSummary {
  /** 改接到保留知识点的关系数（去重之后） */
  moved: number
  /** 因「类型 + 端点」相同而合并掉的关系数 */
  deduplicated: number
  /** 两个知识点之间、合并后去掉的关系数 */
  dropped: number
  /** 保留的知识点新增的别名 */
  addedAliases: string[]
}

export interface MergePreview {
  before: LocalGraph
  after: LocalGraph
  summary: MergeSummary
}

function toNode(kp: KnowledgePoint, role: PreviewNode['role']): PreviewNode {
  return { id: kp.id, name: kp.name, type: kp.type, role, aliases: [...(kp.aliases ?? [])], locked: kp.locked }
}

/** 两个知识点的相邻知识点轮流取，保证两边都有画出来的 */
function pickNeighbors(edges: readonly Relation[], a: string, b: string, limit: number): { shown: string[]; hidden: number } {
  const of = (center: string): string[] => {
    const out: string[] = []
    for (const e of edges) {
      const other = e.from_id === center ? e.to_id : e.to_id === center ? e.from_id : null
      if (other !== null && other !== a && other !== b && !out.includes(other)) out.push(other)
    }
    return out
  }
  const lists = [of(a), of(b)]
  const all: string[] = []
  for (let i = 0; i < Math.max(lists[0]!.length, lists[1]!.length); i += 1) {
    for (const list of lists) {
      const id = list[i]
      if (id !== undefined && !all.includes(id)) all.push(id)
    }
  }
  return { shown: all.slice(0, limit), hidden: Math.max(0, all.length - limit) }
}

/**
 * `pair` 是疑似重复的两个知识点，`primaryId` 是其中要保留的那个。
 * 任一知识点不在图里、或 `primaryId` 不是其中之一时返回 null（调用方不显示预览）。
 */
export function mergePreview(
  graph: Pick<GraphExchange, 'nodes' | 'edges'>,
  pair: readonly [string, string] | readonly string[],
  primaryId: string,
  limit: number = NEIGHBOR_LIMIT,
): MergePreview | null {
  const [first, second] = pair
  if (first === undefined || second === undefined || first === second || !pair.includes(primaryId)) return null
  const mergedId = primaryId === first ? second : first
  const byId = new Map(graph.nodes.map((node) => [node.id, node]))
  const primary = byId.get(primaryId)
  const merged = byId.get(mergedId)
  if (primary === undefined || merged === undefined) return null

  const inPair = (id: string) => id === primaryId || id === mergedId
  // 已驳回的关系不参与；端点缺失的关系不画
  const touching = graph.edges.filter(
    (e) => e.status !== 'rejected' && (inPair(e.from_id) || inPair(e.to_id)) && byId.has(e.from_id) && byId.has(e.to_id),
  )
  const { shown, hidden } = pickNeighbors(touching, first, second, limit)
  const visible = new Set<string>([primaryId, mergedId, ...shown])
  const neighborNodes = shown.map((id) => toNode(byId.get(id)!, 'neighbor'))

  const before: LocalGraph = {
    nodes: [toNode(byId.get(first)!, first === primaryId ? 'primary' : 'merged'), toNode(byId.get(second)!, second === primaryId ? 'primary' : 'merged'), ...neighborNodes],
    edges: touching
      .filter((e) => visible.has(e.from_id) && visible.has(e.to_id))
      .map((e) => ({ id: e.id, type: e.type, from: e.from_id, to: e.to_id, moved: false })),
    hiddenNeighbors: hidden,
  }

  // ---- 合并后：先对全部相关关系推算（说明里的数量不受“只画几个”影响），再取画得出来的
  let dropped = 0
  let deduplicated = 0
  const kept = new Map<string, PreviewEdge>()
  // 保留知识点原有的关系先进，重复时它胜出；两点之间的关系归在后一组里，随后被去掉
  const touchesMerged = (e: Relation) => e.from_id === mergedId || e.to_id === mergedId
  const ordered = [...touching.filter((e) => !touchesMerged(e)), ...touching.filter(touchesMerged)]
  for (const e of ordered) {
    if (inPair(e.from_id) && inPair(e.to_id)) {
      dropped += 1
      continue
    }
    const moved = e.from_id === mergedId || e.to_id === mergedId
    const from = e.from_id === mergedId ? primaryId : e.from_id
    const to = e.to_id === mergedId ? primaryId : e.to_id
    const key = `${e.type}|${from}|${to}`
    if (kept.has(key)) deduplicated += 1
    else kept.set(key, { id: e.id, type: e.type, from, to, moved })
  }
  const afterEdges = [...kept.values()]

  const aliases = [...(primary.aliases ?? [])]
  const addedAliases: string[] = []
  for (const candidate of [merged.name, ...(merged.aliases ?? [])]) {
    if (candidate === primary.name || aliases.includes(candidate)) continue
    aliases.push(candidate)
    addedAliases.push(candidate)
  }

  const after: LocalGraph = {
    nodes: [{ ...toNode(primary, 'primary'), aliases, locked: true }, ...neighborNodes],
    edges: afterEdges.filter((e) => visible.has(e.from) && visible.has(e.to)),
    hiddenNeighbors: hidden,
  }

  return {
    before,
    after,
    summary: { moved: afterEdges.filter((e) => e.moved).length, deduplicated, dropped, addedAliases },
  }
}
