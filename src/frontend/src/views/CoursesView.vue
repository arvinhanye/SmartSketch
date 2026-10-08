<script setup lang="ts">
import { computed, inject, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter, type RouteLocationRaw } from 'vue-router'
import PageSheet from '../components/PageSheet.vue'
import PageHeader from '../components/PageHeader.vue'
import AppIcon from '../components/AppIcon.vue'
import CourseList from '../components/courses/CourseList.vue'
import CourseOverview from '../components/courses/CourseOverview.vue'
import CourseCreate from '../components/courses/CourseCreate.vue'
import { MATERIALS_API_KEY } from '../api/materials'
import { useRuntimeStore } from '../stores/runtime'
import { COURSES_API_KEY } from '../api/courses'
import { courseNextStep, useCourses } from '../composables/useCourses'
import {
  COURSE_MEMBERS_ROUTE,
  COURSE_ROUTE,
  homeRouteFor,
  MATERIALS_ROUTE,
  NOTICE_COURSE_FORBIDDEN,
  ROOT_ROUTE,
  STUDENT_GRAPH_ROUTE,
  TEACHER_GRAPH_ROUTE,
  REVIEW_ROUTE,
  CHAT_ROUTE,
  SETTINGS_ROUTE,
} from '../router'
import { useSessionStore } from '../stores/session'

const api = inject(COURSES_API_KEY, null)
if (api === null) throw new Error('CoursesView 需要注入 COURSES_API_KEY')

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const runtime = useRuntimeStore()
const materialsApi = inject(MATERIALS_API_KEY, null)

const courseId = computed(() => {
  const cid = route.params.cid
  return route.name === COURSE_ROUTE && typeof cid === 'string' && cid !== '' ? cid : null
})
// 创建表单只对教师账号显示；授权以后端为准（学生提交会得到 403 ROLE_FORBIDDEN）
const canCreate = computed(() => session.role === 'teacher')

const {
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
  selectedId,
} = useCourses({
  api,
  materialsApi,
  sessionKey: computed(() => session.accessToken),
  courseId,
  canCreate,
  // errors.v1.md：COURSE_FORBIDDEN 提示无权限并返回课程列表
  onCourseForbidden: () => {
    const role = session.role
    void router.replace(
      role === null ? { name: ROOT_ROUTE } : { name: homeRouteFor(role), query: { notice: NOTICE_COURSE_FORBIDDEN } },
    )
  },
})

// H12：成员管理入口只给本课教师成员，且仅在注册了成员路由时显示；学生无入口
// H12：成员管理入口只给本课教师成员，且仅在注册了成员路由时显示；学生无入口
const hasMembersRoute = router.hasRoute(COURSE_MEMBERS_ROUTE)
// 资料页（H02）只对课程内教师显示入口；未注册资料路由时不显示
const hasMaterials = router.hasRoute(MATERIALS_ROUTE)
const hasChat = router.hasRoute(CHAT_ROUTE)
// 学生图谱页（H11）只对课程内学生显示入口；页面只读已发布版本
const hasStudentGraph = router.hasRoute(STUDENT_GRAPH_ROUTE)
// 教师图谱编辑页（H14）只对课程内教师显示入口；页面只读写草稿
const hasTeacherGraph = router.hasRoute(TEACHER_GRAPH_ROUTE)
// 审核队列页（H09）只对课程内教师显示入口
const hasReview = router.hasRoute(REVIEW_ROUTE)

const nextStep = computed(() => current.value ? courseNextStep({ ...current.value, materialCount: materialCount.value }, runtime.needsConfig) : null)
const actionRoutes = {settings: SETTINGS_ROUTE, materials: MATERIALS_ROUTE, review: REVIEW_ROUTE, teacherGraph: TEACHER_GRAPH_ROUTE, studentGraph: STUDENT_GRAPH_ROUTE}
const actionLabels = {settings: '配置模型 API', materials: '上传与检查资料', review: '审核并发布', teacherGraph: '维护课程图谱', studentGraph: '浏览图谱与学习路径'}
const nextLink = computed(() => {
  const action = nextStep.value?.action
  if (!action || !current.value || !router.hasRoute(actionRoutes[action])) return null
  return { to: {name: actionRoutes[action], ...(action === 'settings' ? {} : {params: {cid: current.value.id}})}, label: actionLabels[action] }
})
const courseForbidden = computed(() => route.query.notice === NOTICE_COURSE_FORBIDDEN)
const createOpen = ref(false)
const createButton = ref<HTMLButtonElement | null>(null)
const highlightedId = ref<string | null>(null)
const copyStatus = ref('')
watch(() => session.accessToken, () => {
  copyStatus.value = ''
  createOpen.value = false
  highlightedId.value = null
}, { flush: 'sync' })
function closeCreate(): void {
  if (creating.value) return
  createOpen.value = false
  void nextTick(() => createButton.value?.focus())
}
async function submitCourse(): Promise<void> {
  await createCourse()
  if (createdName.value !== null) {
    highlightedId.value = courses.value[0]?.id ?? null
    closeCreate()
  }
}
async function copyUsername(): Promise<void> {
  const username = session.user?.username
  const token = session.accessToken
  if (!username) return
  try {
    await navigator.clipboard.writeText(username)
    if (session.accessToken === token) copyStatus.value = '用户名已复制。'
  } catch {
    if (session.accessToken === token) copyStatus.value = `复制失败，请手动复制用户名「${username}」。`
  }
}
const entryLinks = computed(() => {
  const c = current.value
  if (!c) return []
  const entries: Array<{test:string;label:string;description:string;icon:string;to:RouteLocationRaw}> = []
  const add = (visible:boolean,name:string,test:string,label:string,description:string,icon:string) => {
    if (visible) entries.push({test,label,description,icon,to:{name,params:{cid:c.id}}})
  }
  add(hasStudentGraph && c.myRole === 'student',STUDENT_GRAPH_ROUTE,'student-graph-link','浏览课程图谱','查看知识点、掌握进度与学习路径。','graph')
  add(hasTeacherGraph && c.myRole === 'teacher',TEACHER_GRAPH_ROUTE,'teacher-graph-link','编辑课程图谱（草稿）','检查与维护知识点及其关系。','graph')
  add(hasReview && c.myRole === 'teacher',REVIEW_ROUTE,'review-link','审核队列','审核抽取结果并发布课程图谱。','check')
  add(hasMaterials && c.myRole === 'teacher',MATERIALS_ROUTE,'materials-link','资料上传与处理进度','上传课程资料，查看处理状态。','chapters')
  add(hasChat && c.myRole === 'student',CHAT_ROUTE,'chat-link','课程问答','依据已发布资料提问并查看出处。','chat')
  add(hasMembersRoute && c.myRole === 'teacher',COURSE_MEMBERS_ROUTE,'members-link','管理成员','添加课程成员并管理课程内身份。','overview')
  return entries
})
</script>

<template>
 <PageSheet labelledby="courses-title" class="courses">
  <PageHeader id="courses-title" :title="courseId ? '课程概览' : '我的课程'" :description="courseId ? undefined : canCreate ? '管理课程资料、图谱与成员。' : '从课程图谱开始，查看知识点与学习路径。'">
   <template v-if="canCreate" #actions><button ref="createButton" type="button" class="ui-btn ui-btn--primary" data-test="course-create-open" :aria-expanded="createOpen" aria-controls="course-create-panel" :disabled="creating" @click="createOpen ? closeCreate() : createOpen = true"><AppIcon name="plus" :size="16" />新建课程</button></template>
  </PageHeader>
  <p v-if="courseForbidden" data-test="course-forbidden" class="ui-notice ui-notice--danger" role="alert">你无权访问该课程（可能已被移出课程），已返回课程列表。</p>
  <p v-if="createdName" data-test="create-success" class="ui-notice ui-notice--success" role="status">已创建课程「{{ createdName }}」。</p>
  <CourseCreate v-if="canCreate && createOpen" :form="form" :creating="creating" :error="createError" @submit="submitCourse" @cancel="closeCreate" />
  <section v-if="courseId !== null" class="ui-current" data-test="current-course" aria-labelledby="current-course-title" :aria-busy="currentStatus === 'loading'">
   <p v-if="currentStatus === 'loading'" role="status">正在加载课程…</p>
   <p v-else-if="currentStatus === 'error'" data-test="current-course-error" class="ui-notice ui-notice--danger" role="alert">{{ currentError }}</p>
   <CourseOverview v-else-if="current" :current="current" :next-step="nextStep?.text ?? null" :next-link="nextLink" :links="entryLinks" />
  </section>
  <section class="ui-list-region" data-test="course-list-region" aria-labelledby="course-list-title" :aria-busy="listStatus === 'loading'">
   <div class="ui-section-heading"><h3 id="course-list-title">{{ courseId ? '其他课程' : '课程列表' }}</h3><span v-if="listStatus === 'ready'" class="ui-muted">{{ courses.length }} 门课程</span></div>
   <div v-if="listStatus === 'loading'" data-test="courses-loading" class="ui-state" role="status"><p>正在加载课程…</p><div v-for="i in 3" :key="i" class="ui-skeleton" aria-hidden="true" /></div>
   <p v-else-if="listStatus === 'forbidden'" data-test="courses-forbidden" class="ui-notice ui-notice--danger" role="alert">{{ listError }}</p>
   <div v-else-if="listStatus === 'error'" class="ui-state"><p data-test="courses-error" role="alert">{{ listError }}</p><button type="button" class="ui-btn" data-test="courses-retry" @click="loadCourses">重试</button></div>
   <div v-else-if="isEmpty" class="ui-empty"><span class="ui-empty__icon"><AppIcon name="chapters" :size="28" /></span><p data-test="courses-empty">{{ canCreate ? '暂无课程。新建第一门课程，开始上传资料。' : `你还没有加入任何课程。请把用户名「${session.user?.username ?? ''}」告诉任课教师，由教师在「成员」中添加你；发布后即可学习。` }}</p><button v-if="canCreate" type="button" class="ui-btn ui-btn--primary" @click="createOpen = true">新建第一门课程</button><button v-else type="button" class="ui-btn" data-test="course-copy-username" @click="copyUsername">复制用户名</button><p v-if="copyStatus" data-test="course-copy-status" role="status">{{ copyStatus }}</p></div>
   <CourseList v-else :courses="courses" :selected-id="selectedId" :highlighted-id="highlightedId" />
  </section>
 </PageSheet>
</template>
