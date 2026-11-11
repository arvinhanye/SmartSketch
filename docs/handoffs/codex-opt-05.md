# OPT-05：后端分层修正

- task_id: OPT-05
- 状态：READY_FOR_REVIEW；实现、独立复核与续验完成。后端集成通过；原版个人模式 E2E 留有既有控件定位失败，整套原版 integration 门禁不标全绿。
- 负责人：Codex；实施日期：2026-11-05；续验日期：2026-11-09。
- 工作区：`/Users/arvinhan/Desktop/SmartSketch-main`。
- 分支：`codex/opt-05-backend-layering`；代码基线：`ad63341`。
- 输入：`AGENTS.md`、`.claude/rules/backend.md`、架构分层、发布/任务/问答规格，以及本地审查分支 `claude/code-structure-review-handoff-49e73a` 的 `docs/handoffs/claude-code-structure-review-codex-handoff.md` OPT-05（该文件不在本次代码基线中）。
- 不提交、不推送、不开 PR。过程中同一工作区出现 OPT-02 的测试与任务记录修改，全部保留；本次测试改动仅新增 `tests/tooling/test_backend_layering.py`。11 月 5 日全量门禁在包含 OPT-02 测试修改的共享工作区执行；11 月 9 日恢复时这些测试差异已不在当前工作区，未由本任务覆盖/回退。当前源码哈希仍与全量验证前记录一致。

## 交付与逐函数移动清单

下表路径均相对 `src/backend/app/`。“提取”表示领域函数仍在服务层，仅把数据库操作搬到右侧；未把领域判断整体搬入仓储。

| 原位置 / 函数 | 新位置 / 函数 | 保留的行为 |
| --- | --- | --- |
| `services/versions/materialize.py::_relations_query` | `repositories/version_materialize.py::_relations_query` | 关系类型插值与查询原文 |
| 同上 `::_copy_relations_query` | 同仓储 `::_copy_relations_query` | 源/目标版本限定与关系属性复制 |
| 同上 `::_written` 的查询执行部分 | 同仓储 `::_write_rows`、`write_chapters`、`write_nodes`、`write_evidence`、`write_relations` | 空批次不查询；写入数校验和 `MaterializeError` 留在服务事务回调内 |
| 同上 `::materialize.work` 的删除与事务入口 | 同仓储 `::delete_in`、`transaction` | 同一个事务先删，再写章节、节点、来源边、各类关系；校验失败整笔回滚 |
| 同上 `::verify.read` | 同仓储 `::read_chapters`、`read_nodes`、`read_edges` | 三次 worker 读取顺序不变；摘要/向量校验留服务 |
| 同上 `::drop_version` 的删除操作 | 同仓储 `::delete` | 非草稿校验留服务，不删除共享 Chunk |
| 同上 `::copy_version.work` 的数据库操作 | 同仓储 `::delete_in`、`copy_chapters`、`copy_nodes`、`copy_evidence`、`copy_relations`、`transaction` | 源副本节点计数检查仍在复制节点后、复制来源/关系前的同一事务中 |
| `services/versions/chunk_vectors.py::_missing_query`、`_write_query` | `repositories/version_chunk_vectors.py` 同名函数 | 模板逐字不变 |
| 同上 `::_chunks`、`_missing`、`_index_online` | 同仓储同名函数；原服务保留导入别名 | 修订排序、课程限定、缺失判断与索引状态读取不变 |
| 同上 `::index_chunks.work` 与事务入口 | 同仓储 `::write_batch`、`transaction` | 每批一个事务，短写检查仍在该事务回调内；向量生成留服务 |
| `services/embedding_configs.py::save` 的重建前发布检查 | `repositories/embedding_configs.py::active_publication` | 检查先于测试连接和重建 |
| 同上 `::save` 的保存事务 | 同仓储 `::config_update` | 原 `BEGIN IMMEDIATE` → 事务内发布检查 → 服务回调 → `COMMIT`；异常仍由连接关闭隐式回滚 |
| 同上 `::save` 的事务内读写 | 同仓储 `::config_revision`、`owned_courses_in_connection`、`current_lock`、`upsert_config`、`update_committed_spaces` | 同一连接、同样次序和参数；配置/课程/锁判断仍在服务 |
| 同上 `::rebuild_courses` 的索引等待 | 同仓储 `::await_vector_indexes` | `CALL db.awaitIndexes(60)` 原文与位置不变 |
| 同上 `::rebuild_courses.inventory` 的查询 | 同仓储 `::graph_inventory` | 原 inventory 包装留服务，重建前后仍按相同字段比较 |
| 同上 `::rebuild_courses` 的 SQLite 读取 | 同仓储 `::course_chunk_texts`、`committed_versions` | 原共享连接作用域、查询顺序不变 |
| 同上 `::rebuild_courses` 的向量核对查询 | 同仓储 `::vector_readiness` | 只移动查询；完整性判断仍在服务 |
| `services/task_cancel.py::cancel_task` 的事务包装 | `repositories/tasks.py::cancel_transaction` | 原 `BEGIN IMMEDIATE` / `COMMIT` / `BaseException` 条件 `ROLLBACK`；领域判断及 CAS 仍在同一连接内 |
| `services/versions/resolver.py::resolve_published` 的读取 | `repositories/versions.py::read_published_binding` | `_BY_POINTER` / `_BY_NUMBER` 常量原样搬移；课程/状态/版本一致性校验留服务 |
| 同上 `::_revision_ids` 的读取 | 同仓储 `::read_snapshot_digest` | 连接作用域不变；摘要、快照、课程校验及缓存留服务 |
| `api/chat.py::chat_service` 的依赖构建 | `services/qa/factory.py::build_chat_service` | 顺序仍是 embedding → Neo4jRepository → 模型/SqliteCallStore/policy → ChatService；应用缓存留依赖入口 |
| 同上 `::user_chat_service` 的课程配置与个人模型绑定 | 同模块 `::with_course_embedding`、`with_user_models` | 浅拷贝、课程空间绑定、个人模型错误映射不变；UserChatModels 的应用状态缓存仍在 API 依赖入口 |
| 同上 `::_record_outcome` | `services/qa/audit.py::record_outcome` | 函数体原样移动；API 保留 `_record_outcome` 导入别名，所有记账调用点不变 |

另外，`materialize.py` 的 `_DELETE`、`_CHAPTERS`、`_NODES`、`_EVIDENCE`、`_READ_CHAPTERS`、`_READ_NODES`、`_READ_EDGES`、`_COPY_CHAPTERS`、`_COPY_NODES`、`_COPY_EVIDENCE` 与 `chunk_vectors.py::_INDEX_STATE` 原样移至各自新仓储。

## 查询原文、顺序与事务证据

- 基线按 `git show ad63341:<path>` 读取。以 AST 字符串值和 f-string AST 比较查询多重集合，包含空白、换行、插值表达式及重复次数：相关服务/仓储 **85 → 85，删除 0、新增 0**。
- 实际搬移 **35 个定义**：版本物化 12、文本块向量 3、向量配置 14（11 SQL/事务语句 + 3 Cypher）、任务取消 3、版本解析 3。任务描述称物化文件有“17 处”；本次按完整查询定义实测为 12 个，此处不把出现位置数与定义数混用。
- 已执行 `git diff --color-moved`。由于新仓储尚未加入索引，额外把基线与当前相关文件复制到临时目录，运行 `git diff --no-index --color=always --color-moved=plain <before> <after>`，把未跟踪新文件也纳入对照；查询块呈移动，未发现查询文本编辑。命令的差异退出码 1 是预期结果，不作为测试失败。
- 本机证据：`.e2e/opt05-verification/check_queries.py`、`color-moved.diff`、`queries.json`；脚本只读取指定文件，不修改产品/契约。
- `/private/tmp/opt05-version-trace.py` 对基线与当前实现跑 **17 个相同场景**，结果、异常、完整查询、GraphScope、参数、SQLite/向量调用和 begin/commit/rollback 轨迹均一致。覆盖 P8 各类短写、回滚源缺失、P9、补偿、草稿/缺向量拒绝、文本块无操作/分批/短写/缺失/索引未上线。
- 独立只读复核覆盖本轮 14 个代码/测试文件，未发现有证据的行为回归；额外以记录型仓储对照物化/复制 **36 个场景**（含空集合、正常返回、写入计数异常），查询/参数/顺序/事务结局/返回值/异常消息一致。真实图库以 integration 为准。
- `services/versions/publish.py`、`rollback.py`、`snapshot.py` 和环检测实现无修改。发布仍在 P6/P7 构建/校验快照后进入 P8；文本块补齐仍先于版本副本事务；P9 核对、P10 状态推进与 P11 SQLite 提交位置不变。回滚继续复制已验证源快照，不调用向量模型。
- `course_id` 及版本参数原样保留，包括版本解析原有的先读取再校验课程行为；不借本任务改写查询或隔离策略。

## 分层护栏

新增 `tests/tooling/test_backend_layering.py`：AST 扫描 services 的 Cypher `MATCH (` / `MERGE (` 与 `.execute()`，忽略注释/文档串；识别 API 中直接导入、模块别名与 `from_settings` 的仓储类构造，允许类型引用与异常。仓储 dataclass 构造也受限制。

精确白名单只含 4 个 API 文件的 7 个旧调用：`graph.graph_reader`（2）、`graph_nodes.node_store`（2）、`relations.relation_store`（2）、`versions.publish_context`（1）。按文件、函数、完整表达式和次数匹配；新增违规或已消失例外均失败。目标服务与 chat 无白名单。合成样例与基线回放验证均可检出违规。

此护栏不是类型检查器，尚不跟踪动态 `getattr`、再导出或运行时类型；今后真实非数据库 `.execute()` 需要精确且带原因的例外。

## 实际验证

| 验证 | 结果 |
| --- | --- |
| QA 定向：`PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_j07.py tests/backend/test_j10.py tests/backend/test_l08.py tests/backend/test_d2.py tests/backend/test_d3.py tests/backend/test_teacher_embeddings.py tests/backend/test_chat_question_limit.py -q -p no:cacheprovider` | 72 passed；1 条已有 Starlette/httpx 弃用警告 |
| SQL 定向：`PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_teacher_embeddings.py tests/backend/test_c10.py tests/backend/test_g07.py tests/backend/test_td02.py tests/backend/test_c11.py tests/backend/test_g02.py -q` | 166 passed；1 条已有弃用警告 |
| 版本定向：`PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_g01.py tests/backend/test_g02.py tests/backend/test_g06.py tests/backend/test_g07.py tests/backend/test_g08_index.py -q -p no:cacheprovider` | 126 passed；1 条已有弃用警告 |
| `.venv/bin/python -m pytest tests/tooling/test_backend_layering.py -q -p no:cacheprovider` | 10 passed |
| `PYTHONPATH=src/backend .venv/bin/python /private/tmp/opt05-version-trace.py` | 17 个基线/重构场景完全一致 |
| `python3 .e2e/opt05-verification/check_queries.py` | 85/85 定义一致 |
| `git diff --check`；`git diff --exit-code -- src/contracts` | 通过；契约无差异 |
| 11 月 5 日 `./scripts/verify.sh integration` | **exit 1**：契约/启动器通过；后端 **4264 passed / 27 registered skipped**；前端 **82 文件 / 1375 passed**、type-check/build 通过；集成 **461 passed / 2 failed / 4 registered skipped**；图库专项 **44 passed**；E2E 因根目录缺 `@playwright/test` 未启动 |
| `bash .e2e/opt05-verification/targeted.sh`（真实 Neo4j，G03/G04/G06/G08 + demo） | **56 passed / 1 failed**；剩余失败仍是 demo 首次入库返回 released，版本物化/发布/回滚/向量用例通过 |
| 11 月 9 日 demo + K10 原失败定向补跑 | **4 passed**，`demo-current.log` / `.exit`；加了只记录异常的临时诊断插件，无产品/测试源码修改 |
| 11 月 9 日 `PATH="$PWD/.venv/bin:$PATH" VERIFY_NEO4J_PORT=17695 scripts/verify/integration.sh --no-e2e` | **exit 0**：集成 **463 passed / 4 registered skipped（1075.12 秒）**，图库专项 **44 passed（32.41 秒）**；`PASS integration gate` + `PASS backend-live gate`；持久日志 `integration-recheck.log`，退出码 `integration-recheck.exit` |
| 11 月 9 日 `ad63341` 基线 demo 首次入库对照（含 prompts） | **1 failed**；复现相同的 persisting/released 断言，诊断捕获 `RepositoryTransportTimeout / NEO4J_TRANSPORT_TIMEOUT`；`demo-baseline-complete.log` / `.exit` |
| 11 月 9 日 `scripts/e2e.sh tests/e2e/teacher.spec.ts tests/e2e/student.spec.ts` | **2 passed / exit 0**；`e2e-demo.log` / `.exit` |
| 11 月 9 日原版 `E2E_LLM_MODE=personal scripts/e2e.sh tests/e2e/personal.spec.ts` | **1 failed / 1 interrupted / 2 did not run / exit 130**；首例等待隐藏开关 8 分钟超时，第二例到同一步后主动停止；`e2e-personal.log` / `.exit`，浏览器证据 `.e2e/20261109-022858/playwright/` |
| 11 月 9 日个人模式临时 UI 适配副本 | **4 passed / exit 0（3.0 分钟）**：PDF+MD 发布与问答、取消/重传、无效密钥、两课权限/图谱/进度/问答出处隔离；`e2e-personal-ui.log` / `.exit`，运行目录 `.e2e/20261109-023853/`；原版门禁仍有上一行的失败 |

集成门禁采用一次性 Neo4j，独立端口避免并行任务冲突；完整命令：

```sh
PATH="$PWD/.venv/bin:$PATH" \
VERIFY_NEO4J_PORT=17695 E2E_NEO4J_PORT=17696 \
E2E_API_PORT=18005 E2E_WEB_PORT=15178 E2E_PROVIDER_PORT=18905 \
PLAYWRIGHT_CHROMIUM_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
./scripts/verify.sh integration
```

第一轮日志：`/private/tmp/smartsketch-opt05-review/integration.log`。该轮契约通过后因沙箱禁止访问 Go 构建缓存而失败，随后主动中止（exit 130；后端零测试和前端中止不构成代码失败证据）。随后在沙箱外重跑，最后观察到后端约 94% 且无失败输出；但机器重启后进程与 `/private/tmp` 日志丢失，不能据此声称全量通过。用户继续后重新启动 Docker，以现有 Python 3.11 `.venv` 为 PATH 首选重跑完整门禁；持久日志：`.e2e/opt05-verification/integration.log`，退出码：`integration.exit`；完整结果如上，不能把首轮 exit 1 写成通过。历史 17 场景的临时脚本也已随重启消失，其通过结果为本会话此前实际观察；查询/移动差异证据已重新生成在上述忽略目录中。

## 首轮失败归因与补测边界

1. `test_k10::test_a_publish_during_the_backup_is_rejected_by_the_fence`：当时的 OPT-02 差异使 `test_k10` 导入 `bolt_fault_proxy`，后者导入 `tests.waiting`；备份 hook 子进程只有 backend/integration 的模块路径，实际复现 `ModuleNotFoundError: No module named 'tests'`，尚未进入 publish 即退出，因此缺少 outcome 文件。11 月 9 日这些测试差异已不在工作区，原用例补跑通过。本任务不编辑 OPT-02 文件。
2. `test_demo_mode_live::test_upload_to_awaiting_review_with_non_empty_draft_graph`：全量与首次定向均曾在 persisting 返回 `released`。当前补跑 3 个 demo 用例及最终集成全量均通过；worker、底层 Neo4j 事务实现、该测试均与 `ad63341` 无差异，且首次断言前不调用版本物化/文本块索引。11 月 9 日补齐 prompts 的 `ad63341` 副本复现相同断言，临时诊断插件捕获 `RepositoryTransportTimeout / NEO4J_TRANSPORT_TIMEOUT`（Neo4j 阶段约 8972 ms）。这证明该失败现象在未重构基线上也会出现；原全量日志没有保留异常类型，不能断言历史每次失败均由同一异常触发。基线副本第一轮漏带 prompts 而产生的 `PromptNotFoundError` 不计入产品回归证据。
3. E2E 缺依赖：已运行根目录 `npm ci`，按既有 lock 安装 3 个包，未改变 package.json/package-lock.json；随后独立端口、一次性 Neo4j、本机 Chrome + demo/假供应商补跑。
4. 个人模式原版 E2E：`tests/e2e/personal.spec.ts:27` 在没有展开 `details.mc-advanced` 时调用 `mc-disable-thinking.setChecked(true)`，Playwright 明确报告 `element is not visible`；测试与 `ModelSettingsView.vue` 均与 `ad63341` 相同。本任务不改前端或原用例。为继续验证后续后端链路，在忽略目录 `personal-ui/` 复制该用例及依赖，仅增加点击高级选项的步骤，所有原断言保留；临时 Playwright 配置仅换测试目录并将单次操作超时设为 20 秒，避免重复等待 8 分钟。副本补测结果单列，不能替代原版门禁结果。

个人模式副本与支持文件位于 `.e2e/opt05-verification/personal-ui/`，唯一区别记录于 `personal-ui.patch`。复跑沿用上面的 Python/端口/Chrome 环境，执行：

```sh
E2E_LLM_MODE=personal scripts/e2e.sh \
  --config=.e2e/opt05-verification/personal-playwright.config.ts personal.spec.ts
```

## API / 数据 / 配置与后续

无 API、契约、迁移、依赖或环境变量变更；只新增内部仓储/服务边界，并同步 `docs/architecture.md`。无破坏性数据变更或数据回滚步骤。

下一位 Agent：先读取本交接的实际门禁结果并核对工作区改动归属；若要让原版全套门禁通过，需另行维护个人模式 E2E 的高级选项操作。基线 demo 入库的传输超时现象作为既有稳定性风险保留，本次不调大超时或修改重试行为。用户明确指示后才考虑提交/推送/PR。本任务不扩展白名单内其余 API 入口，也不调整发布事务或查询策略。
