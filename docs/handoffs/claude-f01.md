# Claude 交接：F01 复用本地 Neo4j 环境并验证

- 日期：2026-09-25
- 分支 / base：`claude/f01-neo4j-env` / `origin/main@a80519c`
- 认领：issue #93
- 环境：ArvinHan 本机 Docker Desktop 29.8.0（linux/amd64 引擎），Docker Compose v5.5.1。Docker Desktop 刚装好时，现有 shell 的 `PATH` 里没有 `~/.docker/bin`，本次命令都显式加了这个路径。

## 来源与审查

第一个提交 `7f76237` 原样导入 740adb `978671e` 的 `docker-compose.yml`、`scripts/_dev-common.sh`、`dev-up.sh`、`check-apoc.sh`（M0-05，当时因 APOC 未实测而 BLOCKED），同时加入测试，便于逐行比对改动。

审查原脚本（验收第一条「先审原脚本」）的发现：

| # | 问题 | 严重度 | 取证 | 处理 |
| --- | --- | --- | --- | --- |
| 1 | `dev-up.sh` 用 `case *healthy*` 判断健康状态，`unhealthy` 也会匹配，容器不健康时会被报告为就绪 | P1 | 单独运行原 `case` 语句：`"Health":"unhealthy"` 被判为就绪 | 改为读取 `docker inspect` 的 `.State.Health.Status`，完整等于 `healthy` 才算就绪；`unhealthy`、容器不存在时立即失败 |
| 2 | `check-apoc.sh` 在宿主机执行 `docker compose exec … cypher-shell -p "$NEO4J_PASSWORD"`，口令在执行期间出现在进程列表里 | P2 | 假 docker 记录的调用里有 1 条含口令 | 改为在容器内从 `NEO4J_AUTH` 取出凭据，经 `cypher-shell` 认识的 `NEO4J_USERNAME`/`NEO4J_PASSWORD` 环境变量传入。健康检查同样处理，`$$` 防止宿主机插值 |
| 3 | 固定 `container_name: smartsketch-neo4j`，测试沙箱和其他 worktree 没法各起一个实例 | P3 | 测试断言失败 | 删除；容器名随 compose 项目名 |
| 4 | 健康轮询解析 `compose ps --format json` 的输出，依赖 JSON 字段排版 | P3 | 假 docker 下原脚本空等到超时 | 同第 1 条，改为 `ps -q` 加 `inspect` |
| 5 | 端口绑 `0.0.0.0`，局域网内能访问开发库 | P3 | 阅读 | 改为只绑 `127.0.0.1` |
| 6 | `dev-up.sh` 提示用 `dev-down.sh` 停止，但该脚本属于 K07，本任务不导入 | P3 | 阅读 | 改为提示 `docker compose stop neo4j` 或 `down`（两者都保留数据） |
| 7 | 注释说 APOC「首次启动需联网下载」 | 文档 | 实测镜像自带 `apoc-5.26.31-core.jar` | 更正注释 |

保留不改：`resolve_compose` 支持 docker compose、docker-compose、podman-compose 三种命令（新增了引擎名 `ENGINE`，供 `inspect` 使用）；`require_env_file` 仍然 source `.env`，它的行为交给 K07 审查。`NEO4J_DATABASE` 没有导入：社区版只有 `neo4j` 一个库，而且 B06 要求 `.env.example` 恰好覆盖全部设置，这一项等 F02 需要时再加进 `Settings`。

## 交付物

| 文件 | 说明 |
| --- | --- |
| `docker-compose.yml` | 5.26 LTS 社区版；APOC 已启用；只绑本机回环；数据用绑定挂载 `./neo4j/data`、`./neo4j/logs`；健康检查不在命令行传口令；不固定容器名 |
| `scripts/_dev-common.sh` | `resolve_compose`（新增 `ENGINE`）；`require_env_file`；新增 `neo4j_health` 与 `run_cypher` |
| `scripts/dev-up.sh` | 建目录 → `up -d` → 等健康（上限 `NEO4J_WAIT_SECONDS`，默认 180 秒）→ `check-apoc.sh`；可重复执行 |
| `scripts/check-apoc.sh` | 用 `run_cypher` 执行 `RETURN apoc.version()` |
| `tests/integration/test_f01.py` | 假 docker 层 9 项（任何机器都能跑）；真实 Docker 层 3 项（没有守护进程时自动跳过） |
| `.env.example` | 只加了 5 行容器变量注释（compose 缺省值），不影响 B06 |
| `docs/integrations.md` | 新增「本地依赖环境（F01）」一节；「计划集成」的 Neo4j 行注明已落地、备份策略未定 |
| `docs/tasks.md` | 新增「F01」一节 |

## 验证

| 命令 | 结果 |
| --- | --- |
| 原脚本 + 新测试，`SMARTSKETCH_SKIP_DOCKER=1` | 4 failed / 5 passed / 3 skipped（红灯） |
| 修复后，同上 | 9 passed / 3 skipped |
| `PATH=~/.docker/bin:$PATH pytest tests/integration/test_f01.py -q`（真实 Docker，镜像已拉取） | **12 passed**，1 分 35 秒；结束后残留容器 0 个 |
| 反向篡改（假 docker 层，逐项改坏后再恢复） | 健康判断退回子串匹配、不健康时不立即失败、口令放回宿主机命令行、恢复固定容器名、缺 `.env` 不报错：5 处各 1 failed |
| `pytest tests/backend -q` | 756 passed（`.env.example` 的注释行不影响 B06） |

真实容器用例在隔离沙箱里运行：临时目录、随机 compose 项目名、随机空闲端口、独立的数据目录，不碰仓库自己的 `neo4j/data`，结束时执行 `down -v`。覆盖以下内容：

- `dev-up.sh` 启动后等到健康，输出里有 APOC 版本 `5.26.x`，任何输出都不含口令；
- 写入一个探针节点，`docker compose down`（不删卷）后再次运行 `dev-up.sh`，探针节点仍在；
- 口令为空时 `docker compose config` 失败，报错指出 `NEO4J_PASSWORD`。

实测：镜像 Neo4j 5.26.31，自带 `apoc-5.26.31-core.jar`，启用时不联网。

## 接口 / 数据变更

没有应用代码、契约或数据库变更。新增的数据目录 `neo4j/data`、`neo4j/logs` 早已在 `.gitignore` 里。

## 风险与下一步

- **K07**：导入并审查 `dev-down.sh`（普通停止保留数据、删卷须确认），并复核 `require_env_file` 用 source 读 `.env` 的方式（口令里含 `$` 或空格时，shell 和 compose 的解析结果可能不一致）。
- **F02**：Neo4j 驱动从 `.env` 的 `NEO4J_URI`、`NEO4J_USER`、`NEO4J_PASSWORD` 连接；如需指定数据库名，在 `Settings` 里加 `NEO4J_DATABASE`，同时补 `.env.example`。
- **F03**：向量索引维度要等 D-02c 签收；5.26 社区版支持向量索引。
- 首次拉取镜像约 986 MB。CI 目前不跑 `tests/integration`；假 docker 那一层不需要 Docker，以后可以考虑纳入 CI。
- 备份策略未定（已记在「计划集成」）。

## 回滚

还原本分支的全部提交即可。本地已创建的 `neo4j/`、`storage/` 目录都被 git 忽略，是否删除由使用者自己决定（K07 的 `dev-down.sh --destroy` 会提供确认流程）。
