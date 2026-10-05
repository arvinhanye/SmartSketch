# 架构与边界

## 当前审查与实施入口

- 2026-09-22 现状核查与技术全景：[架构审查](architecture-review-2026-09-22.md)。契约真源与生成链按 A10 批 1 在集成分支导入；以本节和 ADR-016 的现行决定为准。
- 单轮实施范围与依赖：[原子任务清单](atomic-task-plan.md)，机器可读版为 `docs/atomic-tasks.json`。清单中的建议不自动替代已确认 ADR。
- 后续完成后审查：[Claude → Codex 流程](claude-review-workflow.md)。

## 逻辑分层

```text
Vue 3 Web（教师端 / 学生端）
          │ REST + SSE
FastAPI API（认证边界、DTO、依赖注入）
          │
领域服务（导入、抽取、融合、审核、问答、路径）
          │
仓储层 ────────────── Worker
  │                      │
Neo4j（图谱/向量）    SQLite（课程、用户、任务、进度、版本）
```

## 源码映射

| 目录 | 职责 | 不应包含 |
| --- | --- | --- |
| `src/frontend/` | Vue 页面、组件、状态、API/SSE 客户端、G6 适配 | 后端实体规则、Cypher |
| `src/backend/app/api/` | FastAPI 路由与依赖注入 | 业务编排、查询字符串 |
| `src/backend/app/schemas/` | 请求/响应/事件 DTO | 持久化实现 |
| `src/backend/app/services/` | 领域规则、流程编排 | HTTP/框架细节 |
| `src/backend/app/repositories/` | Neo4j / SQLite 读写 | 产品策略 |
| `src/backend/app/workers/` | 长时文档任务与状态迁移；以与 API **同机的独立进程**运行，经 SQLite 租约领取任务（`specs/task-processing.md` §8，ADR-011）；常驻入口 `python -m app.workers`（`workers/runner.py`，K08/ADR-039）先过与 API 相同的启动门禁，再起 `WORKER_PROCESSES` 个子进程循环调用 `run_pipeline_once` | Web 请求处理；跨机器部署 |
| `src/contracts/` | OpenAPI 真源、REST/SSE/图谱交换约定与只读生成类型 | 供应商专用密钥/实现、两端自定义的重复 DTO |

## 前端构建、测试与应用外壳（B01～B04）

- `src/frontend/index.html` 只提供 `#app` 挂载点；`src/frontend/src/main.ts` 创建并挂载 Vue 应用，`App.vue` 是单个无业务占位页面。
- Vite 负责开发服务器与产物构建，`vue-tsc` 单独执行严格类型检查；依赖版本由 `src/frontend/package-lock.json` 锁定。
- 测试（B02）：`src/frontend/vitest.config.ts` 继承 `vite.config.ts`，收集仓库外层 `tests/frontend/**/*.test.ts`（jsdom 环境，排除点开头目录，零用例即失败）；测试文件中的裸模块从 `src/frontend/node_modules` 解析。类型检查拆为应用（`tsconfig.json`，浏览器类型）与 Node 侧（`tsconfig.node.json`：构建/测试配置与 `tests/frontend`），应用代码不可见 Node 类型。
- 路由（B03）：`src/frontend/src/router/index.ts` 的 `createAppRouter({ history, getAccountRole })` 按账号类型（`users.role`）把 `/` 引到 `/teacher` 或 `/student`；错角色或未登录时回到对应页面并经 `query.notice` 由 `App.vue` 显示可关闭的 `role="alert"` 提示。关闭提示只隐藏当前消息，路由变化后可再次显示。守卫只是界面引导，授权以后端为准（`specs/identity-access.md` §2.4）。账号类型由调用方注入；登录与会话存储由 H13 接入（D-09），在此之前入口恒为未登录。
- 认证页品牌区（`AuthLayout.vue`）：左侧说明文字下的 SVG 由多组知识主题节点构成，挂载时在专用绘图区随机放置并赋予不同初始尺寸；`authGraphMotion.ts` 在动画帧中移动、缓慢缩放与旋转图谱，处理边界和图谱碰撞。减少动态效果或窄屏时停止动画，组件销毁时取消动画帧。整幅图 `aria-hidden`，图中标签禁用用户选择与指针事件；右侧表单和身份流程不依赖这幅装饰图。
- 课程上下文（B04）：`src/frontend/src/stores/course.ts` 的 `useCourseStore` 持有当前课程与课程内图谱（`GraphExchange`）、问答历史（`ChatTurn[]`）。切课即清空并中止旧 `AbortController`；composables 先 `beginRequest()` 取作用域，把 `scope.signal` 交给 HTTP 客户端，再经 `setGraph` / `appendChatTurns` / `commit` 提交，作用域按代次失效，晚到响应被丢弃。store 与组件都不直接发请求。
- 图谱画布（H03/H04）：`graph/adapter.ts` 把 `GraphExchange` 转为独立的 G6 数据；`graph/lifecycle.ts` 的 `createGraphLifecycle` 负责建图、串行更新、resize 与销毁，G6（`@antv/g6`，版本精确锁定）经工厂按需加载，工厂可由 `GRAPH_FACTORY_KEY` 注入替换；`components/GraphCanvas.vue` 只接收适配图并发出 `nodeClick(kpId)`，不发请求（ADR-040）。
- 图谱筛选与布局（H05）：`composables/useGraphFilters.ts` 在适配图上按搜索词、关系类型、知识点类型、审核状态、章节算出可见图（关系须两端可见，无悬空边），并给元素打 `rejected`/`lowConfidence`/`selected` 状态；选中与布局独立于筛选条件。`components/GraphToolbar.vue` 是搜索、关系图例兼筛选、布局切换与清空的受控组件。`GraphCanvas` 的 `layout` 属性经 `lifecycle.setLayout` 在原图上重新布局（层次 `antv-dagre`／力导向 `d3-force`），不重建、不重设数据（ADR-052）。
- 学生图谱页（H11）：`views/StudentGraphView.vue`（`/courses/:cid/graph`）组装画布、工具栏、卡片与详情；`composables/useStudentGraph.ts` 只在课程内学生角色下、按 `Course.published_version` 经 `api/graph.ts` 读图并核对响应的 `course_id`/`graph_version`，任何入口不读草稿；`components/KnowledgeCards.vue` 是分页、可键盘操作的卡片视图，与图共用 `useGraphFilters` 的筛选与选中（ADR-063）。
- 教师图谱编辑页（H14）：`views/TeacherGraphView.vue`（`/courses/:cid/graph/edit`，仅教师账号）组装草稿画布、工具栏与三个页签面板（H06 详情、H07 节点编辑、H08 关系编辑）；`composables/useTeacherGraph.ts` 只在课程内教师角色下经 `api/graph.ts` 的 `DraftGraphApi`（不带版本号）读草稿，核对 `course_id` 且 `graph_version` 为 null 后写入课程 store，三个编辑器共用这份图，成功写回后画布随之更新；`useSelectionGuard` 在节点面板有未保存修改时先确认再切换（ADR-067）。
- 教师审核队列页（H09）：`views/ReviewView.vue`（`/courses/:cid/review`，仅教师账号）展示低置信度关系、疑似重复、孤立知识点三栏并转发处理；`composables/useReview.ts` 在课程内教师角色下经 `api/review.ts` 读队列（键集分页）、单项处理与合并，数量只取服务端 `totals`，一次只允许一个处理，会连带影响其他栏的处理后重读三栏；关系两端名称取自草稿图谱，读不到退回 ID（ADR-070）。
- 发布历史与回滚面板（H10）：`components/VersionPanel.vue` 嵌入 H09 审核页；`api/versions.ts` 只封装 G06 端点，`composables/useVersions.ts` 先核对课程内教师身份，再读取历史并管理发布/回滚。学生可见指针只采纳重新读取的 `Course.published_version`，失败或刷新未确认时保留上次确认值；回滚先显示目标版本并确认（ADR-073）。

## 后端启动与健康检查（B05）

### C03 身份与访问依赖

- `services/access.py` 校验 C13 的 HS256 JWT，严格检查四个载荷字段及有效期，并按 `sub` 每次回查 `users`；账号类型取数据库。`api/dependencies.py` 从 Bearer 头取得调用者，不读取自定义身份头或请求体 `user_id`。
- 课程访问由 `course_members` 的实时课程角色决定。按 `specs/identity-access.md` §4.1 顺序检查成员、角色、发布状态。课程不存在与非成员同为 403；任务 ID 通过仓储只读归属查询定位，任务不存在或非成员同为 404。下游路由应直接复用依赖，不自行检查 JWT 或信任令牌 `role`。
- 身份/访问拒绝由统一异常处理器输出契约 `Error` 形状；认证错误只返回 `UNAUTHENTICATED`，不输出令牌与请求输入。

### C04 课程列表与创建 API

- `api/courses.py` 只转换 HTTP、注入 C03 身份依赖；`services/courses.py` 按成员课程角色和 `published_version` 过滤列表，并按 `specs/teacher-review-publish.md` V7 从发布指针及修订号推导 `Course.status`。课程与创建者教师成员由 C02 仓储在同一个 SQLite 事务写入。
- 请求/响应直接使用 `src/contracts/v1/generated/python/models.py` 的 `CourseCreate`、`Course` 等类型，经 `app/schemas/contracts.py` 从仓库真源生成物加载，不另写同名 DTO。未有图谱计数时省略可选的 `kp_count`；部署打包时需包含该生成物（K08）。

- `src/backend/app/main.py` 暴露 `create_app()` 与 `app`，将路由注册到 FastAPI。创建应用和导入模块时不连接数据库、模型服务或外部网络；B06 从环境变量读取并校验设置，默认 fake 模式不要求真实模型密钥，非法配置使应用创建失败。
- `GET /health` 是无鉴权的根路径，返回 HTTP 200 和 JSON 对象 `{"status": "ok", "version": "<非空版本字符串>"}`。它只表示 API 进程可响应，不表示 Neo4j、SQLite 或模型服务就绪。响应形状沿用待 A10 导入的 `src/contracts/api.v1.yaml` 现有定义，不新增契约真源。
- 健康检查不接受写入方法；未知或带 `/api/v1` 前缀的健康路径不注册。B05 的测试须覆盖响应、路径边界、错误方法，以及应用工厂无网络副作用。
- `src/backend/app/api/health.py` 中的最小响应模型是契约生成物尚未导入 main 时的 B05 过渡实现。A10/B14 接续导入并生成真源 DTO 后，应按 ADR-004 改为消费生成模型，避免手写公共 DTO 长期存在。

## E07 向量适配边界

E07 接收配置与 E02 `EmbeddingClient`，依 `EMBEDDING_BATCH_SIZE` 分批，并把请求维度传给客户端。输出逐条附 `model`、`dimensions`、`space`；空间格式为 `fake/<dimensions>` 或 `real/<model>/<dimensions>`，即使真实模型 ID 为 `fake` 也不与 fake 模式碰撞；`EMBEDDING_MODE=demo` 的模型取保留 ID `smartsketch-demo-ngram-v1`（`real/smartsketch-demo-ngram-v1/<dimensions>`，ADR-076），空间推导统一由 `app.config.embedding_space_identity` 给出，E07、B06、F03 索引创建与 V12 重新向量化共用。响应数量、每条维度、有限数值及显式响应模型须在缓存前核对。同一次调用先按 `(space, sha256(text))` 合并待计算文本，跨批重复只请求模型一次，再按原输入位置展开。进程内缓存使用相同键，默认最多保留 1024 条向量并按最近使用顺序淘汰；淘汰后再次读取会重新计算。失败批次不写缓存，已完成批次可供重试复用。在线/本地客户端由 E03 注入，E07 不自行切换供应商或空间。

## 后端设置与启动校验（B06）

- `src/backend/app/config.py` 定义只从环境变量构造的类型化 `Settings`；`create_app()` 在创建 FastAPI 对象前执行环境校验，并把设置放入 `app.state.settings`。应用构造/模块导入不连接外部服务，也不读取 `.env` 文件。ASGI lifespan 启动阶段执行本地 SQLite 向量空间门禁；后续 worker 入口调用同一门禁。
- 数值范围、URL、模型模式与条件必填按 `docs/integrations.md`「启动校验」和 `specs/task-processing.md` §8.8 执行；非法配置只报告变量名。密钥使用 Pydantic `SecretStr`，设置对象的 `repr` 不含明文。
- 默认 fake 模式无需真实模型密钥。发布租约与课程写锁参数按 ADR-012 登记在 `.env.example`。`embedding_space_state` 是 SQLite 单行引导表：`singleton = 1`，存 `model`、`dimensions`、`is_fake`；fake 独占空间，在线与本地模式按模型 ID + 维度标识空间，demo 模式记为保留模型 ID + 维度、`is_fake = 0`（ADR-076，无需迁移）。表由 C01 迁移 001 创建；启动门禁只在 `BEGIN IMMEDIATE` 事务内读取该行，无记录时写入配置空间（ADR-012 补注修订 1）；已有记录不一致则拒绝启动并报告记录/配置空间及离线重新向量化要求，不改旧记录。C01 的 `001_base.sql` 与迁移运行器须保留并接管此表；回滚时用迁移前 SQLite 备份恢复，不删除此表来绕过门禁。Neo4j 向量/索引完整性仍由 F03/E07 校验。
- C01 的 SQLite 连接从已校验的 `SQLITE_URL` 取路径，启用 WAL、外键，并将每个连接的 `busy_timeout` 固定为 5000 ms。迁移版本记录在 `schema_migrations(version, filename, checksum, applied_at)`；`001_base.sql` 用 `CREATE TABLE IF NOT EXISTS` 接管 B06 的 `embedding_space_state`，不覆盖现存单行，并建立以 `call_id` 为主键的 `model_calls`（字段见 `docs/integrations.md`「调用记录」）。迁移只向前，逐文件在写事务内应用并记录摘要；已应用文件摘要变化即拒绝；摘要按 LF 归一化后的内容计算，`.gitattributes` 固定迁移文件为 LF。API lifespan 先调用 `validate_schema_current`：有未执行的迁移或历史不一致即拒绝启动（C09 worker 入口须调用同一检查）。每次待执行迁移前，按 `specs/task-processing.md` §8.7 检查有效租约/课程锁、`VACUUM INTO` 备份并验证完整性，校验连接随即关闭；恢复须停机并替换数据库文件。
- 模型与向量客户端统一由 `app.services.ai.factory` 按 `LLM_MODE` / `EMBEDDING_MODE` 装配（worker `build_toolkit`、问答 `chat_service`、发布 `publish_context`、`scripts/backfill_chunk_vectors.py` 共用；`scripts/reembed.py` 同一分支）。`demo` 模式（ADR-076）用 `app.services.ai.demo`：`DemoModelClient` 复用 E02 fake 的截断、模拟 usage 与流式切片，按 `ModelRequest.purpose` 用规则产出能被 E05/E06/E11/J03/J05/E10 真实解析器接受的输出（`PREREQUISITE` 只在含先修表述时给出，且单次输出内先做环检测）；`DemoEmbeddingClient` 为字符 n-gram 哈希词袋向量。演示结果只用于演示与端到端验收，不代表抽取或问答质量；`production` 禁用。
- `API_HOST` 与 `API_PORT` 由 `python -m app` 的 Uvicorn 启动入口使用；直接调用 Uvicorn CLI 时，其 `--host`/`--port` 参数由调用者负责。

## 契约真源与生成物（ADR-004）

下表是 ADR-004 的裁定（2026-09-22 由 ArvinHan 签收），完整理由见 `docs/decisions.md`。**任何 REST / SSE / 图谱格式变更的第一步必须是改真源**；本节固定分工，避免两端各写一份接口。

| 角色 | 位置 | 谁写 | 规则 |
| --- | --- | --- | --- |
| 人工编辑真源 | `src/contracts/api.v1.yaml`（OpenAPI 3.1） | 后端 Agent | 唯一允许人工编辑的机器可读契约；任何 REST/SSE/图谱格式变更的第一步 |
| 配套语义文档 | `src/contracts/errors.v1.md`、`src/contracts/events.v1.md` | 后端 Agent | 只写 OpenAPI 表达不了的时序与语义，不重复定义结构 |
| 生成物 | `src/contracts/v1/generated/`（`openapi.json`、`schemas/*.schema.json`、`python/`、`typescript/`） | `./scripts/gen-contracts.sh` | 入库、**禁止手工编辑**；两次生成字节一致；`--check` 不通过即拒绝合入 |
| 后端消费 | `src/backend/app/schemas/` | 后端 Agent | 只放不对外暴露的内部模型；对外 DTO 从 `v1/generated/python/` 导入 |
| 前端消费 | `src/frontend/src/api/` | 前端 Agent | 类型从 `v1/generated/typescript/` 导入；不得重写、断言或 `any` 绕过 |

- REST 路径前缀与 wire 枚举已由 A02 裁定（ADR-009），见下一节。
- 生成器及版本锁在 `src/contracts/toolchain.txt`；CI 按其安装。缺工具时生成脚本必须非 0 退出，只有显式降级才允许跳过并打印未完成验收标记。
- `scripts/verify.sh` 调用 `scripts/verify/contracts.sh`，依次校验真源结构、生成物同步和门禁负例；缺依赖或生成物漂移均失败。
- 契约校验输出显式 `PASS` / `FAIL`；仅直接传入 `--allow-scaffold` 时，缺依赖可输出 `SKIP` 与 `INCOMPLETE`，该结果不构成验收。仓库门禁不传降级参数；后端测试额外依赖须包含 `toolchain.txt` 锁定的 PyYAML、OpenAPI 校验器与 JSON Schema 校验器。
- 契约的**表达方式**由 ADR-004 裁定，契约的**内容正确性**不由它保证：来源非空、事件判别联合等约束仍须各自的负例测试复验；「引用确属同一课程同一发布版本」schema 表达不了，必须在服务层校验。

## API 前缀与 wire 枚举（A02 / ADR-009）

> **签收状态：已签收**，ArvinHan，2026-09-22。本节是路径前缀、枚举取值与大小写的规范表；`src/contracts/api.v1.yaml` 导入 main（A10）时必须与本表逐值一致，不一致以本表为准回改真源，并同批重新生成。状态转换语义不在本节，见 `specs/task-processing.md`（A03 / ADR-010）。

### 路径前缀

- 所有 REST 与 SSE 端点前缀为 **`/api/v1`**；唯一例外是 `GET /health`（运维探针，不随契约版本变化）。
- 主版本号四处同步：真源文件名 `api.v1.yaml` = URL 前缀 `/api/v1` = 生成物目录 `v1/` = 配套文档 `events.v1.md`/`errors.v1.md`。破坏性变更成套新建 v2，不在 v1 路径下混入。
- S2 方案表 6.6 的 `/api/...` 是省略版本号的书面缩写，不是另一套路径。实现、测试与前端客户端一律写 `/api/v1`；ADR-004 端点迁移表（22 路径 / 29 操作）无需改动。

### 大小写规则

1. **UPPER_SNAKE 只用于两类**：错误码 `ErrorCode`，以及图关系类型 `RelationType`（与 Neo4j 关系类型标签同形）。
2. **其余一切 wire 枚举值一律 lower_snake**，包括领域状态、判别字段取值与 SSE 事件名。
3. 新增枚举若既不是错误码也不是图关系类型，必须 lower_snake；同一概念不得出现大小写变体或同义别名（例如不得写 `canceled`、`md`、`NOT_COVERED` 作 wire 值）。

### wire 枚举表

取值顺序即真源中的顺序。「740adb 核对」指与 `claude/worktree-contract-conflicts-740adb` `978671e` 的 `api.v1.yaml` 逐值比对的结果。

| schema | 取值 | 大小写 | 用于 | 740adb 核对 / 备注 |
| --- | --- | --- | --- | --- |
| `ErrorCode` | `UNAUTHENTICATED`、`COURSE_FORBIDDEN`、`ROLE_FORBIDDEN`、`NOT_FOUND`、`GRAPH_NOT_PUBLISHED`、`UNSUPPORTED_FORMAT`、`FILE_TOO_LARGE`、`VALIDATION_ERROR`、`CYCLE_DETECTED`、`DANGLING_ENDPOINT`、`DUPLICATE_RELATION`、`NODE_LOCKED`、`TASK_NOT_CANCELLABLE`、`PUBLISH_BLOCKED`、`RATE_LIMITED`、`LLM_UNAVAILABLE`、`DOCUMENT_UNREADABLE`、`EXTRACTION_INCOMPLETE`、`STORAGE_UNAVAILABLE`、`INTERNAL_ERROR`、`TASK_ATTEMPTS_EXHAUSTED`、`PUBLISH_IN_PROGRESS`、`COURSE_BUSY`、`BUDGET_EXCEEDED`、`DOCUMENT_NOT_DELETABLE`、`REVISION_CONFLICT`、`USERNAME_TAKEN`、`MODEL_CONFIG_REQUIRED` | UPPER | `Error.code` | 一致。**不含** `NOT_COVERED`、`TASK_FAILED`：它们是领域状态，不是错误码 |
| `RelationType` | `CONTAINS`、`PREREQUISITE`、`RELATED_TO`、`EXAMPLE_OF` | UPPER | `Relation.type` | 一致。闭集；S2 图 6.3 的 `RELATED`、`APPLIES_TO` 不得使用（ADR-008） |
| `TaskStage` | `queued`、`parsing`、`extracting`、`merging`、`persisting`、`awaiting_review`、`completed`、`failed`、`cancelled` | lower | `Task.stage`、`TaskEvent.stage`、`Document.parse_status` | 一致。终态为 `completed`、`failed`、`cancelled`；转换、触发者与取消语义见 `specs/task-processing.md`（ADR-010） |
| `CourseStatus` | `draft`、`published`、`revising` | lower | `Course.status` | 一致 |
| `KnowledgePointStatus` | `draft`、`low_confidence`、`approved`、`rejected` | lower | `KnowledgePoint.status`、`Relation.status` | 一致。名字带 KnowledgePoint，但关系也复用；自动降级的边取 `low_confidence` |
| `KnowledgePointType` | `concept`、`theorem`、`formula`、`method`、`example` | lower | `KnowledgePoint.type` | 一致 |
| `NodeSource` | `ai`、`manual` | lower | `KnowledgePoint.source`、`Relation.source` | 一致。自动降级只作用于未经教师确认的 `ai` 边（`status ∈ {draft, low_confidence}`，见规格「前置关系成环处理」） |
| `DocumentFormat` | `pdf`、`docx`、`txt`、`markdown` | lower | `Document.format` | 一致。wire 值是 `markdown`，扩展名 `.md` 不是枚举值 |
| `Role` | `teacher`、`student` | lower | `User.role` | 一致 |
| `MasteryStatus` | `unknown`、`learning`、`mastered` | lower | 进度读写 | 一致；I01 的 SQLite `learning_progress` 以 `(user_id, course_id, kp_id)` 为主键保存原始状态、`updated_at` 与共享序列 `write_seq`，跨版本继承只在读时投影；I02 的 `app/services/learning/progress.py` 负责投影与批量写入，`GET`/`PUT /progress` 仅学生成员可用（ADR-064）；I05 `GET /recommend` 在同一绑定版本上读已提交快照的图与该投影计算推荐（ADR-069） |
| `ChatStatus` | `answered`、`not_covered` | lower | `ChatResponse.status`（判别字段）、`ChatMetaEvent.status` | 一致 |
| `NotCoveredReason` | `no_retrieval_hit`、`below_similarity_threshold`、`insufficient_evidence`、`all_citations_invalidated` | lower | `ChatNotCovered.reason` | `ff30e0` 无此枚举。`insufficient_evidence` 取代 `740adb` 的旧值（语义为生成模型以哨兵声明证据不足），A09 决定（ADR-015 决定 3），B13 落实真源；前两者不调用生成，后两者调用了生成 |
| 内联枚举 | `ChatTurn.role`：`user`、`assistant`；`LoginResponse.token_type`：`bearer`；`/health` 的 `status`：`ok` | lower | 见左 | 一致 |

SSE 事件名（`event:` 行；问答流的 `data.event` 判别字段与之同值）：

| 流 | 事件名 | 终止事件 |
| --- | --- | --- |
| 任务进度 `GET /api/v1/tasks/{tid}/events` | `stage`、`done`、`error`、`cancelled` | 只覆盖处理阶段。每个连接恰好以一条结束事件收尾：`stage = awaiting_review` 快照或 `done` / `error` / `cancelled` 之一（互斥），随后关流；`completed` 不经已有连接送达，通过任务查询或课程发布状态观察（ADR-010） |
| 问答 `POST /api/v1/courses/{cid}/chat` | `meta`、`delta`、`done`、`error` | `meta` 恰好一条且为首条；`done` / `error` 互斥且恰好一次。客户端断开时服务端停止生成、不再发事件；流未以二者之一结束时客户端本地按错误处理并撤回临时正文（A09，`specs/grounded-qa.md` Q2、Q5、Q6） |

### 文档用语 → wire 值

AGENTS.md、ADR-003、`.claude/rules/backend.md` 等共同契约沿用概念名；它们不是 wire 字面值。新代码、测试断言与前端分支**只使用右列**。

| 文档用语 | wire 表达 | 说明 |
| --- | --- | --- |
| `NOT_COVERED`、「资料未覆盖」 | HTTP 200 + `status: "not_covered"` + `reason: NotCoveredReason` + `citations: []` | 概念名。字段名是 `reason`，不是 `not_covered_reason`（740adb 的 `src/contracts/README.md` 写法有误，以 YAML 为准） |
| 「临时正文」「引用撤回」 | 无独立 wire 字段：临时正文 = 已收到 `delta` 的拼接；撤回 = 结局不是 `done` + `answered` 时客户端清除临时正文 | 答案为 `answered` 时 `final.answer` 恒等于 delta 拼接（A09 不变式 I1，`specs/grounded-qa.md` Q3.3） |
| `TASK_FAILED`、「任务失败」 | HTTP 200 + `stage: "failed"` + `error: Error` | 同上，领域状态不是 HTTP 错误 |
| S2「已上传」 | `queued` | |
| S2「入库中」、前端文案「校验入库」 | `persisting` | 覆盖 DAG 校验与草稿写入 |
| S2「完成」（处理流程结束） | `awaiting_review` | 处理完成待审核；`completed` 由教师发布触发，发布时按任务水位推进（含内容被全部驳回的任务），不经 SSE 送达（A03 已复核，ADR-010） |
| 「已取消」 | `cancelled` | 双 l |
| 前置 / 包含 / 相关 / 应用实例 | `PREREQUISITE` / `CONTAINS` / `RELATED_TO` / `EXAMPLE_OF` | S2 成环降级的目标「相关」即 `RELATED_TO` |

## 核心数据模型

- SQLite：`Course`、`Material`、`ProcessingTask`（含租约与尝试字段）、`TaskChunkCheckpoint`、`CourseLock`、`ModelCall`、`GraphVersion`、`LearningProgress`、`ChatLog`（表 `chat_logs`，每个通过鉴权与版本绑定的问答请求一行，服务端不保存会话；命名由 A09 定，ADR-015，A10 N5；覆盖范围见 ADR-015 修订 1）。其中 `ProcessingTask`、`TaskChunkCheckpoint`、`CourseLock`、`ModelCall` 的字段与迁移规则见 `specs/task-processing.md` §8（ADR-011）。`GraphVersion` 保存每个版本的规范化快照与摘要，`Course` 保存发布指针与草稿修订号（见下节「图谱版本与跨库发布」）。
- SQLite `processing_tasks`（C09 迁移 005，ADR-017 决定 1）：租约六列 `lease_owner`、`lease_token`、`lease_expires_at`、`attempt`、`not_before`、`cleanup_pending`，与任务错误三列 `error_code`、`error_message`、`error_details`（JSON 对象文本，与契约 `Error{code, message, details}` 同构）；数据库 CHECK 强制 `stage = 'failed'` ⇔ `error_code` 非空。均为内部字段，经 `Task.error` 对外；可用码与阶段见 `specs/task-processing.md` §6 与 C08 `FAILURE_CODE_STAGES`。
- Neo4j：`Course`、`KnowledgePoint`、`Chunk`；关系 `CONTAINS`、`PREREQUISITE`、`RELATED_TO`、`EXAMPLE_OF`，以及来源关联 `(:KnowledgePoint)-[:EVIDENCED_BY {task_id, chunk_id, evidence_start, evidence_end}]->(:Chunk)`（F04，ADR-024；人工来源不带 `task_id`）。知识点、关系、章节带 `version_id`（草稿为保留值 `"draft"`）；文本块不可变、各版本共享。
- F03 Neo4j DDL 在 `migrations/neo4j/001_constraints.cypher`，由 `graph_migrations.apply_migrations` 逐条重跑：知识点、章节、共享文本块的作用域复合唯一约束，四种关系各自的复合唯一约束，跨关系类型的 `RelationIdentity(course_id, version_id, rel_id)` 守卫节点唯一约束，以及贡献/修订查询索引。F06 写关系须在同一事务先 MERGE 守卫节点，才能保证 `rel_id` 跨四种类型唯一。F06 另以 `DraftWriteGuard(course_id, version_id)` 课程守卫节点串行同一课程草稿的关系写事务：先锁守卫，再读图、环检测、写入，同一事务提交（ADR-025）；F10 合并知识点也在同一守卫下完成重接、去重、验环与删除（ADR-047），F09 删除知识点在同一守卫下只清理草稿中的节点、相连关系与关系身份（ADR-048）。Neo4j DDL 不作全批回滚；失败修复冲突数据或服务后重跑，不自动删除已有对象。向量属性与索引按空间标识散列派生并并存；F03 写入边界每次从 SQLite 读取当前空间，离线迁移上下文绑定目标空间且在当前空间切换后失效。
- 所有查询和写入均以 `course_id` 为第一隔离条件，图查询同时以 `version_id` 为第二条件。`PREREQUISITE` 只能形成 DAG。
- 关系编辑 HTTP 路由（F06-API，ADR-071）：`api/relations.py` 只做协议转换与依赖注入（课程教师依赖、错误映射、PATCH 请求体逐字段校验）；`services/graph/edit_relation.py` 复用 F08～F10 的课程写锁与 F12 审计（`audit.begin/commit`）以及 F06 的 `apply_relations`（守卫锁、端点校验、重复关系、DAG 环检测），改 `type`/端点时在同一事务内先删旧关系与旧身份再写新身份，只改 `status` 时就地改并保留 `source_pairs`；`repositories/graph_relation_edit.py` 放按 `rel_id` 读一条可见关系、删除关系与其 `RelationIdentity`、同身份改状态的语句。响应由写事务内读回的图与 SQLite 文本块组装，不回声请求体。关系审计行复用 `graph_edit_logs` 的 `create`/`update`/`delete` 动作，以摘要的 `entity = "relation"` 与节点行区分（迁移 012 的 `action` 是数据库级闭集）。

## 图谱版本与跨库发布（A04 / ADR-012）

> **签收状态：已签收**，ArvinHan，2026-09-23（ADR-012，含修订 1）。规范文本只有一份，在 `specs/teacher-review-publish.md`「图谱版本与跨库发布协议」V1～V12；本节只列架构层面的结论，不复制步骤表。

| 问题 | 结论 |
| --- | --- |
| 版本标识 | 内部 `version_id`（ULID，尝试开始时生成、永不复用）；对外整数 `version`（按课程、提交时分配 `max+1`，无空洞） |
| 快照位置 | SQLite `GraphVersion.snapshot_json` 是版本内容的真相，附 sha256 摘要；Neo4j 按 `version_id` 物化副本供遍历与向量检索 |
| 文本块固定 | 文本块按资料修订（资料 + 内容哈希 + 解析器版本）生成 ID，一经写入不可变；快照固定修订列表，检索按 `revision_id` 过滤，不按 `material_id`（修订 1） |
| 向量版本 | 知识点向量随版本复制；文本块向量共享、发布时补齐（ADR-066）；Neo4j 向量索引「多取再过滤」 |
| 向量空间 | 运行时只有一个空间（模型 + 维度）；换模型须停机离线重新向量化 Neo4j 实际存量中的全部文本块、草稿知识点与已提交版本副本，并按存量核对；缓存与中间产物中的向量带空间标识；运行时写入只接受当前空间，只有迁移命令可写迁移目标空间（修订 2 补注）；配置与记录不一致即拒绝启动；向量是派生数据，重算不产生新版本（修订 1、修订 2） |
| 提交点 | 唯一：SQLite 中「CAS 切换发布指针 + 分配版本号 + T7 推进任务」的单个事务。之前任一步失败，按 `(course_id, version_id)` 删除 Neo4j 副本并把尝试记为 `failed`，学生继续读旧版本 |
| 互斥 | 同课程同时至多一个发布/回滚（SQLite 部分唯一索引）；草稿写入与建快照共用 A06 的 SQLite 课程写锁，发布只在读草稿的几秒内持锁 |
| 回滚编号 | 以历史版本内容前滚为新版本号；目标与当前版本摘要相同则幂等，不产生新号；回滚不改草稿、不推进任务 |
| 重复发布 | 发布集合摘要等于当前发布版 → 幂等返回 `unchanged: true`，不产生新号 |
| 读取绑定 | 学生请求开始时读一次指针，全程使用同一 `version_id`；MVP 不回收已提交版本 |
| 崩溃恢复 | worker 周期回收步骤清扫过期尝试与 `cleanup_pending`；Neo4j 有而 SQLite 无的版本只告警不删除 |

跨任务影响：ADR-012 修订 ADR-011 决定 6（课程写锁由「两处持有」扩大到所有草稿写入）；修订 1 再修订 ADR-011 决定 5、7（块 ID 按资料修订生成、来源块删除保护）；新增错误码 `PUBLISH_IN_PROGRESS`、`COURSE_BUSY` 已由 B08 纳入契约。B11 的对外 DTO 包括节点级 `revision`/编辑 `expected_revision`、关系降级解释、`PublishResult.unchanged/excluded`、`GraphVersion.kind/source_version` 与结构化 `PUBLISH_BLOCKED`；快照谱系 `merged_from` 和共享 `commit_seq` 仅内部持久化，不进入节点/版本 wire DTO。配置 `PUBLISH_LEASE_SECONDS`、`COURSE_LOCK_WAIT_SECONDS` 交 A07。

## 解析输出与来源定位（D01）

各格式解析器（D02～D07）统一输出 `src/backend/app/services/parsers/models.py` 的 `ParsedDocument`：块按 `ordinal` 从 0 起连续编号，每块带 `SourceLocator`。D08～D11 只消费这一结构。以下规则在构造时校验，违反即抛 `ParseModelError`（属实现缺陷）。定位字段最终写入 `SourceRef`：`page` 与 `section_path` 至少一个（ADR-003）。

| 格式 | `page` | `paragraph` | `line_start` / `line_end` | `section_path` |
| --- | --- | --- | --- | --- |
| PDF | 必填，≥ 1 | 不填（填了即拒绝） | 不填 | 只取标题路径；无标题时省略该键，只靠 `page` |
| TXT、Markdown | 不填（不编造页码） | 必填 | 必填：解码后源文本的物理行号，闭区间，块间递增不重叠 | 「标题路径 > 第N段」；无标题时为「第N段」 |
| DOCX | 不填（不编造页码） | 必填 | 不填 | 同上 |

- **段落号**：`paragraph` 是该块在同一组标题（`section_titles`）下按文档顺序的序号，从 1 起、连续不断档。同一标题路径在文档中再次出现时接续编号，因此「标题路径 + 第N段」在一份文档内唯一。例：`第3章 > 3.1 栈 > 第2段`。
- **标题规范化**：各级标题以 `" > "` 连接。标题先合并空白、去首尾，再把半角 `>` 替换为全角 `＞`，保证路径能无歧义地拆回各级标题。标题本身不成块。标题文字由 D08 分块时以章节路径的形式拼在每块正文前，供抽取与检索使用（D-13）。
- **空文档**：没有可提取文本（含扫描件无文本层）时不构造结果，抛 `DocumentUnreadableError`。`reason ∈ {corrupted, encrypted, no_text}`，对应任务错误 `DOCUMENT_UNREADABLE`。
- **资料修订**：`RevisionKey(document_id, content_hash, parser_version)`。其中 `parser_version` 为复合版本 `<解析器版本>+<分块版本>`（ADR-018），如 `txt/1+chunk/1@1500-200`：解析器段由解析器给出（一个或多个 `<名称>/<版本>` 按处理顺序用 `,` 连接，不含空白与 `+`，如 `txt/1`；PDF 流水线为 `pdf/1,cleanup/1,headings/1`，取 D06 `CLEANED_PARSER_VERSION`；ADR-018 修订 1），分块段由 D08 `chunking_version(target_chars, overlap_chars)` 给出（`chunk/<CHUNKER_VERSION 规则版本>@<target>-<overlap>`，取实际参数），二者只经 D09 `revision_parser_version` 拼接；D09 拒绝不含合法分块段的修订键，分块规则或参数一变即新修订、新块 ID。`content_hash` 形如 `sha256:<64 位小写十六进制>`，唯一来源是 C05 `FileStorage.save()` 返回的 `StoredFile.content_hash`，D11 直接使用、不重算。`revision_id` 与块 ID 的派生公式归 D09。

## 数据流

1. 上传资料 → SQLite 创建任务/资料记录 → Worker 进程经租约领取任务 → 解析和分块。
2. Worker 调用模型抽取候选节点/关系 → 融合消歧 → DAG 校验 → 写入草稿图谱。草稿按任务记录贡献，T6 提交后才可见，失败任务的内容从失败起即不可见（ADR-011 修订 1）。DAG 校验在 `persisting` 阶段：自动候选成环时把环上未经教师确认的 `ai` 边中置信度最低者降级为 `RELATED_TO` 并送审核，任务不因此失败；人工编辑成环直接 409 拒绝。两者区别见 `specs/course-knowledge-graph.md`「前置关系成环处理」。
3. Worker 更新任务状态，API 经 SSE 发送进度；教师审核并发布不可变图谱版本：持课程写锁读取草稿建快照 → SQLite 写快照 → Neo4j 按 `version_id` 物化并核对摘要 → SQLite 单事务切换发布指针（唯一提交点）。协议见上节「图谱版本与跨库发布」。
4. 学生浏览发布版本（请求开始时绑定一个 `version_id`）；学习进度保存在 SQLite，路径服务查询 Neo4j 前置关系并计算候选与理由。
5. 问答服务检索课程图谱与来源片段，生成带引用答案；若证据不足返回 `NOT_COVERED`（wire：`status: "not_covered"` + `reason`，见上方「文档用语 → wire 值」）。

## 关键质量边界

- API 响应、任务事件、图谱导入/导出格式先在 `src/contracts/` 版本化。
- LLM 是可替换适配器。`live`/`demo`/`fake` 模式下基础 URL、模型和密钥来自环境变量；`personal` 模式（ADR-080）下来自用户本人加密保存的配置：教师任务使用建任务时的密钥快照，学生问答按「用户 + 配置版本」隔离调用策略，用户填写的地址经出站校验并钉住已校验的 IP。向量为系统级在线服务（ADR-081），与用户所选生成模型无关。
- 每次教师修改与发布都保留版本号和审计信息；破坏性迁移需提供回滚说明。教师图编辑审计（F12，ADR-061）在 SQLite `graph_edit_logs`：与 `draft_revision + 1` 同一事务写入 `pending`，Neo4j 写入后置 `committed`/`aborted`，遗留行由下一次同课程教师写入持锁对账；摘要白名单并脱敏。

## 持续集成

- `.github/workflows/ci.yml` 在 push、pull request 和手动触发时运行三个并行 job，只使用只读仓库权限，不注入项目密钥：
  - **Repository scaffold**（CI-01）：`scripts/verify.sh` 及其 Bash 语法检查，含契约生成物漂移与门禁负例。
  - **Frontend**（CI-02）：Node 24 下 `npm ci`（锁文件）、`type-check`、`test -- --run`（收集 `tests/frontend`，零用例即失败）、`build`。
  - **Backend**（CI-02）：Python 3.12 下可编辑安装 `src/backend[test]`、`pip check`、`pytest tests/backend`。
- CI 通过表示上述单元/组件测试与构建通过，不代表 E2E、真实模型或数据库集成通过。K11 在 E2E（K05/K06）就绪后扩展同一门禁；新增检查必须失败即退出，不能以静默跳过冒充通过。


### 计划 B 接手补充（2026-10-03，ADR-086/087）
推荐结构化事实增加可选 importance_defaulted/difficulty_defaulted；服务层识别原始属性缺失，客户端不根据 0.5 猜测。课程作用域保存 myRole，外壳与概览共享同代在途读取但不缓存角色；切课/换号清空，建课返回也带会话代次保护。问答生成输出上限 2048、统一 15 秒截止与逐句出处校验不变。无表结构迁移，无新增外部服务。


### 个人生成模型的思考开关（ADR-090，2026-10-04）

`disable_thinking` 默认 false；保存时省略保留现值，新配置默认 false。配置与任务快照各增加一个 0/1 非空列（迁移018）。开启时，连接测试、问答改写/流式或非流式回答、抽取及 repair 仅追加 `thinking: {type: disabled}`；向量服务不变。学生模型缓存以配置 revision 刷新，教师任务使用创建时快照；中途改配置不追溯已有任务。关闭时不追加字段。供应商是否接受/忽略与性能质量效果由实测确认，不以连接成功代表已生效。测试未保存表单使用表单值，测试已存配置使用已存值；旧客户端可省略可选字段。输出上限、截止、出处与取消/撤销语义不变。


## 已批准设计、尚未实现：跨平台本机启动核心（STARTUP）

- 规格docs/superpowers/specs/2026-10-04-cross-platform-startup-design.md已获用户确认；实施计划docs/superpowers/plans/2026-10-04-cross-platform-startup-plan.md仍待审核，不代表已有可用发行入口。
- 新Go模块拟置于launcher/，仅管理本机首次环境配置、受控Docker编排和短期回环控制页面；不重写Vue业务、不把启动控制API加入业务OpenAPI、不引入系统配置数据库。基础设施仍经环境读取，个人生成模型例外继续按ADR-080。
- 发行Compose使用稳定安装ID的私有命名卷，与原开发/测量环境分离；首个教师通过一次性容器CLI/服务/仓储完成事务建号，无教师公开注册。已有学生注册与课程授权规则不变。
- 就绪不是/health单点成功，须确认迁移/向量空间与索引、Neo4j、API、worker及同源网页；停止保留数据。版本迁移先停机整组备份，恢复保留原卷并核验整组版本，禁止仅降级代码。
- 此段只登记已确认架构方向；新API/DTO/迁移/依赖与启动器代码本轮均未变，技术冻结NOT_PERFORMED。

## 本机启动控制层（2026-10-05，实现验收中）

Go 启动核心位于 launcher/，仅管理本机独立 Docker 安装；其 loopback HTTP 控制接口不是业务 API。配置/安装 ID/发行摘要位于用户私有目录，业务数据留在 ID 对应命名卷。浏览器向导把向量基础设施配置写入本机 .env；业务后端仍仅从环境变量读取。个人生成模型设置沿用 ADR-080，不增加全站向量配置 API。

发行 Compose 位于 packaging/compose.release.yaml，无 Neo4j 宿主端口，web 仅绑定 127.0.0.1。服务、schema、embedding space、索引与代理探测齐备才 READY。首位教师由容器 stdin 工具事务创建；不公开教师注册。升级先阻断、停机整组快照；恢复暂存并二次确认，保留原卷。缺真实发行摘要/三平台验收时不声明正式可用，stage_c_status 与 technical_freeze 不变。
