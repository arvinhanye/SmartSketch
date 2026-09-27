<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { AUTH_API_KEY } from '../api/auth'
import { ApiError, NetworkError, TimeoutError } from '../api/http'
import AuthLayout from '../components/AuthLayout.vue'
import { homeRouteFor, ROOT_ROUTE } from '../router'
import { useSessionStore } from '../stores/session'

/**
 * 学生自助注册页（ADR-079）。只建学生账号；教师账号由管理员用命令行开通。
 * 字段规则与后端 `RegisterRequest` 一致，先在本地校验，服务端 422 时按字段回显固定文案。
 * 成功即登录并进入学生首页；口令不回显、不记录。
 */
const auth = inject(AUTH_API_KEY, null)
if (auth === null) throw new Error('RegisterView 需要注入 AUTH_API_KEY')

const session = useSessionStore()
const router = useRouter()

const USERNAME_RULE = /^[A-Za-z0-9_.-]{3,32}$/
const PASSWORD_MIN = 8
const PASSWORD_MAX = 128

const username = ref('')
const password = ref('')
const confirm = ref('')
const pending = ref(false)
const submitted = ref(false)
const usernameTaken = ref<string | null>(null)
const error = ref<string | null>(null)

const usernameError = computed(() => {
  const value = username.value.trim()
  if (usernameTaken.value !== null && usernameTaken.value === value.toLowerCase()) return '用户名已被占用，请换一个。'
  if (!submitted.value) return null
  if (value === '') return '请输入用户名。'
  if (!USERNAME_RULE.test(value)) return '用户名为 3–32 位字母、数字、下划线、点或横线。'
  return null
})
const passwordError = computed(() => {
  if (!submitted.value) return null
  const length = password.value.length
  if (length < PASSWORD_MIN || length > PASSWORD_MAX) return `口令长度为 ${PASSWORD_MIN}–${PASSWORD_MAX} 个字符。`
  return null
})
const confirmError = computed(() => {
  if (!submitted.value || passwordError.value !== null) return null
  return confirm.value === password.value ? null : '两次输入的口令不一致。'
})

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError) {
    if (cause.status === 429) {
      return cause.retryAfterSeconds !== undefined
        ? `注册请求过多，请 ${cause.retryAfterSeconds} 秒后再试。`
        : '注册请求过多，请稍后再试。'
    }
    if (cause.status === 422) return '填写的内容不符合要求，请检查用户名和口令。'
  }
  if (cause instanceof NetworkError || cause instanceof TimeoutError) return '无法连接服务器，请检查网络后重试。'
  return '注册失败，请稍后重试。'
}

async function submit(): Promise<void> {
  if (pending.value) return
  submitted.value = true
  error.value = null
  if (usernameError.value !== null || passwordError.value !== null || confirmError.value !== null) return
  const name = username.value.trim()
  pending.value = true
  try {
    const response = await auth!.register({ username: name, password: password.value })
    password.value = ''
    confirm.value = ''
    session.signIn(response)
    await router.replace({ name: homeRouteFor(response.user.role) })
  } catch (cause) {
    if (cause instanceof ApiError && cause.code === 'USERNAME_TAKEN') {
      usernameTaken.value = name.toLowerCase()
    } else {
      error.value = messageFor(cause)
    }
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <AuthLayout>
    <form class="register" novalidate :aria-busy="pending" data-test="register-form" @submit.prevent="submit">
      <fieldset :disabled="pending">
        <legend>注册学生账号</legend>
        <label>
          用户名
          <input
            v-model="username"
            name="username"
            type="text"
            autocomplete="username"
            required
            :aria-invalid="usernameError !== null"
            aria-describedby="register-username-help"
          />
        </label>
        <p v-if="usernameError" id="register-username-help" class="register__field-error" data-test="register-username-error">
          {{ usernameError }}
        </p>
        <p v-else id="register-username-help" class="register__help">
          3–32 位字母、数字、下划线、点或横线。老师会按用户名把你加入课程。
        </p>
        <label>
          口令
          <input
            v-model="password"
            name="password"
            type="password"
            autocomplete="new-password"
            required
            :aria-invalid="passwordError !== null"
          />
        </label>
        <p v-if="passwordError" class="register__field-error" data-test="register-password-error">{{ passwordError }}</p>
        <label>
          确认口令
          <input
            v-model="confirm"
            name="confirm"
            type="password"
            autocomplete="new-password"
            required
            :aria-invalid="confirmError !== null"
          />
        </label>
        <p v-if="confirmError" class="register__field-error" data-test="register-confirm-error">{{ confirmError }}</p>
        <p v-if="error" data-test="register-error" role="alert">{{ error }}</p>
        <button type="submit" class="register__submit" :disabled="pending">{{ pending ? '注册中…' : '注册并登录' }}</button>
        <p class="register__help">
          已有账号？<RouterLink :to="{ name: ROOT_ROUTE }">去登录</RouterLink>。教师账号由管理员开通。
        </p>
      </fieldset>
    </form>
  </AuthLayout>
</template>

<style scoped>
.register fieldset {
  display: grid;
  gap: 0.75rem;
  border: none;
  padding: 0;
  background: none;
}
.register legend {
  font-size: 1.4rem;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 0.5rem;
  padding: 0;
}
.register label {
  display: grid;
  gap: 0.3rem;
}
.register__help {
  color: var(--color-text-muted);
  font-size: 0.82rem;
  margin: -0.4rem 0 0;
}
.register__field-error {
  color: var(--color-danger-text);
  font-size: 0.82rem;
  margin: -0.4rem 0 0;
}
.register__submit {
  justify-self: stretch;
  padding-block: 0.6rem;
}
</style>
