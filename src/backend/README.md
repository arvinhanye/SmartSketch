# Backend

B05 已建立 FastAPI 应用工厂与匿名 `GET /health`。B06 在应用创建时从环境变量加载类型化设置并拒绝非法值；默认 fake 模式无需真实模型密钥。当前健康检查仅确认 API 进程可响应；数据库连接与业务路由由后续任务实现。

从仓库根目录创建虚拟环境并安装测试依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e './src/backend[test]'
.\.venv\Scripts\python.exe -m pytest tests/backend/test_b05.py -q
.\.venv\Scripts\python.exe -m pytest tests/backend/test_b06.py -q
```

从仓库根目录启动；相对 `SQLITE_URL` 路径以这个目录为基准，API 和后续 worker 必须使用同一个 SQLite 文件。首次启动前先执行迁移（见下方「SQLite 迁移与恢复」），否则 API 会以「SQLite schema is not migrated」拒绝启动。

启动前还须设置 `AUTH_JWT_SECRET`（登录令牌的 HS256 签名密钥，至少 32 字节）。缺失或过短时 `python -m app` 与 `app.main:app` 非 0 退出，错误只含变量名，不回退默认密钥。下面每次随机生成，仅适合本机试用；需要令牌跨重启有效时，把固定值放在个人本地环境中，不要提交。更换密钥会使已签发的令牌全部失效：

```powershell
$env:PYTHONPATH = (Resolve-Path ./src/backend).Path
$env:AUTH_JWT_SECRET = .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
.\.venv\Scripts\python.exe -m app.repositories.sqlite
.\.venv\Scripts\python.exe -m app
```

健康检查响应为 `{"status":"ok","version":"0.1.0"}`。`app/` 后续模块须遵守根目录 `AGENTS.md`。

设置只读取进程环境变量，不自动加载 `.env` 文件；变量名、无敏感样例和取值约束见根目录 `.env.example` 与 `docs/integrations.md`。`python -m app` 使用 `API_HOST` 和 `API_PORT`；直接使用 Uvicorn CLI 时仍须自行传入监听参数。无效环境设置在应用导入/创建时抛出只含变量名的 `SettingsError`，密钥字段在设置对象的 `repr` 中打码。启动阶段检查 SQLite 中的向量空间；空间不一致时拒绝服务，保留原记录，待离线重新向量化（停 API 与 worker、备份 Neo4j 后运行 `python3 scripts/reembed.py --neo4j-backup-confirmed`，见 ADR-038）。worker 入口建立时须调用同一检查函数。

## Neo4j 图约束迁移（F03）

停止 API 与 worker，先按 K10 流程备份 Neo4j，再在与服务相同的 `NEO4J_URI`、`NEO4J_USER`、`NEO4J_PASSWORD` 环境下运行（命令不打印密码）：

```bash
PYTHONPATH=src/backend python3 -m app.repositories.graph_migrations
```

`001_constraints.cypher` 使用逐条 `IF NOT EXISTS`，重复运行不重建已有约束。若历史数据违反唯一性，迁移在对应语句失败并保留已完成的 DDL；停机修复冲突数据后重跑。回滚不是删除约束或图数据：恢复迁移前的 Neo4j 备份，并按 K10 核对 SQLite/Neo4j 时间点。向量空间索引由 `GraphVectorWriter.ensure_vector_indexes(space)` 分空间创建；切换前旧索引和属性保持不变。

## SQLite 迁移与恢复（C01）

API 启动时会检查迁移是否已是最新，有未执行的迁移即拒绝启动；因此首次启动或部署新增迁移前，**先停止 API 与 worker**，从仓库根目录运行；进程环境中的 `SQLITE_URL` 必须与两者使用的值一致（不设置时为 `sqlite:///./storage/smartsketch.sqlite3`）：

```powershell
$env:PYTHONPATH = (Resolve-Path ./src/backend).Path
.\.venv\Scripts\python.exe -m app.repositories.sqlite
```

新迁移的编号在合并时取「当前 main 最大编号 + 1」，不按计划表预分配（D-10）。迁移器按文件名中的三位版本号顺序执行 `src/backend/migrations/*.sql`，记录版本、文件名和 SHA-256 摘要。重复运行不会再应用已记录的迁移；改动已应用文件、发现旧版缺口或有效任务租约/课程锁时会拒绝执行。连接启用 WAL、外键和 5000 ms `busy_timeout`。C01 的 `001_base.sql` 接管 `embedding_space_state` 表，保留 B06 首次启动写入的空间记录，并创建以 `call_id` 为主键的 `model_calls`；课程、成员和任务表由后续迁移创建。

每项待执行迁移前，迁移器在数据库旁的 `backups/` 目录用 `VACUUM INTO` 生成 `*-before-<版本>.sqlite`，并对副本运行 `PRAGMA integrity_check` 后关闭校验连接；迁移 SQL 与版本记录在同一事务内。迁移失败时原库事务回滚，备份保留。恢复与备份立即移动演练已纳入 `tests/backend/test_c01.py`。

若需恢复，先停止 API 与 worker，选择对应版本迁移前生成且完整性检查通过的备份。下面以默认路径为例，先保留失败库及 WAL 附属文件，再复制备份；所有路径均指向同一数据目录：

```powershell
$db = (Resolve-Path ./storage/smartsketch.sqlite3).Path
$backup = (Resolve-Path ./storage/backups/<选定的备份文件>.sqlite).Path
$failed = Join-Path (Split-Path -Parent $db) ('failed-' + (Get-Date -Format 'yyyyMMddTHHmmss'))
New-Item -ItemType Directory -Path $failed | Out-Null
Move-Item -LiteralPath $db -Destination (Join-Path $failed (Split-Path -Leaf $db))
foreach ($suffix in @('-wal', '-shm')) {
    $sidecar = $db + $suffix
    if (Test-Path -LiteralPath $sidecar) {
        Move-Item -LiteralPath $sidecar -Destination (Join-Path $failed (Split-Path -Leaf $sidecar))
    }
}
Copy-Item -LiteralPath $backup -Destination $db
.\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect(r'$db'); assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'; c.close()"
```

确认恢复后的库版本和向量空间记录后再重启服务。只向前迁移，不执行 down 脚本，也不删除 `embedding_space_state` 来绕过空间校验。
