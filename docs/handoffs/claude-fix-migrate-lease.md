# Claude 交接：迁移器租约检查与 C06 任务表不兼容（FIX-MIGRATE-LEASE）

- 状态：DONE（待 PR 审查/合并）
- 分支：`claude/fix-migrate-lease-guard` / base `origin/main@1ffda90`
- 发现途径：协调方在合并 C02（迁移 004）前同步 main 时，后端测试出现 97 个错误

## 问题

- C01 的 `_check_no_live_leases`（`src/backend/app/repositories/sqlite.py`）在每次应用待执行迁移前，对已存在的 `processing_tasks` / `tasks` 执行 `SELECT … WHERE lease_expires_at >= unixepoch()`，查询失败即 `MigrationError("Cannot inspect processing_tasks lease state")`，按设计“查不了就拒绝迁移”。
- C06（PR #209）的 `003_tasks.sql` 建 `processing_tasks` 时没有租约列：按 `docs/atomic-task-plan.md`，`lease_owner`、`lease_token`、`lease_expires_at` 等由 C09 加入。
- 后果：任何应用过 003 的数据库，**003 之后的所有迁移都无法应用**。main 上暂未出错只是因为还没有 004。

## 修复

- 新增 `_has_column`；只对**有租约列**的表检查租约（`processing_tasks`/`tasks` 的 `lease_expires_at`，`course_locks` 的 `expires_at`）。表里没有租约列，就不可能持有租约。
- 保持原“查不了就拒绝”：表有租约列但查询出错，仍抛 `MigrationError`；有效租约、当前秒到期的租约仍阻止迁移（原用例未改，继续通过）。
- 未修改已合入的 `003_tasks.sql`（改动已应用的迁移校验和风险更高）。

## 验证

| 命令 | 结果 |
| --- | --- |
| 修前 `pytest tests/backend/test_c01.py -q`（新增 3 个用例） | 3 failed（复现：真实 001～003 后追加 004 报 `Cannot inspect processing_tasks lease state`；无租约列的两类表被判为无法检查） |
| 修后 `pytest tests/backend/test_c01.py -q` | 21 passed |
| 修后 `pytest tests/backend -q`（venv，`PYTHONPATH` 指向本 worktree） | 981 passed |
| C02 分支并入本修复后 `pytest tests/backend -q` | 见 C02 交接 |
| `./scripts/verify.sh`、`git diff --check` | 见 PR |

## 接口 / 数据变更

无接口、数据模型、配置变化；仅迁移前检查逻辑。

## 风险与下一步

- **C09** 为 `processing_tasks` 增加租约列的迁移本身会通过（此时表无租约列）；之后的迁移会按列检查租约，符合原设计。
- 若将来租约列改名，须同步 `_check_no_live_leases` 的列名，否则检查会被静默跳过；建议 C09 在其测试中加一条“有效租约阻止迁移”的真实表回归。

## 回滚

`git revert` 本 PR 合并提交即可；无数据迁移。回滚后 003 之后的迁移将再次无法应用。
