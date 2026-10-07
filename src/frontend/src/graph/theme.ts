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

/** 图谱画布与 DOM 共用的字体栈（量文字宽度也用它，保证排布估算与渲染一致） */
export const GRAPH_FONT = "'PingFang SC','Hiragino Sans GB','Microsoft YaHei',system-ui,sans-serif"
