<script setup lang="ts">
import { computed, inject, onScopeDispose, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { COURSES_API_KEY } from '../api/courses'
import { MEMBERS_API_KEY } from '../api/members'
import { useMembers } from '../composables/useMembers'
import { COURSE_MEMBERS_ROUTE, COURSE_ROUTE, homeRouteFor, NOTICE_COURSE_FORBIDDEN, ROOT_ROUTE } from '../router'
import { useSessionStore } from '../stores/session'

/**
 * 课程成员管理页（H12，`specs/identity-access.md` §3.3）。
 *
 * 展示结构（2026-10 改版）：返回课程 + 标题与说明 + 当前课程名（直接落在页面背景上），
 * 下面依次是「添加学生」与「成员列表」两张独立卡片；页面宽度与教学资料页一致（≈1160px 居中）。
 * 业务状态与请求全部留在 `useMembers`，本页只做展示与转发：列表四态（加载 / 就绪 / 失败重试 / 无权限）、
 * 添加的提交中与成功失败、移除的进行中与成功失败，以及 `COURSE_FORBIDDEN` 回课程列表都由它决定。
 * 可移除与否以 `MemberRow.removable`（后端授权）为准，前端不自行判断权限。
 */

const api = inject(MEMBERS_API_KEY, null)
if (api === null) throw new Error('MembersView 需要注入 MEMBERS_API_KEY')
const courses = inject(COURSES_API_KEY, null)
if (courses === null) throw new Error('MembersView 需要注入 COURSES_API_KEY')
const coursesApi = courses

const route = useRoute()
const router = useRouter()
const session = useSessionStore()

const courseId = computed(() => {
  const cid = route.params.cid
  return route.name === COURSE_MEMBERS_ROUTE && typeof cid === 'string' && cid !== '' ? cid : null
})

const {
  members,
  status,
  listError,
  isEmpty,
  loadMembers,
  username,
  adding,
  addError,
  addNotice,
  addMember,
  removing,
  removeError,
  removeNotice,
  removeMember,
} = useMembers({
  api,
  courseId,
  // errors.v1.md：COURSE_FORBIDDEN 提示无权限并返回课程列表（提示由课程页渲染）
  onCourseForbidden: () => {
    const role = session.role
    void router.replace(
      role === null ? { name: ROOT_ROUTE } : { name: homeRouteFor(role), query: { notice: NOTICE_COURSE_FORBIDDEN } },
    )
  },
})

// ---------------------------------------------------------------- 当前课程名
/**
 * 课程名只用于展示，取 `GET /api/v1/courses/{cid}`，不硬编码。
 * 读取失败或未返回时整行隐藏，不影响成员列表与增删操作。
 *
 * 每次请求用**独立**的 `AbortController`：切课时只中止上一次课程名请求。
 * 不能复用组件级控制器——`useMembers` 的切课 watcher 在同一轮里调用 `store.selectCourse` 中止在途请求，
 * 复用同一个控制器会把这次课程名请求一起中止，课程名就永远读不回来（本页联调时踩到过）。
 */
const courseName = ref<string | null>(null)
let nameController: AbortController | null = null

async function loadCourseName(cid: string): Promise<void> {
  nameController?.abort()
  const controller = new AbortController()
  nameController = controller
  courseName.value = null
  try {
    const course = await coursesApi.get(cid, { signal: controller.signal })
    if (controller.signal.aborted || course?.id !== cid) return
    courseName.value = course.name
  } catch {
    if (!controller.signal.aborted) courseName.value = null // 课程名只是展示辅助，读不到就不显示这一行
  }
}

watch(courseId, (cid) => {
  if (cid !== null) void loadCourseName(cid)
}, { immediate: true })

onScopeDispose(() => nameController?.abort())

// ---------------------------------------------------------------- 人数标签
/** 人数由真实成员数据计算；渲染期间数量不会在别处被本地加减 */
const counts = computed(() => ({
  total: members.value.length,
  teacher: members.value.filter((row) => row.role === 'teacher').length,
  student: members.value.filter((row) => row.role === 'student').length,
}))
</script>

<template>
  <div class="page members" data-test="members" aria-labelledby="members-title">
    <p v-if="courseId" class="members__back">
      <RouterLink data-test="members-back" :to="{ name: COURSE_ROUTE, params: { cid: courseId } }">
        <span aria-hidden="true">←</span>
        返回课程
      </RouterLink>
    </p>

    <header class="members__head">
      <h2 id="members-title">课程成员管理</h2>
      <p class="members__lede">按用户名添加学生，管理本课程的成员。</p>
      <p v-if="courseName" class="members__course" data-test="members-course">当前课程：{{ courseName }}</p>
    </header>

    <!-- 添加学生 -->
    <section v-if="status !== 'forbidden'" class="members__card" aria-labelledby="member-add-title">
      <form class="members__add" data-test="member-add" novalidate :aria-busy="adding" @submit.prevent="addMember">
        <fieldset :disabled="adding">
          <legend id="member-add-title" class="members__card-title">添加学生</legend>
          <p class="members__card-hint">将已注册的学生账号加入本课程。</p>

          <div class="members__field">
            <!-- label 只包住输入框本身（按钮在 label 之外），这样 input.closest('label') 仍是「学生用户名」，
                 而按钮文案（含提交中的「添加中…」）不会被算进输入框的无障碍名称；
                 aria-label 再显式锁定该名称，避免以后误把别的文字放进 label 时被污染。 -->
            <label class="members__field-label" for="member-username">
              学生用户名
              <input
                id="member-username"
                v-model="username"
                name="username"
                type="text"
                autocomplete="off"
                placeholder="输入学生用户名"
                aria-label="学生用户名"
                required
              />
            </label>
            <div class="members__field-row">
              <button type="submit" class="members__submit" :disabled="adding">
                <svg class="members__submit-icon" viewBox="0 0 16 16" width="15" height="15" aria-hidden="true" focusable="false">
                  <path d="M8 3.2v9.6M3.2 8h9.6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
                </svg>
                {{ adding ? '添加中…' : '添加学生' }}
              </button>
            </div>
          </div>

          <div class="members__feedback">
            <p v-if="addError" class="members__alert" data-test="member-add-error" role="alert">
              <svg class="members__feedback-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false">
                <circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" stroke-width="1.4" />
                <path d="M8 4.8v4M8 11.2v.2" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
              </svg>
              {{ addError }}
            </p>
            <p v-if="addNotice" class="members__ok" data-test="member-add-success" role="status">
              <svg class="members__feedback-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false">
                <path d="M3.6 8.4 6.4 11.2 12.4 5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
              {{ addNotice }}
            </p>
          </div>

          <p class="members__hint">
            <svg class="members__hint-icon" viewBox="0 0 16 16" width="15" height="15" aria-hidden="true" focusable="false">
              <circle cx="8" cy="8" r="6.4" fill="none" stroke="currentColor" stroke-width="1.3" />
              <path d="M8 7.2v4M8 4.9v.2" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
            </svg>
            学生加入后，可查看本课程已发布的内容。
          </p>
        </fieldset>
      </form>
    </section>

    <!-- 成员列表 -->
    <section
      class="members__card"
      data-test="members-region"
      aria-labelledby="members-list-title"
      :aria-busy="status === 'loading'"
    >
      <header class="members__card-head">
        <h3 id="members-list-title" class="members__card-title">成员列表</h3>
        <ul class="members__counts">
          <li class="members__count" data-test="members-count-total">全部 {{ counts.total }} 人</li>
          <li class="members__count" data-test="members-count-teacher">教师 {{ counts.teacher }} 人</li>
          <li class="members__count" data-test="members-count-student">学生 {{ counts.student }} 人</li>
        </ul>
      </header>

      <p class="members__notice">
        <svg class="members__hint-icon" viewBox="0 0 16 16" width="15" height="15" aria-hidden="true" focusable="false">
          <circle cx="8" cy="8" r="6.4" fill="none" stroke="currentColor" stroke-width="1.3" />
          <path d="M8 7.2v4M8 4.9v.2" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
        </svg>
        教师成员仅可由管理员通过命令行调整。
      </p>

      <p v-if="status === 'loading'" data-test="members-loading" role="status">正在加载成员…</p>

      <p v-else-if="status === 'forbidden'" class="members__alert" data-test="members-forbidden" role="alert">{{ listError }}</p>

      <div v-else-if="status === 'error'" class="members__error">
        <p class="members__alert" data-test="members-error" role="alert">{{ listError }}</p>
        <button type="button" data-variant="secondary" data-test="members-retry" @click="loadMembers">重试</button>
      </div>

      <template v-else>
        <p v-if="removeError" class="members__alert" data-test="member-remove-error" role="alert">{{ removeError }}</p>
        <p v-if="removeNotice" class="members__ok" data-test="member-remove-status" role="status">{{ removeNotice }}</p>
        <p v-if="isEmpty" class="members__hint" data-test="members-empty">暂无学生成员。可在上方按用户名添加学生。</p>

        <div v-if="members.length > 0" class="members__table-wrap">
          <table data-test="members-table">
            <!-- 只作表格名称：教师成员只能由管理员维护的说明留在上方提示条，避免两处重复 -->
            <caption class="members__caption">
              课程成员列表
            </caption>
            <thead>
              <tr>
                <th scope="col">用户名</th>
                <th scope="col">课程内身份</th>
                <th scope="col">加入时间</th>
                <th scope="col">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in members" :key="row.userId" data-test="member-row">
                <th scope="row" class="members__name">{{ row.username }}</th>
                <td>
                  <span class="members__role" :class="`members__role--${row.role}`">{{ row.roleLabel }}</span>
                </td>
                <td class="members__time"><time :datetime="row.joinedAt">{{ row.joinedLabel }}</time></td>
                <td>
                  <button
                    v-if="row.removable"
                    type="button"
                    class="members__remove"
                    data-variant="secondary"
                    data-test="member-remove"
                    :aria-label="`移除学生 ${row.username}`"
                    :disabled="removing.has(row.userId)"
                    :aria-busy="removing.has(row.userId)"
                    @click="removeMember(row)"
                  >
                    {{ removing.has(row.userId) ? '移除中…' : '移除' }}
                  </button>
                  <span v-else class="members__locked">
                    <svg class="members__lock" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false">
                      <rect x="3.6" y="7" width="8.8" height="6.2" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.3" />
                      <path d="M5.9 7V5.5a2.1 2.1 0 0 1 4.2 0V7" fill="none" stroke="currentColor" stroke-width="1.3" />
                    </svg>
                    管理员维护
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <p class="members__total" data-test="members-total">共 {{ members.length }} 位成员。</p>
      </template>
    </section>
  </div>
</template>

<style scoped>
/* 页面宽度与教学资料页一致（≈1160px 居中）；标题直接落在背景上，内容分两张卡片 */
.members {
  width: 100%;
  max-width: 72.5rem;
  margin-inline: auto;
  gap: 1.25rem;
}

.members__back {
  margin: 0;
}

.members__back a {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.3rem 0.6rem 0.3rem 0.45rem;
  margin-left: -0.45rem;
  border-radius: var(--radius-sm);
  color: var(--color-text);
  font-size: 0.875rem;
}

.members__back a:hover,
.members__back a:focus-visible {
  background: var(--color-surface-muted);
  color: var(--color-primary-hover);
  text-decoration: none;
}

.members__head {
  display: grid;
  gap: 0.4rem;
}

.members__head h2 {
  margin: 0;
  font-size: clamp(1.625rem, 2.2vw, 1.875rem); /* 26～30px */
  font-weight: 700;
  line-height: 1.25;
}

.members__lede {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

.members__course {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.8125rem;
}

/* ---------------------------------------------------------------- 卡片 */

.members__card {
  display: grid;
  gap: 0.9rem;
  min-width: 0;
  padding: clamp(1.15rem, 2.2vw, 1.6rem);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  box-shadow: var(--shadow-card);
}

.members__card-title {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 600;
  color: var(--color-text);
}

.members__card-hint {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

/* 卡片头：标题与人数标签分居两侧，窄屏换行 */
.members__card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem 1rem;
  flex-wrap: wrap;
  min-width: 0;
}

/* 人数标签：低调的小胶囊，数量来自真实成员数据 */
.members__counts {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  list-style: none;
  margin: 0;
  padding: 0;
}

.members__count {
  padding: 0.2rem 0.7rem;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  background: var(--color-surface-muted);
  color: var(--color-text-muted);
  font-size: 0.8125rem;
  white-space: nowrap;
}

/* 浅色提示条：只说明管理员维护的边界，不用告警配色 */
.members__notice,
.members__hint {
  display: flex;
  align-items: baseline;
  gap: 0.45rem;
  margin: 0;
  padding: 0.6rem 0.85rem;
  border-radius: var(--radius-sm);
  background: var(--color-surface-muted);
  color: var(--color-text-muted);
  font-size: 0.8125rem;
  line-height: 1.7;
}

.members__hint-icon {
  flex: none;
  align-self: center;
  color: var(--color-text-muted);
}

/* ---------------------------------------------------------------- 添加学生 */

/* 表单只做布局：去掉全局 fieldset 的边框与背景，宽度铺满卡片 */
.members__add fieldset {
  display: grid;
  gap: 0.7rem;
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 0;
  border: none;
  background: none;
}

.members__field {
  display: grid;
  gap: 0.35rem;
  color: var(--color-text);
  font-size: 0.875rem;
}

/* 标签只包住输入框本身：文字在上、输入框占满宽度（按钮在 label 之外，与输入框同排居右） */
.members__field-label {
  display: grid;
  gap: 0.35rem;
  width: 100%;
  color: var(--color-text);
  font-size: 0.875rem;
  font-weight: 500;
}

.members__field-label input {
  width: 100%;
  min-height: 2.6rem;
}

/* 桌面端：输入框占主要宽度，砖红按钮同排居右 */
.members__field-row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  min-width: 0;
}

.members__field-row input {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 2.6rem;
}

.members__submit {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  min-height: 2.6rem;
  padding-inline: 1.1rem;
  font-weight: 600;
}

.members__submit-icon {
  flex: none;
}

/* ---------------------------------------------------------------- 反馈 */

.members__feedback {
  display: grid;
  gap: 0.4rem;
}

.members__feedback:empty {
  display: none;
}

.members__feedback p {
  margin: 0;
  font-size: 0.875rem;
}

.members__alert {
  display: flex;
  align-items: baseline;
  gap: 0.45rem;
  margin: 0;
}

.members__ok {
  display: flex;
  align-items: baseline;
  gap: 0.45rem;
  margin: 0;
  color: var(--color-success-text);
}

.members__feedback-icon {
  flex: none;
  align-self: center;
}

.members__error {
  display: grid;
  gap: 0.6rem;
  justify-items: start;
}

/* ---------------------------------------------------------------- 成员表 */

/* 表格在自身容器内横向滚动：窄屏不撑宽整页 */
.members__table-wrap {
  min-width: 0;
  overflow-x: auto;
  border: 1px solid var(--color-border);
  border-radius: 10px;
}

.members__table-wrap table {
  border: none;
  border-radius: 0;
  min-width: 34rem;
}

.members__caption {
  text-align: left;
  padding: 0.6rem 0.9rem 0.35rem;
  color: var(--color-text-muted);
  font-size: 0.78rem;
}

/* 表头浅暖灰；数据行统一背景，只留细分隔线 */
.members__table-wrap thead th {
  background: var(--color-surface-muted);
  color: var(--color-text-muted);
  font-size: 0.8125rem;
  font-weight: 600;
  padding: 0.6rem 0.9rem;
}

.members__table-wrap tbody th,
.members__table-wrap tbody td {
  padding: 0.7rem 0.9rem;
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  vertical-align: middle;
}

.members__table-wrap tbody tr:last-child th,
.members__table-wrap tbody tr:last-child td {
  border-bottom: none;
}

.members__name {
  font-weight: 600;
  color: var(--color-text);
  overflow-wrap: anywhere;
}

/* 身份标签：教师浅松绿，学生浅米色 */
.members__role {
  display: inline-flex;
  align-items: center;
  padding: 0.15rem 0.6rem;
  border: 1px solid transparent;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 500;
  white-space: nowrap;
}

.members__role--teacher {
  background: var(--color-success-bg);
  border-color: var(--color-success-border);
  color: var(--color-success-text);
}

.members__role--student {
  background: var(--color-surface-muted);
  border-color: var(--color-border);
  color: var(--color-text-muted);
}

.members__time {
  color: var(--color-text-muted);
  font-size: 0.875rem;
  white-space: nowrap;
}

/* 移除：小尺寸砖红描边按钮，沿用次要按钮的克制观感 */
.members__remove {
  padding: 0.32rem 0.85rem;
  border-color: var(--color-danger-border);
  color: var(--color-danger-text);
  font-size: 0.8125rem;
}

.members__remove:hover:not(:disabled) {
  background: var(--color-danger-bg);
  border-color: var(--color-danger-border);
  color: var(--color-danger-text);
}

.members__locked {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  color: var(--color-text-muted);
  font-size: 0.8125rem;
  white-space: nowrap;
}

.members__lock {
  flex: none;
}

.members__total {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.8125rem;
}

/* ---------------------------------------------------------------- 窄屏 */

@media (max-width: 760px) {
  .members__card {
    padding: 1.1rem;
  }

  /* 输入框与按钮改纵向排列，按钮铺满整行 */
  .members__field-row {
    flex-direction: column;
    align-items: stretch;
  }

  .members__submit {
    justify-content: center;
    width: 100%;
  }

  /* 标题与人数标签换行后各自占一行 */
  .members__card-head {
    align-items: flex-start;
  }

  .members__counts {
    width: 100%;
  }
}
</style>
