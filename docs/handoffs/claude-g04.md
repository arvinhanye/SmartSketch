# Claude 交接：G04 原子发布指针切换

- review_status: ready_for_review
- task_id: G04
- 分支：`claude/project-thread-sqwla4`；base：`main@ebb0f42`
- 状态：DONE（待 PR 审查/合并）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/versions/publish.py` | `publish(ctx, course_id, created_by=)`：V5 P2～P12 与 C1；`load_draft`（P4 可见草稿 → G01 `DraftGraph`）；异常 `CourseBusy`、`PublishFailed`，并转出 `PublishInProgress`、`SnapshotBlocked` |
| `src/backend/app/repositories/versions.py`（扩围） | `DraftState`、`read_draft_state`（P4 SQLite 部分：修订号、指针、水位、V、V 的资料修订）、`complete_published_tasks`（T7，须在调用方事务内） |
| `src/backend/app/repositories/course_locks.py`（扩围） | `current_holder`：`COURSE_BUSY` 的 `details.holder` |
| `src/backend/app/repositories/graph_read.py`（扩围） | 节点投影加 `.merged_from`（发布集合谱系；F07 组装 DTO 时不使用） |
| `tests/integration/test_g04.py` | 19 个用例，连真实 Neo4j 与迁移后的 SQLite |
| `tests/backend/test_g04_sqlite.py` | 3 个用例：P4 读取、T7 水位、锁持有方（CI 覆盖） |
| ADR-034、`docs/tasks.md` | 决定与看板 |

## 用法（给路由 / G05 / G06）

```python
ctx = PublishContext(sqlite_url, Neo4jRepository(driver), embedding_adapter, sqlite_current_space(sqlite_url),
                     lease_seconds=settings.PUBLISH_LEASE_SECONDS,
                     lock_wait_seconds=settings.COURSE_LOCK_WAIT_SECONDS)
outcome = publish(ctx, course_id, created_by=user.id)   # P1 鉴权由调用方完成
# PublishInProgress / CourseBusy(.details()) / SnapshotBlocked(.details()) → 409；PublishFailed → 5xx
# PublishResult = {version, published_at, unchanged, excluded, stats: {node_count, edge_count}}
```

## 验收对照

| 条目 | 用例 |
| --- | --- |
| PUB-1、PUB-4 | `test_first_publish_switches_the_pointer_and_completes_tasks` |
| PUB-4、PUB-22 后半 | `test_edits_after_the_lock_is_released_miss_this_snapshot`（P8 时锁已空闲，新 T6 任务不被 T7） |
| PUB-2 | `test_republish_after_an_edit_creates_version_two_and_keeps_version_one` |
| PUB-5、PUB-6 | `test_unchanged_content_takes_the_idempotent_path[approve/touch]` |
| PUB-23 | `test_cycle_blocks_before_the_pointer_moves`（环路首尾同 ID） |
| PUB-24（经 G04） | `test_empty_graph_and_foreign_sources_are_blocked` |
| PUB-35 | `test_invisible_contributions_stay_out_of_the_snapshot` |
| PUB-12、PUB-18（G04 部分） | `test_failures_keep_the_old_pointer_and_leave_no_copy[P8/P9/P10/P11]`、`test_commit_refuses_a_moved_pointer` |
| C1 | `test_error_after_the_commit_point_never_drops_the_committed_copy`、`test_undeletable_copy_is_marked_for_the_sweeper` |
| V5 P7 / V12 | `test_digest_equal_but_space_changed_is_an_invariant_breach` |
| PUB-21 | `test_concurrent_publishes_conflict`（发布与发布、发布与回滚） |
| PUB-22 前半（发布侧） | `test_course_busy_names_the_holder_and_keeps_nothing` |

## 命令与实际结果

`S=<scratchpad>`，`$S/pt.sh` 同 `claude-e12.md`；真实 Neo4j 用 `claude-f04.md` 记录的 Maven harness（`SMARTSKETCH_TEST_NEO4J_URI=bolt://127.0.0.1:7687`、`USER=neo4j`、`PASSWORD=x`）。

| 命令 | 结果 |
| --- | --- |
| `$S/pt.sh tests/integration/test_g04.py -q`（带 Neo4j 环境变量） | 19 passed |
| `$S/pt.sh tests/backend/test_g04_sqlite.py -q` | 3 passed |
| `$S/pt.sh tests/backend -q` | 2962 passed |
| `$S/pt.sh tests/integration -q`（带 Neo4j 环境变量） | 134 passed、4 skipped |
| `PATH=$S/venv/bin:$S/tools/node_modules/.bin:$PATH ./scripts/verify.sh` | exit 0 |
| `git diff --check` | exit 0 |

反向篡改（改 `publish.py` 后跑 `test_g04.py`，每次恢复）：去掉提交事务中的 T7（6 failed）；去掉 P7 空间核对（1 failed）；C1 从不删副本（6 failed）；C1 不看条件更新结果、提交后仍删副本（首轮 18 passed 漏检，补 `test_error_after_the_commit_point_never_drops_the_committed_copy` 后 1 failed）；V 换成全部任务（1 failed）；写锁从不释放（13 failed）；取锁失败不拒绝（1 failed）。

## 接口 / 数据变更

- 无迁移、无契约改动。新增仓储函数见上表；F07 节点投影多返回 `merged_from`（DTO 不变）。

## 风险

- 知识点向量在锁外计算（ADR-034 第 3 条），与 V5 P4 字面不同；向量只依赖快照内容，结果一致。
- 心跳线程每 `PUBLISH_LEASE_SECONDS / 3` 续约；进程在 P8～P11 间被杀时尝试行留到租约过期，由 G05 清扫执行 C1。

## 下一步 / 待决

- `POST /api/v1/courses/{cid}/publish` 路由未分配任务：建议并入 G06 的 `api/versions.py`，按 A05 做教师鉴权并映射上述异常。
- G05：清扫过期尝试与 `cleanup_pending`；可直接复用 `publish._compensate` 的顺序。
- G04 对 F12 的依赖只因谱系（F10 维护 `merged_from`、F12 记直接父子），发布不写审计日志（ADR-034 第 7 条）。
