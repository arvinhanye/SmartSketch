# Codex 交接：K07 开发环境启停脚本

- 日期：2026-09-25
- 分支 / base：`codex/k07-dev-scripts` / `a7a0be05c82551cb43b0ec7db80e41d7bcb478b8`
- 范围：`scripts/_dev-common.sh`、`scripts/dev-up.sh`、新增 `scripts/dev-down.sh`、`tests/tooling/test_k07.py`、`docs/integrations.md`；未改 Compose、仓库数据目录或共享任务台账。

## 行为与接口

- `./scripts/dev-up.sh` 先检查 `.env`，缺失时指出 `cp .env.example .env`；不再将 `.env` 当 shell 脚本执行。只按字面量读取 `STORAGE_DIR`、`NEO4J_WAIT_SECONDS` 和提示用端口；Compose 仍自行解析 `.env` 凭据。既有 `.env` 不会创建、覆盖或写回。
- `./scripts/dev-down.sh` 默认运行 `compose stop neo4j`，保留容器、卷及 `neo4j/data`、`neo4j/logs` 绑定目录。`--destroy` 仅在交互终端输入精确的 `DELETE NEO4J DATA` 后运行 `compose down -v`；拒绝、不精确或非交互输入均不调用删卷命令。未知选项失败且不停止服务。
- **范围决定**：F01 使用绑定挂载，`compose down -v` 只删 Compose 管理的卷，**不会删除** `neo4j/data` 与 `neo4j/logs`。脚本在提示和结果中明确告知这一点；不自动运行 `rm -rf`。若未来需要清除绑定目录，应单独设计备份/路径防护流程。

## 验证

- TDD 初次红灯：`PATH=/opt/anaconda3/bin:$PATH python3 -m pytest tests/tooling/test_k07.py -q` → 5 failed / 6 passed（缺 `dev-down.sh`、`.env` 被 source）。之后新增两项回归各先看到 1 failed（缺 env 的诊断顺序、非法等待值启动前拒绝），再实现。
- 最终 K07：`PATH=/opt/anaconda3/bin:$PATH python3 -m pytest tests/tooling/test_k07.py -q -p no:cacheprovider` → **13 passed**。所有容器操作由临时目录内的假 `docker` 记录；交互确认用 PTY；确认销毁后绑定的 Neo4j data/logs 与 `storage/` 临时探针仍在；未调用真实卷删除。
- F01 假 Docker 回归：`SMARTSKETCH_SKIP_DOCKER=1 /opt/anaconda3/bin/python3 -m pytest tests/integration/test_f01.py -q -p no:cacheprovider` → **9 passed, 3 skipped**。
- `PATH=/opt/anaconda3/bin:$PATH ./scripts/verify.sh` → **Scaffold verification passed**（契约与钩子门禁）。
- `git diff --check` → 0。
- 全仓库 `pytest` 在本机运行时因运行环境缺少 `fastapi`、`pdfminer`、匹配版本的 `argon2` 等后端依赖而在收集期中止；不属于 K07 脚本变更。系统 Python 3.11 也没有 `pytest`；上面的聚焦命令使用 `/opt/anaconda3/bin` 的 pytest。

## 风险与回滚

- `--destroy` 不删除 F01 绑定数据；这是刻意保守的边界，不能把它当成数据库数据清空命令。
- `.env` 中与 Compose 有关的变量插值仍由 Compose 自行处理。脚本仅按字面量读取少数非敏感本地设置；如依赖高级 Compose 插值表达式设置 `STORAGE_DIR`，需检查创建目录是否符合预期。
- 回滚：还原本提交的三个脚本并删除新测试/交接文件；绑定数据目录和个人 `.env` 均无需迁移或改动。
- `docs/integrations.md` 已同步实际启停命令、确认词和绑定数据仍保留的范围。
