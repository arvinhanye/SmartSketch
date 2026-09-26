# Claude 交接：F06 关系事务写入与并发防环

- review_status: ready_for_review
- task_id: F06
- 分支：`claude/project-thread-sqwla4`（与 E12、F04 同一 PR #256）；base：`main@6742f6a`
- 状态：DONE（待 PR 审查/合并）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/graph/relations.py` | `write_relations`、`RelationWriteResult`、错误类 `CycleDetectedError`/`DanglingEndpointError`/`DuplicateRelationError`/`InvalidRelationError`（`code` 为契约错误码） |
| `src/backend/app/repositories/graph_relations.py` | `derive_rel_id`、`DraftRelation`、`StoredRelation`；事务内语句 `lock_draft`、`read_visible_nodes`、`read_prerequisite_graph`、`read_relations`、`merge_relations`；`source_pair` 编码 |
| `src/backend/app/repositories/neo4j.py`（扩围） | `Neo4jRepository.write_transaction(scope, work)` 与 `ScopedTransaction.run`：一个显式写事务内多条语句，每条都做作用域参数校验 |
| `src/backend/migrations/neo4j/001_constraints.cypher`、`graph_migrations.py`（扩围） | `DraftWriteGuard(course_id, version_id)` 唯一约束与期望模式 |
| `tests/integration/test_f06.py` | 16 个无服务器用例 + 12 个真实 Neo4j 用例（环境变量门控） |
| `docs/decisions.md` ADR-025、`docs/architecture.md` 一句 | 守卫节点、关系属性、既有关系处理 |

## 行为要点

1. 一次 `write_relations` = 一个写事务：锁课程守卫节点 → 读可见节点 → 校验端点 → 读已有关系身份 → 读参与环检测的边（可见、`PREREQUISITE`、`status ≠ rejected`）→ F05 `check_candidates` → `MERGE RelationIdentity` + 关系。任何失败整体回滚。
2. 为什么需要守卫节点：只锁端点时，A→B、C→D 提交后，B→C 与 D→A 端点不相交，仍能同时通过检测（`test_live_concurrent_writers_on_disjoint_endpoints_still_serialize` 覆盖）。
3. 写入方：`task_id=None` 为教师（`source=manual`，状态可为四种之一）；否则为任务（`source=ai`，只能 `draft`/`low_confidence`，至少一个本课程来源块）。任务写入时它自己的贡献对它可见（§8.4「当前可见草稿 + 本任务候选」）。
4. 已有关系：教师遇可见同 ID → `DUPLICATE_RELATION`；遇不可见的 → 接管字段、`revision+1`、置 `contrib_manual`。任务遇端点不同 → 跳过并记 `conflicts`；遇类型不同（降级）→ 沿用现有类型并记 `kept_type`；其余只并入贡献与来源，不改字段。
5. `created`：写入前对教师不可见（按 V 与人工贡献）的关系，与 F04 同口径。

## 接口（给 F08 / F13）

```python
from app.services.graph.relations import write_relations, CycleDetectedError
result = write_relations(repo, GraphScope(cid, "draft", effective_task_ids=V),
                         relations=[DraftRelation(rel_id=derive_rel_id(cid, "PREREQUISITE", a, b), ...)],
                         task_id=None)          # 教师；任务写入传 task_id 与 chunks
# CycleDetectedError.cycle -> details.cycle；DanglingEndpointError.missing；DuplicateRelationError.existing_id
```

F13 如需在同一事务里「撤销旧贡献 + 写节点 + 降级 + 写关系」，用 `repo.write_transaction(scope, work)`，在 `work` 里先 `lock_draft(tx)`，再组合 `graph_relations` 的语句（F04 的节点写入目前是独立事务，需要改为接收 `ScopedTransaction`）。

## 命令与实际结果

`S=<scratchpad>`，`$S/pt.sh` 同 `claude-e12.md`；真实 Neo4j 用 `claude-f04.md` 记录的 Maven harness（`bolt://127.0.0.1:7687`，无鉴权）。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 绿灯 | `SMARTSKETCH_TEST_NEO4J_URI=bolt://127.0.0.1:7687 SMARTSKETCH_TEST_NEO4J_USER=neo4j SMARTSKETCH_TEST_NEO4J_PASSWORD=x $S/pt.sh tests/integration/test_f06.py -q` | 28 passed；连跑 5 次均 28 passed |
| 集成（真库） | 同上变量 + `SMARTSKETCH_F03_*`，`$S/pt.sh tests/integration -q` | 73 passed、3 skipped |
| 集成（无真库） | 不设变量 | 53 passed、23 skipped |
| 后端全量 | `$S/pt.sh tests/backend -q` | 2801 passed，1 个既有 warning |
| verify | `PATH=$S/venv/bin:$S/tools/node_modules/.bin:$PATH ./scripts/verify.sh` | exit 0 |

测试与实现同轮写成，未单独留红灯记录；以下反向篡改代替红灯证明用例有效。

### 反向篡改（连真库跑 `test_f06.py`，改回 `cmp` 一致）

| # | 篡改 | 结果 |
| --- | --- | --- |
| T1 | 不锁守卫节点 | 2 failed（两个并发用例） |
| T2 | 读图之后才锁守卫 | 2 failed |
| T3 | `rejected` 边参与环检测 | 1 failed |
| T4 | 任务自己的边不参与环检测 | 1 failed |
| T5 | 教师写入不查可见重复 | 1 failed |
| T6 | 任务候选不沿用降级后的类型 | 1 failed |
| T7 | 来源对重复并入 | 1 failed |
| T8 | 贡献任务重复并入 | 3 failed |

CI 只跑 `tests/backend`，本文件的真实用例与 F03/F04 一样不在 CI 中运行。

## 数据与接口变更

- Neo4j：新增 `DraftWriteGuard` 唯一约束与节点；关系与 `RelationIdentity` 的属性见 ADR-025。
- F02：新增 `write_transaction`；`GraphDriver` 协议加 `session(database=...)`（官方驱动已有）。
- 无 SQLite 迁移、REST/SSE 契约或依赖变更。

## 待决 / 风险

1. **课程写锁与 `draft_revision`**：V4 要求教师草稿写入「取锁 → `draft_revision+1` → Neo4j 事务 → 释放」，`course_locks` 表尚无任务建表。F06 的守卫节点只保证防环，不替代课程写锁与发布串行，F08/G 组需落地。
2. **等锁无上限**：Neo4j 默认等锁不超时；API 侧有界等待（`COURSE_LOCK_WAIT_SECONDS`）落地前，长事务会让同课程写入排队。
3. **节点写入未走守卫**：F04 的节点写入不锁守卫；目前节点只增不减、可见性只增，不影响防环。将来删除/合并节点（F10 等）须先锁守卫。
4. **人工关系的来源**：教师可附来源块（贡献方记 `null`），但契约 `RelationCreate` 暂无该字段。

## 回滚

撤销本提交；执行 `DROP CONSTRAINT draft_write_guard_scope IF EXISTS` 与 `MATCH (g:DraftWriteGuard) DELETE g`。已写入的草稿关系可按 `contrib_tasks`、`contrib_manual` 定向清理。
