import { onScopeDispose, watch, type Ref } from 'vue'

interface Options<T> {
  /** 显示多久后自动关闭（毫秒）。 */
  ms: number
  /** 返回 true 的提示不会自动关闭（例如错误，需要用户看清并自己关闭）。 */
  keep?: (value: T) => boolean
}

/**
 * 提示出现后过一段时间自动关闭。新提示出现会重新计时，所以快速连续的操作不会被上一条的计时器提前关掉；
 * 作用域销毁时清除计时器。
 */
export function useAutoDismiss<T>(source: Ref<T | null>, dismiss: () => void, { ms, keep }: Options<T>): void {
  let timer: ReturnType<typeof setTimeout> | undefined
  const clear = () => {
    if (timer !== undefined) clearTimeout(timer)
    timer = undefined
  }
  watch(source, (value) => {
    clear()
    if (value === null || keep?.(value)) return
    timer = setTimeout(() => {
      timer = undefined
      dismiss()
    }, ms)
  })
  onScopeDispose(clear)
}
