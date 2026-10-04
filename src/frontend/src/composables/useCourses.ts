import { computed, onScopeDispose, ref, shallowRef, watch, type Ref } from 'vue'
import type { MaterialsApi } from '../api/materials'
import type { Course, CourseCreate, CoursesApi } from '../api/courses'
import { AbortedError, ApiError, NetworkError, TimeoutError } from '../api/http'
import { readCourseDetail } from './courseDetailRequest'
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
  status: Course['status']
  publishedVersion: number | null
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
    status: course.status,
    publishedVersion: course.published_version ?? null,
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
  materialsApi?: Pick<MaterialsApi, 'list'> | null
  sessionKey?: Ref<string | null>
  /** 当前路由中的课程 ID；`null` 表示在课程列表（首页） */
  courseId: Ref<string | null>
  /** 是否显示创建表单（账号类型为教师）；只是界面引导 */
  canCreate: Ref<boolean>
  /** 当前课程返回 `COURSE_FORBIDDEN`：当前课程已清空，调用方负责回课程列表 */
  onCourseForbidden: () => void
}

export function useCourses({ api, materialsApi, sessionKey, courseId, canCreate, onCourseForbidden }: UseCoursesOptions) {
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
  let createGeneration = 0
  let createController: AbortController | null = null
  watch(() => sessionKey?.value ?? null, () => {
    createGeneration++
    createController?.abort()
    createController = null
    inFlight = false
    creating.value = false
    form.value = { name: '', description: '' }
    createError.value = null
    createdName.value = null
  }, { flush: 'sync' })

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
    const owner = createGeneration
    const key = sessionKey?.value ?? null
    const controller = new AbortController()
    createController = controller
    const isCurrent = () => !disposed && owner === createGeneration && key === (sessionKey?.value ?? null)
    inFlight = true
    creating.value = true
    createError.value = null
    try {
      const created = await api.create(body, { signal: controller.signal })
      if (!isCurrent()) return
      const card = toCourseCard(created)
      // 列表处于加载/错误态时不改其状态：之后的加载或重试结果本就包含新课程
      courses.value = [card, ...courses.value.filter((c) => c.id !== card.id)]
      form.value = { name: '', description: '' }
      createdName.value = card.name
    } catch (cause) {
      if (isCurrent()) createError.value = createErrorMessage(cause)
    } finally {
      if (isCurrent()) {
        createController = null
        inFlight = false
        creating.value = false
      }
    }
  }

  // ------------------------------------------------------------ 当前课程
  const materialCount = ref<number | null>(null)
  let openSequence = 0
  let disposed = false
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
    const sequence = ++openSequence
    materialCount.value = null
    store.selectCourse(id)
    current.value = null
    currentError.value = null
    if (id === null) {
      currentStatus.value = 'idle'
      return
    }
    const scope = store.beginRequest()
    currentStatus.value = 'loading'
    readCourseDetail(api, id, scope.signal).then(
      (detail) => {
        if (disposed || sequence !== openSequence) return
        store.commit(scope, () => {
          if (detail.id !== scope.courseId) {
            currentStatus.value = 'error'
            currentError.value = '课程加载失败，请稍后重试。'
            return
          }
          store.setRole(scope, detail.my_role)
          current.value = toCourseCard(detail)
          currentStatus.value = 'ready'
          if (detail.my_role === 'teacher' && materialsApi) {
            void materialsApi.list(id, { signal: scope.signal }).then((items) => {
              if (!disposed && sequence === openSequence) store.commit(scope, () => { materialCount.value = items.length })
            }, () => { /* 未知数目，不误报无资料。 */ })
          }
        })
      },
      (cause: unknown) => {
        if (disposed || sequence !== openSequence || !scope.isCurrent() || cause instanceof AbortedError) return
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

  watch([courseId, () => sessionKey?.value ?? null], ([cid], old) => {
    openCourse(cid)
    if (old.length > 0 && old[1] !== (sessionKey?.value ?? null)) { courses.value = []; void loadCourses() }
  }, { immediate: true })
  void loadCourses()

  onScopeDispose(() => {
    disposed = true
    createController?.abort()
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
    materialCount,
    currentStatus,
    currentError,
    selectedId: computed(() => store.courseId),
  }
}

export type CourseAction = 'settings' | 'materials' | 'review' | 'teacherGraph' | 'studentGraph'
export function courseNextStep(input: { myRole: CourseRole; status: Course['status']; publishedVersion: number | null; materialCount: number | null }, needsConfig: boolean): {stage: string; text: string; action: CourseAction | null} {
  const { myRole, status, publishedVersion, materialCount } = input
  const published = publishedVersion !== null
  if (myRole === 'student') {
    if (!published) return { stage: 'waiting_teacher', text: '等待教师发布课程图谱。', action: null }
    return { stage: 'published', text: `第 ${publishedVersion} 版已发布，可浏览图谱与学习路径。${needsConfig ? '提问前请配置个人模型 API。' : ''}`, action: 'studentGraph' }
  }
  if (published && status === 'revising') return { stage: 'waiting_publish', text: `草稿修订中，学生仍看到第 ${publishedVersion} 版；请审核并发布。`, action: 'review' }
  if (published) return { stage: 'published', text: `学生看到第 ${publishedVersion} 版；可继续维护课程图谱。`, action: 'teacherGraph' }
  if (needsConfig) return { stage: 'needs_config', text: '先配置个人模型 API，再上传课程资料。', action: 'settings' }
  if (materialCount === 0) return { stage: 'no_material', text: '尚无资料，请上传课程资料。', action: 'materials' }
  return { stage: 'drafting', text: materialCount === null ? '前往资料页检查处理进度，再审核发布。' : '资料已上传；检查处理进度，审核草稿并发布。', action: materialCount === null ? 'materials' : 'review' }
}
