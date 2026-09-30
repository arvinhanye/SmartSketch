<script setup lang="ts">
/**
 * 可搜索的模型选择器。
 *
 * - 搜索文字与已选模型分开：打开下拉时清空筛选，因此不会因为已选模型的文字而隐藏其它候选；
 * - 每个选项显示名称与实际调用 ID，**保存与调用一律使用 ID**；
 * - 支持点击选择、上下键移动、回车确认、Esc 关闭与空列表提示；
 * - 列表里始终保留「手动填写」一行，服务商不支持列举模型时也能用。
 */
import { computed, nextTick, ref } from 'vue'
import type { ModelOption } from '../api/apiSettings'

const props = withDefaults(defineProps<{
  modelValue: string
  options: ModelOption[]
  inputId: string
  placeholder?: string
  /** 测试钩子：定位输入框 */
  test?: string
}>(), { placeholder: '获取模型列表后选择，或手动填写模型 ID', test: '' })

const emit = defineEmits<{ (event: 'update:modelValue', value: string): void }>()

const open = ref(false)
const search = ref('')
const highlight = ref(-1)
const root = ref<HTMLElement | null>(null)
const input = ref<HTMLInputElement | null>(null)

function labelOf(id: string): string {
  const found = props.options.find((option) => option.id === id)
  return found?.name || found?.id || id
}

/** 输入框只读展示已选模型；筛选词单独存放，所以已选模型的文字不会过滤候选 */
const display = computed(() => labelOf(props.modelValue))

/** 选项显示：名称（若有）与 ID 分开呈现；没有名称时只显示 ID */
const decorated = computed(() => props.options.map((option) => ({
  id: option.id,
  name: option.name || '',
  showId: Boolean(option.name) && option.name !== option.id,
})))

/** 只在用户输入筛选词时过滤；打开下拉（搜索为空）时展示全部候选 */
const visible = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  if (!keyword) return decorated.value
  return decorated.value.filter((option) =>
    option.id.toLowerCase().includes(keyword) || option.name.toLowerCase().includes(keyword))
})

const manualId = computed(() => search.value.trim())
const manualSelected = computed(() => manualId.value !== '' && manualId.value === props.modelValue)
/** 键盘可达行数：候选 + 手动填写行 */
const rowCount = computed(() => visible.value.length + 1)

function showAll(): void {
  open.value = true
  search.value = ''
  highlight.value = -1
  void nextTick(() => input.value?.select())
}

function filter(): void {
  if (!open.value) showAll()
}

function choose(id: string): void {
  emit('update:modelValue', id)
  open.value = false
  highlight.value = -1
}

function commitManual(): void {
  if (manualId.value) choose(manualId.value)
}

function close(): void {
  open.value = false
  highlight.value = -1
  search.value = ''
}

function move(step: number): void {
  if (!open.value) { showAll(); return }
  highlight.value = (highlight.value + step + rowCount.value) % rowCount.value
}

function confirm(): void {
  if (!open.value) { showAll(); return }
  if (highlight.value >= 0 && highlight.value < visible.value.length) choose(visible.value[highlight.value].id)
  else if (highlight.value === visible.value.length) commitManual()
  else if (manualId.value) commitManual()
}

function onBlur(): void {
  // 失焦只关闭下拉并回显已选模型，不改变选择
  window.setTimeout(() => {
    if (!root.value?.contains(document.activeElement)) close()
  }, 120)
}
</script>

<template>
  <div ref="root" class="model-select" :data-test="test">
    <input
      :id="inputId"
      ref="input"
      :value="display"
      type="text"
      role="combobox"
      autocomplete="off"
      :aria-expanded="open"
      :aria-controls="`${inputId}-listbox`"
      :placeholder="placeholder"
      data-test="model-select-input"
      @focus="showAll"
      @click="showAll"
      @input="search = ($event.target as HTMLInputElement).value; filter()"
      @keydown.down.prevent="move(1)"
      @keydown.up.prevent="move(-1)"
      @keydown.enter.prevent="confirm"
      @keydown.esc.prevent="close"
      @blur="onBlur"
    />
    <p class="model-select__hint">点击可展开全部候选；也可直接输入模型 ID。</p>
    <ul v-if="open" class="model-select__list" role="listbox" :id="`${inputId}-listbox`" data-test="model-options">
      <li
        v-for="(option, index) in visible"
        :key="option.id"
        role="option"
        :aria-selected="option.id === modelValue"
        :class="{ 'is-active': index === highlight, 'is-selected': option.id === modelValue }"
        data-test="model-option"
        @mousedown.prevent="choose(option.id)"
        @mousemove="highlight = index"
      >
        <span class="model-select__name">{{ option.name || option.id }}</span>
        <span v-if="option.showId" class="model-select__id">{{ option.id }}</span>
      </li>
      <li
        class="model-select__manual"
        :class="{ 'is-active': highlight === visible.length }"
        role="option"
        :aria-selected="manualSelected"
        data-test="model-manual"
        @mousedown.prevent="commitManual"
        @mousemove="highlight = visible.length"
      >
        <template v-if="manualId">使用手动填写的 ID：<code>{{ manualId }}</code></template>
        <template v-else>输入任意模型 ID 后回车，可使用列表未列出的模型</template>
      </li>
      <li v-if="!visible.length && !manualId" class="model-select__empty" data-test="model-empty">
        没有匹配的模型：请重新获取模型列表，或直接输入模型 ID
      </li>
    </ul>
  </div>
</template>

<style scoped>
.model-select { position: relative; display: grid; gap: 6px; }
.model-select input { width: 100%; }
.model-select__hint { margin: 0; color: var(--color-text-muted); font-size: 12px; }
.model-select__list {
  position: absolute;
  z-index: 20;
  top: calc(100% - 4px);
  left: 0;
  right: 0;
  max-height: 18rem;
  overflow: auto;
  margin: 0;
  padding: 4px;
  list-style: none;
  background: var(--color-surface);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-card);
}
.model-select__list li {
  display: grid;
  gap: 2px;
  padding: 7px 9px;
  border-radius: var(--radius-sm);
  cursor: pointer;
}
.model-select__list li.is-active { background: var(--color-primary-soft); }
.model-select__list li.is-selected .model-select__name { font-weight: 600; color: var(--color-primary); }
.model-select__name { font-size: 14px; }
.model-select__id { color: var(--color-text-muted); font-family: var(--font-mono); font-size: 12px; }
.model-select__manual { border-top: 1px solid var(--color-border); color: var(--color-text-muted); font-size: 12px; }
.model-select__manual code { font-size: 12px; }
.model-select__empty { color: var(--color-text-muted); font-size: 12px; cursor: default; }
</style>
