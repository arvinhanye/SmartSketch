<script setup lang="ts">
import { computed, inject, onActivated, onBeforeUnmount, onMounted, ref, toRaw, watch } from 'vue'
import {
  createGraphLifecycle,
  GRAPH_FACTORY_KEY,
  loadG6Graph,
  type GraphCanvasData,
  type GraphLayoutName,
  type GraphLifecycle,
  type LifecycleStatus,
} from '../graph/lifecycle'

/**
 * 课程知识图谱画布（H04）：只负责把适配图画出来并支持缩放、拖拽。
 * 数据请求、筛选与详情由页面和后续组件负责；`graph` 为 null 表示数据尚未到达。
 */
const props = withDefaults(
  defineProps<{ graph: GraphCanvasData | null; label?: string; layout?: GraphLayoutName }>(),
  { label: '课程知识图谱', layout: 'hierarchical' },
)

const emit = defineEmits<{ nodeClick: [kpId: string] }>()

const factory = inject(GRAPH_FACTORY_KEY, loadG6Graph)
const stage = ref<HTMLElement | null>(null)
const status = ref<LifecycleStatus | 'idle'>('idle')
const drawnOnce = ref(false)
let lifecycle: GraphLifecycle | null = null

const loading = computed(
  () => props.graph === null || (!drawnOnce.value && status.value !== 'error'),
)
const empty = computed(() => !loading.value && props.graph !== null && props.graph.nodes.length === 0)
const ariaLabel = computed(() =>
  props.graph === null
    ? `${props.label}：加载中`
    : `${props.label}：${props.graph.nodes.length} 个知识点，${props.graph.edges.length} 条关系`,
)

function start(): void {
  if (stage.value === null || props.graph === null) return
  drawnOnce.value = false
  // 适配图可能是响应式代理；生命周期会复制一份交给 G6
  lifecycle = createGraphLifecycle(stage.value, {
    data: toRaw(props.graph),
    layout: props.layout,
    factory,
    onNodeClick: (kpId) => emit('nodeClick', kpId),
    onStatus: (next) => {
      status.value = next
      if (next === 'ready') drawnOnce.value = true
    },
  })
}

function stop(): void {
  lifecycle?.destroy()
  lifecycle = null
}

function retry(): void {
  stop()
  start()
}

onMounted(start)

watch(
  () => props.graph,
  (graph) => {
    if (graph === null) return
    if (lifecycle === null) start()
    else lifecycle.update(toRaw(graph))
  },
)

// 布局切换在原图上进行，节点状态（含选中）随数据保留（H05）
watch(
  () => props.layout,
  (layout) => lifecycle?.setLayout(layout),
)

onActivated(() => lifecycle?.refreshSize())
onBeforeUnmount(stop)
</script>

<template>
  <section class="graph-canvas" :aria-busy="loading ? 'true' : 'false'">
    <div ref="stage" class="graph-canvas__stage" role="img" :aria-label="ariaLabel" />
    <div v-if="status === 'error'" class="graph-canvas__overlay" role="alert">
      <p>图谱渲染失败，请重试。</p>
      <button type="button" @click="retry">重试</button>
    </div>
    <p v-else-if="loading" class="graph-canvas__overlay" role="status">图谱加载中…</p>
    <p v-else-if="empty" class="graph-canvas__overlay" role="status">暂无知识点</p>
  </section>
</template>

<style scoped>
.graph-canvas {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 480px;
}

.graph-canvas__stage {
  /* G6 会把容器改为 position: relative，所以尺寸不能靠绝对定位撑开 */
  width: 100%;
  height: 100%;
  min-height: 480px;
  overflow: hidden;
}

.graph-canvas__overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin: 0;
  pointer-events: none;
}

.graph-canvas__overlay button {
  pointer-events: auto;
}
</style>
