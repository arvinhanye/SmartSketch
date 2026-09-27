<script setup lang="ts">
import { computed, inject } from 'vue'
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

const EMPTY_TEXT: Record<ReviewItemKind, string> = {
  low_confidence_relation: '没有低置信度关系。AI 抽取的关系都已达到置信度要求或已处理。',
  suspected_duplicate: '没有疑似重复的知识点。',
  isolated_node: '没有孤立知识点，每个知识点都至少有一条关系。',
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
function primaryName(pair: SuspectedDuplicate): string {
  return pair.candidates.find((c) => c.id === mergeDraft.value?.primaryId)?.name ?? ''
}
function otherName(pair: SuspectedDuplicate): string {
  return pair.candidates.find((c) => c.id !== mergeDraft.value?.primaryId)?.name ?? ''
}
</script>

<template>
  <section class="review" data-test="review-page" aria-labelledby="review-title" :aria-busy="status === 'loading' ? 'true' : 'false'">
    <h2 id="review-title">审核队列</h2>
    <p v-if="courseName" class="review__course">课程：{{ courseName }}<span v-if="status === 'ready'"> · 处理的是草稿，发布后学生才看到</span></p>
    <p v-if="courseId">
      <RouterLink :to="{ name: COURSE_ROUTE, params: { cid: courseId } }">返回课程</RouterLink>
      <template v-if="hasGraphRoute">
        ·
        <RouterLink data-test="rv-graph-link" :to="{ name: TEACHER_GRAPH_ROUTE, params: { cid: courseId } }">编辑图谱</RouterLink>
      </template>
    </p>

    <p v-if="status === 'loading'" data-test="rv-loading" role="status">正在加载审核队列…</p>

    <p v-else-if="status === 'not_teacher'" data-test="rv-not-teacher" role="status">只有本课程的教师可以审核图谱。</p>

    <div v-else-if="status === 'error'" data-test="rv-error" role="alert">
      <p>{{ error }}</p>
      <button v-if="retryable" type="button" data-test="rv-retry" @click="review.reload">重试</button>
    </div>

    <template v-else-if="status === 'ready'">
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
        <button type="button" data-test="rv-refresh-retry" @click="review.refresh">重新加载</button>
      </p>
      <p v-if="allEmpty" data-test="rv-all-empty" role="status">审核队列已清空，可以直接发布。</p>
      <p v-else class="review__hint">队列不阻塞发布：发布时只排除低置信度关系，疑似重复与孤立知识点仅作提示。</p>
      <VersionPanel v-if="courseId" :course-id="courseId" @forbidden="leaveForbidden" />

      <nav class="review__summary" aria-label="审核栏目">
        <a v-for="kind in REVIEW_KINDS" :key="kind" :href="`#rv-${kind}`" :data-test="`rv-total-${kind}`">
          {{ KIND_LABELS[kind] }}（{{ count(kind) }}）
        </a>
      </nav>

      <section
        v-for="kind in REVIEW_KINDS"
        :id="`rv-${kind}`"
        :key="kind"
        class="review__column"
        :data-test="`rv-column-${kind}`"
        :aria-labelledby="`rv-heading-${kind}`"
      >
        <h3 :id="`rv-heading-${kind}`">{{ KIND_LABELS[kind] }}（{{ count(kind) }}）</h3>

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
              —{{ relationLabel(relation) }}→
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

        <!-- 疑似重复 -->
        <ul v-else-if="kind === 'suspected_duplicate'" class="review__list">
          <li
            v-for="pair in items.suspected_duplicates"
            :key="duplicateKey(pair)"
            data-test="rv-duplicate"
            :data-id="duplicateKey(pair)"
            :aria-busy="busyKey === duplicateKey(pair) ? 'true' : 'false'"
          >
            <p>
              <strong>{{ pair.candidates[0]?.name }}</strong> 与 <strong>{{ pair.candidates[1]?.name }}</strong>
            </p>
            <p class="review__meta">
              相似度 {{ percent(pair.similarity) }} · {{ DUPLICATE_REASON_LABELS[pair.reason] ?? pair.reason }}
            </p>

            <fieldset v-if="isMerging(pair)" class="review__merge" data-test="rv-merge-panel">
              <legend>选择保留的主知识点</legend>
              <label v-for="candidate in pair.candidates" :key="candidate.id">
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
              <p data-test="rv-merge-summary">
                「{{ otherName(pair) }}」将并入「{{ primaryName(pair) }}」：名称并入别名，关系与来源迁到主知识点，主知识点被锁定。合并后不能自动拆回。
              </p>
              <button type="button" data-test="rv-merge-confirm" :disabled="busy" @click="review.confirmMerge(pair)">确认合并</button>
              <button type="button" data-test="rv-merge-cancel" :disabled="busy" @click="review.cancelMerge">取消</button>
            </fieldset>
            <div v-else class="review__actions">
              <button type="button" data-test="rv-merge" :disabled="busy" @click="review.startMerge(pair)">合并…</button>
              <button type="button" data-test="rv-not-duplicate" :disabled="busy" @click="review.resolve({ kind, pair }, 'reject')">
                不是重复
              </button>
            </div>

            <div v-if="itemError?.key === duplicateKey(pair)" data-test="rv-item-error" role="alert">
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
    </template>
  </section>
</template>

<style scoped>
.review__course,
.review__hint,
.review__meta {
  color: #595959;
  font-size: 0.875rem;
}
.review__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  margin: 0.5rem 0 1rem;
}
.review__column {
  border-top: 1px solid #f0f0f0;
  padding-top: 0.5rem;
}
.review__list {
  list-style: none;
  padding: 0;
}
.review__list > li {
  border: 1px solid #f0f0f0;
  border-radius: 4px;
  padding: 0.5rem 0.75rem;
  margin-bottom: 0.5rem;
}
.review__actions button + button,
.review__merge button + button {
  margin-left: 0.5rem;
}
.review__merge label {
  display: block;
}
.review__more {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}
[data-tone='error'] {
  color: #cf1322;
}
</style>
