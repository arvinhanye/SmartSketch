/**
 * 面板宽度偏好（UI-GRAPH-FIND-01）：记在本浏览器里，只是便利设置，只存一个数字。
 * 浏览器存储可能不可用（隐私窗口、被清除、被禁用），读写一律吞掉异常，页面照常按默认宽度工作。
 */
const PREFIX = 'smartsketch.panel-width.'

export type PanelWidthKey = 'student-graph' | 'teacher-graph'

export function readPanelWidth(key: PanelWidthKey): number | null {
  try {
    const raw = window.localStorage.getItem(PREFIX + key)
    if (raw === null || raw.trim() === '') return null
    const value = Number(raw)
    return Number.isFinite(value) && value > 0 ? value : null
  } catch {
    return null
  }
}

export function writePanelWidth(key: PanelWidthKey, value: number): void {
  if (!Number.isFinite(value) || value <= 0) return
  try {
    window.localStorage.setItem(PREFIX + key, String(Math.round(value * 100) / 100))
  } catch {
    /* 存储不可用：宽度只在本次页面内生效 */
  }
}
