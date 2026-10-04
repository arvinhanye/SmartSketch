<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { COURSES_API_KEY } from '../api/courses'
import { MATERIALS_API_KEY, TASK_EVENTS_CLIENT_KEY } from '../api/materials'
import {
  MATERIAL_ACCEPT,
  SUPPORTED_FORMATS_TEXT,
  formatBytes,
  useMaterials,
  type TaskStatusKind,
} from '../composables/useMaterials'
import { COURSE_ROUTE, MATERIALS_ROUTE, SETTINGS_ROUTE } from '../router'
import { useRuntimeStore } from '../stores/runtime'

const materialsApi = inject(MATERIALS_API_KEY, null)
if (materialsApi === null) throw new Error('MaterialsView 需要注入 MATERIALS_API_KEY')
const coursesApi = inject(COURSES_API_KEY, null)
if (coursesApi === null) throw new Error('MaterialsView 需要注入 COURSES_API_KEY')
const taskEvents = inject(TASK_EVENTS_CLIENT_KEY, null)
if (taskEvents === null) throw new Error('MaterialsView 需要注入 TASK_EVENTS_CLIENT_KEY')

// L10（ADR-080）：运行模式与本人是否已配置模型 API，用于上传前的配置引导
const runtime = useRuntimeStore()

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

// ---------------------------------------------------------------- 本地展示状态
// 只为展示已选文件的信息；真正的提交文件仍由 composable 持有，这里不参与上传决策
const selectedInfo = ref<{ name: string; size: number; type: string } | null>(null)
const dragDepth = ref(0)
const dragging = ref(false)
/** 拖拽交互的本地提示；与业务 uploadError 分开，不覆盖业务错误 */
const dropNotice = ref<string | null>(null)

const fileInput = ref<HTMLInputElement | null>(null)
const dropzone = ref<HTMLElement | null>(null)

// 键盘焦点可能落在隐藏的原生 input 上（它只有 1px 且透明），
// 因此把「焦点在可见选择区内」显式同步成类名，保证轮廓可见且可复核
const focusWithin = ref(false)

function onDropzoneFocusIn(): void {
  focusWithin.value = true
}

function onDropzoneFocusOut(): void {
  // 焦点在同一选择区内部（label ↔ input）之间移动时不应闪烁
  queueMicrotask(() => {
    const zone = dropzone.value
    if (zone === null) return
    focusWithin.value = zone.contains(document.activeElement)
  })
}

const fileInputValue = computed(() => `${selectionVersion.value}-${selectedName.value ?? ''}`)

/** 是否已经选好一个待上传的文件 */
const hasSelection = computed(() => selectedName.value !== null && selectedInfo.value !== null)
const selectedDetail = computed(() => {
  const info = selectedInfo.value
  if (info === null) return ''
  const parts: string[] = []
  if (info.type.trim() !== '') parts.push(info.type)
  if (Number.isFinite(info.size)) parts.push(formatBytes(info.size))
  return parts.join(' · ')
})
const formatHint = computed(() =>
  limitText.value === null
    ? `支持 ${SUPPORTED_FORMATS_TEXT}，文件大小上限以服务器为准。`
    : `支持 ${SUPPORTED_FORMATS_TEXT}，单个文件不超过 ${limitText.value}。`,
)

function applySelection(file: File | null): void {
  selectFile(file)
  selectedInfo.value = file === null ? null : { name: file.name, size: file.size, type: file.type }
}

function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  // 允许再次选择同一个文件：清空原生值，下次 change 仍会触发
  input.value = ''
  applySelection(file)
}

function openPicker(): void {
  if (uploading.value) return
  dropNotice.value = null
  fileInput.value?.click()
}

function isFileDrag(event: DragEvent): boolean {
  const types = event.dataTransfer?.types
  return types === undefined ? false : Array.from(types).includes('Files')
}

function onDragEnter(event: DragEvent): void {
  if (uploading.value || !isFileDrag(event)) return
  event.preventDefault()
  dropNotice.value = null
  dragDepth.value += 1
  dragging.value = true
}

function onDragOver(event: DragEvent): void {
  // 先识别文件拖拽并阻止默认行为，否则浏览器会直接打开被拖入的文件；
  // 上传中同样必须取消默认动作，只把提示光标改成不可放置
  if (!isFileDrag(event)) return
  event.preventDefault()
  if (event.dataTransfer !== null) {
    event.dataTransfer.dropEffect = uploading.value ? 'none' : 'copy'
  }
}

function onDragLeave(event: DragEvent): void {
  if (!isFileDrag(event)) return
  dragDepth.value = Math.max(0, dragDepth.value - 1)
  if (dragDepth.value === 0) dragging.value = false
}

function resetDrag(): void {
  dragDepth.value = 0
  dragging.value = false
}

function onDrop(event: DragEvent): void {
  // 非文件拖拽（文本、链接等）不作为文件选择处理
  if (!isFileDrag(event)) return
  // 先取消默认动作再判断上传状态：上传中也不允许浏览器打开拖入的文件
  event.preventDefault()
  if (uploading.value) {
    resetDrag()
    return
  }
  const transfer = event.dataTransfer
  resetDrag()
  if (transfer === null) return
  const files = Array.from(transfer.files ?? [])
  if (files.length > 1) {
    dropNotice.value = '一次只能选择一个文件。'
    return
  }
  const file = files[0]
  if (file === undefined) {
    // 目录等拿不到有效 File 的拖入：明确提示，且不清空已有选择
    dropNotice.value = '不支持拖入文件夹，请选择单个资料文件。'
    return
  }
  dropNotice.value = null
  applySelection(file)
}

function clearSelection(): void {
  applySelection(null)
  dropNotice.value = null
  // 焦点回到可见的选择区：隐藏的原生 input 没有可见反馈，不能把焦点留在那里
  dropzone.value?.focus()
}

// 上传成功后 composable 会递增 selectionVersion，这里同步清掉展示信息
watch(selectionVersion, () => { selectedInfo.value = null })
// 离开页面或切换课程后不残留旧文件信息（resetState 不改 selectionVersion）
watch(courseId, () => {
  selectedInfo.value = null
  dropNotice.value = null
  focusWithin.value = false
  resetDrag()
})

// ---------------------------------------------------------------- 状态徽标
/** 状态图标：失败告警、完成对勾、待审核沙漏、其余旋转/时钟，颜色之外还有图形区分 */
function badgeIcon(kind: TaskStatusKind): 'failed' | 'completed' | 'waiting' | 'active' {
  if (kind === 'failed' || kind === 'cancelled') return 'failed'
  if (kind === 'completed') return 'completed'
  if (kind === 'awaiting_review') return 'waiting'
  return 'active'
}
</script>

<template>
  <div class="page materials" data-test="materials-page" aria-labelledby="materials-title" :aria-busy="pageStatus === 'loading'">
    <p v-if="courseId" class="materials__back">
      <RouterLink data-test="materials-back" :to="{ name: COURSE_ROUTE, params: { cid: courseId } }">← 返回课程</RouterLink>
    </p>

    <header class="materials__head">
      <h2 id="materials-title">资料上传与处理进度</h2>
      <p class="materials__lede">上传课程相关的教学资料，系统将自动进行解析与处理。</p>
      <p v-if="courseName" class="materials__course" data-test="materials-course">当前课程：{{ courseName }}</p>
    </header>

    <p v-if="pageStatus === 'loading'" data-test="materials-loading" role="status">正在加载资料…</p>
    <p v-else-if="pageStatus === 'forbidden'" data-test="materials-forbidden" role="alert">{{ pageError }}</p>
    <div v-else-if="pageStatus === 'error'" class="materials__error">
      <p data-test="materials-error" role="alert">{{ pageError }}</p>
      <button type="button" data-variant="secondary" data-test="materials-retry" @click="reload">重试</button>
    </div>

    <template v-else>
      <!-- L10（ADR-080）：本人尚未配置模型 API 时给出引导，并停用上传（图谱生成要用自己的模型） -->
      <p v-if="runtime.needsConfig" class="materials__model-required" data-test="model-config-required" role="alert">
        上传前需要先配置你的模型 API，图谱生成会使用你自己的模型。
        <RouterLink :to="{ name: SETTINGS_ROUTE }" data-test="model-config-link">去设置</RouterLink>
      </p>
      <!-- 上传资料 -->
      <section class="materials__card">
        <form
          class="materials__upload"
          data-test="material-upload-form"
          novalidate
          :aria-busy="uploading"
          @submit.prevent="submitUpload"
        >
          <fieldset :disabled="uploading">
            <legend class="materials__card-title">上传资料</legend>
            <p class="materials__card-hint">选择资料文件</p>

            <!-- 自定义选择区：真实 input 保留在内部并隐藏默认外观 -->
            <label
              ref="dropzone"
              class="dropzone"
              :class="{ 'is-dragging': dragging, 'is-invalid': fileInvalid, 'is-disabled': uploading, 'is-focused': focusWithin }"
              data-test="material-dropzone"
              for="material-file"
              tabindex="0"
              aria-describedby="material-upload-hint"
              @keydown.enter.prevent="openPicker"
              @keydown.space.prevent="openPicker"
              @focusin="onDropzoneFocusIn"
              @focusout="onDropzoneFocusOut"
              @dragenter="onDragEnter"
              @dragover="onDragOver"
              @dragleave="onDragLeave"
              @drop="onDrop"
            >
              <input
                id="material-file"
                ref="fileInput"
                :key="fileInputValue"
                class="dropzone__input"
                data-test="material-file-input"
                name="file"
                type="file"
                :accept="MATERIAL_ACCEPT"
                :aria-invalid="fileInvalid ? 'true' : undefined"
                aria-describedby="material-upload-hint material-upload-feedback"
                @change="onFileChange"
              />

              <span class="dropzone__icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="26" height="26" focusable="false">
                  <path
                    d="M14 3H7.5A2.5 2.5 0 0 0 5 5.5v13A2.5 2.5 0 0 0 7.5 21h9a2.5 2.5 0 0 0 2.5-2.5V8z"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.5"
                    stroke-linejoin="round"
                  />
                  <path d="M14 3v5h5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" />
                </svg>
              </span>

              <template v-if="hasSelection">
                <p class="dropzone__label">选择资料文件</p>
                <p class="dropzone__file" data-test="selected-file">
                  <span class="dropzone__filename" data-test="selected-file-name">{{ selectedName }}</span>
                  <span v-if="selectedDetail" class="dropzone__detail" data-test="selected-file-detail">{{ selectedDetail }}</span>
                </p>
                <span class="dropzone__reselect" data-test="reselect-hint">点击这里可以重新选择文件</span>
              </template>
              <template v-else>
                <p class="dropzone__label">点击选择文件或拖拽文件到此处</p>
                <span class="dropzone__accessible">选择资料文件</span>
              </template>
            </label>

            <p id="material-upload-hint" data-test="upload-hint" class="materials__note">{{ formatHint }}</p>

            <div id="material-upload-feedback" class="materials__feedback">
              <p v-if="dropNotice" data-test="drop-notice" role="status">{{ dropNotice }}</p>
              <p v-if="uploadError" data-test="upload-error" role="alert">{{ uploadError }}</p>
              <p v-if="uploadSuccess" data-test="upload-success" role="status">
                已上传「{{ uploadSuccess }}」，正在处理。
              </p>
            </div>

            <div class="materials__actions">
              <button type="submit" data-test="upload-submit" :disabled="uploading || runtime.needsConfig">
                {{ uploading ? '上传中…' : '上传' }}
              </button>
              <button v-if="canRetryUpload" type="button" data-variant="secondary" data-test="upload-retry" @click="retryUpload">
                重试上传
              </button>
              <button
                v-if="hasSelection && !uploading"
                type="button"
                data-variant="secondary"
                data-test="upload-clear"
                @click="clearSelection"
              >
                取消选择
              </button>
            </div>
          </fieldset>
        </form>
      </section>

      <!-- 已上传资料 -->
      <section class="materials__card" aria-labelledby="materials-list-title">
        <h3 id="materials-list-title" class="materials__card-title">已上传资料</h3>
        <p v-if="isEmpty" class="materials__note" data-test="materials-empty">尚未上传资料。上传后可在这里查看处理进度。</p>
        <ul v-else class="rows">
          <li v-for="row in rows" :key="row.documentId" class="row" data-test="material-row" :data-document-id="row.documentId">
            <div class="row__head">
              <span class="row__icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="22" height="22" focusable="false">
                  <path
                    d="M14 3H7.5A2.5 2.5 0 0 0 5 5.5v13A2.5 2.5 0 0 0 7.5 21h9a2.5 2.5 0 0 0 2.5-2.5V8z"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.5"
                    stroke-linejoin="round"
                  />
                  <path d="M14 3v5h5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" />
                </svg>
              </span>

              <div class="row__info">
                <p class="row__name" data-test="material-filename">{{ row.filename }}</p>
                <p class="row__meta">
                  <span>{{ row.formatLabel }}</span>
                  <template v-if="row.sizeLabel"><span aria-hidden="true"> · </span><span>{{ row.sizeLabel }}</span></template>
                </p>
              </div>

              <p class="row__status" aria-live="polite">
                <strong class="badge" :class="`badge--${row.status.kind}`" data-test="material-status">
                  <svg v-if="badgeIcon(row.status.kind) === 'completed'" class="badge__icon" viewBox="0 0 16 16" width="13" height="13" aria-hidden="true" focusable="false">
                    <path d="M3.5 8.5 6.5 11.5 12.5 5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
                  </svg>
                  <svg v-else-if="badgeIcon(row.status.kind) === 'failed'" class="badge__icon" viewBox="0 0 16 16" width="13" height="13" aria-hidden="true" focusable="false">
                    <path d="M8 4.5v4.2M8 11.4v.2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
                    <circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" stroke-width="1.3" />
                  </svg>
                  <svg v-else-if="badgeIcon(row.status.kind) === 'waiting'" class="badge__icon" viewBox="0 0 16 16" width="13" height="13" aria-hidden="true" focusable="false">
                    <circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" stroke-width="1.3" />
                    <path d="M8 4.8V8l2.2 1.4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
                  </svg>
                  <svg v-else class="badge__icon" viewBox="0 0 16 16" width="13" height="13" aria-hidden="true" focusable="false">
                    <circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" stroke-width="1.3" stroke-dasharray="1.6 2.2" />
                    <circle cx="8" cy="8" r="2.1" fill="currentColor" />
                  </svg>
                  {{ row.status.label }}
                </strong>
              </p>
            </div>

            <div class="row__body">
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
              <p v-if="row.needsReselect" class="materials__note">如需再次处理，请重新选择文件上传。</p>

              <div class="row__actions">
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
                  data-variant="secondary"
                  data-test="material-delete"
                  :aria-label="`删除资料「${row.filename}」`"
                  @click="requestDelete(row.documentId)"
                >
                  删除资料
                </button>
                <template v-if="row.canDelete && row.confirmingDelete">
                  <span class="row__confirm" role="status">删除后不可恢复，确认删除？</span>
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
                    data-variant="secondary"
                    data-test="material-delete-cancel"
                    :disabled="row.deletePending"
                    @click="cancelDelete(row.documentId)"
                  >
                    不删除
                  </button>
                </template>
              </div>
            </div>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<style scoped>
/* 本页宽度上限只作用于资料页自身，不动全局 .page / .app-main */
.materials {
  width: 100%;
  max-width: 72.5rem;      /* ≈1160px */
  margin-inline: auto;
  gap: 1.25rem;
}

.materials__back {
  margin: 0;
}

.materials__back a {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.3rem 0.6rem 0.3rem 0.45rem;
  margin-left: -0.45rem;
  border-radius: var(--radius-sm);
  color: var(--color-text);
  font-size: 0.875rem;
}

.materials__back a:hover,
.materials__back a:focus-visible {
  background: var(--color-surface-muted);
  color: var(--color-primary-hover);
  text-decoration: none;
}

.materials__head {
  display: grid;
  gap: 0.4rem;
}

.materials__head h2 {
  margin: 0;
  font-size: clamp(1.625rem, 2.2vw, 1.875rem);   /* 26～30px */
  font-weight: 700;
  line-height: 1.25;
}

.materials__lede {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

.materials__course {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.8125rem;
}

.materials__error {
  display: grid;
  gap: 0.6rem;
  justify-items: start;
}

/* 两张独立卡片：暖白底、细边框、轻阴影、约 12px 圆角 */
.materials__card {
  display: grid;
  gap: 0.85rem;
  min-width: 0;
  padding: clamp(1.15rem, 2.2vw, 1.75rem);   /* 24～28px */
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  box-shadow: var(--shadow-card);
}

.materials__card-title {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 600;
  color: var(--color-text);
}

.materials__card-hint {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

.materials__note {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.8125rem;
  line-height: 1.7;
}

.materials__feedback {
  display: grid;
  gap: 0.4rem;
}

.materials__feedback p {
  margin: 0;
  font-size: 0.875rem;
}

/* 表单只做布局：去掉全局 fieldset 的边框与背景，宽度不再限制成窄栏 */
.materials__upload fieldset {
  display: grid;
  gap: 0.75rem;
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 0;
  border: none;
  background: none;
}

/* ---------------------------------------------------------------- 文件选择区 */
.dropzone {
  position: relative;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 0.5rem;
  width: 100%;
  min-height: 10rem;          /* ≈160px，不用固定高度避免裁切 */
  padding: 1.35rem 1.1rem;
  text-align: center;
  background: var(--color-surface);
  border: 1px dashed var(--color-border-strong);
  border-radius: 10px;
  cursor: pointer;
  transition: border-color 160ms ease, background-color 160ms ease;
}

.dropzone:hover {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
}

/* 键盘焦点提示：选择区自身或内部隐藏的原生 input 获得焦点时都要显示同一轮廓。
   :focus-visible 覆盖自身焦点，.is-focused 覆盖焦点落在内部隐藏 input 的情况 */
.dropzone:focus-visible,
.dropzone.is-focused {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.dropzone.is-dragging {
  border-color: var(--color-primary);
  border-style: solid;
  background: var(--color-primary-soft);
}

.dropzone.is-invalid {
  border-color: var(--color-danger-border);
}

.dropzone.is-disabled {
  cursor: not-allowed;
  background: var(--color-surface-muted);
  opacity: 0.75;
}

.dropzone__input {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: 0;
  border: 0;
  opacity: 0;
  overflow: hidden;
  white-space: nowrap;
}

.dropzone__icon {
  display: inline-grid;
  place-items: center;
  width: 3rem;
  height: 3rem;
  border-radius: 50%;
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

.dropzone__label {
  margin: 0;
  color: var(--color-text);
  font-size: 0.9375rem;
  font-weight: 500;
}

.dropzone__file {
  display: grid;
  gap: 0.15rem;
  margin: 0;
  max-width: min(100%, 34rem);
}

.dropzone__filename {
  color: var(--color-text);
  font-size: 0.9375rem;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.dropzone__detail {
  color: var(--color-text-muted);
  font-size: 0.8125rem;
}

.dropzone__reselect {
  color: var(--color-primary);
  font-size: 0.8125rem;
}

/* 只补足选择控件的无障碍名称（label 文本的一部分），不重复视觉文案 */
.dropzone__accessible {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: 0;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.materials__actions {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
}

.materials__actions button {
  min-height: 2.6rem;        /* ≈42px */
  padding-inline: 1.25rem;
}

/* ---------------------------------------------------------------- 已上传资料 */
.rows {
  display: grid;
  gap: 0.75rem;
  list-style: none;
  margin: 0;
  padding: 0;
}

.row {
  display: grid;
  gap: 0.6rem;
  min-width: 0;
  padding: 1.05rem 1.15rem;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: var(--color-surface);
}

.row__head {
  display: flex;
  align-items: center;
  gap: 0.9rem;
  min-width: 0;
}

.row__icon {
  flex: none;
  display: inline-grid;
  place-items: center;
  width: 2.75rem;            /* ≈44px */
  height: 2.75rem;
  border-radius: 50%;
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

.row__info {
  flex: 1 1 auto;
  min-width: 0;
}

.row__name {
  margin: 0;
  font-size: 0.975rem;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.row__meta {
  display: flex;
  flex-wrap: wrap;
  margin: 0.1rem 0 0;
  color: var(--color-text-muted);
  font-size: 0.8125rem;
}

.row__status {
  flex: none;
  margin: 0;
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.25rem 0.625rem;
  border: 1px solid transparent;
  border-radius: 999px;
  font-size: 0.8125rem;
  font-weight: 500;
  line-height: 1.5;
  white-space: nowrap;
}

.badge__icon {
  flex: none;
}

.badge--completed {
  background: var(--color-success-bg);
  border-color: var(--color-success-border);
  color: var(--color-success-text);
}

.badge--awaiting_review {
  background: var(--color-warning-bg);
  border-color: var(--color-warning-border);
  color: var(--color-warning-text);
}

.badge--failed {
  background: var(--color-danger-bg);
  border-color: var(--color-danger-border);
  color: var(--color-danger-text);
}

.badge--cancelling,
.badge--cancelled {
  background: var(--color-warning-bg);
  border-color: var(--color-warning-border);
  color: var(--color-warning-text);
}

.badge--processing {
  background: var(--color-primary-soft);
  border-color: var(--color-border);
  color: var(--color-primary-hover);
}

.badge--neutral {
  background: var(--color-surface-muted);
  border-color: var(--color-border);
  color: var(--color-text-muted);
}

/* 一行式信息下方：进度、提示与操作仍然完整保留 */
.row__body {
  display: grid;
  gap: 0.45rem;
  min-width: 0;
}

.row__body p {
  margin: 0;
  font-size: 0.875rem;
}

.row__actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.row__confirm {
  color: var(--color-warning-text);
  font-size: 0.875rem;
}

progress {
  width: 100%;
  height: 0.5rem;
}

@media (max-width: 760px) {
  .materials__card {
    padding: 1.1rem;
  }

  .row__head {
    flex-wrap: wrap;
  }

  .row__status {
    margin-left: calc(2.75rem + 0.9rem);
  }

  .materials__actions button {
    padding-inline: 1rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .dropzone {
    transition: none;
  }
}
</style>
