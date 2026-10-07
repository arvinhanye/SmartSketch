<script setup lang="ts">
import { computed, inject, nextTick, onBeforeUnmount, onMounted, provide, ref, watch, type InjectionKey } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { HTTP_CLIENT_KEY } from '../api/client'
import { COURSES_API_KEY } from '../api/courses'
import { createPublishedGraphApi, PUBLISHED_GRAPH_API_KEY } from '../api/graph'
import type { HttpClient } from '../api/http'
import { createProgressApi, PROGRESS_API_KEY, type MasteryStatus, type ProgressApi } from '../api/progress'
import { createRecommendApi, RECOMMEND_API_KEY, type RecommendApi } from '../api/recommend'
import AppIcon from '../components/AppIcon.vue'
import ChapterMenu, { type ChapterItem } from '../components/ChapterMenu.vue'
import GraphCanvas from '../components/GraphCanvas.vue'
import GraphLegend from '../components/GraphLegend.vue'
import GraphOverlay from '../components/GraphOverlay.vue'
import GraphPreviewCard from '../components/GraphPreviewCard.vue'
import GraphSidePanel from '../components/GraphSidePanel.vue'
import KnowledgeCards from '../components/KnowledgeCards.vue'
import KnowledgeDetail from '../components/KnowledgeDetail.vue'
import LocalViewBar from '../components/LocalViewBar.vue'
import Recommendations from '../components/Recommendations.vue'
import {
  locateNode,
  NODE_TYPE_LABELS,
  RELATION_TYPE_ORDER,
  useGraphFilters,
  type KnowledgePointType,
} from '../composables/useGraphFilters'
import { useGraphLayout } from '../composables/useGraphLayout'
import { MASTERY_LABELS, useLearning } from '../composables/useLearning'
import { kpLinkOutcome } from '../composables/kpLink'
import { useLocalView } from '../composables/useLocalView'
import { usePreviewFocus } from '../composables/usePreviewFocus'
import { useReducedMotion } from '../composables/useReducedMotion'
import { toKnowledgeCards, useStudentGraph } from '../composables/useStudentGraph'
import { kpIdFromElementId, nodeElementId, type RelationType } from '../graph/adapter'
import { applyFocusStates } from '../graph/focusStates'
import type { GraphCanvasData } from '../graph/lifecycle'
import { createObstacleRegistry, GRAPH_OBSTACLES_KEY } from '../graph/obstacles'
import { masteryOfStates } from '../graph/presentation'
import { COURSE_ROUTE, homeRouteFor, NOTICE_COURSE_FORBIDDEN, ROOT_ROUTE, STUDENT_GRAPH_ROUTE } from '../router'
import { useSessionStore } from '../stores/session'

/**
 * 学生图谱页（H11，ADR-063；UI-GRAPH-PILOT-01 工作台）：只读已发布版本，图谱与卡片两种视图共用筛选与选中，
 * 详情复用 H06。左面板（课程说明 / 知识点详情）+ 浅色画布 + 浮层（搜索、章节、图例、预览卡、局部视图条、小地图）。
 *
 * 数据请求与草稿防护在 `useStudentGraph`；筛选在 `useGraphFilters`；掌握标记与推荐在 `useLearning`（I06）；
 * 预览/详情状态机在 `usePreviewFocus`；只看相邻在 `useLocalView`；章节分区布局在 `useGraphLayout`。
 * 本页只做组装：把筛选后的可见图交给 `useLearning` 落掌握状态色与推荐高亮，再叠加局部视图与聚焦状态后交给画布。
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
const reduced = useReducedMotion()
// 浮层登记障碍物：标签排布与镜头适应避开它们
provide(GRAPH_OBSTACLES_KEY, createObstacleRegistry())

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
const { selected, visible, summary } = filters

const canvas = ref<InstanceType<typeof GraphCanvas> | null>(null)

// ---------------------------------------------------------------- 预览 / 详情（规格 §7）
const focus = usePreviewFocus({ selected, select: filters.select })
const { previewId, highlightId } = focus
/** 由画布二次单击打开的详情：节点本来就在视口里，不再移动镜头 */
let skipCameraFor: string | null = null
function onCanvasNode(kpId: string): void {
  if (previewId.value === kpId || selected.value === kpId) skipCameraFor = kpId
  focus.onNodeClick(kpId)
}

// L13-4：问答知识点链接 ?kp=&v=：当前课程的图加载完后选中并聚焦；目标不在或版本不同时提示。
// 同一链接只处理一次（之后用户可自由选择）；切课时组合式重置图谱，旧课程的 kp 不会落到新课程。
const linkNotice = ref<string | null>(null)
let handledLink: string | null = null
watch(
  [() => route.query.kp, () => route.query.v, courseId, status, graphVersion] as const,
  ([kp, v, cid, current]) => {
    if (current !== 'ready' || graph.value === null || cid === null) return
    const key = `${cid}|${String(kp)}|${String(v)}|${graphVersion.value}`
    if (key === handledLink) return
    const outcome = kpLinkOutcome({ kp, v }, cid, {
      course_id: cid,
      graph_version: graphVersion.value,
      nodes: graph.value.nodes.map((node) => ({ id: node.data.kpId })),
    })
    if (outcome === null) return
    handledLink = key
    linkNotice.value = outcome.notice
    // 问答链接是显式选择：直接打开详情
    if (outcome.select !== null) focus.open(outcome.select)
  },
  { immediate: true },
)

type ViewMode = 'graph' | 'cards'
const mode = ref<ViewMode>('graph')

// L13-2 / 规格 §7：搜索框回车定位并进入预览（列表视图直接打开详情）；未找到时提示
const searchNotice = ref<string | null>(null)
function onLocate(): void {
  const current = graph.value
  const query = filters.state.value.query
  if (current === null) return
  const kpId = locateNode(current, filters.state.value, query)
  searchNotice.value = kpId === null ? '未找到匹配的知识点，可调整关键字或筛选条件。' : null
  if (kpId === null) return
  if (mode.value === 'graph') {
    focus.preview(kpId)
    canvas.value?.focus(kpId)
  } else focus.open(kpId)
}
function onQuery(event: Event): void {
  filters.state.value = { ...filters.state.value, query: (event.target as HTMLInputElement).value }
  searchNotice.value = null
}

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
  learningPath,
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
  // L14：路径按完整已发布图计算；点推荐项（即选中它）就解释它，否则解释第一个推荐项
  pathGraph: graph,
  focus: selected,
  onCourseForbidden: leaveForbidden,
  // 显示版本落后于服务端绑定版本：重新加载图谱与进度，而不是把新投影套到旧图
  onVersionStale: reload,
})

// L14：视口跟随路径焦点（首个推荐项，或学生点选的推荐项），让高亮的路径落在画面里
watch(
  [canvas, selected, () => learningPath.value?.focus ?? null, status],
  () => {
    if (status.value !== 'ready') return
    const target = selected.value ?? learningPath.value?.focus ?? null
    if (target === null) return
    if (target === skipCameraFor) {
      skipCameraFor = null
      return
    }
    canvas.value?.focus(target)
  },
  { flush: 'post', immediate: true },
)

// C05-3：路径行里点「之后解锁」的名称：选中该节点并把画布移过去（解锁节点可能在视口外）
function onUnlockLocate(kpId: string): void {
  focus.open(kpId)
  canvas.value?.focus(kpId)
}

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

// ---------------------------------------------------------------- 图例：关系与类型筛选（单一事实来源是筛选状态）
const allTypes = Object.keys(NODE_TYPE_LABELS) as KnowledgePointType[]
const hiddenRelations = computed(() => RELATION_TYPE_ORDER.filter((t) => !filters.state.value.relationTypes.includes(t)))
const hiddenTypes = computed(() => allTypes.filter((t) => !filters.state.value.nodeTypes.includes(t)))
const relationCounts = computed(() => {
  const counts = Object.fromEntries(RELATION_TYPE_ORDER.map((t) => [t, 0])) as Record<RelationType, number>
  for (const edge of graph.value?.edges ?? []) counts[edge.data.type] += 1
  return counts
})
const typeCounts = computed(() => {
  const counts = Object.fromEntries(allTypes.map((t) => [t, 0])) as Record<KnowledgePointType, number>
  for (const node of graph.value?.nodes ?? []) counts[node.data.type] += 1
  return counts
})
function toggleType(type: KnowledgePointType): void {
  const current = filters.state.value.nodeTypes
  filters.state.value = {
    ...filters.state.value,
    nodeTypes: allTypes.filter((t) => t === type !== current.includes(t)),
  }
}
function restoreAllFilters(): void {
  filters.state.value = { ...filters.state.value, relationTypes: [...RELATION_TYPE_ORDER], nodeTypes: [...allTypes] }
}
/** 章节聚焦时图例自动收起（它会压住本章节点）；清除定位后恢复。用户自己点过图例按钮就不再自动恢复 */
const legendOpen = ref(typeof window === 'undefined' || window.innerWidth >= 1280)
let legendAutoClosed = false
function setLegendOpen(open: boolean): void {
  legendAutoClosed = false
  legendOpen.value = open
}

// ---------------------------------------------------------------- 只看相邻（局部视图）
const localView = useLocalView(() => visible.value)
const localName = computed(() => {
  const id = localView.view.value?.id
  return id === undefined ? '' : (graph.value?.nodes.find((n) => n.data.kpId === id)?.data.name ?? id)
})
const hiddenByLocal = computed(() => (visible.value?.nodes.length ?? 0) - (localView.ids.value?.size ?? 0))
// 开启或切换 1/2 跳时，把镜头适应到可见的邻域；恢复全部时回到整图
watch(localView.view, () => {
  void nextTick(() => canvas.value?.fitTo(localView.ids.value === null ? undefined : [...localView.ids.value]))
})
// 局部视图的中心被筛选隐藏或换课程后自动失效
watch(visible, (v) => {
  const id = localView.view.value?.id
  if (id !== undefined && v !== null && !v.nodes.some((n) => n.data.kpId === id)) localView.clear()
  const preview = previewId.value
  if (preview !== null && v !== null && !v.nodes.some((n) => n.data.kpId === preview)) focus.clearPreview()
})

// ---------------------------------------------------------------- 章节跳转与章节聚焦
const chapterId = ref<string | null>(null)
const chapterItems = computed<ChapterItem[]>(() => {
  const g = graph.value
  if (g === null) return []
  const catalog = new Map(chapters.value.map((c) => [c.id, c]))
  const byChapter = new Map<string, string[]>()
  for (const node of g.nodes) {
    if (node.data.chapterId !== null) byChapter.set(node.data.chapterId, [...(byChapter.get(node.data.chapterId) ?? []), node.data.kpId])
  }
  const order = (id: string) => catalog.get(id)?.order ?? Number.POSITIVE_INFINITY
  return [...byChapter.keys()]
    .sort((a, b) => order(a) - order(b) || (a < b ? -1 : a > b ? 1 : 0))
    .map((id) => {
      const ids = byChapter.get(id)!
      return { id, title: catalog.get(id)?.title ?? id, total: ids.length, done: ids.filter((kp) => statusOf(kp) === 'mastered').length }
    })
})
const activeChapter = computed(() => chapterItems.value.find((c) => c.id === chapterId.value) ?? null)
/** 本章节点（知识点 ID），只取当前显示的 */
const chapterKpIds = computed<string[]>(() => {
  if (chapterId.value === null) return []
  return (visible.value?.nodes ?? []).filter((n) => n.data.chapterId === chapterId.value).map((n) => n.data.kpId)
})
function jumpChapter(id: string): void {
  if (legendOpen.value) {
    legendOpen.value = false
    legendAutoClosed = true
  }
  chapterId.value = id
  focus.clearPreview()
  void nextTick(() => canvas.value?.fitTo(chapterKpIds.value))
}
function clearChapter(): void {
  chapterId.value = null
  if (legendAutoClosed) {
    legendAutoClosed = false
    legendOpen.value = true
  }
}

// ---------------------------------------------------------------- 画布数据：学习状态 → 局部视图 → 聚焦状态
/** 预览/选中由 `highlightId` 决定；筛选层与学习路径带来的 `selected` 要去掉，否则预览与详情会同时出现两个外环 */
function withoutSelected(g: GraphCanvasData): GraphCanvasData {
  return {
    nodes: g.nodes.map((n) => (n.states?.includes('selected') ? { ...n, states: n.states.filter((s) => s !== 'selected') } : n)),
    edges: g.edges,
  }
}
const canvasGraph = computed<GraphCanvasData | null>(() => {
  const base = localView.apply(learningGraph.value)
  if (base === null) return null
  const hl = highlightId.value
  const scope = chapterId.value === null ? null : new Set(chapterKpIds.value.map(nodeElementId))
  return applyFocusStates(withoutSelected(base), {
    selectedId: hl === null ? null : nodeElementId(hl),
    matchedIds: new Set(),
    chapterIds: scope,
    fade: 'standard',
  })
})

// ---------------------------------------------------------------- 章节分区布局（对完整已发布图算一次，筛选只显示子集）
const layoutSource = computed(() => {
  const g = graph.value
  if (g === null) return null
  return {
    nodes: g.nodes.map((n) => ({ id: n.data.kpId, chapter: n.data.chapterId })),
    edges: g.edges.map((e) => ({
      id: e.data.relationId,
      source: kpIdFromElementId(e.source),
      target: kpIdFromElementId(e.target),
      type: e.data.type,
    })),
    chapterOrder: [...chapters.value].sort((a, b) => a.order - b.order || (a.id < b.id ? -1 : 1)).map((c) => c.id),
  }
})
const { positions } = useGraphLayout(() => layoutSource.value)

// ---------------------------------------------------------------- 预览卡
const preview = computed(() => {
  const id = previewId.value
  const g = graph.value
  const node = id === null || g === null ? undefined : g.nodes.find((n) => n.data.kpId === id)
  if (id === null || g === null || node === undefined) return null
  const el = nodeElementId(id)
  const status = statusOf(id)
  const mastery: 'mastered' | 'learning' | 'unknown' = status === 'mastered' ? 'mastered' : status === 'learning' ? 'learning' : 'unknown'
  return {
    id,
    name: node.data.name,
    type: node.data.type,
    chapter: chapters.value.find((c) => c.id === node.data.chapterId)?.title ?? '未分章',
    mastery,
    masteryText: MASTERY_LABELS[status],
    prerequisites: g.edges.filter((e) => e.data.type === 'PREREQUISITE' && e.target === el).length,
    unlocks: g.edges.filter((e) => e.data.type === 'PREREQUISITE' && e.source === el).length,
  }
})

// ---------------------------------------------------------------- 进度（左面板概览）
const progress = computed(() => {
  const total = graph.value?.nodes.length ?? 0
  let done = 0
  let learning = 0
  for (const node of graph.value?.nodes ?? []) {
    const s = statusOf(node.data.kpId)
    if (s === 'mastered') done += 1
    else if (s === 'learning') learning += 1
  }
  return { total, done, learning, percent: total === 0 ? 0 : Math.round((done / total) * 100) }
})

// ---------------------------------------------------------------- 面板：按容器宽度判断并置/覆盖
const ws = ref<HTMLElement | null>(null)
const panel = ref<InstanceType<typeof GraphSidePanel> | null>(null)
const panelToggle = ref<HTMLButtonElement | null>(null)
const wsWidth = ref(0)
/** 用户确认：并置面板占工作区 35%；剩余 65% 至少 640px，否则用 90% 覆盖面板 */
const docked = computed(() => wsWidth.value * 0.65 >= 640)
const dockedOpen = ref(true)
const overlayOpen = ref(false)
const panelVisible = computed(() => (docked.value ? dockedOpen.value : overlayOpen.value))
let observer: ResizeObserver | null = null
const measureWorkspace = (): void => {
  wsWidth.value = ws.value?.clientWidth ?? 0
}

function openPanel(): void {
  if (docked.value) dockedOpen.value = true
  else overlayOpen.value = true
  void nextTick(() => panel.value?.el?.querySelector<HTMLElement>('[data-focus-start]')?.focus())
}
function closePanel(): void {
  if (docked.value) dockedOpen.value = false
  else overlayOpen.value = false
  void nextTick(() => panelToggle.value?.focus())
}
// 覆盖模式下选中知识点时抽屉同时打开；并置模式下面板本来就在
watch(selected, (now) => {
  if (now !== null && !docked.value) overlayOpen.value = true
})
watch(docked, (now) => {
  if (now) overlayOpen.value = false
})
// Esc 依次关闭：章节菜单（菜单自己处理）→ 覆盖抽屉 → 预览
function onKey(event: KeyboardEvent): void {
  if (event.key !== 'Escape') return
  if (!docked.value && overlayOpen.value) closePanel()
  else if (previewId.value !== null) focus.clearPreview()
}
onMounted(() => {
  window.addEventListener('keydown', onKey)
  if (ws.value !== null) {
    // 首帧先同步量一次：避免第一次渲染按「0 宽」判成覆盖模式，后台标签页也不依赖观察器回调
    wsWidth.value = ws.value.clientWidth
    if (typeof ResizeObserver === 'function') {
      observer = new ResizeObserver(measureWorkspace)
      observer.observe(ws.value)
    } else window.addEventListener('resize', measureWorkspace)
  }
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('resize', measureWorkspace)
  observer?.disconnect()
})

// ---------------------------------------------------------------- 底部折叠条与布局切换
const nextOpen = ref(false)
function toggleMode(): void {
  mode.value = mode.value === 'graph' ? 'cards' : 'graph'
}
const layoutLabel = computed(() => (filters.layout.value === 'hierarchical' ? '章节分区' : '力导向'))
function toggleLayout(): void {
  filters.layout.value = filters.layout.value === 'hierarchical' ? 'force' : 'hierarchical'
}
const ready = computed(() => status.value === 'ready' && graph.value !== null && !empty.value)
</script>

<template>
  <section
    class="student-graph"
    data-test="student-graph-page"
    aria-labelledby="student-graph-title"
    :aria-busy="status === 'loading' ? 'true' : 'false'"
  >
    <h2 id="student-graph-title" class="visually-hidden">课程知识图谱</h2>

    <div
      ref="ws"
      class="graph-workspace gw"
      :class="{ 'is-docked': docked, 'is-overlay': !docked, 'is-collapsed': docked && !dockedOpen, 'is-state': !ready }"
    >
      <div v-if="!ready" class="gw-state-wrap">
        <p v-if="status === 'loading'" data-test="sg-loading" role="status">正在加载已发布图谱…</p>

        <p v-else-if="status === 'not_student'" data-test="sg-not-student" role="status">
          此页面向本课程的学生，只展示已发布图谱。你在本课程是教师，请在课程页进入教师工作区。
        </p>

        <p v-else-if="status === 'unpublished'" data-test="sg-unpublished" role="status">
          课程尚未发布知识图谱，教师发布后即可浏览。
        </p>

        <div v-else-if="status === 'error'" data-test="sg-error" role="alert">
          <p>{{ error }}</p>
          <button v-if="retryable" type="button" class="gw-btn" data-test="sg-retry" @click="reload">重试</button>
        </div>

        <p v-else-if="empty" data-test="sg-empty" role="status">已发布的图谱中暂无知识点。</p>
      </div>

      <template v-else>
        <!-- 左面板：未选中显示课程说明，选中后原位切换为知识点详情（保留可折叠的「下一步推荐」） -->
        <GraphSidePanel
          ref="panel"
          :open="panelVisible"
          :docked="docked"
          :detail="selected !== null"
          :label="`知识点详情：${selectedName}`"
          :content-key="selected ?? 'course'"
          @close="closePanel"
          @back="focus.open(null)"
        >
          <template v-if="selected === null">
            <h2 class="gw-title" data-focus-start tabindex="-1">{{ courseName || '课程知识图谱' }}</h2>
            <p class="gw-muted">
              <span v-if="graphVersion !== null" data-test="sg-version">已发布版本 v{{ graphVersion }}</span>
              <template v-if="summary"> · {{ summary.totalNodes }} 个知识点，{{ summary.totalEdges }} 条关系</template>
            </p>
            <p v-if="courseId" class="gw-muted">
              <RouterLink class="gw-link" :to="{ name: COURSE_ROUTE, params: { cid: courseId } }">返回课程页面</RouterLink>
            </p>
            <section v-if="learningEnabled && learningStatus === 'ready'" aria-labelledby="gw-progress">
              <h3 id="gw-progress" class="gw-h3">我的进度</h3>
              <div class="gw-bar" role="img" :aria-label="`已掌握 ${progress.done} 个，共 ${progress.total} 个`"><i :style="{ width: `${progress.percent}%` }" /></div>
              <p class="gw-muted">已掌握 {{ progress.done }} 个，学习中 {{ progress.learning }} 个，共 {{ progress.total }} 个</p>
            </section>
          </template>

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
              <button v-if="learningRetryable" type="button" class="gw-btn gw-btn--ghost" data-test="sg-learning-retry" @click="reloadLearning">重试</button>
            </div>

            <template v-else-if="learningStatus === 'ready'">
              <p v-if="learningNotice !== null" class="gw-note" :class="learningNotice.tone === 'error' ? 'gw-note--danger' : 'gw-note--ok'" data-test="sg-learning-notice" :data-tone="learningNotice.tone">
                {{ learningNotice.text }}
              </p>

              <!-- 选中后推荐收成一条可折叠的摘要：折叠时显示第一项，保持「标记 → 推荐刷新」的流程 -->
              <button
                v-if="selected !== null"
                type="button"
                class="gw-next__head"
                data-test="gw-next-toggle"
                :aria-expanded="nextOpen"
                @click="nextOpen = !nextOpen"
              >
                <span class="gw-next__title">下一步推荐</span>
                <span v-if="!nextOpen && recommendations[0]" class="gw-next__peek">1. {{ recommendations[0].name }}</span>
                <AppIcon :name="nextOpen ? 'chevronDown' : 'chevron'" />
              </button>
              <Recommendations
                v-show="selected === null || nextOpen"
                :state="recommendState"
                :items="recommendations"
                :total-eligible="totalEligible"
                :version="graphVersion"
                :loading="recommendLoading"
                :error="recommendError"
                :selected-id="selected"
                :narrative="learningPath?.narrative ?? null"
                :narrative-ids="learningPath?.narrativeIds ?? null"
                @select="focus.open"
                @locate="onUnlockLocate"
                @retry="refreshRecommend"
              />

              <section v-if="selected !== null" class="student-graph__mastery" data-test="sg-mastery" aria-labelledby="sg-mastery-title">
                <h3 id="sg-mastery-title" class="gw-h3">掌握标记</h3>
                <p class="gw-muted" data-test="sg-mastery-target">
                  知识点：{{ selectedName }} · 当前：{{ MASTERY_LABELS[statusOf(selected)] }}
                </p>
                <div class="gw-seg" role="group" aria-label="掌握状态">
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
            </template>
          </div>

          <p v-if="selected === null" class="gw-hint" data-test="sg-mastery-hint">在图中或列表中选择知识点，查看定义、标记掌握状态和原文出处。</p>
          <KnowledgeDetail
            :show-close="false"
            v-if="selected !== null"
            :kp-id="selected"
            @select-knowledge-point="focus.open"
            @close="focus.open(null)"
            @course-forbidden="leaveForbidden"
          />
          <!-- 详情态下版本号仍然可见（概览态在课程标题下） -->
          <p v-if="selected !== null && graphVersion !== null" class="gw-hint" data-test="sg-version">已发布版本 v{{ graphVersion }}</p>
        </GraphSidePanel>

        <div v-if="!docked && overlayOpen" class="gw-scrim" aria-hidden="true" @click="closePanel" />

        <!-- 画布区 -->
        <div class="gw-stage">
          <div class="gw-tl">
            <div class="gw-tl__row">
              <button v-if="!panelVisible" ref="panelToggle" type="button" class="gw-tool" aria-label="显示说明面板" data-test="gw-panel-open" @click="openPanel">
                <AppIcon name="panel" />
              </button>
              <GraphOverlay as="form" class="gw-search" role="search" @submit.prevent="onLocate">
                <AppIcon name="search" :size="16" />
                <input
                  type="search"
                  aria-label="搜索知识点"
                  placeholder="搜索知识点，回车定位"
                  autocomplete="off"
                  :value="filters.state.value.query"
                  @input="onQuery"
                />
              </GraphOverlay>
              <ChapterMenu :chapters="chapterItems" :current-id="chapterId" :disabled="mode !== 'graph'" @jump="jumpChapter" />
            </div>
            <GraphOverlay v-if="searchNotice" as="p" class="gw-notice" data-test="sg-search-notice" role="status">{{ searchNotice }}</GraphOverlay>
            <GraphOverlay v-if="linkNotice" as="p" class="gw-notice" data-test="sg-link-notice" role="status">{{ linkNotice }}</GraphOverlay>
            <GraphOverlay v-if="activeChapter" as="p" class="gw-chip-on" data-test="gw-chapter-chip" role="status">
              已定位：{{ activeChapter.title }}
              <button type="button" class="gw-chip-on__x" aria-label="取消章节高亮" @click="clearChapter"><AppIcon name="close" :size="14" /></button>
            </GraphOverlay>
            <LocalViewBar
              v-if="localView.view.value"
              :name="localName"
              :hidden-count="hiddenByLocal"
              :hops="localView.view.value.hops"
              @set-hops="localView.setHops"
              @restore="localView.clear"
            />
          </div>

          <GraphOverlay class="gw-tr" role="toolbar" aria-label="画布工具">
            <button type="button" class="gw-tool" aria-label="图例与筛选" :aria-pressed="legendOpen" :disabled="mode !== 'graph'" @click="setLegendOpen(!legendOpen)">
              <AppIcon name="filter" />
            </button>
            <button type="button" class="gw-tool" :aria-label="`切换布局，当前：${layoutLabel}`" :disabled="mode !== 'graph'" data-test="gw-layout-toggle" @click="toggleLayout">
              <AppIcon name="overview" />
            </button>
            <div class="gw-tr__sep" aria-hidden="true" />
            <div role="group" aria-label="视图切换" class="gw-tr__modes">
              <button type="button" class="gw-tool" aria-label="图谱视图" data-test="sg-mode-graph" :aria-pressed="mode === 'graph' ? 'true' : 'false'" @click="mode = 'graph'">
                <AppIcon name="graph" />
              </button>
              <button type="button" class="gw-tool" aria-label="卡片视图" data-test="sg-mode-cards" :aria-pressed="mode === 'cards' ? 'true' : 'false'" @click="mode = 'cards'">
                <AppIcon name="list" />
              </button>
            </div>
          </GraphOverlay>

          <!-- 单击节点后的轻量预览：不打开侧栏；再次单击该节点或点「查看详情」才打开 -->
          <GraphPreviewCard
            v-if="preview && mode === 'graph'"
            :name="preview.name"
            :type="preview.type"
            :chapter="preview.chapter"
            :mastery="preview.mastery"
            :mastery-text="preview.masteryText"
            :prerequisites="preview.prerequisites"
            :unlocks="preview.unlocks"
            :local-active="localView.view.value?.id === preview.id"
            @close="focus.clearPreview"
            @open="focus.open(preview.id)"
            @toggle-local="localView.toggle(preview.id)"
          />

          <div v-if="mode === 'graph'" class="student-graph__canvas" data-test="sg-graph">
            <GraphCanvas
              ref="canvas"
              enhanced
              :graph="canvasGraph"
              :layout="filters.layout.value"
              :positions="positions"
              :scope="chapterId === null ? null : chapterKpIds"
              @node-click="onCanvasNode"
              @blank-click="focus.clearPreview"
            />
          </div>
          <div v-else class="gw-list" aria-label="知识点列表">
            <p class="gw-hint">列表与图谱使用同一组筛选和选中状态，键盘可逐项访问。</p>
            <KnowledgeCards :cards="cards" :selected-id="selected" @select="focus.open" />
          </div>

          <!-- 底部折叠条（Bloom 的 Card list）：显示数量，展开即列表视图，是画布的键盘等价路径 -->
          <GraphOverlay class="gw-count" role="group" aria-label="知识点概览">
            <span>显示 <b>{{ canvasGraph?.nodes.length ?? 0 }}</b> / {{ summary?.totalNodes ?? 0 }}</span>
            <span class="gw-count__sel">已选 {{ highlightId === null ? 0 : 1 }}</span>
            <button type="button" class="gw-count__btn" data-test="sg-count-toggle" :aria-expanded="mode === 'cards'" @click="toggleMode">
              {{ mode === 'cards' ? '收起列表' : '展开列表' }}<AppIcon :name="mode === 'cards' ? 'chevronDown' : 'expand'" :size="16" />
            </button>
          </GraphOverlay>

          <GraphLegend
            v-if="mode === 'graph'"
            :open="legendOpen"
            :hidden-relations="hiddenRelations"
            :hidden-types="hiddenTypes"
            :relation-counts="relationCounts"
            :type-counts="typeCounts"
            @update:open="setLegendOpen"
            @toggle-relation="filters.toggleRelationType"
            @toggle-type="toggleType"
            @restore="restoreAllFilters"
          />
        </div>
      </template>
    </div>
  </section>
</template>

<style scoped>
.student-graph {
  display: grid;
  min-height: 0;
  height: auto;
}
.student-graph__learning {
  display: grid;
  gap: 12px;
}
.student-graph__mastery {
  display: grid;
  gap: 8px;
}
/* 画布填满工作区（浮层绝对定位在它上面） */
.student-graph__canvas {
  position: absolute;
  inset: 0;
}
.student-graph__canvas :deep(.graph-canvas) {
  position: absolute;
  inset: 0;
}
</style>
