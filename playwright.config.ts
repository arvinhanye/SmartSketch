import { defineConfig } from '@playwright/test'

// K05/K06 端到端。推荐经 scripts/e2e.sh 运行：它用演示模型启动真实 API、worker 与 Vite，
// 并设置 E2E_BASE_URL、账号口令与输出目录。
// 浏览器版本与 @playwright/test 不匹配（如离线环境预装的 Chromium）时，
// 用 PLAYWRIGHT_CHROMIUM_EXECUTABLE 指定可执行文件。
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 240_000,
  expect: { timeout: 20_000 },
  outputDir: process.env.E2E_OUTPUT_DIR ?? 'test-results',
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173',
    viewport: { width: 1400, height: 900 },
    // 失败时保留证据（K05 验收：保留失败证据）
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    launchOptions: executablePath ? { executablePath } : {},
  },
})
