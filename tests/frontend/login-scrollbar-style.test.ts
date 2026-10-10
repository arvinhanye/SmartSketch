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
const uiCss = readFileSync(resolve(here, '../../src/frontend/src/styles/ui.css'), 'utf8')
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

// 全站复查（审计）发现的同类问题：页面只比窗口高几个像素，于是出现一条几乎不动的整页滚动条。
// 原因是冗余的底部空白，不是内容真的放不下。数值在浏览器里按页面×窗口尺寸实测过，这里只守住不被改回去。
describe('不让页面「刚好多出几个像素」', () => {
  it('共用页面容器底部内边距不超过 40px（原 64px，外层 .app-main 还有 24px）', () => {
    const rule = /\.light-surface \.ui-sheet__inner \{[^}]*padding:\s*40px 44px (\d+)px/.exec(uiCss)
    expect(rule).not.toBeNull()
    expect(Number(rule![1])).toBeLessThanOrEqual(40)
  })
  it('模型设置页的紧凑排版覆盖到 930px 高（原 850px，850–920px 之间宽松排版会多出 21px）', () => {
    const m = /@media\(min-width:1051px\) and \(max-height:(\d+)px\) \{\s*\.light-surface\.model-settings \.ui-sheet__inner/.exec(uiCss)
    expect(m).not.toBeNull()
    expect(Number(m![1])).toBeGreaterThanOrEqual(930)
  })
  it('教师图谱画布顶栏放不下时换行，键盘选择器不再被画布裁到边缘之外', () => {
    // 最后一段覆盖规则生效：之前是 flex-wrap: nowrap + 选择器固定 260px，画布窄于约 770px 时选择器被推出画布。
    const bar = [...uiCss.matchAll(/\.teacher-graph__canvas-bar \{([^}]*)\}/g)].map((m) => m[1]).filter((b) => b.includes('flex-wrap')).pop() ?? ''
    expect(bar).toContain('flex-wrap: wrap')
    const picker = [...uiCss.matchAll(/\.teacher-graph__canvas-bar \.teacher-graph__picker \{([^}]*)\}/g)].map((m) => m[1]).filter((b) => b.includes('flex:')).pop() ?? ''
    expect(picker).toMatch(/flex:\s*0 1 260px/)
    expect(picker).toMatch(/min-width:\s*160px/)
  })
})

