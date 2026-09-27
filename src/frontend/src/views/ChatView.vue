<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { CHAT_STREAM_CLIENT_KEY } from '../api/chatStream'
import ChatMarkdown from '../components/ChatMarkdown.vue'
import { useChat, type Citation } from '../composables/useChat'
import { CHAT_ROUTE, COURSE_ROUTE } from '../router'
import { useCourseStore } from '../stores/course'

const client = inject(CHAT_STREAM_CLIENT_KEY, null)
if (client === null) throw new Error('ChatView 需要注入 CHAT_STREAM_CLIENT_KEY')
const route = useRoute()
const course = useCourseStore()
const courseId = computed(() => {
  const cid = route.params.cid
  return route.name === CHAT_ROUTE && typeof cid === 'string' && cid !== '' ? cid : null
})
const { entries, question, sending, currentVersion, ask, stop } = useChat(client, courseId)
const selectedCitation = ref<Citation | null>(null)
const notice = ref('')
watch(courseId, () => { selectedCitation.value = null; notice.value = '' })

function openKnowledgePoint(id: string): void {
  if (course.graph && course.graph.graph_version === currentVersion.value && !course.graph.nodes.some((node) => node.id === id)) {
    notice.value = '当前版本已无此知识点'
    return
  }
  // 图谱画布接线由 H03/H04 完成；本页保留知识点标识供课程导航使用。
  notice.value = `知识点：${id}`
}
</script>

<template>
  <section class="chat" aria-labelledby="chat-title">
    <h2 id="chat-title">课程问答</h2>
    <p v-if="courseId"><RouterLink :to="{ name: COURSE_ROUTE, params: { cid: courseId } }">返回课程</RouterLink></p>
    <ol class="conversation">
      <li v-for="entry in entries" :key="entry.id" class="exchange">
        <p class="question"><strong>你：</strong>{{ entry.question }}</p>
        <div class="answer" :aria-busy="entry.status === 'streaming'">
          <strong>课程助教：</strong>
          <span v-if="entry.status === 'streaming'" class="pending">生成中</span>
          <ChatMarkdown :text="entry.answer" :citations="entry.citations" :final="entry.status === 'answered'" @citation="selectedCitation = $event" />
          <p v-if="entry.graphVersion !== undefined && currentVersion !== undefined && entry.graphVersion !== currentVersion" class="version">
            基于第 {{ entry.graphVersion }} 版
          </p>
          <p v-if="entry.status === 'not_covered'" class="state">资料未覆盖</p>
          <p v-if="entry.status === 'error'" class="state" role="alert">本次回答未完成</p>
          <p v-if="entry.relatedKpIds.length && (entry.status === 'answered' || entry.status === 'not_covered')">
            涉及的知识点：
            <button v-for="id in entry.relatedKpIds" :key="id" type="button" @click="openKnowledgePoint(id)">{{ id }}</button>
          </p>
          <button v-if="entry.status === 'error' || entry.status === 'aborted'" type="button" @click="ask(entry.question)">重试</button>
        </div>
      </li>
    </ol>
    <aside v-if="selectedCitation" class="source" aria-label="引用原文">
      <button type="button" @click="selectedCitation = null">关闭</button>
      <h3>出处 [{{ selectedCitation.index }}]</h3>
      <p>文档 {{ selectedCitation.document_id }}<template v-if="selectedCitation.page"> · 第 {{ selectedCitation.page }} 页</template><template v-if="selectedCitation.section_path"> · {{ selectedCitation.section_path }}</template></p>
      <blockquote>{{ selectedCitation.text }}</blockquote>
    </aside>
    <p v-if="notice" role="status">{{ notice }}</p>
    <form @submit.prevent="ask()">
      <label for="chat-question">向课程助教提问</label>
      <textarea id="chat-question" v-model="question" rows="3" required />
      <div class="actions">
        <button type="submit" :disabled="!question.trim()">发送</button>
        <button v-if="sending" type="button" @click="stop">停止</button>
      </div>
    </form>
  </section>
</template>

<style scoped>
.chat { display: grid; gap: 1rem; }
.conversation { display: grid; gap: 1rem; padding: 0; list-style: none; }
.exchange { border: 1px solid #d0d7de; border-radius: .5rem; padding: 1rem; }
.question { margin-top: 0; }
.pending, .version, .state { color: #57606a; font-size: .875rem; }
.source { border-left: 3px solid #175ab4; padding: .75rem 1rem; background: #f4f6f8; }
.source blockquote { white-space: pre-wrap; margin: .5rem 0; }
form { display: grid; gap: .5rem; }
textarea { font: inherit; }
.actions { display: flex; gap: .5rem; }
</style>
