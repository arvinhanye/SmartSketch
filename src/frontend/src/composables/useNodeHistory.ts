import { onScopeDispose, watch, type Ref } from 'vue'
import { ApiError, NetworkError, TimeoutError } from '../api/http'
import type { KnowledgePoint, KnowledgePointUpdate, NodeEditApi } from '../api/nodeEdit'
import { useCourseStore, type CourseRequestScope } from '../stores/course'
import type { EditHistory, HistoryResult } from './useEditHistory'

const FIELDS = ['name', 'aliases', 'type', 'definition', 'importance', 'difficulty', 'status'] as const

interface Options {
  api: NodeEditApi
  history: EditHistory
  courseId: Readonly<Ref<string | null>>
  refresh(): Promise<boolean>
  reloadEditor(kpId: string): Promise<boolean>
  onCourseForbidden(): void
}

function failureReason(cause: unknown): string {
  if (cause instanceof ApiError) {
    if (cause.code === 'REVISION_CONFLICT') return '知识点已被修改，请核对最新内容。'
    if (cause.code === 'NOT_FOUND') return '知识点已不存在。'
    if (cause.code === 'COURSE_BUSY') return '课程正在进行其他写入，请稍后重试。'
    if (cause.code === 'ROLE_FORBIDDEN' || cause.code === 'UNAUTHENTICATED') return '当前身份无法修改该知识点。'
  }
  if (cause instanceof NetworkError || cause instanceof TimeoutError) return '网络异常，请核对实际保存状态。'
  return '知识点写入未完成，请核对最新内容。'
}

/** 节点反向写入、部分成功后的同步与课程隔离；页面只负责接线。 */
export function useNodeHistory({ api, history, courseId, refresh, reloadEditor, onCourseForbidden }: Options) {
  const store = useCourseStore()
  let disposed = false
  let generation = 0
  let controller: AbortController | null = null

  function cancel(): void {
    generation += 1
    controller?.abort()
    controller = null
  }
  watch(courseId, cancel, { flush: 'sync' })
  onScopeDispose(() => { disposed = true; cancel() })

  function syncNode(scope: CourseRequestScope, node: KnowledgePoint): void {
    const graph = store.graph
    if (graph === null) return
    store.setGraph(scope, { ...graph, nodes: graph.nodes.map(n => n.id === node.id ? { ...n, ...node } : n) })
  }

  async function apply(kpId: string, fields: Partial<KnowledgePointUpdate>, keepLocked: boolean): Promise<HistoryResult> {
    const currentNode = store.graph?.nodes.find(n => n.id === kpId)
    if (disposed || courseId.value === null || courseId.value !== store.courseId || currentNode === undefined) return false
    cancel()
    const owner = generation
    const scope = store.beginRequest()
    const own = new AbortController()
    controller = own
    const abort = () => own.abort()
    scope.signal.addEventListener('abort', abort, { once: true })
    if (scope.signal.aborted) own.abort()
    const current = () => !disposed && owner === generation && !own.signal.aborted && scope.isCurrent() && courseId.value === scope.courseId
    const adopt = (node: KnowledgePoint): void => {
      if (node?.id !== kpId || node.course_id !== scope.courseId || !Number.isInteger(node.revision)) throw new Error('invalid node response')
      syncNode(scope, node)
    }
    let reason = ''
    let stage: 'update' | 'unlock' = 'update'
    try {
      try {
        // onSaved 仅在 changed 非空时建立历史；契约的“至少一个字段”联合类型无法从动态 pick 推断。
        const body = { ...fields, expected_revision: currentNode.revision } as KnowledgePointUpdate
        let saved = await api.update(scope.courseId, kpId, body, { signal: own.signal })
        if (!current()) return false
        adopt(saved)
        if (!keepLocked && saved.locked) {
          stage = 'unlock'
          saved = await api.unlock(scope.courseId, kpId, saved.revision, { signal: own.signal })
          if (!current()) return false
          adopt(saved)
          if (saved.locked) throw new Error('unlock not confirmed')
        }
      } catch (cause) {
        if (!current()) return false
        if (cause instanceof ApiError && cause.code === 'COURSE_FORBIDDEN') {
          store.selectCourse(null)
          onCourseForbidden()
          return false
        }
        reason = (stage === 'unlock' ? '字段已写入，但解锁未完成。' : '') + failureReason(cause)
      }

      // 写入报错也可能已经改变后端；读回实际状态。两次写入和两次读回均属于同一次历史操作。
      const graphSynced = await refresh()
      if (!current()) return false
      const editorSynced = await reloadEditor(kpId)
      if (!current()) return false
      if (!graphSynced || !editorSynced) reason += '未能完整读取最新状态，请重新加载后核对。'
      return reason === '' ? true : { ok: false, reason }
    } finally {
      scope.signal.removeEventListener('abort', abort)
      if (controller === own) controller = null
    }
  }

  function onSaved(after: KnowledgePoint, before?: KnowledgePoint): void {
    // 成功解锁、或不能逆转的字段保存也属于新写入，必须使旧重做失效。
    history.invalidateRedo()
    if (before === undefined) return
    const value = (node: KnowledgePoint, key: (typeof FIELDS)[number]) => key === 'aliases' ? node.aliases ?? [] : node[key]
    const changed = FIELDS.filter(key => JSON.stringify(value(before, key) ?? null) !== JSON.stringify(value(after, key) ?? null))
    if (changed.length === 0 || changed.some(key => key !== 'aliases' && before[key] === undefined)) return
    const pick = (node: KnowledgePoint): Partial<KnowledgePointUpdate> => Object.fromEntries(changed.map(key => [key, value(node, key)]))
    history.record({
      label: `修改知识点「${before.name}」`,
      undo: () => apply(after.id, pick(before), before.locked),
      redo: () => apply(after.id, pick(after), true),
    })
  }

  return { onSaved }
}
