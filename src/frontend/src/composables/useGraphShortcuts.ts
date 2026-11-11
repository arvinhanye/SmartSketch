import { onBeforeUnmount, onMounted } from 'vue'

/**
 * 图谱快捷键（UI-GRAPH-FIND-01）：`/` 聚焦搜索，`F` 适应画布，`+`/`=` 放大，`-` 缩小。
 *
 * 画布不是 Tab 停靠点（见规格「图谱画布键盘约定」），快捷键挂在窗口上，是效率路径而非唯一路径。
 * 焦点在输入控件或可编辑区域内、带 Ctrl/⌘/Alt、输入法组合中、事件已被处理时都不触发。
 */
export type ShortcutAction = 'search' | 'fit' | 'zoomIn' | 'zoomOut'

const KEYS: Readonly<Record<string, ShortcutAction>> = Object.freeze({
  '/': 'search',
  f: 'fit',
  F: 'fit',
  '+': 'zoomIn',
  '=': 'zoomIn',
  '-': 'zoomOut',
})

function isEditable(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  const tag = target.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable || target.getAttribute('contenteditable') === 'true'
}

/** 这次按键对应的动作；不该触发时返回 null */
export function shortcutAction(event: KeyboardEvent): ShortcutAction | null {
  if (event.defaultPrevented || event.isComposing || event.ctrlKey || event.metaKey || event.altKey) return null
  if (isEditable(event.target)) return null
  return KEYS[event.key] ?? null
}

/** 处理函数返回 false 表示这次没有处理（如画布未就绪），按键照常交给浏览器 */
export function useGraphShortcuts(handlers: Partial<Record<ShortcutAction, () => boolean | void>>): void {
  function onKeydown(event: KeyboardEvent): void {
    const action = shortcutAction(event)
    if (action === null) return
    const handler = handlers[action]
    if (handler === undefined || handler() === false) return
    event.preventDefault()
  }
  onMounted(() => window.addEventListener('keydown', onKeydown))
  onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
}
