<script setup lang="ts">
import { inject, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { AUTH_API_KEY } from '../api/auth'
import { ApiError, NetworkError, TimeoutError } from '../api/http'
import AuthLayout from '../components/AuthLayout.vue'
import { homeRouteFor, REGISTER_ROUTE } from '../router'
import { useSessionStore } from '../stores/session'

const auth = inject(AUTH_API_KEY, null)
if (auth === null) throw new Error('LoginView 需要注入 AUTH_API_KEY')

const session = useSessionStore()
const router = useRouter()
// 注册页由 main.ts 注入；未注入时（如单测只建最小路由）不显示入口
const canRegister = router.hasRoute(REGISTER_ROUTE)

const username = ref('')
const password = ref('')
const pending = ref(false)
const error = ref<string | null>(null)

// 只按状态码与错误类型给出固定文案，不回显服务端 message，也不记录口令或令牌
function messageFor(cause: unknown): string {
  if (cause instanceof ApiError) {
    if (cause.status === 401) return '用户名或密码错误，请重新输入。'
    if (cause.status === 429) {
      return cause.retryAfterSeconds !== undefined
        ? `登录尝试过于频繁，请 ${cause.retryAfterSeconds} 秒后再试。`
        : '登录尝试过于频繁，请稍后再试。'
    }
    if (cause.status === 422) return '请输入用户名和密码。'
  }
  if (cause instanceof NetworkError || cause instanceof TimeoutError) return '无法连接服务器，请检查网络后重试。'
  return '登录失败，请稍后重试。'
}

async function submit(): Promise<void> {
  if (pending.value) return
  if (username.value.trim() === '' || password.value === '') {
    error.value = '请输入用户名和密码。'
    return
  }
  pending.value = true
  error.value = null
  try {
    const response = await auth!.login({ username: username.value, password: password.value })
    password.value = ''
    session.signIn(response)
    await router.replace({ name: homeRouteFor(response.user.role) })
  } catch (cause) {
    password.value = ''
    error.value = messageFor(cause)
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <AuthLayout>
    <form class="login" novalidate :aria-busy="pending" @submit.prevent="submit">
      <fieldset :disabled="pending">
        <legend>登录智绘学途</legend>
        <label>
          用户名
          <input v-model="username" name="username" type="text" autocomplete="username" required />
        </label>
        <label>
          密码
          <input v-model="password" name="password" type="password" autocomplete="current-password" required />
        </label>
        <p v-if="error" data-test="login-error" role="alert">{{ error }}</p>
        <button type="submit" class="login__submit" :disabled="pending">{{ pending ? '登录中…' : '登录' }}</button>
        <p class="login__hint">
          <template v-if="canRegister">
            还没有账号？<RouterLink :to="{ name: REGISTER_ROUTE }" data-test="login-register-link">注册学生账号</RouterLink>。
          </template>
          教师账号由管理员开通。
        </p>
      </fieldset>
    </form>
  </AuthLayout>
</template>

<style scoped>
.login fieldset {
  display: grid;
  gap: 0.9rem;
  border: none;
  padding: 0;
  background: none;
}
.login legend {
  font-size: 1.4rem;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 0.5rem;
  padding: 0;
}
.login label {
  display: grid;
  gap: 0.3rem;
}
.login__submit {
  justify-self: stretch;
  padding-block: 0.6rem;
}
.login__hint {
  color: var(--color-text-muted);
  font-size: 0.85rem;
  margin: 0;
}
</style>
