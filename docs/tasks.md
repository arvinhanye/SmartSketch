# 任务看板

> **R1 最新状态（2026-10-09）**：PR #324 已整合 main 并消除文档/ADR 冲突；代码 head `36b421e` 的 push/pull_request 两轮 8 项 CI 全部 SUCCESS，含真实网络/恢复和 E2E。worker 围栏限定风险 **CLOSED**；用户已授权「CI通过就合并PR」，按最终 head 全绿门禁合入 main，最终合并结局以 PR 状态/提交为准。不部署或技术冻结；全项目 stage_c_status OPEN、technical_freeze NOT_PERFORMED 不变。验收见末节及 `docs/handoffs/codex-pr324-conflict-ci-repair.md`。

> **当前状态（2026-10-04，GitHub 主线集成）**：人工准确率已签收，方式为 arvin 逐条复核后采纳辅助判定，非独立盲判；stage_c_status **OPEN**，technical_freeze **NOT_PERFORMED**。用户要求先修复并自行检查，再决定冻结。关闭思考 Markdown 抽取、浏览器可见首字、v3 + 思考开启基线三项按用户决定不执行，均为未测。旧接手/初始交接的“未签收”“待补测决定”只作历史记录；计划A/B/C与四项验收修复已通过#317、#319、#318合入GitHub main；代码集成不是技术冻结。当前依据以末节与 `docs/handoffs/codex-plan-c-github-integration.md` 为准。


## 2026-10-06 Claude 认领：前端视觉升级——图谱工作台样板页

| ID | 状态 | 负责人 | 范围 | 验收 |
| --- | --- | --- | --- | --- |
| UI-GRAPH-PILOT-01 | IN_PROGRESS（任务1–16与用户批准的详情局部修正已实施；任务17剩余验收待做；用户2026-10-07已授权提交与开PR，以Draft发布） | Claude（设计）/ Codex（实施） | 学生图谱页作为首个样板：暗色外壳 + Kumu 式浅色画布；左说明面板合并详情；`src/frontend/preview/`（隔离预览，不进生产构建）；确认后再改 `App.vue`、`StudentGraphView.vue`、`GraphToolbar.vue`、`Recommendations.vue`、`KnowledgeDetail.vue`、`GraphCanvas.vue`、`graph/adapter.ts`、`graph/lifecycle.ts`、新增 tokens/顶栏/图标组件及相关前端测试 | 不改业务流程、契约与接口；教师审核/发布、学生掌握状态与推荐、来源、`not_covered` 与服务错误的区分完整保留；相同视口前后截图（1440×900、1280×800、768、390）；`npm --prefix src/frontend run type-check`、前端全量测试、`build`、`./scripts/verify.sh`；浏览器走查键盘、焦点、200% 缩放、减少动效 |

- 设计规格：`docs/superpowers/specs/2026-10-06-graph-workbench-design.md`（方向与规格已确认，2026-10-07）。
- 实施计划：`docs/superpowers/plans/2026-10-07-graph-workbench-pilot.md`（17 个任务：纯函数模块 → 画布样式与增强 → 页面层 → 暗色外壳 → 验收与收尾；含与规格不一致处的差异表与未验证清单）。执行方式（子代理逐任务 / 本会话内联）待用户选择；提交、推送、PR 仅在用户明确指示后做。
- 第二批（其余页面推广）计划：`docs/superpowers/plans/2026-10-07-ui-rollout-batch2.md`（2026-10-07，仅计划设计、未实现；沿用 Linear/Kumu/NotebookLM/Bloom/Linkurious/Obsidian 参考。阶段 R1 外壳通用化与通用件 → R2 课程列表与课程主页 → R3 模型 API 设置 → R4 课程问答（暗色页）→ R5 教师图谱页 → R6 资料/审核与发布/成员 → R7 认证页对齐与收口；基线为 Draft PR #321，每阶段一条叠加分支与 Draft PR，开工前先写代码级计划）。未经用户指示不提交、不推送。
- Codex 接手（2026-10-07，用户指定本会话顺序执行）：输入为已确认规格、17 项计划与现有隔离预览；输出为计划内前端文件、测试与 Codex 交接。禁止提交/推送；既有 Claude 未提交文档保留。验收按计划各任务命令及任务 17 清单，基线核验结果与执行进度见 `docs/handoffs/codex-ui-graph-pilot-01.md`。
- Codex 续做证据（2026-10-07）：任务 1–16 已完成 RED/GREEN。任务 14 用户批准章节菜单外点击调用 `close(true)` 的一行修正，补充测试 11/11 通过。用户批准节点详情局部修正已落地：35% 并置 /90% 覆盖、整页滚动取代面板滚动、学生详情移除重复关闭叉；教师关闭行为保留。新增布局/行为测试先 RED 后 GREEN，最新相关子集 4 文件 /117 条、全量 57 文件 /1144 条通过；复审发现收起隐藏内容仍撑高页面及画布零宽，均补 RED 断言并修正，1440 收起后页面900高、画布1364宽；最终 type-check/build/basic exit0，full exit1（仅 backend：现有 argon2 缺 InvalidHashError，frontend gate PASS），顺序复跑日志见交接；基础与 full 门禁结果见 Codex 交接。四宽度节点详情实测无横向裁切、侧栏无内部滚动条；390 宽长内容整页高度 1190px，Esc 关闭抽屉还焦点、返回课程清除详情已走查。0.9 目测确认、其余任务 17 浏览器清单/对比度、真实实例前后截图与 E2E 仍未完成（后两项缺环境）。任务维持 IN_PROGRESS；预览暂保留，未提交/推送。
- 发布授权（用户，2026-10-07）：提交并开 PR；沿用现有分支，目标 main，[Draft PR #321](https://github.com/arvinhanye/SmartSketch/pull/321) 已创建，实施提交 `4375ee5`；明列任务17未验收项及 full 后端环境失败，不合并。第二批路线图和本地 preview 不纳入本次提交；其文件与工作区内容保留。

- 已决（用户，2026-10-06）：视觉方向为暗色外壳 + 浅色图谱画布（tokens 见用户设计说明）；样板页先于其他页面；学生选中知识点后，左面板在详情上方保留可折叠的「下一步推荐」摘要（保持「标记掌握 → 推荐刷新」流程）。
- 未决：教师图谱编辑面板（详情、编辑、关系、版本、新建）在「无右侧栏」布局中的位置，样板确认后另行设计；`lifecycle.ts` 面板开合只 `setSize` 不 `fitView`（与 L14 的窗口缩放重新聚焦区分）；曲线边类型与平行边转换的相互作用；类型标记形式。
- 依赖与风险：沿用现有依赖，不新增；图标用内联 SVG。样板确认前不覆盖全局 `--color-*`，新 tokens 用独立命名空间，回滚即撤销本任务提交。`h05`/`i06`/`l13`/`l14` 等测试断言状态样式，需同步更新。
- 本机环境：Node v26.4.0、npm 11.17.0、Python 3.13.5；本工作区 2026-10-06 执行 `npm ci --prefix src/frontend`（仅锁文件内依赖）。无 `.venv`、`.env`、数据库；不涉及真实模型调用与账号。

## 2026-10-02 Claude 认领：A10 一周参赛冲刺设计

| ID | 状态 | 负责人 | 范围 | 验收 |
| --- | --- | --- | --- | --- |
| L00 | DONE（规格与计划 A 已获用户确认，2026-10-02；本会话内逐任务执行） | Claude（协调） | `docs/superpowers/specs/2026-10-02-contest-sprint-design.md`、本节、`docs/handoffs/claude-l00-sprint-design.md` | 精简设计规格覆盖两条闭环、个人模型凭据与任务绑定、问答隔离、向量方案、性能测量、原子任务候选 L01–L19 与待用户决定事项；用户批准后再写实施计划 |

- 输入：Codex 交接 prompt 与两份审查（仅在 Codex 工作区 `/Users/arvinhan/.codex/worktrees/e92f/SmartSketch`，未提交，按绝对路径引用，不复制）；用户确认只做学生提问与 AI 回答、不做自动出题。输出：设计规格与交接。
- 依赖：基线 `6ff8a8d`；现有规格、契约与源码只读核验。风险：赛题 DOCX 原文未独立复核；Codex 对本文件有未提交改动，后续合并时两段都保留；规格中的接口、迁移、规则调整均未签收。
- 验证命令：`./scripts/verify.sh`、`git status --short`、`git diff --check`。无模型调用、依赖安装、数据写入、契约或迁移变更。
- 验收证据：`./scripts/verify.sh` exit 0（基础档，系统 Python）；`full` / `integration` 未跑。交接 `docs/handoffs/claude-l00-sprint-design.md`。
- 已决（ArvinHan，2026-10-02）：在线向量 `text-embedding-v4`；DeepSeek `deepseek-flash`，预算 30 元（累计计费 token ≤ 500 万）；两门课自编；同意规则调整与新增 `cryptography`。工作区 `.env` 已生成（未跟踪），两个供应商 key 待用户填写。
- 计划 A：`docs/superpowers/plans/2026-10-02-contest-sprint-a-personal-model-api.md`，用户确认在本会话内逐任务执行；L01–L10 的认领见下一节。

## 2026-10-02 Claude 认领：冲刺计划 A（个人模型 API 与真实运行路径）

计划：`docs/superpowers/plans/2026-10-02-contest-sprint-a-personal-model-api.md`；规格：`docs/superpowers/specs/2026-10-02-contest-sprint-design.md`。每项的输入、输出、风险与验证命令见计划对应 Task；验收证据写入 `docs/handoffs/claude-l<nn>.md`。

| ID | 状态 | 负责人 | 范围 | 验收 |
| --- | --- | --- | --- | --- |
| L01 | DONE | Claude | 隔离环境：`.venv`（Python 3.11.9）、`npm ci`、独立 Neo4j（7688/7475）；三档门禁基线；不改业务文件 | basic exit 0；full exit 0（后端 3559 通过/27 跳过，前端 772 通过）；integration exit 1，仅因本机未装 Playwright 浏览器，改用 `PLAYWRIGHT_CHROMIUM_EXECUTABLE` 指向 Chrome 后两条端到端通过。另发现北京地域向量服务在本机网络不可达。交接 `docs/handoffs/claude-l01.md` |
| L02 | DONE | Claude（抽取）；DeepSeek harness（2026-10-03 发布与问答补测） | `evaluation/measure_web_flow.py`、基线报告 `evaluation/reports/l02-baseline-2026-10.md` | 抽取实测 141.72 秒（目标 60 秒，未达标），82 个知识点、4 种关系，计费 101054 token。**发布与问答已补测（2026-10-03，向量网络恢复后）**：发布 HTTP 200 / 21.17 秒 / v1（82 知识点、73 关系、无排除项）；五题中 3 题 `answered`、第 5 题按预期 `not_covered`；完整耗时 p50 5.13 秒、最大 6.12 秒（≤15 秒与 ≤10 秒均达标），首字 5.88/4.70/2.07 秒（S2 的 ≤3 秒目标 3 题中 2 题未达标）；**第 3 题「栈和队列有什么区别？」被整篇撤回**（`all_citations_invalidated` / `no_markers`，输出撞 `ANSWER_MAX_OUTPUT_TOKENS=1024` 上限被截断，`truncated=1`），资料实际覆盖该问题，可确定性复现，**缺陷按本轮边界未修**；发布期向量调用未写入 `model_calls`（记账缺口）。本次计费 16101 token。交接 `docs/handoffs/claude-l02.md`、`docs/handoffs/deepseek-plan-a-verification.md` |
| L03 | DONE | Claude | ADR-080/081、`AGENTS.md` §4/§6、`docs/`、`src/contracts/`、生成物；前端三处错误码清单同步 | 契约门禁 exit 0；前端类型检查与 772 用例通过；后端 3561 通过/27 跳过；交接 `docs/handoffs/claude-l03.md` |
| L04 | DONE | Claude | 迁移 015、`services/credentials.py`、`repositories/model_configs.py`、`config.py`、`cryptography==50.0.2` | 11 个新用例；后端 3572 通过/27 跳过；交接 `docs/handoffs/claude-l04.md` |
| L05 | DONE | Claude | `services/ai/outbound.py`；顺带修复 `_StdlibResponse.read` 在服务端关闭连接时误报连接错误 | 32 个新用例与既有客户端用例通过；交接 `docs/handoffs/claude-l05.md` |
| L06 | DONE | Claude | `services/model_configs.py`、`api/model_config.py`、`main.py` | 20 个新用例；后端 3623 通过/27 跳过；真实 DeepSeek 测试连接成功、无效密钥识别为 auth；交接 `docs/handoffs/claude-l06.md` |
| L07 | DONE | Claude | 上传绑定、`workers/`、调用归属用户 | 13 个新用例；修复旧表结构下写 `created_by` 的回归；交接 `docs/handoffs/claude-l07.md` |
| L08 | DONE | Claude | `api/chat.py`、`services/qa/`、按用户日预算 | 9 个新用例；后端 3645 通过/27 跳过；交接 `docs/handoffs/claude-l08.md` |
| L09 | DONE | DeepSeek harness | 在线向量联调、`local` 明确拒绝、`scripts/start.sh`；用户 2026-10-03 选向量方案第 1 种（恢复到北京地域接口的网络路径，地址不变） | 真实向量实测可用：`check-embedding.py` → `ok model=text-embedding-v4 dimensions=1024 seconds=0.66`（exit 0）。正式入口不静默切 demo：`EMBEDDING_MODE=demo`/`local` 时 `start.sh` 均 exit 1；冒烟 `GET /api/v1/me/model-config` → `{"runtime_mode":"personal","configured":false}`、`/health` ok、worker 无 `Invalid configuration`。后端+tooling 3648 通过/27 跳过/0 失败；`verify.sh` exit 0。交接 `docs/handoffs/deepseek-l09.md` |
| L10 | DONE | Claude（代码）；DeepSeek harness（2026-10-03 真实页面走查） | 前端设置页、未配置引导、模式标识 | 前端 782 用例通过、类型检查与构建通过。**真实页面走查六步全部符合设计**（由 DeepSeek harness 用真实 Chromium 驱动，personal 模式）：侧栏「模型 API 设置」带「未配置」标记、资料页引导且上传禁用；测试连接成功（585 毫秒）、保存后显示「已配置：deepseek-flash · 密钥 ••••+末 4 位」（末 4 位见截图中脱敏显示，不写入本文档）、刷新后仍脱敏且密钥框为空；`localStorage`/`sessionStorage` 无密钥（仅登录令牌）、6 次 `GET /me/model-config` 与 `PUT` 响应均不含密钥；上传 1002 字节文件推进到待审核；学生保存配置后提问得到带引用的回答；教师清除配置后再上传被拒（HTTP 409 `MODEL_CONFIG_REQUIRED`）并显示引导。截图 `.demo/v2/`（Git 忽略）。交接 `docs/handoffs/claude-l10.md`、`docs/handoffs/deepseek-plan-a-verification.md` |

- 2026-10-03 Claude 复核 L09（`ea9484c`）：通过，记录 `docs/reviews/claude-deepseek-l09-2026-10-03.md`。**未决风险**：问答准备阶段的查询向量调用不受 15 秒链路截止约束，向量服务不可达时一次提问可能挂数分钟（`services/qa/chat.py:115`）；建议在计划 B（L15）或计划 C（L16）单独认领修复。本机到北京地域向量接口的网络时通时断，L02 问答补测与 L10 走查需网络稳定后进行。

### V3：业务改动后的完整门禁与端到端（2026-10-03，DeepSeek harness）

**通过，退出码 0，无失败项。** 命令与证据：

```bash
PYTHON=.venv/bin/python PATH="$PWD/.venv/bin:$PATH" \
PLAYWRIGHT_CHROMIUM_EXECUTABLE="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  ./scripts/verify.sh integration > .demo/logs/verify-integration-planA.log 2>&1   # → exit 0
```

| 档位 | 结果 |
| --- | --- |
| 基础档 | 钩子回归通过；`PASS contracts`（32 路径 / 129 schema / 385 `$ref`）；B14 生成与漂移回归、25 项门禁负向测试；B08/B09/B10/B12/B13 契约回归全通过 |
| 后端全量 | 3648 passed、27 skipped → `PASS` |
| 前端全量 | 26 文件 782 passed → `PASS` |
| 集成用例 | 392 passed、4 skipped → `PASS` |
| 图库后端用例 | 44 passed → `PASS` |
| 端到端 | 2 passed（学生主线 52.5 秒、教师主线 1.2 分钟）→ `✓ 端到端通过` |

这是 PR #317 中 L03–L10 业务改动之后的首次完整门禁（此前的端到端证据只来自 L01、业务改动之前）。端到端用演示模型，**不产生费用**。log 与端到端目录：`.demo/logs/verify-integration-planA.log`、`.e2e/20261003-030121/`。两项环境前提：契约门禁硬编码 `python3` 需把 `.venv/bin` 前置到 `PATH`；`tests/tooling/test_k07.py` 的 4 个交互式用例需要更宽的沙箱权限才能分配 PTY（详见 `docs/handoffs/deepseek-l09.md`「环境与沙箱」）。

- 2026-10-03 Claude 复核计划 A 未完成项检查（`92aa8bc`）：通过，记录 `docs/reviews/claude-deepseek-plan-a-verification-2026-10-03.md`。计划 A（L00–L10）完成。**遗留缺陷（未修，待认领）**：D1（高）答案超过 1024 输出 token 被截断后整篇撤回并误报 `not_covered`，违反「资料未覆盖与服务故障分开显示」；D2（低）发布时向量调用不写 `model_calls`；D3（中）问答查询向量调用不受 15 秒截止约束。另：抽取 141.72 秒未达 60 秒目标。

## 2026-10-03 Claude 认领：计划 A 审查修复（D1–D3、N01–N08）

依据：Codex 审查 `/Users/arvinhan/.codex/worktrees/e92f/SmartSketch/docs/reviews/codex-claude-plan-a-2026-10-03.md` 与修复 prompt `/Users/arvinhan/.codex/worktrees/e92f/SmartSketch/docs/handoffs/codex-claude-plan-a-fix-prompt-2026-10-03.md`（均在 Codex 检出、未合并，按绝对路径引用）。审查对象 `6ff8a8d → e86f4b9`；开工时冲刺工作区 HEAD 仍为 `e86f4b9`、工作树干净。会话工具不允许写其他工作树，本轮在工作树 `/Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34`（分支 `claude/smartsketch-plan-a-fixes-e70a34`，从 `e86f4b9` 快进）实施，可快进合回冲刺分支。编号沿用审查的 D1–D3、N01–N08，不覆盖旧 R 编号。交接：`docs/handoffs/claude-plan-a-review-fixes-2026-10-03.md`。

| ID | 级别 | 状态 | 负责人 | 范围 | 验收 |
| --- | --- | --- | --- | --- | --- |
| N01 | P1 | DONE（待复审） | Claude | 迁移 016 配置 `revision`、`repositories/model_configs.py`、`services/qa/user_models.py`、ADR-082 决定 1 | 清除→重建（中间无提问）后下一次出站用 B；两用户互不影响；旧任务仍用创建时快照，清除仍撤销。`tests/backend/test_n01_n06.py`：red 8 failed/2 passed（出站仍为 A 地址；旧成功落到 B）→ green；连同 L04/L06/L07/L08/C 组 432 passed |
| N06 | P2 | DONE（待复审） | Claude | `services/model_configs.py`、`repositories/model_configs.py` | 测试结果只按被测 `revision` 条件落库；保存更换、清除重建、乱序完成均不污染新配置。同上测试文件（阻塞传输 + 乱序门控）red → green |
| D1 | P1 | DONE（待复审） | Claude | `services/qa/citations.py`、`chat.py`、契约 `ChatLlmUnavailableReason += truncated`、`specs/grounded-qa.md` O6/QA-16、前端 `chatStream.ts`/`useChat.ts`、ADR-082 决定 2 | 截断不再判 `not_covered`；无效出处的截断回答不当成功；真实无资料仍 `not_covered`。`tests/backend/test_d1.py` red 5 failed/7 passed → green 12；`tests/frontend/d1-d3.test.ts` red 3 → green；J06 截断用例按决定 2 改断言；basic 门禁 exit 0 |
| D3 | P1 | DONE（待复审） | Claude | `services/qa/chat.py`、`services/ai/embeddings.py`、`client.py`（`EmbeddingRequest.timeout_seconds`）、`compatible.py`（`exchange` 总预算 + 看门狗）、`outbound.py`、`repositories/neo4j.py`（`read_deadline`）、ADR-082 决定 3 | 同一单调截止贯穿改写/向量/检索/生成；连接、读取、多地址、重试用剩余预算；超时为 `LLM_UNAVAILABLE`/`timeout`。`tests/backend/test_d3.py`（假解析/假连接/回环桩：解析挂起、多地址累计、静默与慢速逐字节响应头、向量批次共用预算、缓存命中、改写耗尽、两种传输与日志）：red 14 failed/4 passed（接口先行后）→ green 18；连同 L05/E03 传输用例通过 |
| N02 | P2 | DONE（待复审） | Claude | `workers/extract_task.py`、前端 `useMaterials.ts` 任务失败按凭据原因提示、ADR-082 决定 4 | 实体/关系首次 401/403 不重试、任务 `failed`/`LLM_UNAVAILABLE`/`auth`、不进 merging、停止派发。`tests/backend/test_e12.py` N02 段 red 5 failed（任务进入 merging、chunks_failed=1）→ green（E12+L07 55 passed）；`tests/frontend/h02.test.ts` 凭据原因提示 red 4 → green 85 |
| N03 | P2 | DONE（待复审） | Claude | `App.vue`（按会话令牌监听、中止旧读取）、`stores/runtime.ts`（owner + 代际：`commitRead`/`commitWrite`）、`useModelConfig.ts` | 同角色换号、退出重登、初始读取晚于保存/清除，旧响应均不改当前账号 UI。`tests/frontend/n03-n05.test.ts` N03 段 red → green |
| N04 | P2 | DONE（待复审） | Claude | `useModelConfig.ts`（单一 `busy` 互斥、卸载丢弃）、`ModelSettingsView.vue`（四个按钮按 `busy` 禁用） | 保存/测试/清除互斥（逻辑与按钮），错误后释放，卸载中止，乱序结果不回写。同上测试文件 N04 段 red → green |
| N05 | P2 | DONE（待复审） | Claude | `useModelConfig.ts` | 仅地址与模型都未改且密钥留空时测试已存配置；其余要求先保存或填完整凭据，并标明测试对象（「已保存的配置」/「表单中的配置（尚未保存）」；测试期间改表单则结果作废）。同上测试文件 N05 段 red → green |
| §3.7 | 既有缺口 | DONE（待复审） | Claude | `ChatView.vue`、`useChat.ts`、`specs/grounded-qa.md` Q6.5 | 发送期间按钮、Enter、逻辑入口都不再提交；显式「停止」后可再发。`tests/frontend/chat-send-lock.test.ts` red → green；前端全量 811 中 810 通过，唯一失败为 B02 嵌套 vitest 在满载下超时 5 s，单独重跑 5/5 通过；type-check exit 0 |
| N07 | P2 | DONE（待复审） | Claude | `services/model_configs.py`（`run_test` 开头统一检查存储）、ADR-082 决定 5 | 存储未启用时 `/test` 任何分支在 DNS/传输前返回 503 `credential_store_disabled`。`tests/backend/test_n07_n08.py`（demo/fake × 完整/空请求体、残留配置；启用时仍可测）red → green |
| N08 | P2 | DONE（待复审） | Claude | `services/model_configs.py`（共享 `normalize_model`）、`api/model_config.py`、契约 `model` 说明（已重生成） | 空白模型名 PUT 与 /test 均 422 `VALIDATION_ERROR`（`model`/`blank`），不写库不出站。同上测试文件（空格/制表符/换行，新建、保留密钥修改、测试三入口）red 20 failed/2 passed（含 N07）→ green 22；连同 L06 42 passed |
| D2 | P2 | DONE（待复审） | Claude | `services/ai/embeddings.py`（可选调用存储 + `embedding_calls` 归属）、`services/ai/factory.py`（`build_embedding_adapter`，仅 online 记账）、`api/versions.py`、`api/chat.py`、`services/versions/publish.py`、`services/qa/chat.py`、ADR-082 决定 6 | 发布与查询的每次实际向量出站先预写、再回写；缓存命中/回滚复制不记；不计入个人日预算。`tests/backend/test_d2.py` red 9 failed/1 passed（接口先行后）→ green 10；`tests/integration/test_d2_publish.py`（发布、未变重复发布、回滚）在 integration 档通过 |

- 输入：上述审查与 prompt、已签收冲刺规格与 ADR-080/081、计划 A 代码（`e86f4b9`）。输出：修复代码、仓库回归（先红后绿）、必要的规格/ADR/契约更新、交接。
- 依赖：顺序 N01+N06 → D1+D3 → N02 → N03–N05 与 §3.7 → N07–N08 → D2。共享边界（配置身份、错误闭集、记账归属）先写 ADR-082 再写代码。
- 风险：迁移 016 改已有库（新增可空列 + 回填，附回滚）；D1/D3 改问答终态与错误闭集，需契约、DTO、前端提示同步；D3 涉及出站传输，不可放松地址防护与 TLS 校验。
- 验证命令：每组最小相关测试（`PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/<file> -q`、`npm run test -- --run <file>`）；最终 `./scripts/verify.sh`、`full`、`integration`（仅一次性 Neo4j）、`git diff --check`。不调用真实模型、不动真实课程库。
- 2026-10-03 全部 11 项及 §3.7 已修并提交（`0745ea6` `cc26d4c` `8e539a8` `a787b0b` `45dd86e` `f580b74` `29a10f6` `959331e`），ready_for_review。**门禁（代码 HEAD `959331e`）**：`./scripts/verify.sh integration` 中基础档 PASS；后端 full 3725 passed / 27 skipped（已登记）PASS；前端 full 29 文件 811 passed、type-check 与 build 通过；集成用例 393 passed / 4 skipped（已登记）PASS；图库后端用例 44 passed PASS；端到端首次因本工作树缺根目录 `@playwright/test` 失败（环境原因），补齐依赖后单独运行 `scripts/e2e.sh` 2 passed（演示模型，无费用）。同一次 `verify.sh integration` 未整体 exit 0，端到端为补跑。`git diff --check e86f4b9 HEAD` exit 0。未决：D1 的输出上限是否提高或增加有限重试，需人工按 15 秒与费用实测决定。详见交接。
- 计划 B/C（L11–L19）不在本节范围。

## 2026-10-03 Claude 认领：冲刺计划 B（L11–L15 功能闭环）——功能交付已收尾，质量/性能验收有保留（2026-10-03）

计划：`docs/superpowers/plans/2026-10-03-contest-sprint-b-functional-loop.md`；交接 `docs/handoffs/claude-plan-b-planning.md`。基线 `d766f40`（计划 A 审查修复版本，代码 HEAD `959331e`）。用户 2026-10-03 批准执行；需要阿里云百炼向量或真实模型的测试写交接稿交 DeepSeek harness 运行，本会话不调用真实模型。

| ID | 状态 | 负责人 | 范围 | 验收 |
| --- | --- | --- | --- | --- |
| L11 | IMPLEMENTED（功能代码完成；L11-7 真实模型复测 OPEN） | Claude（L11-1～L11-5）；DeepSeek harness（L11-6 真实模型测量） | 自编两门课资料与 PDF、本机假供应商、个人模式端到端、发布阻断原因、失败路径验收、真实模型测量 | `personal.spec.ts` 教师 PDF+MD 闭环与鉴权失败用例通过；真实模型报告 `evaluation/reports/l11-teacher-loop-2026-10.md` 分列假供应商接线与真实质量/耗时 |
| L12 | DONE（Codex 复审修复；本地验收） | Claude → Codex | `SourceRef`/`Citation` 加可选 `document_name`（ADR-085）、后端同课查名、`SourceViewer`、四入口 | `test_l12.py`（含跨课负例）、`l12.test.ts`、端到端四入口 |
| L13 | DONE（Codex 复审修复；本地验收） | Claude → Codex | 可读初始视口与聚焦、搜索定位、详情栏收起、问答 → 图谱选中 | `l13.test.ts`；端到端 20+ 节点 `data-zoom` ≥ 0.7、问答跳转选中 |
| L14 | DONE（Codex 已修回归；完整本地门禁通过） | Claude → Codex | 学习路径纯函数、画布路径高亮与序号、推荐解释（缺省值标为未标注） | `l14.test.ts` 确定性 DAG；端到端掌握联动 |
| L15 | DONE（本地闭环与真实 QA 抽样完成；性能/质量有保留） | Codex | 课程内角色侧栏、概览阶段与下一步、入课空态、跨课隔离、恶意文本、两课程总验收 | `l15.test.ts`、`test_l15.py`、`l15-creation-scope.test.ts`；`verify.sh integration` 与 D/N 回归 |

- 2026-10-03 L11-1 完成：`datasets/contest/` 两门课各一章（Markdown 为源，PDF 由 `scripts/build-contest-pdfs.sh` 用 Chrome 无头打印：第 3 章 5 页、第 2 章 4 页），`tests/backend/test_l11_datasets.py` red（无清单）→ green。**发现并修复阻断**：macOS 字体 PDF 的部首形近字（⽬⾃⻓⻅），ADR-083、解析器 `pdf/2`，red 4 failed → green；解析相关 1840 passed。已知：pdfminer 对 Chrome 字体打印大量 FontBBox 告警，不影响提取。
- 2026-10-03 L11-2～L11-5 完成：本机 OpenAI 兼容假供应商（`scripts/fake_provider.py`，`tests/tooling/test_l11_fake_provider.py` 13 passed）；个人模式端到端 `tests/e2e/personal.spec.ts` 3 passed（教师 PDF+MD 闭环、处理中取消后重传、供应商拒绝密钥）。走查发现并修复两个前端阻断：教师图谱页没有画布外的选节点方式、没有新建知识点入口（`tests/frontend/l11.test.ts`）；发布被拦时逐条列出原因（L11-4）。`e2e.sh` 修复 bash 3.2 下清理报错导致的容器残留；B02 嵌套 vitest 用例超时与子进程对齐。前端全量 818 passed。
- 观察（不修，R05）：同一章 PDF 与 Markdown 都上传会产生大量同名知识点（审核队列「疑似重复」60 组），跨任务融合不在本期。
- L11-6 真实模型测量交接：`docs/handoffs/claude-l11-6-deepseek-handoff.md`（DeepSeek harness 在冲刺工作树执行；含迁移 016 首次启动核对、预算停止线累计 60 万）。
- 2026-10-03 L11-6 完成（DeepSeek harness）：四次抽取（两门课 × MD/PDF）+ 两次发布全部成功，交接 `docs/handoffs/deepseek-l11-6.md`，报告 `evaluation/reports/l11-teacher-loop-2026-10.md`。**赛题指标**：知识点 75/71/71/74 与关系种类 4/3/4/3 均达标；**抽取耗时四份全部未达 60 秒**（83.97 / 200.37 / 75.51 / 162.54 秒）；准确率未判定（原始输出已导出到 `evaluation/raw/l11/`，待 L16）。**发布与向量记账**：两门 MD 课程 HTTP 200（11.21 / 6.58 秒），`model_calls` 出现 `purpose='embedding'`、`request_id=publish:<version_id>`、`status=ok` 各 10 行，**ADR-082 决定 6 首次真实验证通过**（上一轮的「发布期向量未记账」缺口已消失）。**ADR-083** 在真实 PDF 上核对通过（32 个块里康熙部首/部首补充区字符 0 个）。**迁移 016** 已执行，备份实际在 `src/backend/storage/backups/`（交接写的仓根 `backups/` 有误），`integrity_check=ok`。**新发现（未修）**：PDF 路径成本约为 MD 的 1.6～2.2 倍且 repair 次数达 13 次；PDF 两份都抽不出 `PREREQUISITE`、孤立节点 37/71 与 39/74；旧基线「入库 45.7 秒是头号瓶颈」的判断已不成立（本次非模型阶段仅 1.04～12.39 秒）。**用量**：本次 478987 token，累计 **619217 / 5000000**；越线经用户明确授权（详见交接）。
- 2026-10-03 L11 阶段门禁（`fc2ad94`，`verify.sh integration`，独立端口）：后端 1 failed / 3750 passed / 27 skipped（`test_shell_multibyte_vars` 拦下本轮两处中文前未加花括号的变量，`4ee7b52` 修复后单测通过）；前端 824 passed；集成 393 passed / 4 skipped；图库 44 passed；演示端到端 2 passed、个人模式端到端 3 passed。同一次运行未整体 exit 0。
- 2026-10-03 **L11-7（新增，用户批准在 L12 前修）**：L11-6 实测 PDF 路径成本高、无 PREREQUISITE、近半孤立节点。离线定位根因为一行一块、句子被换行切断；修复为自动换行的续行并回同一段（ADR-084，`headings/2`），比赛 PDF 38/24 块，与 Markdown 37/24 相当。`tests/backend/test_l11_pdf_reflow.py` red 5 → green 10；D06 三个用例按新行为更新期望；解析相关 1850 passed。真实模型复测交接 `docs/handoffs/claude-l11-7-deepseek-retest.md`。
- 2026-10-03 **L12 完成**（`af671cc`、`8b79ccc` 及端到端提交）：契约 `SourceRef`/`Citation` 增加可选 `document_name`（ADR-085），后端按同课资料填写知识点来源、关系来源与问答引用（他课/已删除省略、查名失败不影响回答）；前端统一「文件名 · 第 N 页 · 章节」、缺名写「资料不可用」，知识点详情点开来源即展开查看器（教师、学生共用），问答右栏带文件名。证据：`tests/backend/test_l12.py` 8 passed（含跨课负例）、`tests/frontend/l12.test.ts` 11 passed、前端全量 835 passed；个人模式端到端教师图谱、学生图谱、问答引用三入口均断言文件名与对应格式的位置（3 passed），演示端到端 2 passed。
- 2026-10-03 **L13 完成**（`1d50a33` `50e5389` `25470ab` `8aa5cfb` 及端到端提交）：初始视口不低于可读缩放 0.7 并聚焦入口节点（无前置的第一个节点），页面可按知识点聚焦；搜索框回车按「名称完全一致优先、包含其次、只在当前筛选可见节点中」定位并选中；类型、状态、章节筛选收进默认收起的「更多筛选」（关系图例与布局常显）；问答知识点按钮链接到 `?kp=&v=`，学生图谱选中目标，目标不在当前版本或版本不同时给出提示，不跨课找同 ID 节点。学生页右栏还承载学习路径，详情与掌握标记本就只在选中时渲染，未再收起整栏。证据：`tests/frontend/l13.test.ts` 10 passed、`l13-kp-link.test.ts` 8 passed；个人模式端到端 3 passed（`.e2e/20261003-115144`）：71+ 节点画布 `data-zoom` ≥ 0.7、问答点知识点后详情标题与按钮名称一致、刷新直达仍选中、搜索回车选中教师新建节点。
- 2026-10-03 **L14 完成**（`3b50380` `8d6988e` `5d171e4` `aa2d7ad` `d668e0d` `09349d3` `653089e`）：学习路径纯函数（`graph/learningPath.ts`：只看未被拒的先修边，后继须全部前置满足才算解锁，推荐顺序以服务端为准只给序号）；画布推荐项标签「1. 」、缺失前置/之后解锁/淡化/路径边各有状态，焦点为点选的推荐项或第一个推荐项，视口跟随；推荐列表顶部「已掌握 → 还需先学 → 下一步 → 之后解锁」，「排序参考」中中性值 0.5 写「未标注」。**走查（真实浏览器截图）另发现并修复三处**：服务端理由句把缺失属性的 0.5 写成测量值（后端 `ranking._reason`）；G6 5.1.1 每次 render 都按 autoFit 整图适配，状态更新会把视口拉回整图（L13 的聚焦也受影响）；画布尺寸变化后重新聚焦回入口节点。证据：`tests/frontend/l14.test.ts` 21 passed、`tests/backend/test_l14_reason.py` 3 passed；个人模式端到端 3 passed（标记推荐第 1 项 → 推荐与路径行更新、刷新保留、自助注册的第二个学生看到「未开始」且推荐不变、取消后恢复）。`h05`/`i06` 的样式键清单与 0.5 展示断言按新行为更新。
- 2026-10-03 **计划 B 移交 Codex**：L11（除 L11-7 真实模型复测待 DeepSeek）、L12～L14 已完成待复审；L15 未开始，设计决定与前端测试草稿见交接 `docs/handoffs/claude-plan-b-handoff-to-codex.md`、`docs/handoffs/claude-l15-draft-tests.txt`。L13+L14 合并门禁在交接时未跑完，接手者需重跑。
- 2026-10-03 **L13+L14 合并门禁**（代码 HEAD `56610d4`，`verify.sh integration`，独立端口）**整体 exit 1**：后端 full 3772 passed / 27 skipped，前端 874 passed，集成 393 passed / 4 skipped，图库 44 passed，个人模式端到端 3 passed，均 PASS；**演示端到端 `student.spec.ts` FAIL**。原因是 L14-3 把推荐序号放进按钮，用例取按钮文字首词得到「1.」（证据 `.e2e/20261003-124107`）。交 Codex 修复，根因与建议修法见 `docs/handoffs/claude-plan-b-handoff-to-codex.md` §2。L14 因此不算完成，状态改回 IN_PROGRESS。
- 2026-10-03 用户决定：L12～L14 的 16 个提交（`5a34fec..56610d4`）交 Codex 复审；需要向量模型或真实模型的测试仍交 DeepSeek harness；**调高问答输出上限**（`ANSWER_MAX_OUTPUT_TOKENS` 1024 → 建议 2048，交 Codex 先写 ADR 再按 TDD 实施，实测交 DeepSeek）。详见 `docs/handoffs/claude-plan-b-handoff-to-codex.md` §0。

## 2026-09-28 Codex 认领：认证页动态图谱

| ID | 状态 | 负责人 | 范围 | 验收 |
| --- | --- | --- | --- | --- |
| UI-AUTH-MOTION-03 | DONE | Codex（前端） | `AuthLayout.vue`、装饰图运动逻辑、相关测试、规格和交接 | 图谱大小、位置、旋转随时间变化；在蓝色绘图区内运动，碰撞时反弹；品牌文案和表单不被遮挡；减少动态效果设置可静止展示 |

- 输入：`42afa2f` 的 8 组随机静态 SVG 图谱；输出：可动的装饰图谱。依赖：现有认证页绘图区与 SVG 节点。风险：运动引起文字重叠、边界裁切或不必要的性能开销；使用有限速度、边界/碰撞解算、动画帧生命周期清理和减少动态效果分支。
- 验证命令：装饰图物理单测、`npm run test -- --run h13.test.ts`、`npm run type-check`、`npm run build`、`./scripts/verify.sh`、浏览器动态视觉检查、`git diff --check`。
- 验收证据：前端全量测试 25 个文件、772 个用例通过；`npm run type-check`、`npm run build`、`git diff --check` 通过。浏览器观察到 8 组图谱均移动、尺寸随时间变化，旋转保持在 ±22° 内，装饰区位于说明文字下方，720px 视口无页面纵向溢出。`./scripts/verify.sh` 已尝试，但本机门禁依赖缺少 `openapi-typescript`，临时子进程无法找到 `python3`；详见 `docs/handoffs/codex-ui-auth-motion-03.md`。

## 2026-09-28 Codex 认领：登录页装饰知识图谱

| ID | 状态 | 负责人 | 范围 | 验收 |
| --- | --- | --- | --- | --- |
| UI-AUTH-ART-02 | DONE | Codex（前端） | `AuthLayout.vue`、前端相关测试、身份规格、交接 | 蓝色品牌区有 8 组拓扑各异的小图谱；每次加载随机散布并避让节点文字；装饰文字不可选中复制；登录交互和布局保持可用；修改前后各有本地 Git 提交 |

- 输入：现有单组 SVG 示意图、登录页左右分栏；输出：分布于品牌区下方的多组装饰图谱。依赖：`AuthLayout` 和前端测试环境。风险：装饰内容过密影响文案或矮屏布局；采用自适应 SVG 容器并在窄屏沿用隐藏品牌区的规则。
- 验证命令：`npm run test -- --run h13.test.ts`、`npm run type-check`、`npm run build`、`./scripts/verify.sh`、浏览器视觉检查、`git diff --check`。
- 验收证据：修改前提交 `8d3d992`。浏览器连续 3 次重新加载，8 组图谱位置均变化，37 个标签无重叠、均位于说明文字下方；装饰 SVG 的 `user-select` 与指针事件均为 `none`，拖拽后选区为空；720px 视口文档高度保持 720px。前端定向 30 passed、全量 767 passed、类型检查和构建通过；详见 `docs/handoffs/codex-ui-auth-art-02.md`。
- `./scripts/verify.sh` 已在 Git Bash 中尝试，契约门禁缺少 `openapi-typescript` 命令，且其临时子进程无法找到 `python3`；这两项为本机工具链问题，非本次前端图谱改动。

## 2026-09-28 Codex 认领：登录页提示与视口布局

| ID | 状态 | 负责人 | 范围 | 验收 |
| --- | --- | --- | --- | --- |
| UI-LOGIN-01 | DONE | Codex（前端） | `App.vue`、登录页相关样式、`tests/frontend/h13.test.ts`、身份规格、交接 | 未登录提示可用按钮关闭；登录页在 720px 浏览器视口无纵向溢出；矮窗口表单栏保留内部滚动 |

- 输入：现有 `query.notice` 提示和 `AuthLayout` 登录布局；输出：可关闭提示及填满剩余视口的登录页。依赖：现有 Vue 路由与 H13 登录表单。风险：矮视口下表单高度可能超过可用区域，需让表单区域独立滚动。
- 验证：在 `src/frontend` 运行 `npm run test -- --run h13.test.ts`（29 passed）、`npm run test -- --run`（766 passed）、`npm run type-check`（通过）、`npm run build`（通过）；浏览器实测未登录提示可关闭，关闭前后 `document.documentElement.scrollHeight === window.innerHeight === 720`。`git diff --check` 通过。`./scripts/verify.sh` 已尝试，WSL 中因 Windows 检出脚本的 CRLF shebang 报 `env: bash\r: No such file or directory`，本机未安装 Git Bash。
- 交接：`docs/handoffs/codex-ui-login-01.md`。当前工作树基线 `main@62eb8c7`，比 `origin/main` 落后 6 次提交；尝试快进时因本机 `.git` 写入权限不足失败。

## K05 教师主线 E2E（Codex）

| ID | 状态 | 负责人 | 范围 | 验收 |
| --- | --- | --- | --- | --- |
| K05 | IMPLEMENTED / 待审查验证 | Codex | `tests/e2e/teacher.spec.ts`、`tests/e2e/fixtures.ts`、Playwright 运行入口 | 四格式上传、上传失败重试、成环拒绝、发布后学生可见；默认 fake 模型输出不满足抽取格式，真实 E2E 尚未运行 |

- 输入：自编四格式资料；输出：教师上传到发布的浏览器用例。依赖：前后端、worker、Neo4j、演示账号及能输出有效抽取结构的 fake 模型。风险：当前默认 fake 模型仅返回摘要对象，worker 无法从该输出构建图谱。
- 本轮最小检查：`npm run test:e2e -- tests/e2e/teacher.spec.ts --list`（发现 1 个用例）；完整验证命令：`npm run test:e2e -- tests/e2e/teacher.spec.ts`（未运行）。

## 2026-09-25 Codex 认领：F03

| ID | 状态 | 任务 | 负责人 | 文件范围 | 验收 |
| --- | --- | --- | --- | --- | --- |
| F03 | DONE（PR #246 已合入 `d624208`） | 建立图唯一约束和索引迁移 | Codex（后端） | `src/backend/migrations/neo4j/001_constraints.cypher`、`src/backend/app/repositories/graph_migrations.py`、`tests/integration/test_f03.py`、本节及相关规格/架构/交接 | [PR #246](https://github.com/arvinhanye/SmartSketch/pull/246)；F03 15 passed（一次性 Neo4j 5.26，含审查修复）；最新 main 基线后端 2277 passed；`./scripts/verify.sh` exit 0；`git diff --check` exit 0；交接 `docs/handoffs/codex-f03.md` |

- 输入：F02 Neo4j 驱动、B11/ADR-012 图模型、E07 `EmbeddedVector`；输出：可重跑的 schema 迁移与带空间标识的向量写入边界。
- 依赖：F02、B11 已在当前 `main`。风险：Neo4j DDL 非整体事务；失败后保留已建对象，修复数据或环境后重跑。
- 验证命令：`python3 -m pytest tests/integration/test_f03.py -q`、`./scripts/verify.sh`、`git diff --check`。
- 验收证据：迁移模块缺失、SQLite/CLI 符号缺失、连接关闭泄漏及缺失 SQLite 文件均先红后绿；真实 Neo4j 首次检出向量索引 DDL 缺闭合大括号，新增结构负例先红后修复；独立审查又指出空间错误细节及同名异构 DDL 跳过风险，先加负例后修复并处理 Neo4j 唯一约束配套索引同名；一次性容器中 `tests/integration/test_f03.py` 15 passed。重基到 `origin/main@8985a16` 后虚拟环境 `tests/backend` 2277 passed；虚拟环境 PATH 下 `./scripts/verify.sh` exit 0；详见交接。


## 2026-09-25 并行认领批次

| ID | 状态 | 任务 | 负责人 | 分支 / 基线 | 文件锁（唯一写入者） | 证据 / 同步状态 |
| --- | --- | --- | --- | --- | --- | --- |
| B14 | DONE（PR #214 `342cc3e`；Claude 审查通过；#56 已关闭） | 建立契约导出与漂移检查 | ArvinHan（Codex 子代理） | `codex/b14-contract-drift` / base `a7a0be0` | `scripts/gen-contracts.sh`、`scripts/gen_contracts.py`、`src/contracts/api.v1.yaml`、`src/contracts/v1/generated/`、`tests/contracts/test_b14.py`、`docs/handoffs/codex-b14.md` | 依赖 B09–B13 已在基线；定向 3 passed，`./scripts/verify.sh` exit 0（25 项负例及 B08/B09/B10/B12/B13 回归），`gen-contracts.sh --check`、`git diff --check` 通过；审查修复 `0b1fb6c`；Issue #56 已分配并标记 `status:in-review`；[PR #214](https://github.com/arvinhanye/SmartSketch/pull/214)。
| D08 | DONE（PR #215 `5a0bcdb`；Claude 审查通过，P3 见下；#77 已关闭） | 实现章节内语义分块 | ArvinHan（Codex 子代理） | `codex/d08-semantic-chunking` / base `a7a0be0` | `src/backend/app/services/chunking.py`、`tests/backend/test_d08.py`、`docs/handoffs/codex-d08.md` | 依赖 D02/D03/D04/D06/D07 已在基线，D-13 章节路径前缀已实现；定向 13 passed、后端 1015 passed（1 条既有弃用警告），`./scripts/verify.sh` 与 `git diff --check` 通过；审查修复 `d675d2b`；Issue #77 已分配并标记 `status:in-review`；[PR #215](https://github.com/arvinhanye/SmartSketch/pull/215)。

## 2026-09-25 Codex 认领：E07

| 原子 ID | 状态 | 任务 | 负责人 | 基线与文件范围 | 验收 |
| --- | --- | --- | --- | --- | --- |
| E07 | DONE（PR #217 `8b2c33c`；Claude 审查通过，P3 见下；#87 已关闭） | 实现向量适配与维度检查 | Codex（数据与 AI） | `main@a7a0be0`；`src/backend/app/services/ai/embeddings.py`、`tests/backend/test_e07.py`、相关架构与交接 | 同批/跨批重复请求去重，进程内缓存默认 1024 条 LRU；E07 16 passed；后端全量 1035 passed；`./scripts/verify.sh` exit 0；`docs/handoffs/codex-e07.md` |

- 输入：E02 的 `EmbeddingClient` 与 A07 的模型配置；输出：逐条携带模型和空间标识的向量。依赖 E02、A07 已在当前基线。
- 风险：在线/本地客户端由 E03 接入；E07 通过注入 `EmbeddingClient` 验证模式切换，不引入未经签收的真实供应商依赖。当前工作区的 C03 文件不在 E07 范围内。
- 审查修复：同一次 `embed` 调用按空间与文本哈希合并缓存未命中项，跨批重复只请求一次；LRU 有限缓存超限后重算旧文本。先新增 4 个失败用例复现，再修复为 16 passed；后端全量 1035 passed。
- 验证：项目虚拟环境中 `python -m pytest tests/backend/test_e07.py -q`；通过 Git Bash（设置虚拟环境和前端工具路径）运行 `./scripts/verify.sh`；`git diff --check`。详见交接。
## 2026-09-25 Codex 认领：C04

| 原子 ID | 状态 | 任务 | 负责人 | 基线与文件锁 | 验收 |
| --- | --- | --- | --- | --- | --- |
| C04 | DONE（PR #225 `64e643a`） | 实现课程列表和创建 API | Codex（后端） | `origin/main@130e6b6`（含 C03 PR #216）/ `codex/c04-courses-api`；独占 `src/backend/app/api/courses.py`、`src/backend/app/services/courses.py`、`tests/backend/test_c04.py`；扩围 `src/backend/app/main.py` 作路由注册、`src/backend/app/schemas/contracts.py` 加载生成 DTO | C04+C03 29 passed、后端 1060 passed、生成物检查 exit 0、`verify.sh` exit 0（UTF-8 输出环境）；[PR #225](https://github.com/arvinhanye/SmartSketch/pull/225) 初次 CI 六项通过；待负责人合并 |

- 输入：C02 课程仓储、C03 身份依赖、ADR-013、`specs/identity-access.md` §3.2/§4.4、`specs/teacher-review-publish.md` V7、`src/contracts/api.v1.yaml`。输出：GET/POST `/api/v1/courses`，只列可见课程；创建课程和创建者教师成员同事务。
- 调用链：H01 页面/状态经 B15 API 客户端消费生成的 `Course`/`CourseCreate`；路由用 C03 `current_user`/`teacher_account`；课程服务调 C02 仓储；SQLite `courses`/`course_members` 持有数据。无 worker、Neo4j、SSE。路径、字段、枚举、错误码和鉴权均沿用 v1 契约；不改真源或生成物。
- 风险：C03 PR #216 已合入 `main@130e6b6`，C04 在该基线上复验；生成 Python DTO 不在后端安装包的导入路径，扩围 `app/schemas/contracts.py` 加载仓库已生成文件，部署打包须由后续 K08 保证携带该文件。无数据库迁移；回滚仅撤销 C04 提交，不触碰 C03。
- 验收命令：`python -m pytest tests/backend/test_c04.py -q`、`python -m pytest tests/backend -q`、`./scripts/gen-contracts.sh --check`（核对契约未漂移）、`./scripts/verify.sh`、`git diff --check`。测试用隔离 SQLite 与 fake 身份数据，覆盖成功、边界、错误、课程隔离和生成 DTO 匹配。
- 实测：C03 基线 17 passed；C04 首个测试先以 404 失败，接入后 9 passed；独立审查指出显式 `description: null` 被生成 Python 模型放宽，新增先失败 HTTP 用例并在路由拒绝，最终 C04 10 passed、后端全量 1029 passed；`gen-contracts.sh --check` exit 0；`verify.sh` 首次因 Windows GBK 控制台无法输出 ✓ 字符 exit 1，设置 `PYTHONIOENCODING=utf-8` 后 exit 0（契约负例 24 项通过）。无前端功能修改，前端类型检查/构建、CI 和合并后验证未运行。
- 集成基线复验（`origin/main@130e6b6`）：C04+C03 定向 29 passed；后端全量 1060 passed；`gen-contracts.sh --check` exit 0；`verify.sh` exit 0（契约负例 25 项通过）。B14 的 3 个用例在本机出现 6 条 GBK 子进程读取警告但均通过。前端功能未改；本机前端类型检查/构建未运行，PR CI 结果见下。
- PR 证据：[C04 PR #225](https://github.com/arvinhanye/SmartSketch/pull/225) 以 main 为目标、差异仅 C04；首次两次 CI 运行的 Repository scaffold、Frontend、Backend 共六项均通过。本文档证据提交后须再次检查最新 CI，不将此视为合并后验证。

## 2026-09-25 Codex 认领：C03

| 原子 ID | 状态 | 任务 | 负责人 | 基线与文件范围 | 验收 |
| --- | --- | --- | --- | --- | --- |
| C03 | DONE（PR #216 `81aa691`；Claude 审查发现 P1 C03-R01，已修复后合并；#60 已关闭） | 实现身份边界与课程访问依赖 | Codex（后端） | `main@a7a0be0`；`app/api/dependencies.py`、`app/services/access.py`、账号/任务仓储只读入口、`tests/backend/test_c03.py`、相关架构与交接 | C03 17 passed；后端 1019 passed；`./scripts/verify.sh` exit 0；交接 `docs/handoffs/codex-c03.md` |

- 输入：`specs/identity-access.md` §2、§4 访问矩阵；输出：可复用的身份/课程/任务访问依赖。依赖 C02、B09、C13 已在当前基线。
- 风险：下游路由尚未接入，C03 提供依赖接口和测试用路由，不代替 C04/C07 等任务实现；仅持有任务 ID 时需仓储先解析归属课程。
- 验证：`python -m pytest tests/backend/test_c03.py -q`、`./scripts/verify.sh`、`git diff --check`。
- 验收证据：Bearer 身份、停用实时失效、请求身份字段无效、课程内角色、未发布和任务越权同形错误均有定向用例；`.venv/Scripts/python.exe -m pytest tests/backend/test_c03.py -q` 17 passed；后端全量 1019 passed；Git Bash 运行 `./scripts/verify.sh` exit 0（契约负向 24 项、B08/B09/B10/B12/B13 回归）；详见交接。


## B12 进度与推荐契约（2026-09-25）

| ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| B12 | DONE（PR #202 `d633160`） | 迁移进度和推荐契约 | ArvinHan（Claude 子代理执行） | `claude/b12-progress-contract` / base `8eeac3b` | `src/contracts/api.v1.yaml`、`src/contracts/v1/generated/`、`tests/contracts/test_b12.py`；按 B08～B13 先例接入 `scripts/verify/contracts.sh`；随附 `specs/learning-path.md` 状态标注与 `docs/handoffs/claude-b12.md` | 改真源前 B12 65 failed / 28 passed，改后 93 passed；契约全量 255 passed；`./scripts/gen-contracts.sh --check` exit 0；`./scripts/verify.sh` exit 0（含 B12 回归）；生成 TS `tsc --noEmit --strict` exit 0；`git diff --check` exit 0；反向篡改 6 处均被检出；范围扩展：`src/contracts/errors.v1.md` 登记 `details.diagnostic_id`；`docs/handoffs/claude-b12.md` |

- 输入：`specs/learning-path.md`（LP-1～19、§7）、ADR-014 及修订 1、`docs/atomic-task-plan.md` B12 行；输出：`ProgressEntry` 新字段、GET/PUT 返回全部节点、推荐 DTO 与未发布错误/全部掌握空态区分。
- 依赖：B08、A08 已完成；B11 已合入并释放 YAML 锁（issue #54）。
- 风险：已提交空图按发布快照完整性故障处理，不增加 `no_graph` wire 状态；未舍入 double 分量按 `u→i→c→e` 求和须逐位等于评分。
- 验证：`python3 -m pytest tests/contracts/test_b12.py -q`、`./scripts/gen-contracts.sh --check`、`./scripts/verify.sh`、`git diff --check`。
- 待决（需 ArvinHan 决定，I02/I05 实现前）：
  1. 学生读路径完整性错误的公开码：契约暂用既有 `INTERNAL_ERROR` + 闭合 `details.diagnostic_id`（`LearningIntegrityError`）；是否新增专用码、字段名是否与问答 `details.request_id` 统一。
  2. `PUT /progress` 中 `kp_id` 不在绑定发布版（草稿独有、已删除、他课、发布指针变化后复核失败）时整批拒绝的公开码（422/404/409）与 `details` 形状；契约描述暂写“待定”。
- 待审查的契约决定：进度响应改为 `ProgressResponse{graph_version, entries}`；移除推荐 `target`/`path`（§7，交 O02）；重复 `kp_id` 归 422 `VALIDATION_ERROR`。详见交接。
- 观察：`tests/contracts/test_b11.py` 未接入 `scripts/verify/contracts.sh`，不在 B12 范围内，未改。
- 合并（2026-09-25）：PR #202。合并前协调方补修 `tests/tooling/test_b07.py` 门禁夹具缺 `test_b12.py` 占位（`verify.sh` 与 CI 均不跑 `tests/tooling`，未检出）。B14 现可占用 YAML 与生成物文件锁。

## B11 图谱编辑与版本契约（2026-09-24）

| ID | 状态 | 任务 | 负责人 | 范围与验收 | 证据 |
| --- | --- | --- | --- | --- | --- |
| B11 | DONE（PR #194 `2de97ba`） | 迁移图谱编辑、关系降级及版本发布契约 | Codex（`arvinhanye`） | `src/contracts/api.v1.yaml`、生成物、`tests/contracts/test_b11.py`、相关规格；补节点修订号与编辑前置条件、关系来源及降级解释、发布/回滚结构化响应；负例与生成一致性 | B11 30 passed、契约全量 162 passed、`./scripts/verify.sh` exit 0、`./scripts/gen-contracts.sh --check` exit 0、`git diff --check` exit 0；`docs/handoffs/codex-b11.md`；协调方把 #196、#194 依次临时合到 `a08bd5b` 上复核：生成物一致、契约与工具 176 passed（B11 30）、后端 720 passed、`verify.sh` exit 0；CI 6 项通过；#53 已关闭 |

- 输入：ADR-009、ADR-012（含修订 3）、A02-R01、B08 真源；输出：B11 YAML 真源、全量生成物、契约测试与交接。
- 依赖：B08、A04 已入 main；B12 暂不占用 YAML 锁。风险：新增必填响应字段影响未来实现方；`merged_from` 与 `commit_seq` 只属内部快照/存储，不泄露到 wire DTO。
- 验证：`python3 -m pytest tests/contracts/test_b11.py -q`、`./scripts/gen-contracts.sh --check`、`./scripts/verify.sh`、`git diff --check`。
- 合并后（2026-09-25）：B12 现可占用 YAML 与生成物文件锁。遗留：`downgrade_cycle` 与 `PUBLISH_BLOCKED` 的 `cycle` 首尾同 ID 由 F13、G04 在服务层校验（契约以 `x-closed-cycle: true` 标记）。

> 状态：`TODO` → `IN PROGRESS` → `BLOCKED` / `DONE`。认领或完成任务时更新本表；每个 DONE 项必须指向验收证据和交接文件。

## 当前里程碑：M0 协作与应用骨架

| ID | 状态 | 任务 | 负责人 | 验收条件 | 证据 |
| --- | --- | --- | --- | --- | --- |
| M0-01 | DONE | 建立多 Agent 协作、文档、规格、源码目录骨架 | Codex | 必需文件齐全；基础校验通过 | `scripts/verify.sh`；`docs/handoffs/codex-m0-project-scaffold.md` |
| M0-02 | DONE（B01～B04 已完成；B15 PR #228 `f37262c`） | 初始化 Vue 3 + TypeScript + Vite 前端 | Frontend Agent | 可启动；具备最小路由、类型检查与测试命令 | B01～B04 见下方验收证据；HTTP 客户端 B15 仍待契约 B14 |
| M0-03 | DONE（B05+B06） | 初始化 FastAPI 后端与健康检查 | Backend Agent | 可启动；`GET /health` 有契约和测试 | B05/B06 测试 38 PASS；基础 verify PASS；`docs/handoffs/codex-b05.md`、`docs/handoffs/codex-b06.md` |
| M0-04 | TODO | 定义第一版 API、SSE 任务事件与图谱 DTO | Backend + Frontend Agent | `src/contracts/` 有版本化契约；双方确认 | 待补充 |
| M0-05 | TODO | 定义 Neo4j/SQLite 开发环境与本地启动方式 | Data/Backend Agent | 无密钥可启动依赖；环境变量文档完整 | 待补充 |

## CI 配置

| ID | 状态 | 任务 | 负责人 | 范围与验收 | 证据 |
| --- | --- | --- | --- | --- | --- |
| CI-01 | DONE（待 GitHub 首次运行确认） | 为当前仓库建立 GitHub Actions 基础质量门禁 | Codex | push、pull request 和手动触发；只运行仓库现有 `scripts/verify.sh`，不把尚未建立的前后端测试标成通过；工作流语法和本地校验通过 | `.github/workflows/ci.yml`；`./scripts/verify.sh` PASS；YAML 解析/关键字段检查 PASS；`git diff --check` PASS；`docs/handoffs/codex-ci-01.md` |
| CI-02 | DONE（待审查；PR #29 已合入 `025cbee`） | 把前端与后端测试接入 CI | Claude | 新增 Frontend（`npm ci`、type-check、`test -- --run`、build）与 Backend（`pip install -e src/backend[test]`、`pip check`、`pytest tests/backend`）两个 job；只读权限、无密钥；不跳过、不吞退出码。依赖：B05/B06 已合入 main（PR #14、#21）；B02（PR #27）未合入前 PR 以 B02 分支为目标。K11 仍负责 E2E 接入 | 分支 `claude/ci-02`；YAML 解析三 job PASS；在含 B02～B06 的临时合并树上以干净环境逐条运行 job 命令：前端 30 passed、build 通过，后端（Python 3.11）58 passed、`pip check` 通过；`docs/handoffs/claude-ci-02.md` |

### CI-01 执行约定

- 输入：当前主分支骨架、`scripts/verify.sh`、仓库现有任务与架构约定。
- 输出：`.github/workflows/ci.yml`、CI 范围说明、交接记录。
- 依赖：GitHub Actions 托管运行器；无项目密钥、数据库或付费模型服务。
- 风险：当前门禁只检查骨架，不能代表尚未实现的前后端测试；后续由 K11 接入实际质量门禁。
- 验证：`./scripts/verify.sh`、工作流 YAML 解析与关键字段检查、`git diff --check`。

## 协作安全修复

| ID | 状态 | 任务 | 负责人 | 范围与验收 | 证据 |
| --- | --- | --- | --- | --- | --- |
| HOOK-01 | DONE | 修复 `block-dangerous.sh` 在命令含双引号时漏检，以及解析失败时放行 | Claude | `.claude/hooks/block-dangerous.sh`、新增 `tests/hooks/test_block_dangerous.sh`、`scripts/verify.sh` 加一行接入回归测试（用户同意）；拦截规则不变，只修命令提取；引号之后的危险命令必须被拦截，无法解析的输入必须拒绝，正常命令不误拦 | 回归测试修复前 10 FAIL / exit 1，修复后 14 PASS / exit 0（含系统 Python 3.9 + `LC_ALL=C`）；会话内实时探针被拦；`./scripts/verify.sh` exit 0 且已包含该测试，换回旧钩子则 verify exit 1；`docs/handoffs/claude-hook-01.md` |

## 下一里程碑：M1 课程资料到草稿图谱

| ID | 状态 | 任务 | 负责人 | 验收条件 |
| --- | --- | --- | --- | --- |
| M1-01 | TODO | 课程与资料上传 API | Backend Agent | 资料记录、格式校验、任务创建、错误响应均有测试 |
| M1-02 | TODO | 文档解析与分块 | Data/AI Agent | 支持四种格式；分块保留定位来源 |
| M1-03 | TODO | 节点关系抽取与融合 | Data/AI Agent | 四类关系；低置信度项可审核；课程隔离 |
| M1-04 | TODO | 前置关系 DAG 校验 | Backend Agent | 环路拒绝、错误可解释、自动化测试 |
| M1-05 | TODO | 教师审核与发布版本 | Full-stack Agent | 可编辑、发布、读取已发布版本 |

## 架构审查与可执行拆分

| ID | 状态 | 任务 | 负责人 | 范围与验收 | 证据 |
| --- | --- | --- | --- | --- | --- |
| PLAN-01 | DONE | 核对架构现状、汇总技术方案、拆分单轮任务、建立 Claude 完成后审查约定 | Codex | 协调文档交付；127 个未认领叶子任务；5 项初始审查问题；本项目会话可读；heartbeat 已创建 | `docs/handoffs/codex-plan-01.md`；`docs/reviews/validate_atomic_plan.py`；`./scripts/verify.sh` 与 `git diff --check` |

### PLAN-01 执行约定

- 输入：当前 checkout、项目规格/ADR、关联 worktree 的只读状态、当前项目 Claude 会话元数据。
- 输出：架构审查、原子任务清单、Claude → Codex 审查流程及交接。
- 依赖：现有协作骨架；无需模型密钥或数据库服务。
- 风险：Claude 可能在其他 worktree 工作；文档方案不等于已实现；会话包含私有内容，仅提取项目和完成状态所需字段。
- 验证：`./scripts/verify.sh`、`git diff --check`、任务 ID/依赖/文档链接结构检查。

### 原子任务派发入口

- [技术全景与现状](architecture-review-2026-09-22.md)；[127 项原子计划](atomic-task-plan.md)；机器可读 `docs/atomic-tasks.json`。
- 119 项主线、8 项条件性加分项均为 PROPOSED，尚未认领；本轮 DONE 仅指规划和审查交付，不指其中实现任务完成。
- 认领时按原子 ID 新增状态行，写目标 worktree/HEAD 和文件所有权；M0/M1 原行保留为父任务，不把未合并 worktree 的完成状态自动搬到 main。
- Claude 完成后的自动审查已启用，规则见 [审查流程](claude-review-workflow.md)，首轮问题见 [审查报告](reviews/codex-claude-initial-2026-09-22.md)。

## 待确认决策

| ID | 问题 | 决策人 | 需要在何时确认 |
| --- | --- | --- | --- |
| D-01 | **已关闭**：定为自编「数据结构 第3章 栈与队列」（`evaluation/fixtures/synthetic.json`，ADR-026，ArvinHan 2026-09-26）。原题：MVP 首批课程示例和脱敏资料来源。所选材料须覆盖一门完整课程的一章，作为赛题抽取硬指标的基准（REQ-01，`specs/course-knowledge-graph.md` 验收 7）；按赛题第 7 节，只用自编示例或许可允许使用的开源教材 | 产品负责人 | 已完成 |
| D-02 | 首个 OpenAI 兼容模型供应商与预算上限。A07 已拆为 D-02a～f 六项，签收入口见 `docs/integrations.md`「待签收取值（D-02）」；配置形状与规则已定。**D-02a 已签收**：主用 DeepSeek V4.1 Flash（`deepseek-flash`，ADR-027，ArvinHan 2026-09-26）；D-02d 已签收（ADR-028，按占位值），抽取评测付费调用已确认；D-02b、c、e 仍未签收 | 技术负责人 | 接入抽取服务前（fake 实现可先行） |
| D-03 | 登录是否先采用本地演示角色。**已关闭**：ADR-013（A05）定为本地账号 + 预置演示账号，不采用纯演示角色；账号类型与课程内角色分离；教师按用户名添加学生（ArvinHan，2026-09-23 签收） | 产品负责人 | 已完成 |
| PLAN-D01 | 两个 Claude 分支 YAML-first/Pydantic-first 唯一源、API 前缀和冲突 ADR 编号如何统一（A01/A02）。**已关闭**：唯一源与 ADR 编号由 ADR-004 签收；API 前缀由 ADR-009（A02）定为 `/api/v1`（均为 ArvinHan，2026-09-22） | 技术负责人 | 已完成 |
| PLAN-D02 | 发布快照/图与向量版本化/双存储补偿方案（A04）。**已关闭**：由 ADR-012（A04）裁定（ArvinHan，2026-09-23 签收） | 技术负责人 | 已完成 |
| PLAN-D03 | worker 队列/租约/取消/重试及部分失败语义（A03/A06）。**已关闭**：取消与部分失败语义由 ADR-010（A03），队列 / 租约 / 重试 / 幂等由 ADR-011（A06）签收（均为 ArvinHan，2026-09-23） | 技术负责人 | 已完成 |
| PLAN-D04 | 哪个 worktree 作为集成基线、分批合并顺序与合并权（A10）。**已关闭**：ADR-016 定为以 main 为基线、按批检出文件导入（每批一个 PR、一个功能边界），Agent 只开 PR、由 ArvinHan 合并并交叉审查；批次顺序见 `docs/reviews/branch-integration-map.md` 第 3 节（ArvinHan，2026-09-23 签收） | 项目负责人 | 已完成 |
| D-08 | 融合自动合并阈值与低置信度阈值的初始取值（沿用 `740adb` 未决问题编号，ADR-016 决定 7） | 技术负责人 | E09/E10 开工前 |
| D-09 | 前端登录页与会话存储缺少原子任务。**已关闭**：补登 **H13 实现前端登录页与会话存储**（依赖 C13、B15、B03、B04；原子清单增至 141 项），负责登录页、`sessionStorage` 会话读写、401 清会话与课程上下文回登录页，并向 B03 的 `getAccountRole` 注入真实来源（ArvinHan，2026-09-24 确认） | 产品负责人 / 协调 Agent | 已完成 |
| D-10 | 迁移文件编号何时确定、表间外键如何约束合并顺序。**已关闭**：编号在合并时取「main 最大编号 + 1」，原子清单中 002～009 改为 `NNN_<名称>.sql`；C02 增加对 C13 的依赖（`course_members.user_id` → `users`）。原因：C01 迁移器拒绝应用比已应用版本更小的编号，按旧计划 C13 的 `008` 先合并会使后到的 004～007 无法应用（ArvinHan，2026-09-24） | 技术负责人 | 已完成 |
| D-11 | 上传单文件大小上限。**已关闭**：50 MiB（52 428 800 字节），环境变量名 `UPLOAD_MAX_BYTES`，超过即 413 `FILE_TOO_LARGE`（`details.limit_bytes`）。与存储目录 `STORAGE_DIR` 一起在 C13 合并后补进 `config.py`、`.env.example`、`docs/integrations.md`（三者当前在 C13 文件锁内）；C05 的 `FileStorage(root, max_bytes)` 由 C06/C07 按此传入（ArvinHan，2026-09-24） | 技术负责人 | 已完成（配置已落地，见「D-11 上传配置落地」） |
| D-12 | Markdown 中 `#` 后不加空格的写法（如 `#第一章`）是否算标题。**已关闭**：放宽，由 D03 在 PR #191 中实现；规则保守，只作用于顶层行，不误伤 `#include`、`#1`、`#tag` 这类行，边界见 `docs/handoffs/claude-d03.md`。D03 首次合并前完成，`parser_version` 仍为 `markdown/1`（ArvinHan，2026-09-24） | 产品负责人 | 已完成 |
| D-13 | 解析器只把标题放进章节路径、标题文字不在块正文里，抽取（D12）看不到标题。**已关闭**：由 D08 分块时在每块正文前拼上章节路径（`section_path`），解析器输出与 D01 模型不变（ArvinHan，2026-09-24） | 技术负责人 | 已完成（D08 实现） |
| D-14 | 只设所有者密码（空用户密码即可打开，仅限制复制、打印等权限）的 PDF 是否放行。**暂定**：与其他加密 PDF 一样按 `DOCUMENT_UNREADABLE`（`encrypted`）拒绝（ArvinHan，2026-09-25）。放行前须决定是否遵守「禁止复制」等权限，涉及版权 | 产品负责人 | 首批课程资料导入前（D-01） |
| D-15 | 赛题「知识抽取准确率不低于 70%」是否同时约束关系（REQ-01）。**已关闭**：实体和关系分别计算、各自不低于 70%，写入 `specs/course-knowledge-graph.md` 验收 7 与 K01/K02（ArvinHan，2026-09-24） | 产品负责人 | 已完成 |
| D-16 | C07 资料列表的 `Document.parse_status` 取自哪里、失败/取消后的「再处理」入口（A03 交出项）。**已关闭**：`parse_status` 在读时取该资料**最新创建任务**的 `stage`（单一事实来源，worker 不另写）；`materials.parse_status` 列不再维护，保留默认值待后续迁移清理。MVP 的再处理只靠**重新上传**（新资料、新任务），不新增端点、不改契约；再处理端点留作后续任务（ArvinHan，2026-09-25） | 技术负责人 | 已完成（C07 落实） |
| D-17 | 教师图谱编辑页缺少原子任务：H11 是学生端浏览页（不取草稿），H09 审核队列不含画布编辑，H07 节点编辑面板与 H08 连边编辑无页面可挂，K05 教师主线无法端到端覆盖编辑。**已关闭**：补登 **H14 实现教师图谱编辑页**（依赖 H05、H06、H07、H08；K05 增加对 H14 的依赖；原子清单增至 142 项）（ArvinHan，2026-09-26 选择「新增任务」；issue #281） | 产品负责人 / 协调 Agent | 已完成（清单补登；实现待认领） |
| PLAN-D05 | 学习材料生成分支决定是否同步 main；目标路径是否纳入（O01） | 产品负责人 | 主线验收后、加分项前 |

## Claude 审查批次

| ID | 状态 | 范围 | 负责人 | 验收与证据 |
| --- | --- | --- | --- | --- |
| REVIEW-02 | DONE（分批；S-07 尚有待审范围） | A01 文档交付 `88ea517`/`6c19f25`；S-07 本地脚本 `8865686` | Codex | `docs/reviews/codex-claude-a01-s07-tooling-2026-09-23-0136z.md`；A01 路径映射 22/29 一致；S07-R12～R14 已复现；`docs/handoffs/codex-review-02.md` |
| REVIEW-A08 | DONE（不建议签收；R02/R03 已签收为 ADR-014；待 Codex 修 R01～R04） | Codex A08 未提交快照（`codex-a08-learning-path` @ `1a47eb2` + dirty，指纹见报告） | Claude | `docs/reviews/claude-codex-a08-2026-09-23.md`：P2×4（R01 `no_graph` 与 A04 V3 冲突、R02 中心度恒 ≤0.5、R03 合并进度倒退未列签收、R04 外课/历史 ID 判定不可实现）、P3×6；R02/R03 的产品决定见 `docs/decisions.md` ADR-014；`docs/handoffs/claude-review-a08.md` |
| REVIEW-A08-R2 | DONE（R01～R10 已修；R11～R14 由 Codex 修复后第 3 轮复审通过，无新 P1/P2；§7 与 ADR-014 两项细则已由 ADR-014 修订 1 签收，R15 按“以本次连续归属起点为界”写死） | Codex A08 修订稿（`codex-a08-learning-path` @ `1a47eb2` + dirty，规格 `efe23f9e…`，指纹见报告） | Claude | `docs/reviews/claude-codex-a08-r2-2026-09-23.md`：R01～R10 复核通过（R01 在 `atomic-tasks.json` B12 与 I05 仍有“无图”残留）；P2×1（R11 合并继承后进度接口返回原始还是有效状态未定义）、P3×4（R12 谱系终止与不变式、R13 舍入后分量不可还原、R14 任务清单 Markdown/JSON 不一致、R15 细则 1 提案有歧义）；`docs/handoffs/claude-review-a08-r2.md` |
| REVIEW-03 | DONE（仅 R06 修复；S-07 仍待审） | S-07 `978671e` 的 UTF-8 生成物缺失假绿修复 | Codex | `docs/reviews/codex-claude-s07-r06-978671e-2026-09-23-0305z.md`；定向回归 PASS；`verify.sh` 因生成物未入库 exit 1；`docs/handoffs/codex-review-03.md` |
| REVIEW-04 | DONE（固定提交批次；活跃会话与 S-07 仍待审） | A02 `13d586e` 文档决定；HOOK-01 `3c2dfab` 命令提取修复 | Codex | `docs/reviews/codex-claude-a02-hook01-2026-09-23-0528z.md`；A02-R01 P2；HOOK-01 回归 14 PASS；`docs/handoffs/codex-review-04.md` |
| REVIEW-05 | DONE（A03 固定提交；S-07 仍待审） | A03 `2049129` 生命周期规范；CI-01 交接 `43a278c`/`25d96cf`；S-07 四个生成物 | Codex | `docs/reviews/codex-claude-a03-ci01-s07-2026-09-23-0606z.md`；A03-R01/R02 P2；A03 骨架门禁 PASS；`docs/handoffs/codex-review-05.md` |
| REVIEW-06 | DONE（A06 发现 P1；其他旧范围仍待审） | A03 `6345ce1` 修复复核；A06 `ab04053` 租约/清理规范 | Codex | `docs/reviews/codex-claude-a03fix-a06-ab04053-2026-09-23-0649z.md`；A03-R01/R02 文字冲突已修；A06-R01/R02 P1；骨架门禁 PASS；`docs/handoffs/codex-review-06.md` |
| REVIEW-07 | DONE（A04 发现 P1/P2；A05/A07 仍待稳定） | A04 `110f243` 发布协议与合并冲突 `4b2ccb5` | Codex | `docs/reviews/codex-claude-a04-4b2ccb5-2026-09-23-0730z.md`；A04-R01 P1、A04-R02 P2；文档结构检查及 diff check PASS；`docs/handoffs/codex-review-07.md` |
| REVIEW-08 | DONE（A05 无新问题；A07 发现 P2；其他旧范围仍待审） | A05 `e0b7ccd` 身份边界；A07 `af9ff7d` 模型配置 | Codex | `docs/reviews/codex-claude-a05-a07-2026-09-23-0804z.md`；A07-R01 P2；两目标骨架门禁与 diff check PASS；`docs/handoffs/codex-review-08.md` |
| REVIEW-09 | DONE（固定修订复核；新增 2 项 P2；旧待审范围保留） | A04 `02bc228`、A06 `d426170`、A07 `1012b6f` 文档修订 | Codex | `docs/reviews/codex-claude-a04-fixes-1012b6f-2026-09-23-1215z.md`；FIX-R01/R02 P2；目标骨架门禁与 diff check PASS；`docs/handoffs/codex-review-09.md` |
| REVIEW-10 | DONE（FIX-R01/R02 原缺口文档层关闭；新增 FIX-R03 P2） | FIX-R01/R02 修复提交 `5186e09` 的文档复核 | Codex | `docs/reviews/codex-claude-fix-r01-r02-5186e09-2026-09-23-1252z.md`；固定提交目标 `./scripts/verify.sh` PASS、`git diff 1a47eb2..5186e09 --check` PASS；主目录 `./scripts/verify.sh` 与 `git diff --check` PASS；`docs/handoffs/codex-review-10.md`。仅文档、无运行时测试；旧待审范围保留 |
| REVIEW-11 | DONE（仅 S-07 DAG 任务/规格批次；其余待审） | S-07 `978671e` 的合并任务与课程图谱前置关系验收 | Codex | `docs/reviews/codex-claude-s07-dag-plan-2026-09-23-1304z.md`；S07-R15 P2；目标两次稳定，`git diff 05d214c..978671e --check` PASS；`docs/handoffs/codex-review-11.md` |
| REVIEW-12 | DONE（仅 A09 固定文档批次；A10 与旧范围待审） | A09 `1754c96` 问答终态/引用协议 | Codex | `docs/reviews/codex-claude-a09-1754c96-2026-09-23-1400z.md`；A09-R01/R02 P2；目标两次稳定，`./scripts/verify.sh` 与 `git diff f9dfc8f..1754c96 --check` PASS；`docs/handoffs/codex-review-12.md` |
| REVIEW-13 | DONE（仅 A10 固定文档批次；A08 签收与旧范围待审） | A10 `37da669` 导入映射与 ADR-016 | Codex | `docs/reviews/codex-claude-a10-37da669-2026-09-23-1403z.md`；A10-R01/R02 P2；目标稳定，骨架门禁、diff check、映射核对及 8 个负例 PASS；`docs/handoffs/codex-review-13.md` |
| REVIEW-14 | DONE（仅 A08 签收六文件差异；旧范围仍待审） | A08 签收 `f9dfc8f` 上稳定未提交文档 | Codex | `docs/reviews/codex-claude-a08-signoff-f9dfc8f-2026-09-24-0123z.md`；A08S-R01 P2、A08S-R02 P3；目标 `./scripts/verify.sh`、`git diff HEAD --check`、任务 JSON 语法均 PASS；`docs/handoffs/codex-review-14.md` |
| REVIEW-15 | DONE（仅 A09 修复文档批次；旧范围仍待审） | A09 `1754c96..68b1aaf` 逐句引用与日志规则复核 | Codex | `docs/reviews/codex-claude-a09-fix-68b1aaf-2026-09-24-0200z.md`；A09-R02 文档层关闭，A09F-R01/R02 两项 P2；目标 `./scripts/verify.sh` 与 diff check PASS；`docs/handoffs/codex-review-15.md` |
| REVIEW-16 | DONE（仅 A10 批 1 补；其余待审） | `batch1-qa@3da4f2f` 问答规格命名门禁与逐规格负例 | Codex | `docs/reviews/codex-claude-batch1-qa-3da4f2f-2026-09-24-0446z.md`；无新问题；目标 `verify.sh`（24/24 契约负例）与 diff check PASS；`docs/handoffs/codex-review-16.md` |
| REVIEW-17 | DONE（仅 FIX-R03 规格补注；其余待审） | `wrap-fix-pr16@8dcd7b2` 迁移与运行时空间写入边界 | Codex | `docs/reviews/codex-claude-fix-r03-8dcd7b2-2026-09-24-0451z.md`；FIX-R03 文档层关闭，无新问题；目标骨架门禁、diff check PASS；F03/PUB-39 运行时未实现；`docs/handoffs/codex-review-17.md` |
| REVIEW-18 | DONE（仅 B02 固定提交；B03/B04 与旧范围待审） | `a09-dev-environment-check-8e5e93@8e5b707` 前端测试配置 | Codex | `docs/reviews/codex-claude-b02-8e5b707-2026-09-24-0504z.md`；11 个改动文件已审、无新增问题；隔离副本类型检查、5 用例、构建 PASS；`verify.sh` 因本机缺契约依赖 FAIL（验证缺口）；`docs/handoffs/codex-review-18.md` |
| REVIEW-19 | DONE（B03/B04 固定提交审查；集成与旧范围待审） | B03 `8153186`、B04 `225f102` 与共用准备 `9dddcb4` | Codex | `docs/reviews/codex-claude-b03-b04-2026-09-24-0605z.md`；B03-R01、B04-R01 两项 P2；两隔离副本类型检查、定向/全量测试、构建 PASS；`verify.sh` 缺契约依赖 FAIL；`docs/handoffs/codex-review-19.md` |
| REVIEW-20 | DONE（仅 B10 固定提交；B13 与旧范围待审） | B10 `3771ae1` 任务快照、SSE 与票据契约 | Codex | `docs/reviews/codex-claude-b10-3771ae1-2026-09-24-0703z.md`；B10-R01/R02 两项 P2；隔离副本 36 用例与生成物一致性 PASS；`docs/handoffs/codex-review-20.md` |
| REVIEW-21 | DONE（仅 B13 固定提交；发现 2 项 P2） | B13 `14d405d` 问答与事件契约 | Codex | `docs/reviews/codex-claude-b13-14d405d-2026-09-24-1104z.md`；B13-R01/R02；隔离副本 B13 43 用例和 `verify.sh` PASS；`docs/handoffs/codex-review-21.md` |
| REVIEW-22 | DONE（仅 B10 修正固定提交；集成与旧范围待审） | B10 `21de627` 的 R01～R04 契约修正 | Codex | `docs/reviews/codex-claude-b10-fix-21de627-2026-09-24-1556z.md`；旧 B10-R01/R02 在 JSON Schema 层关闭，新增 B10F-R01 P2、B10F-R02 P3；隔离副本 B10 45 用例 PASS，完整门禁最终输出 PASS 但退出码因中断未确认；`docs/handoffs/codex-review-22.md` |
| REVIEW-23 | DONE（仅 A08 修复固定提交；集成与旧范围待审） | A08 `445478e..2f2e4ce` 同值进度写入与任务板修复 | Codex | `docs/reviews/codex-claude-a08-fix-2f2e4ce-2026-09-24-1603z.md`；A08S-R01/R02 文档层关闭、无新问题；目标 `./scripts/verify.sh` 与 diff check PASS；`docs/handoffs/codex-review-23.md` |
| REVIEW-24 | DONE（仅 D02 固定提交；其他新 worktree 与集成待审） | D02 `588d00a..4651700` TXT 解析器三文件 | Codex | `docs/reviews/codex-claude-d02-4651700-2026-09-25-0403z.md`；D02-R01 P2；目标两次稳定，定向 94 PASS，控制字节反例复现，diff check PASS；`docs/handoffs/codex-review-24.md` |
| REVIEW-25 | DONE（仅 C05 固定提交；C06/C07 与集成待审） | C05 `68affa8..d3b7a6c` 文件落盘边界三文件 | Codex | `docs/reviews/codex-claude-c05-d3b7a6c-2026-09-25-0502z.md`；本批无新增问题；两次指纹稳定，定向 61 PASS，diff check PASS；`docs/handoffs/codex-review-25.md` |
| REVIEW-26 | DONE（仅 D01 固定提交；其他新 worktree 与集成待审） | D01 `909ce33..74be60d` 解析模型与 fixture 十文件 | Codex | `docs/reviews/codex-claude-d01-74be60d-2026-09-25-0503z.md`；D01-R01 P3；目标两次稳定，定向 88 PASS，Anaconda 环境完整门禁 PASS，末尾换行反例复现；`docs/handoffs/codex-review-26.md` |

## 原子任务认领（`docs/atomic-task-plan.md`）

> 本节只记录本 worktree 认领的叶子任务。main 的 `docs/tasks.md` 另有 PLAN-01 与 PLAN-D01～D05 行（已提交为 `9ddcef8`）；合并时保留双方，main 的 PLAN-D 行在前、本节在后。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A01 | DONE（ADR-004 已签收） | 裁决契约唯一来源与 ADR 编号 | Claude（协调 Agent） | `.claude/worktrees/adoring-sinoussi-709263` / base `05d214c` | `docs/decisions.md`、`docs/architecture.md`、本节、`docs/handoffs/claude-a01.md` | `docs/decisions.md` ADR-004；`docs/handoffs/claude-a01.md`；`./scripts/verify.sh` exit 0、`git diff --check` exit 0 |

- A01 的交付物（ADR-004 裁定 + 迁移映射）已于 2026-09-22 由 ArvinHan 签收，成为生效决定。PLAN-D01 的「唯一源」「ADR 编号」两项随之关闭；「API 前缀」按 ADR-004 交给 A02，已由 ADR-009 关闭（见下方 A02 行）。
- A01 未触发任何分支合并；集成基线与合并顺序仍是 PLAN-D04 / 原子任务 A10 的范围。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| M0-09 第一步 | DONE | 安装契约生成工具链并实测生成链（B14 前置） | Claude | 同上 / base `05d214c` | `docs/handoffs/claude-m0-09-toolchain.md`、`docs/decisions.md` 的 ADR-004 实测补注 | 完整生成 exit 0、两次字节一致、`--check` exit 0、四处篡改均非 0、Pydantic import 54 个模型 |

- 工具安装经用户授权：`datamodel-code-generator==0.26.3` 在 venv `~/.local/share/smartsketch/contracts-venv`，`openapi-typescript@7.4.4` 全局。实测在 scratch 副本进行，未修改 `740adb` 的 worktree。
- 实测发现的两个脚本缺陷（Pydantic 产物落成无扩展名文件；`--check` 缺产物时退出 2 并吞掉提示）**已修**：经用户授权直接提交在 `claude/worktree-contract-conflicts-740adb` 的 `8865686`，只改 `scripts/gen-contracts.sh` 一个文件。修复前后对照与 13 项回归矩阵见交接文件。**更正**：该修复在 UTF-8 locale 下引入了新的假绿（Codex S07-R06），已在 `978671e` 修复并加回归测试（13 项矩阵只在 C locale 下跑过）。
- 仍未做：生成物入库（需先定 PLAN-D04 集成基线）；`--check` 顶层陈旧阶段检不出（留给 B14）。`740adb` 的 `verify.sh` 现为 exit 1，原因是产物未入库，不是脚本缺陷（`978671e` 后 C 与 UTF-8 locale 均实测）。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| S07-R06 修复 | DONE | 修复 `8865686` 在 UTF-8 locale 下引入的 `--check` 假绿（Codex 审查 P1） | Claude | `worktree-contract-conflicts-740adb` / base `8865686` | `scripts/gen-contracts.sh`、`tests/contracts/test_contracts.py` | `978671e`；回归测试先红后绿；C / en_US.UTF-8 / zh_CN.UTF-8 缺产物均 exit 1；契约测试 21/21；交接见 `docs/handoffs/claude-m0-09-toolchain.md` 第三节更正 |

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A02 | DONE（ADR-009 已签收） | 统一路径前缀和领域枚举 | Claude（协调 Agent） | `.claude/worktrees/adoring-sinoussi-709263`（分支 `claude/a02-start-4064b7`）/ base `bfa236c` | `specs/course-knowledge-graph.md`、`docs/architecture.md`；**范围扩展**：`docs/decisions.md`（新增 ADR-009 + ADR-004 指针一行，AGENTS.md §6 要求已确认选择入 ADR）、本节、`docs/handoffs/claude-a02.md` | `docs/architecture.md`「API 前缀与 wire 枚举」；`specs/course-knowledge-graph.md`「前置关系成环处理」DAG-1～11；`docs/decisions.md` ADR-009；枚举表对 `740adb` `978671e` YAML 逐值核对 ALL PASS，`ff30e0` 与篡改副本均被检出（exit 1）；`./scripts/verify.sh` exit 0、`git diff --check` exit 0；`docs/handoffs/claude-a02.md` |

- A02 的决定（ArvinHan，2026-09-22 签收）：前缀 `/api/v1`（`/health` 例外）；只有 `ErrorCode`、`RelationType` 用 UPPER_SNAKE，其余 wire 枚举一律 lower_snake，`NOT_COVERED` 是概念名、wire 为 `status: "not_covered"`；自动候选成环降级为 `RELATED_TO` + 送审、不使任务失败，人工编辑成环 409 拒绝。
- A02 交出的后续项（均未认领）：**B11** 须先在 `api.v1.yaml` 给 `Relation` 增加「降级原类型与环路」字段，F13 依赖它；`740adb` `src/contracts/README.md` 的 `not_covered_reason` 应为 `reason`；ADR-005 导入时加注指向 ADR-009；Neo4j 文本块标签 `SourceChunk`（main）与 `Chunk`（ADR-008）不一致，交 A10。状态转换与取消语义仍归 **A03**（现可认领，依赖 A02 已满足）。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A03 | DONE（ADR-010 已签收） | 定义任务生命周期和取消协议 | Claude（协调 Agent） | `.claude/worktrees/a03-d430b9`（分支 `claude/a03-task-lifecycle`）/ base `931361d` | `specs/task-processing.md`（新建）；**范围扩展（用户同意）**：`docs/decisions.md`（新增 ADR-010 + ADR-004 编号表下指针一行）、`specs/course-knowledge-graph.md` 验收 2、`docs/architecture.md`（三处「归 A03 / A03 复核」占位 + SSE 终止事件一行）、PLAN-D03 行、本节、`docs/handoffs/claude-a03.md` | `specs/task-processing.md`（T1～T9、取消矩阵、部分失败、失败码、SSE 关流与重连、TASK-1～19）；`docs/decisions.md` ADR-010；核对脚本 62 项 ALL PASS（含对 `740adb` `978671e` 真源的缺口核实），7 个篡改副本均被逐条检出（exit 1、无崩溃）；`./scripts/verify.sh` exit 0、`git diff --check` exit 0；`docs/handoffs/claude-a03.md` |

- A03 的决定（ArvinHan，2026-09-23 签收）：`awaiting_review` = 处理完成（不可取消、不会失败、推送后关流），`completed` = 发布时推进 T6 提交序号 ≤ 快照任务水位的任务（含内容被全部驳回者；措辞经 A03-R02 修订）；`persisting` 不可取消，`merging → persisting` 是最后取消点；抽取部分失败按 `TASK_MAX_FAILED_CHUNK_RATIO`（默认 0.2）判定；重连由前端封装管理，不依赖 `EventSource` 自动重连。
- A03 交出的后续项（均未认领）：**B10** 补 `Task.cancel_requested`、`TaskCounts.chunks_failed`、`Task.failed_chunks`、`failed ⇔ error` 约束与取消端点描述，并把 `events.v1.md` §2/§4 改为指向本规格；**B08** 加 4 个提议错误码；**A06** 补写 `specs/task-processing.md` §8；**A07** 登记阈值变量；**A04/A06** 定 `persisting` 与发布快照的串行化机制；C06/C07 定再处理入口与 `Document.parse_status` 跟随哪个任务。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A03-R01/R02 修复 | DONE | 修复 Codex 审查 A03-R01（SSE 在 `awaiting_review` 关流后「全部可通过 SSE 观察 / 终态事件恰好一次」措辞失真）与 A03-R02（T7 发布推进谓词与「全部驳回仍 `completed`」自相矛盾） | Claude | `.claude/worktrees/a03-d430b9`（分支 `claude/a03-task-lifecycle`）/ base `2049129` | `specs/task-processing.md`、`specs/course-knowledge-graph.md` 验收 2、`docs/architecture.md` SSE 事件表一行与「文档用语 → wire 值」映射一行、`docs/decisions.md` ADR-010、本节、`docs/handoffs/claude-a03.md` | 审查报告 `docs/reviews/codex-claude-a03-ci01-s07-2026-09-23-0606z.md`（主目录）；核对脚本新增 12 项先红后绿，共 74 项 ALL PASS；新增 5 个负例（N8～N12），连同原 7 个共 12 个均被逐条检出；A02 枚举核对回归 ALL PASS；`./scripts/verify.sh` exit 0、`git diff --check` exit 0；`docs/handoffs/claude-a03.md` 第九节 |

- A03-R01/R02 的修复不改变 ADR-010 的决定方向，只澄清措辞：任务 SSE 只覆盖处理阶段，每个连接恰好以一条结束事件收尾，`completed` 通过任务查询或课程发布状态观察；T7 推进谓词统一为「T6 提交序号 ≤ 快照任务水位」。新增 TASK-20～22。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A06 | DONE（ADR-011 已签收） | 定义 worker 租约和幂等机制 | Claude（协调 Agent） | `.claude/worktrees/a03-d430b9`（分支 `claude/a06-worker-lease`，叠在 `claude/a03-task-lifecycle` 之上）/ base `6345ce1` | `specs/task-processing.md`（§8 及 §1～§7 中指向 A06 的指针、§6「由 A06 定」一行）、`docs/decisions.md`（新增 ADR-011）；**范围扩展（用户同意）**：`docs/architecture.md`（目录表 workers 行、核心数据模型 SQLite 列表）、PLAN-D03 行、本节、`docs/handoffs/claude-a06.md` | `specs/task-processing.md` §8（部署边界、领取/租约/回收、三层重试与耗尽码、各阶段幂等、课程写锁、中间产物、迁移备份与回滚、配置、LEASE-1～17）；`docs/decisions.md` ADR-011；A06 核对脚本 45 项 ALL PASS，9 个篡改副本均被逐条检出；A03 核对（74 项）与 12 个负例、A02 枚举核对回归均通过；`./scripts/verify.sh` exit 0、`git diff --check` exit 0；`docs/handoffs/claude-a06.md` |

- A06 的决定（ArvinHan，2026-09-23 签收）：worker 为与 API 同机的独立进程，共用 SQLite（WAL）作队列，不支持跨机器；单条条件更新领取、60 秒租约心跳续约、令牌防旧写；三层重试（模型调用 / 块 2 次 / 任务 3 次），存储不可用与模型熔断为阶段级临时故障，退避后重排；`extracting` 块级检查点续跑，`persisting` 在课程写锁下单事务 `MERGE`；迁移须停机、`VACUUM INTO` 备份并校验，回滚靠备份恢复。PLAN-D03 至此全部关闭。
- A06 交出的后续项（均未认领）：**B08** 增加 `TASK_ATTEMPTS_EXHAUSTED`；**A07** 登记 §8.8 五个变量；**E 组** 定模型调用缓存键与失效（`merging` 重跑依赖）；**E04** 暴露熔断状态；**A04** 定发布侧何时持课程写锁；C01/C09/E12/F13/K08 按 §8 实现。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A04 | DONE（ADR-012 已签收） | 定义图谱版本和跨库发布协议 | Claude（协调 Agent） | `.claude/worktrees/a04-f5f479`（分支 `claude/a04-f5f479`）/ base `931361d` | `specs/teacher-review-publish.md`（main 新建，以 `740adb` 草稿桩为底稿）、`docs/architecture.md`；**范围扩展**：`docs/decisions.md`（新增 ADR-012；ADR-010/011 已被 A03/A06 的 PR #5/#6 占用。AGENTS.md §6 要求已确认选择入 ADR）、本节、`docs/handoffs/claude-a04.md` | `specs/teacher-review-publish.md`「图谱版本与跨库发布协议」V1～V11（PUB-1～27：成功 4 / 边界 13 / 失败 10）；`docs/architecture.md`「图谱版本与跨库发布」；`docs/decisions.md` ADR-012（已签收）；对 `740adb` `978671e` YAML、A03 `6345ce1`、A06 `ab04053` 与全部远端分支 ADR 的核对脚本 ALL PASS，三个篡改副本均 exit 1；`./scripts/verify.sh` exit 0、`git diff --cached --check` exit 0；`docs/handoffs/claude-a04.md` |

- A04 的决定（ArvinHan，2026-09-23 签收，ADR-012）：SQLite 规范化快照为真相 + Neo4j 按 `version_id` 物化副本；回滚前滚为新版本号，回滚到当前版本幂等；发布集合摘要等于当前发布版则幂等；回滚不动草稿；排除 `low_confidence`，疑似重复与孤立节点只提示；课程写锁扩大到所有草稿写入（修订 ADR-011 决定 6）。
- A04 交出的后续项（均未认领）：**B08** 新增 `PUBLISH_IN_PROGRESS`、`COURSE_BUSY`；**B11** `PublishResult`/`GraphVersion` 加字段、回滚端点补 409、`details.reasons` 结构；**A07** 登记 `PUBLISH_LEASE_SECONDS`、`COURSE_LOCK_WAIT_SECONDS`；**A10** 导入 A06 规格时在 §8.5 加注指向 ADR-012，并统一文本块标签名；G02 状态名改为 `preparing/materialized/committed/failed`。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A07 | DONE（形状已定；取值待 D-02a～f 签收） | 落实模型配置形状与预算决策入口 | Claude（协调 Agent） | `.claude/worktrees/a07-297f68`（分支 `claude/a07-model-config`，叠在 `claude/a06-worker-lease` 之上）/ base `ab04053` | `docs/integrations.md`、`.env.example`；**范围扩展**：D-02 行（指向签收入口）、本节、`docs/handoffs/claude-a07.md` | `docs/integrations.md`「运行时环境变量」（38 个变量，类型/约束/样例/状态）与「模型接入规则（A07）」（切换矩阵、预算、模型版本与向量空间、启动校验、待签收取值 D-02a～f）；`.env.example` 与之逐项一致；核对脚本 344 项 ALL PASS（含对 §8.8、ADR-010 阈值与 `740adb` 命名的逐项核对），11 个篡改副本均被检出（exit 1）；`./scripts/verify.sh` exit 0、`git diff --check` exit 0；`docs/handoffs/claude-a07.md` |

- A07 的形状（ArvinHan，2026-09-23 在会话中确认三节设计）：平铺环境变量、沿用 `740adb` 命名；显式 `LLM_MODE` / `EMBEDDING_MODE`，生产禁 fake；每次调用先试主用、熔断器负责粘住备用；鉴权失败不切备用；流式出字后不切换；向量永不跨模型切换；预算按 token 计的软上限（任务 + 每日），`0` 不发请求、无「不限」写法，向量调用不计入；被拒调用走所在环节既有失败路径。**取值未签收**：D-02a～f 见 `docs/integrations.md`，签收后写 ADR。
- A07 交出的后续项（均未认领）：**B08** 加 `BUDGET_EXCEEDED`（D-02f）；**B06** 按「启动校验」实现设置加载；**E03/E04** 实现切换矩阵、熔断与预算，退避参数须有上限；**E07** 发送 `dimensions`、比对返回长度、按 `EMBEDDING_BATCH_SIZE` 分批；**D09/E 组** 缓存键用实际给出结果的模型 ID；**A10** 导入 `740adb` 时 `.env.example` 与 `docs/integrations.md` 会文本冲突，模型与任务段取本分支、存储与 Neo4j 容器段取 `740adb`。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A05 | DONE（ADR-013 已签收） | 定义课程成员与本地身份边界 | Claude（协调 Agent） | `.claude/worktrees/a05-aa1561`（分支 `claude/a05-identity-access`）/ base `931361d` | `specs/identity-access.md`（新建）、`docs/decisions.md`（新增 ADR-013）；**范围扩展**：本节与 D-03 行、`docs/handoffs/claude-a05.md` | `specs/identity-access.md` 访问矩阵 33 行 + IAM-1～25；`docs/decisions.md` ADR-013；对 `740adb` `978671e` 契约逐项核对 150 PASS，6 个篡改负例均 exit 1；`./scripts/verify.sh` exit 0、`git diff --check` exit 0；`docs/handoffs/claude-a05.md` |

- A05 的决定（ArvinHan，2026-09-23 签收）：本地账号登录，演示账号由种子脚本创建、口令只来自环境变量，无注册端点；调用者身份只来自已验证的令牌，不读请求中的 `user_id`；`users.role` 只决定首页和能否建课，课程内授权只看 `course_members.role` 并每次回查；教师按用户名添加学生；进度、推荐、问答仅学生成员可用，教师不开放；SSE 改用一次性票据（Codex S07-R07、A03 移交项）。
- A05 交出的后续项（均未认领）：**B08 / B09 / B10** 按 `specs/identity-access.md` §7 改契约（`my_role`、成员三操作、票据端点与安全方案、补 `401`）；**原子清单缺口**：登录端点与令牌签发、账号命令行与演示种子、成员管理 API、成员管理页面、票据申领端点，清单均无承接任务，需协调 Agent 拆分编号；`event_tickets` 表补登命名基线交 **A10**（`docs/architecture.md` 现由 A04 持锁）；`AUTH_JWT_SECRET` 等三个变量写入 `.env.example` 交 **A07 或 C03**。
- ADR 编号：ADR-010、011、012 分别由 A03、A06、A04 使用（PR #5、#6、#7；A04 原与 A03 同撞 010，已改用预留的 012），A05 取 013。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A10 | DONE（ADR-016 已签收） | 整理已有成果导入顺序与任务映射 | Claude（协调 Agent） | `.claude/worktrees/quirky-dijkstra-eca5de`（分支 `claude/a10-integration-map`）/ base `6881ffe` | `docs/reviews/branch-integration-map.md`（新建）、本节与 PLAN-D04 行、`docs/handoffs/claude-a10.md`；**范围扩展**：`docs/decisions.md`（新增 ADR-016 + ADR-004 指针一行，AGENTS.md §6 要求已确认选择入 ADR）、「待确认决策」新增 D-08 行（ID-4 的决定） | `docs/decisions.md` ADR-016；`docs/reviews/branch-integration-map.md`：92 个文件逐一处置（导入 56、待决 13、不导入 12、随任务导入 6、逐段合并 3、部分导入 2），批 0～6 各一个功能边界，15 项待签收决定各有签收人，任务编号与清单缺口映射；`740adb` 副本补齐生成物后门禁 exit 0，批 1 叠到 main 副本上 exit 1（原因与修法见第 3 节）；`check_a10.py` ALL PASS，8 个负例均 exit 1；`./scripts/verify.sh` exit 0、`git diff --check` exit 0；`docs/handoffs/claude-a10.md` |

- A10 的决定（ArvinHan 2026-09-23 签收，ADR-016）：以 main 为集成基线，不对 `740adb` 做 `git merge`，按批检出文件、每批一个 PR；先合在途 PR #16、#14、#15，再按批 0～6 推进。批 1（契约真源）须先签 N1（文本块标签），并同时调整命名门禁与测试夹具；批 5（ADR 拆分与命名基线）须先签 S03-1 与 N1～N4；批 6 须先签 PLAN-D05。
- A10 交出的后续项（均未认领）：批 0～6 的执行；原子清单缺口 G-1～G-6（登录与成员管理、重新向量化命令、消融实验、参赛材料与合规等）在批 0 补登编号；D-08 已写入「待确认决策」。命名按 ADR-016 决定 6：`Chunk`、`Document`、`model_calls`、`GraphVersion`，问答记录名交 A09。ADR-015 留给 A09。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A04-R01/R02 修复 | DONE（ADR-012 修订 1 已签收） | 修复 Codex 审查 A04-R01（历史版本只按 `material_id` 过滤会检索到后来的文本块）与 A04-R02（换向量模型后幂等发布与回滚规则冲突） | Claude（协调 Agent） | `.claude/worktrees/a04-f5f479`（分支 `claude/a04-r01-r02-fix`）/ base `0630664` | `specs/teacher-review-publish.md`、`docs/decisions.md`（ADR-012 修订 1）、`docs/architecture.md`、`docs/tasks.md`、`docs/handoffs/claude-a04.md`；**范围扩展**：`specs/task-processing.md` §8.4 `parsing` 行与 §8.6 删除规则（块 ID 与删除保护，A06 条文）、`docs/integrations.md` 两处「重新向量化」（A07 条文） | 规格 V2/V3/V5/V6/V8/V10 修订、新增 V12 与 PUB-28～34；ADR-012 修订 1（决定 9～12）；A06 §8.4/§8.6 与 A07 两处已改并加注；核对脚本 55 项 ALL PASS，三个篡改副本 exit 1；`./scripts/verify.sh` exit 0、`git diff --cached --check` exit 0；`docs/handoffs/claude-a04.md` 第十节 |

- A04-R01/R02 的修复（ArvinHan 2026-09-23 签收，ADR-012 修订 1）：文本块按资料修订（资料 + 内容哈希 + 解析器版本）生成 ID 且不可变，快照固定修订列表，检索按 `revision_id` 过滤；失败任务的来源块加删除保护；运行时只有一个向量空间，换模型须停机离线重新向量化全部文本块、草稿与已提交版本，配置与记录不一致即拒绝启动。
- 交出的后续项（均未认领）：**A10** 在清单中为「重新向量化命令」补登叶子任务；**C06/C07** 定义「下线旧资料修订」；**B06/D09/D10/C09/D11/E07/F03** 按 ADR-012 修订 1 的实现依赖落实。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A06-R01/R02 修复 | DONE（ADR-011 修订 1 已签收） | 修复 Codex 审查 A06-R01（失败清理会删除被其他任务复用的图元素）与 A06-R02（`cleanup_pending` 期间失败任务仍可暴露草稿） | Claude（协调 Agent） | `.claude/worktrees/a04-f5f479`（分支 `claude/a06-r01-r02-fix`）/ base `50a15c9` | `specs/task-processing.md`（I6、§8.4、§8.9）、`docs/decisions.md`（ADR-011 修订 1）、`docs/tasks.md`、`docs/handoffs/claude-a06.md`；**范围扩展**：`specs/teacher-review-publish.md` V3 与 PUB-35（A04 条文）、`docs/architecture.md` | I6、§8.4（贡献记录、草稿可见性、`persisting` 第 1/3/4 条）、LEASE-12 修订与 LEASE-18～23；ADR-011 修订 1（决定 9～11）；A04 V3 可见性前提与 PUB-35；`check_a06.py` 第二版 55 项 ALL PASS、四个篡改副本 exit 1；A04 核对脚本 ALL PASS；`./scripts/verify.sh` exit 0、`git diff --cached --check` exit 0；`docs/handoffs/claude-a06.md` 第九节 |

- A06-R01/R02 的修复（ArvinHan 2026-09-23 签收，ADR-011 修订 1）：草稿按任务记录贡献（`contrib_tasks`、`contrib_manual`、来源关联带 `task_id`），可见性由 SQLite 有效任务集合 V 决定，T6 提交才可见、T9 起即不可见；清理按贡献撤销，只删无贡献元素，降为存储回收。
- 交出的后续项（该记录创建时均未认领）：**F02** 草稿查询必带 V；**F03** 贡献字段约束/索引；**F08/F13** 写入登记贡献；**E10/E11** 融合候选按 V 过滤；**G04** 建快照按 V 过滤。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A07-R01 修复 | DONE（ADR-011 修订 2 已签收） | 修复 Codex 审查 A07-R01（`model_calls` 去重键未覆盖物理重试与问答调用） | Claude（协调 Agent） | `.claude/worktrees/a04-f5f479`（分支 `claude/a07-r01-fix`）/ base `8340b1e` | `docs/integrations.md`（预算）、`specs/task-processing.md`（§8.4「计费不重复」、LEASE-17、LEASE-24～27）、`docs/decisions.md`（ADR-011 修订 2）、`docs/tasks.md`、`docs/handoffs/claude-a07.md` | §8.4「计费不重复」、LEASE-17 修订与 LEASE-24～27；`docs/integrations.md`「预算」四条与新增「调用记录（`model_calls`）」；ADR-011 修订 2（决定 12）；专项核对 17 项 ALL PASS、四个篡改副本 exit 1；`check_a07.py` 329/329、`check_a06.py` 第二版与 A04 核对脚本 ALL PASS；`./scripts/verify.sh` exit 0、`git diff --cached --check` exit 0；`docs/handoffs/claude-a07.md` 第九节 |

- A07-R01 的修复（ArvinHan 2026-09-23 签收，ADR-011 修订 2）：每次实际供应商调用一条 `model_calls`，以发请求前生成的 `call_id` 为身份与去重键；预写失败不发请求；未收到响应按「输入估算 + 声明的输出上限」计入；问答以 `request_id` 归属。
- 交出的后续项（均未认领）：**E03** 每个 LLM 请求声明输出上限并估算输入；**E04** 预写、回写与预算汇总；**E05** 修复调用独立记录；**J03/J05** 问答调用带 `request_id`；**C01** 建表以 `call_id` 为主键。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A08 | DONE（ADR-014 及修订 1 已签收；PR #19 `f9dfc8f`） | 定义推荐评分与进度跨版本规则 | Codex | `.claude/worktrees/codex-a08-learning-path`（`codex/a08-learning-path`）/ base `1a47eb2` | `specs/learning-path.md`、`docs/atomic-task-plan.md` B12/I05 行、`docs/atomic-tasks.json` B12/I05 `acceptance`、本任务行及下方说明、`docs/handoffs/codex-a08.md` | `specs/learning-path.md` LP-1～19；R11～R14 第 3 轮复审通过（PR #17 `acb257c`）；修复映射与验证见 `docs/handoffs/codex-a08.md`；未改 `src/contracts/` |

- A08 行的历史基线：PR #19 合入时，§7 的参数、进度接口字段与 ADR-014 两项细则仍待签收，R15 未修订。这些均已由下方「A08 签收」行（ADR-014 修订 1）签收，现行规则以该行与 `specs/learning-path.md` 为准，本段不再列待决项。当前依赖：**ADR-012** 的下一次修订（快照节点 `merged_from` 与版本提交序号，A04 负责）、**B12** 在 YAML 真源落地 `ProgressEntry` 字段、**C01/I01** 为进度行增加写入序号。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A08 签收 | DONE（ADR-014 修订 1 及 A08S-R01 补注已签收） | 签收 A08 §7 的参数与进度接口字段，以及 ADR-014 的两项细则 | Claude（协调 Agent） | `.claude/worktrees/codex-a08-check-0ae6d7`（分支 `claude/a08-signoff`）/ base `f9dfc8f` | `docs/decisions.md`（ADR-014 修订 1）、`specs/learning-path.md`（§1、§3、§5、§6、§7）、`docs/integrations.md`（学习推荐权重、启动校验）、`.env.example`、本任务行、`docs/handoffs/claude-sign-a08.md` | `docs/decisions.md` ADR-014 修订 1（决定 5～10）；`specs/learning-path.md` LP-1～20；`docs/handoffs/claude-sign-a08.md`；`./scripts/verify.sh` exit 0、`git diff --check` exit 0 |

- A08 签收的决定（ArvinHan 2026-09-23，ADR-014 修订 1）：
  - 缺失属性取 0.5；
  - 权重来自四个 `RECOMMEND_WEIGHT_*` 环境变量，缺省为 S2 值，只设一部分则拒绝启动，不做课程级配置；
  - 推荐上限默认 10、最大 50；
  - 进度接口返回 V 中全部节点，带有效 `status`、`own_status`、`inherited_from[]`、可空 `updated_at`；
  - 细则 1：主节点的显式写入以来源“本次连续归属”的起算版本为界，覆盖来源；
  - 细则 2：谱系作为发布快照节点的 `merged_from` 字段保存。
- 交出的后续项（均未认领）：
  - **A04（ADR-012 下一次修订）**：快照节点增加 `merged_from` 并纳入摘要，版本提交事务取共享序列的提交序号。**已由 ADR-012 修订 3 完成（2026-09-24 签收，PR #179）。**须先于 F10/B11/G04/G06/I01 完成；#16 正在做 ADR-012 修订 2，本项编号排在其后。
  - **B12**：`ProgressEntry` 新字段、GET/PUT 返回全部节点。
  - **C01/I01**：进度行增加写入序号。
  - **I04**：启动时读取并校验权重。
  - **F10**：合并时写入谱系。
- Codex REVIEW-14 修复（A1～A10 收尾，Claude）：**A08S-R01** 同值写入不能只凭原始值相同跳过，按提交时最终绑定版本上是否仍有未被覆盖的来源判定，LP-16/LP-18 补回归，ADR-014 修订 1 决定 9 加补注（ArvinHan 2026-09-24 签收）；**A08S-R02** A08 行说明段改为历史基线并列出当前依赖。审查报告 `docs/reviews/codex-claude-a08-signoff-f9dfc8f-2026-09-24-0123z.md`（主目录）；验证见 `docs/handoffs/claude-sign-a08.md`「第二轮」。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| FIX-R01/R02 修复 | DONE（ADR-011 修订 3、ADR-012 修订 2 已签收） | 修复 Codex REVIEW-09 的 FIX-R01（响应无 usage 时按 0 计费）与 FIX-R02（向量迁移目标集合与单一空间不变式不一致） | Claude（协调 Agent） | `.claude/worktrees/quirky-dijkstra-eca5de`（分支 `claude/fix-r01-r02`）/ base `1a47eb2` | `docs/integrations.md`（预算、调用记录、模型版本与向量空间、D-02a/b）、`specs/task-processing.md`（§8.4「计费不重复」、LEASE）、`specs/teacher-review-publish.md`（V10、V11、V12）、`docs/decisions.md`（ADR-011 修订 3、ADR-012 修订 2）、`docs/architecture.md`（向量空间一行）、本节、`docs/handoffs/claude-a07.md`、`docs/handoffs/claude-a04.md` | 审查报告 `docs/reviews/codex-claude-a04-fixes-1012b6f-2026-09-23-1215z.md`（主目录）；`docs/integrations.md`「预算」「调用记录」第 5 条；LEASE-28～30；V12 第 3/4/6 步与「空间标识随向量走」、PUB-36～38；ADR-011 修订 3、ADR-012 修订 2；`check_fix.py` 修改前 38 FAIL，修改后 40 项 ALL PASS，6 个负例均 exit 1；`check_a07` 347/347、`check_a07r01`、`check_a06` ALL PASS，`check_a04` 除修改前就存在的 2 项过时断言外，仅新增 1 项脚本边界问题（修订 1 之后多了修订 2，见交接）；`./scripts/verify.sh` exit 0、`git diff --check` exit 0；`docs/handoffs/claude-a07.md` 第十节、`docs/handoffs/claude-a04.md` 第十一节 |

- FIX-R01/R02 的修复（ArvinHan 2026-09-23 签收，ADR-011 修订 3、ADR-012 修订 2）：响应不带 usage 时，生成前被拒的错误（`400/401/403/404/413/422/429`）计 0，其余情形按「输入估算 + 输出上限」计，E03 流式请求须请求 usage；重新向量化按 Neo4j 实际存量迁移并按存量核对，缓存与节点外的向量带空间标识，写入按空间标识而非维度拒绝。
- 交出的后续项（均未认领）：**E03** 错误分类含「生成前被拒」、流式请求 usage；**E04** 按修订 3 汇总计费量；**D-02a/b** 签收时注明供应商是否返回 usage；**E07** 缓存键含空间标识；**F03** 写入向量核对空间标识；**A10** 仍须为重新向量化命令补登叶子任务。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| FIX-R03 修复 | DONE（ADR-012 修订 2 补注已签收） | 修复 Codex REVIEW-10 的 FIX-R03（离线迁移写新空间与「只能写当前空间」冲突），并把 `origin/main` 合入本分支解除 PR #16 冲突 | Claude（协调 Agent，A1～A10 收尾） | `.claude/worktrees/wrap-fix-pr16`（分支 `claude/fix-r01-r02`）/ base `5186e09` + 合入 `f9dfc8f` | `specs/teacher-review-publish.md`（V12 第 3 步、「空间标识随向量走」、PUB-39）、`docs/integrations.md`（写入核对一处）、`docs/architecture.md`（向量空间一行）、`docs/decisions.md`（ADR-012 修订 2 补注）、本节、`docs/handoffs/claude-a04.md` 第十二节 | 审查报告 `docs/reviews/codex-claude-fix-r01-r02-5186e09-2026-09-23-1252z.md`（主目录）；`check_fixr03.py` 修改前 13 FAIL、修改后 ALL PASS，负例见交接；`./scripts/verify.sh`、`git diff --check` 结果见 `docs/handoffs/claude-a04.md` 第十二节 |

- FIX-R03 的修复：空间标识按写入上下文核对。运行时写入只接受当前空间，没有绕过参数；只有重新向量化命令在自己的进程内持有迁移上下文，第 3 步只写本次目标空间、不动旧空间，第 5 步提交后失效。不改变 ADR-012 修订 2 已签收的方向。补注由 ArvinHan 2026-09-24 签收。
- 交出的后续项（均未认领）：**F03** 写入接口区分运行时与迁移两种上下文并实现 PUB-39；**重新向量化命令**（A10 批 0 补登的叶子任务）建立并持有迁移上下文。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A09 | DONE（ADR-015 已签收） | 定义问答终态和引用撤回协议 | Claude（协调 Agent） | `.claude/worktrees/a09-dev-environment-check-8e5e93`（分支 `claude/a09-dev-environment-check-8e5e93`）/ base `f9dfc8f` | `specs/grounded-qa.md`（main 新建，以 `740adb` `978671e` 草稿桩为底稿）；**范围扩展（用户同意）**：`docs/decisions.md`（新增 ADR-015）、`docs/architecture.md`（问答 SSE 行、`NotCoveredReason` 行加注、用语映射一行）、本节、`docs/handoffs/claude-a09.md` | `specs/grounded-qa.md`「问答终态与引用撤回协议」Q1～Q12（终态矩阵 O1～O15、QA-1～35：成功 5 / 边界 18 / 失败 12）；`docs/decisions.md` ADR-015（ArvinHan 2026-09-23 签收）；`docs/architecture.md` 三处加注与 `ChatLog` 定名；核对脚本 45 项 ALL PASS（对 `740adb` `978671e` 真源、IAM 矩阵、A07 切换矩阵、ADR-012 V8 与原子清单），19 个篡改副本均被对应检查项检出（exit 1、无崩溃）；流内状态机参考模型 19/19 PASS（每例 200 种随机分块结果一致，仅作验证、不入库）；`./scripts/verify.sh` exit 0、`git diff --check` exit 0；`docs/handoffs/claude-a09.md` |

- A09 的决定（ArvinHan 2026-09-23 在会话中逐项选定、四节设计逐节确认，ADR-015 同日签收）：检索与阈值判定之后才开流，开流前失败为 HTTP 错误，开流后为 `meta delta* (done | error)`；服务端流内逐引用校验，`answered` 时最终正文恒等于 delta 拼接；模型以 `<<INSUFFICIENT_EVIDENCE>>` 开头声明证据不足，`out_of_course_scope` 改名 `insufficient_evidence`；除 `done` + `answered` 外一律撤回临时正文、不自动重试；输出截断按正常结束判定；历史只用于改写、生成不见历史；回答钉在绑定版本、不追溯撤回；问答记录定名 `ChatLog` / `chat_logs`（关闭 A10 N5）。
- 交出的后续项（均未认领）：**B13** 改 `NotCoveredReason`，`meta` 与 `final` 加 `graph_version`、`request_id`，定 `details.reason` 闭集，`events.v1.md` §3 指向本规格；**B08** 落实 `STORAGE_UNAVAILABLE`、`INTERNAL_ERROR`、`BUDGET_EXCEEDED`，改 `RATE_LIMITED` 措辞；**J03～J10、K03** 按规格 Q11 实现（J06 与 J09 共用代码片段夹具）；**A10** 用本规格替换分支桩，并把它加回批 1 门禁扫描清单。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A09-R01/R02 修复 | DONE（ADR-015 修订 1 已签收） | 修复 Codex REVIEW-12 的 A09-R01（一个有效引用即可让无出处的结论成为 `answered`）与 A09-R02（每请求一条日志与鉴权前置顺序冲突） | Claude（协调 Agent，A1～A10 收尾） | `.claude/worktrees/a09-dev-environment-check-8e5e93`（分支 `claude/a09-dev-environment-check-8e5e93`）/ base `1754c96` | `specs/grounded-qa.md`、`docs/decisions.md`（ADR-015 修订 1）、`docs/architecture.md`（`ChatLog` 一处）、本节、`docs/handoffs/claude-a09.md` 第九节 | 审查报告 `docs/reviews/codex-claude-a09-1754c96-2026-09-23-1400z.md`（主目录）；Q3.5、I3、QA-36～38；核对脚本修改前 27 FAIL、修改后 ALL PASS，负例见交接；`./scripts/verify.sh`、`git diff --check` 结果见 `docs/handoffs/claude-a09.md` 第九节 |

- A09-R01/R02 的修复（ArvinHan 2026-09-24 选定方向并签收条文，ADR-015 修订 1）：每个结论单元（句）都须带有效引用，否则整段撤回为 `not_covered` / `all_citations_invalidated`（日志子类 `uncited_sentence`），wire 枚举不变；语义支持度只在 K03 评测中衡量。`chat_logs` 只记通过 P2 的请求，四个必填字段非空；P1/P2 拒绝只写应用日志。
- 交出的后续项（均未认领）：**J05** 提示要求逐句标注；**J06** 实现 Q3.5；**J10** 按新覆盖范围建表；**K03** 统计 `uncited_sentence` 撤回率；**C03/J07** 的统一错误处理写应用日志。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A10-R01/R02 修复 | DONE（ADR-016 修订 1 已签收） | 修复 Codex REVIEW-13 的 A10-R01（批 1 把已合入的学习路径规格移出命名门禁）与 A10-R02（批 5 拟原样导入与现行状态机相反的 ADR-005/006） | Claude（协调 Agent，A1～A10 收尾） | `.claude/worktrees/wrap-a10-fix`（分支 `claude/a10-r01-r02-fix`）/ base `37da669`（PR #18） | `docs/reviews/branch-integration-map.md`（第 3 节批 1/5、第 4 节 ADR-005/006、第 7 节风险 2/6）、`docs/decisions.md`（ADR-016 修订 1）、本节、`docs/handoffs/claude-a10.md` 第十节 | 审查报告 `docs/reviews/codex-claude-a10-37da669-2026-09-23-1403z.md`（主目录）；核对脚本修改前 10 FAIL、修改后 ALL PASS，负例与 `check_a10.py` 回归见交接；`./scripts/verify.sh`、`git diff --check` 结果见 `docs/handoffs/claude-a10.md` 第十节 |

- A10-R01/R02 的修复（ADR-016 修订 1，ArvinHan 2026-09-24 签收）：批 1 的扫描集合按执行时 main 中已存在的规格确定，`learning-path.md` 保留，`grounded-qa.md` 待 A09 合入后加回并补负例；ADR-005/006 在批 5 以 SUPERSEDED 历史记录导入，不得作现行依据。
- 交出的后续项（均未认领）：**批 1 补**（后端 Agent）：A09 合入后把 `specs/grounded-qa.md` 加回 `scripts/check_contracts.py` 扫描清单与 `tests/contracts/test_contracts.py` 夹具，并加该文件的错误命名负例；**批 5**（协调 Agent）按修订 1 导入 ADR-005/006。

## A10 批 0：规划文档对齐

| 原子 ID | 状态 | 任务 | 负责人 | 目标分支 / base | 文件锁 | 验收证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A10-批0 | DONE（本地，待审查） | 按 ADR-016 更新契约任务白名单并补齐 G-1～G-6 清单缺口 | Codex（协调） | `codex/a10-batch0` / A10 `37da669`，已合入 `origin/main@f9dfc8f` | `docs/atomic-task-plan.md`、`docs/atomic-tasks.json`、`docs/reviews/validate_atomic_plan.py`、本任务板、`docs/handoffs/codex-a10-batch0.md` | 140 项清单校验 PASS；无环、路径与链接检查 PASS；基础 verify PASS；负例（缺依赖）被拒；`docs/handoffs/codex-a10-batch0.md` |

- 输入：A10/ADR-016 的导入映射第 3 节批 0 与第 6 节 G-1～G-6；ADR-004 YAML 真源裁定；A05/ADR-013 身份与票据规则。
- 输出：B08～B14、O02、O05 的 YAML 真源与生成物白名单；新增 C13～C16、F14、H12、K13～K19 共 13 个叶子任务；验证器动态计数并可在当前 checkout 运行。
- 依赖：A10 决定已签收；批 1 必须在批 0 验收后开始。
- 风险：A10 本身尚未进入远端 `main`；本轮只在独立分支工作，不改动 B02/B06 工作区。新增任务均为计划，未声称实现。
- 验证：`python docs/reviews/validate_atomic_plan.py`、负例、`./scripts/verify.sh`、`git diff --check`。

## A10 批 1：契约真源与生成链

| 原子 ID | 状态 | 任务 | 负责人 | 目标分支 / base | 文件锁 | 验收证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A10-批1 / M0-09 第二步 | DONE（本地，待 PR 与 CI） | 按 ADR-016 导入 OpenAPI 真源、生成类型、契约门禁及 CI 工具链 | Codex（后端） | `codex/a10-batch1` / `codex/a10-batch0@c795741` | `src/contracts/**`、`scripts/{gen-contracts.sh,gen_contracts.py,check_contracts.py,verify.sh,verify/contracts.sh}`、`tests/contracts/**`、`.github/workflows/ci.yml`、`.gitattributes`、命名相关架构/规格/计划段、本任务板与交接 | `docs/handoffs/codex-a10-batch1.md`；`gen-contracts.sh --check`、22 项契约负例、`verify.sh`、计划校验、生成模型导入与 `pip check` 均通过；远端 CI 待 PR |

- 输入：A10 [导入映射](reviews/branch-integration-map.md) 第 3 节批 1、ADR-004/009/010/016、来源分支 `claude/worktree-contract-conflicts-740adb@978671e`。
- 输出：`api.v1.yaml`、配套语义文档、完整 Python/TypeScript/JSON 生成物、严格契约校验及 CI 安装步骤；N1 的 `Chunk` 命名同步到架构、A04 规格、D10 计划。
- 依赖与风险：批 0 已在本地提交；A10 与前置 PR 仍未全部进入 `main`，本批不能直接合入主线。`events.v1.md` §2 的旧状态机叙述留给 B10 迁移，已在文首标明现行规范的优先级。远端 CI 尚未运行。
- 验证命令：`./scripts/gen-contracts.sh --check`、`./scripts/verify.sh`、`python docs/reviews/validate_atomic_plan.py`、生成模型导入、`python -m pip check`、`git diff --check`；具体结果与回滚见交接。

## A1～A10 收尾（2026-09-24）

> 盘点基线 `origin/main@f9dfc8f`；合并后基线 `origin/main@2819701`。本节只登记状态与去向，不代替各 PR 自己的任务行。

| 原子 ID | 决定 | 合入 main | Codex 审查意见 | 余项 |
| --- | --- | --- | --- | --- |
| A01 | ADR-004 已签收 | PR #1 | 无未决 | — |
| A02 | ADR-009 已签收 | PR #2 | **A02-R01**（P2）：YAML 真源 `Relation.required` 未含 `status`、`source`、`source_refs`，与规格「关系至少含」不一致 | 交 **B11**（见下） |
| A03 | ADR-010 已签收 | PR #5（含 A03-R01/R02 修复） | 无未决 | — |
| A04 | ADR-012 及修订 1、修订 2（含补注）已签收 | PR #7、#10、#16 | FIX-R02、FIX-R03 已修 | 待 Codex 复核 FIX-R03（`970c582`） |
| A05 | ADR-013 已签收 | PR #9 | 无未决 | — |
| A06 | ADR-011 及修订 1 已签收 | PR #6、#11 | 无未决 | — |
| A07 | 形状已定；ADR-011 修订 2、3 已签收 | PR #8、#12、#16 | A07-R01、FIX-R01 已修 | 取值待 D-02a～f |
| A08 | ADR-014 及修订 1（含决定 9 补注）已签收 | PR #19、#23 | A08S-R01/R02 已修 | 待 Codex 复核（`39633fe`） |
| A09 | ADR-015 及修订 1 已签收 | PR #20 | A09-R01/R02 已修 | 待 Codex 复核（`097f248`） |
| A10 | ADR-016 及修订 1 已签收 | PR #18、#24；批 0/1 为 PR #22 | A10-R01/R02 已修 | 待 Codex 复核（`fae2212`）；批 2～6 未执行 |

- **合并记录**：2026-09-24 由 Claude 按 ArvinHan 在会话中的明确指示依次合并 #16 → #23 → #20 → #18 → #24 → #22（ADR-016 规定由 ArvinHan 合并，本次为其授权的代执行）。每个 PR 合并前先同步 main、解决文末追加冲突，本地 `./scripts/verify.sh` 与 `git diff --check` 通过，且 CI 在新的头提交上成功后才合并；#22 合并前本地运行了含契约门禁（22 项负向测试）的完整 `verify.sh`，exit 0。
- **四处补注**已由 ArvinHan 于 2026-09-24 签收：ADR-012 修订 2 补注、ADR-014 修订 1 决定 9 补注、ADR-015 修订 1、ADR-016 修订 1。
- **A 组关闭条件**：仅剩 Codex 复核上表四个修复提交，无新的 P1/P2 即关闭。A 组没有未认领的原子任务。
- **仍开放、但不阻塞 A 组关闭的决定**：D-01（示例课程资料）、D-02a～f（模型供应商与预算取值）、PLAN-D05（学习材料分支）、D-08（A10 登记）。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A1～A10 收尾 | DONE（修复已合入、四处补注已签收；待 Codex 复核） | 盘点 A01～A10，修复 Codex 未决意见 FIX-R03、A08S-R01/R02、A09-R01/R02、A10-R01/R02，按授权依次合并 PR，登记 A02-R01 去向 | Claude（协调 Agent） | `.claude/worktrees/a1-a10-meta-task-wrap-ddbf4b`（分支 `claude/a1-a10-meta-task-wrap-ddbf4b`）/ base `f9dfc8f`，合并后同步 `2819701` | 本节、`docs/handoffs/claude-a1-a10-wrap.md`；各修复的文件锁见对应任务行 | `docs/handoffs/claude-a1-a10-wrap.md`；各修复的核对脚本先红后绿、篡改负例全部检出；合并后 main 上 `./scripts/verify.sh` exit 0 |

- **A02-R01 → B11**（已由 B11 完成，PR #194 `2de97ba`）：在 `src/contracts/api.v1.yaml` 把 `status`、`source`、`source_refs` 加入 `Relation.required`（若允许空来源，须写明适用场景并与 `specs/course-knowledge-graph.md` 对齐），重新生成并加「缺任一字段即拒绝」的 schema 负例；`RelationCreate` 仍可由服务端补齐这三个字段。契约真源已随 PR #22 进入 main，可以开始。审查报告：主目录 `docs/reviews/codex-claude-a02-hook01-2026-09-23-0528z.md`。
- **批 1 补**（未认领，后端 Agent）：A09 已合入，现可把 `specs/grounded-qa.md` 加回 `scripts/check_contracts.py` 扫描清单与 `tests/contracts/test_contracts.py` 夹具，并加该文件的错误命名负例（ADR-016 修订 1）。
- Codex 在主目录未入库的审查记录（REVIEW-03～26 的任务行、`docs/reviews/codex-claude-*.md` 报告 24 份、`docs/handoffs/codex-review-*.md` 交接 24 份与 `claude-review-state.json`）已于 2026-09-25 经 ArvinHan 同意由 Claude 原样代为入库（见 `docs/handoffs/claude-archive-codex-reviews.md`）；各交接中「主目录 `docs/reviews/…`」的引用现在按仓库内同名路径解析。

## A10 批 1 补：问答规格加回契约门禁

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A10-批1补 | DONE | 把 `specs/grounded-qa.md` 加回契约命名门禁的扫描清单与测试夹具，并为每份被扫描的规格加错误命名负例（ADR-016 修订 1） | Claude（后端 Agent） | `.claude/worktrees/batch1-qa`（分支 `claude/batch1-grounded-qa`）/ base `548c4f8` | `scripts/check_contracts.py`（`NAMING_DRIFT_DOCS`）、`tests/contracts/test_contracts.py`、本节、`docs/handoffs/claude-a10-batch1-supplement.md` | 新增 `test_alias_in_each_guarded_spec_fails`、`test_guarded_spec_missing_fails`：去掉扫描项时两项均只因 `grounded-qa.md` 失败，加回后通过；契约负向测试 24/24；`./scripts/verify.sh` exit 0（命名基线 10 份文档）；`git diff --check` exit 0；`docs/handoffs/claude-a10-batch1-supplement.md` |

- 输入：ADR-016 修订 1 决定 1；A09 已随 PR #20 合入 main。输出：`specs/grounded-qa.md` 进入命名门禁扫描清单与测试工作区；四份受保护规格（课程图谱、学习路径、教师发布、问答）各有一处 `SourceChunk` 注入负例和一处缺文件负例。测试中的受保护清单独立列出，不从门禁导入，避免同源漏扫。
- 本项关闭 A1～A10 收尾一节登记的「批 1 补」。

## B01 前端构建与单页挂载

| 原子 ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| B01 | DONE | 初始化 Vue 3 + TypeScript + Vite 构建及单个挂载页面 | Codex（前端） | `codex/b01-vue-scaffold` / base `50a15c9` | `src/frontend/package.json`、`src/frontend/package-lock.json`、`src/frontend/tsconfig.json`、`src/frontend/vite.config.ts`、`src/frontend/index.html`、`src/frontend/src/main.ts`、`src/frontend/src/App.vue`；文档范围：`src/frontend/README.md`、`docs/architecture.md`、本任务板、`docs/handoffs/codex-b01.md` | `npm ci`、`vue-tsc`、Vite build、浏览器挂载烟测、`./scripts/verify.sh` 均通过；见 `docs/handoffs/codex-b01.md` |

- 输入：A01 已确认的前端技术栈与 `docs/atomic-task-plan.md` B01 验收条件；不新增 REST、SSE 或业务 DTO。
- 输出：锁定依赖的最小 Vue 应用、严格类型检查、可构建产物与单页挂载烟测。
- 依赖：A01 已完成；B02 的测试配置与 B03 的角色路由在本轮范围外。
- 风险：构建工具对 Node 版本有下限；本轮以实际本机版本核验。锁文件和构建产物必须分开，`dist/` 不入库。
- 验证：`npm --prefix src/frontend run type-check`、`npm --prefix src/frontend run build`、浏览器挂载烟测、`./scripts/verify.sh`、`git diff --check`。
- 实际结果：Node 24.16.0 / npm 11.13.0；锁文件重装成功；类型检查与生产构建 exit 0；本地 Vite 页面在浏览器显示标题和挂载内容；基础 verify 与 diff check exit 0。正式测试脚本归 B02。
- Claude 审查（REVIEW-B01，2026-09-23）：无 P1/P2；P3×3（B01-R01～R03）不阻塞。合入 `origin/main@548c4f8` 后在合并结果上重跑 `npm ci`、type-check、build、浏览器挂载烟测与 `./scripts/verify.sh` 均通过；见 `docs/handoffs/claude-review-b01.md`。

## B05 后端应用工厂与健康检查

| 原子 ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| B05 | DONE | 初始化 FastAPI 应用工厂与匿名 `GET /health` | Codex（后端） | `codex/b05-fastapi-health` / base `50a15c9` | `src/backend/pyproject.toml`、`src/backend/app/main.py`、`src/backend/app/api/health.py`、`tests/backend/test_b05.py`；**范围扩展**：`src/backend/app/api/__init__.py`（包标记）、`src/backend/README.md`（启动与测试说明）、任务板、架构说明和 `docs/handoffs/codex-b05.md` | pytest 3 PASS；基础 verify PASS；Uvicorn 实际启动并返回 HTTP 200；`docs/handoffs/codex-b05.md` |

- 输入：已签收的 ADR-004、ADR-009，以及 `740adb` 分支现有 `/health` 契约（`status = ok`、`version` 为字符串）；B05 不引入第二套契约真源。
- 输出：可由 Uvicorn 启动的应用工厂、无鉴权健康检查、后端依赖及 pytest 配置、成功/边界/失败测试。
- 依赖：A01 已完成；A10 导入完整 `api.v1.yaml` 与 B06 配置校验仍是后续任务，不阻塞无密钥健康检查。
- 风险：当前主分支尚无契约真源或数据库实现；本任务的健康检查只表示 API 进程可响应，不探测 Neo4j、SQLite 或模型服务。
- 验证：`python -m pytest tests/backend/test_b05.py -q`（本机 Windows 的 `python3` 等价命令）3 PASS；`./scripts/verify.sh` PASS；`git diff --check` PASS；Uvicorn HTTP 冒烟 200，响应含 `status` 与 `version`。详细命令、版本和限制见交接。
- B05 只完成后端最小启动与健康检查；父任务 M0-03 的 B06 设置加载仍待完成。A10 导入契约真源后，生成 DTO 应替换 B05 的临时响应模型。
- Claude 审查（REVIEW-B05，2026-09-24）：无 P1/P2；P3×3（B05-R01～R03）。合入 `origin/main@dddafb3` 后 test_b05 3 passed、uvicorn 实测与契约一致、`verify.sh` 通过；见 `docs/handoffs/claude-review-b05.md`。

## B07 契约门禁缺依赖假绿

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| B07 | DONE（PR #187 已合入 `1d3e20c`） | 校验结果显式 PASS/SKIP/FAIL，缺依赖与坏契约失败 | Codex（后端） | `b07-main` / 初始 `origin/main@28b09b4` | `scripts/check_contracts.py`、`scripts/verify/contracts.sh`、`src/backend/pyproject.toml`、`tests/tooling/test_b07.py`；文档 `docs/architecture.md`、本节、`docs/handoffs/codex-b07.md` | 最新主线临时合并副本：B07 14 PASS、全量 620 PASS、`./scripts/verify.sh` exit 0、diff check PASS；PR 六项 CI 全绿；[审查复核](reviews/codex-b07-pr187-2026-09-25.md)；[PR #187](https://github.com/arvinhanye/SmartSketch/pull/187)；`docs/handoffs/codex-b07.md` |

- 输入：R02 审查结论与已导入 main 的契约门禁；输出：一套门禁的显式状态及后端测试依赖声明，不引入第二套校验入口。
- 依赖：A01、B05、C13 已合入；实际合并保留 C13 的 `argon2-cffi==25.1.0` 和 B07 的三项测试依赖。
- 验收：缺依赖、坏 `$ref`、坏关系枚举均非 0；显式骨架降级标为 `SKIP` / `INCOMPLETE`；运行 `python3 -m pytest tests/tooling/test_b07.py -q`、`./scripts/verify.sh`、`git diff --check`。
- 结果：定向 14 项覆盖正常通过、PyYAML/OpenAPI 校验器/JSON Schema 缺依赖、显式骨架跳过、坏引用、坏枚举、畸形结构的显式 FAIL、聚合门禁状态与测试依赖；最新主线临时合并副本全仓 620 项通过，`./scripts/verify.sh` 通过。PR #187 于 2026-09-25 UTC 合入 `main@1d3e20c`。

## B06 后端设置加载与启动验证

| 原子 ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| B06 | DONE（审查修复） | 从环境变量加载类型化设置并在启动时校验 | Codex（后端） | `codex/b06-settings` / base `e8ce796` | `src/backend/app/config.py`、`tests/backend/test_b06.py`；范围扩展：`src/backend/app/main.py`（接入启动校验）、`src/backend/README.md`、`docs/architecture.md`、`docs/integrations.md`、`.env.example`（登记发布锁参数）、本任务板、`docs/handoffs/codex-b06.md`；审查修复增加 `src/backend/app/repositories/embedding_space.py`、`src/backend/app/services/startup.py`、`src/backend/app/__main__.py`、`tests/backend/test_b05.py` 与发布规格同步 | B05+B06 47 PASS；基础 verify PASS；`git diff --check` PASS；见 `docs/handoffs/codex-b06.md` |

- 输入：A07 环境变量表及启动校验规则、A03/A06 任务配置、ADR-012 发布锁参数、B05 应用工厂。
- 输出：只读环境变量的类型化设置、非法值拒绝启动、密钥脱敏、fake 模式无真实模型凭据可启动。
- 依赖：B05、A07 已完成；真实模型供应商取值 D-02a～f 待签收，不影响 fake 验证。
- 风险：既有 `.env.example` 未登记 `PUBLISH_LEASE_SECONDS`、`COURSE_LOCK_WAIT_SECONDS`；本轮同步补齐，不改变已签收的默认值。
- 验证：`python -m pytest tests/backend/test_b06.py -q`、B05 回归、`./scripts/verify.sh`、`git diff --check`。
- 实际结果：B06 35 PASS、B05 回归 3 PASS；默认 fake、合法 live、非法范围与条件、密钥脱敏、应用导入时拒绝非法配置均有实际测试；基础 verify 与 diff check exit 0。D-02 真实模型取值仍待签收。

### B06 审查修复

- 输入：B06 固定提交 `ca353b1`、审查指出的 PUB-32 启动门禁、URL 漏检和监听参数未接线；`specs/teacher-review-publish.md` V12、ADR-012 修订 1。
- 输出：SQLite 单行向量空间启动门禁、严格 URL 校验、读取 `API_HOST`/`API_PORT` 的启动入口及回归测试。
- 依赖：Python 标准库 SQLite；C01 后续迁移须接管并保留引导表，worker 入口须调用同一门禁。
- 风险：新增 SQLite 引导表；首次启动会写入配置空间，已有空间不一致必须保持旧值并拒绝启动。回滚需停机并从变更前 SQLite 备份恢复，不能删除空间记录绕过检查。
- 验证：先运行新增负例复现；再运行 B05/B06 pytest、`./scripts/verify.sh`、`git diff --check`。
- 结果：新增负例先为 5 FAIL；修复后 B05+B06 共 47 PASS、基础 verify PASS、`git diff --check` PASS。API lifespan 已接入门禁；C09 尚无 worker 入口，须复用 `validate_embedding_space()`；离线重新向量化命令仍归后续任务。
- Claude 审查（REVIEW-B06，2026-09-24）：P2×2 已签收（ArvinHan 2026-09-24，见 `docs/decisions.md`「ADR-012 补注：启动门禁的当前空间记录表与职责拆分」）——**B06-R01** 启动时建 SQLite 表 `embedding_space_state`（超出原子范围的数据模型决定，表名与「C01 接管」约定待签收）；**B06-R02** 修改已签收的 ADR-012 规格两处职责标注。P3×2。同步 main 后补 `RECOMMEND_WEIGHT_*` 四项成组校验（集成修复 `dbfb63d`）；后端 58 passed、启动门禁/密钥脱敏实测通过；见 `docs/handoffs/claude-review-b06.md`。

## B02 前端测试配置

| 原子 ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| B02 | DONE（REVIEW-18 已审，无问题） | 初始化前端测试配置，使仓库外层 `tests/frontend` 被实际发现 | Claude（前端） | `claude/frontend-dev-04eee7` / base `dddafb3` | `src/frontend/vitest.config.ts`、`src/frontend/package.json`、`src/frontend/package-lock.json`、`tests/frontend/setup.ts`、`tests/frontend/b02.test.ts`；因 B01-R01 需要时扩到 `src/frontend/tsconfig*.json`；文档：`src/frontend/README.md`、`docs/architecture.md`、本任务板、`docs/handoffs/claude-b02.md` | 计划验收命令 exit 0（5 passed）；三处反向篡改（去 setup、`passWithNoTests`、脚本吞退出码）均被检出；类型检查覆盖测试与 Node 侧配置，应用代码不可见 Node 类型；`npm ci`、build、`./scripts/verify.sh`、`git diff --check` 通过；见 `docs/handoffs/claude-b02.md` |

- 输入：B01 已合入的 Vue 3 + Vite 骨架（PR #15）；`docs/atomic-task-plan.md` B02 验收；审查意见 B01-R01（Node 侧配置不得混入浏览器类型）。
- 输出：Vitest 配置与 `test` 脚本；DOM 测试环境与全局 setup；`tests/frontend/b02.test.ts` 同时验证 SFC 挂载、setup 生效，以及「故意失败用例使命令非 0」「零用例不算通过」两条门禁行为。
- 依赖：B01；npm 公共源。无后端、契约或环境变量变化。
- 风险：`tests/frontend` 位于 Vite 根目录外，裸模块解析与类型检查可能找不到 `src/frontend/node_modules`；测试依赖可能抬高 Node 版本下限。
- 验证：`npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/b02.test.ts`、`./scripts/verify.sh`、`git diff --check`。
- 实际结果：新增 `src/frontend/tsconfig.node.json`（文件锁中预留的扩展，处理 B01-R01）；`engines` 收紧为 `^22.22.2 || ^24.15.0 || >=26.0.0`（Vitest 5 / jsdom 30 下限）；B01-R02 的 README 命令块已改为 `bash`。CI 仍未跑前端命令，归 K11。

## B03 / B04 前端路由壳与课程上下文（并行）

| 原子 ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| B03/B04 准备 | DONE | 安装 `vue-router@5.3.1`、`pinia@4.0.3`，`main.ts` 接入 Pinia；认领两项任务 | Claude（协调） | `claude/b03-b04-prep` / base `8e5b707`（B02，PR #27 未合） | `src/frontend/package.json`、`package-lock.json`、`src/frontend/src/main.ts`、本任务板 | type-check、B02 测试、build 通过 |
| B03 | DONE（REVIEW-19 已审；B03-R01′ P2 未修，见下方「审查遗留」） | 建立路由壳和角色入口 | Claude（前端子代理） | `claude/b03-router-shell` / base 准备提交 | `src/frontend/src/router/index.ts`、`src/frontend/src/views/TeacherHome.vue`、`src/frontend/src/views/StudentHome.vue`、`tests/frontend/b03.test.ts`；为接线需改 `src/frontend/src/main.ts`（仅加路由）与 `src/frontend/src/App.vue`；`docs/handoffs/claude-b03.md` | 计划验收命令 exit 0（13 passed）；去守卫/去错角色分支/去提示元素三处篡改均被检出；集成后全量 30 passed、build、`verify.sh` 通过；浏览器访问 `/teacher` 落到 `/?notice=unauthenticated` 并显示提示；`docs/handoffs/claude-b03.md` |
| B04 | DONE（REVIEW-19 已审；B04-R01 P2 未修，见下方「审查遗留」） | 建立 Pinia 课程上下文 | Claude（前端子代理） | `claude/b04-course-store` / base 准备提交 | `src/frontend/src/stores/course.ts`、`tests/frontend/b04.test.ts`、`docs/handoffs/claude-b04.md` | 计划验收命令 exit 0（12 passed）；六处篡改（按 courseId 代替代次、不清空、不中止、去幂等、去 course_id 校验、信任 `isCurrent`）均被检出；store 无 fetch/XHR/HTTP 导入；`docs/handoffs/claude-b04.md` |

- 并行约束：B03、B04 的文件锁互不相交；两者都不改 `package.json`、锁文件、`docs/tasks.md`、`docs/architecture.md`，这些由协调方在集成时统一更新。
- 依赖：B02（PR #27 待审查）；B03 另依赖 A05（`specs/identity-access.md` §2.4：路由守卫只用 `user.role` 选首页、`Course.my_role` 选课程视图，仅作界面引导）。
- 风险：原子清单没有前端登录页与会话存储任务（G-1 只列 C13～C16 后端与 H12 成员页），B03 只能以注入方式取得账号类型；缺口在集成时登记。
- 集成：`claude/b03-b04` = 准备提交 + 两个任务分支的 `--no-ff` 合并 + 本次文档更新；两分支文件锁不相交，合并无冲突。
- 协调方审查意见（P3，不阻塞）：**B03-R01** `App.vue` 用 `inject(routeLocationKey, null)` 兼容未装路由的挂载，只为让 B02 两个直接挂载 `App` 的用例不改；产品入口总会装路由。若日后改回 `useRoute()`，同批把 B02 两个挂载用例改为装内存路由。**B04-R01** 图谱/问答槽位对组件仍可直接赋值，绕过作用域校验只靠注释与审查约束；H03/J08 接入时可改为只读暴露。
- 交出的后续项（均未认领）：B15 须把 `scope.signal` 传给 fetch，旧请求才会在网络层真正取消；路由 `cid` 与 `selectCourse` 的接线归 H01；登录页、会话存储与 `getAccountRole` 的真实来源归 H13（D-09）；问答「最新回答与引用」槽位由 J08/J09 决定是否加入并在切课时清空。

## B08 公共错误与来源契约

| 原子 ID | 状态 | 任务 | 负责人 | 目标分支 / base | 文件锁 | 验收证据 |
| --- | --- | --- | --- | --- | --- | --- |
| B08 | DONE（本地，审查问题已修复） | 迁移公共错误和来源契约 | Codex（后端） | `kongsc/b08-contracts` / `codex/a10-batch1@b801553` | `src/contracts/api.v1.yaml`、`src/contracts/errors.v1.md`、生成物、`tests/contracts/test_b08.py`、`scripts/verify/contracts.sh`、相关规格与架构、本任务板、`docs/handoffs/codex-b08.md` | `tests/contracts/test_b08.py` 5 passed；`./scripts/verify.sh` exit 0（含 22 项契约负例及 B08 回归）；`./scripts/gen-contracts.sh --check` PASS；`docs/handoffs/codex-b08.md` |

- 输入：A10 批 1 的 OpenAPI 真源、ADR-010/011/012 与 A07 已确认的错误语义。
- 输出：公共错误码闭集、同步与异步失败语义、已有 SourceRef 定位及四类关系约束的回归测试、更新的生成物。
- 依赖：A10 批 1 已完成；B05 后端运行时尚未进入本基线，B08 只改契约。
- 风险：新增枚举值需下游按未知码兜底；BUDGET_EXCEEDED 的 HTTP 状态由本任务定为 429，并在共享 429 响应中与可重试的 RATE_LIMITED 区分。
- 验证：`python -m pytest tests/contracts/test_b08.py -q`、`./scripts/gen-contracts.sh --check`、`./scripts/verify.sh`、`git diff --check`。

## B09 课程与资料 REST 契约

| 原子 ID | 状态 | 任务 | 负责人 | 目标分支 / base | 文件锁 | 验收证据 |
| --- | --- | --- | --- | --- | --- | --- |
| B09 | DONE（GitHub CI 已验证） | 迁移课程与资料 REST 契约 | Codex（后端） | `kongsc/b09-contracts` / `kongsc/b08-contracts@21253f8`，已纳入 `15dacce` | `src/contracts/api.v1.yaml`、生成物、`tests/contracts/test_b09.py`、`scripts/verify/contracts.sh`、`.github/workflows/ci.yml`、`src/contracts/toolchain.txt`；文档为身份规格、任务板与 `docs/handoffs/codex-b09.md` | B09/B08 专项 9 passed；GitHub Actions [run 35944829534](https://github.com/arvinhanye/SmartSketch/actions/runs/35944829534) 的 `./scripts/verify.sh` 通过（B08 5 项、B09 4 项）；`./scripts/gen-contracts.sh --check` PASS；`docs/handoffs/codex-b09.md` |

- 输入：现有课程/资料 OpenAPI 路径、ADR-013 与 `specs/identity-access.md` §3～§7。
- 输出：带课程内角色的 Course、成员管理 DTO 与 REST 操作、课程列表可见性及现有资料接口的错误响应契约。
- 依赖：B08、A05 已完成；B09 分支已纳入 B08 审查修复 `15dacce`，不修改 B05 运行时文件。
- 风险：B09 只定义协议，成员权限和课程过滤须由后续 C03/C04/C15 实现；当前基线 A10 批 1 尚待集成。
- 验证：`python -m pytest tests/contracts/test_b09.py -q`、`./scripts/gen-contracts.sh --check`、`./scripts/verify.sh`、`git diff --check`。
- CI 修复（2026-09-24）：首次 GitHub 运行因 Python 环境未安装 `pytest` 报 `No module named pytest`；`aa1c3e9` 将 `pytest==8.3.5` 加入工作流依赖和工具链清单，随后 GitHub Actions run 35944829534 通过。
- Claude 审查（REVIEW-B08-B09，2026-09-24）：审查通过；同步 main 后修正 B09-R01（`getCourse` 404 描述与 identity-access §4.1 冲突，先加测试再改并重新生成）；`verify.sh` 通过（B08 5、B09 5）；见 `docs/handoffs/claude-review-b08-b09.md`。自 2026-09-24 起后端由 ArvinHan 接手，B10 起的后端任务负责人记为 ArvinHan（Claude 执行）。

## B10 任务与 SSE 契约

| 原子 ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| B10 | DONE（REVIEW-20 两项已在 `21de627` 修复；REVIEW-22 的 B10F-R01 P2、B10F-R02 P3 未修，见下方「审查遗留」） | 迁移任务与 SSE 契约 | ArvinHan（Claude 执行） | `claude/b10-task-sse-contract` / base `9d2437e` | `src/contracts/api.v1.yaml`、`src/contracts/events.v1.md`、`src/contracts/v1/generated/`、`tests/contracts/test_b10.py`；按 B08/B09 先例接入 `scripts/verify/contracts.sh`；随附状态标注：`specs/task-processing.md` §9、`specs/identity-access.md` §7、`src/contracts/README.md`、`docs/handoffs/claude-b10.md` | `test_b10.py` 先 27 failed 后 36 passed；六处反向篡改均被检出；`gen-contracts.sh --check` 一致；`verify.sh` exit 0（22 负例 + B08 5 + B09 5 + B10 36）；生成的 TS 经 `tsc --strict` 通过；`docs/handoffs/claude-b10.md` |

- 输入：`specs/task-processing.md`「交给后续任务的契约缺口」B10 各行与 §4、§5、§7、TASK-17；`specs/identity-access.md` §5、§7 B10 行、访问矩阵任务行（ADR-010、ADR-013 已签收）。
- 输出：`TaskEvent` 按事件拆成四个独立 schema（按 `stage` 判别）；`Task` 增加 `cancel_requested`、`failed_chunks`，并约束 `failed ⇔ error`；`TaskCounts.chunks_failed`；`issueEventTicket` 与 `EventTicket`；`streamTaskEvents` 改用 `eventTicket`；取消端点 200/409 描述；任务类 403/404 语义；`events.v1.md` §1、§2、§4 按规格改写。
- 依赖：B08（已合入）、A03、A05。无运行时代码、数据库或环境变量改动。
- 风险：`events.v1.md` §6 要求破坏性变更升 v2；依据 ADR-010（`specs/task-processing.md` §7）——v1 尚无消费者（C11/C12 未实现），原地修改。
- 验证：`python3 -m pytest tests/contracts/test_b10.py -q`、`./scripts/gen-contracts.sh --check`、`./scripts/verify.sh`、`git diff --check`。
- Claude 审查（REVIEW-B10，2026-09-24）：P2×4 已修——R01 `Task` 按 `stage` 拆为四个分支（生成器可见 `failed ⇔ error`）、R02 固定进度 `queued = 0` / `awaiting_review = 0.95`、R03 快照补 I5 与 `completed ⇒ progress = 1`、R04 新增 `TaskNotCancellableError` 闭集；P3×4（R05～R08）不阻塞、未改。B10 测试 36 → 45，`verify.sh` 通过；见 `docs/handoffs/claude-review-b10.md`。

## 2026-09-24 协作状态核对与 C08 认领

状态依据：交接基线 `origin/main@62cbbc7` 已包含 PR #175；PR #176 创建后先同步 `origin/main@248b895`，本轮再同步 `origin/main@1bce2c6`（含 B13 R09 修复 PR #177）。交接稿是当时快照，以下为本轮最新 issue/PR 核对；本轮只认领 C08，不改其他成员的源码。

| 分类 | 当前整理结果 |
| --- | --- |
| 已交付并入 main | A01～A10、B01～B06、B08～B10、B13、C01、C08、CI-01/02、HOOK-01、A10 批 0/1/1 补；B13 #55、C01 #58 与 C08 #65 已关闭并标 `status:done` |
| 有 PR、尚未并入 | 无（本节范围内）；B13 #32、C01 #174、C08 #176 均已合入，不再列为待审 PR |
| 阻塞/待认领 | B11 #53 仍按其 issue 处理；C02 #59 已分配 539210，C01 依赖现已合入，不重复认领 |
| 可接取但未认领 | D01、B12、E01、F01、B07、C05；依赖以交接稿第 5 节为起点，开工前再核对 issue 与文件锁 |
| 本轮认领 | C08 #65：已分配 `arvinhanye`，PR #176 已于 2026-09-24 合入 `main@f0b4afe`，issue 已关闭并标 `status:done`，见 [issue 验收记录](https://github.com/arvinhanye/SmartSketch/issues/65#issuecomment-5818583257) |

| 原子 ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 验收与证据 |
| --- | --- | --- | --- | --- | --- | --- |
| C08 | DONE（PR #176 已合入 `f0b4afe`；#65 已关闭） | 实现状态迁移纯函数 | Codex（后端） | `codex/c08-task-state` / 初始 `62cbbc7`、已同步 `1bce2c6`；隔离 worktree `c08-task-state` | `src/backend/app/services/task_state.py`、`tests/backend/test_c08.py`；协作文档仅本节和 `docs/handoffs/codex-c08.md` | §2 合法边与 TASK-16 拒绝路径已实现；C08 定向 67 例、最新 main 上后端 143 例通过、B13 53 例通过，`./scripts/verify.sh`、`git diff --check` 通过。证据与边界见 `docs/handoffs/codex-c08.md`。REVIEW-C08 R01～R04 由 Claude 经授权在同分支修复并同步 `main@28b09b4`：C08 122 例、后端 198 例通过，见 `docs/handoffs/claude-review-fix-c08.md`。PR #176 CI 全绿后由 ArvinHan 授权于 2026-09-24 合入 `main@f0b4afe`。 |

- 输入：B10 已合入的 `Task`/事件契约；ADR-010 签收的 `specs/task-processing.md` §1～§4、TASK-16。
- 输出：无 I/O 的 `(当前任务状态, 事件) → 新任务状态 | 拒绝` 逻辑和定向测试，不变更 API、数据库或既有 DTO。
- 依赖：A03、B10、C01、B13 均已合入；C09、C11、F13 后续消费 C08，C08 已合入，这三项对 C08 的依赖已满足。
- 风险：并发 CAS、租约与持久化不属于本轮纯函数；固定进度及 `failed ⇔ error` 已由运行时校验覆盖。认领时缺依赖的环境缺口已用锁定版本的隔离 venv 解决，`verify.sh` 已通过。
- 当前协作状态：B13 #55 与 C01 #58 已关闭、标 `status:done`；C08 #65 已关闭、标 `status:done`；C02 #59 已分配 539210，现不再受 C01 未合入阻塞。其余任务仍需逐项按 issue/文件锁复核后再认领。

### HANDOFF-0924 固定范围复审（本节覆盖上文各任务行的旧「待审查」标记）

| 审查 ID | 状态 | 固定范围 | 负责人 | 验收与证据 |
| --- | --- | --- | --- | --- |
| REVIEW-HANDOFF-0924 | DONE（B02 Windows 缺口保留；B13 R09 已修） | B10 `f00a3e8..bb48429`；B02 `9d2437e..3fedd4e`；B03/B04 `3fedd4e..06f33aa`；CI-02 `06f33aa..025cbee`；B13 PR #32 `bb48429..791b1d8` | Codex | B10、B02、B03/B04、CI-02 固定范围未发现新增 P1/P2；B13 固定提交发现 P2×7、P3×2。Claude 在 `8a4992c` 修 R01～R07 后 PR #32 已合入；R09 后续由 PR #177 修复并合入，[#178](https://github.com/arvinhanye/SmartSketch/issues/178) 已关闭；本轮未跨文件锁修改契约。Windows 缺口及原始证据见 `docs/handoffs/codex-review-handoff-0924.md`。 |

- 复审只检查固定提交与实际运行的命令，不修改 Claude 的源码；B13 结论不等于新头提交已审。旧自动审查状态文件 `docs/reviews/claude-review-state.json` 在主目录有其他 Codex 未提交改动，本分支不覆盖它；本次增量状态另记 `docs/reviews/codex-handoff-0924-state.json`。
- C08 纯函数已实现并通过本地验证；B10 生成类型忽略固定阶段进度条件的已知限制由 C08 运行时及后续 C11 序列化路径承担。PR #176 已合入 `main@f0b4afe`，issue #65 已关闭；实现验收另记在 `docs/handoffs/codex-c08.md`，不与审查完成混算。REVIEW-C08（PR #176 评论）的 R01 错误详情序列化、R02 失败码按 §6 绑定阶段、R03 `invalid_event`、R04 契约对齐测试已修复，见 `docs/handoffs/claude-review-fix-c08.md`。

## B13 问答与事件契约

| 原子 ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| B13 | DONE（已合入；R09 已修） | 迁移问答与事件契约 | ArvinHan（Claude 执行） | `claude/b13-chat-contract` / 叠在 B10 `3771ae1`（PR #31）上 | `src/contracts/api.v1.yaml`、`src/contracts/events.v1.md` §3、`src/contracts/v1/generated/`、`tests/contracts/test_b13.py`；接入 `scripts/verify/contracts.sh`；随附：`docs/architecture.md` 的 `NotCoveredReason` 行（Q11 要求同一次提交）、`src/contracts/errors.v1.md` 的 `RATE_LIMITED` 措辞（Q11 交 B08 的遗留）、`specs/grounded-qa.md` Q11 状态标注、`docs/handoffs/claude-b13.md` | `test_b13.py` 先 17 failed 后 43 passed；六处反向篡改均被检出；门禁实例级夹具按新必填字段补齐；`gen-contracts.sh --check` 一致；`verify.sh` exit 0；生成的 TS 经 `tsc --strict` 通过；`docs/handoffs/claude-b13.md` |

- 输入：`specs/grounded-qa.md` Q2、Q4、Q5、Q6、Q7、Q9、Q11 B13 行（ADR-015 及修订 1 已签收）。
- 输出：`NotCoveredReason` 改名为 `insufficient_evidence`；`ChatMetaEvent`、`ChatAnswered`、`ChatNotCovered` 增加 `graph_version`、`request_id`；问答错误事件带 `details.request_id`，`LLM_UNAVAILABLE` 的 `details.reason` 取闭集；问答接口补 404/500；`events.v1.md` §3 改为指向规格。
- 依赖：B08（已合入）、A09；叠在 B10 上以避免生成物冲突。
- 风险：同 B10，v1 问答事件尚无消费者（J07/J08 未实现），原地修改。
- 验证：`python3 -m pytest tests/contracts/test_b13.py -q`、`./scripts/gen-contracts.sh --check`、`./scripts/verify.sh`、`git diff --check`。
- Claude 审查（REVIEW-B13，2026-09-24）：修 R01～R07——`ChatError` 按 `code` 拆为两支、错误码闭集、`reason` 只属于 `LLM_UNAVAILABLE`（R01～R03）；`meta.status = answered ⇒ retrieved ≥ 1`（R04）；问答 503 引用 `ChatUnavailableError`（R05）；`events.v1.md` §6 补登 B13 例外（R06）；`ChatError` 与 B10 取消 409 的 `details` 改为具名 schema（R07）。R08 未改。B13 测试 43 → 52；见 `docs/handoffs/claude-review-b13.md`。Codex 另发现 R09（`ChatDoneEvent` 描述与 I1 矛盾），合并后另开 PR 修正，B13 测试 53。
- Codex 固定头 `791b1d8` 复审另发现 R09；随后 PR #177 已合入 `main@1bce2c6` 并新增回归测试。原跟踪 [#178](https://github.com/arvinhanye/SmartSketch/issues/178) 经回归验证后已标 DONE 并关闭；本 C08 分支只保留历史审查证据，不重改契约文件。

## C01 SQLite 连接与迁移运行器

| 原子 ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 验收 |
| --- | --- | --- | --- | --- | --- | --- |
| C01 | DONE（审查 P1/P2 已修） | 建立 SQLite 连接和迁移运行器 | Codex（后端） | `codex/c01-sqlite` / `9d2437e` | `src/backend/app/repositories/sqlite.py`、`src/backend/migrations/001_base.sql`、`tests/backend/test_c01.py`；文档：`docs/architecture.md`、`src/backend/README.md`、本任务板、`docs/handoffs/codex-c01.md` | 临时库迁移可重复；单事务失败回滚；活跃及到期秒租约拒绝；迁移前备份及恢复演练；B06 向量空间记录保留。审查修复：`model_calls` 预写、按 `call_id` 重放去重与归属查询；迁移返回后立即移动备份。专项 13 passed、后端 71 passed、`./scripts/verify.sh` exit 0，见交接。 |

- 输入：B06 的 `SQLITE_URL` 与 `embedding_space_state`，ADR-011 的停机迁移协议，ADR-012 的空间记录约束。
- 输出：WAL/外键/超时连接函数、只向前的版本化迁移、`001_base.sql` 和恢复步骤。
- 依赖：B06、A04、A06 均已完成；不改 REST/SSE 契约。
- 风险：迁移必须在 API/worker 停机时执行；后续表迁移需沿用同一备份与租约检查协议。
- 验证：`python -m pytest tests/backend/test_c01.py -q`、B05/B06 回归、`./scripts/verify.sh`、`git diff --check`。
- Claude 同步与审查（REVIEW-C01，2026-09-24）：同步 main `6790d22`（本节按编号移到 B13 之后，内容不变）；后端 71 passed、CI 三个 job 通过。P2×3（R01 迁移文件换行影响校验和、R02 启动不检查迁移版本、R03 `embedding_space_state` 建表有两处）已由 Claude 修正（ArvinHan 决定；ADR-012 补注修订 1：建表只在迁移，API 启动先检查迁移版本），后端 76 passed；P3×6 未改；见 `docs/handoffs/claude-review-c01.md`。

## ADR-012 修订 3：快照谱系与共享提交序号（解除 B11 阻塞）

| ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| ADR-012 修订 3 | DONE（ArvinHan 2026-09-24 在会话中签收，PR #179） | 落实 ADR-014 修订 1 决定 9、10 交给 ADR-012 的两项：快照节点 `merged_from` 的形状与摘要纳入、版本提交从共享序列取 `commit_seq` | ArvinHan（Claude 起草） | `claude/adr-012-r3` / base `248b895` | `docs/decisions.md`（ADR-012 修订 3 一节与引言一行）、`specs/teacher-review-publish.md`（V2、V3、V5、V6、V10）、`specs/learning-path.md`（§7 细则 1、2 的指向）、本节、`docs/handoffs/claude-adr-012-r3.md` | `docs/handoffs/claude-adr-012-r3.md`；`./scripts/verify.sh` 通过 |

- 输入：ADR-014 修订 1 决定 9、10 与「后果」；`specs/learning-path.md` §5、LP-9、LP-17～LP-20；`specs/teacher-review-publish.md` V2～V6。
- 输出：决定 15～25——`merged_from` 为本版本中归属到该节点的全部来源、链已展平；不变式与 `invalid_lineage` 校验；草稿维护规则；纳入摘要、不升 `snapshot_format`；不进 wire DTO；单行表 `commit_sequence` 与 `commit_seq` / `write_seq`。
- 依赖与风险：已签收，B11、F10、G01、G02、G04、G06、I01 可按本条实现；B11 须同时并入 A02-R01。
- 验证：`./scripts/verify.sh`、`git diff --check`；LP-9、LP-19、LP-20 三个谱系场景已在交接中逐一推演。

## 2026-09-24 并行批次（Claude）

同一批并行开工的四项，各在独立 worktree 与分支上进行，文件锁互不相交；任务板由协调方（本会话）统一更新，各子任务只写自己的交接文件。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| C13 | DONE（PR #186 `6639e16`） | 实现本地账号登录与访问令牌签发 | Claude（后端子代理） | `claude/c13-auth` / `origin/main` | `src/backend/app/api/auth.py`、`src/backend/app/services/auth.py`、`src/backend/app/repositories/accounts.py`、`src/backend/migrations/NNN_accounts.sql`、`tests/backend/test_c13.py`、`src/backend/app/config.py`、`.env.example`、`docs/integrations.md`；接线所需的 `src/backend/app/main.py`；依赖变化时 `src/backend/pyproject.toml` | `docs/handoffs/claude-c13.md`；REVIEW-C13 R01～R06 已修（`9265580`、`7d8deb7`）；C13 58 passed，合入 main 后后端 474 passed，`verify.sh` exit 0；CI 三个 job 通过；#160 已关闭 |
| D01 | DONE（PR #183 `cfec20e`） | 定义解析输出与自编 fixture | Claude（数据子代理） | `claude/d01-parse-model` / `origin/main` | `src/backend/app/services/parsers/`（仅 `__init__.py`、`models.py`）、`tests/fixtures/documents/`、`tests/backend/test_d01.py` | `docs/handoffs/claude-d01.md`；REVIEW-D01 R01～R05 已修（`74be60d`）；D01 88 passed，合并前复核后端 416 passed、`verify.sh` exit 0；CI 通过；#70 已关闭 |
| E01 | DONE（PR #182 `dc20326`） | 建立版本化提示词装载器 | Claude（AI 子代理） | `claude/e01-prompts` / `origin/main` | `src/backend/app/services/ai/`（仅 `__init__.py`、`prompts.py`）、`prompts/`、`tests/backend/test_e01.py` | `docs/handoffs/claude-e01.md`；E01 69 passed、后端全部通过；CI 三个 job 通过 |
| C05 | DONE（PR #181 `3f1f059`） | 实现文件落盘边界 | Claude（后端子代理） | `claude/c05-file-storage` / `origin/main` | `src/backend/app/services/file_storage.py`、`tests/backend/test_c05.py` | `docs/handoffs/claude-c05.md`；C05 61 passed、后端全部通过；CI 三个 job 通过；配置项待补（D-11） |

- 进展（2026-09-24）：C05、E01、D01、C13 均已合并，本批完成。C13 引入的全局 422 处理器输出 `details.fields = [{in, field, reason}]`，已登记到 `src/contracts/errors.v1.md`。
- ~~待认领：按 D-11 把 `UPLOAD_MAX_BYTES`、`STORAGE_DIR` 补进 `config.py`、`.env.example`、`docs/integrations.md`~~（已完成，见「D-11 上传配置落地」）；D02～D05 现可并行认领（只依赖 D01）；C02、C03、C14、H13 的前置 C13 已满足。
- 不在本批：B12（与 539210 的 B11 同改 `api.v1.yaml`）、B07（与 C13 可能同改 `pyproject.toml`）、F01（需要本机 Docker/Neo4j）。
- 并行约束：四项都不改 `docs/tasks.md`、`docs/architecture.md`、`scripts/verify.sh`；需要改共享文件时停下来交给协调方。

## 2026-09-24 解析并行批次（Claude）

D02～D05 只依赖已合并的 D01，四项同时开工，各在独立 worktree 与分支上进行。任务板由协调方统一更新，各子任务只写自己的交接文件。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| D02 | DONE（PR #190 `d2c465e`） | 实现 TXT 编码与标题解析 | Claude（数据子代理） | `claude/d02-txt-parser` / `origin/main` | `src/backend/app/services/parsers/txt.py`、`tests/backend/test_d02.py`、`docs/handoffs/claude-d02.md` | `docs/handoffs/claude-d02.md`；标准库、无新依赖；D02 94 passed，协调方复核后端 568 passed；CI 通过；#71 已关闭 |
| D03 | DONE（PR #191 `2694e3e`） | 实现 Markdown AST 解析 | Claude（数据子代理） | `claude/d03-markdown-parser` / `origin/main` | `src/backend/app/services/parsers/markdown.py`、`tests/backend/test_d03.py`、`docs/handoffs/claude-d03.md`；新增依赖时 `src/backend/pyproject.toml` 的 `dependencies` 一行 | `docs/handoffs/claude-d03.md`；`markdown-it-py==4.2.0`（MIT）；含 D-12 放宽；D03 66 passed，协调方复核后端 634 passed；CI 通过；#72 已关闭 |
| D04 | DONE（PR #193 `ebed3cd`） | 实现 DOCX 段落和表格解析 | Claude（数据子代理） | `claude/d04-docx-parser` / `origin/main` | `src/backend/app/services/parsers/docx.py`、`tests/backend/test_d04.py`、`docs/handoffs/claude-d04.md`；新增依赖时 `src/backend/pyproject.toml` 的 `dependencies` 一行 | `docs/handoffs/claude-d04.md`；标准库自解析、无新依赖；D04 53 passed，协调方复核后端 527 passed，billion-laughs 样例被拒；CI 通过；#73 已关闭 |
| D05 | DONE（PR #197 `a08bd5b`） | 实现 PDF 正文与页码提取 | Claude（数据子代理） | `claude/d05-pdf-parser` / `origin/main` | `src/backend/app/services/parsers/pdf.py`、`tests/backend/test_d05.py`、`docs/handoffs/claude-d05.md`；新增依赖时 `src/backend/pyproject.toml` 的 `dependencies` 一行 | `docs/handoffs/claude-d05.md`；`pdfminer.six==20260107`（MIT）；协调方解决依赖行冲突（`93d5971`）；D05 33 passed，协调方从 PyPI 完整安装后复核后端 720 passed，CI 中 `pip check` 无冲突；#74 已关闭 |

- 依赖约定：D02 只用标准库。D03～D05 如需解析库，只选 MIT/BSD/Apache 类许可，禁用 AGPL（如 PyMuPDF），版本固定为 `==`，只在 `dependencies` 加一行，不动 `test` 组（B07 PR #187 在改 `test` 组）。三者在 `pyproject.toml` 若有文本冲突，由协调方在合并时顺序解决。选库理由写入各自交接，由协调方统一登记到 `docs/integrations.md`。
- 共享文件不改：`parsers/__init__.py`、`parsers/models.py`、`tests/fixtures/documents/`、`docs/tasks.md`、`docs/architecture.md`、`docs/integrations.md`、`scripts/verify.sh`。测试用的 DOCX/PDF 在测试里生成到 `tmp_path`，不入库。需要改共享文件时，停下来交给协调方。
- D05 须给 D06（PDF 标题判定）留下逐行的字号和字重信息，D07 需要的逐页行也要能取到；接口形状写入 D05 交接。
- 进展（2026-09-25）：D02～D05 均已合并，本批完成。解析依赖已登记到 `docs/integrations.md`「文档解析依赖（D02～D05）」。D06、D07 现可认领（依赖 D05，中间结构见 `docs/handoffs/claude-d05.md`）；D08 须按 D-13 在块前拼章节路径。
- 遗留风险：PDF 解析没有限制页数与耗时，恶意文件可能拖慢 worker，由后续 worker 超时机制兜底；DOCX 主文档路径固定为 `word/document.xml`，不按关系文件解析。

## REQ-01 赛题抽取硬指标补登

| ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| REQ-01 | DONE（文档补登；指标尚未实测） | 把赛题「技术要求与指标（一）」的两项硬指标（单章实体 ≥ 20、人工抽样准确率 ≥ 70%）补进规格和原子任务 | ArvinHan（Claude 执行） | `claude/pdf-course-model-training-0b0f46` / `6639e16` | `specs/course-knowledge-graph.md`（关联任务、验收 7）、`docs/product.md`（MVP 表「抽取质量」行）、`docs/atomic-task-plan.md` 与 `docs/atomic-tasks.json`（K01、K02 行，人工决策门 D-01 行）、本节与 D-01 行、`docs/handoffs/claude-req-01.md` | `validate_atomic_plan.py` PASS（141 项，MD/JSON 一致）；`./scripts/verify.sh` exit 0；`git diff --check` exit 0；`docs/handoffs/claude-req-01.md` |

- 输入：赛题原文 `【A10】基于AIGC的课程知识图谱智能构建与学习导航系统【金扬智能】.docx`（在主目录，不入库）第 6 节「技术要求与指标（一）」与第 7 节。
- 输出：验收 7 规定了基准材料、实体数、准确率、判定对象、报告内容和失败路径；K01 负责口径与一章量的标注材料，K02 负责计算、判定并新增 `evaluation/reports/extraction-accuracy.md`。
- 核对：赛题其余指标已有覆盖——格式 ≥ 2 种、关系 ≥ 3 种（四格式、四关系）；问答 ≤ 15 秒（`LLM_CHAT_TIMEOUT_SECONDS`、K04）；讲解与练习题（O05/O06）；赛题不要求训练模型。
- 决策 D-15（ArvinHan，2026-09-24 确认；原拟编号 D-14 已被 PR #199 的 PDF 权限决策占用，合并时改号）：70% 按「实体、关系分别达标」执行。

## D-11 上传配置落地

| ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| D-11 落地 | DONE（PR #205 `50dca8c`） | 把 `STORAGE_DIR`、`UPLOAD_MAX_BYTES` 补进设置、示例与集成登记 | Claude（协调方） | `claude/d11-upload-config` / `04f8ac6` | `src/backend/app/config.py`、`.env.example`、`docs/integrations.md`（应用运行与存储表、启动校验）、`tests/backend/test_d11_upload_config.py`、本节与 D-11 行、`docs/handoffs/claude-d11-upload-config.md` | `docs/handoffs/claude-d11-upload-config.md`；先红 10 failed，后绿 D-11 10 passed；后端全量 730 passed |

- 输入：D-11（50 MiB、变量名 `UPLOAD_MAX_BYTES`）；`STORAGE_DIR=./storage` 沿用 740adb（A10 导入映射「批 2 只取 `STORAGE_DIR`」）。输出：`Settings.STORAGE_DIR`、`Settings.UPLOAD_MAX_BYTES`，C06/C07 按 `FileStorage(settings.STORAGE_DIR, max_bytes=settings.UPLOAD_MAX_BYTES)` 使用。
- 验收：缺省值与 D-11 一致；0、负数、小数、带单位、空串拒绝并指出变量名；空白 `STORAGE_DIR` 拒绝；设置值能直接构造 `FileStorage` 并在超限时给出 `limit_bytes`；`.env.example` 覆盖全部设置（B06 回归）。

## 2026-09-25 Codex 认领：C06

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 验收条件 |
| --- | --- | --- | --- | --- | --- | --- |
| C06 | DONE（PR #209 `8309c03`；#63 已关闭） | 实现资料和任务创建事务 | Codex（后端） | `.claude/worktrees/c06-material-task-transaction`，分支 `codex/c06-material-task-transaction` / `origin/main@a80519c` | `src/backend/app/repositories/materials.py`、`src/backend/app/repositories/tasks.py`、`src/backend/migrations/003_tasks.sql`、`tests/backend/test_c06.py`、`tests/backend/test_c13.py`（范围扩展：仅更新新增 003 后的默认迁移序列断言）、`docs/handoffs/codex-c06.md` | 原子创建、回滚、课程隔离幂等与按课程限定读取已验证；C06 7 passed；后端 763 passed（1 条既有 Starlette/httpx 弃用警告）；`./scripts/verify.sh` 与 `git diff --check` 通过。交接：`docs/handoffs/codex-c06.md`；实现锚点 `7117683`；课程隔离评审修正 `34c73c9`；PR #209。迁移编号按 D-10 已对 `origin/main@a80519c` 复核，最大版本仍为 002。 |

- 输入 / 输出：接收已校验的文件元数据，原子地产生 material 与 queued task。依赖 C01、B10 均已合入 `origin/main`；C05 已合入，上传 API 留给 C07。
- 风险 / 回滚：C13 默认迁移序列测试随新增 003 更新，范围扩展仅限其期望序列；其余只写入上列文件。迁移需遵循 C01 停机、备份与恢复流程；合并前若编号冲突，按 D-10 改号并重跑迁移测试。C07 需在幂等重放时删除新落盘的未引用文件；再处理与 parse_status 语义留待 C07。

## C14 账号管理命令与演示账号种子

| ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| C14 | DONE（PR #210） | 实现账号管理命令与演示账号种子 | Claude | `claude/c14-account-seed` / `04f8ac6` | `scripts/manage-accounts.py`、`scripts/seed-demo-accounts.py`、`tests/backend/test_c14.py`；**范围扩展**（后端分层规则要求业务放 services、持久化放 repositories，#161 已登记）：`src/backend/app/services/account_admin.py`（新建）、`src/backend/app/repositories/accounts.py`（只追加函数）；`docs/integrations.md`（本地账号登录节）、本节、`docs/handoffs/claude-c14.md` | `docs/handoffs/claude-c14.md`；C14 26 passed（先红：缺模块收集失败，后续逐步转绿）；9 处反向篡改中 7 处被抓到，另 2 处是等价变异（原因见交接）；后端全量 746 passed；`verify.sh` exit 0 |

- 输入：`specs/identity-access.md` §1.1、§1.2（ADR-013）；C13 的 `create_account` 与 `users` 表。输出：两个命令脚本，以及服务函数 `set_disabled`、`reset_password`、`list_accounts`、`seed_demo_accounts`。
- 验收：创建和停用都能用 `list` 复查；重复停用保留首次时间；重复种子不新增、不改已有口令和停用状态；缺少或空白的 `SEED_DEMO_PASSWORD` 非 0 退出且不写库；同名账号类型不符整批拒绝；未迁移的库非 0 退出且不建库文件；口令不作为命令行参数，也不出现在任何输出里。
- 不在本任务：协作教师经命令行加入课程（§3.3）需要 C02 的课程和成员表，交 C02/C15。

## 2026-09-25 并行批次（Claude）

F05、E02、D06、D07、C02 前置均已合并，与 B12（改 `api.v1.yaml`）无共享文件，五项同时开工，各在独立 worktree 与分支上进行。C02 原分配 539210（2026-09-24 回复“正在做”，远端无分支或 PR），经 ArvinHan 授权转由 Claude 执行，见 issue #59。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| F05 | DONE（PR #203 `b4ed883`） | 实现 DAG 环检测纯函数 | ArvinHan（Claude 子代理） | `claude/f05-dag-cycle` / `8eeac3b` | `src/backend/app/services/graph/dag.py`、`tests/backend/test_f05.py`、`docs/handoffs/claude-f05.md` | 红：仅测试时收集错误（无 `app.services.graph`）；桩函数 72 failed。绿：`test_f05.py` 73 passed；`tests/backend` 793 passed（基线 720）；5 处篡改全部被检出（其中旋转篡改首轮漏检，已补测试）；`./scripts/verify.sh`、`git diff --check` exit 0。另补 `services/graph/__init__.py`。见 `docs/handoffs/claude-f05.md` |

- F05 验收：自环、三节点环、反转造环、断开图、大链条；复杂度边界明确。验证：`python3 -m pytest tests/backend/test_f05.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| E02 | DONE（PR #207 `aaae534`） | 建立模型接口和 fake 适配器 | ArvinHan（Claude 子代理） | `claude/e02-ai-client` / `8eeac3b` | `src/backend/app/services/ai/client.py`、`src/backend/app/services/ai/fake.py`、`tests/backend/test_e02.py`、`docs/handoffs/claude-e02.md` | `docs/handoffs/claude-e02.md`；实现 `c87ae5c`；E02 先红（收集错误 exit 2）后 65 passed；后端 785 passed；`verify.sh` exit 0；`git diff --check` exit 0；5 处篡改均被检出；无新依赖；待决见交接（fake 模式模型 ID、缓存键取哪个模型 ID） |

- E02 验收：固定输入输出可复现；超时/坏 JSON/限流可模拟；无需密钥。验证：`python3 -m pytest tests/backend/test_e02.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| D06 | DONE（PR #208 `1ffda90`） | 实现 PDF 标题判定 | ArvinHan（Claude 子代理） | `claude/d06-pdf-headings` / `8eeac3b` | `src/backend/app/services/parsers/pdf_headings.py`、`tests/backend/test_d06.py`、`docs/handoffs/claude-d06.md` | `docs/handoffs/claude-d06.md`；无新依赖；先红（模块缺失，收集错误 exit 2）后绿：D06 34 passed，后端 754 passed，6 项反向篡改均被检出；`./scripts/verify.sh` exit 0；`git diff --check` exit 0 |

- D06 验收：正文加粗不误做所有标题；标题跨页、无字号层级有退路。验证：`python3 -m pytest tests/backend/test_d06.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| D07 | DONE（PR #204 `003dd20`） | 实现重复页眉页脚清洗 | ArvinHan（Claude 子代理） | `claude/d07-header-footer` / `8eeac3b` | `src/backend/app/services/parsers/cleanup.py`、`tests/backend/test_d07.py`、`docs/handoffs/claude-d07.md` | `docs/handoffs/claude-d07.md`；标准库、无新依赖；先红（收集错误 exit 2）后绿 D07 43 passed；6 处反向篡改均被检出；后端 763 passed（venv，Python 3.13.5）；`./scripts/verify.sh` exit 0；`git diff --check` exit 0 |

- D07 验收：重复正文不被误删；删除页码不丢原始页定位；支持关掉清洗。验证：`python3 -m pytest tests/backend/test_d07.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| C02 | DONE（PR #206 `a7a0be0`） | 实现课程和成员仓储 | ArvinHan（Claude 子代理；原 539210） | `claude/c02-course-repo` / `8eeac3b` | `src/backend/app/repositories/courses.py`、`src/backend/migrations/NNN_courses.sql`（D-10：合并时取 main 最大编号 + 1）、`tests/backend/test_c02.py`、`docs/handoffs/claude-c02.md` | 迁移取 `004_courses.sql`（C06 #209 先占 003，按 D-10 改号；同步适配 `test_c13.py`、`test_c06.py` 迁移断言）。`test_c02.py`：实现前收集失败（ImportError，0 passed），实现后 21 passed；4 处反向篡改分别 2/2/1/2 failed，恢复后全绿。`tests/backend` 初为 1 failed / 740 passed（`test_c13.py` 断言迁移目录只到 002）；协调方以单独提交把该用例改为只含 001、002 的临时目录（范围扩展），复跑 741 passed。`./scripts/verify.sh` exit 0；`git diff --check` exit 0。交接 `docs/handoffs/claude-c02.md` |

- C02 验收：课程成员唯一；同用户不同课程角色独立；读写外键正确（`course_members.user_id` → C13 的 `users`）。验证：`python3 -m pytest tests/backend/test_c02.py -q`。

- 进展（2026-09-25）：五项均已合并，本批完成。合并前协调方统一了本节五行、把 C02 迁移改号为 004（C06 #209 先占 003），并修复 C01 迁移器与 C06 任务表不兼容（FIX-MIGRATE-LEASE，#212）。合并后 main 复核：后端 1002 passed、契约与工具 269 passed、`verify.sh` exit 0；收尾交接见 `docs/handoffs/claude-batch-0925-closeout.md`。
- 并行约束：各子任务只写自己的文件锁与交接文件，并只改本节自己那一张表的状态与证据；不改 `docs/architecture.md`、`docs/integrations.md`、`scripts/verify.sh`、`parsers/__init__.py`、`parsers/models.py` 等共享文件，需要时停下交协调方。

## F01 复用本地 Neo4j 环境并验证

| ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| F01 | DONE（PR #211） | 复用本地 Neo4j 环境并验证 | Claude | `claude/f01-neo4j-env` / `a80519c` | `docker-compose.yml`、`scripts/dev-up.sh`、`scripts/check-apoc.sh`、`tests/integration/test_f01.py`；按导入映射「批 2」扩到 `scripts/_dev-common.sh`（dev-up 依赖它）、`.env.example`（仅容器变量注释行）、`docs/integrations.md`（本地依赖环境一节与计划集成 Neo4j 行）；本节、`docs/handoffs/claude-f01.md` | `docs/handoffs/claude-f01.md`；真实 Docker 12 passed（Neo4j 5.26.31 + APOC 5.26.31 可用，停启后数据仍在）；原脚本红灯 4 failed，两处缺陷（unhealthy 被判就绪、口令出现在宿主机命令行）已单独取证并修复；反向篡改 5 处全被抓到；后端 756 passed |

- 输入：740adb `978671e` 的 compose 与脚本（M0-05，当时因 APOC 未实测而 BLOCKED）；ArvinHan 本机 Docker Desktop 29.8、Compose v5.5。输出：可启动、可健康检查、已验证 APOC、停启后数据仍在的本地 Neo4j。
- 验收：先审原脚本（审查结论与两处缺陷的取证见交接）；缺 `.env`、容器不健康、APOC 缺失都以非 0 退出并给出提示；口令不出现在任何命令行参数里；真实容器上 APOC 可用、停启后数据仍在。
- 不在本任务：`dev-down.sh` 与启停行为审查（K07）；Neo4j 驱动与仓储（F02）；约束与索引迁移（F03）。

## F02 Neo4j 驱动与作用域仓储

| ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| F02 | DONE（PR #231 已合入 `d4ba033`） | 实现 Neo4j 驱动与作用域仓储 | ArvinHan（Codex） | `codex/f02-neo4j` / `130e6b6` | `src/backend/app/repositories/neo4j.py`、`src/backend/pyproject.toml`、`tests/backend/test_f02.py`、`docs/atomic-task-plan.md`、`docs/atomic-tasks.json`、`docs/handoffs/codex-f02.md`、本节 | `docs/handoffs/codex-f02.md`；F02 聚焦 **74 passed**，后端 **1124 passed**，`./scripts/verify.sh` exit 0，原子计划校验通过，`git diff --check` 通过。全量离线套件 **1405 passed / 3 skipped / 1 failed**；唯一失败为 B07 假工作区缺少 B14 gate 文件，已在干净 base `130e6b6` 复现；本任务未连接真实 Neo4j。PR #231 |

- 验收：仓储对 course/version 参数化并强制草稿 V 与有效任务集合；teacher/student/worker 意图边界、断连错误和凭据日志边界见 handoff。验证：`python3 -m pytest tests/backend/test_f02.py -q`、`python3 -m pytest tests/backend -q`、`./scripts/verify.sh`。

## FIX-MIGRATE-LEASE 迁移器租约检查与 C06 任务表不兼容（2026-09-25）

| ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| FIX-MIGRATE-LEASE | DONE（PR #212 `4e42a5d`） | C01 迁移器只对有租约列的表检查租约，解除 C06 `processing_tasks`（无租约列）对 003 之后所有迁移的阻塞 | ArvinHan（Claude 协调方） | `claude/fix-migrate-lease-guard` / `1ffda90` | `src/backend/app/repositories/sqlite.py`、`tests/backend/test_c01.py`、`docs/handoffs/claude-fix-migrate-lease.md` | 复现用例 3 个修前 failed、修后 C01 21 passed；后端 981 passed；`docs/handoffs/claude-fix-migrate-lease.md` |

- 后续：C09 加租约列时，补一条真实表上“有效租约阻止迁移”的回归。

## 审查遗留（2026-09-25 核对）

把「待审查」状态逐项对照 Codex 审查报告（REVIEW-18～22，已于 PR #201 入库），并在 `origin/main@36670a3` 上复现。下面 4 项仍然存在，还没有任务跟踪：

| 编号 | 级别 | 来源 | 现状（main 上复现） | 建议归属 |
| --- | --- | --- | --- | --- |
| B03-R01′ | P2 | REVIEW-19（`docs/reviews/codex-claude-b03-b04-2026-09-24-0605z.md`）。加 ′ 是为了和上方 B03 节里协调方自提的 P3「B03-R01」区分 | `src/frontend/src/main.ts` 仍为 `getAccountRole: () => null`，真实入口里教师和学生页面都不可达 | H13（登录页与会话存储）：从 `LoginResponse.user.role` 提供角色，登录、登出、401 时导航，并补真实入口的集成测试 |
| B04-R01 | P2 | 同上 | `stores/course.ts` 的 `selectCourse` 遇到相同课程 ID 直接返回；同一标签页里换账号后，旧 `graph`、`chatHistory` 和已签发的作用域仍然有效 | H13：增加会话重置入口，在登出、401、换账号时调用；或者把用户身份纳入作用域键 |
| B10F-R01 | P2 | REVIEW-22（`docs/reviews/codex-claude-b10-fix-21de627-2026-09-24-1556z.md`） | 生成的 `TaskCancelled.cancel_requested` 是 `Literal[True] = True`（有默认值、非必填），缺字段的取消快照能通过 `Task.model_validate`，而 JSON Schema 会拒绝 | 契约修复，建议在 C10/C11 实现取消响应前完成：让生成模型把该字段设为必填，并补缺字段与 `exclude_unset` 的回归测试 |
| B10F-R02 | P3 | 同上 | `TaskNotCancellableError.details` 的三个分支没有 `additionalProperties: false`，`{stage, reason, secret}` 能通过 JSON Schema | 与 B10F-R01 一起修：三个分支加 `additionalProperties: false`，并补负例 |
| D08-P3 | P3 | PR #215 审查（Claude） | `chunking._render` 给窗口里的每个来源段落各拼一次 `section_path`；同一窗口里有多个短段落时，路径重复出现，抽取时多耗 token。D-13「在每块正文前拼上章节路径」对「块」的理解存在歧义 | D12 接入抽取时一并确认：每个窗口拼一次，还是每个来源段落拼一次 |
| E07-P3 | P3 | PR #217 审查（Claude） | `EmbeddingAdapter.embed` 末尾的 `if vector is not None` 过滤，一旦有向量漏填，结果会静默变短并与输入错位 | 改为断言全部填满；可在 E03 接入时顺手修 |

C03-R01（P1，PR #216 审查）：拒绝错误是模块级的单例异常，反复 raise 会累积 `__traceback__` 并持有每次请求的令牌。已在合并前修复（`fe5ae64`，交接 `docs/handoffs/claude-c03-r01-fix.md`），不再是遗留项。

## 2026-09-25 第二批并行（Claude）

C09、E03、I03 前置均已合并，issue 无人认领，与在途工作不共享文件：539210 的 C03（#216，改 `repositories/tasks.py`）、C04、E07（#217，`ai/embeddings.py`），以及 arvinhanye 的 B14（#214）、D08（#215）、F02、K07。三项各在独立 worktree 与分支上进行。各子任务只改本节中自己那一张表的状态与证据列。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| C09 | DONE（PR #220 `b174b2f`） | 实现 worker 原子领取与租约 | ArvinHan（Claude 子代理） | `claude/c09-task-leases` / `36670a3` | `src/backend/app/repositories/task_leases.py`、`src/backend/migrations/NNN_task_leases.sql`（D-10：现取 005）、`tests/backend/test_c09.py`、`docs/handoffs/claude-c09.md`；不改 `repositories/tasks.py`（C03 #216 在改） | `docs/handoffs/claude-c09.md`；迁移 `005_task_leases.sql`（租约六列，另加任务错误三列与 I4 约束，见交接待决 1）；红灯 3 failed + 45 errors（签名桩）→ C09 50 passed；后端 1052 passed；反向篡改 8 处全部检出；#212 要求的「有效租约阻止迁移」真实表回归已补；`verify.sh`、`git diff --check` exit 0；待决 3 项见交接。**ADR-017 追加（2026-09-25）**：决定 1 登记 `docs/architecture.md` 数据模型；决定 6 C08 码表 `LLM_UNAVAILABLE` 放开 `merging`（`failure_code_allowed` 限定为尝试耗尽，`details` 须含 `attempts`、`stage`），C09 耗尽直接写 `LLM_UNAVAILABLE`，§6 补注；红灯 C08 3 failed、C09 1 failed → C08 137 passed、C09 53 passed；后端 1118 passed；篡改 3 处全部检出；`verify.sh`、`git diff --check` exit 0；待决 1、2 已由 ADR-017 解决，待决 3 仍开 |

- C09 验收：两个连接争同一任务只有一个成功；旧租约 token 禁止续写；到期可接管。验证：`python3 -m pytest tests/backend/test_c09.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| E03 | DONE（PR #221 `7c891eb`） | 实现兼容 API 适配器 | ArvinHan（Claude 子代理） | `claude/e03-compatible-api` / `36670a3` | `src/backend/app/services/ai/compatible.py`、`tests/backend/test_e03.py`、`docs/handoffs/claude-e03.md`；不改 `ai/embeddings.py`（E07 #217 在改） | `test_e03.py` 先红（无模块 exit 2；名字桩 171 failed）后 173 passed；`tests/backend` 全量 1175 passed（基线 1002）；5 处篡改均检出（2/7/2/1/1 failed），恢复后 `cmp` 一致；`./scripts/verify.sh` exit 0、`git diff --check` exit 0；不联网、无密钥；待决 10 项（含向量 HTTP 归属、`max_tokens` 字段名、流式 usage 实测）见 `docs/handoffs/claude-e03.md`；**ADR-017 追加**（决定 2、3）：`CompatibleEmbeddingClient`（`POST /embeddings` 带 `dimensions`/`encoding_format`，按 `EMBEDDING_BATCH_SIZE` 分批且不超过供应商上限（默认 10，取自 D-02c，可传参），按 `index` 还原顺序，逐条核对维度），`integrations.md` D-02a/b 补注输出上限字段与冒烟实测项；新增 118 条先红（桩 117 failed、另 1 条实现中补）后 `test_e03.py` 291 passed，`test_e07.py` 16 passed，`tests/backend` 全量 1341 passed（基线 1223）；3 处篡改（不还原顺序/不核对维度/不分批）检出 3/6/6 failed，恢复后 `cmp` 一致；`./scripts/verify.sh`、`git diff --check` exit 0；待决 1、2 已解决，新增待决 11～14 |

- E03 验收：按 OpenAI 兼容协议实现；用模拟传输测超时、错误与结构；真实调用需另行配置（供应商取值待 D-02a）。验证：`python3 -m pytest tests/backend/test_e03.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| I03 | DONE（PR #219 `0c8389b`） | 实现可学集合纯函数 | ArvinHan（Claude 子代理） | `claude/i03-eligible-set` / `36670a3` | `src/backend/app/services/learning/eligible.py`、`tests/backend/test_i03.py`、`docs/handoffs/claude-i03.md` | 新增 `services/learning/__init__.py`（包原不存在）。红：先收集错误（无模块），桩函数 79 failed/1 passed；绿：`test_i03.py` 80 passed；`tests/backend` 全量 1082 passed（基线 1002）；`./scripts/verify.sh` exit 0；`git diff --check` exit 0；6 处反向篡改均检出（36/19/3/3/28/2 failed），恢复后 `cmp` 一致。有环、自环、悬空端点（含外课边）、重复 ID、`V=∅` 抛 `GraphIntegrityError`；`mastered` 含外课 ID 抛 `ProgressOutsideGraphError`（§1）；结果按 `kp_id` UTF-8 字节序。见 `docs/handoffs/claude-i03.md` |

- I03 验收：已掌握集合为空、全部掌握、孤立点、多前置、有环、外课 ID；不修改用户的掌握集合。验证：`python3 -m pytest tests/backend/test_i03.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| B12-R1 | DONE（PR #224 `c1b812e`） | 进度契约错误细节修订（ADR-017 决定 4、5） | ArvinHan（Claude 子代理） | `claude/b12-r1-progress-errors` / ADR-017 提交 | `src/contracts/api.v1.yaml`、`src/contracts/errors.v1.md`、`src/contracts/v1/generated/`、`tests/contracts/test_b12.py`、`specs/learning-path.md`、`docs/handoffs/claude-b12-r1.md` | 改真源前 B12 34 failed / 88 passed，首版 `75a3775` 后 122 passed；追加提交按 ADR-017 勘误把 `field` 改为点路径 `<i>.kp_id`（先 8 failed / 117 passed，后 125 passed），并补 `tests/tooling/test_b07.py` 夹具 `test_b14.py`（tooling 修前 1 failed / 13 passed，修后 14 passed；ADR-017 与 test_b07 属协调方授权的范围扩展）；`tests/contracts tests/tooling` 305 passed；`./scripts/gen-contracts.sh --check` exit 0；`./scripts/verify.sh` exit 0（含 B12 125 项）；生成 TS `tsc --noEmit --strict` exit 0；`git diff --check` exit 0；反向篡改 5 处均被检出；`docs/handoffs/claude-b12-r1.md` |

- B12-R1 验收：`LearningIntegrityDetails` 只含 `request_id`；`PUT /progress` 422 的 `details.fields[].reason = not_in_published_version` 与 `details.graph_version` 有正负例；重新生成且 `gen-contracts.sh --check`、`tests/tooling` 通过。
- ADR-017 同时追加到 C09（#220：决定 1、6）与 E03（#221：决定 2、3），各自在本节表内更新证据。

- 合并约定：三个分支共用本认领提交。若合并前 main 在本文件末尾又有追加导致冲突，由协调方先在 `claude/batch-0925b-claims` 上解决一次，再并入三个分支，保证三者的解决结果一致。
- 进展（2026-09-25）：四项均已合并（#219 `0c8389b`、#220 `b174b2f`、#221 `7c891eb`、#224 `c1b812e`，按此顺序），合并前四者一起试合无冲突。ADR-017 随 #220 入库，勘误行随 #224 入库。

## 2026-09-25 第三批并行（Claude）

D09、C16、B15 的前置均已合并（D09：D08、A07；C16：C03、C06、B10；B15：B02、B14），issue 无人认领、无远端分支。已核对在途工作并避开：539210 的 C04（课程 API）；arvinhanye 的 F02、K07；本人待合并的 I03 #219、C09 #220（迁移 005）、E03 #221、B12-R1 #224。本认领提交基于第二批认领提交 `6a93cf3`，与上述 PR 无文本冲突。三项各在独立分支上进行，各子任务只改本节中自己那一张表的状态与证据列。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| D09 | DONE（PR #226 `abc914d`） | 实现块身份与缓存键 | ArvinHan（Claude 子代理） | `claude/d09-chunk-identity` / 本认领提交 | `src/backend/app/services/chunk_identity.py`、`tests/backend/test_d09.py`、`docs/handoffs/claude-d09.md` | 红：实现前收集错误 `ModuleNotFoundError`；绿：`tests/backend/test_d09.py` 96 passed；后端全量 1146 passed（基线 1050）；反向篡改 5 处（去 course_id、去 model_id、序号补零、修订哈希输入换序、模型 ID 改取响应字段）均变红，改回后 `cmp` 一致；`verify.sh` exit 1 仅因本机缺 `openapi-typescript`（B14 生成类 2 条 + 负例 1 条），base `9116315` 同命令日志逐行相同；`git diff --check` 通过；待决 5 项见 `docs/handoffs/claude-d09.md`；**ADR-018 追加**（`686f57c` ADR 本文 + 其后实现提交）：`chunking.py` 增 `CHUNKER_VERSION`/`chunking_version()`，`chunk_identity.py` 增 `revision_parser_version()` 且修订键拒绝缺分块段的 `parser_version`；红：先改测试时收集错误 `ImportError`；绿：`test_d09.py` 154 passed、`test_d08.py` 13 passed；后端全量 1204 passed；篡改 3 处（不校验分块段 11 failed、分块版本丢参数 4 failed、组合换序 6 failed）改回后 `cmp` 一致；`verify.sh` exit 0；`git diff --check` 通过 |

- D09 验收：同文不同页有独立出处；跨课程不复用身份；提示词/模型变更失效（缓存键用实际给出结果的模型 ID，见 `docs/integrations.md`）；`revision_id` 与块 ID 按 ADR-012 修订 1 确定性派生。验证：`python3 -m pytest tests/backend/test_d09.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| C16 | DONE（PR #227 `7f9eaf1`） | 实现 SSE 一次性票据申领 | ArvinHan（Claude 子代理） | `claude/c16-event-tickets` / 本认领提交 | `src/backend/app/api/event_tickets.py`、`src/backend/app/repositories/event_tickets.py`、`src/backend/migrations/006_event_tickets.sql`（D-10：005 已由 C09 #220 占用）、`tests/backend/test_c16.py`、`docs/handoffs/claude-c16.md`；范围扩展：`src/backend/app/main.py` 仅加路由注册 | 红灯：仅有测试时收集报 `ImportError`（`app.repositories.event_tickets` 不存在）；绿灯：`tests/backend/test_c16.py` 23 passed；后端全量 1073 passed（基线 1050 + 23）；contracts+tooling 4 failed / 269 passed，与基线 `9116315` 相同，均因环境缺 `openapi-typescript`；反向篡改 5 处（存明文、去 `task_id`、去过期、去 `used_at`、去旧行清理）全部检出，改回后 `cmp` 一致；`verify.sh` 退出 1（contracts gate 的 B14 生成回归缺 `openapi-typescript`，基线同样失败）；`git diff --check` 通过；交接 `docs/handoffs/claude-c16.md` |

- C16 验收（`specs/identity-access.md` §5）：仅保存票据哈希；60 秒过期；重复、跨任务或普通 Bearer 查询票据拒绝；迁移可恢复。验证：`python3 -m pytest tests/backend/test_c16.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| B15 | DONE（PR #228 `f37262c`） | 建立前端 HTTP 客户端 | ArvinHan（Claude 子代理） | `claude/b15-http-client` / 本认领提交 | `src/frontend/src/api/http.ts`、`tests/frontend/b15.test.ts`、`docs/handoffs/claude-b15.md` | 红灯：实现前 exit 1（无法解析 `api/http`）；绿灯：type-check + B15 23 passed，前端全量 4 files / 53 passed，build 通过；7 处反向篡改（不传 signal、401 不回调、超时并入取消、不解析错误体、令牌进 URL、登录 401 回调、参数不编码）均使测试失败，恢复后 `cmp` 一致；`verify.sh` 在补 `openapi-typescript@7.4.4`（仓库外临时安装）后 exit 0，缺该工具时 B14 两例失败与基线相同；待决 8 项见 `docs/handoffs/claude-b15.md` |

- B15 验收：类型化错误、超时/取消、认证失败处理；组件不自行拼路径；把 `scope.signal` 传给 fetch（B04 交出项）。验证：`npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/b15.test.ts`。

- 合并约定：三个分支共用本认领提交。若合并前 main 在本文件末尾又有追加导致冲突，由协调方先在 `claude/batch-0925c-claims` 上解决一次，再并入三个分支。C16 的迁移 006 以 C09 #220 的 005 先合并为前提；若 C09 未合并而 C16 先合，按 D-10 改号。
- 进展（2026-09-25）：三项均已合并（#226 `abc914d`、#227 `7f9eaf1`、#228 `f37262c`）。合并前各分支并入新 main 并等 CI 转绿：D09 在 `docs/decisions.md` 末尾与 ADR-017 勘误行冲突（按编号保留两段），C16 在 `main.py` 路由注册处与 C04 #225 冲突（两行都保留）；迁移 005（C09）先于 006（C16）入库。合并后 main@`f37262c` 复核：后端 1676 passed、契约与工具 305 passed、前端 53 passed、`./scripts/verify.sh` exit 0；收尾交接见 `docs/handoffs/claude-batch-0925f-closeout.md`。

## 2026-09-25 第四批（Claude）

C07 前置 C03、C05、C06、B09 均已合并，issue #64 无人认领、无远端分支；规格缺口已由 D-16 关闭（本提交同时补注 `specs/task-processing.md`）。其余新任务的前置均在待合并 PR 中（E04←E03 #221、E05←D09 #226、I04←I03 #219、C10←C09 #220），本轮不领。已核对在途工作：539210 的 C04（课程 API，可能同样改 `main.py` 路由注册）；arvinhanye 的 F02、K07；待合并的 #219、#220、#221、#224、#226、#227、#228。本认领提交基于第三批认领提交 `9116315`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| C07 | DONE（PR #230 `e8e9787`；移植 539210 #229 的先授权后解析） | 实现上传及资料列表 API | ArvinHan（Claude 子代理） | `claude/c07-materials-api` / 本认领提交 | `src/backend/app/api/materials.py`、`src/backend/app/services/materials.py`、`src/backend/app/schemas/materials.py`、`tests/backend/test_c07.py`、`docs/handoffs/claude-c07.md`；范围扩展：`src/backend/app/repositories/materials.py` 仅新增列表查询（按 D-16 关联最新任务），`src/backend/app/main.py` 仅加路由注册 | `docs/handoffs/claude-c07.md`；红：仅测试时收集错误（无 `app.services.materials`），服务桩 39 failed；绿：`test_c07.py` 39 passed；`tests/backend` 1089 passed（基线 1050）；contracts+tooling 272 passed、1 failed 为已知基线 `test_b07[0-PASS]`（#224）；6 处反向篡改（去课程隔离、parse_status 取列、取最早任务、去补偿删除、忽略 `UPLOAD_MAX_BYTES`、去重放删除）全部检出，恢复后 `cmp` 一致；`./scripts/verify.sh`、`git diff --check` exit 0；依赖 `python-multipart==0.0.32` 按 ADR-019（`6bc2ec4`）；待决见交接（契约无幂等键、列表排序、请求体上限前置、无任务回退）；**移植 #229（539210，`8514ecc`）先授权再有界解析**：红 3 failed、绿 `test_c07.py` 42 passed，`tests/backend` 1718 passed，contracts+tooling 305 passed，3 处篡改（恢复 `UploadFile` 参数、去实收字节计数、去 `Content-Length` 预检）全部检出且 `cmp` 一致，`verify.sh`、`git diff --check` exit 0；ADR-019 决定 2 同步改写 |

- C07 验收：非法格式/课程越权拒绝；存盘或建任务失败可补偿（删除新落盘的未引用文件）；长处理不堵请求（只建任务、立即返回 202 `UploadAccepted`）；列表 `parse_status` 按 D-16 取最新任务 `stage`。验证：`python3 -m pytest tests/backend/test_c07.py -q`。

## 2026-09-25 第五批并行（Claude）

D10、E04、E05、C10、I04 的前置均已合入 main@`f37262c`（D10：D09 #226、C01；E04：E03 #221、C01；E05：E02、D09 #226；C10：C09 #220、C03；I04：I03 #219），issue 无人认领、无远端分支。已核对在途工作并避开：arvinhanye（Codex）的 F02 #231（`repositories/neo4j.py`、`pyproject.toml`）、K07 #232（`scripts/`）；本人待合并的 C07 #230（`api/materials.py`、`main.py`）。本认领提交基于第四批认领提交并入 main 后的结果。五项各在独立分支上进行，各子任务只改本节中自己那一张表的状态与证据列。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| D10 | DONE（PR #234 已合入 `dde2f9a`） | 实现来源块持久化 | ArvinHan（Claude 子代理） | `claude/d10-chunk-store` / 本认领提交 | `src/backend/app/repositories/chunks.py`、`src/backend/migrations/007_chunks.sql`（D-10：main 最大 006）、`tests/backend/test_d10.py`、`docs/handoffs/claude-d10.md` | 交接 `docs/handoffs/claude-d10.md`；迁移 007 新增 `material_revisions`/`task_revisions`/`chunks`（库层不可变触发器，回滚步骤已测）。红灯：仅有测试时收集 `ImportError`（1 error）；绿灯：`test_d10.py` 36 passed（PUB-28/29/30、课程隔离、V2 删除保护）；后端全量 1712 passed（基线 1676 + 36）；contracts+tooling 305 passed；反向篡改 5 处分别 1/4/1/1/1 failed，改回 `cmp` 一致；`verify.sh` exit 0；`git diff --check` 通过。待决 5 项（已提交版本判定注入待 G02、在途任务共享修订的保守保护等）见交接 |

- D10 验收：重复重试不重复写；按课程/文档定位；删除资料策略不破坏已发布引用；块 ID 按 D09/ADR-018 派生，已存在 ID 内容哈希不一致即拒绝（PUB-30）。验证：`python3 -m pytest tests/backend/test_d10.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| E04 | DONE（PR #235 已合入 `5df4146`） | 实现模型调用预算与退避 | ArvinHan（Claude 子代理） | `claude/e04-call-policy` / 本认领提交 | `src/backend/app/services/ai/policy.py`、`src/backend/app/repositories/model_calls.py`、`tests/backend/test_e04.py`、`docs/handoffs/claude-e04.md`（`model_calls` 表已在 001，无迁移） | 红灯：实现前收集 `ImportError`；绿灯 `tests/backend/test_e04.py` 66 passed（47 个函数）；全量 `tests/backend` 1742 passed（基线 1676 + 66），`tests/contracts tests/tooling` 305 passed；反向篡改 5 处（鉴权被重试、`Retry-After` 不封顶、任务预算 `>=` 改 `>`、预写失败仍发请求、日志输出提示词）各被检出（5/2/1/2/1 failed），改回 `cmp` 一致；`./scripts/verify.sh` exit 0、`git diff --check` exit 0；待决 9 项（含退避变量登记、生成前被拒的 `error_class` 格式）见 `docs/handoffs/claude-e04.md` |

- E04 验收：429/5xx 有界退避，鉴权错误不重试；预算零不发请求；日志无 token/原文；退避参数有上限（A07 交出项）。验证：`python3 -m pytest tests/backend/test_e04.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| E05 | DONE（PR #236 已合入 `d5bda28`） | 实现块级实体抽取 | ArvinHan（Claude 子代理） | `claude/e05-entity-extraction` / 本认领提交 | `src/backend/app/services/ai/entities.py`、`prompts/extract_entities.yaml`、`tests/backend/test_e05.py`、`docs/handoffs/claude-e05.md` | `docs/handoffs/claude-e05.md`；红灯：实现前收集错误（模块不存在），绿灯 `test_e05.py` 63 passed；后端全量 1739 passed（基线 1676 + 63），contracts/tooling 305 passed；反向篡改 6 处（证据子串、修复一次、修复不超过一次、类型闭集、长度边界、截断）全被抓到；`./scripts/verify.sh` 与 `git diff --check` 通过；提示词升 v2，越锁改 `prompts/MANIFEST.md` 一行（E01 规则要求同提交更新摘要），待协调方确认；长度上限、修复模板、失败块错误码、缓存存储等见交接待决 |

- E05 验收：五类实体、字段范围、证据必须来自输入；坏 JSON 修复最多一次；只用 E02 fake 客户端测试，不需要密钥。验证：`python3 -m pytest tests/backend/test_e05.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| C10 | DONE（PR #237 已合入 `38f0ad9`） | 实现任务取消服务与 API | ArvinHan（Claude 子代理） | `claude/c10-task-cancel` / 本认领提交 | `src/backend/app/services/task_cancel.py`、`src/backend/app/api/task_cancel.py`、`tests/backend/test_c10.py`、`docs/handoffs/claude-c10.md`；范围扩展：`src/backend/app/main.py` 仅加路由注册 | `test_c10.py` 先收集错误（ImportError）后 33 passed；`tests/backend` 1709 passed（基线 1676）；`tests/contracts tests/tooling` 305 passed；六处反向篡改（去比较并交换条件、终态可再取消、跳过授权、取消清租约、延迟 BEGIN、去 course_id）均被检出；`verify.sh` exit 0；`git diff --check` 通过；待决 5 项（本地响应模型、SQL 所在层、B10F-R01 影响、快照可选字段、SSE 投递）见 `docs/handoffs/claude-c10.md` |

- C10 验收：queued/运行中/完成后/重复取消；取消和写入竞争有确定结果（与 C09 租约令牌同一写入序列）。审查遗留 B10F-R01/R02（取消快照 `cancel_requested` 非必填）若影响响应校验，写入交接待决，不在本任务改契约。验证：`python3 -m pytest tests/backend/test_c10.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| I04 | DONE（PR #238 已合入 `11425e4`） | 实现四项评分和结构化理由 | ArvinHan（Claude 子代理） | `claude/i04-ranking` / 本认领提交 | `src/backend/app/services/learning/ranking.py`、`tests/backend/test_i04.py`、`docs/handoffs/claude-i04.md` | 红：仅测试时收集错误 `ModuleNotFoundError`（exit 2）；绿：`test_i04.py` 115 passed；全量 `tests/backend` 1791 passed（基线 1676 + 115）、`tests/contracts tests/tooling` 305 passed；反向篡改 8 处（解锁数改出度 24 failed、同分章节秩颠倒 1、去零分母保护 32、求和顺序颠倒 2、去权重校验 3、排序前舍入 1、kp_id 降序 2；单删"至少一项为正"0 failed，因和校验已覆盖），均 `cmp` 恢复；`./scripts/verify.sh` exit 0；`git diff --check` exit 0；待决 4 项见 `docs/handoffs/claude-i04.md` |

- I04 验收：零分母、全零权重、同分、真实解锁数；分量求和等于 score；理由不用 LLM。验证：`python3 -m pytest tests/backend/test_i04.py -q`。

- 合并约定：五个分支共用本认领提交。只有 D10 新增迁移（007）；C10 与 C07 #230 都改 `main.py` 路由注册，后合者解决一行冲突。

## K07 本地 Neo4j 环境启停脚本

| ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| K07 | DONE（PR #232 已合入 `ddbeb82`） | 复用并审查环境启停脚本 | ArvinHan（Codex） | `codex/k07-dev-scripts` / `130e6b6` | `scripts/_dev-common.sh`、`scripts/dev-up.sh`、`scripts/dev-down.sh`、`tests/tooling/test_k07.py`、`docs/integrations.md`、`docs/handoffs/codex-k07.md`、本节 | `docs/handoffs/codex-k07.md`；K07 **18 passed**，F01 假 Docker **9 passed / 3 skipped**，`./scripts/verify.sh` exit 0，`git diff --check` 通过；review P3 修复后复审无新发现。普通停止保留数据；显式销毁只在精确交互确认后执行 `compose down -v`，绑定目录保留；未运行真实 Compose。PR #232 |

- 验收：缺失 `.env` 时明确报错、不 source 或改写个人 `.env`；默认停止保留数据；销毁须明确交互确认。验证：`python3 -m pytest tests/tooling/test_k07.py -q`、`SMARTSKETCH_SKIP_DOCKER=1 python3 -m pytest tests/integration/test_f01.py -q`、`./scripts/verify.sh`。

## 2026-09-25 第六批并行（Claude）

D11、E08、C11、J03 的前置均已合入 main@`ddbeb82`（D11：C09 #220、C10 #237、D10 #234；E08：E05 #236；C11：C08 #176、C03 #216、B10、C16 #227；J03：E04 #235、E01 #182）。issue #80（D11）、#88（E08）、#132（J03）无人认领、无远端分支；#68（C11）由 539210 于 2026-09-25 16:53 自行分配并标 `status:in-progress`，远端无分支或 PR，经 ArvinHan 授权转由 Claude 执行（同 C02、C10 先例），已在 #68 留言说明。已核对在途工作：main 无未合并 PR；四项文件互不重叠。本认领提交为四个分支共用的 base，各分支只改本节中自己那一张表的状态与证据列。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| D11 | DONE（PR #239 `1df4c33`） | 实现解析阶段 worker 编排 | ArvinHan（Claude） | `claude/d11-parse-worker` / 本认领提交 | `src/backend/app/workers/__init__.py`、`src/backend/app/workers/parse_task.py`、`tests/backend/test_d11.py`、`docs/handoffs/claude-d11.md` | `test_d11.py` 42 passed；`tests/backend` 2147 passed（基线 2105 + 42）；`verify.sh` 通过；反向篡改 7 处全部检出；待决（PDF 管线版本 `pdf/1,cleanup/1,headings/1` 待确认等）见 `docs/handoffs/claude-d11.md` |

- D11 验收：已领取任务（C09 租约）经解析 → 分块 → 块身份（D09）→ 来源块持久化（D10）到 `parsing` 完成检查点（T4 `parsing → extracting`，带令牌条件）；解析失败 T9 `DOCUMENT_UNREADABLE`、取消在检查点 T8、租约丢失即停、重启重跑不产生新块；只做解析阶段，不接真实 LLM。验证：`python3 -m pytest tests/backend/test_d11.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| E08 | DONE（PR #240 已合入 `b28bf99`） | 实现名称归一和重复候选 | ArvinHan（Claude） | `claude/e08-name-normalize` / 本认领提交 | `src/backend/app/services/fusion/__init__.py`、`src/backend/app/services/fusion/normalize.py`、`tests/backend/test_e08.py`、`docs/handoffs/claude-e08.md` | `test_e08.py` 137 passed（红：`ModuleNotFoundError`）；后端全量 2242 passed（基线 2105 + 137）；NFKC/格式字符/ASCII 小写/圆括号别名·注释·公式组/空白规则；候选 `same_key`/`alias`/`containment` 只列不合并，包含限前缀、有效字符 ≥ 2、比 ≥ 3/5、不切拉丁串，「栈/栈帧」「树/二叉树」「图/图灵机」「C/C++」等反例独立；11 处反向篡改均检出、`cmp` 恢复；`./scripts/verify.sh` exit 0、`git diff --check` exit 0；待决 4 项见 `docs/handoffs/claude-e08.md` |

- E08 验收：全半角、空白、括号（含中英文括号内的别名/缩写）归一为确定性键；归一键相同才列为同键候选，名称包含只列候选、不自动合并；误合并反例（如「栈」与「栈帧」、「树」与「二叉树」）保持独立。纯函数、不调模型。验证：`python3 -m pytest tests/backend/test_e08.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| C11 | DONE（PR #241 已合入 `d93ccbb`） | 实现任务查询与 GET SSE | ArvinHan（Claude） | `claude/c11-task-events` / 本认领提交 | `src/backend/app/api/tasks.py`、`src/backend/app/services/task_events.py`、`tests/backend/test_c11.py`、`docs/handoffs/claude-c11.md`；范围扩展：`src/backend/app/main.py` 仅加路由注册 | `test_c11.py` 先收集错误（ImportError）后 46 passed；`tests/backend` 2151 passed（基线 2105）；`tests/contracts tests/tooling` 323 passed；九处反向篡改（SSE/GET 跳过授权、awaiting_review 不关流、结束事件两条、断开不释放、票据可重用、进度回退推送、去 aclose、不补快照）均被检出；`verify.sh` exit 0；`git diff --check` 通过；待决 7 项（SQL 所在层、本地响应模型/B10F-R01、可选字段、轮询间隔配置、错过 awaiting_review 的收尾、C10 `sse_event` 未消费、心跳节奏）见 `docs/handoffs/claude-c11.md` |

- C11 验收：`GET /api/v1/tasks/{tid}` 与 `GET /api/v1/tasks/{tid}/events` 先验证课程权限（C03，越权同形拒绝、不含快照）；SSE 用 C16 一次性票据；建连首条为当前快照，`awaiting_review` 与终态推送后关流，每连接恰好一条结束事件；15 秒心跳；客户端断开释放监听器（`specs/task-processing.md` §7、TASK-1/3/11/19/20）。验证：`python3 -m pytest tests/backend/test_c11.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| J03 | DONE（PR #242） | 实现多轮问题改写 | ArvinHan（Claude） | `claude/j03-query-rewrite` / 本认领提交 | `src/backend/app/services/qa/__init__.py`、`src/backend/app/services/qa/rewrite.py`、`prompts/rewrite_query.yaml`、`tests/backend/test_j03.py`、`docs/handoffs/claude-j03.md`；范围扩展：`prompts/MANIFEST.md` 仅 `rewrite_query` 一行（E01 规则要求升版本同提交更新摘要） | `test_j03.py` 94 passed（与 `test_e01.py` 合计 163 passed）；后端全量 2199 passed（基线 2105 + 94）；`verify.sh` 通过；`git diff --check` 通过；反向篡改 8 处均检出；提示词 v2（草稿）；保留轮数等暂定值与 E04 重试不感知截止时刻等待决见 `docs/handoffs/claude-j03.md` |

- J03 验收：历史按轮数/长度裁剪；只接受 `user`/`assistant` 角色，改写前剔除类标记与哨兵（`specs/grounded-qa.md` H2、QA-19）；改写出错、超时、被预算拒绝、输出为空或不合规均保留原问题；问答调用带 `request_id`、不带 `task_id`（ADR-011 修订 2）；只用 E02 fake 客户端测试。验证：`python3 -m pytest tests/backend/test_j03.py -q`。

- 合并约定：四个分支共用本认领提交。无迁移；只有 C11 改 `main.py` 路由注册。

## TD 技术债四项（2026-09-25，Claude）

来源：D11（#239）、J03（#242）、C10/C11 实现中发现的四个问题，ArvinHan 在会话中确认「按建议修改」。

| ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| TD-01 | DONE（PR #243 `c333bd1`） | PDF 解析器版本格式定稿（ADR-018 修订 1）+ E04 问答截止时间 + 改写预写失败口径 | ArvinHan（Claude） | `claude/pdf-parser-version-tech-debt-e95eaf` / `ddbeb82` | `src/backend/app/services/parsers/pdf_headings.py`、`src/backend/app/services/chunk_identity.py`、`src/backend/app/services/ai/policy.py`、`tests/backend/test_d06.py`、`tests/backend/test_d09.py`、`tests/backend/test_e04.py`、`docs/decisions.md`（ADR-018 修订 1）、`docs/architecture.md`（资料修订一行）、`docs/integrations.md`（调用记录第 1 条、问答链路截止时间）、`specs/grounded-qa.md`（链路时限、P3）、本节、`docs/handoffs/claude-td-01.md` | `docs/handoffs/claude-td-01.md` |
| TD-02 | 见第八批 | 把服务层里读任务行的 SQL 迁到 `repositories/tasks.py` | 见第八批 | C10、C11（#241）、D11（#239）全部合并后再开始 | `src/backend/app/services/task_cancel.py`（C10）、C11 与 D11 服务层中的任务读取、`src/backend/app/repositories/tasks.py` | 验收：只搬迁不改行为；服务层不再直接执行读取 `processing_tasks` 的 SQL（C10 同文件的取消 UPDATE 一并评估是否迁移）；C10/C11/D11 现有测试不改断言即通过 |

TD-01 带出的跟进项：

- **D11（#239）**：worker 删除自拼的 `PDF_PARSER_VERSION`，改为引用 `pdf_headings.CLEANED_PARSER_VERSION`（取值逐字相同，块 ID 不变）；清洗只用默认阈值。 **已完成**（#239）。
- **J03（#242）**：预写失败改用原问题已有测试覆盖；另绑定 E04 截止时间「链路截止 − 预留」并把 `CallDeadlineExceededError` 归为 `timeout`。**已完成**（#242）。
- **J07（IMPLEMENTED / 待审查验证）**：收到请求时计算截止时间，经 `ModelCallPolicy.bind(..., deadline=...)` 传给 J03～J05；把 `CallDeadlineExceededError` 映射为 `LLM_UNAVAILABLE`、`details.reason = timeout`（O9）。不要用关闭重试代替。

## 2026-09-25 第七批并行（Claude）

H13、F03、E06 的前置均已合入 main@`8985a16`（H13：C13、B15、B03、B04；F03：F02 #231、B11 #194；E06：E05 #236）。issue #173（H13）、#95（F03）、#86（E06）无人认领、无远端分支。已核对在途工作：C11 #241（`api/tasks.py`、`main.py`）、E08 #240（`services/fusion/`）待审查，与三项文件不重叠。本认领提交为三个分支共用的 base，各分支只改本节中自己那一张表的状态与证据列。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| H13 | DONE（PR #244 已合入 `0ae3cf6`） | 实现前端登录页与会话存储 | ArvinHan（Claude） | `claude/h13-login-session` / 本认领提交 | `src/frontend/src/views/LoginView.vue`、`src/frontend/src/stores/session.ts`、`src/frontend/src/api/auth.ts`、`src/frontend/src/router/index.ts`、`src/frontend/src/main.ts`、`tests/frontend/h13.test.ts`、`docs/handoffs/claude-h13.md` | `h13.test.ts` 28 passed；前端全量 81 passed；type-check、build、`verify.sh` 通过；关闭审查遗留 B03-R01′、B04-R01；`docs/handoffs/claude-h13.md` |

- H13 验收：令牌与 `LoginResponse.user` 只存 `sessionStorage`（不存 localStorage/Cookie）；登录后按 `user.role` 进首页；401、429 分别明确提示；收到 401 清会话与课程上下文并回登录页（同时关闭审查遗留 B03-R01′、B04-R01）；口令/令牌不写日志；不解析 JWT 做授权。验证：`npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/h13.test.ts`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| F03 | 撤回（改由 Codex 执行） | 建立图唯一约束和索引迁移 | ArvinHan（Claude 子代理） | `claude/f03-graph-constraints` / 本认领提交 | `src/backend/migrations/neo4j/001_constraints.cypher`、`src/backend/app/repositories/graph_migrations.py`、`tests/integration/test_f03.py`、`docs/handoffs/claude-f03.md` | Codex 已在做 F03，本认领撤回避免重复；Claude 子代理未提交的草稿留在本地 worktree `f03-graph-constraints`，未推送 |

- F03 验收：同作用域 ID 唯一；版本不同可共存；迁移可重复执行；迁移失败有回滚/修复说明。验证：`python3 -m pytest tests/integration/test_f03.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| E06 | DONE（PR #245 已合入 `59b2e5a`） | 实现补漏实体抽取 | ArvinHan（Claude 子代理） | `claude/e06-gleaning` / 本认领提交 | `src/backend/app/services/ai/gleaning.py`、`prompts/extract_entities_gleaning.yaml`、`prompts/MANIFEST.md`（一行）、`tests/backend/test_e06.py`、`docs/handoffs/claude-e06.md` | `tests/backend/test_e06.py` 61 passed；`tests/backend` 全量 2338 passed；`./scripts/verify.sh` 通过；交接 `docs/handoffs/claude-e06.md` |

- E06 验收：不开启时零调用；只加遗漏、不复制已有实体；预算和轮数有上限。验证：`python3 -m pytest tests/backend/test_e06.py -q`。

- 合并约定：三个分支共用本认领提交；无 SQLite 迁移；F03 只新增 Neo4j 迁移文件与运行器。

## 2026-09-25 第八批并行（Claude）

C12、E09、H01、C15、K14 的前置均已合入 main@`d624208`（C12：B15、C11 #241；E09：E07 #217、E08 #240；H01：B03、B04、B15、C04；C15：C03、C04、B09；K14：E01、E05 #236、E06 #245）；TD-02 的前置 C10 #237、C11 #241、D11 #239 均已合并。issue #69（C12）、#89（E09）、#113（H01）、#162（C15）、#167（K14）无人认领、无远端分支。已核对在途工作：无未合并 PR。本认领提交为六个分支共用的 base，各分支只改本节中自己那一张表的状态与证据列。

共享文件分配（避免并行冲突）：`src/frontend/src/router/index.ts`、`src/frontend/src/main.ts` 本轮只由 H01 改；`src/backend/app/main.py` 本轮只由 C15 改；`src/backend/app/repositories/tasks.py` 与 `services/task_cancel.py`、`services/task_events.py`、`workers/parse_task.py` 本轮只由 TD-02 改。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| C12 | DONE（PR #252 已合入 `f4a91db`） | 实现前端任务流客户端 | ArvinHan（Claude 子代理） | `claude/c12-task-stream` / 本认领提交 | `src/frontend/src/api/taskEvents.ts`、`tests/frontend/c12.test.ts`、`docs/handoffs/claude-c12.md` | `c12.test.ts` 38 passed；前端全量 6 files / 119 passed；type-check、build、`verify.sh` 通过；交接 `docs/handoffs/claude-c12.md` |

- C12 验收：分片帧/CRLF/心跳/重连；终态和卸载关闭；旧课程事件不污染当前课。验证：`npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/c12.test.ts`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| E09 | DONE（PR #250 已合入 `5072a48`） | 实现向量候选分层 | ArvinHan（Claude 子代理） | `claude/e09-vector-tiers` / 本认领提交 | `src/backend/app/services/fusion/candidates.py`、`tests/backend/test_e09.py`、`docs/handoffs/claude-e09.md` | `test_e09.py` 94 passed（红：`ModuleNotFoundError`；接口变更后先红 12 failed）；后端全量 2615 passed；自动合并/需裁决返回配对，保留组只返回 `kept_count`（不物化，三组计数和 = n(n-1)/2）；边界：`≥ auto_merge` 自动、`review ≤ s < auto_merge` 裁决、`< review` 保留；阈值须有限、`[0, 1]`、`review < auto_merge`，无默认值（D-08 未签收）；跨课程/跨向量空间混传整体拒绝（`VectorIsolationError`）；反向篡改均检出（首版 11 处、变更后 10 处）；`./scripts/verify.sh` exit 0、`git diff --check` exit 0；待决 3 项见 `docs/handoffs/claude-e09.md` |

- E09 验收：课程隔离；阈值顺序非法拒绝；边界等号有明确规则。验证：`python3 -m pytest tests/backend/test_e09.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| H01 | DONE（PR #251 已合入 `08ecb35`） | 实现课程首页和创建表单 | ArvinHan（Claude 子代理） | `claude/h01-courses-view` / 本认领提交 | `src/frontend/src/views/CoursesView.vue`、`src/frontend/src/composables/useCourses.ts`、`src/frontend/src/api/courses.ts`（如需）、`src/frontend/src/router/index.ts`、`src/frontend/src/main.ts`、`tests/frontend/h01.test.ts`、`docs/handoffs/claude-h01.md` | h01 31 passed；前端全量 6 files 112 passed；type-check、build、`verify.sh`、`git diff --check` 均 exit 0；交接 `docs/handoffs/claude-h01.md` |

- H01 验收：加载/空/错/禁止访问；重复点提交不重复创建；切课正确。验证：`npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/h01.test.ts`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| C15 | DONE（PR #248 已合入 `83e9038`） | 实现课程成员管理 API | ArvinHan（Claude 子代理） | `claude/c15-course-members` / 本认领提交 | `src/backend/app/api/members.py`、`src/backend/app/services/members.py`、`src/backend/app/main.py`（路由注册）、`tests/backend/test_c15.py`、`docs/handoffs/claude-c15.md` | `tests/backend/test_c15.py` 26 passed；`tests/backend` 2547 passed；`./scripts/verify.sh` 通过；交接 `docs/handoffs/claude-c15.md` |

- C15 验收：仅课程教师可改；重复添加幂等且不降级教师；跨课与非成员拒绝。验证：`python3 -m pytest tests/backend/test_c15.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| K14 | DONE（PR #247 已合入 `8ad8345`） | 整理提示词工程完整记录 | ArvinHan（Claude 子代理） | `claude/k14-prompt-record` / 本认领提交 | `docs/submission/prompt-engineering.md`、`docs/handoffs/claude-k14.md` | `docs/handoffs/claude-k14.md`；7 个提示词文件的版本、摘要与 3 个调用方版本常量逐条核对一致；`test_e01/e05/e06/j03` 复跑 288 passed（仅 fake 模型）；尚无真实模型评测（K02、K03 未完成） |

- K14 验收：记录版本、用途、输入输出和修改依据；不含密钥或真实课程资料；引用实际评测证据。验证：`git diff --check`，逐条核对验收矩阵与源文档。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| TD-02 | DONE（PR #249 已合入 `4eee6b0`） | 把服务层里读任务行的 SQL 迁到 `repositories/tasks.py` | ArvinHan（Claude 子代理） | `claude/td02-task-repo` / 本认领提交 | `src/backend/app/repositories/tasks.py`、`src/backend/app/services/task_cancel.py`、`src/backend/app/services/task_events.py`、`src/backend/app/workers/parse_task.py`、`tests/backend/test_td02.py`、`docs/handoffs/claude-td-02.md` | `test_td02.py` 14 passed；C10/C11/D11 搬迁前后均 121 passed（断言未改）；后端全量 2535 passed；`verify.sh` 通过；交接 `docs/handoffs/claude-td-02.md` |

- TD-02 验收：只搬迁不改行为；服务层不再直接执行读取 `processing_tasks` 的 SQL；C10/C11/D11 现有测试不改断言即通过。

## 2026-09-26 图谱构建主线：E10 认领（Codex）

| 原子 ID | 状态 | 负责人 | 分支 / base | 范围与文件所有权 | 验收与证据 |
| --- | --- | --- | --- | --- | --- |
| E10 | DONE（PR #253 已合入 `cc53c8d`） | Codex | `codex/e10-fusion-design` / `main@5072a48` | `src/backend/app/services/fusion/judge.py`、`prompts/judge_duplicate.yaml`、`prompts/summarize_definition.yaml`、`prompts/MANIFEST.md`、`tests/backend/test_e10.py`、`specs/course-knowledge-graph.md`、`specs/task-processing.md`、`docs/decisions.md`、`docs/handoffs/codex-e10.md`、设计与计划文件 | E10+邻接测试 468 passed；后端全量 2681 passed、1 个既有 warning（本机回环测试以获准运行方式复跑）；`./scripts/verify.sh` 通过；`git diff --check` 通过。独立审查指出的缓存键与提示词标签问题均已修正。 |

- E10 审查修正（Claude，2026-09-26）：归并提示词带两侧名称、`FusionJudge` 可选 `timeout_seconds`、ADR-017 空行与计划文件 skill 引用；`test_e10.py` 28 passed，后端全量 2683 passed，`verify.sh` 通过；交接 `docs/handoffs/claude-e10-review-fixes.md`。
- **输入**：同课候选对、两侧名称/定义与可定位证据；**输出**：带理由、来源引用、模型/提示词元数据的归并提案或独立待审核结果；**依赖**：E09、E04、E01、E05。**风险**：D-08 阈值未签收；E08/E09 合流与稳定候选 ID 由 E12 定；模型引用能验证来源存在，不能自动证明归并语义正确。后两项及缓存失效规则见 E10 设计规格。

## 2026-09-26 E10 之后第一批：E11、H02、H12 并行（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| E11 | DONE（PR #255 已合入 `6742f6a`） | 实现关系两阶段抽取 | ArvinHan（Claude） | `claude/project-thread-sp1d3a` / `main@5072a48`，已合入含 E10 的 `main@cc53c8d` | `src/backend/app/services/ai/relations.py`、`prompts/extract_relations.yaml`、`tests/backend/test_e11.py`；扩围 `prompts/MANIFEST.md` 一行、`docs/submission/prompt-engineering.md`（K14 交接要求同步） | `test_e11.py` 47 passed；E01/E10/E11 144 passed；后端全量 2702 passed（合入 E10 前）；9 处反向篡改均被检出；`docs/handoffs/claude-e11.md` |
| H02 | DONE（PR #255 已合入 `6742f6a`） | 实现资料上传和进度页面 | ArvinHan（Claude 子代理） | 同上 | `src/frontend/src/views/MaterialsView.vue`、`src/frontend/src/composables/useMaterials.ts`、`src/frontend/src/api/materials.ts`、`tests/frontend/h02.test.ts`；扩围 `router/index.ts`、`CoursesView.vue`、`main.ts`（路由与入口） | `h02.test.ts` 53 passed；7 处反向篡改均被检出；`docs/handoffs/claude-h02.md` |
| H12 | DONE（PR #255 已合入 `6742f6a`） | 实现课程成员管理页面 | ArvinHan（Claude 子代理） | 同上 | `src/frontend/src/views/MembersView.vue`、`src/frontend/src/api/members.ts`、`src/frontend/src/composables/useMembers.ts`、`tests/frontend/h12.test.ts`；扩围同 H02 | `h12.test.ts` 33 passed；5 处反向篡改均被检出；`docs/handoffs/claude-h12.md` |

- 依赖：E11 ← E10（PR #253 已合入）、E05；H02 ← H01、C07、C12；H12 ← C15、B15、H01，均在 main。
- 三项合并后验证：前端 `type-check` exit 0、全量 9 files 236 passed、`build` exit 0；`./scripts/verify.sh` exit 0（需 PATH 含 pytest 与 `openapi-typescript@7.4.4`）；`git diff --check` exit 0。H02/H12 都改了 `router/index.ts`、`CoursesView.vue`、`main.ts`，合并时两段各自保留。
- E11 待决（详见交接）：`PREREQUISITE_CUES` 先修表述清单为本任务暂定；小节范围与实体表上限交 E12；关系抽取缓存键未定。
- H02 待决：~~`Document` 无 `task_id`~~、~~无删除资料端点~~ 已由 ADR-021 解决（见下行）；~~前端 50 MiB 上限写死~~ 已由 ADR-022 解决（见下表）。
- E11 `PREREQUISITE_CUES` 暂定清单：ArvinHan 2026-09-26 确认接受。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| ADR-021 | DONE（PR #255 已合入 `6742f6a`） | `Document.task_id` 与删除未产生贡献的资料（`deleteDocument`） | ArvinHan（Claude） | 同上 | `docs/decisions.md`（ADR-021）、`specs/task-processing.md`、`specs/identity-access.md`、`src/contracts/`（真源、错误码、生成物）、后端 `materials` 路由/服务/仓储/schema、`tests/backend/test_adr021.py`、`tests/backend/test_c07.py`（键集合）、前端 `materials.ts`/`useMaterials.ts`/`MaterialsView.vue`/`http.ts`/`taskEvents.ts`、`tests/frontend/h02.test.ts` | 后端红 25 failed → `test_adr021.py` 27 passed；后端全量 2757 passed；契约+工具 323 passed；前端红 11 failed → 全量 254 passed；`gen-contracts.sh --check`、`verify.sh`、`git diff --check` exit 0；`docs/handoffs/claude-adr021.md` |
| ADR-022 | DONE（PR #255 已合入 `6742f6a`） | 上传上限经 `getUploadPolicy` 下发，前端不再写死 50 MiB | ArvinHan（Claude） | 同上 | `docs/decisions.md`（ADR-022）、`specs/identity-access.md`、`docs/integrations.md`、`src/contracts/`（真源、生成物）、后端 `api/materials.py`/`schemas/materials.py`/`main.py`、`tests/backend/test_adr022.py`、前端 `materials.ts`/`useMaterials.ts`/`MaterialsView.vue`、`tests/frontend/h02.test.ts` | 后端红 7 failed → `test_adr022.py` 7 passed；后端全量 2764 passed；前端红 7 failed → `h02.test.ts` 79 passed、全量 262 passed；4 处反向篡改均被检出；`type-check`、`build`、`gen-contracts.sh --check`、`verify.sh`、`git diff --check` exit 0；`docs/handoffs/claude-adr022.md` |

## 2026-09-26 PR #255 合并后：K01、K02 并行（Claude）

依赖：K01 ← A07、E11、J06、I04；K02 ← K01、E11。E11 已随 PR #255 合入（`6742f6a`），A07、I04 已在 main；**J06 未完成**，所以 K01 只交付实体与关系部分，问答口径在 README 中标「待 J06」。D-01（基准章节）与 D-02（模型供应商）未签收、付费调用需另行确认，真实模型判定未执行。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| K01 | DONE（部分：问答口径待 J06；D-01 已定为本章，ADR-026） | 建立自编标注集及评测口径 | ArvinHan（Claude 子代理） | `claude/project-thread-sp1d3a` / `main@6742f6a` | `evaluation/README.md`、`evaluation/fixtures/synthetic.json`、`docs/handoffs/claude-k01.md` | 自编「数据结构 第3章 栈与队列」3141 字，金标 45 个实体（五类齐全）、40 条关系（四类齐全），证据全部为原文子串、前置关系无环；夹具校验脚本 ALL PASS，4 份篡改副本均被拒；`docs/handoffs/claude-k01.md` |
| K02 | DONE（真实模型已实测：三项硬指标达标，简化融合下的初步结论） | 实现抽取和融合离线评测 | ArvinHan（Claude 子代理 + 联调） | 同上 | `evaluation/evaluate_extraction.py`、`tests/backend/test_k02.py`、`evaluation/reports/extraction-accuracy.md`、`docs/handoffs/claude-k02.md` | 桩实现 46 failed → 46 passed；联调按 README 对齐 4 处，先 5 failed → `test_k02.py` 52 passed（含 K01 夹具用例）；假模型自检在 K01 标注集上跑通，两次输出 sha256 一致，数值全部过线仍判「不可用于判定（假模型）」；`docs/handoffs/claude-k02.md` |

- 本机真实模型运行脚本 `evaluation/run_live_extraction.py`（`tests/backend/test_k02_run.py` 先 12 failed → 13 passed；假模型端到端：16 块、简化融合后 18 个实体、12 条关系，`score` exit 0 且判「不可用于判定（假模型）」；交接 `docs/handoffs/claude-k02-run.md`）。只做同名合并的简化融合，结果是初步数字，最终判定仍需 E12。
- 联调对齐（以 `evaluation/README.md` 为准）：F1 在 precision 或 recall 为 null 时为 null；各指标只统计 `source = "ai"`；按 `judgments.seed` 重算的抽中项有缺判时写「判定不完整」，准确率只统计抽中项；实体数 < 20 直接「未达标」。
- 待决：
  1. ~~D-01~~：已定为本次自编的「栈与队列」一章，`is_final_benchmark` 改为 `true`（ADR-026）。
  2. ~~**D-02**~~：D-02a、D-02d 与付费调用都已确认（ADR-027、ADR-028）。真实模型已在本机跑通并人工全量判定（2026-09-26，`k02-live-20260926T084922Z`，DeepSeek `deepseek-flash`）：AI 实体 74 个、实体准确率 74/74、关系准确率 61/63，结论「达标」，详见 `evaluation/reports/extraction-accuracy.md` 与 `docs/handoffs/claude-k02-judge.md`。
  3. **J06** 完成后补问答夹具（K01 问答部分）并做 K03。
  4. **E11 先修表述清单**：金标 `g-r03`（证据「基于栈的后进先出特性」）不含清单中的表述，E11 会按 `prerequisite_without_cue` 丢弃；是否把「基于」加入清单待实测召回后决定。审查同时指出「基础」「才能」偏宽。
  5. **E12/F13 须对同一小节产出的反向 `PREREQUISITE` 候选做环检测**（PR #255 审查意见，E11 不去重二元环）。
  6. **完整融合后重跑验收 7**：本次是简化融合（仅同名去重），main 上 E12/F13 的 `merging` 也还是直通（ADR-029）。E08～E10 融合接入后，把本章处理到 `awaiting_review`、导出草稿，按报告第 3 节重新抽样判定。
  7. **抽取改进（报告第 5 节）**：小节「3.3.5 栈与队列的比较」关系抽取因 4096 token 输出上限截断；21 条未命中金标关系中 12 条跨小节；`CONTAINS` 被用于「相关」关系（判错 2 条）。
- 看板同步：本次把已合入 main 却仍标「待 PR 审查/合并」或「IN REVIEW」的 24 行改为「DONE（PR #N 已合入 `sha`）」：F02、F03、K07、D10、E04、E05、C10、I04、E08、C11、H13、E06、C12、E09、H01、C15、K14、TD-02、E10、E11、H02、H12、ADR-021、ADR-022。

## 2026-09-26 E11 之后主线：E12、F04、F06、F13（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| E12 | DONE（PR #256 已合入 `fa00164`） | 实现抽取阶段编排和检查点 | ArvinHan（Claude） | `claude/project-thread-sqwla4` / 起于 PR #255 头 `52db31c`，#255 合并后已合入 `main@6742f6a` | `src/backend/app/workers/extract_task.py`、`tests/backend/test_e12.py`；扩围 `src/backend/migrations/008_extraction_checkpoints.sql`、`src/backend/app/repositories/extraction_checkpoints.py`、`docs/decisions.md`（ADR-023）、`specs/task-processing.md`（§8.4 一段） | 红灯：收集 `ImportError`；`test_e12.py` 37 passed（连跑 5 次稳定）；后端全量 2801 passed；8 处反向篡改均检出；`verify.sh` exit 0；`docs/handoffs/claude-e12.md` |
| F04 | DONE（PR #256 已合入 `fa00164`） | 实现草稿节点和来源批写 | ArvinHan（Claude） | 同上 | `src/backend/app/repositories/graph_nodes.py`、`tests/integration/test_f04.py`；扩围 `docs/decisions.md`（ADR-024）、`docs/architecture.md`（来源关联一句） | 红灯：收集 `ImportError`；`test_f04.py` 21 passed（其中 7 个连真实 Neo4j 5.26）；7 处反向篡改均检出；`docs/handoffs/claude-f04.md` |
| F06 | DONE（PR #256 已合入 `fa00164`） | 实现关系事务写入与并发防环 | ArvinHan（Claude） | 同上 | `src/backend/app/repositories/graph_relations.py`、`src/backend/app/services/graph/relations.py`、`tests/integration/test_f06.py`；扩围 `src/backend/app/repositories/neo4j.py`（`write_transaction`）、`src/backend/migrations/neo4j/001_constraints.cypher` 与 `graph_migrations.py`（守卫约束）、`docs/decisions.md`（ADR-025）、`docs/architecture.md` | `test_f06.py` 28 passed（其中 12 个连真实 Neo4j 5.26，连跑 5 次稳定）；8 处反向篡改均检出；后端全量 2801 passed；`verify.sh` exit 0；`docs/handoffs/claude-f06.md` |
| F13 | DONE（PR #256 已合入 `fa00164`） | 完成图持久化 worker 阶段 | ArvinHan（Claude） | 同上 | `src/backend/app/workers/persist_graph.py`、`tests/integration/test_f13.py`；扩围 `src/backend/migrations/009_course_locks.sql`、`src/backend/app/repositories/course_locks.py`、`src/backend/app/services/graph/downgrade.py`、`graph_relations.py`（降级/撤销语句）、`graph_nodes.py`（事务内写入）、`services/graph/relations.py`（事务内写入）、`task_leases.py`（persisting 失败置 `cleanup_pending`）、`tasks.py`（读 V）、`docs/decisions.md`（ADR-029）、`specs/task-processing.md`（§8.4 一段） | `test_f13.py` 27 passed（其中 10 个连真实 Neo4j 5.26，连跑 5 次稳定）；9 处反向篡改均检出；后端全量 2801 passed；`verify.sh` exit 0；`docs/handoffs/claude-f13.md` |

- 依赖：E12 ← D11（#239）、E04（#235）、E11（#255，已合并）；F04 ← F03（#246）、E12。
- 验收：每块失败只重试该块（L2）；在途块数不超过 `LLM_MAX_CONCURRENCY`；取消在块/小节边界生效，在途结果不写检查点（TASK-4）；接管后已结束的块和小节不再调用模型、来源不重复（LEASE-2）；阈值内继续、恰等于阈值继续、超阈值提前判定（TASK-9/10/13）；熔断打开不记失败块并退避释放（LEASE-6）。
- 已决：小节关系抽取失败不计入失败块阈值（ArvinHan 2026-09-26，ADR-023 决定 4）。
- E12 待决（详见交接）：任务快照与 SSE 尚未带 `chunks_done`/`chunks_failed`/`failed_chunks`（C11 接列）；模型调用结果缓存未实现，块中途崩溃会重新计费；小节实体表与提示词长度无上限；检查点保留期清理（§8.6）未实现；生产装配（`ExtractionToolkit` 的模型、输出上限、补漏开关）未接入启动入口；`merging` 阶段 worker 尚无任务承接。

- F04 已决：加锁知识点完全不动，只记为跳过（ArvinHan 2026-09-26，ADR-024 决定 4）。F04 待决：节点状态与低置信度阈值由调用方给（D-08）；§8.4 的「撤销旧贡献 + 写入」同一事务由 F13 组合。
- F06 验收：两个连接并发写 A→B / B→A 恰有一方 `CYCLE_DETECTED`；四个连接并发写成环的四条边恰有一方冲突；读图、环检测与提交在同一写事务里并由课程守卫节点串行（ADR-025）。F06 待决：SQLite 课程写锁 `course_locks` 与 `draft_revision+1` 仍未落地（V4，归 API/发布任务）；ADR-009 自动降级与「撤销旧贡献 + 写入」同一事务由 F13 组合。
- F13 已决（ArvinHan 2026-09-26，ADR-029）：`merging` 先用直通版（不做跨资料融合）；D-08 签收前自动写入的节点和关系状态一律 `draft`。F13 同时补上迁移 009 的 `course_locks` 与 `t6_seq`，F06 待决中的课程写锁表因此已有；`draft_revision+1` 仍归教师编辑（F08）。F13 待决：融合编排（E08～E10 接入 `merging`）无任务承接；D-08 签收后需重算状态；等锁超时消耗一次尝试。

## 2026-09-26 F07 图谱读取（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| F07 | DONE（PR #258 已合入 `608be90`） | 实现草稿图读取与详情服务 | ArvinHan（Claude） | `claude/project-thread-sqwla4` / `main@fa00164`（#256 合并后重开） | `src/backend/app/services/graph/read.py`、`src/backend/app/api/graph.py`、`tests/backend/test_f07.py`；扩围 `src/backend/app/repositories/graph_read.py`（读取 Cypher）、`src/backend/app/schemas/contracts.py`（导出图谱模型）、`src/backend/app/main.py`（注册路由）、`tests/integration/test_f07_live.py`、`docs/decisions.md`（ADR-030） | `test_f07.py` 20 passed；`test_f07_live.py` 4 passed（真实 Neo4j 5.26）；10 处反向篡改均检出；后端全量 2821 passed；`verify.sh` exit 0；`docs/handoffs/claude-f07.md` |

- 验收：教师不带 `version` 读草稿（按 V 过滤），学生只读当前发布版本；空图 200、未发布 404 `GRAPH_NOT_PUBLISHED`、版本不符 404 `NOT_FOUND`；每条来源都有 `page` 或 `section_path`，知识点来源按证据区间定位到解析块并带原文（ADR-030）。
- F07 待决：历史版本读取等 G02 版本表；人工添加且无来源的知识点详情会 500，需 F08 保证新建带来源或改契约；`getKnowledgePoint` 每次整图计算层级。

## 2026-09-26 G 组：发布版本（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| G01 | DONE（PR #259 已合入 `b92c65b`；#106 已关闭） | 实现快照序列化和摘要 | ArvinHan（Claude） | `claude/project-thread-sqwla4` / `main@608be90`（#258 合并后重开） | `src/backend/app/services/versions/snapshot.py`、`tests/backend/test_g01.py`；扩围 `src/backend/app/services/versions/__init__.py`、`docs/decisions.md`（ADR-031） | `test_g01.py` 49 passed；12 处反向篡改均检出；后端全量 2870 passed；`verify.sh` exit 0；`docs/handoffs/claude-g01.md` |
| G02 | DONE（PR #259 已合入 `b92c65b`；#107 已关闭） | 实现版本元数据与发布操作记录 | ArvinHan（Claude） | 同上 | `src/backend/app/repositories/versions.py`、`src/backend/migrations/010_versions.sql`、`tests/backend/test_g02.py`；扩围 `tests/integration/test_f13.py`（009 回滚用例先回滚更新的迁移）、`docs/decisions.md`（ADR-032） | `test_g02.py` 22 passed；10 处反向篡改均检出；后端全量 2892 passed；集成（真实 Neo4j）103 passed、4 skipped；`verify.sh` exit 0；`docs/handoffs/claude-g02.md` |
| G03 | DONE（PR #259 已合入 `b92c65b`；#108 已关闭） | 实现版本图与向量构建 | ArvinHan（Claude） | 同上 | `src/backend/app/services/versions/materialize.py`、`tests/integration/test_g03.py`；扩围 `src/backend/app/services/graph/read.py` 与 `src/backend/app/repositories/graph_read.py`（读版本副本、不回传向量）、`tests/backend/test_f07.py`（1 个用例）、`docs/decisions.md`（ADR-033） | `test_g03.py` 12 passed（其中 11 个连真实 Neo4j 5.26）；8 处反向篡改 7 处检出，第 8 处（删草稿）由 F02 作用域校验兜住；后端全量 2893 passed；集成 115 passed、4 skipped；`verify.sh` exit 0；`docs/handoffs/claude-g03.md` |
| G04 | DONE（PR #261 已合入 `ba761dd`；#109 已关闭） | 实现原子发布指针切换 | ArvinHan（Claude） | `claude/project-thread-sqwla4` / `main@ebb0f42` | `src/backend/app/services/versions/publish.py`、`tests/integration/test_g04.py`；扩围 `src/backend/app/repositories/versions.py`（P4 读取与 T7）、`src/backend/app/repositories/course_locks.py`（`current_holder`）、`src/backend/app/repositories/graph_read.py`（投影加 `merged_from`）、`tests/backend/test_g04_sqlite.py`、`docs/decisions.md`（ADR-034） | `test_g04.py` 19 passed（真实 Neo4j 5.26）；`test_g04_sqlite.py` 3 passed；9 处反向篡改 8 处检出，1 处（C1 提交后仍删副本）补用例后检出；后端全量 2962 passed；集成 134 passed、4 skipped；`verify.sh` exit 0；`docs/handoffs/claude-g04.md` |
| G05 | DONE（待 PR 审查/合并） | 实现发布失败补偿与恢复 | ArvinHan（Claude） | `claude/project-thread-sqwla4` / `main@95d5c9a` | `src/backend/app/services/versions/reconcile.py`、`tests/integration/test_g05.py`；扩围 `src/backend/app/services/versions/publish.py`（C1 改走 reconcile）、`src/backend/app/repositories/versions.py`（过期尝试、课程列表）、`src/backend/app/repositories/graph_read.py`（`stored_version_ids`）、`tests/integration/test_g04.py`（1 行打桩目标）、`src/backend/app/services/versions/snapshot.py`、`src/backend/app/services/versions/materialize.py`、`tests/backend/test_g01.py`（审查修复）、`tests/backend/test_g05_sqlite.py`、`docs/decisions.md`（ADR-036） | `test_g05.py` 14 passed（真实 Neo4j 5.26）；`test_g05_sqlite.py` 2 passed；9 处反向篡改均检出；后端全量 2965 passed；集成 148 passed、4 skipped；`verify.sh` exit 0；`docs/handoffs/claude-g05.md` |
| G06 | DONE（待 PR 审查/合并） | 实现回滚和版本列表 API | ArvinHan（Claude） | `claude/project-thread-sqwla4` / `main@a44c680`（与 G05 同一 PR #264） | `src/backend/app/api/versions.py`、`src/backend/app/services/versions/rollback.py`、`tests/backend/test_g06.py`；扩围 `POST /publish` 路由（ArvinHan 2026-09-26 同意）、`src/backend/app/services/versions/materialize.py`（`copy_version`）、`src/backend/app/main.py`、`src/backend/app/schemas/contracts.py`、`tests/integration/test_g06.py`、`docs/decisions.md`（ADR-041） | `test_g06.py`（后端）15 passed；`tests/integration/test_g06.py` 9 passed（真实 Neo4j 5.26）；7 处反向篡改均检出；后端全量 2980 passed；集成 157 passed、4 skipped；`verify.sh` exit 0；`docs/handoffs/claude-g06.md` |

- 验收：规范化字节键序与数组顺序稳定（PUB-10，乱序构造摘要相同）；端点缺失、来源无效、成环、空图、谱系违规逐条拒绝并符合契约 `PublishBlockedDetails`；`load_snapshot` 读回与原快照逐字节相同、不丢任何属性；PUB-8 排除计数、PUB-9、PUB-11 均有用例。
- G01 待决：从 Neo4j/SQLite 读出可见草稿与修订的装载归 G04（P4～P7）；快照章节带 `parent_id`，而 Neo4j 章节与契约 `Chapter` 尚无此字段，章节层级落地时需同步（ADR-031）。
- G02 验收：同一尝试（幂等键 `version_id`）至多成为一个版本；版本号按课程连续、失败不占号，`(course_id, version)` 唯一；失败行带原因永久可查且不进版本列表；已提交版本不可删改。G02 待决：清扫过期尝试归 G05；租约时长由调用方传入（G04 读 `PUBLISH_LEASE_SECONDS`）。
- G03 验收：物化只写 `(course_id, 新 version_id)`，旧版本副本与发布指针不变，学生照读旧版；向量空间或维度不符、缺向量在连库前失败，缺来源块整体回滚；重试同一版本先删后建、不重复；P9 读回复算摘要一致。G03 已决：已发布知识点对外状态恒为 `approved`、来源类别恒为 `manual`（ArvinHan 2026-09-26，ADR-033 第 5 条）。G03 待决：已发布详情的来源没有原文片段。
- G04 验收：先按 V3 校验（成环、来源无效、空图）再切指针；P7～P11 任一失败、提交指针被移动、写锁超时都保留旧指针且不留副本；版本号无空洞；同课程并发发布或发布与回滚并发返回 `PUBLISH_IN_PROGRESS`；内容未变走幂等路径不占号不写 Neo4j；T7 只完成水位以内的任务，锁释放后的编辑不进本次快照（PUB-1/2/4/5/6/12/21/22/23/35）。G04 待决：`POST /publish` 路由未分配任务（建议并入 G06 的 `api/versions.py`）；G04 依赖 F12 仅因谱系，发布不写审计日志（ADR-034 第 7 条）；过期尝试的清扫归 G05。
- G05 验收：P7～P11 各阶段注入失败（含 SQLite 写失败、Neo4j 删除失败）都保留旧指针，副本或被删除、或置 `cleanup_pending` 且清扫后删除；P8 之后崩溃在租约到期后由清扫执行 C1，之后可再发布；提交与清扫以同一行的条件更新互斥；清扫只删 `failed` 尝试的副本，从不删已提交版本与租约内尝试；补偿与清扫可重复执行（PUB-18/19/20）。G05 另修独立审查（2026-09-26）四项：发布前回收本课过期尝试；清扫已判失败后写入的副本就地删除；悬空章节引用按未归章发布；副本删除/列出按标签匹配（ADR-036 第 6～9 条）。G05 待决：`sweep` 尚未接入 worker 周期回收（A06 §8.6 无调度实现）；孤儿副本与缺副本只告警，处理归 K10；同一审查的其余项（无来源人工节点详情 500，归 F08/F07 口径；worker 清理重试空等课程锁；任务重跑覆盖教师已审核状态）未在本 PR 处理。
- G06 验收：回滚以历史版本内容前滚为新版本（`kind = rollback`、`source_version`），向量随副本复制不调用模型；回滚到当前版本或摘要相同的旧版本幂等；不存在、失败或他课版本 404 且无写入；源副本缺失或向量空间不符时失败、指针不变；回滚不改草稿、不执行 T7，R6 等锁超时仍成功（状态 `revising`，随后发布走幂等纠正）；版本列表按版本号降序、不含失败尝试；三个接口仅限本课程教师（PUB-3/7/15/16/25/26）。G06 待决：学生读取的统一版本解析归 G07。

## 2026-09-26 H03 图谱适配（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| H03 | DONE（PR #262 已合入 `95d5c9a`；#115 已关闭） | 实现契约到 G6 数据适配 | ArvinHan（Claude） | `claude/project-thread-m4mk7n` / `main@ebb0f42` | `src/frontend/src/graph/adapter.ts`、`tests/frontend/h03.test.ts` | `h03.test.ts` 22 passed；11 处反向篡改均检出；前端全量 285 passed；type-check、build、`verify.sh` exit 0；`docs/handoffs/claude-h03.md` |

- 验收：四类边样式两两可区分且带中文图例名；`source/target` 取 `from_id/to_id`，仅 `RELATED_TO` 无箭头；缺端点、外课、重复 ID 的元素不进画布并逐条报告；空图得空数组；元素 ID 为 `kp:`/`rel:` 前缀且按码点排序，输入乱序输出逐字节相同；深冻结输入照常转换，输出不引用输入对象。
- H03 待决：边颜色为占位方案未经设计签收；`rejected`/`low_confidence` 的样式与过滤、`issues` 是否提示给教师，留给 H04/H05。

## 2026-09-26 可开工清单与 issue 同步（Claude，基线 `main@95d5c9a`）

依据 `docs/atomic-tasks.json` 的 `depends_on` 与 GitHub issue 状态计算：以下任务前置全部完成且无人认领。进行中不列入：G05→G06（主线线程，#110/#111 标 `status:in-progress`）、F08（草稿 PR #263，#100 标 `status:in-review`）。

| 原子 ID | 组 | 任务 | 前置（均已完成） | Issue | 备注 |
| --- | --- | --- | --- | --- | --- |
| G07 | 发布版本和补偿 | 实现统一发布版本解析器 | G04 | #112 | 解锁 H11、I01、I05、J01、J02，关键路径优先 |
| H04 | 教师与学生图谱界面 | 实现 G6 生命周期组件 | H03 | #116 | 解锁 H05、H06、H08 |
| F14 | 图存储与教师编辑 | 实现离线重新向量化命令 | E07、D10、F03、G04 | #164 | 与 G05 同属版本/向量区域，开工前核对文件锁 |
| K08 | 评测部署与交付 | 实现前后端与 worker 容器配置 | K07、B05、B01、F13 | #147 | 解锁 K10、K12 |
| K13 | 评测部署与交付 | 实现抽取消融实验 | K02、E06 | #166 | 需真实模型调用，开工前须用户确认预算 |

- 等 F08 合并后可开工：F09、F10（再到 F11、F12）。等 G07：I01、J01、J02。等 H04：H05、H06、H08。
- Issue 同步：关闭已合并任务 #92（E12）、#96（F04）、#98（F06）、#105（F13）、#99（F07）、#106～#109（G01～G04）、#115（H03）、#140（K01，问答口径随 K03）、#141（K02），均附 PR 评论并标 `status:done`；141 个原子任务各有一个 issue，无缺漏。

## 2026-09-26 F08 教师节点编辑与人工编辑锁（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| F08 | DONE（待 PR 审查/合并） | 实现教师节点编辑与手改锁 | ArvinHan（Claude） | `claude/project-thread-z0m8yg` / `main@ebb0f42` | `src/backend/app/services/graph/edit_node.py`、`src/backend/app/api/graph_nodes.py`、`tests/backend/test_f08.py`；扩围 `src/backend/app/repositories/graph_edit.py`（Cypher 与 SQLite 查询）、`src/backend/app/main.py` 与 `src/backend/app/schemas/contracts.py`（各一处注册）、`tests/integration/test_f08.py`、契约（`api.v1.yaml`、`errors.v1.md`、生成物）、`src/frontend/src/api/http.ts` 与 `taskEvents.ts`（错误码副本）、`docs/decisions.md`（ADR-035）、`docs/architecture.md`（错误码表）、`specs/teacher-review-publish.md`（待细化四条） | `test_f08.py` 62 passed（实现前 61 failed）；`tests/integration/test_f08.py` 8 passed（真实 Neo4j 5.26）；后端全量 3024 passed；集成全量 142 passed / 4 skipped；前端 type-check 通过、285 passed（合入 main 后复跑）；`verify.sh` exit 0；`docs/handoffs/claude-f08.md` |

- 验收：后写者 `expected_revision` 过期 → 409 `REVISION_CONFLICT` 带当前内容，不覆盖；教师修改（含只改状态）置 `locked = true`；解锁只能经单独的 `unlockKnowledgePoint`，修改接口带 `locked` 字段 → 422；F04 自动写入跳过加锁节点，解锁后恢复更新；新建知识点必须带至少一条本课程、已提交修订的来源（ADR-035）。
- F08 已决（ArvinHan 2026-09-26，ADR-035）：人工新建节点 `status = approved`、置信度 1.0；任何课程教师均可解锁。
- F08 待决：前端尚无为新建知识点选择来源块的接口与交互（无按资料列块的 API）；审计日志归 F12；删除与合并归 F09/F10。

## 2026-09-26 G07 发布版本解析器（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| G07 | DONE（待 PR 审查/合并） | 实现统一发布版本解析器 | ArvinHan（Claude） | `claude/project-thread-8wzxew` / `main@95d5c9a` | `src/backend/app/services/versions/resolver.py`、`tests/backend/test_g07.py`；扩围 `docs/decisions.md`（ADR-037） | `test_g07.py` 32 passed；13 处反向篡改 10 处直接检出，补 1 个用例后第 11 处检出，余 2 处为多重防护中的冗余分支（见交接）；后端全量 2994 passed；`verify.sh` exit 0；`docs/handoffs/claude-g07.md` |

- 验收：从未发布返回 404 `GRAPH_NOT_PUBLISHED`（带 `version` 亦然，进行中或失败的尝试不算发布）；解析结果不可变，请求内提交 v2 不混读，下一次解析读到 v2（PUB-13）；`?version=1` 在指针指向 v2 时可读，不存在、他课、非正数版本号 404 `NOT_FOUND`（PUB-14 解析部分）；回滚得到新版本号与源版本修订；同一结果提供图谱作用域、`graph_version` 与问答修订过滤；指针或已提交版本损坏报 `INTERNAL_ERROR`，不回退、不缓存。
- G07 待决：F07 `resolve_target`、推荐与问答服务尚未接入解析器（F07 改用后即可读历史版本，完成 PUB-14）；修订列表缓存上限 256 为占位值。

## 2026-09-26 H04 G6 画布生命周期（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| H04 | DONE（待 PR 审查/合并） | 实现 G6 生命周期组件 | ArvinHan（Claude） | `claude/project-thread-3eixq2` / `main@95d5c9a` | `src/frontend/src/graph/lifecycle.ts`、`src/frontend/src/components/GraphCanvas.vue`、`tests/frontend/h04.test.ts`；另含 `src/frontend/package.json`/`package-lock.json`（新增 `@antv/g6`） | `h04.test.ts` 27 passed；16 处反向篡改均检出；前端全量 312 passed；type-check、build、`verify.sh` exit 0；Chromium 冒烟通过；`docs/handoffs/claude-h04.md`；ADR-040 |

- 验收：挂载按容器尺寸建图，尺寸为 0 时推迟；更新走 `setData` + `render`，渲染中连续更新只画最后一次；resize 下一帧合并，`setSize` 后适应视口，隐藏（尺寸 0）与未变不动；销毁后图、观察器、帧、window 监听归零，迟到的建图与渲染不生效；路由来回切换 20 次无泄漏；节点点击回传知识点 ID；加载、空图、失败（可重试）状态与画布无障碍标签。
- H04 待决：H03 的边颜色仍为占位；`rejected`/`low_confidence` 的样式与过滤仍留给 H05；画布本身不可键盘操作，键盘可达由 H11 卡片视图承担。

## 2026-09-26 F14 离线重新向量化（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| F14 | DONE（待 PR 审查/合并） | 实现离线重新向量化命令 | ArvinHan（Claude） | `claude/project-thread-200r6n` / `main@95d5c9a` | `scripts/reembed.py`、`tests/integration/test_f14.py`；扩围 `docs/decisions.md`（ADR-038）、`specs/teacher-review-publish.md`（V12 启动门禁一句）、`src/backend/README.md`（一句） | 红灯：收集错误（`scripts/reembed.py` 不存在）；`test_f14.py` 32 passed（其中 2 个连真实 Neo4j 5.26）；9 处反向篡改均检出；后端全量 2962 passed；集成 165 passed、5 skipped；`verify.sh` exit 0；`docs/handoffs/claude-f14.md` |

- 验收：有未过期租约、课程写锁或任何未完成的发布/回滚尝试即拒绝，不备份、不调模型、不动 Neo4j；按 Neo4j 存量枚举全部文本块、全部草稿知识点（不论状态）与全部已提交副本；模型失败、存量在运行中变化、缺向量或维度不符、已提交副本数不等于 `node_count`、块无原文、记录空间被他人改动时都保留旧空间（旧属性与索引完好）；切换后运行时写入只接受新空间；第 6 步失败退出码 3，重跑完成清理；命令打印回滚步骤。
- F14 与 G05/G06 文件不重叠。F14 待决：K10 Neo4j 备份脚本未实现，暂以 `--neo4j-backup-confirmed` 由操作者确认；worker 入口尚未调用启动门禁（C09 待办，非本任务）。

## 2026-09-26 K13 抽取消融（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| K13 | DONE（真实模型三组已跑，自动比对；人工判定未做） | 实现抽取消融实验 | ArvinHan（Claude） | `claude/project-thread-yswyz2` / `main@a44c680` | `evaluation/ablation.py`、`evaluation/reports/ablation.md`、`tests/backend/test_k13.py`；扩围 `evaluation/prompts/extract_joint.yaml`、`evaluation/README.md`（目录）、`docs/decisions.md`（ADR-045）、`docs/integrations.md`（D-02d 备注） | `test_k13.py` 22 passed；5 处反向篡改均检出；K02/E01 回归通过；`docs/handoffs/claude-k13.md`；#166 |

- 验收：同一标注集、同一模型、同一计分口径记录三组结果、成本与版本；空样本标「空样本」，失败组与未运行组保留行并写明原因；fake 结果一律标「假模型」且不给达标判定。
- 实测（ArvinHan 本机，2026-09-26）：三组全部 ok，合计计费 331155 token。实体召回：单阶段 0.9111、两阶段 0.7556、补漏 0.8222；关系召回：0.4250、0.2000、0.1750；调用次数 17、33、54。详见报告第 4 节。
- 待决：结论只对简化融合、每组单次运行成立；完整融合接入后建议每组至少跑两次并做人工判定，再定生产配置。生产维持两阶段、补漏默认关闭。

## 2026-09-26 K08 应用容器（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| K08 | DONE（待 PR 审查/合并；真实镜像构建未在本机运行） | 实现前后端与 worker 容器配置 | ArvinHan（Claude） | `claude/project-thread-cd4etm` / `main@95d5c9a` | `src/backend/Dockerfile`、`src/frontend/Dockerfile`、`docker-compose.yml`、`tests/integration/test_k08.py`；**范围扩展**：`src/backend/app/workers/__main__.py`、`src/backend/app/workers/runner.py`（仓库原无常驻 worker 入口）、`src/frontend/nginx.conf`、`.dockerignore`、`.env.example`、`docs/integrations.md`「应用容器（K08）」、`docs/architecture.md` worker 行、`docs/decisions.md` ADR-039、本节、`docs/handoffs/claude-k08.md` | `test_k08.py` 22 项：21 passed、1 skipped（真实构建，本机无 Docker 守护进程）；后端全量 2962 passed；F01 9 passed；`verify.sh` exit 0；`docker compose --profile app config` exit 0 |

- 验收：worker 按 A06 §8.1 运行（同机、同 SQLite 卷、`WORKER_PROCESSES` 个进程、启动门禁与 API 相同）；API/worker/web 均有健康检查；密钥只经 `env_file` 进后端三服务；前端 Dockerfile 无构建参数、只 COPY `src/frontend/`，`.dockerignore` 排除 `.env*`。
- K08 待决：镜像真实构建与整套启动未在本机跑（无 Docker 守护进程），须在有 Docker 的机器上跑 `docker compose --profile app up -d --build` 复验；worker 优雅停止不释放在途任务（ADR-039 第 2 条）；`maintenance` 挂点是否接 G05 清扫留给后续任务；镜像基底未钉摘要。

## 2026-09-26 I01 学习进度仓储（Codex 认领）

| ID | 状态 | 任务 | 负责人 | 范围 | 验收 |
| --- | --- | --- | --- | --- | --- |
| I01 | DONE（待 PR 审查） | 实现学习进度仓储 | Codex（后端） | `src/backend/migrations/011_progress.sql`、`src/backend/app/repositories/progress.py`、`tests/backend/test_i01.py`、相关规格/架构/交接 | 用户与课程隔离；原始行和 dormant 行保留；仅允许发布版节点写入；同值无操作及显式覆盖；`write_seq` 与版本提交共用事务序列；I01 6 passed，I01+G02 28 passed，`verify.sh` exit 0；交接 `docs/handoffs/codex-i01.md`。 |

- 输入：已认证 `user_id`/`course_id`、绑定发布版节点集合、原始状态；输出：SQLite 原始进度行及可供 I02 投影的隔离读取结果。
- 依赖：C01、A08、G07 已在本地代码中；I02 负责图谱谱系投影及 HTTP 校验。风险：迁移新增持久表，回滚需停 API/worker 后恢复迁移前 SQLite 备份。
- 验证命令：`.venv/Scripts/python.exe -m pytest tests/backend/test_i01.py tests/backend/test_g02.py -q`、`./scripts/verify.sh`、`git diff --check`。
- 验收证据：审查发现原 `write_progress` 总是另开事务，无法加入 I02 的版本绑定写事务；新增一个用例先因缺少事务入口而失败，修复后 I01 6 passed、I01+G02 28 passed。隔离 worktree 的 `verify.sh` exit 0。此次未重跑后端全量；原始交接记录中的全量结果仅属修复前快照。

## 2026-09-27 J06 引用和终态校验（Codex）

| ID | 状态 | 范围 | 验收证据 |
| --- | --- | --- | --- |
| J06 | DONE | `src/backend/app/services/qa/citations.py`、`tests/backend/test_j06.py`、`tests/fixtures/qa_code_spans.json` | 绑定版本复核来源；流内归一化/剔除未知编号与哨兵；逐句覆盖后构造 `answered` 或固定模板 `not_covered`；共享代码片段夹具。J06 定向 30 passed，`py_compile` exit 0，`verify.sh` exit 0，`git diff --check` exit 0。 |

- 输入：待校验模型输出、允许引用文本块和 G07 已绑定发布版本；输出：仅含已验证标记的 delta、可机读终态与日志所需计数。
- 依赖：B13 契约已合入；J05/J07 后续按本服务接口接入生成流和 SSE API。本任务未改公共契约或路由。
## 2026-09-26 第九批并行：F10→F09、I01、J02、H06、H05、H08、K10（Claude）

基线 `main@0b8aa73`；分支 `claude/upbeat-ramanujan-p4ccbq`（各任务在本地子分支开发后合入本分支）。J01 在 PR #271 进行中，不在本批。ADR 号预分配避免冲突：F10 = ADR-047、F09 = ADR-048、I01 = ADR-049、J02 = ADR-050、H06 = ADR-051、H05 = ADR-052、H08 = ADR-053、K10 = ADR-054（不需要 ADR 的任务空号）。SQLite 迁移号：I01 = `011_progress.sql`。

| 原子 ID | 状态 | 任务 | 负责人 | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- |
| F10 | DONE（本分支 `claude/upbeat-ramanujan-p4ccbq`，待 PR 审查/合并） | 实现节点合并与重接边 | ArvinHan（Claude） | `src/backend/app/services/graph/merge_nodes.py`、`tests/integration/test_f10.py`；与 F09 同一执行者顺序修改 `src/backend/app/repositories/graph_edit.py`、`src/backend/app/api/graph_nodes.py` | `test_f10.py` 27 passed（真实 Neo4j 5.26 + SQLite）；红灯为模块缺失；14 处反向篡改全部检出（1 处补强用例后）；扩围 `graph_edit.py`、`graph_nodes.py`（`POST /kp/merge`）、`schemas/contracts.py`、契约 `MergeRequest.expected_revisions`；ADR-047；`docs/handoffs/claude-f10.md` |
| F09 | DONE（同上） | 实现节点删除与关系清理 | ArvinHan（Claude） | `src/backend/app/services/graph/delete_node.py`、`tests/integration/test_f09.py`；共享文件同上 | `test_f09.py` 17 passed（真实 Neo4j + SQLite，并发用例连跑 5 次通过）；9 处反向篡改全部检出（1 处补强用例后）；扩围 `DELETE /kp/{kid}`（204，可选 `expected_revision`）与契约；ADR-048；`docs/handoffs/claude-f09.md` |
| I01 | SUPERSEDED（`main` 已合入 Codex 的 I01，PR #272；本批实现未采用） | 实现学习进度仓储 | ArvinHan（Claude） | `src/backend/app/repositories/progress.py`、`src/backend/migrations/011_progress.sql`、`tests/backend/test_i01.py` | 本批实现（提交 `9b9231e`，含读时投影与 46 个用例）在合入 `main` 时让位于 PR #272；投影逻辑可供 I02 参考 |
| J02 | DONE（同上） | 实现图结构检索 | ArvinHan（Claude） | `src/backend/app/repositories/graph_search.py`、`tests/integration/test_j02.py` | `test_j02.py` 38 passed（真实 Neo4j 5.26）；15 处反向篡改检出 13，存活 2 处为冗余防护；上限在 Cypher `LIMIT` 生效（缺省 2 跳/30 节点，硬上限 3 跳/200）；ADR-050；`docs/handoffs/claude-j02.md` |
| H06 | DONE（同上） | 实现知识点详情和来源浏览 | ArvinHan（Claude） | `src/frontend/src/components/KnowledgeDetail.vue`、`src/frontend/src/composables/useKnowledgeDetail.ts`、`tests/frontend/h06.test.ts` | `h06.test.ts` 47 passed；16 处反向篡改全部检出；扩围新建 `api/knowledgeDetail.ts`；未接入页面（留 H11）；ADR-051；`docs/handoffs/claude-h06.md` |
| H05 | DONE（同上） | 实现图搜索筛选与布局切换 | ArvinHan（Claude） | `src/frontend/src/composables/useGraphFilters.ts`、`src/frontend/src/components/GraphToolbar.vue`、`tests/frontend/h05.test.ts` | `h05.test.ts` 44 passed；21 处反向篡改全部检出；真实 G6 Chromium 冒烟通过；扩围 `graph/lifecycle.ts`（`setLayout`、状态样式）、`GraphCanvas.vue`（`layout` 属性）、architecture 一行；ADR-052；`docs/handoffs/claude-h05.md` |
| H08 | DONE（同上；后端无 `/relations` 路由，仅假 API 验证） | 实现教师连边编辑交互 | ArvinHan（Claude） | `src/frontend/src/components/RelationEditor.vue`、`src/frontend/src/composables/useRelationEditor.ts`、`tests/frontend/h08.test.ts` | `h08.test.ts` 35 passed；11 处反向篡改全部检出；扩围新建 `api/relations.ts`；ADR-053；`docs/handoffs/claude-h08.md` |
| K10 | DONE（同上；compose 整套实机演练待人工） | 建立备份和恢复演练 | ArvinHan（Claude） | `scripts/backup-demo.sh`、`scripts/restore-demo.sh`、`tests/integration/test_k10.py` | `test_k10.py` 20 passed（含 neo4j-admin dump/load 真实 Docker 容器）；13 处反向篡改全部检出；`.gitignore` 增 `backups/`；ADR-054；`docs/handoffs/claude-k10.md` |

- 共享文件（`docs/decisions.md`、`docs/architecture.md`、`src/contracts/`、`src/frontend/src/api/`、`src/frontend/src/router/`）的扩围改动由各执行者在交接中列明，合入本分支时由协调者解决冲突。
- 合并后复验（协调者，HEAD 含八项合入）：后端 + 契约 + tooling 3465 passed；集成（真实 Neo4j 5.26）321 passed、3 skipped、1 failed——`test_k08.py::test_images_build`，本机 Docker 构建拉镜像遇 Docker Hub 429/构建内无网络，属环境问题，此前无 Docker 守护进程时该用例跳过，K08 镜像实机构建仍待人工复验；前端 438 passed、type-check 与 build 通过；`./scripts/verify.sh` 通过；`git diff --check` 干净。
- 第九批待决（均需 ArvinHan）：ADR-047～054 签收；F10/F09 删除或合并后抽取重建同 ID 节点（F04 查 `merged_from` 或删除留墓碑）；关系是否加修订号（H08）；后端缺关系编辑路由 `/relations`（F06 仅服务层，H08 未联调）；H06 学生端资料名来源；J02 检索上限占位值；K10 compose 下 neo4j-admin 卷挂载与 F14 `--neo4j-backup-confirmed` 换接 K10 备份。
- 本批合入后新解锁：F11、F12（F10+F09）、H07（H06+F09）、H11（H05+H06）、I02（I01）；J04 待 J01（PR #271）合并。

## 2026-09-26 J01 发布来源向量检索（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| J01 | DONE（PR #271，已合并 main 解决冲突） | 建立发布来源向量检索 | ArvinHan（Claude） | `claude/project-thread-sqwla4` / `main@5ff441b` | `src/backend/app/repositories/vector_search.py`、`tests/integration/test_j01.py`；扩围 `docs/decisions.md`（ADR-046） | 红灯：收集错误（模块不存在）；`test_j01.py` 16 passed（真实 Neo4j 5.26）；9 处反向篡改 7 处检出，余 2 处为冗余防护；后端全量与 `verify.sh` 见 `docs/handoffs/claude-j01.md` |

- 验收：只返回本课程、修订属于绑定版本修订列表的文本块，他课和版本外新修订即使更近也不返回；近邻被挤占时自动扩大取数补足召回，到 `max_fetch` 封顶时告警并返回已有结果；无命中或修订列表为空时返回空；查询向量空间、维度、数值不符和草稿作用域在查询前拒绝；当前空间没有索引时抛仓储错误。
- J01 待决：运行时没有任何环节为文本块写向量（F04/F13 只建 `Chunk` 节点，G03 只为知识点算向量，仅 F14 迁移会写），J04 以后接上问答之前需要先补上这一步；`fetch_factor`、`max_fetch` 为占位值（ADR-046）。

## 2026-09-26 F11 审核队列和单项处理（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| F11 | DONE（分支 `claude/project-thread-bd1f83`，待 PR 审查/合并；issue #103） | 实现审核队列和单项处理 | ArvinHan（Claude） | `claude/project-thread-bd1f83` / `main@a7d8075` | `src/backend/app/services/graph/review.py`、`src/backend/app/api/review.py`、`tests/backend/test_f11.py`；扩围 `src/backend/app/repositories/review.py`、`src/backend/migrations/013_review_dismissals.sql`（迁移号协调者预分配）、`api/graph_nodes.py` 的 `_run` 一个分支、`main.py`、`schemas/contracts.py`、契约与生成物 | 见 `docs/handoffs/claude-f11.md`；ADR-060 |

- 验收：三栏按 ADR-060 分类（低置信度关系、E08 名称归一 + 已存别名的疑似重复对、发布后无边的孤立节点）；通过、拒绝、合并后 `totals` 与各栏相应变化，重复提交同一动作 200 `changed = false`，已不在队列 404；各栏固定排序 + 键集分页，边处理边翻页不漏不重。
- F11 待决（需 ArvinHan）：ADR-060 签收（尤其「疑似重复」只用名称归一、不含向量相似；「确认保留」按节点永久生效；新增 `resolveReviewItem` 而不是借 `/relations`）；D-08 阈值定稿后是否把 E09 向量候选并入疑似重复栏。
### F11 独立审查与并行核查遗留（2026-09-26，协调者；不含已修项）

背景：F11 由另一会话的 PR #282 实现；本会话另派的独立实现已作废（SUPERSEDED），但两者都对 #282 做了独立核查，结论如下。已修项见下方「F11 审查修复」。以下均为**未修**、需后续任务或 ArvinHan 裁决的事项。

- **M2 CI 掩盖（中）**：`tests/backend/test_f11.py` 有 23 个真实 Neo4j 用例（`skipif` 依赖 `SMARTSKETCH_TEST_NEO4J_*`），而 `.github/workflows/ci.yml` 只跑 `pytest tests/backend -q` 且不设该 env、也无 Neo4j service 与 `tests/integration` job → CI 恒为 17 passed / 23 skipped 报绿；`docs/atomic-tasks.json` 的 F11 `verification_command` 同样无 env。仓库惯例是 live 用例放 `tests/integration`（F09/F10/J01/K10）。建议迁目录或给 CI 加 Neo4j service。
- **M3 审计缺口（中，跨任务）**：F12（ADR-061）只审计 F08 新建/修改/解锁、F09 删除、F10 合并五个入口。F11 的关系 approve/reject（`repositories/review.py`）与节点 reject 是**直接 Cypher**，不经这五个入口、也直接调 `bump_draft_revision` → 审核队列的图写入**不进审计表、不做 reconcile**，而规格「一致性」要求修改记录写入日志。需显式跟进项（或让 F11 接入 `audit.begin/commit`）。
- **M4 dismissals 永久且无撤销入口（中）**：`review_dismissals`（迁移 013）按 `kp_id`/关系对永久生效，没有 API 或界面可撤销；而 `kp_id` 是确定性派生 `derive_kp_id(course, task, candidate_key)`，`tasks.py` 明说重试返回**原 task_id** → 重跑抽取复用同一批 ID，「不是重复/确认保留」的记录会**静默抑制重建后的条目**（实测：dismiss 后删掉一方、再用同一 ID 建回，totals 仍为 0）。ADR-060 只写「留下的记录无害」，未覆盖该路径。
- **D-1 已修**（`bump_draft_revision` 可重跑事务内未记忆化）→ 见下方审查修复。
- **D-2 低置信度栏口径（中，口径/覆盖缺口）**：低置信度关系只按 `status == "low_confidence"`、**无数值阈值**；而 ADR-029/F13 已决「D-08 签收前自动写入的状态一律 `draft`」，`low_confidence` 只由 ADR-009 的成环降级产生（`services/graph/downgrade.py`）。后果：**未发生过成环降级的课程，该栏恒为空**，即使草稿里全是低置信度 AI 边；现有验收靠手工种 `low_confidence` 行证明，不代表真实数据。`specs/teacher-review-publish.md`「低置信度阈值」仍是待细化，D-08 签收后需回改。
- **D-3 孤立定义口径（低-中，需产品裁决）**：实现只按「没有未拒绝的相连边」，**不含「无章归属」**（与 F07 `GraphStats.isolated_count` 一致）。只挂 `chapter_id`、没有任何关系的节点会进孤立栏，教师「确认保留」后按节点 ID 永久压制。需要在两个自洽口径里选一个并写进规格。
- **D-4 新端点契约未声明 503（低）**：`GET /review` 与 `POST /review/actions` 的契约未声明 503，而实现（复用 `graph_nodes._run`）在 Neo4j 不可达时返回 503 `STORAGE_UNAVAILABLE`，交接也把 503 写进接口变更 → 契约/实现/交接三者不一致（`/graph` 同样未写 503，属既有惯例，非回归）。建议补可复用的 503 响应组件。
- **D-5 幂等判断顺序（低）**：「状态已是目标值 → `changed=false`」排在「仍在队列」判断之前，故「已 approved、但其后某端点被置 rejected」的关系再 approve 返回 200 而非 ADR-060 决定 7 的 404。
- **D-6 跨模块私有导入（低，建议）**：`api/review.py` 从 `api/graph_nodes.py` 导入私有 `_context`/`_run`，并为此改了后者（+3 行，其中 `isinstance(node, dict)` 分支现有调用方不可达）。建议把 `_context`/`_run` 上提到 `api/dependencies.py`（共享 adapter 的既定位置），F11 就不必动 F08/F12 的文件。**合并期已处理**：与 F12 的 `_run(request, access, ...)` 签名冲突已解，`api/review.py` 两处调用点已改传 `access`。
- **D-8 字段名（低）**：`similarity` 对 same_key/alias 恒为 1.0、对 containment 为有效字符比，实际只有三档语义、用途是排序；契约已注明，但字段名与 0～1 值域易被前端当相似度展示。建议改名或强化描述。
- **D-9 关系新增 `revision` 属性未登记（低）**：`repositories/review.py` 给关系写 `coalesce(r.revision,0)+1`，但 `docs/architecture.md` 的 Neo4j 模型段与契约 `Relation` 都未登记，事实上单方面定了 H08 的待决「关系是否加修订号」。
- **缺证据（低）**：无「空草稿队列 → 200 + 三栏空 + totals 全 0」用例；无「他课教师 → 403 `COURSE_FORBIDDEN`」用例（只测了本课学生 403）；无「队列不含已发布副本节点」的固化用例（结构上已排除：`_draft_scope` 硬编码 `version_id="draft"`，端点无 `version` 参数）。
- **已核实的优点（记录备查）**：键集分页为唯一总序（confidence+rel_id / -similarity+左右 ID / name+kp_id）+ 严格 `>` + `_key_shape` 拦跨栏，边处理边翻页不漏不重；关系 approve/reject 与 F08/F09/F10 用同一把课程写锁、`SET r.status` 原地改（rel_id 不变）；幂等由 `INSERT OR IGNORE` + 状态条件写保证；`gen-contracts.sh --check` 与 `check_contracts.py` 均 PASS。

## 2026-09-26 F12 图编辑审计日志（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| F12 | DONE（待 PR 审查/合并，issue #104；**独立审查 APPROVE_WITH_NOTES，必改项已修**） | 实现图编辑审计日志 | ArvinHan（Claude） | `claude/project-thread-21sjlj` / `main@a7d8075` | `src/backend/app/repositories/edit_logs.py`、`src/backend/app/services/graph/audit.py`、`tests/backend/test_f12.py`；扩围 `src/backend/migrations/012_edit_logs.sql`、`tests/integration/test_f12.py`，接入点 `services/graph/edit_node.py`、`delete_node.py`、`merge_nodes.py`、`api/graph_nodes.py`（传调用者）；`docs/decisions.md`（ADR-061）、`docs/architecture.md` 一句、`specs/teacher-review-publish.md`「一致性」 | 红灯：收集错误（模块不存在）；`test_f12.py` 后端 30 passed、集成 8 passed（真实 Neo4j 5.26）；16 处反向篡改全部检出（2 处补强用例后）；后端全量 3132 passed；集成全量 341 passed、8 skipped（真实 Neo4j，Docker 用例跳过）；**独立审查**：修正 PYTHONPATH 后自证测的是本分支代码，后端 30 passed、集成 8 passed、回归 88 passed、6 处独立篡改全部检出；已修 M2（重试预算断言不再由 `RETRY_DELAYS` 派生，篡改 `RETRY_DELAYS=()` 现在红灯）、M1 与脱敏/只追加缺口写入 ADR-061；迁移 012 与 #282(F11) 的 013 无冲突；`verify.sh` exit 0；`docs/handoffs/claude-f12.md` |

- 验收：新建、修改、解锁、删除、合并各记一行 `graph_edit_logs`，含操作者、`created_at`/`resolved_at`、写入后的 `draft_revision`、节点修订号前后值与白名单摘要（合并含直接被合并节点与展平谱系）；只记真实写入，冲突、404、校验失败、成环、未加锁节点的解锁不记；Neo4j 写入失败记 `aborted`；审计更新失败退避重试，仍失败留 `pending`、编辑照常成功，下一次同课程教师写入持锁对账补齐；密钥、令牌、口令散列、私钥与 `password=` 等赋值值不进日志；行只追加，结束后冻结；迁移可按 `ROLLBACK:` 行回滚后重放。
- F12 待决（需 ArvinHan）：ADR-061 签收；迁移号 012 若与并行 PR 冲突，合并前改为 main 最大号 + 1；审计读接口（教师查看历史）未分配任务；关系编辑（F06 路由未实现）与审核队列操作（F11）接入审计留给对应任务；脱敏只按模式匹配。
## 2026-09-26 H07 教师节点编辑面板（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| H07 | DONE（待 PR 审查/合并，issue #119；**独立审查 APPROVE_WITH_NOTES**） | 实现教师节点编辑面板 | ArvinHan（Claude） | `claude/project-thread-130wun` / `main@a7d8075` | `src/frontend/src/components/NodeEditor.vue`、`src/frontend/src/composables/useNodeEditor.ts`、`tests/frontend/h07.test.ts`；扩围新建 `src/frontend/src/api/nodeEdit.ts`、`docs/decisions.md`（ADR-062） | `h07.test.ts` 56 passed；25 处反向篡改全部检出（2 处补强用例后）；type-check 与 build 通过；前端全量**实测 493 passed + 1 failed**，失败项为既有 `b02.test.ts` 子进程 vitest 5 s 超时（本机慢；给 90 s 即通过，`b02.test.ts`/`vitest.config.ts`/`package.json` 本分支未改，`origin/main` 上同样失败）——原写「494 passed」不可复现，已按实测更正；**仅假 API 验证**（真实后端路由已存在但未联调）；独立审查：3 处篡改检出、契约形状与后端 `_CURRENT_FIELDS` 逐字段吻合、`verify.sh` 与 `validate_atomic_plan.py` 通过；`docs/handoffs/claude-h07.md` |

- H07 待决（需 ArvinHan）：ADR-062 签收；教师图谱编辑页无归属（挂载页由新补登的 H14「实现教师图谱编辑页」负责（D-17）；H11 是学生端浏览页，不挂本面板）；`REVISION_CONFLICT` 的 `details.current` 不含章节，采用最新内容时章节沿用本地值。
## 2026-09-26 H11 学生图谱和卡片视图（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| H11 | DONE（待 PR 审查/合并，issue #123） | 实现学生图谱和卡片视图 | ArvinHan（Claude） | `claude/project-thread-vrtfxt` / `main@a7d8075` | `src/frontend/src/views/StudentGraphView.vue`、`src/frontend/src/components/KnowledgeCards.vue`、`tests/frontend/h11.test.ts`；扩围新建 `api/graph.ts`、`composables/useStudentGraph.ts`，小改 `router/index.ts`、`main.ts`、`views/CoursesView.vue`、`components/GraphToolbar.vue`（`showStatuses`） | `h11.test.ts` 45 passed（测试与实现同批写成，未单独跑红灯）；type-check、build 通过；前端全量 15 files 483 passed；`verify.sh` 通过；15 处反向篡改检出 14，存活 1 处为冗余防护；ADR-063；`docs/handoffs/claude-h11.md` |

- 验收：无发布（`published_version = null` 或 `GRAPH_NOT_PUBLISHED`）显示未发布且不读图；空图显示空态；卡片分页；卡片键盘可达（单 Tab 位、方向键跨页、Home/End、PageUp/PageDown、Enter/空格）；任何入口不取草稿（读图必带发布版本号并核对响应版本，课程内教师不发图谱/详情请求，卡片不调 `GET /kp`）。
- H11 待决：课程内教师是否需要「以学生身份预览已发布版」（需详情接口加 `version` 参数）；详情响应不带版本号，读图与读详情之间发布新版本时可能不一致；原文阅读器（`locateSource`）与学生端资料名仍未落地（H06 待决）；未做真实浏览器冒烟。
## 2026-09-26 J04 检索合并与上下文预算（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| J04 | DONE（待 PR 审查/合并，issue #133；**独立审查 APPROVE_WITH_NOTES，必改项已修**） | 实现检索合并与上下文预算 | ArvinHan（Claude） | `claude/project-thread-ohmwyv` / `main@a7d8075` | `src/backend/app/services/qa/context.py`、`tests/backend/test_j04.py`；扩围 `docs/decisions.md`（ADR-065）、`specs/grounded-qa.md`（Q3.1 与「待细化」各一条） | 红灯：收集错误（模块不存在）；`test_j04.py` 44 passed；21 处反向篡改全部检出；后端全量 3146 passed；审查独立复跑 44 passed / 全量 3146 passed / 4 处反向篡改检出；已修 docstring 接线示例（M1）并把 ①② 落成规格文字；`verify.sh` 通过；`docs/handoffs/claude-j04.md` |

- 验收：两路候选按 `chunk_id` 去重并保留出处（`origins`、`kp_ids`）；他课、修订不在绑定版本内、不可定位或读不到的块不获得编号（QA-17）；H 为空 → `no_retrieval_hit`，H 非空但无向量候选达到 fake 阈值 → `below_similarity_threshold`（QA-6、QA-7 的 J04 部分）；token 预算整块取舍，不截断文本与定位；图谱上下文无编号。
- J04 待决：阈值与 `ContextBudget` 三个值无缺省，待 K01 调参、J07 配置；「只有向量相似度能打开闸门」与「预算放不下任何块时按 `below_similarity_threshold` 拒答」待签收（ADR-065）；运行时文本块向量写入缺口（J01 待决）仍未补，接上前问答总会拒答。
## 2026-09-26 G08 发布时补齐文本块向量（Claude，新增任务）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| G08 | DONE（待 PR 审查/合并） | 发布时补齐文本块向量（J01 发现的缺口，ArvinHan 2026-09-26 同意新增） | ArvinHan（Claude） | `claude/project-thread-sqwla4` / `main@a7d8075` | `src/backend/app/services/versions/chunk_vectors.py`、`tests/integration/test_g08.py`；扩围 `src/backend/app/services/versions/publish.py`（P8/P9 各一处）、`specs/teacher-review-publish.md`（P8、P9、V8 各一句）、`docs/architecture.md`（一句）、`docs/decisions.md`（ADR-066） | 红灯：收集错误（模块不存在）；`test_g08.py` 10 passed（真实 Neo4j）；9 处反向篡改，补 1 个用例后全部检出；全量见 `docs/handoffs/claude-g08.md` |

- 依赖：G03、G04、J01、E07。J04 的端到端检索依赖本任务（原子清单 `docs/atomic-tasks.json` 是基线计划，未改）；反向记入 J01/J04 待决：运行时文本块向量只由本任务的发布路径写入，没有发布就没有向量。
- 验收：发布后版本修订内的全部文本块（包括没有被引用的块）都有节点和当前空间向量，J01 能检索到；已有向量的块不再调用模型；版本外修订的块不处理；向量调用失败时发布在 P8 失败，指针不变；P9 能发现缺向量、维度不对或缺 `revision_id` 的块；嵌入器空间不符时拒绝。
- **迁移应用顺序（F11 审查 S2，实测可复现）**：`sqlite.py` 拒绝「比已应用版本更旧的迁移」。若某环境先应用了 F11 的 `013_review_dismissals.sql`，之后再引入 F12 的 `012_edit_logs.sql`，012 在该库上**永久无法应用**（需按 `backups/*-before-013.sqlite` 恢复）。本批把 F12（012）与 F11（013）放在同一合入窗口，迁移按版本号顺序 012 → 013 应用；**任何环境不得先单独跑 013**。
- G08 待决：本任务之前已经提交的版本没有文本块向量，回滚到这些版本时检索结果不全（MVP 阶段没有真实数据）；**补齐途径未闭环**——「重新发布一次即可补齐」已被独立审查证伪（幂等路径跳过 P8；旧修订被新修订取代后永远补不上），需为 G06 或 `scripts/reembed.py` 记「按版本补齐块向量」子命令；首次发布耗时与**尝试租约覆盖**尚未实测（首次发布若超过尝试租约，`reclaim_expired` 会把仍在进行的尝试判失败，而块向量已写一部分）；**跨任务缺口（审查 M3）**：`ensure_vector_indexes` 只在 `scripts/reembed.py` 与测试夹具调用，`main.py` 启动校验与 `apply_migrations`（只接受 `CREATE CONSTRAINT`/`CREATE INDEX`）都不建 `CREATE VECTOR INDEX`，`EXPECTED_SCHEMA` 也不含它 → **P9 绿不等于 J01 可检索**，归 F03/F14 确认。另：P9 只查 `revision_id IS NULL`，非空但错误的值不检出（J01 会静默丢弃该块）；P9 不校验 `document_id`。

## 2026-09-26 断点恢复批次：F11、F12、H07、H11、I02、J04、G08（Claude，协调者）

**断点事实（已核实，非推测）**：上一会话中断时的现场为——本地 `main` 落后远端 28 个提交；6 个 PR（#275 H11、#276 H07、#277 J04、#278 G08、#279 F12、#280 I02）已开待收；**F11 是真正中断的任务**（issue #103 标 `status:in-progress`，无分支、无提交、三个目标文件都不存在，但 Docker 容器 `ss-neo4j-f11` 仍在运行，为其遗留开发环境）。恢复期间发现**另一会话**已在 `17:07Z` 用 PR **#282** 完整实现 F11（17 文件、+2289/-46、迁移 013、契约更新、40 用例），因此本会话派出的并行 F11 实现**作废（SUPERSEDED）**，改为对 #282 的独立审查；该分支名 `claude/f11-f12-h07-h11-i02-j04` 也印证中断批次就是这六个任务加 F11。断点前最后一笔提交为 `bceeced`（D-17 补登 H14 教师图谱编辑页 + K05 增加依赖，issue #281）。

| 原子 ID | 状态 | 本批处置 | 独立审查结论 | 审查修复 |
| --- | --- | --- | --- | --- |
| F11 | DONE（本批合入；#282，ADR-060） | 采纳另一会话实现；本会话并行实现作废 | REQUEST_CHANGES → **已修 S1**（merge 不校验是否在疑似重复栏，无关节点可被合并）与 **M1**（`bump_draft_revision` 在可重跑事务内未记忆化） | 见 `docs/handoffs/claude-f11.md` 与本批说明；遗留项见上一小节 |
| F12 | DONE（本批合入；#279，ADR-061） | 采纳 | APPROVE_WITH_NOTES | M2 测试去自证（篡改 `RETRY_DELAYS=()` 现在红灯）；M1 租约错记窗口与脱敏/只追加缺口写入 ADR-061；迁移 012 与 013 无冲突 |
| H07 | DONE（本批合入；#276，ADR-062） | 采纳 | APPROVE_WITH_NOTES | 证据行按实测更正（493 passed + 1 既有 b02 flake）并补「仅假 API 验证」；删除确认的焦点管理、`aria-invalid`、别名标签一致性已修（h07 61 passed，3 处篡改检出） |
| H11 | DONE（本批合入；#275，ADR-063） | 采纳 | APPROVE_WITH_NOTES（无阻断） | 补 IAM-11 的「课程详情 404 `GRAPH_NOT_PUBLISHED`」回归用例（h11 46 passed）；交接补 `getCourse` 未实现这一依赖 |
| I02 | DONE（本批合入；#280，ADR-064） | 采纳 | APPROVE_WITH_NOTES | 补有鉴别力的「写事务内解析发布指针」用例（原断言恒真，审查实测该篡改存活）；`identity-access.md` 与契约的 `user_id` 多余字段口径冲突显式落文并列入签收；`reason="duplicate"` 登记进 `errors.v1.md` |
| J04 | DONE（本批合入；#277，ADR-065） | 采纳 | APPROVE_WITH_NOTES | M1 接线示例错误已修（`functools.partial` 与 keyword-only `chunk_ids` 不兼容，J07 照抄即崩）；①② 待签收落成 ADR-065 与 `specs/grounded-qa.md` 条文 |
| G08 | DONE（本批合入；#278，ADR-066） | 采纳 | REQUEST_CHANGES（仅文档） | ADR 撞号 047 → **066**（7 处 G08 引用；F10 语境的 ADR-047 未动，含 `src/contracts/*`）；被证伪的「重新发布一次即可补齐」按实测更正；补记补齐途径未闭环、租约覆盖未实测与向量索引无生产创建路径（M3，归 F03/F14） |

- **合并方式**：七个分支按 ADR 号升序（060→066）合入集成分支 `claude/integration-0926`，`docs/decisions.md` 与 `docs/tasks.md` 的末尾追加型冲突一律「两段都保留」；唯一的代码冲突在 `api/graph_nodes.py`——取 F12 的 `_run(request, access, operation)` 签名与 `_context(request, access)`，保留 F11 的 `dict` 返回类型与 `isinstance` 分支，并同步把 `api/review.py` 的两处调用点改为传 `access`（否则审核动作会 TypeError→500）。**迁移应用顺序**：012（F12）与 013（F11）必须同一窗口合入并按版本号顺序应用，任何环境不得先单独跑 013（见 G08 待决中的 S2 记录）。
- **环境事实（写给后续会话）**：worktree 里共享的 `.venv` 是 editable 安装、`app` 包指向**主仓**——在任何 worktree 里跑 Python 测试必须带 `PYTHONPATH=$PWD/src/backend`，否则测的是主仓代码（会假绿或 ImportError）；本批全部审查与实现任务都据此修正并在报告里附了自证输出。集成测试连真实 Neo4j 需 `SMARTSKETCH_TEST_NEO4J_URI=bolt://localhost:17687 SMARTSKETCH_TEST_NEO4J_USER=neo4j SMARTSKETCH_TEST_NEO4J_PASSWORD=testpassword1`（容器 `ss-neo4j-f11`，Neo4j 5.26.31）；注意 `.env` 里的 `NEO4J_URI` 仍写 7687，与容器端口不一致。同名校验：`tests/backend/test_f08.py` 与 `tests/integration/test_f08.py` 同名，混跑会触发 pytest import mismatch，须按目录分开跑。
- **本批新解锁（可开工）**：H14（教师图谱编辑页，依赖 H05/H06/H07/H08，D-17 补登，issue #281）、I05（推荐查询 API，依赖 I02/I04/G07）、J05（有证据问答生成，依赖 J04/E04）；其后 H09（F11+H07）、J06（J05）、I06（I05）跟进。
- **需 ArvinHan 签收（本批累计）**：ADR-060～066 七条；ADR-061 的租约被夺窗口如何处置（当前选择如实记录、接受残留风险）与脱敏/只追加缺口是否本轮补；ADR-065 的「图证据块在闸门打开后可被引用」与「预算 0 块复用 `below_similarity_threshold`」两点；ADR-064 的 `user_id` 多余字段覆盖 `specs/identity-access.md` 相应条目（**已裁决 (A) 保持 422，ArvinHan 2026-09-27**）；I02 的 `reason="duplicate"` 登记（**ADR-064 全部已签收，ArvinHan 2026-09-27**）。
- **收口**：#273（codex 的 J02 draft）已被 #274 合入的 J02 取代，作为重复草稿关闭；已合入 main 但 issue 仍 open 的陈旧项（#100 F08、#110 G05、#111 G06、#130 J01、#131 J02、#117 H05、#118 H06、#120 H08、#149 K10、#101 F09、#102 F10 等）随本批一并关闭并附合并证据。
## 2026-09-26 I02 掌握标记 API（Claude 认领）

| ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| I02 | DONE（待 PR 审查/合并；issue #125） | 实现掌握标记 API | ArvinHan（Claude） | `claude/project-thread-fqm6l4` / `main@a7d8075` | `src/backend/app/services/learning/progress.py`、`src/backend/app/api/progress.py`、`tests/backend/test_i02.py`；**范围扩展**：`app/main.py` 路由注册、`app/schemas/contracts.py` 两行导出、`services/learning/__init__.py` 文档串、`specs/learning-path.md` 状态行、`docs/architecture.md` 一行、ADR-064、`docs/handoffs/claude-i02.md` | `test_i02.py` 24 passed；8 处反向篡改检出 7 处，存活 1 处为冗余防护（绑定版本号复核，G07 已查）；后端 + 契约全量 3417 passed；`./scripts/verify.sh` 通过；`git diff --check` 干净 |

- 验收：请求体带 `user_id` 整批 422 零写入、查询串 `user_id` 不被读取、学生之间与课程之间隔离；改标后 `GET /progress` 与 I03 可学集合按新投影重算；草稿独有、已删除、他课、已并入他点的来源 `kp_id` 均 422 `not_in_published_version` 且零写入；LP-8/9/16～20 的投影与覆盖、同值写入重放无操作、写事务内复核发布指针、完整性故障 500 只含 `request_id`。
- 依赖：I01（PR #272）、C03、B12/B12-R1（契约）、G07 均已在 main。无迁移（预分配的 014 未使用）、无契约与依赖变更。
- 验证：`python3 -m pytest tests/backend/test_i02.py -q`、`./scripts/verify.sh`、`git diff --check`。
- I02 签收（ArvinHan，2026-09-27）：`user_id` 口径裁决 (A) 保持 422；教师成员读写进度一律 403（教师查看学生进度须另立接口）；同批重复 `kp_id` 的 `reason` 取 `duplicate`。ADR-064 全部已签收，I02 无待决项。

## 2026-09-27 G08 遗留修复：向量索引、P9 核对与按版本补齐（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| G08-R1 | DONE（待 PR 审查/合并） | 关闭 #283 审查对 G08 的遗留：生产不建向量索引、补齐途径未闭环、P9 不核对块身份 | ArvinHan（Claude，含 1 个并行子代理） | `claude/project-thread-sqwla4` / `main@f2fbf1e` | `src/backend/app/repositories/graph_migrations.py`（`ensure_current_vector_indexes`、`main`）、`src/backend/app/services/versions/chunk_vectors.py`、`scripts/backfill_chunk_vectors.py`、`tests/integration/test_g08.py`、`tests/integration/test_g08_backfill.py`、`tests/backend/test_g08_index.py`；扩围 `tests/integration/test_g04.py`、`tests/integration/test_k10.py`（夹具按部署流程建 `fake/4` 向量索引）、`specs/teacher-review-publish.md`（P9 一句）、`docs/integrations.md`、`src/backend/README.md`、`docs/decisions.md`（ADR-055） | 红灯：新用例收集失败（函数与脚本不存在）；`test_g08.py` 14 passed、`test_g08_backfill.py` 15 passed、`test_g08_index.py` 4 passed；后端 3223 passed、集成 370 passed；`verify.sh` exit 0；详见 `docs/handoffs/claude-g08-r1.md` |

- 验收：`python -m app.repositories.graph_migrations` 为记录的当前空间建知识点与文本块两个向量索引并等待上线，配置与记录不符时拒绝；P9 在索引缺失、未上线或块节点 `revision_id`/`document_id` 与 SQLite 不符时失败，`index_chunks` 覆盖改正；`scripts/backfill_chunk_vectors.py` 按已提交版本补齐（含被新修订取代的旧修订），可按课程/版本缩小范围，`--dry-run` 不调用模型，空间不符时拒绝，重复运行不重算。
- 关闭 G08 待决中的「补齐途径未闭环」「向量索引无生产创建路径」「P9 不检出错误 `revision_id`、不校验 `document_id`」；「首次发布超过尝试租约」经核对不会发生（发布全程心跳续约，ADR-055 后果）。
- 仍待决：补齐命令与发布的向量调用都不写 `model_calls`（F14 的 `reembed.py` 会写），是否计入预算与审计待定；首次发布耗时尚未用真实课程实测。

## 2026-09-27 H14 教师图谱编辑页（Claude 认领）

| ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| H14 | DONE（#285 已合入；issue #281 已关闭） | 实现教师图谱编辑页 | ArvinHan（Claude） | `claude/project-thread-n5wcl5` / `main@f2fbf1e`（合并前并入 `main@cba4c41`） | `src/frontend/src/views/TeacherGraphView.vue`、`src/frontend/src/composables/useTeacherGraph.ts`、`src/frontend/src/router/index.ts`、`tests/frontend/h14.test.ts`；扩围 `api/graph.ts`（`DraftGraphApi`）、`main.ts`、`views/CoursesView.vue`（教师入口）、`components/NodeEditor.vue`（`defineExpose({ dirty })` 一行）、`docs/architecture.md`、`docs/decisions.md`（ADR-067） | `h14.test.ts` 42 passed；独立审查 25 处篡改 20 处检出（未检出 5 处中 2 处为等价篡改，3 处已补用例）并发现 1 中 5 低问题，均先补复现用例再修；前端全量 17 files / 587 passed；type-check、build、`verify.sh` 通过；**仅假 API 验证**（后端尚无 `/relations` 路由）；`docs/handoffs/claude-h14.md` |

- 断点：上一会话只给 issue #281 打了 `status:in-progress`，无分支、无提交，本轮从 `main@f2fbf1e` 从零实现。
- H14：ADR-067 已由 ArvinHan 2026-09-27 签收（三页签布局、页内确认 + `window.confirm` 离开确认、刷新在途遇写入则重拉）；PR #285 已合入；离开本页不清空课程 store 的草稿图（目前无页面直接读 `store.graph`，已记入 ADR 后果）。
- 解锁：K05 教师主线 E2E 的 H14 依赖满足（仍依赖 H09、H10 等）。

## 2026-09-27 J05 有证据问答生成（Claude 认领）

| ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| J05 | DONE（待 PR 审查/合并；issue #134；**独立审查 APPROVE_WITH_NOTES，测试缺口与包导出已修**） | 实现有证据问答生成 | ArvinHan（Claude） | `claude/project-thread-bkxc2u` / `main@ac21e5d` | `src/backend/app/services/qa/generate.py`、`prompts/answer_with_context.yaml`（v1 → v2）、`tests/backend/test_j05.py`；扩围 `prompts/MANIFEST.md`（一行，E01 规则要求升版本同提交更新摘要）、`tests/backend/test_e01.py`（一行，版本改读清单）、`specs/grounded-qa.md`（「待细化」一条）、`docs/decisions.md`（ADR-068）、`src/backend/app/services/qa/__init__.py`（J05 导出）、`docs/handoffs/claude-j05.md` | 红灯：收集错误（模块不存在）；`test_j05.py` 70 passed（独立审查后补 5 个用例）；实现者 22 处反向篡改全部检出；独立审查 23 处（21 检出、1 处等价改动无观测差异、1 处测试缺口已补并复核检出）；后端全量 3293 passed / 27 skipped；`verify.sh` 通过；`git diff --check` 通过；`docs/handoffs/claude-j05.md` |
| J05 | DONE（待 PR 审查/合并；issue #134） | 实现有证据问答生成 | ArvinHan（Claude） | `claude/project-thread-bkxc2u` / `main@ac21e5d` | `src/backend/app/services/qa/generate.py`、`prompts/answer_with_context.yaml`（v1 → v2）、`tests/backend/test_j05.py`；扩围 `prompts/MANIFEST.md`（一行，E01 规则要求升版本同提交更新摘要）、`tests/backend/test_e01.py`（一行，版本改读清单）、`specs/grounded-qa.md`（「待细化」一条）、`docs/decisions.md`（ADR-068）、`docs/handoffs/claude-j05.md` | 红灯：收集错误（模块不存在）；`test_j05.py` 65 passed；22 处反向篡改全部检出（初次 2 处存活，补 2 个用例）；后端全量 3288 passed / 27 skipped；`verify.sh` 通过；`git diff --check` 通过；`docs/handoffs/claude-j05.md` |

- 验收：J04 上下文为空或低于阈值 → `SkippedGeneration`，fake 调用数与 `model_calls` 行数均为 0（QA-6、QA-7 的 J05 部分）；资料中的「忽略以上指令」、伪造的 `<<课程资料结束>>`、`<<资料 9>>` 块头与哨兵都留在资料段内且被中和，代码 `a[1]`、`cout << x` 原样保留（主验收第 10 条）；链路到期（开始前、读取中、供应商读满剩余时间）为 `LLM_UNAVAILABLE` + `timeout`，与首字前其他故障的 `upstream` 区分（O9 与 QA-24～29 的 J05 部分）；生成接口不接收历史（QA-19）。只用 fake 模型。
- 验证：`python3 -m pytest tests/backend/test_j05.py -q`。
- 待决（ArvinHan）：ADR-068 签收（输出上限 1024 暂定、`<<资料 n>>` 块头、0.25 秒超时容差）；`LLM_CHAT_FIRST_TOKEN_TIMEOUT_SECONDS` 尚无实现（适配器超时覆盖整条流）；提示效果待 K03 真实模型评测，付费调用需另行同意。
- 解锁：J06（J05 + B13）。

## 2026-09-27 J10 问答日志（Codex）

| ID | 状态 | 范围 | 验收证据 |
| --- | --- | --- | --- |
| J10 | IMPLEMENTED / 验证通过，待 PR 复审 | `014_chat_logs.sql`、`chat_logs.py`、J07 问答路由/服务、`test_j10.py` | P2 后各终态写入唯一请求行；按课程/用户查询与统计；不保存回答或模型原始输出；写入时清理 30 天前记录。J07/J10 定向测试 12 passed，`verify.sh` 通过。 |

- J07 已合入并接入日志写入；P1/P2 失败不调用此仓储。迁移编号顺延至 014，以避开已存在的 012、013。
- PR #295 Backend CI 修复：014 迁移补回滚步骤，F11 迁移回滚用例限制迁移范围；原失败三例与 J10 定向测试共 4 passed，待 GitHub CI 重跑。
## 2026-09-27 K04 全链路性能测量（Codex）

| ID | 状态 | 任务 | 分支 | 修改范围 | 验证 |
| --- | --- | --- | --- | --- | --- |
| K04 | IMPLEMENTED / 待实测与 PR 复审 | 固定约 2 万字样本的 worker 阶段耗时、token 与 SSE 问答测量 | `codex/k04-benchmark-pipeline` | `evaluation/benchmark_pipeline.py`、`tests/backend/test_k04.py`、`docs/handoffs/codex-k04.md` | J07 已合入；SSE 首字/终态与 p50/p95 定向测试 3 passed；真实服务测量待环境，`verify.sh` 因本机契约工具链/编码未通过，付费调用未执行 |
## 2026-09-27 I05 推荐查询 API（Claude 认领）

| ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| I05 | DONE（待 PR 审查/合并；issue #128） | 实现推荐查询 API | ArvinHan（Claude） | `claude/project-thread-98kaqt` / `main@ac21e5d` | `src/backend/app/services/learning/recommend.py`、`src/backend/app/api/recommend.py`、`tests/backend/test_i05.py`；**范围扩展**：`app/main.py` 路由注册、`app/schemas/contracts.py` 一行导出、`services/learning/__init__.py` 文档串、`specs/learning-path.md` 状态行、`docs/architecture.md` 一行、ADR-069、`docs/handoffs/claude-i05.md` | `test_i05.py` 34 passed；6 处反向篡改（途中重解析指针、截断后计 `total_eligible`、不过滤边类型、吞掉图错误、截断前改排序、去掉 `limit` 校验）均检出；后端全量 3257 passed / 27 skipped；`./scripts/verify.sh` exit 0；`git diff --check` 干净 |

- 验收：绑定版本后途中提交 v2，本请求的图、投影、`graph_version` 仍为 v1，下一请求读 v2；`limit=1..n` 均为 `limit=50` 结果的前缀且 `total_eligible` 不变；未发布 404 `GRAPH_NOT_PUBLISHED` 与 200 `all_mastered` 区分；环、自环、悬空端点、`V=∅`、章节树损坏、未知章节、谱系损坏、摘要不符均 500 且 `details` 只含 `request_id`，环路节点只进日志；`limit` 越界 422。
- 依赖：I02（#280/#288）、I04（#238）、G07（#267）均已在 main。无迁移、契约与依赖变更（ADR-069 未占用迁移号）。
- 验证：`python3 -m pytest tests/backend/test_i05.py -q`、`./scripts/verify.sh`、`git diff --check`。
- 待签收：ADR-069（图读已提交快照而非 Neo4j 副本；教师 403）。
- 解锁：I06（另需 H11，已在 main）。
- 独立审查（2026-09-27，PR #291，worktree `.claude/worktrees/pr291`）：定向 `test_i05.py` 36 passed；后端全量 3259 passed / 27 skipped；8 处反向篡改 7 处判红，1 处存活（删除图读的摘要复核——该检查只在 G07 修订缓存与 I02 谱系缓存已热时才唯一生效），已新增 `test_graph_read_revalidates_snapshot_with_warm_version_caches`（摘要列/他课两例）闭合并复跑判红；另补「查询串 `user_id` 不能冒充身份」断言。未发现实现缺陷，未改契约真源。
## 2026-09-27 H09 审核队列与节点合并 UI（Claude 认领）

| ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| H09 | DONE（待 PR 审查/合并；issue #121） | 实现审核队列和节点合并 UI | ArvinHan（Claude） | `claude/project-thread-eo5fzo` / `main@ac21e5d` | `src/frontend/src/views/ReviewView.vue`、`src/frontend/src/composables/useReview.ts`、`tests/frontend/h09.test.ts`；扩围 `api/review.ts`（新增）、`router/index.ts`（`REVIEW_ROUTE`）、`main.ts`、`views/CoursesView.vue`（教师入口）、`docs/architecture.md`、`docs/decisions.md`（ADR-070）、`specs/teacher-review-publish.md` | `h09.test.ts` 37 passed（独立审查后补 6 项用例）；前端全量 18 files / 623 passed + 1 既有 `b02` flake；type-check、build、`verify.sh` 通过；**仅假 API 验证**（F11 后端路由已在 main，未联调）；`docs/handoffs/claude-h09.md` |

- 断点：issue #121 挂着旧的 `status:in-progress`，远端无分支、无提交，本轮从 `main@ac21e5d` 从零实现。
- 验收对应：三类空态（各栏空态 + 全空「可以直接发布」）、重复操作（单写禁用、`changed = false`、404 已被处理）、合并冲突（`CYCLE_DETECTED` 名称环路、`COURSE_BUSY`、`REVISION_CONFLICT`）、刷新后数量一致（数量只取服务端 `totals`，重新进入页面数量相同）。
- H09 待决（需 ArvinHan）：ADR-070 签收（三栏上下排列、合并先选主节点再确认、哪些处理后重读队列）。
- 独立审查（2026-09-27，PR #289，worktree `.claude/worktrees/pr289`）：反向篡改 16 处检出 14 处，存活 2 处不可经公开输入触发（游标写回读别栏键、`busyKey` 守卫被 UI 禁用兜住）；补 6 项用例钉住三栏空态文案互异、401 文案、`loadMore` 的 totals 口径、`changed=false` 的 fixture 自相矛盾、成环冲突后改选与双栏游标；**未改 `src/`**。
- 解锁：K05 教师主线 E2E 的 H09 依赖满足（仍依赖 H10 等）。
## 2026-09-27 PR #264（G05+G06）独立审查四项遗留修复（Claude 认领）

| ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| #264-R1 | DONE（待 PR 审查/合并） | `sweep` 接入 worker 周期回收 | ArvinHan（Claude） | `claude/leftovers264-0927` / `main@ac21e5d` | `src/backend/app/workers/runner.py`、`src/backend/app/config.py`、`.env.example`、`docs/integrations.md`、`tests/backend/test_g05_sweep_schedule.py` | 红：4 failed（`PublishSweep`/`build_maintenance` 不存在，旧路径无清扫）；绿：5 passed；篡改 3 处全检出 |
| #264-R2 | DONE（待 PR 审查/合并） | 失败任务无实际贡献时清理不空等课程锁 | ArvinHan（Claude） | 同上 | `src/backend/app/workers/persist_graph.py`、`src/backend/app/repositories/graph_relations.py`、`tests/backend/test_264_cleanup_lock.py` | 红：2 failed（旧实现取锁 `acquired == ['w']` 且返回 False）；绿：4 passed；篡改 3 处全检出 |
| #264-R3 | DONE（待 PR 审查/合并） | 任务重跑不把教师已裁决状态降级回 draft | ArvinHan（Claude） | 同上 | `src/backend/app/repositories/graph_nodes.py`、`tests/integration/test_f13.py` | 红：2 failed（`approved → draft`、`rejected → draft`，真实 Neo4j）；绿：30 passed（整个 `test_f13.py`）；篡改 2 处全检出 |
| #264-R4 | DONE（待 PR 审查/合并） | 无来源手工节点详情返回显式空态而非 500 | ArvinHan（Claude） | 同上 | `src/contracts/api.v1.yaml`、`src/contracts/v1/generated/*`、`src/backend/app/services/graph/read.py`、`src/backend/app/api/graph.py`、`src/backend/app/schemas/contracts.py`、`tests/backend/test_f07.py`、`tests/contracts/test_264_leftovers.py` | 红：`test_manual_node_...` 500 != 200；绿：38 passed（F07 25 + 新契约 4 + R1/R2 新用例 9）；篡改 3 处全检出（含 `minItems` 放宽被 B11 负例拦下） |

- 四项各自独立 commit（R1 `9c5d753`、R2 `b318172`、R3 `38b3dbd`、R4 `03ab66b`），未 push、未 merge。
- 回归：`PYTHONPATH=$PWD/src/backend .venv/bin/python -m pytest tests/backend -q` 全绿；集成（真实 Neo4j 5.26.31，容器 `ss-neo4j-f11`）：`pytest tests/integration/test_f13.py -q` 30 passed。
- 契约：`./scripts/gen-contracts.sh --check` 与 `./scripts/verify/contracts.sh` 与真源一致。
- 决策：ADR-072（含需 ArvinHan 签收的三项：清扫缺省启用与周期、详情响应新增形状、已审核内容可被重跑改写而状态冻结）。
- 待决：孤儿副本与已提交版本缺副本仍只告警（处理归 K10）；`sweep` 只覆盖发布/回滚尝试的副本，§8.6 的块检查点与任务来源块保留期清理仍未接入同一调度（本轮范围外）。
## 2026-09-27 后端关系编辑接口：/relations 三个路由（Claude 认领）

| 原子 ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| F06-API | DONE（待 PR 审查/合并） | 补上后端关系编辑接口（`POST`/`PATCH`/`DELETE /api/v1/courses/{cid}/relations[/{rid}]`），关闭 H14 交接里「仅假 API 验证（后端尚无 `/relations` 路由）」的缺口 | ArvinHan（Claude） | `claude/relations-0927` / `main@ac21e5d` | 新增 `src/backend/app/api/relations.py`、`src/backend/app/services/graph/edit_relation.py`、`src/backend/app/repositories/graph_relation_edit.py`、`tests/backend/test_relations_api.py`、`tests/integration/test_relations_api.py`、`docs/handoffs/claude-relations-api.md`；扩围 `src/backend/app/main.py`（路由注册 2 行）、`src/backend/app/schemas/contracts.py`（`RelationCreate` 导出 2 行）、`src/backend/app/services/graph/audit.py`（关系摘要、`_applied_relation`、`reconcile` 分派）、`docs/decisions.md`（ADR-071）、`docs/architecture.md`（一句接线）、`specs/course-knowledge-graph.md`（状态行一句） | 红灯：`tests/backend/test_relations_api.py` 53 failed / 3 passed（路由不存在）；实现后该文件 58 passed；集成 `tests/integration/test_relations_api.py` 11 passed（真实 Neo4j 5.26.31）；后端全量 3281 passed / 27 skipped；图编辑相关集成（F06/F08/F09/F10/F12/F13 + 本任务）126 passed；`tests/contracts` 291 passed；`scripts/gen-contracts.sh --check` PASS（未改 `src/contracts/`）；`./scripts/verify.sh` exit 0；反向篡改 9 处（矩阵见 `docs/handoffs/claude-relations-api.md`），实现者报告全部检出；协调者另独立复现其中 2 处（创建侧环检测、PATCH 侧环检测）均判红；详见 `docs/handoffs/claude-relations-api.md` |

- 验收：契约的路径、方法、状态码与响应体形状逐条对照（含 `Relation` 的 `oneOf`）；教师角色与课程成员口径（学生 403 `ROLE_FORBIDDEN`、非成员 403 `COURSE_FORBIDDEN`、未认证 401）；`PREREQUISITE` 新建、改向、以及把 `rejected` 恢复为有效时写入前检测成环（409 `CYCLE_DETECTED` + `details.cycle`，拒绝时零写入、不加 `draft_revision`、不记审计）；悬空端点 422 `DANGLING_ENDPOINT`（`details.missing`）；重复关系 409 `DUPLICATE_RELATION`（`details.existing_id`）；课程写锁与 409 `COURSE_BUSY`（`details.holder`）；Neo4j 不可达 503 `STORAGE_UNAVAILABLE`；响应体来自真实图（不回声请求体）；关系新建/修改/删除各记一条 F12 审计且 `draft_revision` 恰加一，审计 `commit` 失败不回滚编辑、行留 `pending` 由下一次写入对账。
- 依赖：F06 服务层（`apply_relations`）、F08 课程写锁与 `EditContext`、F12 审计（ADR-061）、契约 `api.v1.yaml` 的 `createRelation`/`updateRelation`/`deleteRelation`、`errors.v1.md`。无迁移、无依赖升级、未改契约真源。
- 待决（需 ArvinHan 裁决，见 ADR-071 后果）：
  1. **契约未声明 503**：三条路由沿用既有图路由惯例返回 503 `STORAGE_UNAVAILABLE`，但 `api.v1.yaml` 的两条路径只声明 401/403/404/409/422。要么补契约（需另开契约变更），要么把 Neo4j 故障并入 500——本任务选择「不改契约、记差异」，与 F11 审查 D-4 同类。
  2. **两个未登记的领域 `reason`**：非 `PREREQUISITE` 自环报 422 `VALIDATION_ERROR` + `self_loop`；`InvalidRelationError` 兜底报 `invalid_relation`。`errors.v1.md` 要求领域 `reason` 先登记，契约真源本轮冻结。
  3. **改类型/方向会丢弃 `source_pairs`**：新身份 = 新的人工断言（保留 `confidence`/`status`，来源证据归零）；若希望改向后保留 AI 证据，需要另立实现（把块 ID 迁到新身份的 `source_pairs`）。
  4. **审计行语义**：关系行复用 `create`/`update`/`delete` 动作、`kp_id` 存 `rel_id`、修订号列 NULL，靠摘要的 `entity = "relation"` 区分（迁移 012 的 `action` 是数据库级闭集，新增取值要重建表）。若审计消费者需要一个显式的 `entity` 列，需另开迁移。
  5. **前后端未联调**：H14 的教师页仍用注入的假实现，真实 `/relations` 与页面组合未在浏览器里端到端验证（K05 教师主线 E2E 的依赖）。

## 2026-09-27 批次：J05/I05/H09 独立审查 + #264 遗留四项 + 后端关系接口（协调者，5 路并行）

**断点事实（已核实，非推测）**：上一会话（Claude Code）已把 J05/I05/H09 实现完并开了三个 PR——**#290**（J05，分支 `claude/project-thread-bkxc2u`）、**#291**（I05，`...-98kaqt`）、**#289**（H09，`...-eo5fzo`）——三者 CI 六项全绿、可合并，缺的是**独立审查**与**合并**。另有两项新工作：#264（G05+G06）独立审查的 4 个遗留项（G05 交接「待决」列出）与「补关系接口」（H14 交接写明「后端尚无 `/relations` 路由」，故 H14 只能假 API 验证）。

**本批做法**：5 路并行子代理，各占独立 worktree/分支；协调者另做独立第二意见、冲突预判、逐项**亲手复现**子代理声称的鉴别性篡改，并在 `origin/main` 前移后重整集成。**并行期间远端被 Codex 会话推进**：`origin/main` 由 `ac21e5d` → `893f341`，其间合入 **#290（J05）**、#292（J06）、#293（J07）、#294（K03）；`#290` 合入的是**未含本批判修的版本**。

| 工作流 | 结果 | 独立审查结论 | 审查修复（分支上，未 push） |
| --- | --- | --- | --- |
| J05（PR #290，ADR-068） | 已被 Codex 合入 main（不含批修） | APPROVE_WITH_NOTES | `4bb0ca2`：补 `deadline` 类型/有限性用例（原篡改存活）、补「读取中链路到期」用例、`qa/__init__.py` 按 J03 惯例补导出、ADR-068 后果句按实测改为 `max_chunks × 8 + 2` 并落成断言；`db4e6ae` 更正证据数字 |
| I05（PR #291，ADR-069） | DONE | APPROVE_WITH_NOTES | `cf9bb66`：补「图读摘要/他课复核（热缓存下唯一生效）」与「查询串注入 `user_id` 不被信任」断言；未动实现 |
| H09（PR #289，ADR-070） | DONE | APPROVE_WITH_NOTES | `e2cc8c8`：钉住三栏空态文案互异、401 会话过期文案、`loadMore` 的 totals 口径、`changed=false` 的 fixture 自相矛盾、成环冲突后改选、双栏游标分栏；未动 `src/` |
| #264 遗留四项（ADR-072） | DONE | — | `9c5d753` sweep 接入 `run_loop` maintenance（`PUBLISH_SWEEP_INTERVAL_SECONDS`，缺省 3600、0 关闭、环境变量）；`b318172` 无实际贡献时不取课程写锁（新增 `task_has_contributions`）；`38b3dbd` 重跑不把 `approved`/`rejected` 降级回 `draft`；`03ab66b` 无来源手工节点详情 200 显式空态（**新增契约 `KnowledgePointDetailWithoutSource`**，保留 `KnowledgePointDetail.minItems:1` 与 B11 负例）；`6acaa1e` 文档 |
| 关系接口 F06-API（ADR-071） | DONE | — | `fbf163e` `api/relations.py` 三路由 + `edit_relation.py` + `graph_relation_edit.py` + F12 审计接入；契约未改 |

**集成与验证（协调者实测，最终集成分支 `claude/integration-0927` 已并入 `origin/main@893f341`）**

| 门禁 | 实测结果 |
| --- | --- |
| 后端全量 `pytest tests/backend -q` | **3434 passed / 27 skipped**，exit 0（`origin/main` 收集 3349；集成分支 3461，**+112** = J05 修复 +5、I05 +36、关系接口 +58、遗留 +13） |
| 契约全量 `pytest tests/contracts -q` | **295 passed**，exit 0 |
| 集成（真实 Neo4j 5.26.31，容器 `ss-neo4j-f11`） | 386 passed / 4 skipped / **2 failed**（下两项） |
| `./scripts/verify.sh` | **exit 0**（PASS contracts gate） |
| `./scripts/gen-contracts.sh --check` | 一致 |
| 前端 `type-check` / `build` | **exit 0** / **exit 0** |
| 前端 `test -- --run` | 623 passed / **1 failed**（`b02.test.ts` 既有 flake） |
| `git diff --check` | 干净 |

- **2 个集成失败已用 `origin/main` 对照证明为既有环境问题，非本批回归**（`origin/main@893f341` 上跑同两条：同样 2 failed）：`test_k08.py::test_images_build` 是 `docker compose build` 无法写 `~/.docker/buildx/activity/…`（**工作区沙箱拒绝越界写**，非代码）；`test_k10.py::test_an_unfenced_write_during_the_backup_fails_it[neo4j]` 的 hook 用硬编码口令 `x` 连 Neo4j，与本机容器口令 `testpassword1` 不符。
- **`b02.test.ts` 既有 flake 以超时证伪**（非坏）：`--testTimeout=90000` 下 **5 passed / exit 0**；CI 该 job 一直绿。CI 的 Frontend job 把 `type-check` 作为**独立无管道步骤**，退出码真实生效。
- **协调者亲手复现的鉴别力（不是转述）**：I05 去掉 `load_version_graph` 摘要复核 → `test_graph_read_revalidates_snapshot_with_warm_version_caches[digest-column]` 判红；H09 删 401 分支 → 新增用例判红（1 failed / 36 passed）；#264-R3 回退 `n.status = status` → `test_f13` 2 failed（approved + rejected，幂等仍绿）；#264-R2 删无工作早退 → 空清理解锁鉴别用例判红；关系接口删创建侧环检测 → 3 failed（含「409 + `details.cycle` + 零写入」）、删 PATCH 侧环检测 → 1 failed。每处复原后 `git status` 干净。

**环境事实（写给后续会话，均为实测）**

1. **不要把验证命令管进 `| tail`**：`npm run type-check` 在缺 `vue-tsc` 时直接跑 exit **127**、管到 `tail` 后 exit **0**（假绿）。worktree 里 `src/frontend/node_modules` 不会自动存在，需 `ln -s` 到主仓，否则前端命令静默假绿。
2. worktree 里的 `.venv` 是 editable 安装、`app` 包指向**主仓**：任何 worktree 跑 Python 测试必须带 `PYTHONPATH=$PWD/src/backend`，否则测的是主仓代码。
3. `tests/backend/test_relations_api.py` 与 `tests/integration/test_relations_api.py` 同名（同 F08～F13 惯例），**必须按目录分开跑**，否则 pytest import mismatch。
4. 本轮还发现并**纠正**两处子代理证据/判断偏差：I05 审查者与我各自独立发现「app 生成的 OpenAPI 把 500 记为 `Error`、契约真源为 `LearningIntegrityError`」（全局惯例，I02 同样，待统一）；J05 审查者报的 `test_j05.py 71 / 合计 140` 经实测为 **70 / 139（+5）**，已在其分支更正（`db4e6ae`）。另：**协调者给关系接口的任务书把 `DANGLING_ENDPOINT` 误写为 409**，子代理按 `errors.v1.md`（契约真源）**422** 实现并报备，判断正确。

**本批待决（需 ArvinHan）**

1. **推送与合并**：三个 PR 的批修提交、#264 四项、关系接口都**未 push**；集成分支 `claude/integration-0927` 已含全部五路且通过门禁。另注：#290（J05）已被上游合入，故 J05 的批修提交需要**新开 PR**。
2. **J06 的哨兵归属已实证**：`services/qa/citations.py` 里已有 `SENTINEL = "<<INSUFFICIENT_EVIDENCE>>"`，与 ADR-068 决定 2 及 Q11 表（J05 = 提示要求、J06 = Q3.3 状态机）一致——「哨兵无人认领」的疑虑**不成立**；仅 `docs/atomic-tasks.json` 的 J06 `acceptance` 未提 Q3.3，可补。
3. ADR-068～072 五条签收（含 J05 的 1024 输出上限与 0.25s 容差、I05 的图读已提交快照、H09 的数量口径、#264-R1 的 sweep 缺省启用与 3600 周期、#264-R4 的两种成功形状、关系接口的 503 未声明与 `source_pairs` 归零）。
4. 关系接口 5 项（503 未声明、两个未登记 `reason`、改向丢 `source_pairs`、审计行语义、**前后端未联调**）见上一节 ADR-071 待决。
5. `origin/main` 前移带来的新工作（#292 J06、#293 J07、#294 K03 及在开的 #295 J10、#296 K04）不在本批审查范围内，本批只保证与其集成后门禁通过。

## 2026-09-27 H10 发布历史和回滚 UI（Codex 认领）

| ID | 状态 | 任务 | 负责人 | 分支 / 基线 | 文件锁（本轮唯一写入者） | 验收 |
| --- | --- | --- | --- | --- | --- | --- |
| H10 | DONE（待 PR 审查/合并；issue #122） | 实现发布历史和回滚 UI | Codex（前端） | `codex/h10-version-panel` / `main@8741078` | `src/frontend/src/components/VersionPanel.vue`、`src/frontend/src/composables/useVersions.ts`、`tests/frontend/h10.test.ts`；扩围 `src/frontend/src/api/versions.ts`、`src/frontend/src/views/ReviewView.vue`、`src/frontend/src/main.ts`、`tests/frontend/h09.test.ts`（仅注入新增版本 API 测试桩）、相关规格/架构/ADR/交接（均已核对无在途文件锁） | 发布失败保持旧版本标识；草稿修订中学生仍见旧发布版；回滚确认前显示目标版本。 |

- 输入：G06 发布/版本列表/回滚 API 与 `GraphVersion`、`PublishResult` 契约，H09 教师工作流；输出：教师可见的版本历史、发布状态和回滚操作入口。前置 G06、H09 均已合入 `main`。
- 风险：发布/回滚与刷新并发时不得把在途或失败结果显示为已提交版本；回滚是前滚新版本号，确认前必须明确目标版本与影响。审核页嵌入版本面板的设计已获用户确认。
- 验证计划：`npm --prefix src/frontend run test -- --run ../../tests/frontend/h10.test.ts`、`npm --prefix src/frontend run type-check`、`npm --prefix src/frontend run build`、`./scripts/verify.sh`、`git diff --check`。
- 验收证据：H10 测试先因模块缺失红灯，接入页位置、成功响应刷新指针、课程教师权限及超时后暂停写入四项后续用例也各先红后绿；独立审查又发现权限丧失时残留旧 UI、历史列表缺当前版时误报成功，两项均先红后绿。最终 `h10.test.ts` 12 passed，H09+H10 49 passed，前端全量 19 files / 636 passed（B02 嵌套进程测试使用 `--testTimeout 30000`），type-check、build、`./scripts/verify.sh` 均 exit 0。前端仅 fake API 验证，真实服务联调交 K05。详见 `docs/handoffs/codex-h10.md`。

## 2026-09-27 I06 掌握标记与推荐 UI（Claude，worktree `impl-i06`）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| I06 | DONE（待 PR 审查/合并；issue 见原子清单） | 实现掌握标记与推荐 UI | ArvinHan（Claude） | `claude/impl-i06`（worktree `.worktrees/impl-i06`）/ `main@HEAD` | `src/frontend/src/composables/useLearning.ts`（新建）、`src/frontend/src/components/Recommendations.vue`（新建）、`tests/frontend/i06.test.ts`（新建）；扩围新建 `src/frontend/src/api/progress.ts`、`src/frontend/src/api/recommend.ts`，小改 `src/frontend/src/views/StudentGraphView.vue`、`src/frontend/src/main.ts`、`src/frontend/src/graph/lifecycle.ts`（`CanvasElementState` 增四个学习状态与样式）、`tests/frontend/h05.test.ts`（仅同步「状态名集合完全相等」断言，同 H10 先例）、`docs/decisions.md`（ADR-075）、本文件、交接 | `i06.test.ts` 39 passed（先红灯：模块缺失）；type-check、build exit 0；17 处反向篡改 15 处判红，另 2 处「单层篡改被第二层/按钮 disabled 兜住」已澄清并补强用例后判红；全量前端 675 passed（`--testTimeout=30000`）；ADR-075；**PR [#302](https://github.com/arvinhanye/SmartSketch/pull/302)**（rebase 到 `origin/main@481d3ff`，12 文件 / +2028 −7，CI 6/6 全绿）；`docs/handoffs/claude-i06.md` |

- 输入：I05 的 `GET /recommend`（`RecommendState` 闭集 `recommendations`/`all_mastered`、结构化 `reason_facts`/`weighted`）、I02 的 `GET/PUT /progress`（有效 `status`、`own_status`、`inherited_from[]`、`graph_version`）、H11 的学生图谱页；输出：节点掌握状态色 + 推荐高亮、掌握标记三态写入、可解释推荐列表。
- 验收对应：① 乐观标记失败完整回滚且固定文案（不回显服务端 `message`）；② 同一节点在途写入只发一次、按钮禁用；③ 切课用 `CourseRequestScope` + 序号隔离，课程 A 的迟到推荐/进度不写入课程 B；④ 理由逐条取自服务端 `reason_facts`/`weighted`，前端不重算 `score`；⑤ 只在已显示发布版本上读写，响应 `graph_version` 不一致即丢弃并重读图，422 `not_in_published_version` 撤销后重读进度；⑥ 未发布 404 空白态且不读图、教师 403 不给可点击入口；⑦ `all_mastered`/`recommendations` 两个 200 状态与 404/500 的区分，完整性错误只提示 `request_id`；⑧ 状态色由 `CanvasElementState` 驱动、颜色集中在 `buildGraphOptions`。
- **需签收（ADR-075）**：清单验收条目 5 的字面表述「PUT progress 请求带 `graph_version`」与契约冲突——`updateProgress` 的请求体是 `additionalProperties: false` 的 `ProgressUpdate[]`，该操作 `query` 为 `never`，后端 `write_progress` 也无版本参数。实现改为「只在已显示版本上写 + 响应版本比对 + 422 重读」，**不自造字段**（自造字段会被契约拒绝，未声明查询参数会被服务端忽略而给出虚假安全感）。另需签收：学习接口未注入时页面静默退回 H11 原状；掌握标记三态（未开始/学习中/已掌握）直接写 `MasteryStatus`，不引入第四种状态或「跳过先修」操作。
- 待决：真实后端联调（I02/I05 已合入 `main`，本轮仅假 API 验证）交 K06 学生主线 E2E；推荐列表上限未在页面暴露（用服务端默认 10）；进度变化后继承来源（`inherited_from[]`）未在 UI 展示（契约已具备，是否需要展开待定）。
## 2026-09-27 J09 课程问答页（Codex）

| ID | 状态 | 范围 |
| --- | --- | --- |
| J09 | REVIEWED / 待 CI 验证 | `src/frontend/src/views/ChatView.vue`、`src/frontend/src/composables/useChat.ts`、`src/frontend/src/components/ChatMarkdown.vue`：问答流展示、撤回、引用、历史、切课与版本标注。 |

- 审查修复：按 J08 `send` / `onEvent` 接口接入，保留 `done` 后才提交历史的规则。

## 2026-09-27 K06 / K09 / K11 / K12 与演示模型（Claude）

| ID | 状态 | 任务 | 负责人 | 分支 / 基线 | 证据 |
| --- | --- | --- | --- | --- | --- |
| K06 | DONE（待 PR 审查/合并；issue #145） | 学生主线端到端 | Claude | `claude/project-thread-sa7c37` / `main@adbe106` | `tests/e2e/student.spec.ts`：`scripts/e2e.sh tests/e2e/student.spec.ts` 1 passed（真实 API、worker、一次性 Neo4j、演示模型） |
| K09 | DONE（待 PR 审查/合并；issue #148） | 示例课程幂等导入 | Claude | 同上 | `scripts/import-demo.py`、`datasets/demo/`；`tests/backend/test_k09.py` 9 passed，`tests/integration/test_k09.py` 1 passed；实跑两次，第二次 `uploaded: []`、`publish_unchanged: true` |
| K11 | DONE（待 PR 审查/合并；issue #150） | 质量门禁 | Claude | 同上 | `scripts/verify.sh basic/full/integration`、`scripts/verify/gate.py` + `allowed-skips.txt`；`tests/tooling/test_k11.py` 18 passed；CI 新增 integration job；`./scripts/verify.sh full` exit 0 |
| K12 | DONE（待 PR 审查/合并；issue #151） | 运行手册与验收矩阵 | Claude | 同上 | `docs/runbook.md`、`docs/acceptance.md` |

- 顺带修复：`GET /courses/{cid}` 缺失导致课程页恒显示「课程加载失败」（`tests/backend/test_course_detail.py`）；从未发布课程的版本面板误报不一致（`tests/frontend/h10.test.ts` 新增用例）。
- 演示模型（ADR-076）：`LLM_MODE=demo`、`EMBEDDING_MODE=demo`，规则抽取 + 字符 n-gram 向量，无付费调用；`fake` 模式上传必失败，无法做端到端或验收。
- 本轮先写的 J08/J09/J10/K04/K05/I06 已被 Codex 同名 PR 先行合入，本分支已丢弃重复实现，只保留上述增量。
- **已签收**（ArvinHan，2026-09-27）：ADR-076（演示模型与 0.58 阈值）、ADR-077（门禁跳过白名单）、ADR-078（示例导入只增不删）。D-08 融合阈值仍待用户决定。
- PR #307 已于 2026-09-27 合并（main `8450256`）。
- 待人工：macOS 实测、`docker compose --profile app up` 真实守护进程验证（K08 遗留）、真实模型重跑 K02 验收 7 与 K04。详见 `docs/handoffs/claude-k06-k09-k11-k12.md`。

## 2026-09-27 一键启动演示环境（Claude，新增任务）

| ID | 状态 | 任务 | 负责人 | 分支 / 基线 | 证据 |
| --- | --- | --- | --- | --- | --- |
| DEMO-01 | DONE（待 PR 审查/合并） | 一键启动脚本 `scripts/start-demo.sh` | Claude | `claude/one-click-start-2ibfrb` / `main@86bb94d` | 云端容器从零（无 `.venv`、`.env`、`node_modules`）实跑：依赖安装、Neo4j、迁移、建号、导入 v1、前端 5173 就绪，经前端代理登录 `demo_student` 并看到已发布课程；第二次运行账号 `exists, unchanged`、导入 `publish_unchanged: true`；伪终端 Ctrl+C 后无残留进程 |

- 待人工：macOS 实测（脚本按 bash 3.2 写法编写，未在 Mac 上运行过）。详见 `docs/handoffs/claude-start-demo.md`。

| DEMO-02 | DONE（待 PR 审查/合并） | `scripts/start-demo.sh --live`：真实大模型一键启动 | Claude | `claude/real-model-setup-zxgnka` / `main@62eb8c7` | 缺 `LLM_API_KEY` 时退出 1；假密钥与不可达地址下全流程启动，网页上传后 worker 以 `deepseek-flash` 调用主用客户端（connection 失败，无付费调用）；详见 `docs/handoffs/claude-start-demo-live.md` |

- 待人工：在 Mac 上填真实 `LLM_API_KEY` 后上传一份资料，确认生成草稿图谱（付费调用）。

## 2026-09-27 前端改版（方向 A 工作台）+ 学生自助注册（Claude，新增任务）

| ID | 状态 | 任务 | 负责人 | 分支 / 基线 | 证据 |
| --- | --- | --- | --- | --- | --- |
| UI-01 | DONE（待 PR 审查/合并） | 前端改版方向 A「工作台」：登录后左侧导航；教师图谱编辑三栏；学生图谱右侧学习栏；问答页显示知识点名称、出处按章节与页码 | Claude | `claude/frontend-redesign-vzvfus` / `main@fccc1ca` | 方案对比页 https://claude.ai/artifact/KgH1oJ3mqxSaWhGwZxg3Qi（用户选定「A + 1」）；`tests/frontend/redesign-chat.test.ts`；真实页面截图 `/mnt/project-files/redesign-0927/` |
| AUTH-01 | DONE（待 PR 审查/合并；ADR-079 待签收） | 学生自助注册：`POST /api/v1/auth/register` 与 `/register` 页 | Claude | 同上 | `tests/backend/test_adr079_register.py` 14 passed；`tests/frontend/adr079.test.ts` 11 passed |

- 验收条件：① 未登录可打开 `/register`，登录页有入口，已登录访问回本账号首页；② 只建学生账号，请求体带 `role` 422 且零写入；③ 用户名大小写不敏感重复 409 `USERNAME_TAKEN`，页面在用户名下提示；④ 本地校验不过不发请求；⑤ 每进程 60 秒内 60 次，超出 429 带 `Retry-After`；⑥ 问答页知识点显示名称（取回答所依据的发布版），读取失败退回标识；⑦ 退出登录清会话回登录页。
- 顺带修复：`useChat` 直接改原始对象，`currentVersion` 不会更新（改为写响应式代理）。
- 待决：G6 画布在 64 个节点时整体缩得很小、标签难读（改版前已存在，未在本任务处理）；是否需要关闭自助注册的部署开关（ADR-079 后果）。详见 `docs/handoffs/claude-frontend-redesign.md`。

## 2026-10-01 dev-up.sh 启动诊断：Neo4j 起不来时说清原因（Claude，新增任务）

| ID | 状态 | 任务 | 负责人 | 分支 / 基线 | 证据 |
| --- | --- | --- | --- | --- | --- |
| DEMO-03 | DONE（待 PR 审查/合并） | `scripts/dev-up.sh` 端口预检、退出/反复重启/口令不一致立即报告、失败时打印容器状态与日志及对症提示；`unhealthy` 等到截止时间 | Claude | `claude/project-thread-diyack` / `main@2a67189` | `tests/tooling/test_dev_up_diagnostics.py` 8 passed（改前 7 failed）；F01/K07 回归通过；真实 Docker 29 + Neo4j 5.26.31 实跑内存超限、端口被占、口令不一致、正常启动四种情形，详见 `docs/handoffs/claude-dev-up-diagnostics.md` |

- 起因：用户在 macOS（Intel，Docker Desktop 29.8）运行 `scripts/start-demo.sh`，只得到「Neo4j 健康检查失败」。实际原因两个：另一个目录里的 SmartSketch 副本的 Neo4j 容器（`smartsketch-neo4j-1`）一直占着 7474/7687；本目录的 Neo4j 数据/日志在反复崩溃后留下坏状态，以退出码 3、无 ERROR 反复重启。停掉另一份、换全新数据卷后启动成功（2026-10-01 用户确认）。
- 验收条件：① 容器未运行且端口被占时不启动容器、给出 `lsof` 命令；② 容器停在 created/exited 或重启次数增加时立即失败，打印 Docker 报错、退出码与最近 40 行日志；③ 认证被拒时立即失败并说明口令只在首次初始化生效，输出不含口令；④ `unhealthy` 不立即失败，截止时打印最后一次连接输出；⑤ 正常启动行为不变。
- 已排除：「桌面」目录挂载（改用 Docker 卷后照旧退出）；镜像、APOC、内存设置（原版镜像三组对照在该 Mac 上都正常）。坏状态的具体文件未定位，数据已随旧卷删除。


## 2026-10-03 Codex 接手计划 B（c85ee53）

| ID | 状态 | 负责人 | 范围及验收 |
| --- | --- | --- | --- |
| B-TAKEOVER | DONE（本地修复/完整门禁；96f3885 实测已复核） | Codex | 复审 5a34fec..56610d4、修复推荐按钮及确认缺陷、L15、QA 2048；最终稳定代码 integration 门禁；真实模型只交 DeepSeek |
| L15 | DONE（本地闭环与真实测量复核；有保留） | Codex | 课程内角色导航、阶段下一步、入课空态、课程隔离/恶意文本、个人模式双课程 E2E |

输入：claude-plan-b-handoff-to-codex.md 与 c85ee53 文档提交。输出：修复、测试、Codex 审查和 DeepSeek 交接。依赖：现有接口/本地演示与假供应商；风险：切课/换号迟到响应、1024->2048 延迟费用待实测。验证：最小前后端回归、type-check/build、./scripts/verify.sh integration、git diff --check。文件所有权：本轮 Codex 顺序修改相关前后端、契约和文档；不写 Claude 工作树，不推送不合并。旧 Codex 工作树基线较早且有文档改动，保留；新托管 worktree codex/plan-b-takeover 基于 c85ee53。

验收证据（Codex，最终稳定代码）：./scripts/verify.sh integration 整体 exit 0；后端3780 passed/27白名单skip，前端901 passed，集成393 passed/4白名单skip，图库44 passed，演示E2E2 passed、个人假供应商E2E4 passed（包含两课程隔离）；type-check/build与契约门禁均通过，git diff --check exit0。独立 D/N 后端116与前端107均通过。报告 docs/reviews/codex-plan-b-c85ee53.md；接手交接 docs/handoffs/codex-plan-b-takeover.md；真实模型交接 docs/handoffs/codex-plan-b-deepseek-qa.md。

2026-10-03 收尾更新：96f3885 的 L15-6 Step4 真实 QA 已执行并由 Codex 对照 HTTP/只读日志核验：10题=7回答/1截断错误/2课外未覆盖，全部≤15秒；回答成功率7/8，不是抽取准确率；已回答首个delta全超3秒。生成累计648168/5000000，向量累计11943另计。补齐失败题关联与19条调用证据，测量脚本存在时间字符串筛选漏行与两类预算混算（正式报告总量正确）。报告 docs/reviews/codex-plan-b-96f3885-closeout.md，交接 docs/handoffs/codex-plan-b-closeout.md。第二阶段功能交付已收尾；L11-7、抽取准确率/60秒和QA质量/首字目标保留OPEN，不推送不合并不快进冲刺分支。


## 2026-10-03 Codex 认领：第二阶段收尾（96f3885）

| ID | 状态 | 负责人 | 范围及验收 |
| --- | --- | --- | --- |
| B-CLOSEOUT | DONE（证据复核/本地门禁/状态与交接完成） | Codex | 复核 96f3885 十题证据、日志关联、预算和出处；补齐可移交证据；区分功能闭环与性能/质量未达标；更新任务状态与收尾交接 |

输入：96f3885、L15 脱敏证据、既有本地 SQLite（仅只读查询允许字段）、计划 B/L11-7 交接。输出：Codex 审查报告、脱敏核验产物、第二阶段状态及后续待办。依赖：257750e 功能基线和个人模型实测；风险：HTTP 错误与 chat_logs 字段混用、首字口径不是浏览器 SSE、预算汇总漏计中断调用、将未测项误标通过。验证：只读证据核验脚本、相关 D/L 回归、./scripts/verify.sh full、git diff --check。只编辑本 worktree 的 docs/specs/evaluation 核验产物；不改 DeepSeek 原始报告，不调用真实模型，不修改数据、接口或部署配置，不推送不合并。


### 第二阶段收尾后的显式待办（不是已实施的计划 C）

| ID | 状态 | 下一阶段归属 | 验收/首个动作 |
| --- | --- | --- | --- |
| B-EVAL-01 | OPEN | L16 / 待认领 | 固定测量脚本：错误 details.request_id、毫秒时间边界、生成/向量分账、未知 usage；离线负例先测，真实 SSE 首字单独抓取 |
| B-QA-01 | OPEN | L16 / 待认领 | 比较题2048仍截断；研究短答案/上下文和首字分段延迟，不放宽出处/15秒；模型付费复测仍交 DeepSeek且先确认新预算 |
| B-PDF-01 / L11-7-real | OPEN（未收到复测报告） | L11 验收留项 / DeepSeek待接手 | 两份PDF headings/2真实复测；执行前最新生成起点648168（或最新值），旧850000累计止损余201832；预算临界先确认，不自动调额 |
| B-QUALITY-01 | OPEN | L16 / 待认领 | 未改写抽取快照人工评估实体/关系准确率≥70%；抽取≤60秒旧四份全部未达；数量/类型达标不替代准确率 |
| B-INTEGRATE-01 | WAITING_USER | 发布集成 | 当前本地 codex/plan-b-takeover 保留，推送/PR/合并方式及目标分支由用户决定；不自动清理测量数据 |

无新接口、数据模型、迁移、依赖或业务改动。下一阶段范围沿用L16–L19，先质量/性能再美化与材料，不在收尾时增加自动出题或管理员统一模型功能。

收尾验收证据（Codex本轮）：./scripts/verify.sh full 整体exit0，后端3780 passed/27白名单skip，前端901 passed，type-check/build/契约通过；D1/D2/D3/L15/PDF-reflow定向56 passed；只读关联核验十题+额外尝试/19调用通过；git diff --check通过；DeepSeek原始三文件未改。此次无新的真实调用、未重跑integration/E2E，257750e的完整integration仅作为既有代码证据。完整命令、日志、限制和后续首个动作见docs/handoffs/codex-plan-b-closeout.md。


## 2026-10-03 Codex：第三阶段启动交接 prompt

| ID | 状态 | 负责人 | 范围与验收 |
| --- | --- | --- | --- |
| C-HANDOFF-01 | DONE（prompt/范围记录/基础验证完成） | Codex（规划交接） | 基于9ca6e88/第二阶段收尾，交付Claude启动prompt；九类参赛材料从第三阶段暂缓；保留质量/性能/技术验收与预算边界，不实施业务修复 |

输入：用户第三阶段范围调整、codex-plan-b-closeout.md、codex-plan-b-96f3885-closeout.md与已知待办。输出：docs/handoffs/codex-claude-plan-c-start-prompt-2026-10-03.md、ADR-088范围记录、看板状态。依赖：现有第二阶段基线和未完成验收；风险：将推送/合并/付费调用误作已授权、把材料暂缓误作取消技术证据、交接旧工作树代码。验证：引用路径/预算/排除项断言、./scripts/verify.sh basic、git diff --check。仅本工作树文档改动；Claude先提交原子计划供用户确认，真实生成/向量测试继续交DeepSeek。

第三阶段范围覆盖更新（用户2026-10-03确认，ADR-088）：此前收尾清单里“美化与材料/运行材料”的材料部分现在暂缓，九类参赛材料不进入第三阶段验收。B-EVAL-01/B-QA-01/B-PDF-01/B-QUALITY-01仍OPEN；L17轻量美化以主线稳定为前置，L19保留隔离技术复测。内部技术证据/测试/人工判定/预算与交接仍须完成。启动prompt：docs/handoffs/codex-claude-plan-c-start-prompt-2026-10-03.md；Claude未被工具派发，先核9ca6e88基线、提交原子计划，获用户确认再实施。不新增模型调用、合并/推送、环境/数据同步授权。

C-HANDOFF-01验收：启动prompt含六个技术任务、八个已存在证据引用和最新预算边界，路径/范围/预算断言通过；./scripts/verify.sh basic整体exit0，日志/private/tmp/plan-c-prompt-basic.log；git diff --check通过。仅修改本工作树交接、任务、决策文档；未运行full/integration、未修改业务代码或数据、未调用模型。此处交付供用户转交的prompt，尚未向Claude会话发送，也未启动第三阶段实施。

## 2026-10-03 Claude 认领：冲刺计划 C（第三阶段：可靠性、性能与技术冻结）——用户已确认

计划：`docs/superpowers/plans/2026-10-03-contest-sprint-c-reliability-performance.md`。工作区 `/Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34`，分支 `claude/plan-c-reliability`（用户确认自 `ec1291a` 新建，包含 `9ca6e88`）。九类参赛材料暂缓（ADR-088）；美化轻量化，技术达标后由用户另开前端设计任务。本会话不发真实生成或在线向量请求，付费测量交 DeepSeek 并先确认预算（生成累计 648168 / 5000000，向量 11943 另计）。

| ID | 状态 | 负责人 | 范围 | 验收 |
| --- | --- | --- | --- | --- |
| C01（B-EVAL-01） | DONE（已复审；Codex修复续跑预检） | Claude/Codex | 测量工具：错误编号、毫秒时间边界、生成/向量分账、未知 usage、分位统计、SSE 首字三列口径 | 离线重算 11 请求 / 19 调用 = 9+10、生成 28951、向量 59；`tests/tooling/test_c01_measure.py` |
| C02（B-QA-01） | IN_PROGRESS（13题真实终态/服务端与SSE达标；浏览器可见首字、v3+思考开启基线：2026-10-04 用户决定三项补测均不做，保持「未测」） | Codex（本地接手）；DeepSeek（真实轮） | 比较题截断离线定位、最小修法（策略先确认）、分段耗时、真实复测交接 | 出处与 15 秒不放宽；截断仍撤回；回归 |
| C03（B-PDF-01 / L16） | IN_PROGRESS（新两份PDF20.90/28.08秒已核；关闭思考MD抽取：2026-10-04 用户决定三项补测均不做，保持「未测」；慢段根因仍OPEN） | DeepSeek（真实轮）；Codex（本地复审） | 修复后 PDF 真实复测、阶段分解、60 秒最小优化 | 前后对照；不排除真实 AI 耗时 |
| C04（B-QUALITY-01） | DONE（2026-10-04 用户签收新两份 PDF：两课实体、关系均 ≥70%；复核后采纳辅助判定，见 C-ACC 证据） | Claude（工具与辅助判定）；用户（人工签收） | 未改写快照与新快照分别抽样判定 | 实体、关系各 ≥70%（人工） |
| C05 | DONE（待复审；视觉美化移出本阶段） | Claude | 未保存编辑时的搜索定位、问答长来源折叠、视口外解锁节点定位、PDF+MD 重复上传提示 | 失败测试先红后绿 |
| C06 | IN_PROGRESS（本地完整门禁已通过；真实冻结待指标/人工签收） | Codex | 最终门禁、隔离从零复测、交接 | 整次 integration 实际 exit 0 |

- 2026-10-03 C00 基线：`git switch -c claude/plan-c-reliability ec1291a`（用户确认的方式；旧分支保留在 `c85ee53`）。`./scripts/verify.sh basic` exit 0（`env -u LLM_MODE -u EMBEDDING_MODE`）。
- 2026-10-03 **C01 完成**：`measure_web_flow.py` 新增 `audit` 子命令、`ask --stream/--out/--audit-db/--cap`。错误编号兼容 `details.request_id`；按 UTC 时刻的 `[since, until)` 窗口或固定请求 ID 关联；生成与向量分账；未知 usage 不当 0，止损遇未知即停；最近秩分位并注明分母；首字三列口径。离线重算 L15：11 请求、19 调用 = 9+10、生成 28951、向量 59。`tests/tooling/test_c01_measure.py` 22 passed（17 例先红），`tests/tooling` 97 passed，`verify.sh basic` exit 0。交接 `docs/handoffs/claude-plan-c-c01.md`。
- 2026-10-03 **C02-1 诊断完成**（`evaluation/reports/c02-qa-diagnosis.md`，离线、零调用）：可见回答每字 2.9～17 个输出 token，首个 delta ≈ 生成耗时。推断为模型的不可见推理吃掉 2048 预算并推迟可见内容；兼容客户端只读 `delta.content`。输入侧不是主因（平均输入约 2085 token）。修法 A（推理埋点）/B（思考控制）/C（提示词 v3）/D（思考提示）**待用户决定**。**C02-3 完成**：`audit` 逐请求给出查询向量 / 生成 / 其余三段耗时（现有字段，无迁移），`test_c01_measure.py` 新增 2 例先红后绿，共 24 passed。
- 2026-10-03 **C02-2 完成**（用户选 A+C）：ADR-089（`0469bad`）。A：迁移 017 + 推理字数 / 推理 token / 首次推理与首次可见内容时刻，只计量不存正文，回答与 SSE 不变（`33177c0`）。C：提示词 v3（`088a601`）。测量工具读推理列、`--round-started-at`、`audit-task`（`e709ccb`）。后端全量 3825 passed / 27 skipped。交接 `docs/handoffs/claude-plan-c-c02.md`；DeepSeek 交接 `docs/handoffs/claude-plan-c-c02-4-deepseek-qa-retest.md`（止损 45000）、`docs/handoffs/claude-plan-c-c03-1-deepseek-pdf-retest.md`（course2 PDF，止损 110000），**需用户安排带本分支代码与测量数据的环境后执行**。
- 2026-10-03 更正：第三阶段交接文件统一用 `claude-plan-c-` 前缀（`claude-c02.md` 等旧名属于原子清单同号任务；本轮写交接时曾误覆盖 `claude-c02.md` 的工作区副本，未提交，已原样恢复）。`claude-c01.md` 改名为 `claude-plan-c-c01.md`。
- 2026-10-04 **DeepSeek C02-4（`16d9ebd`）与 C03-1（`72fed5e`）完成，Claude 复核** `docs/reviews/claude-deepseek-c02-4-c03-1.md`：
  - C03-1：PDF 修复生效（关系 25→59、`PREREQUISITE` 0→5、孤立 39→3），83522 token、91.34 秒，仍超 60 秒。抽取输出 80% 是推理，两次关系调用推理用满 4096 导致 2 次 repair；末段 15.6 秒非模型时间未归因。
  - C02-4：只测 1 题（冷启动首问超时；8.15 秒无调用记录的空档未归因），因 usage 未知止损规则过严提前停止（工具问题，Claude 负责）。
  - 累计：记录口径 731690，系统计费口径 743806（含 1 次未知调用估算 12116），均在批准上限 803168 内；向量 11946 另计。
- 2026-10-04 用户决定：进入方案 B（思考控制），批准探测预算 5000；course1 PDF 等 B 完成后再测。探测工具 `evaluation/probe_thinking.py`（`8f0fc14`，`tests/tooling/test_c02b_probe.py` 7 例先红后绿）；DeepSeek 交接 `docs/handoffs/claude-plan-c-c02b-deepseek-thinking-probe.md`（5 个变体，最坏 4110 token，直连不进 `model_calls`，需手工记账）。
- 2026-10-04 离线推进（等待方案 B 探测期间）：测量工具止损改用系统计费口径（`312cccb`）；问答准备与 worker 阶段耗时日志（`f8c549f`，后端全量 3838 passed / 27 skipped）；**C05 完成**：C05-1 `ce378bc`、C05-2 `1a8da3f`、C05-3 `c7f15e4`、C05-4 `3101b54`，前端全量 911 passed、type-check 与 build 通过。交接 `docs/handoffs/claude-plan-c-c05.md`。
- 2026-10-04 **C04-1 工具与工作表**：`evaluation/draft_to_predictions.py`（草稿 → K01 predictions + 判定工作表）与 `evaluate_extraction.py judge-report`（无金标只按人工判定算硬指标；`claude-assist` 判定标为非人工验收），`tests/tooling/test_c04_accuracy.py` 7 例（先红）。三份当前版本草稿（course1 MD 75/66、course2 MD 71/55、course2 PDF headings/2 74/59）均 ≤100，按 README §6.2 **全量检查**，工作表在 `evaluation/raw/c04/`。修复前的两份 PDF 草稿已被 headings/2 取代，不再判定。**人工判定待用户**；Claude 辅助判定可按需先做（标 `claude-assist`）。
- 2026-10-04 **计划 C 移交 Codex**：交接 `docs/handoffs/claude-plan-c-handoff-to-codex.md`。已完成 C00/C01/C02-1～3/C05 与 C04-1 工具；DeepSeek 已完成 C02-4（只测 1 题）、C03-1、C02b 探测。**方案 B（ADR-090）已实现但未提交**：后端全量 1 failed / 4153 passed / 27 skipped，失败为 `test_c02_reasoning.py` 写死「最后迁移为 017」的断言；前端全量与整次 integration 未跑。未完成：方案 B 收尾与真实验证（需新预算）、C02-4 重跑、C03 两段未归因时间与 60 秒、C04 人工判定、C06 门禁与冻结。预算（系统计费口径）746357 / 5000000，批准上限 803168 余约 56800。

## 2026-10-04 Codex 认领：计划 C 接手复审

| ID | 状态 | 负责人 | 范围及验收 |
| --- | --- | --- | --- |
| C-TAKEOVER | DONE（本地接手/修复/完整门禁；整阶段仍OPEN） | Codex | 082323a 基线与 Claude 16 个未提交文件的 SHA-256 一致副本；复现迁移断言失败、复审 ADR-090 全调用链、修复确认缺陷、隔离完整门禁、审查与下一轮真实测量交接 |

输入：claude-plan-c-handoff-to-codex.md、计划 C、ADR-089/090、DeepSeek 三轮脱敏结果。输出：本地修复、回归、Codex 报告/交接。依赖：现有 Python/Node 依赖与本地假供应商、一次性 Neo4j。风险：旧迁移升级、开关快照/缓存/连接测试不一致、真实性能结论越界、误写实测数据。验证：test_c02_reasoning/test_c02b_disable_thinking、相关前端回归、contracts、./scripts/verify.sh integration、git diff --check。文件所有权：Codex 顺序编辑独立 codex/plan-c-takeover；源工作区/旧 Codex 工作区保留。未复制 .env、数据库或真实凭据；本轮不发真实生成/在线向量请求，不推送不合并。当前系统计费累计 746357，旧批准上限 803168（剩56811），新实测先确认预算。


### Codex接手后的显式待办（2026-10-04）

| ID | 状态 | 负责人/下一步 | 验收 |
| --- | --- | --- | --- |
| C-MINOR-01 | DONE（本轮RED→GREEN，72f7430） | Codex | 已收到usage后失败/中断仍保存usage_reasoning；增加回归，保持总计费不变 |
| C-MINOR-02 | DONE（本轮RED→GREEN，a6b19b7） | Codex | 长出处A展开后切B重置折叠，保留纯文本/正确引用与文件名 |
| C-REAL-B | DONE（88f9f6f实测已接手；准确率另项） | DeepSeek实测/Codex只读复核 | 两份PDF20.90/28.08秒、13题11answered/2not_covered；系统746357→844451/累计900000，向量12005另计；不要重复花钱 |
| C04-SIGNOFF | DONE（用户 arvin 签收，复核后采纳 claude-assist 263/263；整阶段仍 OPEN） | 用户人工判定 | 新两份PDF工作表全量：course1实体76/关系61，course2实体68/关系58；各≥70%；辅助仅claude-assist，旧快照另存 |
| C-LEGACY-CREDENTIALS | OPEN（仅交接提示，未读取内容） | 原数据持有人 | 收紧旧测量口令文件权限、按需轮换，停止沿用硬编码口令/未知usage记0的旧脚本；不复制进新工区 |

已修C-R1：同轮达到cap后续跑不再先发一次付费问答，新增两例RED→GREEN；仍需保守留足单题/并发在途余量，不能将题前题后检查宣传为严格预留的全局硬上限。旧报告中reasoning_tokens=null必须保留“未返回”语义。当前真实生成/在线向量调用0，新旧实测原始文件保留。

2026-10-04 用户明确选择：本地收尾后再确认真实测量预算。本轮继续仅本地修复/验证，不执行DeepSeek真实轮，不使用旧余额自动开跑。


C-TAKEOVER验收：最终稳定代码树 `./scripts/verify.sh integration` exit0，backend+tooling3862 passed/27登记skip；frontend37文件913 passed；integration393 passed/4登记skip；backend-live44 passed；演示E2E2 passed；个人假供应商E2E4 passed（教师/学生开关保存刷新、抽取问答、取消/鉴权终止、两课隔离）；type-check/build/basic契约通过。定向推理/开关22 passed、测量54 passed、契约全量296 passed；git diff --check通过。报告 `docs/reviews/codex-plan-c-takeover.md`；接手 `docs/handoffs/codex-plan-c-takeover.md`；下一轮准备 `docs/handoffs/codex-plan-c-deepseek-next-round.md`。不把注册SKIP当PASS；无新增skip/删测试/依赖升级；真实调用0，源Claude工作区和旧实测数据保留。用户明确本地收尾后再确认预算，阶段C保持OPEN。

## 2026-10-04 Codex：计划 C 真实结果接手

| ID | 状态 | 负责人 | 范围/验收 |
| --- | --- | --- | --- |
| C-REAL-CLOSEOUT | DONE（本轮范围；整阶段仍OPEN） | Codex | 只读复核88f9f6f的PDF/QA/预算及耗时证据；按RED→GREEN修复两项Minor；对照缺口/预算方案；本地完整门禁与更新交接，整阶段仍OPEN |

输入：deepseek-plan-c-to-codex及指定四份交接/报告、95e0797本地代码；输出：Codex脱敏审计产物/归因与复核报告、Minor修复、本轮验收与待签收项。依赖：测量SQLite仅mode=ro+query_only白名单、已存JSON/日志、既有依赖/本地假供应商。风险：统计分母或轮数误写、日志被后续启动替换、推理null误作0、共享库误写/付费误触发。验证：只读审计、两项定向回归、./scripts/verify.sh integration、git diff --check。本轮仅codex/plan-c-takeover写入；测量分支不合并，旧证据不修改，真实调用0。

### 真实结果接手时已确认与仍 OPEN（88f9f6f，历史状态；最新状态见顶部与验收修复节）

- stage_c_status: **OPEN（准确率未签收，未冻结）**。本轮付费生成/在线向量均0，不推送、不合并。报告`docs/reviews/codex-plan-c-88f9f6f-closeout.md`；交接`docs/handoffs/codex-plan-c-real-closeout.md`；可复现数值/哈希`evaluation/raw/codex-plan-c-closeout/audit.json`。本节取代上轮“待预算/尚未实测”的当前状态，旧历史记录不删除。
- PDF两份68/58、76/61；四关系、DAG、候选来源68/68与76/76已核；QA13题、11answered/2not_covered、无错误/截断/撤回、比较题3重复均answered；浏览器可见首字仍未测。
- 真实累计**844451/900000，剩55549**；向量**12005**另计；unknown新增0。旧746357/803168余额已过时。只读复核总增量98094，无第四项未解释开销；原报告部分中位数、answered分母、15.6秒轮次/来源标签解释在Codex报告校正，原证据不改。
- Minor01后端18 passed；Minor02前端16 passed；新增8后端/4前端参数例与既有ChatView切换断言，先RED后GREEN，不删用例/不放宽断言。

| ID | 当前状态 | 下一步/判定边界 |
| --- | --- | --- |
| C-PERSIST-TRACE | OPEN（证据不足） | 6471ms只能定位run_persist_stage范围；现存日志缺阶段行；旧C03-1末段15.643秒根因仍未判定，未在本轮同幅重现不是已修 |
| C-QA-V3-BASELINE | NOT_EXECUTED（2026-10-04 用户决定三项补测均不做；结论只写「未测」，不能声称关闭思考带来的改善幅度） | 最小同13题v3思考开启未测；保守11调用118052，13调用+余量182056；建议增量185000/累计1030000仅提案，无授权不执行 |
| C-MD-THINKING-OFF | NOT_EXECUTED（用户决定不补测） | 关闭思考的新 Markdown 抽取未测；已有 MD 课程 QA 不是新 MD 抽取证据；PDF ≤60 秒不外推 |
| C-BROWSER-FIRST-TOKEN | NOT_EXECUTED（用户决定不补测） | 浏览器可见首字未测；SSE783～2927ms不替代页面首字 |
| C-PERSISTED-SOURCES | DONE（C-ACC-A 已存只读证据，草稿限定） | 两课草稿详情 76/76、68/68 来源可定位/同课；不证明语义正确，不外推发布副本 |
| C06-FREEZE | WAITING_USER_FREEZE / OPEN | 准确率已签收、三项补测决定不做；修复后由用户自行检查并决定冻结，当前不冻结 |

完整门禁/新上下文审查已按本轮实际结果在末节登记；不能引用旧通过代替当前证据。九类参赛材料、美化、凭据文件处理仍不扩围。

本轮首个完整门禁exit1：个人假供应商E2E3passed/1failed，其他层通过。失败trace/API明确应用连接测试429、Retry-After3；共用teacher六次连接测试触发5次/60秒滚动窗口。只修本机测试夹具调度`3742a4e`，17新增例先RED13failed/4passed，后与来源回归共33passed；非本机发请求前阻断、预算/认证不重试、应用429最多尊重Retry-After再试一次，不放宽生产限流或原断言。第二次实际结果见后文；首轮为失败，不把部分通过算整次PASS。

第二次完整门禁仍exit1：全部运行用例通过，但测试替身headers联合类型引出5处TS2345。单独type-check REDexit2→测试替身显式字典声明`043c274`→完整frontend类型/38文件934测试/build exit0；无any/type断言、删检查或改运行逻辑。第三次整次integration最终exit0见下方验收；前两次exit1保留，不合并部分通过为整次成功。

**C-REAL-CLOSEOUT 本轮验收**：043c274稳定代码树整次`./scripts/verify.sh integration` **exit0**；backend+tooling3870passed/27登记skip，frontend38文件934passed，integration393passed/4登记skip，backend-live44passed，演示E2E2passed，个人本机假供应商E2E4passed；basic/type-check/build通过。无新增skip、删用例、放宽断言或依赖升级。新上下文只读审查Critical0/Important0，1项文档误标已校正；后发现测试夹具问题一次修复通路含类型校验修正，RED→GREEN与最终完整门禁给证据。只读审计exit0，源88f9f6f证据/分支未改，付费生成/在线向量均0；本地提交72f7430、a6b19b7、3742a4e、043c274，不推送不合并。台账仍844451/批准900000、向量12005另计；准确率/基线/浏览器/MD/来源详情/慢段根因边界分别保留OPEN。**stage_c_status: OPEN；未技术冻结**。

## 2026-10-04 Claude 认领：计划 C 验收收尾（stage_c_status: OPEN，technical_freeze: NOT_PERFORMED）

执行工作区 `/Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34`，分支 `claude/plan-c-acceptance`（用户确认自 Codex `4a6308b` 新建，含完整门禁提交 `043c274`）。上轮未提交的方案 B 文件已由 Codex 原样采纳，备份为 `claude/plan-c-b-wip-backup@2692648`，不合并。测量区 `smartsketch-c03b-measure@88f9f6f` 严格只读。本轮不发真实生成或在线向量调用。

| ID | 状态 | 范围 | 输入 → 输出 | 风险 | 验证 |
| --- | --- | --- | --- | --- | --- |
| C-ACC-A 持久化出处只读核验 | DONE（`a094714`） | 两门课（course1 PDF 76 点、course2 PDF 68 点）草稿持久化后的 `source_refs`：数量、同课文档与 chunk、页码或章节、悬空 / 跨课 / 空出处；区分 `source="ai"` 与 `source_refs` | 共享 Neo4j（只读会话，连接变量按用户授权从测量区 `.env` 载入进程、不打印不写盘）+ 测量区 SQLite（`mode=ro`）→ 脱敏报告与证据（只含编号、计数、哈希） | 误写共享库：只读会话 + 只读 SQLite 双重防护；凭据泄露：不打印、不落盘 | 脚本退出码、计数断言、可复跑 |
| C-ACC-B 入库子步骤计时 | DONE（`4304fec`） | `run_persist_stage` 子步骤脱敏计时（候选读取、构建、来源读取、锁等待、Neo4j 事务、SQLite 收尾、释放） | 代码 + 回归 → 本地提交 | 改变锁 / 事务语义：只加计时、不改控制流 | 先红后绿；相关回归；完整门禁（隔离端口、临时库、本机假供应商） |
| C-ACC-C 人工签收入口 | DONE（`452d446`）；用户已签收（见下方证据） | 两份工作表的签收模板与 `judge-report` 命令；Claude 辅助判定另存并标 `claude-assist` | 测量区 predictions（只读复制哈希核对）→ 签收入口与辅助判定文件 | 辅助判定被当作签收：文件与报告均标非人工验收 | 哈希一致；`judge-report` 可运行 |
| C-ACC-D 补测决策表 | DONE（提案）；2026-10-04 用户决定三项补测均不做 | 浏览器可见首字、关闭思考的 Markdown 抽取、v3 + 思考开启 13 题基线 | Codex 报告预算 → 决策表（只提案） | 提案被当授权 | 文档审阅 |

**C-ACC 验收证据**（本轮真实生成 0、在线向量 0；台账仍 844451 / 900000，向量 12005 另计）：

- **A**：`evaluation/audit_persisted_sources.py` 走 API 知识点详情同一路径（草稿、教师，Neo4j 读路由，SQLite `mode=ro&immutable=1` + `query_only`）。实际 exit 0、`defect_items: 0`：course1 76/76、course2 68/68 个 AI 知识点详情都有可定位的本课 `source_refs`（79 / 76 条，均带页码、章节、文件名），悬空块、他课文档、跨课证据边、读取失败均为 0；测量库前后 SHA-256 一致。报告 `evaluation/reports/c-acc-a-persisted-sources.md`，证据 `evaluation/raw/c-acc-a/sources.json`，测试 `tests/tooling/test_c_acc_sources.py` 5 passed（红灯阶段只是「工具文件不存在」，行为断言首次运行即通过，照实记录）。只证明可定位与课程隔离，不证明出处语义正确。
- **B**：`run_persist_stage` 新增一行 `persist steps` INFO（candidates / plan / chunks / lock_wait / lease_check / neo4j + neo4j_attempts / t6 / lock_release / task_release / total），只记任务编号、结果、毫秒数与次数。`tests/backend/test_c02_phase_logs.py` 新增 3 例：RED 3 failed / 3 passed → GREEN 6 passed，覆盖成功、锁未获取、Neo4j 失败与租约丢失。锁、事务、重试、预算与业务语义不变。**只为以后的运行提供归因能力；course1 6471 ms 与旧 15.643 秒的根因仍 OPEN，不做事后归因。**
- **C**：`evaluation/raw/c04-signoff/`：原样复制的两份 predictions 与工作表（SHA-256 与测量区一致）、初始为空后由用户 arvin 签收的判定文件（最新结果见下方 C04 签收登记）、`claude-assist` 辅助判定（`is_human_judgment: false`）与签收说明。辅助参考数 course1 实体 64/76、关系 58/61，course2 实体 61/68、关系 45/58（离 70% 差 5 条），**不是人工验收，不宣布达标**。
- **D**：`evaluation/reports/c-acc-d-retest-decisions.md`：浏览器可见首字（先免费测前端附加时延，再选 3 题真实，52016 落在现剩 55549 之内）、关闭思考的 MD 抽取（course1 一份，建议 95000 / 940000，不发布、向量 0）、v3 + 思考开启（沿用 Codex 185000 / 1030000，A/B 352000 / 1200000）。均未执行。
- **门禁**：`4304fec` 代码树在无 `.env` 的临时工作树、隔离端口、一次性 Neo4j、临时库、本机假供应商下整次 `./scripts/verify.sh integration` **exit 0**：backend+tooling 3878 passed / 27 登记 skip；frontend 38 文件 934 passed；integration 393 passed / 4 登记 skip；backend-live 44 passed；演示 E2E 2 passed；个人本机假供应商 E2E 4 passed；basic 契约、type-check、build 通过。相对 `043c274` 多 8 例（A 5 + B 3），无新增 skip、删用例或放宽断言。最终树 `./scripts/verify.sh`（basic）exit 0。交接 `docs/handoffs/claude-plan-c-acceptance-closeout.md`。**stage_c_status: OPEN；technical_freeze: NOT_PERFORMED**。
- **C 补充（签收填写工具）**：用户要求「在工作表里填 ✓ ✗」。新增 `evaluation/c04_signoff.py`（`init` 生成 `*-worksheet-user.md` 副本，`convert` 校验后写 `*-judgments-user.json` 与 `*-report-user.json`）；原工作表与 predictions 不动。未填、非法标记、判 ✗ 无依据、判定人为空或以 `claude-assist` 开头、改动其他列一律拒绝且不写文件。`tests/tooling/test_c04_signoff_sheet.py` 12 例：先以占位模块 RED（2 failed / 10 errors，均为 NotImplementedError）→ GREEN 12 passed（连同 `test_c04_accuracy.py` 共 19 passed）。真实两课副本用辅助判定在临时目录试填，转换结果与辅助数逐条一致（263 行全部解析），试填产物不入库。
- **C04 人工准确率签收结果**：用户 `arvin` 于 2026-10-04 在本机签收网页逐条复核两课全部 263 条（course1 76 实体 + 61 关系，course2 68 实体 + 58 关系），**采纳 Claude 辅助判定**：263/263 判定一致；35 条 ✗ 的依据中 30 条沿用辅助原文，5 条仅删去【请复核】标记。按用户确认如实记为「复核后采纳辅助判定」，不是独立盲判。course1 实体 64/76（84.21%）、关系 58/61（95.08%）；course2 实体 61/68（89.71%）、关系 45/58（77.59%）；实体数 76 / 68 均 ≥20；`judge-report` 结论两课均为「达标」，`is_human_judgment: true`。证据 `evaluation/raw/c04-signoff/*-worksheet-user.md`、`*-judgments-user.json`、`*-report-user.json`；Claude 复核：判定 JSON 与工作表逐条一致、报告可由判定重算得到、原 predictions / 工作表 / 辅助文件未改。**风险**：course2 关系离 70% 仅 5 条余量，删去【请复核】的 5 条正是两可项，改判可能使结论翻转。签收完成不等于技术冻结：**stage_c_status: OPEN；technical_freeze: NOT_PERFORMED**。
- **补测决定**：2026-10-04 用户决定三项补测均不做（浏览器可见首字、关闭思考的 Markdown 抽取、v3 + 思考开启 13 题基线）。无付费调用，台账仍 844451 / 900000，向量 12005 另计。冻结说明须如实写这三项「未测」：首字只有服务端首 delta 与客户端 SSE 首 delta；关闭思考的新 MD 抽取未测；旧思考开启 MD 为 83.97 / 75.51 秒，均未达 ≤60 秒，≤60 秒实测仅两份 PDF（20.90 / 28.08 秒）；关闭思考的问答改善幅度无法与 v3 提示词分离。整轮交 Codex 复审：`docs/handoffs/claude-plan-c-acceptance-closeout.md`（review_status: ready_for_review）。
- **最终门禁（`bf81d20`，干净临时工作树、隔离端口、一次性 Neo4j、本机假供应商）**：**第 2 次 exit 0**：backend+tooling 3893 passed / 27 登记 skip；frontend 38 文件 934 passed；integration 393 passed / 4 登记 skip；backend-live 44 passed；演示 E2E 2 passed；个人本机假供应商 E2E 4 passed（日志 `scratchpad/logs/c-acc-gate-bf81d20-r2.log`，23356 字节，SHA-256 前 16 位 `0769aeb27f1d9dbb`）。第 1 次 exit 1：backend 3893 / 27 skip、frontend 934 均通过，integration 层因本 shell 的 PATH 缺 `~/.docker/bin` 找不到 docker 命令、未能启动一次性 Neo4j（Docker Desktop 在运行）；第 2 次只把 `~/.docker/bin` 加进 PATH，其余命令、工作树与代码相同（日志 `c-acc-gate-bf81d20.log`，18670 字节，`677970d7dc15994f`）。相对 `4304fec` 多 15 例（签收工具 12 + 3），无新增 skip、删用例或放宽断言。


## 2026-10-04 Codex 认领：计划 C 验收收尾复审（54a7c67）

| ID | 状态 | 负责人 | 范围与验收 |
| --- | --- | --- | --- |
| C-ACC-REVIEW-54 | DONE（REQUEST_CHANGES；仅复审，未冻结） | Codex | 只读逐提交复审4a6308b..54a7c67的24文件；核对入库语义、只读审计、签收工具/证据/措辞与不补测边界；在本隔离工作区验证并输出P1/P2/P3报告及Codex交接；不实施修复/冻结/合并/推送 |

输入：Claude提交与交接、测量区88f9f6f的签收源文件（只读哈希）；输出：docs/reviews/codex-claude-plan-c-acceptance-54a7c67.md与Codex交接。风险：遗漏工具拒绝/表格解析边界、批量转换半写入、历史文档误作当前状态、外部环境污染。验证：指定4份定向测试、离线异常输入探测、签收数据重算、隔离完整门禁与git diff --check。API/DTO/迁移/依赖无改动；本轮仅本工作区文档/脱敏复审资产；真实生成/向量调用0，台账844451/900000、向量12005另计；stage_c_status OPEN、technical_freeze NOT_PERFORMED。

C-ACC-REVIEW-54验收：固定54a7c67隔离工作副本，指定四文件33passed；整次integration实际exit0（backend+tooling3893passed/27登记skip、frontend934、integration393/4登记skip、backend-live44、演示2、个人假供应商4，type-check/build通过）。两课四源哈希一致、签收JSON/报告重算一致，27种入库语义探测等价；发现P2两项（重复行/额外列漏拒绝、批量拒绝部分写入）、P3两项（失败释放计时遗漏、文档当前状态矛盾）。报告docs/reviews/codex-claude-plan-c-acceptance-54a7c67.md；交接docs/handoffs/codex-plan-c-acceptance-review-54a7c67.md。人工准确率已签收，方式为用户arvin逐条复核后采纳辅助判定，非独立盲判；三项补测不做并保留未测。修复另开一轮；stage_c_status OPEN、technical_freeze NOT_PERFORMED；真实生成/向量增量0、台账844451/900000和12005另计；未改源分支/证据，未推送合并。源范围diff-check只报tasks.md末尾空行（exit2），未替Claude改。

## 2026-10-04 Codex 认领：验收复审四项修复与本机检查入口

| ID | 状态 | 负责人 | 范围/验收 |
| --- | --- | --- | --- |
| C-ACC-FIX-54 | DONE（本轮修复；用户手工检查待执行，未冻结） | Codex | 修复 P2-01 工作表重复行/列数校验、P2-02 批量转换拒绝零写入、P3-01 异常解锁计时、P3-02 当前文档矛盾；先回归后实现、隔离完整门禁；交付本修复版本启动及人工闭环检查步骤 |

输入：54a7c67 与 Codex 复审报告；输出：最小代码/测试修复、当前状态统一、Codex 修复交接及启动指南。依赖：既有本机依赖、一次性 Neo4j 和假供应商；风险：表格转义回归、批量半写入、finally 改变异常传播、启动错目录误触共享库。验证：新增回归 RED→GREEN、指定四文件测试、./scripts/verify.sh integration、签收只读重算与 git diff --check。无 API/DTO/契约/迁移/依赖变化。仅自己的 codex/plan-c-acceptance-fixes 工作区；不改 Claude 交接与测量源文件、不复制 .env/业务库/课程正文、不发真实调用、不推送合并。stage_c_status OPEN；technical_freeze NOT_PERFORMED；人工准确率已签收（复核后采纳辅助判定）。用户要求先修复、自行检查后决定是否冻结。


C-ACC-FIX-54 验收：签收新增回归 RED23failed/16passed、计时 RED4failed/6passed；修复后最终指定四文件61passed。整次隔离 `./scripts/verify.sh integration` 实际exit0：backend+tooling3921passed/27登记skip，frontend934（38文件）+type-check/build，integration393/4登记skip，backend-live44，演示E2E2，个人本机假供应商E2E4；无新增skip/删测试/放宽断言/升级依赖。只读签收哈希/263项工作表-判定-报告重算一致、27种入库业务语义与4a6308b等价、异常输入拒绝且批次零写入。新增列探测勘误在Codex自己的复审报告登记，旧资产保留。P3文档以顶部当前状态/README及Codex新交接覆盖历史措辞，Claude原交接按所有权规则不代写。报告 docs/reviews/codex-plan-c-acceptance-fixes.md；交接 docs/handoffs/codex-plan-c-acceptance-fixes.md；启动/本机闭环检查 docs/handoffs/codex-plan-c-manual-start.md。真实个人模式启动本轮未执行，新真实生成/在线向量调用0，台账844451/900000、向量12005另计；源码、签收与测量原证据不改源工作区、不推送合并。**stage_c_status OPEN；technical_freeze NOT_PERFORMED；等待用户本机检查反馈和冻结决定。**

## 2026-10-04 Codex：全站向量 API 网页配置设计

| ID | 状态 | 负责人 | 范围/验收 |
| --- | --- | --- | --- |
| C-EMBED-SETTINGS-DESIGN | CANCELLED_BY_USER（2026-10-04） | Codex | 用户要求暂时不改、撤销全站向量网页配置计划；仅保留设计备档，未开始实现，不再形成实施计划或请求审批；保留原验收修复与现有启动行为 |

输入：用户选择前者、ADR-081、现有启动/配置/向量/个人模型实现；输出：docs/superpowers/specs/2026-10-04-global-embedding-settings-design.md 与Codex设计交接。依赖：现有AES-GCM/SQLite/Neo4j/契约工具链；风险：所有教师可改全站Key、首次无配置打不开网页、API/worker空间不一致、模型同名但供应商不同导致向量混用、测试隐式计费。验证：本轮静态核验与文档自审；实现后的RED→GREEN/契约与完整隔离integration为设计要求，当前不宣称功能已完成。保留既有未提交验收修复、不改Claude/测量区、不出站真实模型、不动共享图谱；stage_c_status OPEN，technical_freeze NOT_PERFORMED。

2026-10-04 用户撤销全站向量 API 网页配置计划：本项停止，不修改启动流程、权限、API、数据或迁移；不继续设计/实施/测试该功能。已有 C-ACC-FIX-54 修复保留，用户仍可按原启动指南检查，stage_c_status OPEN、technical_freeze NOT_PERFORMED。


## 2026-10-04 Codex 认领：最新结果 GitHub 集成

| ID | 状态 | 负责人 | 范围与验收 |
| --- | --- | --- | --- |
| C-INTEGRATE-20261004 | DONE（#317/#319/#318已合并；未冻结） | Codex | 整合当前验收四项修复、复审/交接/启动指南及已撤销设计记录；本机凭据与业务库不入库；干净无.env隔离门禁后提交推送修复PR，按依赖顺序合并相关合格PR至main；不执行技术冻结 |

输入：用户本轮明确授权提交GitHub、开PR和合并可合并PR；现有#317（计划A，base main）、#318（计划B/C与验收，base #317分支、草稿）、本地codex/plan-c-acceptance-fixes最新修复。输出：可追溯提交/PR、独立本地门禁与远程CI结果、本Agent集成交接。依赖：GitHub与Docker可用；风险：叠加PR基线错位、把旧REQUEST_CHANGES直接合并、凭据从说明文档泄露、测试误连用户库、将合并误作冻结。验证：指定四文件回归、无.env干净工作副本./scripts/verify.sh integration、只读签收重算、敏感值扫描、git diff --check、PR头提交与CI状态匹配。只改自己的工作区；不移动/清空用户运行环境，不合并测量分支88f9f6f，不发真实生成或向量请求。此次发布授权覆盖先前历史任务的“不推送合并”约束，但不授权技术冻结：stage_c_status OPEN，technical_freeze NOT_PERFORMED。


C-INTEGRATE-20261004 发布前门禁：新无.env验证worktree独立运行整次integration exit0，backend+tooling3921passed/27登记skip、frontend934+type-check/build、integration393/4登记skip、backend-live44、演示2、个人假供应商4；定向61passed与只读核验通过。对561个待推送历史blob和可发布文件的本机敏感值匹配0；启动指南真实值已恢复占位，私人备档保留在忽略目录，用户.env未改。结果与代码SHA见evaluation/raw/codex-c-acc-fixes/publication-verification.json；远程PR/CI和main合并待执行，不将本地通过记为已合并。


C-INTEGRATE-20261004 实际集成结果：#317（头68762e8）全部8检查SUCCESS，merge commit 3d696158；#319（头d03b5e7，本轮修复）全部8检查SUCCESS，先合入claude/plan-c-acceptance，merge commit bbc8fbea；#318基线改为main、纳入修复后头bbc8fbea全部8检查SUCCESS，merge commit 0436ff34，已进入main。merge commit保留作者/历史，不force-push、不删除分支；没有合并测量分支88f9f6f。验证origin/main包含d03b5e7且完整代码树与已验修复提交一致。仓库当时开放PR列表为空；发布交接与启动说明的文档同步另由后续PR承载，不冒充新的业务修复或冻结。

上述PR状态、头/合并提交与CI链接存evaluation/raw/codex-c-acc-fixes/publication-verification.json。当前代码入口scripts/start.sh已在GitHub main；本地主目录代码未自动pull/切换，本机.env/业务库未改。说明文档不存真实Key，向量仍.env全局online、生成API仍个人网页配置；网页向量配置计划保持CANCELLED_BY_USER。真实测量与人工签收口径不变，三项不补测仍未测，历史慢段根因OPEN；stage_c_status OPEN、technical_freeze NOT_PERFORMED。用户手工检查与冻结决定仍等待用户，不因GitHub合并自动签收。

## 2026-10-08 Codex：课程列表与模型设置 UI

- UI-ROLLOUT-R2-R3：IMPLEMENTED（基础门禁环境阻塞）；负责人 Codex；范围为批准计划 `docs/superpowers/plans/2026-10-08-courses-model-settings-ui.md`。保留业务/API/密钥安全；验收为相关与全量测试、类型、构建、基础门禁、四宽度页面。

## 2026-10-08 Codex：剩余页面 UI 统一

- UI-ROLLOUT-REMAINING：IMPLEMENTED（基础门禁环境阻塞）；负责人 Codex；输入为用户继续修改其他页面的指示与 PR #322 已确认设计；输出为资料、审核/发布、成员、问答、教师图谱视觉升级及认证样式对齐。沿用本地分支，不覆盖已完成两页。
- 依赖现有 API、组合式逻辑及共享 tokens；不新增接口、权限、统计数据。主要风险为编辑确认、SSE 进度、问答引用状态与窄屏溢出；验证为 H02/H09/H10/H12/H14、问答与认证相关回归、全量前端、type-check/build、基础门禁及四宽度浏览器。

UI-ROLLOUT-REMAINING：28 个浏览器页面/宽度组合通过，复审生命周期恢复问题已补 RED/GREEN 回归；交接 `docs/handoffs/codex-remaining-pages-ui.md`。基础门禁因缺少 datamodel-codegen 失败，未记录为全绿；修改仅本地，未提交/推送。

UI-ROLLOUT-REMAINING 最终：前端 60 文件 / 1166 测试 PASS，type-check/build PASS；git diff --check PASS（移除五处末尾空行后）；本地预览保持 5322。

## 2026-10-08 Codex：模型供应商与自动发现

- MODEL-DISCOVERY：DONE；负责人 Codex；用户要求供应商选择、输入 Key 后获取模型列表并允许手填。输入为现有 L10 配置接口与公网出站守卫；输出为供应商预设、自动/手动查询及鉴权只读模型发现接口。
- 无库表迁移；接口先更新契约与身份规格再生成。风险是 Key 跨供应商、DNS/重定向绕过、晚到模型列表与上游响应泄露；验收为服务/接口安全回归、前端状态隔离、真实浏览器假供应商、契约生成检查及相关/全量前端。

MODEL-DISCOVERY 验收：后端发现/原配置/出站回归 74 PASS；全量前端 61 文件 / 1169 PASS，新增发现回归最终 6 PASS；type-check/build PASS；basic 门禁 PASS（已定位现有用户目录生成器并加入检查 PATH）；桌面/手机浏览器 PASS。交接 `docs/handoffs/codex-model-discovery.md`；本地 5322/8321 已运行新接口，未提交或推送。
## 2026-10-08 Codex：资料上传排版优化

- MATERIALS-LAYOUT：DONE；负责人 Codex；输入为用户上传页截图与现有页面。先按用户要求保存当前版本为本地提交 c89b0df，再调整页头、双栏上传卡片、资料列表与空态。只调整展示，沿用上传验证、SSE、取消/重试/删除。
- 验收：H02/H09/H14 回归、type-check/build、桌面/手机空态/已选择/资料列表浏览器检查；风险为原生文件选择键盘可访问性、长文件名与窄屏溢出。无接口与数据变更。

MATERIALS-LAYOUT 验收：H02/H09/H14 共 173 PASS，type-check/build PASS；2559/1440/1280/768/390 五宽度 × 空态/有资料十组浏览器检查通过，包含文件选择键盘焦点与超长文件名；git diff --check PASS。修改前快照 c89b0df，当前排版修改保留为可审查工作树，交接 `docs/handoffs/codex-materials-layout.md`。

MATERIALS-LAYOUT 后续调整：依用户要求删掉右侧说明和分隔线，上传区域使用全宽单栏；清理对应样式。五宽度十组浏览器检查与 type-check PASS。
## 2026-10-08 Codex：审核页面去重与排版

- REVIEW-LAYOUT：DONE；负责人 Codex；用户指出三类审核标题显示两次。根因是栏目导航与内容标题重复。输出为一次展示的三类卡片、紧凑页头与发布区；沿用审核/合并/发布/回滚接口与逻辑。
- 先写重复标题回归（RED：每类出现两次）；验收 H09/H10/H14、类型/构建、宽屏/手机空态和非空页面。沿用户要求保存修改前上传布局为本地版本，再修改审核页面。

REVIEW-LAYOUT 验收：去重回归先 RED（两次）后 GREEN（一次）；H09/H10/H14 共 98 PASS；type-check/build PASS；五宽度 × 空/非空十组浏览器 PASS，含合并面板、回滚确认和无溢出检查。修改前版本 4d9db5b；交接 `docs/handoffs/codex-review-layout.md`，当前排版修改保留工作树，未推送。
## 2026-10-08 Codex：课程成员排版

- MEMBERS-LAYOUT：DONE；负责人 Codex；用户要求优化成员页面并在完成后保存。输出为紧凑添加表单、统一成员卡片/身份/操作排版、响应式布局；沿用现有成员接口与权限。
- 风险：用户名超长、窄屏表格、添加/移除反馈和教师不可移除。验收 H12/H14、type-check/build、五宽度浏览器及 scoped 本地提交。运行文件/密钥/日志不入提交，不推送。

MEMBERS-LAYOUT 验收：H12/H14 共 81 PASS；type-check/build PASS；五宽度 × 列表/无学生/错误十五组浏览器 PASS，包含长用户名不跨列、教师无移除按钮、假 API 添加/移除与反馈。局部文件保存为本地 Git 提交，未推送。交接 `docs/handoffs/codex-members-layout.md`。

## 2026-10-08 Codex：登录页书页与知识插画

- LOGIN-EDITORIAL：DONE；负责人 Codex；用户已确认方案 D 并要求先做前端。输入为已确认登录页预览；输出为独立登录布局、资料/书页/知识/路径 SVG 插画及密码显隐。仅前端与交接文档，无后端/API/数据库修改；注册页保持原版。当前版本以备份分支 codex/login-before-redesign-f54abfd 保存。
- 依赖现有登录 API、路由和会话；风险为密码显隐、错误后的口令清空、窄矮屏按钮可达和样式污染。验证 H13/ADR079/装饰运动、type-check/build、basic 门禁及五宽度浏览器检查。

LOGIN-EDITORIAL 验收：密码显隐先 RED（缺少按钮）后 GREEN；H13/ADR079/auth-graph-motion 共 47 PASS，type-check/build PASS，scripts/verify.sh basic PASS（契约生成、25 项门禁负向与契约回归）。浏览器 2559/1440/1280/768/390 五宽度及 390×460、1024×500 矮窗口共七组 PASS，包含装饰读屏隐藏、窄屏隐藏、无横向溢出、密码显隐无提交、401 口令清空/恢复隐藏、错误提示、注册保留八组装饰图。交接 docs/handoffs/codex-login-editorial.md；只保存本地提交，不推送。

## 2026-10-08 Codex：登录提示浮动

- LOGIN-NOTICE：DONE；负责人 Codex；用户要求未登录提示浮动在欢迎回来上方，不挤压下方内容。根因是 App 主容器的正常流提示占据高度；输入为守卫提示码，输出为仅登录表单的可关闭绝对定位提示。其他页面提示保持；不改后端。验收为显示/关闭前后标题坐标相同、宽屏与窄矮屏提示可见可关闭、H13/ADR079、类型/构建/basic。

LOGIN-NOTICE 验收：浏览器先 RED（关闭提示标题上移 21.59px），后 GREEN。六种桌面/平板/手机/矮窗口显示与关闭前后标题和输入框位移均 0px，提示可见可关闭、在标题上方且无横向溢出；H13/ADR079 44 PASS、type-check/build/basic PASS。交接 docs/handoffs/codex-login-notice.md；后端未改，本地保存不推送。

## 2026-10-08 Codex：学生图谱与问答体验
- STUDENT-WORKSPACE：DONE；负责人 Codex。输入为用户三项学生端调整及教师端预览要求；输出为按钮悬停说明、可拖动/键盘调宽分隔条、浅色问答页、独立教师图谱预览图片。教师图谱实际页面和后端不修改。
- 默认侧栏 25%，最小 280px，画布至少 640px；窄屏沿用抽屉。依赖现有 G6 resize 与路由/API；风险为拖动越界、窄屏、聊天文本对比度。验证 H11/图谱工作区/问答相关测试、type-check/build/basic、浏览器拖动与主题检查。

STUDENT-WORKSPACE 验收：DONE。H11/外壳 52 PASS；图谱工作区/组件/问答 32 PASS（一次并发超时后独立重跑通过）；type-check/build/basic PASS。实际学生课程三个宽度拖动/键盘/恢复/抽屉与浅色问答检查 PASS；假问答两个宽度引用、代码对比度、未覆盖/故障检查 PASS。教师实际页面、后端和数据未改；交接 docs/handoffs/codex-student-workspace.md。

## 2026-10-08 教师向量模型配置

- API-PROVIDER-PRESETS：DONE；负责人 Codex。通用 API 增加 Kimi、智谱 GLM、豆包/火山方舟、MiniMax、百度千帆、腾讯混元；向量栏按能力标记筛选并增加智谱/方舟。已核对官方常规兼容地址。前端32项、type-check/build、verify.sh basic（退出0）通过；真实教师/学生页面验证六个地址带入、密钥/模型清空、通用11选项及向量6选项含自定义。未保存真实设置、未调用真实供应商；后端不改。交接 docs/handoffs/codex-provider-presets.md；仅本地提交，不推送。

- API-SETTINGS-COMPACT：DONE；负责人 Codex。用户要求通用/向量 API 左右并列、桌面一页展示，并把列表/手输合并成可输入模型选择框。两张独立卡片，帮助折叠，短屏紧凑间距；模型输入匹配列表、按钮展开全部、未知名称保留、键盘及焦点关闭。1366×768、1440×900、1920×1080常规/目录加载/自定义维度检查通过；390px自动上下排列、不裁切。前端32项、type-check/build、verify.sh basic通过；后端/接口/库不改。交接 docs/handoffs/codex-api-settings-compact.md；本地保存，不推送。
- TEACHER-EMBEDDING：DONE；负责人 Codex。用户确认按教师课程生效、学生不增加设置。独立加密配置接口、教师表单、维度选择、课程发布/回滚/问答适配与安全重建已实现。相关后端84项及新增提交空间检查通过（向量专项19项），前端30项、type-check、build、verify.sh basic通过；教师/学生宽屏及390px浏览器检查、真实设置页检查通过，既有示例图谱保持63节点70关系。独立复审发现的通用状态污染与发布竞态已修复并复核。迁移019已先备份再应用；真实供应商激活留给用户在页面测试。ADR-092、规格/计划与交接 docs/handoffs/codex-teacher-embedding.md 已更新；仅本地保存，不推送。

## 2026-10-08 教师图谱视口修复
- TEACHER-GRAPH-VIEWPORT：DONE；负责人 Codex。输入为长编辑表单撑高页面的截图；输出为固定可用视口、左侧独立滚动与可调宽面板、扁平搜索筛选栏。保留节点编辑守卫、全部字段、画布和其他页面，不改后端/接口。
- 依赖现有 G6 容器 ResizeObserver。风险为容器尺寸反馈、窄屏、拖动边界与未保存修改。验证实际浏览器打开/关闭长表单、右下角工具始终可见、拖动/键盘调宽、H05/H07/H14、type-check/build、verify.sh basic。

TEACHER-GRAPH-VIEWPORT 验收：实际1440×900浏览器先复现页面1052→1438→1437px（关闭不恢复），修复后打开/关闭均900px且画布高度不变。真实课程和独立假API回归均通过1920/1440/1366/1024/390五尺寸，覆盖长表单、拖动/键盘边界、窗口改变、筛选浮层及未保存确认；无真实图数据写入。H05/H07/H14 153 PASS（初次并发一项加载态超时，独立及最终组合重跑全部通过），type-check/build/basic退出0；构建保留既有大chunk提示。交接 docs/handoffs/codex-teacher-graph-viewport.md，本地保存不推送。

## 2026-10-08 图谱右下角按钮说明
- GRAPH-CONTROL-HINTS：DONE；负责人 Codex。教师右下角四个按钮补齐浏览器原生延迟悬停说明，小地图名称随展开状态更新；学生既有提示与按钮行为保留，无后端修改。验证增强画布现有测试及真实教师/学生页面的四个提示和地图切换。

GRAPH-CONTROL-HINTS 验收：增强画布12项、type-check/build及verify.sh basic通过（退出0）；真实教师与学生页面四个原生title及小地图状态文字检查通过。交接docs/handoffs/codex-graph-control-hints.md；与此前改动一起推送并开PR。

## 2026-10-08 教师图谱圆角卡片
- TEACHER-GRAPH-CARDS：DONE；负责人 Codex。按用户三张参考图改独立圆角左侧卡片、搜索图标/分段布局切换和工具栏新建入口，保留面板调宽、有限视口、全部编辑字段与守卫。不改学生或后端。验证H05/H07/H14、类型/构建/basic和五尺寸浏览器回归。

TEACHER-GRAPH-CARDS 验收：H05/H07/H14 153 PASS、type-check/build/basic退出0；真实课程与独立假API浏览器五尺寸通过，最终紧凑字段样式后长表单回归再次五尺寸通过。真实页面验证圆角三卡片、工具栏唯一新建入口与原有表单可打开。手机固定页签遮挡关闭问题已修复并复核；后端与学生未修改。交接docs/handoffs/codex-teacher-graph-cards.md；只保存本地提交，暂未推送本次改动。

## 2026-10-09 当前状态移交Claude
- CURRENT-HANDOFF-20261009：DONE；负责人Codex。仅汇总固定代码c81f409的进度、边界、真实未测和接手顺序；本轮只读核实PR #323已含圆角改动，以及最新CI前端5项、后端3项、集成迁移与E2E登录失败。不在本轮修复代码或发真实模型请求。交接docs/handoffs/codex-to-claude-current-state-2026-10-09.md，验证引用/无密钥/基本门禁。

CURRENT-HANDOFF-20261009 验收：实际查询PR #321/#322/#323、c81f409最新CI及失败日志，核实端口/本地状态；文档引用与必要事实断言、无API-token标记检查、git diff --check、verify.sh basic退出0。本轮仅文档，不修复CI、不调用真实模型；CI失败作为接手优先项如实登记。只保存本地文档提交，不推送。

## 2026-10-08 Claude：前端复审与 CI 修复（基线 PR #323 head f76020f）

- CLAUDE-CI-REPAIR-20261008：DONE（验证见交接 docs/handoffs/claude-ci-repair-20261008.md；全量门禁结果见下一任务验收）；负责人 Claude。输入为 Codex 交接第 3 节列出的 CI 失败；输出为区分「测试宿主/旧断言/真实缺陷」后的修复。真实缺陷仅一处：迁移 019 缺少 `-- ROLLBACK:` 步骤，使逐版回滚测试遗留 `019` 记录并触发“不能应用比已应用版本更旧的迁移”；已补回滚行并新增覆盖 007–019 的守卫测试，迁移顺序防线与测试均未放宽。其余为旧测试：B03 宿主缺 Pinia/登录页（提示已移入 LoginView）、旧 35% 固定侧栏断言（改为 25% 默认的可调宽比例）、C02b 期望仅应用 018、E2E 的 `getByLabel('密码')` 命中显隐按钮（改为 exact）、E2E 的课程创建弹层与“搜索回车只预览”两处过时步骤。
- CLAUDE-UI-REVIEW-20261008：DONE（见验收）；负责人 Claude。输入为教师/学生页面实际操作复审；输出见交接 `docs/handoffs/claude-ui-review-20261008.md`：教师下拉选择不带动画布、小地图在切换布局后消失、窄屏学生图谱下方大片空白、演示横幅使学生图谱底部控件落出视口、发布历史显示原始 ISO 时间、课程页“其他课程”误导、学生设置页出现教师措辞、关系编辑未以已选节点为起点、教师标题/画布条占用竖向空间。不改后端接口、数据和权限。

CLAUDE-CI-REPAIR-20261008 / CLAUDE-UI-REVIEW-20261008 验收：
- 前端全量 `scripts/verify/frontend.sh full`：62 文件 / 1194 条通过，type-check 与 build 通过；后端全量 `scripts/verify/backend.sh full`：3975 通过、27 登记跳过，gate PASS；`scripts/verify.sh basic` 退出 0。
- E2E（演示模式）教师 + 学生用例通过；个人模式 4/4 通过（首次与全量门禁并发时 3 项失败：1 项旧搜索断言、2 项负载超时，隔离重跑通过）。
- 最终门禁（提交 c8c33fb 上单独运行）：`./scripts/verify.sh integration` PASS 退出 0：后端 3975 passed/27 登记 skipped，前端 1194 passed + build，集成 393 passed/4 skipped，图库专项 44 passed，E2E 教师+学生 2 passed、个人模式 4 passed；`verify.sh basic` PASS。详见 `docs/handoffs/claude-ui-review-20261008.md`。
- 未验证：真实供应商、付费模型、历史“暂不补测”三项；教师页首屏缩放策略（见交接建议）未改。

## 2026-10-08 Claude：教师图谱首屏总览与径向布局（用户确认方案）

- CLAUDE-TEACHER-OVERVIEW-20261008：DONE；负责人 Claude。输入为复审建议第 1 项经用户确认：教师页首屏改“整图适应”，并为单章大树增加径向布局。输出：`radialEngine` + `prefersRadial`（`graph/chapterLayout.ts`）、生命周期 `initialView/edgeStyle`、增强器 `fitPads`、画布 `arrangement/initialView/fitPads` 属性、教师工具栏“径向”选项与默认推荐、总览模式下定位自动放大到可读缩放。不改后端、接口、数据与学生图谱页。
- 验收：新增径向引擎 7 项、生命周期 6 项、教师页 3 项单测；浏览器中首屏整图可见且默认径向（64 节点）、层次/径向/力导向切换小地图保持、选中定位放大到 0.9、适应画布回到总览；教师视口回归与教师 E2E 通过。最终门禁（`25cae93`）：`./scripts/verify.sh integration` PASS 退出 0：后端 3975 passed/27 登记 skipped，前端 63 文件/1210 passed + 类型检查 + build，集成 393 passed/4 skipped，图库专项 44 passed，E2E 教师+学生 2、个人模式 4 passed；首次运行因 h05 测试类型标注失败，修复后整条重跑通过。详见 `docs/handoffs/claude-teacher-overview-20261008.md`。

## 2026-10-09 Claude：教师图谱节点类型图例与总览标签提示（用户选定 1、2）

- CLAUDE-TEACHER-LEGEND-20261009：DONE；负责人 Claude。输入为用户在后续建议中选定的两项（电脑端优先，手机端暂不考虑）。输出：`NodeTypeLegend.vue`（类型图例，计数 + 点击筛选，与工具栏筛选同一状态）、总览标签统计提示（增强器 `onLabels` 回调 → 画布左下角提示）、“放大到可读大小”按钮（生命周期 `zoomToReadable`）、径向横向拉伸 1.9。不改后端、接口、数据；学生页仅多了一个共用画布按钮。
- 验收：新增图例组件 2 项、教师页接线 1 项、生命周期 2 项、画布按钮/提示 2 项单测；浏览器 1440×900 中隐藏“概念”类 64→9 个节点、恢复后 64；“放大到可读大小”后缩放 0.9 且提示消失；教师视口回归与教师 E2E 通过。门禁：`verify.sh basic` PASS；前端门禁（类型检查+全量 64 文件/1217 条+build）PASS；后端/集成未重跑（仅前端改动）。详见 `docs/handoffs/claude-teacher-legend-20261009.md`。

## 2026-10-09 Claude：前端优化批次 3（用户选定 3–7，电脑端优先）

- CLAUDE-POLISH-BATCH3-20261009：DONE；负责人 Claude。输出：① 教师图谱布局按课程记入本浏览器（`useArrangementPreference`）；② 问答“涉及的知识点”默认 8 个、可展开；③ 入口图标统一（`navIcons.ts` 单一来源，新增文档/书本图标，成员不再用概览图标）；④ 除登录页外的页面路由级按需加载（`lazyView`：失败自动重试 2 次，仍失败显示提示）；⑤ `scripts/e2e.sh` 清理加强制结束保险（`scripts/_stop-procs.sh`）。不改后端、接口、数据与权限。
- 验收：单测新增（布局记忆 3、问答折叠 1、图标 3、lazyView 3、强制结束 3）；浏览器 1440×900：刷新后仍保持所选布局、标签 8/27 可展开、7 个导航图标互不相同；E2E 教师+学生对按需加载版本通过。实测（登录页，限速约 1.5 Mbps，缓存关闭，5 次取中位）：1387 ms → 903 ms（-35%），传输 164 KB → 73 KB，入口 JS 437 → 155 KB；G6（1.4 MB）本就是动态加载，未变。门禁（`5ce0a79`）：`./scripts/verify.sh integration` PASS 退出 0：后端 3978 passed/27 登记 skipped，前端 66 文件/1227 passed + 类型检查 + build，集成 393 passed/4 skipped，图库专项 44，E2E 教师+学生 2、个人模式 4 passed。详见 `docs/handoffs/claude-polish-batch3-20261009.md`。

## 2026-10-09 Claude：前端体验审计与问答链路优化（UI-QA-01，用户确认方案）

| ID | 状态 | 负责人 | 范围 | 验收 |
| --- | --- | --- | --- | --- |
| UI-QA-01 | 实现与自动化验收完成，待用户视觉签收（2026-10-09；review_status: ready_for_review） | Claude | 学生问答链路（提问 → 流式 → 已回答/资料未覆盖/未完成 → 出处 → 跳转图谱）与图谱画布键盘停靠点修正。文件：`src/frontend/src/views/ChatView.vue`、新增 `components/chat/AnswerCard.vue`、`composables/chatSources.ts`、`composables/useCopyFeedback.ts`、`composables/useFollowLatest.ts`、`components/ChatMarkdown.vue`、`components/SourceViewer.vue`（仅样式）、`components/AppIcon.vue`（新增 copy/info 图标）、`graph/a11y.ts` + `graph/lifecycle.ts`、`styles/ui.css`（清理问答段）、相关前端测试、`specs/grounded-qa.md`（新增「前端呈现」一节）、`specs/course-knowledge-graph.md`（画布键盘约定） | 不改后端、接口、契约、数据与权限；出处校验、`not_covered` 与服务错误分开、流式结束与撤回语义不变；既有 `data-test` 钩子保留。`type-check`、前端全量、`build`、`./scripts/verify.sh`、问答 E2E；1440×900/1280×800/768 前后对比截图，390 仅验证无溢出（用户 2026-10-09 决定：手机端不专门优化）；Tab 顺序、焦点可见、200% 缩放、减少动效；测试通过与浏览器验收分别报告 |

- 审计依据：隔离演示栈（演示模型）+ Playwright，教师/学生 12 个页面 × 1440/1280/768/390，问答三种状态实走；证据与结论见 `docs/handoffs/claude-ui-qa-01.md`。
- 已决（用户，2026-10-09）：① 问答页保持已交付的浅色内容表面，规格中“问答页是暗色页”的说法作废；② 本轮范围为问答链路 + 画布 Tab 停靠点，候选只做：出处按回答归属、复制回答（含出处）并反馈、输入区固定与滚到最新；③ 成员移除用行内二步确认（与资料删除一致），与“离开页面前提示未保存”一起放第二批；④ Playwright 检查脚本不进仓库（本地一次性，需要保留时另开任务放 `tests/`）；⑤ 手机端（390）只验证无溢出。
- 本轮不做、待确认（C 类或需新决定）：推荐理由里的“解锁度 1.0000”“按中性值 0.5 计，易学度 0.5000”由服务端 `reason` 生成，后端测试（`test_l14_reason.py`）与 `specs/learning-path.md` §4 要求前端原样展示，前端解析句子会脆弱，若要改写须先改服务端文案与规格；对话历史跨刷新保留（持久化与隐私）；示例问题（需要内容来源）；课程主页待审核数（需要新数据）；成员批量添加（新接口）。
- 第二批候选（审计发现，已确认可做但未排期）：成员移除行内确认；教师图谱未保存离开前提示（`beforeunload`）；首次访问登录页不应显示“未登录”红色提示；教师图谱详情来源行排版与标题焦点框；模型设置演示模式下表单提示与教师页重名控件；资料上传原生英文文件按钮与“可拖放”暗示不符；课程概览页两个主按钮。
- 验收证据（2026-10-09，详见 `docs/handoffs/claude-ui-qa-01.md`）：新增 6 个测试文件先 RED 后 GREEN，既有测试未改；`type-check` 无错误，前端 72 文件 / 1263 条通过，`build` 成功，`scripts/verify/frontend.sh full` 与 `./scripts/verify.sh`（basic）通过；E2E 教师 + 学生 2 passed、个人模式 4 passed。浏览器（一次性演示栈，1440/1280/768/390）：48 次加载无溢出、无控制台错误；图谱页第一个 Tab 停靠点由 canvas 变为导航链接；问答已回答/未覆盖/失败、长对话固定输入区、上翻后“回到最新”、复制含出处均实走通过；问答页文字对比度 0 项不达标。**未运行** `verify.sh full/integration` 的后端与集成部分（后端未改）；**未验证** reduced-motion 实测、读屏、画布像素对比度、真实模型/真实课程、用户视觉签收。
- 更正（审计结论）：ui.css 的问答段不是“没生效的暗色样式”，而是把 `--ss-*` 重映射成浅色，已整体替换为 `.light-surface` + `--gw-*`。
- 回滚：各任务独立，`git revert` 对应差异即可；无数据与接口变化。
- 本机环境：Node v26.4.0；本会话在工作区执行 `npm ci`（根目录与 `src/frontend`，仅锁文件内依赖，node_modules 被忽略）；审计用一次性 Neo4j 容器与演示栈已停止删除。无真实模型调用与账号。

## 2026-10-08 Codex 认领：R1 worker 旧租约图提交防护

| ID | 状态 | 负责人 | 范围与验收 |
| --- | --- | --- | --- |
| R1-PERSIST-FENCE | VERIFIED_LOCAL（核心及截止补充已验证；限定风险 CLOSED） | Codex | 仅修复旧 worker 在租约丢失后提交 Neo4j 的高严重程度发现；双租约守卫、显式图事务、SQLite 提交围栏与同连接 T6；旧 worker 零提交、异常恢复和锁释放回归。其余四项中严重程度发现不纳入本任务。 |

- 输入：`bdb89c4` 基线的只读审查与真实 SQLite/图调度替身复现；用户确认「双租约守卫＋显式图事务＋提交围栏」方案。
- 当前输出：双租约守卫、显式图事务、SQLite 最终围栏、同连接 T6、完成结果读回及定向/真实 Neo4j 回归；实施计划 `docs/superpowers/plans/2026-10-08-worker-persist-fence.md`，实施交接 `docs/handoffs/codex-r1-persist-fence.md`。用户在书面规格交付后明确要求「实施修改」，本会话顺序执行。无公共契约、迁移或项目依赖变化；测试依赖仅在 `/private/tmp/smartsketch-r1-testdeps`。
- 已实施范围：worker 持久化与心跳、任务租约/课程锁仓储、Neo4j 显式事务入口、新增定向回归；保留其他调用者的托管事务入口和公共 API。
- 依赖：现有单机 worker、SQLite WAL 和 Neo4j 5.28.2 同步驱动；复用 §8.4 的贡献可见性与接管重建，不引入跨库原子提交。
- 风险/需评审：SQLite 提交围栏是全库单写者；Neo4j 提交应答阻塞会延长持锁时间，服务端事务 timeout 不等于客户端提交应答截止。书面规格区分一致性保证与可用性限制；实现阶段必须用故障注入证明退出/恢复行为，未解决的无界等待不作为已闭环发布。
- 验证命令：`git diff --check`、`PATH="/opt/anaconda3/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS="-p no:cacheprovider" ./scripts/verify.sh`（basic）；实现时再执行规格中的 worker 回归和独立 Neo4j 集成。
- 本轮设计验收证据：上述 basic 门禁 exit 0，契约回归 237 passed、门禁负向测试 25 项通过；文档链接解析及 TODO/TBD 扫描通过，`git diff --check` exit 0。日志 `/private/tmp/smartsketch-ocr-46o1tbcy/r1-design-verify.log`。仅验证文档/既有基础门禁，不是 R1 修复验收；新 worker 回归与真实 Neo4j 故障验收尚未运行。
- 实施验收证据：最终定向 214 passed（F02/C09/D11/清理/计时及新增回归）、真实 Neo4j F13/R1 34 passed，两个 XML 零失败/错误/skip；旧 worker 在相同真实回归遗留节点而失败。独立审查后新增提交前/后截止测试，故障变异各失败、正常版本通过。最终 basic exit 0，`git diff --check` 通过。日志与 XML 在 `/private/tmp/smartsketch-ocr-46o1tbcy/`，详见实施交接。
- 全量限制：backend full 3945 passed/27 skip/1 failed/6 errors，七项失败均是工具子进程丢失临时依赖；独立临时 venv 复验该模块与新回归 45 passed，但完整 full 未重跑。frontend full 因缺 node_modules 失败，完整 integration/E2E 未跑，不宣称全量门禁通过。实际应用环境未改，临时 Neo4j 已移除。
- 下一步：保留本地修改/提交；网络级总截止及真实断连时资源释放/全库写阻塞上限仍需准入验证，暂不发布、不推送、不创建 PR、不操作用户业务库。独立审查未发现新确定性运行时缺陷，Important 提交前/后截止测试缺口已补；Minor 两个实际心跳调用者的延迟/连续失败故障测试暂缓。

## 2026-10-08 Codex 认领：R1 提交传输截止补充设计

| ID | 状态 | 负责人 | 范围与验收 |
| --- | --- | --- | --- |
| R1-PERSIST-DEADLINE-DESIGN | DONE（已批准、实施及完整验证） | Codex | 补充书面规格及七任务计划已确认；七任务已完成；最终代码整次门禁 exit 0，限定风险 CLOSED。 |

- 输入：本地 R1 修复 `e111315`、现有设计 §7 与实施交接；用户明确要求「按首选方向编写补充设计」。
- 输出：`docs/superpowers/specs/2026-10-08-worker-persist-deadline-design.md`、架构/任务协议/决策同步及 Codex 设计交接。
- 依赖：现有 Neo4j 5.28.2 的 AsyncSession 公开取消能力、Python 3.11+ asyncio、同步 worker 与 SQLite 同线程围栏；不升级项目依赖、不操作共享库。
- 风险：取消仅证明连接退出，不证明服务端图未提交；截止预算不能因心跳或分步等待重置；退出清理与重建路径不能再次引入无界等待；全库写者仍可能遇到 busy timeout。
- 验证：文档链接/状态/预算自审、`git diff --check`、`PATH="/opt/anaconda3/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS="-p no:cacheprovider" ./scripts/verify.sh`。产品/网络故障测试留至获批实施；发布准入仍 OPEN。
- 审批边界：本轮确认仅批准写补充设计；书面规格获批后才编写实施计划，计划与执行方式获批后实施。
- 设计要点（详细取值待书面批准）：COMMIT 默认 2 s/上限 3 s；资源清理默认 1 s/上限 5 s，等待型清理置于围栏外；取消不证明图未提交。恢复清理经 DraftWriteGuard 幂等撤销后才清标记，拟修订 ADR-072 的此入口无贡献快路径。默认围栏 ≤3 s 是待真实故障验证的阈值，不是当前保证。
- 设计验收：8 个文档文件、17 条本地链接解析通过；新规格无未填占位、代码围栏配对、状态/预算/范围核对通过；Settings 与 `.env.example` 未加入候选配置。`git diff --check` exit 0；本轮 basic 门禁 exit 0，契约测试 237 passed、门禁负向测试 25 项通过。日志 `/private/tmp/smartsketch-ocr-46o1tbcy/r1-deadline-design-verify.log`，设计校验/哈希 `/private/tmp/smartsketch-ocr-46o1tbcy/r1-deadline-design-check.json`。仅验证设计文档与既有基础门禁；没有新产品/网络故障验收或全量结果，不关闭风险。

## 2026-10-08 Codex 认领：R1 截止补充实施计划

| ID | 状态 | 负责人 | 范围与验收 |
| --- | --- | --- | --- |
| R1-PERSIST-DEADLINE | DONE（限定可用性风险 CLOSED） | Codex | 用户已确认书面计划并要求开始实施；Codex 顺序测试先行实现；全部网络、恢复和最终整次门禁已通过。 |

- 输入：`e41e951` 书面规格与用户「确认实施」；输出：`docs/superpowers/plans/2026-10-08-worker-persist-deadline.md` 和 Codex 计划交接。
- 依赖：复用当前受管 worktree、既有临时 Python 3.11 测试 venv；未来实测需一次性 Neo4j、回环 TCP 代理与项目声明的前端/E2E 依赖。
- 风险：公开取消与 Runner 清理仍需真网络证据；取消后服务器迟到结局及 failed 清理排序；环境不足不能用登记 skip 代替准入。
- 本轮验证：计划/规格覆盖、接口与路径自审、`git diff --check`、basic 门禁；产品测试及真实故障只在获批实施后运行。
- 审批/执行方式：用户确认时书面计划尚未存在，只确认已交付规格与实施意图；计划现已写入待审阅，不能把此前确认外推为已审阅计划。保留先前本会话顺序执行方式，等待书面计划确认；不推送、不创建 PR、不合并、不冻结。
- 计划验收：规格 §1～§9 映射七任务；五项 Review Focus 各有断言；接口/具体文件/类型核对，增加只记录 BEGIN 完成时刻的可选 on_acquired 回调以精确计量围栏。9 个文档文件、24 条本地链接通过，35 项实施步骤未勾选，产品树/运行配置未变。`git diff --check` exit 0，本轮 basic exit 0，契约 237 passed、门禁负向测试 25 项通过。日志 `/private/tmp/smartsketch-ocr-46o1tbcy/r1-deadline-plan-verify.log`，校验/哈希 `/private/tmp/smartsketch-ocr-46o1tbcy/r1-deadline-plan-check.json`；仅计划与既有门禁验证，无产品/网络新验收，风险 OPEN。

- 2026-10-08 最新审批：用户「确认计划，开始实施」；书面计划与当前会话顺序执行均获确认。实施输入/依赖/风险/命令沿用已批准计划，不再等待重复确认。

- R1-PERSIST-DEADLINE 最新实施进度（2026-10-08）：Tasks 1～5 已测试并本地提交；Task 6 真实故障矩阵及 Task 7 完整门禁正在验证。最终审查两项 Important 已复现 RED（3 失败）并修复 GREEN（3 通过）：DNS 启动错误脱敏/重试分类、T6 结局读回 attempt 校验。没有发布/PR 授权；准入 OPEN，完整计数和结论待整次命令结束记录。

## 2026-10-08 Codex 认领：R1 后续验证失败修复

| ID | 状态 | 负责人 | 范围与验收 |
| --- | --- | --- | --- |
| R1-DEADLINE-VERIFY-REPAIR | DONE | Codex | 用户要求修复 NOOP 断连证据、F13 持久化/恢复和 E2E 解释器配置；先定位并测试先行，修复后重跑原阈值的真实矩阵及最终版本整次门禁。 |

- 输入：提交 `2ea6319`、本任务现有未提交测试/文档，以及上轮失败日志。仅接续自己的 Task 6/7 文件；不覆盖其他成员改动。
- 输出：最小修复、复现测试、真实验收日志、实施交接；无推送/PR/合并/发布授权。
- 依赖与风险：临时 Python/锁定 npm/Playwright、自建回环 Neo4j；FIN 与 RST 必须区分，探针错误不自动等于产品回归；F13 图库就绪与 COMMIT 时延需独立实测，禁止放宽截止/跳过失败。
- 验证：proxy/K11 工具回归、独立自有图库 F13/R1 和 65 项网络矩阵、283 项定向选择、`./scripts/verify.sh` 与最终版本 `./scripts/verify.sh integration`（E2E 使用已验证临时解释器）。
- 上轮最终结局：整次 integration FAILED，backend 3 failed/3997 passed/27 登记 skip，integration 5 failed/457 passed/4 登记 skip；其中 backend 三项是审查修复的旧加载代码结果，当前定向已 GREEN，仍须最终版本整次复验。之前 ledger 关于 backend 导入时点的判断撤销，堆栈仍指向旧启动分支，不能把该轮当最终代码门禁。
- 上轮 F13/最终证明：4 failed/82 passed/13 errors；增强迟到实验因自建图库就绪失败有 2 errors；未关闭准入。保留原日志，后续修复不覆盖失败证据。原 Task 5 fixture 已不存在（Docker inspect 已核实），新实验新建带随机所有权标签的临时图库，不猜测或复用旧端口。

- 本轮定位证据：SO_LINGER 的真实 TCP RST 复现代理错误分支只记录异常却没有断连事件；集成脚本对隐式 PYTHON 未传 E2E_PYTHON（2 RED/显式覆盖例通过）→修复后工具回归 25 passed。新单实例图库就绪 23.358s，真实 async 连接 0.038s、健康 COMMIT 0.007s；原 F13/R1 34 项再次通过。演示/K09 失败的 fixture 仍只提供同步仓储，缺少 worker 专用工厂；补齐工厂，保留业务断言及其他同步入口，不增加产品回退。

- R1-DEADLINE-VERIFY-REPAIR 本轮验收进展：真实 38 项 F13/R1/demo/K09 与 65 项网络矩阵均零 skip 全通过；304 项完整定向通过。默认/上限围栏最大 2.010052s/3.003443s（阈值 3/4s），退出预算 1/5s 最大 1.042527s/5.041602s；迟到提交 takeover 3/5、failed_cleanup 5/5 次观察并收敛。当前副本变异三项均 RED、正常版本 GREEN；整次最终 integration 在运行，准入仍 OPEN。

- Task 6 结束验证已记录完成：提交 `b89844b`，顺序自建图库的 F13/R1 34 passed + 网络 65 passed，零 skip；范围内源 SHA 与整次门禁启动 manifest 相同。E2E 脚本修复提交 `b7e84a1`。本轮整次门禁首轮 backend 4003 passed/27 登记 skip、frontend 934/type-check/build 通过，但默认 17689 端口占用致整次 exit 1；占用者保持原状，第二轮使用既有端口覆盖机制从头执行，不拼接部分结果。

- 第二轮实际整次 exit 1：backend 4003/27 登记 skip、frontend 934、integration 462/4 登记 skip、backend-live 44、演示 E2E 2 全通过；个人 E2E 3 passed/1 failed。失败在 `personal.spec.ts:235` 要求掌握后路径文字必变。只读 trace 已证推荐首项从 `kp_63b0…` 切换至同名 `kp_80b7…`，掌握接口 200；PDF/MD 独立抽取允许同名异 ID。下一修复只调整该 E2E 为「文字与解锁 ID 联合身份」变化/恢复，保留掌握消失、刷新持久化、学生隔离与原超时；不修改推荐/图谱产品规则。先单独复验个人 E2E，再启动最终整次门禁。


### R1 最终验收与 PR 发布（2026-10-08）

- 上文设计/实施轮的 OPEN、暂不发布及失败计数是历史阶段证据；本节是 R1 当前状态，不删除失败日志。用户最新要求「检查门禁状态，若通过则开PR，更新项目状态」，授权推送本修复分支及创建 PR，不授权合并、部署或技术冻结。
- 最终代码 `f9c54553`（含 `2ea6319`、`b89844b`、`b7e84a1`）整次 `./scripts/verify.sh integration` 实际 **exit 0**：backend+tooling **4003 passed / 27 既有登记 skip**；frontend **934 passed**（38 文件）+type-check/build；integration **462 passed / 4 既有登记 skip**；backend-live **44 passed**；演示 E2E **2 passed**、个人假供应商 E2E **4 passed**。零 failure/error，无新增 skip、放宽超时、删用例或依赖升级。门禁执行前后 16 个相关代码/测试/脚本 SHA256 一致。
- 定向 304 项、F13/R1/demo/K09 38 项、真实网络 65 项均通过；Task 6 结束原选择 34+65 共 99 项零 skip。新旧版本及移除截止/取消/守卫三个变异均提供 RED 证据。真实 NOOP FIN/RST 判定、资源退出、迟到结局的接管和 failed 清理均验证。
- 最终整次网络 run `7de6155b7906…`：默认围栏最大 2.001980s、独立写者 2.115376s（≤3s）；上限围栏 3.001610s、写者 3.029492s（≤4s）；退出预算 1/5s 实测最大 1.046460/5.151670s（≤预算+1s）；迟到提交 takeover/failed_cleanup 各 4/5 次实际发生并收敛。未把 TCP 取消误作服务端回滚证明。
- **风险状态：CLOSED，仅限 worker 网络 COMMIT 无界占用 SQLite 最终围栏**。DNS 执行器退出、一般进程停机、其他图入口、宿主暂停/存储异常仍在保证之外；原四项中严重程度发现及两个既有心跳故障测试未纳入本轮。全项目 `stage_c_status OPEN`、`technical_freeze NOT_PERFORMED` 保持原状态。
- 原始日志/XML/manifest/292 行逐次计时及机读校验已导出到 `/private/tmp/smartsketch-r1-deadline-evidence-20261008/`；整次日志 `repair-full-final.log`、机读结果 `verification-summary.json`、哈希清单 `evidence-hashes.json`；交接 `docs/handoffs/codex-r1-persist-deadline.md`。

| ID | 状态 | 负责人 | 范围与验收 |
| --- | --- | --- | --- |
| R1-PUBLISH-PR | DONE_DRAFT | Codex | 输入最终门禁、源码哈希和用户 PR 授权；核对 origin/main 与工作区基线，更新状态和交接、运行最终 basic、推送 codex/ 修复分支、创建并附加 PR；保留工作区及证据，不合并/部署/冻结。 |

- PR 主线预检：最新 `origin/main=2e6acef7` 已合入 #321～#323；本修复实际分叉 `bdb89c46`。只读 Git merge-tree 确认 `docs/tasks.md`、`docs/decisions.md` 内容冲突，代码/个人 E2E 可自动合并，但未经主线整合验收。主线已占用 ADR-091/092（图谱工作台/教师向量），与本分支的历史 worker ADR 编号撞号，整合时须保留双方决定并重编号/同步引用。故创建 **草稿 PR**：本轮风险在受测修复分支上 CLOSED，主线尚未部署本修复；主线整合与远程 CI/审阅保持待完成，不将 branch 门禁外推为 merge-result 门禁。

- PR 发布结果：[修复草稿 PR #324](https://github.com/arvinhanye/SmartSketch/pull/324) 已创建并附加当前任务，`codex/r1-persist-deadline` → `main`，OPEN/DRAFT；GitHub 实测 mergeable=CONFLICTING，与本地两文档冲突预检一致。创建后远程 CI 四项启动中，不记远程通过。状态更新与修复提交已推送；未合并、部署或技术冻结。待主线整合、ADR 编号协调、合并结果门禁及审阅后转 ready；本任务交付已完成。

- Task 7 最终收尾：`task-done` 实际 exit 0，范围 `2ea6319..7d266ae`；再次核对最终整次 exit 0、四份完整 XML、16 源码哈希，最终 basic 和 diff-check 全通过。七任务 complete；草稿 PR 交付不替代后续主线整合验收。

## 2026-10-09 Codex 认领：PR #324 冲突与 CI 失败修复

| ID | 状态 | 负责人 | 范围与验收 |
| --- | --- | --- | --- |
| R1-PR324-REPAIR | DONE_CI_VERIFIED | Codex | 用户要求检查并修复 #324 冲突及失败；读取原始 CI 日志，整合最新 main，保留双方文档/代码与历史证据，协调 worker ADR 编号，复现失败后最小修复，完整门禁及远程 CI 验证后更新现有 PR。 |

- 输入：PR head `350d7c6`、最新抓取 main `5398a1f0`、失败 CI run `37878331607`；GitHub 原 head scaffold/frontend/backend SUCCESS，Integration and E2E FAILURE。原修复分支限定风险 CLOSED 证据保留，不外推为整合结果通过。
- 输出：原 #324 分支上的可追溯 merge/修复提交、冲突/失败原因与验证交接；不新建替代 PR、不强推、不合并 PR、不部署或冻结。
- 依赖：GitHub 原始日志，锁定 Python/前端/浏览器依赖，自有临时 Neo4j/SQLite；不读本机 .env/业务数据，不操作他人服务。
- 风险：两份共享文档同位置追加造成文本冲突，ADR-091/092 撞号；新主线 UI/模型/迁移行为必须保留；旧分支通过不等于合并结果通过。未知 CI 失败先定位，不放宽断言或网络截止、不新增 skip。
- 验证：原失败选择 RED→GREEN、worker 网络/恢复回归、ADR 引用与冲突标记检查、`./scripts/verify.sh integration`、最新 PR head 的远程 CI、`git diff --check`。回退整合前代码可恢复 `350d7c6` 的已验分支但会重新存在主线冲突；无本轮新增迁移或依赖升级。

- 原始失败已定位：run `37878331607` Integration 为 63 failed/399 passed/4 既有登记 skip；62 项在记录真实网络证据时写入 Linux 不存在的 `/private/tmp`，1 项因浅克隆缺少旧版本归档基线。backend-live 44、演示 E2E 2、个人 E2E 4 均通过；本轮不是 E2E 产品失败。
- 主线 `5398a1f0` 已整合到工作树：保留双方追加任务/决定，worker ADR 重编号为 093/094，主线 091/092 不变。原失败的三项回归先实际 RED（目录、历史配置、编号重复），最小修复后 3 passed；当前合并结果全量/远程 CI 仍待验证，原风险 CLOSED 仅为旧受测分支结论。
- 合并后定向实测发现主线 `_stop-procs.sh` 的整数 `SECONDS` 会将 2 秒宽限缩短至约 1.3 秒。新增在秒边界附近启动的真实子进程回归先 RED，随后以完成的 0.2 秒等待次数计满宽限，保留提前正常退出和宽限后强杀，不放宽原断言；此项限 E2E 清理脚本，不改 worker 产品截止。


### PR #324 修复验收与条件合并授权（2026-10-09）

- 用户最新指示「CI通过就合并PR」覆盖前述仅更新草稿、不合并的历史边界；仅当最终 PR head 所有检查成功时转 ready 并合入 `main`，不绕过门禁、不使用管理员覆盖、不强推、不删除修复分支或受管工作区、不部署/冻结。
- 修复代码 `36b421e` 已通过 push run `37904046120` 和 pull_request run `37904049198`：每轮 scaffold/frontend/backend/integration 全 SUCCESS，共 8 项。GitHub 实测 base `5398a1f0`、MERGEABLE/CLEAN。backend+tooling 4064 passed/27 既有登记 skip；frontend 1227 passed（66 文件）、type-check/build；integration 462 passed/4 既有登记 skip；backend-live 44；演示 E2E 2、个人 E2E 4。无新增 skip/删除用例/放宽预算。
- CI 网络 artifact 73 行与当前 6 产品源码拼接 SHA、测试 SHA 一致；默认/上限围栏最大 2.002760/3.003735s，独立写者最大 2.031202/3.031960s，均在 3/4s 原阈值；退出 1/5s 最大 1.170164/5.176260s，均在预算+1s。取消后实际迟到提交 takeover 5/5、failed_cleanup 3/5，两路恢复均收敛；旧基线 10s watchdog 围栏仍占用的真实负向证据保留。
- 独立只读审阅未发现本轮阻塞；3 项可移植性/编号回归 RED→GREEN，秒边界计时回归 RED→GREEN，定向合计 78 passed。
- 本地整次 `./scripts/verify.sh integration` 在用户中断时停止于 backend 未结束，缺少退出码，明确登记 INTERRUPTED，不称为通过；验收以同源码最新 Ubuntu CI 的全部实际门禁为准，保留本地未完成日志，不拼接为整次 exit 0。最终文档提交再运行本地 basic，并等其最新 head CI 全绿后条件合并。
- 采用 GitHub merge commit（非 squash）保留 pinned `e111315ffabdc5ce980afdf525b8321ef572dc8e` 历史祖先，使 main 的真实旧 worker 对照不依赖保留远程分支。合并使用精确 head 匹配，不删除分支/工作区。最终合并记录随 PR 保存；此验收关闭范围仍仅 worker 网络 COMMIT 无界占用 SQLite 围栏，其他审查发现/全项目冻结状态不变。
- 最终文档版本地 `./scripts/verify.sh` exit 0；可移植性/ADR 三项回归 3 passed，diff-check 通过。仅三份文档更新，无产品/测试/脚本变更；提交并推送原分支后仍按其最终 head 独立 CI 全绿执行用户的条件合并。
