# 交接：UI-GRAPH-PILOT-01 图谱工作台样板页 → Codex 执行

- 任务：`UI-GRAPH-PILOT-01`（`docs/tasks.md` 顶部认领段）。发起：Claude（前端）。接手：Codex。
- 状态：设计已确认、规格已写、实施计划已写；**生产代码未改**（写计划时临时落地验证后已还原）。等待 Codex 按计划执行。
- 目标 worktree：`/Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-frontend-init-0d2af9`，分支 `claude/smartsketch-frontend-init-0d2af9`，base/head `bdb89c4`（工作区有未提交文件，见下）。
- 本文件由 Claude 写入；Codex 的完成交接请另写 `docs/handoffs/codex-ui-graph-pilot-01.md`，审查报告放 `docs/reviews/`。

## 必读（按顺序）

1. `AGENTS.md`、`CLAUDE.md`、`.claude/rules/frontend.md`、`.claude/rules/testing.md`、`docs/tasks.md`（UI-GRAPH-PILOT-01 段）。
2. 设计规格：`docs/superpowers/specs/2026-10-06-graph-workbench-design.md`。
3. **实施计划：`docs/superpowers/plans/2026-10-07-graph-workbench-pilot.md`**（17 个任务；每个任务有文件清单、接口签名、先写失败测试 → 实现 → 验证命令；最终代码与测试已逐字嵌入）。开头的「计划验证状态与实施中确认的差异」表必读。
4. 历史与踩坑：`docs/handoffs/claude-ui-graph-pilot-01.md`（第 1–9 轮）。
5. 行为参考实现（隔离预览，最后删除）：`src/frontend/preview/`；其中 `prod.html` + `prod-main.ts` 可把生产的 `App` + `StudentGraphView` 挂在合成数据上做真实 G6 目测。

## 工作区现状

- 已跟踪文件：仅 `docs/tasks.md` 有改动（认领与计划状态）。
- 未跟踪：`docs/handoffs/claude-ui-graph-pilot-01*.md`、`docs/superpowers/specs/2026-10-06-graph-workbench-design.md`、`docs/superpowers/plans/2026-10-07-graph-workbench-pilot.md`、`src/frontend/preview/`。**在别的 worktree 工作时要把这些文件一并带过去**，否则读不到规格与计划。
- 基线（已重新验证）：`npm --prefix src/frontend run type-check` 0；`npm --prefix src/frontend run test -- --run` 38 个文件 / 934 条通过；`./scripts/verify.sh` 基础档 0。

## 已确认的决定（不要重新讨论）

- 风格：Linear 式暗色外壳（`--ss-*`）+ Kumu 式浅色图谱画布（`--gw-*`）；只做学生图谱页，教师页走 `enhanced = false` 保持旧行为。
- 单击节点 = 预览（侧栏不变、镜头不动）；再次单击同一节点或「查看详情」才开详情；搜索回车 = 预览；列表/推荐/关联知识/问答链接 `?kp=` 是显式选择，直接开详情。
- 淡化：悬停强淡化（瞬时）、预览/选中标准淡化（持久）；**不用整体 opacity**。只有预览/选中的节点强制显示标签（布尔判断，不用分数阈值）。
- 采用章节分区 + 紧凑间距布局；章节跳转 = 整章范围适应 + 外框 + 其他章节淡化 + 跨章线弱化。
- P0：标签分级、小地图、只看相邻（1/2 跳）、带计数的图例筛选。可读缩放 0.7 → 0.9（**待用户在真实实例上目测确认**）。
- 左面板选中后保留可折叠的「下一步推荐」摘要；选中外环与先修边同色 `#5145CD`，靠形状区分。

## 约束

- 不新增依赖、不引入 UI/图标库；不改 `src/contracts/`、后端、数据库；不碰账号、真实模型调用；不打印口令/令牌。
- 业务不变：服务端确认前不显示掌握成功、推荐 `reason` 取自服务端、`not_covered` 与服务错误分开、来源可定位、课程隔离。
- 保留既有 `data-test` 钩子；推荐编号「1. 名称」是有意设计（L14），不是文本污染。
- 先写失败测试再实现；既有断言只在计划列出的几处更新，**不放宽、不删除测试**；不用破坏性 git 命令。
- **不 commit / push / 开 PR，除非用户明确指示**（计划里的提交步骤仅在授权后执行）。
- 登录凭据问题未解决：不要猜测或重置账号。端到端与「真实实例前后截图」需要用户提供环境；没有就如实写「未做」。

## 与规格不一致、已写进计划的 12 处

见计划开头差异表。要点：预览卡不含定义；掌握状态区在详情上方；搜索输入仍是筛选、回车才定位；卡片视图章节菜单禁用；图例不写 `EXAMPLE_OF` 方向；不新增 `importance` 字段（按度数估算）；「未开始」→「未学习」（含成功提示、`i06`、端到端）；增强模式换布局/位置重算会重建画布。执行时同步改规格对应小节并写 ADR-091（草稿在任务 17）。

## 计划代码已验证过的内容

临时落地任务 1–16 后：type-check 0；前端 55 个文件 / 1122 条通过；build 0；`verify.sh` 基础档 0；隔离页在 1280×800 目测概览态与预览一致。随后已还原。若备份还在：`/private/tmp/claude-501/-Users-arvinhan-SmartSketch--claude-worktrees-smartsketch-frontend-init-0d2af9/773f7eb6-d8f9-41e4-be77-bf0206166ad5/scratchpad/final-backup.tgz`（会话暂存，可能已清理；以计划里嵌入的代码为准）。

## 未验证（执行者必须补）

端到端（Playwright，需后端与数据）；`./scripts/verify.sh full` 与 `integration`；真实课程数据上的布局；G6 画布像素色对比度（文字 ≥4.5:1、图形 ≥3:1，按页面实际渲染色）；键盘 Tab 全路径与抽屉焦点；200% 缩放；真实 `prefers-reduced-motion`；真实 G6 里点击/悬停/章节跳转的逐项目测；修改前后截图（1440×900、1280×800、768、390）。

## 已知坑（计划里已处理，执行时留意）

- 既有 `i06`/`h11` 里点画布节点就期望详情 → 现在要点两次；`l13`/`l14` 的聚焦断言要 `vi.waitFor`（章节布局异步）。
- 画布位置 `null → Map` 只由 `ready` 建图，位置监听只处理重算/换位置，否则建两次并丢聚焦。
- `:inert` 关闭写 `true`、打开写 `undefined`，不要写 `false`（jsdom 渲染成字符串）。
- `.app-main > section` 的全站卡片样式要在图谱外壳里覆盖；工作区选择器统一 `.graph-workspace` 前缀；`section.recommendations` 才压得过 scoped 样式。
- G6 5.1.1：`hull` 插件不能移除（`Hull.destroy` 会抛），渲染后要手动 `drawHull()`；`labelVisibility` 无效，用布尔 `label`；`getZoom()` 在初始化/销毁中会抛，用 `zoomOf`；小地图延迟渲染，销毁要延后 400ms 并吞掉拒绝。
- 内置浏览器：窗格宽度变化会清掉自定义视口；模拟视口大于窗格时截图被缩小；后台页不派发 `ResizeObserver`。

## 风险

`process-parallel-edges` 与 `cubic-vertical` 同时开启只在合成数据上看过；`EXAMPLE_OF` 方向契约未明文；真实数据上章节很大（>20 节点）、`chapter_id` 缺失、全孤立等边界要补测；教师页第二批另行设计。

## 首个动作

1. 读完上面「必读」，确认基线命令仍是 38 / 934。
2. 在 `docs/tasks.md` 的 UI-GRAPH-PILOT-01 段补「Codex 接手」与范围（不要改 Claude 已写的决定）。
3. 从计划任务 1 起顺序执行；每个任务做完跑该任务的命令，并在 `docs/handoffs/codex-ui-graph-pilot-01.md` 记录实际命令与结果。
4. 任务 17 后写完成交接并请 Claude/用户审查（`review_status: ready_for_review`，列出 base/head、PASS/SKIP/FAIL 与未验证范围）。

## 试点之后

试点只覆盖学生图谱页。其余页面的推广范围、顺序与每页的决策点见 `docs/superpowers/plans/2026-10-07-ui-rollout-batch2.md`（路线图，不是代码级计划）。**试点未经用户确认通过前不要开始第二批**；第二批每个页面都要先向用户确认设计、做隔离预览、写规格和代码级计划后才改生产代码。

## 回滚

任务提交按「tokens → 画布引擎（1–10）→ 页面层（11–15）→ 外壳（16）→ 文档（17）」分批，可逐批 `git revert`；新 CSS 是新增命名空间；无迁移、依赖、契约变更。删除 `src/frontend/preview/` 前先确认交接与规格已记录全部证据。
