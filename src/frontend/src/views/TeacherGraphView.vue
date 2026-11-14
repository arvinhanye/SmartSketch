<script setup lang="ts">
import PageSheet from '../components/PageSheet.vue'
import AppIcon from '../components/AppIcon.vue'
import PageHeader from '../components/PageHeader.vue'
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, RouterLink, useRoute, useRouter } from 'vue-router'
import { HTTP_CLIENT_KEY } from '../api/client'
import { COURSES_API_KEY } from '../api/courses'
import { createDraftGraphApi, DRAFT_GRAPH_API_KEY } from '../api/graph'
import { createKnowledgeDetailApi, KNOWLEDGE_DETAIL_API_KEY, KNOWLEDGE_DELETION_API_KEY } from '../api/knowledgeDetail'
import { createNodeEditApi, NODE_EDIT_API_KEY } from '../api/nodeEdit'
import { createRelationsApi, RELATIONS_API_KEY } from '../api/relations'
import CanvasEditLayer from '../components/canvas/CanvasEditLayer.vue'
import GraphCanvas from '../components/GraphCanvas.vue'
import GraphLegend from '../components/GraphLegend.vue'
import GraphSearch, { type SearchOption } from '../components/GraphSearch.vue'
import GraphToolbar from '../components/GraphToolbar.vue'
import KnowledgeDetail from '../components/KnowledgeDetail.vue'
import NodeCreator from '../components/NodeCreator.vue'
import NodeDeletionConfirm from '../components/NodeDeletionConfirm.vue'
import { useNodeDeletion } from '../composables/useNodeDeletion'
import ToastNotice from '../components/ToastNotice.vue'
import NodeEditor from '../components/NodeEditor.vue'
import RelationEditor from '../components/RelationEditor.vue'
import { readArrangement, writeArrangement, type Arrangement } from '../composables/useArrangementPreference'
import { useAutoDismiss } from '../composables/useAutoDismiss'
import { useCanvasEditing } from '../composables/useCanvasEditing'
import { useEditHistory } from '../composables/useEditHistory'
import { useNodeHistory } from '../composables/useNodeHistory'
import { useRelationHistory } from '../composables/useRelationHistory'
import { useGraphLayout } from '../composables/useGraphLayout'
import { useGraphShortcuts } from '../composables/useGraphShortcuts'
import { readPanelWidth, writePanelWidth } from '../composables/usePanelWidthPreference'
import { applyFocusStates } from '../graph/focusStates'
import { kpIdFromElementId, nodeElementId } from '../graph/adapter'
import type { GraphLayoutName } from '../graph/lifecycle'
import {
  chapterOptions,
  countNodeTypes,
  NODE_TYPE_LABELS,
  NODE_TYPE_ORDER,
  RELATION_TYPE_ORDER,
  toggledNodeTypes,
  useGraphFilters,
  type KnowledgePointType,
} from '../composables/useGraphFilters'
import { nodePickerOptions, useNodeCreator } from '../composables/useNodeCreator'
import { useRelationEditor } from '../composables/useRelationEditor'
import { useSelectionGuard, useTeacherGraph } from '../composables/useTeacherGraph'
import {
  COURSE_ROUTE,
  homeRouteFor,
  MATERIALS_ROUTE,
  NOTICE_COURSE_FORBIDDEN,
  ROOT_ROUTE,
  TEACHER_GRAPH_ROUTE,
} from '../router'
import { useSessionStore } from '../stores/session'

/**
 * 教师图谱编辑页（H14，ADR-067）：草稿画布 + 左侧可调宽面板（H06 详情 / H07 节点编辑 / H08 关系编辑）。
 * 草稿读取与课程教师校验在 `useTeacherGraph`；筛选在 `useGraphFilters`；连边在 `useRelationEditor`；本页只做组装。
 * 三个编辑器共用课程 store 里的草稿，保存/删除/连边成功后画布随之更新，失败时草稿不变。
 */
const coursesApi = inject(COURSES_API_KEY, null)
if (coursesApi === null) throw new Error('TeacherGraphView 需要注入 COURSES_API_KEY')
const client = inject(HTTP_CLIENT_KEY, null)
function fallbackClient() {
  if (client === null) throw new Error('TeacherGraphView 需要注入各功能 API 或 HTTP_CLIENT_KEY')
  return client
}
const graphApi = inject(DRAFT_GRAPH_API_KEY, null) ?? createDraftGraphApi(fallbackClient())
const relationsApi = inject(RELATIONS_API_KEY, null) ?? createRelationsApi(fallbackClient())

const route = useRoute()
const router = useRouter()
const session = useSessionStore()

// 离开本路由即为 null：composable 中止在途请求
const courseId = computed(() => {
  const cid = route.params.cid
  return route.name === TEACHER_GRAPH_ROUTE && typeof cid === 'string' && cid !== '' ? cid : null
})

// 被拒或会话失效时的强制离开不再询问未保存的修改（此时已无法保存）
let forceLeave = false

function leaveForbidden(): void {
  forceLeave = true
  const role = session.role
  void router.replace(
    role === null ? { name: ROOT_ROUTE } : { name: homeRouteFor(role), query: { notice: NOTICE_COURSE_FORBIDDEN } },
  )
}

const teacher = useTeacherGraph({ coursesApi, graphApi, courseId, onCourseForbidden: leaveForbidden })
const { status, error, retryable, courseName, graph, chapters, refreshing, refreshError } = teacher

const relations = useRelationEditor({
  api: relationsApi,
  onRefreshNeeded: teacher.refresh,
  onCourseForbidden: leaveForbidden,
})

// ---------------------------------------------------------------- 撤销 / 重做（UI-GRAPH-UNDO-04）
// 有写请求在途、或编辑面板里有未保存的修改时不执行：撤销知识点字段会重新读取面板，不能把没保存的内容冲掉
const writesBusy = () => relations.saving.value || nodeEditor.value?.saving === true || creator.busy.value || deletion?.status.value === 'deleting'
const history = useEditHistory({ busy: () => writesBusy() || isDirty(), shortcuts: true })
/** 带撤销记录的关系编辑：画布上的直接操作与“编辑关系”页签都用它，两处的修改进同一份记录 */
const recordedRelations = useRelationHistory(relations, history)
useAutoDismiss(history.notice, history.dismissNotice, { ms: 4500, keep: (value) => value.tone === 'error' })
const historyBlocked = computed(() => history.working.value || writesBusy() || nodeEditor.value?.dirty === true)
const undoTitle = computed(() => {
  if (nodeEditor.value?.dirty === true) return '有未保存的修改，先保存或放弃后才能撤销'
  return history.undoLabel.value === null ? '没有可撤销的操作' : `撤销：${history.undoLabel.value}（Ctrl/⌘ + Z）`
})
const redoTitle = computed(() => {
  if (nodeEditor.value?.dirty === true) return '有未保存的修改，先保存或放弃后才能重做'
  return history.redoLabel.value === null ? '没有可重做的操作' : `重做：${history.redoLabel.value}（Ctrl/⌘ + Shift + Z）`
})

// 画布取连边编辑器的派生图：含保存中的临时边与成环冲突标色
// UI-GRAPH-FIND-01：搜索只高亮命中，不把其余知识点从画布上移除
const filters = useGraphFilters(() => (graph.value === null ? null : relations.canvasData.value), { search: 'highlight' })
const { selected, visible, summary, isDefault, selectedHidden } = filters
/** 交给画布的图：有命中时命中带 `match`、其余淡化（选中的节点不淡化） */
// UX-REVIEW-DEDUP-01：从审核页“在图谱中查看”带来的一对疑似重复知识点（`?pair=a,b`）
const pairDismissed = ref(false)
const pairView = computed<{ ids: string[]; names: string[] } | { missing: true } | null>(() => {
  const raw = route.query.pair
  const g = graph.value
  if (pairDismissed.value || typeof raw !== 'string' || raw === '' || g === null) return null
  const ids = [...new Set(raw.split(',').filter((id) => id !== ''))]
  if (ids.length !== 2) return null
  const found = ids.map((id) => g.nodes.find((n) => n.id === id))
  if (found.some((node) => node === undefined)) return { missing: true }
  return { ids, names: found.map((node) => node!.name) }
})
const pairIds = computed(() => (pairView.value !== null && 'ids' in pairView.value ? pairView.value.ids : []))
function dismissPair(): void {
  pairDismissed.value = true
  const { pair: _pair, ...rest } = route.query
  void router.replace({ query: rest })
}
/** 画布建好后把镜头适应到这一对（画布还没建好时调用会被忽略，所以等它的 ready 事件） */
function onCanvasReady(): void {
  if (pairIds.value.length === 2) canvas.value?.fitTo(pairIds.value)
}

/** 交给画布的图：搜索命中优先；没有搜索时高亮正在查看的这一对。命中带 `match`、其余淡化（选中的节点不淡化） */
const canvasGraph = computed(() => {
  const v = visible.value
  const hits = filters.matches.value
  const marked = hits.length > 0 ? hits.map((hit) => hit.kpId) : pairIds.value
  if (v === null) return v
  const focused = marked.length === 0 ? v : applyFocusStates(v, { selectedId: null, matchedIds: new Set(marked.map(nodeElementId)), chapterIds: null, fade: 'standard' })
  // UI-GRAPH-EDIT-02：工具条对应的那条关系线加粗，看得出正在改哪一条
  const openRelation = editing.edgeTool.value?.relationId
  if (openRelation === undefined) return focused
  return { nodes: focused.nodes, edges: focused.edges.map((e) => (e.data.relationId === openRelation ? { ...e, states: [...(e.states ?? []), 'active' as const] } : e)) }
})

// 节点类型图例：计数取整张草稿图；点击与工具栏“筛选”里的知识点类型是同一份状态
const allTypes = NODE_TYPE_ORDER
const typeCounts = computed(() => countNodeTypes(relations.canvasData.value?.nodes ?? []))
const hiddenTypes = computed(() => allTypes.filter((t) => !filters.state.value.nodeTypes.includes(t)))
function toggleType(type: KnowledgePointType): void {
  filters.state.value = { ...filters.state.value, nodeTypes: toggledNodeTypes(filters.state.value.nodeTypes, type) }
}

type PanelTab = 'detail' | 'edit' | 'relations' | 'create'
const tab = ref<PanelTab>('detail')
const tabs: Array<{ value: PanelTab; label: string }> = [
  { value: 'detail', label: '详情' },
  { value: 'edit', label: '编辑知识点' },
  { value: 'relations', label: '编辑关系' },
]

const nodeEditor = ref<InstanceType<typeof NodeEditor> | null>(null)
const isDirty = () => nodeEditor.value?.dirty === true

const guard = useSelectionGuard({ selected, apply: filters.select, isDirty })
const pendingName = computed(() => {
  const target = guard.pending.value
  if (target === null || target.kpId === null) return null
  return graph.value?.nodes.find((n) => n.id === target.kpId)?.name ?? target.kpId
})
const currentName = computed(() => graph.value?.nodes.find((n) => n.id === selected.value)?.name ?? null)

// L13-2：搜索框回车定位；选中经过「未保存修改」守卫，画布聚焦到该节点
const canvas = ref<InstanceType<typeof GraphCanvas> | null>(null)
const searchNotice = ref<string | null>(null)
// UI-GRAPH-UNDO-04：教师页复用学生页的搜索框——候选、计数、上一个 / 下一个；定位仍然是“选中并聚焦”，经过未保存修改的确认
const searchBox = ref<InstanceType<typeof GraphSearch> | null>(null)
const searchCursor = ref(-1)
const searchOptions = computed<SearchOption[]>(() => {
  const g = graph.value
  if (g === null) return []
  const byId = new Map(g.nodes.map((n) => [n.id, n]))
  const titles = new Map(chapters.value.map((c) => [c.id, c.title]))
  return filters.matches.value.map((hit) => {
    const node = byId.get(hit.kpId)
    const chapter = node?.chapter_id == null ? '未分章' : (titles.get(node.chapter_id) ?? '未分章')
    return { kpId: hit.kpId, name: hit.name, alias: hit.alias, meta: node === undefined ? chapter : `${chapter} · ${NODE_TYPE_LABELS[node.type]}` }
  })
})
watch(filters.matches, () => {
  searchCursor.value = -1
})
function goToHit(index: number): void {
  const hit = filters.matches.value[index]
  if (hit === undefined) return
  searchCursor.value = index
  searchNotice.value = null
  // C05-1：有未保存修改时先确认；画布只在选中真正切换后才聚焦，取消则画布与详情都留在原节点
  guard.request(hit.kpId, { then: (target) => target !== null && canvas.value?.focus(target) })
}
function onSearchStep(delta: 1 | -1): void {
  if (graph.value === null) return
  const total = filters.matches.value.length
  if (total === 0) {
    searchNotice.value = filters.state.value.query.trim() === '' ? null : '未找到匹配的知识点，可调整关键字或筛选条件。'
    return
  }
  const from = searchCursor.value
  goToHit(from < 0 ? (delta === 1 ? 0 : total - 1) : (from + delta + total) % total)
}
function onSearchPick(kpId: string): void {
  goToHit(filters.matches.value.findIndex((hit) => hit.kpId === kpId))
}
function onSearchQuery(query: string): void {
  filters.state.value = { ...filters.state.value, query }
  searchNotice.value = null
}

// ---- 图例：与学生页同一个组件，浮在画布左下角；关系与类型的隐藏状态仍是筛选状态那一份
const legendOpen = ref(typeof window === 'undefined' || window.innerWidth >= 1280)
const hiddenRelations = computed(() => RELATION_TYPE_ORDER.filter((t) => !filters.state.value.relationTypes.includes(t)))
const relationCounts = computed(() => {
  const counts = Object.fromEntries(RELATION_TYPE_ORDER.map((t) => [t, 0])) as Record<(typeof RELATION_TYPE_ORDER)[number], number>
  for (const edge of relations.canvasData.value?.edges ?? []) counts[edge.data.type] += 1
  return counts
})
function restoreLegend(): void {
  filters.state.value = { ...filters.state.value, relationTypes: [...RELATION_TYPE_ORDER], nodeTypes: [...allTypes] }
}

// L11：画布之外的可访问选择方式（键盘与自动化可用），选择同样经过「未保存修改」守卫
const pickerOptions = computed(() => nodePickerOptions(graph.value))
function onPick(event: Event): void {
  const value = (event.target as HTMLSelectElement).value
  // 选中后画布聚焦到该知识点（与搜索定位一致），否则下拉选择与画布不同步；有未保存修改时确认后才聚焦
  guard.request(value === '' ? null : value, { then: (target) => target !== null && canvas.value?.focus(target) })
}
// 详情里的关联知识点链接同样要让画布跟随
function onSelectRelated(kpId: string | null): void {
  guard.request(kpId, { then: (target) => target !== null && canvas.value?.focus(target) })
}

// L11：新建知识点（ADR-035：必带来源，来源取自当前选中知识点）
const nodeEditApi = inject(NODE_EDIT_API_KEY, null) ?? createNodeEditApi(fallbackClient())
const detailApi = inject(KNOWLEDGE_DETAIL_API_KEY, null) ?? createKnowledgeDetailApi(fallbackClient())
const creator = useNodeCreator({
  api: nodeEditApi,
  detailApi,
  sourceKpId: selected,
  onCreated: async (kp) => {
    history.invalidateRedo()
    // refresh 的结果同时验证课程作用域、请求代次和页面存活；失效或读回失败不再切换选中。
    if (await teacher.refresh()) guard.request(kp.id)
  },
})
function openCreator(): void {
  tab.value = 'create'
  void creator.open()
}
watch(selected, () => {
  if (tab.value === 'create' && creator.success.value === null) void creator.open()
})
// 进入「编辑关系」时，已选中的知识点直接作为起点（不必在图上或下拉里再选一遍）
watch(tab, (next) => {
  if (next === 'relations' && relations.fromId.value === null && selected.value !== null) relations.pickNode(selected.value)
})

/** 画布点击：连线点选中先交给连线；关系页签下用于依次点选起点、终点；其余页签切换当前知识点 */
function onNodeClick(kpId: string): void {
  if (editing.consumeNodeClick(kpId)) return
  editing.dismiss()
  if (tab.value === 'relations') relations.pickNode(kpId)
  else guard.request(kpId)
}

// ---------------------------------------------------------------- 画布上的直接操作（UI-GRAPH-EDIT-02）
const editing = useCanvasEditing({
  relations: recordedRelations,
  // 删除提示上的“撤销”与工具栏的撤销是同一个动作
  undoLast: () => history.undo(),
  anchors: () => canvas.value?.nodeAnchors() ?? [],
  // 查看、编辑、删除都要先切换选中：经过“未保存修改”确认，确认后才切页签
  onDetail: (kpId) => guard.request(kpId, { then: (target) => { if (target !== null) tab.value = 'detail' } }),
  onEdit: (kpId) => guard.request(kpId, { then: (target) => { if (target !== null) tab.value = 'edit' } }),
  onDelete: (kpId) =>
    guard.request(kpId, {
      then: (target) => {
        if (target === null) return
        tab.value = 'edit'
        // 等编辑面板载入该知识点后再打开它自己的删除确认
        void nextTick(() => nodeEditor.value?.requestDelete())
      },
    }),
})
// 删除提示只对应“刚才那次删除”：之后记录里的最后一步变了（又做了别的、或已被撤销），提示就收起
let undoAnchor: string | null = null
watch(editing.undo, (now) => {
  undoAnchor = now === null ? null : history.undoLabel.value
})
watch(history.undoLabel, (label) => {
  if (editing.undo.value !== null && label !== undoAnchor) editing.dismissUndo()
})

// 节点历史的课程作用域、写入与读回同步由组合式逻辑负责。
const nodeHistory = useNodeHistory({
  api: nodeEditApi,
  history,
  courseId,
  refresh: teacher.refresh,
  reloadEditor: async (kpId) => selected.value !== kpId || nodeEditor.value === null ? true : nodeEditor.value.reload(),
  onCourseForbidden: leaveForbidden,
})

/** 画布上发起的关系操作失败时的说明：在“编辑关系”页签里由面板自己显示，这里不重复 */
const canvasError = computed(() => (tab.value === 'relations' ? null : relations.error.value))
const canvasConflict = computed(() => (tab.value === 'relations' ? null : (relations.conflict.value?.path.map((p) => p.name) ?? null)))
function dismissCanvasError(): void {
  relations.error.value = null
  relations.dismissConflict()
  editing.undoError.value = null
}

// 页面级提示：删除成功、当前节点被刷新掉（面板随选中清空而回到空态，提示留在页面上）
const notice = ref<string | null>(null)
let justDeleted: string | null = null

function onDeleted(kpId: string): void {
  history.invalidateRedo()
  justDeleted = kpId
  notice.value = '知识点已删除，与它相连的关系已一并删除。'
  filters.select(null)
}

const deletionApi = inject(KNOWLEDGE_DELETION_API_KEY, null) ?? (client === null ? null : createKnowledgeDetailApi(client))
const deletion = deletionApi === null ? null : useNodeDeletion({
  api: deletionApi, courseId, selectedId: selected, identity: computed(() => session.accessToken),
  onCourseForbidden: leaveForbidden,
  onDeleted: async (kpId, impact) => {
    history.invalidateRedo()
    justDeleted = kpId
    notice.value = impact !== null && impact.deleted_count > 1
      ? `已删除「${impact.root_name}」及 ${impact.deleted_count - 1} 个下级知识点，相关关系一并删除。`
      : '知识点已删除，与它相连的关系已一并删除。'
    // 删除确认仍属于当前选中时立即清空；刷新期间用户可能已选中别的节点并开始编辑。
    filters.select(null)
    await teacher.refresh()
  },
})

// 该侦听在面板收到新的 kpId 之前运行，此时 isDirty 仍反映被移除节点的表单
watch(selected, (next, prev) => {
  if (next !== null) {
    notice.value = null
    return
  }
  if (prev === null) return
  if (justDeleted === prev) {
    justDeleted = null
    return
  }
  if (graph.value !== null && !graph.value.nodes.some((n) => n.id === prev)) {
    notice.value = isDirty()
      ? '当前知识点已不在草稿中（可能已被他人删除），未保存的修改已丢弃。'
      : '当前知识点已不在草稿中（可能已被他人删除）。'
  }
})

const confirmBox = ref<HTMLElement | null>(null)
watch(
  () => guard.pending.value,
  async (next) => {
    if (next === null) return
    await nextTick()
    confirmBox.value?.focus()
  },
)

// 离开页面或换课前，未保存的节点修改需确认
const DISCARD_PROMPT = '当前知识点有未保存的修改，离开将丢失这些修改。确定离开？'
function confirmLeave(): boolean {
  if (forceLeave || session.role === null) return true
  return !isDirty() || window.confirm(DISCARD_PROMPT)
}
onBeforeRouteLeave(confirmLeave)
onBeforeRouteUpdate((to, from) => (to.params.cid === from.params.cid ? true : confirmLeave()))

// 刷新或关闭标签页时由浏览器提示
function onBeforeUnload(event: BeforeUnloadEvent): void {
  if (!isDirty()) return
  event.preventDefault()
  event.returnValue = ''
}
onMounted(() => window.addEventListener('beforeunload', onBeforeUnload))
onBeforeUnmount(() => window.removeEventListener('beforeunload', onBeforeUnload))

const chapterList = computed(() => {
  const full = graph.value === null ? null : relations.canvasData.value
  return full === null ? [] : chapterOptions(full, chapters.value)
})
const layoutSource = computed(() => {
  const g = graph.value === null ? null : relations.canvasData.value
  if (g === null) return null
  return {
    nodes: g.nodes.map(n => ({ id: n.data.kpId, chapter: n.data.chapterId })),
    edges: g.edges.map(e => ({ id: e.data.relationId, source: kpIdFromElementId(e.source), target: kpIdFromElementId(e.target), type: e.data.type })),
    chapterOrder: [...chapters.value].sort((a,b) => a.order - b.order || a.id.localeCompare(b.id)).map(c => c.id),
  }
})
// UI-GRAPH-STABLE-03：只增删关系或删掉知识点时节点位置不动，画布不重建；需要时由教师点“重新排布”
const { positions, radialPositions, recommended, error: layoutError, stale: layoutStale, relayout } = useGraphLayout(() => layoutSource.value, undefined, true, { stable: true })

// 排布：层次（章节分区）/ 径向 / 力导向。层次布局把单章大树拉成长条时，默认用径向；教师手动选择后不再自动改，并按课程记住
// 教师在本课程选过的布局记在本浏览器里，下次进入直接使用（不再按推荐值重选）
const storedArrangement = readArrangement(courseId.value)
const arrangement = ref<Arrangement>(storedArrangement ?? 'hierarchical')
let arrangementChosen = storedArrangement !== null
function chooseArrangement(next: GraphLayoutName | 'radial'): void {
  arrangementChosen = true
  arrangement.value = next
  writeArrangement(courseId.value, next)
}
// 同一页面实例里换课程（路由参数变化）：改用新课程记住的布局，没有就回到推荐值
watch(courseId, (cid) => {
  // 换课程：上一门课的撤销记录不带过来
  history.clear()
  const stored = readArrangement(cid)
  arrangementChosen = stored !== null
  arrangement.value = stored ?? recommended.value ?? 'hierarchical'
})
watch(recommended, (next) => {
  if (next !== null && !arrangementChosen) arrangement.value = next
})
const canvasLayout = computed<GraphLayoutName>(() => (arrangement.value === 'force' ? 'force' : 'hierarchical'))
const canvasPositions = computed(() => (arrangement.value === 'radial' && radialPositions.value !== null ? radialPositions.value : positions.value))
// 教师页没有顶部浮层：整图适应时上、左留白收紧；右侧与底部仍避开缩放工具与小地图
const TEACHER_FIT_PADS = { left: 40, top: 40, right: 96 }
// 面板只在有限高度内滚动；宽度调整不会改变草稿或选择状态。
const workspace = ref<HTMLElement | null>(null)
const workspaceWidth = ref(0)
const preferredWidth = ref(readPanelWidth('teacher-graph') ?? 360)
const minWidth = computed(() => Math.min(280, workspaceWidth.value * .4))
const maxWidth = computed(() => Math.max(minWidth.value, Math.min(640, workspaceWidth.value - 360)))
const panelWidth = computed(() => Math.min(maxWidth.value, Math.max(minWidth.value, preferredWidth.value)))
function setWidth(value: number): void {
  preferredWidth.value = Math.min(maxWidth.value, Math.max(minWidth.value, value))
  writePanelWidth('teacher-graph', preferredWidth.value)
}
const resizing = ref(false)
function startResize(event: PointerEvent): void {
  if (event.button !== 0) return
  event.preventDefault()
  resizing.value = true
  const handle = event.currentTarget as HTMLElement
  handle.focus()
  handle.setPointerCapture(event.pointerId)
}
function moveResize(event: PointerEvent): void {
  if (resizing.value && workspace.value) setWidth(event.clientX - workspace.value.getBoundingClientRect().left)
}
function endResize(): void { resizing.value = false }
function resizeKey(event: KeyboardEvent): void {
  const values: Record<string, number> = { ArrowLeft: panelWidth.value - 20, ArrowRight: panelWidth.value + 20, Home: minWidth.value, End: maxWidth.value }
  if (values[event.key] === undefined) return
  event.preventDefault()
  setWidth(values[event.key]!)
}
let workspaceObserver: ResizeObserver | null = null
watch(workspace, (element) => {
  workspaceObserver?.disconnect()
  workspaceWidth.value = element?.clientWidth ?? 0
  if (!element || typeof ResizeObserver !== 'function') return
  workspaceObserver = new ResizeObserver(() => { workspaceWidth.value = element.clientWidth })
  workspaceObserver.observe(element)
}, { flush: 'post' })
onBeforeUnmount(() => workspaceObserver?.disconnect())
const empty = computed(() => status.value === 'ready' && graph.value !== null && graph.value.nodes.length === 0)

// 快捷键（UI-GRAPH-FIND-01）：/ 聚焦搜索，F 适应画布，+、- 缩放
useGraphShortcuts({
  search: () => {
    if (searchBox.value === null) return false
    searchBox.value.focus()
  },
  fit: () => (canvas.value === null ? false : void canvas.value.fitTo()),
  zoomIn: () => (canvas.value === null ? false : void canvas.value.zoomBy(1.25)),
  zoomOut: () => (canvas.value === null ? false : void canvas.value.zoomBy(0.8)),
})
</script>

<template>
  <PageSheet
    labelledby="teacher-graph-title"
    class="teacher-graph ui-management ui-teacher-workspace"
    data-test="teacher-graph-page"
    :aria-busy="status === 'loading' ? 'true' : 'false'"
  >
    <header class="teacher-graph__header">
      <PageHeader id="teacher-graph-title" title="编辑课程知识图谱（草稿）" />
      <span v-if="status === 'ready'" class="teacher-graph__badge">草稿</span>
      <p v-if="courseName" class="teacher-graph__course">
        课程：{{ courseName }}<span v-if="status === 'ready'" data-test="tg-draft"> · 草稿，学生在发布前看不到这些修改</span>
      </p>
      <p v-if="courseId" class="teacher-graph__back">
        <RouterLink :to="{ name: COURSE_ROUTE, params: { cid: courseId } }">返回课程</RouterLink>
      </p>
    </header>

    <p v-if="status === 'loading'" data-test="tg-loading" role="status">正在加载草稿图谱…</p>

    <p v-else-if="status === 'not_teacher'" data-test="tg-not-teacher" role="status">
      只有本课程的教师可以编辑草稿图谱。
    </p>

    <div v-else-if="status === 'error'" data-test="tg-error" role="alert">
      <p>{{ error }}</p>
      <button v-if="retryable" type="button" data-test="tg-retry" @click="teacher.reload">重试</button>
    </div>

    <div v-else-if="empty" data-test="tg-empty" role="status">
      <p>草稿中还没有知识点。上传课程资料并处理完成后，知识点会出现在这里。</p>
      <p v-if="courseId && router.hasRoute(MATERIALS_ROUTE)">
        <RouterLink :to="{ name: MATERIALS_ROUTE, params: { cid: courseId } }">去上传资料</RouterLink>
      </p>
    </div>

    <template v-else-if="status === 'ready' && graph !== null">
      <p v-if="notice" data-test="tg-notice" role="status">{{ notice }}</p>
      <ToastNotice v-if="history.notice.value" data-test="tg-history-notice" :tone="history.notice.value.tone" :text="history.notice.value.text" @dismiss="history.dismissNotice" />
      <p v-if="pairView && 'ids' in pairView" class="teacher-graph__pair" data-test="tg-pair-notice" role="status">
        正在查看疑似重复：「{{ pairView.names[0] }}」与「{{ pairView.names[1] }}」
        <button type="button" data-test="tg-pair-dismiss" @click="dismissPair">结束查看</button>
      </p>
      <p v-else-if="pairView" class="teacher-graph__pair" data-test="tg-pair-missing" role="status">
        要查看的知识点已不在草稿中（可能已被合并或删除）。
        <button type="button" data-test="tg-pair-dismiss" @click="dismissPair">知道了</button>
      </p>
      <p v-if="refreshing" data-test="tg-refreshing" role="status">正在刷新草稿图谱…</p>
      <p v-if="refreshError" data-test="tg-refresh-error" role="alert">
        {{ refreshError }}
        <button type="button" data-test="tg-refresh-retry" @click="teacher.refresh">重新刷新</button>
      </p>

      <div ref="workspace" class="teacher-graph__body" :class="{ 'is-resizing': resizing }" :style="{ '--teacher-panel-width': `${panelWidth}px` }">
        <aside class="teacher-graph__filters" aria-label="筛选">
          <GraphToolbar
            v-model="filters.state.value"
            :layout="arrangement"
            :chapters="chapterList"
            :summary="summary"
            :can-clear="!isDefault"
            :selected-hidden="selectedHidden"
            compact
            radial
            hide-relations
            @update:layout="chooseArrangement"
            @clear="filters.clear"
          >
            <template #search>
              <div class="graph-workspace teacher-graph__search">
                <GraphSearch ref="searchBox" :model-value="filters.state.value.query" :options="searchOptions" :cursor="searchCursor" @update:model-value="onSearchQuery" @step="onSearchStep" @pick="onSearchPick" />
              </div>
            </template>
            <template #actions>
              <span class="teacher-graph__history" role="group" aria-label="撤销与重做">
                <button type="button" data-test="tg-undo" :disabled="!history.canUndo.value || historyBlocked" :title="undoTitle" @click="history.undo()">撤销</button>
                <button type="button" data-test="tg-redo" :disabled="!history.canRedo.value || historyBlocked" :title="redoTitle" @click="history.redo()">重做</button>
              </span>
              <button type="button" class="teacher-graph__create" data-test="tg-create-open" :aria-pressed="tab === 'create'" @click="openCreator">
                <AppIcon name="plus" /> 新建知识点
              </button>
            </template>
          </GraphToolbar>
          <p v-if="searchNotice" data-test="tg-search-notice" role="status">{{ searchNotice }}</p>
        </aside>

        <div class="teacher-graph__canvas" data-test="tg-graph">
          <div class="teacher-graph__canvas-bar">
            <p class="teacher-graph__hint" :title="tab === 'relations' ? '在图上依次点击起点和终点来新建关系。' : '点击知识点查看详情或编辑；画布支持缩放与拖拽。'">
              {{ tab === 'relations' ? '在图上依次点击起点和终点来新建关系。' : '点击知识点查看详情或编辑；画布支持缩放与拖拽。' }}
            </p>
            <button v-if="layoutStale && arrangement !== 'force'" type="button" class="teacher-graph__relayout" data-test="tg-relayout" title="关系变了之后节点位置保持不动；点这里按现在的关系重新排布整张图" @click="relayout">
              重新排布
            </button>
            <label class="teacher-graph__picker">
              选择知识点
              <select data-test="tg-node-picker" :value="selected ?? ''" @change="onPick">
                <option value="">（未选择）</option>
                <option v-for="option in pickerOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
              </select>
            </label>
          </div>
          <p v-if="layoutError" role="status" class="ui-muted">章节布局暂不可用，已切换到基础布局。</p>
          <GraphCanvas ref="canvas" :graph="canvasGraph" @ready="onCanvasReady" @edge-click="editing.openEdge" @node-menu="editing.openMenu" @node-hover="editing.onNodeHover" @view-change="editing.onViewChange" @blank-click="editing.onViewChange" :layout="canvasLayout" :arrangement="arrangement === 'radial' ? 'radial' : 'layered'" initial-view="overview" :fit-pads="TEACHER_FIT_PADS" show-label-stat :enhanced="!layoutError" :positions="canvasPositions" audience="teacher" label="课程知识图谱（草稿）" @node-click="onNodeClick">
            <div class="graph-workspace teacher-graph__legend-host">
              <GraphLegend
                :open="legendOpen"
                :hidden-relations="hiddenRelations"
                :hidden-types="hiddenTypes"
                :relation-counts="relationCounts"
                :type-counts="typeCounts"
                @update:open="legendOpen = $event"
                @toggle-relation="filters.toggleRelationType"
                @toggle-type="toggleType"
                @restore="restoreLegend"
              />
            </div>
            <CanvasEditLayer :editing="editing" :error="canvasError" :conflict="canvasConflict" @dismiss-error="dismissCanvasError" />
          </GraphCanvas>
        </div>

        <div
          class="teacher-graph__divider"
          data-test="tg-panel-divider"
          role="separator"
          tabindex="0"
          aria-label="调整知识点面板宽度"
          aria-controls="teacher-knowledge-panel"
          aria-orientation="vertical"
          :aria-valuemin="Math.round(minWidth)"
          :aria-valuemax="Math.round(maxWidth)"
          :aria-valuenow="Math.round(panelWidth)"
          @pointerdown="startResize"
          @pointermove="moveResize"
          @pointerup="endResize"
          @pointercancel="endResize"
          @lostpointercapture="endResize"
          @keydown="resizeKey"
        />
        <div class="teacher-graph__panel" id="teacher-knowledge-panel" :inert="history.working.value">
          <p v-if="nodeEditor?.dirty" class="ui-unsaved" role="status">未保存</p>
          <div class="teacher-graph__tabs" role="group" aria-label="面板切换">
            <button
              v-for="item in tabs"
              :key="item.value"
              type="button"
              :data-test="`tg-tab-${item.value}`"
              :aria-pressed="tab === item.value ? 'true' : 'false'"
              @click="tab = item.value"
            >
              {{ item.label }}
            </button>

          </div>

          <div
            v-if="guard.pending.value"
            ref="confirmBox"
            class="teacher-graph__confirm"
            data-test="tg-discard-confirm"
            role="alertdialog"
            aria-label="放弃未保存的修改？"
            aria-describedby="tg-discard-text"
            tabindex="-1"
          >
            <p id="tg-discard-text">
              「{{ currentName ?? '当前知识点' }}」有未保存的修改，{{ pendingName ? `切换到「${pendingName}」` : '关闭面板' }}将丢弃这些修改。
            </p>
            <button type="button" data-test="tg-discard-yes" @click="guard.confirm">放弃修改并切换</button>
            <button type="button" data-test="tg-discard-no" @click="guard.cancel">继续编辑</button>
          </div>

          <template v-if="tab === 'detail'">
            <KnowledgeDetail
              v-if="selected !== null"
              :kp-id="selected"
              :allow-delete="deletion !== null"
              @delete="deletion?.open($event)"
              @select-knowledge-point="onSelectRelated"
              @close="guard.request(null)"
              @course-forbidden="leaveForbidden"
            />
            <p v-else data-test="tg-detail-empty" role="status">在图谱中点击一个知识点查看详情。</p>
            <NodeDeletionConfirm v-if="deletion !== null && deletion.kpId.value !== null"
              :status="deletion.status.value" :impact="deletion.impact.value" :error="deletion.error.value"
              :name="deletion.impact.value?.root_name ?? currentName ?? '该知识点'"
              @confirm="deletion.confirm($event)" @cancel="deletion.close"
              @retry="deletion.kpId.value !== null && deletion.open(deletion.kpId.value)" />
          </template>

          <!-- 切到其他页签时保留编辑面板，未保存的修改不丢 -->
          <NodeEditor
            v-show="tab === 'edit'"
            ref="nodeEditor"
            :kp-id="selected"
            @deleted="onDeleted"
            @saved="nodeHistory.onSaved"
            :history-busy="history.working.value"
            @refresh-needed="teacher.refresh"
            @close="guard.request(null)"
            @course-forbidden="leaveForbidden"
          />

          <RelationEditor v-if="tab === 'relations'" :editor="recordedRelations" />
          <NodeCreator v-if="tab === 'create'" :creator="creator" :source-name="currentName" />
        </div>
      </div>
    </template>
  </PageSheet>
</template>
