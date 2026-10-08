<script setup lang="ts">
import { RouterLink } from 'vue-router'
import AppIcon from '../AppIcon.vue'
import type { CourseCard } from '../../composables/useCourses'
import { COURSE_ROUTE } from '../../router'
defineProps<{ courses: readonly CourseCard[]; selectedId: string | null; highlightedId?: string | null }>()
</script>
<template>
  <ul class="ui-course-list">
    <li v-for="card in courses" :key="card.id" data-test="course-card" :class="{ 'is-new': card.id === highlightedId }">
      <RouterLink class="ui-course-row" :to="{ name: COURSE_ROUTE, params: { cid: card.id } }" :aria-current="card.id === selectedId ? 'page' : undefined">
        <span class="ui-course-icon"><AppIcon name="chapters" :size="20" /></span>
        <span class="ui-course-row__text"><strong>{{ card.name }}</strong><span v-if="card.description" class="ui-course-description">{{ card.description }}</span></span>
        <span class="ui-course-row__meta">
          <span class="ui-chip">我的身份：{{ card.roleLabel }}</span>
          <span class="ui-chip" :class="card.status === 'published' ? 'ui-chip--success' : 'ui-chip--muted'">状态：{{ card.statusLabel }}<template v-if="card.publishedVersion !== null"> v{{ card.publishedVersion }}</template></span>
          <span class="ui-course-count">知识点：{{ card.knowledgePointCount }}</span>
        </span>
        <AppIcon name="chevron" :size="16" />
      </RouterLink>
    </li>
  </ul>
</template>
