<script setup lang="ts">
import { computed, inject } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { COURSES_API_KEY } from '../api/courses'
import { MATERIALS_API_KEY, TASK_EVENTS_CLIENT_KEY } from '../api/materials'
import { MATERIAL_ACCEPT, SUPPORTED_FORMATS_TEXT, useMaterials } from '../composables/useMaterials'
import { COURSE_ROUTE, MATERIALS_ROUTE } from '../router'

const materialsApi = inject(MATERIALS_API_KEY, null)
if (materialsApi === null) throw new Error('MaterialsView 需要注入 MATERIALS_API_KEY')
const coursesApi = inject(COURSES_API_KEY, null)
if (coursesApi === null) throw new Error('MaterialsView 需要注入 COURSES_API_KEY')
const taskEvents = inject(TASK_EVENTS_CLIENT_KEY, null)
if (taskEvents === null) throw new Error('MaterialsView 需要注入 TASK_EVENTS_CLIENT_KEY')

const route = useRoute()
// 离开资料路由即为 null：composable 关闭全部进度流并中止在途请求
const courseId = computed(() => {
  const cid = route.params.cid
  return route.name === MATERIALS_ROUTE && typeof cid === 'string' && cid !== '' ? cid : null
})

const {
  pageStatus,
  pageError,
  courseName,
  rows,
  isEmpty,
  limitText,
  reload,
  selectedName,
  fileInvalid,
  selectionVersion,
  uploading,
  uploadError,
  uploadSuccess,
  canRetryUpload,
  selectFile,
  submitUpload,
  retryUpload,
  retryTask,
  cancel,
  reconnect,
  requestDelete,
  cancelDelete,
  confirmDelete,
} = useMaterials({ materialsApi, coursesApi, taskEvents, courseId })

function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  selectFile(input.files?.[0] ?? null)
}
</script>

<template>
  <section class="materials" data-test="materials-page" aria-labelledby="materials-title" :aria-busy="pageStatus === 'loading'">
    <h2 id="materials-title">资料上传与处理进度</h2>
    <p v-if="courseName" class="course">课程：{{ courseName }}</p>
    <p v-if="courseId">
      <RouterLink :to="{ name: COURSE_ROUTE, params: { cid: courseId } }">返回课程</RouterLink>
    </p>

    <p v-if="pageStatus === 'loading'" data-test="materials-loading" role="status">正在加载资料…</p>
    <p v-else-if="pageStatus === 'forbidden'" data-test="materials-forbidden" role="alert">{{ pageError }}</p>
    <div v-else-if="pageStatus === 'error'">
      <p data-test="materials-error" role="alert">{{ pageError }}</p>
      <button type="button" data-test="materials-retry" @click="reload">重试</button>
    </div>

    <template v-else>
      <form
        class="upload"
        data-test="material-upload-form"
        novalidate
        :aria-busy="uploading"
        @submit.prevent="submitUpload"
      >
        <fieldset :disabled="uploading">
          <legend>上传资料</legend>
          <label for="material-file">选择资料文件</label>
          <input
            id="material-file"
            :key="selectionVersion"
            data-test="material-file-input"
            name="file"
            type="file"
            :accept="MATERIAL_ACCEPT"
            :aria-invalid="fileInvalid ? 'true' : undefined"
            aria-describedby="material-upload-hint material-upload-feedback"
            @change="onFileChange"
          />
          <p id="material-upload-hint" data-test="upload-hint" class="hint">
            支持 {{ SUPPORTED_FORMATS_TEXT }}，<template v-if="limitText">单个文件不超过 {{ limitText }}。</template
            ><template v-else>文件大小上限以服务器为准。</template>
          </p>
          <div id="material-upload-feedback">
            <p v-if="uploadError" data-test="upload-error" role="alert">{{ uploadError }}</p>
            <p v-if="uploadSuccess" data-test="upload-success" role="status">
              已上传「{{ uploadSuccess }}」，正在处理。
            </p>
          </div>
          <div class="actions">
            <button type="submit" data-test="upload-submit" :disabled="uploading">
              {{ uploading ? '上传中…' : selectedName ? `上传「${selectedName}」` : '上传' }}
            </button>
            <button v-if="canRetryUpload" type="button" data-test="upload-retry" @click="retryUpload">重试上传</button>
          </div>
        </fieldset>
      </form>

      <section class="list" aria-labelledby="materials-list-title">
        <h3 id="materials-list-title">已上传资料</h3>
        <p v-if="isEmpty" data-test="materials-empty">尚未上传资料。上传后可在这里查看处理进度。</p>
        <ul v-else class="rows">
          <li v-for="row in rows" :key="row.documentId" data-test="material-row" :data-document-id="row.documentId">
            <p class="name">
              <span>{{ row.filename }}</span>
              <span class="meta">{{ row.formatLabel }}<template v-if="row.sizeLabel"> · {{ row.sizeLabel }}</template></span>
            </p>
            <p class="status" aria-live="polite">
              状态：<strong data-test="material-status" :class="`status-${row.status.kind}`">{{ row.status.label }}</strong>
            </p>
            <progress
              v-if="row.progressPercent !== null"
              data-test="material-progress"
              role="progressbar"
              max="100"
              :value="row.progressPercent"
              aria-valuemin="0"
              aria-valuemax="100"
              :aria-valuenow="row.progressPercent"
              :aria-label="`${row.filename} 处理进度`"
            >
              {{ row.progressPercent }}%
            </progress>
            <p v-if="row.errorMessage" data-test="task-error" role="alert">{{ row.errorMessage }}</p>
            <p v-if="row.cancelError" data-test="cancel-error" role="alert">{{ row.cancelError }}</p>
            <p v-if="row.streamNotice" data-test="stream-status" role="status">{{ row.streamNotice }}</p>
            <p v-if="row.deleteError" data-test="delete-error" role="alert">{{ row.deleteError }}</p>
            <p v-if="row.needsReselect" class="hint">如需再次处理，请重新选择文件上传。</p>
            <div class="actions">
              <button
                v-if="row.canCancel"
                type="button"
                data-test="task-cancel"
                :disabled="row.cancelPending"
                :aria-label="`取消处理「${row.filename}」`"
                @click="cancel(row.documentId)"
              >
                {{ row.cancelPending ? '正在提交取消…' : '取消处理' }}
              </button>
              <button
                v-if="row.canRetry"
                type="button"
                data-test="task-retry"
                :disabled="uploading"
                :aria-label="`重新上传「${row.filename}」`"
                @click="retryTask(row.documentId)"
              >
                重新上传
              </button>
              <button
                v-if="row.canReconnect"
                type="button"
                data-test="stream-reconnect"
                @click="reconnect(row.documentId)"
              >
                重新连接
              </button>
              <button
                v-if="row.canDelete && !row.confirmingDelete"
                type="button"
                data-test="material-delete"
                :aria-label="`删除资料「${row.filename}」`"
                @click="requestDelete(row.documentId)"
              >
                删除资料
              </button>
              <template v-if="row.canDelete && row.confirmingDelete">
                <span role="status">删除后不可恢复，确认删除？</span>
                <button
                  type="button"
                  data-test="material-delete-confirm"
                  :disabled="row.deletePending"
                  :aria-label="`确认删除资料「${row.filename}」`"
                  @click="confirmDelete(row.documentId)"
                >
                  {{ row.deletePending ? '正在删除…' : '确认删除' }}
                </button>
                <button
                  type="button"
                  data-test="material-delete-cancel"
                  :disabled="row.deletePending"
                  @click="cancelDelete(row.documentId)"
                >
                  不删除
                </button>
              </template>
            </div>
          </li>
        </ul>
      </section>
    </template>
  </section>
</template>

<style scoped>
.materials {
  display: grid;
  gap: 1.25rem;
}

.upload fieldset {
  display: grid;
  gap: 0.5rem;
  max-width: 32rem;
  border: none;
  padding: 0;
}

.hint,
.meta {
  font-size: 0.875rem;
  color: #57606a;
}

.meta {
  margin-left: 0.75rem;
}

.rows {
  display: grid;
  gap: 0.75rem;
  list-style: none;
  padding: 0;
  margin: 0;
}

.rows li {
  border: 1px solid #d0d7de;
  border-radius: 0.5rem;
  padding: 0.75rem 1rem;
}

.rows p {
  margin: 0.25rem 0;
}

progress {
  width: 100%;
}

.actions {
  display: flex;
  gap: 0.5rem;
}

.status-failed {
  color: #cf222e;
}

.status-cancelling,
.status-cancelled {
  color: #9a6700;
}
</style>
