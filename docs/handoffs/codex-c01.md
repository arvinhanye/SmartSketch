# C01 SQLite 连接与迁移运行器交接

- 任务：C01，分支 `codex/c01-sqlite`，基线 `main@9d2437e`；Issue [#58](https://github.com/arvinhanye/SmartSketch/issues/58)。
- 状态：本地实现与代码审查修复已完成；待 PR 合并。未修改当前主工作树的未提交内容。

## 交付与关键决定

- `src/backend/app/repositories/sqlite.py`：从环境配置中的 `SQLITE_URL` 解析文件路径，短生命周期连接启用 WAL、外键与 5000 ms 忙等待；迁移按三位版本号升序执行，`schema_migrations` 保存文件名、SHA-256 摘要和应用时间。已应用文件变更、历史缺口与活跃租约/课程锁均拒绝迁移。
- `src/backend/migrations/001_base.sql`：以 `CREATE TABLE IF NOT EXISTS` 接管 B06 的 `embedding_space_state`，不覆盖既有模型、维度与 fake 标志。业务表仍归 C02/C06 等后续迁移。
- 每个待执行版本先 `VACUUM INTO` 到数据库旁 `backups/`，验证副本 `integrity_check=ok`；迁移 SQL 与版本记录同一 `BEGIN IMMEDIATE` 事务，异常时回滚。迁移 SQL 中的事务控制语句由 SQLite authorizer 拒绝，避免脚本提前提交。API 与 worker 必须先停机，租约检查只是额外保护。
- `tests/backend/test_c01.py` 覆盖连接 PRAGMA、B06 记录保留、重复迁移、失败回滚及提前提交拒绝、有效和到期秒任务租约/课程锁拒绝、备份与 WAL 附属文件恢复、摘要漂移及迁移文件注释。
- 同步 `docs/architecture.md`、`src/backend/README.md` 的接口、数据模型、操作与恢复说明，`docs/tasks.md` 记录认领和验收。

## 验证

- B05/B06 基线：58 passed。
- C01 专项：先观察缺模块导致收集失败；边界回归先复现 3 个失败；修复后 11 passed。
- `python -m pytest tests/backend -q`：69 passed，2 条上游弃用警告。
- `python -m app.repositories.sqlite` 指向临时库：首次 `Applied migrations: 001`；第二次 `none`；版本表记录 `001`。
- `./scripts/verify.sh`：Git Bash 下以临时命令入口映射本机 Python/生成器执行，exit 0；22 项契约负例、B08/B09 各 5 项通过，生成物与真源一致。
- `git diff --check`：exit 0。

## 接口、数据与后续

- 无 REST/SSE 契约或环境变量变更。新增 SQLite 内部表 `schema_migrations`，接管已存在的 `embedding_space_state`；连接 API 为 `connect(sqlite_url)` 上下文管理器，迁移 API 为 `migrate(sqlite_url, migrations_dir=None)`，命令入口为 `python -m app.repositories.sqlite`。
- C02/C06 等后续迁移须沿用三位版本命名、迁移器提供的单事务、有效租约检查和备份验证；写事务由调用方显式开启。C09 worker 入口仍需复用 B06 的向量空间门禁。C09 的过期租约接管与 `attempt + 1` 属于 worker 行为，C01 的文件恢复演练不验证该行为。
- 风险：迁移器无法仅凭 SQLite 判断操作系统中 API/worker 进程是否已停止；部署者须先停机。恢复前应保留失败库及 `-wal`/`-shm`，按 README 复制正确版本的备份并验证完整性。
- 回滚：停 API/worker，保留原库及 WAL 附属文件，用对应 `*-before-<版本>.sqlite` 备份替换数据库文件后验证并重启；不要删除 `embedding_space_state` 来绕过校验。具体 PowerShell 步骤见后端 README。
