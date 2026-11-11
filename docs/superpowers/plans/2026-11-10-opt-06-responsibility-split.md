# OPT-06 大文件职责拆分实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按原交接将四个候选文件拆成职责明确的内部模块，保留旧导入入口与既有行为。

**Architecture:** Python 旧模块保留公共类型/函数再导出；TypeScript 旧模块保留公共导出。Vue 页面保留路由装配、模板和样式，将计算逻辑及面板生命周期移到 composables，保持 DOM、事件、焦点和响应式行为。

**Tech Stack:** 现有 Python 3.11 / FastAPI、Vue 3 / TypeScript / Vite / G6；不新增依赖。

**Spec:** 审查分支 `claude/code-structure-review-handoff-49e73a` 的 `docs/handoffs/claude-code-structure-review-codex-handoff.md` §1 OPT-06；`specs/task-processing.md`、`specs/course-knowledge-graph.md`、`specs/learning-path.md`。

## 状态与前置条件

**IN_PROGRESS：用户已授权本地整合后继续；原远端状态核查如下。** 2026-11-10 核实：OPT-03 为本地 `36c1f92`，未找到远端分支或 PR；OPT-05 PR #339 为 open / merged=false，目标为 `codex/opt-base-ad63341`；底座 PR #338 也未合并。当前 `99c1f01` 含 OPT-05、不含 OPT-03。

原交接要求「只在 OPT-03/05 合入后做」。以下为基于当前源码的预备拆分安排；解除依赖后先核对最终基线和导出清单，再开始逐项实施。用户已授权 OPT-06 实施；用户已明确允许在隔离分支本地整合依赖、验证后继续，暂不推送或合并远端 PR。本地整合基线为 `ec92026`（父提交 `36c1f92` / `99c1f01`），任务表冲突保留双方内容。

## Global Constraints

- 每个原候选文件对应一条分支、一个 PR 范围；不把四项混成一个 PR。
- 对外导出名不变，旧模块保留再导出；函数签名、返回值、异常、调用顺序和配置默认值不变。
- 不调整契约、SQL/Cypher、事务、模型提示词、并发策略、重试/取消规则及界面文案。
- 不覆盖现有 `docs/tasks.md` 中 EXTRACT-PERF-01 的未提交追加内容及其两份未跟踪交接。
- `codex/extraction-perf` 已修改 `workers/extract_task.py`；本任务不自动纳入该分支，也不丢弃其工作。合入顺序变化时重新取基线。
- 公共 API 或数据模型不变；内部源码映射随各项同步更新 `docs/architecture.md`。

## Review Focus

- Python 模块搬移后旧导入路径、导出对象身份和测试注入点仍有效，避免循环导入。
- 网络 transport 的总时限、关闭资源、流式用量/错误解析保持一致。
- worker 的租约、取消、检查点、失败阈值、输出排序与事务边界保持一致。
- 资料页切课/卸载时中止请求、丢弃晚到响应并关闭 SSE，保持旧作用域清理顺序。
- 学生图谱页保留窄屏抽屉、宽屏拖拽、Esc/还焦点、深链接和布局切换；截图比较保持相同数据与视口。

## 0. 建立可验证基线

- [x] 读取原交接、相关规则和依赖完成记录，核实 GitHub PR 状态与本地提交祖先关系。
- [ ] 确认含 OPT-03/05 的已合入基线；若用户允许提前本地整合，使用原提交保留历史，记录两者 SHA、冲突解决及独立验证结果。
- [ ] 在适合的隔离工作区建立每项分支，保存公共导出/签名清单和同视口前端基线截图。
- [ ] `PATH="$PWD/.venv/bin:$PATH" GOCACHE="$PWD/.demo/opt-06/go-build-cache" ./scripts/verify.sh full`，保存原始日志和退出码。失败归因后再判断后续差异。

## Task 1: OPT-06A：compatible.py

**Files:** 保留 `src/backend/app/services/ai/compatible.py` 入口；候选新模块为同目录 `compatible_transport.py`（HTTP 协议、deadline、DNS/连接、stdlib transport）、`compatible_protocol.py`（请求/响应解析和错误映射）、`compatible_base.py`（共享 HTTP client）、`compatible_embedding.py`（embedding client）。聊天 client 留在原入口；按依赖方向搬移，禁止新模块反向导入入口。

**Interfaces:** 保留 `CompatibleModelClient`、`CompatibleEmbeddingClient`、`HttpResponse`、`HttpTransport`、`StdlibTransport`、`ExchangeDeadline`、`estimate_input_tokens`、`thinking_body`、`system_addresses`、`resolve_within`、`exchange` 及实际消费者使用的其他旧符号，签名以最终基线为准。

- [ ] 枚举消费方和测试注入点；搬移前后比较导入与签名，给未覆盖的兼容性风险补最小测试。
- [ ] 原样搬移职责块，核对请求体、响应解析、错误映射及资源关闭顺序；旧模块显式再导出。
- [ ] 运行 `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_e03.py tests/backend/test_e04.py tests/backend/test_l05.py tests/backend/test_c02b_disable_thinking.py -q`，再运行后端全量门禁 `scripts/verify/backend.sh full`。

## Task 2: OPT-06B：extract_task.py

**Files:** 保留 `src/backend/app/workers/extract_task.py` 作为任务入口与调度装配；候选新模块为 `extraction/types.py`（数据类型和阈值）、`extraction/candidates.py`（序列化/分组/读取候选）、`extraction/units.py`（单元抽取和重试）、`extraction/state.py`（检查点与状态写入）、`extraction/dispatch.py`（有界调度与进度），包目录位于 `workers/` 下。

**Interfaces:** 保留 `ExtractStatus`、`ExtractOutcome`、`ExtractLimits`、`ExtractionToolkit`、`TaskEntity`、`FailedChunk`、`FailedSection`、`ExtractionCandidates`、`RunOnceResult`、`task_entity_id`、`exceeds_threshold`、`fail_for_credential`、`run_extract_stage`、`load_candidates`、`run_once` 的旧路径与签名。

- [ ] 核对最终基线是否包含提速分支；枚举跨模块类型和私有函数依赖，先划清无循环依赖的移动组。
- [ ] 按类型 → 候选数据 → 单元执行 → 状态/调度顺序搬移；调度循环、失败阈值、租约检查点与数据库上下文保持原顺序。
- [ ] 运行 `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_e12.py tests/backend/test_demo_mode.py tests/backend/test_c02_phase_logs.py tests/backend/test_k02_run.py -q`，再运行 `scripts/verify/backend.sh full`；若最终基线已含提速测试，同步加入其定向回归。

## Task 3: OPT-06C：useMaterials.ts

**Files:** 保留 `src/frontend/src/composables/useMaterials.ts` 的状态和请求/SSE 生命周期；候选新模块为 `materials/files.ts`（扩展名/同章异格式/大小校验）、`materials/status.ts`（阶段与流状态呈现）、`materials/errors.ts`（错误映射）、`materials/types.ts`（内部共享类型），目录位于 `composables/` 下。

**Interfaces:** 保留 `useMaterials(options: UseMaterialsOptions)` 的返回对象，以及 `MATERIAL_EXTENSIONS`、`SUPPORTED_FORMATS_TEXT`、`MATERIAL_ACCEPT`、`sameChapterOtherFormat`、`formatBytes`、`validateMaterialFile`、`taskStatusOf` 与全部原导出类型。

- [ ] 记录导出/返回值清单，原样搬移纯函数和类型；旧入口显式再导出，避免对 reactive 状态做值拷贝。
- [ ] 保留 composable 内 watch、上传/取消/删除、请求代次和 dispose 顺序；执行切课、晚到响应、任务终态回归。
- [ ] 运行 `npm --prefix src/frontend run test -- --run h02.test.ts`，再运行 `scripts/verify/frontend.sh full`。

## Task 4: OPT-06D：StudentGraphView.vue

**Files:** 保留 `src/frontend/src/views/StudentGraphView.vue` 页面入口、模板、样式和 API 注入；候选新模块为 `composables/useStudentGraphPanel.ts`（宽度、分隔条、开关、observer/键盘生命周期）、`composables/useStudentGraphPresentation.ts`（画布焦点数据、章节布局输入、预览及掌握进度计算）。

**Interfaces:** 页面仍使用原路由与注入键；新 composable 接收原 refs/computed 和回调，返回现有模板同名绑定。实现前从最终基线提取精确类型；不引入 DOM 包装层，不改变 scoped 样式作用域。

- [ ] 保存同数据、1440/1280/768/390 宽截图；保留模板绑定名称与事件顺序，再逐职责搬移 script 逻辑。
- [ ] 运行 `npm --prefix src/frontend run test -- --run h11.test.ts i06.test.ts l13-kp-link.test.ts l14.test.ts student-graph-workbench.test.ts`，再运行 `scripts/verify/frontend.sh full`。
- [ ] 浏览器比较截图并走查窄屏抽屉、分隔条拖拽/键盘、Esc/还焦点、深链接、掌握状态与推荐刷新；无法执行的项目单列未验证。

## Task 5: 各项收尾

- [ ] 每项记录最小相关测试、相应后端/前端全量测试和 `./scripts/verify.sh` 的实际结果；前端确认 type-check 与 build 均通过。
- [ ] 查看最终 diff / `git diff --check`，核对行为、导出清单及契约无变化。
- [ ] 更新源码映射、任务状态及 `docs/handoffs/codex-opt-06[a-d].md`，每项保留独立可审查范围；远端提交/推送/PR 按用户授权执行。
