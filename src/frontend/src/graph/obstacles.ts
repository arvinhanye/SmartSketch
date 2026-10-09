import { inject, onBeforeUnmount, onMounted, type InjectionKey, type Ref } from 'vue'
import type { Box } from './labelPlan'

/**
 * 浮层障碍物注册表（UI-GRAPH-PILOT-01，规格 §4 第 1 层）。
 *
 * 工具栏、搜索栏、图例、小地图、底部折叠条、预览卡、提示条会盖在画布上。标签排布与镜头适应要避开它们，
 * 所以浮层组件把自己的根元素登记进来，画布按当前屏幕位置取包围盒。
 * - `hard`：标签与镜头适应都要避开；
 * - `soft`（如可展开的图例）：只有标签避开，镜头适应不为它缩小范围。
 */
export type ObstacleKind = 'hard' | 'soft'

export interface ObstacleRegistry {
  /** 登记元素，返回注销函数 */
  register(el: HTMLElement, kind?: ObstacleKind): () => void
  /** 相对 `base` 元素左上角的包围盒（四周外扩 6px，留出标签与浮层之间的间隙）；尺寸为 0 的元素忽略 */
  boxes(base: HTMLElement): { hard: Box[]; soft: Box[] }
  /** 登记、注销或元素尺寸变化时通知；返回取消订阅函数 */
  onChange(listener: () => void): () => void
}

const PAD = 6

export function createObstacleRegistry(): ObstacleRegistry {
  const items = new Map<HTMLElement, ObstacleKind>()
  const listeners = new Set<() => void>()
  let observer: ResizeObserver | null = null
  const notify = () => listeners.forEach((listener) => listener())

  return {
    register(el, kind = 'hard') {
      items.set(el, kind)
      if (typeof ResizeObserver === 'function') {
        observer ??= new ResizeObserver(notify)
        observer.observe(el)
      }
      notify()
      return () => {
        if (!items.delete(el)) return
        observer?.unobserve(el)
        notify()
      }
    },
    boxes(base) {
      const origin = base.getBoundingClientRect()
      const out: { hard: Box[]; soft: Box[] } = { hard: [], soft: [] }
      for (const [el, kind] of items) {
        const r = el.getBoundingClientRect()
        if (r.width <= 0 || r.height <= 0) continue
        out[kind].push([r.left - origin.left - PAD, r.top - origin.top - PAD, r.right - origin.left + PAD, r.bottom - origin.top + PAD])
      }
      return out
    },
    onChange(listener) {
      listeners.add(listener)
      return () => {
        listeners.delete(listener)
      }
    },
  }
}

/** 页面提供、画布与浮层注入；不提供时画布不做浮层避让 */
export const GRAPH_OBSTACLES_KEY: InjectionKey<ObstacleRegistry> = Symbol('graph-obstacles')

/** 浮层组件内使用：挂载时登记根元素，卸载时注销；没有注册表时什么都不做 */
export function useGraphObstacle(el: Ref<HTMLElement | null>, kind: ObstacleKind = 'hard'): void {
  const registry = inject(GRAPH_OBSTACLES_KEY, null)
  let off: (() => void) | null = null
  onMounted(() => {
    if (registry !== null && el.value !== null) off = registry.register(el.value, kind)
  })
  onBeforeUnmount(() => off?.())
}
