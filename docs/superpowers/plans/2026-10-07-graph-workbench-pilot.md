# 图谱工作台试点（学生图谱页）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把已在隔离预览中验证的图谱工作台（Linear 式暗色外壳 + Kumu 式浅色画布、章节分区布局、语义缩放与标签避让、悬停/预览淡化、小地图、局部视图、图例筛选、章节聚焦、左面板）渐进落进生产的学生图谱页，业务流程与现有测试语义不变。

**Architecture:** 纯函数先行（主题、缩放下限、标签排布、适配视口、章节布局、聚焦状态各一个无 G6/Vue 依赖的模块，各自带单元测试）；`graph/lifecycle.ts` 通过**可选的 `enhance` / `positions` 开关**接入这些模块，不开启时行为与 H04 完全一致，因此既有 h03/h04/h05/i06/l13/l14 的行为断言只改"样式/状态名"相关的几处；页面层新增 composables（预览状态机、局部视图、布局）与小组件（图例、预览卡、章节菜单、局部视图条、左面板），`StudentGraphView` 只做组装并保留全部 `data-test` 钩子。

**Tech Stack:** Vue 3 + TypeScript + Vite、`@antv/g6` 5.1.1（`hull`、`minimap` 插件，`AntVDagreLayout`，不新增依赖）、Pinia、Vue Router、Vitest（jsdom）、Playwright（`tests/e2e`）。

**Spec:** `docs/superpowers/specs/2026-10-06-graph-workbench-design.md`（执行者先读它；隔离预览 `src/frontend/preview/` 是行为参考实现，交接 `docs/handoffs/claude-ui-graph-pilot-01.md` 记录了踩过的坑）。

## Global Constraints

- 前端：Vue 3 + TypeScript + Vite + AntV G6（仅 2D）；**不新增依赖、不引入 UI/图标库**；图标用手写内联 SVG 组件。
- 业务不变：学生掌握状态与「标记 → 推荐刷新」；**服务端确认前不显示成功**；推荐理由 `reason` 取自服务端；`not_covered` 与服务错误分开；来源可定位；关系类型仅 `CONTAINS`、`PREREQUISITE`、`RELATED_TO`、`EXAMPLE_OF` 且 `PREREQUISITE` 方向清楚；课程隔离。
- **接口与契约无变更**：所有新增交互（预览、局部视图、筛选、目录、小地图、章节聚焦）在前端本地完成；不改 `src/contracts/`、后端、数据库。
- 色彩：应用外壳 `--ss-*`、图谱工作区 `--gw-*`，放在新文件 `src/frontend/src/styles/tokens.css`，**不改现有 `--color-*`**；G6 字面量集中在 `graph/theme.ts`，与 tokens.css 数值由测试保证一致。
- 对比度：文字 ≥4.5:1、必要图形/控件边界 ≥3:1；以页面实际渲染色为准。悬停强淡化是唯一的对比度例外（瞬时状态，见规格 §3.4a）。
- **不使用整体 `opacity` 淡化**（悬停与预览都靠换色/换填充）、不删除关系、不统一缩小字体；不使用渐变、玻璃模糊、发光、循环背景动画（G6 `active` 边状态的 halo 必须显式关闭）。
- 点击语义：单击节点 = **预览**（高亮 + 预览卡，侧栏不变，不移动镜头）；再次单击同一节点或「查看详情」才打开详情；列表/推荐/关联知识/问答链接 `?kp=` 是显式选择，直接打开详情；搜索回车 = 预览。
- 淡化：**悬停用强淡化（瞬时），预览/选中用标准档（持久）**；只有被预览/选中的节点强制显示标签（用布尔值判断，不用累加分数阈值）。
- 动效：统一 easing `cubic-bezier(0.2, 0, 0, 1)`，只动画 `transform` 与 `opacity`，不用 `transition: all`；镜头动画 240ms；`prefers-reduced-motion: reduce` 下关闭位移/缩放/镜头动画。
- 可读缩放 `READABLE_ZOOM = 0.9`（原 0.7，新标签 13px，**待用户在真实实例上目测确认**）；`GraphToolbar` 保留给教师页，学生页不再用。
- 保留既有 `data-test` 钩子：`student-graph-page`、`sg-*`、`rc-*`、`graph-canvas`（含 `data-zoom`）等；推荐编号「1. 名称」是有意设计（L14），不是文本污染。
- 流程：先写失败测试再实现；不放宽既有断言（只在"样式/状态名随设计变化"处更新期望并写明原因）；**不 commit / push / 开 PR，除非用户明确指示**（计划里的 commit 步骤仅在用户授权后执行）；不碰账号、数据库、真实模型调用；不打印口令/令牌。
- 命令基线（`/Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-frontend-init-0d2af9`）：`npm --prefix src/frontend run type-check`、`npm --prefix src/frontend run test -- --run`、`npm --prefix src/frontend run build`、`./scripts/verify.sh`。预览阶段基线：type-check 0、38 个测试文件/934 用例通过、build 0、verify 0。

---

## File Structure

**新增（`src/frontend/src/`）**

| 文件 | 职责 |
| --- | --- |
| `styles/tokens.css` | `--ss-*`（暗色外壳）与 `.graph-workspace` 内 `--gw-*` 两套 tokens |
| `styles/graph-workspace.css` | 图谱工作区与外壳的组件样式（`.gw-*`、`.app-topbar`、`.app-rail`），取自预览 CSS |
| `graph/theme.ts` | G6 字面量（颜色、类型填充、类型单字、字体）与 tokens 对应 |
| `graph/scale.ts` | 语义缩放：标签放大系数、节点/线/箭头屏幕下限、`READABLE_ZOOM` |
| `graph/labelPlan.ts` | 标签贪心排布（纯函数，含障碍物） |
| `graph/fit.ts` | 把一组点适应进视口的缩放与平移计算 |
| `graph/chapterLayout.ts` | 章节分区 + 紧凑间距布局（纯函数，引擎可替换） |
| `graph/focusStates.ts` | 预览/选中/章节聚焦/悬停的元素状态计算 |
| `graph/presentation.ts` | 把缩放档位、标签显示集写进节点/边 `data`，让 G6 回调读取 |
| `graph/viewport.ts` | 量文字、障碍物、取点位置、整组适应等与 G6 实例交互的视口辅助 |
| `graph/obstacles.ts` | 浮层障碍物注册表（标签避让、镜头适应用） |
| `composables/usePreviewFocus.ts` | 预览/详情状态机（单击预览、再次单击打开） |
| `composables/useLocalView.ts` | 只看相邻（1/2 跳）与恢复 |
| `composables/useGraphLayout.ts` | 异步计算章节分区布局，带过期结果保护 |
| `components/AppIcon.vue` | 内联 SVG 图标 |
| `components/GraphLegend.vue` | 图例 + 关系/类型计数筛选 |
| `components/GraphPreviewCard.vue` | 画布底部预览卡 |
| `components/ChapterMenu.vue` | 章节跳转菜单 |
| `components/LocalViewBar.vue` | 局部视图提示条 |
| `components/GraphSidePanel.vue` | 左面板（概览/详情，保留推荐摘要） |
| `components/AppTopbar.vue` | 顶栏（面包屑 + 用户） |

**修改**：`graph/adapter.ts`、`graph/lifecycle.ts`、`components/GraphCanvas.vue`、`views/StudentGraphView.vue`、`App.vue`、`main.ts`（引入 tokens/样式）、`composables/useLearning.ts`（仅 `MASTERY_LABELS.unknown` 文案）。

**测试**：新增 `tests/frontend/graph-*.test.ts`、`graph-presentation.test.ts`、`graph-viewport.test.ts`、`graph-lifecycle-enhance.test.ts`、`graph-obstacles.test.ts`、`preview-focus.test.ts`、`local-view.test.ts`、`student-graph-workbench.test.ts`；更新 `h03/h05/i06/l13/l14`（仅样式/状态名/缩放常量），`tests/e2e/personal.spec.ts`。

**最后删除**：`src/frontend/preview/`（隔离预览）。

**关于"已验证的模块"**：任务 1–6 里的源码与测试已在预览阶段落到仓库、跑过（theme 9、scale 10、label-plan 12 + fit 10、chapter-layout 17、focus-states 18，共 76 条，type-check 干净），随后为写本计划移出了工作区。执行时**原样建回**这些文件，再跑一遍测试确认；不要重新设计它们。

---

## 计划验证状态与实施中确认的差异

**本计划里的代码已被验证过**：写计划时把 Task 1–16 的全部代码临时落在本工作区，结果为——`npm --prefix src/frontend run type-check` 退出码 0；`npm --prefix src/frontend run test -- --run` 55 个文件 / 1122 条全部通过（基线 38 个文件 / 934 条）；`npm --prefix src/frontend run build` 退出码 0；`./scripts/verify.sh`（基础档）退出码 0；用隔离页 `src/frontend/preview/prod.html`（生产的 `App` + `StudentGraphView` 挂在合成数据上、真实 G6 渲染）在 1280×800 看过概览态：暗色外壳、左面板、图例、小地图、右侧工具、底部折叠条的版面与预览一致。之后为不越过「计划审阅」这道关，**已把工作区还原**（仅保留规格、交接、`docs/tasks.md` 认领与隔离预览）；全部文件的最终版本逐字嵌在下面各任务里。

**这次验证没做的**：端到端（Playwright，需要后端与数据）、`./scripts/verify.sh full|integration`、真实课程数据上的布局、G6 画布像素色的对比度采样、键盘 Tab 全路径、200% 缩放、真实 `prefers-reduced-motion`、点击节点/悬停/章节跳转在**真实 G6** 里的逐项目测（只在单元层用替身验证了行为）。这些放在 Task 17。

**写计划时发现、与规格不一致的地方**（执行时同步改规格相应小节，并记入 ADR）：

| # | 规格原写 | 实际做法 | 原因 |
| --- | --- | --- | --- |
| 1 | 适配层新增契约 `importance` | **不新增**；标签优先级的 `importance` 用度数 / 最大度数估算 | 契约没有该字段，且本任务不改契约；有了字段再接 |
| 2 | 预览卡显示定义 | 预览卡**不含定义**，只有名称、类型、章节、掌握状态文字、先修/解锁数量 | 列表接口不带定义，不为预览多发请求；定义在详情里 |
| 3 | 详情顺序：定义 → 掌握状态 → 关联知识 → 来源 | 掌握状态区在 `KnowledgeDetail` **上方** | 掌握标记在详情加载中/失败时也必须可用（既有 I06 用例）；要放进定义之后需给 `KnowledgeDetail` 加插槽，列入第二批 |
| 4 | 关联知识每组带线型样例、芯片化 | 只用 CSS 把芯片/来源卡片重做，**没有线型样例** | 不改 `KnowledgeDetail` 标记与既有 `data-test`；第二批随插槽一起做 |
| 5 | 搜索回车 = 预览；输入时高亮匹配 | 输入仍是**筛选**（`filters.state.query`，保持 H05/H11/卡片视图行为），回车才定位并预览 | 不改既有筛选语义；`locateNode` 纯函数已导出，页面不用会选中详情的 `filters.locate` |
| 6 | 章节跳转在列表视图滚动到该章 | 卡片视图下**章节菜单禁用** | `KnowledgeCards` 是分页的平铺列表；第二批随「目录」页签做 |
| 7 | 图例每类关系写箭头方向 | `EXAMPLE_OF` **不写方向说明** | 契约与架构文档没有明文它的方向，以画布箭头为准 |
| 8 | 未学习显示「未学习」 | `MASTERY_LABELS.unknown` 与成功提示由「未开始」改为「未学习」，同步 `i06`、端到端 | 与规格 §3.4 一致；这是用户可见文案变化 |
| 9 | 面板开合只 `setSize` | 增强模式：`ResizeObserver` 只 `setSize`；**窗口缩放**（`window` 的 `resize`）与 `refreshSize()` 仍整图重新适配 | 保留 L14 的窗口缩放后重新聚焦；非增强模式（教师页）完全不变 |
| 10 | — | 增强模式下**切换布局、位置重算会重建画布**（选中等状态随数据保留；重建后回到最近一次聚焦的节点） | 章节分区是预先算好的位置；G6 无法在力导向与预设位置间无损切换 |
| 11 | 搜索/章节命中的节点标签仍可强制显示 | 只有预览/选中的节点强制显示标签（布尔判断） | 规格 §4.2 已写；累加分数的阈值会越线，导致标签重叠 |
| 12 | — | `GraphToolbar` 学生页不再用，**教师页继续用**，未改 | 教师页第二批另行设计 |

---

## 第一阶段：纯函数模块（无 G6、无 Vue 依赖，已验证）

### Task 1: tokens 与图谱主题字面量

**Files:**
- Create: `src/frontend/src/styles/tokens.css`
- Create: `src/frontend/src/graph/theme.ts`
- Test: `tests/frontend/graph-theme.test.ts`

**Interfaces:**
- Produces: `GRAPH_COLORS`（`canvas/panel/hover/line/controlEdge/text/accent/accentSoft/nodeStroke/ok/warn/danger/dimmedFill/dimmedStroke/fadedFill/fadedStroke/fadedIcon/fadedEdge/hullFill`）、`NODE_TYPE_FILL`、`NODE_TYPE_GLYPH`、`KnowledgePointType`；`tokens.css` 的 `--ss-*` 与 `.graph-workspace { --gw-* }`。
- 该测试把 `theme.ts` 的数值与 `tokens.css` 逐项比对，并断言 tokens 里没有改动既有 `--color-*`、字面量颜色对比度达标。

- [ ] **Step 1: 写测试**（已验证的测试文件，原样建立）

`tests/frontend/graph-theme.test.ts`：

```ts
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { GRAPH_COLORS, NODE_TYPE_FILL, NODE_TYPE_GLYPH } from '../../src/frontend/src/graph/theme'

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
```

- [ ] **Step 2: 运行，确认失败**

Run: `npm --prefix src/frontend run test -- --run graph-theme`
Expected: FAIL（`Cannot find module '../../src/frontend/src/graph/theme'` 或读取 `tokens.css` 失败）

- [ ] **Step 3: 建立 tokens.css 与 theme.ts**

`src/frontend/src/styles/tokens.css`：

```css
/*
 * 图谱工作台 tokens（UI-GRAPH-PILOT-01，设计规格 §3）。
 *
 * --ss-*：暗色应用外壳；--gw-*：图谱浅色工作区。独立命名空间，不改现有 --color-*，
 * 其他页面推广前保持原样。G6 画布读不到 CSS 变量，画布里的字面量在 `graph/theme.ts`，
 * 两处数值必须一致（tests/frontend/graph-theme.test.ts 会比对）。
 */
:root {
  --ss-bg: #101114;
  --ss-panel: #18191d;
  --ss-raised: #222329;
  --ss-hover: #2c2d35;
  --ss-line: #35363f; /* 装饰分隔线，不承担识别功能 */
  --ss-edge: #7a7c8a; /* 输入框等需独立识别的边界 */
  --ss-text: #f1f2f4;
  --ss-text-2: #b2b4bf;
  --ss-text-3: #9c9faa;
  --ss-primary: #5b5bd6;
  --ss-primary-hover: #6262da;
  --ss-primary-press: #4b4bc0;
  --ss-link: #b1acff; /* 暗底链接与焦点 */
  --ss-selected: #282742;
  --ss-ok: #92d3af;
  --ss-ok-bg: #1f322b;
  --ss-warn: #f2c46d;
  --ss-warn-bg: #342a1d;
  --ss-danger: #f0a3a3;
  --ss-danger-bg: #3b2227;

  --ss-radius-sm: 6px;
  --ss-radius-md: 10px;
  --ss-radius-lg: 14px;
  --ss-ease: cubic-bezier(0.2, 0, 0, 1);
  --ss-shadow-pop-dark: 0 8px 24px rgb(0 0 0 / 28%);
  --ss-shadow-pop-light: 0 8px 24px rgb(29 36 51 / 12%);
}

/* 图谱工作区：说明面板、画布、浮动工具条、tooltip、菜单都显式用浅色 tokens */
.graph-workspace {
  --gw-canvas: #f4f5f7;
  --gw-panel: #f8f9fb;
  --gw-hover: #eaecf1;
  --gw-line: #d2d5de;
  --gw-edge: #747a87; /* 控件边界 */
  --gw-text: #20232a;
  --gw-text-2: #545967;
  --gw-text-3: #626876;
  --gw-accent: #5145cd; /* 浅底链接、选中、先修强调、焦点 */
  --gw-selected: #e9e6fa;
  --gw-ok: #1f6b3a;
  --gw-ok-bg: #eaf6ee;
  --gw-warn: #8a5a10;
  --gw-warn-bg: #fdf4e3;
  --gw-danger: #8f2323;
  --gw-danger-bg: #fdecec;
  color: var(--gw-text);
}
```

`src/frontend/src/graph/theme.ts`：

```ts
import type { KnowledgePoint } from './adapter'

/**
 * 图谱浅色主题的字面量（UI-GRAPH-PILOT-01，设计规格 §3.3–3.4）。
 *
 * G6 画布读不到 CSS 变量，所以这里存一份与 `styles/tokens.css` 的 `--gw-*` 一一对应的数值，
 * 并由 tests/frontend/graph-theme.test.ts 保证两处一致。颜色只在这里与 `buildGraphOptions` 定义一处。
 */
export const GRAPH_COLORS = Object.freeze({
  canvas: '#F4F5F7',
  panel: '#F8F9FB',
  hover: '#EAECF1',
  line: '#D2D5DE',
  controlEdge: '#747A87',
  text: '#20232A',
  text2: '#545967',
  text3: '#626876',
  accent: '#5145CD',
  accentSoft: '#E9E6FA',
  nodeStroke: '#606A7B',
  ok: '#1F6B3A',
  warn: '#8A5A10',
  danger: '#8F2323',
  /** 标准淡化：非相关节点只降填充饱和度，边框与标签仍满足对比度 */
  dimmedFill: '#ECEEF2',
  dimmedStroke: '#7F8695',
  /** 强淡化（悬停，瞬时）：退成近画布色的小点；偏离 3:1 的有意例外，见规格 3.4a */
  fadedFill: '#F0F1F4',
  fadedStroke: '#C9CED8',
  fadedIcon: '#B7BCC8',
  fadedEdge: '#D3D7E0',
  /** 章节外框底色 */
  hullFill: '#EEEBFB',
})

export type KnowledgePointType = KnowledgePoint['type']

/** 节点类型填充：与画布对比仅 1.12–1.20，所以类型必须同时有单字标记，不能只靠颜色 */
export const NODE_TYPE_FILL: Readonly<Record<KnowledgePointType, string>> = Object.freeze({
  concept: '#DDE5F3',
  theorem: '#E5DEF4',
  formula: '#F6E6CD',
  method: '#D8EAE6',
  example: '#E8EAD8',
})

/** 节点内的单字类型标记 */
export const NODE_TYPE_GLYPH: Readonly<Record<KnowledgePointType, string>> = Object.freeze({
  concept: '概',
  theorem: '理',
  formula: '式',
  method: '法',
  example: '例',
})
```

- [ ] **Step 4: 运行，确认通过，并确认类型检查干净**

Run: `npm --prefix src/frontend run test -- --run graph-theme && npm --prefix src/frontend run type-check`
Expected: `graph-theme` 9 passed；type-check 退出码 0

- [ ] **Step 5: 提交（仅在用户授权后）**

```bash
git add src/frontend/src/styles/tokens.css src/frontend/src/graph/theme.ts tests/frontend/graph-theme.test.ts
git commit -m "feat(frontend): add graph workspace tokens and G6 theme literals"
```

---

### Task 2: 语义缩放（标签放大系数与屏幕下限）

**Files:**
- Create: `src/frontend/src/graph/scale.ts`
- Test: `tests/frontend/graph-scale.test.ts`

**Interfaces:**
- Produces: `READABLE_ZOOM = 0.9`；`NODE_BASE_PX/NODE_MIN_PX/LINE_MIN_PX/ARROW_BASE_PX/ARROW_MIN_PX/LABEL_BASE_PX`；`interface ScaleFloors { nodeK; lwMin; arrowK }`；`NO_FLOORS`；`scaleFloors(zoom: number, enabled: boolean): ScaleFloors`（节点 0.25 步、线宽 0.5 步量化）；`labelScale(zoom: number): number`（≥ `READABLE_ZOOM` 为 1，否则 `1/zoom` 按 0.5 步取整、上限 5）；`sameFloors(a, b): boolean`。

- [ ] **Step 1: 写测试**

`tests/frontend/graph-scale.test.ts`：

```ts
import { describe, expect, it } from 'vitest'
import {
  ARROW_MIN_PX,
  labelScale,
  LINE_MIN_PX,
  NODE_BASE_PX,
  NODE_MIN_PX,
  READABLE_ZOOM,
  sameFloors,
  scaleFloors,
} from '../../src/frontend/src/graph/scale'

describe('屏幕尺寸下限 scaleFloors', () => {
  it('总览缩放 0.2：节点 ≥14px、线宽 ≥1px、箭头 ≥6px（修改前是 7.2px / 0.3px / 1.8px）', () => {
    const f = scaleFloors(0.2, true)
    expect(NODE_BASE_PX * f.nodeK * 0.2).toBeGreaterThanOrEqual(NODE_MIN_PX)
    expect(f.lwMin * 0.2).toBeGreaterThanOrEqual(LINE_MIN_PX)
    expect(9 * f.arrowK * 0.2).toBeGreaterThanOrEqual(ARROW_MIN_PX)
    expect(f).toEqual({ nodeK: 2, lwMin: 5, arrowK: 3.5 })
  })

  it('缩放 ≥ 约 0.4 时节点不放大，尺寸与原设计一致', () => {
    expect(scaleFloors(0.4, true).nodeK).toBe(1)
    expect(scaleFloors(0.9, true).nodeK).toBe(1)
    expect(scaleFloors(1, true)).toEqual({ nodeK: 1, lwMin: 1, arrowK: 1 })
    expect(scaleFloors(2, true).arrowK).toBe(1)
  })

  it('线宽下限随缩放反比，按 0.5 档量化', () => {
    expect(scaleFloors(0.5, true).lwMin).toBe(2)
    expect(scaleFloors(0.34, true).lwMin).toBe(3)
    expect(scaleFloors(0.28, true).lwMin).toBe(3.5)
  })

  it('关闭或缩放无效时不设下限（回到修改前的行为）', () => {
    expect(scaleFloors(0.2, false)).toEqual({ nodeK: 1, lwMin: 0, arrowK: 1 })
    expect(scaleFloors(0, true)).toEqual({ nodeK: 1, lwMin: 0, arrowK: 1 })
    expect(scaleFloors(Number.NaN, true)).toEqual({ nodeK: 1, lwMin: 0, arrowK: 1 })
    expect(scaleFloors(-1, true)).toEqual({ nodeK: 1, lwMin: 0, arrowK: 1 })
  })

  it('返回新对象，调用方改写不会污染共享常量', () => {
    const a = scaleFloors(0.2, false)
    a.nodeK = 99
    expect(scaleFloors(0.2, false).nodeK).toBe(1)
  })

  it('档位量化：缩放略有变化时系数不变，避免每帧重绘', () => {
    expect(sameFloors(scaleFloors(0.2, true), scaleFloors(0.205, true))).toBe(true)
    expect(sameFloors(scaleFloors(0.3, true), scaleFloors(0.305, true))).toBe(true)
    expect(sameFloors(scaleFloors(0.9, true), scaleFloors(0.95, true))).toBe(true)
    // 缩放变化足够大时系数才会变，此时才需要重绘
    expect(sameFloors(scaleFloors(0.2, true), scaleFloors(0.3, true))).toBe(false)
  })
})

describe('标签放大系数 labelScale', () => {
  it('缩放 ≥ 可读缩放时为 1', () => {
    expect(READABLE_ZOOM).toBe(0.9)
    expect(labelScale(1)).toBe(1)
    expect(labelScale(0.9)).toBe(1)
    expect(labelScale(2.5)).toBe(1)
  })

  it('缩小时让标签在屏幕上保持约 13px：系数 × 缩放 ≈ 1', () => {
    for (const zoom of [0.85, 0.6, 0.5, 0.34, 0.27, 0.2]) {
      const k = labelScale(zoom)
      expect(k * zoom).toBeGreaterThan(0.7)
      expect(k * zoom).toBeLessThan(1.4)
    }
  })

  it('按 0.5 步量化，上限 5', () => {
    expect(labelScale(0.5)).toBe(2)
    expect(labelScale(0.268)).toBe(3.5)
    expect(labelScale(0.2)).toBe(5)
    expect(labelScale(0.05)).toBe(5)
  })

  it('无效缩放返回 1', () => {
    expect(labelScale(0)).toBe(1)
    expect(labelScale(Number.NaN)).toBe(1)
  })
})
```

- [ ] **Step 2: 运行，确认失败**

Run: `npm --prefix src/frontend run test -- --run graph-scale`
Expected: FAIL（找不到 `graph/scale`）

- [ ] **Step 3: 实现**

`src/frontend/src/graph/scale.ts`：

```ts
/**
 * 缩放相关的纯函数（设计规格 §3.4「屏幕尺寸下限」与 §4 标签分级）。
 *
 * 缩小时标签靠放大字号保持约 13px，但节点、线和箭头原先会缩成 7px 的点和 0.3px 的发丝，与标签严重失衡。
 * 这里给它们设屏幕下限（不是缩小标签，也不是降透明度）：节点直径 ≥14px、线宽 ≥1px、箭头 ≥6px。
 * 放大系数按档位量化（节点 0.25 步、线宽 0.5 步），避免滚轮缩放时每一帧都重绘。
 */

/** 可读缩放：整图适配后低于它就放大到它并聚焦入口节点（13px 标签在 0.9 下约 11.7px；原 0.7 时只有约 9px） */
export const READABLE_ZOOM = 0.9

export const NODE_BASE_PX = 36
export const NODE_MIN_PX = 14
export const LINE_MIN_PX = 1
export const ARROW_BASE_PX = 9
export const ARROW_MIN_PX = 6
export const LABEL_BASE_PX = 13

export interface ScaleFloors {
  /** 节点放大系数（≥1） */
  nodeK: number
  /** 线宽下限，画布像素（0 表示不设下限） */
  lwMin: number
  /** 箭头放大系数（≥1） */
  arrowK: number
}

export const NO_FLOORS: Readonly<ScaleFloors> = Object.freeze({ nodeK: 1, lwMin: 0, arrowK: 1 })

const quantize = (value: number, step: number): number => Math.round(value / step) * step

/** 按当前缩放算屏幕下限；关闭（enabled=false）或缩放无效时不设下限 */
export function scaleFloors(zoom: number, enabled: boolean): ScaleFloors {
  if (!enabled || !(zoom > 0)) return { ...NO_FLOORS }
  return {
    nodeK: Math.max(1, quantize(NODE_MIN_PX / (NODE_BASE_PX * zoom), 0.25)),
    lwMin: Math.max(0, quantize(LINE_MIN_PX / zoom, 0.5)),
    arrowK: Math.max(1, quantize(ARROW_MIN_PX / (ARROW_BASE_PX * zoom), 0.5)),
  }
}

/**
 * 标签放大系数：缩放 ≥ 可读缩放时为 1；缩小时放大字号，让标签在屏幕上保持约 13px。
 * 按 0.5 步量化，上限 5（缩放 0.2）。
 */
export function labelScale(zoom: number): number {
  if (!(zoom > 0) || zoom >= READABLE_ZOOM) return 1
  return Math.min(5, Math.max(1, Math.round((1 / zoom) * 2) / 2))
}

export function sameFloors(a: ScaleFloors, b: ScaleFloors): boolean {
  return a.nodeK === b.nodeK && a.lwMin === b.lwMin && a.arrowK === b.arrowK
}
```

- [ ] **Step 4: 运行，确认通过**

Run: `npm --prefix src/frontend run test -- --run graph-scale`
Expected: 10 passed

- [ ] **Step 5: 提交（仅在用户授权后）**

```bash
git add src/frontend/src/graph/scale.ts tests/frontend/graph-scale.test.ts
git commit -m "feat(frontend): add semantic zoom scale helpers"
```

---

### Task 3: 标签排布

**Files:**
- Create: `src/frontend/src/graph/labelPlan.ts`
- Test: `tests/frontend/graph-label-plan.test.ts`

**Interfaces:**
- Produces: `type Box = readonly [left, top, right, bottom]`；`interface LabelCandidate { id; x; y; text; score; forced }`（`x/y` 为屏幕坐标）；`planLabels(input: { candidates; viewport: {width,height}; zoom; labelK; nodeK; obstacles: Box[]; measure: (text, fontPx) => number }): Set<string>`（返回应显示标签的节点元素 id；`forced` 的候选即使重叠也保留，但仍不显示在障碍物下面）。

- [ ] **Step 1: 写测试**

`tests/frontend/graph-label-plan.test.ts`：

```ts
import { describe, expect, it } from 'vitest'
import { planLabels, type Box, type LabelCandidate, type LabelPlanInput } from '../../src/frontend/src/graph/labelPlan'

/** 每个字符占 fontPx（全角近似）；测试用，不依赖真实字体 */
const measure = (text: string, fontPx: number) => text.length * fontPx

function candidate(id: string, x: number, y: number, over: Partial<LabelCandidate> = {}): LabelCandidate {
  return { id, x, y, text: '知识点', score: 0, forced: false, ...over }
}

function input(candidates: LabelCandidate[], over: Partial<LabelPlanInput> = {}): LabelPlanInput {
  return {
    candidates,
    viewport: { width: 800, height: 600 },
    zoom: 1,
    labelK: 1,
    nodeK: 1,
    obstacles: [],
    measure,
    ...over,
  }
}

describe('标签排布 planLabels', () => {
  it('互不重叠的标签都显示', () => {
    const shown = planLabels(input([candidate('a', 100, 100), candidate('b', 400, 100), candidate('c', 100, 400)]))
    expect([...shown].sort()).toEqual(['a', 'b', 'c'])
  })

  it('重叠时分数高的保留、低的隐藏，与输入顺序无关', () => {
    const near = [candidate('low', 100, 100, { score: 1 }), candidate('high', 110, 100, { score: 9 })]
    expect([...planLabels(input(near))]).toEqual(['high'])
    expect([...planLabels(input([...near].reverse()))]).toEqual(['high'])
  })

  it('分数相同按 id 决定，结果稳定', () => {
    const tie = [candidate('b', 100, 100), candidate('a', 105, 100)]
    expect([...planLabels(input(tie))]).toEqual(['a'])
    expect([...planLabels(input([...tie].reverse()))]).toEqual(['a'])
  })

  it('forced（被预览/选中的节点）即使重叠也显示，且不会因为分数低而被挤掉', () => {
    const shown = planLabels(
      input([candidate('a', 100, 100, { score: 500 }), candidate('picked', 105, 100, { score: 0, forced: true })]),
    )
    expect(shown.has('picked')).toBe(true)
    // 高分的先排：picked 作为 forced 后排但仍放入
    expect(shown.has('a')).toBe(true)
  })

  it('高分（如章节成员 950 + 推荐项 300）不是强制：仍然要避让', () => {
    const shown = planLabels(
      input([candidate('chapter-a', 100, 100, { score: 1250 }), candidate('chapter-b', 105, 100, { score: 950 })]),
    )
    expect([...shown]).toEqual(['chapter-a'])
  })

  it('视口外（超出边距）的标签不参与排布', () => {
    const shown = planLabels(input([candidate('in', 10, 10), candidate('out', 900, 100), candidate('above', 100, -80)]))
    expect([...shown]).toEqual(['in'])
  })

  it('落在浮层（工具栏、图例、小地图…）下面的标签不显示，forced 也一样', () => {
    const obstacles: Box[] = [[0, 0, 300, 200]]
    const shown = planLabels(
      input([candidate('under', 100, 100), candidate('picked', 120, 90, { forced: true }), candidate('free', 500, 400)], {
        obstacles,
      }),
    )
    expect([...shown]).toEqual(['free'])
  })

  it('按真实宽度判断重叠：长文字挡住邻居，短文字不挡', () => {
    const wide = planLabels(
      input(
        [
          candidate('long', 100, 100, { text: '基于哈希函数的冲突处理策略', score: 5 }),
          candidate('near', 150, 100, { text: '堆', score: 1 }), // 长标签换行宽度 112，右缘约 164
        ],
        { measure },
      ),
    )
    expect(wide.has('near')).toBe(false)
    const narrow = planLabels(
      input([candidate('s1', 100, 100, { text: '栈', score: 5 }), candidate('s2', 180, 100, { text: '堆', score: 1 })]),
    )
    expect(narrow.has('s2')).toBe(true)
  })

  it('标签放大系数与缩放共同决定屏幕占位：缩小后放大字号，同样距离的两个标签更容易重叠', () => {
    const pair = [candidate('a', 100, 100, { score: 2 }), candidate('b', 170, 100, { score: 1 })]
    // zoom 1、k 1：字号 13，宽 ≈ 39+10，间距 70 → 不重叠
    expect(planLabels(input(pair)).size).toBe(2)
    // zoom 0.5、k 2：屏幕字号仍是 13，但节点放大系数不影响水平宽度；换成更宽的文字才会重叠
    const wideText = pair.map((c) => ({ ...c, text: '较长的知识点名称' }))
    expect(planLabels(input(wideText, { zoom: 0.5, labelK: 2 })).size).toBe(1)
  })

  it('节点放大系数把标签向下推（标签画在放大后的节点下面）', () => {
    // b 在 a 的正下方：节点不放大时标签刚好错开，节点放大后标签下移 → 与 b 的标签区域重叠
    const stack = [candidate('a', 100, 100, { score: 2 }), candidate('b', 100, 150, { score: 1 })]
    const plain = planLabels(input(stack, { nodeK: 1 }))
    const bigger = planLabels(input(stack, { nodeK: 3 }))
    expect(plain.size).toBeGreaterThanOrEqual(bigger.size)
  })

  it('空输入、缩放无效时返回空集合', () => {
    expect(planLabels(input([])).size).toBe(0)
    expect(planLabels(input([candidate('a', 10, 10)], { zoom: 0 })).size).toBe(0)
    expect(planLabels(input([candidate('a', 10, 10)], { zoom: Number.NaN })).size).toBe(0)
  })

  it('不修改输入', () => {
    const list = [candidate('b', 100, 100, { score: 1 }), candidate('a', 105, 100, { score: 2 })]
    const snapshot = JSON.stringify(list)
    planLabels(input(list))
    expect(JSON.stringify(list)).toBe(snapshot)
  })
})
```

- [ ] **Step 2: 运行，确认失败**

Run: `npm --prefix src/frontend run test -- --run graph-label-plan`
Expected: FAIL

- [ ] **Step 3: 实现**

`src/frontend/src/graph/labelPlan.ts`：

```ts
/**
 * 标签排布（设计规格 §4 第 1 层「标签分级」）。纯函数，不依赖 G6。
 *
 * 缩小时标签不能全部画出来：按优先级从高到低，在屏幕坐标里估算每个标签的占位，
 * 与已放置的标签重叠、或落在工具栏/图例/小地图等浮层下面的就不显示。
 * 节点本身不隐藏；隐藏的标签可经 tooltip、列表、搜索找到。
 *
 * 强制显示只留给「被预览/选中的那个节点」（`forced`）。优先级分数是累加的（章节成员 +950，再加推荐项 +300），
 * 绝不能用分数阈值判断强制，否则章节内的推荐项会意外越线、造成拥挤。
 */
import { LABEL_BASE_PX } from './scale'

/** [x1, y1, x2, y2]，与候选标签使用同一套屏幕坐标 */
export type Box = readonly [number, number, number, number]

export interface LabelCandidate {
  /** 元素 id（调用方自定，如 `kp:abc`） */
  id: string
  /** 节点中心在画布视口里的位置（像素） */
  x: number
  y: number
  /** 标签文字（含推荐序号前缀「1. 」） */
  text: string
  /** 优先级分数，越大越先排 */
  score: number
  /** 被预览/选中的节点：即使与别的标签重叠也显示 */
  forced: boolean
}

export interface LabelPlanInput {
  candidates: readonly LabelCandidate[]
  viewport: { width: number; height: number }
  /** 当前画布缩放 */
  zoom: number
  /** 标签放大系数（`labelScale`） */
  labelK: number
  /** 节点放大系数（`scaleFloors().nodeK`） */
  nodeK: number
  /** 浮层的屏幕包围盒（已含外扩边距） */
  obstacles: readonly Box[]
  /** 量文字宽度：fontPx 为标签在屏幕上的字号。必须用真实字体量，不能按字符数估算 */
  measure: (text: string, fontPx: number) => number
}

/** 视口外多远以内仍参与排布（拖动时标签不会在边缘突然出现） */
const MARGIN = 24
const WRAP_BASE_PX = 112

function overlaps(a: Box, b: Box): boolean {
  return a[0] < b[2] && a[2] > b[0] && a[1] < b[3] && a[3] > b[1]
}

/** 返回允许显示标签的元素 id 集合 */
export function planLabels(input: LabelPlanInput): Set<string> {
  const { viewport, zoom, labelK, nodeK, obstacles, measure } = input
  const shown = new Set<string>()
  if (!(zoom > 0)) return shown
  const fontPx = LABEL_BASE_PX * labelK * zoom
  const wrap = WRAP_BASE_PX * labelK * zoom
  const placed: Box[] = []
  // 分数相同按 id 排，保证结果与输入顺序无关
  const ordered = [...input.candidates].sort((a, b) => b.score - a.score || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
  for (const c of ordered) {
    if (c.x < -MARGIN || c.y < -MARGIN || c.x > viewport.width + MARGIN || c.y > viewport.height + MARGIN) continue
    const natural = measure(c.text, fontPx)
    const width = Math.min(natural, wrap) + 10
    const lines = Math.min(2, Math.max(1, Math.ceil(natural / Math.max(wrap, 1))))
    const height = lines * fontPx * 1.3 + 4
    const top = c.y + 18 * nodeK * zoom + 4 * labelK * zoom
    const box: Box = [c.x - width / 2 - 3, top, c.x + width / 2 + 3, top + height + 3]
    // 落在浮层下面的标签看不见：对被预览/选中的节点也一样
    if (obstacles.some((o) => overlaps(box, o))) continue
    if (c.forced || !placed.some((p) => overlaps(box, p))) {
      placed.push(box)
      shown.add(c.id)
    }
  }
  return shown
}
```

- [ ] **Step 4: 运行，确认通过**

Run: `npm --prefix src/frontend run test -- --run graph-label-plan`
Expected: 12 passed

- [ ] **Step 5: 提交（仅在用户授权后）**

```bash
git add src/frontend/src/graph/labelPlan.ts tests/frontend/graph-label-plan.test.ts
git commit -m "feat(frontend): add greedy label planner with obstacles"
```

---

### Task 4: 视口适应计算

**Files:**
- Create: `src/frontend/src/graph/fit.ts`
- Test: `tests/frontend/graph-fit.test.ts`

**Interfaces:**
- Consumes: `Box`（Task 3）。
- Produces: `DEFAULT_PADS = { left: 56, right: 96, top: 104, bottom: 96 }`；`computeFit({ points; viewport; pads; nodeRadius; bottomExtra; minZoom?; maxZoom? }): { zoom; center; target } | null`（缩放夹在 0.2–1.2；`center` 是点集包围盒中心，`target` 是它应落到的视口坐标）；`bottomPad(hardObstacles: Box[], viewportHeight: number, base?: number): number`（只看底部 45% 的硬障碍，给小地图让位）。

- [ ] **Step 1: 写测试**

`tests/frontend/graph-fit.test.ts`：

```ts
import { describe, expect, it } from 'vitest'
import { bottomPad, computeFit, DEFAULT_PADS } from '../../src/frontend/src/graph/fit'

const base = {
  viewport: { width: 884, height: 732 },
  pads: DEFAULT_PADS,
  nodeRadius: 24,
  bottomExtra: 20,
}

describe('范围适应 computeFit', () => {
  it('没有节点时返回 null', () => {
    expect(computeFit({ ...base, points: [] })).toBeNull()
  })

  it('一组节点整体放得进可用区域：包围盒缩放后不超过可用宽高', () => {
    const points: Array<[number, number]> = [[0, 0], [600, 0], [0, 500], [600, 500]]
    const fit = computeFit({ ...base, points })!
    const availW = 884 - 56 - 96
    const availH = 732 - 104 - 96
    const boxW = (600 + 48) * fit.zoom
    const boxH = (500 + 48 + 20) * fit.zoom
    expect(boxW).toBeLessThanOrEqual(availW + 0.001)
    expect(boxH).toBeLessThanOrEqual(availH + 0.001)
    // 至少有一个方向恰好贴满
    expect(Math.max(boxW / availW, boxH / availH)).toBeCloseTo(1, 5)
  })

  it('目标位置是可用区域的中心，而不是视口中心（避开搜索栏、右侧工具、底部折叠条）', () => {
    const fit = computeFit({ ...base, points: [[0, 0], [100, 100]] })!
    expect(fit.target).toEqual([56 + (884 - 56 - 96) / 2, 104 + (732 - 104 - 96) / 2])
    expect(fit.target[0]).not.toBe(884 / 2)
  })

  it('包围盒中心含节点半径与底部标签余量', () => {
    const fit = computeFit({ ...base, points: [[100, 100], [300, 200]] })!
    expect(fit.center[0]).toBeCloseTo((76 + 324) / 2)
    expect(fit.center[1]).toBeCloseTo((76 + (200 + 24 + 20)) / 2)
  })

  it('缩放被限制在 [minZoom, maxZoom]：很大的范围不会缩到 0.2 以下，单个点不会放大到 1.2 以上', () => {
    expect(computeFit({ ...base, points: [[0, 0], [90000, 90000]] })!.zoom).toBe(0.2)
    expect(computeFit({ ...base, points: [[5, 5]] })!.zoom).toBe(1.2)
    expect(computeFit({ ...base, points: [[5, 5]], maxZoom: 2 })!.zoom).toBe(2)
    expect(computeFit({ ...base, points: [[0, 0], [90000, 0]], minZoom: 0.05 })!.zoom).toBeLessThan(0.2)
  })

  it('视口比边距还小时仍给出有限的结果', () => {
    const fit = computeFit({ ...base, viewport: { width: 50, height: 50 }, points: [[0, 0], [300, 300]] })!
    expect(Number.isFinite(fit.zoom)).toBe(true)
    expect(fit.zoom).toBeGreaterThanOrEqual(0.2)
  })

  it('不修改输入', () => {
    const points: Array<readonly [number, number]> = [[1, 2], [3, 4]]
    const snapshot = JSON.stringify(points)
    computeFit({ ...base, points })
    expect(JSON.stringify(points)).toBe(snapshot)
  })
})

describe('底部边距 bottomPad', () => {
  it('没有障碍物时是默认边距', () => {
    expect(bottomPad([], 732)).toBe(96)
  })

  it('避开视口下半部分的硬障碍（小地图），上半部分的不计', () => {
    const minimap = [600, 580, 880, 726] as const // 顶边在 580 > 732 × 0.55
    expect(bottomPad([minimap], 732)).toBe(732 - 580 + 6)
    const toolbar = [10, 10, 300, 60] as const
    expect(bottomPad([toolbar], 732)).toBe(96)
  })

  it('障碍物不高时不会比默认边距更小', () => {
    expect(bottomPad([[0, 700, 100, 730]], 732)).toBe(96)
  })
})
```

- [ ] **Step 2: 运行，确认失败**

Run: `npm --prefix src/frontend run test -- --run graph-fit`
Expected: FAIL

- [ ] **Step 3: 实现**

`src/frontend/src/graph/fit.ts`：

```ts
/**
 * 范围适应（设计规格 §4.2）。纯函数，不依赖 G6。
 *
 * 把一组节点整体放进视口：先按包围盒算缩放，再算出「包围盒中心应落在视口哪个位置」——
 * 中心取在「未被搜索栏、右侧工具、底部折叠条和小地图占用的区域」的中心。
 * 章节跳转展示的是整章范围而不是一个点；局部视图、类型筛选下的「适应画布」也只按可见节点计算。
 */
import type { Box } from './labelPlan'

export interface FitPads {
  left: number
  right: number
  top: number
  bottom: number
}

export interface FitInput {
  /** 节点中心（画布坐标） */
  points: ReadonlyArray<readonly [number, number]>
  viewport: { width: number; height: number }
  pads: FitPads
  /** 节点半径（含放大系数） */
  nodeRadius: number
  /** 包围盒底部额外留给标签的高度 */
  bottomExtra: number
  minZoom?: number
  maxZoom?: number
}

export interface FitResult {
  zoom: number
  /** 包围盒中心（画布坐标） */
  center: [number, number]
  /** 适应后该中心应落在的视口位置（像素） */
  target: [number, number]
}

export const DEFAULT_PADS: Readonly<FitPads> = Object.freeze({ left: 56, right: 96, top: 104, bottom: 96 })

export function computeFit(input: FitInput): FitResult | null {
  const { points, viewport, pads, nodeRadius, bottomExtra } = input
  if (points.length === 0) return null
  const minZoom = input.minZoom ?? 0.2
  const maxZoom = input.maxZoom ?? 1.2
  const xs = points.map((p) => p[0])
  const ys = points.map((p) => p[1])
  const minX = Math.min(...xs) - nodeRadius
  const maxX = Math.max(...xs) + nodeRadius
  const minY = Math.min(...ys) - nodeRadius
  const maxY = Math.max(...ys) + nodeRadius + bottomExtra
  const availW = Math.max(viewport.width - pads.left - pads.right, 100)
  const availH = Math.max(viewport.height - pads.top - pads.bottom, 100)
  const raw = Math.min(availW / Math.max(maxX - minX, 1), availH / Math.max(maxY - minY, 1))
  return {
    zoom: Math.min(maxZoom, Math.max(minZoom, raw)),
    center: [(minX + maxX) / 2, (minY + maxY) / 2],
    target: [pads.left + availW / 2, pads.top + availH / 2],
  }
}

/**
 * 底部边距：至少 `base`，并避开处于视口下半部分的浮层（如小地图）。
 * 传入的应是「硬障碍」；可展开的图例这类「软障碍」由调用方过滤掉，否则总览会因此缩小。
 */
export function bottomPad(hardObstacles: readonly Box[], viewportHeight: number, base = DEFAULT_PADS.bottom): number {
  let pad = base
  for (const box of hardObstacles) {
    if (box[1] > viewportHeight * 0.55) pad = Math.max(pad, viewportHeight - box[1] + 6)
  }
  return pad
}
```

- [ ] **Step 4: 运行，确认通过**

Run: `npm --prefix src/frontend run test -- --run graph-fit`
Expected: 10 passed

- [ ] **Step 5: 提交（仅在用户授权后）**

```bash
git add src/frontend/src/graph/fit.ts tests/frontend/graph-fit.test.ts
git commit -m "feat(frontend): add viewport fit computation"
```

---

### Task 5: 章节分区布局

**Files:**
- Create: `src/frontend/src/graph/chapterLayout.ts`
- Test: `tests/frontend/graph-chapter-layout.test.ts`

**Interfaces:**
- Consumes: `RelationType`（`graph/adapter.ts`）。
- Produces: `type LayoutMode = 'all' | 'hier' | 'chapter'`；`LayoutNode { id; chapter: string | null }`；`LayoutEdge { id; source; target; type }`；`type Positions = Map<string, {x, y}>`；`COMPACT_OPTIONS`（nodesep 28、ranksep 57、cellW 120、cellH 100、laneGap 100、viewport [884, 732]）；`computeLayout(nodes, edges, mode, chapterOrder, options?, engine?): Promise<Positions>`（默认引擎是 `@antv/g6` 的 `AntVDagreLayout`，可替换，测试用替身）；`layoutMetrics(...)`（节点最小间距、先修方向违例等度量，测试用）。
- 保证：不删除/隐藏任何关系；`chapter_id` 缺失的节点归入「未归章」分区；目录里没有的章节按出现顺序跟在后面，节点不会因目录缺失而消失。

- [ ] **Step 1: 写测试**

`tests/frontend/graph-chapter-layout.test.ts`：

```ts
import { describe, expect, it } from 'vitest'
import {
  COMPACT_OPTIONS,
  computeLayout,
  layoutMetrics,
  type DagreEngine,
  type LayoutEdge,
  type LayoutNode,
  type Positions,
} from '../../src/frontend/src/graph/chapterLayout'

/**
 * 每章 perChapter 个节点：
 * - n0…n(k-3) 是先修树（PREREQUISITE，节点 i 的先修是 floor((i-1)/2)，深度约 3，接近真实课程的章内结构）；
 * - n(k-2) 没有任何关系（孤立）；
 * - n(k-1) 是例题，经 EXAMPLE_OF 挂在 n1 上（卫星）；
 * 章与章之间：上一章最后一个链节点 → 下一章 n0 的先修边；n2 之间有相关边。
 */
function course(chapters: number, perChapter: number): { nodes: LayoutNode[]; edges: LayoutEdge[]; order: string[] } {
  const nodes: LayoutNode[] = []
  const edges: LayoutEdge[] = []
  const id = (c: number, i: number) => `c${c}n${i}`
  let e = 0
  for (let c = 0; c < chapters; c += 1) {
    for (let i = 0; i < perChapter; i += 1) nodes.push({ id: id(c, i), chapter: `ch${c}` })
    const chain = perChapter - 2
    for (let i = 1; i < chain; i += 1) edges.push({ id: `e${e++}`, source: id(c, Math.floor((i - 1) / 2)), target: id(c, i), type: 'PREREQUISITE' })
    edges.push({ id: `e${e++}`, source: id(c, perChapter - 1), target: id(c, 1), type: 'EXAMPLE_OF' })
    if (c + 1 < chapters) {
      edges.push({ id: `e${e++}`, source: id(c, chain - 1), target: id(c + 1, 0), type: 'PREREQUISITE' })
      edges.push({ id: `e${e++}`, source: id(c, 2), target: id(c + 1, 2), type: 'RELATED_TO' })
    }
  }
  return { nodes, edges, order: Array.from({ length: chapters }, (_, c) => `ch${c}`) }
}

function bboxOf(pos: Positions, ids: string[]) {
  const xs = ids.map((i) => pos.get(i)!.x)
  const ys = ids.map((i) => pos.get(i)!.y)
  return { x1: Math.min(...xs), x2: Math.max(...xs), y1: Math.min(...ys), y2: Math.max(...ys) }
}

describe('章节分区布局 computeLayout（真实 G6 dagre 引擎）', () => {
  const g = course(4, 8)

  it('每个节点都有有限的位置', async () => {
    const pos = await computeLayout(g.nodes, g.edges, 'chapter', g.order)
    expect(pos.size).toBe(g.nodes.length)
    for (const n of g.nodes) {
      const p = pos.get(n.id)!
      expect(Number.isFinite(p.x) && Number.isFinite(p.y), n.id).toBe(true)
    }
  })

  it('节点互不重叠：任意两节点中心距 ≥ 60', async () => {
    const pos = await computeLayout(g.nodes, g.edges, 'chapter', g.order)
    const m = layoutMetrics(pos, g.nodes, g.edges)
    expect(m.minNodeDist).toBeGreaterThanOrEqual(60)
  })

  it('章内先修边方向不变：全部向下', async () => {
    const pos = await computeLayout(g.nodes, g.edges, 'chapter', g.order)
    expect(layoutMetrics(pos, g.nodes, g.edges).prereqWithinDownShare).toBe(1)
  })

  it('各章的包围盒互不相交（章节是分区）', async () => {
    const pos = await computeLayout(g.nodes, g.edges, 'chapter', g.order)
    const boxes = g.order.map((c) => bboxOf(pos, g.nodes.filter((n) => n.chapter === c).map((n) => n.id)))
    for (let i = 0; i < boxes.length; i += 1) {
      for (let j = i + 1; j < boxes.length; j += 1) {
        const a = boxes[i]!
        const b = boxes[j]!
        const disjoint = a.x2 < b.x1 || b.x2 < a.x1 || a.y2 < b.y1 || b.y2 < a.y1
        expect(disjoint, `ch${i} 与 ch${j} 的包围盒相交`).toBe(true)
      }
    }
  })

  it('各章按课程顺序排列：行优先（先从左到右，再从上到下）', async () => {
    const pos = await computeLayout(g.nodes, g.edges, 'chapter', g.order)
    const boxes = g.order.map((c) => bboxOf(pos, g.nodes.filter((n) => n.chapter === c).map((n) => n.id)))
    for (let i = 0; i + 1 < boxes.length; i += 1) {
      const a = boxes[i]!
      const b = boxes[i + 1]!
      const nextRow = b.y1 > a.y1 + 1
      const sameRowRight = Math.abs(b.y1 - a.y1) <= 1 && b.x1 > a.x1
      expect(nextRow || sameRowRight, `ch${i + 1} 应在 ch${i} 之后`).toBe(true)
    }
  })

  it('例题（卫星）挨着它说明的知识点，不被甩到远处', async () => {
    const pos = await computeLayout(g.nodes, g.edges, 'chapter', g.order)
    for (let c = 0; c < 4; c += 1) {
      const example = pos.get(`c${c}n7`)!
      const concept = pos.get(`c${c}n1`)!
      expect(Math.hypot(example.x - concept.x, example.y - concept.y)).toBeLessThanOrEqual(COMPACT_OPTIONS.cellW * 3)
    }
  })

  it('没有任何关系的孤立节点也有位置，且不压在别的节点上', async () => {
    const pos = await computeLayout(g.nodes, g.edges, 'chapter', g.order)
    for (let c = 0; c < 4; c += 1) {
      const orphan = pos.get(`c${c}n6`)!
      expect(orphan).toBeDefined()
      for (const n of g.nodes) {
        if (n.id === `c${c}n6`) continue
        const p = pos.get(n.id)!
        expect(Math.hypot(p.x - orphan.x, p.y - orphan.y), `${n.id}`).toBeGreaterThan(40)
      }
    }
  })

  it('结果是确定的：同样输入得到同样位置', async () => {
    const a = await computeLayout(g.nodes, g.edges, 'chapter', g.order)
    const b = await computeLayout(g.nodes, g.edges, 'chapter', g.order)
    expect([...a]).toEqual([...b])
  })

  it('不修改输入', async () => {
    const nodes = JSON.stringify(g.nodes)
    const edges = JSON.stringify(g.edges)
    await computeLayout(g.nodes, g.edges, 'chapter', g.order)
    expect(JSON.stringify(g.nodes)).toBe(nodes)
    expect(JSON.stringify(g.edges)).toBe(edges)
  })
})

describe('章节分区布局：边界', () => {
  it('空图返回空', async () => {
    expect((await computeLayout([], [], 'chapter', [])).size).toBe(0)
  })

  it('章节不在目录里的节点不会消失；未归章节点归入最后一个分区', async () => {
    const nodes: LayoutNode[] = [
      { id: 'a', chapter: 'ch1' },
      { id: 'b', chapter: 'ch1' },
      { id: 'c', chapter: 'ghost' }, // 目录里没有
      { id: 'd', chapter: null }, // 未归章
    ]
    const edges: LayoutEdge[] = [{ id: 'e', source: 'a', target: 'b', type: 'PREREQUISITE' }]
    const pos = await computeLayout(nodes, edges, 'chapter', ['ch1'])
    expect([...pos.keys()].sort()).toEqual(['a', 'b', 'c', 'd'])
  })

  it('指向不存在节点的边被忽略，不影响布局', async () => {
    const nodes: LayoutNode[] = [{ id: 'a', chapter: 'x' }, { id: 'b', chapter: 'x' }]
    const edges: LayoutEdge[] = [
      { id: 'e1', source: 'a', target: 'b', type: 'PREREQUISITE' },
      { id: 'e2', source: 'a', target: 'missing', type: 'PREREQUISITE' },
    ]
    for (const mode of ['all', 'hier', 'chapter'] as const) {
      const pos = await computeLayout(nodes, edges, mode, ['x'])
      expect(pos.size, mode).toBe(2)
    }
  })

  it('没有任何先修关系（PDF 式）时也是接近横屏的紧凑网格，不会排成一条长带', async () => {
    const nodes: LayoutNode[] = []
    for (let c = 0; c < 8; c += 1) for (let i = 0; i < 12; i += 1) nodes.push({ id: `c${c}n${i}`, chapter: `ch${c}` })
    const order = Array.from({ length: 8 }, (_, c) => `ch${c}`)
    const pos = await computeLayout(nodes, [], 'chapter', order)
    const m = layoutMetrics(pos, nodes, [])
    expect(m.aspect).toBeGreaterThan(0.4)
    expect(m.aspect).toBeLessThan(3)
    expect(m.minNodeDist).toBeGreaterThanOrEqual(60)
  })
})

describe('章节分区布局：可替换引擎', () => {
  it('chapter 模式每章调用一次引擎，且只传该章的层级边（相关/应用实例关系不参与布局）', async () => {
    const calls: Array<{ ids: string[]; edges: Array<{ source: string; target: string }> }> = []
    const stack: DagreEngine = async (ids, edges) => {
      calls.push({ ids, edges })
      return new Map(ids.map((id, i) => [id, { x: 0, y: i * 150 }]))
    }
    const g = course(3, 8)
    await computeLayout(g.nodes, g.edges, 'chapter', g.order, {}, stack)
    expect(calls).toHaveLength(3)
    for (const [c, call] of calls.entries()) {
      for (const id of call.ids) expect(id.startsWith(`c${c}n`)).toBe(true)
      for (const e of call.edges) {
        expect(e.source.startsWith(`c${c}n`) && e.target.startsWith(`c${c}n`)).toBe(true)
      }
    }
  })

  it('hier 模式不把相关/应用实例边交给引擎；all 模式把全部边交给引擎', async () => {
    const seen: number[] = []
    const stub: DagreEngine = async (ids, edges) => {
      seen.push(edges.length)
      return new Map(ids.map((id, i) => [id, { x: i * 100, y: 0 }]))
    }
    const g = course(2, 8)
    await computeLayout(g.nodes, g.edges, 'hier', g.order, {}, stub)
    const hierCount = g.edges.filter((e) => e.type === 'PREREQUISITE' || e.type === 'CONTAINS').length
    expect(seen.at(-1)).toBe(hierCount)
    await computeLayout(g.nodes, g.edges, 'all', g.order, {}, stub)
    expect(seen.at(-1)).toBe(g.edges.length)
  })
})

describe('章节分区布局：对比现状（96 节点，8 章 × 12）', () => {
  const g = course(8, 12)

  it('每章都能放进可读缩放下的一屏；现状一章都放不下', async () => {
    const chapter = layoutMetrics(await computeLayout(g.nodes, g.edges, 'chapter', g.order), g.nodes, g.edges)
    expect(chapter.chapters.fitOneScreen).toBe(chapter.chapters.n)
    const all = layoutMetrics(await computeLayout(g.nodes, g.edges, 'all', g.order, { nodesep: 56, ranksep: 110 }), g.nodes, g.edges)
    expect(all.chapters.fitOneScreen).toBeLessThan(chapter.chapters.fitOneScreen)
  })

  it('适应一屏的缩放至少是现状的 2 倍，且画布接近横屏', async () => {
    const chapter = layoutMetrics(await computeLayout(g.nodes, g.edges, 'chapter', g.order), g.nodes, g.edges)
    const all = layoutMetrics(await computeLayout(g.nodes, g.edges, 'all', g.order, { nodesep: 56, ranksep: 110 }), g.nodes, g.edges)
    expect(chapter.fitZoom).toBeGreaterThan(all.fitZoom * 2)
    expect(chapter.aspect).toBeGreaterThan(0.5)
    expect(chapter.aspect).toBeLessThan(2.5)
  })
})
```

- [ ] **Step 2: 运行，确认失败**

Run: `npm --prefix src/frontend run test -- --run graph-chapter-layout`
Expected: FAIL

- [ ] **Step 3: 实现**

`src/frontend/src/graph/chapterLayout.ts`：

```ts
/**
 * 图谱布局（设计规格 §4.1，用户确认采用「章节分区 + 紧凑间距」）。纯函数，不渲染。
 *
 * 现状的问题：四类关系全部参与布局，跨章长线和「例题挂在远处」把画布拉成 5:1 的长条
 * （96 节点 9042×1792，适应一屏缩放 0.10，没有一章能放进一屏）。
 *
 * 三种模式：
 * - all：四类关系全部参与（现状基线，只用于对比测量）
 * - hier：只有 PREREQUISITE 与 CONTAINS 决定层级；RELATED_TO / EXAMPLE_OF 照常画，但不再拉扯位置，
 *         没有层级边的节点作为「卫星」放到所关联节点旁边，无关联的孤立节点排成网格
 * - chapter（默认）：在 hier 的基础上每章单独布局，各章按课程顺序排成分区
 *
 * 任何模式都不删除、不隐藏任何关系。缺章节信息的节点归入「未归章」分区。
 */
import type { RelationType } from './adapter'

export type LayoutMode = 'all' | 'hier' | 'chapter'

export interface LayoutNode {
  id: string
  /** 所属章节 id；null 表示未归章 */
  chapter: string | null
}

export interface LayoutEdge {
  id: string
  source: string
  target: string
  type: RelationType
}

export type Positions = Map<string, { x: number; y: number }>

export interface LayoutOptions {
  nodesep: number
  ranksep: number
  /** 卫星/孤立节点占位格子的宽高（含标签） */
  cellW: number
  cellH: number
  /** 章节分区之间的间距 */
  laneGap: number
  /** 排版时参照的视口（画布像素）：在多种列数里选「适应该视口时缩放最大」的一种 */
  viewport: readonly [number, number]
}

/**
 * 紧凑间距。注意 G6 `antv-dagre` 的实际间距是「节点尺寸 + 3×nodesep」「节点尺寸 + 2×ranksep」，
 * 原来的 56 / 110 实际是 204 / 256，比设定值宽松很多；这里的 28 / 57 实际约 120 / 150。
 */
export const COMPACT_OPTIONS: Readonly<LayoutOptions> = Object.freeze({
  nodesep: 28,
  ranksep: 57,
  cellW: 120,
  cellH: 100,
  laneGap: 100,
  viewport: [884, 732] as const,
})

/** 层级布局引擎：给一组节点和它们之间的层级边，返回每个节点的位置。可替换，便于测试 */
export type DagreEngine = (
  ids: string[],
  edges: Array<{ source: string; target: string }>,
  options: LayoutOptions,
) => Promise<Positions>

/** 默认引擎：G6 自带的 antv-dagre（按需加载，不新增依赖） */
export const g6DagreEngine: DagreEngine = async (ids, edges, o) => {
  const pos: Positions = new Map()
  if (ids.length === 0) return pos
  const { AntVDagreLayout } = await import('@antv/g6')
  const layout = new AntVDagreLayout({ rankdir: 'TB', nodesep: o.nodesep, ranksep: o.ranksep, nodeSize: [36, 36] } as never)
  await layout.execute({
    nodes: ids.map((id) => ({ id })),
    edges: edges.map((e, i) => ({ id: `e${i}`, source: e.source, target: e.target })),
  } as never)
  layout.forEachNode((node) => {
    // G6 的节点 id 类型是 string | number，位置字段在布局后一定存在
    pos.set(String(node.id), { x: Number(node.x), y: Number(node.y) })
  })
  return pos
}

const isHierarchy = (type: RelationType): boolean => type === 'PREREQUISITE' || type === 'CONTAINS'

/**
 * 把没有层级边的节点放到「它所关联的节点」旁边最近的空位。
 * 用真实坐标做矩形碰撞：dagre 的坐标并不落在整齐的格子上，格子取整会让卫星压到别的层的节点上。
 * 返回找不到关联（或周围没有空位）的节点。
 */
function placeSatellites(
  pos: Positions,
  free: string[],
  edges: LayoutEdge[],
  o: LayoutOptions,
  within: ReadonlySet<string>,
): string[] {
  const taken: Array<{ x: number; y: number }> = [...pos.values()]
  const collides = (x: number, y: number) =>
    taken.some((t) => Math.abs(t.x - x) < o.cellW * 0.9 && Math.abs(t.y - y) < o.cellH * 0.9)
  const leftover: string[] = []
  const anchorOf = (id: string): string | null => {
    // 应用实例优先（例题挨着它说明的知识点），其次相关
    for (const type of ['EXAMPLE_OF', 'RELATED_TO'] as const) {
      for (const e of edges) {
        if (e.type !== type) continue
        const other = e.source === id ? e.target : e.target === id ? e.source : null
        if (other !== null && pos.has(other) && within.has(other)) return other
      }
    }
    return null
  }
  // 以锚点为中心的螺旋搜索顺序：优先右侧，再下方
  const ring: Array<[number, number]> = []
  for (let r = 1; r <= 8; r += 1) {
    for (let dy = 0; dy <= r; dy += 1) for (const dx of [r, -r]) ring.push([dx, dy])
    for (let dx = 0; dx < r; dx += 1) ring.push([dx, r])
  }
  for (const id of free) {
    const anchor = anchorOf(id)
    if (anchor === null) {
      leftover.push(id)
      continue
    }
    const base = pos.get(anchor)!
    let placed = false
    for (const [dx, dy] of ring) {
      const x = base.x + dx * o.cellW
      const y = base.y + dy * o.cellH
      if (!collides(x, y)) {
        pos.set(id, { x, y })
        taken.push({ x, y })
        placed = true
        break
      }
    }
    if (!placed) leftover.push(id)
  }
  return leftover
}

/** 布局一个节点集合（全局或某一章）：层级节点走引擎，其余作为卫星或排成网格 */
async function layoutGroup(
  nodes: LayoutNode[],
  edges: LayoutEdge[],
  o: LayoutOptions,
  engine: DagreEngine,
): Promise<Positions> {
  const ids = new Set(nodes.map((n) => n.id))
  const inGroup = edges.filter((e) => ids.has(e.source) && ids.has(e.target))
  const hierarchy = inGroup.filter((e) => isHierarchy(e.type))
  const connected = new Set<string>()
  for (const e of hierarchy) {
    connected.add(e.source)
    connected.add(e.target)
  }
  const main = nodes.filter((n) => connected.has(n.id)).map((n) => n.id)
  const pos = await engine(main, hierarchy, o)
  const free = nodes.filter((n) => !connected.has(n.id)).map((n) => n.id)
  if (free.length === 0) return pos
  const leftover = placeSatellites(pos, free, inGroup, o, ids)
  if (leftover.length > 0) {
    let maxY = 0
    let minX = Infinity
    let maxX = -Infinity
    for (const p of pos.values()) {
      maxY = Math.max(maxY, p.y)
      minX = Math.min(minX, p.x)
      maxX = Math.max(maxX, p.x)
    }
    if (!Number.isFinite(minX)) {
      minX = 0
      maxX = o.cellW * 3
    }
    // 列数取「现有宽度能放下的列数」与「接近 1.4:1 的网格」两者较大者，避免没有层级边时排成一条长带
    const cols = Math.max(3, Math.floor((maxX - minX) / o.cellW) + 1, Math.ceil(Math.sqrt(leftover.length * 1.4)))
    const top = pos.size === 0 ? 0 : maxY + o.cellH * 1.4
    leftover.forEach((id, i) =>
      pos.set(id, { x: minX + (i % cols) * o.cellW, y: top + o.cellH * Math.floor(i / cols) }),
    )
  }
  return pos
}

const NO_CHAPTER = '__none__'

export async function computeLayout(
  nodes: readonly LayoutNode[],
  edges: readonly LayoutEdge[],
  mode: LayoutMode,
  chapterOrder: readonly string[],
  options: Partial<LayoutOptions> = {},
  engine: DagreEngine = g6DagreEngine,
): Promise<Positions> {
  const o: LayoutOptions = { ...COMPACT_OPTIONS, ...options }
  if (nodes.length === 0) return new Map()
  const known = new Set(nodes.map((n) => n.id))
  const valid = edges.filter((e) => known.has(e.source) && known.has(e.target))

  if (mode === 'all') {
    // 现状：全部关系参与；孤立节点由引擎自己放在第一行
    return engine(nodes.map((n) => n.id), valid, o)
  }
  if (mode === 'hier') return layoutGroup([...nodes], valid, o, engine)

  // chapter：每章单独布局，再按课程顺序排成分区
  const groups = new Map<string, LayoutNode[]>()
  for (const n of nodes) {
    const key = n.chapter ?? NO_CHAPTER
    groups.set(key, [...(groups.get(key) ?? []), n])
  }
  // 目录里有的章节按目录顺序；目录里没有的章节按出现顺序跟在后面；未归章最后。节点不能因为目录缺失而消失
  const listed = chapterOrder.filter((c) => groups.has(c))
  const unlisted = [...groups.keys()].filter((c) => c !== NO_CHAPTER && !chapterOrder.includes(c))
  const keys = [...listed, ...unlisted, ...(groups.has(NO_CHAPTER) ? [NO_CHAPTER] : [])]

  const blocks: Array<{ pos: Positions; w: number; h: number }> = []
  for (const key of keys) {
    const pos = await layoutGroup(groups.get(key)!, valid, o, engine)
    let minX = Infinity
    let minY = Infinity
    let maxX = -Infinity
    let maxY = -Infinity
    for (const p of pos.values()) {
      minX = Math.min(minX, p.x)
      minY = Math.min(minY, p.y)
      maxX = Math.max(maxX, p.x)
      maxY = Math.max(maxY, p.y)
    }
    const normalized: Positions = new Map([...pos].map(([id, p]) => [id, { x: p.x - minX, y: p.y - minY }]))
    blocks.push({ pos: normalized, w: maxX - minX, h: maxY - minY })
  }

  // 行式排版：按课程顺序从左到右、从上到下；试遍各种行宽，选「适应视口时缩放最大」的一种
  const pack = (targetW: number) => {
    const placed: Array<[string, { x: number; y: number }]> = []
    let x = 0
    let y = 0
    let rowH = 0
    let maxX = 0
    for (const b of blocks) {
      if (x > 0 && x + b.w > targetW) {
        x = 0
        y += rowH + o.laneGap
        rowH = 0
      }
      for (const [id, p] of b.pos) placed.push([id, { x: x + p.x, y: y + p.y }])
      maxX = Math.max(maxX, x + b.w)
      x += b.w + o.laneGap
      rowH = Math.max(rowH, b.h)
    }
    const fit = Math.min(o.viewport[0] / (maxX + 200), o.viewport[1] / (y + rowH + 200))
    return { placed, fit }
  }
  const widest = Math.max(...blocks.map((b) => b.w), 1)
  let best = pack(widest)
  for (let cols = 2; cols <= blocks.length; cols += 1) {
    const width = blocks.slice(0, cols).reduce((sum, b) => sum + b.w, 0) + (cols - 1) * o.laneGap
    const candidate = pack(Math.max(widest, width))
    if (candidate.fit > best.fit) best = candidate
  }
  return new Map(best.placed)
}

// ------------------------------------------------------------------ 度量（验收与测试用）

export interface LayoutMetrics {
  bbox: [number, number]
  /** 宽 / 高 */
  aspect: number
  /** 适应给定视口时的缩放（不含 0.2 的下限，便于比较） */
  fitZoom: number
  /** 最近的两个节点中心距；小于节点直径（36）说明重叠 */
  minNodeDist: number
  chapters: { n: number; fitOneScreen: number }
  /** 章内先修边是否向下 */
  prereqWithinDownShare: number
}

export function layoutMetrics(
  pos: Positions,
  nodes: readonly LayoutNode[],
  edges: readonly LayoutEdge[],
  viewport: readonly [number, number] = COMPACT_OPTIONS.viewport,
  readableZoom = 0.9,
): LayoutMetrics {
  const pts = [...pos.values()]
  const xs = pts.map((p) => p.x)
  const ys = pts.map((p) => p.y)
  const W = Math.max(...xs) - Math.min(...xs)
  const H = Math.max(...ys) - Math.min(...ys)
  let minDist = Infinity
  for (let i = 0; i < pts.length; i += 1) {
    for (let j = i + 1; j < pts.length; j += 1) {
      minDist = Math.min(minDist, Math.hypot(pts[i]!.x - pts[j]!.x, pts[i]!.y - pts[j]!.y))
    }
  }
  const chapterOf = new Map(nodes.map((n) => [n.id, n.chapter]))
  const byChapter = new Map<string, string[]>()
  for (const n of nodes) byChapter.set(n.chapter ?? NO_CHAPTER, [...(byChapter.get(n.chapter ?? NO_CHAPTER) ?? []), n.id])
  const vw = viewport[0] / readableZoom
  const vh = viewport[1] / readableZoom
  let fits = 0
  for (const ids of byChapter.values()) {
    const px = ids.map((i) => pos.get(i)!.x)
    const py = ids.map((i) => pos.get(i)!.y)
    if (Math.max(...px) - Math.min(...px) <= vw && Math.max(...py) - Math.min(...py) <= vh) fits += 1
  }
  const within = edges.filter((e) => e.type === 'PREREQUISITE' && chapterOf.get(e.source) === chapterOf.get(e.target))
  const down = within.filter((e) => pos.get(e.target)!.y > pos.get(e.source)!.y).length
  return {
    bbox: [Math.round(W), Math.round(H)],
    aspect: +(W / Math.max(H, 1)).toFixed(2),
    fitZoom: Math.min(viewport[0] / (W + 200), viewport[1] / (H + 200)),
    minNodeDist: Math.round(minDist),
    chapters: { n: byChapter.size, fitOneScreen: fits },
    prereqWithinDownShare: +(down / Math.max(within.length, 1)).toFixed(2),
  }
}
```

- [ ] **Step 4: 运行，确认通过，并类型检查**

Run: `npm --prefix src/frontend run test -- --run graph-chapter-layout && npm --prefix src/frontend run type-check`
Expected: 17 passed；type-check 退出码 0

- [ ] **Step 5: 提交（仅在用户授权后）**

```bash
git add src/frontend/src/graph/chapterLayout.ts tests/frontend/graph-chapter-layout.test.ts
git commit -m "feat(frontend): add chapter-partition graph layout"
```

---

### Task 6: 聚焦状态

**Files:**
- Create: `src/frontend/src/graph/focusStates.ts`
- Test: `tests/frontend/graph-focus-states.test.ts`

**Interfaces:**
- Produces: `neighborsOf(edges, nodeId): { nodes: Set; edges: Set }`；`applyFocusStates(graph: { nodes; edges }, focus: { selectedId: string | null; matchedIds: ReadonlySet<string>; chapterIds: ReadonlySet<string> | null; fade: 'standard' | 'strong' }): { nodes; edges }`（把 `selected/neighbor/dimmed|faded/match` 与边的 `active/scoped/faded` 追加进元素 `states`，不修改输入）；`hoverStateMap({ nodes; edges; hoverId; selectedId }): Record<string, string[]>`（悬停瞬时状态，只给 `setElementState` 用）；`labelScore({ states; importance?; pathOrder? }): number`；`isForcedLabel(states): boolean`（**只有 `selected` 为真**）。
- 元素 id 就是 G6 元素 id（节点 `kp:<id>`，边 `rel:<id>`）。

- [ ] **Step 1: 写测试**

`tests/frontend/graph-focus-states.test.ts`：

```ts
import { describe, expect, it } from 'vitest'
import {
  applyFocusStates,
  hoverStateMap,
  isForcedLabel,
  labelScore,
  neighborsOf,
  type FocusEdgeLike,
  type FocusInput,
  type FocusNodeLike,
} from '../../src/frontend/src/graph/focusStates'

const node = (id: string, states?: string[]): FocusNodeLike => (states ? { id, states } : { id })
const edge = (id: string, source: string, target: string, states?: string[]): FocusEdgeLike =>
  states ? { id, source, target, states } : { id, source, target }

//   a → b → c      d（孤立）
const nodes = [node('a'), node('b'), node('c'), node('d')]
const edges = [edge('ab', 'a', 'b'), edge('bc', 'b', 'c')]

const none: FocusInput = { selectedId: null, matchedIds: new Set(), chapterIds: null, fade: 'standard' }
const statesOf = (list: Array<{ id: string; states?: string[] }>) => Object.fromEntries(list.map((x) => [x.id, x.states ?? []]))

describe('neighborsOf', () => {
  it('一阶邻居与相关边，不分方向，不含自己', () => {
    const { nodes: n, edges: e } = neighborsOf(edges, 'b')
    expect([...n].sort()).toEqual(['a', 'c'])
    expect([...e].sort()).toEqual(['ab', 'bc'])
    expect(neighborsOf(edges, 'd').nodes.size).toBe(0)
  })
})

describe('applyFocusStates：预览/选中', () => {
  it('选中节点 selected，邻居 neighbor，其余 dimmed（标准淡化）；相关边 active，其余边不动', () => {
    const out = applyFocusStates({ nodes, edges }, { ...none, selectedId: 'a' })
    expect(statesOf(out.nodes)).toEqual({ a: ['selected'], b: ['neighbor'], c: ['dimmed'], d: ['dimmed'] })
    expect(statesOf(out.edges)).toEqual({ ab: ['active'], bc: [] })
  })

  it('强淡化（strong）：非相关节点与非相关边用 faded', () => {
    const out = applyFocusStates({ nodes, edges }, { ...none, selectedId: 'a', fade: 'strong' })
    expect(statesOf(out.nodes).c).toEqual(['faded'])
    expect(statesOf(out.edges)).toEqual({ ab: ['active'], bc: ['faded'] })
  })

  it('没有预览/选中、没有章节、没有命中时原样返回（同一个对象，不产生多余的重绘）', () => {
    const out = applyFocusStates({ nodes, edges }, none)
    expect(out.nodes[0]).toBe(nodes[0])
    expect(out.edges[0]).toBe(edges[0])
  })

  it('保留已有状态并追加在后面；不重复添加', () => {
    const out = applyFocusStates(
      { nodes: [node('a', ['mastered', 'selected']), node('b', ['learning'])], edges: [edge('ab', 'a', 'b')] },
      { ...none, selectedId: 'a' },
    )
    expect(statesOf(out.nodes)).toEqual({ a: ['mastered', 'selected'], b: ['learning', 'neighbor'] })
  })
})

describe('applyFocusStates：章节聚焦与搜索命中', () => {
  const chapter = new Set(['a', 'b'])

  it('非本章节点 dimmed，本章节点 match；与本章节点相连的边 scoped', () => {
    const out = applyFocusStates({ nodes, edges }, { ...none, chapterIds: chapter })
    expect(statesOf(out.nodes)).toEqual({ a: ['match'], b: ['match'], c: ['dimmed'], d: ['dimmed'] })
    expect(statesOf(out.edges)).toEqual({ ab: ['scoped'], bc: ['scoped'] })
  })

  it('有预览/选中时预览规则优先，章节成员仍带 match', () => {
    const out = applyFocusStates({ nodes, edges }, { ...none, chapterIds: chapter, selectedId: 'c' })
    const s = statesOf(out.nodes)
    expect(s.c).toEqual(['selected'])
    expect(s.a).toEqual(['dimmed', 'match'])
    expect(s.b).toEqual(['neighbor', 'match'])
  })

  it('搜索命中只加 match，不淡化其他节点', () => {
    const out = applyFocusStates({ nodes, edges }, { ...none, matchedIds: new Set(['c']) })
    expect(statesOf(out.nodes)).toEqual({ a: [], b: [], c: ['match'], d: [] })
  })

  it('不修改输入', () => {
    const snapshot = JSON.stringify({ nodes, edges })
    applyFocusStates({ nodes, edges }, { ...none, selectedId: 'a', chapterIds: chapter })
    expect(JSON.stringify({ nodes, edges })).toBe(snapshot)
  })
})

describe('hoverStateMap：悬停（瞬时强淡化）', () => {
  it('悬停节点 hovered，直接相邻 hoverRelated，其余 hoverFaded；相关边 active，其余边 hoverFaded', () => {
    const map = hoverStateMap({ nodes, edges, hoverId: 'a', selectedId: null })
    expect(map).toMatchObject({ a: ['hovered'], b: ['hoverRelated'], c: ['hoverFaded'], d: ['hoverFaded'], ab: ['active'], bc: ['hoverFaded'] })
  })

  it('悬停状态排在基础状态之后（悬停赢），基础状态保留', () => {
    const map = hoverStateMap({ nodes: [node('a', ['mastered']), node('b', ['dimmed'])], edges: [edge('ab', 'a', 'b')], hoverId: 'a', selectedId: null })
    expect(map.a).toEqual(['mastered', 'hovered'])
    expect(map.b).toEqual(['dimmed', 'hoverRelated'])
  })

  it('被预览/选中的节点即使与悬停节点无关也不被淡化（用户不会丢掉自己的焦点）', () => {
    const map = hoverStateMap({ nodes, edges, hoverId: 'a', selectedId: 'd' })
    expect(map.d).toEqual([])
    expect(map.c).toEqual(['hoverFaded'])
  })

  it('hoverId 为 null：只返回基础状态（用于悬停结束后恢复）', () => {
    const map = hoverStateMap({ nodes: [node('a', ['selected'])], edges: [edge('ab', 'a', 'b', ['active'])], hoverId: null, selectedId: 'a' })
    expect(map).toEqual({ a: ['selected'], ab: ['active'] })
  })

  it('不重复添加已有的 active', () => {
    const map = hoverStateMap({ nodes, edges: [edge('ab', 'a', 'b', ['active'])], hoverId: 'a', selectedId: null })
    expect(map.ab).toEqual(['active'])
  })
})

describe('labelScore 与强制显示', () => {
  it('预览/选中 > 搜索命中与章节成员 > 推荐项 > 邻居 > importance', () => {
    const selected = labelScore({ states: ['selected'] })
    const matched = labelScore({ states: ['match'] })
    const recommended = labelScore({ states: [], pathOrder: 1 })
    const neighbor = labelScore({ states: ['neighbor'] })
    const important = labelScore({ states: [], importance: 1 })
    expect(selected).toBeGreaterThan(matched)
    expect(matched).toBeGreaterThan(recommended)
    expect(recommended).toBeGreaterThan(neighbor)
    expect(neighbor).toBeGreaterThan(important)
  })

  it('分数是累加的：章节成员里的推荐项（match + 推荐）仍然低于被选中的节点', () => {
    const memberRecommended = labelScore({ states: ['match'], pathOrder: 2, importance: 1 })
    expect(memberRecommended).toBeLessThan(labelScore({ states: ['selected'] }))
  })

  it('强制显示只看是否被预览/选中，不看分数：高分的章节成员也不强制', () => {
    expect(isForcedLabel(['selected'])).toBe(true)
    expect(isForcedLabel(['match', 'neighbor'])).toBe(false)
    expect(isForcedLabel([])).toBe(false)
  })

  it('缺省值：没有 importance、没有推荐序号时为 0', () => {
    expect(labelScore({ states: [] })).toBe(0)
  })
})
```

- [ ] **Step 2: 运行，确认失败**

Run: `npm --prefix src/frontend run test -- --run graph-focus-states`
Expected: FAIL

- [ ] **Step 3: 实现**

`src/frontend/src/graph/focusStates.ts`：

```ts
/**
 * 聚焦状态（设计规格 §3.4、§3.4a、§4.2、§7）。纯函数，不依赖 G6 与 Vue。
 *
 * 持久状态（预览/选中、章节聚焦）由 `applyFocusStates` 写进元素的 `states`，随数据交给画布；
 * 瞬时状态（悬停）由画布生命周期用 `hoverStateMap` 现算，只调 `setElementState`，不重绘数据。
 *
 * 状态只带名字，颜色只在 `buildGraphOptions` 定义一处。所有函数都不修改输入。
 */

/** 节点上由聚焦逻辑产生的状态（`selected` 沿用既有名字） */
export type FocusNodeState = 'selected' | 'neighbor' | 'dimmed' | 'faded' | 'match' | 'hovered' | 'hoverRelated' | 'hoverFaded'
/** 边上由聚焦逻辑产生的状态 */
export type FocusEdgeState = 'active' | 'scoped' | 'faded' | 'hoverFaded'

export interface FocusNodeLike {
  id: string
  states?: string[]
}
export interface FocusEdgeLike {
  id: string
  source: string
  target: string
  states?: string[]
}

export interface FocusInput {
  /** 被预览或选中的节点元素 id；没有则为 null */
  selectedId: string | null
  /** 搜索命中的节点元素 id */
  matchedIds: ReadonlySet<string>
  /** 定位的章节的节点元素 id；没有则为 null */
  chapterIds: ReadonlySet<string> | null
  /**
   * 预览/选中时非相关内容的淡化强度：
   * standard 只降填充饱和度（持久状态，边框与标签仍满足对比度，默认）；
   * strong 为 Obsidian 式（退成近画布色小点），仅供对比，持久状态默认不用。
   */
  fade: 'standard' | 'strong'
}

/** 一个节点的一阶邻居与相关边（不分方向） */
export function neighborsOf(
  edges: ReadonlyArray<{ id: string; source: string; target: string }>,
  nodeId: string,
): { nodes: Set<string>; edges: Set<string> } {
  const nodes = new Set<string>()
  const edgeIds = new Set<string>()
  for (const e of edges) {
    if (e.source === nodeId || e.target === nodeId) {
      edgeIds.add(e.id)
      nodes.add(e.source === nodeId ? e.target : e.source)
    }
  }
  nodes.delete(nodeId)
  return { nodes, edges: edgeIds }
}

/** 追加状态并去重，保持已有顺序 */
function withStates(existing: readonly string[] | undefined, extra: readonly string[]): string[] {
  const out = [...(existing ?? [])]
  for (const s of extra) if (!out.includes(s)) out.push(s)
  return out
}

/**
 * 把预览/选中、章节聚焦写进 `states`。
 * - 有预览/选中：节点 `selected`；一阶邻居 `neighbor`；其余 `dimmed`（standard）或 `faded`（strong）；
 *   相关边 `active`，strong 下其余边 `faded`。
 * - 没有预览/选中、有章节聚焦：非本章节点 `dimmed`；与本章节点相连的边 `scoped`（恢复正常粗细）。
 * - 搜索命中与章节成员都带 `match`。
 */
export function applyFocusStates<N extends FocusNodeLike, E extends FocusEdgeLike>(
  graph: { nodes: readonly N[]; edges: readonly E[] },
  focus: FocusInput,
): { nodes: N[]; edges: E[] } {
  const sel = focus.selectedId
  const around = sel === null ? null : neighborsOf(graph.edges, sel)
  const scope = focus.chapterIds

  const nodes = graph.nodes.map((n) => {
    const extra: string[] = []
    if (sel !== null) {
      if (n.id === sel) extra.push('selected')
      else if (around!.nodes.has(n.id)) extra.push('neighbor')
      else extra.push(focus.fade === 'strong' ? 'faded' : 'dimmed')
    } else if (scope !== null && !scope.has(n.id)) {
      extra.push('dimmed')
    }
    if ((scope !== null && scope.has(n.id)) || focus.matchedIds.has(n.id)) extra.push('match')
    return extra.length === 0 ? n : { ...n, states: withStates(n.states, extra) }
  })

  const edges = graph.edges.map((e) => {
    const extra: string[] = []
    if (sel !== null) {
      if (around!.edges.has(e.id)) extra.push('active')
      else if (focus.fade === 'strong') extra.push('faded')
    } else if (scope !== null && (scope.has(e.source) || scope.has(e.target))) {
      extra.push('scoped')
    }
    return extra.length === 0 ? e : { ...e, states: withStates(e.states, extra) }
  })
  return { nodes, edges }
}

/**
 * 悬停（瞬时强淡化，Obsidian 式）：返回「基础状态 + 悬停状态」的完整表，直接交给 `setElementState`。
 * 悬停状态排在基础状态之后，所以悬停时它赢；被预览/选中的节点即使与悬停节点无关也保留，用户不会丢掉自己的焦点。
 * `hoverId` 为 null 时只返回基础状态（用于悬停结束后恢复）。
 */
export function hoverStateMap(input: {
  nodes: readonly FocusNodeLike[]
  edges: readonly FocusEdgeLike[]
  hoverId: string | null
  selectedId: string | null
}): Record<string, string[]> {
  const { nodes, edges, hoverId, selectedId } = input
  const around = hoverId === null ? null : neighborsOf(edges, hoverId)
  const out: Record<string, string[]> = {}
  for (const n of nodes) {
    const extra: string[] = []
    if (around !== null) {
      if (n.id === hoverId) extra.push('hovered')
      else if (around.nodes.has(n.id)) extra.push('hoverRelated')
      else if (n.id !== selectedId) extra.push('hoverFaded')
    }
    out[n.id] = withStates(n.states, extra)
  }
  for (const e of edges) {
    const extra: string[] = []
    if (around !== null) extra.push(around.edges.has(e.id) ? 'active' : 'hoverFaded')
    out[e.id] = withStates(e.states, extra)
  }
  return out
}

/**
 * 标签优先级（`planLabels` 的排序依据）：预览/选中 > 搜索命中与章节成员 > 推荐项 > 选中节点的邻居 > importance。
 * 分数是累加的，所以**不能**用分数阈值判断「强制显示」：强制只看 `states` 是否含 `selected`。
 */
export function labelScore(input: {
  states: readonly string[]
  /** 契约的 importance（0–1）；缺省视为 0 */
  importance?: number
  /** 推荐序号（1 起）；没有则为 undefined */
  pathOrder?: number
}): number {
  const { states } = input
  let score = (input.importance ?? 0) * 100
  if (input.pathOrder !== undefined) score += 300
  if (states.includes('match')) score += 500
  if (states.includes('neighbor')) score += 200
  if (states.includes('selected')) score += 1000
  return score
}

/** 强制显示标签：只有被预览/选中的那个节点 */
export function isForcedLabel(states: readonly string[]): boolean {
  return states.includes('selected')
}
```

- [ ] **Step 4: 运行第一阶段全部六组，确认通过**

Run: `npm --prefix src/frontend run test -- --run graph-theme graph-scale graph-label-plan graph-fit graph-chapter-layout graph-focus-states`
Expected: 6 个文件、76 条用例通过

- [ ] **Step 5: 提交（仅在用户授权后）**

```bash
git add src/frontend/src/graph/focusStates.ts tests/frontend/graph-focus-states.test.ts
git commit -m "feat(frontend): add preview/hover/chapter focus state computation"
```

---

## 第二阶段：适配层与画布样式

### Task 7: 展示数据（presentation）、关系样式与适配层类型

**Files:**
- Create: `src/frontend/src/graph/presentation.ts`
- Modify: `src/frontend/src/graph/adapter.ts`（`RELATION_STYLES` 颜色线宽；`G6NodeData`/`G6EdgeData` 增加可选展示字段）
- Modify: `src/frontend/src/graph/theme.ts`（增加 `GRAPH_FONT`）
- Test: `tests/frontend/graph-presentation.test.ts`；`tests/frontend/graph-theme.test.ts`（补一条字体断言）

**Interfaces:**
- Consumes: `ScaleFloors`、`NO_FLOORS`（Task 2）、`GRAPH_COLORS`（Task 1）。
- Produces（后续任务依赖的精确签名）：
  ```ts
  // presentation.ts
  export interface ViewState { labelK: number; floors: ScaleFloors; labelShown: ReadonlySet<string> | null }
  export const INITIAL_VIEW: Readonly<ViewState>
  export type MasteryKind = 'mastered' | 'learning' | 'unknown'
  export function masteryOfStates(states: readonly string[] | undefined): MasteryKind
  export function decorateNodeData(id: string, data: G6NodeData, states: readonly string[] | undefined, view: ViewState): G6NodeData
  export function decorateEdge(edge: { data: G6EdgeData; style: G6EdgeStyle; states?: readonly string[] }, cross: boolean, view: ViewState): { data: G6EdgeData; style: G6EdgeStyle }
  export function chapterOfNodes(nodes: ReadonlyArray<{ id: string; data: { chapterId: string | null } }>): Map<string, string | null>
  export function badgesFor(mastery: MasteryKind | undefined, nodeK: number): NodeBadgeStyleProps[] // 类型来自 @antv/g6
  export function nodeLabel(data: Pick<G6NodeData, 'name' | 'pathOrder'>): string // 推荐项前加序号「1. 」（L14）；原在 lifecycle.ts，Task 8 起由此导入并再导出
  export const MASTERY_TEXT: Readonly<Record<MasteryKind, string>> // 与 useLearning.MASTERY_LABELS 一致，有测试守着
  // theme.ts
  export const GRAPH_FONT: string
  // adapter.ts：G6NodeData 增加 k?/nk?/lw?/labelOn?/mastery?；G6EdgeData 增加 lw?/ak?/cross?/emph?/showLabel?
  ```
- 规则：`labelShown === null` 表示尚未排布（全部显示）；边的 `showLabel` 只在 `active` 状态为真；跨章边（两端 `chapterId` 不同）未被强调（`active`/`scoped`）时线宽取 1，被强调时取关系本身线宽；任何情况下线宽不低于 `floors.lwMin`。

- [ ] **Step 1: 写失败测试**

`tests/frontend/graph-presentation.test.ts`：

```ts
import { describe, expect, it } from 'vitest'
import type { G6EdgeData, G6EdgeStyle, G6NodeData } from '../../src/frontend/src/graph/adapter'
import {
  badgesFor,
  chapterOfNodes,
  decorateEdge,
  decorateNodeData,
  INITIAL_VIEW,
  masteryOfStates,
  nodeLabel,
  type ViewState,
} from '../../src/frontend/src/graph/presentation'
import { scaleFloors } from '../../src/frontend/src/graph/scale'

const data: G6NodeData = {
  kpId: 'a', name: '线性表', type: 'concept', level: 1, chapterId: 'c1',
  status: 'approved', confidence: 1, source: 'ai', locked: false,
}
const edgeData: G6EdgeData = {
  relationId: 'r1', type: 'PREREQUISITE', directed: true, status: 'approved', confidence: 1, source: 'ai', downgraded: false,
}
const edgeStyle: G6EdgeStyle = { stroke: '#5145CD', lineWidth: 2, lineDash: [], endArrow: true, labelText: '前置' }
const zoomedOut: ViewState = { labelK: 5, floors: scaleFloors(0.2, true), labelShown: new Set(['kp:a']) }

describe('decorateNodeData', () => {
  it('把标签放大系数、节点放大系数、线宽下限与标签开关写进 data，不改原对象', () => {
    const out = decorateNodeData('kp:a', data, ['mastered'], zoomedOut)
    expect(out).toMatchObject({ k: 5, nk: zoomedOut.floors.nodeK, lw: zoomedOut.floors.lwMin, labelOn: true, mastery: 'mastered' })
    expect(data).not.toHaveProperty('k')
  })
  it('不在显示集合里的节点关闭标签；尚未排布时全部显示', () => {
    expect(decorateNodeData('kp:b', { ...data, kpId: 'b' }, [], zoomedOut).labelOn).toBe(false)
    expect(decorateNodeData('kp:b', { ...data, kpId: 'b' }, [], INITIAL_VIEW).labelOn).toBe(true)
  })
})

describe('masteryOfStates', () => {
  it('掌握状态取自 states：mastered > learning > unknown', () => {
    expect(masteryOfStates(['mastered', 'recommended'])).toBe('mastered')
    expect(masteryOfStates(['learning'])).toBe('learning')
    expect(masteryOfStates(['notStarted'])).toBe('unknown')
    expect(masteryOfStates(undefined)).toBe('unknown')
  })
})

describe('badgesFor', () => {
  it('已掌握 ✓、学习中 ◐，未学习没有角标；字号与内边距随节点放大', () => {
    expect(badgesFor('unknown', 1)).toEqual([])
    expect(badgesFor(undefined, 1)).toEqual([])
    expect(badgesFor('mastered', 1)[0]).toMatchObject({ text: '✓', fontSize: 11 })
    expect(badgesFor('learning', 2)[0]).toMatchObject({ text: '◐', fontSize: 22 })
  })
})

describe('decorateEdge', () => {
  it('关系名标签只在 active 边上显示', () => {
    expect(decorateEdge({ data: edgeData, style: edgeStyle, states: ['active'] }, false, INITIAL_VIEW).style.labelText).toBe('前置')
    expect(decorateEdge({ data: edgeData, style: edgeStyle, states: [] }, false, INITIAL_VIEW).style.labelText).toBe('')
  })
  it('跨章边未被强调时画 1px，被强调（active/scoped）时恢复关系线宽', () => {
    expect(decorateEdge({ data: edgeData, style: edgeStyle, states: [] }, true, INITIAL_VIEW).style.lineWidth).toBe(1)
    expect(decorateEdge({ data: edgeData, style: edgeStyle, states: ['active'] }, true, INITIAL_VIEW).style.lineWidth).toBe(2)
    expect(decorateEdge({ data: edgeData, style: edgeStyle, states: ['scoped'] }, true, INITIAL_VIEW).style.lineWidth).toBe(2)
    expect(decorateEdge({ data: edgeData, style: edgeStyle, states: [] }, false, INITIAL_VIEW).style.lineWidth).toBe(2)
  })
  it('缩小时线宽不低于屏幕下限，箭头系数写进 data', () => {
    const out = decorateEdge({ data: edgeData, style: edgeStyle, states: [] }, true, zoomedOut)
    expect(out.style.lineWidth).toBe(Math.max(1, zoomedOut.floors.lwMin))
    expect(out.data).toMatchObject({ lw: zoomedOut.floors.lwMin, ak: zoomedOut.floors.arrowK, cross: true, emph: false, showLabel: false })
  })
  it('不修改输入（style.lineDash 是副本）', () => {
    const out = decorateEdge({ data: edgeData, style: { ...edgeStyle, lineDash: [6, 4] }, states: [] }, false, INITIAL_VIEW)
    expect(out.style.lineDash).toEqual([6, 4])
    expect(out.style.lineDash).not.toBe(edgeStyle.lineDash)
    expect(edgeData).not.toHaveProperty('cross')
  })
})

describe('chapterOfNodes', () => {
  it('元素 id → 章节 id，缺章节为 null', () => {
    const map = chapterOfNodes([
      { id: 'kp:a', data: { chapterId: 'c1' } },
      { id: 'kp:b', data: { chapterId: null } },
    ])
    expect(map.get('kp:a')).toBe('c1')
    expect(map.get('kp:b')).toBeNull()
  })
})

describe('nodeLabel', () => {
  it('推荐项前加序号「1. 」（L14），其余为名称', () => {
    expect(nodeLabel({ name: '栈', pathOrder: 2 })).toBe('2. 栈')
    expect(nodeLabel({ name: '栈' })).toBe('栈')
  })
})
```

在 `tests/frontend/graph-theme.test.ts` 的最后一个 `describe` 之后追加：

```ts
describe('字体', () => {
  it('图谱字体栈以中文无衬线优先，并带系统回退', () => {
    expect(GRAPH_FONT).toMatch(/PingFang SC/)
    expect(GRAPH_FONT).toMatch(/system-ui/)
  })
})
```

并把该文件顶部的 `from '../../src/frontend/src/graph/theme'` 导入列表里加上 `GRAPH_FONT`。

- [ ] **Step 2: 运行，确认失败**

Run: `npm --prefix src/frontend run test -- --run graph-presentation graph-theme`
Expected: FAIL（找不到 `graph/presentation`；`GRAPH_FONT` 未导出）

- [ ] **Step 3: 实现**

在 `src/frontend/src/graph/theme.ts` 末尾追加：

```ts
/** 图谱画布与 DOM 共用的字体栈（量文字宽度也用它，保证排布估算与渲染一致） */
export const GRAPH_FONT = "'PingFang SC','Hiragino Sans GB','Microsoft YaHei',system-ui,sans-serif"
```

`src/frontend/src/graph/adapter.ts`：把 `RELATION_STYLES` 改为（`label` 不变，`h03` 断言仍成立）：

```ts
export const RELATION_STYLES: Readonly<Record<RelationType, RelationStyle>> = Object.freeze({
  CONTAINS: style({ label: '包含', stroke: '#727A89', lineWidth: 1.5, lineDash: [], directed: true }),
  PREREQUISITE: style({ label: '前置', stroke: '#5145CD', lineWidth: 2, lineDash: [], directed: true }),
  RELATED_TO: style({ label: '相关', stroke: '#4C7480', lineWidth: 1.5, lineDash: [6, 4], directed: false }),
  EXAMPLE_OF: style({ label: '应用实例', stroke: '#906638', lineWidth: 1.5, lineDash: [2, 3], directed: true }),
})
```

并在同文件给两个数据接口追加可选的展示字段（适配层 `toG6Data` 不填，只有画布生命周期的增强模式填写）：

```ts
export interface G6NodeData {
  // ……原有字段不变……
  pathOrder?: number
  /** 展示字段（`graph/presentation.ts` 在增强模式下写入；适配层不填） */
  k?: number // 标签放大系数
  nk?: number // 节点放大系数
  lw?: number // 线宽屏幕下限（画布像素）
  labelOn?: boolean // 标签是否显示
  mastery?: 'mastered' | 'learning' | 'unknown'
}

export interface G6EdgeData {
  // ……原有字段不变……
  downgraded: boolean
  lw?: number
  ak?: number // 箭头放大系数
  cross?: boolean // 跨章关系
  emph?: boolean // 被预览/选中/章节聚焦涉及
  showLabel?: boolean
}
```

`src/frontend/src/graph/presentation.ts`：

```ts
import type { NodeBadgeStyleProps } from '@antv/g6'
import type { G6EdgeData, G6EdgeStyle, G6NodeData } from './adapter'
import { GRAPH_COLORS } from './theme'
import { NO_FLOORS, type ScaleFloors } from './scale'

/**
 * 展示数据（UI-GRAPH-PILOT-01）：G6 的样式回调只能读元素自己的 `data`，所以把"当前缩放档位、
 * 标签是否显示、掌握角标"这些随视口变化的量写进 `data`，由 `buildGraphOptions` 的回调读取。
 * 纯函数，不修改输入，不依赖 G6。
 */

export interface ViewState {
  /** 标签放大系数（缩小时让标签在屏幕上保持约 13px） */
  labelK: number
  /** 节点、线、箭头的屏幕下限 */
  floors: ScaleFloors
  /** 允许显示标签的节点元素 id；null 表示尚未排布（全部显示） */
  labelShown: ReadonlySet<string> | null
}

export const INITIAL_VIEW: Readonly<ViewState> = Object.freeze({ labelK: 1, floors: NO_FLOORS, labelShown: null })

export type MasteryKind = 'mastered' | 'learning' | 'unknown'

export function masteryOfStates(states: readonly string[] | undefined): MasteryKind {
  if (states?.includes('mastered')) return 'mastered'
  if (states?.includes('learning')) return 'learning'
  return 'unknown'
}

export function decorateNodeData(
  id: string,
  data: G6NodeData,
  states: readonly string[] | undefined,
  view: ViewState,
): G6NodeData {
  return {
    ...data,
    k: view.labelK,
    nk: view.floors.nodeK,
    lw: view.floors.lwMin,
    labelOn: view.labelShown === null ? true : view.labelShown.has(id),
    mastery: masteryOfStates(states),
  }
}

export function decorateEdge(
  edge: { data: G6EdgeData; style: G6EdgeStyle; states?: readonly string[] },
  cross: boolean,
  view: ViewState,
): { data: G6EdgeData; style: G6EdgeStyle } {
  const active = edge.states?.includes('active') ?? false
  const emph = active || (edge.states?.includes('scoped') ?? false)
  const lwMin = view.floors.lwMin
  return {
    data: { ...edge.data, lw: lwMin, ak: view.floors.arrowK, cross, emph, showLabel: active },
    style: {
      ...edge.style,
      lineDash: [...edge.style.lineDash],
      lineWidth: Math.max(cross && !emph ? 1 : edge.style.lineWidth, lwMin),
      labelText: active ? edge.style.labelText : '',
    },
  }
}

export function chapterOfNodes(
  nodes: ReadonlyArray<{ id: string; data: { chapterId: string | null } }>,
): Map<string, string | null> {
  return new Map(nodes.map((n) => [n.id, n.data.chapterId]))
}

/** 掌握角标：已掌握 ✓、学习中 ◐；未学习没有角标（详情、预览卡、列表用文字「未学习」） */
export function badgesFor(mastery: MasteryKind | undefined, nodeK: number): NodeBadgeStyleProps[] {
  if (mastery === 'mastered') {
    return [{ text: '✓', placement: 'right-top', fill: '#FFFFFF', backgroundFill: GRAPH_COLORS.ok, fontSize: 11 * nodeK, fontWeight: 700, padding: [1 * nodeK, 4 * nodeK] }]
  }
  if (mastery === 'learning') {
    return [{ text: '◐', placement: 'right-top', fill: '#FFFFFF', backgroundFill: GRAPH_COLORS.warn, fontSize: 11 * nodeK, padding: [1 * nodeK, 4 * nodeK] }]
  }
  return []
}

/** 节点标签：推荐项前加序号「1. 」（L14），其余为名称 */
export function nodeLabel(data: Pick<G6NodeData, 'name' | 'pathOrder'>): string {
  return data.pathOrder === undefined ? data.name : `${data.pathOrder}. ${data.name}`
}

/** 掌握状态的文字（预览卡、tooltip、列表）：颜色与角标之外必须有文字；与 `useLearning.MASTERY_LABELS` 一致（有测试守着） */
export const MASTERY_TEXT: Readonly<Record<MasteryKind, string>> = Object.freeze({
  mastered: '已掌握',
  learning: '学习中',
  unknown: '未学习',
})
```

- [ ] **Step 4: 运行，确认通过**

Run: `npm --prefix src/frontend run test -- --run graph-presentation graph-theme h03 && npm --prefix src/frontend run type-check`
Expected: 全部通过；type-check 退出码 0（`h03` 只比较 `RELATION_STYLES` 与边样式是否一致，颜色换了仍成立）

- [ ] **Step 5: 提交（仅在用户授权后）**

```bash
git add src/frontend/src/graph/presentation.ts src/frontend/src/graph/adapter.ts src/frontend/src/graph/theme.ts tests/frontend/graph-presentation.test.ts tests/frontend/graph-theme.test.ts
git commit -m "feat(frontend): add graph presentation data and refreshed relation styles"
```

---

### Task 8: `buildGraphOptions` 换新主题（节点、状态、边）

**Files:**
- Modify: `src/frontend/src/graph/lifecycle.ts`（`CanvasElementState`、`READABLE_ZOOM`、`buildGraphOptions`）
- Modify: `tests/frontend/h05.test.ts`、`tests/frontend/i06.test.ts`、`tests/frontend/l14.test.ts`（样式/状态名/缩放常量随设计变化的几处）
- Test: `tests/frontend/graph-options.test.ts`

**Interfaces:**
- Consumes: `GRAPH_COLORS`、`GRAPH_FONT`、`NODE_TYPE_FILL`、`NODE_TYPE_GLYPH`（Task 1/7）；`NODE_BASE_PX`、`READABLE_ZOOM`（Task 2）；`badgesFor`（Task 7）。
- Produces：
  - `CanvasElementState` 追加 `'neighbor' | 'match' | 'faded' | 'hovered' | 'hoverRelated' | 'hoverFaded' | 'active' | 'scoped'`。
  - `export { READABLE_ZOOM }`（从 `./scale` 再导出，`l13.test.ts` 的导入继续有效，值变为 0.9）。
  - `buildGraphOptions` 节点状态名（`Object.keys(...).sort()`）：`dimmed, faded, hoverFaded, hoverRelated, hovered, learning, lowConfidence, mastered, match, neighbor, notStarted, pathPrereq, pathUnlock, recommended, rejected, selected`；边状态名：`active, dimmed, faded, hoverFaded, lowConfidence, pathEdge, rejected, scoped`。
  - 样式回调读 `data.k / nk / lw / labelOn / mastery`（缺省时等价于 1 / 1 / 0 / true / 无角标），所以**不开增强模式时**节点只是换了新主题的静态样子。

- [ ] **Step 1: 写失败测试**

`tests/frontend/graph-options.test.ts`：

```ts
import { describe, expect, it } from 'vitest'
import type { G6Edge, G6Node } from '../../src/frontend/src/graph/adapter'
import { buildGraphOptions, READABLE_ZOOM } from '../../src/frontend/src/graph/lifecycle'
import { GRAPH_COLORS, NODE_TYPE_FILL, NODE_TYPE_GLYPH } from '../../src/frontend/src/graph/theme'

type Fn = (d: unknown) => unknown
function options() {
  return buildGraphOptions({ container: document.createElement('div'), width: 100, height: 100, data: { nodes: [], edges: [] } }) as unknown as {
    node: { style: Record<string, Fn | unknown>; state: Record<string, Record<string, unknown>> }
    edge: { style: Record<string, Fn | unknown>; state: Record<string, Record<string, unknown>> }
  }
}
function node(extra: Partial<G6Node['data']> = {}): G6Node {
  return {
    id: 'kp:a',
    data: { kpId: 'a', name: '线性表', type: 'concept', level: 1, chapterId: 'c1', status: 'approved', confidence: 1, source: 'ai', locked: false, ...extra },
  }
}
const call = (fn: unknown, d: unknown) => (fn as Fn)(d)

describe('buildGraphOptions 新主题', () => {
  it('可读缩放常量是 0.9，并仍由 lifecycle 导出', () => {
    expect(READABLE_ZOOM).toBe(0.9)
  })

  it('节点：类型填充 + 单字标记，不只靠颜色', () => {
    const s = options().node.style
    expect(call(s.fill, node({ type: 'theorem' }))).toBe(NODE_TYPE_FILL.theorem)
    expect(call(s.iconText, node({ type: 'method' }))).toBe(NODE_TYPE_GLYPH.method)
    expect(s.stroke).toBe(GRAPH_COLORS.nodeStroke)
  })

  it('节点尺寸、字号、行高、折行宽度随展示字段放大，缺省时是基础值', () => {
    const s = options().node.style
    expect(call(s.size, node())).toBe(36)
    expect(call(s.size, node({ nk: 2.5 }))).toBe(90)
    expect(call(s.labelFontSize, node({ k: 5 }))).toBe(65)
    expect(call(s.labelLineHeight, node({ k: 2 }))).toBe(34)
    expect(call(s.labelWordWrapWidth, node({ k: 2 }))).toBe(224)
  })

  it('标签用布尔 label 开关（labelVisibility 无效），默认显示', () => {
    const s = options().node.style
    expect(call(s.label, node())).toBe(true)
    expect(call(s.label, node({ labelOn: false }))).toBe(false)
  })

  it('标签文本保持 L14 的「1. 名称」格式；掌握状态用角标', () => {
    const s = options().node.style
    expect(call(s.labelText, node({ pathOrder: 2, name: '栈' }))).toBe('2. 栈')
    expect(call(s.badges, node({ mastery: 'mastered' }))).toHaveLength(1)
    expect(call(s.badges, node())).toEqual([])
  })

  it('状态名清单：持久状态与悬停瞬时状态', () => {
    const o = options()
    expect(Object.keys(o.node.state).sort()).toEqual([
      'dimmed', 'faded', 'hoverFaded', 'hoverRelated', 'hovered', 'learning', 'lowConfidence', 'mastered', 'match',
      'neighbor', 'notStarted', 'pathPrereq', 'pathUnlock', 'recommended', 'rejected', 'selected',
    ])
    expect(Object.keys(o.edge.state).sort()).toEqual([
      'active', 'dimmed', 'faded', 'hoverFaded', 'lowConfidence', 'pathEdge', 'rejected', 'scoped',
    ])
  })

  it('标准淡化（dimmed）换填充与边框，不用整体 opacity；强淡化与悬停淡化隐去标签与角标', () => {
    const { node: n, edge: e } = options()
    expect(n.state.dimmed).toMatchObject({ fill: GRAPH_COLORS.dimmedFill, stroke: GRAPH_COLORS.dimmedStroke })
    expect(n.state.dimmed).not.toHaveProperty('opacity')
    expect(n.state.hoverFaded).toMatchObject({ fill: GRAPH_COLORS.fadedFill, stroke: GRAPH_COLORS.fadedStroke, label: false, badge: false })
    expect(e.state.hoverFaded).toMatchObject({ stroke: GRAPH_COLORS.fadedEdge, lineWidth: 1, halo: false })
    expect(e.state.dimmed).not.toHaveProperty('opacity')
  })

  it('选中与搜索命中用靛紫外环；边的 active 状态显式关闭 G6 自带的光晕', () => {
    const { node: n, edge: e } = options()
    expect(n.state.selected).toMatchObject({ stroke: GRAPH_COLORS.accent })
    expect(n.state.match).toMatchObject({ stroke: GRAPH_COLORS.accent, labelFill: GRAPH_COLORS.accent })
    expect(e.state.active).toMatchObject({ halo: false })
  })

  it('边：箭头大小随展示字段，关系名标签带不透明底', () => {
    const s = options().edge.style
    const edge = { data: { ak: 2 } } as unknown as G6Edge
    expect(call(s.endArrowSize, edge)).toBe(18)
    expect(s.labelBackground).toBe(true)
    expect(s.labelBackgroundOpacity).toBe(1)
  })
})
```

- [ ] **Step 2: 运行，确认失败**

Run: `npm --prefix src/frontend run test -- --run graph-options`
Expected: FAIL（`READABLE_ZOOM` 仍是 0.7；状态名不符；回调不存在）

- [ ] **Step 3: 实现**

在 `src/frontend/src/graph/lifecycle.ts` 顶部导入区追加，并删除本文件里 `export const READABLE_ZOOM = 0.7` 那一行（连同它上面解释 0.7 的注释，改成指向 `scale.ts`）：

```ts
import type { G6Edge, G6EdgeData, G6Node, G6NodeData } from './adapter'
import { nodeElementId } from './adapter'
import { badgesFor, nodeLabel } from './presentation'
import { NODE_BASE_PX, READABLE_ZOOM } from './scale'
import { GRAPH_COLORS, GRAPH_FONT, NODE_TYPE_FILL, NODE_TYPE_GLYPH } from './theme'

/** 可读缩放见 `graph/scale.ts`（0.9：新标签 13px，0.7 时只有约 9px）；这里再导出，保持既有导入路径有效 */
export { READABLE_ZOOM }
/** 节点标签函数已移到 `graph/presentation.ts`（增强模式的标签排布也要用）；这里再导出，`l14.test.ts` 等既有导入继续有效 */
export { nodeLabel }
```

（原先的 `import { nodeElementId, type G6Edge, type G6Node } from './adapter'` 与上面合并，不要重复导入。同时**删除**本文件里原有的 `export function nodeLabel(...)` 函数定义——它已移到 `presentation.ts`。）

`CanvasElementState` 联合追加（保持其余成员与注释）：

```ts
  | 'dimmed'
  | 'pathEdge'
  // UI-GRAPH-PILOT-01 聚焦与悬停状态（`graph/focusStates.ts` 计算；颜色只在 `buildGraphOptions` 定义一处）
  | 'neighbor'
  | 'match'
  | 'faded'
  | 'hovered'
  | 'hoverRelated'
  | 'hoverFaded'
  | 'active'
  | 'scoped'
```

把 `buildGraphOptions` 整个函数替换为：

```ts
const nd = (d: unknown): G6NodeData => (d as G6Node).data
const ed = (d: unknown): G6EdgeData => (d as G6Edge).data
const labelK = (d: unknown): number => nd(d).k ?? 1
const nodeK = (d: unknown): number => nd(d).nk ?? 1
const lwMin = (d: unknown): number => nd(d).lw ?? 0

/** 默认建图参数：新主题（浅色画布、类型填充 + 单字标记、掌握角标）；布局、缩放、拖拽与平行边处理沿用 H04/H05 */
export function buildGraphOptions(init: CanvasGraphInit): GraphOptions {
  const C = GRAPH_COLORS
  return {
    container: init.container,
    width: init.width,
    height: init.height,
    data: init.data as unknown as GraphData,
    autoFit: 'view',
    padding: 40,
    animation: false,
    zoomRange: [0.2, 4],
    node: {
      type: 'circle',
      style: {
        size: (d: unknown) => NODE_BASE_PX * nodeK(d),
        fill: (d: unknown) => NODE_TYPE_FILL[nd(d).type],
        stroke: C.nodeStroke,
        lineWidth: (d: unknown) => Math.max(1.5, lwMin(d)),
        iconText: (d: unknown) => NODE_TYPE_GLYPH[nd(d).type],
        iconFontSize: (d: unknown) => 14 * nodeK(d),
        iconFontWeight: 500,
        iconFill: C.text,
        iconFontFamily: GRAPH_FONT,
        labelText: (d: unknown) => nodeLabel(nd(d)),
        labelPlacement: 'bottom',
        // G6 节点的 label 是布尔开关：false 时整个标签不绘制（`labelVisibility` 无效）
        label: (d: unknown) => nd(d).labelOn !== false,
        labelFontSize: (d: unknown) => 13 * labelK(d),
        // 字号随缩放放大时行高必须同步，否则多行标签的两行会叠在一起
        labelLineHeight: (d: unknown) => Math.round(13 * labelK(d) * 1.3),
        labelFontWeight: 500,
        labelFill: C.text,
        labelFontFamily: GRAPH_FONT,
        labelWordWrap: true,
        labelWordWrapWidth: (d: unknown) => 112 * labelK(d),
        labelMaxLines: 2,
        labelTextOverflow: 'ellipsis',
        labelOffsetY: (d: unknown) => 4 * labelK(d),
        // 关系线从标签下方穿过时不应像删除线：标签带与画布同色的不透明底
        labelBackground: true,
        labelBackgroundFill: C.canvas,
        labelBackgroundOpacity: 0.94,
        labelPadding: [1, 3],
        badges: (d: unknown) => badgesFor(nd(d).mastery, nodeK(d)),
      },
      // 多个状态按 states 数组顺序叠加：审核/学习状态在前，聚焦状态居中，选中在后，悬停瞬时状态最后
      state: {
        rejected: { opacity: 0.4, stroke: '#7F8695', lineDash: [4, 3] },
        lowConfidence: { stroke: C.warn, lineDash: [4, 3] },
        // I06：掌握状态色只在这里定义；元素只带状态名，角标由 `badgesFor` 画（颜色之外还有 ✓/◐ 与文字）
        mastered: { stroke: C.ok, lineWidth: 2 },
        learning: { stroke: C.warn, lineWidth: 2 },
        notStarted: { stroke: C.nodeStroke },
        recommended: { stroke: C.accent, lineWidth: 3 },
        // L14 学习路径：未满足的前置（虚线）、之后解锁（点线）；与当前路径无关用 dimmed（标准淡化）
        pathPrereq: { stroke: C.warn, lineWidth: 2.5, lineDash: [4, 3] },
        pathUnlock: { stroke: C.accent, lineWidth: 2, lineDash: [2, 3] },
        // 标准淡化：降填充饱和度，边框 ≥3:1、标签保留（不使用整体 opacity）
        dimmed: { fill: C.dimmedFill, stroke: C.dimmedStroke, labelFill: '#545967', iconFill: '#545967' },
        // 强淡化（Obsidian 式，仅供对比）：近底色小点；标签由排布函数直接隐藏
        faded: { fill: C.fadedFill, stroke: C.fadedStroke, lineWidth: 1, iconFill: C.fadedIcon, halo: false },
        neighbor: { stroke: C.accent, lineWidth: (d: unknown) => Math.max(2, lwMin(d) * 1.5) },
        selected: {
          stroke: C.accent,
          lineWidth: (d: unknown) => Math.max(2.5, lwMin(d) * 2),
          halo: true,
          haloStroke: C.accent,
          haloLineWidth: (d: unknown) => Math.max(5, lwMin(d) * 3),
          haloStrokeOpacity: 0.22,
          labelFontWeight: 700,
        },
        // 搜索命中 / 章节定位：靛紫外环 + 标签加粗改靛紫，不用淡紫色底块
        match: { stroke: C.accent, lineWidth: (d: unknown) => Math.max(2.5, lwMin(d) * 2), labelFill: C.accent, labelFontWeight: 700 },
        // 悬停（瞬时，强淡化）：悬停节点与其直接相邻保持清楚，其余退成近底色小点并隐去标签与角标
        hovered: { stroke: C.accent, lineWidth: (d: unknown) => Math.max(2.5, lwMin(d) * 2), labelFontWeight: 700 },
        hoverRelated: { stroke: C.accent, lineWidth: (d: unknown) => Math.max(2, lwMin(d) * 1.5) },
        hoverFaded: { fill: C.fadedFill, stroke: C.fadedStroke, lineWidth: 1, iconFill: C.fadedIcon, halo: false, label: false, badge: false },
      },
    },
    edge: {
      // 不指定 type：增强模式（章节布局）由 `Task 9` 设为 cubic-vertical；平行边转换会把成组的边改为曲线
      style: {
        endArrowSize: (d: unknown) => 9 * (ed(d).ak ?? 1),
        labelFontSize: 12,
        labelFill: C.text,
        labelFontFamily: GRAPH_FONT,
        labelBackground: true,
        labelBackgroundFill: C.panel,
        labelBackgroundOpacity: 1,
        labelPadding: [1, 5],
      },
      state: {
        rejected: { opacity: 0.3 },
        lowConfidence: { opacity: 0.6 },
        pathEdge: { stroke: C.accent, lineWidth: 3.5, halo: false },
        // 与关系线重合的状态不再用 opacity；G6 内置 active 状态自带灰色光晕，必须显式关闭
        active: { lineWidth: (d: unknown) => Math.max(3, (ed(d).lw ?? 0) * 2.5), halo: false },
        scoped: { lineWidth: (d: unknown) => Math.max(2, ed(d).lw ?? 0), halo: false },
        dimmed: { stroke: C.fadedEdge, lineWidth: 1, halo: false },
        faded: { stroke: C.fadedEdge, lineWidth: 1, halo: false },
        hoverFaded: { stroke: C.fadedEdge, lineWidth: 1, halo: false, label: false },
      },
    },
    layout: layoutOptions(init.layout ?? 'hierarchical'),
    behaviors: ['zoom-canvas', 'drag-canvas', 'drag-element'],
    // 同一对知识点间可同时有前置与相关等多条关系，分开画避免重叠
    transforms: ['process-parallel-edges'],
  }
}
```

`layoutOptions` 与其余代码不动（既有 `h05` 对 `antv-dagre` 的断言继续成立；章节布局在 Task 9 以 `positions` 选项单独接入）。

更新既有测试里**随设计变化**的期望（每处都写明原因，不放宽其他断言）：

`tests/frontend/h05.test.ts`（用例「节点定义选中/驳回/低置信度与 I06 的四个学习状态样式，边定义驳回与低置信度」，约 L354–372）——状态名随设计追加聚焦与悬停状态。把该用例里**从注释 `// L14 追加学习路径状态：…` 起，到边状态断言 `expect(Object.keys(options.edge?.state ?? {}).sort()).toEqual(['dimmed', 'lowConfidence', 'pathEdge', 'rejected'])` 止**的整段替换为：

```ts
    // UI-GRAPH-PILOT-01 在同一 `state` 表追加聚焦与悬停状态；边增加 active/scoped/faded/hoverFaded，dimmed 不再用 opacity
    expect(Object.keys(options.node?.state ?? {}).sort()).toEqual([
      'dimmed', 'faded', 'hoverFaded', 'hoverRelated', 'hovered', 'learning', 'lowConfidence', 'mastered', 'match',
      'neighbor', 'notStarted', 'pathPrereq', 'pathUnlock', 'recommended', 'rejected', 'selected',
    ])
    expect(Object.keys(options.edge?.state ?? {}).sort()).toEqual([
      'active', 'dimmed', 'faded', 'hoverFaded', 'lowConfidence', 'pathEdge', 'rejected', 'scoped',
    ])
```

`tests/frontend/i06.test.ts`（用例「画布为四个学习状态定义了样式……」，约 L378–388）：把**从注释 `// L14 追加的学习路径状态（dimmed/pathPrereq/pathUnlock）另见 l14.test.ts` 起，到 `expect(nodeState.mastered).toMatchObject({ stroke: '#52c41a' })` 止**的整段替换为：

```ts
    // 状态名清单随 UI-GRAPH-PILOT-01 追加；掌握状态色改用图谱主题的成功色（并有 ✓ 角标，见 graph-options.test.ts）
    expect(Object.keys(nodeState).sort()).toEqual([
      'dimmed', 'faded', 'hoverFaded', 'hoverRelated', 'hovered', 'learning', 'lowConfidence', 'mastered', 'match',
      'neighbor', 'notStarted', 'pathPrereq', 'pathUnlock', 'recommended', 'rejected', 'selected',
    ])
    expect(nodeState.mastered).toMatchObject({ stroke: GRAPH_COLORS.ok })
```

并在该文件顶部导入加 `import { GRAPH_COLORS } from '../../src/frontend/src/graph/theme'`。

`tests/frontend/l14.test.ts`：L420、L425、L447 的 `expect(graph.zoom).toBe(0.7)` 改为 `toBe(READABLE_ZOOM)`，并在导入 `lifecycle` 的那一行加上 `READABLE_ZOOM`（可读缩放由 0.7 调到 0.9 是已记录的设计决定，见规格 §10）。

- [ ] **Step 4: 运行，确认通过，再跑受影响的既有用例**

Run: `npm --prefix src/frontend run test -- --run graph-options h03 h04 h05 i06 l13 l14`
Expected: 全部通过（写计划时已验证：`h03`、`h04`、`l13` 不需要改动；若你的基线不同、它们里有写死 `0.7` 的断言，同样改为 `READABLE_ZOOM` 并在提交说明里写明）；其余断言**不得**放宽。

- [ ] **Step 5: type-check 与提交（提交仅在用户授权后）**

Run: `npm --prefix src/frontend run type-check`
Expected: 退出码 0

```bash
git add src/frontend/src/graph/lifecycle.ts tests/frontend/graph-options.test.ts tests/frontend/h05.test.ts tests/frontend/i06.test.ts tests/frontend/l14.test.ts
git commit -m "feat(frontend): restyle G6 canvas with light workspace theme"
```

---

## 第三阶段：画布增强（增强器与生命周期接入）

### Task 9: 增强器（语义缩放、标签排布、悬停强淡化、章节外框、整组适应）

**Files:**
- Create: `src/frontend/src/graph/enhancer.ts`
- Create: `tests/frontend/fakeEnhancedGraph.ts`（G6 `Graph` 的测试替身，Task 10、12 也用）
- Test: `tests/frontend/graph-enhancer.test.ts`
- Modify: `src/frontend/src/graph/lifecycle.ts`（只扩充 `CanvasGraph` 接口；Task 10 会整体替换此文件，这里的改动是它的子集）

**Interfaces:**
- Consumes: `planLabels`/`Box`/`LabelCandidate`（Task 3）、`computeFit`/`bottomPad`/`DEFAULT_PADS`（Task 4）、`hoverStateMap`/`isForcedLabel`/`labelScore`（Task 6）、`decorateNodeData`/`decorateEdge`/`chapterOfNodes`/`nodeLabel`/`INITIAL_VIEW`/`ViewState`（Task 7）、`labelScale`/`scaleFloors`/`sameFloors`/`LABEL_BASE_PX`（Task 2）、`GRAPH_COLORS`/`GRAPH_FONT`（Task 1/7）、`nodeElementId`（adapter）。
- Produces（Task 10 依赖的精确签名）：
  ```ts
  export interface EnhanceOptions {
    obstacles?: () => { hard: readonly Box[]; soft: readonly Box[] }  // 屏幕包围盒，相对画布容器
    minimap?: HTMLElement | null
    measure?: (text: string, fontPx: number) => number               // 测试替身；缺省用真实字体量
    labelDelayMs?: number                                              // 默认 90
    reduceMotion?: () => boolean
    onHover?: (info: { kpId: string; clientX: number; clientY: number } | null) => void
    onBlankClick?: () => void
  }
  export interface EnhancerDeps { graph(): CanvasGraph | null; size(): readonly [number, number]; enqueue(task: () => Promise<void>): void; alive(): boolean; onZoom(zoom: number): void; options: EnhanceOptions }
  export interface Enhancer {
    readonly view: ViewState
    decorate(data: EnhancedData): EnhancedData        // 记录最新未装饰数据并返回装饰后的副本
    attach(): void                                      // aftertransform / canvas:click / node:pointerenter|leave / canvas:pointermove / edge:pointerenter
    afterRender(): Promise<void>
    setScope(kpIds: readonly string[] | null): void     // 章节外框成员（hull 插件，zIndex -1，首次添加后只更新、不移除）
    fitTo(kpIds?: readonly string[]): Promise<void>
    zoomBy(ratio: number): Promise<void>
    ensureVisible(kpId: string): Promise<void>
    relayoutLabels(): void
    leaveHover(): void
    minimapColor(elementId: string): string            // selected 靛紫 > mastered 绿 > learning 琥珀 > 石板灰
    detach(): void
  }
  export function createEnhancer(deps: EnhancerDeps): Enhancer
  export function zoomOf(g: CanvasGraph | null): number | null    // 读不到（初始化、销毁中 getZoom 会抛）返回 null
  export function measureLabel(text: string, fontPx: number): number
  ```
- 行为要点（均有测试）：缩小到 0.2 时标签放大 5 倍、节点/线宽有屏幕下限，档位量化，缩放档位不变时滚轮缩放**不重绘**；重绘会丢元素状态，所以 `draw()` 之后重写 `setElementState`；强制显示标签**只看 `selected` 状态**（布尔，不是分数阈值），且仍不显示在障碍物下面；标签排布有合并窗口，窗口内又来新事件时窗口结束后再算一次；悬停 60ms 后恢复，进入新节点会取消恢复，触屏无悬停；`hull` 插件从不移除（`Hull.destroy` 在 G6 5.1.1 会抛），渲染之后添加/更新要主动 `drawHull()`。

- [ ] **Step 1: 扩充 `CanvasGraph` 接口并写测试替身与测试**

在 `src/frontend/src/graph/lifecycle.ts` 里做以下四处改动（其余不动）：

1) `CanvasGraph.on` 的签名改为通用事件：

```ts
  on(event: string, handler: (event: GraphEvent) => void): unknown
```

2) 在 `NodeClickEvent` 之后增加：

```ts
/** 画布事件的公共子集（点击、悬停；`client` 是页面坐标） */
export interface GraphEvent extends NodeClickEvent {
  pointerType?: string
  client?: { x: number; y: number }
}

/** 画布坐标 / 视口坐标（G6 的 `Point` 可带第三维，这里只用前两维） */
export type Point2 = readonly number[]
```

3) `zoomTo?` 与 `focusElement?` 增加动画参数：

```ts
  zoomTo?(zoom: number, animation?: unknown): Promise<void>
  focusElement?(id: string, animation?: unknown): Promise<void>
```

4) 在 `setOptions?` 之后、接口结束的 `}` 之前增加：

```ts
  /**
   * 增强模式（UI-GRAPH-PILOT-01）用到的视口、数据与插件接口：G6 `Graph` 均有；测试替身可不实现，
   * 此时对应能力静默跳过。
   */
  getElementPosition?(id: string): Point2
  getViewportByCanvas?(point: Point2): Point2
  translateBy?(offset: Point2, animation?: unknown): Promise<void>
  zoomBy?(ratio: number, animation?: unknown): Promise<void>
  updateNodeData?(data: ReadonlyArray<Record<string, unknown>>): void
  updateEdgeData?(data: ReadonlyArray<Record<string, unknown>>): void
  draw?(): Promise<void>
  setElementState?(state: Record<string, string[]>, animation?: boolean): Promise<void>
  setPlugins?(update: (plugins: unknown[]) => unknown[]): void
  updatePlugin?(option: Record<string, unknown>): void
  getPluginInstance?(key: string): unknown
```

`tests/frontend/fakeEnhancedGraph.ts`：

```ts
import { vi } from 'vitest'
import type { CanvasGraph, CanvasGraphInit, GraphEvent } from '../../src/frontend/src/graph/lifecycle'

/**
 * G6 `Graph` 的测试替身，实现增强模式用到的全部可选方法（`CanvasGraph`）。
 * 记录调用与数据更新，`emit` 手动派发画布事件；`getViewportByCanvas` 是简单的缩放 + 平移变换。
 */
export type Update = Array<{ id: string; data: Record<string, unknown> }>

export class FakeEnhancedGraph implements CanvasGraph {
  destroyed = false
  zoom = 1
  offset: [number, number] = [0, 0]
  calls: string[] = []
  nodeUpdates: Update[] = []
  edgeUpdates: Update[] = []
  stateCalls: Array<Record<string, string[]>> = []
  pluginsAdded: unknown[][] = []
  pluginUpdates: Array<Record<string, unknown>> = []
  focusCalls: Array<[string, unknown]> = []
  drawHull = vi.fn()
  handlers = new Map<string, Array<(event: GraphEvent) => void>>()

  constructor(
    readonly pos: Record<string, [number, number]> = {},
    readonly init?: CanvasGraphInit,
  ) {
    // 带初始坐标的节点（章节布局）直接取它们的位置
    for (const node of init?.data.nodes ?? []) {
      const at = (node as { style?: { x: number; y: number } }).style
      if (at !== undefined) this.pos[node.id] = [at.x, at.y]
    }
  }

  data: unknown = null
  render(): Promise<void> {
    this.calls.push('render')
    return Promise.resolve()
  }
  setData(data: unknown): void {
    this.calls.push('setData')
    this.data = data
  }
  setSize(width: number, height: number): void {
    this.calls.push(`setSize ${width}x${height}`)
  }
  fitView(): Promise<void> {
    this.calls.push('fitView')
    return Promise.resolve()
  }
  on(event: string, handler: (event: GraphEvent) => void): this {
    this.handlers.set(event, [...(this.handlers.get(event) ?? []), handler])
    return this
  }
  emit(event: string, payload: GraphEvent = {}): void {
    for (const handler of this.handlers.get(event) ?? []) handler(payload)
  }
  destroy(): void {
    this.calls.push('destroy')
    this.destroyed = true
  }
  getZoom(): number {
    return this.zoom
  }
  zoomTo(zoom: number): Promise<void> {
    this.zoom = zoom
    this.calls.push(`zoomTo ${zoom}`)
    this.emit('aftertransform')
    return Promise.resolve()
  }
  zoomBy(ratio: number): Promise<void> {
    this.calls.push(`zoomBy ${ratio}`)
    this.zoom *= ratio
    return Promise.resolve()
  }
  getElementPosition(id: string): number[] {
    const at = this.pos[id]
    if (at === undefined) throw new Error('no such element')
    return [...at]
  }
  getViewportByCanvas(point: readonly number[]): number[] {
    return [point[0]! * this.zoom + this.offset[0], point[1]! * this.zoom + this.offset[1]]
  }
  translateBy(offset: readonly number[]): Promise<void> {
    this.offset = [this.offset[0] + offset[0]!, this.offset[1] + offset[1]!]
    this.calls.push('translateBy')
    return Promise.resolve()
  }
  focusElement(id: string, animation?: unknown): Promise<void> {
    this.focusCalls.push([id, animation])
    return Promise.resolve()
  }
  updateNodeData(data: ReadonlyArray<Record<string, unknown>>): void {
    this.nodeUpdates.push(data as Update)
  }
  updateEdgeData(data: ReadonlyArray<Record<string, unknown>>): void {
    this.edgeUpdates.push(data as Update)
  }
  draw(): Promise<void> {
    this.calls.push('draw')
    return Promise.resolve()
  }
  setElementState(state: Record<string, string[]>): Promise<void> {
    this.stateCalls.push(state)
    return Promise.resolve()
  }
  setPlugins(update: (plugins: unknown[]) => unknown[]): void {
    this.pluginsAdded.push(update([]))
  }
  updatePlugin(option: Record<string, unknown>): void {
    this.pluginUpdates.push(option)
  }
  getPluginInstance(): unknown {
    return { drawHull: this.drawHull }
  }
}
```

`tests/frontend/graph-enhancer.test.ts`：

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { G6EdgeData, G6NodeData } from '../../src/frontend/src/graph/adapter'
import { createEnhancer, type EnhanceOptions, zoomOf } from '../../src/frontend/src/graph/enhancer'
import type { CanvasEdge, CanvasElementState, CanvasNode } from '../../src/frontend/src/graph/lifecycle'
import { GRAPH_COLORS } from '../../src/frontend/src/graph/theme'
import { FakeEnhancedGraph as FakeGraph } from './fakeEnhancedGraph'

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

function kp(id: string, extra: Partial<G6NodeData> = {}): CanvasNode {
  return {
    id: `kp:${id}`,
    data: { kpId: id, name: `知识点${id}`, type: 'concept', level: 1, chapterId: 'c1', status: 'approved', confidence: 1, source: 'ai', locked: false, ...extra },
  }
}
/** 带状态的节点 */
function st(node: CanvasNode, ...states: CanvasElementState[]): CanvasNode {
  return { ...node, states }
}
function rel(id: string, from: string, to: string, type: G6EdgeData['type'] = 'PREREQUISITE'): CanvasEdge {
  return {
    id: `rel:${id}`,
    source: `kp:${from}`,
    target: `kp:${to}`,
    data: { relationId: id, type, directed: true, status: 'approved', confidence: 1, source: 'ai', downgraded: false },
    style: { stroke: '#5145CD', lineWidth: 2, lineDash: [], endArrow: true, labelText: '前置' },
  }
}

type Pos = Record<string, [number, number]>
const DEFAULT_POS: Pos = { 'kp:a': [100, 100], 'kp:b': [100, 100], 'kp:c': [600, 400] }

function setup(over: Partial<EnhanceOptions> = {}, pos: Pos = DEFAULT_POS, size: [number, number] = [800, 600]) {
  const graph = new FakeGraph(pos)
  const queue: Array<() => Promise<void>> = []
  const zooms: number[] = []
  let alive = true
  const enhancer = createEnhancer({
    graph: () => graph,
    size: () => size,
    enqueue: (task) => {
      queue.push(task)
    },
    alive: () => alive,
    onZoom: (zoom) => zooms.push(zoom),
    options: { measure: (text, px) => text.length * px, labelDelayMs: 0, ...over },
  })
  const drain = async () => {
    while (queue.length > 0) await queue.shift()!()
  }
  return {
    graph,
    enhancer,
    drain,
    zooms,
    kill: () => {
      alive = false
    },
  }
}

beforeEach(() => {
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    callback(0)
    return 0
  })
})
afterEach(() => vi.unstubAllGlobals())

describe('decorate', () => {
  it('返回装饰后的副本（标签放大 1、全部显示），不修改输入', () => {
    const { enhancer } = setup()
    const input = { nodes: [kp('a'), kp('b')], edges: [rel('r1', 'a', 'b')] }
    const out = enhancer.decorate(input)
    expect(out.nodes[0]!.data).toMatchObject({ k: 1, nk: 1, labelOn: true, mastery: 'unknown' })
    expect(out.edges[0]!.data).toMatchObject({ showLabel: false, cross: false })
    expect(input.nodes[0]!.data).not.toHaveProperty('k')
  })
  it('跨章边被识别并画 1px', () => {
    const { enhancer } = setup()
    const out = enhancer.decorate({ nodes: [kp('a'), kp('b', { chapterId: 'c2' })], edges: [rel('r1', 'a', 'b')] })
    expect(out.edges[0]!.data.cross).toBe(true)
    expect(out.edges[0]!.style.lineWidth).toBe(1)
  })
})

describe('语义缩放', () => {
  it('缩小到 0.2：标签放大 5 倍、节点与线宽有屏幕下限，随后重写元素状态', async () => {
    const { graph, enhancer, zooms } = setup()
    enhancer.decorate({ nodes: [kp('a'), kp('b')], edges: [rel('r1', 'a', 'b')] })
    graph.zoom = 0.2
    await enhancer.afterRender()
    expect(enhancer.view.labelK).toBe(5)
    expect(enhancer.view.floors.nodeK).toBeGreaterThan(1)
    expect(graph.nodeUpdates.at(-1)![0]!.data).toMatchObject({ k: 5 })
    expect(graph.edgeUpdates.at(-1)![0]!.data.lw).toBe(enhancer.view.floors.lwMin)
    expect(graph.calls).toContain('draw')
    expect(graph.stateCalls.length).toBe(1)
    expect(zooms.at(-1)).toBe(0.2)
  })
  it('缩放档位不变时不重绘（滚轮缩放不会每帧重绘）', async () => {
    const { graph, enhancer, drain } = setup()
    enhancer.decorate({ nodes: [kp('a')], edges: [] })
    enhancer.attach()
    await enhancer.afterRender()
    await sleep(10)
    await drain() // 先让首次标签排布落地，再量基线
    const draws = graph.calls.filter((c) => c === 'draw').length
    graph.emit('aftertransform')
    await sleep(10)
    await drain()
    expect(graph.calls.filter((c) => c === 'draw').length).toBe(draws)
  })
  it('zoomOf 读不到时返回 null（初始化或销毁中 getZoom 会抛）', () => {
    const g = new FakeGraph({})
    g.getZoom = () => {
      throw new Error('not ready')
    }
    expect(zoomOf(g)).toBeNull()
    expect(zoomOf(null)).toBeNull()
  })
})

describe('标签排布', () => {
  it('两个节点重叠时只保留优先级高的（搜索命中 > 普通）', async () => {
    const { graph, enhancer, drain } = setup()
    enhancer.decorate({ nodes: [st(kp('a'), 'match'), kp('b')], edges: [] })
    await enhancer.afterRender()
    await sleep(10)
    await drain()
    const last = new Map(graph.nodeUpdates.at(-1)!.map((n) => [n.id, n.data.labelOn]))
    expect(last.get('kp:a')).toBe(true)
    expect(last.get('kp:b')).toBe(false)
  })
  it('被预览/选中的节点强制显示，但落在浮层下面时仍不显示', async () => {
    const hard: Array<[number, number, number, number]> = [[0, 0, 400, 400]]
    const { graph, enhancer, drain } = setup({ obstacles: () => ({ hard, soft: [] }) })
    enhancer.decorate({ nodes: [st(kp('a'), 'selected'), kp('c')], edges: [] })
    await enhancer.afterRender()
    await sleep(10)
    await drain()
    const last = new Map(graph.nodeUpdates.at(-1)!.map((n) => [n.id, n.data.labelOn]))
    expect(last.get('kp:a')).toBe(false) // 在障碍物下
    expect(last.get('kp:c')).toBe(true)
  })
  it('浮层变化后 relayoutLabels 重新排布', async () => {
    let hard: Array<[number, number, number, number]> = []
    const { graph, enhancer, drain } = setup({ obstacles: () => ({ hard, soft: [] }) })
    enhancer.decorate({ nodes: [kp('a')], edges: [] })
    await enhancer.afterRender()
    await sleep(10)
    await drain()
    const before = graph.nodeUpdates.length
    hard = [[0, 0, 400, 400]]
    enhancer.relayoutLabels()
    await sleep(10)
    await drain()
    expect(graph.nodeUpdates.length).toBeGreaterThan(before)
    expect(graph.nodeUpdates.at(-1)![0]!.data.labelOn).toBe(false)
  })
})

describe('整组适应 fitTo', () => {
  it('把一组节点整体放进视口，且落在边距内', async () => {
    const pos: Pos = { 'kp:a': [0, 0], 'kp:b': [1600, 0], 'kp:c': [0, 1200] }
    const { graph, enhancer } = setup({}, pos)
    enhancer.decorate({ nodes: [kp('a'), kp('b'), kp('c')], edges: [] })
    await enhancer.fitTo()
    expect(graph.calls).toContain('translateBy')
    for (const id of Object.keys(pos)) {
      const [x, y] = graph.getViewportByCanvas(graph.getElementPosition(id))
      expect(x).toBeGreaterThanOrEqual(56)
      expect(x).toBeLessThanOrEqual(800 - 96)
      expect(y).toBeGreaterThanOrEqual(104)
      expect(y).toBeLessThanOrEqual(600 - 96)
    }
  })
  it('只适应指定的知识点；不在图中的忽略；缩放不超过 1.2', async () => {
    const pos: Pos = { 'kp:a': [0, 0], 'kp:b': [100, 0], 'kp:c': [5000, 5000] }
    const { graph, enhancer } = setup({}, pos)
    enhancer.decorate({ nodes: [kp('a'), kp('b'), kp('c')], edges: [] })
    await enhancer.fitTo(['a', 'b', 'nope'])
    expect(graph.zoom).toBeGreaterThan(1)
    expect(graph.zoom).toBeLessThanOrEqual(1.2)
  })
  it('没有可用节点时不动镜头', async () => {
    const { graph, enhancer } = setup()
    enhancer.decorate({ nodes: [], edges: [] })
    await enhancer.fitTo()
    expect(graph.calls).toEqual([])
  })
})

describe('ensureVisible / zoomBy', () => {
  it('节点在视口内不移动镜头，在视口外才聚焦；减少动效时关闭动画', async () => {
    const { graph, enhancer } = setup({ reduceMotion: () => true }, { 'kp:a': [100, 100], 'kp:c': [5000, 5000] })
    enhancer.decorate({ nodes: [kp('a'), kp('c')], edges: [] })
    await enhancer.ensureVisible('a')
    expect(graph.focusCalls).toEqual([])
    await enhancer.ensureVisible('c')
    expect(graph.focusCalls).toEqual([['kp:c', false]])
  })
  it('zoomBy 上报缩放', async () => {
    const { graph, enhancer, zooms } = setup()
    await enhancer.zoomBy(2)
    expect(graph.zoom).toBe(2)
    expect(zooms.at(-1)).toBe(2)
  })
})

describe('悬停强淡化（瞬时）', () => {
  const data = () => ({ nodes: [st(kp('a'), 'mastered'), kp('b'), kp('c')], edges: [rel('r1', 'a', 'b')] })

  it('悬停节点与相邻保持清楚，其余退后；持久状态保留；移开 60ms 后恢复', async () => {
    const hovers: unknown[] = []
    const { graph, enhancer } = setup({ onHover: (info) => hovers.push(info) })
    enhancer.decorate(data())
    enhancer.attach()
    graph.emit('node:pointerenter', { target: { id: 'kp:a' }, pointerType: 'mouse', client: { x: 10, y: 20 } })
    const during = graph.stateCalls.at(-1)!
    expect(during['kp:a']).toEqual(['mastered', 'hovered'])
    expect(during['kp:b']).toEqual(['hoverRelated'])
    expect(during['kp:c']).toEqual(['hoverFaded'])
    expect(during['rel:r1']).toEqual(['active'])
    expect(hovers.at(-1)).toEqual({ kpId: 'a', clientX: 10, clientY: 20 })
    graph.emit('node:pointerleave')
    expect(hovers.at(-1)).toBeNull()
    await sleep(90)
    const after = graph.stateCalls.at(-1)!
    expect(after['kp:a']).toEqual(['mastered'])
    expect(after['kp:c']).toEqual([])
  })
  it('触屏没有悬停效果', () => {
    const { graph, enhancer } = setup()
    enhancer.decorate(data())
    enhancer.attach()
    graph.emit('node:pointerenter', { target: { id: 'kp:a' }, pointerType: 'touch' })
    expect(graph.stateCalls).toEqual([])
  })
  it('快速移到相邻节点时不闪：进入新节点会取消恢复', async () => {
    const { graph, enhancer } = setup()
    enhancer.decorate(data())
    enhancer.attach()
    graph.emit('node:pointerenter', { target: { id: 'kp:a' }, pointerType: 'mouse' })
    graph.emit('node:pointerleave')
    graph.emit('node:pointerenter', { target: { id: 'kp:b' }, pointerType: 'mouse' })
    await sleep(90)
    expect(graph.stateCalls.at(-1)!['kp:b']).toEqual(['hovered'])
  })
  it('兜底：画布空白处移动、进入边也结束悬停', async () => {
    const { graph, enhancer } = setup()
    enhancer.decorate(data())
    enhancer.attach()
    graph.emit('node:pointerenter', { target: { id: 'kp:a' }, pointerType: 'mouse' })
    graph.emit('canvas:pointermove')
    await sleep(90)
    expect(graph.stateCalls.at(-1)!['kp:a']).toEqual(['mastered'])
    graph.emit('node:pointerenter', { target: { id: 'kp:a' }, pointerType: 'mouse' })
    graph.emit('edge:pointerenter')
    await sleep(90)
    expect(graph.stateCalls.at(-1)!['kp:a']).toEqual(['mastered'])
  })
  it('兜底：指针离开整个画布容器也结束悬停；没有悬停时是空操作', async () => {
    const { graph, enhancer } = setup()
    enhancer.decorate(data())
    enhancer.attach()
    enhancer.leaveHover()
    expect(graph.stateCalls).toEqual([])
    graph.emit('node:pointerenter', { target: { id: 'kp:a' }, pointerType: 'mouse' })
    enhancer.leaveHover()
    await sleep(90)
    expect(graph.stateCalls.at(-1)!['kp:a']).toEqual(['mastered'])
  })
  it('预览/选中的节点即使与悬停节点无关也保留外环', () => {
    const { graph, enhancer } = setup()
    enhancer.decorate({ nodes: [kp('a'), st(kp('c'), 'selected')], edges: [] })
    enhancer.attach()
    graph.emit('node:pointerenter', { target: { id: 'kp:a' }, pointerType: 'mouse' })
    expect(graph.stateCalls.at(-1)!['kp:c']).toEqual(['selected'])
  })
})

describe('空白点击与销毁', () => {
  it('点击画布空白处通知页面取消预览；detach 后不再响应', () => {
    const onBlankClick = vi.fn()
    const { graph, enhancer } = setup({ onBlankClick })
    enhancer.attach()
    graph.emit('canvas:click')
    expect(onBlankClick).toHaveBeenCalledTimes(1)
    enhancer.detach()
    graph.emit('canvas:click')
    expect(onBlankClick).toHaveBeenCalledTimes(1)
  })
  it('生命周期销毁后（alive=false）事件被忽略', () => {
    const onBlankClick = vi.fn()
    const { graph, enhancer, kill } = setup({ onBlankClick })
    enhancer.attach()
    kill()
    graph.emit('canvas:click')
    graph.emit('aftertransform')
    expect(onBlankClick).not.toHaveBeenCalled()
  })
})

describe('章节外框（hull 插件）', () => {
  it('首次添加插件（zIndex -1、靛紫虚线），之后只更新成员与可见性，从不移除', () => {
    const { graph, enhancer } = setup()
    enhancer.decorate({ nodes: [kp('a'), kp('b'), kp('c')], edges: [] })
    enhancer.setScope(['a', 'b'])
    expect(graph.pluginsAdded).toHaveLength(1)
    expect(graph.pluginsAdded[0]![0]).toMatchObject({
      type: 'hull',
      key: 'chapter-hull',
      members: ['kp:a', 'kp:b'],
      zIndex: -1,
      stroke: GRAPH_COLORS.accent,
      fill: GRAPH_COLORS.hullFill,
    })
    expect(graph.drawHull).toHaveBeenCalled()
    enhancer.setScope(null)
    expect(graph.pluginUpdates.at(-1)).toMatchObject({ key: 'chapter-hull', members: [], visibility: 'hidden' })
    enhancer.setScope(['c'])
    expect(graph.pluginUpdates.at(-1)).toMatchObject({ members: ['kp:c'], visibility: 'visible' })
    expect(graph.pluginsAdded).toHaveLength(1)
  })
  it('没有章节范围时不添加插件；不在图中的成员被忽略；相同成员不重复更新', () => {
    const { graph, enhancer } = setup()
    enhancer.decorate({ nodes: [kp('a')], edges: [] })
    enhancer.setScope(null)
    enhancer.setScope(['zzz'])
    expect(graph.pluginsAdded).toHaveLength(0)
    enhancer.setScope(['a'])
    enhancer.setScope(['a'])
    expect(graph.pluginsAdded).toHaveLength(1)
    expect(graph.pluginUpdates).toHaveLength(0)
  })
})

describe('小地图着色', () => {
  it('当前高亮靛紫、已掌握绿、学习中琥珀、其余石板灰', () => {
    const { enhancer } = setup()
    enhancer.decorate({
      nodes: [st(kp('a'), 'selected', 'mastered'), st(kp('b'), 'mastered'), st(kp('c'), 'learning'), kp('d')],
      edges: [],
    })
    expect(enhancer.minimapColor('kp:a')).toBe(GRAPH_COLORS.accent)
    expect(enhancer.minimapColor('kp:b')).toBe(GRAPH_COLORS.ok)
    expect(enhancer.minimapColor('kp:c')).toBe(GRAPH_COLORS.warn)
    expect(enhancer.minimapColor('kp:d')).toBe(GRAPH_COLORS.nodeStroke)
  })
})
```

- [ ] **Step 2: 运行，确认失败**

Run: `npm --prefix src/frontend run test -- --run graph-enhancer`
Expected: FAIL（找不到 `graph/enhancer`）

- [ ] **Step 3: 实现增强器**

`src/frontend/src/graph/enhancer.ts`：

```ts
import { nodeElementId } from './adapter'
import { bottomPad, computeFit, DEFAULT_PADS } from './fit'
import { hoverStateMap, isForcedLabel, labelScore } from './focusStates'
import { planLabels, type Box, type LabelCandidate } from './labelPlan'
import type { CanvasEdge, CanvasGraph, CanvasNode, GraphEvent } from './lifecycle'
import { chapterOfNodes, decorateEdge, decorateNodeData, INITIAL_VIEW, nodeLabel, type ViewState } from './presentation'
import { LABEL_BASE_PX, labelScale, sameFloors, scaleFloors } from './scale'
import { GRAPH_COLORS, GRAPH_FONT } from './theme'

/**
 * 画布增强（UI-GRAPH-PILOT-01）：语义缩放、标签排布、悬停强淡化、章节外框、整组适应。
 *
 * 由 `createGraphLifecycle` 在 `enhance` 选项开启时创建；所有对 G6 的异步写操作都通过 `deps.enqueue`
 * 排进生命周期的串行队列。G6 实例的缺失方法（测试替身）一律静默跳过。
 */

export interface EnhanceOptions {
  /** 浮层的屏幕包围盒（相对画布容器）：hard 参与镜头适应与标签避让，soft（如可展开的图例）只避让标签 */
  obstacles?: () => { hard: readonly Box[]; soft: readonly Box[] }
  /** 小地图容器；缺省不画小地图 */
  minimap?: HTMLElement | null
  /** 量文字宽度（测试替身用）；缺省用真实字体在离屏 canvas 上量 */
  measure?: (text: string, fontPx: number) => number
  /** 标签排布的合并窗口（毫秒），缺省 90 */
  labelDelayMs?: number
  /** 减少动效：镜头动画一律关闭 */
  reduceMotion?: () => boolean
  /** 悬停节点（非触屏）时回调，用于 tooltip；移开时回调 null */
  onHover?: (info: { kpId: string; clientX: number; clientY: number } | null) => void
  /** 点击画布空白处（取消预览） */
  onBlankClick?: () => void
}

export interface EnhancerDeps {
  graph(): CanvasGraph | null
  /** 画布容器的当前尺寸 */
  size(): readonly [number, number]
  enqueue(task: () => Promise<void>): void
  alive(): boolean
  onZoom(zoom: number): void
  options: EnhanceOptions
}

export interface EnhancedData {
  nodes: CanvasNode[]
  edges: CanvasEdge[]
}

export interface Enhancer {
  /** 当前视图状态（缩放档位、标签显示集） */
  readonly view: ViewState
  /** 记录最新数据（未装饰的副本）并返回装饰后的数据，交给 G6 */
  decorate(data: EnhancedData): EnhancedData
  /** 图创建后绑定事件 */
  attach(): void
  /** 数据画完之后（首次渲染、更新、布局、改尺寸）：同步档位、章节外框、重新排布标签 */
  afterRender(): Promise<void>
  /** 章节外框的成员（知识点 ID）；null 隐藏外框 */
  setScope(kpIds: readonly string[] | null): void
  /** 把一组知识点（缺省为全部）整体放进视口 */
  fitTo(kpIds?: readonly string[]): Promise<void>
  zoomBy(ratio: number): Promise<void>
  /** 节点在视口外时才把镜头移过去；在视口内不动 */
  ensureVisible(kpId: string): Promise<void>
  /** 浮层变化（出现、消失、展开收起）后重新排布标签 */
  relayoutLabels(): void
  /** 指针离开整个画布：结束悬停（悬停淡化的兜底之一，只依赖节点的 pointerleave 在快速移动时不可靠） */
  leaveHover(): void
  /** 小地图里某个节点点的颜色：当前高亮靛紫、已掌握绿、学习中琥珀、其余石板灰 */
  minimapColor(elementId: string): string
  detach(): void
}

/** 安全读取缩放：G6 在初始化、销毁过程中就会发出视口事件，此时内部上下文可能没就绪，直接读会抛异步异常 */
export function zoomOf(g: CanvasGraph | null): number | null {
  if (g === null || g.getZoom === undefined) return null
  try {
    return g.getZoom()
  } catch {
    return null
  }
}

let measureContext: CanvasRenderingContext2D | null | undefined
const baseWidths = new Map<string, number>()

/** 用真实字体量文字宽度（13px 基准量一次再等比换算）：拉丁字母与全角字符宽度差很多，不能按字符数估算 */
export function measureLabel(text: string, fontPx: number): number {
  let base = baseWidths.get(text)
  if (base === undefined) {
    if (measureContext === undefined) {
      try {
        measureContext = document.createElement('canvas').getContext('2d')
      } catch {
        measureContext = null
      }
    }
    if (measureContext === null || measureContext === undefined) return text.length * fontPx
    measureContext.font = `500 ${LABEL_BASE_PX}px ${GRAPH_FONT}`
    base = measureContext.measureText(text).width
    baseWidths.set(text, base)
  }
  return (base / LABEL_BASE_PX) * fontPx
}

const round2 = (value: number): number => Math.round(value * 100) / 100

export function createEnhancer(deps: EnhancerDeps): Enhancer {
  const { options } = deps
  let view: ViewState = INITIAL_VIEW
  let nodes: CanvasNode[] = []
  let edges: CanvasEdge[] = []
  let chapterOf = new Map<string, string | null>()
  let importance = new Map<string, number>()
  let scope: readonly string[] | null = null
  let hoverId: string | null = null
  let hoverLeave: ReturnType<typeof setTimeout> | null = null
  let labelTimer: ReturnType<typeof setTimeout> | null = null
  let labelDirty = false
  let hullAdded = false
  let hullKey = ''
  let detached = false

  const live = () => !detached && deps.alive()
  const animation = (ms: number) => (options.reduceMotion?.() === true ? false : { duration: ms, easing: 'ease-out' })

  function decoratedNodes(): CanvasNode[] {
    return nodes.map((n) => ({ ...n, data: decorateNodeData(n.id, n.data, n.states, view) }))
  }
  function decoratedEdges(): CanvasEdge[] {
    return edges.map((e) => {
      const cross = (chapterOf.get(e.source) ?? null) !== (chapterOf.get(e.target) ?? null)
      const out = decorateEdge(e, cross, view)
      return { ...e, data: out.data, style: out.style }
    })
  }

  function decorate(data: EnhancedData): EnhancedData {
    nodes = data.nodes
    edges = data.edges
    chapterOf = chapterOfNodes(nodes)
    const degree = new Map<string, number>()
    for (const e of edges) {
      degree.set(e.source, (degree.get(e.source) ?? 0) + 1)
      degree.set(e.target, (degree.get(e.target) ?? 0) + 1)
    }
    const max = Math.max(1, ...degree.values())
    importance = new Map(nodes.map((n) => [n.id, (degree.get(n.id) ?? 0) / max]))
    return { nodes: decoratedNodes(), edges: decoratedEdges() }
  }

  function selectedElement(): string | null {
    return nodes.find((n) => n.states?.includes('selected') === true)?.id ?? null
  }

  function stateMap(): Record<string, string[]> {
    return hoverStateMap({ nodes, edges, hoverId, selectedId: selectedElement() })
  }

  /** 把当前视图状态写进元素数据并重绘；重绘会丢元素状态，所以随后重新写一次 */
  async function pushView(): Promise<void> {
    const g = deps.graph()
    if (!live() || g === null || g.updateNodeData === undefined || g.updateEdgeData === undefined || g.draw === undefined) return
    g.updateNodeData(decoratedNodes().map((n) => ({ id: n.id, data: n.data })))
    g.updateEdgeData(decoratedEdges().map((e) => ({ id: e.id, data: e.data, style: e.style })))
    await g.draw()
    if (live()) await g.setElementState?.(stateMap(), false)
  }

  /** 按当前缩放重算档位；返回是否变化。档位量化，滚轮缩放时不会每帧重绘 */
  function syncView(zoom: number): boolean {
    const labelK = labelScale(zoom)
    const floors = scaleFloors(zoom, true)
    if (labelK === view.labelK && sameFloors(floors, view.floors)) return false
    view = { ...view, labelK, floors }
    return true
  }

  function planNow(): Set<string> | null {
    const g = deps.graph()
    if (g === null || g.getElementPosition === undefined || g.getViewportByCanvas === undefined) return null
    const zoom = zoomOf(g)
    const [width, height] = deps.size()
    if (zoom === null || width === 0) return null
    const o = options.obstacles?.() ?? { hard: [], soft: [] }
    const candidates: LabelCandidate[] = []
    for (const n of nodes) {
      let at: readonly number[]
      try {
        at = g.getViewportByCanvas(g.getElementPosition(n.id))
      } catch {
        continue
      }
      const states = n.states ?? []
      candidates.push({
        id: n.id,
        x: at[0]!,
        y: at[1]!,
        text: nodeLabel(n.data),
        // 强制只看是不是被预览/选中的那个节点：分数是累加的，不能用阈值判断
        forced: isForcedLabel(states),
        score: labelScore({ states, importance: importance.get(n.id), pathOrder: n.data.pathOrder }),
      })
    }
    return planLabels({
      candidates,
      viewport: { width, height },
      zoom,
      labelK: view.labelK,
      nodeK: view.floors.nodeK,
      obstacles: [...o.hard, ...o.soft],
      measure: options.measure ?? measureLabel,
    })
  }

  /**
   * 视口或数据变化后重新排布；只有显示集合变了才重绘。合并窗口内又来了新事件时，窗口结束后必须再算一次：
   * 镜头动画的最后一次视口事件常常落在窗口里，被吞掉的话排布会停在动画中途的位置上。
   */
  function scheduleLabels(): void {
    if (labelTimer !== null) {
      labelDirty = true
      return
    }
    labelTimer = setTimeout(() => {
      labelTimer = null
      if (!live()) return
      if (labelDirty) {
        labelDirty = false
        scheduleLabels()
        return
      }
      const next = planNow()
      if (next === null) return
      const prev = view.labelShown
      if (prev !== null && prev.size === next.size && [...next].every((id) => prev.has(id))) return
      view = { ...view, labelShown: next }
      deps.enqueue(pushView)
    }, options.labelDelayMs ?? 90)
  }

  function drawHullSoon(g: CanvasGraph): void {
    requestAnimationFrame(() => {
      if (!live() || deps.graph() !== g) return
      try {
        ;(g.getPluginInstance?.('chapter-hull') as { drawHull?: () => void } | undefined)?.drawHull?.()
      } catch {
        /* 插件尚未就绪，下一次同步时再画 */
      }
    })
  }

  /**
   * 章节外框（`hull` 插件）：画在节点后面（`zIndex: -1`）。不要移除插件——G6 5.1.1 的 `Hull.destroy`
   * 读取未定义的 shape 会抛未捕获异常；首次添加后一直保留，只更新成员与可见性。
   * Hull 只在 `afterrender` 里绘制，我们是在渲染之后添加或更新的，所以要主动调 `drawHull`。
   */
  function syncHull(): void {
    const g = deps.graph()
    if (g === null || g.setPlugins === undefined || g.updatePlugin === undefined) return
    const present = new Set(nodes.map((n) => n.id))
    const ids = (scope ?? []).map(nodeElementId).filter((id) => present.has(id))
    const key = ids.join(',')
    if (key === hullKey) return
    hullKey = key
    if (!hullAdded) {
      if (ids.length === 0) return
      hullAdded = true
      g.setPlugins((prev) => [
        ...prev,
        {
          type: 'hull',
          key: 'chapter-hull',
          members: ids,
          padding: 34,
          corner: 'rounded',
          fill: GRAPH_COLORS.hullFill,
          fillOpacity: 1,
          stroke: GRAPH_COLORS.accent,
          lineWidth: 1.5,
          lineDash: [8, 5],
          zIndex: -1,
        },
      ])
    } else {
      g.updatePlugin({ key: 'chapter-hull', members: ids, visibility: ids.length === 0 ? 'hidden' : 'visible' })
    }
    drawHullSoon(g)
  }

  function applyHover(): void {
    const g = deps.graph()
    if (!live() || g === null || g.setElementState === undefined) return
    void g.setElementState(stateMap(), false).catch(() => undefined)
  }

  function endHover(): void {
    options.onHover?.(null)
    if (hoverLeave !== null) clearTimeout(hoverLeave)
    // 稍等一下再恢复：从一个节点移到相邻节点时不闪（期间进入新节点会取消）
    hoverLeave = setTimeout(() => {
      hoverLeave = null
      hoverId = null
      applyHover()
    }, 60)
  }

  function attach(): void {
    const g = deps.graph()
    if (g === null) return
    // 语义缩放：缩小时标签按档位放大，屏幕上保持约 13px；节点、线、箭头按屏幕下限放大
    g.on('aftertransform', () => {
      if (!live() || deps.graph() !== g) return
      const zoom = zoomOf(g)
      if (zoom === null) return
      deps.onZoom(round2(zoom))
      if (syncView(zoom)) deps.enqueue(pushView)
      scheduleLabels()
    })
    g.on('canvas:click', () => {
      if (live()) options.onBlankClick?.()
    })
    g.on('node:pointerenter', (event: GraphEvent) => {
      const id = event.target?.id
      // 触屏没有悬停：不做悬停淡化与 tooltip
      if (!live() || id === undefined || event.pointerType === 'touch') return
      if (hoverLeave !== null) clearTimeout(hoverLeave)
      hoverLeave = null
      hoverId = id
      applyHover()
      const node = nodes.find((n) => n.id === id)
      if (node !== undefined) {
        options.onHover?.({ kpId: node.data.kpId, clientX: event.client?.x ?? 0, clientY: event.client?.y ?? 0 })
      }
    })
    g.on('node:pointerleave', () => {
      if (live() && hoverId !== null) endHover()
    })
    // 兜底：只依赖节点的 pointerleave 在快速移动时不可靠
    g.on('canvas:pointermove', () => {
      if (live() && hoverId !== null) endHover()
    })
    g.on('edge:pointerenter', () => {
      if (live() && hoverId !== null) endHover()
    })
  }

  async function afterRender(): Promise<void> {
    const g = deps.graph()
    if (!live() || g === null) return
    const zoom = zoomOf(g)
    if (zoom !== null) {
      deps.onZoom(round2(zoom))
      if (syncView(zoom)) await pushView()
    }
    syncHull()
    scheduleLabels()
  }

  async function fitTo(kpIds?: readonly string[]): Promise<void> {
    const g = deps.graph()
    if (!live() || g === null || g.getElementPosition === undefined || g.getViewportByCanvas === undefined) return
    if (g.zoomTo === undefined || g.translateBy === undefined) return
    const present = new Set(nodes.map((n) => n.id))
    const ids = (kpIds === undefined ? nodes.map((n) => n.id) : kpIds.map(nodeElementId)).filter((id) => present.has(id))
    const points: Array<[number, number]> = []
    for (const id of ids) {
      try {
        const at = g.getElementPosition(id)
        points.push([at[0]!, at[1]!])
      } catch {
        /* 不在图中的忽略 */
      }
    }
    const [width, height] = deps.size()
    // 底部要避开小地图（按实际浮层高度算，软障碍不计）；上、左、右边距避开搜索栏与右侧工具
    const hard = options.obstacles?.().hard ?? []
    const fit = computeFit({
      points,
      viewport: { width, height },
      pads: { ...DEFAULT_PADS, bottom: bottomPad(hard, height) },
      nodeRadius: 24 * view.floors.nodeK,
      bottomExtra: 48 * view.labelK * 0.4,
    })
    if (fit === null) return
    await g.zoomTo(fit.zoom, false)
    if (!live() || deps.graph() !== g) return
    const at = g.getViewportByCanvas(fit.center)
    await g.translateBy([fit.target[0] - at[0]!, fit.target[1] - at[1]!], animation(240))
    if (live()) {
      const zoom = zoomOf(g)
      if (zoom !== null) deps.onZoom(round2(zoom))
    }
  }

  return {
    get view() {
      return view
    },
    decorate,
    attach,
    afterRender,
    setScope(kpIds) {
      scope = kpIds
      syncHull()
    },
    fitTo,
    async zoomBy(ratio) {
      const g = deps.graph()
      if (!live() || g === null || g.zoomBy === undefined) return
      await g.zoomBy(ratio, animation(160))
      const zoom = zoomOf(g)
      if (live() && zoom !== null) deps.onZoom(round2(zoom))
    },
    async ensureVisible(kpId) {
      const g = deps.graph()
      if (!live() || g === null || g.getElementPosition === undefined || g.getViewportByCanvas === undefined) return
      const [width, height] = deps.size()
      try {
        const at = g.getViewportByCanvas(g.getElementPosition(nodeElementId(kpId)))
        const margin = 56
        if (at[0]! < margin || at[1]! < margin || at[0]! > width - margin || at[1]! > height - margin) {
          await g.focusElement?.(nodeElementId(kpId), animation(240))
        }
      } catch {
        await g.focusElement?.(nodeElementId(kpId), false)
      }
    },
    relayoutLabels: scheduleLabels,
    leaveHover() {
      if (live() && hoverId !== null) endHover()
    },
    minimapColor(elementId) {
      const states = nodes.find((n) => n.id === elementId)?.states ?? []
      if (states.includes('selected')) return GRAPH_COLORS.accent
      if (states.includes('mastered')) return GRAPH_COLORS.ok
      if (states.includes('learning')) return GRAPH_COLORS.warn
      return GRAPH_COLORS.nodeStroke
    },
    detach() {
      detached = true
      if (labelTimer !== null) clearTimeout(labelTimer)
      if (hoverLeave !== null) clearTimeout(hoverLeave)
      labelTimer = null
      hoverLeave = null
    },
  }
}
```

- [ ] **Step 4: 运行，确认通过，并类型检查**

Run: `npm --prefix src/frontend run test -- --run graph-enhancer && npm --prefix src/frontend run type-check`
Expected: `graph-enhancer` 24 passed；type-check 退出码 0

- [ ] **Step 5: 提交（仅在用户授权后）**

```bash
git add src/frontend/src/graph/enhancer.ts src/frontend/src/graph/lifecycle.ts tests/frontend/fakeEnhancedGraph.ts tests/frontend/graph-enhancer.test.ts
git commit -m "feat(frontend): add graph enhancer (semantic zoom, label planning, hover fade, chapter hull)"
```

---

### Task 10: 生命周期接入增强器（章节位置、尺寸策略、新方法）

**Files:**
- Modify（整体替换）: `src/frontend/src/graph/lifecycle.ts`
- Test: `tests/frontend/graph-lifecycle-enhance.test.ts`

**Interfaces:**
- Consumes: `createEnhancer`/`EnhanceOptions`/`Enhancer`（Task 9）、`Positions`（Task 5）。
- Produces：
  ```ts
  // GraphLifecycleOptions 新增
  positions?: Positions | null            // 章节分区位置（知识点 ID → 坐标），建图时一次性给定；力导向下忽略
  enhance?: EnhanceOptions                // 缺省关闭：行为与 H04 完全一致
  // GraphLifecycle 新增（未开增强时为空操作）
  fitTo(kpIds?: readonly string[]): void; setScope(kpIds: readonly string[] | null): void
  zoomBy(ratio: number): void; ensureVisible(kpId: string): void; relayoutLabels(): void; leaveHover(): void
  // CanvasGraphInit 新增
  positions?: Positions | null; minimap?: { container: HTMLElement; color: (elementId: string) => string }
  // CanvasNode 新增 style?: { x: number; y: number }
  ```
- 行为要点：有位置时 `buildGraphOptions` **不再给 `layout`**、边为 `cubic-vertical`；小地图是 `minimap` 插件（外部容器、自定义 `shape` 克隆主形状着色、`delay: 100`）；增强模式下 `ResizeObserver` 触发的尺寸变化（面板开合）只 `setSize`，**窗口缩放**（`window` 的 `resize` 事件）与 `refreshSize()` 才整图重新适配；增强模式销毁图实例**延后 400ms** 并吞掉拒绝（插件有延迟回调）；未开增强时 `destroy` 仍立即销毁。

- [ ] **Step 1: 写测试**

`tests/frontend/graph-lifecycle-enhance.test.ts`：

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Positions } from '../../src/frontend/src/graph/chapterLayout'
import {
  buildGraphOptions,
  createGraphLifecycle,
  type CanvasEdge,
  type CanvasGraphFactory,
  type CanvasNode,
  type GraphCanvasData,
  type GraphLifecycleOptions,
} from '../../src/frontend/src/graph/lifecycle'
import { GRAPH_COLORS } from '../../src/frontend/src/graph/theme'
import { FakeEnhancedGraph } from './fakeEnhancedGraph'

function kp(id: string, chapterId: string, states?: CanvasNode['states']): CanvasNode {
  return {
    id: `kp:${id}`,
    data: { kpId: id, name: `知识点${id}`, type: 'concept', level: 1, chapterId, status: 'approved', confidence: 1, source: 'ai', locked: false },
    ...(states === undefined ? {} : { states }),
  }
}
const edge: CanvasEdge = {
  id: 'rel:r1',
  source: 'kp:a',
  target: 'kp:b',
  data: { relationId: 'r1', type: 'PREREQUISITE', directed: true, status: 'approved', confidence: 1, source: 'ai', downgraded: false },
  style: { stroke: '#5145CD', lineWidth: 2, lineDash: [], endArrow: true, labelText: '前置' },
}
const sample = (): GraphCanvasData => ({ nodes: [kp('a', 'c1'), kp('b', 'c2')], edges: [edge] })
const positions: Positions = new Map([
  ['a', { x: 10, y: 20 }],
  ['b', { x: 300, y: 400 }],
])
const measure = (text: string, px: number) => text.length * px

function box(width = 800, height = 600): HTMLElement {
  const el = document.createElement('div')
  Object.defineProperty(el, 'clientWidth', { configurable: true, value: width })
  Object.defineProperty(el, 'clientHeight', { configurable: true, value: height })
  return el
}
const resize = (el: HTMLElement, width: number, height = 600) => {
  Object.defineProperty(el, 'clientWidth', { configurable: true, value: width })
  Object.defineProperty(el, 'clientHeight', { configurable: true, value: height })
}

class FakeResizeObserver {
  static instances: FakeResizeObserver[] = []
  disconnected = false
  constructor(readonly callback: () => void) {
    FakeResizeObserver.instances.push(this)
  }
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {
    this.disconnected = true
  }
}

let frames: Array<() => void> = []
const flushFrames = () => {
  const run = frames
  frames = []
  run.forEach((fn) => fn())
}
async function settle(): Promise<void> {
  for (let i = 0; i < 10; i += 1) await Promise.resolve()
  await new Promise((resolve) => setTimeout(resolve, 5))
}

function make() {
  const graphs: FakeEnhancedGraph[] = []
  const factory: CanvasGraphFactory = (init) => {
    const g = new FakeEnhancedGraph({}, init)
    graphs.push(g)
    return g
  }
  return { graphs, factory }
}

beforeEach(() => {
  FakeResizeObserver.instances = []
  frames = []
  vi.stubGlobal('ResizeObserver', FakeResizeObserver)
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    frames.push(() => callback(0))
    return frames.length
  })
  vi.stubGlobal('cancelAnimationFrame', () => undefined)
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

const enhance = { measure, labelDelayMs: 0 }
function start(over: Partial<GraphLifecycleOptions> = {}, el = box()) {
  const m = make()
  const life = createGraphLifecycle(el, { data: sample(), factory: m.factory, enhance, ...over })
  return { ...m, life, el }
}

describe('章节布局位置', () => {
  it('位置随建图传给工厂，节点数据带坐标，G6 不再自己布局', async () => {
    const { graphs } = start({ positions })
    await settle()
    const init = graphs[0]!.init!
    expect(init.positions).toBe(positions)
    expect(init.data.nodes.map((n) => n.style)).toEqual([{ x: 10, y: 20 }, { x: 300, y: 400 }])
    const options = buildGraphOptions({ ...init, container: document.createElement('div') }) as unknown as { layout?: unknown; edge: { type?: string } }
    expect(options.layout).toBeUndefined()
    expect(options.edge.type).toBe('cubic-vertical')
  })
  it('力导向布局忽略位置，仍由 G6 布局', async () => {
    const { graphs } = start({ positions, layout: 'force' })
    await settle()
    const init = graphs[0]!.init!
    expect(init.positions).toBeNull()
    expect(init.data.nodes.every((n) => n.style === undefined)).toBe(true)
    const options = buildGraphOptions({ ...init, container: document.createElement('div') }) as unknown as { layout?: { type: string }; edge: { type?: string } }
    expect(options.layout?.type).toBe('d3-force')
    expect(options.edge.type).toBeUndefined()
  })
  it('更新数据后新节点同样带上坐标', async () => {
    const { graphs, life } = start({ positions })
    await settle()
    life.update({ nodes: [kp('b', 'c2')], edges: [] })
    await settle()
    const data = graphs[0]!.data as GraphCanvasData
    expect(data.nodes.map((n) => n.style)).toEqual([{ x: 300, y: 400 }])
  })
  it('不给位置、不开增强时与 H04 完全一致：数据没有坐标与展示字段', async () => {
    const m = make()
    createGraphLifecycle(box(), { data: sample(), factory: m.factory })
    await settle()
    const init = m.graphs[0]!.init!
    expect(init.positions).toBeNull()
    expect(init.minimap).toBeUndefined()
    expect(init.data.nodes[0]).not.toHaveProperty('style')
    expect(init.data.nodes[0]!.data).not.toHaveProperty('k')
  })
})

describe('增强模式的数据与事件', () => {
  it('数据带展示字段（标签放大 1、全部显示、掌握角标）', async () => {
    const m = make()
    createGraphLifecycle(box(), { data: { nodes: [kp('a', 'c1', ['mastered']), kp('b', 'c2')], edges: [edge] }, factory: m.factory, enhance })
    await settle()
    const [a] = m.graphs[0]!.init!.data.nodes
    expect(a!.data).toMatchObject({ k: 1, nk: 1, labelOn: true, mastery: 'mastered' })
    expect(m.graphs[0]!.init!.data.edges[0]!.data).toMatchObject({ cross: true, showLabel: false })
  })
  it('渲染后上报缩放；点击空白处通知页面', async () => {
    const zooms: number[] = []
    const onBlankClick = vi.fn()
    const { graphs } = start({ onZoom: (z) => zooms.push(z), enhance: { ...enhance, onBlankClick } })
    await settle()
    expect(zooms.at(-1)).toBe(1)
    graphs[0]!.emit('canvas:click')
    expect(onBlankClick).toHaveBeenCalledTimes(1)
  })
  it('小地图：容器与着色回调传给工厂', async () => {
    const mini = document.createElement('div')
    const m = make()
    createGraphLifecycle(box(), { data: { nodes: [kp('a', 'c1', ['selected']), kp('b', 'c2', ['mastered'])], edges: [] }, factory: m.factory, enhance: { ...enhance, minimap: mini } })
    await settle()
    const init = m.graphs[0]!.init!
    expect(init.minimap?.container).toBe(mini)
    expect(init.minimap?.color('kp:a')).toBe(GRAPH_COLORS.accent)
    expect(init.minimap?.color('kp:b')).toBe(GRAPH_COLORS.ok)
    const options = buildGraphOptions({ ...init, container: document.createElement('div') }) as unknown as { plugins: Array<Record<string, unknown>> }
    expect(options.plugins[0]).toMatchObject({ type: 'minimap', key: 'minimap', container: mini, size: [180, 120] })
  })
})

describe('容器尺寸变化策略（增强模式）', () => {
  it('面板开合（ResizeObserver）只 setSize，不整图重新适配；窗口缩放与 refreshSize 才重新适配', async () => {
    const { graphs, life, el } = start()
    await settle()
    const g = graphs[0]!
    g.calls.length = 0

    resize(el, 500)
    FakeResizeObserver.instances[0]!.callback()
    flushFrames()
    await settle()
    expect(g.calls).toContain('setSize 500x600')
    expect(g.calls).not.toContain('fitView')

    g.calls.length = 0
    resize(el, 600)
    window.dispatchEvent(new Event('resize'))
    FakeResizeObserver.instances[0]!.callback()
    flushFrames()
    await settle()
    expect(g.calls).toContain('fitView')

    // 窗口缩放之后的下一次面板开合又回到「只 setSize」
    g.calls.length = 0
    resize(el, 700)
    FakeResizeObserver.instances[0]!.callback()
    flushFrames()
    await settle()
    expect(g.calls).not.toContain('fitView')

    g.calls.length = 0
    resize(el, 650)
    life.refreshSize()
    flushFrames()
    await settle()
    expect(g.calls).toContain('fitView')
  })
  it('未开增强时每次尺寸变化都重新适配（H04 行为不变）', async () => {
    const m = make()
    const el = box()
    createGraphLifecycle(el, { data: sample(), factory: m.factory })
    await settle()
    m.graphs[0]!.calls.length = 0
    resize(el, 500)
    FakeResizeObserver.instances[0]!.callback()
    flushFrames()
    await settle()
    expect(m.graphs[0]!.calls).toContain('fitView')
  })
  it('销毁后移除窗口监听', async () => {
    const remove = vi.spyOn(window, 'removeEventListener')
    const { life } = start()
    await settle()
    life.destroy()
    expect(remove).toHaveBeenCalledWith('resize', expect.any(Function))
  })
})

describe('增强模式的视口方法', () => {
  it('fitTo 把一组知识点放进视口；zoomBy、ensureVisible 转发', async () => {
    const { graphs, life } = start({ positions })
    await settle()
    const g = graphs[0]!
    life.fitTo(['a', 'b'])
    life.zoomBy(2)
    await settle()
    expect(g.calls).toContain('translateBy')
    expect(g.calls).toContain('zoomBy 2')
    g.offset = [-5000, -5000]
    life.ensureVisible('a')
    await settle()
    expect(g.focusCalls.map(([id]) => id)).toEqual(['kp:a'])
  })
  it('setScope 在建图前后都能画出章节外框，null 只隐藏不移除', async () => {
    const { graphs, life } = start({ positions })
    life.setScope(['a'])
    await settle()
    flushFrames()
    expect(graphs[0]!.pluginsAdded).toHaveLength(1)
    life.setScope(null)
    await settle()
    expect(graphs[0]!.pluginUpdates.at(-1)).toMatchObject({ key: 'chapter-hull', visibility: 'hidden' })
    expect(graphs[0]!.pluginsAdded).toHaveLength(1)
  })
  it('未开增强时这些方法是空操作', async () => {
    const m = make()
    const life = createGraphLifecycle(box(), { data: sample(), factory: m.factory })
    await settle()
    life.fitTo(['a'])
    life.setScope(['a'])
    life.zoomBy(2)
    life.ensureVisible('a')
    life.relayoutLabels()
    life.leaveHover()
    await settle()
    expect(m.graphs[0]!.calls).toEqual(['render'])
  })
})

describe('销毁', () => {
  it('增强模式延后 400ms 销毁图实例（插件有延迟回调）；之后迟到的事件被忽略', async () => {
    const onBlankClick = vi.fn()
    const { graphs, life } = start({ enhance: { ...enhance, onBlankClick } })
    await settle()
    vi.useFakeTimers()
    life.destroy()
    expect(graphs[0]!.destroyed).toBe(false)
    graphs[0]!.emit('canvas:click')
    expect(onBlankClick).not.toHaveBeenCalled()
    vi.advanceTimersByTime(400)
    expect(graphs[0]!.destroyed).toBe(true)
  })
  it('未开增强时立即销毁', async () => {
    const m = make()
    const life = createGraphLifecycle(box(), { data: sample(), factory: m.factory })
    await settle()
    life.destroy()
    expect(m.graphs[0]!.destroyed).toBe(true)
  })
})
```

- [ ] **Step 2: 运行，确认失败**

Run: `npm --prefix src/frontend run test -- --run graph-lifecycle-enhance`
Expected: FAIL（`positions`/`enhance` 选项与新方法不存在）

- [ ] **Step 3: 整体替换 `lifecycle.ts`**

这是 Task 8（新主题的 `buildGraphOptions`、`READABLE_ZOOM`/`nodeLabel` 再导出）、Task 9（`CanvasGraph` 接口扩充）与本任务（`positions`、`enhance`、尺寸策略、新方法、延后销毁）合并后的最终文件，**整体替换** `src/frontend/src/graph/lifecycle.ts`：

```ts
import type { GraphData, GraphOptions } from '@antv/g6'
import type { InjectionKey } from 'vue'
import { nodeElementId, type G6Edge, type G6EdgeData, type G6Node, type G6NodeData } from './adapter'
import type { Positions } from './chapterLayout'
import { createEnhancer, type EnhanceOptions, type Enhancer } from './enhancer'
import { badgesFor, nodeLabel } from './presentation'
import { NODE_BASE_PX, READABLE_ZOOM } from './scale'
import { GRAPH_COLORS, GRAPH_FONT, NODE_TYPE_FILL, NODE_TYPE_GLYPH } from './theme'

/** 可读缩放见 `graph/scale.ts`（0.9：新标签 13px，0.7 时只有约 9px）；这里再导出，保持既有导入路径有效 */
export { READABLE_ZOOM }

/**
 * G6 画布生命周期（H04）。
 *
 * 把一张适配图（H03 `toG6Data` 的节点与边）画进容器，并负责：
 * - 挂载：量出容器尺寸再建图；尺寸为 0（隐藏页签、未排版）时推迟到出现尺寸再建。
 * - 更新：`setData` + `render` 串行执行；渲染进行中的多次更新合并为一次，落在最后一次数据。
 * - resize：容器尺寸变化在下一帧合并处理，`setSize` 后重新适应视口；尺寸为 0 或未变时不动。
 * - 销毁：销毁图实例、断开观察、取消待执行帧；之后迟到的建图、渲染结果都被丢弃。
 *
 * 交给 G6 的数据是副本（G6 布局会往数据里写坐标），调用方的对象不被改写。
 * G6 通过工厂创建，默认按需加载 `@antv/g6`，测试可换成替身。
 */

/**
 * 画布元素状态（H05）：筛选层据审核状态与选中项给元素打标，样式见 `buildGraphOptions` 的 `state`。
 * 状态随数据交给 G6，所以重新布局、重设数据都不会丢选中高亮。
 *
 * I06 追加学习状态：学生页按服务端投影的 `MasteryStatus`（`mastered`/`learning`/`notStarted`）
 * 与推荐项（`recommended`）给节点打标；元素只携带状态名，颜色只在 `buildGraphOptions` 定义一处。
 */
export type CanvasElementState =
  | 'selected'
  | 'rejected'
  | 'lowConfidence'
  | 'mastered'
  | 'learning'
  | 'notStarted'
  | 'recommended'
  // L14 学习路径：未满足的前置、之后解锁、与当前路径无关（淡化）；边：路径上的先修边
  | 'pathPrereq'
  | 'pathUnlock'
  | 'dimmed'
  | 'pathEdge'
  // UI-GRAPH-PILOT-01 聚焦与悬停状态（`graph/focusStates.ts` 计算；颜色只在 `buildGraphOptions` 定义一处）
  | 'neighbor'
  | 'match'
  | 'faded'
  | 'hovered'
  | 'hoverRelated'
  | 'hoverFaded'
  | 'active'
  | 'scoped'

export { nodeLabel }

export type CanvasNode = G6Node & { states?: CanvasElementState[]; style?: { x: number; y: number } }
export type CanvasEdge = G6Edge & { states?: CanvasElementState[] }

/** 适配图（H03 `AdaptedGraph` 的节点与边）可直接传入；筛选层可附加 `states` */
export interface GraphCanvasData {
  nodes: CanvasNode[]
  edges: CanvasEdge[]
}

/** 画布布局（H05）：层次（自上而下）或力导向 */
export type GraphLayoutName = 'hierarchical' | 'force'

export interface NodeClickEvent {
  target?: { id?: string }
}

/** 画布事件的公共子集（点击、悬停；`client` 是页面坐标） */
export interface GraphEvent extends NodeClickEvent {
  pointerType?: string
  client?: { x: number; y: number }
}

/** 画布坐标 / 视口坐标（G6 的 `Point` 可带第三维，这里只用前两维） */
export type Point2 = readonly number[]

/** 生命周期用到的 G6 `Graph` 子集 */
export interface CanvasGraph {
  readonly destroyed: boolean
  render(): Promise<void>
  setData(data: GraphCanvasData): void
  setSize(width: number, height: number): void
  fitView(): Promise<void>
  on(event: string, handler: (event: GraphEvent) => void): unknown
  destroy(): void
  /** G6 `Graph` 均有；测试替身可不实现，此时布局切换不生效（H05） */
  setLayout?(layout: NonNullable<GraphOptions['layout']>): void
  layout?(): Promise<void>
  /** 视口（L13）：G6 `Graph` 均有；测试替身可不实现，此时保持整图适配、不做聚焦 */
  getZoom?(): number
  zoomTo?(zoom: number, animation?: unknown): Promise<void>
  focusElement?(id: string, animation?: unknown): Promise<void>
  /**
   * L14：G6 5.x 的 `render()` 每次都按 `autoFit` 重新整图适配，掌握状态、选中、路径高亮引起的数据更新
   * 因此会把视口拉回整图。首次渲染后用它关掉 `autoFit`；之后的适配只在尺寸变化与切换布局时显式 `fitView`。
   */
  setOptions?(options: Partial<GraphOptions>): void
  /**
   * 增强模式（UI-GRAPH-PILOT-01）用到的视口、数据与插件接口：G6 `Graph` 均有；测试替身可不实现，
   * 此时对应能力静默跳过。
   */
  getElementPosition?(id: string): Point2
  getViewportByCanvas?(point: Point2): Point2
  translateBy?(offset: Point2, animation?: unknown): Promise<void>
  zoomBy?(ratio: number, animation?: unknown): Promise<void>
  updateNodeData?(data: ReadonlyArray<Record<string, unknown>>): void
  updateEdgeData?(data: ReadonlyArray<Record<string, unknown>>): void
  draw?(): Promise<void>
  setElementState?(state: Record<string, string[]>, animation?: boolean): Promise<void>
  setPlugins?(update: (plugins: unknown[]) => unknown[]): void
  updatePlugin?(option: Record<string, unknown>): void
  getPluginInstance?(key: string): unknown
}

export interface CanvasGraphInit {
  container: HTMLElement
  width: number
  height: number
  data: GraphCanvasData
  /** 缺省为层次布局 */
  layout?: GraphLayoutName
  /** 预先算好的位置（章节分区布局）：给了就不再让 G6 布局，边画成竖向曲线；只对层次布局生效 */
  positions?: Positions | null
  /** 小地图（增强模式）：外部容器与节点点的着色回调 */
  minimap?: { container: HTMLElement; color: (elementId: string) => string }
}

export type CanvasGraphFactory = (init: CanvasGraphInit) => CanvasGraph | Promise<CanvasGraph>

/**
 * - `waiting`：容器尚无尺寸，未建图
 * - `rendering`：正在加载 G6、渲染或应用更新
 * - `ready`：最近一次数据已画完
 * - `error`：建图或渲染失败，需销毁后重建
 * - `destroyed`：已销毁
 */
export type LifecycleStatus = 'waiting' | 'rendering' | 'ready' | 'error' | 'destroyed'

export interface GraphLifecycleOptions {
  data: GraphCanvasData
  /** 缺省为层次布局 */
  layout?: GraphLayoutName
  /**
   * 章节分区布局算好的位置（知识点 ID → 画布坐标），建图时一次性给定；缺省沿用 G6 布局。
   * 力导向布局下忽略。位置变了（换图、换布局）由调用方重建生命周期。
   */
  positions?: Positions | null
  /**
   * 增强模式（语义缩放、标签排布、悬停强淡化、章节外框、小地图、整组适应）。缺省关闭，行为与 H04 完全一致。
   * 开启后容器尺寸变化（面板开合）只 `setSize`、保持镜头；窗口缩放与 `refreshSize()` 仍整图重新适配。
   */
  enhance?: EnhanceOptions
  factory?: CanvasGraphFactory
  /** 参数是知识点 ID（契约 ID，不带 `kp:` 前缀） */
  onNodeClick?: (kpId: string) => void
  onStatus?: (status: LifecycleStatus, error?: unknown) => void
  /** 视口调整后的缩放值（L13，页面写到 `data-zoom` 供验收） */
  onZoom?: (zoom: number) => void
}

export interface GraphLifecycle {
  readonly status: LifecycleStatus
  update(data: GraphCanvasData): void
  /** 在原图上换布局并适应视口，不重建、不重设数据；尚未建图时建图即用新布局 */
  setLayout(layout: GraphLayoutName): void
  /** 容器可能变了尺寸但观察器不会通知时（如 KeepAlive 重新激活）主动复查 */
  refreshSize(): void
  /** 把视口移到该知识点（搜索定位、问答跳转）；尚未建图时在首次渲染后执行；不在图中的知识点忽略 */
  focus(kpId: string): void
  /** 增强模式：把一组知识点（缺省为当前全部）整体放进视口；未开启增强或尚未建图时忽略 */
  fitTo(kpIds?: readonly string[]): void
  /** 增强模式：章节外框的成员（知识点 ID）；null 隐藏外框 */
  setScope(kpIds: readonly string[] | null): void
  /** 增强模式：按比例缩放（工具栏的放大、缩小） */
  zoomBy(ratio: number): void
  /** 增强模式：节点在视口外时才把镜头移过去（面板里的显式选择） */
  ensureVisible(kpId: string): void
  /** 增强模式：浮层出现、消失、展开收起后重新排布标签 */
  relayoutLabels(): void
  /** 增强模式：指针离开整个画布容器时结束悬停淡化 */
  leaveHover(): void
  destroy(): void
}

/** 画布组件取 G6 工厂的注入键；不提供时用 `loadG6Graph` */
export const GRAPH_FACTORY_KEY: InjectionKey<CanvasGraphFactory> = Symbol('graph-factory')

/** 两种布局的 G6 参数；层次布局与 H04 默认一致 */
export function layoutOptions(layout: GraphLayoutName): NonNullable<GraphOptions['layout']> {
  if (layout === 'force') {
    return { type: 'd3-force', link: { distance: 120 }, manyBody: { strength: -300 }, collide: { radius: 40 } }
  }
  return { type: 'antv-dagre', rankdir: 'TB', nodesep: 40, ranksep: 70 }
}

/**
 * 小地图：只画节点，克隆节点主形状并重新着色（已掌握绿、学习中琥珀、当前高亮靛紫、其余石板灰），
 * 缩略图同时是学习进度总览。装饰性，键盘等价路径是搜索、章节跳转与列表。
 */
function minimapPlugin(minimap: NonNullable<CanvasGraphInit['minimap']>): Record<string, unknown> {
  return {
    type: 'minimap',
    key: 'minimap',
    container: minimap.container,
    size: [180, 120],
    padding: 8,
    filter: (_id: string, kind: string) => kind === 'node',
    shape: (id: string, _kind: string, element: { getShape(name: string): { cloneNode(): { style: Record<string, unknown> } } }) => {
      const dot = element.getShape('key').cloneNode()
      dot.style.fill = minimap.color(id)
      dot.style.lineWidth = 0
      return dot
    },
    maskStyle: { border: `2px solid ${GRAPH_COLORS.accent}`, background: 'rgb(81 69 205 / 12%)' },
    delay: 100,
  }
}

const nd = (d: unknown): G6NodeData => (d as G6Node).data
const ed = (d: unknown): G6EdgeData => (d as G6Edge).data
const labelK = (d: unknown): number => nd(d).k ?? 1
const nodeK = (d: unknown): number => nd(d).nk ?? 1
const lwMin = (d: unknown): number => nd(d).lw ?? 0

/** 默认建图参数：新主题（浅色画布、类型填充 + 单字标记、掌握角标）；布局、缩放、拖拽与平行边处理沿用 H04/H05 */
export function buildGraphOptions(init: CanvasGraphInit): GraphOptions {
  const C = GRAPH_COLORS
  const withPositions = init.positions != null && (init.layout ?? 'hierarchical') === 'hierarchical'
  return {
    container: init.container,
    width: init.width,
    height: init.height,
    data: init.data as unknown as GraphData,
    autoFit: 'view',
    padding: 40,
    animation: false,
    zoomRange: [0.2, 4],
    node: {
      type: 'circle',
      style: {
        size: (d: unknown) => NODE_BASE_PX * nodeK(d),
        fill: (d: unknown) => NODE_TYPE_FILL[nd(d).type],
        stroke: C.nodeStroke,
        lineWidth: (d: unknown) => Math.max(1.5, lwMin(d)),
        iconText: (d: unknown) => NODE_TYPE_GLYPH[nd(d).type],
        iconFontSize: (d: unknown) => 14 * nodeK(d),
        iconFontWeight: 500,
        iconFill: C.text,
        iconFontFamily: GRAPH_FONT,
        labelText: (d: unknown) => nodeLabel(nd(d)),
        labelPlacement: 'bottom',
        // G6 节点的 label 是布尔开关：false 时整个标签不绘制（`labelVisibility` 无效）
        label: (d: unknown) => nd(d).labelOn !== false,
        labelFontSize: (d: unknown) => 13 * labelK(d),
        // 字号随缩放放大时行高必须同步，否则多行标签的两行会叠在一起
        labelLineHeight: (d: unknown) => Math.round(13 * labelK(d) * 1.3),
        labelFontWeight: 500,
        labelFill: C.text,
        labelFontFamily: GRAPH_FONT,
        labelWordWrap: true,
        labelWordWrapWidth: (d: unknown) => 112 * labelK(d),
        labelMaxLines: 2,
        labelTextOverflow: 'ellipsis',
        labelOffsetY: (d: unknown) => 4 * labelK(d),
        // 关系线从标签下方穿过时不应像删除线：标签带与画布同色的不透明底
        labelBackground: true,
        labelBackgroundFill: C.canvas,
        labelBackgroundOpacity: 0.94,
        labelPadding: [1, 3],
        badges: (d: unknown) => badgesFor(nd(d).mastery, nodeK(d)),
      },
      // 多个状态按 states 数组顺序叠加：审核/学习状态在前，聚焦状态居中，选中在后，悬停瞬时状态最后
      state: {
        rejected: { opacity: 0.4, stroke: '#7F8695', lineDash: [4, 3] },
        lowConfidence: { stroke: C.warn, lineDash: [4, 3] },
        // I06：掌握状态色只在这里定义；元素只带状态名，角标由 `badgesFor` 画（颜色之外还有 ✓/◐ 与文字）
        mastered: { stroke: C.ok, lineWidth: 2 },
        learning: { stroke: C.warn, lineWidth: 2 },
        notStarted: { stroke: C.nodeStroke },
        recommended: { stroke: C.accent, lineWidth: 3 },
        // L14 学习路径：未满足的前置（虚线）、之后解锁（点线）；与当前路径无关用 dimmed（标准淡化）
        pathPrereq: { stroke: C.warn, lineWidth: 2.5, lineDash: [4, 3] },
        pathUnlock: { stroke: C.accent, lineWidth: 2, lineDash: [2, 3] },
        // 标准淡化：降填充饱和度，边框 ≥3:1、标签保留（不使用整体 opacity）
        dimmed: { fill: C.dimmedFill, stroke: C.dimmedStroke, labelFill: '#545967', iconFill: '#545967' },
        // 强淡化（Obsidian 式，仅供对比）：近底色小点；标签由排布函数直接隐藏
        faded: { fill: C.fadedFill, stroke: C.fadedStroke, lineWidth: 1, iconFill: C.fadedIcon, halo: false },
        neighbor: { stroke: C.accent, lineWidth: (d: unknown) => Math.max(2, lwMin(d) * 1.5) },
        selected: {
          stroke: C.accent,
          lineWidth: (d: unknown) => Math.max(2.5, lwMin(d) * 2),
          halo: true,
          haloStroke: C.accent,
          haloLineWidth: (d: unknown) => Math.max(5, lwMin(d) * 3),
          haloStrokeOpacity: 0.22,
          labelFontWeight: 700,
        },
        // 搜索命中 / 章节定位：靛紫外环 + 标签加粗改靛紫，不用淡紫色底块
        match: { stroke: C.accent, lineWidth: (d: unknown) => Math.max(2.5, lwMin(d) * 2), labelFill: C.accent, labelFontWeight: 700 },
        // 悬停（瞬时，强淡化）：悬停节点与其直接相邻保持清楚，其余退成近底色小点并隐去标签与角标
        hovered: { stroke: C.accent, lineWidth: (d: unknown) => Math.max(2.5, lwMin(d) * 2), labelFontWeight: 700 },
        hoverRelated: { stroke: C.accent, lineWidth: (d: unknown) => Math.max(2, lwMin(d) * 1.5) },
        hoverFaded: { fill: C.fadedFill, stroke: C.fadedStroke, lineWidth: 1, iconFill: C.fadedIcon, halo: false, label: false, badge: false },
      },
    },
    edge: {
      // 章节分区布局下画竖向曲线；其余不指定 type（平行边转换会把成组的边改为曲线）
      ...(withPositions ? { type: 'cubic-vertical' } : {}),
      style: {
        endArrowSize: (d: unknown) => 9 * (ed(d).ak ?? 1),
        labelFontSize: 12,
        labelFill: C.text,
        labelFontFamily: GRAPH_FONT,
        labelBackground: true,
        labelBackgroundFill: C.panel,
        labelBackgroundOpacity: 1,
        labelPadding: [1, 5],
      },
      state: {
        rejected: { opacity: 0.3 },
        lowConfidence: { opacity: 0.6 },
        pathEdge: { stroke: C.accent, lineWidth: 3.5, halo: false },
        // 与关系线重合的状态不再用 opacity；G6 内置 active 状态自带灰色光晕，必须显式关闭
        active: { lineWidth: (d: unknown) => Math.max(3, (ed(d).lw ?? 0) * 2.5), halo: false },
        scoped: { lineWidth: (d: unknown) => Math.max(2, ed(d).lw ?? 0), halo: false },
        dimmed: { stroke: C.fadedEdge, lineWidth: 1, halo: false },
        faded: { stroke: C.fadedEdge, lineWidth: 1, halo: false },
        hoverFaded: { stroke: C.fadedEdge, lineWidth: 1, halo: false, label: false },
      },
    },
    // 有预先算好的位置时不再让 G6 布局（位置稳定，且可以按章节聚拢）
    ...(withPositions ? {} : { layout: layoutOptions(init.layout ?? 'hierarchical') }),
    behaviors: ['zoom-canvas', 'drag-canvas', 'drag-element'],
    // 同一对知识点间可同时有前置与相关等多条关系，分开画避免重叠
    transforms: ['process-parallel-edges'],
    ...(init.minimap === undefined ? {} : { plugins: [minimapPlugin(init.minimap)] as unknown as GraphOptions['plugins'] }),
  }
}


/** 按需加载 G6，让未打开图谱的页面不下载它 */
export const loadG6Graph: CanvasGraphFactory = async (init) => {
  const { Graph } = await import('@antv/g6')
  return new Graph(buildGraphOptions(init)) as unknown as CanvasGraph
}

function copyNode(node: CanvasNode, positions: Positions | null): CanvasNode {
  const copy: CanvasNode = { id: node.id, data: { ...node.data } }
  if (node.states !== undefined) copy.states = [...node.states]
  const at = positions?.get(node.data.kpId)
  if (at !== undefined) copy.style = { x: at.x, y: at.y }
  return copy
}

function copyEdge(edge: CanvasEdge): CanvasEdge {
  const copy: CanvasEdge = {
    id: edge.id,
    source: edge.source,
    target: edge.target,
    data: { ...edge.data },
    style: { ...edge.style, lineDash: [...edge.style.lineDash] },
  }
  if (edge.states !== undefined) copy.states = [...edge.states]
  return copy
}

function copyData(data: GraphCanvasData, positions: Positions | null): GraphCanvasData {
  return { nodes: data.nodes.map((node) => copyNode(node, positions)), edges: data.edges.map(copyEdge) }
}

function kpIndex(data: GraphCanvasData): Map<string, string> {
  return new Map(data.nodes.map((node) => [node.id, node.data.kpId]))
}

export function createGraphLifecycle(container: HTMLElement, options: GraphLifecycleOptions): GraphLifecycle {
  const factory = options.factory ?? loadG6Graph
  /** 章节分区布局的位置，只对层次布局生效（力导向由 G6 自己布局） */
  const positions: Positions | null = (options.layout ?? 'hierarchical') === 'hierarchical' ? (options.positions ?? null) : null
  let status: LifecycleStatus = 'waiting'
  let graph: CanvasGraph | null = null
  let creating = false
  /** 尚未交给 G6 的最新数据；null 表示已同步 */
  let pending: GraphCanvasData | null = copyData(options.data, positions)
  /** 当前画布上的元素 ID → 知识点 ID */
  let drawn = new Map<string, string>()
  /** 当前画布上的边（入口节点判定用） */
  let lastEdges: GraphCanvasData['edges'] = []
  let width = 0
  let height = 0
  /** 期望的布局，与 G6 实例当前使用的布局 */
  let layout: GraphLayoutName = options.layout ?? 'hierarchical'
  let appliedLayout: GraphLayoutName = layout
  let frame: number | null = null
  /** 所有对 G6 的异步操作串行执行 */
  let chain: Promise<void> = Promise.resolve()
  /** 建图前请求的聚焦目标（知识点 ID） */
  let pendingFocus: string | null = null
  /** 最近一次页面请求聚焦的知识点（L14）：尺寸变化重新适配后回到它，而不是入口节点 */
  let anchor: string | null = null

  const alive = () => status !== 'destroyed' && status !== 'error'

  function setStatus(next: LifecycleStatus, error?: unknown): void {
    status = next
    options.onStatus?.(next, error)
  }

  function fail(error: unknown): void {
    if (!alive()) return
    setStatus('error', error)
  }

  function enqueue(task: () => Promise<void>): void {
    chain = chain.then(async () => {
      if (!alive()) return
      try {
        await task()
      } catch (error) {
        fail(error)
      }
    })
  }

  const enhancer: Enhancer | null =
    options.enhance === undefined
      ? null
      : createEnhancer({
          graph: () => graph,
          size: () => [width, height],
          enqueue,
          alive,
          onZoom: (zoom) => options.onZoom?.(zoom),
          options: options.enhance,
        })

  /** 交给 G6 的数据：增强模式下附上缩放档位、标签开关、掌握角标等展示字段 */
  function prepare(data: GraphCanvasData): GraphCanvasData {
    return enhancer === null ? data : enhancer.decorate(data)
  }

  function measure(): [number, number] {
    return [container.clientWidth, container.clientHeight]
  }

  function reportZoom(g: CanvasGraph): void {
    if (g.getZoom !== undefined) options.onZoom?.(g.getZoom())
  }

  /** 入口节点：数据中第一个没有入边的节点；全图成环时取第一个节点 */
  function entryNode(): string | null {
    const ids = [...drawn.keys()]
    if (ids.length === 0) return null
    return ids.find((id) => !lastEdges.some((e) => e.target === id)) ?? ids[0]!
  }

  /** 整图适配之后：缩放低于可读值时放大并聚焦（有待聚焦目标时聚焦目标，否则入口节点） */
  async function ensureReadable(g: CanvasGraph): Promise<void> {
    if (g.getZoom !== undefined && g.zoomTo !== undefined && g.getZoom() < READABLE_ZOOM) {
      await g.zoomTo(READABLE_ZOOM)
      if (!alive()) return
      const wanted = pendingFocus ?? anchor
      const target = wanted !== null && drawn.has(nodeElementId(wanted)) ? nodeElementId(wanted) : entryNode()
      pendingFocus = null
      if (target !== null && drawn.has(target) && g.focusElement !== undefined) await g.focusElement(target)
    } else if (pendingFocus !== null) {
      const target = nodeElementId(pendingFocus)
      pendingFocus = null
      if (drawn.has(target) && g.focusElement !== undefined) await g.focusElement(target)
    }
    if (alive()) reportZoom(g)
  }

  function create(): void {
    creating = true
    enqueue(async () => {
      setStatus('rendering')
      const data = prepare(pending ?? { nodes: [], edges: [] })
      pending = null
      appliedLayout = layout
      const minimap =
        enhancer !== null && options.enhance?.minimap != null
          ? { container: options.enhance.minimap, color: (id: string) => enhancer.minimapColor(id) }
          : undefined
      const created = await factory({ container, width, height, data, layout, positions, minimap })
      if (!alive()) {
        created.destroy()
        return
      }
      graph = created
      drawn = kpIndex(data)
      lastEdges = data.edges
      graph.on('node:click', (event) => {
        const kpId = event.target?.id === undefined ? undefined : drawn.get(event.target.id)
        if (kpId !== undefined && alive()) options.onNodeClick?.(kpId)
      })
      enhancer?.attach()
      await graph.render()
      if (!alive()) return
      // 之后的数据更新保持学生正在看的位置，不再回到整图适配（见 `CanvasGraph.setOptions`）
      graph.setOptions?.({ autoFit: undefined })
      await ensureReadable(graph)
      if (!alive()) return
      await enhancer?.afterRender()
      if (!alive()) return
      if (pending !== null) flush()
      else setStatus('ready')
      // 加载 G6 期间切换过布局
      if (appliedLayout !== layout) relayout()
    })
  }

  /** 可重复调用：排到时布局已是期望值即空转，连续切换因此只落在最后一次 */
  function relayout(): void {
    enqueue(async () => {
      const g = graph
      if (g === null || appliedLayout === layout) return
      if (g.setLayout === undefined || g.layout === undefined) return
      appliedLayout = layout
      setStatus('rendering')
      g.setLayout(layoutOptions(layout))
      await g.layout()
      if (!alive()) return
      await g.fitView()
      if (!alive()) return
      await ensureReadable(g)
      if (!alive()) return
      await enhancer?.afterRender()
      if (!alive()) return
      // 期间又有更新或切换时，已排队的 flush / relayout 负责收尾
      if (pending === null && appliedLayout === layout) setStatus('ready')
    })
  }

  /** 可重复调用：排到时若数据已被前一次取走即空转，连续更新因此只画最后一次 */
  function flush(): void {
    enqueue(async () => {
      if (graph === null || pending === null) return
      const data = prepare(pending)
      pending = null
      setStatus('rendering')
      graph.setData(data)
      drawn = kpIndex(data)
      lastEdges = data.edges
      await graph.render()
      if (!alive()) return
      await enhancer?.afterRender()
      if (!alive()) return
      if (pending !== null) flush()
      else setStatus('ready')
    })
  }

  /** 下一次尺寸变化是否整图重新适配：窗口缩放与 `refreshSize()` 为真；增强模式下的面板开合为假 */
  let refitNext = enhancer === null

  function applySize(): void {
    frame = null
    if (!alive()) return
    const refit = refitNext || enhancer === null
    refitNext = enhancer === null
    const [w, h] = measure()
    if (w <= 0 || h <= 0 || (w === width && h === height)) return
    width = w
    height = h
    if (graph === null) {
      if (!creating) create()
      return
    }
    enqueue(async () => {
      graph!.setSize(w, h)
      if (refit) {
        await graph!.fitView()
        if (alive()) await ensureReadable(graph!)
      }
      // 画布尺寸变了：标签排布依赖视口，章节外框与小地图随之重算
      if (alive()) await enhancer?.afterRender()
    })
  }

  function scheduleSize(): void {
    if (frame !== null || !alive()) return
    frame = requestAnimationFrame(applySize)
  }

  let stopObserving: () => void
  if (typeof ResizeObserver === 'function') {
    const observer = new ResizeObserver(scheduleSize)
    observer.observe(container)
    // 增强模式：容器尺寸变化多半是面板开合（只 setSize）；窗口缩放才整图重新适配
    const onWindowResize = () => {
      refitNext = true
    }
    if (enhancer !== null) window.addEventListener('resize', onWindowResize)
    stopObserving = () => {
      observer.disconnect()
      if (enhancer !== null) window.removeEventListener('resize', onWindowResize)
    }
  } else {
    window.addEventListener('resize', scheduleSize)
    stopObserving = () => window.removeEventListener('resize', scheduleSize)
  }

  ;[width, height] = measure()
  if (width > 0 && height > 0) create()
  else options.onStatus?.('waiting')

  return {
    get status() {
      return status
    },
    update(data) {
      if (!alive()) return
      pending = copyData(data, positions)
      if (graph !== null) flush()
    },
    setLayout(next) {
      if (!alive() || next === layout) return
      layout = next
      if (graph !== null) relayout()
    },
    refreshSize() {
      refitNext = true
      scheduleSize()
    },
    focus(kpId) {
      if (!alive()) return
      anchor = kpId
      if (graph === null) {
        pendingFocus = kpId
        return
      }
      enqueue(async () => {
        const g = graph
        const target = nodeElementId(kpId)
        if (g === null || g.focusElement === undefined || !drawn.has(target)) return
        await g.focusElement(target)
      })
    },
    fitTo(kpIds) {
      if (!alive() || enhancer === null || graph === null) return
      enqueue(() => enhancer.fitTo(kpIds))
    },
    setScope(kpIds) {
      if (!alive() || enhancer === null) return
      // 建图前先记下，渲染后由 `afterRender` 画出；建图后排在当前渲染之后
      if (graph === null) enhancer.setScope(kpIds)
      else enqueue(async () => enhancer.setScope(kpIds))
    },
    zoomBy(ratio) {
      if (!alive() || enhancer === null || graph === null) return
      enqueue(() => enhancer.zoomBy(ratio))
    },
    ensureVisible(kpId) {
      if (!alive() || enhancer === null || graph === null) return
      enqueue(() => enhancer.ensureVisible(kpId))
    },
    relayoutLabels() {
      if (alive()) enhancer?.relayoutLabels()
    },
    leaveHover() {
      if (alive()) enhancer?.leaveHover()
    },
    destroy() {
      if (status === 'destroyed') return
      stopObserving()
      if (frame !== null) cancelAnimationFrame(frame)
      frame = null
      setStatus('destroyed')
      enhancer?.detach()
      const g = graph
      if (g !== null && !g.destroyed) {
        if (enhancer === null) g.destroy()
        else {
          // 小地图、章节外框插件在视口变化后有延迟回调：立刻销毁会让它们在销毁后读取已清空的数据而抛错。
          // 延后一点再销毁；销毁本身可能返回会拒绝的 Promise，一并吞掉
          setTimeout(() => {
            try {
              void Promise.resolve(g.destroy()).catch(() => undefined)
            } catch {
              /* 已销毁 */
            }
          }, 400)
        }
      }
      graph = null
      drawn = new Map()
    },
  }
}
```

- [ ] **Step 4: 运行，确认通过；再跑所有受影响的既有用例**

Run: `npm --prefix src/frontend run test -- --run graph-lifecycle-enhance graph-enhancer graph-options h03 h04 h05 i06 l13 l14`
Expected: 全部通过（既有 `h04`/`h05` 的生命周期调用序列断言**一条都不改**——不开增强时行为完全不变）；`npm --prefix src/frontend run type-check` 退出码 0

- [ ] **Step 5: 提交（仅在用户授权后）**

```bash
git add src/frontend/src/graph/lifecycle.ts tests/frontend/graph-lifecycle-enhance.test.ts
git commit -m "feat(frontend): wire enhancer, chapter positions and resize policy into graph lifecycle"
```

---

## 第四阶段：页面层

### Task 11: 浮层障碍物注册表、减少动效、内联图标、适配层逆运算

**Files:**
- Create: `src/frontend/src/graph/obstacles.ts`
- Create: `src/frontend/src/composables/useReducedMotion.ts`
- Create: `src/frontend/src/components/AppIcon.vue`
- Modify: `src/frontend/src/graph/adapter.ts`（增加 `kpIdFromElementId`）
- Test: `tests/frontend/graph-obstacles.test.ts`

**Interfaces:**
- Produces：
  ```ts
  // obstacles.ts
  export type ObstacleKind = 'hard' | 'soft'
  export interface ObstacleRegistry { register(el: HTMLElement, kind?: ObstacleKind): () => void; boxes(base: HTMLElement): { hard: Box[]; soft: Box[] }; onChange(listener: () => void): () => void }
  export function createObstacleRegistry(): ObstacleRegistry
  export const GRAPH_OBSTACLES_KEY: InjectionKey<ObstacleRegistry>
  export function useGraphObstacle(el: Ref<HTMLElement | null>, kind?: ObstacleKind): void   // 挂载登记、卸载注销；没有注册表时空操作
  // useReducedMotion.ts
  export function useReducedMotion(): Ref<boolean>
  // adapter.ts
  export function kpIdFromElementId(elementId: string): string   // `kp:xxx` → `xxx`
  // AppIcon.vue：<AppIcon name="home|overview|graph|chat|key|menu|map|filter|chapters|search|plus|minus|fit|list|back|chevron|chevronDown|close|panel|expand|collapse|check|half|eyeOff|warn" :size="18" />
  ```
- 包围盒四周外扩 6px，相对 `base` 元素左上角；尺寸为 0（隐藏）的元素忽略。

- [ ] **Step 1: 写测试**

`tests/frontend/graph-obstacles.test.ts`：

```ts
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { createObstacleRegistry, GRAPH_OBSTACLES_KEY, useGraphObstacle } from '../../src/frontend/src/graph/obstacles'

function rect(el: HTMLElement, left: number, top: number, width: number, height: number): void {
  el.getBoundingClientRect = () =>
    ({ left, top, width, height, right: left + width, bottom: top + height, x: left, y: top, toJSON: () => ({}) }) as DOMRect
}

class FakeResizeObserver {
  static instances: FakeResizeObserver[] = []
  observed = new Set<Element>()
  constructor(readonly callback: () => void) {
    FakeResizeObserver.instances.push(this)
  }
  observe(el: Element): void {
    this.observed.add(el)
  }
  unobserve(el: Element): void {
    this.observed.delete(el)
  }
  disconnect(): void {}
}

beforeEach(() => {
  FakeResizeObserver.instances = []
  vi.stubGlobal('ResizeObserver', FakeResizeObserver)
})
afterEach(() => vi.unstubAllGlobals())

describe('createObstacleRegistry', () => {
  it('包围盒相对画布左上角，四周外扩 6px，硬/软障碍分开', () => {
    const registry = createObstacleRegistry()
    const base = document.createElement('div')
    rect(base, 100, 50, 800, 600)
    const bar = document.createElement('div')
    rect(bar, 120, 60, 280, 40)
    const legend = document.createElement('div')
    rect(legend, 110, 400, 200, 100)
    registry.register(bar)
    registry.register(legend, 'soft')
    expect(registry.boxes(base)).toEqual({
      hard: [[14, 4, 306, 56]],
      soft: [[4, 344, 216, 456]],
    })
  })
  it('尺寸为 0（隐藏）的元素被忽略；注销后不再计入', () => {
    const registry = createObstacleRegistry()
    const base = document.createElement('div')
    rect(base, 0, 0, 800, 600)
    const hidden = document.createElement('div')
    rect(hidden, 10, 10, 0, 0)
    const shown = document.createElement('div')
    rect(shown, 10, 10, 50, 20)
    registry.register(hidden)
    const off = registry.register(shown)
    expect(registry.boxes(base).hard).toHaveLength(1)
    off()
    expect(registry.boxes(base).hard).toHaveLength(0)
  })
  it('登记、注销和元素尺寸变化时通知订阅者；取消订阅后不再通知', () => {
    const registry = createObstacleRegistry()
    const listener = vi.fn()
    const stop = registry.onChange(listener)
    const el = document.createElement('div')
    const off = registry.register(el)
    expect(listener).toHaveBeenCalledTimes(1)
    FakeResizeObserver.instances[0]!.callback()
    expect(listener).toHaveBeenCalledTimes(2)
    off()
    expect(listener).toHaveBeenCalledTimes(3)
    off() // 重复注销不再通知
    expect(listener).toHaveBeenCalledTimes(3)
    stop()
    registry.register(el)
    expect(listener).toHaveBeenCalledTimes(3)
  })
})

describe('useGraphObstacle', () => {
  const Overlay = defineComponent({
    setup() {
      const el = ref<HTMLElement | null>(null)
      useGraphObstacle(el, 'soft')
      return () => h('div', { ref: el }, '浮层')
    },
  })

  it('挂载时登记、卸载时注销', () => {
    const registry = createObstacleRegistry()
    const listener = vi.fn()
    registry.onChange(listener)
    const wrapper = mount(Overlay, { global: { provide: { [GRAPH_OBSTACLES_KEY as symbol]: registry } } })
    expect(listener).toHaveBeenCalledTimes(1)
    const base = document.createElement('div')
    rect(base, 0, 0, 100, 100)
    rect(wrapper.element as HTMLElement, 10, 10, 20, 20)
    expect(registry.boxes(base).soft).toHaveLength(1)
    wrapper.unmount()
    expect(registry.boxes(base).soft).toHaveLength(0)
  })
  it('没有注册表时什么都不做', () => {
    expect(() => mount(Overlay).unmount()).not.toThrow()
  })
})
```

- [ ] **Step 2: 运行，确认失败**

Run: `npm --prefix src/frontend run test -- --run graph-obstacles`
Expected: FAIL（找不到 `graph/obstacles`）

- [ ] **Step 3: 实现**

`src/frontend/src/graph/obstacles.ts`：

```ts
import { inject, onBeforeUnmount, onMounted, type InjectionKey, type Ref } from 'vue'
import type { Box } from './labelPlan'

/**
 * 浮层障碍物注册表（UI-GRAPH-PILOT-01，规格 §4 第 1 层）。
 *
 * 工具栏、搜索栏、图例、小地图、底部折叠条、预览卡、提示条会盖在画布上。标签排布与镜头适应要避开它们，
 * 所以浮层组件把自己的根元素登记进来，画布按当前屏幕位置取包围盒。
 * - `hard`：标签与镜头适应都要避开；
 * - `soft`（如可展开的图例）：只有标签避开，镜头适应不为它缩小范围。
 */
export type ObstacleKind = 'hard' | 'soft'

export interface ObstacleRegistry {
  /** 登记元素，返回注销函数 */
  register(el: HTMLElement, kind?: ObstacleKind): () => void
  /** 相对 `base` 元素左上角的包围盒（四周外扩 6px，留出标签与浮层之间的间隙）；尺寸为 0 的元素忽略 */
  boxes(base: HTMLElement): { hard: Box[]; soft: Box[] }
  /** 登记、注销或元素尺寸变化时通知；返回取消订阅函数 */
  onChange(listener: () => void): () => void
}

const PAD = 6

export function createObstacleRegistry(): ObstacleRegistry {
  const items = new Map<HTMLElement, ObstacleKind>()
  const listeners = new Set<() => void>()
  let observer: ResizeObserver | null = null
  const notify = () => listeners.forEach((listener) => listener())

  return {
    register(el, kind = 'hard') {
      items.set(el, kind)
      if (typeof ResizeObserver === 'function') {
        observer ??= new ResizeObserver(notify)
        observer.observe(el)
      }
      notify()
      return () => {
        if (!items.delete(el)) return
        observer?.unobserve(el)
        notify()
      }
    },
    boxes(base) {
      const origin = base.getBoundingClientRect()
      const out: { hard: Box[]; soft: Box[] } = { hard: [], soft: [] }
      for (const [el, kind] of items) {
        const r = el.getBoundingClientRect()
        if (r.width <= 0 || r.height <= 0) continue
        out[kind].push([r.left - origin.left - PAD, r.top - origin.top - PAD, r.right - origin.left + PAD, r.bottom - origin.top + PAD])
      }
      return out
    },
    onChange(listener) {
      listeners.add(listener)
      return () => {
        listeners.delete(listener)
      }
    },
  }
}

/** 页面提供、画布与浮层注入；不提供时画布不做浮层避让 */
export const GRAPH_OBSTACLES_KEY: InjectionKey<ObstacleRegistry> = Symbol('graph-obstacles')

/** 浮层组件内使用：挂载时登记根元素，卸载时注销；没有注册表时什么都不做 */
export function useGraphObstacle(el: Ref<HTMLElement | null>, kind: ObstacleKind = 'hard'): void {
  const registry = inject(GRAPH_OBSTACLES_KEY, null)
  let off: (() => void) | null = null
  onMounted(() => {
    if (registry !== null && el.value !== null) off = registry.register(el.value, kind)
  })
  onBeforeUnmount(() => off?.())
}
```

`src/frontend/src/composables/useReducedMotion.ts`：

```ts
import { onBeforeUnmount, ref, type Ref } from 'vue'

/**
 * `prefers-reduced-motion: reduce` 的响应式读取（规格 §8、§9）：图谱镜头动画与淡入据此关闭。
 * 没有 `matchMedia` 的环境（部分测试）视为不减少动效。
 */
export function useReducedMotion(): Ref<boolean> {
  const reduced = ref(false)
  if (typeof matchMedia !== 'function') return reduced
  const query = matchMedia('(prefers-reduced-motion: reduce)')
  reduced.value = query.matches
  const onChange = (event: MediaQueryListEvent) => {
    reduced.value = event.matches
  }
  query.addEventListener?.('change', onChange)
  onBeforeUnmount(() => query.removeEventListener?.('change', onChange))
  return reduced
}
```

`src/frontend/src/components/AppIcon.vue`：

```vue
<script setup lang="ts">
/** 内联图标（24 格、1.75 描边），不引入图标库；装饰用（`aria-hidden`），可访问名称由外层按钮提供 */
defineProps<{ name: string; size?: number }>()

const PATHS: Record<string, string> = {
  home: '<path d="M3.5 11 12 4l8.5 7"/><path d="M5.5 10v9.5h4.5v-5.5h4v5.5h4.5V10"/>',
  overview: '<rect x="4" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5"/>',
  graph: '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="8" r="2.5"/><circle cx="9" cy="18" r="2.5"/><path d="m8 7 8 .8M7.2 8.2 8.4 15.6M16.6 10l-5.8 6.4"/>',
  chat: '<path d="M5 5.5h14v10H11l-4.5 3.5v-3.5H5z"/>',
  key: '<circle cx="8" cy="15" r="3.5"/><path d="m10.5 12.5 8-8M15 8l2.5 2.5M17.5 5.5 20 8"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  map: '<path d="M4 6.5 9 4l6 2.5L20 4v13.5L15 20l-6-2.5L4 20z"/><path d="M9 4v13.5M15 6.5V20"/>',
  filter: '<path d="M4 6h16M7 12h10M10 18h4"/>',
  chapters:'<path d="M5 6h14M5 11h14M5 16h9M5 21h6"/>',
  search:'<circle cx="11" cy="11" r="6"/><path d="m20 20-4.5-4.5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  minus: '<path d="M5 12h14"/>',
  fit: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
  list: '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.8" cy="6" r=".6"/><circle cx="4.8" cy="12" r=".6"/><circle cx="4.8" cy="18" r=".6"/>',
  back: '<path d="m14.5 6-6 6 6 6"/>',
  chevron: '<path d="m9.5 6 6 6-6 6"/>',
  chevronDown: '<path d="m6 9.5 6 6 6-6"/>',
  close: '<path d="m6 6 12 12M18 6 6 18"/>',
  panel: '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M9.5 4.5v15"/>',
  expand: '<path d="m6 7 5 5-5 5M13 7l5 5-5 5"/>',
  collapse: '<path d="m11 7-5 5 5 5M18 7l-5 5 5 5"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  half: '<circle cx="12" cy="12" r="7.5"/><path d="M12 4.5a7.5 7.5 0 0 1 0 15z" fill="currentColor"/>',
  eyeOff: '<path d="M4 4l16 16M9.5 5.6A8.8 8.8 0 0 1 12 5.3c4.4 0 7.5 4.2 8.5 6.7a12 12 0 0 1-2.4 3.4M6.3 7.7A12.4 12.4 0 0 0 3.5 12c1 2.5 4.1 6.7 8.5 6.7 1.2 0 2.2-.3 3.2-.7"/>',
  warn: '<path d="M12 4.5 21 19.5H3z"/><path d="M12 10v4.5M12 17v.2"/>',
}
</script>

<template>
  <svg
    :width="size ?? 18"
    :height="size ?? 18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.75"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
    v-html="PATHS[name] ?? ''"
  />
</template>
```

在 `src/frontend/src/graph/adapter.ts` 的 `nodeElementId` 之后、`edgeElementId` 之前增加：

```ts
/** 元素 ID 还原为契约的知识点 ID（`nodeElementId` 的逆运算） */
export function kpIdFromElementId(elementId: string): string {
  return elementId.startsWith('kp:') ? elementId.slice(3) : elementId
}
```

- [ ] **Step 4: 运行，确认通过**

Run: `npm --prefix src/frontend run test -- --run graph-obstacles && npm --prefix src/frontend run type-check`
Expected: 5 passed；type-check 退出码 0

- [ ] **Step 5: 提交（仅在用户授权后）**

```bash
git add src/frontend/src/graph/obstacles.ts src/frontend/src/composables/useReducedMotion.ts src/frontend/src/components/AppIcon.vue src/frontend/src/graph/adapter.ts tests/frontend/graph-obstacles.test.ts
git commit -m "feat(frontend): add overlay obstacle registry, reduced-motion helper and inline icons"
```

---

### Task 12: `GraphCanvas` 增强模式

**Files:**
- Modify（整体替换）: `src/frontend/src/components/GraphCanvas.vue`
- Test: `tests/frontend/graph-canvas-enhanced.test.ts`

**Interfaces:**
- Consumes: `createGraphLifecycle`（Task 10）、`GRAPH_OBSTACLES_KEY`/`useGraphObstacle`（Task 11）、`useReducedMotion`、`MASTERY_TEXT`/`masteryOfStates`（Task 7）、`AppIcon`。
- Produces（页面依赖）：
  ```ts
  // props（新增）：enhanced?: boolean（默认 false，教师页沿用 H04 行为）; positions?: Positions | null; scope?: readonly string[] | null
  // emits：nodeClick(kpId)；blankClick()
  // expose：focus(kpId)；fitTo(kpIds?)；ensureVisible(kpId)
  ```
- 行为要点：增强 + 层次布局时**位置为 `null` 就不建图**（显示加载），到了再建；位置从 Map 变 `null`（重算）时拆掉旧画布，从一份变另一份同样重建；首次 `null → Map` 由 `ready` 负责建图、**不重复建**（曾因此建两次）；增强模式切换布局重建（普通模式在原图上 `setLayout`）；重建后回到最近一次聚焦的节点（`lastFocus`，不是只用一次的 `pendingFocus`）；传给生命周期的位置是 `toRaw`（保持 Map 恒等）；悬停 300ms 后出现「名称（掌握状态文字）」tooltip；小地图默认 ≥1024px 展开；`data-zoom` 与既有 `data-test="graph-canvas"` 保留。

- [ ] **Step 1: 写测试**

`tests/frontend/graph-canvas-enhanced.test.ts`：

```ts
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, ref, type Ref } from 'vue'
import GraphCanvas from '../../src/frontend/src/components/GraphCanvas.vue'
import type { Positions } from '../../src/frontend/src/graph/chapterLayout'
import {
  GRAPH_FACTORY_KEY,
  type CanvasEdge,
  type CanvasGraphFactory,
  type CanvasNode,
  type GraphCanvasData,
  type GraphLayoutName,
} from '../../src/frontend/src/graph/lifecycle'
import { FakeEnhancedGraph } from './fakeEnhancedGraph'

function kp(id: string, states?: CanvasNode['states']): CanvasNode {
  return {
    id: `kp:${id}`,
    data: { kpId: id, name: `知识点${id}`, type: 'concept', level: 1, chapterId: 'c1', status: 'approved', confidence: 1, source: 'ai', locked: false },
    ...(states === undefined ? {} : { states }),
  }
}
const edge: CanvasEdge = {
  id: 'rel:r1',
  source: 'kp:a',
  target: 'kp:b',
  data: { relationId: 'r1', type: 'PREREQUISITE', directed: true, status: 'approved', confidence: 1, source: 'ai', downgraded: false },
  style: { stroke: '#5145CD', lineWidth: 2, lineDash: [], endArrow: true, labelText: '前置' },
}
const sample = (): GraphCanvasData => ({ nodes: [kp('a', ['mastered']), kp('b')], edges: [edge] })
const positionsA: Positions = new Map([['a', { x: 0, y: 0 }], ['b', { x: 100, y: 100 }]])
const positionsB: Positions = new Map([['a', { x: 5, y: 5 }], ['b', { x: 50, y: 50 }]])

async function settle(): Promise<void> {
  for (let i = 0; i < 10; i += 1) await Promise.resolve()
  await new Promise((resolve) => setTimeout(resolve, 5))
}

/** jsdom 不排版：画布容器给 800×600，其他元素为 0 */
function sizeStages(): () => void {
  for (const [key, value] of [['clientWidth', 800], ['clientHeight', 600]] as const) {
    Object.defineProperty(HTMLElement.prototype, key, {
      configurable: true,
      get(this: HTMLElement) {
        return this.classList.contains('graph-canvas__stage') ? value : 0
      },
    })
  }
  return () => {
    for (const key of ['clientWidth', 'clientHeight']) delete (HTMLElement.prototype as unknown as Record<string, unknown>)[key]
  }
}

class NoopResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

function setup(props: { enhanced?: boolean; positions?: Ref<Positions | null>; layout?: Ref<GraphLayoutName>; scope?: Ref<string[] | null> } = {}) {
  const graphs: FakeEnhancedGraph[] = []
  const factory: CanvasGraphFactory = (init) => {
    const g = new FakeEnhancedGraph({}, init)
    graphs.push(g)
    return g
  }
  const clicked: string[] = []
  const blank = vi.fn()
  const positions = props.positions ?? ref<Positions | null>(positionsA)
  const layout = props.layout ?? ref<GraphLayoutName>('hierarchical')
  const scope = props.scope ?? ref<string[] | null>(null)
  const Host = defineComponent({
    setup() {
      return () =>
        h(GraphCanvas, {
          graph: sample(),
          enhanced: props.enhanced ?? true,
          positions: positions.value,
          layout: layout.value,
          scope: scope.value,
          onNodeClick: (id: string) => clicked.push(id),
          onBlankClick: blank,
        })
    },
  })
  const wrapper = mount(Host, { attachTo: document.body, global: { provide: { [GRAPH_FACTORY_KEY as symbol]: factory } } })
  return { wrapper, graphs, clicked, blank, positions, layout, scope }
}

let restoreSize: () => void
beforeEach(() => {
  restoreSize = sizeStages()
  vi.stubGlobal('ResizeObserver', NoopResizeObserver)
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
    cb(0)
    return 0
  })
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  restoreSize()
})

describe('GraphCanvas 增强模式', () => {
  it('位置还在计算（null）时只显示加载，不建图；位置到达后用同一份位置建图并带上小地图容器', async () => {
    const positions = ref<Positions | null>(null)
    const { wrapper, graphs } = setup({ positions })
    await settle()
    expect(graphs).toHaveLength(0)
    expect(wrapper.get('[role="status"]').text()).toContain('加载中')
    positions.value = positionsA
    await settle()
    expect(graphs).toHaveLength(1)
    expect(graphs[0]!.init!.positions).toBe(positionsA)
    expect(graphs[0]!.init!.minimap?.container).toBe(wrapper.get('.gw-mini').element)
    wrapper.unmount()
  })

  it('力导向布局不需要位置，直接建图', async () => {
    const { graphs, wrapper } = setup({ positions: ref<Positions | null>(null), layout: ref<GraphLayoutName>('force') })
    await settle()
    expect(graphs).toHaveLength(1)
    expect(graphs[0]!.init!.positions).toBeNull()
    wrapper.unmount()
  })

  it('地图与缩放控件：小地图开关、放大、缩小、适应画布都有可访问名称并转发给画布', async () => {
    const { wrapper, graphs } = setup()
    await settle()
    const group = wrapper.get('[role="group"][aria-label="地图与缩放"]')
    const names = group.findAll('button').map((b) => b.attributes('aria-label'))
    expect(names).toEqual(['收起小地图', '放大', '缩小', '适应画布'])
    await group.get('[aria-label="放大"]').trigger('click')
    await group.get('[aria-label="缩小"]').trigger('click')
    await group.get('[aria-label="适应画布"]').trigger('click')
    await settle()
    expect(graphs[0]!.calls).toContain('zoomBy 1.25')
    expect(graphs[0]!.calls).toContain('zoomBy 0.8')
    expect(graphs[0]!.calls).toContain('translateBy')
    await group.get('[aria-label="收起小地图"]').trigger('click')
    expect(group.get('[aria-pressed]').attributes('aria-pressed')).toBe('false')
    expect(wrapper.get('.gw-mini').isVisible()).toBe(false)
    wrapper.unmount()
  })

  it('点击节点与点击空白处分别向页面发事件', async () => {
    const { wrapper, graphs, clicked, blank } = setup()
    await settle()
    graphs[0]!.emit('node:click', { target: { id: 'kp:a' } })
    graphs[0]!.emit('canvas:click')
    expect(clicked).toEqual(['a'])
    expect(blank).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('位置变化（换版本重算）重建画布；增强模式切换布局同样重建', async () => {
    const positions = ref<Positions | null>(positionsA)
    const layout = ref<GraphLayoutName>('hierarchical')
    const { wrapper, graphs } = setup({ positions, layout })
    await settle()
    expect(graphs).toHaveLength(1)
    positions.value = positionsB
    await settle()
    expect(graphs).toHaveLength(2)
    expect(graphs[1]!.init!.positions).toBe(positionsB)
    layout.value = 'force'
    await settle()
    expect(graphs).toHaveLength(3)
    expect(graphs[2]!.init!.positions).toBeNull()
    wrapper.unmount()
  })

  it('位置重新计算（位置 → null）时拆掉旧画布并显示加载，新位置到了再重建，且回到最近一次聚焦的节点', async () => {
    const positions = ref<Positions | null>(positionsA)
    const { wrapper, graphs } = setup({ positions })
    await settle()
    wrapper.findComponent(GraphCanvas).vm.focus('b')
    await settle()
    positions.value = null
    await settle()
    expect(graphs).toHaveLength(1)
    expect(wrapper.get('[role="status"]').text()).toContain('加载中')
    positions.value = positionsB
    await settle()
    expect(graphs).toHaveLength(2)
    expect(graphs[1]!.calls.filter((c) => c === 'render')).toHaveLength(1)
    expect(graphs[1]!.focusCalls.map(([id]) => id)).toContain('kp:b')
    wrapper.unmount()
  })

  it('章节外框成员（scope）变化时画出/隐藏外框', async () => {
    const scope = ref<string[] | null>(null)
    const { wrapper, graphs } = setup({ scope })
    await settle()
    scope.value = ['a', 'b']
    await settle()
    expect(graphs[0]!.pluginsAdded).toHaveLength(1)
    scope.value = null
    await settle()
    expect(graphs[0]!.pluginUpdates.at(-1)).toMatchObject({ key: 'chapter-hull', visibility: 'hidden' })
    wrapper.unmount()
  })

  it('悬停 300ms 后显示名称与掌握状态文字的 tooltip，移开即消失', async () => {
    const { wrapper, graphs } = setup()
    await settle()
    vi.useFakeTimers()
    graphs[0]!.emit('node:pointerenter', { target: { id: 'kp:a' }, pointerType: 'mouse', client: { x: 30, y: 40 } })
    vi.advanceTimersByTime(299)
    await nextTick()
    expect(wrapper.find('[role="tooltip"]').exists()).toBe(false)
    vi.advanceTimersByTime(2)
    await nextTick()
    expect(wrapper.get('[role="tooltip"]').text()).toBe('知识点a（已掌握）')
    graphs[0]!.emit('node:pointerleave')
    await nextTick()
    expect(wrapper.find('[role="tooltip"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('画布加载与错误状态沿用 H04：无障碍标签说明规模，带 data-zoom', async () => {
    const { wrapper } = setup()
    await settle()
    expect(wrapper.get('.graph-canvas__stage').attributes('aria-label')).toBe('课程知识图谱：2 个知识点，1 条关系')
    expect(wrapper.get('[data-test="graph-canvas"]').attributes('data-zoom')).toBe('1')
    wrapper.unmount()
  })
})

describe('GraphCanvas 普通模式（教师页沿用）', () => {
  it('没有地图控件与 tooltip，不用位置，行为与 H04 一致', async () => {
    const { wrapper, graphs } = setup({ enhanced: false })
    await settle()
    expect(graphs).toHaveLength(1)
    expect(graphs[0]!.init!.positions).toBeNull()
    expect(graphs[0]!.init!.minimap).toBeUndefined()
    expect(wrapper.find('.gw-map').exists()).toBe(false)
    wrapper.unmount()
  })
  it('切换布局在原图上进行，不重建', async () => {
    const layout = ref<GraphLayoutName>('hierarchical')
    const { wrapper, graphs } = setup({ enhanced: false, layout })
    await settle()
    layout.value = 'force'
    await settle()
    expect(graphs).toHaveLength(1)
    wrapper.unmount()
  })
})
```

- [ ] **Step 2: 运行，确认失败**

Run: `npm --prefix src/frontend run test -- --run graph-canvas-enhanced`
Expected: FAIL（`enhanced`/`positions`/`scope` 属性与地图控件不存在）

- [ ] **Step 3: 整体替换 `GraphCanvas.vue`**

`src/frontend/src/components/GraphCanvas.vue`：

```vue
<script setup lang="ts">
import { computed, inject, onActivated, onBeforeUnmount, onMounted, ref, toRaw, watch } from 'vue'
import { useReducedMotion } from '../composables/useReducedMotion'
import type { Positions } from '../graph/chapterLayout'
import {
  createGraphLifecycle,
  GRAPH_FACTORY_KEY,
  loadG6Graph,
  type GraphCanvasData,
  type GraphLayoutName,
  type GraphLifecycle,
  type LifecycleStatus,
} from '../graph/lifecycle'
import { GRAPH_OBSTACLES_KEY, useGraphObstacle } from '../graph/obstacles'
import { MASTERY_TEXT, masteryOfStates } from '../graph/presentation'
import AppIcon from './AppIcon.vue'

/**
 * 课程知识图谱画布（H04）：只负责把适配图画出来并支持缩放、拖拽。
 * 数据请求、筛选与详情由页面和后续组件负责；`graph` 为 null 表示数据尚未到达。
 * L13：初始视口不低于可读缩放（`data-zoom` 记录当前缩放）；`focus(kpId)` 供页面在搜索、跳转后聚焦。
 *
 * 增强模式（`enhanced`，学生图谱页，UI-GRAPH-PILOT-01）：章节分区布局（`positions`）、语义缩放与标签避让、
 * 悬停强淡化、章节外框（`scope`）、小地图与缩放控件、悬停 tooltip。关闭时与 H04 一致（教师页沿用）。
 * 增强模式下切换布局或位置变化会重建画布（选中等状态随数据保留）。
 */
const props = withDefaults(
  defineProps<{
    graph: GraphCanvasData | null
    label?: string
    layout?: GraphLayoutName
    enhanced?: boolean
    /** 章节分区布局的位置（知识点 ID → 坐标）；增强模式下 null 表示还在计算，画布等它 */
    positions?: Positions | null
    /** 章节外框成员（知识点 ID）；null 为没有 */
    scope?: readonly string[] | null
  }>(),
  { label: '课程知识图谱', layout: 'hierarchical', enhanced: false, positions: null, scope: null },
)

const emit = defineEmits<{ nodeClick: [kpId: string]; blankClick: [] }>()

const factory = inject(GRAPH_FACTORY_KEY, loadG6Graph)
const registry = inject(GRAPH_OBSTACLES_KEY, null)
const reduced = useReducedMotion()
const root = ref<HTMLElement | null>(null)
const stage = ref<HTMLElement | null>(null)
const mini = ref<HTMLElement | null>(null)
const controls = ref<HTMLElement | null>(null)
const status = ref<LifecycleStatus | 'idle'>('idle')
const drawnOnce = ref(false)
const zoom = ref<number | null>(null)
/** 小地图默认展开；<1024px 默认收起（规格 §5.1） */
const miniOpen = ref(typeof window === 'undefined' || window.innerWidth >= 1024)
const tip = ref<{ text: string; x: number; y: number } | null>(null)
let lifecycle: GraphLifecycle | null = null
let tipTimer: ReturnType<typeof setTimeout> | null = null
let stopObstacles: (() => void) | null = null
/**
 * 最近一次请求聚焦的知识点：画布建好之前请求的聚焦在建好后执行；重建（换布局、换位置）后回到它，
 * 而不是退回整图适配（L14：视口跟随最近一次聚焦）
 */
let lastFocus: string | null = null

// 小地图与缩放控件本身也是画布上的浮层
useGraphObstacle(controls, 'hard')

/** 增强模式 + 层次布局时要等章节布局算好才建图（避免先画一遍 dagre 再跳变） */
const ready = computed(
  () => props.graph !== null && (!props.enhanced || props.layout !== 'hierarchical' || props.positions !== null),
)
const loading = computed(() => !ready.value || (!drawnOnce.value && status.value !== 'error'))
const empty = computed(() => !loading.value && props.graph !== null && props.graph.nodes.length === 0)
const ariaLabel = computed(() =>
  props.graph === null
    ? `${props.label}：加载中`
    : `${props.label}：${props.graph.nodes.length} 个知识点，${props.graph.edges.length} 条关系`,
)

function showTip(info: { kpId: string; clientX: number; clientY: number } | null): void {
  if (tipTimer !== null) clearTimeout(tipTimer)
  tip.value = null
  if (info === null || root.value === null) return
  const box = root.value.getBoundingClientRect()
  // tooltip 延迟 300ms 出现（规格 §9）：名称与掌握状态文字，完整名称不依赖标签是否显示
  tipTimer = setTimeout(() => {
    const node = props.graph?.nodes.find((n) => n.data.kpId === info.kpId)
    if (node === undefined) return
    tip.value = {
      text: `${node.data.name}（${MASTERY_TEXT[masteryOfStates(node.states)]}）`,
      x: info.clientX - box.left,
      y: info.clientY - box.top,
    }
  }, 300)
}

function start(): void {
  if (stage.value === null || props.graph === null || !ready.value) return
  drawnOnce.value = false
  // 适配图可能是响应式代理；生命周期会复制一份交给 G6
  lifecycle = createGraphLifecycle(stage.value, {
    data: toRaw(props.graph),
    layout: props.layout,
    positions: props.enhanced && props.positions !== null ? toRaw(props.positions) : null,
    enhance: props.enhanced
      ? {
          obstacles: () => (stage.value !== null && registry !== null ? registry.boxes(stage.value) : { hard: [], soft: [] }),
          minimap: mini.value,
          reduceMotion: () => reduced.value,
          onBlankClick: () => emit('blankClick'),
          onHover: showTip,
        }
      : undefined,
    factory,
    onNodeClick: (kpId) => emit('nodeClick', kpId),
    onStatus: (next) => {
      status.value = next
      if (next === 'ready') drawnOnce.value = true
    },
    onZoom: (value) => {
      zoom.value = Math.round(value * 100) / 100
    },
  })
  if (props.scope !== null) lifecycle.setScope(props.scope)
  if (lastFocus !== null) lifecycle.focus(lastFocus)
}

/** 把视口移到该知识点；画布尚未建好时在首次渲染后执行 */
function focus(kpId: string): void {
  lastFocus = kpId
  lifecycle?.focus(kpId)
}

defineExpose({
  focus,
  /** 把一组知识点（缺省为全部可见节点）整体放进视口（章节跳转、局部视图、适应画布） */
  fitTo: (kpIds?: readonly string[]) => lifecycle?.fitTo(kpIds),
  /** 节点在视口外时才移动镜头（面板里的显式选择） */
  ensureVisible: (kpId: string) => lifecycle?.ensureVisible(kpId),
})

const zoomBy = (ratio: number): void => lifecycle?.zoomBy(ratio)
const fitAll = (): void => lifecycle?.fitTo()
const leaveHover = (): void => lifecycle?.leaveHover()

function stop(): void {
  showTip(null)
  lifecycle?.destroy()
  lifecycle = null
}

function retry(): void {
  stop()
  start()
}

onMounted(() => {
  start()
  // 浮层出现、消失、展开收起时重新排布标签
  stopObstacles = registry?.onChange(() => lifecycle?.relayoutLabels()) ?? null
})

watch(
  () => props.graph,
  (graph) => {
    if (graph === null) return
    if (lifecycle === null) start()
    else lifecycle.update(toRaw(graph))
  },
)

// 位置就绪（章节布局算完）后建图
watch(ready, (now) => {
  if (now && lifecycle === null) start()
})

// 位置在重新计算（换版本）：旧画布对应的是另一张图，先拆掉，等新位置到了由 `ready` 重建；
// 位置从一份换成另一份（没经过 null）同样重建。首次到达（null → 位置）由 `ready` 负责建图，这里不重复建
watch(
  () => props.positions,
  (now, before) => {
    if (!props.enhanced || lifecycle === null) return
    if (now === null) stop()
    else if (before !== null) retry()
  },
)

// 层次布局下切换：普通模式在原图上进行，节点状态（含选中）随数据保留（H05）；增强模式的章节布局是预先算好的位置，重建
watch(
  () => props.layout,
  (layout) => {
    if (props.enhanced) {
      if (lifecycle !== null) retry()
    } else lifecycle?.setLayout(layout)
  },
)

watch(
  () => props.scope,
  (scope) => lifecycle?.setScope(scope),
)

onActivated(() => lifecycle?.refreshSize())
onBeforeUnmount(() => {
  stopObstacles?.()
  stop()
})
</script>

<template>
  <section
    ref="root"
    class="graph-canvas"
    :class="{ 'graph-canvas--enhanced': enhanced }"
    data-test="graph-canvas"
    :data-zoom="zoom ?? undefined"
    :aria-busy="loading ? 'true' : 'false'"
    @pointerleave="leaveHover"
  >
    <div ref="stage" class="graph-canvas__stage" role="img" :aria-label="ariaLabel" />
    <div v-if="status === 'error'" class="graph-canvas__overlay" role="alert">
      <p>图谱渲染失败，请重试。</p>
      <button type="button" @click="retry">重试</button>
    </div>
    <p v-else-if="loading" class="graph-canvas__overlay" role="status">图谱加载中…</p>
    <p v-else-if="empty" class="graph-canvas__overlay" role="status">暂无知识点</p>

    <!-- 小地图与缩放控件：缩略图只画节点，遮罩框是当前视口；装饰性，键盘等价路径是搜索、章节跳转与列表 -->
    <div v-if="enhanced" ref="controls" class="gw-map" role="group" aria-label="地图与缩放">
      <div v-show="miniOpen" ref="mini" class="gw-mini" aria-hidden="true" />
      <div class="gw-map__ctl">
        <button type="button" class="gw-tool" :aria-label="miniOpen ? '收起小地图' : '展开小地图'" :aria-pressed="miniOpen" @click="miniOpen = !miniOpen">
          <AppIcon name="map" />
        </button>
        <button type="button" class="gw-tool" aria-label="放大" @click="zoomBy(1.25)"><AppIcon name="plus" /></button>
        <button type="button" class="gw-tool" aria-label="缩小" @click="zoomBy(0.8)"><AppIcon name="minus" /></button>
        <button type="button" class="gw-tool" aria-label="适应画布" @click="fitAll"><AppIcon name="fit" /></button>
      </div>
    </div>
    <div v-if="tip" class="gw-tip" role="tooltip" :style="{ left: `${tip.x + 14}px`, top: `${tip.y + 14}px` }">{{ tip.text }}</div>
  </section>
</template>

<style scoped>
.graph-canvas {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 480px;
}

.graph-canvas__stage {
  /* G6 会把容器改为 position: relative，所以尺寸不能靠绝对定位撑开 */
  width: 100%;
  height: 100%;
  min-height: 480px;
  overflow: hidden;
}

.graph-canvas__overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin: 0;
  pointer-events: none;
}

.graph-canvas__overlay button {
  pointer-events: auto;
}

/* 增强模式：画布填满工作区，不再自带最小高度 */
.graph-canvas--enhanced,
.graph-canvas--enhanced .graph-canvas__stage {
  min-height: 0;
}

.gw-map {
  position: absolute;
  z-index: 6;
  right: 16px;
  bottom: 16px;
  display: flex;
  align-items: flex-end;
  gap: 8px;
}
.gw-mini {
  width: 180px;
  height: 120px;
  border: 1px solid var(--gw-edge);
  border-radius: 10px;
  background: var(--gw-panel);
  overflow: hidden;
  box-shadow: 0 1px 2px rgb(29 36 51 / 10%);
}
.gw-map__ctl {
  display: grid;
  gap: 6px;
}
.gw-tip {
  position: absolute;
  z-index: 5;
  max-width: 280px;
  padding: 6px 10px;
  border-radius: var(--ss-radius-sm);
  background: var(--gw-panel);
  color: var(--gw-text);
  border: 1px solid var(--gw-line);
  font-size: 12px;
  line-height: 18px;
  box-shadow: var(--ss-shadow-pop-light);
  pointer-events: none;
  animation: gw-tip-in 120ms var(--ss-ease);
}
@keyframes gw-tip-in {
  from {
    opacity: 0;
    transform: translateY(2px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
@media (prefers-reduced-motion: reduce) {
  .gw-tip {
    animation-duration: 1ms;
  }
}
</style>
```

- [ ] **Step 4: 运行，确认通过；再跑既有画布用例**

Run: `npm --prefix src/frontend run test -- --run graph-canvas-enhanced h04 h05 && npm --prefix src/frontend run type-check`
Expected: 全部通过；type-check 退出码 0

- [ ] **Step 5: 提交（仅在用户授权后）**

```bash
git add src/frontend/src/components/GraphCanvas.vue tests/frontend/graph-canvas-enhanced.test.ts
git commit -m "feat(frontend): enhanced GraphCanvas (chapter layout, minimap controls, tooltip, hull scope)"
```

---

### Task 13: 预览状态机、局部视图、章节布局 composables

**Files:**
- Create: `src/frontend/src/composables/usePreviewFocus.ts`
- Create: `src/frontend/src/composables/useLocalView.ts`
- Create: `src/frontend/src/composables/useGraphLayout.ts`
- Test: `tests/frontend/preview-focus.test.ts`、`tests/frontend/local-view.test.ts`、`tests/frontend/graph-layout-composable.test.ts`

**Interfaces:**
- Consumes: `computeLayout`/`DagreEngine`/`LayoutNode`/`LayoutEdge`/`Positions`（Task 5）、`kpIdFromElementId`（Task 11）、`GraphCanvasData`（lifecycle）。
- Produces：
  ```ts
  // usePreviewFocus
  usePreviewFocus({ selected: Ref<string | null>, select: (kpId: string | null) => void }): {
    previewId: Ref<string | null>; highlightId: ComputedRef<string | null>   // 预览中的优先，否则详情节点
    onNodeClick(kpId): void   // 单击预览；再次单击同一节点（或已打开详情的节点）才打开详情
    preview(kpId): void; open(kpId: string | null): void; clearPreview(): void }
  // useLocalView
  export interface LocalView { id: string; hops: 1 | 2 }
  export function localKpIds(graph: GraphCanvasData, view: LocalView): Set<string>
  export function restrictGraph(graph: GraphCanvasData, ids: ReadonlySet<string>): GraphCanvasData
  useLocalView(source: () => GraphCanvasData | null): { view: Ref<LocalView | null>; toggle(kpId): void; setHops(hops: 1 | 2): void; clear(): void; ids: ComputedRef<Set<string> | null>; apply(graph: GraphCanvasData | null): GraphCanvasData | null }
  // useGraphLayout —— source 必须返回稳定引用（用 computed），返回新对象会每次重算
  export interface LayoutSource { nodes: LayoutNode[]; edges: LayoutEdge[]; chapterOrder: string[] }
  useGraphLayout(source: () => LayoutSource | null, engine?: DagreEngine): { positions: Ref<Positions | null>; error: Ref<unknown> }
  ```
- 行为要点：局部范围只在**传入的（已筛选的）图**里找邻居，所以与类型/关系筛选叠加时取交集；`useGraphLayout` 在重算期间把位置置回 `null`（画布据此等待，不用旧位置画新图），过期结果丢弃（`seq`）。

- [ ] **Step 1: 写测试**

`tests/frontend/preview-focus.test.ts`：

```ts
import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { usePreviewFocus } from '../../src/frontend/src/composables/usePreviewFocus'

function setup(initial: string | null = null) {
  const selected = ref<string | null>(initial)
  const select = vi.fn((kpId: string | null) => {
    selected.value = kpId
  })
  return { selected, select, focus: usePreviewFocus({ selected, select }) }
}

describe('usePreviewFocus', () => {
  it('单击节点只进入预览，不打开详情', () => {
    const { focus, select, selected } = setup()
    focus.onNodeClick('a')
    expect(focus.previewId.value).toBe('a')
    expect(focus.highlightId.value).toBe('a')
    expect(select).not.toHaveBeenCalled()
    expect(selected.value).toBeNull()
  })
  it('再次单击同一节点才打开详情，并结束预览', () => {
    const { focus, select, selected } = setup()
    focus.onNodeClick('a')
    focus.onNodeClick('a')
    expect(select).toHaveBeenCalledWith('a')
    expect(selected.value).toBe('a')
    expect(focus.previewId.value).toBeNull()
    expect(focus.highlightId.value).toBe('a')
  })
  it('详情已打开时单击另一个节点：只预览新节点，详情保持不变', () => {
    const { focus, select, selected } = setup('a')
    focus.onNodeClick('b')
    expect(focus.previewId.value).toBe('b')
    expect(focus.highlightId.value).toBe('b')
    expect(selected.value).toBe('a')
    expect(select).not.toHaveBeenCalled()
    focus.onNodeClick('b')
    expect(selected.value).toBe('b')
  })
  it('单击已打开详情的节点：保持打开，不进入预览', () => {
    const { focus, selected } = setup('a')
    focus.onNodeClick('a')
    expect(selected.value).toBe('a')
    expect(focus.previewId.value).toBeNull()
  })
  it('取消预览后回到详情节点的高亮；详情不受影响', () => {
    const { focus, selected } = setup('a')
    focus.onNodeClick('b')
    focus.clearPreview()
    expect(focus.highlightId.value).toBe('a')
    expect(selected.value).toBe('a')
  })
  it('搜索回车进入预览（不是直接打开详情）', () => {
    const { focus, select } = setup()
    focus.preview('c')
    expect(focus.previewId.value).toBe('c')
    expect(select).not.toHaveBeenCalled()
  })
  it('面板、列表、推荐里的显式选择直接打开详情；传 null 返回课程说明', () => {
    const { focus, selected } = setup()
    focus.preview('c')
    focus.open('d')
    expect(selected.value).toBe('d')
    expect(focus.previewId.value).toBeNull()
    focus.open(null)
    expect(selected.value).toBeNull()
  })
})
```

`tests/frontend/local-view.test.ts`：

```ts
import { describe, expect, it } from 'vitest'
import { useLocalView, localKpIds, restrictGraph } from '../../src/frontend/src/composables/useLocalView'
import type { CanvasEdge, CanvasNode, GraphCanvasData } from '../../src/frontend/src/graph/lifecycle'

function node(id: string): CanvasNode {
  return {
    id: `kp:${id}`,
    data: { kpId: id, name: id, type: 'concept', level: 1, chapterId: 'c1', status: 'approved', confidence: 1, source: 'ai', locked: false },
  }
}
function edge(id: string, from: string, to: string): CanvasEdge {
  return {
    id: `rel:${id}`, source: `kp:${from}`, target: `kp:${to}`,
    data: { relationId: id, type: 'PREREQUISITE', directed: true, status: 'approved', confidence: 1, source: 'ai', downgraded: false },
    style: { stroke: '#000', lineWidth: 1, lineDash: [], endArrow: true, labelText: '前置' },
  }
}
// a→b→c→d，e 孤立
const graph: GraphCanvasData = {
  nodes: ['a', 'b', 'c', 'd', 'e'].map(node),
  edges: [edge('1', 'a', 'b'), edge('2', 'b', 'c'), edge('3', 'c', 'd')],
}

describe('localKpIds', () => {
  it('1 跳：中心与直接相邻（不分方向）', () => {
    expect([...localKpIds(graph, { id: 'b', hops: 1 })].sort()).toEqual(['a', 'b', 'c'])
  })
  it('2 跳：再向外一圈', () => {
    expect([...localKpIds(graph, { id: 'b', hops: 2 })].sort()).toEqual(['a', 'b', 'c', 'd'])
  })
  it('孤立节点只有自己', () => {
    expect([...localKpIds(graph, { id: 'e', hops: 2 })]).toEqual(['e'])
  })
  it('只在传入的图里找：被筛选隐藏的邻居不会被带回来', () => {
    const filtered = restrictGraph(graph, new Set(['a', 'b', 'd']))
    expect([...localKpIds(filtered, { id: 'b', hops: 2 })].sort()).toEqual(['a', 'b'])
  })
})

describe('restrictGraph', () => {
  it('保留范围内的节点与两端都在范围内的边，不修改输入', () => {
    const out = restrictGraph(graph, new Set(['a', 'b']))
    expect(out.nodes.map((n) => n.data.kpId)).toEqual(['a', 'b'])
    expect(out.edges.map((e) => e.id)).toEqual(['rel:1'])
    expect(graph.nodes).toHaveLength(5)
  })
})

describe('useLocalView', () => {
  it('toggle 开启 1 跳、再次对同一知识点调用关闭；setHops 切换范围；clear 恢复', () => {
    const lv = useLocalView(() => graph)
    expect(lv.ids.value).toBeNull()
    expect(lv.apply(graph)).toBe(graph)
    lv.toggle('b')
    expect(lv.view.value).toEqual({ id: 'b', hops: 1 })
    expect(lv.apply(graph)!.nodes).toHaveLength(3)
    lv.setHops(2)
    expect(lv.apply(graph)!.nodes).toHaveLength(4)
    lv.toggle('b')
    expect(lv.view.value).toBeNull()
    lv.toggle('c')
    lv.clear()
    expect(lv.ids.value).toBeNull()
  })
  it('没有开启时 setHops 无效；图为 null 时 apply 返回 null', () => {
    const lv = useLocalView(() => null)
    lv.setHops(2)
    expect(lv.view.value).toBeNull()
    expect(lv.apply(null)).toBeNull()
  })
})
```

`tests/frontend/graph-layout-composable.test.ts`：

```ts
import { flushPromises } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import type { DagreEngine } from '../../src/frontend/src/graph/chapterLayout'
import { useGraphLayout, type LayoutSource } from '../../src/frontend/src/composables/useGraphLayout'

/** 替身引擎：每个节点按序号排成一行，可手动放行 */
function makeEngine() {
  const waiting: Array<() => void> = []
  const calls: string[][] = []
  const engine: DagreEngine = (ids) => {
    calls.push(ids)
    return new Promise((resolve) => {
      waiting.push(() => resolve(new Map(ids.map((id, i) => [id, { x: i * 100, y: 0 }]))))
    })
  }
  return { engine, calls, release: () => waiting.splice(0).forEach((fn) => fn()) }
}

const source = (ids: string[]): LayoutSource => ({
  nodes: ids.map((id) => ({ id, chapter: 'c1' })),
  edges: [],
  chapterOrder: ['c1'],
})

describe('useGraphLayout', () => {
  it('源为 null 时没有位置；源到达后异步算出位置', async () => {
    const src = ref<LayoutSource | null>(null)
    const { engine, release } = makeEngine()
    const { positions } = useGraphLayout(() => src.value, engine)
    expect(positions.value).toBeNull()
    src.value = source(['a', 'b'])
    await flushPromises()
    expect(positions.value).toBeNull() // 引擎还没放行
    release()
    await flushPromises()
    expect([...positions.value!.keys()].sort()).toEqual(['a', 'b'])
  })
  it('期间源又变化时丢弃过期结果', async () => {
    const src = ref<LayoutSource | null>(source(['a']))
    const { engine, release } = makeEngine()
    const { positions } = useGraphLayout(() => src.value, engine)
    await flushPromises()
    src.value = source(['x', 'y'])
    await flushPromises()
    release() // 两次计算同时放行：旧的先完成也不能覆盖新的
    await flushPromises()
    expect([...positions.value!.keys()].sort()).toEqual(['x', 'y'])
  })
  it('源重新计算期间位置回到 null（画布据此等待，而不是用旧位置画新图）', async () => {
    const src = ref<LayoutSource | null>(source(['a']))
    const { engine, release } = makeEngine()
    const { positions } = useGraphLayout(() => src.value, engine)
    await flushPromises()
    release()
    await flushPromises()
    expect(positions.value).not.toBeNull()
    src.value = source(['b'])
    await flushPromises()
    expect(positions.value).toBeNull()
  })
  it('引擎失败时记录错误、位置保持 null', async () => {
    const src = ref<LayoutSource | null>(source(['a']))
    const failing: DagreEngine = () => Promise.reject(new Error('layout failed'))
    const { positions, error } = useGraphLayout(() => src.value, failing)
    await flushPromises()
    expect(positions.value).toBeNull()
    expect(error.value).toBeInstanceOf(Error)
  })
})
```

- [ ] **Step 2: 运行，确认失败**

Run: `npm --prefix src/frontend run test -- --run preview-focus local-view graph-layout-composable`
Expected: FAIL（找不到三个 composable）

- [ ] **Step 3: 实现**

`src/frontend/src/composables/usePreviewFocus.ts`：

```ts
import { computed, ref, type ComputedRef, type Ref } from 'vue'

/**
 * 预览 / 详情状态机（规格 §7）。
 *
 * - 画布单击一个节点：进入**预览**（高亮 + 预览卡），侧栏不变；
 * - 再次单击同一节点（或已打开详情的那个节点）：打开详情；
 * - 详情已打开时单击另一个节点：只预览新节点，侧栏保持当前详情，直到再次单击；
 * - 点空白处 / Esc / 预览卡 ✕：取消预览，详情不受影响；
 * - 面板、列表、推荐、关联知识里的选择与问答链接是显式选择，直接打开详情。
 */
export interface PreviewFocus {
  /** 画布上处于预览状态的知识点 */
  previewId: Ref<string | null>
  /** 画布上高亮的知识点：预览中的优先，否则是已打开详情的 */
  highlightId: ComputedRef<string | null>
  /** 画布单击 */
  onNodeClick(kpId: string): void
  /** 进入预览（搜索回车） */
  preview(kpId: string): void
  /** 打开详情（预览卡「查看详情」、面板里的显式选择） */
  open(kpId: string | null): void
  clearPreview(): void
}

export function usePreviewFocus(options: { selected: Ref<string | null>; select: (kpId: string | null) => void }): PreviewFocus {
  const previewId = ref<string | null>(null)
  const highlightId = computed(() => previewId.value ?? options.selected.value)

  function open(kpId: string | null): void {
    previewId.value = null
    options.select(kpId)
  }

  return {
    previewId,
    highlightId,
    onNodeClick(kpId) {
      if (previewId.value === kpId || options.selected.value === kpId) open(kpId)
      else previewId.value = kpId
    },
    preview(kpId) {
      previewId.value = kpId
    },
    open,
    clearPreview() {
      previewId.value = null
    },
  }
}
```

`src/frontend/src/composables/useLocalView.ts`：

```ts
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { kpIdFromElementId } from '../graph/adapter'
import type { GraphCanvasData } from '../graph/lifecycle'

/**
 * 只看相邻（局部视图，规格 §4 第 3 层）：用户主动开启，只显示某知识点及 1 或 2 跳邻居，其余**隐藏**（不是淡化）。
 * 与类型/关系筛选叠加时按交集显示；隐藏状态在页面顶部提示条里可见、可恢复。
 */
export interface LocalView {
  /** 中心知识点（契约 ID） */
  id: string
  hops: 1 | 2
}

/** 中心点及 `hops` 跳以内的邻居（不分关系方向），只在传入的图里找 */
export function localKpIds(graph: GraphCanvasData, view: LocalView): Set<string> {
  const kpOf = new Map(graph.nodes.map((n) => [n.id, n.data.kpId]))
  const reach = new Set<string>([view.id])
  let frontier = [view.id]
  for (let hop = 0; hop < view.hops; hop += 1) {
    const next: string[] = []
    for (const e of graph.edges) {
      const a = kpOf.get(e.source) ?? kpIdFromElementId(e.source)
      const b = kpOf.get(e.target) ?? kpIdFromElementId(e.target)
      for (const [from, to] of [[a, b], [b, a]] as const) {
        if (frontier.includes(from) && !reach.has(to)) {
          reach.add(to)
          next.push(to)
        }
      }
    }
    frontier = next
  }
  return reach
}

/** 只保留在 `ids` 里的节点，以及两端都保留的边；不修改输入 */
export function restrictGraph(graph: GraphCanvasData, ids: ReadonlySet<string>): GraphCanvasData {
  const nodes = graph.nodes.filter((n) => ids.has(n.data.kpId))
  const present = new Set(nodes.map((n) => n.id))
  return { nodes, edges: graph.edges.filter((e) => present.has(e.source) && present.has(e.target)) }
}

export interface UseLocalView {
  view: Ref<LocalView | null>
  /** 开启/关闭某知识点的局部视图（再次对同一知识点调用即关闭） */
  toggle(kpId: string): void
  setHops(hops: 1 | 2): void
  clear(): void
  /** 局部视图可见的知识点；未开启为 null */
  ids: ComputedRef<Set<string> | null>
  /** 应用局部视图；未开启时原样返回 */
  apply(graph: GraphCanvasData | null): GraphCanvasData | null
}

/** `source` 是已按筛选得到的可见图：局部范围在它里面找，所以与筛选叠加时取交集 */
export function useLocalView(source: () => GraphCanvasData | null): UseLocalView {
  const view = ref<LocalView | null>(null)
  const ids = computed(() => {
    const g = source()
    return view.value === null || g === null ? null : localKpIds(g, view.value)
  })
  return {
    view,
    toggle(kpId) {
      view.value = view.value?.id === kpId ? null : { id: kpId, hops: 1 }
    },
    setHops(hops) {
      if (view.value !== null) view.value = { ...view.value, hops }
    },
    clear() {
      view.value = null
    },
    ids,
    apply(graph) {
      return graph === null || ids.value === null ? graph : restrictGraph(graph, ids.value)
    },
  }
}
```

`src/frontend/src/composables/useGraphLayout.ts`：

```ts
import { ref, shallowRef, watch, type Ref } from 'vue'
import { computeLayout, type DagreEngine, type LayoutEdge, type LayoutNode, type Positions } from '../graph/chapterLayout'

/**
 * 章节分区布局（规格 §4.1）：对**完整已发布图**异步计算一次位置，筛选与局部视图只显示子集，位置不跟着抖动。
 * 源变化时重新计算；期间又变化时丢弃过期结果（`seq` 保护）。
 */
export interface LayoutSource {
  nodes: LayoutNode[]
  edges: LayoutEdge[]
  /** 章节顺序（章节 id，按目录 order） */
  chapterOrder: string[]
}

export interface UseGraphLayout {
  /** 位置；源未到或正在重算时为 null */
  positions: Ref<Positions | null>
  error: Ref<unknown>
}

export function useGraphLayout(source: () => LayoutSource | null, engine?: DagreEngine): UseGraphLayout {
  const positions = shallowRef<Positions | null>(null)
  const error = ref<unknown>(null)
  let seq = 0

  watch(
    source,
    async (src) => {
      const mine = ++seq
      positions.value = null
      error.value = null
      if (src === null) return
      try {
        const result = await computeLayout(src.nodes, src.edges, 'chapter', src.chapterOrder, {}, engine)
        if (mine === seq) positions.value = result
      } catch (cause) {
        if (mine === seq) error.value = cause
      }
    },
    { immediate: true },
  )

  return { positions, error }
}
```

- [ ] **Step 4: 运行，确认通过**

Run: `npm --prefix src/frontend run test -- --run preview-focus local-view graph-layout-composable && npm --prefix src/frontend run type-check`
Expected: 7 + 7 + 4 条通过；type-check 退出码 0

- [ ] **Step 5: 提交（仅在用户授权后）**

```bash
git add src/frontend/src/composables/usePreviewFocus.ts src/frontend/src/composables/useLocalView.ts src/frontend/src/composables/useGraphLayout.ts tests/frontend/preview-focus.test.ts tests/frontend/local-view.test.ts tests/frontend/graph-layout-composable.test.ts
git commit -m "feat(frontend): add preview/detail state machine, local view and chapter layout composables"
```

---

### Task 14: 工作区样式与浮层/面板组件

**Files:**
- Create: `src/frontend/src/styles/graph-workspace.css`
- Create: `src/frontend/src/components/GraphOverlay.vue`、`GraphLegend.vue`、`GraphPreviewCard.vue`、`LocalViewBar.vue`、`ChapterMenu.vue`、`GraphSidePanel.vue`
- 测试：这些展示组件由 Task 15 的 `student-graph-workbench.test.ts` 通过页面驱动覆盖（图例计数与筛选、预览卡、局部视图条、章节菜单、面板并置/覆盖），本任务只做类型检查。

**Interfaces:**
- Consumes: `useGraphObstacle`（Task 11）、`AppIcon`、`RELATION_STYLES`、`NODE_TYPE_LABELS`/`RELATION_TYPE_ORDER`（useGraphFilters）、`NODE_TYPE_FILL`/`NODE_TYPE_GLYPH`（Task 1）。
- Produces（Task 15 依赖的 props / emits / `data-test`）：
  ```ts
  // GraphLegend：props { open; hiddenRelations; hiddenTypes; relationCounts; typeCounts }；emits update:open, toggleRelation(type), toggleType(type), restore
  //   根元素 data-test="relation-legend"（沿用 h11 的钩子）；按钮 legend-rel-<TYPE> / legend-type-<type> / legend-restore；是「软障碍」
  // GraphPreviewCard：props { name; type; chapter; masteryText; mastery; prerequisites; unlocks; localActive }；emits close, open, toggleLocal
  //   data-test: gw-preview, gw-preview-close, gw-preview-open, gw-preview-local
  // LocalViewBar：props { name; hiddenCount; hops }；emits setHops(1|2), restore；data-test: gw-local-bar, gw-local-1, gw-local-2, gw-local-restore
  // ChapterMenu：props { chapters: ChapterItem[]; currentId; disabled? }；emits jump(chapterId)；data-test: gw-chapter-button, gw-chapter-<id>；Esc 与点菜单外关闭，焦点回按钮
  // GraphOverlay：props { kind?: 'hard' | 'soft'; as?: string }，渲染插槽并把根元素登记为障碍物
  // GraphSidePanel：props { open; docked; detail; label; contentKey }；emits close, back；expose { el }；data-test: gw-panel, gw-back, gw-panel-close
  //   关闭时 :inert="open ? undefined : true"（不能写 false：jsdom 会把它渲染成字符串属性）
  ```
- 样式规则：所有选择器带 `.graph-workspace` 前缀（隔离其他页面，也让特异性高于全站 `button:hover:not(:disabled)`）；`:where(.graph-workspace) button` 重置全站主按钮样式；既有 `Recommendations`（整行卡片：伪元素撑满整张卡，序号徽标，14px/500 名称）与 `KnowledgeDetail`（关联知识芯片、来源卡片）**只用 CSS 重做**，不改它们的标记与 `data-test`；`.recommendations` 选择器要写成 `section.recommendations`，否则与组件自带的 scoped 样式特异性相同；`.visually-hidden` 必须是全局规则（页面标题在工作区之外）；`.app--graph .app-main > .student-graph` 要覆盖全站 `.app-main > section` 的卡片外观（内边距、背景、阴影）；暗色外壳（`.app--graph`、`.app-topbar`、`.app-rail`、`.app-drawer`）的规则也在此文件，Task 16 使用。

- [ ] **Step 1: 建立样式文件**

`src/frontend/src/styles/graph-workspace.css`：

```css
/*
 * 图谱工作区组件样式（UI-GRAPH-PILOT-01，规格 §3、§5、§6、§9）。
 * 所有选择器都带 `.graph-workspace` 前缀：既隔离其他页面，也让特异性高于全站的 `button:hover:not(:disabled)`。
 * 颜色只用 `--gw-*` / `--ss-*` tokens（`styles/tokens.css`）；个别写死的 #747a87 / #5b5bd6 是控件边界与主按钮，
 * 与 tokens 的 `--gw-edge` / `--ss-primary` 数值一致。
 */

/* 仅屏幕阅读器可见（页面标题放在工作区之外，所以不带 .graph-workspace 前缀） */
.visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }

/* 工作区内的按钮不继承全站的主按钮样式（`:where` 不增加特异性，下面带前缀的组件规则都能覆盖它） */
:where(.graph-workspace) button { padding: 0; border: 1px solid transparent; border-radius: 0; background: transparent; color: inherit; font: inherit; font-weight: 400; justify-self: auto; cursor: pointer; }
:where(.graph-workspace) button:hover:not(:disabled) { background: var(--gw-hover); }
:where(.graph-workspace) button:disabled { background: transparent; border-color: transparent; color: var(--gw-text-3); cursor: not-allowed; }
:where(.graph-workspace) :is(h2, h3, p, ul, ol) { margin: 0; }
:where(.graph-workspace) :is(ul, ol) { padding: 0; list-style: none; }
.graph-workspace :focus-visible { outline: 2px solid var(--gw-accent); outline-offset: 2px; }

/* ---------- 工作区 */
.graph-workspace.gw { position: relative; flex: 1; min-width: 0; display: grid; grid-template-columns: 320px minmax(0, 1fr); background: var(--gw-canvas); border-radius: var(--ss-radius-md); overflow: hidden; box-shadow: 0 1px 2px rgb(0 0 0 / 24%); animation: gw-in 180ms var(--ss-ease); font-size: 14px; }
.graph-workspace.gw.is-collapsed { grid-template-columns: 0 minmax(0, 1fr); }
.graph-workspace.gw.is-overlay { grid-template-columns: minmax(0, 1fr); }
.graph-workspace .gw-panel { background: var(--gw-panel); border-right: 1px solid var(--gw-line); display: flex; flex-direction: column; min-width: 0; overflow: hidden; }
.graph-workspace.gw.is-collapsed .gw-panel { visibility: hidden; border: 0; }
.graph-workspace.gw.is-overlay .gw-panel { position: absolute; z-index: 20; inset: 0 auto 0 0; width: min(320px, calc(100vw - 32px)); box-shadow: var(--ss-shadow-pop-light); opacity: 0; transform: translateX(-16px); visibility: hidden; transition: transform 220ms var(--ss-ease), opacity 220ms var(--ss-ease), visibility 0s linear 220ms; }
.graph-workspace.gw.is-overlay .gw-panel.is-open { opacity: 1; transform: none; visibility: visible; transition-delay: 0s; }
.graph-workspace .gw-scrim { position: absolute; inset: 0; z-index: 19; background: rgb(32 35 42 / 28%); animation: gw-fade 160ms var(--ss-ease); }
.graph-workspace .gw-panel__head { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 12px 12px 0 20px; min-height: 48px; }
.graph-workspace .gw-panel__tag { color: var(--gw-text-3); font-size: 12px; line-height: 18px; }
.graph-workspace .gw-panel__scroll { flex: 1; min-height: 0; overflow-y: auto; overflow-x: hidden; padding: 8px 20px 24px; }
.graph-workspace .gw-fade { animation: gw-fade 140ms var(--ss-ease); display: grid; grid-template-columns: minmax(0, 1fr); gap: 16px; align-content: start; }
.graph-workspace .gw-title { margin: 0; font-size: 20px; line-height: 28px; font-weight: 600; overflow-wrap: anywhere; }
.graph-workspace .gw-h3 { margin: 0 0 8px; font-size: 14px; line-height: 22px; font-weight: 600; color: var(--gw-text); }
.graph-workspace .gw-body { margin: 0; font-size: 14px; line-height: 24px; overflow-wrap: anywhere; }
.graph-workspace .gw-muted { color: var(--gw-text-3); font-size: 12px; line-height: 18px; overflow-wrap: anywhere; }
.graph-workspace .gw-hint { margin: 0; color: var(--gw-text-3); font-size: 12px; line-height: 18px; }
.graph-workspace .gw-type { margin: 0; display: flex; align-items: center; gap: 8px; font-size: 12px; line-height: 18px; color: var(--gw-text-2); flex-wrap: wrap; }
/* 行高必须压到 1：继承正文 22px 行高时，文字行框比圆圈还高，字会被撑得偏下 */
.graph-workspace .gw-glyph { display: inline-grid; place-items: center; width: 24px; height: 24px; padding: 0; border: 1.5px solid #606a7b; border-radius: 50%; font-size: 12px; line-height: 1; font-weight: 500; color: var(--gw-text); flex: none; }
.graph-workspace .gw-glyph--s { width: 20px; height: 20px; font-size: 11px; }
.graph-workspace .gw-back, .graph-workspace .gw-iconbtn, .graph-workspace .gw-tool, .graph-workspace .gw-btn, .graph-workspace .gw-link { transition: background-color 120ms var(--ss-ease), border-color 120ms var(--ss-ease), color 120ms var(--ss-ease), transform 80ms var(--ss-ease); }
.graph-workspace .gw-back { display: inline-flex; align-items: center; gap: 4px; min-height: 32px; padding: 0 10px 0 6px; border: 0; border-radius: 6px; background: transparent; color: var(--gw-accent); font-weight: 500; }
.graph-workspace .gw-back:hover, .graph-workspace .gw-iconbtn:hover { background: var(--gw-hover); }
.graph-workspace .gw-iconbtn { display: grid; place-items: center; width: 36px; height: 36px; border: 0; border-radius: 6px; background: transparent; color: var(--gw-text-2); }
.graph-workspace .gw-link { border: 0; background: none; padding: 0; color: var(--gw-accent); text-align: left; text-decoration: underline; text-underline-offset: 2px; }
.graph-workspace .gw-link:hover { color: #3f35a6; }

.graph-workspace .gw-next { border: 1px solid var(--gw-line); border-radius: 10px; background: var(--gw-canvas); }
.graph-workspace .gw-next__head { width: 100%; min-height: 40px; display: flex; align-items: center; gap: 8px; padding: 0 12px; border: 0; background: transparent; color: var(--gw-text); text-align: left; border-radius: 10px; }
.graph-workspace .gw-next__head:hover { background: var(--gw-hover); }
.graph-workspace .gw-next__title { font-weight: 600; flex: none; }
.graph-workspace .gw-next__peek { flex: 1; min-width: 0; color: var(--gw-text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.graph-workspace .gw-next__head svg { margin-left: auto; flex: none; }
.graph-workspace .gw-next__list { margin: 0; padding: 0 8px 8px; list-style: none; display: grid; gap: 2px; }
.graph-workspace .gw-next__item { width: 100%; display: flex; align-items: center; gap: 10px; padding: 8px; border: 0; border-radius: 6px; background: transparent; text-align: left; color: var(--gw-text); transition: background-color 120ms var(--ss-ease); }
.graph-workspace .gw-next__item:hover { background: var(--gw-selected); }
.graph-workspace .gw-next__item svg { flex: none; color: var(--gw-accent); }
.graph-workspace .gw-next__order { display: grid; place-items: center; flex: none; width: 22px; height: 22px; border-radius: 11px; background: var(--gw-selected); color: var(--gw-accent); font-size: 12px; font-weight: 600; }
.graph-workspace .gw-next__text { flex: 1; min-width: 0; display: grid; gap: 2px; }
.graph-workspace .gw-next__name { font-size: 14px; line-height: 22px; font-weight: 500; overflow-wrap: anywhere; }
.graph-workspace .gw-next__reason { color: var(--gw-text-2); font-size: 12px; line-height: 18px; }
.graph-workspace .gw-next__empty { padding: 8px; color: var(--gw-text-2); font-size: 13px; line-height: 20px; }

.graph-workspace .gw-seg { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.graph-workspace .gw-seg button { display: inline-flex; align-items: center; justify-content: center; gap: 4px; min-height: 40px; padding: 0 8px; border: 1px solid #747a87; border-radius: 6px; background: #fff; color: var(--gw-text); }
.graph-workspace .gw-seg button:hover:not(:disabled):not([aria-pressed='true']) { background: var(--gw-hover); }
.graph-workspace .gw-seg button[aria-pressed='true'] { background: #5b5bd6; border-color: #5b5bd6; color: #fff; font-weight: 500; }
.graph-workspace .gw-seg button:active:not(:disabled) { transform: scale(0.98); }
.graph-workspace .gw-seg button:disabled { opacity: 1; color: var(--gw-text-3); background: var(--gw-hover); }
.graph-workspace .gw-seg button[aria-pressed='true']:disabled { background: #5b5bd6; color: #fff; }
.graph-workspace .gw-note { margin: 8px 0 0; padding: 8px 12px; border-radius: 6px; font-size: 13px; line-height: 20px; }
.graph-workspace .gw-note--ok { background: var(--gw-ok-bg); color: var(--gw-ok); }
.graph-workspace .gw-note--danger { background: var(--gw-danger-bg); color: var(--gw-danger); }

.graph-workspace .gw-group { margin-bottom: 12px; }
.graph-workspace .gw-group__title { display: flex; align-items: center; gap: 8px; margin: 0 0 4px; font-size: 12px; line-height: 18px; color: var(--gw-text-2); }
.graph-workspace .gw-chips { margin: 0; padding: 0; list-style: none; display: flex; flex-wrap: wrap; gap: 8px; }
.graph-workspace .gw-chip { display: inline-flex; align-items: center; gap: 6px; max-width: 100%; min-height: 32px; padding: 0 10px 0 6px; border: 1px solid #747a87; border-radius: 6px; background: #fff; color: var(--gw-text); text-align: left; }
.graph-workspace .gw-chip:hover { background: var(--gw-selected); border-color: var(--gw-accent); }
.graph-workspace .gw-chip__name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.graph-workspace .gw-chip__state { flex: none; font-size: 12px; color: var(--gw-text-3); }
.graph-workspace .gw-src { border: 1px solid var(--gw-line); border-radius: 6px; margin-bottom: 8px; background: #fff; }
.graph-workspace .gw-src summary { padding: 8px 12px; cursor: pointer; overflow-wrap: anywhere; }
.graph-workspace .gw-src summary:hover { background: var(--gw-hover); }
.graph-workspace .gw-src blockquote { margin: 0; padding: 8px 12px 12px; border-top: 1px solid var(--gw-line); color: var(--gw-text-2); font-size: 13px; line-height: 22px; overflow-wrap: anywhere; }
.graph-workspace .gw-bar { height: 6px; border-radius: 3px; background: var(--gw-hover); overflow: hidden; margin-bottom: 8px; }
.graph-workspace .gw-bar i { display: block; height: 100%; background: var(--gw-accent); }
.graph-workspace .gw-rec { margin: 0; padding: 0; list-style: none; display: grid; gap: 8px; }
/* 可点击的卡片是控件：边界用 #747A87（≥3:1），不用装饰分隔线色 */
.graph-workspace .gw-rec__item { width: 100%; display: grid; gap: 2px; text-align: left; padding: 10px 12px; border: 1px solid #747a87; border-radius: 10px; background: #fff; }
.graph-workspace .gw-rec__item:hover { border-color: var(--gw-accent); background: var(--gw-selected); }
.graph-workspace .gw-rec__name { font-weight: 500; overflow-wrap: anywhere; }

/* ---------- 画布与浮层 */
.graph-workspace .gw-stage { position: relative; min-width: 0; min-height: 0; background: var(--gw-canvas); }
.graph-workspace .gw-tl { position: absolute; z-index: 6; top: 16px; left: 16px; right: 72px; display: grid; gap: 8px; justify-items: start; }
.graph-workspace .gw-tl__row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; max-width: 100%; }
.graph-workspace .gw-tool.gw-tool--text { width: auto; min-width: 36px; height: 40px; padding: 0 12px; display: inline-flex; align-items: center; gap: 6px; font-weight: 500; white-space: nowrap; }
.graph-workspace .gw-chap { position: relative; }
.graph-workspace .gw-menu { position: absolute; top: calc(100% + 6px); left: 0; z-index: 8; width: 288px; max-width: calc(100vw - 48px); max-height: min(60vh, 420px); overflow-y: auto; padding: 6px; display: grid; gap: 2px; background: var(--gw-panel); border: 1px solid #747a87; border-radius: 10px; box-shadow: var(--ss-shadow-pop-light); animation: gw-fade 120ms var(--ss-ease); }
.graph-workspace .gw-menu__item { display: grid; width: 100%; min-height: 44px; padding: 6px 10px; border: 0; border-radius: 6px; background: transparent; text-align: left; color: var(--gw-text); transition: background-color 120ms var(--ss-ease); }
.graph-workspace .gw-menu__item:hover { background: var(--gw-hover); }
.graph-workspace .gw-menu__item.is-current { background: var(--gw-selected); box-shadow: inset 2px 0 0 var(--gw-accent); }
.graph-workspace .gw-menu__title { font-size: 14px; line-height: 22px; font-weight: 500; }
.graph-workspace .gw-menu__meta { font-size: 12px; line-height: 18px; color: var(--gw-text-2); }
.graph-workspace .gw-chip-on { margin: 0; display: inline-flex; align-items: center; gap: 4px; padding: 2px 4px 2px 12px; border: 1px solid var(--gw-accent); border-radius: 6px; background: var(--gw-selected); color: var(--gw-text); font-size: 13px; line-height: 20px; }
.graph-workspace .gw-chip-on__x { display: grid; place-items: center; width: 28px; height: 28px; border: 0; border-radius: 6px; background: transparent; color: var(--gw-text-2); }
.graph-workspace .gw-chip-on__x:hover { background: var(--gw-hover); }
.graph-workspace .gw-list__group.is-active { box-shadow: inset 2px 0 0 var(--gw-accent); padding-left: 10px; }
.graph-workspace .gw-list__group:focus-visible { outline-offset: 4px; }
.graph-workspace .gw-preview { position: absolute; z-index: 7; left: 50%; transform: translateX(-50%); bottom: 68px; width: min(360px, calc(100% - 32px)); padding: 16px; display: grid; gap: 8px; background: var(--gw-panel); border: 1px solid #747a87; border-radius: 14px; box-shadow: var(--ss-shadow-pop-light); animation: gw-fade 140ms var(--ss-ease); }
.graph-workspace .gw-preview__top { display: flex; align-items: center; gap: 8px; font-size: 12px; line-height: 18px; color: var(--gw-text-2); }
.graph-workspace .gw-preview__top .gw-iconbtn { margin-left: auto; margin-right: -8px; margin-top: -8px; }
.graph-workspace .gw-preview__name { margin: 0; font-size: 16px; line-height: 24px; font-weight: 600; overflow-wrap: anywhere; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.graph-workspace .gw-preview__def { margin: 0; font-size: 13px; line-height: 20px; color: var(--gw-text-2); overflow-wrap: anywhere; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.graph-workspace .gw-preview__meta { margin: 0; display: flex; flex-wrap: wrap; gap: 2px 12px; font-size: 12px; line-height: 18px; color: var(--gw-text-2); }
.graph-workspace .gw-preview__meta [data-mastery='mastered'] { color: var(--gw-ok); font-weight: 500; }
.graph-workspace .gw-preview__meta [data-mastery='learning'] { color: var(--gw-warn); font-weight: 500; }
.graph-workspace .gw-preview__actions { display: flex; align-items: center; gap: 8px 12px; flex-wrap: wrap; }
.graph-workspace .gw-btn.gw-btn--ghost { background: #fff; color: var(--gw-text); border: 1px solid #747a87; }
.graph-workspace .gw-btn.gw-btn--ghost:hover { background: var(--gw-hover); }
.graph-workspace .gw-btn.gw-btn--ghost[aria-pressed='true'] { background: var(--gw-selected); border-color: var(--gw-accent); color: var(--gw-accent); font-weight: 600; }
.graph-workspace .gw-focus { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 12px; max-width: 100%; padding: 6px 12px; border: 1px solid var(--gw-accent); border-radius: 6px; background: var(--gw-selected); font-size: 13px; line-height: 20px; }
.graph-workspace .gw-segmini { display: inline-flex; gap: 4px; }
.graph-workspace .gw-segmini button { min-height: 28px; padding: 0 10px; border: 1px solid #747a87; border-radius: 6px; background: #fff; color: var(--gw-text); font-size: 12px; }
.graph-workspace .gw-segmini button[aria-pressed='true'] { background: #5b5bd6; border-color: #5b5bd6; color: #fff; font-weight: 500; }
.graph-workspace .gw-count { position: absolute; z-index: 6; left: 50%; bottom: 16px; transform: translateX(-50%); display: flex; align-items: center; gap: 12px; min-height: 40px; padding: 0 6px 0 14px; border: 1px solid #747a87; border-radius: 10px; background: var(--gw-panel); color: var(--gw-text-2); font-size: 13px; white-space: nowrap; box-shadow: 0 1px 2px rgb(29 36 51 / 10%); }
.graph-workspace .gw-count b { color: var(--gw-text); font-weight: 600; }
.graph-workspace .gw-count__btn { display: inline-flex; align-items: center; gap: 4px; min-height: 32px; padding: 0 10px; border: 0; border-radius: 6px; background: transparent; color: var(--gw-accent); font-weight: 500; }
.graph-workspace .gw-count__btn:hover { background: var(--gw-selected); }
.graph-workspace .gw-legend__count { margin-left: auto; font-size: 12px; color: var(--gw-text-2); }
.graph-workspace .gw-legend__rel .gw-legend__off { margin-left: 8px; }
.graph-workspace .gw-legend__types li button { display: inline-flex; align-items: center; gap: 4px; min-height: 28px; padding: 0 8px 0 4px; border: 1px solid #747a87; border-radius: 6px; background: #fff; color: var(--gw-text); font-size: 12px; }
.graph-workspace .gw-legend__types li button:hover { background: var(--gw-hover); }
.graph-workspace .gw-legend__types li button[aria-pressed='false'] { background: var(--gw-hover); color: var(--gw-text-3); }
.graph-workspace .gw-legend__types li button small { color: var(--gw-text-2); font-size: 11px; }
.graph-workspace .gw-search { display: flex; align-items: center; gap: 8px; width: 280px; max-width: 100%; min-height: 40px; padding: 0 12px; border: 1px solid #747a87; border-radius: 6px; background: var(--gw-panel); color: var(--gw-text-3); }
.graph-workspace .gw-search input { flex: 1; min-width: 0; border: 0; outline: 0; background: transparent; color: var(--gw-text); font: inherit; }
.graph-workspace .gw-search input::placeholder { color: var(--gw-text-3); opacity: 1; }
.graph-workspace .gw-search:focus-within { outline: 2px solid var(--gw-accent); outline-offset: 2px; }
.graph-workspace .gw-tool { display: grid; place-items: center; width: 36px; height: 36px; flex: none; border: 1px solid #747a87; border-radius: 6px; background: var(--gw-panel); color: var(--gw-text); }
.graph-workspace .gw-tool:hover:not(:disabled) { background: var(--gw-hover); }
.graph-workspace .gw-tool[aria-pressed='true'] { background: var(--gw-selected); border-color: var(--gw-accent); color: var(--gw-accent); }
.graph-workspace .gw-tool:disabled { color: var(--gw-text-3); background: var(--gw-hover); }
.graph-workspace .gw-tr { position: absolute; z-index: 6; top: 16px; right: 16px; display: grid; gap: 6px; }
.graph-workspace .gw-tr__sep { height: 1px; background: var(--gw-line); margin: 2px 4px; }
.graph-workspace .gw-notice { margin: 0; max-width: 360px; padding: 6px 12px; border-radius: 6px; background: var(--gw-warn-bg); color: var(--gw-warn); font-size: 13px; line-height: 20px; }
.graph-workspace .gw-legend { position: absolute; z-index: 6; left: 16px; bottom: 16px; width: 236px; max-height: calc(100% - 96px); overflow-y: auto; border: 1px solid #747a87; border-radius: 10px; background: var(--gw-panel); box-shadow: 0 1px 2px rgb(29 36 51 / 10%); }
.graph-workspace .gw-legend.is-closed { width: auto; }
.graph-workspace .gw-legend__head { width: 100%; display: flex; align-items: center; justify-content: space-between; gap: 8px; min-height: 36px; padding: 0 10px 0 12px; border: 0; background: transparent; font-weight: 600; color: var(--gw-text); border-radius: 10px; }
.graph-workspace .gw-legend__head:hover { background: var(--gw-hover); }
.graph-workspace .gw-legend ul { list-style: none; margin: 0; padding: 0; }
.graph-workspace .gw-legend__rel button { width: 100%; display: flex; align-items: center; gap: 8px; min-height: 36px; padding: 0 12px; border: 0; background: transparent; text-align: left; color: var(--gw-text); }
.graph-workspace .gw-legend__rel button:hover { background: var(--gw-hover); }
.graph-workspace .gw-legend__rel button[aria-pressed='false'] { color: var(--gw-text-3); }
.graph-workspace .gw-legend__rel button[aria-pressed='false'] svg { opacity: 0.55; }
.graph-workspace .gw-legend__rel span { display: grid; line-height: 16px; min-width: 0; }
.graph-workspace .gw-legend__rel small { color: var(--gw-text-3); font-size: 11px; }
.graph-workspace .gw-legend__off { margin-left: auto; display: inline-flex !important; align-items: center; gap: 2px; font-size: 11px; color: var(--gw-text-3); }
.graph-workspace .gw-legend__restore { margin: 0; padding: 6px 12px; font-size: 12px; background: var(--gw-warn-bg); color: var(--gw-warn); }
.graph-workspace .gw-legend__types, .graph-workspace .gw-legend__mastery { display: flex !important; flex-wrap: wrap; gap: 4px 12px; padding: 8px 12px !important; border-top: 1px solid var(--gw-line) !important; font-size: 12px; line-height: 20px; color: var(--gw-text-2); }
.graph-workspace .gw-legend__types li, .graph-workspace .gw-legend__mastery li { display: inline-flex; align-items: center; gap: 4px; }
.graph-workspace .gw-badge { display: inline-grid; place-items: center; width: 16px; height: 16px; border-radius: 8px; color: #fff; font-size: 10px; font-weight: 700; }
.graph-workspace .gw-badge--ok { background: #1f6b3a; }
.graph-workspace .gw-badge--warn { background: #8a5a10; }
.graph-workspace .gw-badge--none { border: 1.5px solid #606a7b; background: #fff; }
.graph-workspace .gw-state { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; padding: 24px; text-align: center; }
.graph-workspace .gw-state p { margin: 0; }
.graph-workspace .gw-state__title { font-size: 16px; font-weight: 600; }
.graph-workspace .gw-btn { min-height: 40px; padding: 0 14px; border: 0; border-radius: 6px; background: #5b5bd6; color: #fff; font-weight: 500; }
.graph-workspace .gw-btn:hover { background: #6262da; }
.graph-workspace .gw-btn:active { background: #4b4bc0; transform: scale(0.98); }
.graph-workspace .gw-list { position: absolute; inset: 0; overflow-y: auto; padding: 72px 24px 24px; display: grid; gap: 16px; align-content: start; }
.graph-workspace .gw-list ul { list-style: none; margin: 0; padding: 0; }
.graph-workspace .gw-row { width: 100%; display: flex; align-items: center; gap: 12px; min-height: 48px; padding: 8px 12px; border: 0; border-radius: 6px; background: transparent; text-align: left; color: var(--gw-text); }
.graph-workspace .gw-row:hover { background: var(--gw-hover); }
.graph-workspace .gw-row.is-selected { background: var(--gw-selected); box-shadow: inset 2px 0 0 var(--gw-accent); }
.graph-workspace .gw-row__name { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.graph-workspace .gw-row__state { flex: none; font-size: 12px; color: var(--gw-text-3); }
.graph-workspace .gw-row__state[data-mastery='mastered'] { color: var(--gw-ok); }
.graph-workspace .gw-row__state[data-mastery='learning'] { color: var(--gw-warn); }
.graph-workspace .gw-skel { display: grid; gap: 12px; }
.graph-workspace .gw-skel i { display: block; height: 14px; border-radius: 4px; background: var(--gw-hover); animation: gw-pulse 900ms ease-in-out infinite alternate; }
.graph-workspace .gw-skel--canvas { width: min(480px, 70%); }
.graph-workspace .gw-skel--canvas i { height: 36px; border-radius: 18px; }

@keyframes gw-in { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
@keyframes gw-fade { from { opacity: 0; } to { opacity: 1; } }
@keyframes gw-pulse { from { opacity: 0.55; } to { opacity: 1; } }

@media (pointer: coarse) {
  .graph-workspace .gw-tool, .graph-workspace .gw-iconbtn { width: 44px; height: 44px; }
  .graph-workspace .gw-seg button, .graph-workspace .gw-chip, .graph-workspace .gw-btn, .graph-workspace .gw-back { min-height: 44px; }
}
@media (max-width: 767px) {
  .graph-workspace .gw-search { width: 100%; }
  .graph-workspace .gw-count__sel { display: none; }
  .graph-workspace .gw-count { gap: 8px; }
  .graph-workspace .gw-legend { width: min(236px, calc(100% - 32px)); }
}
/* 减少动效：关闭位移、缩放与循环骨架，只保留不超过 100ms 的淡入；静态状态不变 */
@media (prefers-reduced-motion: reduce) {
  .graph-workspace, .graph-workspace * { animation-duration: 100ms !important; transition-duration: 1ms !important; transition-delay: 0s !important; }
  .graph-workspace .gw-skel i { animation: none; }
  .graph-workspace.gw.is-overlay .gw-panel { transform: none; }
}

/* ---------- 页面补充：状态、列表、右侧工具、既有组件在工作区内的样子 */
.graph-workspace.gw.is-state { grid-template-columns: minmax(0, 1fr); }
.graph-workspace .gw-state-wrap { display: grid; place-items: center; align-content: center; gap: 12px; min-height: 320px; padding: 24px; text-align: center; color: var(--gw-text); }
.graph-workspace .gw-state-wrap p { margin: 0; }
.graph-workspace .gw-list { position: absolute; inset: 0; overflow-y: auto; padding: 72px 24px 72px; display: grid; gap: 12px; align-content: start; }
.graph-workspace .gw-tr__modes { display: grid; gap: 6px; }
.graph-workspace .gw-hint { margin: 0; color: var(--gw-text-3); font-size: 12px; line-height: 18px; }

/* 推荐：整行卡片（序号徽标、14px/500 名称、次级理由）；名称按钮用伪元素撑满整张卡，整行可点；不用带下划线的裸链接 */
.graph-workspace section.recommendations { padding: 0; border: 0; border-radius: 0; background: transparent; display: grid; gap: 8px; }
.graph-workspace .recommendations h3 { margin: 0; font-size: 14px; line-height: 22px; font-weight: 600; }
.graph-workspace .recommendations .recommendations__version, .graph-workspace .recommendations .recommendations__total { margin: 0; color: var(--gw-text-3); font-size: 12px; line-height: 18px; }
.graph-workspace .recommendations .recommendations__path { margin: 0; color: var(--gw-text-2); font-size: 13px; line-height: 20px; }
.graph-workspace .recommendations .recommendations__unlock { padding: 0; border: 0; background: none; color: var(--gw-accent); font: inherit; text-decoration: underline; text-underline-offset: 2px; }
.graph-workspace .recommendations .recommendations__list { display: grid; gap: 8px; }
.graph-workspace .recommendations .recommendations__item { position: relative; display: grid; grid-template-columns: 22px minmax(0, 1fr); column-gap: 10px; align-items: start; padding: 10px 12px; border: 1px solid #747a87; border-radius: 10px; background: #fff; transition: background-color 120ms var(--ss-ease), border-color 120ms var(--ss-ease); }
.graph-workspace .recommendations .recommendations__item:first-child { box-shadow: inset 3px 0 0 var(--gw-accent); }
.graph-workspace .recommendations .recommendations__item:hover { background: var(--gw-selected); border-color: var(--gw-accent); }
.graph-workspace .recommendations .recommendations__item[data-highlighted='true'] { background: var(--gw-selected); outline: 0; border-color: var(--gw-accent); }
.graph-workspace .recommendations .recommendations__order { grid-row: 1; display: grid; place-items: center; width: 22px; height: 22px; margin: 0; border-radius: 11px; background: var(--gw-selected); color: var(--gw-accent); font-size: 12px; font-weight: 600; line-height: 1; }
.graph-workspace .recommendations .recommendations__select, .graph-workspace .recommendations .recommendations__select:hover:not(:disabled) { grid-column: 2; padding: 0; border: 0; background: none; color: var(--gw-text); font-size: 14px; line-height: 22px; font-weight: 500; text-align: left; text-decoration: none; overflow-wrap: anywhere; }
.graph-workspace .recommendations .recommendations__select::after { content: ''; position: absolute; inset: 0; border-radius: 10px; }
.graph-workspace .recommendations .recommendations__reason { grid-column: 2; margin: 2px 0 0; color: var(--gw-text-2); font-size: 12px; line-height: 18px; }
.graph-workspace .recommendations .recommendations__details { grid-column: 2; position: relative; z-index: 1; margin-top: 4px; }
.graph-workspace .recommendations .recommendations__details summary { cursor: pointer; color: var(--gw-text-2); font-size: 12px; line-height: 18px; }

/* 选中后推荐收成一条可折叠摘要 */
.graph-workspace .gw-next__head { border: 1px solid var(--gw-line); background: var(--gw-canvas); }

/* 掌握状态与详情 */
.graph-workspace .student-graph__mastery .gw-h3 { margin: 0; }
.graph-workspace .knowledge-detail { position: relative; padding: 0; gap: 16px; overflow: visible; color: var(--gw-text); }
.graph-workspace .knowledge-detail h2 { margin: 0; font-size: 20px; line-height: 28px; font-weight: 600; }
.graph-workspace .knowledge-detail h3 { margin: 0 0 8px; font-size: 14px; line-height: 22px; font-weight: 600; }
.graph-workspace .knowledge-detail p { margin: 0; font-size: 14px; line-height: 24px; }
.graph-workspace .knowledge-detail .knowledge-detail__meta { color: var(--gw-text-2); font-size: 12px; line-height: 18px; }
.graph-workspace .knowledge-detail ul { display: flex; flex-wrap: wrap; gap: 8px; margin: 0; padding: 0; list-style: none; }
.graph-workspace .knowledge-detail ol { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
.graph-workspace .knowledge-detail li > button { display: inline-flex; align-items: center; max-width: 100%; min-height: 32px; padding: 0 10px; border: 1px solid #747a87; border-radius: 6px; background: #fff; color: var(--gw-text); font-weight: 400; text-align: left; }
.graph-workspace .knowledge-detail li > button:hover:not(:disabled) { background: var(--gw-selected); border-color: var(--gw-accent); }
.graph-workspace .knowledge-detail ol > li > button { display: flex; width: 100%; }
.graph-workspace .knowledge-detail blockquote { margin: 4px 0 0; padding-left: 8px; border-left: 3px solid var(--gw-line); color: var(--gw-text-2); font-size: 13px; line-height: 22px; }
.graph-workspace .knowledge-detail .knowledge-detail__close { top: -4px; right: -4px; display: grid; place-items: center; width: 32px; height: 32px; padding: 0; border: 0; border-radius: 6px; background: transparent; color: var(--gw-text-2); font-size: 18px; line-height: 1; }
.graph-workspace .knowledge-detail .knowledge-detail__close:hover:not(:disabled) { background: var(--gw-hover); }

/* ---------- 暗色外壳（只有图谱页 .app--graph；其他页面推广前保持原样） */
.app--graph { height: 100vh; height: 100dvh; min-height: 0; display: grid; grid-template-columns: auto minmax(0, 1fr); grid-template-rows: 56px minmax(0, 1fr); grid-template-areas: 'top top' 'rail main'; background: var(--ss-bg); color: var(--ss-text); font-size: 14px; line-height: 22px; overflow: hidden; }
.app--graph :focus-visible { outline: 2px solid var(--ss-link); outline-offset: 2px; }
.app--graph :where(button) { padding: 0; border: 0; border-radius: 0; background: transparent; color: inherit; font: inherit; justify-self: auto; cursor: pointer; }
.app--graph :where(button):hover:not(:disabled) { background: transparent; }
.app-topbar { grid-area: top; display: flex; align-items: center; gap: 12px; min-height: 56px; padding: 0 24px; }
.app-topbar__logo { display: grid; place-items: center; width: 28px; height: 28px; border-radius: var(--ss-radius-sm); background: var(--ss-primary); color: #fff; font-weight: 600; }
.app-topbar__crumb { display: flex; align-items: center; gap: 8px; min-width: 0; color: var(--ss-text-2); }
.app-topbar__crumb a { padding: 2px 4px; border-radius: var(--ss-radius-sm); color: var(--ss-text-2); text-decoration: none; transition: background-color 120ms var(--ss-ease); }
.app-topbar__crumb a:hover { background: var(--ss-hover); color: var(--ss-text); }
.app-topbar__crumb [aria-current] { color: var(--ss-text); font-weight: 500; white-space: nowrap; }
.app-topbar__user { margin-left: auto; display: flex; align-items: center; gap: 12px; color: var(--ss-text-3); }
.app--graph .app-topbar__out { min-height: 32px; padding: 0 12px; border: 1px solid var(--ss-edge); border-radius: 6px; color: var(--ss-text-2); }
.app--graph .app-topbar__out:hover:not(:disabled) { background: var(--ss-hover); color: var(--ss-text); }
.app--graph .app-iconbtn { display: grid; place-items: center; width: 36px; height: 36px; border-radius: var(--ss-radius-sm); color: var(--ss-text-2); transition: background-color 120ms var(--ss-ease); }
.app--graph .app-iconbtn:hover:not(:disabled) { background: var(--ss-hover); color: var(--ss-text); }
.app-rail { grid-area: rail; width: 64px; display: flex; flex-direction: column; gap: 4px; padding: 4px 12px; }
.app-rail.is-expanded { width: 224px; }
.app--graph .app-rail__item, .app--graph .app-rail__toggle { display: flex; align-items: center; gap: 12px; min-height: 40px; padding: 0 11px; border-radius: 6px; color: var(--ss-text-2); text-decoration: none; text-align: left; transition: background-color 120ms var(--ss-ease), color 120ms var(--ss-ease); }
.app--graph .app-rail__item:hover, .app--graph .app-rail__toggle:hover:not(:disabled) { background: var(--ss-hover); color: var(--ss-text); }
.app--graph .app-rail__item.is-current { background: var(--ss-selected); color: var(--ss-text); box-shadow: inset 2px 0 0 var(--ss-link); }
.app-rail__toggle { margin-top: auto; }
.app-rail__label { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.app-scrim { position: fixed; inset: 0; z-index: 30; background: rgb(0 0 0 / 48%); animation: gw-fade 160ms var(--ss-ease); }
.app-drawer { position: fixed; z-index: 31; inset: 0 auto 0 0; width: min(280px, calc(100vw - 32px)); display: flex; flex-direction: column; gap: 4px; padding: 56px 12px 12px; background: var(--ss-panel); box-shadow: var(--ss-shadow-pop-dark); animation: gw-slide-l 220ms var(--ss-ease); }
.app-drawer__close { position: absolute; top: 10px; right: 12px; }
.app-rail__item.is-wide { padding: 0 12px; }
.app--graph .app-main { grid-area: main; max-width: none; margin: 0; padding: 0 12px 12px 0; display: flex; flex-direction: column; gap: 8px; min-height: 0; min-width: 0; }
.app--graph .app-main > .student-graph { flex: 1; min-height: 0; padding: 0; border: 0; border-radius: 0; background: none; box-shadow: none; }  /* 覆盖全站 `.app-main > section` 的卡片外观 */
.app--graph .student-graph > .graph-workspace { height: 100%; min-height: 0; }
@media (max-width: 1023px) { .app--graph { grid-template-columns: minmax(0, 1fr); grid-template-areas: 'top' 'main'; } .app--graph .app-main { padding: 0 16px 12px; } }
@media (max-width: 767px) { .app-topbar { padding: 0 12px; } .app-topbar__name { display: none; } .app-topbar__crumb a, .app-topbar__crumb > span[aria-hidden] { display: none; } .app--graph .app-main { padding: 0 8px 8px; } }
@keyframes gw-slide-l { from { opacity: 0; transform: translateX(-16px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { .app--graph *, .app--graph *::before, .app--graph *::after { animation-duration: 100ms !important; transition-duration: 1ms !important; transition-delay: 0s !important; } }
```

- [ ] **Step 2: 建立组件**

`src/frontend/src/components/GraphOverlay.vue`：

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { useGraphObstacle, type ObstacleKind } from '../graph/obstacles'

/** 盖在画布上的浮层容器（搜索栏、右侧工具、提示条、底部折叠条等）：把自己登记为障碍物，标签排布与镜头适应会避开它 */
const props = withDefaults(defineProps<{ kind?: ObstacleKind; as?: string }>(), { kind: 'hard', as: 'div' })
const el = ref<HTMLElement | null>(null)
useGraphObstacle(el, props.kind)
</script>

<template>
  <component :is="as" ref="el"><slot /></component>
</template>
```

`src/frontend/src/components/GraphLegend.vue`：

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { NODE_TYPE_LABELS, RELATION_TYPE_ORDER, type KnowledgePointType } from '../composables/useGraphFilters'
import { RELATION_STYLES, type RelationType } from '../graph/adapter'
import { useGraphObstacle } from '../graph/obstacles'
import { NODE_TYPE_FILL, NODE_TYPE_GLYPH } from '../graph/theme'
import AppIcon from './AppIcon.vue'

/**
 * 图例兼关系与类型筛选（规格 §4 第 4 层，借鉴 Bloom 的 Legend）：带计数，可按类隐藏；隐藏状态可见、可恢复。
 * 计数取整张图，不随筛选变化。可展开的图例是「软障碍」：标签要避开它，但镜头适应不为它缩小范围。
 */
const props = defineProps<{
  open: boolean
  hiddenRelations: readonly RelationType[]
  hiddenTypes: readonly KnowledgePointType[]
  relationCounts: Readonly<Record<RelationType, number>>
  typeCounts: Readonly<Record<KnowledgePointType, number>>
}>()

const emit = defineEmits<{
  'update:open': [open: boolean]
  toggleRelation: [type: RelationType]
  toggleType: [type: KnowledgePointType]
  restore: []
}>()

const root = ref<HTMLElement | null>(null)
useGraphObstacle(root, 'soft')

/** 箭头方向说明；`EXAMPLE_OF` 的方向契约未明文，这里不写，以画布箭头为准 */
const RELATION_HINTS: Partial<Record<RelationType, string>> = {
  PREREQUISITE: '先学 → 后学',
  CONTAINS: '上级 → 下级',
  RELATED_TO: '无方向',
}
const typeOrder = Object.keys(NODE_TYPE_LABELS) as KnowledgePointType[]
const hiddenCount = () => props.hiddenRelations.length + props.hiddenTypes.length
</script>

<template>
  <section ref="root" class="gw-legend" :class="{ 'is-closed': !open }" data-test="relation-legend" aria-label="图例与关系筛选">
    <button type="button" class="gw-legend__head" :aria-expanded="open" @click="emit('update:open', !open)">
      图例<AppIcon :name="open ? 'chevronDown' : 'chevron'" :size="16" />
    </button>
    <template v-if="open">
      <ul class="gw-legend__rel">
        <li v-for="type in RELATION_TYPE_ORDER" :key="type">
          <button
            type="button"
            :aria-pressed="!hiddenRelations.includes(type)"
            :aria-label="`${RELATION_STYLES[type].label}：${hiddenRelations.includes(type) ? '已隐藏，点击显示' : '显示中，点击隐藏'}`"
            :data-test="`legend-rel-${type}`"
            @click="emit('toggleRelation', type)"
          >
            <svg width="34" height="10" aria-hidden="true">
              <line
                x1="1"
                y1="5"
                :x2="RELATION_STYLES[type].directed ? 25 : 33"
                y2="5"
                :stroke="RELATION_STYLES[type].stroke"
                :stroke-width="RELATION_STYLES[type].lineWidth"
                :stroke-dasharray="RELATION_STYLES[type].lineDash.join(' ')"
              />
              <path v-if="RELATION_STYLES[type].directed" d="M33 5 25 1.5v7z" :fill="RELATION_STYLES[type].stroke" />
            </svg>
            <span>{{ RELATION_STYLES[type].label }}<small v-if="RELATION_HINTS[type]">{{ RELATION_HINTS[type] }}</small></span>
            <span class="gw-legend__count">{{ relationCounts[type] }}</span>
            <span v-if="hiddenRelations.includes(type)" class="gw-legend__off"><AppIcon name="eyeOff" :size="14" />已隐藏</span>
          </button>
        </li>
      </ul>
      <p v-if="hiddenCount() > 0" class="gw-legend__restore" role="status">
        已隐藏 {{ hiddenCount() }} 类 <button type="button" class="gw-link" data-test="legend-restore" @click="emit('restore')">恢复全部</button>
      </p>
      <ul class="gw-legend__types" aria-label="知识点类型，可按类型筛选">
        <li v-for="type in typeOrder" :key="type">
          <button
            type="button"
            :aria-pressed="!hiddenTypes.includes(type)"
            :aria-label="`${NODE_TYPE_LABELS[type]}，${typeCounts[type]} 个：${hiddenTypes.includes(type) ? '已隐藏，点击显示' : '显示中，点击隐藏'}`"
            :data-test="`legend-type-${type}`"
            @click="emit('toggleType', type)"
          >
            <span class="gw-glyph gw-glyph--s" :style="{ background: NODE_TYPE_FILL[type] }" aria-hidden="true">{{ NODE_TYPE_GLYPH[type] }}</span>
            {{ NODE_TYPE_LABELS[type] }}<small>{{ typeCounts[type] }}</small>
            <AppIcon v-if="hiddenTypes.includes(type)" name="eyeOff" :size="14" />
          </button>
        </li>
      </ul>
      <ul class="gw-legend__mastery" aria-label="掌握状态">
        <li><span class="gw-badge gw-badge--ok" aria-hidden="true">✓</span>已掌握</li>
        <li><span class="gw-badge gw-badge--warn" aria-hidden="true">◐</span>学习中</li>
        <li><span class="gw-badge gw-badge--none" aria-hidden="true" />未学习</li>
      </ul>
    </template>
  </section>
</template>
```

`src/frontend/src/components/GraphPreviewCard.vue`：

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { NODE_TYPE_LABELS, type KnowledgePointType } from '../composables/useGraphFilters'
import { useGraphObstacle } from '../graph/obstacles'
import { NODE_TYPE_FILL, NODE_TYPE_GLYPH } from '../graph/theme'
import AppIcon from './AppIcon.vue'

/**
 * 单击节点后的轻量预览卡（规格 §7）：画布底部居中，侧栏不变。再次单击该节点或点「查看详情」才打开详情。
 * 列表接口不带定义，所以这里只放名称、类型、章节、掌握状态与先修/解锁数量；定义在详情里（不为预览多发请求）。
 */
defineProps<{
  name: string
  type: KnowledgePointType
  chapter: string
  masteryText: string
  mastery: 'mastered' | 'learning' | 'unknown'
  prerequisites: number
  unlocks: number
  /** 当前是否处于「只看相邻」 */
  localActive: boolean
}>()

const emit = defineEmits<{ close: []; open: []; toggleLocal: [] }>()

const root = ref<HTMLElement | null>(null)
useGraphObstacle(root)
</script>

<template>
  <aside ref="root" class="gw-preview" data-test="gw-preview" aria-label="知识点预览" aria-live="polite">
    <div class="gw-preview__top">
      <span class="gw-glyph" :style="{ background: NODE_TYPE_FILL[type] }" aria-hidden="true">{{ NODE_TYPE_GLYPH[type] }}</span>
      <span>{{ NODE_TYPE_LABELS[type] }}，{{ chapter }}</span>
      <button type="button" class="gw-iconbtn" aria-label="关闭预览" data-test="gw-preview-close" @click="emit('close')"><AppIcon name="close" /></button>
    </div>
    <p class="gw-preview__name">{{ name }}</p>
    <p class="gw-preview__meta">
      <span :data-mastery="mastery">{{ masteryText }}</span>
      <span>先修 {{ prerequisites }} 项</span>
      <span>学完可解锁 {{ unlocks }} 项</span>
    </p>
    <div class="gw-preview__actions">
      <button type="button" class="gw-btn" data-test="gw-preview-open" @click="emit('open')">查看详情</button>
      <button type="button" class="gw-btn gw-btn--ghost" data-test="gw-preview-local" :aria-pressed="localActive" @click="emit('toggleLocal')">
        {{ localActive ? '显示全部' : '只看相邻' }}
      </button>
      <span class="gw-hint">也可以再次点击该节点</span>
    </div>
  </aside>
</template>
```

`src/frontend/src/components/LocalViewBar.vue`：

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { useGraphObstacle } from '../graph/obstacles'

/** 局部视图提示条：说明隐藏了多少，给出范围（1/2 跳）与恢复入口；隐藏状态必须可见、可恢复 */
defineProps<{ name: string; hiddenCount: number; hops: 1 | 2 }>()
const emit = defineEmits<{ setHops: [hops: 1 | 2]; restore: [] }>()

const root = ref<HTMLElement | null>(null)
useGraphObstacle(root)
</script>

<template>
  <div ref="root" class="gw-focus" data-test="gw-local-bar" role="status">
    <span class="gw-focus__text">只看「{{ name }}」的相邻知识，已隐藏 {{ hiddenCount }} 个</span>
    <span class="gw-segmini" role="group" aria-label="相邻范围">
      <button type="button" :aria-pressed="hops === 1" data-test="gw-local-1" @click="emit('setHops', 1)">1 跳</button>
      <button type="button" :aria-pressed="hops === 2" data-test="gw-local-2" @click="emit('setHops', 2)">2 跳</button>
    </span>
    <button type="button" class="gw-link" data-test="gw-local-restore" @click="emit('restore')">恢复全部</button>
  </div>
</template>
```

`src/frontend/src/components/ChapterMenu.vue`：

```vue
<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useGraphObstacle } from '../graph/obstacles'
import AppIcon from './AppIcon.vue'

/**
 * 章节跳转菜单（规格 §4）：大图只能靠可读缩放浏览，按章节把镜头带到整章。
 * 每项显示本章知识点数量与已掌握数量；Esc 或点菜单外关闭，关闭后焦点回到按钮。
 */
export interface ChapterItem {
  id: string
  title: string
  total: number
  done: number
}

defineProps<{ chapters: readonly ChapterItem[]; currentId: string | null; disabled?: boolean }>()
const emit = defineEmits<{ jump: [chapterId: string] }>()

const root = ref<HTMLElement | null>(null)
const button = ref<HTMLButtonElement | null>(null)
const open = ref(false)
useGraphObstacle(root)

function close(focusButton: boolean): void {
  open.value = false
  if (focusButton) void nextTick(() => button.value?.focus())
}
function onDocumentPointer(event: PointerEvent): void {
  if (open.value && !root.value?.contains(event.target as Node | null)) open.value = false
}
function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && open.value) {
    event.stopPropagation()
    close(true)
  }
}
function jump(id: string): void {
  open.value = false
  emit('jump', id)
  void nextTick(() => button.value?.focus())
}

onMounted(() => document.addEventListener('pointerdown', onDocumentPointer))
onBeforeUnmount(() => document.removeEventListener('pointerdown', onDocumentPointer))
</script>

<template>
  <div ref="root" class="gw-chap" @keydown="onKeydown">
    <button
      ref="button"
      type="button"
      class="gw-tool gw-tool--text"
      data-test="gw-chapter-button"
      aria-haspopup="true"
      :aria-expanded="open"
      :disabled="disabled"
      @click="open = !open"
    >
      <AppIcon name="chapters" />章节<AppIcon name="chevronDown" :size="14" />
    </button>
    <div v-if="open" class="gw-menu" role="group" aria-label="跳转到章节">
      <button
        v-for="chapter in chapters"
        :key="chapter.id"
        type="button"
        class="gw-menu__item"
        :class="{ 'is-current': chapter.id === currentId }"
        :aria-current="chapter.id === currentId ? 'true' : undefined"
        :data-test="`gw-chapter-${chapter.id}`"
        @click="jump(chapter.id)"
      >
        <span class="gw-menu__title">{{ chapter.title }}</span>
        <span class="gw-menu__meta">共 {{ chapter.total }} 个，已掌握 {{ chapter.done }}</span>
      </button>
    </div>
  </div>
</template>
```

`src/frontend/src/components/GraphSidePanel.vue`：

```vue
<script setup lang="ts">
import { ref } from 'vue'
import AppIcon from './AppIcon.vue'

/**
 * 工作台左面板外壳（规格 §5、§6）：未选中显示课程说明，选中后原位切换为知识点详情。
 * 并置模式（容器宽度足够）是普通侧栏，可收起；覆盖模式是左侧抽屉。关闭时整块 `inert`（不可聚焦、读屏不读；关闭时写 `true`、打开时写 `undefined`，不写 `false`：jsdom 等没有 `inert` 属性的环境会把 `false` 渲染成字符串属性）。
 * 内容由页面通过插槽提供（页面保留全部业务与 `data-test` 钩子）；焦点管理（打开进标题、关闭回开关）也在页面。
 */
defineProps<{
  open: boolean
  /** 并置（true）或覆盖抽屉（false） */
  docked: boolean
  /** 当前是否在详情态（决定头部是「返回课程」还是标签） */
  detail: boolean
  /** 详情态的无障碍标题，例如「知识点详情：线性表」 */
  label: string
  /** 内容切换的 key，变化时触发淡入 */
  contentKey: string
}>()

const emit = defineEmits<{ close: []; back: [] }>()
const panel = ref<HTMLElement | null>(null)
defineExpose({ el: panel })
</script>

<template>
  <aside
    ref="panel"
    class="gw-panel"
    :class="{ 'is-open': open }"
    data-test="gw-panel"
    :inert="open ? undefined : true"
    :role="docked ? 'complementary' : 'dialog'"
    :aria-label="detail ? label : '课程说明'"
  >
    <div class="gw-panel__head">
      <button v-if="detail" type="button" class="gw-back" data-focus-start data-test="gw-back" @click="emit('back')">
        <AppIcon name="back" /> 返回课程
      </button>
      <span v-else class="gw-panel__tag">课程说明</span>
      <button type="button" class="gw-iconbtn" aria-label="收起说明面板" data-test="gw-panel-close" @click="emit('close')"><AppIcon name="panel" /></button>
    </div>
    <div class="gw-panel__scroll">
      <div :key="contentKey" class="gw-fade">
        <slot />
      </div>
    </div>
  </aside>
</template>
```

- [ ] **Step 3: 类型检查**

Run: `npm --prefix src/frontend run type-check`
Expected: 退出码 0

- [ ] **Step 4: 提交（仅在用户授权后）**

```bash
git add src/frontend/src/styles/graph-workspace.css src/frontend/src/components/GraphOverlay.vue src/frontend/src/components/GraphLegend.vue src/frontend/src/components/GraphPreviewCard.vue src/frontend/src/components/LocalViewBar.vue src/frontend/src/components/ChapterMenu.vue src/frontend/src/components/GraphSidePanel.vue
git commit -m "feat(frontend): add graph workspace styles and overlay/panel components"
```

---

### Task 15: 学生图谱页接入（保留全部业务与 `data-test` 钩子）

**Files:**
- Modify（整体替换）: `src/frontend/src/views/StudentGraphView.vue`
- Modify: `src/frontend/src/composables/useLearning.ts`（`MASTERY_LABELS.unknown` 文案与成功提示）
- Modify（随设计变化的断言，见 Step 1）: `tests/frontend/h11.test.ts`、`i06.test.ts`、`l13-kp-link.test.ts`、`l14.test.ts`、`tests/e2e/personal.spec.ts`
- Test: `tests/frontend/student-graph-workbench.test.ts`

**Interfaces:**
- Consumes：Task 5–14 的全部模块；`useStudentGraph`、`useGraphFilters`（`locateNode` 纯函数、`toggleRelationType`、`state`/`layout`）、`useLearning`（`learningGraph`、`statusOf`、`setMastery`…）、`Recommendations`、`KnowledgeDetail`、`KnowledgeCards`。
- 画布数据流：`useLearning(visible)` → `useLocalView.apply` → `withoutSelected` → `applyFocusStates`。**必须去掉筛选层与学习路径带来的 `selected`**，否则预览与详情会同时出现两个外环；`selected` 只由 `highlightId`（预览优先，否则详情节点）决定。
- 行为要点：
  - 单击 = 预览；再次单击同一节点或「查看详情」才打开详情；详情已打开时单击另一节点只预览；点空白/Esc/✕ 取消预览；搜索回车 = 预览（卡片视图直接打开详情）；问答链接 `?kp=` 与推荐/关联知识/列表是显式选择，直接打开详情。
  - 搜索框输入仍是**筛选**（保持 H05/H11 行为），回车才定位；`locateNode` 是 `useGraphFilters` 已导出的纯函数，页面不用会选中详情的 `filters.locate`。
  - 画布二次单击打开详情时节点本来就在视口里：用 `skipCameraFor` 跳过「视口跟随选中」；推荐项/列表选中仍移动镜头（L14 保留）。
  - 左面板按**容器宽度**（不是 viewport）判断：≥ 320 + 640 并置，否则覆盖抽屉；首帧同步量一次；没有 `ResizeObserver` 的环境退回 `window` 的 `resize`；覆盖模式选中知识点时抽屉同时打开；Esc 先关抽屉再取消预览。
  - 左面板：概览（课程名、`sg-version`、返回课程链接、进度、`Recommendations`、提示）/ 详情（返回课程、**折叠的「下一步推荐」摘要**——折叠时显示第一项，`v-show` 而非 `v-if`，推荐组件始终挂载、`rc-*` 钩子始终在；掌握标记；`KnowledgeDetail`；详情态下 `sg-version` 仍可见，端到端用例依赖它）。
  - 图例筛选以 `filters.state` 为单一事实来源（隐藏 = 不在可见列表里）；章节聚焦时图例自动收起（用户手动开合后不再自动恢复）；章节菜单在卡片视图禁用。
  - 图谱/卡片切换保留 `sg-mode-graph` / `sg-mode-cards`（`aria-pressed`）；新增布局切换 `gw-layout-toggle`；底部折叠条 `sg-count-toggle`。

- [ ] **Step 1: 更新既有测试中随设计变化的断言，并写新测试**

既有用例里**只改下列几处**（每处都因设计变化，不放宽其他断言）：

`tests/frontend/i06.test.ts`：`selectNode` 改为单击两次（预览 → 打开详情）；`MASTERY_LABELS` 与四处「未开始」改为「未学习」：

```ts
/** 选中一个知识点（图上点选），掌握标记按钮随之出现。UI-GRAPH-PILOT-01：单击只预览，再次单击才打开详情 */
async function selectNode(wrapper: VueWrapper, kpId: string): Promise<void> {
  wrapper.findComponent(GraphCanvas).vm.$emit('nodeClick', kpId)
  wrapper.findComponent(GraphCanvas).vm.$emit('nodeClick', kpId)
  await flushPromises()
}
```

并把该文件里所有 `未开始` 替换为 `未学习`（`MASTERY_LABELS` 断言一处、`sg-mastery-target` 断言三处）。

`tests/frontend/h11.test.ts`（「图上选中后切到卡片」）：

```ts
    // UI-GRAPH-PILOT-01：单击只预览，再次单击同一节点才打开详情（选中）
    wrapper.findComponent(GraphCanvas).vm.$emit('nodeClick', 'k27')
    wrapper.findComponent(GraphCanvas).vm.$emit('nodeClick', 'k27')
    await flushPromises()
    await toCards(wrapper)
```

`tests/frontend/l13-kp-link.test.ts`（两条「QA direct link … preserves requested focus b」）：章节分区布局是异步计算的，算完才建图并聚焦，所以不能只 `flushPromises()` 一次：

```ts
    await flushPromises()
    expect(wrapper.get('[data-test="kd-title"]').text()).toBe('知识点 b')
    // 章节分区布局是异步计算的，算完才建图并聚焦
    await vi.waitFor(() => expect(captured.at(-1)).toBe('kp:b'))
```

`tests/frontend/l14.test.ts`（「画布视口跟随路径焦点」）：

```ts
    // 章节分区布局是异步计算的，算完才建图并聚焦
    await vi.waitFor(() => expect(focused.at(-1)).toBe(nodeElementId('C')))
    await wrapper.get('[data-test="rc-select-G"]').trigger('click')
    await vi.waitFor(() => expect(focused.at(-1)).toBe(nodeElementId('G')))
```

`tests/e2e/personal.spec.ts`：两处 `未开始` 改为 `未学习`（`当前：未学习`、`已标记为未学习`）。

`tests/frontend/graph-presentation.test.ts`：在 `presentation` 的导入列表里加上 `MASTERY_TEXT`，顶部加 `import { MASTERY_LABELS } from '../../src/frontend/src/composables/useLearning'`，并在文件末尾追加（Task 7 时 `MASTERY_LABELS.unknown` 还是「未开始」，所以这条断言放到本任务改完文案之后）：

```ts
describe('MASTERY_TEXT', () => {
  it('与 useLearning 的 MASTERY_LABELS 一致（预览卡、tooltip、列表、详情用同一套文字，不会漂移）', () => {
    expect(MASTERY_TEXT).toEqual(MASTERY_LABELS)
  })
})
```

新增 `tests/frontend/student-graph-workbench.test.ts`：

```ts
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, RouterView } from 'vue-router'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import { COURSES_API_KEY, type CoursesApi } from '../../src/frontend/src/api/courses'
import { PUBLISHED_GRAPH_API_KEY, type PublishedGraphApi } from '../../src/frontend/src/api/graph'
import { KNOWLEDGE_DETAIL_API_KEY, type KnowledgeDetailApi } from '../../src/frontend/src/api/knowledgeDetail'
import GraphCanvas from '../../src/frontend/src/components/GraphCanvas.vue'
import { GRAPH_FACTORY_KEY, type CanvasGraph, type CanvasGraphFactory, type GraphCanvasData } from '../../src/frontend/src/graph/lifecycle'
import { createAppRouter } from '../../src/frontend/src/router/index.ts'
import { useSessionStore } from '../../src/frontend/src/stores/session'
import CoursesView from '../../src/frontend/src/views/CoursesView.vue'
import StudentGraphView from '../../src/frontend/src/views/StudentGraphView.vue'

type KnowledgePoint = components['schemas']['KnowledgePoint']
type KnowledgePointDetail = components['schemas']['KnowledgePointDetail']
type Relation = components['schemas']['Relation']

// ---------------------------------------------------------------- 夹具：a→b→c→d 先修链，e 孤立；两章

function kp(id: string, over: Partial<KnowledgePoint> = {}): KnowledgePoint {
  return {
    id, course_id: 'c1', name: `知识点${id}`, type: 'concept', definition: `${id} 的定义`, level: 1, confidence: 0.9,
    status: 'approved', source: 'ai', locked: false, revision: 1, chapter_id: 'ch1', ...over,
  }
}
function rel(id: string, from: string, to: string): Relation {
  return { id, course_id: 'c1', type: 'PREREQUISITE', from_id: from, to_id: to, confidence: 0.9, status: 'approved', source: 'ai', source_refs: [] } as unknown as Relation
}
const nodes = [kp('a'), kp('b'), kp('c'), kp('d', { chapter_id: 'ch2', type: 'method' }), kp('e', { chapter_id: 'ch2', type: 'method' })]
const edges = [rel('r1', 'a', 'b'), rel('r2', 'b', 'c'), rel('r3', 'c', 'd')]

const factory = (() => ({
  render: () => Promise.resolve(),
  setData: () => {},
  setSize: () => {},
  fitView: () => Promise.resolve(),
  on() {
    return this
  },
  destroy: () => {},
})) as unknown as CanvasGraphFactory

/** jsdom 不排版：把工作区容器量成指定宽度（≥960 并置，否则覆盖） */
function mockWorkspaceWidth(width: number): void {
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(function (this: HTMLElement) {
    return this.classList.contains('graph-workspace') ? width : 0
  })
}

let pinia: Pinia
beforeEach(() => {
  // 宽屏（≥1280）图例默认展开
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1440 })
  sessionStorage.clear()
  pinia = createPinia()
  setActivePinia(pinia)
})
afterEach(() => vi.restoreAllMocks())

async function mountPage(path = '/courses/c1/graph') {
  const session = useSessionStore(pinia)
  session.signIn({ access_token: 'tok', token_type: 'bearer', expires_in: 3600, user: { id: 'u1', username: 'student', role: 'student' } })
  const router = createAppRouter({
    history: createMemoryHistory(),
    getAccountRole: () => session.role,
    coursesComponent: CoursesView,
    studentGraphComponent: StudentGraphView,
  })
  await router.push(path)
  await router.isReady()
  const getPublished = vi.fn<PublishedGraphApi['getPublished']>(async (cid, version) => ({
    format_version: '1.0', course_id: cid, graph_version: version, generated_at: '2026-09-26T00:00:00Z',
    chapters: [{ id: 'ch1', title: '第一章 线性表', order: 1 }, { id: 'ch2', title: '第二章 栈', order: 2 }],
    nodes, edges,
  }))
  const wrapper = mount(defineComponent({ render: () => h(RouterView) }), {
    attachTo: document.body,
    global: {
      plugins: [pinia, router],
      provide: {
        [COURSES_API_KEY as symbol]: {
          list: async () => [], create: vi.fn(),
          get: vi.fn<CoursesApi['get']>(async (cid) => ({ id: cid, name: '数据结构', status: 'published', my_role: 'student', published_version: 3, created_at: '2026-09-01T00:00:00Z' })),
        },
        [PUBLISHED_GRAPH_API_KEY as symbol]: { getPublished },
        [KNOWLEDGE_DETAIL_API_KEY as symbol]: {
          get: vi.fn<KnowledgeDetailApi['get']>(async (cid, kid) => ({ ...kp(kid), course_id: cid, source_refs: [], prerequisites: [], successors: [], related: [] }) as unknown as KnowledgePointDetail),
        },
        [GRAPH_FACTORY_KEY as symbol]: factory,
      },
    },
  })
  await flushPromises()
  return wrapper
}

const canvasProps = (w: VueWrapper) => w.findComponent(GraphCanvas).props() as { graph: GraphCanvasData | null; scope: readonly string[] | null; positions: unknown }
const emitCanvas = (w: VueWrapper, event: 'nodeClick' | 'blankClick', ...args: string[]) => w.findComponent(GraphCanvas).vm.$emit(event, ...args)
const statesOf = (w: VueWrapper, kpId: string) => canvasProps(w).graph?.nodes.find((n) => n.data.kpId === kpId)?.states ?? []
const shownIds = (w: VueWrapper) => canvasProps(w).graph!.nodes.map((n) => n.data.kpId).sort()

describe('学生图谱页：预览与详情（规格 §7）', () => {
  it('单击节点只进入预览：预览卡出现、节点高亮，侧栏不打开详情', async () => {
    const w = await mountPage()
    emitCanvas(w, 'nodeClick', 'b')
    await flushPromises()
    expect(w.get('[data-test="gw-preview"]').text()).toContain('知识点b')
    expect(w.find('[data-test="knowledge-detail"]').exists()).toBe(false)
    expect(statesOf(w, 'b')).toContain('selected')
    expect(statesOf(w, 'a')).toContain('neighbor')
    expect(statesOf(w, 'e')).toContain('dimmed')
    w.unmount()
  })

  it('再次单击同一节点才打开详情，预览卡消失', async () => {
    const w = await mountPage()
    emitCanvas(w, 'nodeClick', 'b')
    emitCanvas(w, 'nodeClick', 'b')
    await flushPromises()
    expect(w.find('[data-test="gw-preview"]').exists()).toBe(false)
    expect(w.get('[data-test="kd-title"]').text()).toBe('知识点b')
    expect(w.get('[data-test="sg-version"]').text()).toContain('v3') // 详情态下版本号仍然可见（端到端用例依赖它）
    w.unmount()
  })

  it('详情已打开时单击另一个节点：只预览新节点，详情保持不变；画布上只有新节点带选中外环', async () => {
    const w = await mountPage()
    emitCanvas(w, 'nodeClick', 'b')
    emitCanvas(w, 'nodeClick', 'b')
    await flushPromises()
    emitCanvas(w, 'nodeClick', 'c')
    await flushPromises()
    expect(w.get('[data-test="gw-preview"]').text()).toContain('知识点c')
    expect(w.get('[data-test="kd-title"]').text()).toBe('知识点b')
    expect(statesOf(w, 'c')).toContain('selected')
    expect(statesOf(w, 'b')).not.toContain('selected')
    w.unmount()
  })

  it('点空白处、Esc、预览卡 ✕ 都取消预览，详情不受影响', async () => {
    mockWorkspaceWidth(1200) // 并置模式：Esc 直接取消预览（覆盖抽屉打开时 Esc 先关抽屉，见下方面板用例）
    const w = await mountPage()
    emitCanvas(w, 'nodeClick', 'b')
    emitCanvas(w, 'nodeClick', 'b')
    emitCanvas(w, 'nodeClick', 'c')
    await flushPromises()
    emitCanvas(w, 'blankClick')
    await flushPromises()
    expect(w.find('[data-test="gw-preview"]').exists()).toBe(false)
    expect(w.get('[data-test="kd-title"]').text()).toBe('知识点b')

    emitCanvas(w, 'nodeClick', 'c')
    await flushPromises()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(w.find('[data-test="gw-preview"]').exists()).toBe(false)

    emitCanvas(w, 'nodeClick', 'c')
    await flushPromises()
    await w.get('[data-test="gw-preview-close"]').trigger('click')
    expect(w.find('[data-test="gw-preview"]').exists()).toBe(false)
    expect(w.get('[data-test="kd-title"]').text()).toBe('知识点b')
    w.unmount()
  })

  it('预览卡「查看详情」打开详情；卡上有先修与解锁数量和掌握状态文字', async () => {
    const w = await mountPage()
    emitCanvas(w, 'nodeClick', 'b')
    await flushPromises()
    const card = w.get('[data-test="gw-preview"]').text()
    expect(card).toContain('先修 1 项')
    expect(card).toContain('学完可解锁 1 项')
    expect(card).toContain('未学习')
    await w.get('[data-test="gw-preview-open"]').trigger('click')
    await flushPromises()
    expect(w.get('[data-test="kd-title"]').text()).toBe('知识点b')
    w.unmount()
  })

  it('搜索回车：定位并进入预览（不是直接打开详情）；没有匹配时给出提示', async () => {
    const w = await mountPage()
    const input = w.get('input[type="search"]')
    await input.setValue('知识点c')
    await w.get('form[role="search"]').trigger('submit')
    await flushPromises()
    expect(w.get('[data-test="gw-preview"]').text()).toContain('知识点c')
    expect(w.find('[data-test="knowledge-detail"]').exists()).toBe(false)

    await input.setValue('不存在')
    await w.get('form[role="search"]').trigger('submit')
    await flushPromises()
    expect(w.get('[data-test="sg-search-notice"]').text()).toContain('未找到匹配的知识点')
    w.unmount()
  })

  it('问答链接 ?kp= 是显式选择：直接打开详情', async () => {
    const w = await mountPage('/courses/c1/graph?kp=c&v=3')
    expect(w.get('[data-test="kd-title"]').text()).toBe('知识点c')
    expect(w.find('[data-test="gw-preview"]').exists()).toBe(false)
    w.unmount()
  })
})

describe('学生图谱页：只看相邻（局部视图）', () => {
  it('开启 1 跳隐藏其余节点并给出提示条；2 跳扩大范围；恢复全部回到整图；清除预览不取消局部视图', async () => {
    const w = await mountPage()
    emitCanvas(w, 'nodeClick', 'b')
    await flushPromises()
    await w.get('[data-test="gw-preview-local"]').trigger('click')
    await flushPromises()
    expect(shownIds(w)).toEqual(['a', 'b', 'c'])
    expect(w.get('[data-test="gw-local-bar"]').text()).toContain('只看「知识点b」的相邻知识，已隐藏 2 个')

    await w.get('[data-test="gw-local-2"]').trigger('click')
    await flushPromises()
    expect(shownIds(w)).toEqual(['a', 'b', 'c', 'd'])
    expect(w.get('[data-test="gw-local-bar"]').text()).toContain('已隐藏 1 个')

    emitCanvas(w, 'blankClick')
    await flushPromises()
    expect(w.find('[data-test="gw-local-bar"]').exists()).toBe(true)

    await w.get('[data-test="gw-local-restore"]').trigger('click')
    await flushPromises()
    expect(shownIds(w)).toEqual(['a', 'b', 'c', 'd', 'e'])
    expect(w.find('[data-test="gw-local-bar"]').exists()).toBe(false)
    w.unmount()
  })

  it('与类型筛选叠加取交集，底部计数同步', async () => {
    const w = await mountPage()
    emitCanvas(w, 'nodeClick', 'c')
    await flushPromises()
    await w.get('[data-test="gw-preview-local"]').trigger('click')
    await w.get('[data-test="legend-type-method"]').trigger('click') // 隐藏方法类（d、e）
    await flushPromises()
    expect(shownIds(w)).toEqual(['b', 'c'])
    expect(w.get('.gw-count').text()).toContain('显示 2 / 5')
    w.unmount()
  })
})

describe('学生图谱页：图例即筛选', () => {
  it('图例带计数；隐藏类型后画布与列表同步，「恢复全部」同时恢复关系与类型', async () => {
    const w = await mountPage()
    const legend = w.get('[data-test="relation-legend"]')
    expect(legend.get('[data-test="legend-type-concept"]').text()).toContain('3')
    expect(legend.get('[data-test="legend-type-method"]').text()).toContain('2')
    expect(legend.get('[data-test="legend-rel-PREREQUISITE"]').text()).toContain('3')

    await legend.get('[data-test="legend-type-method"]').trigger('click')
    await legend.get('[data-test="legend-rel-PREREQUISITE"]').trigger('click')
    await flushPromises()
    expect(shownIds(w)).toEqual(['a', 'b', 'c'])
    expect(canvasProps(w).graph!.edges).toHaveLength(0)
    expect(legend.get('[data-test="legend-type-method"]').attributes('aria-label')).toContain('已隐藏')
    expect(legend.text()).toContain('已隐藏 2 类')

    await legend.get('[data-test="legend-restore"]').trigger('click')
    await flushPromises()
    expect(shownIds(w)).toEqual(['a', 'b', 'c', 'd', 'e'])
    expect(canvasProps(w).graph!.edges).toHaveLength(3)
    w.unmount()
  })
})

describe('学生图谱页：章节跳转与章节聚焦', () => {
  it('选择章节后外框成员为本章节点，其他章节淡化，出现可取消的「已定位」标签并收起图例；取消后恢复', async () => {
    const w = await mountPage()
    await w.get('[data-test="gw-chapter-button"]').trigger('click')
    expect(w.get('[data-test="gw-chapter-ch2"]').text()).toContain('共 2 个，已掌握 0')
    await w.get('[data-test="gw-chapter-ch2"]').trigger('click')
    await flushPromises()
    expect(w.get('[data-test="gw-chapter-chip"]').text()).toContain('已定位：第二章 栈')
    expect(canvasProps(w).scope).toEqual(['d', 'e'])
    expect(statesOf(w, 'd')).toContain('match')
    expect(statesOf(w, 'a')).toContain('dimmed')
    expect(w.find('[data-test="legend-type-concept"]').exists()).toBe(false) // 图例自动收起

    await w.get('.gw-chip-on__x').trigger('click')
    await flushPromises()
    expect(w.find('[data-test="gw-chapter-chip"]').exists()).toBe(false)
    expect(canvasProps(w).scope).toBeNull()
    expect(statesOf(w, 'a')).not.toContain('dimmed')
    expect(w.find('[data-test="legend-type-concept"]').exists()).toBe(true) // 自动收起的图例自动恢复
    w.unmount()
  })
})

describe('学生图谱页：左面板按容器宽度并置或覆盖', () => {
  it('容器宽度 ≥960 并置，可收起；不足时是覆盖抽屉（关闭时 inert），选中知识点时抽屉同时打开', async () => {
    mockWorkspaceWidth(1200)
    const docked = await mountPage()
    expect(docked.get('.graph-workspace').classes()).toContain('is-docked')
    expect(docked.get('[data-test="gw-panel"]').attributes('role')).toBe('complementary')
    await docked.get('[data-test="gw-panel-close"]').trigger('click')
    expect(docked.get('.graph-workspace').classes()).toContain('is-collapsed')
    expect(docked.get('[data-test="gw-panel"]').attributes('inert')).toBeDefined()
    await docked.get('[data-test="gw-panel-open"]').trigger('click')
    expect(docked.get('.graph-workspace').classes()).not.toContain('is-collapsed')
    docked.unmount()
    vi.restoreAllMocks()

    const overlay = await mountPage() // jsdom 宽度为 0 → 覆盖模式
    expect(overlay.get('.graph-workspace').classes()).toContain('is-overlay')
    expect(overlay.get('[data-test="gw-panel"]').attributes('role')).toBe('dialog')
    expect(overlay.get('[data-test="gw-panel"]').attributes('inert')).toBeDefined()
    emitCanvas(overlay, 'nodeClick', 'b')
    emitCanvas(overlay, 'nodeClick', 'b')
    await flushPromises()
    expect(overlay.get('[data-test="gw-panel"]').attributes('inert')).toBeUndefined()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(overlay.get('[data-test="gw-panel"]').attributes('inert')).toBeDefined()
    overlay.unmount()
  })
})

describe('学生图谱页：状态与可访问性', () => {
  it('无障碍：画布区描述规模；图例按钮名称写明显示/隐藏状态；工具栏有名称', async () => {
    const w = await mountPage()
    expect(w.get('.graph-canvas__stage').attributes('aria-label')).toBe('课程知识图谱：5 个知识点，3 条关系')
    expect(w.get('[data-test="legend-rel-PREREQUISITE"]').attributes('aria-label')).toBe('前置：显示中，点击隐藏')
    expect(w.get('[role="toolbar"]').attributes('aria-label')).toBe('画布工具')
    expect(w.get('[data-test="sg-mode-graph"]').attributes('aria-label')).toBe('图谱视图')
    w.unmount()
  })
})
```

- [ ] **Step 2: 运行，确认失败**

Run: `npm --prefix src/frontend run test -- --run student-graph-workbench h11 i06 l13 l14`
Expected: FAIL（页面还是旧版：没有预览卡、图例、章节菜单、左面板；`MASTERY_LABELS` 仍是「未开始」）

- [ ] **Step 3: 改 `useLearning.ts` 的文案**

`src/frontend/src/composables/useLearning.ts`：`MASTERY_LABELS` 里 `unknown: '未开始'` 改为 `unknown: '未学习'`；同文件 `successText` 里返回的 `'已标记为未开始。'` 改为 `'已标记为未学习。'`（规格 §3.4：`unknown` 显示明确文字「未学习」）。

- [ ] **Step 4: 整体替换 `StudentGraphView.vue`**

`src/frontend/src/views/StudentGraphView.vue`：

```vue
<script setup lang="ts">
import { computed, inject, nextTick, onBeforeUnmount, onMounted, provide, ref, watch, type InjectionKey } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { HTTP_CLIENT_KEY } from '../api/client'
import { COURSES_API_KEY } from '../api/courses'
import { createPublishedGraphApi, PUBLISHED_GRAPH_API_KEY } from '../api/graph'
import type { HttpClient } from '../api/http'
import { createProgressApi, PROGRESS_API_KEY, type MasteryStatus, type ProgressApi } from '../api/progress'
import { createRecommendApi, RECOMMEND_API_KEY, type RecommendApi } from '../api/recommend'
import AppIcon from '../components/AppIcon.vue'
import ChapterMenu, { type ChapterItem } from '../components/ChapterMenu.vue'
import GraphCanvas from '../components/GraphCanvas.vue'
import GraphLegend from '../components/GraphLegend.vue'
import GraphOverlay from '../components/GraphOverlay.vue'
import GraphPreviewCard from '../components/GraphPreviewCard.vue'
import GraphSidePanel from '../components/GraphSidePanel.vue'
import KnowledgeCards from '../components/KnowledgeCards.vue'
import KnowledgeDetail from '../components/KnowledgeDetail.vue'
import LocalViewBar from '../components/LocalViewBar.vue'
import Recommendations from '../components/Recommendations.vue'
import {
  locateNode,
  NODE_TYPE_LABELS,
  RELATION_TYPE_ORDER,
  useGraphFilters,
  type KnowledgePointType,
} from '../composables/useGraphFilters'
import { useGraphLayout } from '../composables/useGraphLayout'
import { MASTERY_LABELS, useLearning } from '../composables/useLearning'
import { kpLinkOutcome } from '../composables/kpLink'
import { useLocalView } from '../composables/useLocalView'
import { usePreviewFocus } from '../composables/usePreviewFocus'
import { useReducedMotion } from '../composables/useReducedMotion'
import { toKnowledgeCards, useStudentGraph } from '../composables/useStudentGraph'
import { kpIdFromElementId, nodeElementId, type RelationType } from '../graph/adapter'
import { applyFocusStates } from '../graph/focusStates'
import type { GraphCanvasData } from '../graph/lifecycle'
import { createObstacleRegistry, GRAPH_OBSTACLES_KEY } from '../graph/obstacles'
import { masteryOfStates } from '../graph/presentation'
import { COURSE_ROUTE, homeRouteFor, NOTICE_COURSE_FORBIDDEN, ROOT_ROUTE, STUDENT_GRAPH_ROUTE } from '../router'
import { useSessionStore } from '../stores/session'

/**
 * 学生图谱页（H11，ADR-063；UI-GRAPH-PILOT-01 工作台）：只读已发布版本，图谱与卡片两种视图共用筛选与选中，
 * 详情复用 H06。左面板（课程说明 / 知识点详情）+ 浅色画布 + 浮层（搜索、章节、图例、预览卡、局部视图条、小地图）。
 *
 * 数据请求与草稿防护在 `useStudentGraph`；筛选在 `useGraphFilters`；掌握标记与推荐在 `useLearning`（I06）；
 * 预览/详情状态机在 `usePreviewFocus`；只看相邻在 `useLocalView`；章节分区布局在 `useGraphLayout`。
 * 本页只做组装：把筛选后的可见图交给 `useLearning` 落掌握状态色与推荐高亮，再叠加局部视图与聚焦状态后交给画布。
 *
 * I06 增量：学习接口（`PROGRESS_API_KEY`/`RECOMMEND_API_KEY`）未注入时退回 H11 原状（不读进度、不渲染标记与推荐）。
 */
const coursesApi = inject(COURSES_API_KEY, null)
if (coursesApi === null) throw new Error('StudentGraphView 需要注入 COURSES_API_KEY')
const graphApi =
  inject(PUBLISHED_GRAPH_API_KEY, null) ??
  (() => {
    const client = inject(HTTP_CLIENT_KEY, null)
    if (client === null) throw new Error('StudentGraphView 需要注入 PUBLISHED_GRAPH_API_KEY 或 HTTP_CLIENT_KEY')
    return createPublishedGraphApi(client)
  })()

/** 学习接口沿用 H09/H14 的注入惯例：优先注入键，否则用会话客户端构造；两者都缺时返回 null（本页退回 H11 原状） */
function learningApi<T>(key: InjectionKey<T>, build: (client: HttpClient) => T): T | null {
  const injected = inject(key, null)
  if (injected !== null) return injected
  const client = inject(HTTP_CLIENT_KEY, null)
  return client === null ? null : build(client)
}
const progressApi = learningApi<ProgressApi>(PROGRESS_API_KEY, createProgressApi)
const recommendApi = learningApi<RecommendApi>(RECOMMEND_API_KEY, createRecommendApi)

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const reduced = useReducedMotion()
// 浮层登记障碍物：标签排布与镜头适应避开它们
provide(GRAPH_OBSTACLES_KEY, createObstacleRegistry())

// 离开本路由即为 null：composable 中止在途请求
const courseId = computed(() => {
  const cid = route.params.cid
  return route.name === STUDENT_GRAPH_ROUTE && typeof cid === 'string' && cid !== '' ? cid : null
})

function leaveForbidden(): void {
  const role = session.role
  void router.replace(
    role === null ? { name: ROOT_ROUTE } : { name: homeRouteFor(role), query: { notice: NOTICE_COURSE_FORBIDDEN } },
  )
}

const { status, error, retryable, courseName, graphVersion, graph, chapters, reload } = useStudentGraph({
  coursesApi,
  graphApi,
  courseId,
  onCourseForbidden: leaveForbidden,
})

const filters = useGraphFilters(graph)
const { selected, visible, summary } = filters

const canvas = ref<InstanceType<typeof GraphCanvas> | null>(null)

// ---------------------------------------------------------------- 预览 / 详情（规格 §7）
const focus = usePreviewFocus({ selected, select: filters.select })
const { previewId, highlightId } = focus
/** 由画布二次单击打开的详情：节点本来就在视口里，不再移动镜头 */
let skipCameraFor: string | null = null
function onCanvasNode(kpId: string): void {
  if (previewId.value === kpId || selected.value === kpId) skipCameraFor = kpId
  focus.onNodeClick(kpId)
}

// L13-4：问答知识点链接 ?kp=&v=：当前课程的图加载完后选中并聚焦；目标不在或版本不同时提示。
// 同一链接只处理一次（之后用户可自由选择）；切课时组合式重置图谱，旧课程的 kp 不会落到新课程。
const linkNotice = ref<string | null>(null)
let handledLink: string | null = null
watch(
  [() => route.query.kp, () => route.query.v, courseId, status, graphVersion] as const,
  ([kp, v, cid, current]) => {
    if (current !== 'ready' || graph.value === null || cid === null) return
    const key = `${cid}|${String(kp)}|${String(v)}|${graphVersion.value}`
    if (key === handledLink) return
    const outcome = kpLinkOutcome({ kp, v }, cid, {
      course_id: cid,
      graph_version: graphVersion.value,
      nodes: graph.value.nodes.map((node) => ({ id: node.data.kpId })),
    })
    if (outcome === null) return
    handledLink = key
    linkNotice.value = outcome.notice
    // 问答链接是显式选择：直接打开详情
    if (outcome.select !== null) focus.open(outcome.select)
  },
  { immediate: true },
)

type ViewMode = 'graph' | 'cards'
const mode = ref<ViewMode>('graph')

// L13-2 / 规格 §7：搜索框回车定位并进入预览（列表视图直接打开详情）；未找到时提示
const searchNotice = ref<string | null>(null)
function onLocate(): void {
  const current = graph.value
  const query = filters.state.value.query
  if (current === null) return
  const kpId = locateNode(current, filters.state.value, query)
  searchNotice.value = kpId === null ? '未找到匹配的知识点，可调整关键字或筛选条件。' : null
  if (kpId === null) return
  if (mode.value === 'graph') {
    focus.preview(kpId)
    canvas.value?.focus(kpId)
  } else focus.open(kpId)
}
function onQuery(event: Event): void {
  filters.state.value = { ...filters.state.value, query: (event.target as HTMLInputElement).value }
  searchNotice.value = null
}

const cards = computed(() => (visible.value === null ? [] : toKnowledgeCards(visible.value.nodes, chapters.value)))
const empty = computed(() => status.value === 'ready' && graph.value !== null && graph.value.nodes.length === 0)

// ---------------------------------------------------------------- I06：掌握标记与推荐

const learningEnabled = progressApi !== null && recommendApi !== null
const {
  status: learningStatus,
  error: learningError,
  retryable: learningRetryable,
  recommendState,
  recommendations,
  totalEligible,
  recommendError,
  recommendLoading,
  busyKpId,
  notice: learningNotice,
  learningGraph,
  learningPath,
  statusOf,
  setMastery,
  reload: reloadLearning,
  refreshRecommend,
} = useLearning({
  progressApi,
  recommendApi,
  courseId,
  // 掌握标记只在已显示的发布版本上读写：版本未知时组合式既不读也不写
  graphVersion,
  ready: computed(() => status.value === 'ready'),
  graph: visible,
  // L14：路径按完整已发布图计算；点推荐项（即选中它）就解释它，否则解释第一个推荐项
  pathGraph: graph,
  focus: selected,
  onCourseForbidden: leaveForbidden,
  // 显示版本落后于服务端绑定版本：重新加载图谱与进度，而不是把新投影套到旧图
  onVersionStale: reload,
})

// L14：视口跟随路径焦点（首个推荐项，或学生点选的推荐项），让高亮的路径落在画面里
watch(
  [canvas, selected, () => learningPath.value?.focus ?? null, status],
  () => {
    if (status.value !== 'ready') return
    const target = selected.value ?? learningPath.value?.focus ?? null
    if (target === null) return
    if (target === skipCameraFor) {
      skipCameraFor = null
      return
    }
    canvas.value?.focus(target)
  },
  { flush: 'post', immediate: true },
)

// C05-3：路径行里点「之后解锁」的名称：选中该节点并把画布移过去（解锁节点可能在视口外）
function onUnlockLocate(kpId: string): void {
  focus.open(kpId)
  canvas.value?.focus(kpId)
}

const masteryOptions: Array<{ value: MasteryStatus; label: string }> = [
  { value: 'unknown', label: MASTERY_LABELS.unknown },
  { value: 'learning', label: MASTERY_LABELS.learning },
  { value: 'mastered', label: MASTERY_LABELS.mastered },
]

const selectedName = computed(() => {
  const kpId = selected.value
  if (kpId === null) return ''
  return graph.value?.nodes.find((node) => node.data.kpId === kpId)?.data.name ?? kpId
})

// ---------------------------------------------------------------- 图例：关系与类型筛选（单一事实来源是筛选状态）
const allTypes = Object.keys(NODE_TYPE_LABELS) as KnowledgePointType[]
const hiddenRelations = computed(() => RELATION_TYPE_ORDER.filter((t) => !filters.state.value.relationTypes.includes(t)))
const hiddenTypes = computed(() => allTypes.filter((t) => !filters.state.value.nodeTypes.includes(t)))
const relationCounts = computed(() => {
  const counts = Object.fromEntries(RELATION_TYPE_ORDER.map((t) => [t, 0])) as Record<RelationType, number>
  for (const edge of graph.value?.edges ?? []) counts[edge.data.type] += 1
  return counts
})
const typeCounts = computed(() => {
  const counts = Object.fromEntries(allTypes.map((t) => [t, 0])) as Record<KnowledgePointType, number>
  for (const node of graph.value?.nodes ?? []) counts[node.data.type] += 1
  return counts
})
function toggleType(type: KnowledgePointType): void {
  const current = filters.state.value.nodeTypes
  filters.state.value = {
    ...filters.state.value,
    nodeTypes: allTypes.filter((t) => t === type !== current.includes(t)),
  }
}
function restoreAllFilters(): void {
  filters.state.value = { ...filters.state.value, relationTypes: [...RELATION_TYPE_ORDER], nodeTypes: [...allTypes] }
}
/** 章节聚焦时图例自动收起（它会压住本章节点）；清除定位后恢复。用户自己点过图例按钮就不再自动恢复 */
const legendOpen = ref(typeof window === 'undefined' || window.innerWidth >= 1280)
let legendAutoClosed = false
function setLegendOpen(open: boolean): void {
  legendAutoClosed = false
  legendOpen.value = open
}

// ---------------------------------------------------------------- 只看相邻（局部视图）
const localView = useLocalView(() => visible.value)
const localName = computed(() => {
  const id = localView.view.value?.id
  return id === undefined ? '' : (graph.value?.nodes.find((n) => n.data.kpId === id)?.data.name ?? id)
})
const hiddenByLocal = computed(() => (visible.value?.nodes.length ?? 0) - (localView.ids.value?.size ?? 0))
// 开启或切换 1/2 跳时，把镜头适应到可见的邻域；恢复全部时回到整图
watch(localView.view, () => {
  void nextTick(() => canvas.value?.fitTo(localView.ids.value === null ? undefined : [...localView.ids.value]))
})
// 局部视图的中心被筛选隐藏或换课程后自动失效
watch(visible, (v) => {
  const id = localView.view.value?.id
  if (id !== undefined && v !== null && !v.nodes.some((n) => n.data.kpId === id)) localView.clear()
  const preview = previewId.value
  if (preview !== null && v !== null && !v.nodes.some((n) => n.data.kpId === preview)) focus.clearPreview()
})

// ---------------------------------------------------------------- 章节跳转与章节聚焦
const chapterId = ref<string | null>(null)
const chapterItems = computed<ChapterItem[]>(() => {
  const g = graph.value
  if (g === null) return []
  const catalog = new Map(chapters.value.map((c) => [c.id, c]))
  const byChapter = new Map<string, string[]>()
  for (const node of g.nodes) {
    if (node.data.chapterId !== null) byChapter.set(node.data.chapterId, [...(byChapter.get(node.data.chapterId) ?? []), node.data.kpId])
  }
  const order = (id: string) => catalog.get(id)?.order ?? Number.POSITIVE_INFINITY
  return [...byChapter.keys()]
    .sort((a, b) => order(a) - order(b) || (a < b ? -1 : a > b ? 1 : 0))
    .map((id) => {
      const ids = byChapter.get(id)!
      return { id, title: catalog.get(id)?.title ?? id, total: ids.length, done: ids.filter((kp) => statusOf(kp) === 'mastered').length }
    })
})
const activeChapter = computed(() => chapterItems.value.find((c) => c.id === chapterId.value) ?? null)
/** 本章节点（知识点 ID），只取当前显示的 */
const chapterKpIds = computed<string[]>(() => {
  if (chapterId.value === null) return []
  return (visible.value?.nodes ?? []).filter((n) => n.data.chapterId === chapterId.value).map((n) => n.data.kpId)
})
function jumpChapter(id: string): void {
  if (legendOpen.value) {
    legendOpen.value = false
    legendAutoClosed = true
  }
  chapterId.value = id
  focus.clearPreview()
  void nextTick(() => canvas.value?.fitTo(chapterKpIds.value))
}
function clearChapter(): void {
  chapterId.value = null
  if (legendAutoClosed) {
    legendAutoClosed = false
    legendOpen.value = true
  }
}

// ---------------------------------------------------------------- 画布数据：学习状态 → 局部视图 → 聚焦状态
/** 预览/选中由 `highlightId` 决定；筛选层与学习路径带来的 `selected` 要去掉，否则预览与详情会同时出现两个外环 */
function withoutSelected(g: GraphCanvasData): GraphCanvasData {
  return {
    nodes: g.nodes.map((n) => (n.states?.includes('selected') ? { ...n, states: n.states.filter((s) => s !== 'selected') } : n)),
    edges: g.edges,
  }
}
const canvasGraph = computed<GraphCanvasData | null>(() => {
  const base = localView.apply(learningGraph.value)
  if (base === null) return null
  const hl = highlightId.value
  const scope = chapterId.value === null ? null : new Set(chapterKpIds.value.map(nodeElementId))
  return applyFocusStates(withoutSelected(base), {
    selectedId: hl === null ? null : nodeElementId(hl),
    matchedIds: new Set(),
    chapterIds: scope,
    fade: 'standard',
  })
})

// ---------------------------------------------------------------- 章节分区布局（对完整已发布图算一次，筛选只显示子集）
const layoutSource = computed(() => {
  const g = graph.value
  if (g === null) return null
  return {
    nodes: g.nodes.map((n) => ({ id: n.data.kpId, chapter: n.data.chapterId })),
    edges: g.edges.map((e) => ({
      id: e.data.relationId,
      source: kpIdFromElementId(e.source),
      target: kpIdFromElementId(e.target),
      type: e.data.type,
    })),
    chapterOrder: [...chapters.value].sort((a, b) => a.order - b.order || (a.id < b.id ? -1 : 1)).map((c) => c.id),
  }
})
const { positions } = useGraphLayout(() => layoutSource.value)

// ---------------------------------------------------------------- 预览卡
const preview = computed(() => {
  const id = previewId.value
  const g = graph.value
  const node = id === null || g === null ? undefined : g.nodes.find((n) => n.data.kpId === id)
  if (id === null || g === null || node === undefined) return null
  const el = nodeElementId(id)
  const status = statusOf(id)
  const mastery: 'mastered' | 'learning' | 'unknown' = status === 'mastered' ? 'mastered' : status === 'learning' ? 'learning' : 'unknown'
  return {
    id,
    name: node.data.name,
    type: node.data.type,
    chapter: chapters.value.find((c) => c.id === node.data.chapterId)?.title ?? '未分章',
    mastery,
    masteryText: MASTERY_LABELS[status],
    prerequisites: g.edges.filter((e) => e.data.type === 'PREREQUISITE' && e.target === el).length,
    unlocks: g.edges.filter((e) => e.data.type === 'PREREQUISITE' && e.source === el).length,
  }
})

// ---------------------------------------------------------------- 进度（左面板概览）
const progress = computed(() => {
  const total = graph.value?.nodes.length ?? 0
  let done = 0
  let learning = 0
  for (const node of graph.value?.nodes ?? []) {
    const s = statusOf(node.data.kpId)
    if (s === 'mastered') done += 1
    else if (s === 'learning') learning += 1
  }
  return { total, done, learning, percent: total === 0 ? 0 : Math.round((done / total) * 100) }
})

// ---------------------------------------------------------------- 面板：按容器宽度判断并置/覆盖
const ws = ref<HTMLElement | null>(null)
const panel = ref<InstanceType<typeof GraphSidePanel> | null>(null)
const panelToggle = ref<HTMLButtonElement | null>(null)
const wsWidth = ref(0)
/** 左面板 320 + 画布至少 640（规格 §5.1）；容器宽度不足时改覆盖抽屉 */
const docked = computed(() => wsWidth.value >= 320 + 640)
const dockedOpen = ref(true)
const overlayOpen = ref(false)
const panelVisible = computed(() => (docked.value ? dockedOpen.value : overlayOpen.value))
let observer: ResizeObserver | null = null
const measureWorkspace = (): void => {
  wsWidth.value = ws.value?.clientWidth ?? 0
}

function openPanel(): void {
  if (docked.value) dockedOpen.value = true
  else overlayOpen.value = true
  void nextTick(() => panel.value?.el?.querySelector<HTMLElement>('[data-focus-start]')?.focus())
}
function closePanel(): void {
  if (docked.value) dockedOpen.value = false
  else overlayOpen.value = false
  void nextTick(() => panelToggle.value?.focus())
}
// 覆盖模式下选中知识点时抽屉同时打开；并置模式下面板本来就在
watch(selected, (now) => {
  if (now !== null && !docked.value) overlayOpen.value = true
})
watch(docked, (now) => {
  if (now) overlayOpen.value = false
})
// Esc 依次关闭：章节菜单（菜单自己处理）→ 覆盖抽屉 → 预览
function onKey(event: KeyboardEvent): void {
  if (event.key !== 'Escape') return
  if (!docked.value && overlayOpen.value) closePanel()
  else if (previewId.value !== null) focus.clearPreview()
}
onMounted(() => {
  window.addEventListener('keydown', onKey)
  if (ws.value !== null) {
    // 首帧先同步量一次：避免第一次渲染按「0 宽」判成覆盖模式，后台标签页也不依赖观察器回调
    wsWidth.value = ws.value.clientWidth
    if (typeof ResizeObserver === 'function') {
      observer = new ResizeObserver(measureWorkspace)
      observer.observe(ws.value)
    } else window.addEventListener('resize', measureWorkspace)
  }
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('resize', measureWorkspace)
  observer?.disconnect()
})

// ---------------------------------------------------------------- 底部折叠条与布局切换
const nextOpen = ref(false)
function toggleMode(): void {
  mode.value = mode.value === 'graph' ? 'cards' : 'graph'
}
const layoutLabel = computed(() => (filters.layout.value === 'hierarchical' ? '章节分区' : '力导向'))
function toggleLayout(): void {
  filters.layout.value = filters.layout.value === 'hierarchical' ? 'force' : 'hierarchical'
}
const ready = computed(() => status.value === 'ready' && graph.value !== null && !empty.value)
</script>

<template>
  <section
    class="student-graph"
    data-test="student-graph-page"
    aria-labelledby="student-graph-title"
    :aria-busy="status === 'loading' ? 'true' : 'false'"
  >
    <h2 id="student-graph-title" class="visually-hidden">课程知识图谱</h2>

    <div
      ref="ws"
      class="graph-workspace gw"
      :class="{ 'is-docked': docked, 'is-overlay': !docked, 'is-collapsed': docked && !dockedOpen, 'is-state': !ready }"
    >
      <div v-if="!ready" class="gw-state-wrap">
        <p v-if="status === 'loading'" data-test="sg-loading" role="status">正在加载已发布图谱…</p>

        <p v-else-if="status === 'not_student'" data-test="sg-not-student" role="status">
          此页面向本课程的学生，只展示已发布图谱。你在本课程是教师，请在课程页进入教师工作区。
        </p>

        <p v-else-if="status === 'unpublished'" data-test="sg-unpublished" role="status">
          课程尚未发布知识图谱，教师发布后即可浏览。
        </p>

        <div v-else-if="status === 'error'" data-test="sg-error" role="alert">
          <p>{{ error }}</p>
          <button v-if="retryable" type="button" class="gw-btn" data-test="sg-retry" @click="reload">重试</button>
        </div>

        <p v-else-if="empty" data-test="sg-empty" role="status">已发布的图谱中暂无知识点。</p>
      </div>

      <template v-else>
        <!-- 左面板：未选中显示课程说明，选中后原位切换为知识点详情（保留可折叠的「下一步推荐」） -->
        <GraphSidePanel
          ref="panel"
          :open="panelVisible"
          :docked="docked"
          :detail="selected !== null"
          :label="`知识点详情：${selectedName}`"
          :content-key="selected ?? 'course'"
          @close="closePanel"
          @back="focus.open(null)"
        >
          <template v-if="selected === null">
            <h2 class="gw-title" data-focus-start tabindex="-1">{{ courseName || '课程知识图谱' }}</h2>
            <p class="gw-muted">
              <span v-if="graphVersion !== null" data-test="sg-version">已发布版本 v{{ graphVersion }}</span>
              <template v-if="summary"> · {{ summary.totalNodes }} 个知识点，{{ summary.totalEdges }} 条关系</template>
            </p>
            <p v-if="courseId" class="gw-muted">
              <RouterLink class="gw-link" :to="{ name: COURSE_ROUTE, params: { cid: courseId } }">返回课程页面</RouterLink>
            </p>
            <section v-if="learningEnabled && learningStatus === 'ready'" aria-labelledby="gw-progress">
              <h3 id="gw-progress" class="gw-h3">我的进度</h3>
              <div class="gw-bar" role="img" :aria-label="`已掌握 ${progress.done} 个，共 ${progress.total} 个`"><i :style="{ width: `${progress.percent}%` }" /></div>
              <p class="gw-muted">已掌握 {{ progress.done }} 个，学习中 {{ progress.learning }} 个，共 {{ progress.total }} 个</p>
            </section>
          </template>

          <!-- I06：掌握标记与下一步推荐。不可写（未发布/非学生/加载失败）时不给任何可点击入口 -->
          <div v-if="learningEnabled" class="student-graph__learning" data-test="sg-learning">
            <p v-if="learningStatus === 'not_student'" data-test="sg-learning-forbidden" role="alert">
              你在本课程是教师，掌握标记与下一步推荐是学生行为，请在课程页进入教师工作区。
            </p>
            <p v-else-if="learningStatus === 'unpublished'" data-test="sg-learning-unpublished" role="status">
              课程尚未发布知识图谱，暂时无法记录学习进度。
            </p>
            <div v-else-if="learningStatus === 'error'" data-test="sg-learning-error" role="alert">
              <p>{{ learningError }}</p>
              <button v-if="learningRetryable" type="button" class="gw-btn gw-btn--ghost" data-test="sg-learning-retry" @click="reloadLearning">重试</button>
            </div>

            <template v-else-if="learningStatus === 'ready'">
              <p v-if="learningNotice !== null" class="gw-note" :class="learningNotice.tone === 'error' ? 'gw-note--danger' : 'gw-note--ok'" data-test="sg-learning-notice" :data-tone="learningNotice.tone">
                {{ learningNotice.text }}
              </p>

              <!-- 选中后推荐收成一条可折叠的摘要：折叠时显示第一项，保持「标记 → 推荐刷新」的流程 -->
              <button
                v-if="selected !== null"
                type="button"
                class="gw-next__head"
                data-test="gw-next-toggle"
                :aria-expanded="nextOpen"
                @click="nextOpen = !nextOpen"
              >
                <span class="gw-next__title">下一步推荐</span>
                <span v-if="!nextOpen && recommendations[0]" class="gw-next__peek">1. {{ recommendations[0].name }}</span>
                <AppIcon :name="nextOpen ? 'chevronDown' : 'chevron'" />
              </button>
              <Recommendations
                v-show="selected === null || nextOpen"
                :state="recommendState"
                :items="recommendations"
                :total-eligible="totalEligible"
                :version="graphVersion"
                :loading="recommendLoading"
                :error="recommendError"
                :selected-id="selected"
                :narrative="learningPath?.narrative ?? null"
                :narrative-ids="learningPath?.narrativeIds ?? null"
                @select="focus.open"
                @locate="onUnlockLocate"
                @retry="refreshRecommend"
              />

              <section v-if="selected !== null" class="student-graph__mastery" data-test="sg-mastery" aria-labelledby="sg-mastery-title">
                <h3 id="sg-mastery-title" class="gw-h3">掌握标记</h3>
                <p class="gw-muted" data-test="sg-mastery-target">
                  知识点：{{ selectedName }} · 当前：{{ MASTERY_LABELS[statusOf(selected)] }}
                </p>
                <div class="gw-seg" role="group" aria-label="掌握状态">
                  <button
                    v-for="item in masteryOptions"
                    :key="item.value"
                    type="button"
                    :data-test="`sg-mastery-${item.value}`"
                    :aria-pressed="statusOf(selected) === item.value ? 'true' : 'false'"
                    :disabled="busyKpId !== null"
                    @click="setMastery(selected, item.value)"
                  >
                    {{ item.label }}
                  </button>
                </div>
              </section>
            </template>
          </div>

          <p v-if="selected === null" class="gw-hint" data-test="sg-mastery-hint">在图中或列表中选择知识点，查看定义、标记掌握状态和原文出处。</p>
          <KnowledgeDetail
            v-if="selected !== null"
            :kp-id="selected"
            @select-knowledge-point="focus.open"
            @close="focus.open(null)"
            @course-forbidden="leaveForbidden"
          />
          <!-- 详情态下版本号仍然可见（概览态在课程标题下） -->
          <p v-if="selected !== null && graphVersion !== null" class="gw-hint" data-test="sg-version">已发布版本 v{{ graphVersion }}</p>
        </GraphSidePanel>

        <div v-if="!docked && overlayOpen" class="gw-scrim" aria-hidden="true" @click="closePanel" />

        <!-- 画布区 -->
        <div class="gw-stage">
          <div class="gw-tl">
            <div class="gw-tl__row">
              <button v-if="!panelVisible" ref="panelToggle" type="button" class="gw-tool" aria-label="显示说明面板" data-test="gw-panel-open" @click="openPanel">
                <AppIcon name="panel" />
              </button>
              <GraphOverlay as="form" class="gw-search" role="search" @submit.prevent="onLocate">
                <AppIcon name="search" :size="16" />
                <input
                  type="search"
                  aria-label="搜索知识点"
                  placeholder="搜索知识点，回车定位"
                  autocomplete="off"
                  :value="filters.state.value.query"
                  @input="onQuery"
                />
              </GraphOverlay>
              <ChapterMenu :chapters="chapterItems" :current-id="chapterId" :disabled="mode !== 'graph'" @jump="jumpChapter" />
            </div>
            <GraphOverlay v-if="searchNotice" as="p" class="gw-notice" data-test="sg-search-notice" role="status">{{ searchNotice }}</GraphOverlay>
            <GraphOverlay v-if="linkNotice" as="p" class="gw-notice" data-test="sg-link-notice" role="status">{{ linkNotice }}</GraphOverlay>
            <GraphOverlay v-if="activeChapter" as="p" class="gw-chip-on" data-test="gw-chapter-chip" role="status">
              已定位：{{ activeChapter.title }}
              <button type="button" class="gw-chip-on__x" aria-label="取消章节高亮" @click="clearChapter"><AppIcon name="close" :size="14" /></button>
            </GraphOverlay>
            <LocalViewBar
              v-if="localView.view.value"
              :name="localName"
              :hidden-count="hiddenByLocal"
              :hops="localView.view.value.hops"
              @set-hops="localView.setHops"
              @restore="localView.clear"
            />
          </div>

          <GraphOverlay class="gw-tr" role="toolbar" aria-label="画布工具">
            <button type="button" class="gw-tool" aria-label="图例与筛选" :aria-pressed="legendOpen" :disabled="mode !== 'graph'" @click="setLegendOpen(!legendOpen)">
              <AppIcon name="filter" />
            </button>
            <button type="button" class="gw-tool" :aria-label="`切换布局，当前：${layoutLabel}`" :disabled="mode !== 'graph'" data-test="gw-layout-toggle" @click="toggleLayout">
              <AppIcon name="overview" />
            </button>
            <div class="gw-tr__sep" aria-hidden="true" />
            <div role="group" aria-label="视图切换" class="gw-tr__modes">
              <button type="button" class="gw-tool" aria-label="图谱视图" data-test="sg-mode-graph" :aria-pressed="mode === 'graph' ? 'true' : 'false'" @click="mode = 'graph'">
                <AppIcon name="graph" />
              </button>
              <button type="button" class="gw-tool" aria-label="卡片视图" data-test="sg-mode-cards" :aria-pressed="mode === 'cards' ? 'true' : 'false'" @click="mode = 'cards'">
                <AppIcon name="list" />
              </button>
            </div>
          </GraphOverlay>

          <!-- 单击节点后的轻量预览：不打开侧栏；再次单击该节点或点「查看详情」才打开 -->
          <GraphPreviewCard
            v-if="preview && mode === 'graph'"
            :name="preview.name"
            :type="preview.type"
            :chapter="preview.chapter"
            :mastery="preview.mastery"
            :mastery-text="preview.masteryText"
            :prerequisites="preview.prerequisites"
            :unlocks="preview.unlocks"
            :local-active="localView.view.value?.id === preview.id"
            @close="focus.clearPreview"
            @open="focus.open(preview.id)"
            @toggle-local="localView.toggle(preview.id)"
          />

          <div v-if="mode === 'graph'" class="student-graph__canvas" data-test="sg-graph">
            <GraphCanvas
              ref="canvas"
              enhanced
              :graph="canvasGraph"
              :layout="filters.layout.value"
              :positions="positions"
              :scope="chapterId === null ? null : chapterKpIds"
              @node-click="onCanvasNode"
              @blank-click="focus.clearPreview"
            />
          </div>
          <div v-else class="gw-list" aria-label="知识点列表">
            <p class="gw-hint">列表与图谱使用同一组筛选和选中状态，键盘可逐项访问。</p>
            <KnowledgeCards :cards="cards" :selected-id="selected" @select="focus.open" />
          </div>

          <!-- 底部折叠条（Bloom 的 Card list）：显示数量，展开即列表视图，是画布的键盘等价路径 -->
          <GraphOverlay class="gw-count" role="group" aria-label="知识点概览">
            <span>显示 <b>{{ canvasGraph?.nodes.length ?? 0 }}</b> / {{ summary?.totalNodes ?? 0 }}</span>
            <span class="gw-count__sel">已选 {{ highlightId === null ? 0 : 1 }}</span>
            <button type="button" class="gw-count__btn" data-test="sg-count-toggle" :aria-expanded="mode === 'cards'" @click="toggleMode">
              {{ mode === 'cards' ? '收起列表' : '展开列表' }}<AppIcon :name="mode === 'cards' ? 'chevronDown' : 'expand'" :size="16" />
            </button>
          </GraphOverlay>

          <GraphLegend
            v-if="mode === 'graph'"
            :open="legendOpen"
            :hidden-relations="hiddenRelations"
            :hidden-types="hiddenTypes"
            :relation-counts="relationCounts"
            :type-counts="typeCounts"
            @update:open="setLegendOpen"
            @toggle-relation="filters.toggleRelationType"
            @toggle-type="toggleType"
            @restore="restoreAllFilters"
          />
        </div>
      </template>
    </div>
  </section>
</template>

<style scoped>
.student-graph {
  display: grid;
  min-height: 0;
  height: 100%;
}
.student-graph__learning {
  display: grid;
  gap: 12px;
}
.student-graph__mastery {
  display: grid;
  gap: 8px;
}
/* 画布填满工作区（浮层绝对定位在它上面） */
.student-graph__canvas {
  position: absolute;
  inset: 0;
}
.student-graph__canvas :deep(.graph-canvas) {
  position: absolute;
  inset: 0;
}
</style>
```

- [ ] **Step 5: 运行，确认通过；再跑全量前端用例**

Run: `npm --prefix src/frontend run test -- --run student-graph-workbench h11 i06 l13 l14 && npm --prefix src/frontend run type-check`
Expected: 全部通过；type-check 退出码 0

Run: `npm --prefix src/frontend run test -- --run`
Expected: 全量通过（实施本任务及之前各任务后，预期总数为 54 个文件 / 1117 条；加上 Task 16 的外壳用例后为 55 个文件 / 1122 条）

- [ ] **Step 6: 提交（仅在用户授权后）**

```bash
git add src/frontend/src/views/StudentGraphView.vue src/frontend/src/composables/useLearning.ts tests/frontend/student-graph-workbench.test.ts tests/frontend/h11.test.ts tests/frontend/i06.test.ts tests/frontend/l13-kp-link.test.ts tests/frontend/l14.test.ts tests/e2e/personal.spec.ts
git commit -m "feat(frontend): student graph workbench (preview/detail, chapter jump, legend filters, local view, left panel)"
```

---

### Task 16: 图谱页的暗色外壳（顶栏 + 图标栏 + 导航抽屉）

**Files:**
- Create: `src/frontend/src/components/AppTopbar.vue`
- Modify（整体替换）: `src/frontend/src/App.vue`
- Test: `tests/frontend/app-graph-shell.test.ts`

**Interfaces:**
- Consumes: `AppIcon`（Task 11）；`.app--graph`、`.app-topbar`、`.app-rail`、`.app-drawer` 等样式（Task 14 的 `graph-workspace.css`，由 `App.vue` 在 `styles.css` 之后引入，连同 `tokens.css`）。
- Produces：只有**学生图谱路由**用暗色外壳（`graphShell = withSidebar && route.name === STUDENT_GRAPH_ROUTE`），其他页面沿用左侧栏（推广前保持原样）。`AppTopbar` props `{ crumbs: Crumb[]; user: string; showMenu: boolean }`，emits `menu`、`signOut`；保留 `data-test="app-user"` / `app-sign-out`（图谱页没有旧侧栏，这两个钩子挪到顶栏）。<1024px 没有图标栏，顶栏出现打开导航抽屉的按钮（`data-test="app-menu"`），抽屉 `role="dialog"`，Esc 关闭并把焦点还给按钮。

- [ ] **Step 1: 写测试**

`tests/frontend/app-graph-shell.test.ts`：

```ts
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'
import { createMemoryHistory } from 'vue-router'
import App from '../../src/frontend/src/App.vue'
import { COURSES_API_KEY } from '../../src/frontend/src/api/courses'
import { createAppRouter, ROOT_ROUTE } from '../../src/frontend/src/router/index.ts'
import { useSessionStore } from '../../src/frontend/src/stores/session'

const Page = (text: string) => defineComponent({ render: () => h('p', text) })

let pinia: Pinia
beforeEach(() => {
  sessionStorage.clear()
  pinia = createPinia()
  setActivePinia(pinia)
})
afterEach(() => {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1024 })
})

async function mountAt(path: string, width: number) {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: width })
  const session = useSessionStore(pinia)
  session.signIn({ access_token: 'tok', token_type: 'bearer', expires_in: 3600, user: { id: 'u1', username: 'li_xiaoming', role: 'student' } })
  const router = createAppRouter({
    history: createMemoryHistory(),
    getAccountRole: () => session.role,
    coursesComponent: Page('课程'),
    studentGraphComponent: Page('图谱页'),
  })
  await router.push(path)
  await router.isReady()
  // 课程内角色决定导航里有没有「知识图谱与学习路径」（L15）：读到 my_role = student 后才出现
  const courses = {
    list: async () => [],
    create: async () => {
      throw new Error('不应创建课程')
    },
    get: async (cid: string) => ({ id: cid, name: '数据结构', status: 'published', my_role: 'student', published_version: 1, created_at: '2026-09-01T00:00:00Z' }),
  }
  const wrapper = mount(App, { attachTo: document.body, global: { plugins: [pinia, router], provide: { [COURSES_API_KEY as symbol]: courses } } })
  await flushPromises()
  return { wrapper, router, session }
}

describe('图谱页的暗色外壳（仅学生图谱页）', () => {
  it('图谱页：顶栏（面包屑、用户、退出）+ 64px 图标栏，没有旧侧栏；当前页是 aria-current 的最后一项', async () => {
    const { wrapper } = await mountAt('/courses/c1/graph', 1440)
    expect(wrapper.get('.app').classes()).toContain('app--graph')
    expect(wrapper.find('.app-sidebar').exists()).toBe(false)
    const crumb = wrapper.get('nav[aria-label="当前位置"]')
    expect(crumb.text()).toContain('我的课程')
    expect(crumb.get('[aria-current="page"]').text()).toBe('知识图谱')
    expect(wrapper.get('[data-test="app-user"]').text()).toContain('li_xiaoming')
    const rail = wrapper.get('nav.app-rail')
    expect(rail.findAll('a').length).toBeGreaterThan(0)
    expect(rail.get('[aria-current="page"]').attributes('title')).toBe('知识图谱与学习路径')
    wrapper.unmount()
  })

  it('图标栏可展开显示名称，展开按钮有可访问名称与状态', async () => {
    const { wrapper } = await mountAt('/courses/c1/graph', 1440)
    const toggle = wrapper.get('.app-rail__toggle')
    expect(toggle.attributes('aria-label')).toBe('展开导航，显示名称')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    await toggle.trigger('click')
    expect(wrapper.get('.app-rail').classes()).toContain('is-expanded')
    expect(wrapper.get('.app-rail').text()).toContain('知识图谱与学习路径')
    expect(wrapper.get('.app-rail__toggle').attributes('aria-expanded')).toBe('true')
    wrapper.unmount()
  })

  it('窄屏（<1024）没有图标栏，顶栏出现打开导航抽屉的按钮；抽屉可用 Esc 关闭并把焦点还给按钮', async () => {
    const { wrapper } = await mountAt('/courses/c1/graph', 800)
    expect(wrapper.find('nav.app-rail').exists()).toBe(false)
    const menu = wrapper.get('[data-test="app-menu"]')
    await menu.trigger('click')
    await flushPromises()
    const drawer = wrapper.get('nav.app-drawer')
    expect(drawer.attributes('role')).toBe('dialog')
    expect(drawer.text()).toContain('知识图谱与学习路径')
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(wrapper.find('nav.app-drawer').exists()).toBe(false)
    expect(document.activeElement).toBe(menu.element)
    wrapper.unmount()
  })

  it('退出登录回到登录页', async () => {
    const { wrapper, router, session } = await mountAt('/courses/c1/graph', 1440)
    await wrapper.get('[data-test="app-sign-out"]').trigger('click')
    await flushPromises()
    expect(session.role).toBeNull()
    expect(router.currentRoute.value.name).toBe(ROOT_ROUTE)
    wrapper.unmount()
  })

  it('其他页面沿用左侧栏，不出现顶栏与图标栏（推广前保持原样）', async () => {
    const { wrapper } = await mountAt('/courses/c1', 1440)
    expect(wrapper.get('.app').classes()).not.toContain('app--graph')
    expect(wrapper.find('.app-sidebar').exists()).toBe(true)
    expect(wrapper.find('.app-topbar').exists()).toBe(false)
    expect(wrapper.find('nav.app-rail').exists()).toBe(false)
    wrapper.unmount()
  })
})
```

- [ ] **Step 2: 运行，确认失败**

Run: `npm --prefix src/frontend run test -- --run app-graph-shell`
Expected: FAIL（没有 `.app--graph`、顶栏与图标栏）

- [ ] **Step 3: 实现**

`src/frontend/src/components/AppTopbar.vue`：

```vue
<script setup lang="ts">
import { RouterLink, type RouteLocationRaw } from 'vue-router'
import AppIcon from './AppIcon.vue'

/**
 * 暗色外壳顶栏（规格 §5.1）：品牌、面包屑、用户与退出。图谱页专用；窄屏（<1024）多一个打开导航抽屉的按钮。
 * 面包屑最后一项是当前页（`aria-current="page"`），不是链接。
 */
export interface Crumb {
  label: string
  to?: RouteLocationRaw
}

defineProps<{ crumbs: readonly Crumb[]; user: string; showMenu: boolean }>()
const emit = defineEmits<{ menu: []; signOut: [] }>()
</script>

<template>
  <header class="app-topbar">
    <button v-if="showMenu" type="button" class="app-iconbtn" aria-label="打开导航" data-test="app-menu" @click="emit('menu')">
      <AppIcon name="menu" />
    </button>
    <span class="app-topbar__logo" aria-hidden="true">智</span>
    <nav class="app-topbar__crumb" aria-label="当前位置">
      <template v-for="(crumb, index) in crumbs" :key="index">
        <span v-if="index > 0" aria-hidden="true">/</span>
        <RouterLink v-if="crumb.to && index < crumbs.length - 1" :to="crumb.to">{{ crumb.label }}</RouterLink>
        <span v-else :aria-current="index === crumbs.length - 1 ? 'page' : undefined">{{ crumb.label }}</span>
      </template>
    </nav>
    <div class="app-topbar__user">
      <span class="app-topbar__name" data-test="app-user">{{ user }}</span>
      <button type="button" class="app-topbar__out" data-test="app-sign-out" @click="emit('signOut')">退出登录</button>
    </div>
  </header>
</template>
```

整体替换 `src/frontend/src/App.vue`（改动：引入 `AppIcon`/`AppTopbar`、两份新样式；增加 `graphShell`、`railItems`、`crumbs`、导航抽屉的状态与键盘处理；模板里图谱页渲染顶栏 + 图标栏 + 抽屉，其余页面的左侧栏不变）：

```vue
<script setup lang="ts">
import { getActivePinia } from 'pinia'
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, RouterView, routeLocationKey, routerKey, type RouteLocationRaw } from 'vue-router'
import {
  CHAT_ROUTE,
  COURSE_MEMBERS_ROUTE,
  COURSE_ROUTE,
  homeRouteFor,
  MATERIALS_ROUTE,
  NOTICE_UNAUTHENTICATED,
  NOTICE_WRONG_ROLE,
  REVIEW_ROUTE,
  ROOT_ROUTE,
  SETTINGS_ROUTE,
  STUDENT_GRAPH_ROUTE,
  TEACHER_GRAPH_ROUTE,
} from './router'
import AppIcon from './components/AppIcon.vue'
import AppTopbar, { type Crumb } from './components/AppTopbar.vue'
import { readCourseDetail } from './composables/courseDetailRequest'
import { COURSES_API_KEY } from './api/courses'
import { useCourseStore } from './stores/course'
import { MODEL_CONFIG_API_KEY } from './api/modelConfig'
import { useRuntimeStore } from './stores/runtime'
import { useSessionStore } from './stores/session'
import './styles.css'
// 图谱工作区 tokens 与组件样式（新命名空间 --ss-* / --gw-*，不改现有 --color-*）
import './styles/tokens.css'
import './styles/graph-workspace.css'

const appName = '智绘学途'
// 未安装路由时（如 B02 单独挂载外壳）只渲染标题，不报错
const route = inject(routeLocationKey, null)
const router = inject(routerKey, null)
// 未安装 Pinia 时（如 B03 只测路由守卫）不显示侧栏，外壳退回顶栏
const session = getActivePinia() ? useSessionStore() : null
const dismissedNotice = ref(false)
watch(
  () => route?.fullPath,
  () => { dismissedNotice.value = false },
)

// 提示码来自守卫写入的 query；只在与当前页面相符时显示
const notice = computed(() => {
  if (!route || dismissedNotice.value) return null
  const code = route.query.notice
  const role = route.meta.accountRole
  if (code === NOTICE_UNAUTHENTICATED && route.name === ROOT_ROUTE) {
    return '未登录：请先登录，再进入教师或学生首页。'
  }
  if (code === NOTICE_WRONG_ROLE && role === 'teacher') {
    return '当前账号类型为教师，无法进入学生首页，已返回教师首页。'
  }
  if (code === NOTICE_WRONG_ROLE && role === 'student') {
    return '当前账号类型为学生，无法进入教师首页，已返回学生首页。'
  }
  return null
})

const role = computed(() => session?.role ?? null)
// 方向 A「工作台」：登录后左侧常驻导航；未登录（登录、注册页）只留顶栏
const withSidebar = computed(() => route !== null && role.value !== null)
const onLoginPage = computed(() => route?.name === ROOT_ROUTE && role.value === null)

interface NavItem {
  label: string
  to: RouteLocationRaw
  active: boolean
}

const courseId = computed(() => {
  const cid = route?.params.cid
  return typeof cid === 'string' && cid !== '' ? cid : null
})

// L15：课程权限与账号类型分离；读取失败/未知时不猜测权限。
const courseApi = inject(COURSES_API_KEY, null)
const courseStore = getActivePinia() ? useCourseStore() : null
watch([courseId, () => session?.accessToken ?? null], async ([cid, token]) => {
  if (courseStore === null) return
  courseStore.selectCourse(token === null ? null : cid)
  if (cid === null || token === null || courseApi === null) return
  const scope = courseStore.beginRequest()
  try {
    const detail = await readCourseDetail(courseApi, cid, scope.signal)
    if (session?.accessToken === token && detail.id === cid) courseStore.setRole(scope, detail.my_role)
  } catch { /* 未知角色只提供概览，页面负责错误提示。 */ }
}, { immediate: true, flush: 'sync' })
const courseNav = computed<NavItem[]>(() => {
  const cid = courseId.value
  if (cid === null || router === null || role.value === null) return []
  const names =
    courseStore?.myRole === null || courseStore === null
      ? [[COURSE_ROUTE, '课程概览']]
      : courseStore.myRole === 'teacher'
      ? [
          [COURSE_ROUTE, '课程概览'],
          [MATERIALS_ROUTE, '教学资料'],
          [TEACHER_GRAPH_ROUTE, '图谱编辑'],
          [REVIEW_ROUTE, '审核队列'],
          [COURSE_MEMBERS_ROUTE, '成员'],
        ]
      : [
          [COURSE_ROUTE, '课程概览'],
          [STUDENT_GRAPH_ROUTE, '知识图谱与学习路径'],
          [CHAT_ROUTE, '课程问答'],
        ]
  return names
    .filter(([name]) => router.hasRoute(name))
    .map(([name, label]) => ({ label, to: { name, params: { cid } }, active: route?.name === name }))
})

const homeLink = computed<RouteLocationRaw | null>(() => (role.value === null ? null : { name: homeRouteFor(role.value) }))
const homeActive = computed(() => role.value !== null && route?.name === homeRouteFor(role.value))
const roleLabel = computed(() => (role.value === 'teacher' ? '教师' : '学生'))

// L10（ADR-080）：登录后读取一次运行模式与本人配置状态，供侧栏提示与上传/问答页的引导；
// 读取失败不阻断外壳（设置页自有错误态）。未注入接口或未装 Pinia 时（单独挂载外壳的测试）跳过。
// N03：按会话身份（登录令牌）而不是账号类型监听——同角色换号、退出重登都会立即重置；
// 旧读取被中止，即便晚到也因会话或代际不符而被丢弃。
const modelConfigApi = inject(MODEL_CONFIG_API_KEY, null)
const runtime = getActivePinia() ? useRuntimeStore() : null
let runtimeRead: AbortController | null = null
watch(
  () => session?.accessToken ?? null,
  async (key) => {
    if (runtime === null) return
    runtimeRead?.abort()
    runtimeRead = null
    runtime.startSession(key)
    if (key === null || modelConfigApi === null) return
    const controller = new AbortController()
    runtimeRead = controller
    const ticket = runtime.claim()
    try {
      runtime.commitRead(ticket, await modelConfigApi.get({ signal: controller.signal }))
    } catch {
      // 忽略：设置页会显示加载错误
    } finally {
      if (runtimeRead === controller) runtimeRead = null
    }
  },
  { immediate: true },
)
const settingsLink = computed<RouteLocationRaw | null>(() =>
  router !== null && role.value !== null && router.hasRoute(SETTINGS_ROUTE) ? { name: SETTINGS_ROUTE } : null,
)
const settingsActive = computed(() => route?.name === SETTINGS_ROUTE)

// ---------------------------------------------------------------- 图谱页的暗色外壳（UI-GRAPH-PILOT-01）：顶栏 + 64px 图标栏
// 只有学生图谱页用它；其他页面沿用左侧栏，推广到其他页面前保持原样。
const graphShell = computed(() => withSidebar.value && route?.name === STUDENT_GRAPH_ROUTE)
const NAV_ICONS: Record<string, string> = {
  我的课程: 'home',
  课程概览: 'overview',
  知识图谱与学习路径: 'graph',
  课程问答: 'chat',
  '模型 API 设置': 'key',
}
const railItems = computed(() => {
  const items: Array<{ label: string; to: RouteLocationRaw; active: boolean; icon: string }> = []
  if (homeLink.value !== null) items.push({ label: '我的课程', to: homeLink.value, active: homeActive.value, icon: 'home' })
  for (const item of courseNav.value) items.push({ ...item, icon: NAV_ICONS[item.label] ?? 'overview' })
  if (settingsLink.value !== null) items.push({ label: '模型 API 设置', to: settingsLink.value, active: settingsActive.value, icon: 'key' })
  return items
})
const crumbs = computed<Crumb[]>(() => {
  const list: Crumb[] = []
  if (homeLink.value !== null) list.push({ label: '我的课程', to: homeLink.value })
  const cid = courseId.value
  if (cid !== null && router !== null && router.hasRoute(COURSE_ROUTE)) list.push({ label: '课程', to: { name: COURSE_ROUTE, params: { cid } } })
  list.push({ label: '知识图谱' })
  return list
})
const railExpanded = ref(false)
const vw = ref(typeof window === 'undefined' ? 1280 : window.innerWidth)
const railVisible = computed(() => vw.value >= 1024)
const navDrawer = ref(false)
const drawer = ref<HTMLElement | null>(null)
function onResize(): void {
  vw.value = window.innerWidth
  if (vw.value >= 1024) navDrawer.value = false
}
function openNav(): void {
  navDrawer.value = true
  void nextTick(() => drawer.value?.querySelector<HTMLElement>('a, button')?.focus())
}
function closeNav(): void {
  navDrawer.value = false
  void nextTick(() => document.querySelector<HTMLElement>('[data-test="app-menu"]')?.focus())
}
function onNavKey(event: KeyboardEvent): void {
  if (event.key === 'Escape' && navDrawer.value) {
    event.stopPropagation()
    closeNav()
  }
}
onMounted(() => {
  window.addEventListener('resize', onResize)
  window.addEventListener('keydown', onNavKey, true)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  window.removeEventListener('keydown', onNavKey, true)
})

function signOut(): void {
  session?.signOut()
  void router?.replace({ name: ROOT_ROUTE })
}
</script>

<template>
  <div class="app" :class="{ 'app--workbench': withSidebar && !graphShell, 'app--graph': graphShell, 'app--login': onLoginPage }">
    <AppTopbar
      v-if="graphShell"
      :crumbs="crumbs"
      :user="`${session?.user?.username ?? ''} · ${roleLabel}`"
      :show-menu="!railVisible"
      @menu="openNav"
      @sign-out="signOut"
    />
    <header v-if="!withSidebar" class="app-header">
      <div class="app-header-inner">
        <span class="app-logo" aria-hidden="true">智</span>
        <h1>{{ appName }}</h1>
        <p class="app-tagline">AIGC 课程知识图谱智能构建与学习导航</p>
      </div>
    </header>
    <main class="app-main" :class="{ 'app-main--graph': graphShell }">
      <div v-if="notice" class="app-notice" role="alert">
        <span>{{ notice }}</span>
        <button type="button" class="app-notice__close" aria-label="关闭提示" @click="dismissedNotice = true">×</button>
      </div>
      <RouterView v-if="route" />
    </main>
    <!-- 侧栏在 DOM 中位于主内容之后，读屏与键盘先到页面内容；视觉上由网格放在左侧 -->
    <nav v-if="graphShell && railVisible" class="app-rail" :class="{ 'is-expanded': railExpanded }" aria-label="主导航">
      <RouterLink
        v-for="item in railItems"
        :key="item.label"
        :to="item.to"
        class="app-rail__item"
        :class="{ 'is-current': item.active }"
        :aria-current="item.active ? 'page' : undefined"
        :aria-label="railExpanded ? undefined : item.label"
        :title="item.label"
      >
        <AppIcon :name="item.icon" :size="18" />
        <span v-if="railExpanded" class="app-rail__label">{{ item.label }}</span>
      </RouterLink>
      <button
        type="button"
        class="app-rail__toggle"
        :aria-label="railExpanded ? '收起导航' : '展开导航，显示名称'"
        :aria-expanded="railExpanded"
        @click="railExpanded = !railExpanded"
      >
        <AppIcon :name="railExpanded ? 'collapse' : 'expand'" :size="18" />
        <span v-if="railExpanded" class="app-rail__label">收起导航</span>
      </button>
    </nav>
    <template v-if="graphShell && navDrawer">
      <div class="app-scrim" aria-hidden="true" @click="closeNav" />
      <nav ref="drawer" class="app-drawer" aria-label="主导航" role="dialog">
        <button type="button" class="app-iconbtn app-drawer__close" aria-label="关闭导航" @click="closeNav"><AppIcon name="close" /></button>
        <RouterLink
          v-for="item in railItems"
          :key="item.label"
          :to="item.to"
          class="app-rail__item is-wide"
          :class="{ 'is-current': item.active }"
          :aria-current="item.active ? 'page' : undefined"
          @click="closeNav"
        >
          <AppIcon :name="item.icon" :size="18" /><span class="app-rail__label">{{ item.label }}</span>
        </RouterLink>
      </nav>
    </template>
    <aside v-if="withSidebar && !graphShell" class="app-sidebar" aria-label="导航">
      <div class="app-sidebar__brand">
        <span class="app-logo" aria-hidden="true">智</span>
        <h1>{{ appName }}</h1>
      </div>
      <nav class="app-nav" aria-label="主导航">
        <RouterLink v-if="homeLink" :to="homeLink" class="app-nav__item" :class="{ 'is-active': homeActive }">
          我的课程
        </RouterLink>
        <template v-if="courseNav.length">
          <p class="app-nav__heading">当前课程</p>
          <RouterLink
            v-for="item in courseNav"
            :key="item.label"
            :to="item.to"
            class="app-nav__item"
            :class="{ 'is-active': item.active }"
            :aria-current="item.active ? 'page' : undefined"
          >
            {{ item.label }}
          </RouterLink>
        </template>
        <RouterLink
          v-if="settingsLink"
          :to="settingsLink"
          class="app-nav__item"
          :class="{ 'is-active': settingsActive }"
          :aria-current="settingsActive ? 'page' : undefined"
          data-test="nav-model-settings"
        >
          模型 API 设置
          <span v-if="runtime?.needsConfig" class="app-nav__badge" data-test="nav-model-settings-pending">未配置</span>
        </RouterLink>
      </nav>
      <p v-if="runtime?.isDemo" class="app-mode" data-test="mode-demo" role="status">演示模式 · 使用内置演示模型，不调用个人 API</p>
      <div class="app-sidebar__user">
        <span data-test="app-user">{{ session?.user?.username }} · {{ roleLabel }}</span>
        <button type="button" data-variant="secondary" data-test="app-sign-out" @click="signOut">退出登录</button>
      </div>
    </aside>
  </div>
</template>
```

- [ ] **Step 4: 运行，确认通过；再跑全量与构建**

Run: `npm --prefix src/frontend run test -- --run app-graph-shell && npm --prefix src/frontend run type-check`
Expected: 5 passed；type-check 退出码 0

Run: `npm --prefix src/frontend run test -- --run && npm --prefix src/frontend run build`
Expected: 全量通过（55 个文件 / 1122 条）；build 退出码 0（G6 所在的 chunk 超过 500 kB 的提示是既有现象，不是失败）

- [ ] **Step 5: 提交（仅在用户授权后）**

```bash
git add src/frontend/src/components/AppTopbar.vue src/frontend/src/App.vue tests/frontend/app-graph-shell.test.ts
git commit -m "feat(frontend): dark app shell (topbar, icon rail, nav drawer) for the student graph route"
```

---

## 第五阶段：验收、文档与收尾

### Task 17: 浏览器验收、文档、清理与回滚预案

**Files:**
- Modify: `docs/tasks.md`（UI-GRAPH-PILOT-01 的状态与验收证据）
- Modify: `docs/superpowers/specs/2026-10-06-graph-workbench-design.md`（状态；按上面「实施中确认的与规格不一致」表更新 §6、§7、§10、§11、§15）
- Modify: `docs/decisions.md`（追加 ADR-091）
- Modify: `docs/handoffs/claude-ui-graph-pilot-01.md`（追加实施轮次：交付物、命令与结果、未验证项、风险、下一步）
- Delete: `src/frontend/preview/`（隔离预览，含 `prod.html` / `prod-main.ts` 验收页；确认验收完成后再删）
- 不新增依赖、不改 `src/contracts/`、后端、数据库。

**Interfaces:**
- Consumes: Task 1–16 的全部交付物。
- Produces: 带证据的验收记录；工作区只剩正式实现、规格、计划与交接。

- [ ] **Step 1: 全量自动化验证**

Run（每条的退出码与摘要如实记入交接）：

```bash
npm --prefix src/frontend run type-check
npm --prefix src/frontend run test -- --run
npm --prefix src/frontend run build
./scripts/verify.sh
./scripts/verify.sh full
```

Expected: type-check 0；55 个文件 / 1122 条通过；build 0；`verify.sh` 与 `full` 退出码 0。`integration` 与端到端（`tests/e2e`，需要后端与数据）在有环境时运行：`./scripts/verify.sh integration`；端到端失败时先看是不是下面两类**设计变化**：① 直接点画布节点后期望立即出现详情（现在是预览，要再点一次）；② 文案「未开始」（现在是「未学习」）。缺环境、失败、未执行的项如实分列，不写「通过」。

- [ ] **Step 2: 隔离页真实 G6 验收（合成数据，不连后端）**

`src/frontend/preview/prod.html` 加载 `prod-main.ts`：生产的 `App` + `StudentGraphView` 挂在 `preview/data.ts` 的合成课程上（接口是内存假实现，掌握标记会真实改变内存状态并有 350ms 延迟）。

```bash
npm --prefix src/frontend exec vite -- --port 5199 --strictPort
```

然后依次打开：`http://localhost:5199/preview/prod.html?size=100`、`?size=30`、`?size=100&profile=pdf`（无先修关系、孤立节点多）。**内置浏览器的已知现象**：窗格宽度变化会清掉自定义视口；后台标签页不派发 `ResizeObserver`（重新加载页面即可）；模拟视口大于窗格时截图会被缩小——先 `resize_window` 再立刻截图。

逐项检查并记录（宽度 1440×900、1280×800、768×1024、390×844 各一遍）：

| 区域 | 检查项 |
| --- | --- |
| 版面 | 无整页横向溢出；≥1280 并置、960 以下覆盖抽屉（按**工作区容器宽度**）；预览卡、图例、底部折叠条、小地图、右侧工具、搜索栏两两不重叠；<1024 无图标栏、顶栏有菜单按钮、小地图默认收起 |
| 点击语义 | 单击节点 → 外环 + 邻居强调 + 关系名 + 预览卡，侧栏不变、镜头不动；再次单击 / 「查看详情」→ 详情；详情已开时单击另一节点只预览；点空白 / Esc / ✕ 取消预览（覆盖模式 Esc 先关抽屉） |
| 淡化 | 悬停：相邻清楚、其余退成近底色小点并隐去标签，移开 60ms 恢复，触屏无；预览：标准淡化（填充 `#ECEEF2`、边框 `#7F8695`、标签 `#545967` 保留），**没有整体 opacity**；选中外环与先修边同色，靠形状区分，目测复核 |
| 大图 | 96 节点「适应画布」：标签不重叠、节点 ≥14px、线 ≥1px、箭头 ≥6px；标签避开工具栏/图例/小地图；预览/选中的节点标签强制显示；章节跳转 → 整章进视口 + 外框 + 其他章节淡化 + 「已定位」标签 + 图例自动收起，取消后恢复；只看相邻 1/2 跳 + 提示条 + 恢复；图例计数与筛选、「已隐藏」「恢复全部」 |
| 布局 | 章节分区：每章可在一屏内看全；跨章边未强调时 1px、强调时恢复；先修方向向下；`pdf` 档孤立节点不成长条 |
| 业务 | 标记掌握状态：保存中全部禁用并显示「保存中…」→ 服务端确认后才显示成功；推荐刷新；卡片视图与图谱共用筛选/选中；`?kp=` 链接直达详情；`not_covered` 与服务错误在问答页保持分开（本任务未改） |
| 减少动效 | 系统设置打开「减少动态效果」后：镜头动画关闭、抽屉无位移、骨架不循环 |

- [ ] **Step 3: 对比度与键盘（以页面实际渲染色为准，不只看 CSS 变量）**

用浏览器开发者工具或脚本读取**渲染后**的颜色，分别检查暗色普通页、浅色图谱页、tooltip/菜单浮层，覆盖默认、hover、选中、搜索命中、淡化状态：文字 ≥4.5:1、必要图形与控件边界 ≥3:1（悬停强淡化是规格记录的唯一例外）。键盘：Tab 顺序（顶栏 → 图标栏 → 面板 → 搜索 → 章节 → 右侧工具 → 底部条 → 图例）、焦点环 2px（暗底 `#B1ACFF`、浅底 `#5145CD`）、抽屉打开后焦点进面板、关闭后回到开关、200% 文字缩放下全部内容可达。**G6 画布内像素色**需截图采样后计算（预览阶段未做）。把实测数值写进交接，不达标的列为缺陷。

- [ ] **Step 4: 修改前后截图（同一实例）**

在用户指定的真实实例上（登录凭据问题尚未解决，**不要**猜测或重置账号）对比 1440×900、1280×800、768、390 宽度的：总览、章节聚焦、局部邻域、节点详情，修改前用 `main` 构建、修改后用本分支。没有可用实例时，如实写「未做」，并以 Step 2 的隔离页截图作为替代证据（注明数据是合成的）。截图不入库，交接里记录场景、尺寸与结论。

- [ ] **Step 5: 更新文档**

`docs/decisions.md` 末尾追加：

```markdown
## ADR-091：学生图谱页升级为图谱工作台（UI-GRAPH-PILOT-01，2026-10-07）

- 背景：现有学生图谱页信息层级松散、约 100 个节点时标签不可读、点击即打开侧栏打断浏览；用户确认方向为 Linear 式暗色外壳 + Kumu 式浅色画布，样板页先行。
- 决定：① 视觉用 `--ss-*`（外壳）/`--gw-*`（图谱工作区）两套 tokens，G6 字面量集中在 `graph/theme.ts` 并由测试对齐；② 单击节点只预览，再次单击才打开详情，搜索回车 = 预览；③ 悬停强淡化（瞬时）、预览/选中标准淡化（持久），均不使用整体透明度；④ 章节分区 + 紧凑间距的预先布局，边弱化跨章线；⑤ 语义缩放（标签放大 + 节点/线/箭头屏幕下限）与带障碍物的标签排布，只有预览/选中强制显示标签；⑥ 小地图、只看相邻、带计数的图例筛选、章节跳转与整章范围适应；⑦ 可读缩放下限由 0.7 调到 0.9；⑧ 「未开始」文案改为「未学习」。
- 后果：契约、接口、数据库均无变更；`h05/i06/l13/l14` 中样式、状态名、缩放常量与点击语义的断言随之更新；教师页沿用旧画布行为（`enhanced` 关闭），第二批再做；暗色外壳只用于学生图谱路由；回滚见任务 17。
```

`docs/tasks.md`：把 UI-GRAPH-PILOT-01 的状态改为 `DONE`（或按实际：`IN_PROGRESS`，列出未验证项），验收证据写 Step 1–4 的真实命令、退出码与摘要；`docs/handoffs/claude-ui-graph-pilot-01.md` 追加本轮：交付物清单、接口/数据变更（无）、与规格的差异表、风险（G6 像素色未采样、`process-parallel-edges` 与 `cubic-vertical` 的相互作用需在真实数据上实测、`EXAMPLE_OF` 方向未确认、真实课程数据上的布局未验证）、下一步（教师页、目录页签、`KnowledgeDetail` 插槽、其余页面推广）。规格文件头部状态改为「已实施，差异见 §…」。

- [ ] **Step 6: 删除隔离预览并复核**

确认验收完成、证据已写入交接后，删除 `src/frontend/preview/` 目录（它是未跟踪目录，不进构建；先 `git status --short` 确认里面只有预览文件）。然后：

```bash
git status --short
npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run && npm --prefix src/frontend run build
```

Expected: `git status` 只剩本任务的正式改动；三条命令退出码 0（预览目录不在 `tsconfig` 的 `src/**` 里，也不是构建入口，删除不影响它们）。

- [ ] **Step 7: 提交（仅在用户授权后）**

```bash
git add docs/tasks.md docs/decisions.md docs/handoffs/claude-ui-graph-pilot-01.md docs/superpowers/specs/2026-10-06-graph-workbench-design.md docs/superpowers/plans/2026-10-07-graph-workbench-pilot.md
git commit -m "docs: record graph workbench pilot acceptance, ADR-091 and handoff"
```

**回滚预案**：任务提交按 tokens → 画布引擎（Task 1–10）→ 页面层（11–15）→ 外壳（16）→ 文档（17）分批，可逐批 `git revert`（不用整仓重置）。`styles/tokens.css` 与 `graph-workspace.css` 是新增命名空间，撤销即恢复原样；教师页始终走 `enhanced = false`，不受影响；不涉及迁移、依赖、契约，因此没有数据回滚；删除隔离预览前先确认交接与规格已记录全部证据（预览目录删除后只能从历史里找回行为参考）。不通过删除或放宽测试掩盖失败。

---

## 自检（对照规格）

- **规格覆盖**：§3 tokens 与主题字面量 → Task 1、7、8、14；§3.4 画布元素与屏幕下限 → Task 2、7、8；§3.4a 悬停/预览淡化 → Task 6、9、15；§4 标签分级、小地图、只看相邻、图例筛选、章节分区 → Task 3、9–15；§4.1 章节布局 → Task 5、13；§4.2 章节聚焦（整章适应、外框、淡化、跨章线、图例收起） → Task 4、9、15；§5 版面与响应式 → Task 14、15、16；§6 左面板 → Task 14、15；§7 交互规则 → Task 13、15；§8 状态与可访问性 → Task 14–17；§9 动效 → Task 8（easing/时长在 CSS）、14、16、`useReducedMotion`（Task 11）；§10 与现有实现的差异 → Task 8–16；§11 文件范围 → 文件结构；§12 实施顺序 → 本计划任务顺序；§13 验收 → Task 17；§16 回滚 → Task 17。已知缺口见「实施中确认的与规格不一致」表（#1–#12）与 Task 17 的「未验证」清单。
- **占位符扫描**：全文没有 TBD/TODO/「类似 Task N」；所有代码步骤都带完整代码或逐字嵌入的最终文件。
- **类型一致性**：`Positions`（Task 5）在 Task 10、12、13 同名同形；`EnhanceOptions`/`Enhancer`（Task 9）在 Task 10 使用的方法名一致（`decorate`、`attach`、`afterRender`、`setScope`、`fitTo`、`zoomBy`、`ensureVisible`、`relayoutLabels`、`leaveHover`、`minimapColor`、`detach`）；`GraphLifecycle` 的新方法与 `GraphCanvas`（Task 12）调用一致；`MASTERY_TEXT`（Task 7）与 `MASTERY_LABELS`（Task 15）由测试对齐；状态名清单（Task 8）与 `focusStates.ts`（Task 6）、`graph-options.test.ts` 一致。
