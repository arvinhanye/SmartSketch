/**
 * 教师图谱布局偏好（层次 / 径向 / 力导向）：按课程记在本浏览器里，只是便利设置。
 * 浏览器存储可能不可用（隐私窗口、被清除、被禁用），读写一律吞掉异常，页面照常按推荐值工作。
 * 存的只有布局名，不含任何账号或课程内容；换浏览器、换设备不会同步。
 */
export type Arrangement = 'hierarchical' | 'radial' | 'force'

const PREFIX = 'smartsketch.teacher-graph.arrangement.'
const VALID: readonly Arrangement[] = ['hierarchical', 'radial', 'force']

export function readArrangement(courseId: string | null): Arrangement | null {
  if (courseId === null) return null
  try {
    const value = window.localStorage.getItem(PREFIX + courseId)
    return VALID.find((item) => item === value) ?? null
  } catch {
    return null
  }
}

export function writeArrangement(courseId: string | null, value: Arrangement): void {
  if (courseId === null) return
  try {
    window.localStorage.setItem(PREFIX + courseId, value)
  } catch {
    /* 存储不可用：偏好只在本次页面内生效 */
  }
}
