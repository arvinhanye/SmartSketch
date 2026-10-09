<script setup lang="ts">
defineProps<{ id: string; title: string; description?: string }>()
</script>
<template>
  <header class="ui-page-header">
    <div class="ui-page-header__text"><h2 :id="id">{{ title }}</h2><p v-if="description">{{ description }}</p></div>
    <div v-if="$slots.actions" class="ui-page-header__actions"><slot name="actions" /></div>
  </header>
</template>
