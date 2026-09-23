# Codex 交接：B06 后端设置加载与启动验证

- 任务与状态：B06 DONE；父任务 M0-03 的 B05+B06 均已完成。
- 分支与基线：`codex/b06-settings`，base `e8ce796`；本地提交，不推送。交接随分支提交，提交范围以该分支 HEAD 相对基线为准。
- 功能文件：`src/backend/app/config.py`、`src/backend/app/main.py`、`tests/backend/test_b06.py`；文档和配置：`docs/architecture.md`、`docs/integrations.md`、`.env.example`、`src/backend/README.md`、`docs/tasks.md`。

## 交付与决定

- `load_settings()` 只从进程环境变量加载 40 个类型化设置；不读取 `.env` 文件、不连接数据库、模型或网络。应用工厂在构造 FastAPI 前调用它，并把结果放入 `app.state.settings`。
- 校验枚举、端口与数值范围、URL、主备模型的条件必填、生产环境 fake 禁令和首字超时小于总超时。非法值以 `SettingsError` 报出变量名；密钥用 `SecretStr`，异常与设置对象 `repr` 不显示明文。
- 补登 ADR-012 已规定但 A07 清单中缺失的 `PUBLISH_LEASE_SECONDS`、`COURSE_LOCK_WAIT_SECONDS`，未变更其默认值或语义。

## 实际验证

| 命令或方法 | 结果 |
| --- | --- |
| 用仓库现有 `.venv`、设置 `PYTHONPATH` 为本工作树 `src/backend`，执行 `python -B -m pytest -p no:cacheprovider tests/backend/test_b06.py -q` | 35 passed，exit 0 |
| 同条件执行 `tests/backend/test_b05.py -q` | 3 passed，exit 0；2 条上游弃用警告 |
| 同条件执行 B05+B06 两文件 | 38 passed，exit 0；2 条上游弃用警告 |
| Git Bash 中临时提供 `python3` 函数后运行 `./scripts/verify.sh` | `block-dangerous hook tests passed.`、`Scaffold verification passed.`，exit 0 |
| `git diff --check` | exit 0 |

测试覆盖默认 fake 无真实密钥、完整 live 配置、`.env.example` 变量名集合、非法端口/预算/维度/租约、条件必填、非法 URL、生产 fake 禁令、密钥脱敏及无效配置使模块导入失败。

## 接口、数据与风险

- 无新增 REST/SSE 接口、数据库迁移或外部服务调用。新增的两个环境变量及默认值已同步到文档与 `.env.example`。
- D-02a～f 的真实供应商与预算取值仍待签收；本任务仅实现已确认的形状和规则。向量空间与持久记录/Neo4j 索引的一致性需由后续存储接入任务校验。
- 后续 worker 入口也须调用 `load_settings()`，不能只依赖 API 工厂完成启动校验。

## 下一步与回滚

- 首个后续动作：C05 可消费已验证的存储设置并实现文件落盘边界；C01 可消费 SQLite/worker 配置并建立迁移运行器。
- 回滚只撤销 B06 本地提交；没有数据库或远端状态需恢复。

## 审查修复（2026-09-23）

本节覆盖上方关于「启动不访问数据库」「没有数据库变更」和「运行时空间留待后续」的原交付说明。

- 输入：`ca353b1` 的三项审查问题——PUB-32 缺启动门禁、`WEB_ORIGIN` 接受空值/无效主机、`API_HOST`/`API_PORT` 未用于监听。
- 交付：`src/backend/app/repositories/embedding_space.py` 用 `BEGIN IMMEDIATE` 创建并读写 SQLite 单行向量空间；`src/backend/app/services/startup.py` 提供 API/后续 worker 共用的比对函数；API lifespan 在对外服务前调用。`config.py` 拒绝空或含空格的 URL、非 origin 的 `WEB_ORIGIN`、内存 SQLite；`python -m app` 读取监听主机和端口。同步架构、集成、发布规格、示例环境变量、README 与任务板。
- 复现与验证：新增负例先运行得 5 FAIL、12 PASS；修复后设置 `PYTHONPATH` 为本工作树 `src/backend`，执行 `.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider tests/backend/test_b06.py tests/backend/test_b05.py -q`，47 PASS、2 条上游弃用警告、exit 0；Git Bash 临时映射 `python3` 后 `./scripts/verify.sh` exit 0；`git diff --check` exit 0。
- 数据/回滚：首次启动会在 `SQLITE_URL` 指向的文件建 `embedding_space_state` 并写入空间；再次启动不一致时只读旧行并拒绝服务。C01 的 `001_base.sql` 须保留此表并由迁移接管。若需撤销数据模型变更，停 API/worker，用变更前 SQLite 备份恢复后重启；只回退代码时可保留表与记录，不得删除记录绕过空间门禁。
- 未完成：C09 worker 入口尚不存在，创建时须调用 `validate_embedding_space()`；离线重新向量化命令尚未实现，A10 须登记承接任务。在命令与 E07/F03 实现前，改变已有空间只能被拒绝，不能在线迁移。API/worker 必须指向同一 SQLite 文件；示例相对路径按进程工作目录解析。
- 下一位 Agent：C01 先把单行状态表纳入 `001_base.sql` / 迁移；C09 复用共享门禁；A10 为离线重新向量化命令编号并明确实际运行命令。
