<script setup lang="ts">
import { computed, nextTick, ref, useId, watch } from 'vue'
import type { KnowledgeCard } from '../composables/useStudentGraph'

/**
 * 知识点卡片视图（H11）：分页列出知识点，键盘可完整操作，与图谱共用选中态。
 *
 * - 受控选中：`selectedId` 由页面给出，点击或回车只发 `select`，不自存选中。
 * - 选中项不在当前页时跳到它所在的页；列表变短时页码收回到最后一页。
 * - 键盘：卡片组只占一个 Tab 位（漫游 tabindex）；方向键在卡片间移动，越过页边自动翻页；
 *   Home/End 到本页首尾，PageUp/PageDown 翻页；Enter/空格选中（原生按钮）。
 * - 只接收视图模型，不接触后端响应；文本全部插值渲染。
 */
const props = withDefaults(
  defineProps<{
    cards: KnowledgeCard[]
    selectedId?: string | null
    pageSize?: number
    label?: string
  }>(),
  { selectedId: null, pageSize: 12, label: '知识点卡片' },
)

const emit = defineEmits<{ select: [kpId: string] }>()

const uid = useId()
const page = ref(1)
/** 本页内键盘焦点所在卡片的下标 */
const cursor = ref(0)
const list = ref<HTMLElement | null>(null)

const size = computed(() => (Number.isInteger(props.pageSize) && props.pageSize > 0 ? props.pageSize : 12))
const pageCount = computed(() => Math.max(1, Math.ceil(props.cards.length / size.value)))
const pageCards = computed(() => props.cards.slice((page.value - 1) * size.value, page.value * size.value))
const statusText = computed(() =>
  props.cards.length === 0
    ? ''
    : `第 ${page.value} / ${pageCount.value} 页，共 ${props.cards.length} 个知识点`,
)

function pageOf(kpId: string | null): number | null {
  if (kpId === null) return null
  const index = props.cards.findIndex((card) => card.kpId === kpId)
  return index < 0 ? null : Math.floor(index / size.value) + 1
}

function placeCursor(): void {
  const index = pageCards.value.findIndex((card) => card.kpId === props.selectedId)
  cursor.value = index < 0 ? Math.min(cursor.value, Math.max(0, pageCards.value.length - 1)) : index
}

// 选中项变化（例如在图谱里点了别的知识点）：跳到它所在的页
watch(
  () => props.selectedId,
  (kpId) => {
    const target = pageOf(kpId)
    if (target !== null) page.value = target
    placeCursor()
  },
  { immediate: true },
)

// 列表变化（筛选、换图）：页码收回有效范围，再尽量停在选中项所在页
watch(
  () => [props.cards, size.value] as const,
  () => {
    const target = pageOf(props.selectedId)
    page.value = target ?? Math.min(page.value, pageCount.value)
    placeCursor()
  },
)

async function focusCard(index: number): Promise<void> {
  cursor.value = index
  await nextTick()
  // v-for 的模板引用数组不保证顺序，按 DOM 顺序取
  list.value?.querySelectorAll<HTMLButtonElement>('[data-test="kc-card"]')[index]?.focus()
}

function goTo(next: number, focus: 'first' | 'last' | 'keep' | 'none' = 'none'): void {
  const target = Math.min(Math.max(1, next), pageCount.value)
  if (target !== page.value) {
    page.value = target
    cursor.value = 0
  }
  if (focus === 'none') return
  const last = pageCards.value.length - 1
  void focusCard(focus === 'first' ? 0 : focus === 'last' ? last : Math.min(cursor.value, last))
}

function onKeydown(event: KeyboardEvent, index: number): void {
  const last = pageCards.value.length - 1
  switch (event.key) {
    case 'ArrowRight':
    case 'ArrowDown':
      if (index < last) void focusCard(index + 1)
      else if (page.value < pageCount.value) goTo(page.value + 1, 'first')
      break
    case 'ArrowLeft':
    case 'ArrowUp':
      if (index > 0) void focusCard(index - 1)
      else if (page.value > 1) goTo(page.value - 1, 'last')
      break
    case 'Home':
      void focusCard(0)
      break
    case 'End':
      void focusCard(last)
      break
    case 'PageDown':
      goTo(page.value + 1, 'keep')
      break
    case 'PageUp':
      goTo(page.value - 1, 'keep')
      break
    default:
      return
  }
  event.preventDefault()
}
</script>

<template>
  <section class="knowledge-cards" data-test="knowledge-cards" :aria-labelledby="`kc-title${uid}`">
    <h3 :id="`kc-title${uid}`" class="knowledge-cards__title">{{ label }}</h3>

    <p v-if="cards.length === 0" data-test="kc-empty" role="status">没有符合条件的知识点。</p>

    <template v-else>
      <ul ref="list" class="knowledge-cards__list" data-test="kc-list">
        <li v-for="(card, index) in pageCards" :key="card.kpId">
          <button
            type="button"
            class="knowledge-cards__card"
            data-test="kc-card"
            :data-kp-id="card.kpId"
            :aria-pressed="card.kpId === selectedId ? 'true' : 'false'"
            :tabindex="index === cursor ? 0 : -1"
            @click="emit('select', card.kpId)"
            @focus="cursor = index"
            @keydown="onKeydown($event, index)"
          >
            <span class="knowledge-cards__name">{{ card.name }}</span>
            <span class="knowledge-cards__meta">{{ card.typeLabel }} · {{ card.chapterLabel }} · 层级 {{ card.level }}</span>
          </button>
        </li>
      </ul>

      <nav class="knowledge-cards__pager" :aria-label="`${label}分页`">
        <button type="button" data-test="kc-prev" :disabled="page <= 1" @click="goTo(page - 1)">上一页</button>
        <span data-test="kc-page" aria-live="polite">{{ statusText }}</span>
        <button type="button" data-test="kc-next" :disabled="page >= pageCount" @click="goTo(page + 1)">下一页</button>
      </nav>
    </template>
  </section>
</template>

<style scoped>
.knowledge-cards__list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(12rem, 1fr));
  gap: 0.5rem;
  padding: 0;
  list-style: none;
}
.knowledge-cards__card {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  width: 100%;
  padding: 0.75rem;
  text-align: left;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
}
.knowledge-cards__card[aria-pressed='true'] {
  border-color: #0958d9;
  box-shadow: 0 0 0 1px #0958d9;
}
.knowledge-cards__card:focus-visible {
  outline: 2px solid #0958d9;
  outline-offset: 2px;
}
.knowledge-cards__name {
  font-weight: 600;
}
.knowledge-cards__meta {
  color: #595959;
  font-size: 0.875rem;
}
.knowledge-cards__pager {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  margin-top: 0.5rem;
}
</style>
