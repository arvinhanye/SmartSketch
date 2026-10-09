import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

// UI-BATCH2-01：样式规则的回归保护（真实呈现由浏览器验收确认）。
const css = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../../src/frontend/src/styles/ui.css'), 'utf8')
const rule = (selector: string): string => {
  const start = css.indexOf(selector)
  expect(start, `缺少样式规则：${selector}`).toBeGreaterThanOrEqual(0)
  return css.slice(start, css.indexOf('}', start) + 1)
}

describe('教师图谱详情', () => {
  const detail = '.light-surface.ui-teacher-workspace .teacher-graph__panel .knowledge-detail'
  it('来源行是左对齐的整块文字，文件名与位置自然换行，不被 flex 居中挤成碎片', () => {
    const block = rule(`${detail} ol > li > button {`)
    expect(block).toContain('display: block')
    expect(block).toContain('text-align: left')
    expect(block).toContain('overflow-wrap: anywhere')
  })
  it('程序聚焦的标题不画整行焦点框（它不是可操作控件，框会盖住关闭按钮）', () => {
    expect(rule(`${detail} h2[tabindex='-1']:focus {`)).toContain('outline: none')
  })
})

describe('资料上传框', () => {
  it('原生文件输入视觉隐藏但仍在 DOM 里（键盘聚焦与自动化可用），中文按钮承担视觉', () => {
    const block = rule('.light-surface.materials .ui-upload-card .materials-file-zone input.materials-file-input {')
    expect(block).toContain('position: absolute')
    expect(block).toContain('clip-path: inset(50%)')
  })
  it('拖到框上时有清晰的高亮状态；键盘聚焦时中文按钮显示焦点环', () => {
    expect(rule('.materials-file-zone.is-dragging {')).toContain('border-style: solid')
    expect(rule('.light-surface.materials .materials-file-zone:has(.materials-file-input:focus-visible) .materials-pick {')).toContain('outline: 2px solid var(--gw-accent)')
  })
})
