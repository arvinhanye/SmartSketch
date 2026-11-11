import { onScopeDispose, ref, watch, type Ref } from 'vue'
import type { KnowledgeDeletionApi, KnowledgePointDeletion } from '../api/knowledgeDetail'

export interface UseNodeDeletionOptions {
  api: KnowledgeDeletionApi
  courseId: Ref<string | null>
  selectedId?: Ref<string | null>
  identity?: Ref<string | null>
  onDeleted?: (id: string, impact: KnowledgePointDeletion | null) => void | Promise<void>
  onCourseForbidden?: () => void
}
export type DeletionStatus = 'idle' | 'loading' | 'ready' | 'deleting' | 'error'

/** ADR-097: a preview belongs to one request generation, course, identity and node. */
export function useNodeDeletion(options: UseNodeDeletionOptions) {
  const kpId = ref<string | null>(null)
  const status = ref<DeletionStatus>('idle')
  const impact = ref<KnowledgePointDeletion | null>(null)
  const error = ref<string | null>(null)
  let generation = 0
  let controller: AbortController | null = null
  let targetCourse: string | null = null
  let disposed = false

  function reset(): void {
    generation += 1
    controller?.abort()
    controller = null
    targetCourse = null
    kpId.value = null
    impact.value = null
    error.value = null
    status.value = 'idle'
  }
  const current = (serial: number, cid: string, kid: string) =>
    !disposed && generation === serial && options.courseId.value === cid && targetCourse === cid && kpId.value === kid

  async function open(id: string): Promise<void> {
    if (disposed || status.value === 'deleting') return
    reset()
    const cid = options.courseId.value
    if (cid === null || (options.identity !== undefined && options.identity.value === null)) return
    const serial = generation
    targetCourse = cid
    kpId.value = id
    controller = new AbortController()
    status.value = 'loading'
    try {
      const result = await options.api.deleteImpact(cid, id, { signal: controller.signal })
      if (!current(serial, cid, id)) return
      if (result.root_id !== id) throw new Error('preview target mismatch')
      impact.value = result
      status.value = 'ready'
    } catch (cause) {
      if (!current(serial, cid, id)) return
      impact.value = null
      status.value = 'error'
      error.value = message(cause)
      if (httpStatus(cause) === 403 || httpStatus(cause) === 401) options.onCourseForbidden?.()
    }
  }

  function close(): void {
    if (status.value !== 'deleting') reset()
  }

  async function confirm(cascade = false): Promise<boolean> {
    const id = kpId.value
    const cid = targetCourse
    const preview = impact.value
    const serial = generation
    if (id === null || cid === null || preview === null || status.value !== 'ready'
      || preview.root_id !== id || !current(serial, cid, id)) return false
    status.value = 'deleting'
    error.value = null
    let result: KnowledgePointDeletion | null
    try {
      result = await options.api.remove(cid, id, {
        cascade, previewToken: preview.preview_token, expectedRevision: preview.root_revision, signal: controller?.signal,
      })
    } catch (cause) {
      if (!current(serial, cid, id)) return false
      impact.value = null
      status.value = 'error'
      error.value = message(cause)
      if (httpStatus(cause) === 409) {
        // Never repeat the delete automatically. The refreshed plan needs a new click.
        const refreshed = open(id)
        const refreshGeneration = generation
        await refreshed
        if (current(refreshGeneration, cid, id) && impact.value !== null) {
          error.value = '图谱已变化，已重新计算删除影响，请重新确认。'
        }
      } else if (httpStatus(cause) === 403 || httpStatus(cause) === 401) {
        options.onCourseForbidden?.()
      }
      return false
    }
    if (!current(serial, cid, id)) return false
    reset()
    await options.onDeleted?.(id, result)
    return true
  }

  watch(options.courseId, reset, { flush: 'sync' })
  if (options.selectedId) watch(options.selectedId, reset, { flush: 'sync' })
  if (options.identity) watch(options.identity, reset, { flush: 'sync' })
  onScopeDispose(() => { disposed = true; reset() })
  return { kpId, status, impact, error, open, close, confirm, reset }
}

function httpStatus(cause: unknown): number | undefined {
  return (cause as { status?: number } | null)?.status
}
function message(cause: unknown): string {
  if (httpStatus(cause) === 403 || httpStatus(cause) === 401) return '当前账号已无权操作此课程。'
  if (httpStatus(cause) === 404) return '知识点已不存在，请刷新图谱。'
  if (httpStatus(cause) === 409) return '图谱已变化，请重新预览并确认。'
  return '操作结果尚未确认，请重新预览并核对图谱后再操作。'
}
