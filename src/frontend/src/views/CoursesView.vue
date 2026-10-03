<script setup lang="ts">
import { computed, inject, nextTick, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { COURSES_API_KEY } from '../api/courses'
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

// ---------------------------------------------------------------- 顶部统计与说明
// 只有列表就绪时才给确定数字；加载中/失败不把未加载的数据说成「0 门课程」
const listReady = computed(() => listStatus.value === 'ready')
const courseCount = computed(() => courses.value.length)
// 仅统计当前列表范围内各课程的知识点数，不代表全站
const knowledgePointTotal = computed(() =>
  courses.value.reduce((sum, card) => sum + (card.knowledgePointCount ?? 0), 0),
)
const statsLine = computed(() => {
  if (!listReady.value) return '课程列表加载中'
  return `${courseCount.value} 门课程 · ${knowledgePointTotal.value} 个知识点`
})
const roleLede = computed(() =>
  session.role === 'teacher'
    ? '管理你的课程、知识图谱和教学资料'
    : '浏览课程知识图谱，规划学习路径并进行课程问答',
)

// ---------------------------------------------------------------- 创建面板（默认收起）
const createOpen = ref(false)
const createNameInput = ref<HTMLInputElement | null>(null)
const createButton = ref<HTMLButtonElement | null>(null)

async function toggleCreate(): Promise<void> {
  // 请求进行中不允许收起，避免提交状态与界面不同步
  if (creating.value) return
  createOpen.value = !createOpen.value
  await nextTick()
  if (createOpen.value) createNameInput.value?.focus()
  else createButton.value?.focus()
}

function cancelCreate(): void {
  if (creating.value) return
  createOpen.value = false
  void nextTick(() => createButton.value?.focus())
}

// ---------------------------------------------------------------- 卡片展示细节
/** 「进入课程 →」这一行不参与无障碍名称，卡片标题与状态才是 */
const CARD_ACTION_LABEL = '进入课程'
/** 状态徽标配色：草稿灰、已发布绿、修订中琥珀，未知状态用中性色 */
function statusTone(label: string): string {
  if (label === '已发布') return 'is-published'
  if (label === '修订中') return 'is-revising'
  if (label === '草稿') return 'is-draft'
  return 'is-neutral'
}

/** 卡片装饰：一组固定坐标的节点与连线，纯装饰、不发起任何请求 */
const GRAPH_NODES: { cx: number; cy: number; r: number; tone?: string }[] = [
  { cx: 20, cy: 68, r: 6, tone: 'is-strong' },
  { cx: 54, cy: 34, r: 4 },
  { cx: 88, cy: 56, r: 7 },
  { cx: 120, cy: 24, r: 3.5, tone: 'is-soft' },
  { cx: 152, cy: 62, r: 5 },
  { cx: 118, cy: 96, r: 4.5, tone: 'is-strong' },
  { cx: 62, cy: 104, r: 3.5 },
  { cx: 168, cy: 100, r: 3, tone: 'is-soft' },
]
const GRAPH_LINKS: [number, number][] = [
  [0, 1],
  [1, 2],
  [2, 3],
  [2, 4],
  [4, 5],
  [5, 6],
  [6, 0],
  [4, 7],
]
/** 供模板按索引取节点坐标画线（避免在模板里写复杂表达式） */
function nodeAt(index: number): { cx: number; cy: number } {
  const node = GRAPH_NODES[index] ?? GRAPH_NODES[0]!
  return { cx: node.cx, cy: node.cy }
}
</script>

<template>
  <div class="page courses" aria-labelledby="courses-title">
    <header class="courses__head">
      <div class="courses__intro">
        <h2 id="courses-title">我的课程</h2>
        <p class="courses__stats" data-test="courses-stats">{{ statsLine }}</p>
        <p class="courses__lede">{{ roleLede }}</p>
      </div>
      <div v-if="canCreate" class="courses__actions">
        <button
          ref="createButton"
          type="button"
          class="courses__create"
          :aria-expanded="createOpen"
          aria-controls="course-create-panel"
          :disabled="creating"
          data-test="create-toggle"
          @click="toggleCreate"
        >
          <svg class="courses__create-icon" viewBox="0 0 16 16" width="15" height="15" aria-hidden="true">
            <path d="M8 3v10M3 8h10" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
          </svg>
          {{ creating ? '创建中…' : '创建课程' }}
        </button>
      </div>
    </header>

    <p v-if="courseForbidden" data-test="course-forbidden" role="alert">
      你无权访问该课程（可能已被移出课程），已返回课程列表。
    </p>

    <p v-if="createdName" class="courses__feedback" data-test="create-toast" role="status">
      <span class="courses__feedback-ok" data-test="create-success-outside">已创建课程「{{ createdName }}」。</span>
    </p>

    <form
      v-if="canCreate"
      v-show="createOpen"
      id="course-create-panel"
      class="courses__create-panel"
      data-test="course-create"
      novalidate
      :aria-busy="creating"
      @submit.prevent="createCourse"
    >
      <fieldset :disabled="creating">
        <legend class="courses__create-title">创建课程</legend>
        <p class="courses__create-hint">填写课程名称即可创建；简介可以稍后补充。</p>
        <label>
          课程名称
          <input
            ref="createNameInput"
            v-model="form.name"
            name="name"
            type="text"
            required
            :maxlength="COURSE_NAME_MAX"
          />
        </label>
        <label>
          课程简介（可选）
          <textarea v-model="form.description" name="description" rows="3" :maxlength="COURSE_DESCRIPTION_MAX" />
        </label>
        <!-- 表单内的提示保持原语义：失败用 alert，成功用 status -->
        <p v-if="createError" data-test="create-error" role="alert">{{ createError }}</p>
        <p v-if="createdName" data-test="create-success" role="status">已创建课程「{{ createdName }}」。</p>
        <div class="courses__create-actions">
          <button type="submit" :disabled="creating">{{ creating ? '创建中…' : '创建课程' }}</button>
          <button type="button" data-variant="secondary" :disabled="creating" data-test="create-cancel" @click="cancelCreate">
            取消
          </button>
        </div>
      </fieldset>
    </form>

    <section
      v-if="courseId !== null"
      class="courses__current"
      data-test="current-course"
      aria-labelledby="current-course-title"
      :aria-busy="currentStatus === 'loading'"
    >
      <h3 id="current-course-title">当前课程</h3>
      <p v-if="currentStatus === 'loading'" role="status">正在加载课程…</p>
      <p v-else-if="currentStatus === 'error'" data-test="current-course-error" role="alert">{{ currentError }}</p>
      <template v-else-if="current">
        <p class="courses__current-name">{{ current.name }}</p>
        <p class="courses__current-meta">
          课程内身份：{{ current.roleLabel }}（{{ current.myRole === 'teacher' ? '教师视图' : '学生视图' }}）
          · 状态：{{ current.statusLabel }}
        </p>
        <p v-if="current.description" class="courses__current-desc">{{ current.description }}</p>
        <ul class="courses__current-links">
          <li v-if="hasStudentGraph && current.myRole === 'student'">
            <RouterLink data-test="student-graph-link" :to="{ name: STUDENT_GRAPH_ROUTE, params: { cid: current.id } }">
              浏览课程图谱
            </RouterLink>
          </li>
          <li v-if="hasTeacherGraph && current.myRole === 'teacher'">
            <RouterLink data-test="teacher-graph-link" :to="{ name: TEACHER_GRAPH_ROUTE, params: { cid: current.id } }">
              编辑课程图谱（草稿）
            </RouterLink>
          </li>
          <li v-if="hasReview && current.myRole === 'teacher'">
            <RouterLink data-test="review-link" :to="{ name: REVIEW_ROUTE, params: { cid: current.id } }">
              审核队列
            </RouterLink>
          </li>
          <li v-if="hasMaterials && current.myRole === 'teacher'">
            <RouterLink data-test="materials-link" :to="{ name: MATERIALS_ROUTE, params: { cid: current.id } }">
              资料上传与处理进度
            </RouterLink>
          </li>
          <li v-if="hasChat && current.myRole === 'student'">
            <RouterLink :to="{ name: CHAT_ROUTE, params: { cid: current.id } }">课程问答</RouterLink>
          </li>
          <li v-if="hasMembersRoute && current.myRole === 'teacher'">
            <RouterLink data-test="members-link" :to="{ name: COURSE_MEMBERS_ROUTE, params: { cid: current.id } }">
              管理成员
            </RouterLink>
          </li>
        </ul>
      </template>
    </section>

    <section
      class="courses__list"
      data-test="course-list-region"
      aria-labelledby="course-list-title"
      :aria-busy="listStatus === 'loading'"
    >
      <header class="courses__list-head">
        <h3 id="course-list-title">课程列表</h3>
        <span v-if="listReady" class="courses__list-total" data-test="courses-total">共 {{ courseCount }} 门</span>
      </header>

      <p v-if="listStatus === 'loading'" data-test="courses-loading" role="status">正在加载课程…</p>
      <p v-else-if="listStatus === 'forbidden'" data-test="courses-forbidden" role="alert">{{ listError }}</p>
      <div v-else-if="listStatus === 'error'" class="courses__list-error">
        <p data-test="courses-error" role="alert">{{ listError }}</p>
        <button type="button" data-variant="secondary" data-test="courses-retry" @click="loadCourses">重试</button>
      </div>
      <p v-else-if="isEmpty" class="courses__list-empty" data-test="courses-empty">
        暂无课程。{{ canCreate ? '可以在上方展开「创建课程」创建第一门。' : '教师将你加入课程并发布图谱后，课程会出现在这里。' }}
      </p>

      <ul v-else class="courses__grid">
        <li v-for="card in courses" :key="card.id" class="course-card" data-test="course-card">
          <RouterLink
            class="course-card__link"
            :to="{ name: COURSE_ROUTE, params: { cid: card.id } }"
            :aria-current="card.id === selectedId ? 'page' : undefined"
          >
            <svg class="course-card__decor" viewBox="0 0 190 130" aria-hidden="true" focusable="false">
              <line
                v-for="(link, index) in GRAPH_LINKS"
                :key="`l-${index}`"
                :x1="nodeAt(link[0]!).cx"
                :y1="nodeAt(link[0]!).cy"
                :x2="nodeAt(link[1]!).cx"
                :y2="nodeAt(link[1]!).cy"
              />
              <circle
                v-for="(node, index) in GRAPH_NODES"
                :key="`n-${index}`"
                :cx="node.cx"
                :cy="node.cy"
                :r="node.r"
                :class="node.tone"
              />
            </svg>

            <span class="course-card__badge" :class="statusTone(card.statusLabel)">{{ card.statusLabel }}</span>
            <h4 class="course-card__name">{{ card.name }}</h4>
            <p v-if="card.description" class="course-card__desc">{{ card.description }}</p>

            <div class="course-card__footer">
              <ul class="course-card__chips">
                <li class="course-card__chip">
                  <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false">
                    <circle cx="8" cy="5" r="2.6" fill="none" stroke="currentColor" stroke-width="1.4" />
                    <path d="M3 13.5c0-2.5 2.2-4 5-4s5 1.5 5 4" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
                  </svg>
                  {{ card.roleLabel }}
                </li>
                <li class="course-card__chip">
                  <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false">
                    <path d="M3 3.5h4.5A2 2 0 0 1 9.5 5.5V13a2 2 0 0 0-2-2H3z" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round" />
                    <path d="M13 3.5H9.5A2 2 0 0 0 7.5 5.5V13a2 2 0 0 1 2-2H13z" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round" />
                  </svg>
                  {{ card.knowledgePointCount }} 个知识点
                </li>
              </ul>
              <span class="course-card__cta">
                {{ CARD_ACTION_LABEL }}
                <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false">
                  <path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
                </svg>
              </span>
            </div>
          </RouterLink>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
/* 本页只在课程页放宽内容宽度；不改全局 .page / .app-main，避免影响其它页面画布 */
.courses {
  --courses-max: 72.5rem;          /* ≈1160px */
  --card-min: 32rem;               /* ≈512px：两列布局下单卡下限 */
  --card-max: 33rem;               /* ≈528px：单卡上限，避免一门课时被拉满整行 */
  width: 100%;
  max-width: var(--courses-max);
  margin-inline: auto;
  gap: 1.5rem;
}

/* ---------------------------------------------------------------- 顶部区域 */
.courses__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem 1.5rem;
  flex-wrap: wrap;
}

.courses__intro {
  display: grid;
  gap: 0.4rem;
  min-width: 0;
}

.courses__intro h2 {
  margin: 0;
  font-size: clamp(1.875rem, 2.4vw, 2.125rem);   /* 30～34px */
  line-height: 1.2;
}

.courses__stats {
  margin: 0;
  color: var(--color-text);
  font-size: 0.95rem;
  font-weight: 500;
}

.courses__lede {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

.courses__actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.courses__create {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  min-height: 2.75rem;            /* ≈44px */
  padding: 0 1.15rem;
  border-radius: var(--radius-md);
  box-shadow: none;
  font-weight: 600;
}

.courses__create-icon {
  flex: none;
}

/* 创建结果提示：面板收起后仍然可见 */
.courses__feedback {
  display: grid;
  gap: 0.25rem;
  margin: 0;
  font-size: 0.875rem;
}

.courses__feedback-ok {
  color: var(--color-success-text);
}

.courses__feedback-err {
  color: var(--color-danger-text);
}

/* ---------------------------------------------------------------- 创建面板 */
.courses__create-panel {
  padding: clamp(1rem, 2vw, 1.4rem);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-card);
}

.courses__create-panel fieldset {
  display: grid;
  gap: 0.75rem;
  max-width: 34rem;
  border: none;
  padding: 0;
  background: none;
}

.courses__create-title {
  padding: 0;
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--color-text);
}

.courses__create-hint {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.8125rem;
}

.courses__create-panel label {
  display: grid;
  gap: 0.3rem;
}

.courses__create-actions {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
}

/* ---------------------------------------------------------------- 当前课程（进入详情时使用，保持原有入口） */
.courses__current {
  display: grid;
  gap: 0.5rem;
  min-width: 0;
  padding: clamp(1rem, 2vw, 1.4rem);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-card);
}

.courses__current > h3 {
  margin: 0;
  font-size: 1.05rem;
}

.courses__current-name {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 600;
}

.courses__current-meta,
.courses__current-desc {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

.courses__current-links {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1.25rem;
  margin: 0.25rem 0 0;
  padding: 0;
  list-style: none;
}

/* ---------------------------------------------------------------- 课程列表 */
/* 列表只做分区，不再套一层大白卡 */
.courses__list {
  display: grid;
  gap: 1rem;
  min-width: 0;
}

.courses__list-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
}

.courses__list-head h3 {
  margin: 0;
  font-size: 1.15rem;
}

.courses__list-total {
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

.courses__list-error,
.courses__list-empty {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

.courses__list-error {
  display: grid;
  gap: 0.6rem;
  justify-items: start;
}

.courses__grid {
  display: grid;
  gap: 1rem;
  /* 单卡有上限：只有一门课时不会被拉满整行，多余空间留在右侧 */
  grid-template-columns: repeat(auto-fill, minmax(min(100%, var(--card-min)), var(--card-max)));
  justify-content: start;
  margin: 0;
  padding: 0;
  list-style: none;
}

/* ---------------------------------------------------------------- 课程卡片 */
.course-card {
  display: flex;
  min-width: 0;
}

.course-card__link {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  display: grid;
  grid-template-rows: auto auto 1fr auto;
  gap: 0.5rem;
  width: 100%;
  min-height: 13.5rem;
  padding: clamp(1.1rem, 2vw, 1.5rem);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  color: var(--color-text);
  text-decoration: none;
  transition: transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease;
}

.course-card__link:hover,
.course-card__link:focus-visible {
  transform: translateY(-2px);
  border-color: var(--color-border-strong);
  box-shadow: 0 2px 4px rgb(35 32 28 / 6%), 0 10px 26px rgb(35 32 28 / 8%);
  text-decoration: none;
}

.course-card__link:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

/* 右侧装饰图谱：纯装饰，不拦鼠标、不进无障碍树 */
.course-card__decor {
  position: absolute;
  top: 0.6rem;
  right: 0.4rem;
  width: min(16rem, 62%);
  height: auto;
  opacity: 0.08;
  pointer-events: none;
  z-index: -1;
}

.course-card__decor line {
  stroke: var(--color-primary);
  stroke-width: 1;
}

.course-card__decor circle {
  fill: var(--color-primary);
}

.course-card__decor circle.is-strong {
  fill: var(--color-primary);
}

.course-card__decor circle.is-soft {
  fill: var(--color-success-text);
}

.course-card__badge {
  justify-self: start;
  padding: 0.15rem 0.55rem;
  border-radius: 999px;
  border: 1px solid transparent;
  font-size: 0.75rem;
  font-weight: 500;
  line-height: 1.6;
}

.course-card__badge.is-published {
  background: var(--color-success-bg);
  border-color: var(--color-success-border);
  color: var(--color-success-text);
}

.course-card__badge.is-draft {
  background: var(--color-surface-muted);
  border-color: var(--color-border);
  color: var(--color-text-muted);
}

.course-card__badge.is-revising {
  background: var(--color-warning-bg);
  border-color: var(--color-warning-border);
  color: var(--color-warning-text);
}

.course-card__badge.is-neutral {
  background: var(--color-surface-muted);
  border-color: var(--color-border);
  color: var(--color-text-muted);
}

.course-card__name {
  margin: 0;
  font-size: 1.3rem;
  font-weight: 600;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.course-card__desc {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow: hidden;
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.9375rem;
  line-height: 1.65;
}

.course-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 0.9rem;
  flex-wrap: wrap;
  margin-top: 0.35rem;
  padding-top: 0.85rem;
  border-top: 1px solid var(--color-border);
}

.course-card__chips {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin: 0;
  padding: 0;
  list-style: none;
}

.course-card__chip {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.28rem 0.6rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface-muted);
  color: var(--color-text-muted);
  font-size: 0.8125rem;
  white-space: nowrap;
}

.course-card__cta {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  margin-left: auto;
  color: var(--color-primary);
  font-size: 0.9375rem;
  font-weight: 600;
  white-space: nowrap;
}

.course-card__link:hover .course-card__cta {
  color: var(--color-primary-hover);
}

@media (max-width: 760px) {
  .courses {
    --card-min: 100%;
  }

  .courses__head {
    align-items: stretch;
  }

  .courses__actions,
  .courses__create {
    width: 100%;
  }

  .courses__create {
    justify-content: center;
  }

  .courses__grid {
    grid-template-columns: 1fr;
  }

  .course-card__link {
    min-height: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .course-card__link {
    transition: none;
  }

  .course-card__link:hover,
  .course-card__link:focus-visible {
    transform: none;
  }
}
</style>
