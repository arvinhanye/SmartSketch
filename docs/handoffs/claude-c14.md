# Claude 交接：C14 账号管理命令与演示账号种子

- 日期：2026-09-25
- 分支 / base：`claude/c14-account-seed` / `origin/main@04f8ac6`
- 认领：issue #161（ArvinHan 同意由 Claude 接取）
- 依据：`specs/identity-access.md` §1.1、§1.2（ADR-013）；C13 的 `create_account`、`users` 表（迁移 002）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/repositories/accounts.py` | 只追加三个函数：`list_accounts`；`set_disabled`（用 `COALESCE` 保留首次停用时间，启用时置 NULL）；`update_password_hash` |
| `src/backend/app/services/account_admin.py`（新建） | `DEMO_ACCOUNTS`、`set_disabled`、`reset_password`、`list_accounts`、`seed_demo_accounts`；异常 `AccountNotFound`、`DemoSeedConflict` |
| `scripts/seed-demo-accounts.py` | 读 `SEED_DEMO_PASSWORD`，缺失或空白时非 0 退出；检查待迁移；逐个输出 created 或 exists, unchanged |
| `scripts/manage-accounts.py` | 子命令 `create`、`disable`、`enable`、`reset-password`、`list`；口令交互输入两次，或 `--password-env VAR` |
| `tests/backend/test_c14.py` | 26 个用例：服务层 13 个，脚本以子进程运行 13 个 |
| `docs/integrations.md` | `SEED_DEMO_PASSWORD` 行注明读取方；新增账号命令用法表 |
| `docs/tasks.md` | 新增「C14」节 |

**范围扩展**：原子清单只列了两个脚本和测试文件。后端规则要求业务逻辑放 `services/`、持久化放 `repositories/`，不能在脚本里写 SQL，所以新增了服务模块，并在仓储里追加函数。#161 与任务板都已登记。

## 行为约定

- **种子**：先校验口令，再检查三个演示用户名是否被类型不符的账号占用，都通过后才写入，所以任一检查失败都不写库。已存在的账号不改口令、不改停用状态（§1.2「不重置已有账号的口令」）。并发重跑时遇到重复用户名，按「已存在」处理。
- **停用**：不删行（§1.1）。重复停用保留首次时间，方便复查。C13 登录与 C03 的每次回查都看 `disabled_at`，所以停用后旧令牌的下一次请求即 401（IAM-10 由 C03 覆盖）。
- **口令输入**：不接受命令行参数。argparse 默认允许前缀缩写，`--password X` 会被当成 `--password-env X`，于是口令会出现在「变量未设置」的报错里；它还会在 `unrecognized arguments` 里原样回显多余参数。测试抓到了这两处，现在的处理：解析器全部 `allow_abbrev=False`；遇到多余参数时只打印固定提示，不回显。
- **迁移**：两个脚本都先调用 `pending_migrations`（只读，不建库文件）。有待迁移时非 0 退出，并提示运行 `python -m app.repositories.sqlite`。脚本不会替用户跑迁移，因为迁移会做备份，也有租约检查。
- 输出只含用户名、账号类型、创建时间、停用状态，从不含口令和哈希；`AccountRecord.__repr__` 本来就不含哈希。

## 验证

| 命令 | 结果 |
| --- | --- |
| 红灯：只有测试时 `pytest tests/backend/test_c14.py -q` | 收集失败（`app.services.account_admin` 不存在） |
| 加仓储与服务后 | 服务层用例全过；6 个脚本用例失败（脚本不存在） |
| 加脚本后 | 1 failed：`--password` 被当作 `--password-env` 的缩写。改为 `allow_abbrev=False` |
| 新增「不回显 `--password`」用例 | 2 failed（`unrecognized arguments` 回显口令），改为不回显后全过 |
| `pytest tests/backend/test_c14.py -q` | **26 passed** |
| `pytest tests/backend -q` | **746 passed**，1 warning（既有 Starlette `httpx` 弃用提示） |
| `./scripts/verify.sh` | exit 0，`Scaffold verification passed.` |

反向篡改（逐项改坏后跑 C14，再恢复）：

| 篡改 | 结果 |
| --- | --- |
| 去掉角色冲突检查 | 1 failed |
| 重复停用覆盖首次时间 | 1 failed |
| 重置口令不校验长度 | 1 failed |
| `create` 子命令允许参数缩写 | 3 failed |
| 回显多余参数 | 2 failed |
| 不检查待迁移 | 1 failed |
| 空白口令放行 | 1 failed。原测试用 3 个空格，本来就因长度不足被拒，没起作用；已改为 12 个空格 |
| 已存在的账号也调用创建 | 26 passed，等价变异：唯一约束抛出的重复用户名异常被捕获，结果同样是「未新建」 |
| 只在顶层解析器允许缩写 | 26 passed，等价变异：`--password` 由子解析器处理 |

## 接口 / 数据变更

没有契约、迁移或配置变更。`users` 表只用到已有的 `disabled_at` 和 `password_hash` 列。

## 风险与下一步

- 协作教师经命令行加入课程（§3.3）需要 C02 的 `courses`、`course_members`，不在本任务，交 C02/C15。
- 交互输入口令依赖终端。在 CI 或脚本里请用 `--password-env`。
- K09（演示流程）如果要改演示用户名，改 `account_admin.DEMO_ACCOUNTS` 一处即可。

## 回滚

删除新增的 4 个文件（两个脚本、`account_admin.py`、`test_c14.py`），撤销 `accounts.py` 末尾追加的三个函数，还原文档改动。没有数据或迁移需要回滚。
