<script setup lang="ts">
import { ref } from 'vue'
import { useGraphObstacle, type ObstacleKind } from '../graph/obstacles'

/** 盖在画布上的浮层容器（搜索栏、右侧工具、提示条、底部折叠条等）：把自己登记为障碍物，标签排布与镜头适应会避开它 */
const props = withDefaults(defineProps<{ kind?: ObstacleKind; as?: string }>(), { kind: 'hard', as: 'div' })
const el = ref<HTMLElement | null>(null)
useGraphObstacle(el, props.kind)
</script>

<template>
  <component :is="as" ref="el"><slot /></component>
</template>
