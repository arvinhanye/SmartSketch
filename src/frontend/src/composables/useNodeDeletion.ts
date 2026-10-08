import { ref, type Ref } from 'vue'
import type {
  KnowledgeDetailApi,
  KnowledgePointDeletion,
} from '../api/knowledgeDetail'

/**
 * 知识点删除流程（F09 扩展，ADR-092）。
 *
 * 交互分两步，避免误删：
 *  1. `open()` 拉取**只读删除影响预览**，把「会删掉哪些知识点、多少条关系」摊开给教师看；
 *  2. 教师选择「仅删此节点」或「连同会变成孤儿的后代一起删」，`confirm(cascade)` 才真正删除。
 *
 * 级联与否**由教师每次选择**，不提供默认整批删除；预览在打开弹窗时取一次，
 * 因此弹窗里显示的数量就是即将删除的数量。
 *
 * 只做流程与状态；错误按 B15 的错误类型原样抛出并转成文案，不在这里拼 HTTP 细节。
 */

export interface UseNodeDeletionOptions {
  api: KnowledgeDetailApi
  /** 路由给出的课程 ID；未就绪（`null`）时删除会被拒绝，不会发出请求 */
  courseId: Ref<string | null>
  /** 删除成功后的回调（页面据此刷新图谱并清空选中） */
  onDeleted?: (kpId: string, impact: KnowledgePointDeletion | null) => void
  /** 删除成功但后台要求重新登录/进入课程时的回调；与详情面板的一致 */
  onCourseForbidden?: () => void
}

export type DeletionStatus = 'idle' | 'loading' | 'ready' | 'deleting' | 'error'

export function useNodeDeletion(options: UseNodeDeletionOptions) {
  const kpId = ref<string | null>(null)
  const status = ref<DeletionStatus>('idle')
  const impact = ref<KnowledgePointDeletion | null>(null)
  const error = ref<string | null>(null)

  function reset(): void {
    kpId.value = null
    status.value = 'idle'
    impact.value = null
    error.value = null
  }

  /** 打开确认弹窗：取预览，成功后才进入 `ready`。 */
  async function open(id: string): Promise<void> {
    const cid = options.courseId.value
    if (cid === null) return
    kpId.value = id
    impact.value = null
    error.value = null
    status.value = 'loading'
    try {
      impact.value = await options.api.deleteImpact(cid, id)
      status.value = 'ready'
    } catch (cause) {
      error.value = message(cause)
      status.value = 'error'
    }
  }

  function close(): void {
    if (status.value === 'deleting') return
    reset()
  }

  /** 真正删除；`cascade` 由教师在上一步选择。返回是否删除成功。 */
  async function confirm(cascade: boolean): Promise<boolean> {
    const id = kpId.value
    const cid = options.courseId.value
    if (id === null || cid === null) return false
    status.value = 'deleting'
    error.value = null
    try {
      const result = await options.api.remove(cid, id, { cascade })
      options.onDeleted?.(id, result)
      reset()
      return true
    } catch (cause) {
      error.value = message(cause)
      // 保留 kpId 与已有预览，让教师能重试或改选另一种删除方式
      status.value = 'ready'
      if ((cause as { status?: number } | null)?.status === 403) options.onCourseForbidden?.()
      return false
    }
  }

  return { kpId, status, impact, error, open, close, confirm, reset }
}

function message(cause: unknown): string {
  const status = (cause as { status?: number } | null)?.status
  if (status === 403) return '你没有删除该知识点的权限。'
  if (status === 404) return '该知识点已不存在，可能已被他人删除。'
  if (status === 409) return '课程正在被其他操作写入或被他人修改，请刷新后重试。'
  return '删除失败，请稍后重试。'
}
