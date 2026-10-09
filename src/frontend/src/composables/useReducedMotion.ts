import { onBeforeUnmount, ref, type Ref } from 'vue'

/**
 * `prefers-reduced-motion: reduce` 的响应式读取（规格 §8、§9）：图谱镜头动画与淡入据此关闭。
 * 没有 `matchMedia` 的环境（部分测试）视为不减少动效。
 */
export function useReducedMotion(): Ref<boolean> {
  const reduced = ref(false)
  if (typeof matchMedia !== 'function') return reduced
  const query = matchMedia('(prefers-reduced-motion: reduce)')
  reduced.value = query.matches
  const onChange = (event: MediaQueryListEvent) => {
    reduced.value = event.matches
  }
  query.addEventListener?.('change', onChange)
  onBeforeUnmount(() => query.removeEventListener?.('change', onChange))
  return reduced
}
