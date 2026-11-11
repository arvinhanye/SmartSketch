<script setup lang="ts">
import { inject, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { AUTH_API_KEY } from '../api/auth'
import { ApiError, NetworkError, TimeoutError } from '../api/http'
import LoginLayout from '../components/LoginLayout.vue'
import { homeRouteFor, REGISTER_ROUTE } from '../router'
import { useSessionStore } from '../stores/session'

const props = withDefaults(defineProps<{ loginNotice?: string | null }>(), { loginNotice: null })
const emit = defineEmits<{ 'dismiss-login-notice': [] }>()

const auth = inject(AUTH_API_KEY, null)
if (auth === null) throw new Error('LoginView 需要注入 AUTH_API_KEY')

const session = useSessionStore()
const router = useRouter()
// 注册页由 main.ts 注入；未注入时（如单测只建最小路由）不显示入口
const canRegister = router.hasRoute(REGISTER_ROUTE)

const username = ref('')
const password = ref('')
const showPassword = ref(false)
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
  showPassword.value = false
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
  <LoginLayout>
    <form class="login" novalidate :aria-busy="pending" aria-label="登录智绘学途" @submit.prevent="submit">
      <div v-if="props.loginNotice" class="login__notice" role="alert" data-test="login-notice">
        <span>{{ props.loginNotice }}</span>
        <button type="button" aria-label="关闭提示" @click="emit('dismiss-login-notice')">×</button>
      </div>
      <h2 class="login__sr-only">登录</h2>
      <fieldset :disabled="pending">
        <legend class="login__sr-only">登录智绘学途</legend>
        <label class="login__field">
          用户名
          <input v-model="username" name="username" type="text" placeholder="请输入用户名" autocomplete="username" required />
        </label>
        <div class="login__field">
          <label for="login-password">密码</label>
          <div class="login__password">
            <input id="login-password" v-model="password" name="password" :type="showPassword ? 'text' : 'password'" placeholder="请输入密码" autocomplete="current-password" required />
            <button type="button" class="login__eye" :aria-label="showPassword ? '隐藏密码' : '显示密码'" :aria-pressed="showPassword" aria-controls="login-password" @click="showPassword = !showPassword">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/><path v-if="showPassword" d="m3 3 18 18" /></svg>
            </button>
          </div>
        </div>
        <p v-if="error" class="login__error" data-test="login-error" role="alert">{{ error }}</p>
        <div class="login__actions">
          <p class="login__hint">教师账号由管理员开通</p>
          <button type="submit" class="login__submit" :disabled="pending">{{ pending ? '登录中…' : '登录' }}</button>
        </div>
      </fieldset>
      <p v-if="canRegister" class="login__register">还没有账号？<RouterLink :to="{ name: REGISTER_ROUTE }" data-test="login-register-link">注册学生账号</RouterLink></p>
    </form>
  </LoginLayout>
</template>
<style scoped>
.login {
  position: relative;
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  width: 100%;
  color: var(--ui-text);
}
.login fieldset {
  display: block;
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
  background: none;
}
.login__sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
.login .login__field {
  display: block;
  margin: 0 0 24px;
}
.login label {
  display: block;
  color: var(--ui-text-2);
  font-size: 13px;
  line-height: 1.5;
}
.login input {
  display: block;
  margin-top: 4px;
  width: 100%;
  height: 44px;
  border: 0;
  border-bottom: 1.5px solid var(--ui-line);
  border-radius: 0;
  background: transparent;
  color: var(--ui-text);
  padding: 0 2px;
  font: inherit;
  font-size: 16px;
}
.login input:focus { border-bottom-color: var(--ui-primary); outline: none; }
.login input::placeholder {
  color: var(--ui-text-3);
  font-size: 14px;
}
.login__password {
  position: relative;
}
.login__password input {
  padding-right: 46px;
}
.login .login__eye {
  position: absolute;
  top: 0;
  right: 0;
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  min-height: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--ui-text-2);
  border-radius: 8px;
  cursor: pointer;
}
.login__eye svg {
  width: 19px;
  height: 19px;
}
.login .login__eye:hover:not(:disabled) {
  background: var(--ui-surface-2);
}
.login__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 4px;
}
.login .login__submit {
  flex: none;
  min-width: 112px;
  height: 44px;
  padding: 0 28px;
  border-radius: 22px;
  background: var(--ui-primary);
  border: 1px solid var(--ui-primary);
  color: #fff;
  font: inherit;
  font-size: 14px;
  font-weight: 500;
  box-shadow: 0 6px 14px rgb(14 107 92 / 28%);
  cursor: pointer;
}
.login .login__submit:hover:not(:disabled) { background: var(--ui-primary-press); border-color: var(--ui-primary-press); }
.login__register {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-top: 1px solid var(--ui-line-soft);
  margin: 32px 0 0;
  padding-top: 18px;
  color: var(--ui-text-2);
  font-size: 13px;
  line-height: 1.8;
}
.login__register a {
  display: inline-flex;
  align-items: center;
  min-height: 36px;
  padding: 0 16px;
  border-radius: 18px;
  border: 1px solid var(--ui-highlight);
  background: var(--ui-highlight-soft);
  color: var(--ui-text);
  text-decoration: none;
}
.login__hint {
  margin: 0;
  color: var(--ui-text-3);
  font-size: 12px;
  line-height: 1.6;
}
.login__error {
  color: #8f2323;
  background: #fdecec;
  border: 1px solid #f0b4b4;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 13px;
  line-height: 1.7;
  margin: 0 0 16px;
}
.login :is(input, button, a):focus-visible {
  outline: 2px solid var(--ui-highlight);
  outline-offset: 3px;
}
.login button:disabled {
  opacity: .65;
  cursor: wait;
}
.login__notice {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  margin: 0 0 20px;
  border: 1px solid #f0b4b4;
  border-radius: 8px;
  padding: 6px 6px 6px 12px;
  background: #fdecec;
  color: #8f2323;
  font-size: 13px;
  line-height: 1.7;
}
.login__notice span { flex: 1; min-width: 0; }
.login .login__notice button {
  flex: none;
  width: 36px;
  height: 44px;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: inherit;
  font-size: 20px;
}
.login .login__notice button:hover { background: #f8dada; }
</style>
