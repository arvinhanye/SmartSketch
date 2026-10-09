# SmartSketch 当前状态与 Claude 接手交接

日期：2026-10-09（北京时间）。负责人：Codex。任务：CURRENT-HANDOFF-20261009。

> 这是给下一位使用 Claude 的开发者的接手入口，汇总截至下述固定提交的状态。页面专项完成不等于全量 CI 或整体产品验收完成。本轮只整理文档和只读核对，没有修复下述 CI 问题，没有调用真实模型或改动业务数据。

## 1. 先确认接手版本

| 项目 | 本轮核实结果 |
| --- | --- |
| 仓库 | https://github.com/arvinhanye/SmartSketch |
| 当前开发分支 | `codex/ui-polish-model-discovery` |
| 本文代码快照 | `c81f40992cdf5c53859f1f895d85a705a37d66f7` |
| 最新代码提交 | `style: round teacher graph cards and move create action to toolbar` |
| 交接计划基线 | `55b19d0`，PR #322 的交接文档分支 |
| PR #323 | OPEN；head 已包含 c81f409，GitHub 返回 MERGEABLE，但 CI 失败，未合并 |
| 本地工作树 | 核对时无 tracked 源码未提交变化；两个未跟踪 preview 日志保留，不提交 |

PR 依赖链：[#321](https://github.com/arvinhanye/SmartSketch/pull/321) → `main`；[#322](https://github.com/arvinhanye/SmartSketch/pull/322) → `claude/smartsketch-frontend-init-0d2af9`；[#323](https://github.com/arvinhanye/SmartSketch/pull/323) → `claude/ui-rollout-batch2-plan`。三个 PR 本轮查询均 OPEN。接手完整实现应使用 #323 的 head，不能只拉 main 或 #322。不要未经确认合并依赖链或更换 PR 基线。

**历史记录校正**：早先卡片交接和聊天写“c81f409 仅本地、未推送”；本轮 GitHub 查询确认 #323 的 head 已经是 c81f409，该旧描述已过时。本文是当前状态入口；不追溯推送来源。本交接文档本身需要另行传递或推送，不能假定远端已有。

同机真实仓库位于外层 SmartSketch 下的 `_pr-preview-321`。外层还有 `migration-new-backend` 等运行资料，不要在错误目录改代码或提交数据库。

## 2. 本轮需求完成进度

| 功能 | 状态与交付 | 核心提交/入口 |
| --- | --- | --- |
| 课程列表及通用页面 | 已实现：课程卡片、课程概览、模型设置等沿统一紫色/浅色内容风格调整 | c89b0df；相关视图和 `styles/ui.css` |
| 资料上传 | 已实现：上传区域重新排版，按用户要求删除右侧冗余说明 | 4d9db5b；MaterialsView.vue |
| 审核发布 | 已实现：三类审核条目去掉重复侧栏，分类卡片和发布区重新排版 | ea7f1ca；ReviewView.vue |
| 课程成员 | 已实现：紧凑添加表单、成员卡片/表格及响应式排列 | f54abfd；MembersView.vue |
| 登录 | 已实现：书页/知识/学习路径关联的前端插画；密码显隐；欢迎标题上方浮动提示 | 081a0d0、05e0c19；LoginView.vue、App.vue |
| API 供应商与模型 | 已实现：供应商预设、自动目录发现、手输/匹配/展开全部合为一个模型选择框 | c89b0df、0788a62、35ab825 |
| 教师 API 并列设置 | 已实现：通用和向量配置左右并列，常规桌面尽量一页展示；手机上下排列 | 0788a62；ModelSettingsView.vue、EmbeddingSettings.vue |
| 教师课程向量配置 | 已实现：加密密钥、模型/维度、发现/测试/保存、教师权限、课程使用配置、重建与发布适配 | e7291d2；迁移019和后端向量服务 |
| 学生图谱和问答 | 已实现：按钮悬停说明、图谱/侧栏可调宽、问答浅色内容区 | 80faac7；StudentGraphView.vue、ChatView.vue |
| 教师图谱视口 | 已实现：长表单内部滚动，不再撑高画布；左侧可调宽，小地图/工具稳定 | 0a1579f；TeacherGraphView.vue |
| 教师图谱按钮说明 | 已实现：教师/学生均有原生 title；小地图提示随状态变化 | 598774e；GraphCanvas.vue |
| 教师图谱圆角卡片 | 已实现：独立圆角搜索栏/左栏/画布；左栏参考用户图；新建入口移到顶部 | c81f409；GraphToolbar.vue、TeacherGraphView.vue |
| 用户最终视觉签收 | 尚未登记完成；请收集反馈，不以自动化截图检查替代 |
| 最新全量工程验收 | 未通过；见下一节 CI 失败，不可标 DONE |

代码已实现的状态仅针对本轮明确需求，不意味着任务板上所有历史工作均已验收。

## 3. 目前最需要接手的失败：GitHub CI

本轮实际读取 [CI run 37805487911](https://github.com/arvinhanye/SmartSketch/actions/runs/37805487911)，绑定 c81f409；最终状态 FAILURE。Repository scaffold 成功；Frontend、Backend、Integration and E2E 均失败。另一次重复运行也显示失败，不把重复检查当成不同代码版本。

### P1：前端全量 5 failed / 1181 passed

- `tests/frontend/b03.test.ts` 四个未登录入口用例找不到 `[role="alert"]`；覆盖 `/`、`/teacher`、`/student`、不存在路由。日志中 App 测试宿主的 RouterView 为空。
- `tests/frontend/graph-detail-layout.test.ts` 仍断言 `grid-template-columns: 35% minmax(...)`，与用户要求的可调宽侧栏存在冲突。
- 首先核实：浮动登录提示是否在真实 LoginView 正常呈现，测试是否替换掉了该组件；再决定调整测试宿主或实现，不能简单删断言。35% 旧布局断言应与已确认的默认25%和拖动/边界行为协调，不要为了旧断言恢复用户已否定的固定布局。
- 以上是日志事实与排查方向，尚未完成根因修复。

### P1：后端全量 3 failed / 3958 passed / 27 skipped

1. `test_c02b_disable_thinking.py::test_upgrade_from_017_preserves_existing_config_and_task`：实际新增迁移为 `['018','019']`，旧断言期待 `['018']`。
2. `test_f12.py::test_migration_012_rolls_back_and_reapplies`。
3. `test_g02.py::test_migration_010_rolls_back_and_reapplies`。

后两项抛 `MigrationError: Cannot apply a migration older than an already applied version`。优先检查加入019后，旧测试的隔离迁移集合/回滚 fixture 是否正确；必须保留“不能应用比已应用版本更旧的迁移”的生产防线。不得删除真实库迁移记录来过测试。27项 skipped 不等于27项通过，应核对允许跳过登记和原因。

### P1：集成及端到端

- 集成：1 failed / 392 passed / 4 skipped。失败为 `tests/integration/test_f13.py::test_migration_009_rolls_back`，同样是迁移先后顺序错误。
- 图库专项：44 passed；这不是整次集成通过。
- 演示 E2E 两条失败、个人模式 E2E 四条失败，均在登录处：`getByLabel('密码')` 同时匹配密码输入框和密码显隐按钮，触发 strict mode violation。修复入口选择器/可访问名称歧义并验证密码显隐后再跑全流程，不能据此宣称上传/发布/问答下游已通过。
- 定位入口：`tests/e2e/fixtures.ts`、`personal.spec.ts`、LoginView.vue。修复应保持可访问名称清晰，不破坏键盘和读屏。

建议按登录测试/布局测试 → 隔离迁移测试 → full → integration 的顺序处理，保存实际日志和失败截图。

## 4. 已有验证证据和它们的适用范围

| 证据 | 已记录结果 | 限制 |
| --- | --- | --- |
| 教师最新卡片/视口专项 H05/H07/H14 | 153 PASS | 不是全量前端；CI另有5项失败 |
| 图谱控件专项 | 12 PASS | 原生提示检查属性和地图状态，提示弹窗由浏览器渲染 |
| API 设置/模型选择专项 | 32 PASS，类型/构建通过 | 目录响应主要用受控假供应商 |
| 教师向量后端专项 | 84通过，另有提交空间检查；交接统计85个不同相关用例 | 不是当前全量后端通过 |
| 教师向量前端专项 | 30 PASS | 不替代真实供应商激活 |
| 最近 type-check/build/basic | 退出0 | basic只含骨架/契约等，不含全量业务或E2E |
| 教师页面浏览器 | 1920/1440/1366/1024/390五宽度通过 | 主要只读；未实际保存/删除整套真实图数据 |
| 长表单回归 | 1400px textarea、开关/滚动/拖动/键盘/窗口改变等通过 | 无法替代业务数据变更联调 |
| 真实演示课程读取 | 历史只读检查教师/学生各63节点70关系 | 本轮交接未重新执行全部业务操作 |

测试脚本：`tests/frontend/teacher-viewport.browser.cjs` 可独立用假 API 复现；Playwright运行时可通过 `PLAYWRIGHT_MODULE` 指定。截图和临时检查脚本在忽略的 `.local-run` 中，不是远端必备文件。构建仍有既有 >500kB chunk 提示，性能优化待按实际数据评估。

## 5. 必须保留的产品和技术边界

### 产品与视觉约束

- 教师编辑的是草稿；学生只能看到已发布版本。教师改草稿不能直接同步为学生可见内容，发布成功后才切换学生版本。
- 统一紫色强调色、浅色内容区、深色公共外壳。保留当前登录插画；不要换成页面截图或恢复原来的散点连线装饰。
- 不恢复资料上传右侧冗余说明，不重复三个审核类别，不拆回两个模型输入控件。
- 通用/向量设置常规桌面并列；展开帮助、多重错误、确认等可以增长，手机允许滚动。不能为“一页展示”裁掉必要字段或错误。
- 教师知识点详情/编辑在左侧，可调宽；新建唯一入口在顶部。不能重新引入长表单撑高图谱的问题。仅教师视口采用有限高度，不污染学生独立工作区。
- 右下角说明使用原生title，停留时间由浏览器决定；若以后要求固定延迟/统一弹层，作为单独前端任务实施和验证。

### 技术栈与安全边界

- Vue3/TypeScript/Vite/AntV G6；Python/FastAPI；Neo4j图谱/向量，SQLite业务/任务/个人配置。
- 页面、composable、API客户端和图谱引擎保持分层；不把HTTP请求、图转换和组件混写。
- 合同真源 `src/contracts/api.v1.yaml`，修改接口后同步生成物，不手改生成代码。
- 关系仅 CONTAINS、PREREQUISITE、RELATED_TO、EXAMPLE_OF；前置关系必须DAG，课程隔离和成员权限必须服务端校验。
- 保留来源引用、同课出处、资料不足时明确not_covered；不放宽问答15秒等既定验收口径来掩盖失败。
- 系统配置来自环境；用户密钥只能走受控接口加密存储。不打印/提交真实Key、运行配置、数据库、真实课件或原始聊天。
- 保留出站公网地址检查、DNS固定/TLS主机校验、请求预算、禁止重定向及响应大小限制；目录有结果不代表模型可用。
- 不扩展到3D、跨课程融合、生产SSO、原生移动端或多租户计费。

### 教师向量配置的已确认决定

- 按教师所属课程生效；学生没有向量配置页，自动使用对应课程的检索空间。学生自己的通用生成凭据仍独立。
- 教师配置与生成配置状态隔离；无覆盖时保留环境默认。不是一个教师改全系统的全局向量模型。
- 切换向量模型/维度需要完整重建并检查后原子激活，不允许混用空间；保留发布/回滚锁、活动尝试和提交空间检查。
- 旧向量属性/索引为增量保留，不自动破坏性清理。全局reembed不能越过混合教师覆盖保护。

## 6. 尚未完成/未验证与后续方向

### 优先完成

1. 修复并重新跑第3节 CI；全量绿色后才考虑PR整合。不要以本地专项替代整次门禁。
2. 用户手工签收：教师和已入课学生分别登录，教师编辑→保存草稿→审核→发布→学生重新读取；确认未发布改动不可见，发布后新版本可见，进度/出处不串课。
3. 在隔离课程验证：向量配置真实测试/保存、维度变化、完整重建、发布/回滚、学生检索，以及失败时旧空间保留。供应商需事先选择和有明确预算；本交接没有授权新付费调用。
4. 整个操作链的错误路径：权限失效、会话过期、修订冲突、发布超时/结果未确认、供应商拒绝、缺模型目录、不支持维度；不能把“审核队列清空”当作发布必成功。

### 仍未验证或未整体签收

- 新增各供应商的真实账号兼容性、模型目录开放情况、账号地域/模型ID、支持向量维度。11个通用选项与6个向量选项包含自定义；预设能力标记不是服务端保证。
- 本轮修改后的真实上传→抽取→融合→发布→学生问答完整端到端与生产部署，没有证明全部通过。
- 极短窗口、大型图谱、超长名称、千条模型目录、不同浏览器/读屏/高缩放的全面验收不完整。已测五宽度不等于所有组合。
- CSS中教师样式已有多轮覆盖；以后可小步整理重复规则并以截图/视口回归保护，避免大范围重构导致其他页面回退。
- 原生title触屏没有悬停入口；若要移动端额外说明，另立任务，不在本轮默改。
- G6大chunk、首屏及大图性能需要实测后优化，不盲目升级依赖。

### 历史计划C的保留缺口（不能被本轮UI验收覆盖）

先读 `codex-plan-c-acceptance-fixes.md`、`codex-plan-c-real-closeout.md` 和 `codex-plan-c-github-integration.md`。最终复审记录说明两课人工准确率已有用户采纳签收，但并非独立盲判；不要再复制更早的“完全未人工判定”描述。

浏览器可见首字、v3+思考开启基线、关闭思考MD抽取三项补测曾被用户决定不做，应继续标未测，不能自行恢复付费测量。耗时部分慢段根因仍OPEN；技术冻结未登记执行，stage C仍OPEN。旧性能/质量证据仅适用于其原始版本/模型/课程，不能外推到这次改动或所有PDF。后续冻结及真实测量另按用户明确决定推进。

## 7. 本机检查与可复现命令

本轮核实端口仍监听：前端5322、后端8321、Neo4j Bolt17688；端口监听不是所有业务健康证明。

- 前端 http://127.0.0.1:5322
- 教师图谱 `/courses/f013d69cf4484948a510e670ea13fd8a/graph/edit`
- 学生图谱同课程 `/graph`；模型设置 `/settings/model`
- API http://127.0.0.1:8321；`/docs` 是开发接口文档，不是用户前端。
- 本机演示账号：教师demo_teacher；学生demo_student2；本机测试口令smartsketch-demo。仅用于当前本地演示环境，其他机器不要假定账号/课程已自动存在。

现有 `.local-run/start.ps1` 启动API/worker/Vite，`.local-run/run.py`读取忽略的本机配置，`.local-run/stop.ps1`和processes.json管理进程。它们不随Git克隆提供；先检查端口和脚本内容再用，不能重复启动或误停其他任务。Neo4j需先确认启动。迁移019本机历史记录为备份后已应用，恢复备份位置见 `codex-teacher-embedding.md`；切换机器需按正规迁移流程初始化并验证，不复制带密钥的运行库。

通用开发命令（在真实仓库根执行）：

```bash
npm ci --prefix src/frontend
npm --prefix src/frontend test -- --run ../../tests/frontend/h05.test.ts ../../tests/frontend/h07.test.ts ../../tests/frontend/h14.test.ts
npm --prefix src/frontend run type-check
npm --prefix src/frontend run build
scripts/verify.sh basic
scripts/verify.sh full
scripts/verify.sh integration
```

先配置项目README所需Python/Node/Neo4j环境，integration用一次性库/演示模型；不要在用户演示库跑可写fixture。Windows上basic还需Python UTF-8、契约生成器所在Scripts目录和前端node_modules/.bin加入PATH，环境不足要记录FAIL/BLOCKED而不是跳过。Vite连接本机API需 `SMARTSKETCH_API_TARGET=http://127.0.0.1:8321`，否则默认8000。变更后按范围跑专项，修CI收尾必须跑整次full/integration。

## 8. 给 Claude 的首轮任务（可直接复制）

```text
请接手SmartSketch分支codex/ui-polish-model-discovery，先读AGENTS.md、CLAUDE.md、.claude/rules/、docs/tasks.md以及docs/handoffs/codex-to-claude-current-state-2026-10-09.md。
先核对HEAD、tracked/untracked变化、PR #321/#322/#323的基线和最新CI，不覆盖其他人工作；本交接代码快照c81f409。
第一轮只复现并修复本文第3节的前端、迁移和E2E登录失败，逐项区分测试宿主/旧断言与真实回归。保留用户已确认的布局、权限、DAG、迁移顺序、草稿发布隔离、来源与向量空间保护。
先登记原子任务和影响文件，再实现；禁止删失败测试、放宽安全/业务规则或读取/输出真实Key来凑绿。
使用隔离数据与假供应商；不自动发付费生成/向量请求，不自动部署、推送或合并。历史三项不补测仍保持未测。
每个原子任务完成后写docs/handoffs/claude-<task>.md，记录base/head、改动文件、实际命令/退出码和PASS/FAIL/SKIP、未验证范围、回滚与下一步。跑完必要检查后仅stage任务文件并创建本地Git提交，交付分支、提交哈希、提交说明；若提交受阻如实说明。
CI修复后整次full和integration验证，仍有失败如实报告，不宣称整体完成。交付review_status: ready_for_review，留给下一轮复审及用户视觉/业务签收。
```

文档入口：`docs/frontend-ui-handoff.md`、`docs/product.md`、`docs/architecture.md`、`docs/decisions.md`（ADR-080/092）、`specs/identity-access.md`、`specs/course-knowledge-graph.md`、`specs/teacher-review-publish.md`。逐项历史证据在 `docs/handoffs/codex-*.md`；历史“不推送/只预览”等边界必须按日期和本次核实状态解释，不能直接当作当前事实。

## 9. 本交接文档自身的检查

本轮核对Git/PR快照、读取绑定c81f409的失败CI日志，检查引用文件均存在及文档不含API-token标记；`git diff --check`通过，`scripts/verify.sh basic`退出0。仅本交接的文档检查通过，不改变第3节业务CI失败结论。本文与任务登记保存为新的本地文档提交，未自动推送；交给下一位时请同时提供本文件，或另行授权将该文档提交推送。
