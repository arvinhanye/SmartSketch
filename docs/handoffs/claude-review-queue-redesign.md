# claude-review-queue-redesign

- **task_id**: UI-02
- **review_status**: ready_for_review
- **目标 worktree**: 仓库根 `SmartSketch_src`（Windows 本机）
- **分支 / 基线**: `codex/api-settings-demo-restored` / base `e51dd67`；本轮未切换分支，未推送、未部署
- **任务与状态**: DONE（待 PR 审查/合并）——审核队列页（H09）与版本面板（H10）的界面重构

## 1. 目标与范围

把审核页从「三栏同时铺开 + 页面最外层大白卡 + 版本面板夹在中间」改为
**紧凑发布状态栏 + 分类切换 + 宽松单列审核列表 + 默认折叠版本历史**，改善信息层级与留白，
并让「发布」成为页面上唯一的强按钮。

改：
- `src/frontend/src/views/ReviewView.vue`（模板、局部展示状态、scoped CSS）
- `src/frontend/src/components/VersionPanel.vue`（布局、`review-content` 插槽、折叠历史、scoped CSS）
- `tests/frontend/h09.test.ts`、`tests/frontend/h10.test.ts`（跟随新的分类切换与折叠交互）

不改：后端、数据库、OpenAPI 契约、router / store / composable 的业务逻辑、审核与发布回滚规则、
图谱与 `graph/` 目录、其它页面、`App.vue` 与共用侧栏、`styles.css`。

## 2. 关键决定

1. **版本状态只有一份**：`ReviewView` 不再自己挂 `VersionPanel`；它把整页渲染进
   `VersionPanel` 的 `review-content` 插槽。`VersionPanel` 依次渲染「顶部发布状态栏 → 插槽 → 底部版本历史」，
   三段共用同一个 `useVersions` 实例，不重复请求、不复制版本状态。
   插槽位于 `state.course.value` 条件之外：版本数据加载失败时审核内容仍可见/可操作。
   不传插槽时 `VersionPanel` 仍可独立使用（`h10` 的组件级用例全部保持）。
2. **分类是 tablist**：`role="tablist"` + 三个 `role="tab"` 真按钮，`aria-selected` / `aria-controls` /
   `aria-labelledby` / roving `tabindex` 齐全，方向键与 Home/End 可切换。同一时刻只渲染当前分类的列表。
3. **默认分类只在首次加载成功后判定一次**：第一个有待处理项的分类；三类都为空时选第一类。
   之后不再自动跳类——刷新、处理完最后一项、切换分类都不改变用户选择；切换分类不重新初始化审核状态，
   `mergeDraft` 与各分类已加载数据/游标全部保留。换课（`courseId` 变化）时重置局部分类与证据展开集合。
4. **证据展开按关系 ID 独立**，只用插槽内的局部 `Set`；无可用来源（既无 `page` 也无 `section_path`）
   时不渲染展开入口，只显示「无原文证据」。原文片段用普通文本插值，不用 `v-html`；
   不把 `document_id` 当文件名，不虚构来源，不新增证据查询请求。
5. **RELATED_TO 无方向**：`UNDIRECTED_TYPES` 里的类型渲染 `—`，其余渲染 `→`，不把相关关系画成前置关系。
6. **折叠只影响展示**：版本历史用原生 `details/summary`，默认关闭；回滚确认区放在 `details` 之外，
   折叠不会静默隐藏待确认的回滚操作。发布时间用 `Intl.DateTimeFormat` 固定 `Asia/Shanghai` 并显式带
   `UTC+8`，缺失或非法时间显示「发布时间未知」，不出现 `Invalid Date` 与原始 ISO 字符串。
7. **数量一律取服务端 `totals`**：分类徽标与「共 N 项」都由 `totals` 计算（`共 N 项` = 三类待处理项之和，
   不是知识点去重数）。删除了「已显示 X / X 项」，只留一个居中的「更多」，调用现有
   `review.loadMore(当前分类)`，无 `next cursor` 时隐藏。
8. **视觉**：沿用现有暖色变量（`--color-*`）、细边框、`--shadow-card`、10～12px 圆角；
   页面宽度上限 `72.5rem`（≈1160px）只作用于审核页，不动全局 `.page` / `.app-main`；
   标题区直接落在页面背景上（移除最外层 `surface-card`）。条目按钮用 `data-variant="secondary"` 描边样式，
   只有发布按钮保持实心主色。新增样式全部写在两个组件的 `scoped` 样式里。

## 3. 保留的行为（未改）

`loading` / `not_teacher` / `error` + `retry` / `refreshing` / `refreshError` / `notice` / `itemError` /
`moreError` / `busyKey` / 课程作用域与迟到响应处理；busy 时禁止重复写、stale 时禁止发布与回滚、
refreshing 与刷新禁用条件；forbidden 事件与返回课程逻辑；发布结果仍以课程详情 + 版本历史核对，
网络中断/超时沿用「结果未确认」原文案；`data-test`、`data-id`、`aria-*` 全部迁移到实际对应元素
（新增 `rv-count-*` 用于分类数量的独立断言，`rv-evidence-toggle-*` / `rv-evidence-*` 用于证据展开）。

小屏（≤720px）：发布栏与条目按钮换行、条目标题与按钮不重叠、长名称/证据可换行、无横向滚动；
`prefers-reduced-motion` 下关闭过渡。

## 4. 已运行命令与实际结果

在 `src/frontend`（node v24.16.0 / npm 11.13.0）执行：

| 命令 | 结果 |
| --- | --- |
| `npm run type-check`（`vue-tsc --noEmit` × 2） | PASS，0 错 |
| `npm run build`（`vite build`） | PASS（1402 modules，产物已生成；仅有既存的 >500kB chunk 提醒） |
| `npx vitest run ../../tests/frontend/h09.test.ts ../../tests/frontend/h10.test.ts` | PASS，59 passed |
| `npx vitest run`（全量前端，回归确认） | PASS，25 files / 811 tests |
| `git diff --check` / `git diff --cached --check` | PASS（无空白错误） |
| 无头 Chrome（headless=new）渲染真实组件的临时入口 + 截图 | 见 §4.1，1440px 与 375px 均通过 |

### 4.1 视觉验证（已做）

用一次性临时入口（`visual-check.html` / `visual-check.ts`，只挂 `ReviewView` + `VersionPanel`
并注入假 API，验证完已删除、未进提交）在 `vite` 开发服务器上渲染真实组件，
再用无头 Chrome 截图，并用 CDP 在 375px / 320px 量 `documentElement.scrollWidth`：

- 1440px：三段（发布状态栏 / 审核卡 / 版本历史）左右对齐在 1160px；分类计数徽标、条目间距、
  「查看证据」展开后的原文片段、居中的「更多」、折叠的「版本历史（3）」都符合预期。
- 展开历史：`v3 发布 当前学生可见` 无回滚按钮，`v2 回滚自 v1`、`v1 发布` 有回滚按钮，
  时间为「2026年9月25日 08:00 UTC+8」（固定 Asia/Shanghai，无 ISO / Invalid Date）。
- 疑似重复分类：`合并…` 展开的合并面板（主知识点单选、合并说明、确认合并 / 取消）在卡片内正常撑开。
- 360px / 375px / 305px：`scrollWidth === clientWidth`，无横向滚动；发布栏按钮换行、
  分类标签换行、条目按钮整行、长知识点名称换行且不与按钮重叠。
- 期间发现并修掉一处**只有真渲染才看得出来**的对齐问题：发布栏与版本历史当时铺满主区宽度，
  而审核卡居中在 1160px。改为在 `VersionPanel` 根元素上统一限制宽度，三段才对齐。

**仍未验证**：
- `scripts/verify.sh full` 在本机跑不了：本机 `bash` 只有 WSL 存根，`/bin/bash` 不存在
  （`execvpe(/bin/bash) failed`）。已用上表三条等价命令替代 gate 里的
  `type-check → vitest 全量 → build`；`scripts/verify/gate.py` 的 JUnit 判定未执行。
- 真实后端 + 真实数据下的浏览（本机没有可用的后端/演示环境）；截图来自注入假数据的临时入口。
- E2E（`tests/e2e/teacher.spec.ts` 里的 `[data-test=version-panel]`）未运行；组件根与 `data-test` 未变。

## 5. 接口 / 数据 / 配置变更

无。未改 API 客户端、契约、DTO、环境变量或依赖（没有新增运行时依赖）。

## 6. 风险 / 未完成项 / 下一位 Agent 的首个动作

- 分类切换后「更多」按钮只对当前分类可见，符合「一次只铺开一类」的目标；如后续需要跨分类一次性
  看到全部待处理项，需要产品再决策（本轮刻意不做「全部」标签）。
- 分类数量徽标依赖 `totals` 实时性：处理后由既有 `refresh()` / 响应 `totals` 回填，未改计数语义。
- 下一位 Agent 建议动作：在真实后端 + 演示数据上打开 `/courses/{cid}/review` 做一次视觉与键盘走查
  （发布/刷新/回滚、证据展开、375px 宽度），并把截图补进本交接。

## 7. 回滚

只改前端展示层，回滚方式为 `git revert <本轮提交>`；无数据迁移、无破坏性变更。
