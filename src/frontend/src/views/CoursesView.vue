<script setup lang="ts">
import { computed, inject } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { COURSES_API_KEY } from '../api/courses'
import { COURSE_DESCRIPTION_MAX, COURSE_NAME_MAX, useCourses } from '../composables/useCourses'
import { COURSE_MEMBERS_ROUTE, COURSE_ROUTE, homeRouteFor, MATERIALS_ROUTE, NOTICE_COURSE_FORBIDDEN, ROOT_ROUTE } from '../router'
import { useSessionStore } from '../stores/session'

const api = inject(COURSES_API_KEY, null)
if (api === null) throw new Error('CoursesView 需要注入 COURSES_API_KEY')

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

const courseForbidden = computed(() => route.query.notice === NOTICE_COURSE_FORBIDDEN)
</script>

<template>
  <section class="courses" aria-labelledby="courses-title">
    <h2 id="courses-title">我的课程</h2>

    <p v-if="courseForbidden" data-test="course-forbidden" role="alert">
      你无权访问该课程（可能已被移出课程），已返回课程列表。
    </p>

    <section
      v-if="courseId !== null"
      class="current"
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
        <p v-if="hasMaterials && current.myRole === 'teacher'">
          <RouterLink data-test="materials-link" :to="{ name: MATERIALS_ROUTE, params: { cid: current.id } }">
            资料上传与处理进度
          </RouterLink>
        </p>
        <p v-if="hasMembersRoute && current.myRole === 'teacher'">
          <RouterLink data-test="members-link" :to="{ name: COURSE_MEMBERS_ROUTE, params: { cid: current.id } }">
            管理成员
          </RouterLink>
        </p>
      </template>
    </section>

    <section
      class="list"
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
      class="create"
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
  </section>
</template>

<style scoped>
.courses {
  display: grid;
  gap: 1.5rem;
}

.cards {
  display: grid;
  gap: 0.75rem;
  grid-template-columns: repeat(auto-fill, minmax(14rem, 1fr));
  list-style: none;
  padding: 0;
  margin: 0;
}

.cards li {
  border: 1px solid #d0d7de;
  border-radius: 0.5rem;
  padding: 0.75rem 1rem;
}

.cards a[aria-current='page'] {
  font-weight: 700;
}

.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1rem;
  font-size: 0.875rem;
}

.create fieldset {
  display: grid;
  gap: 0.75rem;
  max-width: 28rem;
  border: none;
  padding: 0;
}

.create label {
  display: grid;
  gap: 0.25rem;
}
</style>
