<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { AUTH_API_KEY } from '../api/auth'
import { ApiError, NetworkError, TimeoutError } from '../api/http'
import LoginLayout from '../components/LoginLayout.vue'
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
const showPassword = ref(false)

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
  <LoginLayout>
    <form class="register" novalidate :aria-busy="pending" aria-label="注册智绘学途学生账号" data-test="register-form" @submit.prevent="submit">
      <p class="register__eyebrow">加入智绘学途</p>
      <h2>注册学生账号</h2>
      <fieldset :disabled="pending">
        <legend class="register__sr-only">注册学生账号</legend>
        <div class="register__field">
          <label for="register-username">用户名</label>
          <input
            id="register-username"
            v-model="username"
            name="username"
            type="text"
            placeholder="3–32 位字母、数字、下划线、点或横线"
            autocomplete="username"
            required
            :aria-invalid="usernameError !== null"
            :aria-describedby="usernameError ? 'register-username-help' : undefined"
          />
          <p v-if="usernameError" id="register-username-help" class="register__field-error" data-test="register-username-error">
            {{ usernameError }}
          </p>
        </div>
        <div class="register__field">
          <label for="register-password">口令</label>
          <div class="register__password">
            <input
              id="register-password"
              v-model="password"
              name="password"
              :type="showPassword ? 'text' : 'password'"
              placeholder="至少 8 位"
              autocomplete="new-password"
              required
              :aria-invalid="passwordError !== null"
            />
            <button
              type="button"
              class="register__eye"
              :aria-label="showPassword ? '隐藏口令' : '显示口令'"
              :aria-pressed="showPassword"
              aria-controls="register-password register-confirm"
              @click="showPassword = !showPassword"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /><path v-if="showPassword" d="m3 3 18 18" /></svg>
            </button>
          </div>
          <p v-if="passwordError" class="register__field-error" data-test="register-password-error">{{ passwordError }}</p>
        </div>
        <div class="register__field">
          <label for="register-confirm">确认口令</label>
          <input
            id="register-confirm"
            v-model="confirm"
            name="confirm"
            :type="showPassword ? 'text' : 'password'"
            placeholder="再输入一次口令"
            autocomplete="new-password"
            required
            :aria-invalid="confirmError !== null"
          />
          <p v-if="confirmError" class="register__field-error" data-test="register-confirm-error">{{ confirmError }}</p>
        </div>
        <p v-if="error" class="register__error" data-test="register-error" role="alert">{{ error }}</p>
        <button type="submit" class="register__submit" :disabled="pending">
          {{ pending ? '注册中…' : '注册并登录' }}
          <svg v-if="!pending" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M5 12h14m-5-5 5 5-5 5" /></svg>
        </button>
      </fieldset>
      <p class="register__login">已有账号？<RouterLink :to="{ name: ROOT_ROUTE }">去登录</RouterLink></p>
      <p class="register__hint">老师会按用户名把你加入课程；教师账号由管理员开通。</p>
    </form>
  </LoginLayout>
</template>

<style scoped>
/* 版式与登录页（LoginView）一致，保持两页观感统一。 */
.register { position: relative; width: 100%; color: var(--ss-text); }
.register__eyebrow { color: var(--ss-link); font-size: 12px; letter-spacing: 1px; margin: 0 0 13px; }
.register h2 { font-size: 29px; font-weight: 600; margin: 0 0 24px; color: var(--ss-text); line-height: 1.4; }
.register fieldset { display: block; min-width: 0; margin: 0; padding: 0; border: 0; background: none; }
.register__sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
.register .register__field { display: block; margin: 0 0 16px; }
.register label { display: block; color: #d4d6df; font-size: 13px; line-height: 1.5; }
.register input {
  display: block;
  margin-top: 8px;
  width: 100%;
  height: 44px;
  border: 1px solid #777c8c;
  border-radius: 8px;
  background: var(--ss-panel);
  color: var(--ss-text);
  padding: 0 14px;
  font: inherit;
  font-size: 14px;
}
.register input::placeholder { color: #9da2b2; font-size: 13px; }
.register input[aria-invalid='true'] { border-color: #b4616f; }
.register__password { position: relative; }
.register__password input { padding-right: 44px; }
.register .register__eye {
  position: absolute;
  top: 3px;
  right: 3px;
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  min-height: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: #aeb2bf;
  border-radius: 6px;
  cursor: pointer;
}
.register__eye svg { width: 19px; height: 19px; }
.register .register__eye:hover:not(:disabled) { background: #242631; }
.register .register__submit {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  width: 100%;
  height: 46px;
  margin-top: 4px;
  padding: 0;
  border-radius: 8px;
  background: var(--ss-primary);
  border: 1px solid var(--ss-primary);
  color: white;
  font: inherit;
  font-size: 14px;
  font-weight: 500;
}
.register__submit svg { width: 18px; height: 18px; }
.register__field-error { color: #f2a7b1; font-size: 12px; line-height: 1.7; margin: 8px 0 0; }
.register__error {
  color: #f2a7b1;
  background: #32202a;
  border: 1px solid #794a57;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 13px;
  line-height: 1.7;
  margin: 0 0 16px;
}
.register__login { border-top: 1px solid var(--ss-line); margin: 22px 0 0; padding-top: 18px; color: #aeb2bf; font-size: 13px; line-height: 1.8; }
.register__login a { margin-left: 7px; color: var(--ss-link); }
.register__hint { color: #9da2b2; font-size: 12px; line-height: 1.7; margin: 8px 0 0; }
.register :is(input, button, a):focus-visible { outline: 2px solid var(--ss-link); outline-offset: 3px; }
.register button:disabled { opacity: 0.65; cursor: wait; }
@media (max-width: 760px) {
  .register h2 { font-size: 25px; }
}
</style>
