import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

/**
 * 本机开发与预览的反代目标（B01/K12）。
 *
 * 浏览器里的前端一律用同源相对路径 `/api/v1` 访问后端（`src/frontend/src/api/http.ts`），
 * 生产由 `src/frontend/nginx.conf` 反代；Vite dev server / preview 与后端不同源，用同一套路径在这里反代，
 * 否则 `npm run dev` 起来的页面永远拿不到接口（与容器内行为不一致）。
 * 目标可经 `SMARTSKETCH_API_TARGET` 覆盖（例如后端换了端口）。
 */
const API_TARGET = process.env.SMARTSKETCH_API_TARGET ?? 'http://127.0.0.1:8000'

// SSE（任务进度、问答）经此转发；http-proxy 默认不缓冲响应体，无需额外开关。
const proxy = {
  '/api': { target: API_TARGET, changeOrigin: false },
  '/health': { target: API_TARGET, changeOrigin: false },
}

export default defineConfig({
  plugins: [vue()],
  server: { proxy },
  // `npm run preview` 服务的是 `npm run build` 的产物：E2E 与截图验收用它，
  // 避免 dev server 按需编译带来的首屏等待与抖动。
  preview: { proxy },
})
