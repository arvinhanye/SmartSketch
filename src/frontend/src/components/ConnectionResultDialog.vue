<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch, nextTick } from 'vue'
import type { ConnectionResult } from '../api/apiSettings'
const props = defineProps<{ open: boolean; title: string; pending: boolean; elapsed: number; result: ConnectionResult | null }>()
const emit = defineEmits<{ close: [] }>()
const panel = ref<HTMLElement | null>(null)
let previousFocus: HTMLElement | null = null
function keydown(event: KeyboardEvent) {
  if (!props.open) return
  if (event.key === 'Escape') emit('close')
  if (event.key === 'Tab') {
    event.preventDefault()
    panel.value?.querySelector<HTMLButtonElement>('button')?.focus()
  }
}
watch(() => props.open, async (open) => {
  if (open) { previousFocus = document.activeElement as HTMLElement; await nextTick(); panel.value?.focus() }
  else previousFocus?.focus()
})
onMounted(() => document.addEventListener('keydown', keydown))
onUnmounted(() => document.removeEventListener('keydown', keydown))
</script>
<template>
  <Teleport to="body">
    <div v-if="open" class="dialog-shade" @click.self="emit('close')">
      <section ref="panel" class="dialog" role="dialog" aria-modal="true" :aria-label="`${title}测试结果`" tabindex="-1">
        <header><h3>{{ title }}测试结果</h3><button type="button" aria-label="关闭测试结果" @click="emit('close')">×</button></header>
        <p role="status" :class="{ success: !pending && result?.ok, failure: !pending && !result?.ok }">{{ pending ? '测试中…' : result?.ok ? '连接成功' : '连接失败' }}</p>
        <dl>
          <dt>往返延迟</dt><dd>{{ pending ? `${(elapsed / 1000).toFixed(1)} 秒` : result?.latency_ms != null ? `${result.latency_ms} ms` : '未发起请求' }}</dd>
          <dt>接口地址</dt><dd>{{ result?.provider || '等待响应' }}</dd>
          <dt>使用模型</dt><dd>{{ result?.detail.model || '待确认' }}</dd>
          <template v-if="result?.detail.dimensions != null"><dt>向量维度</dt><dd>{{ result.detail.dimensions }}</dd></template>
          <template v-if="result?.http_status != null"><dt>HTTP 状态</dt><dd>{{ result.http_status }}</dd></template>
        </dl>
        <p v-if="!pending && result && !result.ok" class="error">{{ result.error }}</p>
        <small>延迟为本机进程到服务商的完整往返时间；测试只发送一次最小请求。</small>
      </section>
    </div>
  </Teleport>
</template>
<style scoped>
.dialog-shade{position:fixed;inset:0;z-index:1000;background:rgb(35 32 28 / 32%);display:grid;place-items:center;padding:20px}
.dialog{width:min(100%,22rem);max-height:90vh;overflow:auto;background:var(--color-surface);border:1px solid var(--color-border);border-radius:8px;padding:20px;color:var(--color-text)}
header{display:flex;align-items:center;justify-content:space-between;gap:8px}h3{margin:0;font-size:17px}button{background:var(--color-surface);color:var(--color-text);border:1px solid var(--color-border);padding:3px 10px;min-height:32px}dl{display:grid;grid-template-columns:6rem minmax(0,1fr);gap:10px;font-size:14px}dt,small{color:var(--color-text-muted)}dd{margin:0;overflow-wrap:anywhere}.success{color:var(--color-success-text)}.failure{color:var(--color-primary)}.error{background:var(--color-danger-bg);border:1px solid var(--color-danger-border);color:var(--color-danger-text);padding:10px;border-radius:4px}button:focus-visible,.dialog:focus-visible{outline:2px solid var(--color-border)}
</style>
