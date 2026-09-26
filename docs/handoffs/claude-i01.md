# Claude 交接：I01 学习进度仓储

- review_status: superseded
- **未采用**：与 `main` 合并时，`main` 已含 Codex 的 I01（PR #272）；三份 I01 文件取 `main` 版本，本交接描述的实现（`9b9231e`，仍在分支历史中）未采用。现行实现见 `docs/handoffs/codex-i01.md`。
- task_id: I01
- 分支：`task/i01`（本地，未 push）；base：`ddae1ed`（`main@0b8aa73` + 第九批认领）
- 状态：DONE（待合入 `claude/upbeat-ramanujan-p4ccbq` 与审查）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/migrations/011_progress.sql` | `learning_progress` 表（主键 `(user_id, course_id, kp_id)`，外键 users/courses，`status` 三值，`write_seq ≥ 1`，`updated_at`），文件头 `ROLLBACK` 行 |
| `src/backend/app/repositories/progress.py` | `write_progress`、`project_progress`、`read_rows`、结果类型 `ProgressView/ProgressEntry/InheritedSource/ProgressRow/ProgressWrite`、错误 `ProgressValidationError`、`ProgressNotInPublishedVersion`、`clear_cache` |
| `tests/backend/test_i01.py` | 46 个用例，连迁移后的真实 SQLite；版本由 G01 `build_snapshot` 生成、G02 仓储提交/回滚，G07 `resolve_published` 绑定 |
| **扩围**：`docs/decisions.md` ADR-049 | 实现约定（表、一个事务一个 `write_seq`、投影位置、脏行、完整性错误、同值写入） |

## 用法（给 I02 / I05）

```python
# PUT /progress（I02）：鉴权后
result = write_progress(sqlite_url, access.user.id, course_id, [u.model_dump() for u in body])
return result.view.to_dict()                     # 契约 ProgressResponse
# ProgressValidationError → 422 VALIDATION_ERROR（通用）
# ProgressNotInPublishedVersion → 422 VALIDATION_ERROR，details = error.details()
# AccessDenied(404 NOT_FOUND / GRAPH_NOT_PUBLISHED)；VersionIntegrityError → 500 INTERNAL_ERROR

# GET /progress 与推荐（I05）：同一请求只解析一次
bound = resolve_published(sqlite_url, course_id)
view = project_progress(sqlite_url, access.user.id, bound)
eligible_set(graph, view.mastered)               # I03：M ⊆ V
```

## 验收对照

| 条目 | 用例 |
| --- | --- |
| 用户隔离 | `test_users_are_isolated` |
| 课程隔离 | `test_courses_are_isolated`、`test_a_foreign_row_with_the_same_kp_id_in_another_course_does_not_leak` |
| 重复写幂等 | `test_repeating_the_same_write_is_a_no_op`、`test_partial_repeat_writes_only_the_changed_items`、`test_writing_unknown_to_a_node_without_a_row_creates_the_row`、LP-18 重放 |
| 未知节点拒绝（整批零写入） | `test_unknown_nodes_reject_the_whole_batch_with_indices`（已删除、草稿独有、他课）、`test_write_binds_to_the_pointer_seen_inside_its_transaction`（途中新版本删除目标）、`test_malformed_or_duplicate_batches_write_nothing[8 组]`、`test_writing_to_an_unpublished_or_missing_course_is_refused` |
| 共享序列 | `test_one_write_transaction_takes_one_number_from_the_shared_sequence` |
| A08 版本迁移 | LP-8 `test_lp8_...`；LP-9/17 `test_lp9_lp17_...`、`test_lp9_primary_row_written_before_the_merge_...`、`test_lp9_chain_merge_...`、`test_lp9_rollback_...`；LP-10 `test_lp10_...`；LP-18 两条；LP-19 `test_lp19_...`；LP-20 `test_lp20_...`；连续性 `test_continuous_attribution_...`、`test_reattribution_to_another_primary_...` |
| 脏行 / 完整性（LP-11/12） | `test_dirty_rows_are_ignored_with_a_warning_and_dormant_rows_are_silent`、`test_invalid_lineage_in_the_bound_version_is_an_integrity_error[3]`、`test_an_empty_committed_version_is_an_integrity_error`、`test_bound_version_of_another_course_is_refused`、`test_a_historical_version_holding_another_courses_snapshot_...`、`test_pointer_to_a_corrupt_version_is_an_integrity_error_on_write` |
| 迁移 | `test_migration_011_creates_the_progress_table`、`test_table_constraints_reject_bad_rows`、`test_migration_011_rolls_back_and_reapplies` |

## 命令与实际结果（Linux，Python 3.11 共享 venv）

```bash
S=/tmp/claude-0/-home-user-SmartSketch/<session>/scratchpad
$S/pt.sh tests/backend/test_i01.py -q
#   实现前：收集失败（ImportError: cannot import name 'progress'）——红灯
#   实现后：46 passed
$S/pt.sh tests/backend -q                     # 3142 passed（基线 3096 + 本任务 46，既有用例无改动）
$S/pt.sh tests/integration/test_f13.py tests/integration/test_k08.py -q
#   38 passed, 10 skipped, 1 failed：test_k08::test_images_build 为 Docker Hub 429 限流（环境问题，与本任务无关）
PATH=$S/venv/bin:$S/tools-f10/bin:$S/tools-f10/node_modules/.bin:$PATH ./scripts/verify.sh   # exit 0
git diff --check                              # exit 0
```

迁移数量：没有既有测试断言完整迁移清单（`test_c01/c02/c06/c13/c16` 只断言截断到 001～004 的临时目录）；`test_g02::test_migration_010_rolls_back_and_reapplies` 会先按倒序执行更新迁移的 `ROLLBACK` 行，011 的两行已随之验证。**无扩围测试改动。**

反向篡改（`$S/mutate_i01.py`，逐个改实现后跑 `test_i01.py`）22 处，21 处检出：去掉 user/course 隔离、不往前找起算版本、连续性不中断、同值写入不看来源/总是写、不拒绝未知节点、脏来源参与继承、谱系缺陷/空版本/同一来源两处放行、不复核摘要、快照不核课程、绑定版本不在本课程也放行、不继承、同批重复放行、不记告警、继承来源不排序、不写缓存、写入不按指针版本、字段不闭合。存活 1 处为等价变异：覆盖判定 `>` 改 `>=`——写入序号与提交序号取自同一全局计数器，二者永不相等。另删除了一处冗余检查（`_history` 的课程核对，被 `_lineage` 的快照课程核对完全覆盖，篡改存活后确认冗余）。

## 接口 / 数据变更

- 新迁移 `011_progress.sql`（新表，不改既有表）。无契约、无依赖变更。
- 新仓储模块，暂无调用方（I02/I05 接入）。

## 风险

1. 投影（业务规则）放在仓储文件里，是 I01 文件锁所限；与后端规则「业务规则放 services」有张力。接口已固定，后续可把 `_project` 移到 `services/learning/` 而不改调用方。
2. 投影每次读取本课程全部已提交版本的元数据；解析结果按 `version_id` 缓存（LRU 256，多进程各自缓存，版本不可变无一致性问题）。版本数很多的课程第一次读较慢。
3. 历史版本快照损坏会让当前读取也报 500（投影需要全部版本的节点集与谱系）；这是按「不输出部分进度」的保守选择。
4. 仓储不校验 `user_id` 是否为课程学生成员（I02 负责）；未知 `user_id` 由外键拒绝（`sqlite3.IntegrityError`）。

## 待决

1. `specs/learning-path.md` 状态行仍写「后端尚未实现」，不在本任务文件锁内，建议协调者合入时更新或留给 I02/I05。
2. ADR-049 待 ArvinHan 审阅签收。

## 下一步

I02（掌握标记 API：鉴权、`write_progress`、错误映射）；I05（推荐：`resolve_published` → `project_progress` → I03/I04）。

## 回滚步骤

- 代码：撤销 `src/backend/app/repositories/progress.py`、`tests/backend/test_i01.py`、ADR-049。
- 数据：停 API 与 worker，恢复 `backups/*-before-011.sqlite`；或在一个事务里执行 `011_progress.sql` 文件头的两条 `ROLLBACK` 行（丢失全部学生进度；`commit_sequence` 属于 010，不动），然后删除迁移文件。
