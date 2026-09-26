<script setup lang="ts">
import { computed, inject } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { MEMBERS_API_KEY } from '../api/members'
import { useMembers } from '../composables/useMembers'
import { COURSE_MEMBERS_ROUTE, COURSE_ROUTE, homeRouteFor, NOTICE_COURSE_FORBIDDEN, ROOT_ROUTE } from '../router'
import { useSessionStore } from '../stores/session'

const api = inject(MEMBERS_API_KEY, null)
if (api === null) throw new Error('MembersView 需要注入 MEMBERS_API_KEY')

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
</script>

<template>
  <section class="members" data-test="members" aria-labelledby="members-title">
    <h2 id="members-title">课程成员管理</h2>
    <p v-if="courseId">
      <RouterLink data-test="members-back" :to="{ name: COURSE_ROUTE, params: { cid: courseId } }">返回课程</RouterLink>
    </p>

    <section
      class="list"
      data-test="members-region"
      aria-labelledby="members-list-title"
      :aria-busy="status === 'loading'"
    >
      <h3 id="members-list-title">成员列表</h3>
      <p v-if="status === 'loading'" data-test="members-loading" role="status">正在加载成员…</p>
      <p v-else-if="status === 'forbidden'" data-test="members-forbidden" role="alert">{{ listError }}</p>
      <div v-else-if="status === 'error'">
        <p data-test="members-error" role="alert">{{ listError }}</p>
        <button type="button" data-test="members-retry" @click="loadMembers">重试</button>
      </div>
      <template v-else>
        <p v-if="isEmpty" data-test="members-empty">暂无学生成员。可在下方按用户名添加学生。</p>
        <p v-if="removeError" data-test="member-remove-error" role="alert">{{ removeError }}</p>
        <p v-if="removeNotice" data-test="member-remove-status" role="status">{{ removeNotice }}</p>
        <table v-if="members.length > 0" data-test="members-table">
          <caption>
            本课程成员（{{ members.length }} 人）；教师成员只能由管理员通过命令行调整
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
              <th scope="row">{{ row.username }}</th>
              <td>{{ row.roleLabel }}</td>
              <td><time :datetime="row.joinedAt">{{ row.joinedLabel }}</time></td>
              <td>
                <button
                  v-if="row.removable"
                  type="button"
                  data-test="member-remove"
                  :aria-label="`移除学生 ${row.username}`"
                  :disabled="removing.has(row.userId)"
                  :aria-busy="removing.has(row.userId)"
                  @click="removeMember(row)"
                >
                  {{ removing.has(row.userId) ? '移除中…' : '移除' }}
                </button>
                <span v-else class="muted">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </template>
    </section>

    <form
      v-if="status !== 'forbidden'"
      class="add"
      data-test="member-add"
      novalidate
      :aria-busy="adding"
      @submit.prevent="addMember"
    >
      <fieldset :disabled="adding">
        <legend>添加学生</legend>
        <label>
          学生用户名
          <input v-model="username" name="username" type="text" autocomplete="off" required />
        </label>
        <p v-if="addError" data-test="member-add-error" role="alert">{{ addError }}</p>
        <p v-if="addNotice" data-test="member-add-success" role="status">{{ addNotice }}</p>
        <button type="submit" :disabled="adding">{{ adding ? '添加中…' : '添加' }}</button>
      </fieldset>
    </form>
  </section>
</template>

<style scoped>
.members {
  display: grid;
  gap: 1.5rem;
}

table {
  width: 100%;
  border-collapse: collapse;
}

caption {
  text-align: left;
  font-size: 0.875rem;
  padding-bottom: 0.5rem;
}

th,
td {
  text-align: left;
  padding: 0.375rem 0.5rem;
  border-bottom: 1px solid #d0d7de;
}

.muted {
  color: #57606a;
}

.add fieldset {
  display: grid;
  gap: 0.75rem;
  max-width: 28rem;
  border: none;
  padding: 0;
}

.add label {
  display: grid;
  gap: 0.25rem;
}
</style>
