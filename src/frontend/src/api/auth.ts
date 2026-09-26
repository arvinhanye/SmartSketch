import type { InjectionKey } from 'vue'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import { createHttpClient, type HttpClient, type HttpClientOptions, type RequestControl } from './http'

/**
 * 登录接口与会话接线（H13）。
 *
 * - `login` 走契约 `POST /api/v1/auth/login`（`security: []`）：不带令牌，401 是凭据错误，不清会话。
 * - `createSessionHttpClient` 把会话接到 B15 客户端：每次请求读当前令牌放进 `Authorization`；
 *   受保护接口 401 时先清会话与课程上下文（`session.signOut()`），再通知调用方回登录页。
 * - 令牌只当不透明字符串使用，不解析 JWT（`specs/identity-access.md` §2.4）。
 */

export type LoginRequest = components['schemas']['LoginRequest']
export type LoginResponse = components['schemas']['LoginResponse']

export interface AuthApi {
  login(body: LoginRequest, control?: RequestControl): Promise<LoginResponse>
}

/** 视图经 inject 取得登录接口，测试可注入假实现 */
export const AUTH_API_KEY: InjectionKey<AuthApi> = Symbol('smartsketch.auth-api')

export function createAuthApi(client: HttpClient): AuthApi {
  return {
    login: (body, control = {}) => client.request('post', '/api/v1/auth/login', { ...control, body }),
  }
}

/** HTTP 客户端需要的会话能力：当前令牌与清会话 */
export interface SessionCredentials {
  readonly accessToken: string | null
  signOut(): void
}

export function createSessionHttpClient(
  session: SessionCredentials,
  onExpired: () => void,
  options: Omit<HttpClientOptions, 'getAccessToken' | 'onUnauthenticated'> = {},
): HttpClient {
  return createHttpClient({
    ...options,
    getAccessToken: () => session.accessToken,
    onUnauthenticated: () => {
      session.signOut()
      onExpired()
    },
  })
}
