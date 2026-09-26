# Claude 交接：F13 直通 merging 与 persisting 阶段

- review_status: ready_for_review
- task_id: F13
- 分支：`claude/project-thread-sqwla4`（与 E12、F04、F06 同一 PR #256）；base：`main@6742f6a`
- 状态：DONE（待 PR 审查/合并）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/workers/persist_graph.py` | `run_merge_stage`（直通 T5/T8）、`run_persist_stage`、`build_plan`（候选 → 草稿节点/关系）、`cleanup_failed_task`、`run_pipeline_once`（解析 → 抽取 → 融合 → 持久化一次跑完） |
| `src/backend/migrations/009_course_locks.sql` | `course_locks` 表、`processing_tasks.t6_seq` 与部分唯一索引；文件头 `ROLLBACK` 行 |
| `src/backend/app/repositories/course_locks.py` | `try_acquire`/`acquire`（有界等待）/`renew`/`release`/`held`（持锁期间每 `L/3` 续约） |
| `src/backend/app/services/graph/downgrade.py` | ADR-009 降级算法 `plan_downgrades`，纯函数 |
| `graph_relations.py`（扩） | `read_prerequisite_edges`、`downgrade_relation`、`revoke_task`；`DraftRelation.downgrade_cycle` |
| `graph_nodes.py`、`services/graph/relations.py`（扩） | 事务内版本 `write_draft_nodes_in`、`apply_relations` |
| `task_leases.py`（扩） | 回收或释放时 `persisting` 耗尽 → 置 `cleanup_pending` |
| `tasks.py`（扩） | `read_effective_task_ids`（V） |
| `tests/integration/test_f13.py` | 17 个无服务器用例 + 10 个真实 Neo4j 用例 |
| ADR-029、`specs/task-processing.md` §8.4 一段、`docs/tasks.md` | 决定与看板 |

## 行为要点

1. `merging` 直通：只执行 C08 `stage_done`；取消标志为真 → `cancelled`（T8，清空租约），否则 → `persisting`（T5，仍持租约）。
2. 候选映射：实体 `tent_…` → `kp_id = derive_kp_id(课程, 任务, tent_id)`，定义取首个非空，置信度取最高（缺失记 0），别名为其他写法，来源按块与证据区间去重；关系端点映射后同 `rel_id` 合并来源、取最高置信度，端点缺失或自环丢弃。状态一律 `draft`。
3. `persisting`：取课程写锁 → 复核租约（丢了就不写 Neo4j）→ 读 V → 一个 Neo4j 事务（锁守卫 → 撤销本任务贡献 → 写节点 → 降级 → 写关系）→ T6（`t6_seq` = 本课程最大 + 1，`courses.draft_revision + 1`）→ 释放锁。
4. 失败：存储故障/等锁超时 → 释放退避（耗尽 T9 `STORAGE_UNAVAILABLE`）；草稿里已有全由已确认边组成的环 → T9 `CYCLE_DETECTED`，`details.cycle`；其他 → T9 `INTERNAL_ERROR`。任何 `persisting` 失败都置 `cleanup_pending`，随即尝试清理；`run_pipeline_once` 在每次领取前重试遗留的清理。

## 命令与实际结果

`S=<scratchpad>`，`$S/pt.sh` 同 `claude-e12.md`；真实 Neo4j 用 `claude-f04.md` 记录的 Maven harness。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 绿灯 | `SMARTSKETCH_TEST_NEO4J_URI=bolt://127.0.0.1:7687 SMARTSKETCH_TEST_NEO4J_USER=neo4j SMARTSKETCH_TEST_NEO4J_PASSWORD=x $S/pt.sh tests/integration/test_f13.py -q` | 27 passed；连跑 5 次均通过 |
| 集成（真库 / 无真库） | `$S/pt.sh tests/integration -q` | 99 passed、3 skipped / 69 passed、33 skipped（加续约用例前） |
| 后端全量 | `$S/pt.sh tests/backend -q` | 2801 passed，1 个既有 warning |
| verify | `PATH=$S/venv/bin:$S/tools/node_modules/.bin:$PATH ./scripts/verify.sh`；`git diff --check` | exit 0；通过 |

测试与实现同轮写成，未单独留红灯记录；以下反向篡改代替红灯证明用例有效。

| # | 篡改 | 结果 |
| --- | --- | --- |
| T1 | 不撤销本任务旧贡献 | 1 failed（LEASE-21） |
| T2 | T6 序号恒为 1 | 1 failed |
| T3 | 不做降级 | 2 failed |
| T4 | 释放耗尽时不置 `cleanup_pending` | 2 failed |
| T5 | 写 Neo4j 前不复核租约 | 1 failed |
| T6 | 不取课程写锁 | 1 failed |
| T7 | 撤销时删除仍有他人贡献的关系 | 1 failed（LEASE-18） |
| T8 | `merging` 忽略取消标志 | 1 failed |
| T9 | 课程写锁不续约 | 1 failed |

CI 只跑 `tests/backend`，本文件（含无服务器用例）与 F03/F04/F06 一样不在 CI 中运行。

## 数据与接口变更

- SQLite 迁移 009（新表 + 新列 + 索引，回滚见文件头）。Neo4j 无新 DDL；关系新增可选属性 `downgraded_from_type`、`downgrade_cycle`（契约 `RelationDowngraded` 已有）。
- 无 REST/SSE 契约、环境变量或依赖变更。

## 待决 / 风险

1. **融合没有任务承接**：E08～E10 已完成，但没有任务把它们接进 `merging`；这需要 D-08 阈值与向量（E07）。在接入之前，不同资料里的同名知识点会各自成节点。
2. **D-08**：签收后需按阈值重算 `draft`/`low_confidence`（置信度原值已保存）。
3. **等锁超时消耗尝试次数**：发布长时间持锁时，任务可能因多次等锁超时而耗尽尝试；发布只在建快照期间持锁（V4），风险低。
4. **快照与 SSE**：C11 的 `chunks_done`/`failed_chunks` 仍未接（E12 待决 1）。
5. **生产装配**：`run_pipeline_once` 需要调用方传 `ExtractionToolkit` 与 `Neo4jRepository`，尚无常驻 worker 进程入口。
6. **`draft_revision`**：T6 时递增（任务内容此刻变为可见，课程状态由 `published` 变 `revising`）；规格 V4 只写了教师编辑递增，这是 Claude 的补充，见 ADR-029。教师编辑的递增仍归 F08。

## 回滚

停 API 与 worker；按迁移 009 文件头的 `ROLLBACK` 行回滚（测试已验证），或恢复 `backups/*-before-009.sqlite`；撤销本提交。已写入的草稿内容可按 `contrib_tasks` 定向清理。
