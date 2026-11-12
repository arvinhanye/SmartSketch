/**
 * 成环预判（UI-GRAPH-EDIT-02）。纯函数，不修改输入。
 *
 * 拖线、点选连线时提前告诉教师“这两个知识点之间加前置关系会成环”，让“前置”在类型选择里不可选。
 * 口径与后端一致：只看未驳回的 `PREREQUISITE`。它只是提示，最终裁决仍是后端的环检测。
 */
export interface CycleEdge {
  type: string
  from_id: string
  to_id: string
  status: string
}

/** 新增「from → to」的前置关系后是否成环：`to` 沿现有前置关系能走到 `from`（或两者相同） */
export function prerequisiteWouldCycle(edges: readonly CycleEdge[], from: string, to: string): boolean {
  if (from === to) return true
  const next = new Map<string, string[]>()
  for (const edge of edges) {
    if (edge.type !== 'PREREQUISITE' || edge.status === 'rejected') continue
    const list = next.get(edge.from_id)
    if (list === undefined) next.set(edge.from_id, [edge.to_id])
    else list.push(edge.to_id)
  }
  const seen = new Set<string>([to])
  const queue = [to]
  while (queue.length > 0) {
    const current = queue.shift()!
    for (const neighbor of next.get(current) ?? []) {
      if (neighbor === from) return true
      if (!seen.has(neighbor)) {
        seen.add(neighbor)
        queue.push(neighbor)
      }
    }
  }
  return false
}
