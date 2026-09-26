# Claude 交接：F04 草稿节点与来源批写

- review_status: ready_for_review
- task_id: F04
- 分支：`claude/project-thread-sqwla4`（与 E12 同一 PR #256）；base：`main@6742f6a`
- 状态：DONE（待 PR 审查/合并）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/repositories/graph_nodes.py` | `write_draft_nodes`、`derive_kp_id`、`DraftNode`、`NodeSource`、`NodeWriteResult`、`RejectReason` |
| `tests/integration/test_f04.py` | 14 个无服务器用例 + 7 个真实 Neo4j 用例（环境变量门控） |
| `docs/decisions.md` ADR-024、`docs/architecture.md` 一句 | 来源关联 `EVIDENCED_BY` 的形状、加锁节点完全不动 |

## 行为要点

1. 写库前逐条校验，不合格只拒绝该节点：字段非法、无来源、kp_id 重复、来源块不属于本课程（调用方传入按课程读出的 SQLite 块）、资料/修订/证据区间与块不符。
2. 每批一个托管事务（默认 200 个节点）：`MERGE` 草稿节点；新建时 `source=ai`、`locked=false`、`contrib_manual=false`、`revision=1`、`level=0`；`contrib_tasks` 不重复并入本任务；内容变化才递增 `revision`。
3. 来源：`MERGE (:Chunk {course_id, chunk_id})`（只在新建时写资料与修订），`MERGE (kp)-[:EVIDENCED_BY {task_id, chunk_id, evidence_start, evidence_end}]->(chunk)`。
4. 加锁节点：内容、贡献、来源都不动，只进 `skipped_locked`（ArvinHan 在会话卡片上选定）。
5. 某批写库失败：该批节点记 `write_failed`，其余批次继续；错误已由 F02 脱敏。
6. `created`：写入前对教师不可见（不存在，或贡献任务都不在 V 中且非人工）的节点；其余写入的是对可见节点的更新。

## 命令与实际结果

真实 Neo4j：本环境没有 Docker 守护进程，也连不上 `dist.neo4j.org`，改用 Maven Central 的 `org.neo4j.test:neo4j-harness:5.26.0` 在进程内启动 Neo4j（Bolt `127.0.0.1:7687`，无鉴权）。做法：scratchpad 下一个只依赖该 harness 的 Maven 工程，`mvn -q compile dependency:copy-dependencies`，`java -cp "target/classes:target/lib/*" <Main>`，Main 用 `Neo4jBuilders.newInProcessBuilder().withConfig(BoltConnector.enabled, true)` 并固定监听地址。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 真库可用性 | `SMARTSKETCH_F03_URI=bolt://127.0.0.1:7687 … pytest tests/integration/test_f03.py` | 15 passed（含 F03 的真实用例） |
| 红灯 | `SMARTSKETCH_TEST_NEO4J_URI=bolt://127.0.0.1:7687 SMARTSKETCH_TEST_NEO4J_USER=neo4j SMARTSKETCH_TEST_NEO4J_PASSWORD=x $S/pt.sh tests/integration/test_f04.py -q`（实现前） | 收集错误（模块不存在） |
| 绿灯 | 同上 | 21 passed |
| 无真库 | 不设上述变量跑 `tests/integration` | 37 passed、11 skipped |
| 后端全量 / verify | 见 PR 与 `claude-e12.md` 的同一轮命令 | 通过 |

### 反向篡改（连真库跑 `test_f04.py`，改回 `cmp` 一致）

| # | 篡改 | 结果 |
| --- | --- | --- |
| T1 | 去掉加锁过滤 | 1 failed |
| T2 | `contrib_tasks` 无条件追加 | 1 failed |
| T3 | 不校验来源块的课程 | 1 failed |
| T4 | 每次写都递增 `revision` | 1 failed |
| T5 | 批次失败直接抛出 | 2 failed |
| T6 | 来源关联不带 `task_id` | 2 failed |
| T7 | 不校验证据区间 | 3 failed |

CI 只跑 `tests/backend`，本文件的真实用例与 F03 一样不在 CI 中运行。

## 数据与接口变更

- Neo4j：新增关系类型 `EVIDENCED_BY` 与 `Chunk` 节点的写入（F03 已有约束与索引）；无新 DDL。
- 无 SQLite 迁移、REST/SSE 契约或依赖变更。测试专用环境变量 `SMARTSKETCH_TEST_NEO4J_URI/USER/PASSWORD` 只在本地测试使用，不进 `.env.example`。

## 待决 / 风险

1. **节点状态与置信度阈值**：`draft`/`low_confidence` 与 `confidence` 由调用方给（D-08 未签收，E05 待决 5）。
2. **§8.4 单事务**：「撤销本任务旧贡献 + 写入」须在一个 Neo4j 事务内，F02 `Neo4jRepository` 目前一条查询一个事务；F13 组合时需要多语句事务接口，或把撤销并入同一条查询。
3. **融合映射**：`merging` 阶段尚无任务承接。F13 之前需要把 E12 的 `tent_…` 映射为 `kp_id`（新节点用 `derive_kp_id(course, task, tent_id)`，融合命中已有节点则用其 ID）。
4. **加锁节点的新证据被丢弃**：按决定不挂来源；如以后要保留，需另加「待教师确认的来源」形态。
5. **`chapter_id`、`importance`、`difficulty`** 未写，由章节/评分相关任务补。

## 下一步

- F06：同样用 `(course_id, "draft")` 作用域写关系，先 `MERGE RelationIdentity` 守卫（F03 交接）。
- F13：读 `load_candidates` → 映射 kp_id → `write_draft_nodes` → F06 → T6。

## 回滚

撤销本提交；已写入的草稿节点与来源可按 `contrib_tasks`、`EVIDENCED_BY.task_id` 定向清理（草稿对读者的可见性由 V 保证，未提交 T6 的任务内容本就不可见）。
