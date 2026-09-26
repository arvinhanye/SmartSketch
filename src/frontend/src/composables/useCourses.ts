import { computed, onScopeDispose, ref, shallowRef, watch, type Ref } from 'vue'
import type { Course, CourseCreate, CoursesApi } from '../api/courses'
import { AbortedError, ApiError, NetworkError, TimeoutError } from '../api/http'
import { useCourseStore } from '../stores/course'

/**
 * 课程首页状态（H01）：课程列表四态、创建表单防重入、按路由 `cid` 切换当前课程。
 *
 * - 视图只拿 `CourseCard` 视图模型，不接触后端原始 `Course`。
 * - 当前课程经 `useCourseStore().selectCourse` 切换；详情请求用 `beginRequest()` 作用域，
 *   结果经 `commit` 提交，切课后旧课程晚到的响应被丢弃，在途请求随作用域 signal 取消。
 * - 错误只按状态码/错误类型给固定文案，不回显服务端 message。
 * - `canCreate` 只是界面引导（`specs/identity-access.md` §2.4），授权以后端 403 为准。
 */

export type CourseRole = Course['my_role']

export interface CourseCard {
  id: string
  name: string
  description: string | null
  myRole: CourseRole
  roleLabel: string
  statusLabel: string
  knowledgePointCount: number
}

const ROLE_LABEL: Record<CourseRole, string> = { teacher: '教师', student: '学生' }
const STATUS_LABEL: Record<Course['status'], string> = { draft: '草稿', published: '已发布', revising: '修订中' }

export const COURSE_NAME_MAX = 120
export const COURSE_DESCRIPTION_MAX = 1000

export function toCourseCard(course: Course): CourseCard {
  const description = course.description?.trim() ?? ''
  return {
    id: course.id,
    name: course.name,
    description: description === '' ? null : description,
    myRole: course.my_role,
    roleLabel: ROLE_LABEL[course.my_role],
    statusLabel: STATUS_LABEL[course.status],
    knowledgePointCount: course.kp_count ?? 0,
  }
}

const NETWORK_MESSAGE = '无法连接服务器，请检查网络后重试。'

function isNetworkFailure(cause: unknown): boolean {
  return cause instanceof NetworkError || cause instanceof TimeoutError
}

export type ListStatus = 'loading' | 'ready' | 'error' | 'forbidden'
export type CurrentStatus = 'idle' | 'loading' | 'ready' | 'error'

export interface UseCoursesOptions {
  api: CoursesApi
  /** 当前路由中的课程 ID；`null` 表示在课程列表（首页） */
  courseId: Ref<string | null>
  /** 是否显示创建表单（账号类型为教师）；只是界面引导 */
  canCreate: Ref<boolean>
  /** 当前课程返回 `COURSE_FORBIDDEN`：当前课程已清空，调用方负责回课程列表 */
  onCourseForbidden: () => void
}

export function useCourses({ api, courseId, canCreate, onCourseForbidden }: UseCoursesOptions) {
  const store = useCourseStore()

  // ------------------------------------------------------------ 列表
  const courses = ref<CourseCard[]>([])
  const listStatus = ref<ListStatus>('loading')
  const listError = ref<string | null>(null)
  let listController: AbortController | null = null

  async function loadCourses(): Promise<void> {
    listController?.abort()
    const controller = new AbortController()
    listController = controller
    listStatus.value = 'loading'
    listError.value = null
    try {
      const result = await api.list({ signal: controller.signal })
      if (listController !== controller) return
      courses.value = result.map(toCourseCard)
      listStatus.value = 'ready'
    } catch (cause) {
      if (listController !== controller || cause instanceof AbortedError) return
      if (cause instanceof ApiError && cause.status === 403) {
        listStatus.value = 'forbidden'
        listError.value = '当前账号无权查看课程列表。'
        return
      }
      listStatus.value = 'error'
      listError.value = isNetworkFailure(cause) ? NETWORK_MESSAGE : '课程列表加载失败，请稍后重试。'
    }
  }

  const isEmpty = computed(() => listStatus.value === 'ready' && courses.value.length === 0)

  // ------------------------------------------------------------ 创建
  const form = ref({ name: '', description: '' })
  const creating = ref(false)
  const createError = ref<string | null>(null)
  const createdName = ref<string | null>(null)
  // 防重入用同步标志：两次 submit 事件可能在一次渲染（按钮禁用）之前连续到达
  let inFlight = false

  function createErrorMessage(cause: unknown): string {
    if (cause instanceof ApiError) {
      if (cause.status === 403) return '当前账号无权创建课程。'
      if (cause.status === 422) return '课程信息未通过校验，请检查课程名与简介。'
      if (cause.status === 401) return '登录已失效，请重新登录。'
    }
    if (isNetworkFailure(cause)) return NETWORK_MESSAGE
    return '创建课程失败，请稍后重试。'
  }

  async function createCourse(): Promise<void> {
    if (inFlight || !canCreate.value) return
    const name = form.value.name.trim()
    const description = form.value.description.trim()
    createdName.value = null
    if (name === '') {
      createError.value = '请输入课程名称。'
      return
    }
    if (name.length > COURSE_NAME_MAX) {
      createError.value = `课程名称不能超过 ${COURSE_NAME_MAX} 个字符。`
      return
    }
    if (description.length > COURSE_DESCRIPTION_MAX) {
      createError.value = `课程简介不能超过 ${COURSE_DESCRIPTION_MAX} 个字符。`
      return
    }
    const body: CourseCreate = description === '' ? { name } : { name, description }
    inFlight = true
    creating.value = true
    createError.value = null
    try {
      const created = await api.create(body)
      const card = toCourseCard(created)
      // 列表处于加载/错误态时不改其状态：之后的加载或重试结果本就包含新课程
      courses.value = [card, ...courses.value.filter((c) => c.id !== card.id)]
      form.value = { name: '', description: '' }
      createdName.value = card.name
    } catch (cause) {
      createError.value = createErrorMessage(cause)
    } finally {
      inFlight = false
      creating.value = false
    }
  }

  // ------------------------------------------------------------ 当前课程
  const current = shallowRef<CourseCard | null>(null)
  const currentStatus = ref<CurrentStatus>('idle')
  const currentError = ref<string | null>(null)

  function currentErrorMessage(cause: unknown): string {
    if (cause instanceof ApiError) {
      if (cause.status === 404 && cause.code === 'GRAPH_NOT_PUBLISHED') return '该课程尚未发布，暂时无法查看。'
      if (cause.status === 404) return '课程不存在。'
    }
    if (isNetworkFailure(cause)) return NETWORK_MESSAGE
    return '课程加载失败，请稍后重试。'
  }

  function openCourse(id: string | null): void {
    store.selectCourse(id)
    current.value = null
    currentError.value = null
    if (id === null) {
      currentStatus.value = 'idle'
      return
    }
    const scope = store.beginRequest()
    currentStatus.value = 'loading'
    api.get(id, { signal: scope.signal }).then(
      (detail) => {
        store.commit(scope, () => {
          if (detail.id !== scope.courseId) {
            currentStatus.value = 'error'
            currentError.value = '课程加载失败，请稍后重试。'
            return
          }
          current.value = toCourseCard(detail)
          currentStatus.value = 'ready'
        })
      },
      (cause: unknown) => {
        if (!scope.isCurrent() || cause instanceof AbortedError) return
        if (cause instanceof ApiError && cause.code === 'COURSE_FORBIDDEN') {
          store.selectCourse(null)
          currentStatus.value = 'idle'
          onCourseForbidden()
          return
        }
        store.commit(scope, () => {
          currentStatus.value = 'error'
          currentError.value = currentErrorMessage(cause)
        })
      },
    )
  }

  watch(courseId, openCourse, { immediate: true })
  void loadCourses()

  onScopeDispose(() => {
    listController?.abort()
    listController = null
  })

  return {
    courses,
    listStatus,
    listError,
    isEmpty,
    loadCourses,
    form,
    creating,
    createError,
    createdName,
    createCourse,
    current,
    currentStatus,
    currentError,
    selectedId: computed(() => store.courseId),
  }
}
