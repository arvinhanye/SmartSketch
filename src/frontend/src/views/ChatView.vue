<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { CHAT_STREAM_CLIENT_KEY } from '../api/chatStream'
import { HTTP_CLIENT_KEY } from '../api/client'
import { createPublishedGraphApi, PUBLISHED_GRAPH_API_KEY } from '../api/graph'
import ChatMarkdown from '../components/ChatMarkdown.vue'
import { useChat, type Citation } from '../composables/useChat'
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
const selectedCitation = ref<Citation | null>(null)
const notice = ref('')
watch(courseId, () => { selectedCitation.value = null; notice.value = '' })

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

function openKnowledgePoint(id: string): void {
  if (course.graph && course.graph.graph_version === currentVersion.value && !course.graph.nodes.some((node) => node.id === id)) {
    notice.value = '当前版本已无此知识点'
    return
  }
  notice.value = `知识点：${kpLabel(id)}`
}

function sourceLine(citation: Citation): string {
  const parts: string[] = []
  if (citation.section_path) parts.push(citation.section_path)
  if (citation.page) parts.push(`第 ${citation.page} 页`)
  return parts.join(' · ')
}

// 右栏按回答列出全部出处；点正文中的编号时高亮对应一条
const latestCitations = computed(() => {
  const last = [...entries.value].reverse().find((entry) => entry.status === 'answered')
  return last?.citations ?? []
})

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
    event.preventDefault()
    submitQuestion()
  }
}
</script>

<template>
  <section class="chat" aria-labelledby="chat-title">
    <header class="chat__header">
      <h2 id="chat-title">课程问答</h2>
      <span class="chat__badge">仅依据已发布资料回答</span>
      <p v-if="courseId" class="chat__back">
        <RouterLink :to="{ name: COURSE_ROUTE, params: { cid: courseId } }">返回课程</RouterLink>
      </p>
    </header>

    <div class="chat__layout">
      <div class="chat__main">
        <p v-if="entries.length === 0" class="chat__empty" role="status">
          问一个与本课程有关的问题。回答都会标出出处；已发布资料中没有的内容，助教会直接说明「资料未覆盖」。
        </p>
        <ol class="conversation">
          <li v-for="entry in entries" :key="entry.id" class="exchange">
            <p class="question"><span class="sr-only">你：</span>{{ entry.question }}</p>
            <div class="answer" :class="{ 'answer--not-covered': entry.status === 'not_covered' }" :aria-busy="entry.status === 'streaming'">
              <strong class="answer__who">课程助教</strong>
              <span v-if="entry.status === 'streaming'" class="pending">生成中</span>
              <p v-if="entry.status === 'not_covered'" class="state state--not-covered">资料未覆盖</p>
              <ChatMarkdown :text="entry.answer" :citations="entry.citations" :final="entry.status === 'answered'" @citation="selectedCitation = $event" />
              <p v-if="entry.graphVersion !== undefined && currentVersion !== undefined && entry.graphVersion !== currentVersion" class="version">
                基于第 {{ entry.graphVersion }} 版
              </p>
              <p v-if="entry.status === 'error'" class="state" role="alert">本次回答未完成</p>
              <p v-if="entry.relatedKpIds.length && (entry.status === 'answered' || entry.status === 'not_covered')" class="kps">
                <span class="kps__label">涉及的知识点：</span>
                <button
                  v-for="id in entry.relatedKpIds"
                  :key="id"
                  type="button"
                  class="kps__chip"
                  data-test="chat-kp"
                  @click="openKnowledgePoint(id)"
                >
                  {{ kpLabel(id) }}
                </button>
              </p>
              <button v-if="entry.status === 'error' || entry.status === 'aborted'" type="button" :disabled="sending" @click="ask(entry.question)">重试</button>
            </div>
          </li>
        </ol>
        <p v-if="notice" role="status">
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
        <form class="compose" @submit.prevent="submitQuestion">
          <label for="chat-question" class="sr-only">向课程助教提问</label>
          <textarea
            id="chat-question"
            v-model="question"
            rows="3"
            required
            placeholder="向课程助教提问，比如「为什么循环队列要空出一个位置？」（Ctrl/⌘ + Enter 发送）"
            @keydown="onKeydown"
          />
          <div class="actions">
            <button v-if="sending" type="button" data-variant="secondary" data-test="chat-stop" @click="stop">停止</button>
            <button type="submit" data-test="chat-send" :disabled="sending || !question.trim() || runtime.needsConfig">发送</button>
          </div>
        </form>
      </div>

      <aside class="chat__sources" aria-label="引用原文">
        <h3>出处</h3>
        <p v-if="latestCitations.length === 0 && !selectedCitation" class="chat__sources-empty">
          点回答中的编号查看对应原文。
        </p>
        <ul v-if="latestCitations.length" class="source-list">
          <li v-for="citation in latestCitations" :key="citation.index">
            <button
              type="button"
              class="source-list__item"
              :aria-pressed="selectedCitation?.index === citation.index ? 'true' : 'false'"
              @click="selectedCitation = citation"
            >
              <b>[{{ citation.index }}]</b> {{ sourceLine(citation) }}
            </button>
          </li>
        </ul>
        <article v-if="selectedCitation" class="source">
          <p class="source__where"><b>出处 [{{ selectedCitation.index }}]</b> {{ sourceLine(selectedCitation) }}</p>
          <blockquote>{{ selectedCitation.text }}</blockquote>
          <button type="button" data-variant="secondary" @click="selectedCitation = null">收起原文</button>
        </article>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.chat { display: grid; gap: 0.75rem; }
.chat__header { display: flex; flex-wrap: wrap; align-items: center; gap: 0.25rem 0.75rem; }
.chat__header h2 { margin: 0; }
.chat__badge { font-size: 0.75rem; border-radius: 4px; padding: 0.05rem 0.5rem; background: var(--color-surface-muted); color: var(--color-text-muted); }
.chat__back { margin: 0; font-size: 0.875rem; }
.chat__layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(260px, 20rem); gap: 1rem; align-items: start; }
.chat__main { display: grid; gap: 1rem; min-width: 0; }
.chat__empty { color: var(--color-text-muted); margin: 0; }
.conversation { display: grid; gap: 1rem; padding: 0; margin: 0; list-style: none; }
.exchange { display: grid; gap: 0.6rem; }
.question {
  justify-self: end;
  max-width: 75%;
  margin: 0;
  padding: 0.5rem 0.9rem;
  border-radius: 12px 12px 2px 12px;
  background: var(--color-primary);
  color: #fff;
}
.answer {
  max-width: 90%;
  padding: 0.75rem 1rem;
  border: 1px solid var(--color-border);
  border-radius: 12px 12px 12px 2px;
  background: var(--color-surface);
}
.answer--not-covered { background: var(--color-warning-bg); border-color: var(--color-warning-border); }
.answer__who { display: block; font-size: 0.8rem; color: var(--color-text-muted); font-weight: 500; margin-bottom: 0.25rem; }
.answer :deep(button) { font-size: 0.8rem; }
.pending, .version, .state { color: var(--color-text-muted); font-size: .875rem; }
.state--not-covered { color: var(--color-warning-text); font-weight: 600; margin: 0 0 0.25rem; }
.kps { display: flex; flex-wrap: wrap; align-items: center; gap: 0.35rem; margin: 0.6rem 0 0; }
.kps__label { color: var(--color-text-muted); font-size: 0.8rem; }
.kps__chip {
  background: var(--color-primary-soft);
  color: var(--color-primary-hover);
  border: 1px solid transparent;
  border-radius: 999px;
  padding: 0.1rem 0.7rem;
  font-weight: 500;
}
.kps__chip:hover:not(:disabled) { background: var(--color-primary-soft); border-color: var(--color-primary); }
.compose { display: grid; gap: .5rem; }
.compose textarea { font: inherit; }
.actions { display: flex; gap: .5rem; justify-content: flex-end; }
.chat__sources { display: grid; gap: 0.6rem; position: sticky; top: 1rem; }
.chat__sources h3 { margin: 0; font-size: 0.95rem; }
.chat__sources-empty { color: var(--color-text-muted); font-size: 0.85rem; margin: 0; }
.source-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.25rem; }
.source-list__item {
  width: 100%;
  text-align: left;
  background: var(--color-surface-muted);
  color: var(--color-text);
  font-weight: 400;
  font-size: 0.85rem;
  padding: 0.4rem 0.6rem;
}
.source-list__item:hover:not(:disabled) { background: var(--color-primary-soft); }
.source-list__item[aria-pressed='true'] { background: var(--color-primary-soft); box-shadow: inset 3px 0 0 var(--color-primary); }
.source-list__item b { color: var(--color-primary); }
.source { display: grid; gap: 0.4rem; border-radius: var(--radius-sm); background: var(--color-primary-soft); padding: .6rem .8rem; font-size: 0.85rem; border-left: 3px solid var(--color-primary); }
.source__where { margin: 0 0 0.25rem; color: var(--color-text-muted); }
.source__where b { color: var(--color-primary); }
.source blockquote { white-space: pre-wrap; margin: 0; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
@media (max-width: 900px) {
  .chat__layout { grid-template-columns: minmax(0, 1fr); }
  .chat__sources { position: static; }
}
</style>
