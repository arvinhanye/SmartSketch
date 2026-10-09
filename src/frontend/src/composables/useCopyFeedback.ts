import { onBeforeUnmount, ref } from 'vue'

export interface CopyFeedbackOptions {
  write?: (text: string) => Promise<void>
  successMs?: number
}

/** 复制并给出可见反馈：成功提示数秒后消失，失败提示保留到下一次操作（失败时用户需要手动复制） */
export function useCopyFeedback({ write, successMs = 3000 }: CopyFeedbackOptions = {}) {
  const state = ref<{ id: number; ok: boolean } | null>(null)
  let timer: ReturnType<typeof setTimeout> | null = null
  const clear = (): void => {
    if (timer !== null) clearTimeout(timer)
    timer = null
  }
  async function copy(id: number, text: string): Promise<void> {
    clear()
    try {
      if (write !== undefined) await write(text)
      else if (typeof navigator !== 'undefined' && navigator.clipboard) await navigator.clipboard.writeText(text)
      else throw new Error('clipboard unavailable')
      state.value = { id, ok: true }
      timer = setTimeout(() => {
        state.value = null
        timer = null
      }, successMs)
    } catch {
      state.value = { id, ok: false }
    }
  }
  onBeforeUnmount(clear)
  return { state, copy }
}
