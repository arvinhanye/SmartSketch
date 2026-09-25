# Claude 交接：C09 worker 原子领取与租约

- `task_id`: C09（GitHub issue #66）
- `review_status`: ready_for_review（「待决」第 1、2 条已由 ADR-017 决定 1、6 解决，见文末「ADR-017 追加」；第 3 条仍待决）
- `worktree`: `/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/c09-task-leases`，分支 `claude/c09-task-leases`
- `base`: `54b37d8`（认领提交，基于 main `36670a3`）；`head` 以分支最新提交为准。写交接时 `origin/main` 已到 `5a0bcdb`（D08、B14、#218），迁移最大号仍是 004
- 依据：`specs/task-processing.md` §2（T2/T8/T9）、§6、§8.1～§8.3、§8.7、§8.9 LEASE-1/4/5/7/8/9/16、TASK-8；ADR-011 决定 2～4；C06 `003_tasks.sql`；C08 `services/task_state.py` 的 `FAILURE_CODE_STAGES`；C01 迁移器 `_check_no_live_leases`；`docs/handoffs/claude-fix-migrate-lease.md`

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/migrations/005_task_leases.sql` | 给 `processing_tasks` 加租约六列和任务错误三列，回填已有任务的 `not_before`，新增两个触发器 |
| `src/backend/app/repositories/task_leases.py` | `claim_next`、`renew_lease`、`fence`、`leased_transaction`、`reclaim_expired`、`clear_cleanup_pending`、`release_after_transient_failure`、`release_on_shutdown`；记录类型 `Lease`、`ReclaimedTask`、`ReclaimResult`、`ReleaseOutcome`；异常 `LeaseLost` |
| `tests/backend/test_c09.py` | 50 个用例（成功、边界、失败路径） |

未改 `repositories/tasks.py`（C03 #216 在改）、`sqlite.py`、`003_tasks.sql`、`pyproject.toml`、`docs/integrations.md`、`scripts/verify.sh`。`docs/architecture.md`、C08 `services/task_state.py` 与 `tests/backend/test_c08.py` 由 ADR-017 追加提交修改（见文末）。

## 表结构（`005_task_leases.sql`，全部为内部字段，不上 wire）

| 列 | 类型与约束 | 依据 |
| --- | --- | --- |
| `lease_owner` | TEXT，可空，长度 1～255 | §8.2，仅用于排查 |
| `lease_token` | TEXT，可空，长度 ≥ 32（仓储用 `secrets.token_hex(16)`，128 位） | §8.2「不少于 128 位」 |
| `lease_expires_at` | INTEGER（unix 秒），可空；与 `lease_token`、`lease_owner` 同为空或同非空 | §8.2「NULL 表示无人持有」；与迁移器的 `lease_expires_at >= unixepoch()` 同单位 |
| `attempt` | INTEGER NOT NULL DEFAULT 0，≥ 0 | §8.2 |
| `not_before` | INTEGER（unix 秒）；已有任务回填为 `unixepoch(created_at)`；新任务由 `AFTER INSERT` 触发器置为创建时间；`BEFORE UPDATE` 触发器拒绝改成 NULL | §8.2「初值为任务创建时间」。`ADD COLUMN` 不能用非常量缺省值，C06 的插入语句又不能改，所以用触发器 |
| `cleanup_pending` | INTEGER NOT NULL DEFAULT 0，∈ {0, 1} | §8.2、§8.4 |
| `error_code`、`error_message`、`error_details` | 可空；I4：`stage = 'failed'` ⇔ `error_code` 非空；`error_message` 与 `error_code` 同为空或同非空且非空白；`error_details` 为 JSON 对象 | §2 I4、§6、§8.3 的 T9 需要落 `error`；**见待决 1** |

时间一律由 SQLite 在语句执行时求值（`unixepoch()`），不接收 worker 传入的时间（§8.1）。

## 关键决定

1. **领取**：一个 `BEGIN IMMEDIATE` 事务里只执行一条语句：`UPDATE … WHERE id = (SELECT id … WHERE C ORDER BY created_at, id LIMIT 1) AND C RETURNING …`。C 与 §8.2 逐字一致：`attempt < max AND not_before ≤ 现在 AND cancel_requested = 0 AND (stage = queued OR (stage ∈ 处理中四阶段 AND (lease_expires_at IS NULL OR lease_expires_at < 现在)))`。写新 owner/token、`lease_expires_at = 现在 + L`、`attempt + 1`；`queued` 同句转 `parsing`（T2），其余阶段 `stage` 和 `progress` 不变（接管）。0 行返回 `None`，不重试同一行。领取是全局队列，不按课程过滤；返回的 `Lease` 带 `course_id`，供后续按课程隔离。
2. **防旧写**：`fence(连接, task_id, token)` 在调用方已开启的事务里执行 `UPDATE processing_tasks SET lease_token = lease_token WHERE id = ? AND lease_token = ?`，0 行抛 `LeaseLost`，不在事务里调用直接报错。`leased_transaction` 负责 `BEGIN IMMEDIATE`、fence、提交，出任何异常都回滚。fence 放在事务开头：`BEGIN IMMEDIATE` 之后写锁一直持有，别人在事务期间换不了令牌。D11/E12/F13 对任务行和附属表（块检查点、T6 序号）的所有写入都应经过它。
3. **续约**：`UPDATE … SET lease_expires_at = 现在 + L WHERE id = ? AND lease_token = ? RETURNING`，返回新到期时间，0 行返回 `None`。按规格只校验令牌：租约已过期但还没被接管时，续约仍会成功。
4. **回收**：`reclaim_expired` 在一个事务里依次执行：① 取消已请求，阶段在 `parsing/extracting/merging`，租约过期或已释放 → `cancelled`（T8），清空租约；② 阶段在处理中四阶段，`attempt ≥ max`，租约过期或已释放 → `failed`，`TASK_ATTEMPTS_EXHAUSTED`，`details = {attempts, stage}`，`progress` 不变，清空租约；③ 其余不动，等待接管；另外列出 `stage = failed AND cleanup_pending = 1` 的任务。① 先于 ②，所以取消优先于耗尽。返回值带 `course_id`，推送 `cancelled`/`error` 事件由调用方（C11）负责。回收条件不看 `not_before`，与规格一致。
5. **主动释放**：`release_after_transient_failure` 只接受 `STORAGE_UNAVAILABLE`、`LLM_UNAVAILABLE`（§8.3 只有这两种阶段级临时故障）。`attempt < max` 时清空租约，并置 `not_before = 现在 + 30 × 2^(attempt−1)`（依次 30、60 秒）；`attempt ≥ max` 时直接 T9，沿用该故障码，`details = {attempts, stage}`。两条 UPDATE 都带令牌条件；令牌已失效返回 `lost`，不做任何写入。终态码须经 C08 `failure_code_allowed(code, stage, details)` 判定可用，否则抛 `ValueError`，不写入。ADR-017 决定 6 之后，`merging` 中 `LLM_UNAVAILABLE` 耗尽直接写入该码；仍会被拒的只剩 `parsing`、`persisting` 中的 `LLM_UNAVAILABLE`（这两个阶段不调用模型）。
6. **正常退出**：`release_on_shutdown` 用一条带令牌条件的语句清空租约，置 `not_before = 现在`、`attempt − 1`。
7. **失败码与消息**：`error_message` 用中文面向用户（与 `errors.v1.md` 示例一致），不含堆栈或原文。
8. **配置**：LEASE-16（`TASK_MAX_ATTEMPTS=0`、`TASK_LEASE_SECONDS=5` 被拒并指出变量名）已由 B06 的 `load_settings` 实现，本任务只补回归用例；worker 启动时调用它归 D11/K08。仓储函数另外把 `lease_seconds`、`max_attempts` 限为正整数（排除 bool）。

## 验收对应

| 验收 | 用例 |
| --- | --- |
| LEASE-1 两个连接争同一任务只有一个成功 | `test_two_connections_claiming_the_same_task_exactly_one_wins`（两个线程、两条真实连接，用 Barrier 对齐，重复 10 轮）；`test_many_concurrent_workers_each_task_is_owned_once`（8 个线程抢 5 个任务） |
| LEASE-4 旧令牌不能续约或写回 | `test_old_token_cannot_renew_after_takeover`；`test_stale_token_writes_are_rolled_back_and_leave_the_new_owner_untouched`（进度、模拟块检查点表、T6 式阶段写入三种都回滚，B 的写入成功） |
| 到期可接管 | `test_expired_lease_is_taken_over_without_changing_stage_or_progress`；`test_unexpired_lease_is_not_taken_over` |
| LEASE-5 续约 | `test_renew_extends_the_lease_for_the_current_token` |
| LEASE-7 尝试耗尽 | `test_reclaim_fails_a_task_after_three_consecutive_expired_leases`；`test_transient_failure_on_the_last_attempt_fails_with_the_fault_code` |
| LEASE-8 过期且已请求取消 | `test_reclaim_cancels_an_expired_task_with_a_cancel_request` |
| LEASE-9 正常退出 | `test_shutdown_release_does_not_count_the_attempt` |
| LEASE-16 非法配置 | `test_invalid_lease_configuration_is_refused_by_name` |
| TASK-8 取消与领取竞争 | `test_claim_and_cancel_race_has_a_deterministic_winner` |
| 可领取条件 C / 退避 | `test_claim_skips_tasks_outside_the_claimable_condition`；`test_claim_order_is_created_at_then_id_across_courses`；`test_transient_failure_release_backs_off_thirty_seconds_times_two_to_the_attempt` |
| #212 交接要求的迁移回归 | `test_live_lease_on_the_migrated_task_table_blocks_the_next_migration`（有效租约 → `MigrationError`，探针迁移未应用；把租约改为过期后同一迁移成功）；`test_released_lease_does_not_block_the_next_migration` |

迁移用例只用临时目录：复制真实迁移中版本号不超过租约迁移的文件，再加一个 `<租约号+1>_lease_probe.sql` 探针。租约迁移按文件名后缀 `*_task_leases.sql` 查找，合并前改号不影响用例；不断言真实迁移目录的全集。

## 验证（实际结果）

测试环境：scratchpad 下本任务专用 venv（`pip install './src/backend[test]'` 后卸载 `smartsketch-backend` 包，pip 留下的 `build/`、`egg-info` 已移出 worktree），运行时 `PYTHONPATH=<worktree>/src/backend`。Python 3.13.5，SQLite 3.45.3。

| 命令 | 结果 |
| --- | --- |
| 基线 `pytest tests/backend -q`（未改动） | 1002 passed |
| 红灯 1：`pytest tests/backend/test_c09.py -q`（无实现） | 收集阶段 ImportError，1 error |
| 红灯 2：同上（只有函数签名、会抛错的桩，无迁移） | 3 failed、45 errors、2 passed（通过的 2 个是 LEASE-16 配置用例，B06 已实现） |
| 实现后 `pytest tests/backend/test_c09.py -q` | 50 passed，exit 0；连跑 5 次均为 50 passed |
| `pytest tests/backend -q` | 1052 passed，exit 0（1 条 warning 在基线就有） |
| `./scripts/verify.sh` | exit 0，`Scaffold verification passed.` |
| `git diff --check` | exit 0 |

反向篡改（每次改完都用备份恢复，并用 `cmp` 确认与备份一致）：

| # | 篡改 | 结果 |
| --- | --- | --- |
| M1 | `fence` 去掉令牌条件 | 2 failed（旧令牌写回、调用方事务内 fence） |
| M2 | `renew_lease` 去掉令牌条件 | 1 failed（旧令牌续约） |
| M3 | 可领取条件去掉「租约已过期或无人持有」 | 8 failed |
| M4 | 退避指数 `attempt − 1` 改成 `attempt` | 1 failed |
| M5 | 正常退出不回退 `attempt` | 1 failed |
| M6 | 领取改成先查后写（另开连接 SELECT，再 `UPDATE WHERE id = ?`） | 2 failed（两个并发用例；单独连跑 3 次都检出） |
| M7 | 回收时先判耗尽、后判取消 | 1 failed |
| M8 | 迁移去掉 I4 检查 | 2 failed |

## API / 数据 / 配置变更

- 数据：`processing_tasks` 新增 9 列、2 个触发器（见表结构）。没有新增表或索引，也不改已有列。
- API / 契约：无（所有新字段都是内部字段）。
- 配置：无新增变量；使用已登记的 `TASK_LEASE_SECONDS`、`TASK_MAX_ATTEMPTS`，由调用方从 `Settings` 传入。

## 回滚

只向前迁移（§8.7）。回滚：停止 API 与 worker → 用 `backups/*-before-005.sqlite` 替换数据库文件（按 `src/backend/README.md`「SQLite 迁移与恢复」，先保留失败库及 WAL 附属文件）→ 重启。代码回滚用 `git revert` 撤销本任务提交。数据库和代码要一起回滚：只回滚数据库，下次运行迁移会重新应用 005；只回滚代码，迁移器会报「Database has a migration version absent from this codebase」。

## 待决（需 ArvinHan 决定）

1. **（已由 ADR-017 决定 1 解决）任务错误列不在「租约列」范围内，但本任务加了。** ADR-017 决定 1 确认三列并入 C09、列名与 JSON 编码保持、I4 在数据库层强制；`docs/architecture.md` 数据模型已登记。以下为原始记录： 回收（§8.2 第 2 步）和主动释放（§8.3）都要执行 T9，而 I4 要求 `failed` 必须带 `error`。C06 建表时没有错误列，规划中也没有任务负责这几列。本任务在 005 中加了 `error_code`、`error_message`、`error_details`（JSON），并用 CHECK 在数据库层强制 I4。请确认：列名和 JSON 编码可以接受（C11 返回 `Task.error` 时要读这几列）；I4 放在数据库层，之后任何写入路径都绕不过。若不接受，替代方案是拆一个独立任务加错误列，C09 暂缓回收的 T9 分支。
2. **（已由 ADR-017 决定 6 解决）`LLM_UNAVAILABLE` 在 `merging` 阶段耗尽时用什么码。** ADR-017 决定 6：写入 `LLM_UNAVAILABLE`，C08 码表放开 `merging`（仅限尝试耗尽）。实现见文末。以下为原始记录： §8.3 写「沿用该故障的码」，§6 耗尽行写「任意处理中阶段」，但 §6 的 `LLM_UNAVAILABLE` 行和 C08 的 `FAILURE_CODE_STAGES` 只允许 `extracting`。而 `merging` 也调用模型（E10）。当前实现：抛 `ValueError`，不写入；租约自然过期后，由回收按 `TASK_ATTEMPTS_EXHAUSTED` 置为失败。需要决定是放宽 C08 表，还是 `merging` 的熔断不走主动释放。
3. **`materials.parse_status` 不随任务阶段同步。** C06 建了这一列，初值 `queued`。领取和回收都没有改它，因为规格没说谁维护。建议 C07 或 C11 确认它是否需要跟随 `stage`。

## 风险与下一步

- **终态写入要清空租约**：D11/E12/F13 用 `leased_transaction` 执行 T6/T8/T9 时，应在同一条 UPDATE 里把 `lease_owner`、`lease_token`、`lease_expires_at` 置为 NULL。否则终态行上仍有未过期的租约，会让迁移器拒绝迁移，直到租约过期（最长 L 秒）。数据库层没有强制这一点，以免约束其他任务的写法。本任务自己的 T8/T9（回收、主动释放）都已清空租约。
- **推送**：回收把任务转为 `cancelled`/`failed` 后，由调用方负责推送 SSE；目前还没有事件出口（C11）。
- **worker 循环**：「每次领取前先回收」、心跳每 L/3 续约、本地截止规则（单调时钟）都在 worker 进程里，归 D11/K08。本任务只提供存储原语。
- **清理重试**：`reclaim_expired().cleanup_pending` 列出待清理的任务，清理成功后调用 `clear_cleanup_pending(按课程)`；置 `cleanup_pending = 1` 的写入由 F13 在 T9 事务里完成。
- LEASE-2/3/6/10～15/17～30 分属 E12、F13、G04、C01、E04 等任务，本任务不覆盖。
- 合并前若 main 已有 005，按 D-10 改号：重命名迁移文件，并改文件头注释和本交接；测试按后缀查找文件，不需要改。

## ADR-017 追加（2026-09-25）

依据 `docs/decisions.md` ADR-017 决定 1、6 与「后果」第 1 条。C08 的 `task_state.py` 属范围扩展，由该 ADR 授权。

### 改动

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/task_state.py` | `FAILURE_CODE_STAGES["LLM_UNAVAILABLE"]` 放开为 `{extracting, merging}`；新增 `EXHAUSTION_ONLY_FAILURES = {("LLM_UNAVAILABLE", "merging")}` 与 `failure_code_allowed(code, stage, details)`；`apply_event` 的 `fail` 分支改用它判定，拒绝理由仍为 `error_stage_mismatch` |
| `src/backend/app/repositories/task_leases.py` | 耗尽分支先构造 `details = {attempts, stage}`，再用 `failure_code_allowed` 判定后写入；`merging` 的 `LLM_UNAVAILABLE` 直接 T9，不再抛 `ValueError`、等租约过期后由回收改记 `TASK_ATTEMPTS_EXHAUSTED` |
| `tests/backend/test_c08.py` | 期望码表改为 `LLM_UNAVAILABLE: {extracting, merging}`；新增 15 个用例（见下） |
| `tests/backend/test_c09.py` | 原「`merging` 耗尽报 `ValueError`」用例改为正例；拒绝用例改用 `parsing`、`persisting` 两个阶段；新增 `merging` 未耗尽时退避的回归 |
| `specs/task-processing.md` | §6 `LLM_UNAVAILABLE` 行「契约现状」列补注：`merging` 尝试耗尽时也用此码，依据 ADR-017 决定 6。其他规则未改 |
| `docs/architecture.md` | 「核心数据模型」新增一行：`processing_tasks` 的租约六列、错误三列与 `failed` ⇔ `error_code` 非空，引用 ADR-017 决定 1 |

### 额外约束：为什么加了 `failure_code_allowed`

C08 码表是「码 → 允许的阶段集合」，只能按阶段放开，无法表达 ADR-017 要求的「仅限尝试耗尽」。只改码表会让任何调用 `apply_event` 的代码（D11/E10）在 `merging` 遇到第一次模型故障就直接以 `LLM_UNAVAILABLE` 终结任务，跳过 §8.3 要求的主动释放与退避。所以保持码表结构不变，另加一张「仅限耗尽」的 `(码, 阶段)` 表：命中时 `details` 必须是映射，且 `attempts` 为 ≥ 1 的整数（排除 bool、浮点、字符串）、`stage` 等于当前阶段。`extracting` 的 `LLM_UNAVAILABLE`（超阈值，`details` 为块计数）不受影响。C09 与 C08 共用这一个函数，写入库的错误必然能被 `fail` 事件接受（`test_c09` 正例里有交叉断言）。

### C08 旧断言的变化

`test_c08.py` 原先的期望码表 `"LLM_UNAVAILABLE": {"extracting"}`（REVIEW-C08 R02）等于断言「`LLM_UNAVAILABLE` 只能用于 `extracting`」。已按 ADR-017 改为 `{"extracting", "merging"}`。参数化用例 `test_failure_code_is_bound_to_stage` 对 `(LLM_UNAVAILABLE, merging)` 不带 `details` 的事件仍期望 `error_stage_mismatch`，因为缺耗尽细节。

### 新增用例

- `test_c08.py`（+15）：`test_exhaustion_only_pairs_match_implementation`；`test_llm_unavailable_in_merging_is_allowed_when_attempts_are_exhausted`；`test_llm_unavailable_in_merging_without_exhaustion_details_is_rejected` × 10（无 details、空、缺 stage、缺 attempts、stage 不符、attempts 为 0/True/"3"/3.0、块计数式 details）；`test_llm_unavailable_in_extracting_keeps_its_threshold_meaning`；`test_llm_unavailable_stays_out_of_parsing_and_persisting_even_when_exhausted` × 2。
- `test_c09.py`（净 +3，共 53）：`test_llm_outage_on_the_last_merging_attempt_fails_with_llm_unavailable`（`failed`、进度不变、`details = {attempts: 3, stage: merging}`、租约清空、C08 接受该错误、之后回收不改码）；`test_llm_outage_before_the_last_merging_attempt_backs_off_instead_of_failing`；`test_exhausting_code_not_allowed_in_the_stage_is_refused_without_writing[parsing|persisting]`（替换原 `merging` 版本）。

### 验证（实际结果）

测试环境：scratchpad 下新建 venv `venv-c09-adr017`（Python 3.13.5），只按 `pyproject.toml` 的固定版本安装依赖与 test 依赖，未安装本包、未 editable；运行时 `PYTHONPATH=<worktree>/src/backend`。

| 命令 | 结果 |
| --- | --- |
| 基线 `pytest tests/backend -q`（ADR-017 合入后、本次改动前） | 1100 passed |
| 红灯：先改测试，`pytest tests/backend/test_c08.py -q` | 3 failed、134 passed（新增正例 2 个 + 改后的码表断言 1 个；新增的 10 个拒绝用例与 3 个其他用例在旧实现下已通过，它们是放开后防止过度放开的守卫） |
| 红灯：`pytest tests/backend/test_c09.py -q` | 1 failed、52 passed（`merging` 正例） |
| 实现后 `pytest tests/backend/test_c09.py -q` | 53 passed，exit 0 |
| 实现后 `pytest tests/backend/test_c08.py -q` | 137 passed，exit 0 |
| `pytest tests/backend -q` | 1118 passed，exit 0（1 条 warning 基线就有） |
| `./scripts/verify.sh` | exit 0，`Scaffold verification passed.` |
| `git diff --check` | exit 0 |

反向篡改（改前备份，改后运行 `test_c08.py` + `test_c09.py`，再用备份恢复并 `cmp` 确认一致）：

| # | 篡改 | 结果 |
| --- | --- | --- |
| A1 | 码表不放开 `merging`（`LLM_UNAVAILABLE` 回到 `{extracting}`） | 3 failed（C08 正例、码表一致性、C09 `merging` 正例） |
| A2 | C09 耗尽 `details` 去掉 `stage` | 2 failed（C09 `merging` 正例因 C08 拒绝而抛 `ValueError`；`STORAGE_UNAVAILABLE` 耗尽的 details 断言） |
| A3 | C08 去掉「仅限耗尽」约束（码表放开即通过） | 11 failed（10 个拒绝用例 + 参数化 `LLM_UNAVAILABLE-merging`） |

### 仍待决

- 原待决 3（`materials.parse_status` 不随任务阶段同步）未变。
- `merging` 中单次模型故障（熔断器打开、未耗尽）仍走主动释放退避；E10/D11 调用 `apply_event` 以 `LLM_UNAVAILABLE` 失败 `merging` 时须带 `details = {attempts, stage}`，否则被拒。
