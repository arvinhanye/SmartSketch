# 交接：同步并审查 C01（PR #174，539210 / kongsc）

- `task_id`: REVIEW-C01
- `status`: 审查完成；9 项意见，均未修改，等 ArvinHan 决定由谁修、修哪些
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

## 未验证

- R01 的 CRLF 情形只按 git 行为推断，没有在 Windows 上实测；原作者有 Windows 环境，可以直接复现。
- 没有做真实数据量下的备份耗时测试。

## 下一步

- ArvinHan 决定修正范围与执行人（原作者 kongsc，或 Claude）。R01～R03 建议合并前处理。
- 合并后关闭 issue #58；C02、C06、C13 的依赖即全部满足。
