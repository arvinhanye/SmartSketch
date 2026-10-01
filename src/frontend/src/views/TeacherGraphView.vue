<script setup lang="ts">
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, RouterLink, useRoute, useRouter } from 'vue-router'
import { HTTP_CLIENT_KEY } from '../api/client'
import { COURSES_API_KEY } from '../api/courses'
import { createDraftGraphApi, DRAFT_GRAPH_API_KEY } from '../api/graph'
import { createRelationsApi, RELATIONS_API_KEY } from '../api/relations'
import GraphCanvas from '../components/GraphCanvas.vue'
import GraphToolbar from '../components/GraphToolbar.vue'
import KnowledgeDetail from '../components/KnowledgeDetail.vue'
import NodeEditor from '../components/NodeEditor.vue'
import RelationEditor from '../components/RelationEditor.vue'
import { chapterOptions, useGraphFilters } from '../composables/useGraphFilters'
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
 * 教师图谱编辑页（H14，ADR-067）：草稿画布 + 右侧面板（H06 详情 / H07 节点编辑 / H08 关系编辑）。
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

type PanelTab = 'detail' | 'edit' | 'relations'
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
const empty = computed(() => status.value === 'ready' && graph.value !== null && graph.value.nodes.length === 0)
</script>

<template>
  <section
    class="page surface-card teacher-graph"
    data-test="teacher-graph-page"
    aria-labelledby="teacher-graph-title"
    :aria-busy="status === 'loading' ? 'true' : 'false'"
  >
    <header class="teacher-graph__header">
      <h2 id="teacher-graph-title">编辑课程知识图谱（草稿）</h2>
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

      <div class="teacher-graph__body">
        <aside class="teacher-graph__filters" aria-label="筛选">
          <GraphToolbar
            v-model="filters.state.value"
            v-model:layout="filters.layout.value"
            :chapters="chapterList"
            :summary="summary"
            :can-clear="!isDefault"
            :selected-hidden="selectedHidden"
            vertical
            @clear="filters.clear"
          />
        </aside>

        <div class="teacher-graph__canvas" data-test="tg-graph">
          <p class="teacher-graph__hint">
            {{ tab === 'relations' ? '在图上依次点击起点和终点来新建关系。' : '点击知识点查看详情或编辑；画布支持缩放与拖拽。' }}
          </p>
          <GraphCanvas :graph="visible" :layout="filters.layout.value" label="课程知识图谱（草稿）" @node-click="onNodeClick" />
        </div>

        <div class="teacher-graph__panel">
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
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.teacher-graph {
  display: grid;
  gap: 0.75rem;
}
.teacher-graph__header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.75rem;
}
.teacher-graph__header h2 {
  margin: 0;
}
.teacher-graph__badge {
  font-size: 0.75rem;
  border-radius: 4px;
  padding: 0.05rem 0.5rem;
  background: var(--color-warning-bg);
  color: var(--color-warning-text);
}
.teacher-graph__course {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.875rem;
  flex-basis: 100%;
}
.teacher-graph__back {
  margin: 0;
  font-size: 0.875rem;
}
/* 工作台三栏：筛选 | 画布 | 详情与编辑 */
.teacher-graph__body {
  display: grid;
  grid-template-columns: 13.5rem minmax(0, 1fr) minmax(280px, 22rem);
  gap: 0;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
  min-height: 560px;
}
.teacher-graph__filters {
  background: var(--color-surface-muted);
  border-right: 1px solid var(--color-border);
  padding: 0.85rem;
}
.teacher-graph__canvas {
  min-height: 560px;
  display: flex;
  flex-direction: column;
  background-color: var(--color-surface);
  background-image: radial-gradient(var(--color-border) 1px, transparent 1px);
  background-size: 18px 18px;
}
.teacher-graph__canvas > :last-child {
  flex: 1;
}
.teacher-graph__hint {
  color: var(--color-text-muted);
  font-size: 0.8rem;
  margin: 0;
  padding: 0.5rem 0.75rem 0;
}
.teacher-graph__panel {
  border-left: 1px solid var(--color-border);
  padding: 0.85rem;
  background: var(--color-surface);
  min-width: 0;
}
.teacher-graph__tabs {
  display: flex;
  gap: 0.25rem;
  margin-bottom: 0.75rem;
  border-bottom: 1px solid var(--color-border);
}
.teacher-graph__tabs button {
  background: none;
  color: var(--color-text-muted);
  border: none;
  border-bottom: 2px solid transparent;
  border-radius: 0;
  padding: 0.4rem 0.6rem;
  margin-bottom: -1px;
}
.teacher-graph__tabs button:hover:not(:disabled) {
  background: none;
  color: var(--color-text);
}
.teacher-graph__tabs button[aria-pressed='true'] {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
  font-weight: 600;
}
.teacher-graph__confirm {
  border: 1px solid var(--color-warning-border);
  background: var(--color-warning-bg);
  border-radius: var(--radius-sm);
  padding: 0.5rem 0.75rem;
  margin-bottom: 0.5rem;
}
.teacher-graph__confirm button + button {
  margin-left: 0.5rem;
}
@media (max-width: 1100px) {
  .teacher-graph__body {
    grid-template-columns: minmax(0, 1fr);
  }
  .teacher-graph__filters,
  .teacher-graph__panel {
    border: none;
  }
}
</style>
