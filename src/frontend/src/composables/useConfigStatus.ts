/** 本机 API 配置状态：没配好时引导用户去「API 设置」，不假装还能用。 */

import { ref } from 'vue'

export interface ConfigStatus {
  ready: boolean
  configured: boolean
  restart_needed: boolean
  missing: string[]
}

/** 未完成配置时对用户说的唯一一句话 */
export const NOT_CONFIGURED_MESSAGE = '请先完成 API 设置'

const status = ref<ConfigStatus | null>(null)
let inflight: Promise<ConfigStatus | null> | null = null
let checkedAt = 0

/** 缓存时间：够短，改完设置返回页面就能立刻看到效果 */
const TTL_MS = 5000

export async function refreshConfigStatus(token: string | null, force = false): Promise<ConfigStatus | null> {
  const fresh = Date.now() - checkedAt < TTL_MS
  if (!force && fresh && status.value !== null) return status.value
  if (inflight !== null) return inflight
  inflight = (async () => {
    try {
      const response = await fetch('/api/v1/api-settings/status', {
        headers: { Authorization: `Bearer ${token ?? ''}` },
        signal: AbortSignal.timeout(8000),
      })
      if (!response.ok) return null
      const next = (await response.json()) as ConfigStatus
      status.value = next
      checkedAt = Date.now()
      return next
    } catch {
      // 读不到状态时不拦人：宁可让页面自己报错，也不要因为一次网络抖动把用户锁在设置页
      return null
    } finally {
      inflight = null
    }
  })()
  return inflight
}

export function configStatus(): ConfigStatus | null {
  return status.value
}

export function resetConfigStatus(): void {
  status.value = null
  checkedAt = 0
}

/** 应用外壳注入的令牌读取函数（避免这里反向依赖 store，也方便路由守卫调用） */
export type TokenReader = () => string | null
let readToken: TokenReader = () => null

export function bindConfigStatusToken(reader: TokenReader): void {
  readToken = reader
}

/** 是否已确认「没配好」；读不到状态时返回 false，不拦人 */
export async function apiConfigured(): Promise<boolean> {
  const next = await refreshConfigStatus(readToken())
  return next === null || next.ready !== false
}

/** 需要先完成 API 设置才能用的页面（登录、注册与设置页本身不在此列） */
export const EXEMPT_ROUTES: readonly string[] = ['api-settings', 'root', 'register']

export function requiresConfiguredApi(routeName: string | null | undefined): boolean {
  return Boolean(routeName) && !EXEMPT_ROUTES.includes(routeName as string)
}
