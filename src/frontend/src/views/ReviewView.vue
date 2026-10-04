<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { HTTP_CLIENT_KEY } from '../api/client'
import { COURSES_API_KEY } from '../api/courses'
import { createDraftGraphApi, DRAFT_GRAPH_API_KEY } from '../api/graph'
import { createReviewApi, REVIEW_API_KEY, type Relation, type ReviewItemKind, type SuspectedDuplicate } from '../api/review'
import VersionPanel from '../components/VersionPanel.vue'
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
 * 教师审核队列页（H09，ADR-070）：低置信度关系、疑似重复知识点、孤立知识点三类。
 *
 * 展示结构（2026-10 改版）：返回课程 / 编辑图谱导航 + 审核队列标题与课程说明 + 紧凑发布状态栏
 * + 分类切换与宽松单列审核列表 + 默认折叠的版本历史。
 * 标题必须排在发布栏之前，因此导航与标题放在 `VersionPanel` 的 `review-header` 插槽，
 * 待处理事项、分类标签、当前分类内容与版本历史留在 `review-content` 插槽之后。
 * 同一时刻只渲染当前分类的条目，分类数量与「共 N 项」都取服务端 `totals`，不用已加载数组长度代替。
 * 空状态互斥：三类都为空只显示一条总提示，只有当前分类为空才显示该分类的空提示。
 * 业务状态与请求全部在 `useReview` / `useVersions`，本页只做展示与转发，并保留三个**局部** UI 状态：
 * 当前分类、每条关系的证据展开集合、课程切换时的展示状态重置。版本状态只有一份：
 * 页面把导航标题与审核区作为插槽交给 `VersionPanel`，发布栏与版本历史复用同一个 `useVersions` 实例。
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
  nameOf,
} = review

/** 三栏名称与数量的统一格式：既用于 tab 的 aria-label，也用于（旧布局留下的）数量定位标记 */
const COUNT_UNIT = '项'

const RELATION_TYPE_LABELS: Readonly<Record<string, string>> = {
  CONTAINS: '包含',
  PREREQUISITE: '前置',
  RELATED_TO: '相关',
  EXAMPLE_OF: '例题',
}

/** 只表达真实方向：RELATED_TO 是无方向连接，不能画成有向前置关系 */
const UNDIRECTED_TYPES = new Set(['RELATED_TO'])

const EMPTY_TEXT: Readonly<Record<ReviewItemKind, string>> = {
  low_confidence_relation: '当前没有待处理的低置信度关系。',
  suspected_duplicate: '当前没有待处理的疑似重复知识点。',
  isolated_node: '当前没有待处理的孤立知识点。',
}

const hasGraphRoute = computed(() => router.hasRoute(TEACHER_GRAPH_ROUTE))
const busy = computed(() => busyKey.value !== null)

const totalCount = computed(() => REVIEW_KINDS.reduce((sum, kind) => sum + totals.value[KIND_FIELD[kind]], 0))
const kindTabs = computed(() =>
  REVIEW_KINDS.map((kind) => ({
    kind,
    label: KIND_LABELS[kind],
    count: totals.value[KIND_FIELD[kind]],
    /** 无障碍名称与可见文本都带数量；可见数量单独放在 aria-hidden 的徽标里，避免重复朗读 */
    ariaLabel: `${KIND_LABELS[kind]}，共 ${totals.value[KIND_FIELD[kind]]} ${COUNT_UNIT}`,
    /** 「名称（数量）」形式，供既有的数量断言与无障碍标签复用 */
    heading: `${KIND_LABELS[kind]}（${totals.value[KIND_FIELD[kind]]}）`,
  })),
)

/** 当前分类：首次加载成功后落在第一个有待处理项的分类，之后只跟随用户选择 */
const selectedKind = ref<ReviewItemKind>(REVIEW_KINDS[0]!)
const selected = computed(() => kindTabs.value.find((tab) => tab.kind === selectedKind.value) ?? kindTabs.value[0]!)
let autoSelected = false

watch(
  () => [status.value, selectedKind.value, totals.value] as const,
  () => {
    if (status.value !== 'ready' || autoSelected) return
    selectedKind.value = REVIEW_KINDS.find((kind) => totals.value[KIND_FIELD[kind]] > 0) ?? REVIEW_KINDS[0]!
    autoSelected = true
  },
)

/** 每条关系独立展开证据，键用稳定的关系 ID；换课后清空，避免旧课程展示状态残留 */
const openEvidence = ref<ReadonlySet<string>>(new Set())
function isOpen(key: string): boolean {
  return openEvidence.value.has(key)
}
function toggleEvidence(key: string): void {
  const next = new Set(openEvidence.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  openEvidence.value = next
}

watch(courseId, () => {
  autoSelected = false
  selectedKind.value = REVIEW_KINDS[0]!
  openEvidence.value = new Set()
})

function selectTab(kind: ReviewItemKind): void {
  selectedKind.value = kind
}
/**
 * 完整实现 tab 键盘行为：左右 / 上下在分类间移动并即时切换，Home / End 跳到首尾。
 * 焦点通过 tablist 内的按钮顺序定位，不额外维护 ref 数组。
 */
function onTabKeydown(event: KeyboardEvent): void {
  const last = REVIEW_KINDS.length - 1
  let next: number
  if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = selectedTabIndex() === last ? 0 : selectedTabIndex() + 1
  else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = selectedTabIndex() === 0 ? last : selectedTabIndex() - 1
  else if (event.key === 'Home') next = 0
  else if (event.key === 'End') next = last
  else return
  event.preventDefault()
  const tablist = event.currentTarget instanceof HTMLElement ? event.currentTarget.parentElement : null
  const buttons = tablist === null ? [] : Array.from(tablist.querySelectorAll<HTMLElement>('[role="tab"]'))
  selectTab(REVIEW_KINDS[next]!)
  const target = buttons[next]
  if (target !== undefined) target.focus()
}
function selectedTabIndex(): number {
  return Math.max(0, REVIEW_KINDS.indexOf(selectedKind.value))
}

function relationLabel(relation: Relation): string {
  return RELATION_TYPE_LABELS[relation.type] ?? relation.type
}
function relationDirected(relation: Relation): boolean {
  return !UNDIRECTED_TYPES.has(relation.type)
}
function percent(value: number): string {
  return `${Math.round(value * 100)}%`
}

/** 来源摘要：只用接口真给的页码 / 章节路径，找不到时给中性文案，不虚构文件名 */
function sourceLocation(ref_: unknown): string | null {
  if (typeof ref_ !== 'object' || ref_ === null) return null
  const row = ref_ as { page?: unknown; section_path?: unknown }
  const parts: string[] = []
  if (typeof row.page === 'number' && Number.isFinite(row.page)) parts.push(`第 ${row.page} 页`)
  if (typeof row.section_path === 'string' && row.section_path.trim() !== '') parts.push(row.section_path)
  return parts.length === 0 ? null : parts.join(' · ')
}
function sourceText(ref_: unknown): string | null {
  if (typeof ref_ !== 'object' || ref_ === null) return null
  const text = (ref_ as { text?: unknown }).text
  return typeof text === 'string' && text.trim() !== '' ? text : null
}
function evidenceList(relation: Relation): Array<{ index: number; location: string | null; text: string | null }> {
  const refs = Array.isArray(relation.source_refs) ? relation.source_refs : []
  return refs.map((ref_, index) => ({ index, location: sourceLocation(ref_), text: sourceText(ref_) }))
}
/** 只有确实含有页码或章节的引用才值得展开；无来源时不提供无效的展开入口 */
function canExpand(relation: Relation): boolean {
  return evidenceList(relation).some((row) => row.location !== null)
}
/** 展开入口旁的来源摘要：用第一条可定位来源，多处以「等 N 处」收尾 */
function evidenceSummary(relation: Relation): string {
  const located = evidenceList(relation).filter((row) => row.location !== null)
  const first = located[0]
  if (first === undefined) return ''
  return located.length > 1 ? `${first.location} 等 ${located.length} 处` : first.location!
}

function isMerging(pair: SuspectedDuplicate): boolean {
  return mergeDraft.value?.key === duplicateKey(pair)
}
function primaryName(pair: SuspectedDuplicate): string {
  return pair.candidates.find((c) => c.id === mergeDraft.value?.primaryId)?.name ?? ''
}
function otherName(pair: SuspectedDuplicate): string {
  return pair.candidates.find((c) => c.id !== mergeDraft.value?.primaryId)?.name ?? ''
}
</script>

<template>
  <VersionPanel v-if="courseId" :course-id="courseId" @forbidden="leaveForbidden">
    <template #review-header>
      <div class="review__top">
        <p class="review__back">
          <RouterLink :to="{ name: COURSE_ROUTE, params: { cid: courseId } }" data-test="rv-back">
            <span aria-hidden="true">←</span>
            返回课程
          </RouterLink>
          <template v-if="hasGraphRoute">
            <span class="review__back-sep" aria-hidden="true">|</span>
            <RouterLink data-test="rv-graph-link" :to="{ name: TEACHER_GRAPH_ROUTE, params: { cid: courseId } }">编辑图谱</RouterLink>
          </template>
        </p>

        <header class="review__head">
          <h2 id="review-title">审核队列</h2>
          <p v-if="courseName" class="review__lede" data-test="rv-course">
            {{ courseName }}<span v-if="status === 'ready'"> · 当前处理的是草稿</span>
          </p>
        </header>
      </div>
    </template>

    <template #review-content>
      <div class="page review" data-test="review-page" aria-labelledby="review-title" :aria-busy="status === 'loading' ? 'true' : 'false'">
        <p v-if="status === 'loading'" data-test="rv-loading" role="status">正在加载审核队列…</p>

        <p v-else-if="status === 'not_teacher'" data-test="rv-not-teacher" role="status">只有本课程的教师可以审核图谱。</p>

        <div v-else-if="status === 'error'" class="review__error" data-test="rv-error" role="alert">
          <p>{{ error }}</p>
          <button v-if="retryable" type="button" data-variant="secondary" data-test="rv-retry" @click="review.reload">重试</button>
        </div>

        <template v-else-if="status === 'ready'">
          <div class="review__feedback">
            <p
              v-if="notice"
              data-test="rv-notice"
              :data-tone="notice.tone"
              :role="notice.tone === 'error' ? 'alert' : 'status'"
            >
              {{ notice.text }}
            </p>
            <p v-if="refreshing" data-test="rv-refreshing" role="status">正在刷新审核队列…</p>
            <p v-if="refreshError" data-test="rv-refresh-error" role="alert">
              {{ refreshError }}
              <button type="button" data-variant="secondary" data-test="rv-refresh-retry" @click="review.refresh">重新加载</button>
            </p>
          </div>

          <section class="review-card" aria-labelledby="review-pending-title">
            <header class="review-card__head">
              <h3 id="review-pending-title" class="review-card__title">
                待处理事项
                <span class="review-card__total">共 {{ totalCount }} 项</span>
              </h3>
            </header>

            <div class="tabs" role="tablist" aria-label="审核分类">
              <button
                v-for="tab in kindTabs"
                :key="tab.kind"
                type="button"
                role="tab"
                class="tabs__tab"
                :class="{ 'is-active': tab.kind === selectedKind }"
                :id="`rv-tab-${tab.kind}`"
                :data-test="`rv-total-${tab.kind}`"
                :data-count="tab.count"
                :data-heading="tab.heading"
                :aria-label="tab.ariaLabel"
                :aria-selected="tab.kind === selectedKind ? 'true' : 'false'"
                :aria-controls="`rv-panel-${tab.kind}`"
                :tabindex="tab.kind === selectedKind ? 0 : -1"
                @click="selectTab(tab.kind)"
                @keydown="onTabKeydown($event)"
              >
                {{ tab.label }}<span class="tabs__count" :data-test="`rv-count-${tab.kind}`" aria-hidden="true">{{ tab.count }}</span>
              </button>
            </div>

            <p class="review-card__rule">
              队列不阻塞发布，低置信度关系将从发布内容中排除。疑似重复与孤立知识点仅作提示。
            </p>

            <p v-if="allEmpty" class="review__done" data-test="rv-all-empty" role="status">当前没有待处理的审核项，可以直接发布。</p>

            <div
              class="tabpanel"
              role="tabpanel"
              :id="`rv-panel-${selected.kind}`"
              :aria-labelledby="`rv-tab-${selected.kind}`"
              tabindex="0"
            >
              <!-- 空状态互斥：三类都为空时只留总提示，避免总提示与分类空提示同时出现；
                   分类是否为空看服务端 totals（selected.count），不用已加载数组长度代替 -->
              <p
                v-if="!allEmpty && selected.count === 0"
                class="review__empty"
                :data-test="`rv-empty-${selected.kind}`"
                role="status"
              >
                {{ EMPTY_TEXT[selected.kind] }}
              </p>

              <!-- 低置信度关系：单列卡片，证据默认收起 -->
              <ul v-if="selected.kind === 'low_confidence_relation'" class="review__list">
                <li
                  v-for="relation in items.low_confidence_relations"
                  :key="relation.id"
                  class="item"
                  data-test="rv-relation"
                  :data-id="relation.id"
                  :aria-busy="busyKey === `rel:${relation.id}` ? 'true' : 'false'"
                >
                  <div class="item__body">
                    <p class="item__names">
                      <strong class="item__name">{{ nameOf(relation.from_id) }}</strong>
                      <span class="item__link" :class="{ 'is-undirected': !relationDirected(relation) }" aria-hidden="true">
                        {{ relationDirected(relation) ? '→' : '—' }}
                      </span>
                      <strong class="item__name">{{ nameOf(relation.to_id) }}</strong>
                      <span class="item__kind">{{ relationLabel(relation) }}</span>
                    </p>
                    <p class="item__meta">
                      置信度 {{ percent(relation.confidence) }}
                      <!-- 「前置 → 后继」只对 PREREQUISITE 成立：CONTAINS / EXAMPLE_OF 同样有方向，但不是前置关系 -->
                      <span v-if="relation.type === 'PREREQUISITE'"> · 前置 → 后继</span>
                    </p>
                    <p v-if="canExpand(relation)" class="item__link-row">
                      <button
                        type="button"
                        class="item__evidence-toggle"
                        :data-test="`rv-evidence-toggle-${relation.id}`"
                        :aria-expanded="isOpen(relation.id) ? 'true' : 'false'"
                        :aria-controls="`rv-evidence-${relation.id}`"
                        @click="toggleEvidence(relation.id)"
                      >
                        查看证据
                        <span class="item__caret" aria-hidden="true">{{ isOpen(relation.id) ? '⌃' : '⌄' }}</span>
                      </button>
                      <span class="item__source">{{ evidenceSummary(relation) }}</span>
                    </p>
                    <p v-else class="item__source item__source--plain">无原文证据</p>
                  </div>
                  <div class="item__actions">
                    <button
                      type="button"
                      class="item__action"
                      data-variant="secondary"
                      data-test="rv-approve"
                      :disabled="busy"
                      @click="review.resolve({ kind: selected.kind, relation }, 'approve')"
                    >
                      通过
                    </button>
                    <button
                      type="button"
                      class="item__action"
                      data-variant="secondary"
                      data-test="rv-reject"
                      :disabled="busy"
                      @click="review.resolve({ kind: selected.kind, relation }, 'reject')"
                    >
                      拒绝
                    </button>
                  </div>
                  <div
                    v-if="isOpen(relation.id)"
                    class="item__evidence"
                    :id="`rv-evidence-${relation.id}`"
                    :data-test="`rv-evidence-${relation.id}`"
                  >
                    <ul class="evidence">
                      <li v-for="row in evidenceList(relation)" :key="row.index" class="evidence__row">
                        <p class="evidence__where">{{ row.location ?? '来源位置未知' }}</p>
                        <p v-if="row.text" class="evidence__text">{{ row.text }}</p>
                      </li>
                    </ul>
                  </div>
                  <p v-if="itemError?.key === `rel:${relation.id}`" class="item__error" data-test="rv-item-error" role="alert">
                    {{ itemError.message }}
                  </p>
                </li>
              </ul>

              <!-- 疑似重复：默认只给两个候选与操作，点「合并…」才在当前卡片内展开原有合并面板 -->
              <ul v-else-if="selected.kind === 'suspected_duplicate'" class="review__list">
                <li
                  v-for="pair in items.suspected_duplicates"
                  :key="duplicateKey(pair)"
                  class="item"
                  data-test="rv-duplicate"
                  :data-id="duplicateKey(pair)"
                  :aria-busy="busyKey === duplicateKey(pair) ? 'true' : 'false'"
                >
                  <div class="item__body">
                    <p class="item__names">
                      <strong class="item__name">{{ pair.candidates[0]?.name }}</strong>
                      <span class="item__link item__link--undirected" aria-hidden="true">—</span>
                      <strong class="item__name">{{ pair.candidates[1]?.name }}</strong>
                    </p>
                    <p class="item__meta">
                      相似度 {{ percent(pair.similarity) }} · {{ DUPLICATE_REASON_LABELS[pair.reason] ?? pair.reason }}
                    </p>
                  </div>

                  <fieldset v-if="isMerging(pair)" class="merge" data-test="rv-merge-panel">
                    <legend class="merge__legend">选择保留的主知识点</legend>
                    <label v-for="candidate in pair.candidates" :key="candidate.id" class="merge__option">
                      <input
                        type="radio"
                        :name="`primary-${duplicateKey(pair)}`"
                        :value="candidate.id"
                        :checked="mergeDraft?.primaryId === candidate.id"
                        :disabled="busy"
                        data-test="rv-primary"
                        @change="review.choosePrimary(candidate.id)"
                      />
                      {{ candidate.name }}
                    </label>
                    <p class="merge__summary" data-test="rv-merge-summary">
                      「{{ otherName(pair) }}」将并入「{{ primaryName(pair) }}」：名称并入别名，关系与来源迁到主知识点，主知识点被锁定。合并后不能自动拆回。
                    </p>
                    <div class="merge__actions">
                      <button type="button" data-test="rv-merge-confirm" :disabled="busy" @click="review.confirmMerge(pair)">确认合并</button>
                      <button
                        type="button"
                        data-variant="secondary"
                        data-test="rv-merge-cancel"
                        :disabled="busy"
                        @click="review.cancelMerge"
                      >
                        取消
                      </button>
                    </div>
                  </fieldset>
                  <div v-else class="item__actions">
                    <button
                      type="button"
                      class="item__action"
                      data-variant="secondary"
                      data-test="rv-merge"
                      :disabled="busy"
                      @click="review.startMerge(pair)"
                    >
                      合并…
                    </button>
                    <button
                      type="button"
                      class="item__action"
                      data-variant="secondary"
                      data-test="rv-not-duplicate"
                      :disabled="busy"
                      @click="review.resolve({ kind: selected.kind, pair }, 'reject')"
                    >
                      不是重复
                    </button>
                  </div>

                  <div v-if="itemError?.key === duplicateKey(pair)" class="item__error" data-test="rv-item-error" role="alert">
                    <p>{{ itemError.message }}</p>
                    <p v-if="itemError.cycle" data-test="rv-cycle">
                      环路：<template v-for="(step, index) in itemError.cycle" :key="`${step.kpId}-${index}`">
                        <span v-if="index > 0"> → </span>{{ step.name }}
                      </template>
                    </p>
                  </div>
                </li>
              </ul>

              <!-- 孤立知识点 -->
              <ul v-else class="review__list">
                <li
                  v-for="node in items.isolated_nodes"
                  :key="node.id"
                  class="item"
                  data-test="rv-isolated"
                  :data-id="node.id"
                  :aria-busy="busyKey === `iso:${node.id}` ? 'true' : 'false'"
                >
                  <div class="item__body">
                    <p class="item__names"><strong class="item__name">{{ node.name }}</strong></p>
                    <p class="item__meta">暂无与之相连的关系，等待确认保留或拒绝。</p>
                  </div>
                  <div class="item__actions">
                    <button
                      type="button"
                      class="item__action"
                      data-variant="secondary"
                      data-test="rv-keep"
                      :disabled="busy"
                      @click="review.resolve({ kind: selected.kind, node }, 'approve')"
                    >
                      确认保留
                    </button>
                    <button
                      type="button"
                      class="item__action"
                      data-variant="secondary"
                      data-test="rv-reject-node"
                      :disabled="busy"
                      @click="review.resolve({ kind: selected.kind, node }, 'reject')"
                    >
                      拒绝
                    </button>
                  </div>
                  <p v-if="itemError?.key === `iso:${node.id}`" class="item__error" data-test="rv-item-error" role="alert">
                    {{ itemError.message }}
                  </p>
                </li>
              </ul>

              <p
                v-if="selected.count > 0 && items[KIND_FIELD[selected.kind]].length === 0 && cursors[KIND_FIELD[selected.kind]] === null"
                class="review__drained"
                :data-test="`rv-drained-${selected.kind}`"
                role="status"
              >
                本栏已加载的条目都已处理。
                <button type="button" data-variant="secondary" data-test="rv-drained-refresh" :disabled="refreshing" @click="review.refresh">
                  刷新队列
                </button>
              </p>

              <div v-if="cursors[KIND_FIELD[selected.kind]] !== null" class="review__more">
                <button
                  type="button"
                  data-variant="secondary"
                  :data-test="`rv-more-${selected.kind}`"
                  :disabled="loadingMore !== null || refreshing"
                  @click="review.loadMore(selected.kind)"
                >
                  {{ loadingMore === selected.kind ? '加载中…' : '更多' }}
                </button>
              </div>

              <p v-if="moreError?.kind === selected.kind" class="review__more-error" :data-test="`rv-more-error-${selected.kind}`" role="alert">
                {{ moreError.message }}
              </p>
            </div>
          </section>
        </template>
      </div>
    </template>
  </VersionPanel>
</template>

<style scoped>
/* 审核页宽度只由 VersionPanel 根元素（含两个插槽内容）统一限制，这里不再单独设上限 */
.review {
  width: 100%;
  gap: 1.1rem;
}

/* 导航与标题段：与发布栏、审核卡共用同一条左右基线 */
.review__top {
  display: grid;
  gap: 0.55rem;
  min-width: 0;
  width: 100%;
}

.review__back {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0;
  font-size: 0.875rem;
}

.review__back a {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.25rem 0.5rem;
  margin-left: -0.5rem;
  border-radius: var(--radius-sm);
  color: var(--color-text);
}

.review__back a:hover,
.review__back a:focus-visible {
  background: var(--color-surface-muted);
  color: var(--color-primary-hover);
  text-decoration: none;
}

.review__back-sep {
  color: var(--color-border-strong);
}

.review__head {
  display: grid;
  gap: 0.35rem;
}

.review__head h2 {
  margin: 0;
  font-size: clamp(1.75rem, 2.4vw, 2rem); /* 28～32px */
  font-weight: 700;
  line-height: 1.25;
}

.review__lede {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

.review__error {
  display: grid;
  gap: 0.6rem;
  justify-items: start;
}

.review__feedback {
  display: grid;
  gap: 0.4rem;
}

.review__feedback p {
  margin: 0;
  font-size: 0.875rem;
}

[data-tone='error'] {
  color: var(--color-danger-text);
}

/* 待处理事项卡片：暖白底、细边框、轻阴影、12px 圆角 */
.review-card {
  display: grid;
  gap: 0.9rem;
  min-width: 0;
  padding: clamp(1.15rem, 2.2vw, 1.5rem);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  box-shadow: var(--shadow-card);
}

.review-card__title {
  display: flex;
  align-items: baseline;
  gap: 0.6rem;
  flex-wrap: wrap;
  margin: 0;
  font-size: 1.2rem;
  font-weight: 700;
}

.review-card__total {
  color: var(--color-text-muted);
  font-size: 0.85rem;
  font-weight: 500;
}

/* 分类切换：真按钮 + 完整 tab 语义，键盘方向键与 Home/End 可用 */
.tabs {
  display: flex;
  align-items: center;
  gap: 0.4rem 1.25rem;
  flex-wrap: wrap;
  padding-bottom: 0.55rem;
  border-bottom: 1px solid var(--color-border);
}

.tabs__tab {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.35rem 0.1rem 0.55rem;
  margin-bottom: -0.6rem;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  border-radius: 0;
  color: var(--color-text-muted);
  font-size: 0.9375rem;
  font-weight: 500;
  transition: border-color 160ms ease, color 160ms ease;
}

.tabs__tab:hover:not(:disabled) {
  background: none;
  color: var(--color-text);
}

.tabs__tab.is-active {
  border-bottom-color: var(--color-primary);
  color: var(--color-primary);
  font-weight: 600;
}

.tabs__tab:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.tabs__count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.5rem;
  padding: 0.05rem 0.4rem;
  border-radius: 999px;
  background: var(--color-surface-muted);
  border: 1px solid var(--color-border);
  color: var(--color-text-muted);
  font-size: 0.75rem;
  font-weight: 600;
}

.tabs__tab.is-active .tabs__count {
  background: var(--color-primary-soft);
  border-color: var(--color-primary-soft);
  color: var(--color-primary);
}

.review-card__rule {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.8125rem;
  line-height: 1.7;
}

.review__done {
  margin: 0;
  color: var(--color-success-text);
  font-size: 0.9375rem;
}

.tabpanel {
  min-width: 0;
}

.tabpanel:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 4px;
  border-radius: var(--radius-sm);
}

.review__empty,
.review__drained {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

.review__drained {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
}

/* 宽松单列列表：条目之间约 20px，条目内约 24px */
.review__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 1.25rem;
}

.item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: start;
  gap: 0.75rem 1.25rem;
  min-width: 0;
  padding: 1.5rem;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 10px;
}

.item__body {
  display: grid;
  gap: 0.55rem;
  min-width: 0;
}

.item__names {
  display: flex;
  align-items: baseline;
  gap: 0.5rem 0.55rem;
  flex-wrap: wrap;
  margin: 0;
  font-size: 1.0625rem;
  line-height: 1.5;
}

.item__name {
  overflow-wrap: anywhere;
}

.item__link {
  color: var(--color-primary);
  font-weight: 600;
}

.item__link.is-undirected,
.item__link--undirected {
  color: var(--color-text-muted);
}

.item__kind {
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  background: var(--color-surface-muted);
  color: var(--color-text-muted);
  font-size: 0.75rem;
  white-space: nowrap;
}

.item__meta {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.85rem;
}

.item__link-row {
  display: flex;
  align-items: center;
  gap: 0.5rem 0.75rem;
  flex-wrap: wrap;
  margin: 0;
}

.item__evidence-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.2rem 0.5rem;
  background: none;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  font-size: 0.8125rem;
  font-weight: 500;
  transition: background-color 160ms ease;
}

.item__evidence-toggle:hover:not(:disabled) {
  background: var(--color-surface-muted);
}

.item__caret {
  color: var(--color-text-muted);
}

.item__source {
  color: var(--color-text-muted);
  font-size: 0.8125rem;
}

.item__source--plain {
  margin: 0;
}

.item__actions,
.merge__actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

/* 条目按钮比发布按钮克制：描边样式，不做大面积实心砖红 */
.item__action {
  padding: 0.35rem 0.9rem;
  font-size: 0.875rem;
}

.item__evidence {
  grid-column: 1 / -1;
  padding-top: 0.35rem;
  border-top: 1px solid var(--color-border);
}

.evidence {
  display: grid;
  gap: 0.6rem;
  list-style: none;
  margin: 0;
  padding: 0;
}

.evidence__row {
  display: grid;
  gap: 0.2rem;
  min-width: 0;
  padding-left: 0.75rem;
  border-left: 2px solid var(--color-primary-soft);
}

.evidence__where {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.8125rem;
}

.evidence__text {
  margin: 0;
  color: var(--color-text);
  font-size: 0.875rem;
  line-height: 1.7;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

/* 合并面板：沿用全局 fieldset 外观，只在卡片内做布局 */
.merge {
  grid-column: 1 / -1;
  gap: 0.7rem;
  border-radius: 10px;
}

.merge__legend {
  font-weight: 600;
  color: var(--color-text);
}

.merge__option {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  color: var(--color-text);
  font-size: 0.9375rem;
}

.merge__summary {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.85rem;
  line-height: 1.7;
}

.item__error {
  grid-column: 1 / -1;
  margin: 0;
}

.item__error p {
  margin: 0 0 0.35rem;
}

.review__more {
  display: flex;
  justify-content: center;
  margin-top: 1.1rem;
}

.review__more button {
  padding: 0.4rem 1.4rem;
  font-size: 0.875rem;
}

.review__more-error {
  margin: 0.6rem 0 0;
}

@media (max-width: 720px) {
  .item {
    grid-template-columns: minmax(0, 1fr);
    padding: 1.1rem;
  }

  .item__actions {
    width: 100%;
  }

  .item__action {
    flex: 1 1 auto;
  }

  .review-card {
    padding: 1.1rem;
  }

  .tabs {
    gap: 0.3rem 1rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .tabs__tab,
  .item__evidence-toggle {
    transition: none;
  }
}
</style>
