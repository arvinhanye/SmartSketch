import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

// 软件首页（登录页）不应出现突兀的上下滚动条。
// 第一层：表单栏去掉原来上下各 96px 的内边距，约 650px 高的窗口就放得下（已在浏览器里按 1440×780、
// 1280×720、1100×650 实测无滚动容器）。第二层：更矮的窗口仍可滚动（不藏提交按钮），但不显示滚动条。
const here = dirname(fileURLToPath(import.meta.url))
const css = readFileSync(resolve(here, '../../src/frontend/src/styles.css'), 'utf8')
const layout = readFileSync(resolve(here, '../../src/frontend/src/components/LoginLayout.vue'), 'utf8')
const start = css.indexOf('.app.app--login .auth-layout__form {')
const block = start >= 0 ? css.slice(start, css.indexOf('}', start) + 1) : ''

describe('登录页表单栏的滚动条', () => {
  it('更矮的窗口里仍可内部滚动（不能让提交按钮被隐藏）', () => {
    expect(block).toContain('overflow-y: auto')
  })
  it('不显示滚动条本身（两套写法覆盖 Firefox 与 Chromium/WebKit）', () => {
    expect(block).toContain('scrollbar-width: none')
    expect(css).toMatch(/\.app\.app--login \.auth-layout__form::-webkit-scrollbar\s*\{\s*display: none;/)
  })
  it('表单栏不再占用上下各 96px 的内边距', () => {
    const form = layout.slice(layout.indexOf('.auth-layout__form {'), layout.indexOf('}', layout.indexOf('.auth-layout__form {')))
    expect(form).toMatch(/padding:\s*8px 0/)
    expect(layout).not.toMatch(/padding(-top)?:\s*96px/)
  })
})
