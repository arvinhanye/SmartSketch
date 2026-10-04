<script setup lang="ts">
import { computed, inject, nextTick, ref, toRef, useId, watch } from 'vue'
import { HTTP_CLIENT_KEY } from '../api/client'
import { createKnowledgeDetailApi, KNOWLEDGE_DETAIL_API_KEY } from '../api/knowledgeDetail'
import {
  highlightSegments,
  useKnowledgeDetail,
  type SourceLocation,
  type SourceView,
} from '../composables/useKnowledgeDetail'
import { EXCERPT_FOLD_CHARS, documentLabel as documentName } from '../composables/sourceLabel'
import SourceViewer from './SourceViewer.vue'

/**
 * 知识点详情抽屉（H06）：定义、别名、直接关系与可定位来源。
 *
 * - `kpId` 来自画布 `nodeClick`；null 时显示空态提示。
 * - 点击来源发出 `locateSource`（页码/章节/块 ID），并在该条下展开来源查看器（文件名、位置、原文片段，
 *   L12/R04），可收起；点击关联知识点发出 `selectKnowledgePoint`。
 * - 资料名优先取服务端随来源返回的同课文件名（L12，ADR-085），其次取页面经 `documentNames` 提供的映射；
 *   都没有时写「资料不可用」，不编造标题，也不拿资料编号冒充。
 * - 所有服务端文本以插值渲染，不用 `v-html`。
 */
const props = withDefaults(
  defineProps<{
    kpId: string | null
    /** document_id → 资料显示名（可选） */
    documentNames?: Record<string, string>
  }>(),
  { documentNames: () => ({}) },
)

const emit = defineEmits<{
  locateSource: [location: SourceLocation]
  selectKnowledgePoint: [kpId: string]
  close: []
  courseForbidden: []
}>()

const api =
  inject(KNOWLEDGE_DETAIL_API_KEY, null) ??
  (() => {
    const client = inject(HTTP_CLIENT_KEY, null)
    if (client === null) throw new Error('KnowledgeDetail 需要注入 KNOWLEDGE_DETAIL_API_KEY 或 HTTP_CLIENT_KEY')
    return createKnowledgeDetailApi(client)
  })()

const { status, detail, error, retryable, activeSourceKey, retry, locate } = useKnowledgeDetail({
  api,
  kpId: toRef(props, 'kpId'),
  onCourseForbidden: () => emit('courseForbidden'),
})

const titleId = `kd-title${useId()}`
const title = ref<HTMLElement | null>(null)
const busy = computed(() => status.value === 'loading')

const relationGroups = computed(() =>
  detail.value === null
    ? []
    : [
        { key: 'prerequisites', label: '前置知识', items: detail.value.prerequisites },
        { key: 'successors', label: '后续知识', items: detail.value.successors },
        { key: 'related', label: '相关知识', items: detail.value.related },
      ],
)

/** 资料文件名：服务端随来源返回的优先，其次页面提供的映射；都没有时为 undefined */
function resolvedName(source: SourceView): string | undefined {
  if (source.documentName) return source.documentName
  const names = props.documentNames
  const name = Object.prototype.hasOwnProperty.call(names, source.documentId) ? names[source.documentId] : undefined
  return typeof name === 'string' && name.trim() !== '' ? name : undefined
}

function documentLabel(source: SourceView): string {
  return documentName(resolvedName(source))
}

function onLocate(source: SourceView): void {
  emit('locateSource', locate(source))
}

// 新详情就绪后把焦点移到标题，屏幕阅读器从知识点名称开始播报
watch(detail, async (next) => {
  if (next === null) return
  await nextTick()
  title.value?.focus()
})
</script>

<template>
  <aside
    class="knowledge-detail"
    data-test="knowledge-detail"
    :aria-labelledby="detail ? titleId : undefined"
    :aria-label="detail ? undefined : '知识点详情'"
    :aria-busy="busy ? 'true' : 'false'"
    @keydown.esc="emit('close')"
  >
    <button type="button" class="knowledge-detail__close" data-test="kd-close" aria-label="关闭知识点详情" @click="emit('close')">
      ×
    </button>

    <p v-if="status === 'idle'" data-test="kd-empty" role="status">点击图谱中的知识点查看定义、关系与来源。</p>

    <p v-else-if="status === 'loading'" data-test="kd-loading" role="status">知识点详情加载中…</p>

    <div v-else-if="status === 'error' || status === 'not_found'" data-test="kd-error" role="alert">
      <p>{{ error }}</p>
      <button v-if="retryable" type="button" data-test="kd-retry" @click="retry">重试</button>
    </div>

    <article v-else-if="detail" class="knowledge-detail__body">
      <header>
        <h2 :id="titleId" ref="title" data-test="kd-title" tabindex="-1">{{ detail.name }}</h2>
        <p class="knowledge-detail__meta">
          <span data-test="kd-type">{{ detail.typeLabel }}</span>
          <span> · 层级 {{ detail.level }}</span>
        </p>
        <p v-if="detail.aliases.length" data-test="kd-aliases">别名：{{ detail.aliases.join('、') }}</p>
      </header>

      <section :aria-labelledby="`${titleId}-definition`">
        <h3 :id="`${titleId}-definition`">定义</h3>
        <p data-test="kd-definition">{{ detail.definition }}</p>
      </section>

      <section
        v-for="group in relationGroups"
        :key="group.key"
        :data-test="`kd-${group.key}`"
        :aria-labelledby="`${titleId}-${group.key}`"
      >
        <h3 :id="`${titleId}-${group.key}`">{{ group.label }}</h3>
        <ul v-if="group.items.length">
          <li v-for="item in group.items" :key="item.id">
            <button type="button" @click="emit('selectKnowledgePoint', item.id)">{{ item.name }}</button>
          </li>
        </ul>
        <p v-else>无</p>
      </section>

      <section data-test="kd-sources" :aria-labelledby="`${titleId}-sources`">
        <h3 :id="`${titleId}-sources`">来源</h3>
        <ol v-if="detail.sources.length">
          <li v-for="source in detail.sources" :key="source.key" data-test="kd-source">
            <button
              type="button"
              data-test="kd-source-locate"
              :aria-pressed="activeSourceKey === source.key ? 'true' : 'false'"
              @click="onLocate(source)"
            >
              <span>{{ documentLabel(source) }}</span>
              <span>：{{ source.locationLabel }}</span>
            </button>
            <blockquote v-if="source.excerpt && activeSourceKey !== source.key" data-test="kd-source-excerpt"
              ><template v-for="(segment, i) in highlightSegments(source.excerpt.length > EXCERPT_FOLD_CHARS ? source.excerpt.slice(0, EXCERPT_FOLD_CHARS) + '…' : source.excerpt, detail.highlightTerms)" :key="i"
                ><mark v-if="segment.mark">{{ segment.text }}</mark
                ><template v-else>{{ segment.text }}</template></template
              ></blockquote
            >
                      <SourceViewer
              v-if="activeSourceKey === source.key"
              :source="{ ...source, documentName: resolvedName(source) }"
              @close="activeSourceKey = null"
            />
          </li>
        </ol>
        <p v-else data-test="kd-sources-none" role="note">该知识点的来源无法定位到页码或章节，暂不显示。</p>
        <p v-if="detail.droppedSources > 0 && detail.sources.length" data-test="kd-sources-dropped" role="note">
          另有 {{ detail.droppedSources }} 条来源缺少页码和章节，未显示。
        </p>
      </section>
    </article>
  </aside>
</template>

<style scoped>
.knowledge-detail {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  overflow-y: auto;
  overflow-wrap: anywhere;
}

.knowledge-detail__close {
  position: absolute;
  top: 8px;
  right: 8px;
}

.knowledge-detail__meta {
  color: #555;
}

.knowledge-detail blockquote {
  margin: 4px 0 0;
  padding-left: 8px;
  border-left: 3px solid #ccc;
  white-space: pre-wrap;
}

.knowledge-detail button[aria-pressed='true'] {
  font-weight: bold;
  outline: 2px solid #1d6fd8;
}
</style>
