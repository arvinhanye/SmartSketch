import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import { useCourseStore } from './course'

type LoginResponse = components['schemas']['LoginResponse']
type User = components['schemas']['User']
type Role = components['schemas']['Role']

/** sessionStorage 中的会话键；值为 `{ access_token, user }` 的 JSON */
export const SESSION_STORAGE_KEY = 'smartsketch.session'

const ROLES: ReadonlySet<string> = new Set<Role>(['teacher', 'student'])

interface StoredSession {
  access_token: string
  user: User
}

function isNonBlank(value: unknown): value is string {
  return typeof value === 'string' && value.trim() !== ''
}

function parseStored(raw: string): StoredSession | null {
  let value: unknown
  try {
    value = JSON.parse(raw)
  } catch {
    return null
  }
  if (typeof value !== 'object' || value === null) return null
  const { access_token: token, user } = value as Record<string, unknown>
  if (!isNonBlank(token) || typeof user !== 'object' || user === null) return null
  const { id, username, role } = user as Record<string, unknown>
  if (!isNonBlank(id) || typeof username !== 'string' || typeof role !== 'string' || !ROLES.has(role)) return null
  return { access_token: token, user: { id, username, role: role as Role } }
}

// sessionStorage 在隐私模式或配额满时可能抛错；读写失败时会话只留在内存里
function readStorage(): StoredSession | null {
  try {
    const raw = sessionStorage.getItem(SESSION_STORAGE_KEY)
    if (raw === null) return null
    const parsed = parseStored(raw)
    if (parsed === null) sessionStorage.removeItem(SESSION_STORAGE_KEY)
    return parsed
  } catch {
    return null
  }
}

function writeStorage(value: StoredSession | null): void {
  try {
    if (value === null) sessionStorage.removeItem(SESSION_STORAGE_KEY)
    else sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(value))
  } catch {
    // 忽略：内存中的会话仍然有效，只是刷新页面后需要重新登录
  }
}

/**
 * 当前标签页的登录会话（H13，`specs/identity-access.md` §2.4）。
 *
 * 令牌与 `LoginResponse.user` 只存 sessionStorage，不存 localStorage、不写 Cookie，
 * 因此同一浏览器的不同标签页可以分别登录。`role` 只用于界面引导，授权以后端为准。
 * 登录、退出与会话过期都会清空课程上下文（`useCourseStore().selectCourse(null)`），
 * 上一账号签发的课程作用域随之失效（审查遗留 B04-R01）。
 */
export const useSessionStore = defineStore('session', () => {
  const course = useCourseStore()
  const stored = readStorage()
  const accessToken = ref<string | null>(stored?.access_token ?? null)
  const user = ref<User | null>(stored?.user ?? null)
  const role = computed<Role | null>(() => user.value?.role ?? null)

  function signIn(response: LoginResponse): void {
    course.selectCourse(null)
    const next: StoredSession = {
      access_token: response.access_token,
      user: { id: response.user.id, username: response.user.username, role: response.user.role },
    }
    accessToken.value = next.access_token
    user.value = next.user
    writeStorage(next)
  }

  function signOut(): void {
    course.selectCourse(null)
    accessToken.value = null
    user.value = null
    writeStorage(null)
  }

  return { accessToken, user, role, signIn, signOut }
})
