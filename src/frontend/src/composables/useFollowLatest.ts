import { onBeforeUnmount, onMounted, ref } from 'vue'

const NEAR_BOTTOM_PX = 120

export interface FollowLatestOptions {
  /** 减少动效时「回到最新」不用平滑滚动；缺省读取系统设置 */
  reducedMotion?: () => boolean
}

function systemReduced(): boolean {
  return typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
}

/**
 * 对话页的滚动跟随（页面整体滚动在 window）：用户在底部时新内容自动滚到最新；
 * 用户上翻阅读时不强拉，只置 `behind` 让页面显示「回到最新」（UI-QA-01 F5）。
 */
export function useFollowLatest({ reducedMotion = systemReduced }: FollowLatestOptions = {}) {
  const behind = ref(false)
  let following = true
  const bottomGap = (): number => document.documentElement.scrollHeight - (window.scrollY + window.innerHeight)
  const onScroll = (): void => {
    following = bottomGap() <= NEAR_BOTTOM_PX
    if (following) behind.value = false
  }
  const toBottom = (behavior: ScrollBehavior): void => window.scrollTo({ top: document.documentElement.scrollHeight, behavior })

  function contentChanged(): void {
    if (following) toBottom('auto')
    else behind.value = true
  }
  function scrollToLatest(): void {
    following = true
    behind.value = false
    toBottom(reducedMotion() ? 'auto' : 'smooth')
  }
  onMounted(() => window.addEventListener('scroll', onScroll, { passive: true }))
  onBeforeUnmount(() => window.removeEventListener('scroll', onScroll))
  return { behind, contentChanged, scrollToLatest }
}
