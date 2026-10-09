# UI-BATCH2-01：前端体验第二批

review_status: ready_for_review
task_id: UI-BATCH2-01
日期：2026-10-09；负责人：Claude；基线：UI-QA-01 之上同一工作区（分支 `claude/smartsketch-frontend-ux-672666`，基线 main `5398a1f`）。范围：电脑端（手机端只验证无溢出）。未提交、未推送。

## 逐项结果
| # | 项目 | 结果 |
| --- | --- | --- |
| 1 | 成员移除行内二步确认 | **已做**。点“移除”只在本行展开确认（含后果说明），点“确认移除”才发请求；“不移除”/Esc 收起；展开后焦点在“不移除”，收起回到“移除”，成功后焦点落在结果提示；请求中确认按钮禁用“移除中…”；失败回到“移除”。表格列宽调整以容纳确认区。 |
| 2 | 教师图谱未保存离开前提示 | **核查：已存在**（H14 起就有路由内确认和 `beforeunload`）。我之前误判为缺失，本批只加回归测试，未新增实现。 |
| 3 | 登录页首次访问不显示“未登录” | **已做**。守卫：未登录直接打开 `/` 不带提示；受保护页面、未知路径仍带 `notice=unauthenticated` 并显示提示（用 `to.redirectedFrom` 区分）。 |
| 4 | 教师图谱详情来源行与标题焦点框 | **已做**（样式）。来源按钮改为左对齐整块、自然换行；程序聚焦的标题不画整行焦点框。 |
| 5 | 模型设置演示模式与重名控件 | **核查后未改**。两张卡片本来是带标题的 `section` 区域，读屏可区分重名控件，且无测试依赖这些名称；演示模式下是否应禁用表单取决于服务端是否接受保存（业务行为），待决定。 |
| 6 | 资料上传框 | **已做**。虚线框支持拖放（同一条校验；多文件只选第一个并提示；上传中忽略）；原生英文文件控件视觉隐藏（仍可键盘聚焦、自动化可用），由中文按钮“选择资料文件 / 重新选择资料文件”替代，聚焦显示焦点环；拖入时高亮。 |
| 7 | 课程概览页两个主按钮 | **已做**。概览页“新建课程”降为次按钮，主按钮只剩“下一步”；课程列表页“新建课程”仍是主按钮。 |

## 文件
- 修改：`composables/useMembers.ts`（`confirmingId/requestRemove/cancelRemove`）、`views/MembersView.vue`、`router/index.ts`（守卫一行）、`views/MaterialsView.vue`、`views/CoursesView.vue`、`styles/ui.css`（成员确认、教师详情、资料上传框三段）。
- 测试：`h12`（五条移除用例改为先确认；新增 4 条确认用例）、`b03`（拆出“直接打开 `/`”一条）、`h02`（新增 6 条拖放/中文按钮用例）、`h14`（1 条 `beforeunload` 回归保护）、`course-page-ui`（1 条主按钮用例）、新增 `ui-batch2-styles`（4 条样式规则回归保护，真实呈现以浏览器验收为准）。
- 文档：`specs/identity-access.md`、`specs/task-processing.md`、`specs/course-knowledge-graph.md` 各补一节；`docs/tasks.md`。
- 接口、契约、后端、数据、权限无变化。

## 既有测试的调整及原因
- `h12`：移除多了“确认”这一步（用户批准的设计变化），原用例改为经 `removeRow()`（点“移除”再点“确认移除”）；原断言（调用参数、行消失、各类错误提示、防重入、COURSE_FORBIDDEN 回课程列表）全部保留。
- `b03`：`it.each` 中的 `/` 拆出为单独用例，改断言“无提示”；`/teacher`、`/student`、`/no-such-page` 仍断言有提示。

## 验证（测试与浏览器分开）
**自动化**
- 各项新增测试先 RED（失败原因为行为缺失）后 GREEN。
- `npm --prefix src/frontend run type-check`：exit 0；`npm --prefix src/frontend run test -- --run`：73 文件 / 1279 条通过；`npm --prefix src/frontend run build`：exit 0。
- `scripts/verify/frontend.sh full`：exit 0；`./scripts/verify.sh`（basic）：exit 0。
- E2E（一次性 Neo4j）：教师 + 学生（演示模式）2 passed；个人模式 4 passed。
- **未运行**：`verify.sh full/integration` 的后端与集成部分（后端未改）。

**浏览器**（一次性演示栈 + Playwright/Chromium，脚本与截图在会话临时目录，不进仓库）
- 登录：直接打开 `/` 无提示；`/teacher` 重定向后有提示。
- 课程概览：主按钮只有“维护课程图谱”。
- 成员：展开确认后焦点在“不移除”；Esc 收起、焦点回到“移除”、行数 3→3（未真正移除任何人）；390 宽无横向溢出；1440 截图确认区排版正常。
- 教师详情：标题 outline 为 none；来源按钮 `display:block`、左对齐，截图确认整块换行。
- 资料：派发 dragover 后出现高亮类，drop 后描述显示文件名、按钮变“重新选择资料文件”、高亮清除；Tab 可到达隐藏输入且按钮显示焦点环。
- **未验证**：真实浏览器里的原生拖放手势（脚本派发的是拖放事件）、读屏、`prefers-reduced-motion`、成员确认的真实“确认移除”走查（避免改动演示数据，由单测与 E2E 覆盖请求路径）、用户视觉签收。

## 风险
- 资料输入框视觉隐藏依赖 `clip-path`，若以后重构上传框需保留它在 DOM 中且可聚焦（e2e 与键盘依赖）。
- 守卫用 `to.redirectedFrom` 区分“直接打开”和“被重定向”；若以后新增会重定向到首页的路由，也会带提示（符合预期）。
- 成员表格列宽改了（操作列 38%），极窄桌面宽度下确认区会换行但无溢出（390 已验）。

## 回滚
各项独立：成员（`useMembers.ts` + `MembersView.vue` + ui.css 成员段 + h12 调整）、守卫（`router/index.ts` 一行 + `b03`）、教师详情样式、资料上传框（`MaterialsView.vue` + ui.css 段 + h02 新增）、课程概览按钮（`CoursesView.vue` 一处 + 测试）分别 `git revert`；无数据与接口变化。

## 待你决定 / 下一步
1. 演示模式下模型设置表单是否应禁用（取决于服务端行为）。
2. 推荐理由文案（“解锁度 1.0000”等，需服务端与规格先改）。
3. 本工作区目前累积 UI-QA-01 与 UI-BATCH2-01 两批未提交改动；提交方式和是否开 PR 等你指示。
