import { fileURLToPath } from 'node:url'
import type { Plugin } from 'vite'
import { configDefaults, defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config.ts'

const testsDir = fileURLToPath(new URL('../../tests/frontend/', import.meta.url))
const configFile = fileURLToPath(import.meta.url)

// tests/frontend 在前端包之外，向上找不到 src/frontend/node_modules；
// 把其中的裸模块导入改为从前端包内解析，测试与应用共用同一份依赖。
function resolveTestDepsFromFrontend(): Plugin {
  return {
    name: 'smartsketch:resolve-test-deps-from-frontend',
    enforce: 'pre',
    resolveId(source, importer, options) {
      if (!importer?.startsWith(testsDir) || /^[./]|^[a-z]+:/i.test(source)) return null
      return this.resolve(source, configFile, { ...options, skipSelf: true })
    },
  }
}

export default mergeConfig(
  viteConfig,
  defineConfig({
    plugins: [resolveTestDepsFromFrontend()],
    server: {
      fs: { allow: ['.', testsDir] },
    },
    test: {
      dir: testsDir,
      include: ['**/*.test.ts'],
      // 点开头的目录是临时或工具目录（如 b02 的探针目录），不属于正式用例
      exclude: [...configDefaults.exclude, '**/.*/**'],
      environment: 'jsdom',
      setupFiles: [`${testsDir}setup.ts`],
    },
  }),
)
