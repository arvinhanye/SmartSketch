# 任务看板

## 2026-11-11 Codex：DISAMBIG-PR-02 发布 BE-04

- 状态 READY_FOR_PR；负责人 Codex；用户明确授权提交 BE-04 并开 PR，再推进局部规范化与受影响关系重抽。
- 范围：`codex/disambiguation-context-windows` 中已验收的 BE-04；基线 `04286ec`，PR 目标为仍未合并的 `codex/knowledge-disambiguation`，只展示本批增量，不自动合并。
- 发布前复核：22 个源码/测试文件与上一轮最终验收哈希一致；本轮窗口/分层/测试索引 35 passed，exit 0。上一轮同一源码的 basic、后端 full 4513 passed / 27 登记跳过、定向 404 与新增/真实 Neo4j 56 的证据继续有效，未冒充本轮重新运行。保护 Claude 工作树，不包含其前端改动或开发数据。

## 2026-11-11 Codex：DISAMBIG-BE-04 有界抽取窗口与覆盖保护

- 状态 DONE（本批工程验收）；负责人 Codex；基线 `04286ec`（PR #348），分支 `codex/disambiguation-context-windows`。承接完整方案 §6/§9，先交付长材料实体/关系抽取窗口与覆盖保护这个可独立验证的增量；局部语义规范化/拆分重抽及手动合并计划继续后续工作包。
- 输入：原始块/小节实体表、模型请求预算和原始出处；输出：完整请求受限、证据还原至原始块、窗口计划和完成情况、抽取未完整时禁止本任务自动合并。只改后端/后端与集成测试及相关文档，不改 Claude 前端或公开契约，不更改默认开关。
- 依赖/风险：复用现有共享池、调用审计、L1/L2 重试与租约/取消保护；窗口重叠、Unicode 偏移、同名多出现、实体表分批、旧任务接管、窗口失败和预算不足均须覆盖。字节预算是保守工程上限，不是模型有效上下文或零幻觉保证。
- 验收：TDD、E05/E06/E11/E12/调度/消歧回归、真实 Neo4j 下覆盖缺口不合并、basic 与后端 full，一次独立终审及交接；本批不调用真实模型、不承诺减负或生成速度已达标。
- 结果：basic exit 0；最终定向 404 passed / 1 既有警告（71.14s）；新增后端与真实 Neo4j 集成 56 passed / 1 既有警告（42.00s）；后端 full 4513 passed / 27 登记跳过 / 1 既有警告（1101.95s），exit 0。一次独立审查的两项 Important 已 RED→GREEN 修复；22 个源码/测试文件哈希一致。迁移 022 仅在隔离测试库演练，临时容器已清理；Claude 工作树的三项新增前端改动未触碰。本批本地未提交、未推送；详见[交接](handoffs/codex-disambiguation-context-windows.md)。
- 后续登记：`DISAMBIG-FU-REL-01 OPEN`，关系同窗重复引文仍为基线首匹配；后续由后端/数据 AI 范围补唯一出现定位与歧义保护，再核查图校验依赖。该限制已同步规格与交接，不将本批来源还原表述为关系来源已经唯一消歧。
## 2026-11-14 Codex：PR-FIX-MERGE-04 修复七项问题并依序合并

- 状态 IN_PROGRESS；负责人 Codex；用户明确授权修复上一轮 7 项问题，测试和复审通过后按依赖顺序合并 #348、#350、#351。
- 输入：上一轮固定提交审查与可复现反例；输出：#348 两项后端修复、#351 五项前端修复、持久回归测试、独立复审与新 CI、三个 PR 的最终合并状态。
- 所有权：后端修复负责 `src/backend/`、相关后端/集成测试和 `specs/generation-disambiguation.md`；前端修复在固定 #351 临时快照内完成并交付补丁，负责前端/前端测试与图谱规格；协调者负责任务、索引、交接、合并和门禁。不会同步编辑同一功能文件。
- 约束：不改公开 API、不升级依赖、不调用真实模型、不迁移开发库、不纳入其他工作树未提交批次。保留不可变审计与有效贡献删除保护；以原始反例红→绿和现有测试证明修复。
- 验收：`./scripts/verify.sh`、后端/前端 full、相关真实 Neo4j 集成与新 PR CI；修复后独立审查无 P1/P2，再以固定 head 依序合并。计划见 `docs/superpowers/plans/2026-11-14-pr-review-fixes.md`。
- #348 修复进展：两处最小生产修复，新增回归先红后绿，相关 106 passed；basic 和兼容前端 full 1532 passed；独立复审无 P1/P2，完整后端 4504 passed / 27 登记 skip，Neo4j 504 passed / 4 登记 skip + 44 live passed，新 head 20 CI 全绿；#348 已合并为 `d63116f`。外层日志包装脚本退出码记录失误与门禁通过分开记录于专项交接。专项交接 `docs/handoffs/codex-pr348-fixes-20261114.md`；全程记录 `docs/handoffs/codex-pr-fixes-20261114.md`。

- #350 整合：已将 base 改为 main，保留窗口参数与独立组撤销测试参数；代码与验证快照逐文件一致。定向 54 passed、basic exit 0、隔离 Neo4j 32 passed；新 CI 与合并待完成。

## 2026-11-14 Codex：PR-REVIEW-MERGE-03 开放 PR 审核与合并

- 状态 REVIEW_COMPLETE / MERGE_BLOCKED；负责人 Codex；用户授权检查、审核并合并仓库开放 PR，覆盖此前批次“不自动合并”的交付限制。
- 输入：PR #348 `04286ec`、#350 `27339d9`、#351 `a1f0864`，main `50e6cba`，对应规格、交接、CI 和审查记录；输出：固定提交审查、必要冲突处理、验证证据、按依赖顺序的合并结果。
- 范围与依赖：#348 生成消歧基础；#350 依赖 #348 的有界窗口；#351 前端撤销重做。仅操作本工作树与本轮 PR，不纳入其他工作树未提交成果，不改默认模型开关或开发数据库。
- 风险：双存储投影及撤销、跨窗口覆盖、前端历史并发、主线兼容和既有 CI 偶发失败。三个 PR 分别只读审查；协调者核对发现、合并和最终状态。
- 验证：OCR delegate 文件/规则覆盖；`./scripts/verify.sh`，最小相关测试，合并冲突后的前端/后端适用门禁及 GitHub CI；记录未验证的真实模型、人工视觉和跨浏览器范围。交付 `docs/reviews/codex-pr-review-20261114.md` 与 `docs/handoffs/codex-pr-review-20261114.md`。

- 结果：#348 两项 P2（失败/取消资料删除被新外键阻断、撤销回退节点修订号导致旧请求通过）；#351 五项 P2（输入丢失、切课历史污染、旧重做覆盖新保存、部分成功不同步、图谱刷新未等待）。#350 未发现本批新增 P1/P2，但依赖 #348。全部保留开放；本轮未推送或合并。
- CI 复核：#351 唯一红项为既有密文篡改测试的随机无修改问题，单项重跑成功（run `43434532004` attempt 2）；不把 CI 绿灯视为上述反例已修复。
- 验证：#348 与 main 的本地兼容快照 basic exit 0、定向 150 passed；#350 固定 head 窗口回归 24 passed；#351 原相关测试 101 passed，五条新增反例全部失败并经协调者复跑确认。前端 full 的类型检查通过，测试/构建被共享依赖缓存写入权限阻断（EPERM），未计通过。真实模型和新浏览器验收未做。
- 交付：[审核报告](reviews/codex-pr-review-20261114.md)、[交接](handoffs/codex-pr-review-20261114.md)。反例与覆盖清单保存在本地 `.demo/pr-review-20261114/`；试合并已撤销，代码恢复开始时 main `50e6cba`。


## 2026-11-11 Codex：DISAMBIG-PR-01 提交已完成的消歧批次

- 状态 DONE；负责人 Codex；提交 `04286ec9aae4db818e67109a2d82ad73b8f6c620` 已推送，[PR #348](https://github.com/arvinhanye/SmartSketch/pull/348) 已创建且远端所有检查通过、可合并，未合并。用户授权先提交现有 BE-01～03 与设计/交接，再创建指向 main 的 PR，随后继续后端计划。本次授权更新此前“保留未提交、未推送”的交付约束，不授权自动合并 PR。
- 范围：当前 `codex/knowledge-disambiguation` 的 86 个已核对文件；无 Claude 工作树修改、开发数据或临时产物。接口客户端及两条原因标签随契约同步，保留新版页面布局和交互修复。
- 验证：提交前重新运行 basic、150 项消歧定向回归、后端 full、前端 full；保留既有隔离 Neo4j 和 Claude 兼容验收证据。真实模型评测与后续生成改造不混入本次基线提交。
- 结果：basic exit 0；消歧定向 150 passed（25.61s）；后端 full 4488 passed / 27 登记跳过 / 1 既有警告（897.97s），exit 0；前端 full 85 文件 / 1446 passed、类型检查和构建通过，exit 0。暂存差异与文件哈希核对通过，Claude 工作树干净。详见[提交交接](handoffs/codex-disambiguation-pr.md)。

## 2026-11-11 Codex：DISAMBIG-BE-03 审核消歧与撤销接口

- 状态 DONE（本批后端与最小客户端工程验收；新状态/历史/撤销控件及真实模型质量另验）；负责人 Codex。承接 BE-01/02，补齐审核过滤、覆盖状态、自动合并历史与预览/执行撤销 API，并交接 Claude。
- 输入：完整消歧方案、BE-02 不可变计划和撤销服务、Claude 审核页 `d102915`（只读核对）；输出：兼容现有审核路径的后端、OpenAPI/生成类型、最小前端接口适配、测试及接口交接。
- 所有权：后端、共享契约及生成物、相关测试和 Codex 文档；前端仅接口封装及新增原因标签，不修改 Claude 工作树、页面布局、对比/预览和交互修复，不自动合并分支。
- 边界：仅消费已提交且仍对应当前草稿的分析；打开审核页不调用模型；无分析/旧修订显式回退 legacy 并报告未检查，不把旧结论用于隐藏。自动合并继续默认关闭。撤销只面向自动合并，沿用教师权限、课程写锁、修订号、冲突和幂等保护。
- 验收：纯函数与 HTTP 权限/校验/过滤/分页/冲突回归、隔离 Neo4j 生成到审核及撤销实测、契约/basic、后端全量、必要前端类型/接口检查；真实模型质量与减负不由 fixtures 替代。
- 实际结果：有效生成结论驱动审核列表与 totals；技术缺口、语义未决、过期和未分析分别报告；公开覆盖、分页历史、单组预览/撤销四条新路径。撤销复用 BE-02 权限、课程锁、修订冲突和幂等服务。修复跨任务原始成员 ID 顺序问题，投影后候选须核对完整交叉成员。
- 验证：`PATH="$PWD/.venv/bin:$PATH" ./scripts/verify.sh` exit 0；`scripts/verify/backend.sh full` **4488 passed / 27 登记跳过**，exit 0（706.57s）；分层/视图/HTTP/存储/撤销 **73 passed**；隔离 Neo4j 融合/API/F11 **71 passed**，最后分层修复后 API/F11 **50 passed**。当前前端接口/H09 **45 passed**、type-check 通过；Claude `d102915` 临时兼容副本 **89 passed**、type-check 通过。独立终审无 Critical/Important/Minor。首轮全量分层失败已保留记录，修复代码所有权后复验，未放宽门禁。
- 交付：[Claude 接口交接](handoffs/codex-to-claude-disambiguation-api-20261111.md)；Claude 原工作树 242 个前端/测试文件哈希未变且状态干净，未整文件覆盖其审核页。新控件仍由 Claude 接入；未真实调用模型、验收减负/速度、改默认开关或开发数据库，两个临时 Neo4j 容器已清理。保留未提交、未推送成果。

## 2026-11-11 Codex：DISAMBIG-BE-02 混合召回与可撤销生成合并

- 状态 DONE（本批后端工程验收，真实模型质量及前端契约接入另行验收）；负责人 Codex；用户明确要求先修复 BE-01 两项审计待办，再完成混合召回、映射、图校验、可撤销合并。复用 `codex/knowledge-disambiguation` 和前批未提交成果。
- 所有权：后端、后端/集成测试、迁移、后端维护脚本、相关规格和 Codex 文档；不改 `src/frontend/`、`tests/frontend/`、Claude 工作树或其交接。保持现有前端协议兼容，撤销先提供后端服务/维护入口。
- 输入：完整消歧设计及 BE-01 交接；输出：[第二批规格](../specs/generation-disambiguation.md)、[实施计划](superpowers/plans/2026-11-11-disambiguation-reversible-backend.md)。
- 存储决定：保留原始检查点与合并前后快照；新草稿投影使用独立存储版本，SQLite 在 T6 围栏内切换有效指针。推理不持课程写锁，提交前检查草稿修订、有效任务与当前投影。
- 风险/验证：长上下文和召回覆盖、错误传递合并、合并诱发环、跨任务覆盖、教师锁定、失败半提交、撤销依赖、旧任务兼容；TDD、相关后端、basic、后端全量及真实 Neo4j 隔离集成。真实模型质量及费用评测另行进行，自动执行默认不开启。
- 实际结果：两项审计待办修复；混合召回、原始成员全组校验、版本化映射、完整图校验、T6 独立草稿切换及有冲突保护的单组合并撤销已接通。独立审查 4 项 Important 均以失败回归复现并修复；保留教师审核决定、人工关系及跨任务成员证据。
- 验收：`./scripts/verify.sh` basic 通过；`scripts/verify/backend.sh full` **4438 passed / 27 登记跳过**，exit 0；隔离 Neo4j `scripts/verify/integration.sh --no-e2e` **494 passed / 4 登记跳过 + 44 backend-live passed**，exit 0。其后补充的物理草稿 reembed 兼容修复，完整 F14 模块 **34 passed**（含 2 个新增回归）。保留此前中断及邀请迁移测试失败记录，不将其重记为通过。
- 交付：[后端交接](handoffs/codex-disambiguation-reversible-backend.md)。自动合并默认关闭，撤销交付后端服务及本地维护入口；未验证真实模型准确率、审核减负或生成速度，未做浏览器 E2E。前端、公开契约与 Claude 工作树未修改，未迁移开发数据库；临时验证容器已清理。保留未提交、未推送成果。

## 2026-11-11 Codex：DISAMBIG-BE-01 生成消歧后端基础

- 状态 DONE（后端第一批基础能力，完整消歧方案仍在分批实施）；用户已授权按消歧方案开始实施，前端修复由 Claude 负责。分支 `codex/knowledge-disambiguation`，基线 `31a7e6c`。
- 所有权：后端、后端测试、提示词、评测和 Codex 文档；不碰前端、前端测试、Claude 工作树/交接；本批不改审核 DTO。
- 输入：[完整设计](superpowers/specs/2026-11-11-knowledge-disambiguation-design.md)；输出：[第一批实施计划](superpowers/plans/2026-11-11-disambiguation-backend-foundation.md)、受限语义裁决、提及身份及生成分析检查点。
- 边界：分析默认关闭，可显式启用评测；不提前启用缺少版本贡献与撤销保护的自动合并。后续仍需混合召回、全局映射、图校验、跨任务提交与撤销、前端新契约及真实模型评测。
- 验收：TDD、E06/E10/E11/E12/调度/个人凭据回归、后端全量和 basic；真实语义质量不以 fake 替代。基线 E10/E11/E12 119 passed。
- 实际结果：三态裁决与独立复核、v2 提及身份、小节分析检查点、逐次物理调用 guard、离线指标已实现；独立审查 2 个 Important 经 7 个失败回归修复。最终定向回归 101 + 288 passed；basic exit 0；后端全量 4393 passed、27 登记跳过、1 条既有弃用警告，gate exit 0。首次全量 ADR 标题格式失败及修复记录保留在交接。最终文档链接与 `git diff --check` 通过；前端/契约及 Claude 工作树未修改，未提交、未推送。默认关闭分析，未启用自动合并，未验证真实模型质量、生成速度或审核减负。
- 后续进展：混合召回、最终映射/整组校验、同课程已有节点版本与撤销，以及 `input_digest` 输出预算、调用元数据异常路径两项审计待办，已由 DISAMBIG-BE-02 完成。真实模型质量/性能/审核量、长窗口实际覆盖及前端新契约仍待验收；成本以 SQLite `model_calls` 为准。第一批历史证据见 [后端交接](handoffs/codex-disambiguation-backend-foundation.md)。

## 2026-11-11 Codex：DEDUP-DOC-01 新版审核前端修复交接与生成消歧方案

- 状态 DONE（文档交付）；负责人 Codex；范围仅文档。用户要求整理本次前端检查结果，并形成适配新版前端的完整消歧优化方案，先不改代码。
- 输入：主线 `31a7e6c`、Claude 前端 `claude/ux-backlog-20261111@8420097`、隔离 Docker/API/浏览器检查证据、已有消歧讨论与论文；输出：[给 Claude 的修复交接](handoffs/codex-to-claude-review-dedup-fixes-20261111.md)和[完整设计稿](superpowers/specs/2026-11-11-knowledge-disambiguation-design.md)。
- 依赖与边界：保留 Claude 已确认的并排对比、合并预览、图谱查看和逐条处理；不改产品代码、契约、提示词、数据库或既有 ADR。现有课程是测试数据；方案涵盖同课程新增及已有节点，保护教师锁定内容，不做跨课程融合。
- 验收：区分已复现缺陷、契约兼容缺口与后续增强；完整说明生成阶段流程、自动与人工边界、长上下文保护、跨任务可见性及撤销、速度与质量指标；校验文档链接、`git diff --check` 和 `./scripts/verify.sh`（basic）。
- 实际结果：两份文档交付；前端交接列出 5 个已复现缺陷与 1 个契约兼容缺口，附代码位置、证据、修复边界和验收；设计包含文献、生成流程、同课程已有节点、误合并保护、撤销、长上下文、新版前端适配及评测口径。`PATH="$PWD/.venv/bin:$PATH" ./scripts/verify.sh`（basic）exit 0；文档相对链接/代码围栏/空白检查通过，`git diff --check` 通过。仅两份新 Markdown 和本任务段落变化；Claude 工作树未修改，未提交、未推送。未修复前端缺陷、未实施消歧、未运行真实模型评测。
- 待落实：字段贡献或不可变投影的存储选择、新契约版本、真实模型评测配置/预算，以及质量指标签收；设计中的新接口、完成度和验收目标均为提案。实施前同步相关规格/架构/ADR，并登记独立实施任务。本轮不视为批准或完成这些改造。
## 2026-11-11 Claude：画布上的直接操作（UI-GRAPH-EDIT-02，图谱体验第二批，用户确认设计稿）

| ID | 状态 | 负责人 | 范围 | 验收 |
| --- | --- | --- | --- | --- |
| UI-GRAPH-EDIT-02 | 实现与自动化验收完成，真实画布已实测（接口为替身），待真实后端复核与用户视觉签收（2026-11-11；review_status: ready_for_review） | Claude | 分支 `claude/graph-direct-edit-20261111`（基于 `claude/ux-backlog-20261111@d102915`，即 PR #347）。教师页：关系线点击工具条（改类型 / 反转 / 可撤销删除）、节点右键与“⋯”菜单、连接柄拖线与“从这里连线…”、成环预判；学生页：预览卡“就此提问”。文件：`graph/cycle.ts`、`graph/hitTest.ts`（新）、`graph/enhancer.ts`、`graph/lifecycle.ts`、`components/GraphCanvas.vue`、`components/canvas/*`（新）、`composables/useCanvasEditing.ts`（新）、`composables/useRelationEditor.ts`、`views/TeacherGraphView.vue`、`components/GraphPreviewCard.vue`、`views/StudentGraphView.vue`、`views/ChatView.vue`、样式与前端测试；规格 `specs/course-knowledge-graph.md`「画布上的直接操作」 | 不改后端、契约、数据与权限；“编辑关系”页签与既有 `data-test` 钩子保留（端到端用例依赖 `tg-tab-relations`）。`scripts/verify/frontend.sh full`、`./scripts/verify.sh`；隔离真实后端实走 |

- 用户确认的三项取舍：① 只有从连接柄开始拖才是连线，另有“从这里连线…”点选路径；② 拖动中做前端成环预判，最终以后端为准；③ 关系线删除不弹确认、给可撤销提示，节点删除保留现有确认流程。
- 与设计稿的出入：教师页菜单里没有“只看相邻”（教师页目前没有局部视图，另行排期）。
- 验收证据（2026-11-11，详见 `docs/handoffs/claude-ui-graph-edit-02.md`）：新增 `graph-direct-edit.test.ts` 9 条、`canvas-edit.test.ts` 15 条，`h14.test.ts` 追加 9 条；`scripts/verify/frontend.sh full` exit 0（89 文件 / 1523 条），`./scripts/verify.sh` exit 0；后端与契约零改动。真实 G6 画布上用真实鼠标走通：点关系线出工具条、删除并撤销、悬停出“⋯”与连接柄、从连接柄拖线并选类型、右键菜单（临时预览页，接口为内存替身，已删除）。**未做**：真实后端（当时 Docker 未运行）、学生“就此提问”的浏览器实走、触屏与其他浏览器。已知既有问题被放大：关系增删后整图重新布局。
- UI-GRAPH-EDIT-02 真实后端复核（2026-11-11）：隔离环境（临时 Neo4j / SQLite、演示课程 64 节点）上逐项通过——关系线工具条、改类型 200、反转成环 409 并回滚、删除 204 与撤销 201、连接柄拖线 201 与成环预判、右键菜单、学生“就此提问”到问答页预填。复核中修掉 3 处：工具条被数据更新后的缩放回报误收起（上一轮引入的回归，已补回归测试）、成环提示环路重复、“就此提问”按钮颜色被盖。未覆盖：修订冲突、网络失败。详见 `docs/handoffs/claude-ui-graph-edit-02.md`「真实后端复核」。
- UI-GRAPH-STABLE-03（2026-11-11，同一分支追加，用户确认）：DONE（待视觉签收）。教师页只增删改关系或删除知识点时节点位置不动、画布不重建；出现新知识点等才重新计算；关系与排布时不同时提供“重新排布”。`useGraphLayout` 新增 `stable` 选项，学生页不变。测试先红后绿（`graph-layout-composable.test.ts` 5 条、`h14.test.ts` 1 条）；真实画布实测连线后位置不变、“重新排布”可用。规格 `specs/course-knowledge-graph.md`「关系增删后节点位置不动」。
- 风险：G6 的边命中与右键事件、HTML 连接柄与画布拖拽的配合只能在真实浏览器里验证；撤销删除是重新建边，原关系的编号、来源与状态不恢复。回滚：还原本任务提交，无数据迁移。

## 2026-11-11 待优化：面向非技术用户的两项体验问题（用户提出，待设计）

背景（用户 2026-11-11 提出）：软件的使用者是教师和学生，必须保证在计算机知识储备不足的情况下也能顺畅使用。下面两项是当前体验最差的地方，先登记为待优化项；均**未开始、未认领**，动手前需要先做需求澄清并更新规格。

| ID | 状态 | 负责人 | 现状（按 main `31a7e6c` 的代码核对） | 待定 / 验收方向 |
| --- | --- | --- | --- | --- |
| UX-MODEL-SETUP-01 | OPEN / 待设计 | — | 模型 API 设置页（`views/ModelSettingsView.vue`、`components/EmbeddingSettings.vue`）：通用模型要依次选供应商、填服务地址、填 API Key、刷新并选择模型名称，另有“高级选项”和“测试连接”，最后保存；教师还有第二张“向量模型 API”卡片，要再填一遍供应商、服务地址、API Key、模型名称和向量维度。页面用语是“服务地址”“API Key”“向量维度”这类术语，没有分步引导，也没有“去哪里拿 Key”的说明。 | 待定：是否做分步向导（选供应商 → 粘贴 Key → 自动测试并选好默认模型）；常见供应商是否预填服务地址与推荐模型；向量模型是否对教师默认隐藏、沿用系统默认；出错提示改成能照着做的话。约束：ADR-080（个人凭据加密存储）、ADR-081 / ADR-092（向量配置）不变，不改变密钥的存储与权限边界。验收方向：不懂“服务地址 / 模型名称”的教师只凭页面提示能完成配置并看到“可用”结果；失败时知道下一步做什么。 |
| UX-REVIEW-DEDUP-01 | 前端实现与自动化验收完成，待真实后端走查与用户视觉签收（2026-11-11；review_status: ready_for_review） | Claude（前端） | 审核页（`views/ReviewView.vue`、`composables/useReview.ts`）的“疑似重复知识点”一栏是纯文字列表：每条只有两个名称、相似度百分比和原因；点“合并…”后选主知识点、看一段文字说明再“确认合并”，或点“不是重复”。一次只能处理一条（任一请求在途时所有按钮禁用），没有批量操作。页面上看不到这两个知识点的定义、各自连着哪些关系，也看不到合并前后图谱的变化；要看图只能点“编辑图谱”离开本页。 | 待定：在哪里处理（留在审核页加图谱预览，还是搬到图谱编辑页里就地处理）；合并前是否并排显示两个知识点的定义、来源与相邻关系，并预览合并后的局部图；是否支持批量（如“高相似度的一键全部合并”）及其撤销办法；合并成环（409 `CYCLE_DETECTED`）时怎样用图说明。约束：合并规则（ADR-047：名称并入别名、关系与来源迁移、主知识点锁定）与环检测不变。验收方向：教师不离开当前页面就能看清“这两个是不是同一个东西”以及“合并后图会变成什么样”；处理一批重复项的点击次数明显减少。 |

- UX-REVIEW-DEDUP-01 前端认领（2026-11-11，Claude，分支 `claude/ux-backlog-20261111`）：用户确认“先做这项、审核页预览与图谱内查看两处都做、不做批量”，并确认设计稿。范围只含前端：`views/ReviewView.vue`、`composables/useReview.ts`（暴露草稿图）、新增 `graph/mergePreview.ts`、`components/review/DuplicateCompare.vue`、`components/review/MergePreviewGraph.vue`、`views/TeacherGraphView.vue`（`pair` 参数高亮）、`styles/ui.css`、相关前端测试；规格 `specs/teacher-review-publish.md`「疑似重复知识点：对比与合并预览」。**边界：Codex 正在改进疑似重复的产生方式（规范化与消歧去重），本任务不碰后端、契约和审核队列的数据形状，只消费现有字段，未知 `reason`、缺失相似度都要能显示。** 风险：合并后预览是前端按 ADR-047 推算，可能与服务端结果有出入（界面标“预计”）；审核页布局由三栏改为左右两区，既有 H09 测试的钩子需保留。回滚：还原本任务提交，无数据迁移。
- UX-REVIEW-DEDUP-01 验收证据（2026-11-11，详见 `docs/handoffs/claude-ux-review-dedup-01.md`）：新增 `merge-preview.test.ts` 8 条（先红后绿）、`review-dedup.test.ts` 9 条，`h09.test.ts` 追加 7 条、`h14.test.ts` 追加 3 条；H09 原有 42 条未改且通过。`scripts/verify/frontend.sh full` exit 0（86 文件 / 1470 条），`./scripts/verify.sh` exit 0；`src/backend`、`src/contracts` 零改动。样式在临时预览页（示例数据，已删除）上看过。**未做**：连真实后端的完整流程（本机 Docker 未启动）、预览与真实合并结果的对照、窄屏与读屏。
- UX-REVIEW-DEDUP-01 审查意见修复（2026-11-11）：Codex 的 `docs/handoffs/codex-to-claude-review-dedup-fixes-20261111.md` 提出 F1～F6，六条我在 `8420097` 上都复现或确认成立。F1（长按 M 连续合并）、F2（来源显示 0 处）、F3（404 记为已合并）、F4（旧预览无提示）、F5（单选框方向键被抢）FIXED，先写失败回归再改；F6（缺 `similarity` 整页报错）OPEN，登记为待契约任务，规格已改回与契约一致。`scripts/verify/frontend.sh full` exit 0（87 文件 / 1490 条），`./scripts/verify.sh` exit 0；隔离真实后端（临时 Neo4j / SQLite、临时课程 4 对疑似重复）上逐场景复核通过，环境已清理。后端与契约零改动。详见 `docs/handoffs/claude-ux-review-dedup-01.md`「审查意见修复」。
- **待契约任务（未认领）**：`SuspectedDuplicate.similarity` 是否改为可选（F6）。需要后端 / 契约任务先改 OpenAPI 与生成类型，前端再放宽 `useReview.ts` 的 `isDuplicate`；与 Codex 的消歧去重设计一并决定。
- 与图谱体验后续批次的关系：UX-REVIEW-DEDUP-01 若选择“在图谱里就地处理”，会用到第二批计划中的节点菜单与边的直接操作，两者的先后需要一起定。
- 来源：2026-11-10 体验差距分析之后的用户反馈；现状描述是读代码得到的，没有在浏览器里逐步走过这两个流程。

## 2026-11-11 Codex：MAIN-INTEGRATE-02 历史独有改动审查与收敛

- 状态 DONE；负责人 Codex；基线 main `f944786`；有效代码 `e0022ab` 经 [PR #345](https://github.com/arvinhanye/SmartSketch/pull/345) 合入 main `9dccc30`。用户授权的剩余 15 个历史分支全部完成审查和原子删除。
- 输入：15 个远端历史分支及逐分支 merge-base 差异、现行规格/ADR、主线实现与测试；输出：逐分支语义比对和处置证据、必要的最小移植、恢复清单、更新后的 main。
- 执行：前端、问答/导入/E2E、跨平台/图谱三组只读并行审查；协调者核对历史契约/文档并统一实施。按文件所有权推进，不对旧分支整体覆盖主线。
- 约束：保留现行权限、接口、请求隔离、图谱工作台与模型设置行为；旧设计不能仅因提交独有就重新启用。确有规格冲突先记录并解决；无迁移、依赖升级或付费模型调用。
- 验证：原引用和完整 bundle 校验；逐分支差异覆盖与后续替代证据；必要代码移植先做有意义的失败回归，执行对应门禁及 `./scripts/verify.sh`；文档差异检查；PR 检查通过后合并；删除使用精确 SHA lease 与最终远端复核。
- 恢复材料：主检出 `.demo/historical-branch-cleanup-20261111/`；审计 `docs/reviews/historical-branches-20261111.md`，交接 `docs/handoffs/codex-historical-branches-20261111.md`。
- 实际纳入：用户确认的 ADR-097 安全级联删除（默认单点、明确选择、预览变化拒绝、修订号保护）；模型设置结果失效、RELATED_TO 无向显示、SQLite 问答审计故障隔离与最小跨平台修复；旧 K08 有效记录归档。
- 验收：最终代码 10 项 CI 全绿；后端 4340 passed / 27 登记跳过，前端 1443 passed，Windows portability 13 passed，真实 Neo4j 471 passed / 4 登记跳过，图库专项 44 passed，两组 E2E 2+4 passed。独立复核的已确认缺陷均已修复并重跑原反例。
- 本地：完整命令的契约/启动器/后端/前端/Neo4j/F11 通过，但受限环境 Chrome 启动报 EPERM/SIGABRT，整条命令 exit 1。正常权限审批后单独补跑原两组 E2E，2/2、4/4 且 exit 0；原失败记录保留，没有弱化断言或重记为整条通过。
- 清理：完整 bundle 校验成功后，逐项核对 15 个远端 SHA，dry-run 与实际删除均使用 atomic + 精确 SHA lease；操作后远端确认全部消失，main 不变。原 SHA、删除日志、CI 与本地验证证据均在恢复目录，其他工作区与本地环境保留。


## 2026-11-11 Codex：MAIN-INTEGRATE-01 分支整合与清理

- 状态 DONE；负责人 Codex；基线 `99e169a`；整合代码 `6bbcf14` 经 [PR #343](https://github.com/arvinhanye/SmartSketch/pull/343) 合入 main，合并提交 `1dbd272`；#342 随之合并。
- 范围：OPT-01～06 已由 #341 进入主线；本轮整合图谱查找/快捷键/视图记忆及抽取性能优化，处理 OPT-06 模块拆分、测试夹具、测量探针和 ADR 归档冲突。没有新增 API、迁移、依赖或付费模型调用。
- 验证：定向 73 passed；GitHub 9 项检查全绿，后端/工具 4293 passed / 27 登记 skip，前端 1414 passed，真实 Neo4j 463 passed / 4 登记 skip，图库专项 44 passed，教师/学生 E2E 2 passed，个人模式 E2E 4 passed。
- 本地验证：`./scripts/verify.sh integration` 的契约、启动器、后端、前端、Neo4j及图库专项均通过；E2E 入口因新 worktree 缺根目录 Playwright 依赖退出，整条命令 exit 1。接回已有依赖后单独补跑两组 E2E，2/2、4/4 通过且各 exit 0；没有将首轮整条命令改记为通过，也未重复已通过的长门禁。
- 清理：原远端 195→16（main + 15 个含未确认独有改动的历史分叉），删除 179 个旧远端引用；原本地 20→1，仅 main；本次临时整合分支也已清理。重复 PR #337/#339/#340 关闭，开放 PR 为零。逐分支 SHA 与保留依据见 [审计](reviews/branch-cleanup-20261111.md)。
- 保护：原未提交的任务段落与两份交接稿已逐字核实包含在 main，并额外保留恢复 stash；完整 Git bundle 与操作日志存主检出 `.demo/branch-cleanup-20261111/`。其他工作区文件和本地环境保留。
- 限制：真实模型准确率/耗时、图库持久化优化、发布向量化以及既有窄屏/读屏验收状态不因合并而关闭。交接 [codex-main-integration-20261111.md](handoffs/codex-main-integration-20261111.md)。

## 2026-11-10 Claude：图谱查找、快捷键与视图记忆（UI-GRAPH-FIND-01，用户确认“开始第一批”）

| ID | 状态 | 负责人 | 范围 | 验收 |
| --- | --- | --- | --- | --- |
| UI-GRAPH-FIND-01 | 实现、自动化验收与浏览器实走完成，待用户视觉签收（2026-11-11；review_status: ready_for_review） | Claude | 分支 `claude/knowledge-graph-ux-analysis-2e7400`。搜索改为“高亮 + 淡化”并支持别名、候选、上一个/下一个；画布快捷键（`/`、`F`、`+`、`-`）；学生页视图状态写入地址；两页面板宽度本地记忆。文件：`src/frontend/src/graph/search.ts`（新）、`graph/adapter.ts`、`graph/focusStates.ts`、`composables/useGraphFilters.ts`、`composables/useGraphShortcuts.ts`（新）、`composables/usePanelWidthPreference.ts`（新）、`composables/graphViewQuery.ts`（新）、`components/GraphSearch.vue`（新）、`components/GraphCanvas.vue`、`views/StudentGraphView.vue`、`views/TeacherGraphView.vue`、`styles/graph-workspace.css`、相关前端测试、`specs/course-knowledge-graph.md` | 不改后端、接口、契约、数据与权限；`filterGraph` 既有语义与既有 `data-test` 钩子保留。验收条件见 `specs/course-knowledge-graph.md`「图谱查找、快捷键与视图记忆」；`type-check`、前端全量、`build`、`./scripts/verify.sh`；浏览器实走与自动化分别报告 |

- 输入：2026-11-10 体验差距分析（搜索是过滤而非查找、无效率快捷键、视图状态不记忆）；输出：上表文件与交接 `docs/handoffs/claude-ui-graph-find-01.md`。依赖：现有 `match`/`dimmed` 画布状态、契约 `KnowledgePoint.aliases`。风险：既有测试里依赖“搜索隐藏节点”的断言；地址写回与问答链接 `?kp=&v=` 的处理互相触发；G6 画布重建时快捷键调用落空。回滚：还原本任务提交即可，无数据迁移。
- 本批不做（留待后续批次）：镜头位置写入地址；教师页视图状态写入地址；拼音/模糊匹配；搜索定义正文；命令面板。
- 验收证据（2026-11-11，详见 `docs/handoffs/claude-ui-graph-find-01.md`）：新增 `tests/frontend/graph-find.test.ts`（31 条）与 `h14.test.ts` 3 条；因规格变更调整 2 条既有断言（`graph-focus-states.test.ts` 命中时其余淡化、`h03.test.ts` 节点数据带别名）。`scripts/verify/frontend.sh full` exit 0（type-check 无错误，78 文件 / 1338 条通过，build 成功）；`./scripts/verify.sh`（basic）exit 0。反向验证一次：去掉学生页的 `search: 'highlight'` 后新测试 3 条失败，恢复后通过。**未做**：浏览器实走（本机 Docker 未启动，没有可用后端）、读屏、真实课程数据下的候选与淡化观感、`verify.sh full/integration` 的后端与集成部分（后端未改）。测试是在实现之后补写的，不是先红后绿。未提交、未推送。
- 续（2026-11-11）：按用户指示合入 `codex/opt-05-backend-layering@99c1f01`（改版前端），冲突三处已解。最终代码 `scripts/verify/frontend.sh full` exit 0（83 文件 / 1414 条）、`./scripts/verify.sh` exit 0。浏览器实走（1440×900，演示课程 64 节点，学生与教师两页）逐项通过，并修掉实走发现的两处：缩得很小时搜索定位不放大、教师页回车后焦点被详情与编辑面板标题抢走（新增 `composables/searchFocus.ts`）。上一条里“未做浏览器实走”“未提交”已不再成立；仍未验证：读屏、Firefox/Safari、窄屏、后端与集成门禁。已提交到本分支，未推送。待定：PR 目标分支（本分支含对方 10 个提交）、搜索框是否加宽。
- 续（2026-11-11）：按用户“整合到 main”的指示，在 #341（OPT-01..06 集成）合入 main 后把 main 合进本分支。冲突两处：本文件（取 main 的归档版，只保留本节）与 `StudentGraphView.vue`（OPT-06D 已把画布数据与面板逻辑拆到 `useStudentGraphPresentation` / `useStudentGraphPanel`，本任务的搜索命中与面板宽度记忆改接到这两个组合式）。

## 2026-11-10 Codex：OPT-03 后端测试夹具收敛

- 状态 DONE；负责人 Codex；分支 `codex/opt-03-test-fixtures`；从已提交且干净的 `codex/opt-02-test-waits@eca579c` 建立独立 worktree。OPT-02 剩余浏览器/集成验收不属于本任务。
- 输入：AGENTS、`.claude/rules/testing.md`、原审查分支 OPT-03 节及当前后端测试；本基线没有 `tests/INDEX.md`。
- 输出：仅后端测试共享辅助/初始化、消费者迁移及本任务文档；不改断言、不删或增加用例、不改产品代码。
- 依赖/风险：复用已有 Python/前端依赖；SQLite 路径与所有 fixture 保持 function 作用域，保留不同实现和专门迁移测试，避免状态交叉污染。
- 执行：先记录收集数/重复定义及初始化计数；每批只迁一种辅助并立即运行该批测试；最后对修改文件用两个固定随机种子运行。
- 验收：`PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend --collect-only -q`；各批 pytest；修改文件两次随机运行；`PATH="$PWD/.venv/bin:$PATH" ./scripts/verify.sh full`；`git diff --check`；交接 `docs/handoffs/codex-opt-03.md` 记录实际结果/未合并差异，最后仅本地提交（含 Co-Authored-By），不推送、不建 PR。

- 验收结果：基线与最终均收集 4072 项；原断言、测试参数定义不变。27 批最终全部通过；54 个修改测试文件以 seed 20261110/20261111 随机运行，各 1545 passed / 27 原有 skip，实际顺序全部不同。五类辅助总实现 41→11；直接迁移文件 63→23；create_app 文件 27→16。
- 完整门禁：`PATH="$PWD/.venv/bin:$PATH" GOCACHE="$PWD/.demo/opt-03/go-build-cache" ./scripts/verify.sh full` exit 0；后端/工具 4254 passed / 27 登记 skip，前端 82 文件/1375 passed，类型检查、构建、启动器与契约通过。首轮因系统 Go 缓存权限失败后主动中止（143），没有计为通过；重跑只调整测试进程缓存位置。`git diff --check` 与源文件校验值核对通过。
- 交付：[OPT-03 交接](handoffs/codex-opt-03.md) 包含 grep 计数命令、各批文件/结果、未合并原因和原始失败记录；按授权仅本地提交，含 Co-Authored-By，不推送、不建 PR。

## 2026-11-10 Codex：E2E-PERSONAL-01 高级选项操作修复

- 状态 DONE；负责人 Codex；工作区 `opt-02-test-waits/SmartSketch-main`，分支 `codex/opt-02-test-waits`，起点 `51ef5cb`（干净）。用户要求先确定可行方案再修复，范围为个人模式E2E隐藏控件超时；窄屏布局缺陷仍另行OPEN。
- 输入：4份真实E2E超时trace、`ModelSettingsView.vue`默认折叠的高级选项、`personal.spec.ts`共享配置步骤、测试规则及个人配置规格。
- 方案：只改测试；在通用模型表单内定位高级选项，仅收起时正常点击summary，确认开关可见后操作；刷新后重复展开并保留保存值断言。真实页面教师/学生两角色已验证旧步骤失败、新步骤可行，覆盖true/false、已展开、刷新路径。
- 输出：`tests/e2e/personal.spec.ts`、本任务记录与 `docs/handoffs/codex-e2e-personal-01.md`；不改产品、API、持久化或用例总超时，不使用force或直接改DOM状态。
- 依赖/风险：本地Chrome、现有依赖、一次性Neo4j与本机假供应商；后续E2E可能暴露此前被第一步阻挡的问题，需如实记录，不以隐藏控件修复推断整个业务闭环通过。
- 验收命令：真实页面方案诊断；`E2E_LLM_MODE=personal scripts/e2e.sh tests/e2e/personal.spec.ts --max-failures=1`（全4项，首次失败即停止避免重复长超时）；`PATH="$PWD/.venv/bin:$PATH" ./scripts/verify.sh`；`git diff --check`。本轮不重跑已完成的Python20轮或整条integration长门禁。
- 结果：教师/学生真实页面方案检查通过；个人模式E2E **4 passed，exit 0，约1.7分钟**；基础门禁exit 0；`git diff --check`通过。原15个测试/辅助文件SHA256未变。详见[交接](handoffs/codex-e2e-personal-01.md)。

## 2026-11-05 Codex：OPT-02 测试等待稳定性

- 状态 IN_PROGRESS（浏览器20轮仍受阻；完整integration前次被取消，尚无自然结束结果；个人模式E2E已另项修复并通过）；负责人 Codex；分支 `codex/opt-02-test-waits`；基线 `ad63341`；原任务起点干净，本轮接手时已有未提交改动全部保留。
- 输入：`AGENTS.md`、`.claude/rules/testing.md`、审查分支 `claude/code-structure-review-handoff-49e73a` 中 `docs/handoffs/claude-code-structure-review-codex-handoff.md` 的 OPT-02 节（当前分支无该文件）；重新运行的固定等待清单。
- 输出：仅 `tests/` 内条件轮询、事件/假时钟或真实时长保留说明；本任务记录和 `docs/handoffs/codex-opt-02.md`。先复现 macOS `test_grace_period_is_not_shortened_by_shell_seconds_rounding`，确认根因再改；产品竞态只记录，不修产品。
- 依赖与风险：现有 Python/前端测试环境；集成验证需要可用的本机 Neo4j。计时测试不得弱化断言，子进程与后台线程必须清理；不同代理按文件划分所有权。
- 验收：每个改动的测试文件循环 20 次；`./scripts/verify.sh full`；涉及集成时 `./scripts/verify.sh integration`（环境缺失则记录 SKIP/原因）；最终差异仅测试与上述文档。不推送、不开 PR。
- 已验证（2026-11-09恢复核对）：31处固定等待逐项处理，27处改用条件/事件/局部假时钟或移除，4处保留真实时长并说明原因；macOS宽限期失败先复现，根因是测试跨进程相减单调时钟，已改同进程计时与就绪握手。12个Python测试文件各20轮通过，共11480项；full通过。完整清单、命令、重启造成的验证中断及证据边界见 [交接](handoffs/codex-opt-02.md)。
- 门禁：11月10日使用绝对Python路径与一次性Neo4j重新执行完整`./scripts/verify.sh integration`；后端4254通过/27登记跳过、前端1375通过、真实集成463通过/4登记跳过、图库补验44通过、教师/学生E2E 2通过。个人模式4项均因隐藏的`mc-disable-thinking`控件超时失败，E2E子脚本exit 1。用户要求取消时已停止；总脚本未写最终退出码，不计完整自然结束。停止后核对日志，最后一项已记录原定超时，最终日志为4 failed，不是3 failed + 1 interrupted。命令、证据及前次中断记录见[交接](handoffs/codex-opt-02.md)。未重做12个Python文件已通过的20轮。
- 浏览器：原版与当前版诊断副本各退出1；四个宽视口通过，390×844在原断言`initial.mapTop >= initial.canvasTop`失败。实测越界的是`.gw-map__ctl`五按钮列；缩略图`.gw-mini`已隐藏。`5×44 + 4×6 + 16 - 239 = 21px`，首按钮实际覆盖知识点下拉框；是产品布局缺陷，非测量错误。浏览器20轮明确为未通过/受阻，保留全部断言与产品代码。
- 续修结果：`E2E-PERSONAL-01`已完成，高级选项先展开再操作/刷新核验，个人模式E2E 4项通过、基础门禁通过；前次失败与取消记录保留为历史证据。当前未决为下方`UI-TEACHER-CONTROLS-01` OPEN及之后的浏览器20轮/完整integration验收。未改产品布局；不推送、不开PR。

## 2026-11-09：UI-TEACHER-CONTROLS-01 教师窄屏地图/缩放按钮列越界

- 状态 OPEN；发现/记录 Codex（OPT-02验收），实施负责人待定；等待用户决定是否另行修复，不属于OPT-02的测试等待改造范围。
- 复现：基线`ad63341`，390×844，教师图谱编辑页只读API夹具。`.gw-map`/`.gw-map__ctl` top=495.671875，`.graph-canvas`/stage/原生canvas top=516.671875、高239；首个“展开小地图”按钮上缘越界21px，覆盖上方知识点下拉框。原版和当前版测试同样失败，测量正确。
- 来源：`src/frontend/src/styles/ui.css:259`移动端按钮高度44px；`src/frontend/src/components/GraphCanvas.vue:348–350`控件列`display:grid;gap:6px`；同文件`:330–334`工具组绝对定位`bottom:16px`。五按钮共244px，要求至少260px绘图区，而卡片340px减上下边框2px和换行栏99px后只剩239px。不是继续等待能消除的问题。
- 证据：见[OPT-02收尾交接](handoffs/codex-opt-02.md)的DOM/CSS数据、命中测试与截图路径；本次仅记录，未调整CSS或断言。
- 待用户决定：是否授权单独安排窄屏控件布局修复。后续验收需保留原断言，390×844下控件完整位于绘图区且不覆盖知识点选择栏，其他四种宽视口不回归；随后原浏览器脚本连续20轮通过。

## 2026-11-05 Codex：OPT-05 后端分层修正

- 状态 READY_FOR_REVIEW（实现/复核/续验完成，2026-11-09；原版个人模式 E2E 有既有验收例外）；负责人 Codex；分支 `codex/opt-05-backend-layering`；代码基线 `ad63341`，开始时工作区干净。过程中出现的并行改动未由本任务覆盖/回退。
- 输入：`AGENTS.md`、`.claude/rules/backend.md`、`docs/architecture.md` 后端分层；审查分支 `claude/code-structure-review-handoff-49e73a` 的 `docs/handoffs/claude-code-structure-review-codex-handoff.md` OPT-05（当前基线无此文件）；发布、任务与问答规格。
- 输出：版本物化/文本块向量的 Cypher 与指定三个服务的 SQL 下沉仓储；问答服务装配与日志下沉 `services/qa/`；`docs/handoffs/codex-opt-05.md` 逐函数移动清单与验证证据。
- 实施顺序：并行搬移版本 Cypher、配置/取消/版本解析 SQL；主代理下沉 QA 装配和日志；汇总审查查询原文、参数、调用次序与事务作用域；运行门禁后更新状态。代理按文件独占，文档由主代理维护。
- 依赖与风险：Python 3.11.9 / 现有 `.venv`；本机 Docker 可用，集成门禁使用一次性 Neo4j。查询文本逐字不变，`course_id` 参数、事务内外位置与 PREREQUISITE 环检测链路不变；契约生成物不得变化。
- 验收：定向后端测试、`./scripts/verify.sh integration`（环境不可用则 `full` 并标 integration 未验证）、`git diff --color-moved` 与 `git diff --check`；不推送、不开 PR。
- 已实现：35 个查询定义下沉，85/85 查询定义原文及重复次数一致；课程参数、事务边界、调用次序和环检测路径保留；新增分层护栏 10/10 通过；契约生成物无变化。
- 验证证据：11 月 5 日完整门禁的后端 4264 passed / 27 登记跳过，前端 1375 passed；11 月 9 日 `scripts/verify/integration.sh --no-e2e` **exit 0**，真实 Neo4j 集成 **463 passed / 4 登记跳过**、图库专项 **44 passed**；demo+K10 原失败定向 4 passed、教师/学生 E2E 2 passed。
- 验收例外：原版个人模式 E2E 因折叠高级选项中的开关不可见而超时（1 failed / 1 interrupted / 2 未执行），临时副本仅补展开步骤后 4 passed，原用例与前端均未改；此补测不等同于原版完整门禁通过。基线 `ad63341` 也复现过 demo 入库传输超时，本轮集成该用例通过，稳定性现象如实保留在交接中。
- 交接：[codex-opt-05.md](handoffs/codex-opt-05.md) 含逐函数移动表、查询对照、原失败与基线复现、补测边界。保持未提交，不推送、不开 PR。


> **R1 最新状态（2026-10-09）**：PR #324 已整合 main 并消除文档/ADR 冲突；代码 head `36b421e` 的 push/pull_request 两轮 8 项 CI 全部 SUCCESS，含真实网络/恢复和 E2E。worker 围栏限定风险 **CLOSED**；用户已授权「CI通过就合并PR」，按最终 head 全绿门禁合入 main，最终合并结局以 PR 状态/提交为准。不部署或技术冻结；全项目 stage_c_status OPEN、technical_freeze NOT_PERFORMED 不变。验收见末节及 `docs/handoffs/codex-pr324-conflict-ci-repair.md`。

> **当前状态（2026-10-04，GitHub 主线集成）**：人工准确率已签收，方式为 arvin 逐条复核后采纳辅助判定，非独立盲判；stage_c_status **OPEN**，technical_freeze **NOT_PERFORMED**。用户要求先修复并自行检查，再决定冻结。关闭思考 Markdown 抽取、浏览器可见首字、v3 + 思考开启基线三项按用户决定不执行，均为未测。旧接手/初始交接的“未签收”“待补测决定”只作历史记录；计划A/B/C与四项验收修复已通过#317、#319、#318合入GitHub main；代码集成不是技术冻结。当前依据以末节与 `docs/handoffs/codex-plan-c-github-integration.md` 为准。


> **归档后看板（2026-11-05）**：以下保留未关闭条目及未决风险的原文摘录；旧状态未重新签收，历史子句可能已被后续记录取代，须结合所链原节核对。完整历史按月归档；日期不明的早期骨架节归入 2026-09。FORMAL 依用户确认只保留最新发布结论和待办。

## 2026-10-06 Claude 认领：前端视觉升级——图谱工作台样板页

[完整上下文](archive/tasks-2026-10.md#t000)

| ID | 状态 | 负责人 | 范围 | 验收 |
| --- | --- | --- | --- | --- |
| UI-GRAPH-PILOT-01 | IN_PROGRESS（任务1–16与用户批准的详情局部修正已实施；任务17剩余验收待做；用户2026-10-07已授权提交与开PR，以Draft发布） | Claude（设计）/ Codex（实施） | 学生图谱页作为首个样板：暗色外壳 + Kumu 式浅色画布；左说明面板合并详情；`src/frontend/preview/`（隔离预览，不进生产构建）；确认后再改 `App.vue`、`StudentGraphView.vue`、`GraphToolbar.vue`、`Recommendations.vue`、`KnowledgeDetail.vue`、`GraphCanvas.vue`、`graph/adapter.ts`、`graph/lifecycle.ts`、新增 tokens/顶栏/图标组件及相关前端测试 | 不改业务流程、契约与接口；教师审核/发布、学生掌握状态与推荐、来源、`not_covered` 与服务错误的区分完整保留；相同视口前后截图（1440×900、1280×800、768、390）；`npm --prefix src/frontend run type-check`、前端全量测试、`build`、`./scripts/verify.sh`；浏览器走查键盘、焦点、200% 缩放、减少动效 |

- 未决：教师图谱编辑面板（详情、编辑、关系、版本、新建）在「无右侧栏」布局中的位置，样板确认后另行设计；`lifecycle.ts` 面板开合只 `setSize` 不 `fitView`（与 L14 的窗口缩放重新聚焦区分）；曲线边类型与平行边转换的相互作用；类型标记形式。
- 依赖与风险：沿用现有依赖，不新增；图标用内联 SVG。样板确认前不覆盖全局 `--color-*`，新 tokens 用独立命名空间，回滚即撤销本任务提交。`h05`/`i06`/`l13`/`l14` 等测试断言状态样式，需同步更新。

## 2026-10-03 Claude 认领：冲刺计划 B（L11–L15 功能闭环）——功能交付已收尾，质量/性能验收有保留（2026-10-03）

[完整上下文](archive/tasks-2026-10.md#t004)

| ID | 状态 | 负责人 | 范围 | 验收 |
| --- | --- | --- | --- | --- |
| L11 | IMPLEMENTED（功能代码完成；L11-7 真实模型复测 OPEN） | Claude（L11-1～L11-5）；DeepSeek harness（L11-6 真实模型测量） | 自编两门课资料与 PDF、本机假供应商、个人模式端到端、发布阻断原因、失败路径验收、真实模型测量 | `personal.spec.ts` 教师 PDF+MD 闭环与鉴权失败用例通过；真实模型报告 `evaluation/reports/l11-teacher-loop-2026-10.md` 分列假供应商接线与真实质量/耗时 |

## K05 教师主线 E2E（Codex）

[完整上下文](archive/tasks-2026-09.md#t008)

| ID | 状态 | 负责人 | 范围 | 验收 |
| --- | --- | --- | --- | --- |
| K05 | IMPLEMENTED / 待审查验证 | Codex | `tests/e2e/teacher.spec.ts`、`tests/e2e/fixtures.ts`、Playwright 运行入口 | 四格式上传、上传失败重试、成环拒绝、发布后学生可见；默认 fake 模型输出不满足抽取格式，真实 E2E 尚未运行 |

## 当前里程碑：M0 协作与应用骨架

[完整上下文](archive/tasks-2026-09.md#t016)

| ID | 状态 | 任务 | 负责人 | 验收条件 | 证据 |
| --- | --- | --- | --- | --- | --- |

| M0-04 | TODO | 定义第一版 API、SSE 任务事件与图谱 DTO | Backend + Frontend Agent | `src/contracts/` 有版本化契约；双方确认 | 待补充 |
| M0-05 | TODO | 定义 Neo4j/SQLite 开发环境与本地启动方式 | Data/Backend Agent | 无密钥可启动依赖；环境变量文档完整 | 待补充 |

## 下一里程碑：M1 课程资料到草稿图谱

[完整上下文](archive/tasks-2026-09.md#t019)

| ID | 状态 | 任务 | 负责人 | 验收条件 |
| --- | --- | --- | --- | --- |
| M1-01 | TODO | 课程与资料上传 API | Backend Agent | 资料记录、格式校验、任务创建、错误响应均有测试 |
| M1-02 | TODO | 文档解析与分块 | Data/AI Agent | 支持四种格式；分块保留定位来源 |
| M1-03 | TODO | 节点关系抽取与融合 | Data/AI Agent | 四类关系；低置信度项可审核；课程隔离 |
| M1-04 | TODO | 前置关系 DAG 校验 | Backend Agent | 环路拒绝、错误可解释、自动化测试 |
| M1-05 | TODO | 教师审核与发布版本 | Full-stack Agent | 可编辑、发布、读取已发布版本 |

## 架构审查与可执行拆分

[完整上下文](archive/tasks-2026-09.md#t020)

- 认领时按原子 ID 新增状态行，写目标 worktree/HEAD 和文件所有权；M0/M1 原行保留为父任务，不把未合并 worktree 的完成状态自动搬到 main。

## 待确认决策

[完整上下文](archive/tasks-2026-09.md#t021)

| ID | 问题 | 决策人 | 需要在何时确认 |
| --- | --- | --- | --- |

| D-02 | 首个 OpenAI 兼容模型供应商与预算上限。A07 已拆为 D-02a～f 六项，签收入口见 `docs/integrations.md`「待签收取值（D-02）」；配置形状与规则已定。**D-02a 已签收**：主用 DeepSeek V4.1 Flash（`deepseek-flash`，ADR-027，ArvinHan 2026-09-26）；D-02d 已签收（ADR-028，按占位值），抽取评测付费调用已确认；D-02b、c、e 仍未签收 | 技术负责人 | 接入抽取服务前（fake 实现可先行） |

| D-08 | 融合自动合并阈值与低置信度阈值的初始取值（沿用 `740adb` 未决问题编号，ADR-016 决定 7） | 技术负责人 | E09/E10 开工前 |

| D-14 | 只设所有者密码（空用户密码即可打开，仅限制复制、打印等权限）的 PDF 是否放行。**暂定**：与其他加密 PDF 一样按 `DOCUMENT_UNREADABLE`（`encrypted`）拒绝（ArvinHan，2026-09-25）。放行前须决定是否遵守「禁止复制」等权限，涉及版权 | 产品负责人 | 首批课程资料导入前（D-01） |

| PLAN-D05 | 学习材料生成分支决定是否同步 main；目标路径是否纳入（O01） | 产品负责人 | 主线验收后、加分项前 |

## 审查遗留（2026-09-25 核对）

[完整上下文](archive/tasks-2026-09.md#t051)

| 编号 | 级别 | 来源 | 现状（main 上复现） | 建议归属 |
| --- | --- | --- | --- | --- |

| B10F-R01 | P2 | REVIEW-22（`docs/reviews/codex-claude-b10-fix-21de627-2026-09-24-1556z.md`） | 生成的 `TaskCancelled.cancel_requested` 是 `Literal[True] = True`（有默认值、非必填），缺字段的取消快照能通过 `Task.model_validate`，而 JSON Schema 会拒绝 | 契约修复，建议在 C10/C11 实现取消响应前完成：让生成模型把该字段设为必填，并补缺字段与 `exclude_unset` 的回归测试 |
| B10F-R02 | P3 | 同上 | `TaskNotCancellableError.details` 的三个分支没有 `additionalProperties: false`，`{stage, reason, secret}` 能通过 JSON Schema | 与 B10F-R01 一起修：三个分支加 `additionalProperties: false`，并补负例 |
| D08-P3 | P3 | PR #215 审查（Claude） | `chunking._render` 给窗口里的每个来源段落各拼一次 `section_path`；同一窗口里有多个短段落时，路径重复出现，抽取时多耗 token。D-13「在每块正文前拼上章节路径」对「块」的理解存在歧义 | D12 接入抽取时一并确认：每个窗口拼一次，还是每个来源段落拼一次 |
| E07-P3 | P3 | PR #217 审查（Claude） | `EmbeddingAdapter.embed` 末尾的 `if vector is not None` 过滤，一旦有向量漏填，结果会静默变短并与输入错位 | 改为断言全部填满；可在 E03 接入时顺手修 |

## 2026-09-26 E10 之后第一批：E11、H02、H12 并行（Claude）

[完整上下文](archive/tasks-2026-09.md#t062)

- E11 待决（详见交接）：`PREREQUISITE_CUES` 先修表述清单为本任务暂定；小节范围与实体表上限交 E12；关系抽取缓存键未定。

## 2026-09-26 PR #255 合并后：K01、K02 并行（Claude）

[完整上下文](archive/tasks-2026-09.md#t063)

  4. **E11 先修表述清单**：金标 `g-r03`（证据「基于栈的后进先出特性」）不含清单中的表述，E11 会按 `prerequisite_without_cue` 丢弃；是否把「基于」加入清单待实测召回后决定。审查同时指出「基础」「才能」偏宽。
  5. **E12/F13 须对同一小节产出的反向 `PREREQUISITE` 候选做环检测**（PR #255 审查意见，E11 不去重二元环）。
  6. **完整融合后重跑验收 7**：本次是简化融合（仅同名去重），main 上 E12/F13 的 `merging` 也还是直通（ADR-029）。E08～E10 融合接入后，把本章处理到 `awaiting_review`、导出草稿，按报告第 3 节重新抽样判定。
  7. **抽取改进（报告第 5 节）**：小节「3.3.5 栈与队列的比较」关系抽取因 4096 token 输出上限截断；21 条未命中金标关系中 12 条跨小节；`CONTAINS` 被用于「相关」关系（判错 2 条）。

## 2026-09-26 E11 之后主线：E12、F04、F06、F13（Claude）

[完整上下文](archive/tasks-2026-09.md#t064)

- E12 待决（详见交接）：任务快照与 SSE 尚未带 `chunks_done`/`chunks_failed`/`failed_chunks`（C11 接列）；模型调用结果缓存未实现，块中途崩溃会重新计费；小节实体表与提示词长度无上限；检查点保留期清理（§8.6）未实现；生产装配（`ExtractionToolkit` 的模型、输出上限、补漏开关）未接入启动入口；`merging` 阶段 worker 尚无任务承接。

- F13 已决（ArvinHan 2026-09-26，ADR-029）：`merging` 先用直通版（不做跨资料融合）；D-08 签收前自动写入的节点和关系状态一律 `draft`。F13 同时补上迁移 009 的 `course_locks` 与 `t6_seq`，F06 待决中的课程写锁表因此已有；`draft_revision+1` 仍归教师编辑（F08）。F13 待决：融合编排（E08～E10 接入 `merging`）无任务承接；D-08 签收后需重算状态；等锁超时消耗一次尝试。

## 2026-09-26 G 组：发布版本（Claude）

[完整上下文](archive/tasks-2026-09.md#t066)

- G01 待决：从 Neo4j/SQLite 读出可见草稿与修订的装载归 G04（P4～P7）；快照章节带 `parent_id`，而 Neo4j 章节与契约 `Chapter` 尚无此字段，章节层级落地时需同步（ADR-031）。

## 2026-09-26 K13 抽取消融（Claude）

[完整上下文](archive/tasks-2026-09.md#t073)

- 待决：结论只对简化融合、每组单次运行成立；完整融合接入后建议每组至少跑两次并做人工判定，再定生产配置。生产维持两阶段、补漏默认关闭。

## 2026-09-26 第九批并行：F10→F09、I01、J02、H06、H05、H08、K10（Claude）

[完整上下文](archive/tasks-2026-09.md#t077)

| 原子 ID | 状态 | 任务 | 负责人 | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- |

| I01 | SUPERSEDED（`main` 已合入 Codex 的 I01，PR #272；本批实现未采用） | 实现学习进度仓储 | ArvinHan（Claude） | `src/backend/app/repositories/progress.py`、`src/backend/migrations/011_progress.sql`、`tests/backend/test_i01.py` | 本批实现（提交 `9b9231e`，含读时投影与 46 个用例）在合入 `main` 时让位于 PR #272；投影逻辑可供 I02 参考 |

- 第九批待决（均需 ArvinHan）：ADR-047～054 签收；F10/F09 删除或合并后抽取重建同 ID 节点（F04 查 `merged_from` 或删除留墓碑）；关系是否加修订号（H08）；后端缺关系编辑路由 `/relations`（F06 仅服务层，H08 未联调）；H06 学生端资料名来源；J02 检索上限占位值；K10 compose 下 neo4j-admin 卷挂载与 F14 `--neo4j-backup-confirmed` 换接 K10 备份。

## 2026-09-26 F11 审核队列和单项处理（Claude）

[完整上下文](archive/tasks-2026-09.md#t079)

- F11 待决（需 ArvinHan）：ADR-060 签收（尤其「疑似重复」只用名称归一、不含向量相似；「确认保留」按节点永久生效；新增 `resolveReviewItem` 而不是借 `/relations`）；D-08 阈值定稿后是否把 E09 向量候选并入疑似重复栏。
### F11 独立审查与并行核查遗留（2026-09-26，协调者；不含已修项）

背景：F11 由另一会话的 PR #282 实现；本会话另派的独立实现已作废（SUPERSEDED），但两者都对 #282 做了独立核查，结论如下。已修项见下方「F11 审查修复」。以下均为**未修**、需后续任务或 ArvinHan 裁决的事项。

- **M2 CI 掩盖（中）**：`tests/backend/test_f11.py` 有 23 个真实 Neo4j 用例（`skipif` 依赖 `SMARTSKETCH_TEST_NEO4J_*`），而 `.github/workflows/ci.yml` 只跑 `pytest tests/backend -q` 且不设该 env、也无 Neo4j service 与 `tests/integration` job → CI 恒为 17 passed / 23 skipped 报绿；`docs/atomic-tasks.json` 的 F11 `verification_command` 同样无 env。仓库惯例是 live 用例放 `tests/integration`（F09/F10/J01/K10）。建议迁目录或给 CI 加 Neo4j service。
- **M3 审计缺口（中，跨任务）**：F12（ADR-061）只审计 F08 新建/修改/解锁、F09 删除、F10 合并五个入口。F11 的关系 approve/reject（`repositories/review.py`）与节点 reject 是**直接 Cypher**，不经这五个入口、也直接调 `bump_draft_revision` → 审核队列的图写入**不进审计表、不做 reconcile**，而规格「一致性」要求修改记录写入日志。需显式跟进项（或让 F11 接入 `audit.begin/commit`）。
- **M4 dismissals 永久且无撤销入口（中）**：`review_dismissals`（迁移 013）按 `kp_id`/关系对永久生效，没有 API 或界面可撤销；而 `kp_id` 是确定性派生 `derive_kp_id(course, task, candidate_key)`，`tasks.py` 明说重试返回**原 task_id** → 重跑抽取复用同一批 ID，「不是重复/确认保留」的记录会**静默抑制重建后的条目**（实测：dismiss 后删掉一方、再用同一 ID 建回，totals 仍为 0）。ADR-060 只写「留下的记录无害」，未覆盖该路径。

- **D-2 低置信度栏口径（中，口径/覆盖缺口）**：低置信度关系只按 `status == "low_confidence"`、**无数值阈值**；而 ADR-029/F13 已决「D-08 签收前自动写入的状态一律 `draft`」，`low_confidence` 只由 ADR-009 的成环降级产生（`services/graph/downgrade.py`）。后果：**未发生过成环降级的课程，该栏恒为空**，即使草稿里全是低置信度 AI 边；现有验收靠手工种 `low_confidence` 行证明，不代表真实数据。`specs/teacher-review-publish.md`「低置信度阈值」仍是待细化，D-08 签收后需回改。
- **D-3 孤立定义口径（低-中，需产品裁决）**：实现只按「没有未拒绝的相连边」，**不含「无章归属」**（与 F07 `GraphStats.isolated_count` 一致）。只挂 `chapter_id`、没有任何关系的节点会进孤立栏，教师「确认保留」后按节点 ID 永久压制。需要在两个自洽口径里选一个并写进规格。
- **D-4 新端点契约未声明 503（低）**：`GET /review` 与 `POST /review/actions` 的契约未声明 503，而实现（复用 `graph_nodes._run`）在 Neo4j 不可达时返回 503 `STORAGE_UNAVAILABLE`，交接也把 503 写进接口变更 → 契约/实现/交接三者不一致（`/graph` 同样未写 503，属既有惯例，非回归）。建议补可复用的 503 响应组件。
- **D-5 幂等判断顺序（低）**：「状态已是目标值 → `changed=false`」排在「仍在队列」判断之前，故「已 approved、但其后某端点被置 rejected」的关系再 approve 返回 200 而非 ADR-060 决定 7 的 404。
- **D-6 跨模块私有导入（低，建议）**：`api/review.py` 从 `api/graph_nodes.py` 导入私有 `_context`/`_run`，并为此改了后者（+3 行，其中 `isinstance(node, dict)` 分支现有调用方不可达）。建议把 `_context`/`_run` 上提到 `api/dependencies.py`（共享 adapter 的既定位置），F11 就不必动 F08/F12 的文件。**合并期已处理**：与 F12 的 `_run(request, access, ...)` 签名冲突已解，`api/review.py` 两处调用点已改传 `access`。
- **D-8 字段名（低）**：`similarity` 对 same_key/alias 恒为 1.0、对 containment 为有效字符比，实际只有三档语义、用途是排序；契约已注明，但字段名与 0～1 值域易被前端当相似度展示。建议改名或强化描述。
- **D-9 关系新增 `revision` 属性未登记（低）**：`repositories/review.py` 给关系写 `coalesce(r.revision,0)+1`，但 `docs/architecture.md` 的 Neo4j 模型段与契约 `Relation` 都未登记，事实上单方面定了 H08 的待决「关系是否加修订号」。
- **缺证据（低）**：无「空草稿队列 → 200 + 三栏空 + totals 全 0」用例；无「他课教师 → 403 `COURSE_FORBIDDEN`」用例（只测了本课学生 403）；无「队列不含已发布副本节点」的固化用例（结构上已排除：`_draft_scope` 硬编码 `version_id="draft"`，端点无 `version` 参数）。

## 2026-09-26 F12 图编辑审计日志（Claude）

[完整上下文](archive/tasks-2026-09.md#t080)

- F12 待决（需 ArvinHan）：ADR-061 签收；迁移号 012 若与并行 PR 冲突，合并前改为 main 最大号 + 1；审计读接口（教师查看历史）未分配任务；关系编辑（F06 路由未实现）与审核队列操作（F11）接入审计留给对应任务；脱敏只按模式匹配。

## 2026-09-26 H07 教师节点编辑面板（Claude）

[完整上下文](archive/tasks-2026-09.md#t081)

- H07 待决（需 ArvinHan）：ADR-062 签收；教师图谱编辑页无归属（挂载页由新补登的 H14「实现教师图谱编辑页」负责（D-17）；H11 是学生端浏览页，不挂本面板）；`REVISION_CONFLICT` 的 `details.current` 不含章节，采用最新内容时章节沿用本地值。

## 2026-09-26 H11 学生图谱和卡片视图（Claude）

[完整上下文](archive/tasks-2026-09.md#t082)

- H11 待决：课程内教师是否需要「以学生身份预览已发布版」（需详情接口加 `version` 参数）；详情响应不带版本号，读图与读详情之间发布新版本时可能不一致；原文阅读器（`locateSource`）与学生端资料名仍未落地（H06 待决）；未做真实浏览器冒烟。

## 2026-09-26 断点恢复批次：F11、F12、H07、H11、I02、J04、G08（Claude，协调者）

[完整上下文](archive/tasks-2026-09.md#t085)

- **需 ArvinHan 签收（本批累计）**：ADR-060～066 七条；ADR-061 的租约被夺窗口如何处置（当前选择如实记录、接受残留风险）与脱敏/只追加缺口是否本轮补；ADR-065 的「图证据块在闸门打开后可被引用」与「预算 0 块复用 `below_similarity_threshold`」两点；ADR-064 的 `user_id` 多余字段覆盖 `specs/identity-access.md` 相应条目（**已裁决 (A) 保持 422，ArvinHan 2026-09-27**）；I02 的 `reason="duplicate"` 登记（**ADR-064 全部已签收，ArvinHan 2026-09-27**）。

## 2026-09-27 J05 有证据问答生成（Claude 认领）

[完整上下文](archive/tasks-2026-09.md#t089)

- 待决（ArvinHan）：ADR-068 签收（输出上限 1024 暂定、`<<资料 n>>` 块头、0.25 秒超时容差）；`LLM_CHAT_FIRST_TOKEN_TIMEOUT_SECONDS` 尚无实现（适配器超时覆盖整条流）；提示效果待 K03 真实模型评测，付费调用需另行同意。

## 2026-09-27 J10 问答日志（Codex）

[完整上下文](archive/tasks-2026-09.md#t090)

| ID | 状态 | 范围 | 验收证据 |
| --- | --- | --- | --- |
| J10 | IMPLEMENTED / 验证通过，待 PR 复审 | `014_chat_logs.sql`、`chat_logs.py`、J07 问答路由/服务、`test_j10.py` | P2 后各终态写入唯一请求行；按课程/用户查询与统计；不保存回答或模型原始输出；写入时清理 30 天前记录。J07/J10 定向测试 12 passed，`verify.sh` 通过。 |

## 2026-09-27 K04 全链路性能测量（Codex）

[完整上下文](archive/tasks-2026-09.md#t091)

| ID | 状态 | 任务 | 分支 | 修改范围 | 验证 |
| --- | --- | --- | --- | --- | --- |
| K04 | IMPLEMENTED / 待实测与 PR 复审 | 固定约 2 万字样本的 worker 阶段耗时、token 与 SSE 问答测量 | `codex/k04-benchmark-pipeline` | `evaluation/benchmark_pipeline.py`、`tests/backend/test_k04.py`、`docs/handoffs/codex-k04.md` | J07 已合入；SSE 首字/终态与 p50/p95 定向测试 3 passed；真实服务测量待环境，`verify.sh` 因本机契约工具链/编码未通过，付费调用未执行 |

## 2026-09-27 I05 推荐查询 API（Claude 认领）

[完整上下文](archive/tasks-2026-09.md#t092)

- 待签收：ADR-069（图读已提交快照而非 Neo4j 副本；教师 403）。

## 2026-09-27 H09 审核队列与节点合并 UI（Claude 认领）

[完整上下文](archive/tasks-2026-09.md#t093)

- H09 待决（需 ArvinHan）：ADR-070 签收（三栏上下排列、合并先选主节点再确认、哪些处理后重读队列）。

## 2026-09-27 PR #264（G05+G06）独立审查四项遗留修复（Claude 认领）

[完整上下文](archive/tasks-2026-09.md#t094)

- 待决：孤儿副本与已提交版本缺副本仍只告警（处理归 K10）；`sweep` 只覆盖发布/回滚尝试的副本，§8.6 的块检查点与任务来源块保留期清理仍未接入同一调度（本轮范围外）。

## 2026-09-27 后端关系编辑接口：/relations 三个路由（Claude 认领）

[完整上下文](archive/tasks-2026-09.md#t095)

- 待决（需 ArvinHan 裁决，见 ADR-071 后果）：
  1. **契约未声明 503**：三条路由沿用既有图路由惯例返回 503 `STORAGE_UNAVAILABLE`，但 `api.v1.yaml` 的两条路径只声明 401/403/404/409/422。要么补契约（需另开契约变更），要么把 Neo4j 故障并入 500——本任务选择「不改契约、记差异」，与 F11 审查 D-4 同类。
  2. **两个未登记的领域 `reason`**：非 `PREREQUISITE` 自环报 422 `VALIDATION_ERROR` + `self_loop`；`InvalidRelationError` 兜底报 `invalid_relation`。`errors.v1.md` 要求领域 `reason` 先登记，契约真源本轮冻结。
  3. **改类型/方向会丢弃 `source_pairs`**：新身份 = 新的人工断言（保留 `confidence`/`status`，来源证据归零）；若希望改向后保留 AI 证据，需要另立实现（把块 ID 迁到新身份的 `source_pairs`）。
  4. **审计行语义**：关系行复用 `create`/`update`/`delete` 动作、`kp_id` 存 `rel_id`、修订号列 NULL，靠摘要的 `entity = "relation"` 区分（迁移 012 的 `action` 是数据库级闭集，新增取值要重建表）。若审计消费者需要一个显式的 `entity` 列，需另开迁移。
  5. **前后端未联调**：H14 的教师页仍用注入的假实现，真实 `/relations` 与页面组合未在浏览器里端到端验证（K05 教师主线 E2E 的依赖）。

## 2026-09-27 批次：J05/I05/H09 独立审查 + #264 遗留四项 + 后端关系接口（协调者，5 路并行）

[完整上下文](archive/tasks-2026-09.md#t096)

3. ADR-068～072 五条签收（含 J05 的 1024 输出上限与 0.25s 容差、I05 的图读已提交快照、H09 的数量口径、#264-R1 的 sweep 缺省启用与 3600 周期、#264-R4 的两种成功形状、关系接口的 503 未声明与 `source_pairs` 归零）。
4. 关系接口 5 项（503 未声明、两个未登记 `reason`、改向丢 `source_pairs`、审计行语义、**前后端未联调**）见上一节 ADR-071 待决。

## 2026-09-27 I06 掌握标记与推荐 UI（Claude，worktree `impl-i06`）

[完整上下文](archive/tasks-2026-09.md#t098)

- **需签收（ADR-075）**：清单验收条目 5 的字面表述「PUT progress 请求带 `graph_version`」与契约冲突——`updateProgress` 的请求体是 `additionalProperties: false` 的 `ProgressUpdate[]`，该操作 `query` 为 `never`，后端 `write_progress` 也无版本参数。实现改为「只在已显示版本上写 + 响应版本比对 + 422 重读」，**不自造字段**（自造字段会被契约拒绝，未声明查询参数会被服务端忽略而给出虚假安全感）。另需签收：学习接口未注入时页面静默退回 H11 原状；掌握标记三态（未开始/学习中/已掌握）直接写 `MasteryStatus`，不引入第四种状态或「跳过先修」操作。
- 待决：真实后端联调（I02/I05 已合入 `main`，本轮仅假 API 验证）交 K06 学生主线 E2E；推荐列表上限未在页面暴露（用服务端默认 10）；进度变化后继承来源（`inherited_from[]`）未在 UI 展示（契约已具备，是否需要展开待定）。

## 2026-09-27 J09 课程问答页（Codex）

[完整上下文](archive/tasks-2026-09.md#t099)

| ID | 状态 | 范围 |
| --- | --- | --- |
| J09 | REVIEWED / 待 CI 验证 | `src/frontend/src/views/ChatView.vue`、`src/frontend/src/composables/useChat.ts`、`src/frontend/src/components/ChatMarkdown.vue`：问答流展示、撤回、引用、历史、切课与版本标注。 |

## 2026-09-27 K06 / K09 / K11 / K12 与演示模型（Claude）

[完整上下文](archive/tasks-2026-09.md#t100)

- 本轮先写的 J08/J09/J10/K04/K05/I06 已被 Codex 同名 PR 先行合入，本分支已丢弃重复实现，只保留上述增量。
- **已签收**（ArvinHan，2026-09-27）：ADR-076（演示模型与 0.58 阈值）、ADR-077（门禁跳过白名单）、ADR-078（示例导入只增不删）。D-08 融合阈值仍待用户决定。
- PR #307 已于 2026-09-27 合并（main `8450256`）。
- 待人工：macOS 实测、`docker compose --profile app up` 真实守护进程验证（K08 遗留）、真实模型重跑 K02 验收 7 与 K04。详见 `docs/handoffs/claude-k06-k09-k11-k12.md`。

## 2026-09-27 前端改版（方向 A 工作台）+ 学生自助注册（Claude，新增任务）

[完整上下文](archive/tasks-2026-09.md#t102)

- 待决：G6 画布在 64 个节点时整体缩得很小、标签难读（改版前已存在，未在本任务处理）；是否需要关闭自助注册的部署开关（ADR-079 后果）。详见 `docs/handoffs/claude-frontend-redesign.md`。

## 2026-10-03 Claude 认领：冲刺计划 C（第三阶段：可靠性、性能与技术冻结）——用户已确认

[完整上下文](archive/tasks-2026-10.md#t107)

| ID | 状态 | 负责人 | 范围 | 验收 |
| --- | --- | --- | --- | --- |

| C02（B-QA-01） | IN_PROGRESS（13题真实终态/服务端与SSE达标；浏览器可见首字、v3+思考开启基线：2026-10-04 用户决定三项补测均不做，保持「未测」） | Codex（本地接手）；DeepSeek（真实轮） | 比较题截断离线定位、最小修法（策略先确认）、分段耗时、真实复测交接 | 出处与 15 秒不放宽；截断仍撤回；回归 |
| C03（B-PDF-01 / L16） | IN_PROGRESS（新两份PDF20.90/28.08秒已核；关闭思考MD抽取：2026-10-04 用户决定三项补测均不做，保持「未测」；慢段根因仍OPEN） | DeepSeek（真实轮）；Codex（本地复审） | 修复后 PDF 真实复测、阶段分解、60 秒最小优化 | 前后对照；不排除真实 AI 耗时 |

| C06 | IN_PROGRESS（本地完整门禁已通过；真实冻结待指标/人工签收） | Codex | 最终门禁、隔离从零复测、交接 | 整次 integration 实际 exit 0 |

## 2026-10-04 Codex 认领：计划 C 接手复审

[完整上下文](archive/tasks-2026-10.md#t108)

| ID | 状态 | 负责人/下一步 | 验收 |
| --- | --- | --- | --- |

| C-LEGACY-CREDENTIALS | OPEN（仅交接提示，未读取内容） | 原数据持有人 | 收紧旧测量口令文件权限、按需轮换，停止沿用硬编码口令/未知usage记0的旧脚本；不复制进新工区 |

## 2026-10-04 Codex：计划 C 真实结果接手

[完整上下文](archive/tasks-2026-10.md#t109)

| ID | 当前状态 | 下一步/判定边界 |
| --- | --- | --- |
| C-PERSIST-TRACE | OPEN（证据不足） | 6471ms只能定位run_persist_stage范围；现存日志缺阶段行；旧C03-1末段15.643秒根因仍未判定，未在本轮同幅重现不是已修 |
| C-QA-V3-BASELINE | NOT_EXECUTED（2026-10-04 用户决定三项补测均不做；结论只写「未测」，不能声称关闭思考带来的改善幅度） | 最小同13题v3思考开启未测；保守11调用118052，13调用+余量182056；建议增量185000/累计1030000仅提案，无授权不执行 |
| C-MD-THINKING-OFF | NOT_EXECUTED（用户决定不补测） | 关闭思考的新 Markdown 抽取未测；已有 MD 课程 QA 不是新 MD 抽取证据；PDF ≤60 秒不外推 |
| C-BROWSER-FIRST-TOKEN | NOT_EXECUTED（用户决定不补测） | 浏览器可见首字未测；SSE783～2927ms不替代页面首字 |

| C06-FREEZE | WAITING_USER_FREEZE / OPEN | 准确率已签收、三项补测决定不做；修复后由用户自行检查并决定冻结，当前不冻结 |

## 2026-10-09 Claude：前端体验审计与问答链路优化（UI-QA-01，用户确认方案）

[完整上下文](archive/tasks-2026-10.md#t133)

| ID | 状态 | 负责人 | 范围 | 验收 |
| --- | --- | --- | --- | --- |
| UI-QA-01 | 实现与自动化验收完成，待用户视觉签收（2026-10-09；review_status: ready_for_review） | Claude | 学生问答链路（提问 → 流式 → 已回答/资料未覆盖/未完成 → 出处 → 跳转图谱）与图谱画布键盘停靠点修正。文件：`src/frontend/src/views/ChatView.vue`、新增 `components/chat/AnswerCard.vue`、`composables/chatSources.ts`、`composables/useCopyFeedback.ts`、`composables/useFollowLatest.ts`、`components/ChatMarkdown.vue`、`components/SourceViewer.vue`（仅样式）、`components/AppIcon.vue`（新增 copy/info 图标）、`graph/a11y.ts` + `graph/lifecycle.ts`、`styles/ui.css`（清理问答段）、相关前端测试、`specs/grounded-qa.md`（新增「前端呈现」一节）、`specs/course-knowledge-graph.md`（画布键盘约定） | 不改后端、接口、契约、数据与权限；出处校验、`not_covered` 与服务错误分开、流式结束与撤回语义不变；既有 `data-test` 钩子保留。`type-check`、前端全量、`build`、`./scripts/verify.sh`、问答 E2E；1440×900/1280×800/768 前后对比截图，390 仅验证无溢出（用户 2026-10-09 决定：手机端不专门优化）；Tab 顺序、焦点可见、200% 缩放、减少动效；测试通过与浏览器验收分别报告 |

- 本轮不做、待确认（C 类或需新决定）：推荐理由里的“解锁度 1.0000”“按中性值 0.5 计，易学度 0.5000”由服务端 `reason` 生成，后端测试（`test_l14_reason.py`）与 `specs/learning-path.md` §4 要求前端原样展示，前端解析句子会脆弱，若要改写须先改服务端文案与规格；对话历史跨刷新保留（持久化与隐私）；示例问题（需要内容来源）；课程主页待审核数（需要新数据）；成员批量添加（新接口）。

## 2026-10-09 Claude：前端体验第二批（UI-BATCH2-01，用户指示逐个进行）

[完整上下文](archive/tasks-2026-10.md#t134)

| ID | 状态 | 负责人 | 范围 | 验收 |
| --- | --- | --- | --- | --- |
| UI-BATCH2-01 | 实现与自动化验收完成，待用户视觉签收（2026-10-09；review_status: ready_for_review） | Claude | 审计第二批候选逐项：① 成员移除行内二步确认；② 教师图谱“未保存离开前提示”（核查：已存在，只补回归测试）；③ 登录页直接打开不显示“未登录”提示；④ 教师图谱详情来源行排版与标题焦点框；⑤ 模型设置演示模式与重名控件（核查后**未改**，见下）；⑥ 资料上传框拖放与中文按钮；⑦ 课程概览页只保留一个主按钮。文件：`composables/useMembers.ts`、`views/MembersView.vue`、`router/index.ts`、`views/MaterialsView.vue`、`views/CoursesView.vue`、`styles/ui.css`、相关测试 | 不改后端、接口、契约、数据与权限；上传校验、成员授权、守卫对受保护页面的重定向不变；既有 `data-test` 钩子保留。前端类型检查/全量/构建、`verify.sh`、E2E；浏览器 1440/390（成员确认）及逐项实走；测试与浏览器分别报告 |

- ⑤ 核查结论：教师设置页的“通用模型 API”“向量模型 API”两张卡片本来就是带标题的 `section` 区域，重名控件（模型供应商、API Key、刷新模型列表、测试连接）在读屏里可由区域区分，且没有测试依赖这些控件名；演示模式下表单仍可填写——是否应整体禁用取决于服务端在演示模式下是否接受保存，属业务行为，**待你决定**，本批不改。

## 2026-10-08 Codex 认领：R1 后续验证失败修复

[完整上下文](archive/tasks-2026-10.md#t138)

- **风险状态：CLOSED，仅限 worker 网络 COMMIT 无界占用 SQLite 最终围栏**。DNS 执行器退出、一般进程停机、其他图入口、宿主暂停/存储异常仍在保证之外；原四项中严重程度发现及两个既有心跳故障测试未纳入本轮。全项目 `stage_c_status OPEN`、`technical_freeze NOT_PERFORMED` 保持原状态。

## 2026-10-05 STARTUP 实现验收（Codex）

[完整上下文](archive/tasks-2026-10.md#t144)

| 任务 | 当前状态 | 证据 / 剩余 |
|---|---|---|
| STARTUP-03～08（T1～6） | IMPLEMENTED / 本地回归已测 | 私有配置、实例控制、教师引导、发行编排、就绪/停启、认证向导；实机项另列 |
| STARTUP-09（T7） | LOCAL_VERIFIED / 实机OPEN | 真实合成卷整组/重复恢复通过；确认操作/源卷保留/根权限/WAL/完整租约回归通过，非用户业务库签收 |
| STARTUP-10（T8） | IMPLEMENTED / 未发行 | 三平台编译和打包测试通过；Windows/ARM 实机 OPEN；真实摘要未填写 |
| STARTUP-11（T9） | LOCAL_VERIFIED / PLATFORM_RELEASE_OPEN | 7fee1c8完整integration exit0、定向29/真实Docker3 PASS；独立复审未有完整clean结论；三平台正式包与发行验收仍OPEN |

## 2026-10-05 STARTUP-12：实际安装包与配置至登录验收

[完整上下文](archive/tasks-2026-10.md#t146)

负责人 Codex；状态 IN_PROGRESS。用户要求继续完整“双击→配置→启动→登录”，接续 STARTUP-10/11 的发行缺口，不重复已完成源码任务。

## 2026-10-05 STARTUP-14：下载后Mac入口Killed:9

[完整上下文](archive/tasks-2026-10.md#t148)

负责人Codex；状态IN_PROGRESS/发行签收OPEN。输入：用户Downloads实际包、PID44020错误；输出：已定位的签名/隔离证据、SIGKILL诊断回归、明确启动说明及交接。只读检查确认二进制SHA9116108b...与发布一致，unsigned且有com.apple.quarantine；spctl exit3/no usable signature，syspolicyd明确Gatekeeper rejection PID44020。不是Docker或个人API故障。本机可用Developer ID Application身份数0；完整分发修复需用户提供签名条件，不读取私钥。修复范围先补入口137条件诊断，不把提示修复冒充信任修复；不自动删quarantine、不更改Gatekeeper或用户配置、数据库，不重发镜像/替换Release附件。先写SIGKILL/成功/其他错误回归，运行定向测试与无.env副本verify.sh basic。未知平台和签收状态保持OPEN。

## 2026-10-06 STARTUP-15：Intel 下载包启动失败排查

[完整上下文](archive/tasks-2026-10.md#t149)

- 负责人：Codex；状态 IN_PROGRESS，仅定位，不改用户配置、容器、课程或发布版本。

## 2026-10-09 Claude：正式交付闭环检查（FORMAL-RELEASE-01，用户指示）

[完整上下文](archive/tasks-2026-10.md#t151)

- 待评估需求（用户 2026-10-09 提出，**未排期**）：① "软件启动后再填写向量模型"（向导不再要求向量）——现状：生产/个人模式下后端启动必须有系统级 `EMBEDDING_BASE_URL/API_KEY/MODEL`（`config.py` 校验），启动时还要初始化/校验系统向量空间（`services/startup.py`），启动器就绪判定包含 `EmbeddingSpaceMatches` 与 `VectorIndexesOnline`；因此是架构级改动而不是界面调整，需修订 ADR-081/092。② 除 Docker 桌面安装包外的服务器部署（多用户共享一台服务器）：现状无反向代理/TLS/域名、发行 compose 仅绑定 127.0.0.1、教师账号靠 CLI 创建、学生可自助注册；镜像仅 amd64。估算见对话，需用户先定服务器、域名/TLS、注册策略。

  - 仍未完成 / 待排期：Windows 实机验证（需 Windows + Docker Desktop 机器）；darwin-arm64 的镜像方案（多架构重建或接受模拟运行）与实机；签名与公证；Gatekeeper/SmartScreen 实测；真实业务数据的备份与恢复签收；冒烟测试泄漏 Docker 网络；`tests/tooling/test_stop_procs.py::test_grace_period_is_not_shortened_by_shell_seconds_rounding` 在本机 macOS 稳定失败（宽限期实测 0.01 秒，Linux CI 为绿）；`/health` 不覆盖「模型调用链就绪」；向导外修复错误向量维度的恢复流程；M7 并发下向量瞬时失败的真实环境复测。

- FORMAL-RELEASE-01 Release 已公开（2026-10-10，用户操作）：`rc-7f8a0cd` 作为**预发布**公开（`isDraft: false`、`isPrerelease: true`，2026-10-10T07:04:58Z），tag `rc-7f8a0cd` 指向 `21858897cfe07d5759126009cc520543f2ce8622`（PR #335 合并提交），附件为 `SmartSketch-rc-7f8a0cd-darwin-amd64.tar.gz`、`SmartSketch-rc-7f8a0cd-windows-amd64.zip` 与只列这两个包的 `SHA256SUMS`。仓库 `README.md` 已改为已发布状态，下载链接直接指向 tag 页面（预发布不会出现在 GitHub 的「最新版本」入口）。交付范围不变：Mac Intel 已实测；Windows 仅交叉编译、从未实机运行；Apple Silicon 与 Windows ARM 不提供；未签名未公证。
  - 仍待办：两个更早的旧草稿（2026-10-05 预览、2026-10-06 热修复预览）是否删除由用户决定；Windows 实机验证；Gatekeeper/SmartScreen 实测；签名与公证；`upgrade.json` 升级成功后未清理（无害）；冒烟测试泄漏 Docker 网络；`test_stop_procs` 在本机 macOS 稳定失败；测试里其他固定时长等待可能还有同类竞态；从预览版升级的路径只在一台真实安装上走通过一次。

- 当前待决补充（原节 09:45 记录）：受控出站代理支持、正式模式依赖用户保持可用网络出口的接受边界，尚无签收；向量自动重试已在后续修复实现。最新包未复测教师账号路径与业务闭环，沿用 `rc-e3b04b5` 的证据；签名/公证在最新验证记录中为用户决定不做。Safari、窄屏功能栏、注册校验出错后的整页视觉未覆盖。

## 2026-11-04 Claude 认领：青松明黄界面改版（UI-PINE-01）

[完整上下文](archive/tasks-2026-11.md#t153)

| ID | 状态 | 负责人 | 范围 | 验收 |
| --- | --- | --- | --- | --- |
| UI-PINE-01 | IN_PROGRESS（配色、Logo、外壳、登录/注册、页面与图谱页外围、学生继续学习主卡、三步式模型设置已完成并通过全量门禁；邀请码、向量卡片三步式、图谱工具轨合并未做） | Claude | 按设计预览 v3 改前端配色、Logo、外壳、登录/注册、图谱页外围、课程进入页、模型 API 页；图谱画布样式不变；不改接口与数据模型 | type-check、前端全量 vitest、build、`./scripts/verify.sh` 通过；演示环境截图走查；`data-test` 钩子保留 |

- 计划：`docs/superpowers/plans/2026-11-04-ui-pine-redesign.md`；分支 `claude/ui-pine-redesign`（本地，未推送）。
- 依赖与风险：多处前端测试断言样式类与文案，需随设计更新并写明原因；邀请码需新接口与迁移，单列 P6，先写规格与 ADR。

## 2026-11-05 Claude：代码结构审查与优化任务交接（CODE-STRUCT-REVIEW-01）

| ID | 状态 | 负责人 | 范围 | 验收 |
| --- | --- | --- | --- | --- |
| CODE-STRUCT-REVIEW-01 | DONE（只读审查，未改代码） | Claude | 统计代码/测试/文档结构，挑出适合 Codex 的高耗读、低决策优化任务 | 交接 `docs/handoffs/claude-code-structure-review-codex-handoff.md` |
| OPT-01 | DONE | Codex | `docs/tasks.md`（496 KB）与 `docs/decisions.md`（356 KB）归档瘦身；同步 ADR 唯一性测试 | 历史内容零丢失 diff；`verify.sh`；`AGENTS.md` §2 措辞改动需用户先确认 |
| OPT-02 | OPEN / 待认领（建议 Codex） | — | 测试中 31 处固定时长等待改为条件轮询；`test_stop_procs` macOS 稳定失败定位 | 改动文件连跑 20 次全绿；`verify.sh full` |
| OPT-03 | OPEN / 待认领（OPT-02 之后） | — | 后端测试重复辅助函数与迁移初始化收敛到 conftest/helpers | 用例总数不变；`verify.sh full` |
| OPT-04 | OPEN / 待认领 | — | 新增 `tests/INDEX.md`（任务 ID 命名测试 → 被测功能），不重命名文件 | 索引覆盖全部测试文件；`verify.sh` |
| OPT-05 | OPEN / 待认领（需 Neo4j） | — | services 中的 Cypher/SQL 下沉 repositories；`api/chat.py` 落库移入 service | 纯搬移；`verify.sh integration` |
| OPT-06 | OPEN / 可选（最后） | — | 大文件按职责拆分（compatible.py、extract_task.py、useMaterials.ts、StudentGraphView.vue） | 行为不变；对应全量测试与 type-check/build |

- OPT-01 输入：本分支 `ad63341` 的两份文档与用户批准原样引入的 PR #337 交接；输出：当前看板、ADR 索引、原文归档、依赖引用与验证记录。依赖/风险：其他会话也在认领 OPT，后续整合须逐条保留；本工作树不改其认领。
- OPT-01 验收：逐字重建 diff、`./scripts/verify.sh`、`pytest tests/tooling/test_worker_network_ci.py`、`git diff --check`；详见 [Codex 交接](handoffs/codex-opt-01.md)。AGENTS.md 全文保持不变；不推送、不开 PR。

- OPT-01 完成证据：历史重建两份 diff 均为 0 字节；basic PASS、tooling 3 PASS；306 个导航链接有效；`git diff --check` 通过。一次性脚本仅在 `/private/tmp/smartsketch-opt-01/`，未提交。

## 归档索引

| 原节标题 | 原文归档（文件与锚点） |
| --- | --- |
| 2026-10-06 Claude 认领：前端视觉升级——图谱工作台样板页 | [2026-10](archive/tasks-2026-10.md#t000) |
| 2026-10-02 Claude 认领：A10 一周参赛冲刺设计 | [2026-10](archive/tasks-2026-10.md#t001) |
| 2026-10-02 Claude 认领：冲刺计划 A（个人模型 API 与真实运行路径） | [2026-10](archive/tasks-2026-10.md#t002) |
| 2026-10-03 Claude 认领：计划 A 审查修复（D1–D3、N01–N08） | [2026-10](archive/tasks-2026-10.md#t003) |
| 2026-10-03 Claude 认领：冲刺计划 B（L11–L15 功能闭环）——功能交付已收尾，质量/性能验收有保留（2026-10-03） | [2026-10](archive/tasks-2026-10.md#t004) |
| 2026-09-28 Codex 认领：认证页动态图谱 | [2026-09](archive/tasks-2026-09.md#t005) |
| 2026-09-28 Codex 认领：登录页装饰知识图谱 | [2026-09](archive/tasks-2026-09.md#t006) |
| 2026-09-28 Codex 认领：登录页提示与视口布局 | [2026-09](archive/tasks-2026-09.md#t007) |
| K05 教师主线 E2E（Codex） | [2026-09](archive/tasks-2026-09.md#t008) |
| 2026-09-25 Codex 认领：F03 | [2026-09](archive/tasks-2026-09.md#t009) |
| 2026-09-25 并行认领批次 | [2026-09](archive/tasks-2026-09.md#t010) |
| 2026-09-25 Codex 认领：E07 | [2026-09](archive/tasks-2026-09.md#t011) |
| 2026-09-25 Codex 认领：C04 | [2026-09](archive/tasks-2026-09.md#t012) |
| 2026-09-25 Codex 认领：C03 | [2026-09](archive/tasks-2026-09.md#t013) |
| B12 进度与推荐契约（2026-09-25） | [2026-09](archive/tasks-2026-09.md#t014) |
| B11 图谱编辑与版本契约（2026-09-24） | [2026-09](archive/tasks-2026-09.md#t015) |
| 当前里程碑：M0 协作与应用骨架 | [2026-09](archive/tasks-2026-09.md#t016) |
| CI 配置 | [2026-09](archive/tasks-2026-09.md#t017) |
| 协作安全修复 | [2026-09](archive/tasks-2026-09.md#t018) |
| 下一里程碑：M1 课程资料到草稿图谱 | [2026-09](archive/tasks-2026-09.md#t019) |
| 架构审查与可执行拆分 | [2026-09](archive/tasks-2026-09.md#t020) |
| 待确认决策 | [2026-09](archive/tasks-2026-09.md#t021) |
| Claude 审查批次 | [2026-09](archive/tasks-2026-09.md#t022) |
| 原子任务认领（`docs/atomic-task-plan.md`） | [2026-09](archive/tasks-2026-09.md#t023) |
| A10 批 0：规划文档对齐 | [2026-09](archive/tasks-2026-09.md#t024) |
| A10 批 1：契约真源与生成链 | [2026-09](archive/tasks-2026-09.md#t025) |
| A1～A10 收尾（2026-09-24） | [2026-09](archive/tasks-2026-09.md#t026) |
| A10 批 1 补：问答规格加回契约门禁 | [2026-09](archive/tasks-2026-09.md#t027) |
| B01 前端构建与单页挂载 | [2026-09](archive/tasks-2026-09.md#t028) |
| B05 后端应用工厂与健康检查 | [2026-09](archive/tasks-2026-09.md#t029) |
| B07 契约门禁缺依赖假绿 | [2026-09](archive/tasks-2026-09.md#t030) |
| B06 后端设置加载与启动验证 | [2026-09](archive/tasks-2026-09.md#t031) |
| B02 前端测试配置 | [2026-09](archive/tasks-2026-09.md#t032) |
| B03 / B04 前端路由壳与课程上下文（并行） | [2026-09](archive/tasks-2026-09.md#t033) |
| B08 公共错误与来源契约 | [2026-09](archive/tasks-2026-09.md#t034) |
| B09 课程与资料 REST 契约 | [2026-09](archive/tasks-2026-09.md#t035) |
| B10 任务与 SSE 契约 | [2026-09](archive/tasks-2026-09.md#t036) |
| 2026-09-24 协作状态核对与 C08 认领 | [2026-09](archive/tasks-2026-09.md#t037) |
| B13 问答与事件契约 | [2026-09](archive/tasks-2026-09.md#t038) |
| C01 SQLite 连接与迁移运行器 | [2026-09](archive/tasks-2026-09.md#t039) |
| ADR-012 修订 3：快照谱系与共享提交序号（解除 B11 阻塞） | [2026-09](archive/tasks-2026-09.md#t040) |
| 2026-09-24 并行批次（Claude） | [2026-09](archive/tasks-2026-09.md#t041) |
| 2026-09-24 解析并行批次（Claude） | [2026-09](archive/tasks-2026-09.md#t042) |
| REQ-01 赛题抽取硬指标补登 | [2026-09](archive/tasks-2026-09.md#t043) |
| D-11 上传配置落地 | [2026-09](archive/tasks-2026-09.md#t044) |
| 2026-09-25 Codex 认领：C06 | [2026-09](archive/tasks-2026-09.md#t045) |
| C14 账号管理命令与演示账号种子 | [2026-09](archive/tasks-2026-09.md#t046) |
| 2026-09-25 并行批次（Claude） | [2026-09](archive/tasks-2026-09.md#t047) |
| F01 复用本地 Neo4j 环境并验证 | [2026-09](archive/tasks-2026-09.md#t048) |
| F02 Neo4j 驱动与作用域仓储 | [2026-09](archive/tasks-2026-09.md#t049) |
| FIX-MIGRATE-LEASE 迁移器租约检查与 C06 任务表不兼容（2026-09-25） | [2026-09](archive/tasks-2026-09.md#t050) |
| 审查遗留（2026-09-25 核对） | [2026-09](archive/tasks-2026-09.md#t051) |
| 2026-09-25 第二批并行（Claude） | [2026-09](archive/tasks-2026-09.md#t052) |
| 2026-09-25 第三批并行（Claude） | [2026-09](archive/tasks-2026-09.md#t053) |
| 2026-09-25 第四批（Claude） | [2026-09](archive/tasks-2026-09.md#t054) |
| 2026-09-25 第五批并行（Claude） | [2026-09](archive/tasks-2026-09.md#t055) |
| K07 本地 Neo4j 环境启停脚本 | [2026-09](archive/tasks-2026-09.md#t056) |
| 2026-09-25 第六批并行（Claude） | [2026-09](archive/tasks-2026-09.md#t057) |
| TD 技术债四项（2026-09-25，Claude） | [2026-09](archive/tasks-2026-09.md#t058) |
| 2026-09-25 第七批并行（Claude） | [2026-09](archive/tasks-2026-09.md#t059) |
| 2026-09-25 第八批并行（Claude） | [2026-09](archive/tasks-2026-09.md#t060) |
| 2026-09-26 图谱构建主线：E10 认领（Codex） | [2026-09](archive/tasks-2026-09.md#t061) |
| 2026-09-26 E10 之后第一批：E11、H02、H12 并行（Claude） | [2026-09](archive/tasks-2026-09.md#t062) |
| 2026-09-26 PR #255 合并后：K01、K02 并行（Claude） | [2026-09](archive/tasks-2026-09.md#t063) |
| 2026-09-26 E11 之后主线：E12、F04、F06、F13（Claude） | [2026-09](archive/tasks-2026-09.md#t064) |
| 2026-09-26 F07 图谱读取（Claude） | [2026-09](archive/tasks-2026-09.md#t065) |
| 2026-09-26 G 组：发布版本（Claude） | [2026-09](archive/tasks-2026-09.md#t066) |
| 2026-09-26 H03 图谱适配（Claude） | [2026-09](archive/tasks-2026-09.md#t067) |
| 2026-09-26 可开工清单与 issue 同步（Claude，基线 `main@95d5c9a`） | [2026-09](archive/tasks-2026-09.md#t068) |
| 2026-09-26 F08 教师节点编辑与人工编辑锁（Claude） | [2026-09](archive/tasks-2026-09.md#t069) |
| 2026-09-26 G07 发布版本解析器（Claude） | [2026-09](archive/tasks-2026-09.md#t070) |
| 2026-09-26 H04 G6 画布生命周期（Claude） | [2026-09](archive/tasks-2026-09.md#t071) |
| 2026-09-26 F14 离线重新向量化（Claude） | [2026-09](archive/tasks-2026-09.md#t072) |
| 2026-09-26 K13 抽取消融（Claude） | [2026-09](archive/tasks-2026-09.md#t073) |
| 2026-09-26 K08 应用容器（Claude） | [2026-09](archive/tasks-2026-09.md#t074) |
| 2026-09-26 I01 学习进度仓储（Codex 认领） | [2026-09](archive/tasks-2026-09.md#t075) |
| 2026-09-27 J06 引用和终态校验（Codex） | [2026-09](archive/tasks-2026-09.md#t076) |
| 2026-09-26 第九批并行：F10→F09、I01、J02、H06、H05、H08、K10（Claude） | [2026-09](archive/tasks-2026-09.md#t077) |
| 2026-09-26 J01 发布来源向量检索（Claude） | [2026-09](archive/tasks-2026-09.md#t078) |
| 2026-09-26 F11 审核队列和单项处理（Claude） | [2026-09](archive/tasks-2026-09.md#t079) |
| 2026-09-26 F12 图编辑审计日志（Claude） | [2026-09](archive/tasks-2026-09.md#t080) |
| 2026-09-26 H07 教师节点编辑面板（Claude） | [2026-09](archive/tasks-2026-09.md#t081) |
| 2026-09-26 H11 学生图谱和卡片视图（Claude） | [2026-09](archive/tasks-2026-09.md#t082) |
| 2026-09-26 J04 检索合并与上下文预算（Claude） | [2026-09](archive/tasks-2026-09.md#t083) |
| 2026-09-26 G08 发布时补齐文本块向量（Claude，新增任务） | [2026-09](archive/tasks-2026-09.md#t084) |
| 2026-09-26 断点恢复批次：F11、F12、H07、H11、I02、J04、G08（Claude，协调者） | [2026-09](archive/tasks-2026-09.md#t085) |
| 2026-09-26 I02 掌握标记 API（Claude 认领） | [2026-09](archive/tasks-2026-09.md#t086) |
| 2026-09-27 G08 遗留修复：向量索引、P9 核对与按版本补齐（Claude） | [2026-09](archive/tasks-2026-09.md#t087) |
| 2026-09-27 H14 教师图谱编辑页（Claude 认领） | [2026-09](archive/tasks-2026-09.md#t088) |
| 2026-09-27 J05 有证据问答生成（Claude 认领） | [2026-09](archive/tasks-2026-09.md#t089) |
| 2026-09-27 J10 问答日志（Codex） | [2026-09](archive/tasks-2026-09.md#t090) |
| 2026-09-27 K04 全链路性能测量（Codex） | [2026-09](archive/tasks-2026-09.md#t091) |
| 2026-09-27 I05 推荐查询 API（Claude 认领） | [2026-09](archive/tasks-2026-09.md#t092) |
| 2026-09-27 H09 审核队列与节点合并 UI（Claude 认领） | [2026-09](archive/tasks-2026-09.md#t093) |
| 2026-09-27 PR #264（G05+G06）独立审查四项遗留修复（Claude 认领） | [2026-09](archive/tasks-2026-09.md#t094) |
| 2026-09-27 后端关系编辑接口：/relations 三个路由（Claude 认领） | [2026-09](archive/tasks-2026-09.md#t095) |
| 2026-09-27 批次：J05/I05/H09 独立审查 + #264 遗留四项 + 后端关系接口（协调者，5 路并行） | [2026-09](archive/tasks-2026-09.md#t096) |
| 2026-09-27 H10 发布历史和回滚 UI（Codex 认领） | [2026-09](archive/tasks-2026-09.md#t097) |
| 2026-09-27 I06 掌握标记与推荐 UI（Claude，worktree `impl-i06`） | [2026-09](archive/tasks-2026-09.md#t098) |
| 2026-09-27 J09 课程问答页（Codex） | [2026-09](archive/tasks-2026-09.md#t099) |
| 2026-09-27 K06 / K09 / K11 / K12 与演示模型（Claude） | [2026-09](archive/tasks-2026-09.md#t100) |
| 2026-09-27 一键启动演示环境（Claude，新增任务） | [2026-09](archive/tasks-2026-09.md#t101) |
| 2026-09-27 前端改版（方向 A 工作台）+ 学生自助注册（Claude，新增任务） | [2026-09](archive/tasks-2026-09.md#t102) |
| 2026-10-01 dev-up.sh 启动诊断：Neo4j 起不来时说清原因（Claude，新增任务） | [2026-10](archive/tasks-2026-10.md#t103) |
| 2026-10-03 Codex 接手计划 B（c85ee53） | [2026-10](archive/tasks-2026-10.md#t104) |
| 2026-10-03 Codex 认领：第二阶段收尾（96f3885） | [2026-10](archive/tasks-2026-10.md#t105) |
| 2026-10-03 Codex：第三阶段启动交接 prompt | [2026-10](archive/tasks-2026-10.md#t106) |
| 2026-10-03 Claude 认领：冲刺计划 C（第三阶段：可靠性、性能与技术冻结）——用户已确认 | [2026-10](archive/tasks-2026-10.md#t107) |
| 2026-10-04 Codex 认领：计划 C 接手复审 | [2026-10](archive/tasks-2026-10.md#t108) |
| 2026-10-04 Codex：计划 C 真实结果接手 | [2026-10](archive/tasks-2026-10.md#t109) |
| 2026-10-04 Claude 认领：计划 C 验收收尾（stage_c_status: OPEN，technical_freeze: NOT_PERFORMED） | [2026-10](archive/tasks-2026-10.md#t110) |
| 2026-10-04 Codex 认领：计划 C 验收收尾复审（54a7c67） | [2026-10](archive/tasks-2026-10.md#t111) |
| 2026-10-04 Codex 认领：验收复审四项修复与本机检查入口 | [2026-10](archive/tasks-2026-10.md#t112) |
| 2026-10-04 Codex：全站向量 API 网页配置设计 | [2026-10](archive/tasks-2026-10.md#t113) |
| 2026-10-04 Codex 认领：最新结果 GitHub 集成 | [2026-10](archive/tasks-2026-10.md#t114) |
| 2026-10-08 Codex：课程列表与模型设置 UI | [2026-10](archive/tasks-2026-10.md#t115) |
| 2026-10-08 Codex：剩余页面 UI 统一 | [2026-10](archive/tasks-2026-10.md#t116) |
| 2026-10-08 Codex：模型供应商与自动发现 | [2026-10](archive/tasks-2026-10.md#t117) |
| 2026-10-08 Codex：资料上传排版优化 | [2026-10](archive/tasks-2026-10.md#t118) |
| 2026-10-08 Codex：审核页面去重与排版 | [2026-10](archive/tasks-2026-10.md#t119) |
| 2026-10-08 Codex：课程成员排版 | [2026-10](archive/tasks-2026-10.md#t120) |
| 2026-10-08 Codex：登录页书页与知识插画 | [2026-10](archive/tasks-2026-10.md#t121) |
| 2026-10-08 Codex：登录提示浮动 | [2026-10](archive/tasks-2026-10.md#t122) |
| 2026-10-08 Codex：学生图谱与问答体验 | [2026-10](archive/tasks-2026-10.md#t123) |
| 2026-10-08 教师向量模型配置 | [2026-10](archive/tasks-2026-10.md#t124) |
| 2026-10-08 教师图谱视口修复 | [2026-10](archive/tasks-2026-10.md#t125) |
| 2026-10-08 图谱右下角按钮说明 | [2026-10](archive/tasks-2026-10.md#t126) |
| 2026-10-08 教师图谱圆角卡片 | [2026-10](archive/tasks-2026-10.md#t127) |
| 2026-10-09 当前状态移交Claude | [2026-10](archive/tasks-2026-10.md#t128) |
| 2026-10-08 Claude：前端复审与 CI 修复（基线 PR #323 head f76020f） | [2026-10](archive/tasks-2026-10.md#t129) |
| 2026-10-08 Claude：教师图谱首屏总览与径向布局（用户确认方案） | [2026-10](archive/tasks-2026-10.md#t130) |
| 2026-10-09 Claude：教师图谱节点类型图例与总览标签提示（用户选定 1、2） | [2026-10](archive/tasks-2026-10.md#t131) |
| 2026-10-09 Claude：前端优化批次 3（用户选定 3–7，电脑端优先） | [2026-10](archive/tasks-2026-10.md#t132) |
| 2026-10-09 Claude：前端体验审计与问答链路优化（UI-QA-01，用户确认方案） | [2026-10](archive/tasks-2026-10.md#t133) |
| 2026-10-09 Claude：前端体验第二批（UI-BATCH2-01，用户指示逐个进行） | [2026-10](archive/tasks-2026-10.md#t134) |
| 2026-10-08 Codex 认领：R1 worker 旧租约图提交防护 | [2026-10](archive/tasks-2026-10.md#t135) |
| 2026-10-08 Codex 认领：R1 提交传输截止补充设计 | [2026-10](archive/tasks-2026-10.md#t136) |
| 2026-10-08 Codex 认领：R1 截止补充实施计划 | [2026-10](archive/tasks-2026-10.md#t137) |
| 2026-10-08 Codex 认领：R1 后续验证失败修复 | [2026-10](archive/tasks-2026-10.md#t138) |
| 2026-10-09 Codex 认领：PR #324 冲突与 CI 失败修复 | [2026-10](archive/tasks-2026-10.md#t139) |
| 2026-10-09 Codex 认领：非法枚举输入 HTTP 500 | [2026-10](archive/tasks-2026-10.md#t140) |
| 2026-10-04 Codex 认领：STARTUP-01 跨平台双击入口与安装向导设计 | [2026-10](archive/tasks-2026-10.md#t141) |
| 2026-10-04 Codex 认领：STARTUP-02 启动方案实施计划 | [2026-10](archive/tasks-2026-10.md#t142) |
| 2026-10-04 Codex：STARTUP 实施（本会话执行已批准） | [2026-10](archive/tasks-2026-10.md#t143) |
| 2026-10-05 STARTUP 实现验收（Codex） | [2026-10](archive/tasks-2026-10.md#t144) |
| 2026-10-05 STARTUP 收尾：本地验证通过，平台／发行未签收 | [2026-10](archive/tasks-2026-10.md#t145) |
| 2026-10-05 STARTUP-12：实际安装包与配置至登录验收 | [2026-10](archive/tasks-2026-10.md#t146) |
| 2026-10-05 STARTUP-13：GitHub Release下载测试草稿 | [2026-10](archive/tasks-2026-10.md#t147) |
| 2026-10-05 STARTUP-14：下载后Mac入口Killed:9 | [2026-10](archive/tasks-2026-10.md#t148) |
| 2026-10-06 STARTUP-15：Intel 下载包启动失败排查 | [2026-10](archive/tasks-2026-10.md#t149) |
| 2026-10-06 STARTUP-16：启动器热修复与新版草稿 Release | [2026-10](archive/tasks-2026-10.md#t150) |
| 2026-10-09 Claude：正式交付闭环检查（FORMAL-RELEASE-01，用户指示） | [2026-10](archive/tasks-2026-10.md#t151) |
| 2026-11-02 Claude：决赛前全流程走查（WALKTHROUGH-20261102） | [2026-11](archive/tasks-2026-11.md#t152) |
| 2026-11-04 Claude 认领：青松明黄界面改版（UI-PINE-01） | [2026-11](archive/tasks-2026-11.md#t153) |
| 2026-11-05 Claude → Codex 交接：邀请码、图谱悬停卡顿、全局优化重构 | [2026-11](archive/tasks-2026-11.md#t154) |
| 2026-11-05 Codex：GRAPH-HOVER-01 悬停性能修复 | [2026-11](archive/tasks-2026-11.md#t155) |
| 2026-11-05 Codex：INVITE-01 课程邀请码 | [2026-11](archive/tasks-2026-11.md#t156) |
| 2026-11-05 Codex：REFACTOR-01 行为保持重构 | [2026-11](archive/tasks-2026-11.md#t157) |
| 2026-11-05 Claude：课程之外的页面去掉侧栏（UI-NORAIL-01） | [2026-11](archive/tasks-2026-11.md#t158) |


## 2026-11-10 Codex 认领：OPT-06 大文件按职责拆分

- 状态 **DONE_LOCAL**；负责人 Codex；依赖核查后用户已明确允许在隔离分支本地整合 OPT-03/05、验证后继续，暂不推送或合并远端 PR。本地整合基线 `ec92026`，工作区 `opt-06-responsibility-split/SmartSketch-main`。
- 输入：审查分支 `claude/code-structure-review-handoff-49e73a` 的原交接 OPT-06、OPT-03/05 交接、任务/图谱/路径规格；整合前基线 `99c1f01`。
- 依赖核查（2026-11-10）：OPT-03 本地 `36c1f92` 已验收，GitHub 未找到对应分支或 PR；OPT-05 [PR #339](https://github.com/arvinhanye/SmartSketch/pull/339) 为 open / merged=false，目标为底座分支；底座 [PR #338](https://github.com/arvinhanye/SmartSketch/pull/338) 也未合并。整合前 HEAD 含 OPT-05、不含 OPT-03。原交接的远端合入条件未满足；已由用户明确授权本地整合并完成整合基线 full 验证。
- 输出范围：`compatible.py`、`extract_task.py`、`useMaterials.ts`、`StudentGraphView.vue` 分为四项独立交付；旧入口/导出名保留，不改行为，每个原候选文件一个 PR 范围。
- 风险：Python 导入兼容/循环依赖、网络资源释放、worker 事务与租约、前端请求/SSE 生命周期、响应式及焦点/布局；`codex/extraction-perf` 同时修改 `extract_task.py`，本轮已核查并排除，后续合入时重查。
- 验收：各项最小相关回归及对应后端/前端全量，`./scripts/verify.sh`，前端 type-check/build，Vue 同视口截图与交互走查，最终 diff；命令与分项范围见 `docs/superpowers/plans/2026-11-10-opt-06-responsibility-split.md`。
- 已决：用户确认允许本地整合后继续，不等待远端合入；暂不推送或合并远端 PR。四项分别保留本地叠加分支与独立提交范围。核查证据和验证记录见 `docs/handoffs/codex-opt-06.md`。

- OPT-06A：AI 兼容客户端拆分；44 定义/30 签名核对通过，定向 413 passed，后端 full 4264 passed / 27 登记 skip，exit 0；最终共用 basic exit 0，独立审查无可操作问题；本地验收完成。

- OPT-06C：材料页纯函数/类型拆分；41 声明/14 导出核对通过，定向 95 passed；前端 full 82 文件 / 1375 passed，type-check/build exit 0；最终共用 basic exit 0，独立审查无可操作问题；本地验收完成。

- OPT-06D：学生图谱页面拆分；81 声明、模板/样式核对通过，定向 135 passed；前端 full 82 文件 / 1375 passed、type-check/build exit 0，四种宽度浏览器走查通过；最终共用 basic exit 0，独立审查无可操作问题；本地验收完成。

- OPT-06B：worker 五职责拆分，60 定义/47 签名核对通过，定向 87 passed；后端 full 4264 passed / 27 登记 skip、共用 basic exit 0，独立审查无可操作问题；本地验收完成。

- 最终收尾：整合基线 full exit 0；A/B 后端 full 各 4264 passed / 27 登记 skip；C/D 前端 full 各 82 文件 / 1375 passed，type-check/build 通过；最终 basic exit 0。Chrome 四宽度 8/8 截图逐像素一致、交互通过，独立最终审查无可操作问题。实现提交 A `7cccaaa`、C `936b41e`、D `3974731`、B `76d1fd7`；相邻 base 与证据见 `docs/handoffs/codex-opt-06.md`。无推送/远端 PR 操作，EXTRACT-PERF 重叠留待其整合时处理。

## 2026-11-05 Codex：代码结构优化 OPT-04 测试索引

| ID | 状态 | 负责人 | 分支 / 基线 | 范围与验收 |
| --- | --- | --- | --- | --- |
| OPT-04 | DONE（本地未提交） | Codex | `codex/opt-04-test-index` / `ad63341` | `tests/INDEX.md` 覆盖 224 文件（backend 115 / frontend 82 / integration 27）；完整性测试 1 passed，临时正反例 6/6 符合预期；`./scripts/verify.sh` basic exit 0；交接 `docs/handoffs/codex-opt-04.md` |

- 输入：`claude/code-structure-review-handoff-49e73a@0796917` 的 `docs/handoffs/claude-code-structure-review-codex-handoff.md` OPT-04 节，以及当前测试文件的头部文档字符串、import、describe；该交接尚未合入本基线，已从本地分支读取。
- 输出与文件所有权：Codex 唯一写入 `tests/INDEX.md`、`tests/tooling/test_test_index.py`、本节与 `docs/handoffs/codex-opt-04.md`；不重命名或修改已有测试。
- 依赖与风险：描述/规格关联无明确依据时标「待确认」；索引限定 `tests/backend/test_*.py`、`tests/frontend/*.test.ts`、`tests/integration/test_*.py`。若 OPT-03 同期合入，合并后重新核对来源并生成索引，再跑完整性测试。
- 验证命令：`python3 -m pytest tests/tooling/test_test_index.py -q`、`./scripts/verify.sh`（默认 basic）、`git diff --check`；使用仓库已有 Python 3.11 虚拟环境。不推送、不开 PR。
- 验收证据：索引与三个匹配范围双向一致；来源不足的关联与功能保留「待确认」；原有测试零改动、零重命名。完整性测试在缺少索引时先失败，最终 1 passed；临时样例验证漏项、失效文件、重复项、错误链接和无效格式均被拒绝。basic 契约门禁及 25 项负例通过（仅 pytest 缓存受沙箱限制警告）；日志 `/private/tmp/opt04-verify.log`。
- OPT-03 同步：本分支基线未包含 OPT-03，本轮结束时本地分支/提交记录未检出同期合入；未自行合并其他任务。若后续合并 OPT-03，按交接重新核对头部/import/describe、重生成索引并复跑完整性测试与 basic。

## 2026-11-05 Claude → Codex 交接：图谱生成提速（EXTRACT-PERF-01）

- 用户反馈图谱生成仍慢。Claude 读代码与 L02 实测（141.7 秒：抽取 94.4、merging 45.7）后的初判：块阶段与小节关系阶段之间有屏障；块过小导致调用多、并发上限仅 4；merging 慢段根因仍 OPEN（已有 `persist steps` 日志未被分析）；发布向量化逐批串行。
- 交接稿：`docs/handoffs/claude-to-codex-extraction-perf.md`；prompt：`docs/handoffs/claude-to-codex-extraction-perf.prompt.md`。先用假供应商测量；只做不影响抽取结果的优化；合并小块、默认关闭思考、合并调用等影响准确率的方案交用户决定；真实复测需用户确认预算。

- Codex 认领：DONE_SCOPED（按用户确认范围交付生成提速；图库与发布优化后续，真实模型验收仍待复测）；负责人 Codex；分支 `codex/extraction-perf`，隔离 worktree，基线 `ad63341`。起步时OPT-05尚未提交，按交接 §1 未编辑发布向量化文件。源工作区全部改动保留。
- 输入：本交接、L02 报告、任务/图谱规格与 ADR-011/080/082/089/090。输出：固定 8 秒假供应商基线、逐项收益与回归测试、性能报告和 `codex-extraction-perf.md`。
- 执行：先测量；再逐项先红测试→最小优化→复测→全量后端/basic 验证→独立本地提交。并发 4/8 先实验覆盖，再按下方用户决定改默认8；P2只做离线评估。
- 风险/依赖：已有 Python/Node 环境、隔离 SQLite/Neo4j、本地假供应商；取消/失败阈值/接管/租约/凭据语义和模型输入保持。真实模型调用与默认配置变化须用户决定。
- 验证：`scripts/verify/backend.sh full`、`./scripts/verify.sh`；涉及 Neo4j 写入运行 integration；最终差异检查。未推送、不开 PR、不合并。
- 用户决定（2026-11-05）：采用保守去屏障方案，实体块优先；仅在剩余块全部失败仍不超阈值且有空位时提前派发已就绪小节，保留全部既有断言。并发/调度变更前新增确定性交错回归。
- P1-1 已验证：新增13项确定性交错回归，与原E12合计57 PASS；全后端4270 PASS/27登记SKIP，basic PASS。均匀8秒假供应商暖轮抽取65.450→64.752秒；早关系交叠0.160秒，31次请求及归一化图摘要相同。总耗时76.157→72.491秒中图库波动不能计为调度收益；冷轮异常及复跑均保留。证据见 `evaluation/reports/extraction-perf-2026-11.md`、`docs/handoffs/codex-extraction-perf.md`。
- 用户决定（2026-11-05）：并发8实验冷/暖轮58.901/44.871秒，抽取33.324/33.429秒、图摘要一致；批准默认 `LLM_MAX_CONCURRENCY=8`，保留环境变量覆盖，独立配置提交。真实429与准确率尚未付费复测。
- 用户决定（2026-11-05）：本轮先交付生成提速；发布向量化登记后续待办，等待OPT-05完成提交后接续。原工作区未提交文件完全保留，本轮不碰发布相关文件。
- 默认8落地复测：从应用缺省值读取8，冷轮52.388秒、暖轮41.172秒；抽取33.167/32.952秒，31次调用与原归一化图SHA相同。实际池上限/环境覆盖测试先1红1绿，改后连同调度/E12共59 PASS；本项全后端4272 PASS/27登记SKIP、gate PASS（1184.07秒），basic PASS。独立提交 `efb866c`；调度提交 `507f609`。
- P1-3定位：新增逐查询PROFILE证据，SQLite锁为毫秒、图库写入已批量且命中唯一索引，主要时间在服务端首结果返回前；冷暖差异显著，未证明安全有效的生产修法。用户于2026-11-05明确决定本轮交付生成提速，图库根因与修复登记后续专项 `GRAPH-PERSIST-PERF-01`；不标为已修复。
- 当前交付边界：生成代码两项及本地验证完成；真实≤60秒/准确率尚未付费复测，B-QUALITY-01/B-EVAL-01原验收状态不变。P1-5按用户决定后续；P2默认分块、思考、合并调用不变。性能报告含完整分解、每项收益、异常冷轮和P2调用数评估。

## GRAPH-PERSIST-PERF-01：图库持久化慢段专项

- 状态：OPEN（待认领，未启动）；来源：用户2026-11-05决定从EXTRACT-PERF-01转后续专项。
- 输入：`evaluation/reports/extraction-perf-2026-11.md`、`evaluation/raw/extraction-perf/persist-profile-summary.json`及冷轮超时/续跑证据；开始前核对届时基线与相关文件所有权。
- 范围：在可记录的负载条件下复测冷暖查询，区分规划、执行、传输与环境因素；先证明根因和可安全修复点，再实施不改图内容、DAG校验、双租约及提交围栏语义的优化。不凭冷暖差值宣称代码收益，不调大截止时间掩盖问题。
- 验收：可复现的分步耗时与前后收益、图内容一致、相关故障回归；改代码前先补复现，改Neo4j写入时运行integration，并运行backend full及`./scripts/verify.sh`。不调用付费模型，真实复测另行确认预算。
