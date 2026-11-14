import { computed, onBeforeUnmount, onMounted, onScopeDispose, ref, shallowRef } from 'vue'

/**
 * 撤销 / 重做记录（UI-GRAPH-UNDO-04）。
 *
 * 后端没有通用撤销接口，所以每一步都自带“怎么撤销、怎么重做”的反向操作（再发一次请求）。这里只管顺序与状态：
 * - 后进先出；做了新操作后重做记录清空；最多保留 `HISTORY_LIMIT` 步，只在页面内存里；
 * - 一次只做一步：进行中、或外部有写请求在途时，撤销和重做都不执行；
 * - 反向操作失败（被后端拒绝、对象已不在、网络）时这一步直接移除并说明，不重试，不影响更早的步骤。
 */
export const HISTORY_LIMIT = 50

export type HistoryResult = boolean | { ok: boolean; reason: string }

export interface HistoryStep {
  /** 这一步做了什么，用在按钮说明和提示里，如“删除关系 A → B（包含）” */
  label: string
  /** 执行反向操作；返回是否成功 */
  undo(): Promise<HistoryResult>
  /** 把这一步重新做一遍；返回是否成功 */
  redo(): Promise<HistoryResult>
}

export interface UseEditHistoryOptions {
  /** 外部是否有写请求在途（此时不执行撤销 / 重做） */
  busy?: () => boolean
  /** 在窗口上绑定 Ctrl/⌘+Z、Ctrl/⌘+Shift+Z、Ctrl+Y（需在组件 setup 里调用） */
  shortcuts?: boolean
  limit?: number
}

function isEditable(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  const tag = target.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable || target.getAttribute('contenteditable') === 'true'
}

export function useEditHistory(options: UseEditHistoryOptions = {}) {
  const limit = options.limit ?? HISTORY_LIMIT
  let generation = 0
  let disposed = false
  const undoStack = shallowRef<HistoryStep[]>([])
  const redoStack = shallowRef<HistoryStep[]>([])
  const working = ref(false)
  const notice = shallowRef<{ tone: 'success' | 'error'; text: string } | null>(null)

  const canUndo = computed(() => undoStack.value.length > 0)
  const canRedo = computed(() => redoStack.value.length > 0)
  const undoLabel = computed(() => undoStack.value.at(-1)?.label ?? null)
  const redoLabel = computed(() => redoStack.value.at(-1)?.label ?? null)
  const blocked = () => disposed || working.value || options.busy?.() === true

  function invalidateRedo(): void {
    redoStack.value = []
  }

  function record(step: HistoryStep): void {
    if (disposed) return
    undoStack.value = [...undoStack.value, step].slice(-limit)
    invalidateRedo()
  }

  async function run(kind: 'undo' | 'redo'): Promise<boolean> {
    const from = kind === 'undo' ? undoStack : redoStack
    const to = kind === 'undo' ? redoStack : undoStack
    const step = from.value.at(-1)
    if (blocked() || step === undefined) return false
    const owner = generation
    working.value = true
    from.value = from.value.slice(0, -1)
    let ok = false
    let reason = ''
    try {
      const result = await (kind === 'undo' ? step.undo() : step.redo())
      ok = typeof result === 'boolean' ? result : result.ok
      reason = typeof result === 'boolean' ? '' : result.reason
    } catch {
      ok = false
    } finally {
      if (owner === generation) working.value = false
    }
    if (disposed || owner !== generation) return false
    if (ok) {
      to.value = [...to.value, step].slice(-limit)
      notice.value = { tone: 'success', text: `${kind === 'undo' ? '已撤销' : '已重做'}：${step.label}` }
    } else {
      notice.value = {
        tone: 'error',
        text: (kind === 'undo' ? `未撤销：${step.label}。这一步已从撤销记录中移除。` : `未重做：${step.label}。这一步已从记录中移除。`) + reason,
      }
    }
    return ok
  }

  function clear(): void {
    generation += 1
    working.value = false
    undoStack.value = []
    redoStack.value = []
    notice.value = null
  }

  onScopeDispose(() => {
    disposed = true
    clear()
  })

  if (options.shortcuts === true) {
    const onKeydown = (event: KeyboardEvent): void => {
      if (event.defaultPrevented || event.isComposing || event.altKey || !(event.ctrlKey || event.metaKey)) return
      // 输入控件里的 Ctrl/⌘+Z 是浏览器自己的文字撤销
      if (isEditable(event.target)) return
      const key = event.key.toLowerCase()
      const kind = key === 'z' ? (event.shiftKey ? 'redo' : 'undo') : key === 'y' && event.ctrlKey && !event.shiftKey ? 'redo' : null
      if (kind === null) return
      if (kind === 'undo' ? !canUndo.value : !canRedo.value) return
      event.preventDefault()
      void run(kind)
    }
    onMounted(() => window.addEventListener('keydown', onKeydown))
    onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
  }

  return {
    canUndo,
    canRedo,
    undoLabel,
    redoLabel,
    working,
    notice,
    record,
    invalidateRedo,
    undo: () => run('undo'),
    redo: () => run('redo'),
    clear,
    dismissNotice: () => {
      notice.value = null
    },
  }
}

export type EditHistory = ReturnType<typeof useEditHistory>
