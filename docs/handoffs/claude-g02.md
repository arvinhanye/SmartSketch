# Claude 交接：G02 版本元数据与发布操作记录

- review_status: ready_for_review
- task_id: G02
- 分支：`claude/project-thread-sqwla4`（与 G01 同一 PR #259）；base：`main@608be90`
- 状态：DONE（待 PR 审查/合并）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/migrations/010_versions.sql` | `graph_versions`（V2 全部字段、状态一致性约束、`(course_id, version)`/`commit_seq`/「每课程一个进行中尝试」部分唯一索引、已提交行防删防改触发器）、`commit_sequence` 单行表；文件头 `ROLLBACK` 行 |
| `src/backend/app/repositories/versions.py` | `begin_attempt`（回滚时复制源版本快照）、`heartbeat`、`record_snapshot`（校验摘要）、`mark_materialized`、`commit_attempt`/`discard_attempt`（在调用方事务内）、`next_commit_seq`、`fail_attempt`、`set_cleanup_pending`、`immediate`，以及读取 `get_version`/`get_committed`/`current_version`/`list_versions`/`list_attempts`/`read_snapshot` |
| `tests/backend/test_g02.py` | 22 个用例（真实迁移后的 SQLite） |
| `tests/integration/test_f13.py`（扩围） | 009 回滚用例改为先按编号倒序回滚更新的迁移 |
| ADR-032、`docs/tasks.md` | 决定与看板 |

## 给 G04/G06 的用法

```python
attempt = versions.begin_attempt(url, cid, kind="publish", created_by=uid, lease_seconds=settings.PUBLISH_LEASE_SECONDS)
# PublishInProgress → 409 PUBLISH_IN_PROGRESS
versions.record_snapshot(url, attempt.version_id, snapshot=build.snapshot.canonical, digest=build.snapshot.digest, ...)
versions.mark_materialized(url, attempt.version_id)
with versions.immediate(url) as db:          # P11
    versions.commit_attempt(db, attempt.version_id, expected_pointer=old, published_from_revision=r)
    ...  # T7 in the same transaction
# CommitRejected → C1：versions.fail_attempt(...)，再清理 Neo4j，失败则 set_cleanup_pending
```

## 命令与实际结果

`S=<scratchpad>`，`$S/pt.sh` 同 `claude-e12.md`。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 本任务 | `$S/pt.sh tests/backend/test_g02.py -q` | 22 passed |
| 后端全量 | `$S/pt.sh tests/backend -q` | 2892 passed，1 个既有 warning |
| 集成（真实 Neo4j） | `SMARTSKETCH_TEST_NEO4J_URI=bolt://127.0.0.1:7687 SMARTSKETCH_TEST_NEO4J_USER=neo4j SMARTSKETCH_TEST_NEO4J_PASSWORD=x $S/pt.sh tests/integration -q` | 修改前 1 failed（`test_migration_009_rolls_back`：迁移器拒绝在 010 已应用时重放 009）；修改后 103 passed、4 skipped |
| verify | `PATH=$S/venv/bin:$S/tools/node_modules/.bin:$PATH ./scripts/verify.sh`；`git diff --check` | exit 0；通过 |

反向篡改（每项都有用例失败）：去掉进行中尝试的部分唯一索引、版本号跨课程取最大、提交不查 `materialized` 与租约、指针 CAS 不生效、`fail_attempt` 可改已提交行、去掉防改触发器、`record_snapshot` 不校验摘要、回滚不复制源快照、`discard_attempt` 可删失败行、提交序号不取号（共 10 项）。

## 数据与接口变更

- SQLite 迁移 010（新表 + 索引 + 触发器 + 单行表，回滚见文件头）。
- 无 REST/SSE 契约、环境变量或依赖变更（`PUBLISH_LEASE_SECONDS` 已存在）。

## 待决 / 风险

1. 清扫过期尝试（`preparing`/`materialized` 且租约过期 → `failed`，再清 Neo4j）归 G05。
2. `commit_sequence` 与 I01 进度写入共用；I01 实现时直接调 `next_commit_seq`。
3. 迁移 010 手工回滚会丢失全部版本历史与发布指针所指的行，只适用于从未发布过的库；已发布的库请恢复备份。

## 回滚

停 API 与 worker；恢复 `backups/*-before-010.sqlite`，或（从未发布时）按迁移 010 文件头的 `ROLLBACK` 行回滚；撤销本提交。
