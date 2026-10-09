<script setup lang="ts">
import { computed, inject, nextTick, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { CHAT_STREAM_CLIENT_KEY } from '../api/chatStream'
import { HTTP_CLIENT_KEY } from '../api/client'
import { createPublishedGraphApi, PUBLISHED_GRAPH_API_KEY } from '../api/graph'
import AppIcon from '../components/AppIcon.vue'
import AnswerCard from '../components/chat/AnswerCard.vue'
import PageHeader from '../components/PageHeader.vue'
import PageSheet from '../components/PageSheet.vue'
import SourceViewer from '../components/SourceViewer.vue'
import { citationLine, copyText, sourcesPanel } from '../composables/chatSources'
import { useChat, type ChatEntry, type Citation } from '../composables/useChat'
import { useCopyFeedback } from '../composables/useCopyFeedback'
import { useFollowLatest } from '../composables/useFollowLatest'
import { CHAT_ROUTE, COURSE_ROUTE, SETTINGS_ROUTE, STUDENT_GRAPH_ROUTE } from '../router'
import { useCourseStore } from '../stores/course'
import { useRuntimeStore } from '../stores/runtime'

const client = inject(CHAT_STREAM_CLIENT_KEY, null)
if (client === null) throw new Error('ChatView 需要注入 CHAT_STREAM_CLIENT_KEY')
// 知识点名称取自回答所依据的发布版图谱；没有图谱接口时退回显示标识，不影响问答
const httpClient = inject(HTTP_CLIENT_KEY, null)
const graphApi = inject(PUBLISHED_GRAPH_API_KEY, null) ?? (httpClient ? createPublishedGraphApi(httpClient) : null)

const route = useRoute()
const router = useRouter()
const course = useCourseStore()
const courseId = computed(() => {
  const cid = route.params.cid
  return route.name === CHAT_ROUTE && typeof cid === 'string' && cid !== '' ? cid : null
})
const { entries, question, sending, currentVersion, ask, stop } = useChat(client, courseId)
// L10（ADR-080）：personal 模式下未配置个人模型 API 时不发起提问，引导到设置页
const runtime = useRuntimeStore()
function submitQuestion(): void {
  if (runtime.needsConfig || sending.value) return
  void ask()
}
const notice = ref('')

// UI-QA-01 F2：右侧「出处」面板只显示当前回答的出处。当前回答默认是最后一条；
// 点某条回答的编号或「查看 N 处出处」后改为那一条；提出新问题后回到最后一条。
const activeEntryId = ref<number | null>(null)
const selected = ref<{ entryId: number; citation: Citation } | null>(null)
const activeEntry = computed<ChatEntry | null>(() => entries.value.find((entry) => entry.id === activeEntryId.value) ?? entries.value.at(-1) ?? null)
const panel = computed(() => sourcesPanel(activeEntry.value))
// 展开的原文只属于选中它的那条回答：当前回答变了就不再显示
const selectedCitation = computed(() => (selected.value !== null && selected.value.entryId === activeEntry.value?.id ? selected.value.citation : null))
watch(() => entries.value.length, () => { activeEntryId.value = null })
watch(courseId, () => { activeEntryId.value = null; selected.value = null; notice.value = '' })
function pickCitation(entry: ChatEntry, citation: Citation): void {
  activeEntryId.value = entry.id
  selected.value = { entryId: entry.id, citation }
}
function showSources(entry: ChatEntry): void {
  activeEntryId.value = entry.id
  selected.value = null
}

// F4 复制回答（含出处）与反馈
const copyFeedback = useCopyFeedback()
function copyAnswer(entry: ChatEntry): void {
  void copyFeedback.copy(entry.id, copyText(entry.answer, entry.citations))
}
function copyStateOf(entry: ChatEntry): { ok: boolean } | null {
  const state = copyFeedback.state.value
  return state !== null && state.id === entry.id ? { ok: state.ok } : null
}

// F5 用户在底部时自动跟随最新内容，否则给「回到最新」
const follow = useFollowLatest()
watch(
  () => [entries.value.length, entries.value.at(-1)?.answer.length, entries.value.at(-1)?.status],
  () => { void nextTick(follow.contentChanged) },
)

// 回答带回 graph_version 后，按该版本读一次已发布图谱，放进课程作用域（切课即作废）
let requestedVersion: number | null = null
watch(currentVersion, async (version) => {
  if (version === undefined || graphApi === null || courseId.value === null) return
  if (course.graph?.graph_version === version || requestedVersion === version) return
  requestedVersion = version
  const scope = course.beginRequest()
  try {
    course.setGraph(scope, await graphApi.getPublished(scope.courseId, version, { signal: scope.signal }))
  } catch {
    // 名称只是展示增强；读取失败时继续显示标识
  } finally {
    if (requestedVersion === version) requestedVersion = null
  }
})

const kpNames = computed(() => new Map((course.graph?.nodes ?? []).map((node) => [node.id, node.name])))
function kpLabel(id: string): string {
  return kpNames.value.get(id) ?? id
}

const graphLinkAvailable = router.hasRoute(STUDENT_GRAPH_ROUTE)

function openKnowledgePoint(id: string): void {
  if (course.graph && course.graph.graph_version === currentVersion.value && !course.graph.nodes.some((node) => node.id === id)) {
    notice.value = '当前版本已无此知识点'
    return
  }
  notice.value = `知识点：${kpLabel(id)}`
}

/** 「文件名 · 第 N 页 · 章节」；缺文件名写「资料不可用」（L12，ADR-085） */
function citationSource(citation: Citation): { documentName?: string; page?: number; sectionPath?: string; excerpt?: string } {
  return {
    documentName: citation.document_name ?? undefined,
    page: citation.page ?? undefined,
    sectionPath: citation.section_path ?? undefined,
    excerpt: citation.text,
  }
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
    event.preventDefault()
    submitQuestion()
  }
}
</script>

<template>
  <PageSheet class="chat" labelledby="chat-title">
    <PageHeader id="chat-title" title="课程问答" description="只依据已发布的课程资料回答，每条回答都标注出处。">
      <template #actions>
        <span class="ui-chip">仅依据已发布资料回答</span>
        <RouterLink v-if="courseId" class="ui-btn" :to="{ name: COURSE_ROUTE, params: { cid: courseId } }"><AppIcon name="back" :size="16" />返回课程</RouterLink>
      </template>
    </PageHeader>

    <div class="chat__layout">
      <div class="chat__main">
        <p v-if="entries.length === 0" class="chat__empty" role="status">
          问一个与本课程有关的问题。回答都会标出出处；已发布资料中没有的内容，助教会直接说明「资料未覆盖」。
        </p>
        <ol class="conversation">
          <li v-for="entry in entries" :key="entry.id" class="exchange">
            <p class="question"><span class="sr-only">你：</span>{{ entry.question }}</p>
            <AnswerCard
              :entry="entry"
              :active="activeEntry?.id === entry.id"
              :current-version="currentVersion"
              :course-id="courseId"
              :graph-link-available="graphLinkAvailable"
              :kp-label="kpLabel"
              :copy-state="copyStateOf(entry)"
              :sending="sending"
              @citation="pickCitation(entry, $event)"
              @show-sources="showSources(entry)"
              @copy="copyAnswer(entry)"
              @retry="ask(entry.question)"
              @open-kp="openKnowledgePoint"
            />
          </li>
        </ol>
        <p v-if="notice" class="chat__notice" role="status">
          {{ notice }}
          <RouterLink
            v-if="courseId && router.hasRoute(STUDENT_GRAPH_ROUTE)"
            :to="{ name: STUDENT_GRAPH_ROUTE, params: { cid: courseId } }"
          >在图谱中查看</RouterLink>
        </p>
        <p v-if="runtime.needsConfig" class="model-required" data-test="model-config-required" role="alert">
          提问前需要先配置你的模型 API，回答会使用你自己的模型。
          <RouterLink :to="{ name: SETTINGS_ROUTE }" data-test="model-config-link">去设置</RouterLink>
        </p>
        <div class="chat__dock">
          <button v-if="follow.behind.value" type="button" class="chat__jump" data-test="chat-jump-latest" @click="follow.scrollToLatest">
            <AppIcon name="chevronDown" :size="14" />回到最新
          </button>
          <form class="compose" data-test="chat-compose" @submit.prevent="submitQuestion">
            <label for="chat-question" class="sr-only">向课程助教提问</label>
            <textarea
              id="chat-question"
              v-model="question"
              rows="3"
              required
              maxlength="2000"
              placeholder="向课程助教提问，比如「为什么循环队列要空出一个位置？」（Ctrl/⌘ + Enter 发送）"
              @keydown="onKeydown"
            />
            <div class="actions">
              <button v-if="sending" type="button" class="ui-btn" data-test="chat-stop" @click="stop">停止</button>
              <button type="submit" class="ui-btn ui-btn--primary" data-test="chat-send" :disabled="sending || !question.trim() || runtime.needsConfig">发送</button>
            </div>
          </form>
        </div>
      </div>

      <aside class="chat__sources" aria-label="引用原文">
        <h3>出处</h3>
        <p v-if="panel.hint" class="chat__sources-empty">{{ panel.hint }}</p>
        <ul v-if="panel.citations.length" class="source-list">
          <li v-for="citation in panel.citations" :key="citation.index">
            <button
              type="button"
              class="source-list__item"
              :aria-pressed="selectedCitation?.index === citation.index ? 'true' : 'false'"
              @click="activeEntry && pickCitation(activeEntry, citation)"
            >
              <b>[{{ citation.index }}]</b> {{ citationLine(citation) }}
            </button>
          </li>
        </ul>
        <!-- C05-2：与图谱来源同一个查看器（600 字折叠、文件名与位置、纯文本渲染） -->
        <article v-if="selectedCitation" class="source">
          <p class="source__where"><b>出处 [{{ selectedCitation.index }}]</b></p>
          <SourceViewer :source="citationSource(selectedCitation)" @close="selected = null" />
        </article>
      </aside>
    </div>
  </PageSheet>
</template>

<style scoped>
.chat__layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(240px, 300px); gap: 28px; align-items: start; }
.chat__main { display: grid; gap: 16px; min-width: 0; }
.chat__empty { margin: 0; padding: 28px; border: 1px dashed var(--gw-edge, #747a87); border-radius: 10px; background: var(--gw-canvas, #f4f5f7); color: var(--gw-text-2, #545967); font-size: 14px; line-height: 26px; }
.conversation { display: grid; gap: 20px; padding: 0; margin: 0; list-style: none; }
.exchange { display: grid; gap: 10px; }
.question { justify-self: end; max-width: 85%; margin: 0; padding: 12px 16px; border-radius: 12px 12px 2px 12px; background: var(--ss-primary, #5b5bd6); color: #fff; font-size: 14px; line-height: 24px; }
.chat__notice { margin: 0; font-size: 13px; color: var(--gw-text-2, #545967); }
.model-required { margin: 0; padding: 12px 16px; border-radius: 8px; background: var(--gw-warn-bg, #fdf4e3); color: var(--gw-warn, #8a5a10); font-size: 13px; line-height: 22px; }
/* 输入区固定在内容区底部，对话变长时提问不必来回滚动 */
.chat__dock { position: sticky; bottom: 0; z-index: 2; display: grid; gap: 8px; padding: 12px 0 4px; background: linear-gradient(to bottom, transparent, var(--gw-panel, #f8f9fb) 12px); }
.chat__jump { justify-self: center; display: inline-flex; align-items: center; gap: 6px; min-height: 32px; padding: 4px 14px; border: 1px solid var(--gw-edge, #747a87); border-radius: 999px; background: #fff; color: var(--gw-accent, #5145cd); font-size: 13px; font-weight: 500; cursor: pointer; }
.chat__jump:hover { background: var(--gw-selected, #e9e6fa); }
.compose { display: grid; gap: 8px; padding: 12px; border: 1px solid var(--gw-edge, #747a87); border-radius: 10px; background: #fff; box-shadow: 0 -2px 12px rgb(29 36 51 / 6%); }
.compose textarea { width: 100%; min-width: 0; box-sizing: border-box; resize: vertical; border: 0; background: transparent; color: var(--gw-text, #20232a); font: inherit; font-size: 14px; line-height: 24px; padding: 6px 8px; }
.compose textarea::placeholder { color: var(--gw-text-3, #626876); }
.compose textarea:focus-visible { outline: 2px solid var(--gw-accent, #5145cd); outline-offset: 2px; border-radius: 6px; }
.actions { display: flex; gap: 8px; justify-content: flex-end; }
.chat__sources { display: grid; gap: 10px; position: sticky; top: 16px; padding: 18px; border: 1px solid var(--gw-line, #d2d5de); border-radius: 10px; background: var(--gw-canvas, #f4f5f7); }
.chat__sources h3 { margin: 0; }
.chat__sources-empty { margin: 0; font-size: 13px; line-height: 22px; color: var(--gw-text-2, #545967); }
.source-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
.source-list__item { width: 100%; text-align: left; padding: 8px 10px; border: 1px solid var(--gw-edge, #747a87); border-radius: 6px; background: #fff; color: var(--gw-text, #20232a); font-size: 13px; line-height: 20px; cursor: pointer; }
.source-list__item:hover { background: var(--gw-hover, #eaecf1); }
.source-list__item[aria-pressed='true'] { background: var(--gw-selected, #e9e6fa); box-shadow: inset 3px 0 0 var(--gw-accent, #5145cd); }
.source-list__item b { color: var(--gw-accent, #5145cd); }
.source-list__item:focus-visible { outline: 2px solid var(--gw-accent, #5145cd); outline-offset: 2px; }
.source { display: grid; gap: 6px; font-size: 13px; }
.source__where { margin: 0; color: var(--gw-text-2, #545967); }
.source__where b { color: var(--gw-accent, #5145cd); }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
@media (max-width: 1100px) {
  .chat__layout { grid-template-columns: minmax(0, 1fr); }
  .chat__sources { position: static; }
}
</style>
