<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { COURSES_API_KEY, type CourseIntelligence, type CoursesApi } from '../api/courses'
import { COURSE_DESCRIPTION_MAX, COURSE_NAME_MAX, useCourses } from '../composables/useCourses'
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
} from '../router'
import { useSessionStore } from '../stores/session'

const injected = inject(COURSES_API_KEY, null)
if (injected === null) throw new Error('CoursesView 需要注入 COURSES_API_KEY')
const api: CoursesApi = injected

const route = useRoute()
const router = useRouter()
const session = useSessionStore()

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
  currentStatus,
  currentError,
  selectedId,
} = useCourses({
  api,
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

const courseForbidden = computed(() => route.query.notice === NOTICE_COURSE_FORBIDDEN)

/** 当前课程的智能功能状态：旧演示向量需要用户主动重新处理资料 */
const intelligence = ref<CourseIntelligence | null>(null)
const reprocessing = ref(false)
const reprocessMessage = ref('')
const needsReprocess = computed(() => intelligence.value?.needs_reprocess === true)

async function loadIntelligence(): Promise<void> {
  const cid = courseId.value
  reprocessMessage.value = ''
  if (cid === null || api.intelligence === undefined) { intelligence.value = null; return }
  try {
    intelligence.value = await api.intelligence(cid)
  } catch {
    // 状态读不到时不打扰用户：页面本身仍可用
    intelligence.value = null
  }
}
async function startReprocess(): Promise<void> {
  const cid = courseId.value
  if (cid === null || reprocessing.value || api.reprocess === undefined) return
  reprocessing.value = true
  reprocessMessage.value = ''
  try {
    const result = await api.reprocess(cid)
    reprocessMessage.value = `已提交重新处理（${result.count} 份资料），进度可在「教学资料」中查看。`
    await loadIntelligence()
  } catch (error) {
    reprocessMessage.value = error instanceof Error ? error.message : '提交失败，请稍后重试。'
  } finally {
    reprocessing.value = false
  }
}

watch(courseId, () => { void loadIntelligence() }, { immediate: true })
</script>

<template>
  <div class="page courses" aria-labelledby="courses-title">
    <header class="page__heading">
      <h2 id="courses-title">我的课程</h2>
      <p class="page__lede">选择一门课程进入课程工作台；教师可以在下方创建新课程。</p>
    </header>

    <p v-if="courseForbidden" data-test="course-forbidden" role="alert">
      你无权访问该课程（可能已被移出课程），已返回课程列表。
    </p>

    <section
      v-if="courseId !== null"
      class="surface-card current"
      data-test="current-course"
      aria-labelledby="current-course-title"
      :aria-busy="currentStatus === 'loading'"
    >
      <h3 id="current-course-title">当前课程</h3>
      <p v-if="currentStatus === 'loading'" role="status">正在加载课程…</p>
      <p v-else-if="currentStatus === 'error'" data-test="current-course-error" role="alert">{{ currentError }}</p>
      <template v-else-if="current">
        <p class="current-name">{{ current.name }}</p>
        <p>
          课程内身份：{{ current.roleLabel }}（{{ current.myRole === 'teacher' ? '教师视图' : '学生视图' }}）
          · 状态：{{ current.statusLabel }}
        </p>
        <p v-if="current.description">{{ current.description }}</p>
        <!-- 旧数据是演示向量：不能直接当在线数据用，要求用户主动重新处理资料 -->
        <div v-if="needsReprocess" class="intelligence-note" data-test="course-needs-reprocess" role="status">
          <p>{{ intelligence?.message || '这门课程需要重新处理资料后才能使用智能功能。' }}</p>
          <button
            v-if="current.myRole === 'teacher' && intelligence?.can_reprocess"
            type="button"
            :disabled="reprocessing"
            data-test="course-reprocess"
            @click="startReprocess"
          >
            {{ reprocessing ? '正在提交…' : '重新处理资料' }}
          </button>
          <p v-if="reprocessMessage" class="intelligence-note__result" data-test="reprocess-result">{{ reprocessMessage }}</p>
        </div>
        <p v-if="hasStudentGraph && current.myRole === 'student'">
          <RouterLink data-test="student-graph-link" :to="{ name: STUDENT_GRAPH_ROUTE, params: { cid: current.id } }">
            浏览课程图谱
          </RouterLink>
        </p>
        <p v-if="hasTeacherGraph && current.myRole === 'teacher'">
          <RouterLink data-test="teacher-graph-link" :to="{ name: TEACHER_GRAPH_ROUTE, params: { cid: current.id } }">
            编辑课程图谱（草稿）
          </RouterLink>
        </p>
        <p v-if="hasReview && current.myRole === 'teacher'">
          <RouterLink data-test="review-link" :to="{ name: REVIEW_ROUTE, params: { cid: current.id } }">
            审核队列
          </RouterLink>
        </p>
        <p v-if="hasMaterials && current.myRole === 'teacher'">
          <RouterLink data-test="materials-link" :to="{ name: MATERIALS_ROUTE, params: { cid: current.id } }">
            资料上传与处理进度
          </RouterLink>
        </p>
        <p v-if="hasChat && current.myRole === 'student'">
          <RouterLink :to="{ name: CHAT_ROUTE, params: { cid: current.id } }">课程问答</RouterLink>
        </p>
        <p v-if="hasMembersRoute && current.myRole === 'teacher'">
          <RouterLink data-test="members-link" :to="{ name: COURSE_MEMBERS_ROUTE, params: { cid: current.id } }">
            管理成员
          </RouterLink>
        </p>
      </template>
    </section>

    <section
      class="surface-card list"
      data-test="course-list-region"
      aria-labelledby="course-list-title"
      :aria-busy="listStatus === 'loading'"
    >
      <h3 id="course-list-title">课程列表</h3>
      <p v-if="listStatus === 'loading'" data-test="courses-loading" role="status">正在加载课程…</p>
      <p v-else-if="listStatus === 'forbidden'" data-test="courses-forbidden" role="alert">{{ listError }}</p>
      <div v-else-if="listStatus === 'error'">
        <p data-test="courses-error" role="alert">{{ listError }}</p>
        <button type="button" data-test="courses-retry" @click="loadCourses">重试</button>
      </div>
      <p v-else-if="isEmpty" data-test="courses-empty">
        暂无课程。{{ canCreate ? '可在下方创建第一门课程。' : '教师将你加入课程并发布图谱后，课程会出现在这里。' }}
      </p>
      <ul v-else class="cards">
        <li v-for="card in courses" :key="card.id" data-test="course-card">
          <RouterLink
            :to="{ name: COURSE_ROUTE, params: { cid: card.id } }"
            :aria-current="card.id === selectedId ? 'page' : undefined"
          >
            {{ card.name }}
          </RouterLink>
          <p class="meta">
            <span>我的身份：{{ card.roleLabel }}</span>
            <span>状态：{{ card.statusLabel }}</span>
            <span>知识点：{{ card.knowledgePointCount }}</span>
          </p>
          <p v-if="card.description" class="description">{{ card.description }}</p>
        </li>
      </ul>
    </section>

    <form
      v-if="canCreate"
      class="surface-card create"
      data-test="course-create"
      novalidate
      :aria-busy="creating"
      @submit.prevent="createCourse"
    >
      <fieldset :disabled="creating">
        <legend>创建课程</legend>
        <label>
          课程名称
          <input v-model="form.name" name="name" type="text" required :maxlength="COURSE_NAME_MAX" />
        </label>
        <label>
          课程简介（可选）
          <textarea v-model="form.description" name="description" rows="3" :maxlength="COURSE_DESCRIPTION_MAX" />
        </label>
        <p v-if="createError" data-test="create-error" role="alert">{{ createError }}</p>
        <p v-if="createdName" data-test="create-success" role="status">已创建课程「{{ createdName }}」。</p>
        <button type="submit" :disabled="creating">{{ creating ? '创建中…' : '创建课程' }}</button>
      </fieldset>
    </form>
  </div>
</template>

<style scoped>
/* 布局只管排列；背景、卡片、边框与阴影统一来自全局 .page / .surface-card（API 设置页是基准） */
.courses {
  align-content: start;
}

.cards {
  display: grid;
  gap: 0.75rem;
  grid-template-columns: repeat(auto-fill, minmax(14rem, 1fr));
  list-style: none;
  padding: 0;
  margin: 0;
}

/* 课程卡片：与 API 页接口卡片同款（暖白底 + 细边框 + 圆角 + 暖色阴影） */
.cards li {
  display: grid;
  gap: 0.35rem;
  align-content: start;
  padding: 0.9rem 1rem;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-card);
}

.cards a[aria-current='page'] {
  font-weight: 700;
}

.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1rem;
  font-size: 0.875rem;
  color: var(--color-text-muted);
}

.current .current-name {
  font-weight: 600;
}

.create fieldset {
  display: grid;
  gap: 0.75rem;
  max-width: 28rem;
  border: none;
  padding: 0;
  background: none;
}

.create label {
  display: grid;
  gap: 0.25rem;
}

/* 旧数据（演示向量）需要重新处理资料：提示 + 用户主动触发的操作 */
.intelligence-note {
  display: grid;
  gap: 0.5rem;
  justify-items: start;
  margin: 0.5rem 0;
  padding: 0.75rem 0.9rem;
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning-border);
  border-radius: var(--radius-sm);
  color: var(--color-warning-text);
  font-size: 0.875rem;
}
.intelligence-note p {
  margin: 0;
}
.intelligence-note__result {
  color: var(--color-text-muted);
}
</style>
