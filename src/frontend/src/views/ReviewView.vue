<script setup lang="ts">
import PageSheet from '../components/PageSheet.vue'
import PageHeader from '../components/PageHeader.vue'
import AppIcon from '../components/AppIcon.vue'
import ToastNotice from '../components/ToastNotice.vue'
import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { HTTP_CLIENT_KEY } from '../api/client'
import { COURSES_API_KEY } from '../api/courses'
import { createDraftGraphApi, DRAFT_GRAPH_API_KEY } from '../api/graph'
import { createKnowledgeDetailApi, KNOWLEDGE_DETAIL_API_KEY } from '../api/knowledgeDetail'
import { createReviewApi, REVIEW_API_KEY, type Relation, type ReviewItemKind, type SuspectedDuplicate } from '../api/review'
import DuplicateCompare from '../components/review/DuplicateCompare.vue'
import VersionPanel from '../components/VersionPanel.vue'
import { useAutoDismiss } from '../composables/useAutoDismiss'
import { useSourceCounts, type SourceCount } from '../composables/useSourceCounts'
import {
  DUPLICATE_REASON_LABELS,
  duplicateKey,
  KIND_FIELD,
  KIND_LABELS,
  REVIEW_KINDS,
  useReview,
} from '../composables/useReview'
import { COURSE_ROUTE, homeRouteFor, NOTICE_COURSE_FORBIDDEN, REVIEW_ROUTE, ROOT_ROUTE, TEACHER_GRAPH_ROUTE } from '../router'
import { useSessionStore } from '../stores/session'

/**
 * 教师审核队列页（H09，ADR-070）：低置信度关系、疑似重复知识点、孤立知识点三栏，
 * 每条一键通过 / 拒绝，疑似重复可选主知识点后合并。状态与请求都在 `useReview`，本页只做展示与转发。
 */
const coursesApi = inject(COURSES_API_KEY, null)
if (coursesApi === null) throw new Error('ReviewView 需要注入 COURSES_API_KEY')
const client = inject(HTTP_CLIENT_KEY, null)
function fallbackClient() {
  if (client === null) throw new Error('ReviewView 需要注入各功能 API 或 HTTP_CLIENT_KEY')
  return client
}
const reviewApi = inject(REVIEW_API_KEY, null) ?? createReviewApi(fallbackClient())
const graphApi = inject(DRAFT_GRAPH_API_KEY, null) ?? (client === null ? undefined : createDraftGraphApi(client))
// 来源数量只是对比时的辅助信息：没有详情接口时卡片上说明读不到，不影响审核
const detailApi = inject(KNOWLEDGE_DETAIL_API_KEY, null) ?? (client === null ? null : createKnowledgeDetailApi(client))

const route = useRoute()
const router = useRouter()
const session = useSessionStore()

const courseId = computed(() => {
  const cid = route.params.cid
  return route.name === REVIEW_ROUTE && typeof cid === 'string' && cid !== '' ? cid : null
})

function leaveForbidden(): void {
  const role = session.role
  void router.replace(
    role === null ? { name: ROOT_ROUTE } : { name: homeRouteFor(role), query: { notice: NOTICE_COURSE_FORBIDDEN } },
  )
}

const review = useReview({ coursesApi, reviewApi, graphApi, courseId, onCourseForbidden: leaveForbidden })
const {
  status,
  error,
  retryable,
  courseName,
  items,
  totals,
  cursors,
  allEmpty,
  loadingMore,
  moreError,
  refreshing,
  refreshError,
  busyKey,
  itemError,
  notice,
  mergeDraft,
  draftGraph,
  draftState,
  nameOf,
} = review

// 成功/信息提示 4.5 秒后自动收起；错误提示留着，由用户关闭（快速连点时每条都会重新计时）。
useAutoDismiss(notice, review.dismissNotice, { ms: 4500, keep: (value) => value.tone === 'error' })

const EMPTY_TEXT: Record<ReviewItemKind, string> = {
  low_confidence_relation: '当前没有待审核的关系。',
  suspected_duplicate: '未发现需要合并的重复条目。',
  isolated_node: '没有待处理的孤立条目。',
}

const RELATION_TYPE_LABELS: Record<string, string> = {
  CONTAINS: '包含',
  PREREQUISITE: '前置',
  RELATED_TO: '相关',
  EXAMPLE_OF: '例题',
}

const hasGraphRoute = computed(() => router.hasRoute(TEACHER_GRAPH_ROUTE))
const busy = computed(() => busyKey.value !== null)

function count(kind: ReviewItemKind): number {
  return totals.value[KIND_FIELD[kind]]
}
function loadedCount(kind: ReviewItemKind): number {
  return items.value[KIND_FIELD[kind]].length
}
function hasMore(kind: ReviewItemKind): boolean {
  return cursors.value[KIND_FIELD[kind]] !== null
}

function relationLabel(relation: Relation): string {
  return RELATION_TYPE_LABELS[relation.type] ?? relation.type
}
function evidence(relation: Relation): string {
  const refs = relation.source_refs ?? []
  if (refs.length === 0) return '无原文证据'
  const first = refs[0] as { page?: number; section_path?: string }
  const where = first.page !== undefined ? `第 ${first.page} 页` : (first.section_path ?? '')
  return refs.length > 1 ? `${where} 等 ${refs.length} 处` : where
}
function percent(value: number): string {
  return `${Math.round(value * 100)}%`
}
function isMerging(pair: SuspectedDuplicate): boolean {
  return mergeDraft.value?.key === duplicateKey(pair)
}

// ---------------------------------------------------------------- 疑似重复：对比、连续处理与键盘（UX-REVIEW-DEDUP-01）
/** 相似度缺失或不是数字时不显示（候选怎样产生由后端决定，页面不假设一定有分数） */
function duplicateMeta(pair: SuspectedDuplicate): string {
  const parts: string[] = []
  if (typeof pair.similarity === 'number' && Number.isFinite(pair.similarity)) parts.push(`相似度 ${percent(pair.similarity)}`)
  const reason = DUPLICATE_REASON_LABELS[pair.reason] ?? pair.reason
  if (typeof reason === 'string' && reason !== '') parts.push(reason)
  return parts.join(' · ')
}
function graphLinkFor(pair: SuspectedDuplicate) {
  if (courseId.value === null || !hasGraphRoute.value) return null
  return { name: TEACHER_GRAPH_ROUTE, params: { cid: courseId.value }, query: { pair: pair.candidates.map((c) => c.id).join(',') } }
}

/** 本次进入页面后**确认生效**的处理：留一行记录，让教师看得到进度；只是页面内存里的反馈，不是审计日志 */
const handled = ref<Array<{ key: string; text: string }>>([])
// 换课程：上一门课的记录不带过来
watch(courseId, () => {
  handled.value = []
})

// ---- 来源数量（DEDUP-FIX F2）：草稿图的节点不带来源，展开时按需向详情接口读这两个知识点的
const sourceCounts = useSourceCounts({ api: detailApi, courseId })
function sourceTargets(pair: SuspectedDuplicate) {
  return pair.candidates.map((c) => ({ id: c.id, revision: draftGraph.value?.nodes.find((n) => n.id === c.id)?.revision ?? 0 }))
}
function sourcesFor(pair: SuspectedDuplicate): Record<string, SourceCount | undefined> {
  return Object.fromEntries(sourceTargets(pair).map((target) => [target.id, sourceCounts.of(target)]))
}
const expandedPair = computed(() => items.value.suspected_duplicates.find(isMerging) ?? null)
watch([expandedPair, draftGraph], () => {
  if (expandedPair.value !== null) sourceCounts.ensure(sourceTargets(expandedPair.value))
})

const expandedIndex = computed(() => items.value.suspected_duplicates.findIndex(isMerging))
function expandAt(index: number): void {
  const list = items.value.suspected_duplicates
  const pair = list[Math.min(Math.max(index, 0), list.length - 1)]
  if (pair !== undefined) review.startMerge(pair)
}
/**
 * 处理一条。只有服务端确认本次写入生效（`applied`）才记进“本次已处理”（DEDUP-FIX F3）：
 * 别人已处理（404）、幂等重放、被拒绝、结果不确定都不记成功，它们各有自己的提示。
 * 条目离开了队列且处理的是展开着的那条时，自动展开原位置上的下一条。
 */
async function settle(pair: SuspectedDuplicate, verb: 'merge' | 'reject'): Promise<void> {
  const key = duplicateKey(pair)
  const cid = courseId.value
  const index = items.value.suspected_duplicates.findIndex((p) => duplicateKey(p) === key)
  const wasExpanded = mergeDraft.value?.key === key
  const primaryId = wasExpanded ? mergeDraft.value!.primaryId : null
  const [first, second] = pair.candidates
  const outcome = verb === 'merge' ? await review.confirmMerge(pair) : await review.resolve({ kind: 'suspected_duplicate', pair }, 'reject')
  // 作废的结果（换了课程、页面已卸载、无权限）不动当前页面
  if (outcome === 'aborted' || courseId.value !== cid) return
  if (outcome === 'applied') {
    const kept = pair.candidates.find((c) => c.id === primaryId)?.name ?? first?.name ?? ''
    const gone = pair.candidates.find((c) => c.id !== primaryId)?.name ?? second?.name ?? ''
    handled.value = [...handled.value, { key, text: verb === 'merge' ? `已合并：「${gone}」并入「${kept}」` : `不是重复：「${first?.name ?? ''}」与「${second?.name ?? ''}」` }]
    if (verb === 'merge') sourceCounts.invalidate(pair.candidates.map((c) => c.id))
  }
  if (items.value.suspected_duplicates.some((p) => duplicateKey(p) === key)) return
  // 只有处理的是展开着的那条才前进；在收起的一行上直接标记不打开别的条目
  if (wasExpanded && index >= 0 && mergeDraft.value === null) expandAt(index)
}

/** 文本输入类控件：M / N 不触发（单选、复选、按钮上仍可用） */
function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target instanceof HTMLInputElement) return !['radio', 'checkbox', 'button'].includes(target.type)
  return target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable
}
/** 自己会用方向键的控件（DEDUP-FIX F5）：单选组用方向键换选项，输入框移动光标，下拉框换选项；条目导航不抢 */
function usesArrows(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return target instanceof HTMLInputElement || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable
}
function onKeydown(event: KeyboardEvent): void {
  if (event.defaultPrevented || event.isComposing || event.ctrlKey || event.metaKey || event.altKey) return
  if (status.value !== 'ready' || busy.value) return
  const index = expandedIndex.value
  const pair = items.value.suspected_duplicates[index]
  if (pair === undefined) return
  const key = event.key.toLowerCase()
  if (key === 'm' || key === 'n') {
    // 写入必须来自一次独立的按下（DEDUP-FIX F1）：按住不放产生的重复事件不算，
    // 否则第一笔完成、页面前进后，同一次按键会把下一条也处理掉
    if (event.repeat || isTyping(event.target)) return
    void settle(pair, key === 'm' ? 'merge' : 'reject')
  } else if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
    if (usesArrows(event.target)) return
    const next = event.key === 'ArrowRight' ? index + 1 : index - 1
    if (next < 0 || next >= items.value.suspected_duplicates.length) return
    expandAt(next)
  } else return
  event.preventDefault()
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <PageSheet class="review ui-management" data-test="review-page" labelledby="review-title" :aria-busy="status === 'loading'">
    <PageHeader id="review-title" title="审核与发布" :description="courseName ? `${courseName} · 检查草稿后发布给学生。` : '检查待处理条目，整理草稿，再发布给学生。'">
      <template #actions>
        <RouterLink v-if="courseId" class="ui-btn" :to="{ name: COURSE_ROUTE, params: { cid: courseId } }"><AppIcon name="back" :size="16" />返回课程</RouterLink>
        <RouterLink v-if="courseId && hasGraphRoute" class="ui-btn" data-test="rv-graph-link" :to="{ name: TEACHER_GRAPH_ROUTE, params: { cid: courseId } }"><AppIcon name="graph" :size="16" />编辑图谱</RouterLink>
      </template>
    </PageHeader>

    <p v-if="status === 'loading'" data-test="rv-loading" role="status">正在加载审核队列…</p>

    <p v-else-if="status === 'not_teacher'" data-test="rv-not-teacher" role="status">只有本课程的教师可以审核图谱。</p>

    <div v-else-if="status === 'error'" data-test="rv-error" role="alert">
      <p>{{ error }}</p>
      <button v-if="retryable" type="button" data-test="rv-retry" @click="review.reload">重试</button>
    </div>

    <template v-else-if="status === 'ready'">
      <ToastNotice v-if="notice" data-test="rv-notice" :tone="notice.tone" :text="notice.text" @dismiss="review.dismissNotice" />
      <p v-if="refreshing" data-test="rv-refreshing" role="status">正在刷新审核队列…</p>
      <p v-if="refreshError" data-test="rv-refresh-error" role="alert">
        {{ refreshError }}
        <button type="button" data-test="rv-refresh-retry" @click="review.refresh">重新加载</button>
      </p>
      <p v-if="allEmpty" class="review__ready" data-test="rv-all-empty" role="status"><AppIcon name="check" :size="18" />审核队列已清空，可以直接发布。</p>
      <p v-else class="review__hint">队列不阻塞发布：发布时只排除低置信度关系，疑似重复与孤立知识点仅作提示。</p>


      <div class="ui-review-inbox">
      <section
        v-for="kind in REVIEW_KINDS"
        :id="`rv-${kind}`"
        :key="kind"
        class="review__column"
        :data-test="`rv-column-${kind}`"
        :aria-labelledby="`rv-heading-${kind}`"
      >
        <h3 :id="`rv-heading-${kind}`" :data-test="`rv-total-${kind}`"><span>{{ KIND_LABELS[kind] }}</span><span class="review__count">（{{ count(kind) }}）</span></h3>

        <p v-if="count(kind) === 0 && loadedCount(kind) === 0" :data-test="`rv-empty-${kind}`" role="status">
          {{ EMPTY_TEXT[kind] }}
        </p>

        <!-- 低置信度关系 -->
        <ul v-if="kind === 'low_confidence_relation'" class="review__list">
          <li
            v-for="relation in items.low_confidence_relations"
            :key="relation.id"
            data-test="rv-relation"
            :data-id="relation.id"
            :aria-busy="busyKey === `rel:${relation.id}` ? 'true' : 'false'"
          >
            <p>
              <strong>{{ nameOf(relation.from_id) }}</strong>
              —{{ relationLabel(relation) }}{{ relation.type === 'RELATED_TO' ? '—' : '→' }}
              <strong>{{ nameOf(relation.to_id) }}</strong>
            </p>
            <p class="review__meta">置信度 {{ percent(relation.confidence) }} · 证据：{{ evidence(relation) }}</p>
            <div class="review__actions">
              <button
                type="button"
                data-test="rv-approve"
                :disabled="busy"
                @click="review.resolve({ kind, relation }, 'approve')"
              >
                通过
              </button>
              <button type="button" data-test="rv-reject" :disabled="busy" @click="review.resolve({ kind, relation }, 'reject')">
                拒绝
              </button>
            </div>
            <p v-if="itemError?.key === `rel:${relation.id}`" data-test="rv-item-error" role="alert">{{ itemError.message }}</p>
          </li>
        </ul>

        <!-- 疑似重复：每条收成一行，展开一条看对比与合并预览（UX-REVIEW-DEDUP-01） -->
        <template v-else-if="kind === 'suspected_duplicate'">
        <ul v-if="handled.length > 0" class="review__handled" data-test="rv-handled" aria-label="本次已处理">
          <li v-for="entry in handled" :key="entry.key"><AppIcon name="check" :size="14" />{{ entry.text }}</li>
        </ul>
        <ul class="review__list">
          <li
            v-for="(pair, index) in items.suspected_duplicates"
            :key="duplicateKey(pair)"
            data-test="rv-duplicate"
            :data-id="duplicateKey(pair)"
            :class="{ 'is-expanded': isMerging(pair) }"
            :aria-busy="busyKey === duplicateKey(pair) ? 'true' : 'false'"
          >
            <div class="review__dup-row">
              <p>
                <strong>{{ pair.candidates[0]?.name }}</strong> 与 <strong>{{ pair.candidates[1]?.name }}</strong>
              </p>
              <p class="review__meta">
                {{ duplicateMeta(pair) }}<template v-if="isMerging(pair)"> · 第 {{ index + 1 }} / {{ items.suspected_duplicates.length }} 条</template>
              </p>
            </div>

            <DuplicateCompare
              v-if="isMerging(pair)"
              :pair="pair"
              :graph="draftGraph"
              :graph-state="draftState"
              :sources="sourcesFor(pair)"
              :reloading="refreshing"
              @reload-graph="review.refresh"
              :primary-id="mergeDraft?.primaryId ?? ''"
              :busy="busy"
              :error="itemError?.key === duplicateKey(pair) ? itemError : null"
              :radio-name="`primary-${duplicateKey(pair)}`"
              :graph-link="graphLinkFor(pair)"
              @choose="review.choosePrimary"
              @merge="settle(pair, 'merge')"
              @reject="settle(pair, 'reject')"
              @collapse="review.cancelMerge"
            />
            <template v-else>
              <div class="review__actions">
                <button type="button" data-test="rv-merge" :disabled="busy" @click="review.startMerge(pair)">合并…</button>
                <button type="button" data-test="rv-not-duplicate" :disabled="busy" @click="settle(pair, 'reject')">
                  不是重复
                </button>
              </div>
              <div v-if="itemError?.key === duplicateKey(pair)" data-test="rv-item-error" role="alert">
                <p>{{ itemError.message }}</p>
                <p v-if="itemError.cycle" data-test="rv-cycle">
                  环路：<template v-for="(step, stepIndex) in itemError.cycle" :key="`${step.kpId}-${stepIndex}`">
                    <span v-if="stepIndex > 0"> → </span>{{ step.name }}
                  </template>
                </p>
              </div>
            </template>
          </li>
        </ul>
        </template>

        <!-- 孤立知识点 -->
        <ul v-else class="review__list">
          <li
            v-for="node in items.isolated_nodes"
            :key="node.id"
            data-test="rv-isolated"
            :data-id="node.id"
            :aria-busy="busyKey === `iso:${node.id}` ? 'true' : 'false'"
          >
            <p><strong>{{ node.name }}</strong></p>
            <div class="review__actions">
              <button type="button" data-test="rv-keep" :disabled="busy" @click="review.resolve({ kind, node }, 'approve')">
                确认保留
              </button>
              <button type="button" data-test="rv-reject-node" :disabled="busy" @click="review.resolve({ kind, node }, 'reject')">
                拒绝
              </button>
            </div>
            <p v-if="itemError?.key === `iso:${node.id}`" data-test="rv-item-error" role="alert">{{ itemError.message }}</p>
          </li>
        </ul>

        <p v-if="count(kind) > 0 && loadedCount(kind) === 0 && !hasMore(kind)" :data-test="`rv-drained-${kind}`" role="status">
          本栏已加载的条目都已处理。
          <button type="button" data-test="rv-drained-refresh" :disabled="refreshing" @click="review.refresh">刷新队列</button>
        </p>
        <div v-if="hasMore(kind)" class="review__more">
          <span>已显示 {{ loadedCount(kind) }} / {{ count(kind) }}</span>
          <button
            type="button"
            :data-test="`rv-more-${kind}`"
            :disabled="loadingMore !== null || refreshing"
            @click="review.loadMore(kind)"
          >
            {{ loadingMore === kind ? '正在加载…' : '加载更多' }}
          </button>
        </div>
        <p v-if="moreError?.kind === kind" :data-test="`rv-more-error-${kind}`" role="alert">{{ moreError.message }}</p>
      </section>
      </div>
      <VersionPanel v-if="courseId" :course-id="courseId" @forbidden="leaveForbidden" />
    </template>
  </PageSheet>
</template>
