import { computed, onScopeDispose, ref, watch, type Ref } from 'vue'
import type { CourseMember, MembersApi } from '../api/members'
import { AbortedError, ApiError, NetworkError, TimeoutError } from '../api/http'
import { useCourseStore, type CourseRequestScope } from '../stores/course'

/**
 * 课程成员管理状态（H12）：成员列表四态、按用户名添加学生、移除学生成员。
 *
 * - 视图只拿 `MemberRow` 视图模型，不接触后端原始 `CourseMember`。
 * - 路由 `cid` 经 `useCourseStore().selectCourse` 成为当前课程；列表与增删请求都在 `beginRequest()`
 *   作用域内发出并经 `commit` 提交，切课后旧课程的晚到响应被丢弃、在途请求随 signal 取消。
 * - 防重复：添加与移除都用同步标志防重入（两次事件可能在按钮禁用渲染前连续到达）；
 *   添加接口对已是成员幂等返回原行（200），此处按 `user_id` 去重，不会出现两行，也不改原角色。
 * - 错误只按状态码/错误码给固定文案，不回显服务端 message；`COURSE_FORBIDDEN` 交给调用方回课程列表
 *   （`errors.v1.md`），`ROLE_FORBIDDEN` 明确提示无权限且不重试。
 * - 授权以后端为准（`specs/identity-access.md` §2.4、§3.3）：前端只对学生成员显示移除按钮。
 */

export type MemberRole = CourseMember['role']

export interface MemberRow {
  userId: string
  username: string
  role: MemberRole
  roleLabel: string
  /** ISO 8601 加入时间，视图用 `<time datetime>` 展示 */
  joinedAt: string
  joinedLabel: string
  /** 只能移除学生成员（§3.3）；教师成员只能用命令行调整 */
  removable: boolean
}

const ROLE_LABEL: Record<MemberRole, string> = { teacher: '教师', student: '学生' }

function formatJoined(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

export function toMemberRow(member: CourseMember): MemberRow {
  return {
    userId: member.user_id,
    username: member.username,
    role: member.role,
    roleLabel: ROLE_LABEL[member.role],
    joinedAt: member.created_at,
    joinedLabel: formatJoined(member.created_at),
    removable: member.role === 'student',
  }
}

export type MembersStatus = 'loading' | 'ready' | 'error' | 'forbidden'

const NETWORK_MESSAGE = '无法连接服务器，请检查网络后重试。'
const ROLE_FORBIDDEN_MESSAGE = '无权管理成员：只有本课程的教师成员可以查看和调整成员。'
const SESSION_EXPIRED_MESSAGE = '登录已失效，请重新登录。'

function isNetworkFailure(cause: unknown): boolean {
  return cause instanceof NetworkError || cause instanceof TimeoutError
}

function isCourseForbidden(cause: unknown): boolean {
  return cause instanceof ApiError && cause.code === 'COURSE_FORBIDDEN'
}

export interface UseMembersOptions {
  api: MembersApi
  /** 当前路由中的课程 ID */
  courseId: Ref<string | null>
  /** 返回 `COURSE_FORBIDDEN`（不是成员或已被移出）：当前课程已清空，调用方负责回课程列表 */
  onCourseForbidden: () => void
}

export function useMembers({ api, courseId, onCourseForbidden }: UseMembersOptions) {
  const store = useCourseStore()
  let disposed = false

  function courseForbidden(): void {
    store.selectCourse(null)
    onCourseForbidden()
  }

  /** 开启当前课程的请求作用域；未选课程时返回 null */
  function beginScope(): CourseRequestScope | null {
    return store.courseId === null ? null : store.beginRequest()
  }

  // ------------------------------------------------------------ 列表
  const members = ref<MemberRow[]>([])
  const status = ref<MembersStatus>('loading')
  const listError = ref<string | null>(null)

  function listErrorMessage(cause: unknown): string {
    if (cause instanceof ApiError && cause.status === 401) return SESSION_EXPIRED_MESSAGE
    if (isNetworkFailure(cause)) return NETWORK_MESSAGE
    return '成员列表加载失败，请稍后重试。'
  }

  async function loadMembers(): Promise<void> {
    const scope = beginScope()
    if (scope === null) return
    status.value = 'loading'
    listError.value = null
    try {
      const result = await api.list(scope.courseId, { signal: scope.signal })
      store.commit(scope, () => {
        members.value = result.map(toMemberRow)
        status.value = 'ready'
      })
    } catch (cause) {
      if (disposed || !scope.isCurrent() || cause instanceof AbortedError) return
      if (isCourseForbidden(cause)) return courseForbidden()
      store.commit(scope, () => {
        if (cause instanceof ApiError && cause.code === 'ROLE_FORBIDDEN') {
          status.value = 'forbidden'
          listError.value = ROLE_FORBIDDEN_MESSAGE
          return
        }
        status.value = 'error'
        listError.value = listErrorMessage(cause)
      })
    }
  }

  const hasStudents = computed(() => members.value.some((m) => m.role === 'student'))
  const isEmpty = computed(() => status.value === 'ready' && !hasStudents.value)

  // ------------------------------------------------------------ 添加
  const username = ref('')
  const adding = ref(false)
  const addError = ref<string | null>(null)
  const addNotice = ref<string | null>(null)
  let addInFlight = false

  function addErrorMessage(cause: unknown): string {
    if (cause instanceof ApiError) {
      if (cause.status === 404) return '未找到该用户，或该账号已停用。请核对用户名。'
      if (cause.code === 'ROLE_FORBIDDEN') return ROLE_FORBIDDEN_MESSAGE
      if (cause.status === 422) return '用户名不符合要求，请检查后重试。'
      if (cause.status === 401) return SESSION_EXPIRED_MESSAGE
    }
    if (isNetworkFailure(cause)) return NETWORK_MESSAGE
    return '添加成员失败，请稍后重试。'
  }

  async function addMember(): Promise<void> {
    if (addInFlight) return
    const name = username.value.trim()
    addNotice.value = null
    if (name === '') {
      addError.value = '请输入学生用户名。'
      return
    }
    const scope = beginScope()
    if (scope === null) return
    addInFlight = true
    adding.value = true
    addError.value = null
    try {
      const added = await api.add(scope.courseId, { username: name }, { signal: scope.signal })
      store.commit(scope, () => {
        const row = toMemberRow(added)
        const existing = members.value.findIndex((m) => m.userId === row.userId)
        if (existing >= 0) {
          // 已是成员：接口返回原行（角色不变），以它刷新本行，不新增
          members.value.splice(existing, 1, row)
          addNotice.value = `「${row.username}」已是课程成员（${row.roleLabel}），未重复添加。`
        } else {
          members.value.push(row)
          addNotice.value = `已添加学生「${row.username}」。`
        }
        username.value = ''
      })
    } catch (cause) {
      if (disposed || !scope.isCurrent() || cause instanceof AbortedError) return
      if (isCourseForbidden(cause)) return courseForbidden()
      addError.value = addErrorMessage(cause)
    } finally {
      addInFlight = false
      adding.value = false
    }
  }

  // ------------------------------------------------------------ 移除
  const removing = ref<ReadonlySet<string>>(new Set())
  const removeError = ref<string | null>(null)
  const removeNotice = ref<string | null>(null)
  const removeInFlight = new Set<string>()

  function setRemoving(userId: string, on: boolean): void {
    const next = new Set(removing.value)
    if (on) next.add(userId)
    else next.delete(userId)
    removing.value = next
  }

  function dropRow(userId: string): void {
    members.value = members.value.filter((m) => m.userId !== userId)
  }

  function removeErrorMessage(cause: unknown): string {
    if (cause instanceof ApiError) {
      if (cause.code === 'ROLE_FORBIDDEN') return '无权移除该成员：教师成员不能移除，且只有本课程的教师成员可以操作。'
      if (cause.status === 401) return SESSION_EXPIRED_MESSAGE
    }
    if (isNetworkFailure(cause)) return NETWORK_MESSAGE
    return '移除成员失败，请稍后重试。'
  }

  async function removeMember(row: MemberRow): Promise<void> {
    if (!row.removable || removeInFlight.has(row.userId)) return
    const scope = beginScope()
    if (scope === null) return
    removeInFlight.add(row.userId)
    setRemoving(row.userId, true)
    removeError.value = null
    removeNotice.value = null
    try {
      await api.remove(scope.courseId, row.userId, { signal: scope.signal })
      store.commit(scope, () => {
        dropRow(row.userId)
        removeNotice.value = `已将「${row.username}」移出课程。`
      })
    } catch (cause) {
      if (disposed || !scope.isCurrent() || cause instanceof AbortedError) return
      if (isCourseForbidden(cause)) return courseForbidden()
      if (cause instanceof ApiError && cause.status === 404) {
        // 目标已不是成员（可能已被其他操作移除）：与服务端对齐
        dropRow(row.userId)
        removeNotice.value = `「${row.username}」已不是课程成员，已从列表中移除。`
        return
      }
      removeError.value = removeErrorMessage(cause)
    } finally {
      removeInFlight.delete(row.userId)
      setRemoving(row.userId, false)
    }
  }

  // ------------------------------------------------------------ 切课
  watch(
    courseId,
    (id) => {
      store.selectCourse(id)
      members.value = []
      username.value = ''
      addError.value = null
      addNotice.value = null
      removeError.value = null
      removeNotice.value = null
      removeInFlight.clear()
      removing.value = new Set()
      void loadMembers()
    },
    { immediate: true },
  )

  onScopeDispose(() => {
    disposed = true
  })

  return {
    members,
    status,
    listError,
    isEmpty,
    loadMembers,
    username,
    adding,
    addError,
    addNotice,
    addMember,
    removing,
    removeError,
    removeNotice,
    removeMember,
  }
}
