import { spawnSync } from 'node:child_process'
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import App from '../../src/frontend/src/App.vue'

const testsDir = dirname(fileURLToPath(import.meta.url))
const frontendDir = resolve(testsDir, '../../src/frontend')

// 用项目自己的 npm test 脚本在临时目录上再跑一次 Vitest，检验脚本与配置本身的退出码。
// 临时目录以点开头，vitest.config.ts 排除点目录，外层收集不会误跑探针。
function runVitestOn(files: Record<string, string>) {
  const dir = mkdtempSync(join(testsDir, '.b02-probe-'))
  probeDirs.push(dir)
  for (const [name, content] of Object.entries(files)) writeFileSync(join(dir, name), content)
  // 经 npm 启动时用它注入的 npm_execpath 由当前 node 执行，避免 Windows 上 npm 实为 npm.cmd 找不到。
  const npmCli = process.env.npm_execpath
  const [command, cliArgs] = npmCli ? [process.execPath, [npmCli]] : ['npm', []]
  const npmArgs = ['--prefix', frontendDir, 'run', 'test', '--', '--run', '--dir', dir]
  const result = spawnSync(command, [...cliArgs, ...npmArgs], {
    encoding: 'utf8',
    shell: !npmCli && process.platform === 'win32',
    env: { ...process.env, NO_COLOR: '1', FORCE_COLOR: '0' },
    timeout: 30_000,
  })
  return { status: result.status, output: `${result.stdout}${result.stderr}` }
}

const probeDirs: string[] = []
afterEach(() => {
  for (const dir of probeDirs.splice(0)) rmSync(dir, { recursive: true, force: true })
})

describe('B02 前端测试配置', () => {
  it('能从仓库外层 tests/frontend 挂载 src 中的 SFC', () => {
    const wrapper = mount(App)
    expect(wrapper.get('h1').text()).toBe('智绘学途')
  })

  describe('全局 setup', () => {
    it('挂载到 document.body 的组件在当前用例内可见', () => {
      mount(App, { attachTo: document.body })
      expect(document.body.textContent).toContain('智绘学途')
    })

    it('下一个用例开始前已被自动卸载', () => {
      expect(document.body.textContent).not.toContain('智绘学途')
    })
  })

  describe('npm test 的退出码', () => {
    it('断言失败时命令非 0，且失败原因是断言而不是模块解析', () => {
      const { status, output } = runVitestOn({
        'probe.test.ts': "import { expect, it } from 'vitest'\nit('probe', () => { expect(1).toBe(2) })\n",
      })
      expect(output).toContain('expected 1 to be 2')
      expect(status).not.toBe(0)
    })

    it('一个用例都没收集到时命令非 0', () => {
      const { status, output } = runVitestOn({})
      expect(output).toMatch(/No test files found/i)
      expect(status).not.toBe(0)
    })
  })
})
