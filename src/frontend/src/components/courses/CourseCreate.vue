<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { COURSE_NAME_MAX, COURSE_DESCRIPTION_MAX } from '../../composables/useCourses'
defineProps<{ form: { name: string; description: string }; creating: boolean; error: string | null }>()
const emit=defineEmits<{submit: []; cancel: []}>()
const nameInput=ref<HTMLInputElement|null>(null)
onMounted(()=>nameInput.value?.focus())
</script>
<template>
 <form id="course-create-panel" class="ui-create" data-test="course-create" novalidate :aria-busy="creating" @submit.prevent="emit('submit')">
  <fieldset :disabled="creating">
   <legend>创建课程</legend>
   <p class="ui-muted">填写课程名称，创建后即可上传教学资料。</p>
   <label class="ui-field"><span>课程名称</span><input ref="nameInput" v-model="form.name" name="name" type="text" required :maxlength="COURSE_NAME_MAX" placeholder="例如：数据结构" /></label>
   <label class="ui-field"><span>课程简介（可选）</span><textarea v-model="form.description" name="description" rows="3" :maxlength="COURSE_DESCRIPTION_MAX" placeholder="简要介绍课程内容" /><small>{{ form.description.length }} / {{ COURSE_DESCRIPTION_MAX }}</small></label>
   <p v-if="error" data-test="create-error" class="ui-notice ui-notice--danger" role="alert">{{ error }}</p>
   <div class="ui-actions"><button class="ui-btn ui-btn--primary" type="submit" :disabled="creating">{{ creating ? '创建中…' : '创建课程' }}</button><button class="ui-btn" type="button" data-test="course-create-cancel" :disabled="creating" @click="emit('cancel')">取消</button></div>
  </fieldset>
 </form>
</template>
