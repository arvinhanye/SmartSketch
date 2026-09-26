# Claude 交接：G05 发布失败补偿与清扫

- review_status: ready_for_review
- task_id: G05
- 分支：`claude/project-thread-sqwla4`；base：`main@95d5c9a`
- 状态：DONE（待 PR 审查/合并）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/versions/reconcile.py` | `compensate`（C1，发布与回滚共用）、`sweep_course`（V9 第 1～5 步）、`sweep`（逐课程、单课失败不影响其他）、`SweepReport`、`LEASE_EXPIRED` |
| `src/backend/app/services/versions/publish.py`（扩围） | `_compensate` 改为调用 `reconcile.compensate`，自身失败只记日志 |
| `src/backend/app/repositories/versions.py`（扩围） | `list_expired_attempts`、`list_course_ids` |
| `src/backend/app/repositories/graph_read.py`（扩围） | `stored_version_ids`：本课程 Neo4j 中的全部非草稿版本 |
| `tests/integration/test_g05.py` | 14 个用例，连真实 Neo4j 与迁移后的 SQLite（夹具取自 `test_g04.py`） |
| `tests/backend/test_g05_sqlite.py` | 2 个用例（CI 覆盖） |
| `tests/integration/test_g04.py`（扩围） | Neo4j 删除失败用例的打桩目标改为 `reconcile.drop_version` |
| `src/backend/app/services/versions/snapshot.py`（扩围） | 悬空章节引用按未归章 / 顶层章节发布（审查修复） |
| `src/backend/app/services/versions/materialize.py`（扩围） | 副本删除按标签匹配（审查修复） |
| `tests/backend/test_g01.py`（扩围） | 1 个用例：悬空章节引用 |
| ADR-036、`docs/tasks.md` | 决定与看板 |

## 用法（给 worker 周期回收 / G06）

```python
reports = sweep(sqlite_url, repo)          # 周期调用；每个 SweepReport 列出 expired/dropped/pending/orphans/missing_copies
compensate(sqlite_url, repo, cid, vid, reason, touched_graph=True)   # G06 回滚失败时的 C1
```

## 验收对照

| 条目 | 用例 |
| --- | --- |
| PUB-18 P7 | `test_p7_snapshot_write_failure_keeps_the_old_pointer[raise/refused]` |
| PUB-18 P8～P11 | G04 的 `test_failures_keep_the_old_pointer_and_leave_no_copy` |
| PUB-18 Neo4j 删除失败 | `test_neo4j_cleanup_failure_is_finished_by_the_sweeper`（含幂等） |
| PUB-18 SQLite 写失败 | `test_sqlite_failure_during_c1_is_finished_after_the_lease_expires` |
| PUB-19 | `test_crash_between_p8_and_p11_is_swept_and_publishing_resumes[materialize/verify/mark_materialized]` |
| PUB-20 | `test_sweeper_wins_once_the_lease_expired`、`test_commit_wins_while_the_lease_holds_and_the_copy_survives` |
| 不清仍被读的版本 | `test_sweeper_only_removes_failed_copies` |
| V9 第 4、5 步 | `test_orphans_and_missing_copies_are_only_reported` |
| 按课程隔离 | `test_sweep_isolates_courses` |
| 审查：崩溃后课程不再永久 409 | `test_publish_reclaims_an_expired_attempt_without_waiting_for_the_sweeper` |
| 审查：清扫后写入的孤儿副本 | `test_copy_written_after_the_sweeper_failed_the_attempt_is_dropped` |

## 命令与实际结果

`S=<scratchpad>`，`$S/pt.sh` 同 `claude-e12.md`；真实 Neo4j 用 `claude-f04.md` 记录的 Maven harness（`SMARTSKETCH_TEST_NEO4J_URI=bolt://127.0.0.1:7687`、`USER=neo4j`、`PASSWORD=x`）。

| 命令 | 结果 |
| --- | --- |
| `$S/pt.sh tests/integration/test_g05.py tests/integration/test_g04.py -q`（带 Neo4j 环境变量） | 33 passed |
| `$S/pt.sh tests/backend/test_g05_sqlite.py -q` | 2 passed |
| `$S/pt.sh tests/backend -q` | 2965 passed |
| `$S/pt.sh tests/integration -q`（带 Neo4j 环境变量） | 148 passed、4 skipped |
| `PATH=$S/venv/bin:$S/tools/node_modules/.bin:$PATH ./scripts/verify.sh` | exit 0 |
| `git diff --check` | exit 0 |

反向篡改（改 `reconcile.py` 后跑 `test_g05.py`，每次恢复）：C1 忽略 0 行结果（1 failed）；清扫处理租约内尝试（2 failed）；清扫删除已提交版本（8 failed）；`cleanup_pending` 不清除（1 failed）；孤儿副本被删除（1 failed）；跳过 V9 第 3 步（1 failed）；单课失败中断全部清扫（1 failed）；发布前不回收过期尝试（1 failed）；C1 遇已失败行不删副本（1 failed）。

## 接口 / 数据变更

- 无迁移、无契约改动。新增仓储函数见上表。

## 风险

- 清扫第 1 步不知道过期尝试是否写过 Neo4j，一律尝试删除（可重复执行，只删该 `version_id`）。
- `stored_version_ids` 每次清扫对每门课扫描一次该课程的知识点与章节；课程很多时的周期与开销需在接入调度时评估。

## 下一步 / 待决

- 同一独立审查的其余项未在本 PR 处理：无来源人工节点详情 500（F08/F07 口径）；worker 清理重试空等课程锁；任务重跑覆盖教师已审核状态。
- 把 `sweep` 接入 worker 周期回收（A06 §8.6）；目前仓库里没有周期回收的调度实现。
- 孤儿副本与缺副本只告警，人工处理与副本重建归 K10。
- G06 回滚失败时调用 `reconcile.compensate`。
