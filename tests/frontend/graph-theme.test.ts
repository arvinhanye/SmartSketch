import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { GRAPH_FONT, GRAPH_COLORS, NODE_TYPE_FILL, NODE_TYPE_GLYPH } from '../../src/frontend/src/graph/theme'

const tokensCss = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../../src/frontend/src/styles/tokens.css'),
  'utf8',
)

/** WCAG 2.x 相对亮度与对比度 */
function luminance(hex: string): number {
  const channel = (i: number) => {
    const v = Number.parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16) / 255
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * channel(0) + 0.7152 * channel(1) + 0.0722 * channel(2)
}
function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number]
  return (hi + 0.05) / (lo + 0.05)
}

/** 读出 tokens.css 里某个前缀的全部十六进制变量 */
function cssVars(prefix: '--gw-' | '--ss-'): Map<string, string> {
  const out = new Map<string, string>()
  for (const m of tokensCss.matchAll(new RegExp(`${prefix}([a-z0-9-]+):\\s*(#[0-9a-fA-F]{6})`, 'g'))) {
    out.set(m[1]!, m[2]!.toLowerCase())
  }
  return out
}

describe('图谱主题：CSS tokens 与画布字面量一致', () => {
  it('--gw-* 与 GRAPH_COLORS 数值一一对应（G6 读不到 CSS 变量，两处必须同步）', () => {
    const gw = cssVars('--gw-')
    const pairs: Array<[string, string]> = [
      ['canvas', GRAPH_COLORS.canvas],
      ['panel', GRAPH_COLORS.panel],
      ['hover', GRAPH_COLORS.hover],
      ['line', GRAPH_COLORS.line],
      ['edge', GRAPH_COLORS.controlEdge],
      ['text', GRAPH_COLORS.text],
      ['text-2', GRAPH_COLORS.text2],
      ['text-3', GRAPH_COLORS.text3],
      ['accent', GRAPH_COLORS.accent],
      ['selected', GRAPH_COLORS.accentSoft],
      ['ok', GRAPH_COLORS.ok],
      ['warn', GRAPH_COLORS.warn],
      ['danger', GRAPH_COLORS.danger],
    ]
    for (const [name, literal] of pairs) expect(gw.get(name), `--gw-${name}`).toBe(literal.toLowerCase())
  })

  it('不改现有 --color-*：tokens.css 只定义 --ss-* 与 --gw-*', () => {
    // 先去掉注释：注释里会解释「不改 --color-*」
    const code = tokensCss.replace(/\/\*[\s\S]*?\*\//g, '')
    expect(code).not.toMatch(/--color-/)
    expect(code).toMatch(/--ss-bg:/)
    expect(code).toMatch(/\.graph-workspace\s*\{/)
  })
})

describe('图谱主题：对比度（规格 3.5）', () => {
  const light = GRAPH_COLORS
  it('浅色文字对 ≥ 4.5:1', () => {
    expect(contrast(light.text, light.canvas)).toBeGreaterThanOrEqual(4.5)
    expect(contrast(light.text2, light.panel)).toBeGreaterThanOrEqual(4.5)
    expect(contrast(light.text3, light.panel)).toBeGreaterThanOrEqual(4.5)
    expect(contrast(light.text3, light.hover)).toBeGreaterThanOrEqual(4.5)
    expect(contrast(light.accent, light.panel)).toBeGreaterThanOrEqual(4.5)
    expect(contrast(light.accent, light.accentSoft)).toBeGreaterThanOrEqual(4.5)
    expect(contrast('#FFFFFF', '#5B5BD6')).toBeGreaterThanOrEqual(4.5)
    expect(contrast(light.ok, '#EAF6EE')).toBeGreaterThanOrEqual(4.5)
    expect(contrast(light.warn, '#FDF4E3')).toBeGreaterThanOrEqual(4.5)
    expect(contrast(light.danger, '#FDECEC')).toBeGreaterThanOrEqual(4.5)
  })

  it('控件边界与持久状态的图形（节点边框、各类关系线、先修线）≥ 3:1', () => {
    expect(contrast(light.controlEdge, light.panel)).toBeGreaterThanOrEqual(3)
    expect(contrast(light.nodeStroke, light.canvas)).toBeGreaterThanOrEqual(3)
    expect(contrast(light.dimmedStroke, light.canvas)).toBeGreaterThanOrEqual(3)
    expect(contrast('#727A89', light.canvas)).toBeGreaterThanOrEqual(3) // CONTAINS
    expect(contrast(light.accent, light.canvas)).toBeGreaterThanOrEqual(3) // PREREQUISITE
    expect(contrast('#4C7480', light.canvas)).toBeGreaterThanOrEqual(3) // RELATED_TO
    expect(contrast('#906638', light.canvas)).toBeGreaterThanOrEqual(3) // EXAMPLE_OF
  })

  it('强淡化是有意例外：只允许用在悬停这种瞬时状态，数值低于 3:1', () => {
    expect(contrast(GRAPH_COLORS.fadedStroke, light.canvas)).toBeLessThan(3)
    expect(contrast(GRAPH_COLORS.fadedEdge, light.canvas)).toBeLessThan(3)
  })

  it('暗色外壳文字与控件边界达标', () => {
    const ss = cssVars('--ss-')
    expect(contrast(ss.get('text')!, ss.get('panel')!)).toBeGreaterThanOrEqual(4.5)
    expect(contrast(ss.get('text-2')!, ss.get('panel')!)).toBeGreaterThanOrEqual(4.5)
    expect(contrast(ss.get('text-3')!, ss.get('hover')!)).toBeGreaterThanOrEqual(4.5)
    expect(contrast(ss.get('link')!, ss.get('selected')!)).toBeGreaterThanOrEqual(4.5)
    expect(contrast('#FFFFFF', ss.get('primary-hover')!)).toBeGreaterThanOrEqual(4.5)
    expect(contrast(ss.get('edge')!, ss.get('panel')!)).toBeGreaterThanOrEqual(3)
    // 装饰分隔线不承担识别功能：允许低于 3:1，但不能被当作控件边界使用
    expect(contrast(ss.get('line')!, ss.get('panel')!)).toBeLessThan(3)
  })
})

describe('节点类型标记', () => {
  it('五种类型都有填充色与单字标记，且单字互不相同（颜色之外仍可辨认）', () => {
    expect(Object.keys(NODE_TYPE_FILL).sort()).toEqual(['concept', 'example', 'formula', 'method', 'theorem'])
    expect(Object.keys(NODE_TYPE_GLYPH).sort()).toEqual(['concept', 'example', 'formula', 'method', 'theorem'])
    expect(new Set(Object.values(NODE_TYPE_GLYPH)).size).toBe(5)
    for (const glyph of Object.values(NODE_TYPE_GLYPH)) expect(glyph).toHaveLength(1)
  })

  it('类型填充与画布几乎同色（1.1–1.3），这正是类型标记必须带单字的原因', () => {
    for (const fill of Object.values(NODE_TYPE_FILL)) {
      expect(contrast(fill, GRAPH_COLORS.canvas)).toBeLessThan(1.3)
      expect(contrast(GRAPH_COLORS.text, fill)).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('对象被冻结，运行期不可被改写', () => {
    expect(Object.isFrozen(GRAPH_COLORS)).toBe(true)
    expect(Object.isFrozen(NODE_TYPE_FILL)).toBe(true)
    expect(Object.isFrozen(NODE_TYPE_GLYPH)).toBe(true)
  })
})

describe('字体', () => {
  it('图谱字体栈以中文无衬线优先，并带系统回退', () => {
    expect(GRAPH_FONT).toMatch(/PingFang SC/)
    expect(GRAPH_FONT).toMatch(/system-ui/)
  })
})
