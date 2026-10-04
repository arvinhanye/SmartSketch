/**
 * 学习路径（L14，R11）：在已发布图上为「下一步」解释先修关系，纯函数、不依赖 Vue。
 *
 * - 只看未被拒的 `PREREQUISITE` 边（`RELATED_TO` 等不表示先修）；指向图外节点的边与掌握记录忽略。
 * - 推荐顺序与候选资格以服务端为准（`specs/learning-path.md`），这里不重排、不重算分数，只给序号。
 * - 焦点 f：`focus` 是推荐项时取它，否则取第一个推荐项；没有推荐（全部掌握或无可学）时没有焦点。
 * - f 的直接前置：已掌握为 `mastered`、未掌握为 `prereqMissing`；f 自身为 `next`。
 * - f 的直接后继 s：s 的**全部**前置都在「已掌握 ∪ {f}」内才是 `unlocks`；这些 s 的其他前置（必为已掌握）
 *   也标 `mastered`——它们和 f 一起促成解锁。
 * - 高亮边：f 的入边、指向 `unlocks` 节点的全部入边。其余节点为 `dimmed`。
 */

import type { G6Edge, G6Node } from './adapter'

export type PathRole = 'mastered' | 'prereqMissing' | 'next' | 'unlocks' | 'dimmed'

export interface LearningPath {
  /** 本次解释的推荐项；null 表示没有推荐 */
  focus: string | null
  /** 推荐顺序：kpId → 1 起的序号（仅推荐项） */
  order: ReadonlyMap<string, number>
  /** 各节点的角色；未出现的节点为 dimmed */
  roles: ReadonlyMap<string, PathRole>
  /** 应高亮的先修边：relation id */
  edges: ReadonlySet<string>
  /** 「已掌握 →（还需先学）→ 下一步 → 之后解锁」的名称列表，按节点在图中的顺序 */
  narrative: { mastered: string[]; missing: string[]; next: string[]; unlocks: string[] }
  /** 与 ``narrative`` 同序的知识点编号（C05-3：路径行里的名称可点击定位） */
  narrativeIds: { mastered: string[]; missing: string[]; next: string[]; unlocks: string[] }
}

export interface PathNode {
  id: string
  name: string
}

export interface PathEdge {
  id: string
  type: string
  from_id: string
  to_id: string
  status?: string
}

export function buildLearningPath(
  nodes: ReadonlyArray<PathNode>,
  edges: ReadonlyArray<PathEdge>,
  mastery: ReadonlyMap<string, string>,
  recommendations: ReadonlyArray<{ kp_id: string }>,
  focus: string | null,
): LearningPath {
  const known = new Set(nodes.map((node) => node.id))
  const order = new Map<string, number>()
  for (const item of recommendations) {
    if (known.has(item.kp_id) && !order.has(item.kp_id)) order.set(item.kp_id, order.size + 1)
  }
  const roles = new Map<string, PathRole>(nodes.map((node) => [node.id, 'dimmed']))
  const highlighted = new Set<string>()
  const first: string | undefined = order.keys().next().value
  const f: string | null = focus !== null && order.has(focus) ? focus : (first ?? null)
  if (f === null) return { focus: null, order, roles, edges: highlighted, ...narrate(nodes, roles) }

  const prereqs: PathEdge[] = edges.filter(
    (edge) => edge.type === 'PREREQUISITE' && edge.status !== 'rejected' && known.has(edge.from_id) && known.has(edge.to_id),
  )
  const incoming = (id: string): PathEdge[] => prereqs.filter((edge) => edge.to_id === id)
  const mastered = (id: string) => mastery.get(id) === 'mastered'

  roles.set(f, 'next')
  for (const edge of incoming(f)) {
    roles.set(edge.from_id, mastered(edge.from_id) ? 'mastered' : 'prereqMissing')
    highlighted.add(edge.id)
  }
  for (const out of prereqs.filter((edge) => edge.from_id === f)) {
    const target: string = out.to_id
    if (roles.get(target) === 'unlocks' || target === f || mastered(target)) continue
    const into: PathEdge[] = incoming(target)
    if (!into.every((edge) => edge.from_id === f || mastered(edge.from_id))) continue
    roles.set(target, 'unlocks')
    into.forEach((edge: PathEdge) => {
      highlighted.add(edge.id)
      if (edge.from_id !== f && roles.get(edge.from_id) === 'dimmed') roles.set(edge.from_id, 'mastered')
    })
  }
  return { focus: f, order, roles, edges: highlighted, ...narrate(nodes, roles) }
}

function narrate(
  nodes: ReadonlyArray<PathNode>,
  roles: ReadonlyMap<string, PathRole>,
): Pick<LearningPath, 'narrative' | 'narrativeIds'> {
  const of = (role: PathRole) => nodes.filter((node) => roles.get(node.id) === role)
  const names = (role: PathRole) => of(role).map((node) => node.name)
  const ids = (role: PathRole) => of(role).map((node) => node.id)
  return {
    narrative: { mastered: names('mastered'), missing: names('prereqMissing'), next: names('next'), unlocks: names('unlocks') },
    narrativeIds: { mastered: ids('mastered'), missing: ids('prereqMissing'), next: ids('next'), unlocks: ids('unlocks') },
  }
}

/** 画布数据（适配层输出）→ 路径输入：节点用 kpId、边用 relation id 与两端 kpId */
export function pathInputFromCanvas(graph: { nodes: readonly G6Node[]; edges: readonly G6Edge[] }): {
  nodes: PathNode[]
  edges: PathEdge[]
} {
  const kpOf = new Map(graph.nodes.map((node) => [node.id, node.data.kpId]))
  const edges: PathEdge[] = []
  for (const edge of graph.edges) {
    const from = kpOf.get(edge.source)
    const to = kpOf.get(edge.target)
    if (from === undefined || to === undefined) continue
    edges.push({ id: edge.data.relationId, type: edge.data.type, from_id: from, to_id: to, status: edge.data.status })
  }
  return { nodes: graph.nodes.map((node) => ({ id: node.data.kpId, name: node.data.name })), edges }
}
