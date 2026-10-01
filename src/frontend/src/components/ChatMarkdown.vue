<script setup lang="ts">
import { computed } from 'vue'
import type { Citation } from '../composables/useChat'

const props = defineProps<{ text: string; citations: Citation[]; final: boolean }>()
const emit = defineEmits<{ citation: [citation: Citation] }>()
type Segment = { kind: 'text' | 'code' | 'citation'; text: string; citation?: Citation }
type Block = { kind: 'paragraph' | 'heading' | 'list' | 'code'; segments: Segment[]; text?: string }

function inline(source: string, state: { codeRun: string | null }): Segment[] {
  const result: Segment[] = []
  const byIndex = new Map(props.final ? props.citations.map((item) => [item.index, item]) : [])
  let pending = ''
  const flush = () => { if (pending) { result.push({ kind: 'text', text: pending }); pending = '' } }
  for (let i = 0; i < source.length;) {
    if (state.codeRun) {
      const close = source.indexOf(state.codeRun, i)
      result.push({ kind: 'code', text: close < 0 ? source.slice(i) : source.slice(i, close) })
      if (close < 0) return result
      i = close + state.codeRun.length
      state.codeRun = null
      continue
    }
    if (source[i] === '`') {
      const run = source.slice(i).match(/^`+/)?.[0] ?? '`'
      const close = source.indexOf(run, i + run.length)
      flush()
      if (close < 0) {
        state.codeRun = run
        result.push({ kind: 'code', text: source.slice(i + run.length) })
        return result
      }
      result.push({ kind: 'code', text: source.slice(i + run.length, close) })
      i = close + run.length
      continue
    }
    if (props.final && source[i] === '[') {
      const match = /^\[([1-9]\d*)\]/.exec(source.slice(i))
      const citation = match ? byIndex.get(Number(match[1])) : undefined
      if (match && citation) {
        flush()
        result.push({ kind: 'citation', text: match[0], citation })
        i += match[0].length
        continue
      }
    }
    pending += source[i]
    i++
  }
  flush()
  return result
}

// 只将行首 ``` / ~~~ 识别为围栏；缩进代码块保持普通文本，与服务端 J06 一致。
const blocks = computed<Block[]>(() => {
  const lines = props.text.split('\n')
  const output: Block[] = []
  let fence: string | null = null
  let code: string[] = []
  const inlineState = { codeRun: null as string | null }
  for (const line of lines) {
    const marker = inlineState.codeRun ? undefined : /^(?<run>`{3,}|~{3,})/.exec(line)?.groups?.run
    if (marker && (!fence || marker[0] === fence)) {
      if (fence) { output.push({ kind: 'code', segments: [], text: code.join('\n') }); code = []; fence = null }
      else fence = marker[0]
      continue
    }
    if (fence) { code.push(line); continue }
    if (!line.trim()) continue
    const heading = inlineState.codeRun ? null : /^#{1,6} (.*)$/.exec(line)
    const list = inlineState.codeRun ? null : /^\s*[-*+] (.*)$/.exec(line)
    output.push({ kind: heading ? 'heading' : list ? 'list' : 'paragraph', segments: inline(heading?.[1] ?? list?.[1] ?? line, inlineState) })
  }
  if (fence) output.push({ kind: 'code', segments: [], text: code.join('\n') })
  return output
})
</script>

<template>
  <div class="chat-markdown">
    <template v-for="(block, index) in blocks" :key="index">
      <pre v-if="block.kind === 'code'"><code>{{ block.text }}</code></pre>
      <component :is="block.kind === 'heading' ? 'h4' : block.kind === 'list' ? 'li' : 'p'" v-else>
        <template v-for="(segment, part) in block.segments" :key="part">
          <code v-if="segment.kind === 'code'">{{ segment.text }}</code>
          <button v-else-if="segment.kind === 'citation' && segment.citation" type="button" class="citation" @click="emit('citation', segment.citation)">{{ segment.text }}</button>
          <template v-else>{{ segment.text }}</template>
        </template>
      </component>
    </template>
  </div>
</template>

<style scoped>
pre { overflow-x: auto; padding: .75rem; background: var(--color-surface-muted); }
code { background: var(--color-surface-muted); }
.citation { color: var(--color-primary); border: 0; background: none; cursor: pointer; text-decoration: underline; }
</style>
