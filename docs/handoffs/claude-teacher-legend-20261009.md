# 教师图谱：节点类型图例与总览标签提示
review_status: ready_for_review
task_id: CLAUDE-TEACHER-LEGEND-20261009
日期：2026-10-09；负责人：Claude；基线：main `2e6acef`（本分支内容与其一致）。范围：电脑端（用户说明手机端暂不考虑）。

## 交付
1. **节点类型图例**（`components/NodeTypeLegend.vue`，教师页画布上方一行）：五类知识点的单字标记 + 名称 + 个数（取整张草稿图）；点击隐藏/显示该类，与工具栏“筛选”里的类型共用 `filters.state.nodeTypes`；有隐藏时显示“恢复全部类型”；按钮有 `aria-label`（含个数与状态）与 `title`。画布提示改为单行省略，键盘选择器保持。
2. **总览标签提示**：增强器每次重排标签后回调 `onLabels(shown,total)`；教师画布（`show-label-stat`）左下角显示“显示 n / m 个标签 · 放大可看到更多”，缩放 ≥ 0.9 或标签已全部显示时隐藏。
3. **放大到可读大小**：共用画布控件新增按钮（`data-test=zoom-readable`，图标 `readable`）；生命周期 `zoomToReadable()`：缩放 < 0.9 时放大到 0.9（视口中心），否则不动。学生页也会看到这个按钮（共用控件），其余学生页行为不变。
4. 径向布局横向拉伸 1.5→1.9。

## 验证
- 单测：`node-type-legend.test.ts` 2；`h14.test.ts` +1（图例计数、隐藏→画布节点减少、计数不随筛选变、恢复）；`graph-lifecycle-enhance.test.ts` +2（`onLabels`、`zoomToReadable`）；`graph-canvas-enhanced.test.ts` +2（按钮放大、提示默认不出现）并更新既有“控件可访问名称”断言（新增第 5 个按钮）。
- 浏览器（隔离演示栈，64 节点；1440×900）：图例显示 55/1/4/3/1；隐藏“概念”后“显示 9 / 64 个知识点”，恢复后 64；总览提示“显示 24 / 64 个标签”；点“放大到可读大小”后缩放 0.9 且提示消失；学生页工具组含新按钮、无标签提示。`tests/frontend/teacher-viewport.browser.cjs` 退出 0；`tests/e2e/teacher.spec.ts`（对该栈）通过。
- 门禁：见下节。

## 最终门禁
仅前端改动（后端、迁移、契约未触碰），所以只跑了相关部分：`./scripts/verify.sh basic` PASS（退出 0）；`scripts/verify/frontend.sh integration`（type-check 两个 tsconfig + vitest 全量 + build）PASS：64 文件 / 1217 passed。**没有**重跑后端全量、集成与个人模式 E2E，这次不是整条 `verify.sh integration` 的结果；上一轮整条命令在 `25cae93` 通过（见 `claude-teacher-overview-20261008.md`）。教师 E2E 用例对预览栈通过。

## 限制与建议
- 总览缩放约 0.25 时仍只显示约四成标签（枢纽节点优先的既有策略未改）；“放大到可读大小”会以视口中心为准，径向布局下中心是枢纽节点，周围节点较远，需要平移或用搜索/下拉定位。
- 类型图例在“概念”占绝大多数（55/64）的课程里区分度有限；后续可考虑按章节着色。

## 回滚
`git revert` 本任务提交；无数据/接口变化。
