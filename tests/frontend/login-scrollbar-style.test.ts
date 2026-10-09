import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

// 装包前修复：登录页在较矮的窗口里，表单栏内部滚动（有意保留，避免提交按钮被藏起来），
// 但原生的浅色宽滚动条在深色页面上很突兀；改为细的深色滚动条。真实呈现以浏览器核对为准。
const css = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../../src/frontend/src/styles.css'), 'utf8')
const start = css.indexOf('.app.app--login .auth-layout__form {')
const block = start >= 0 ? css.slice(start, css.indexOf('}', start) + 1) : ''

describe('登录页表单栏的滚动条', () => {
  it('仍然是表单栏内部滚动（不能让提交按钮被隐藏）', () => {
    expect(block).toContain('overflow-y: auto')
  })
  it('滚动条是细的、深色的，与深色页面协调', () => {
    expect(block).toContain('color-scheme: dark')
    expect(block).toContain('scrollbar-width: thin')
    expect(block).toMatch(/scrollbar-color:\s*[^;]+\s+transparent/)
  })
})
