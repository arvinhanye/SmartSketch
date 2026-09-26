import type { components } from '../../../contracts/v1/generated/typescript/openapi'

/**
 * 图谱交换格式 → G6 数据（H03）。
 *
 * 纯函数，不依赖 G6 运行时：输出是 G6 v5 `GraphData` 形状的普通对象，由画布组件（H04）交给 G6。
 * - 不修改输入，输出不引用输入中的任何对象或数组，画布可随意改写。
 * - 元素 ID 由契约 ID 加类别前缀（`kp:` / `rel:`）得到，节点与边同名 ID 不冲突；
 *   节点、边都按契约 ID 的码点顺序输出，同一张图不论输入顺序如何，输出逐字节相同。
 * - 其他课程的元素、重复 ID、端点不在节点集中的边不进画布，逐条记入 `issues`，由调用方决定是否提示。
 */

export type GraphExchange = components['schemas']['GraphExchange']
export type KnowledgePoint = components['schemas']['KnowledgePoint']
export type Relation = components['schemas']['Relation']
export type RelationType = components['schemas']['RelationType']

export interface RelationStyle {
  /** 图例与边标签的中文名（`docs/architecture.md` 术语表） */
  readonly label: string
  readonly stroke: string
  readonly lineWidth: number
  /** 空数组为实线 */
  readonly lineDash: readonly number[]
  /** 有向关系画终点箭头；`RELATED_TO` 无方向 */
  readonly directed: boolean
}

function style(value: RelationStyle): RelationStyle {
  Object.freeze(value.lineDash)
  return Object.freeze(value)
}

/** 四类关系的边样式，图例（H 组）与画布共用此表 */
export const RELATION_STYLES: Readonly<Record<RelationType, RelationStyle>> = Object.freeze({
  CONTAINS: style({ label: '包含', stroke: '#8c8c8c', lineWidth: 1.5, lineDash: [], directed: true }),
  PREREQUISITE: style({ label: '前置', stroke: '#1677ff', lineWidth: 2, lineDash: [], directed: true }),
  RELATED_TO: style({ label: '相关', stroke: '#52c41a', lineWidth: 1, lineDash: [6, 4], directed: false }),
  EXAMPLE_OF: style({ label: '应用实例', stroke: '#fa8c16', lineWidth: 1, lineDash: [2, 3], directed: true }),
})

export interface G6NodeData {
  kpId: string
  name: string
  type: KnowledgePoint['type']
  level: number
  chapterId: string | null
  status: KnowledgePoint['status']
  confidence: number
  source: KnowledgePoint['source']
  locked: boolean
}

export interface G6Node {
  id: string
  data: G6NodeData
}

export interface G6EdgeData {
  relationId: string
  type: RelationType
  directed: boolean
  status: Relation['status']
  confidence: number
  source: Relation['source']
  /** 自动成环降级而来的 `RELATED_TO`（B11） */
  downgraded: boolean
}

export interface G6EdgeStyle {
  stroke: string
  lineWidth: number
  lineDash: number[]
  endArrow: boolean
  labelText: string
}

export interface G6Edge {
  id: string
  source: string
  target: string
  data: G6EdgeData
  style: G6EdgeStyle
}

export type AdapterIssue =
  | { element: 'node' | 'edge'; id: string; reason: 'foreign_course' | 'duplicate_id' }
  | { element: 'edge'; id: string; reason: 'missing_endpoint'; missing: string[] }

export interface AdaptedGraph {
  nodes: G6Node[]
  edges: G6Edge[]
  issues: AdapterIssue[]
}

export function nodeElementId(kpId: string): string {
  return `kp:${kpId}`
}

export function edgeElementId(relationId: string): string {
  return `rel:${relationId}`
}

/** 码点顺序；不用 localeCompare，避免结果随运行环境的区域设置变化 */
function byCodePoint(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0
}

/** 按课程与 ID 去重，保留每个 ID 首次出现的元素 */
function admit<T extends { id: string; course_id: string }>(
  items: readonly T[],
  courseId: string,
  element: 'node' | 'edge',
  issues: AdapterIssue[],
): T[] {
  const kept = new Map<string, T>()
  for (const item of items) {
    if (item.course_id !== courseId) {
      issues.push({ element, id: item.id, reason: 'foreign_course' })
    } else if (kept.has(item.id)) {
      issues.push({ element, id: item.id, reason: 'duplicate_id' })
    } else {
      kept.set(item.id, item)
    }
  }
  return [...kept.values()].sort((a, b) => byCodePoint(a.id, b.id))
}

function toNode(kp: KnowledgePoint): G6Node {
  return {
    id: nodeElementId(kp.id),
    data: {
      kpId: kp.id,
      name: kp.name,
      type: kp.type,
      level: kp.level,
      chapterId: kp.chapter_id ?? null,
      status: kp.status,
      confidence: kp.confidence,
      source: kp.source,
      locked: kp.locked,
    },
  }
}

function toEdge(relation: Relation): G6Edge {
  const s = RELATION_STYLES[relation.type]
  return {
    id: edgeElementId(relation.id),
    source: nodeElementId(relation.from_id),
    target: nodeElementId(relation.to_id),
    data: {
      relationId: relation.id,
      type: relation.type,
      directed: s.directed,
      status: relation.status,
      confidence: relation.confidence,
      source: relation.source,
      downgraded: 'downgraded_from_type' in relation,
    },
    style: {
      stroke: s.stroke,
      lineWidth: s.lineWidth,
      lineDash: [...s.lineDash],
      endArrow: s.directed,
      labelText: s.label,
    },
  }
}

export function toG6Data(graph: GraphExchange): AdaptedGraph {
  const nodeIssues: AdapterIssue[] = []
  const edgeIssues: AdapterIssue[] = []
  const kps = admit(graph.nodes, graph.course_id, 'node', nodeIssues)
  const relations = admit(graph.edges, graph.course_id, 'edge', edgeIssues)

  const present = new Set(kps.map((kp) => kp.id))
  const edges: G6Edge[] = []
  for (const relation of relations) {
    const missing = [...new Set([relation.from_id, relation.to_id])].filter((id) => !present.has(id))
    if (missing.length > 0) {
      edgeIssues.push({ element: 'edge', id: relation.id, reason: 'missing_endpoint', missing })
    } else {
      edges.push(toEdge(relation))
    }
  }

  const byId = (a: AdapterIssue, b: AdapterIssue) => byCodePoint(a.id, b.id)
  return {
    nodes: kps.map(toNode),
    edges,
    issues: [...nodeIssues.sort(byId), ...edgeIssues.sort(byId)],
  }
}
