import { computed, onScopeDispose, ref, shallowRef } from 'vue'
import { prerequisiteWouldCycle } from '../graph/cycle'
import type { RelationType } from '../graph/adapter'
import { nodeAt, type NodeAnchor } from '../graph/hitTest'
import type { RelationEditor, RelationRow } from './useRelationEditor'

/**
 * 画布上的直接操作（UI-GRAPH-EDIT-02）：关系线工具条、节点菜单、连线（拖动或点选）、可撤销的关系删除。
 *
 * 只管“正在操作什么”的界面状态；真正的写入全部交给 `useRelationEditor`（乐观更新、成环与冲突处理、单请求串行），
 * 节点的查看 / 编辑 / 删除交回页面（它们要经过“未保存修改”确认与现有的删除确认）。
 * 坐标一律是画布容器内的屏幕坐标。
 */
export const UNDO_MS = 6000
/** 指针离开节点后悬停工具再留多久（给指针移到“⋯”和连接柄上的时间） */
export const HOVER_LINGER_MS = 350

export interface Point {
  x: number
  y: number
}

export type ConnectState =
  | { phase: 'picking'; from: string }
  | { phase: 'dragging'; from: string; start: Point; pointer: Point; target: NodeAnchor | null; cycle: boolean }
  | { phase: 'choosing'; from: string; to: string; at: Point; prerequisiteBlocked: boolean }

export interface UseCanvasEditingOptions {
  relations: RelationEditor
  /** 各节点当前的屏幕位置；画布没建好时返回空数组 */
  anchors: () => NodeAnchor[]
  /** 撤销刚才的关系删除。给了就用它（页面的撤销记录），否则按原类型和端点重新建一条 */
  undoLast?: () => Promise<boolean>
  onDetail: (kpId: string) => void
  onEdit: (kpId: string) => void
  onDelete: (kpId: string) => void
}

export function useCanvasEditing({ relations, anchors, undoLast, onDetail, onEdit, onDelete }: UseCanvasEditingOptions) {
  const edgeTool = shallowRef<{ relationId: string; at: Point } | null>(null)
  const menu = shallowRef<{ kpId: string; at: Point } | null>(null)
  const hover = shallowRef<NodeAnchor | null>(null)
  const connect = shallowRef<ConnectState | null>(null)
  const undo = shallowRef<{ text: string; from: string; to: string; type: RelationType } | null>(null)
  /** 撤销没成功时的说明（关系未恢复） */
  const undoError = ref<string | null>(null)
  let hoverTimer: ReturnType<typeof setTimeout> | null = null
  let undoTimer: ReturnType<typeof setTimeout> | null = null
  let dragAnchors: NodeAnchor[] = []

  const busy = computed(() => relations.saving.value)
  const edgeRow = computed<RelationRow | null>(() => (edgeTool.value === null ? null : relations.describeRelation(edgeTool.value.relationId)))
  const nameOf = (kpId: string) => relations.nodeOptions.value.find((n) => n.id === kpId)?.name ?? kpId
  const edgesNow = () => relations.graph.value?.edges ?? []

  function clearHoverTimer(): void {
    if (hoverTimer !== null) clearTimeout(hoverTimer)
    hoverTimer = null
  }
  function clearUndo(): void {
    if (undoTimer !== null) clearTimeout(undoTimer)
    undoTimer = null
    undo.value = null
  }

  /** 收起所有浮在画布上的临时工具（不动撤销提示） */
  function dismiss(): void {
    edgeTool.value = null
    menu.value = null
    connect.value = null
    hover.value = null
    clearHoverTimer()
  }

  /**
   * 画布平移、缩放或点了空白处：钉在某个屏幕位置上的工具（关系线工具条、菜单、类型选择、悬停工具）收起；
   * “点选连线”继续等目标——教师常常要先挪一下画布才找得到目标节点。
   */
  function onViewChange(): void {
    edgeTool.value = null
    menu.value = null
    hover.value = null
    clearHoverTimer()
    if (connect.value !== null && connect.value.phase === 'choosing') connect.value = null
  }

  // ---------------------------------------------------------------- 关系线
  function openEdge(info: { relationId: string; x: number; y: number }): void {
    const row = relations.describeRelation(info.relationId)
    // 保存中的临时线、或连线进行中：不打开工具条
    if (row === null || row.pending || connect.value !== null) return
    menu.value = null
    hover.value = null
    edgeTool.value = { relationId: info.relationId, at: { x: info.x, y: info.y } }
  }
  async function changeEdgeType(type: RelationType): Promise<void> {
    const tool = edgeTool.value
    if (tool === null || busy.value) return
    await relations.changeType(tool.relationId, type)
  }
  async function reverseEdge(): Promise<void> {
    const tool = edgeTool.value
    if (tool === null || busy.value) return
    await relations.reverseRelation(tool.relationId)
  }
  async function deleteEdge(): Promise<void> {
    const row = edgeRow.value
    if (row === null || busy.value) return
    edgeTool.value = null
    undoError.value = null
    const ok = await relations.deleteRelation(row.id)
    if (!ok) return
    clearUndo()
    undo.value = { text: `已删除关系：${row.fromName} → ${row.toName}（${row.typeLabel}）`, from: row.fromId, to: row.toId, type: row.type }
    undoTimer = setTimeout(clearUndo, UNDO_MS)
  }
  /** 撤销删除：按原来的类型和端点重新建一条（新的人工关系，原编号、来源与状态不恢复） */
  async function undoDelete(): Promise<void> {
    const last = undo.value
    if (last === null || busy.value) return
    clearUndo()
    const ok = undoLast !== undefined ? await undoLast() : await relations.createBetween(last.from, last.to, last.type, `已恢复关系：${nameOf(last.from)} → ${nameOf(last.to)}。`)
    if (!ok) undoError.value = '撤销没有成功，关系未恢复。'
  }

  // ---------------------------------------------------------------- 节点悬停工具与菜单
  function onNodeHover(kpId: string | null): void {
    clearHoverTimer()
    if (menu.value !== null || edgeTool.value !== null || connect.value !== null) return
    if (kpId === null) {
      hoverTimer = setTimeout(() => {
        hover.value = null
      }, HOVER_LINGER_MS)
      return
    }
    hover.value = anchors().find((a) => a.kpId === kpId) ?? null
  }
  /** 指针进入悬停工具：别让它消失 */
  function holdHover(): void {
    clearHoverTimer()
  }
  function releaseHover(): void {
    clearHoverTimer()
    hoverTimer = setTimeout(() => {
      hover.value = null
    }, HOVER_LINGER_MS)
  }
  function openMenu(info: { kpId: string; x: number; y: number }): void {
    if (connect.value !== null) return
    edgeTool.value = null
    hover.value = null
    clearHoverTimer()
    menu.value = { kpId: info.kpId, at: { x: info.x, y: info.y } }
  }
  function menuAction(action: 'detail' | 'edit' | 'connect' | 'delete'): void {
    const target = menu.value
    if (target === null) return
    menu.value = null
    if (action === 'detail') onDetail(target.kpId)
    else if (action === 'edit') onEdit(target.kpId)
    else if (action === 'delete') onDelete(target.kpId)
    else connect.value = { phase: 'picking', from: target.kpId }
  }

  // ---------------------------------------------------------------- 连线
  function choose(from: string, to: string, at: Point): void {
    connect.value = { phase: 'choosing', from, to, at, prerequisiteBlocked: prerequisiteWouldCycle(edgesNow(), from, to) }
  }
  /** 点选连线时的节点点击：已被连线流程用掉返回 true，页面不再切换选中 */
  function consumeNodeClick(kpId: string): boolean {
    const state = connect.value
    if (state === null) return false
    if (state.phase !== 'picking') return true
    if (kpId === state.from) return true
    const anchor = anchors().find((a) => a.kpId === kpId)
    choose(state.from, kpId, anchor === undefined ? { x: 0, y: 0 } : { x: anchor.x, y: anchor.y })
    return true
  }
  function startDrag(from: NodeAnchor, pointer: Point): void {
    if (busy.value) return
    dragAnchors = anchors()
    menu.value = null
    edgeTool.value = null
    hover.value = null
    clearHoverTimer()
    connect.value = { phase: 'dragging', from: from.kpId, start: { x: from.x, y: from.y }, pointer, target: null, cycle: false }
  }
  function dragTo(pointer: Point): void {
    const state = connect.value
    if (state === null || state.phase !== 'dragging') return
    const target = nodeAt(dragAnchors, pointer.x, pointer.y, { exclude: state.from })
    connect.value = { ...state, pointer, target, cycle: target !== null && prerequisiteWouldCycle(edgesNow(), state.from, target.kpId) }
  }
  function endDrag(): void {
    const state = connect.value
    if (state === null || state.phase !== 'dragging') return
    if (state.target === null) connect.value = null
    else choose(state.from, state.target.kpId, { x: state.target.x, y: state.target.y })
  }
  async function confirmType(type: RelationType): Promise<void> {
    const state = connect.value
    if (state === null || state.phase !== 'choosing' || busy.value) return
    if (type === 'PREREQUISITE' && state.prerequisiteBlocked) return
    connect.value = null
    await relations.createBetween(state.from, state.to, type)
  }

  onScopeDispose(() => {
    clearHoverTimer()
    if (undoTimer !== null) clearTimeout(undoTimer)
  })

  return {
    edgeTool,
    edgeRow,
    menu,
    hover,
    connect,
    undo,
    undoError,
    busy,
    nameOf,
    dismiss,
    onViewChange,
    openEdge,
    changeEdgeType,
    reverseEdge,
    deleteEdge,
    undoDelete,
    dismissUndo: clearUndo,
    onNodeHover,
    holdHover,
    releaseHover,
    openMenu,
    menuAction,
    consumeNodeClick,
    startDrag,
    dragTo,
    endDrag,
    confirmType,
  }
}

export type CanvasEditing = ReturnType<typeof useCanvasEditing>
