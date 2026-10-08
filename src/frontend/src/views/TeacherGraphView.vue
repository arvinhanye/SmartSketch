<script setup lang="ts">
import PageSheet from '../components/PageSheet.vue'
import AppIcon from '../components/AppIcon.vue'
import PageHeader from '../components/PageHeader.vue'
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, RouterLink, useRoute, useRouter } from 'vue-router'
import { HTTP_CLIENT_KEY } from '../api/client'
import { COURSES_API_KEY } from '../api/courses'
import { createDraftGraphApi, DRAFT_GRAPH_API_KEY } from '../api/graph'
import { createKnowledgeDetailApi, KNOWLEDGE_DETAIL_API_KEY } from '../api/knowledgeDetail'
import { createNodeEditApi, NODE_EDIT_API_KEY } from '../api/nodeEdit'
import { createRelationsApi, RELATIONS_API_KEY } from '../api/relations'
import GraphCanvas from '../components/GraphCanvas.vue'
import GraphToolbar from '../components/GraphToolbar.vue'
import KnowledgeDetail from '../components/KnowledgeDetail.vue'
import NodeCreator from '../components/NodeCreator.vue'
import NodeEditor from '../components/NodeEditor.vue'
import RelationEditor from '../components/RelationEditor.vue'
import { useGraphLayout } from '../composables/useGraphLayout'
import { kpIdFromElementId } from '../graph/adapter'
import { chapterOptions, locateNode, useGraphFilters } from '../composables/useGraphFilters'
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

// 画布取连边编辑器的派生图：含保存中的临时边与成环冲突标色
const filters = useGraphFilters(() => (graph.value === null ? null : relations.canvasData.value))
const { selected, visible, summary, isDefault, selectedHidden } = filters

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
function onLocate(query: string): void {
  const full = graph.value === null ? null : relations.canvasData.value
  const kpId = full === null ? null : locateNode(full, filters.state.value, query)
  searchNotice.value = kpId === null ? '未找到匹配的知识点，可调整关键字或筛选条件。' : null
  if (kpId === null) return
  // C05-1：有未保存修改时先确认；画布只在选中真正切换后才聚焦，取消则画布与详情都留在原节点
  guard.request(kpId, { then: (target) => target !== null && canvas.value?.focus(target) })
}

// L11：画布之外的可访问选择方式（键盘与自动化可用），选择同样经过「未保存修改」守卫
const pickerOptions = computed(() => nodePickerOptions(graph.value))
function onPick(event: Event): void {
  const value = (event.target as HTMLSelectElement).value
  guard.request(value === '' ? null : value)
}

// L11：新建知识点（ADR-035：必带来源，来源取自当前选中知识点）
const nodeEditApi = inject(NODE_EDIT_API_KEY, null) ?? createNodeEditApi(fallbackClient())
const detailApi = inject(KNOWLEDGE_DETAIL_API_KEY, null) ?? createKnowledgeDetailApi(fallbackClient())
const creator = useNodeCreator({
  api: nodeEditApi,
  detailApi,
  sourceKpId: selected,
  onCreated: async (kp) => {
    await teacher.refresh()
    guard.request(kp.id)
  },
})
function openCreator(): void {
  tab.value = 'create'
  void creator.open()
}
watch(selected, () => {
  if (tab.value === 'create' && creator.success.value === null) void creator.open()
})

/** 画布点击：关系页签下用于依次点选起点、终点；其余页签切换当前知识点 */
function onNodeClick(kpId: string): void {
  if (tab.value === 'relations') relations.pickNode(kpId)
  else guard.request(kpId)
}

// 页面级提示：删除成功、当前节点被刷新掉（面板随选中清空而回到空态，提示留在页面上）
const notice = ref<string | null>(null)
let justDeleted: string | null = null

function onDeleted(kpId: string): void {
  justDeleted = kpId
  notice.value = '知识点已删除，与它相连的关系已一并删除。'
  filters.select(null)
}

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
const { positions, error: layoutError } = useGraphLayout(() => layoutSource.value)
// 面板只在有限高度内滚动；宽度调整不会改变草稿或选择状态。
const workspace = ref<HTMLElement | null>(null)
const workspaceWidth = ref(0)
const preferredWidth = ref(360)
const minWidth = computed(() => Math.min(280, workspaceWidth.value * .4))
const maxWidth = computed(() => Math.max(minWidth.value, Math.min(640, workspaceWidth.value - 360)))
const panelWidth = computed(() => Math.min(maxWidth.value, Math.max(minWidth.value, preferredWidth.value)))
function setWidth(value: number): void {
  preferredWidth.value = Math.min(maxWidth.value, Math.max(minWidth.value, value))
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
      <p v-if="refreshing" data-test="tg-refreshing" role="status">正在刷新草稿图谱…</p>
      <p v-if="refreshError" data-test="tg-refresh-error" role="alert">
        {{ refreshError }}
        <button type="button" data-test="tg-refresh-retry" @click="teacher.refresh">重新刷新</button>
      </p>

      <div ref="workspace" class="teacher-graph__body" :class="{ 'is-resizing': resizing }" :style="{ '--teacher-panel-width': `${panelWidth}px` }">
        <aside class="teacher-graph__filters" aria-label="筛选">
          <GraphToolbar
            v-model="filters.state.value"
            v-model:layout="filters.layout.value"
            :chapters="chapterList"
            :summary="summary"
            :can-clear="!isDefault"
            :selected-hidden="selectedHidden"
            compact
            @clear="filters.clear"
            @locate="onLocate"
          >
            <template #actions>
              <button type="button" class="teacher-graph__create" data-test="tg-create-open" :aria-pressed="tab === 'create'" @click="openCreator">
                <AppIcon name="plus" /> 新建知识点
              </button>
            </template>
          </GraphToolbar>
          <p v-if="searchNotice" data-test="tg-search-notice" role="status">{{ searchNotice }}</p>
        </aside>

        <div class="teacher-graph__canvas" data-test="tg-graph">
          <p class="teacher-graph__hint">
            {{ tab === 'relations' ? '在图上依次点击起点和终点来新建关系。' : '点击知识点查看详情或编辑；画布支持缩放与拖拽。' }}
          </p>
          <label class="teacher-graph__picker">
            选择知识点
            <select data-test="tg-node-picker" :value="selected ?? ''" @change="onPick">
              <option value="">（未选择）</option>
              <option v-for="option in pickerOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </label>
          <p v-if="layoutError" role="status" class="ui-muted">章节布局暂不可用，已切换到基础布局。</p>
          <GraphCanvas ref="canvas" :graph="visible" :layout="filters.layout.value" :enhanced="!layoutError" :positions="positions" audience="teacher" label="课程知识图谱（草稿）" @node-click="onNodeClick" />
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
        <div class="teacher-graph__panel" id="teacher-knowledge-panel">
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
              @select-knowledge-point="guard.request"
              @close="guard.request(null)"
              @course-forbidden="leaveForbidden"
            />
            <p v-else data-test="tg-detail-empty" role="status">在图谱中点击一个知识点查看详情。</p>
          </template>

          <!-- 切到其他页签时保留编辑面板，未保存的修改不丢 -->
          <NodeEditor
            v-show="tab === 'edit'"
            ref="nodeEditor"
            :kp-id="selected"
            @deleted="onDeleted"
            @refresh-needed="teacher.refresh"
            @close="guard.request(null)"
            @course-forbidden="leaveForbidden"
          />

          <RelationEditor v-if="tab === 'relations'" :editor="relations" />
          <NodeCreator v-if="tab === 'create'" :creator="creator" :source-name="currentName" />
        </div>
      </div>
    </template>
  </PageSheet>
</template>
