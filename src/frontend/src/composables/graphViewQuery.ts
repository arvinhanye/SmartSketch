import type { RelationType } from '../graph/adapter'
import { NODE_TYPE_LABELS, RELATION_TYPE_ORDER, type KnowledgePointType } from './useGraphFilters'

/**
 * 学生图谱页的视图状态 ↔ 地址查询参数（UI-GRAPH-FIND-01）。纯函数。
 *
 * `kp` 已打开详情的知识点、`q` 搜索关键字、`ch` 定位的章节、`rel`/`type` 被隐藏的关系与知识点类型（逗号分隔）、
 * `view=cards` 列表视图。缺省值不写；不认识的值忽略。镜头位置不进地址。
 */
export interface GraphViewState {
  kp: string | null
  q: string
  ch: string | null
  hiddenRelations: RelationType[]
  hiddenTypes: KnowledgePointType[]
  cards: boolean
}

export const VIEW_QUERY_KEYS = ['kp', 'q', 'ch', 'rel', 'type', 'view'] as const

const NODE_TYPES = Object.keys(NODE_TYPE_LABELS) as KnowledgePointType[]

function text(value: unknown): string | null {
  return typeof value === 'string' && value !== '' ? value : null
}

function list<T extends string>(value: unknown, allowed: readonly T[]): T[] {
  const raw = text(value)
  if (raw === null) return []
  const wanted = new Set(raw.split(','))
  return allowed.filter((item) => wanted.has(item))
}

export function parseViewQuery(query: Record<string, unknown>): GraphViewState {
  return {
    kp: text(query.kp),
    q: text(query.q) ?? '',
    ch: text(query.ch),
    hiddenRelations: list(query.rel, RELATION_TYPE_ORDER),
    hiddenTypes: list(query.type, NODE_TYPES),
    cards: query.view === 'cards',
  }
}

export function viewQuery(state: GraphViewState): Record<string, string> {
  const out: Record<string, string> = {}
  if (state.kp !== null && state.kp !== '') out.kp = state.kp
  if (state.q.trim() !== '') out.q = state.q
  if (state.ch !== null && state.ch !== '') out.ch = state.ch
  if (state.hiddenRelations.length > 0) out.rel = RELATION_TYPE_ORDER.filter((t) => state.hiddenRelations.includes(t)).join(',')
  if (state.hiddenTypes.length > 0) out.type = NODE_TYPES.filter((t) => state.hiddenTypes.includes(t)).join(',')
  if (state.cards) out.view = 'cards'
  return out
}
