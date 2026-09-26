<script setup lang="ts">
import { computed, inject, nextTick, ref, toRef, useId, watch } from 'vue'
import { HTTP_CLIENT_KEY } from '../api/client'
import { createNodeEditApi, NODE_EDIT_API_KEY, type KnowledgePoint } from '../api/nodeEdit'
import {
  FIELD_LABELS,
  KP_STATUS_OPTIONS,
  KP_TYPE_OPTIONS,
  useNodeEditor,
  type EditableField,
} from '../composables/useNodeEditor'

/**
 * 教师节点编辑面板（H07）：编辑名称、别名、类型、定义、重要度、难度与审核状态；保存、解锁、删除。
 *
 * - 保存成功后节点被锁定（自动抽取不再覆盖），已锁定节点显示「解锁」。
 * - 删除需二次确认；确认区说明会一并删除相连关系、未保存的修改会丢失。
 * - 修订冲突时并列展示「你的修改」与「最新内容」，由教师选择；失败时表单保留修改并明确说明未保存。
 * - 所有服务端文本以插值渲染，不用 `v-html`。
 */
const props = defineProps<{ kpId: string | null }>()

const emit = defineEmits<{
  saved: [kp: KnowledgePoint]
  deleted: [kpId: string]
  refreshNeeded: []
  close: []
  courseForbidden: []
}>()

const api =
  inject(NODE_EDIT_API_KEY, null) ??
  (() => {
    const client = inject(HTTP_CLIENT_KEY, null)
    if (client === null) throw new Error('NodeEditor 需要注入 NODE_EDIT_API_KEY 或 HTTP_CLIENT_KEY')
    return createNodeEditApi(client)
  })()

const editor = useNodeEditor({
  api,
  kpId: toRef(props, 'kpId'),
  onSaved: (kp) => emit('saved', kp),
  onDeleted: (kid) => emit('deleted', kid),
  onRefreshNeeded: () => emit('refreshNeeded'),
  onCourseForbidden: () => emit('courseForbidden'),
})
const { status, original, form, dirty, locked, canSave, fieldErrors, loadError, loadRetryable, error, notice, saving, conflict, stale } =
  editor

const uid = useId()
const id = (field: string) => `ne-${field}${uid}`
const titleId = id('title')
const title = ref<HTMLElement | null>(null)
const root = ref<HTMLElement | null>(null)
const confirmBox = ref<HTMLElement | null>(null)
const deleteButton = ref<HTMLButtonElement | null>(null)
const confirmingDelete = ref(false)
const busy = computed(() => status.value === 'loading' || saving.value)

function errorOf(field: EditableField): string | undefined {
  return fieldErrors.value[field]
}

function describedBy(field: EditableField): string | undefined {
  return errorOf(field) ? id(`${field}-error`) : undefined
}

async function onSave(): Promise<void> {
  await editor.save()
}

/**
 * 焦点管理（无障碍）：确认区打开时焦点移入确认区，关闭时归还给触发删除的按钮；
 * 触发按钮已不在 DOM（删除成功）时落到面板根容器，绝不留焦点在 `BODY`。
 */
async function openDeleteConfirm(): Promise<void> {
  confirmingDelete.value = true
  await nextTick()
  confirmBox.value?.focus()
}

async function closeDeleteConfirm(): Promise<void> {
  confirmingDelete.value = false
  await nextTick()
  ;(deleteButton.value ?? root.value)?.focus()
}

async function onConfirmDelete(): Promise<void> {
  const ok = await editor.remove()
  if (!ok && status.value === 'ready') return
  await closeDeleteConfirm()
}

watch(
  () => props.kpId,
  () => {
    confirmingDelete.value = false
  },
)

// 载入新节点后把焦点移到标题
watch(
  () => (status.value === 'ready' ? original.value?.id : null),
  async (next, prev) => {
    if (next === null || next === undefined || next === prev) return
    await nextTick()
    title.value?.focus()
  },
)
</script>

<template>
  <aside
    ref="root"
    class="node-editor"
    data-test="node-editor"
    tabindex="-1"
    :aria-labelledby="original ? titleId : undefined"
    :aria-label="original ? undefined : '知识点编辑'"
    :aria-busy="busy ? 'true' : 'false'"
    @keydown.esc="emit('close')"
  >
    <button type="button" class="node-editor__close" data-test="ne-close" aria-label="关闭知识点编辑" @click="emit('close')">
      ×
    </button>

    <p v-if="status === 'idle'" data-test="ne-empty" role="status">在图谱中选择一个知识点进行编辑。</p>

    <p v-else-if="status === 'loading'" data-test="ne-loading" role="status">知识点加载中…</p>

    <div v-else-if="status === 'deleted'" data-test="ne-deleted" role="status">
      <p>{{ notice ?? error ?? '该知识点已删除。' }}</p>
    </div>

    <div v-else-if="status === 'error' || status === 'not_found'" data-test="ne-load-error" role="alert">
      <p>{{ loadError ?? error }}</p>
      <button v-if="loadRetryable" type="button" data-test="ne-retry" @click="editor.reload">重试</button>
    </div>

    <form v-else-if="original" class="node-editor__form" data-test="ne-form" novalidate @submit.prevent="onSave">
      <header>
        <h2 :id="titleId" ref="title" data-test="ne-title" tabindex="-1">编辑：{{ original.name }}</h2>
        <p class="node-editor__meta">
          <span data-test="ne-lock-state">{{ locked ? '已锁定（自动抽取不会覆盖）' : '未锁定（自动抽取可更新）' }}</span>
          <span> · 修订 {{ original.revision }}</span>
          <span v-if="dirty" data-test="ne-dirty"> · 有未保存的修改</span>
        </p>
      </header>

      <div class="node-editor__field">
        <label :for="id('name')">{{ FIELD_LABELS.name }}</label>
        <input
          :id="id('name')"
          v-model="form.name"
          data-test="ne-name"
          type="text"
          :aria-invalid="errorOf('name') ? 'true' : 'false'"
          :aria-describedby="describedBy('name')"
        />
        <p v-if="errorOf('name')" :id="id('name-error')" class="node-editor__error" data-test="ne-name-error">
          {{ errorOf('name') }}
        </p>
      </div>

      <div class="node-editor__field">
        <label :for="id('aliases')">{{ FIELD_LABELS.aliases }}（每行一个，或用逗号、顿号、分号分隔）</label>
        <textarea
          :id="id('aliases')"
          v-model="form.aliases"
          data-test="ne-aliases"
          rows="2"
          :aria-invalid="errorOf('aliases') ? 'true' : 'false'"
          :aria-describedby="describedBy('aliases')"
        />
        <p v-if="errorOf('aliases')" :id="id('aliases-error')" class="node-editor__error" data-test="ne-aliases-error">
          {{ errorOf('aliases') }}
        </p>
      </div>

      <div class="node-editor__field">
        <label :for="id('type')">{{ FIELD_LABELS.type }}</label>
        <select
          :id="id('type')"
          v-model="form.type"
          data-test="ne-type"
          :aria-invalid="errorOf('type') ? 'true' : 'false'"
          :aria-describedby="describedBy('type')"
        >
          <option v-for="opt in KP_TYPE_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
        <p v-if="errorOf('type')" :id="id('type-error')" class="node-editor__error" data-test="ne-type-error">
          {{ errorOf('type') }}
        </p>
      </div>

      <div class="node-editor__field">
        <label :for="id('definition')">{{ FIELD_LABELS.definition }}</label>
        <textarea
          :id="id('definition')"
          v-model="form.definition"
          data-test="ne-definition"
          rows="4"
          :aria-invalid="errorOf('definition') ? 'true' : 'false'"
          :aria-describedby="describedBy('definition')"
        />
        <p
          v-if="errorOf('definition')"
          :id="id('definition-error')"
          class="node-editor__error"
          data-test="ne-definition-error"
        >
          {{ errorOf('definition') }}
        </p>
      </div>

      <div v-for="key in (['importance', 'difficulty'] as const)" :key="key" class="node-editor__field">
        <label :for="id(key)">{{ FIELD_LABELS[key] }}（0～1）</label>
        <input
          :id="id(key)"
          v-model="form[key]"
          :data-test="`ne-${key}`"
          type="text"
          inputmode="decimal"
          :aria-invalid="errorOf(key) ? 'true' : 'false'"
          :aria-describedby="describedBy(key)"
        />
        <p v-if="errorOf(key)" :id="id(`${key}-error`)" class="node-editor__error" :data-test="`ne-${key}-error`">
          {{ errorOf(key) }}
        </p>
      </div>

      <div class="node-editor__field">
        <label :for="id('status')">{{ FIELD_LABELS.status }}</label>
        <select
          :id="id('status')"
          v-model="form.status"
          data-test="ne-status"
          :aria-invalid="errorOf('status') ? 'true' : 'false'"
          :aria-describedby="describedBy('status')"
        >
          <option v-for="opt in KP_STATUS_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
        <p v-if="errorOf('status')" :id="id('status-error')" class="node-editor__error" data-test="ne-status-error">
          {{ errorOf('status') }}
        </p>
      </div>

      <p v-if="error" class="node-editor__error" data-test="ne-error" role="alert">{{ error }}</p>
      <p v-if="notice" data-test="ne-notice" role="status">{{ notice }}</p>

      <section v-if="conflict" class="node-editor__conflict" data-test="ne-conflict" :aria-labelledby="id('conflict')">
        <h3 :id="id('conflict')">修订冲突（最新修订 {{ conflict.currentRevision }}）</h3>
        <template v-if="conflict.action === 'save'">
          <table v-if="conflict.diffs.length" data-test="ne-conflict-diffs">
            <thead>
              <tr>
                <th scope="col">字段</th>
                <th scope="col">你的修改</th>
                <th scope="col">最新内容</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="d in conflict.diffs" :key="d.field" :data-test="`ne-conflict-${d.field}`">
                <th scope="row">{{ d.label }}</th>
                <td>{{ d.mine }}</td>
                <td>{{ d.theirs }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else data-test="ne-conflict-same">你修改的字段与最新内容一致，其他字段已被他人修改。</p>
          <button type="button" data-test="ne-accept-theirs" :disabled="saving" @click="editor.acceptTheirs">
            采用最新内容
          </button>
          <button type="button" data-test="ne-keep-mine" :disabled="saving" @click="editor.keepMine">
            保留我的修改并重新保存
          </button>
        </template>
        <button v-else type="button" data-test="ne-dismiss-conflict" @click="editor.dismissConflict">知道了</button>
      </section>

      <p v-if="stale" data-test="ne-stale">
        <button type="button" data-test="ne-reload" :disabled="saving" @click="editor.reload">重新加载节点</button>
      </p>

      <div class="node-editor__actions">
        <button type="submit" data-test="ne-save" :disabled="!canSave">{{ saving ? '保存中…' : '保存' }}</button>
        <button type="button" data-test="ne-discard" :disabled="!dirty || saving" @click="editor.discard">放弃修改</button>
        <button v-if="locked" type="button" data-test="ne-unlock" :disabled="saving" @click="editor.unlock">解锁</button>
        <button
          v-if="!confirmingDelete"
          ref="deleteButton"
          type="button"
          class="node-editor__danger"
          data-test="ne-delete"
          :disabled="saving"
          @click="openDeleteConfirm"
        >
          删除
        </button>
      </div>

      <div
        v-if="confirmingDelete"
        ref="confirmBox"
        class="node-editor__confirm"
        data-test="ne-delete-confirm"
        role="alertdialog"
        aria-modal="true"
        tabindex="-1"
        :aria-labelledby="id('confirm')"
        @keydown.esc.stop.prevent="closeDeleteConfirm"
      >
        <p :id="id('confirm')">
          确定删除「{{ original.name }}」？与它相连的全部关系会一并删除<span v-if="dirty">，未保存的修改也会丢失</span>。
        </p>
        <button type="button" class="node-editor__danger" data-test="ne-delete-yes" :disabled="saving" @click="onConfirmDelete">
          确认删除
        </button>
        <button type="button" data-test="ne-delete-no" :disabled="saving" @click="closeDeleteConfirm">取消</button>
      </div>
    </form>
  </aside>
</template>

<style scoped>
.node-editor {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  overflow-y: auto;
  overflow-wrap: anywhere;
}

.node-editor__close {
  position: absolute;
  top: 8px;
  right: 8px;
}

.node-editor__form,
.node-editor__field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.node-editor__form {
  gap: 12px;
}

.node-editor__meta {
  color: #555;
}

.node-editor__error {
  color: #c62828;
}

.node-editor [aria-invalid='true'] {
  border-color: #c62828;
}

.node-editor__actions,
.node-editor__confirm {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.node-editor__danger {
  color: #c62828;
}

.node-editor__conflict table {
  border-collapse: collapse;
}

.node-editor__conflict th,
.node-editor__conflict td {
  padding: 2px 8px;
  border: 1px solid #ccc;
  text-align: left;
}
</style>
