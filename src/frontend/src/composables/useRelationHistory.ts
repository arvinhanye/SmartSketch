import { RELATION_STYLES, type RelationType } from '../graph/adapter'
import type { EditHistory } from './useEditHistory'
import type { RelationEditor } from './useRelationEditor'

/**
 * 给关系编辑加上撤销 / 重做记录（UI-GRAPH-UNDO-04）。
 *
 * 返回一个和 `useRelationEditor` 同形的对象：新建、改类型、反转、删除成功后各记一步，其余原样透传。
 * 画布上的直接操作和“编辑关系”页签都用这个对象，所以两处做的修改进同一份记录。
 *
 * 反向操作不记关系编号：后端按“类型 + 端点”重新派生编号，改过类型或方向后原编号就不存在了。
 * 这里按“类型 + 起点 + 终点”在当前草稿里现找（“相关”无方向，两个方向都算），找不到就算这一步失败。
 * 撤销 / 重做时调用的是原始的编辑方法，不会再被记一遍。
 */
export function useRelationHistory(relations: RelationEditor, history: EditHistory): RelationEditor {
  const label = (type: RelationType) => RELATION_STYLES[type].label

  function find(type: RelationType, from: string, to: string): string | null {
    for (const edge of relations.graph.value?.edges ?? []) {
      if (edge.type !== type || edge.id.startsWith('pending:')) continue
      if (edge.from_id === from && edge.to_id === to) return edge.id
      if (!RELATION_STYLES[type].directed && edge.from_id === to && edge.to_id === from) return edge.id
    }
    return null
  }
  /** 两个端点的名称（取不到时退回 ID） */
  function names(type: RelationType, from: string, to: string): [string, string] {
    const id = find(type, from, to)
    const row = id === null ? null : relations.describeRelation(id)
    if (row === null) return [from, to]
    return row.fromId === from ? [row.fromName, row.toName] : [row.toName, row.fromName]
  }
  const on = async (type: RelationType, from: string, to: string, act: (id: string) => Promise<boolean>): Promise<boolean> => {
    const id = find(type, from, to)
    return id === null ? false : act(id)
  }

  async function createBetween(from: string, to: string, type: RelationType, success?: string): Promise<boolean> {
    const ok = await relations.createBetween(from, to, type, success)
    if (!ok) return false
    const [a, b] = names(type, from, to)
    history.record({
      label: `新建关系 ${a} → ${b}（${label(type)}）`,
      undo: () => on(type, from, to, (id) => relations.deleteRelation(id)),
      redo: () => relations.createBetween(from, to, type),
    })
    return true
  }

  async function createRelation(): Promise<boolean> {
    const from = relations.fromId.value
    const to = relations.toId.value
    // 起点或终点没选：交回原来的校验与提示
    if (from === null || to === null) return relations.createRelation()
    const ok = await createBetween(from, to, relations.draftType.value)
    if (ok) relations.toId.value = null
    return ok
  }

  async function changeType(relationId: string, type: RelationType): Promise<boolean> {
    const before = relations.describeRelation(relationId)
    const ok = await relations.changeType(relationId, type)
    if (!ok || before === null || before.type === type) return ok
    const { fromId, toId, fromName, toName, type: old } = before
    history.record({
      label: `把 ${fromName} → ${toName} 的类型由“${label(old)}”改为“${label(type)}”`,
      undo: () => on(type, fromId, toId, (id) => relations.changeType(id, old)),
      redo: () => on(old, fromId, toId, (id) => relations.changeType(id, type)),
    })
    return true
  }

  async function reverseRelation(relationId: string): Promise<boolean> {
    const before = relations.describeRelation(relationId)
    const ok = await relations.reverseRelation(relationId)
    if (!ok || before === null) return ok
    const { fromId, toId, fromName, toName, type } = before
    history.record({
      label: `反转 ${fromName} → ${toName}（${label(type)}）`,
      undo: () => on(type, toId, fromId, (id) => relations.reverseRelation(id)),
      redo: () => on(type, fromId, toId, (id) => relations.reverseRelation(id)),
    })
    return true
  }

  async function deleteRelation(relationId: string): Promise<boolean> {
    const before = relations.describeRelation(relationId)
    const ok = await relations.deleteRelation(relationId)
    if (!ok || before === null) return ok
    const { fromId, toId, fromName, toName, type } = before
    history.record({
      label: `删除关系 ${fromName} → ${toName}（${label(type)}）`,
      // 重新建立的是一条新的人工关系：原关系的编号、来源片段与审核状态不恢复
      undo: () => relations.createBetween(fromId, toId, type, `已恢复关系：${fromName} → ${toName}。`),
      redo: () => on(type, fromId, toId, (id) => relations.deleteRelation(id)),
    })
    return true
  }

  return { ...relations, createBetween, createRelation, changeType, reverseRelation, deleteRelation }
}
