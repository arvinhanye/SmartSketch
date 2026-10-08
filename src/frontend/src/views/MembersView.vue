<script setup lang="ts">
import PageSheet from '../components/PageSheet.vue'
import PageHeader from '../components/PageHeader.vue'
import AppIcon from '../components/AppIcon.vue'
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
  <PageSheet class="members ui-management" data-test="members" labelledby="members-title">
    <PageHeader id="members-title" title="课程成员" description="添加学生，管理本课程的学习成员。">
      <template #actions><RouterLink v-if="courseId" class="ui-btn" data-test="members-back" :to="{ name: COURSE_ROUTE, params: { cid: courseId } }"><AppIcon name="back" :size="16" />返回课程</RouterLink></template>
    </PageHeader>

    <form
      v-if="status !== 'forbidden'"
      class="add ui-add-member"
      data-test="member-add"
      novalidate
      :aria-busy="adding"
      @submit.prevent="addMember"
    >
      <fieldset :disabled="adding">
        <legend>添加学生</legend>
        <div class="members-add-fields">
          <label for="member-username">学生用户名<input id="member-username" v-model="username" name="username" type="text" autocomplete="off" placeholder="输入学生已注册的用户名" aria-describedby="member-username-hint" required /></label>
          <button type="submit" :disabled="adding"><AppIcon name="plus" :size="16" />{{ adding ? '添加中…' : '添加学生' }}</button>
        </div>
        <p id="member-username-hint" class="members-add-hint">使用学生注册时的用户名，将其加入当前课程。</p>
        <p v-if="addError" data-test="member-add-error" role="alert">{{ addError }}</p>
        <p v-if="addNotice" data-test="member-add-success" role="status">{{ addNotice }}</p>
      </fieldset>
    </form>

    <section
      class="list members-list-card"
      data-test="members-region"
      aria-labelledby="members-list-title"
      :aria-busy="status === 'loading'"
    >
      <div class="members-list-heading"><h3 id="members-list-title">成员列表</h3><span v-if="status === 'ready'" class="members-count">{{ members.length }} 人</span></div>
      <p v-if="status === 'loading'" data-test="members-loading" role="status">正在加载成员…</p>
      <p v-else-if="status === 'forbidden'" data-test="members-forbidden" role="alert">{{ listError }}</p>
      <div v-else-if="status === 'error'">
        <p data-test="members-error" role="alert">{{ listError }}</p>
        <button type="button" data-test="members-retry" @click="loadMembers">重试</button>
      </div>
      <template v-else>
        <p v-if="isEmpty" class="members-empty" data-test="members-empty"><AppIcon name="members" :size="28" />暂无学生成员。可在上方按用户名添加学生。</p>
        <p v-if="removeError" data-test="member-remove-error" role="alert">{{ removeError }}</p>
        <p v-if="removeNotice" data-test="member-remove-status" role="status">{{ removeNotice }}</p>
        <table class="ui-table ui-member-table" v-if="members.length > 0" data-test="members-table">
          <caption>
            本课程成员（{{ members.length }} 人）
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
              <th scope="row" data-label="用户名"><span class="members-user"><span class="members-avatar" :class="{ 'is-teacher': row.role === 'teacher' }" aria-hidden="true">{{ row.username.slice(0,1).toUpperCase() }}</span><span>{{ row.username }}</span></span></th>
              <td data-label="课程内身份"><span class="members-role" :class="{ 'is-teacher': row.role === 'teacher' }">{{ row.roleLabel }}</span></td>
              <td data-label="加入时间"><time :datetime="row.joinedAt">{{ row.joinedLabel }}</time></td>
              <td data-label="操作">
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
                <span v-else class="members-protected">由管理员维护</span>
              </td>
            </tr>
          </tbody>
        </table>
      </template>
    </section>


  </PageSheet>
</template>
