<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { HTTP_CLIENT_KEY } from '../api/client'
import { COURSES_API_KEY } from '../api/courses'
import { createPublishedGraphApi, PUBLISHED_GRAPH_API_KEY } from '../api/graph'
import GraphCanvas from '../components/GraphCanvas.vue'
import GraphToolbar from '../components/GraphToolbar.vue'
import KnowledgeCards from '../components/KnowledgeCards.vue'
import KnowledgeDetail from '../components/KnowledgeDetail.vue'
import { chapterOptions, useGraphFilters } from '../composables/useGraphFilters'
import { toKnowledgeCards, useStudentGraph } from '../composables/useStudentGraph'
import { COURSE_ROUTE, homeRouteFor, NOTICE_COURSE_FORBIDDEN, ROOT_ROUTE, STUDENT_GRAPH_ROUTE } from '../router'
import { useSessionStore } from '../stores/session'

/**
 * 学生图谱页（H11，ADR-063）：只读已发布版本，图谱与卡片两种视图共用筛选与选中，详情抽屉复用 H06。
 * 数据请求与草稿防护在 `useStudentGraph`；筛选在 `useGraphFilters`；本页只做组装。
 */
const coursesApi = inject(COURSES_API_KEY, null)
if (coursesApi === null) throw new Error('StudentGraphView 需要注入 COURSES_API_KEY')
const graphApi =
  inject(PUBLISHED_GRAPH_API_KEY, null) ??
  (() => {
    const client = inject(HTTP_CLIENT_KEY, null)
    if (client === null) throw new Error('StudentGraphView 需要注入 PUBLISHED_GRAPH_API_KEY 或 HTTP_CLIENT_KEY')
    return createPublishedGraphApi(client)
  })()

const route = useRoute()
const router = useRouter()
const session = useSessionStore()

// 离开本路由即为 null：composable 中止在途请求
const courseId = computed(() => {
  const cid = route.params.cid
  return route.name === STUDENT_GRAPH_ROUTE && typeof cid === 'string' && cid !== '' ? cid : null
})

function leaveForbidden(): void {
  const role = session.role
  void router.replace(
    role === null ? { name: ROOT_ROUTE } : { name: homeRouteFor(role), query: { notice: NOTICE_COURSE_FORBIDDEN } },
  )
}

const { status, error, retryable, courseName, graphVersion, graph, chapters, reload } = useStudentGraph({
  coursesApi,
  graphApi,
  courseId,
  onCourseForbidden: leaveForbidden,
})

const filters = useGraphFilters(graph)
const { selected, visible, summary, isDefault, selectedHidden } = filters

type ViewMode = 'graph' | 'cards'
const mode = ref<ViewMode>('graph')
const modes: Array<{ value: ViewMode; label: string }> = [
  { value: 'graph', label: '图谱' },
  { value: 'cards', label: '卡片' },
]

const chapterList = computed(() => (graph.value === null ? [] : chapterOptions(graph.value, chapters.value)))
const cards = computed(() => (visible.value === null ? [] : toKnowledgeCards(visible.value.nodes, chapters.value)))
const empty = computed(() => status.value === 'ready' && graph.value !== null && graph.value.nodes.length === 0)
</script>

<template>
  <section
    class="student-graph"
    data-test="student-graph-page"
    aria-labelledby="student-graph-title"
    :aria-busy="status === 'loading' ? 'true' : 'false'"
  >
    <h2 id="student-graph-title">课程知识图谱</h2>
    <p v-if="courseName" class="student-graph__course">
      课程：{{ courseName }}<span v-if="graphVersion !== null" data-test="sg-version"> · 已发布版本 v{{ graphVersion }}</span>
    </p>
    <p v-if="courseId">
      <RouterLink :to="{ name: COURSE_ROUTE, params: { cid: courseId } }">返回课程</RouterLink>
    </p>

    <p v-if="status === 'loading'" data-test="sg-loading" role="status">正在加载已发布图谱…</p>

    <p v-else-if="status === 'not_student'" data-test="sg-not-student" role="status">
      此页面向本课程的学生，只展示已发布图谱。你在本课程是教师，请在课程页进入教师工作区。
    </p>

    <p v-else-if="status === 'unpublished'" data-test="sg-unpublished" role="status">
      课程尚未发布知识图谱，教师发布后即可浏览。
    </p>

    <div v-else-if="status === 'error'" data-test="sg-error" role="alert">
      <p>{{ error }}</p>
      <button v-if="retryable" type="button" data-test="sg-retry" @click="reload">重试</button>
    </div>

    <p v-else-if="empty" data-test="sg-empty" role="status">已发布的图谱中暂无知识点。</p>

    <template v-else-if="status === 'ready' && graph !== null">
      <div class="student-graph__modes" role="group" aria-label="视图切换">
        <button
          v-for="item in modes"
          :key="item.value"
          type="button"
          :data-test="`sg-mode-${item.value}`"
          :aria-pressed="mode === item.value ? 'true' : 'false'"
          @click="mode = item.value"
        >
          {{ item.label }}
        </button>
      </div>

      <GraphToolbar
        v-model="filters.state.value"
        v-model:layout="filters.layout.value"
        :chapters="chapterList"
        :summary="summary"
        :can-clear="!isDefault"
        :selected-hidden="selectedHidden"
        :show-statuses="false"
        @clear="filters.clear"
      />

      <div class="student-graph__body">
        <div v-if="mode === 'graph'" class="student-graph__canvas" data-test="sg-graph">
          <p class="student-graph__hint">画布支持鼠标缩放与拖拽；使用键盘请切换到「卡片」视图。</p>
          <GraphCanvas :graph="visible" :layout="filters.layout.value" @node-click="filters.select" />
        </div>
        <KnowledgeCards
          v-else
          :cards="cards"
          :selected-id="selected"
          @select="filters.select"
        />

        <KnowledgeDetail
          v-if="selected !== null"
          :kp-id="selected"
          @select-knowledge-point="filters.select"
          @close="filters.select(null)"
          @course-forbidden="leaveForbidden"
        />
      </div>
    </template>
  </section>
</template>

<style scoped>
.student-graph__modes {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}
.student-graph__modes button[aria-pressed='true'] {
  font-weight: 600;
  border-color: #0958d9;
}
.student-graph__body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 1rem;
}
.student-graph__canvas {
  min-height: 480px;
}
.student-graph__hint {
  color: #595959;
  font-size: 0.875rem;
}
</style>
