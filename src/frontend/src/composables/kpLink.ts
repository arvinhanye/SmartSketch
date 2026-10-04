/**
 * 问答 → 图谱的知识点链接（L13-4，R08）：`/courses/:cid/graph?kp=<知识点>&v=<回答所依据的图谱版本>`。
 * 学生图谱页加载完当前课程的图后按本函数决定是否选中、给出什么提示：只在本课程已加载的图里找，
 * 绝不跨课程找同 ID 节点；回答所依据的版本与当前版本不同则如实提示。
 */

export interface KpLinkQuery {
  kp?: unknown
  v?: unknown
}

export interface KpLinkGraph {
  course_id: string
  graph_version: number | null
  nodes: ReadonlyArray<{ id: string }>
}

export interface KpLinkOutcome {
  select: string | null
  notice: string | null
}

/** 图未加载、不属于当前课程或没有有效的 kp 时返回 null（不处理） */
export function kpLinkOutcome(query: KpLinkQuery, courseId: string | null, graph: KpLinkGraph | null): KpLinkOutcome | null {
  const kp = query.kp
  if (typeof kp !== 'string' || kp === '' || graph === null || courseId === null || graph.course_id !== courseId) return null
  if (!graph.nodes.some((node) => node.id === kp)) {
    return { select: null, notice: '该知识点不在当前发布版本中（可能已被删除或合并）。' }
  }
  const answered = typeof query.v === 'string' && /^[1-9][0-9]*$/.test(query.v) ? Number(query.v) : null
  if (answered !== null && graph.graph_version !== null && answered !== graph.graph_version) {
    return { select: kp, notice: `回答基于第 ${answered} 版图谱，当前为第 ${graph.graph_version} 版；知识点内容可能已有变化。` }
  }
  return { select: kp, notice: null }
}
