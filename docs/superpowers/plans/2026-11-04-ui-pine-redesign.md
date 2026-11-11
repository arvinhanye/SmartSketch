# UI-PINE-01：青松明黄界面改版实施计划（2026-11-04）

## 目标与依据

- 目标：按用户确认的设计预览 v3（https://claude.ai/artifact/Vg9yqHzdfAgEVvu1bAKnRV）重做前端配色与登录、课程进入、模型 API、图谱页外围，为 11 月 21 日决赛答辩服务。
- 已决（用户，2026-11-02～11-04）：配色方案 B「青松明黄」；图谱本身的展示样式不变（浅色画布、原节点与关系配色、靛紫强调）；不加白色转角框；软件内不放介绍性长文案；新 Logo 替换「智」字，侧栏不放 Logo；登录页仿分栏封面；学生问答保持各自配置模型；入课改邀请码（后端另立任务）。

## 约束

- 不改业务流程、接口契约与数据模型（邀请码除外，见 P6）。
- 既有 `data-test` 钩子全部保留；可访问性（键盘、焦点、对比度 ≥4.5:1、减少动效）不倒退。
- `--gw-*` 与 `graph/theme.ts` 的图谱色值保持一致不动（`tests/frontend/graph-theme.test.ts`）；界面新色用独立的 `--ui-*`，外壳沿用 `--ss-*` 但换值。
- 只改样式与结构时，既有测试断言仅在「样式/结构/文案随设计变化」处更新并写明原因。

## 色板（--ui-*）

| 用途 | 值 |
| --- | --- |
| 页面底 | `#EDF2EF` |
| 面板 | `#FFFFFF`，边框 `#D3DDD8`，弱边 `#E2EAE6`，浅底 `#F6F9F7` |
| 深松（顶栏、导航） | `#0F3D36` |
| 青松（主按钮、链接） | `#0E6B5C`，按下 `#0B5A4D`，浅底 `#E2F1EC` |
| 明黄（推荐、当前导航） | `#F5B82E`，浅底 `#FFF6DB` |
| 正文 / 次要 / 三级 | `#15211E` / `#50605B` / `#6B7A75` |

## 阶段

| 阶段 | 内容 | 主要文件 |
| --- | --- | --- |
| P1 | tokens：新增 `--ui-*`，`--ss-*` 换成深松外壳；新增 `BrandMark` Logo 组件 | `styles/tokens.css`、`components/BrandMark.vue` |
| P2 | 外壳：顶栏去 Logo、演示模式改为顶栏标签、导航当前项明黄、主区浅底 | `App.vue`、`AppTopbar.vue`、`styles/graph-workspace.css` |
| P3 | 登录 / 注册：分栏封面（左表单、右品牌几何面板），文案精简 | `LoginLayout.vue`、`LoginView.vue`、`RegisterView.vue` |
| P4 | 图谱页外围：白色浮层、工具轨合并（画布工具 + 地图与缩放）、推荐项明黄高亮；图谱画布不动 | `StudentGraphView.vue`、`GraphCanvas.vue`、`styles/graph-workspace.css` |
| P5 | 课程进入页「继续学习」主卡、课程卡进度；模型 API 三步式（服务商 → Key → 模型，高级选项折叠） | `CoursesView.vue`、`ModelSettingsView.vue`、`styles/ui.css` |
| P6 | 邀请码（后端 + 契约 + 前端加入框）：先写规格与 ADR，另起任务 | 待定 |

## 验证

每阶段：`npm --prefix src/frontend run type-check`、受影响的 vitest 用例；收尾：前端全量 vitest、`build`、`./scripts/verify.sh`，演示环境下 1440×900 与 1280×720 截图走查登录、课程、图谱、问答、设置。

## 回滚

所有改动在分支 `claude/ui-pine-redesign`；回滚即不合并或还原该分支提交。tokens 与组件改动无数据迁移。
