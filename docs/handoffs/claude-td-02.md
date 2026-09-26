---
review_status: ready_for_review
task_id: TD-02
worktree: .claude/worktrees/td02-task-repo
branch: claude/td02-task-repo
base: bdcf165
---

# TD-02 交接：任务读取 SQL 迁入 `repositories/tasks.py`

## 任务与状态

来源：TD-01 第 3 项、C11 交接待决 1、C10 交接待办。只搬迁、不改行为。状态：DONE，待 PR 审查/合并。

## 改动文件

| 文件 | 改动 |
| --- | --- |
| `src/backend/app/repositories/tasks.py` | 新增 `TaskSnapshotRow`（含 `error_code`、`error_message`、`error_details_json`）、`read_task_snapshot(database, task_id, *, course_id)`（调用方连接/事务）、`get_task_snapshot(sqlite_url, task_id, *, course_id)`、`mark_cancel_requested(database, *, task_id, course_id, expected_stage, target_stage)`（C10 比较并交换写入）、`LeasedTaskRow` 与 `read_leased_task(database, task_id, lease_token)`（D11 按令牌读）。SQL 文本、列清单与条件逐字搬自原位置 |
| `src/backend/app/services/task_cancel.py` | 删除 SQL 与列常量；新增公开的 `snapshot_from_row(TaskSnapshotRow) -> TaskSnapshot`，是行 → `TaskSnapshot` 的唯一映射；`_read_task`、`_write_cancel` 保留原签名（C10 测试对它们打桩），内部改调仓储 |
| `src/backend/app/services/task_events.py` | 删除重复的 `_snapshot_from_row` 与列常量；`load_task` 改为 `get_task_snapshot` + `snapshot_from_row`，签名不变 |
| `src/backend/app/workers/parse_task.py` | `_leased_row` 改调 `read_leased_task`，仍返回原 `_LeasedRow`；带令牌条件的写入未动 |
| `tests/backend/test_td02.py` | 14 个用例：仓储新函数（课程隔离、错误列、调用方事务可见性、CAS 各条件、令牌读）、单一映射、服务/worker 无读取 SQL、`task_cancel` 无任务 SQL、仓储不导入 `app.services`/`app.workers`、worker 经仓储读取 |

`TaskSnapshot` 未移动，仍定义在 `app.services.task_cancel`（原导入路径不变）。

## 分层决定

- `TaskSnapshot.error` 是 `services/task_state.TaskError`，仓储不能依赖服务层，因此仓储返回自己的行类型 `TaskSnapshotRow`，`error_details` 保留为存储的 JSON 文本；解码与 `TaskError` 构造在服务层 `snapshot_from_row` 一处完成。这样也保住原行为：只有 `error_code` 非空时才解码 `error_details`。
- 未把数据类下沉到 `schemas/` 等中立位置：那会连带移动 `TaskError`，触及 `task_state.py` 及其所有导入方，超出本任务文件锁。
- 注：`repositories/task_leases.py` 现有 `from app.services.task_state import failure_code_allowed`，是已存在的反向依赖，不在本任务范围，未改动。

## 写入是否一起迁移（评估与决定）

- **C10 取消 UPDATE：已迁移**，即 `mark_cancel_requested`。它接收调用方连接，仍在 `cancel_task` 的同一个 `BEGIN IMMEDIATE` 事务内执行；`WHERE id AND course_id AND stage = ? AND cancel_requested = 0 AND stage IN (queued, parsing, extracting, merging)` 与 `updated_at` 表达式逐字不变，返回值仍为 `rowcount == 1`。理由：只是一条语句，事务边界不跨层，迁移后 `task_cancel.py` 完全没有 SQL；C10 并发/陈旧读用例（对 `_write_cancel`、`_read_task` 打桩）不改断言即通过。
- **D11 带租约令牌条件的写入（进度、T8、T4、T9）：不迁移**。理由：(1) 它们与 C09 的 `leased_transaction` fence 语义绑定，归属上更接近 `repositories/task_leases.py`，该文件不在本任务文件锁内；(2) 本任务验收只要求读取迁移，写入保持原位零风险。建议后续小任务把这四条写入迁到 `task_leases.py`（接收调用方连接，同一事务，条件逐字保留）。
- **D11 读取的隔离条件**：`read_leased_task` 按 `id AND lease_token` 读，保持原条件，未追加 `course_id`。租约令牌每次领取唯一，已是比课程更窄的归属条件；若追加 `course_id`，课程不符会从「抛 `ValueError`（调用方缺陷）」变成「返回 lost」，属于行为变化，与「只搬迁」冲突。C10/C11 的两条读取仍按 `id AND course_id` 隔离。

## 已运行命令与结果

`<venv>` 为本机 scratchpad 中新建的虚拟环境（`python3 -m venv` + `pip install -e './src/backend[test]'`），所有 pytest 命令带 `PYTHONPATH=$PWD/src/backend`。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 搬迁前对照 | `<venv>/bin/python -m pytest -q tests/backend/test_c10.py tests/backend/test_c11.py tests/backend/test_d11.py` | `121 passed, 1 warning` |
| TD-02 红灯 | 仅新增 `test_td02.py`，未改实现：`... -m pytest -q tests/backend/test_td02.py` | `13 failed, 1 passed` |
| TD-02 绿灯 | 同上，搬迁后 | `14 passed` |
| 搬迁后对照 | 同「搬迁前对照」，C10/C11/D11 测试文件未改 | `121 passed, 1 warning` |
| 后端全量 | `<venv>/bin/python -m pytest -q tests/backend` | `2535 passed, 1 warning` |
| 门禁 | `PATH=<venv>/bin:$PATH ./scripts/verify.sh` | `Scaffold verification passed.` |
| 空白 | `git diff --check` | 无输出 |
| 残留读取 | `grep -rn "FROM processing_tasks" src/backend/app/services src/backend/app/workers` | 无输出 |
| 静态检查 | `<venv>/bin/python -m pyflakes`（改动的 5 个文件） | 无输出 |

说明：`test_c11.py::test_event_source_is_the_database_not_an_in_process_bus` 断言 `task_events.py` 源码含 `processing_tasks`。模块说明里本来就写明事件源是该表的行（现在经仓储读取），这句保留了该词，断言未改。

## 接口 / 数据 / 配置变更

- 新增仓储公开符号：`TaskSnapshotRow`、`LeasedTaskRow`、`read_task_snapshot`、`get_task_snapshot`、`mark_cancel_requested`、`read_leased_task`；新增服务公开函数 `task_cancel.snapshot_from_row`。
- 删除私有符号：`task_events._snapshot_from_row`、`task_cancel._snapshot_from_row`、两处 `_COLUMNS`、`task_cancel._NOW_TEXT`。仓库内无其他引用。
- HTTP 接口、契约、数据库结构、迁移、依赖、环境变量均无变化。

## 风险

- 行为等价依赖 SQL 逐字搬迁；C10 的并发与陈旧读用例、C11 的快照/差分用例、D11 的令牌丢失用例都覆盖了搬迁后的路径。
- `_read_task` / `_write_cancel` 仍作为测试打桩点保留；日后改名需同时改 C10 测试。

## 回滚

`git revert <本 PR 合并提交>` 即可。无数据或迁移变更，回滚不需要数据操作。

## 下一步

- 把 D11 四条带租约令牌的写入迁到 `repositories/task_leases.py`（见上）。
- 消除 `repositories/task_leases.py` 对 `app.services.task_state` 的依赖（可把 `failure_code_allowed` 所需的码表下沉）。
- C11 待决 2（导出生成的 `Task` 模型并修 B10F-R01）仍未处理。
