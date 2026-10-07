<script setup lang="ts">
import { ref } from 'vue'
import { useGraphObstacle } from '../graph/obstacles'

/** 局部视图提示条：说明隐藏了多少，给出范围（1/2 跳）与恢复入口；隐藏状态必须可见、可恢复 */
defineProps<{ name: string; hiddenCount: number; hops: 1 | 2 }>()
const emit = defineEmits<{ setHops: [hops: 1 | 2]; restore: [] }>()

const root = ref<HTMLElement | null>(null)
useGraphObstacle(root)
</script>

<template>
  <div ref="root" class="gw-focus" data-test="gw-local-bar" role="status">
    <span class="gw-focus__text">只看「{{ name }}」的相邻知识，已隐藏 {{ hiddenCount }} 个</span>
    <span class="gw-segmini" role="group" aria-label="相邻范围">
      <button type="button" :aria-pressed="hops === 1" data-test="gw-local-1" @click="emit('setHops', 1)">1 跳</button>
      <button type="button" :aria-pressed="hops === 2" data-test="gw-local-2" @click="emit('setHops', 2)">2 跳</button>
    </span>
    <button type="button" class="gw-link" data-test="gw-local-restore" @click="emit('restore')">恢复全部</button>
  </div>
</template>
