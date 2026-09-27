<script setup lang="ts">
import { computed, inject, ref, type InjectionKey } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { HTTP_CLIENT_KEY } from '../api/client'
import { COURSES_API_KEY } from '../api/courses'
import { createPublishedGraphApi, PUBLISHED_GRAPH_API_KEY } from '../api/graph'
import type { HttpClient } from '../api/http'
import { createProgressApi, PROGRESS_API_KEY, type MasteryStatus, type ProgressApi } from '../api/progress'
import { createRecommendApi, RECOMMEND_API_KEY, type RecommendApi } from '../api/recommend'
import GraphCanvas from '../components/GraphCanvas.vue'
import GraphToolbar from '../components/GraphToolbar.vue'
import KnowledgeCards from '../components/KnowledgeCards.vue'
import KnowledgeDetail from '../components/KnowledgeDetail.vue'
import Recommendations from '../components/Recommendations.vue'
import { chapterOptions, useGraphFilters } from '../composables/useGraphFilters'
import { MASTERY_LABELS, useLearning } from '../composables/useLearning'
import { toKnowledgeCards, useStudentGraph } from '../composables/useStudentGraph'
import { COURSE_ROUTE, homeRouteFor, NOTICE_COURSE_FORBIDDEN, ROOT_ROUTE, STUDENT_GRAPH_ROUTE } from '../router'
import { useSessionStore } from '../stores/session'

/**
 * 学生图谱页（H11，ADR-063）：只读已发布版本，图谱与卡片两种视图共用筛选与选中，详情抽屉复用 H06。
 * 数据请求与草稿防护在 `useStudentGraph`；筛选在 `useGraphFilters`；掌握标记与推荐在 `useLearning`（I06）；
 * 本页只做组装：把筛选后的可见图交给 `useLearning` 落掌握状态色与推荐高亮，再把结果交给画布。
 *
 * I06 增量：学习接口（`PROGRESS_API_KEY`/`RECOMMEND_API_KEY`）未注入时退回 H11 原状（不读进度、不渲染标记与推荐）。
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

/** 学习接口沿用 H09/H14 的注入惯例：优先注入键，否则用会话客户端构造；两者都缺时返回 null（本页退回 H11 原状） */
function learningApi<T>(key: InjectionKey<T>, build: (client: HttpClient) => T): T | null {
  const injected = inject(key, null)
  if (injected !== null) return injected
  const client = inject(HTTP_CLIENT_KEY, null)
  return client === null ? null : build(client)
}
const progressApi = learningApi<ProgressApi>(PROGRESS_API_KEY, createProgressApi)
const recommendApi = learningApi<RecommendApi>(RECOMMEND_API_KEY, createRecommendApi)

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

// ---------------------------------------------------------------- I06：掌握标记与推荐

const learningEnabled = progressApi !== null && recommendApi !== null
const {
  status: learningStatus,
  error: learningError,
  retryable: learningRetryable,
  recommendState,
  recommendations,
  totalEligible,
  recommendError,
  recommendLoading,
  busyKpId,
  notice: learningNotice,
  learningGraph,
  statusOf,
  setMastery,
  reload: reloadLearning,
  refreshRecommend,
} = useLearning({
  progressApi,
  recommendApi,
  courseId,
  // 掌握标记只在已显示的发布版本上读写：版本未知时组合式既不读也不写
  graphVersion,
  ready: computed(() => status.value === 'ready'),
  graph: visible,
  onCourseForbidden: leaveForbidden,
  // 显示版本落后于服务端绑定版本：重新加载图谱与进度，而不是把新投影套到旧图
  onVersionStale: reload,
})

const masteryOptions: Array<{ value: MasteryStatus; label: string }> = [
  { value: 'unknown', label: MASTERY_LABELS.unknown },
  { value: 'learning', label: MASTERY_LABELS.learning },
  { value: 'mastered', label: MASTERY_LABELS.mastered },
]

const selectedName = computed(() => {
  const kpId = selected.value
  if (kpId === null) return ''
  return graph.value?.nodes.find((node) => node.data.kpId === kpId)?.data.name ?? kpId
})
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
          <GraphCanvas :graph="learningGraph" :layout="filters.layout.value" @node-click="filters.select" />
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

      <!-- I06：掌握标记与下一步推荐。不可写（未发布/非学生/加载失败）时不给任何可点击入口 -->
      <div v-if="learningEnabled" class="student-graph__learning" data-test="sg-learning">
        <p v-if="learningStatus === 'not_student'" data-test="sg-learning-forbidden" role="alert">
          你在本课程是教师，掌握标记与下一步推荐是学生行为，请在课程页进入教师工作区。
        </p>
        <p v-else-if="learningStatus === 'unpublished'" data-test="sg-learning-unpublished" role="status">
          课程尚未发布知识图谱，暂时无法记录学习进度。
        </p>
        <div v-else-if="learningStatus === 'error'" data-test="sg-learning-error" role="alert">
          <p>{{ learningError }}</p>
          <button v-if="learningRetryable" type="button" data-test="sg-learning-retry" @click="reloadLearning">重试</button>
        </div>

        <template v-else-if="learningStatus === 'ready'">
          <p v-if="learningNotice !== null" data-test="sg-learning-notice" :data-tone="learningNotice.tone">
            {{ learningNotice.text }}
          </p>

          <Recommendations
            :state="recommendState"
            :items="recommendations"
            :total-eligible="totalEligible"
            :version="graphVersion"
            :loading="recommendLoading"
            :error="recommendError"
            :selected-id="selected"
            @select="filters.select"
            @retry="refreshRecommend"
          />

          <section v-if="selected !== null" class="student-graph__mastery" data-test="sg-mastery" aria-labelledby="sg-mastery-title">
            <h3 id="sg-mastery-title">掌握标记</h3>
            <p data-test="sg-mastery-target">
              知识点：{{ selectedName }} · 当前：{{ MASTERY_LABELS[statusOf(selected)] }}
            </p>
            <div role="group" aria-label="掌握状态">
              <button
                v-for="item in masteryOptions"
                :key="item.value"
                type="button"
                :data-test="`sg-mastery-${item.value}`"
                :aria-pressed="statusOf(selected) === item.value ? 'true' : 'false'"
                :disabled="busyKpId !== null"
                @click="setMastery(selected, item.value)"
              >
                {{ item.label }}
              </button>
            </div>
          </section>
          <p v-else class="student-graph__hint" data-test="sg-mastery-hint">
            在图中或卡片中选择一个知识点后可标记掌握状态。
          </p>
        </template>
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
.student-graph__learning {
  margin-top: 1rem;
}
.student-graph__mastery {
  margin-top: 1rem;
  padding: 0.75rem;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
}
.student-graph__mastery button[aria-pressed='true'] {
  font-weight: 600;
}
</style>
