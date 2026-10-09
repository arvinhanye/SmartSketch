<script setup lang="ts">
defineProps<{ labelledby: string; compact?: boolean }>()
</script>
<template>
  <section class="light-surface ui-sheet" :class="{ 'ui-sheet--compact': compact }" :aria-labelledby="labelledby">
    <div class="ui-sheet__inner"><slot /></div>
  </section>
</template>
