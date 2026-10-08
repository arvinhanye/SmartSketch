<script setup lang="ts">
import { RouterLink, type RouteLocationRaw } from 'vue-router'
import AppIcon from '../AppIcon.vue'
import type { CourseCard } from '../../composables/useCourses'
defineProps<{ current: CourseCard; nextStep: string | null; nextLink: {to:RouteLocationRaw;label:string}|null; links: readonly {test:string;label:string;description:string;icon:string;to:RouteLocationRaw}[] }>()
</script>
<template>
 <div class="ui-overview">
  <div class="ui-overview__heading"><h3 id="current-course-title" class="current-name">{{ current.name }}</h3><p v-if="current.description" class="ui-muted">{{ current.description }}</p><div class="ui-chip-row"><span class="ui-chip">课程内身份：{{ current.roleLabel }}（{{ current.myRole === 'teacher' ? '教师视图' : '学生视图' }}）</span><span class="ui-chip" :class="current.status === 'published' ? 'ui-chip--success' : 'ui-chip--muted'">状态：{{ current.statusLabel }}<template v-if="current.publishedVersion !== null"> v{{ current.publishedVersion }}</template></span></div></div>
  <div v-if="nextStep" class="ui-next-step"><div><span class="ui-eyebrow">下一步</span><p data-test="course-stage" role="status">{{ nextStep }}</p></div><RouterLink v-if="nextLink" class="ui-btn ui-btn--primary" data-test="course-next-action" :to="nextLink.to">{{ nextLink.label }}<AppIcon name="chevron" :size="16" /></RouterLink></div>
  <div class="ui-course-entries"><RouterLink v-for="link in links" :key="link.test" class="ui-entry" :data-test="link.test" :to="link.to"><span class="ui-entry__icon"><AppIcon :name="link.icon" :size="22" /></span><span><strong>{{ link.label }}</strong><small>{{ link.description }}</small></span><AppIcon name="chevron" :size="16" /></RouterLink></div>
 </div>
</template>
