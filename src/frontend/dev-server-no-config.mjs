/**
 * 本机沙箱环境下的 Vite 开发服务器启动器。
 *
 * 为什么需要它：Vite 在 Windows 上首次做 realpath 时会执行 `exec("net use")`
 * （见 node_modules/vite/dist/node/chunks/node.js 的 optimizeSafeRealPathSync，
 * 用来识别网络驱动器映射）。受限沙箱不允许进程用管道捕获子进程输出，该调用抛
 * `spawn EPERM` 并直接终止 vite 启动。`--configLoader runner` 也走不通，因为它绕开
 * 打包后 vite.config.ts 的依赖（picomatch）会以 CJS 形式被求值而报错。
 *
 * 本脚本用 `configFile: false` 把配置作为内联对象交给 Vite，于是既不需要打包配置
 * 文件、也不触发任何 exec，等价于 vite.config.ts 的 plugins + server.proxy。
 *
 * 用法：node dev-server-no-config.mjs [端口]
 */

import { createServer } from 'vite'
import vue from '@vitejs/plugin-vue'

const API_TARGET = process.env.SMARTSKETCH_API_TARGET ?? 'http://127.0.0.1:8000'
const port = Number(process.argv[2] ?? process.env.DEMO_WEB_PORT ?? 5173)

const proxy = {
  '/api': { target: API_TARGET, changeOrigin: false },
  '/health': { target: API_TARGET, changeOrigin: false },
}

const server = await createServer({
  configFile: false,
  root: import.meta.dirname,
  plugins: [vue()],
  server: { host: '127.0.0.1', port, strictPort: true, proxy },
})

await server.listen()
server.printUrls()
