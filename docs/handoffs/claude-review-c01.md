# 交接：同步并审查 C01（PR #174，539210 / kongsc）

- `task_id`: REVIEW-C01
- `status`: 审查完成；按 ArvinHan 的决定由 Claude 修 R01～R03 后合并，R04～R09 未改
- `审查目标`: `origin/codex/c01-sqlite` @ `121365c`（base `9d2437e`），同步后 @ `c9d5738`
- `依据`: `specs/task-processing.md` §8.2、§8.5、§8.7（ADR-011）；ADR-012 补注（`embedding_space_state`）；`docs/integrations.md`「调用记录」（ADR-011 修订 2、3）；AGENTS.md §5

## 同步

合入 `origin/main@6790d22`（含 B02～B04、CI-02、B10、B13），只有 `docs/tasks.md` 冲突：main 在同一位置已有「A10 批 1 补」一节。按任务编号把 C01 节移到 B13 之后，内容逐字不变（脚本比对一致）。代码文件自动合并。只用 merge，没有改写原提交。

## 审查结论

实现质量扎实：迁移 SQL 与版本记录同一事务、authorizer 拒绝脚本自带的事务控制、备份后校验完整性、历史缺口与校验和漂移都在执行任何迁移前检查；`model_calls` 字段与「调用记录」一节逐项一致；`course_locks.expires_at` 与 §8.5 一致；租约测试用固定时钟，不受秒边界影响。以下是需要处理的问题。

| ID | 级别 | 问题 | 建议 |
| --- | --- | --- | --- |
| R01 | P2 | 校验和取 `read_bytes()`，`.gitattributes` 只对生成物规定 `eol=lf`；Windows 上开启 `core.autocrlf` 会检出 CRLF，校验和与 macOS/Linux 不同（仓库索引中为 LF；未在 Windows 实测） | `.gitattributes` 加 `src/backend/migrations/*.sql text eol=lf`，或对归一化换行后的文本计算校验和 |
| R02 | P2 | API 启动不检查 `schema_migrations` 是否已到最新版本；未迁移的库也能启动，问题要到 C02/C06/E04 首次访问才暴露 | lifespan 与 C09 worker 入口加「已应用版本 = 代码库最新版本」门禁 |
| R03 | P2 | `embedding_space_state` 的 DDL 同时在 `001_base.sql` 与 B06 的 `embedding_space.py`；启动门禁仍会建表 | 门禁只读写行，表缺失即报「未迁移」；建表只留在迁移 |
| R04 | P3 | 租约守卫只查猜测的 `processing_tasks` / `tasks`；任务表名由 C06 决定，不符时静默放行；测试只覆盖 `processing_tasks` | 扫描所有含 `lease_expires_at` 列的表，或要求 C06 登记表名并加测试 |
| R05 | P3 | `embedding_space.py` 仍自行解析路径并直接 `sqlite3.connect`，没有用新的 `connect()`；`SQLITE_URL` 有三套解析 | 门禁改用 `connect()` / `database_path()` |
| R06 | P3 | README 的迁移与恢复步骤只有 PowerShell（AGENTS.md §5 要求迁移有回滚步骤） | 补 bash 版本 |
| R07 | P3 | `main()` 不处理 `SettingsError`，环境变量错误时打印堆栈 | 转为只含变量名的拒绝信息与退出码 1 |
| R08 | P3 | 每个待执行版本都整库备份，`backups/` 没有保留策略 | 每次运行只在首个待执行版本前备份一次，并写明保留策略 |
| R09 | P3 | `provider_role` 是闭集（主用 / 备用）却没有 CHECK，`status` 有 | 加 CHECK；表已由迁移创建，越晚加越要重建表 |

R02、R03 可合并为一个改动：启动门禁改为校验迁移版本并只读写 `embedding_space_state` 的行。

## 已运行命令与结果（macOS，Python 3.13.5）

| 命令 | 结果 |
| --- | --- |
| 同步后 `./scripts/verify.sh` | exit 0（负例 24 项，B08、B09、B10、B13 回归） |
| 新建 venv，`pip install -e './src/backend[test]'`、`pip check` | 通过 |
| `pytest tests/backend -q` | 71 passed，与 PR 描述一致 |
| `git ls-files --eol src/backend/migrations/001_base.sql`、`git check-attr -a` | 索引与工作区均为 LF，无属性 |
| GitHub CI（`c9d5738`） | Repository scaffold、Frontend、Backend 均通过；Backend 为首次在 CI 中运行 C01 测试 |

`pip install -e` 生成的 `src/backend/smartsketch_backend.egg-info/` 已删除（`.gitignore` 未忽略，见 HANDOFF-0924 第 7 节）。

## R01～R03 的修正（ArvinHan 2026-09-24 决定：由 Claude 修后合并）

- **R01**：`_checksum()` 先把 CRLF 归一化为 LF 再算 SHA-256；`.gitattributes` 加 `src/backend/migrations/*.sql text eol=lf`。两层都做：规则防止检出差异，归一化兼容已经存在的 CRLF 副本。
- **R02**：新增只读的 `pending_migrations(sqlite_url)`——校验历史（与 `migrate()` 共用 `_validate_history()`），返回未执行版本；数据库文件不存在时直接返回全部版本，**不会创建文件**。`services/startup.py` 新增 `validate_schema_current()`，API lifespan 在向量空间门禁之前调用；有未执行迁移或历史不一致即以 `SettingsError` 拒绝启动，并提示停机后运行 `python -m app.repositories.sqlite`。C09 worker 入口须调用同一检查。
- **R03**：`embedding_space.py` 删除 `CREATE TABLE`，只在事务内读取或写入这一行；建表只在迁移 001。
- **行为变化与文档**：首次启动前必须先迁移。已在 `docs/decisions.md` 补「ADR-012 补注修订 1」（改的是已签收的决定 1 中「启动时建表」一句，首次写入与不一致即拒绝的规则不变），并更新 `docs/architecture.md`、`src/backend/README.md`（启动前先迁移）。
- **测试**：`test_c01.py` 新增 5 项（CRLF/LF 校验和一致、`.gitattributes` 规则、只读检查不建库且校验历史、API 未迁移拒绝启动、门禁不建表）；「接管」用例改为手工建旧版 B06 表来模拟已有数据库，场景不变。`test_b05.py`、`test_b06.py` 在启动 API 前先 `migrate()`——这是本次有意引入的前置条件，断言未改动。

| 命令 | 结果 |
| --- | --- |
| 改实现前 `pytest tests/backend -q` | 收集失败：`cannot import name 'pending_migrations'` |
| 改实现后 | 76 passed（原 71 + 新 5） |
| 逐项撤销修复（不归一化换行、去掉 `.gitattributes` 规则、lifespan 不调检查、只读检查改为会建库、门禁恢复建表） | 分别 1、1、1、2、1 failed，且失败的正是对应的新测试；恢复后 76 passed |
| 命令行端到端（临时库） | 未迁移时 `python -m app` 退出码 3，报「SQLite schema is not migrated (pending: 001)…」且未创建数据库文件；`python -m app.repositories.sqlite` 先后输出 `001`、`none`；之后启动 API，`/health` 返回 `{"status":"ok","version":"0.1.0"}` |
| `./scripts/verify.sh` | exit 0 |
| `git diff --check` | exit 0 |

## 未验证

- R01 的 CRLF 情形只按 git 行为推断，没有在 Windows 上实测；原作者有 Windows 环境，可以直接复现。
- 没有做真实数据量下的备份耗时测试。

## 下一步

- R04～R09 未改：可由 C06（R04 任务表名）、C09（worker 入口调用 `validate_schema_current` 与向量空间门禁）或后续整理处理。
- 合并后关闭 issue #58；C02、C06、C13 的依赖即全部满足。
