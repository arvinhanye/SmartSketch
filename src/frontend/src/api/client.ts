import type { InjectionKey } from 'vue'
import type { HttpClient } from './http'

/**
 * 通用 HTTP 客户端注入键（H01，按 H13 交接建议新增）。
 *
 * `main.ts` 把接好会话的同一个客户端（`createSessionHttpClient`）经此键提供，
 * 各功能 API 都从它构造，受保护接口 401 才会统一清会话并回登录页。
 */
export const HTTP_CLIENT_KEY: InjectionKey<HttpClient> = Symbol('smartsketch.http-client')
