# Claude 交接：DEMO-03 dev-up.sh 启动诊断

- 状态：DONE，待 PR 审查/合并。分支 `claude/project-thread-diyack`，基线 `main@2a67189`。
- review_status: ready_for_review

## 背景

用户在 macOS（Docker Desktop，项目解压在 `~/Desktop/SmartSketch-main`）运行 `scripts/start-demo.sh`，只看到「Neo4j 健康检查失败」。逐步排查得到两个问题：

1. 一次启动时容器停在 `created`，Docker 报 `Bind for 127.0.0.1:7474 failed: port is already allocated`。
2. 前台启动时 Neo4j 以退出码 3 反复重启，日志在 `Logging config in use` 后直接 `Neo4j Server shutdown initiated by request`，没有 ERROR。

查 Neo4j 5.26.31 的 `NeoBootstrapper.start`（javap 反汇编）：退出码 3 有两条路径。一是内存超过物理内存，会打印 `ERROR Invalid memory configuration`；二是 log4j 初始化 `user-logs.xml`（写 `/logs/neo4j.log`）出错，`SystemLogger.errorsEncounteredDuringSetup()` 返回 true，**不打印任何 ERROR**。用户看到的是第二种，所以推测挂载的 `neo4j/logs` 在「桌面」目录下读写异常；未在 Mac 上复现确认。

## 改动

- `scripts/_dev-common.sh`：`neo4j_health` 换成 `neo4j_state`（一行输出健康、容器状态、重启次数），找不到运行中容器时用 `compose ps -aq` 找已创建/已退出的；新增 `port_listening`（bash `/dev/tcp`）和只读的 `neo4j_diagnose`（容器状态、最近 40 行日志、按 Docker 报错/退出码/日志内容给提示）。
- `scripts/dev-up.sh`：
  - 容器不存在或停在 created/exited/dead 时，先查 HTTP/Bolt 端口是否被占，被占则不启动并给出 `lsof` 命令。
  - 等待循环：created/exited/dead、`restarting` 或重启次数比启动时多 → 立即诊断并失败。
  - 每 15 秒（或 unhealthy 时）自己跑一次 `RETURN 1`；认证被拒立即失败，说明口令只在 `neo4j/data` 首次初始化时生效。
  - `unhealthy` 不再立即失败：compose 健康检查 40 + 12×10 = 160 秒就判 unhealthy，早于脚本自己的 180 秒，`NEO4J_WAIT_SECONDS` 调大也无效。现在等到截止时间，截止时打印诊断和最后一次连接输出。
- `.gitignore`：忽略 `docker-compose.override.yml`（本机覆盖）。
- 文档：`docs/runbook.md` 第 8 节新增四行故障与「macOS：改用 Docker 卷」；`docs/integrations.md` 更新 dev-up 行为说明；`docs/tasks.md` 新增 DEMO-03。
- 测试：新增 `tests/tooling/test_dev_up_diagnostics.py`（8 个，假 docker）；`tests/integration/test_f01.py` 的 unhealthy 用例改为 `NEO4J_WAIT_SECONDS=0`，断言从「没有任何 exec」改为「没有跑 APOC 检查」（等待中会做连接探测）。

接口、数据模型、`docker-compose.yml` 均未改动。

## 验证

- `python3 -m pytest -q tests/tooling/test_dev_up_diagnostics.py`：改实现前 7 failed（当时 7 个用例），改后 8 passed。
- `python3 -m pytest -q tests/tooling/test_dev_up_diagnostics.py tests/tooling/test_k07.py tests/integration/test_f01.py`：全部通过（含 F01 真实容器用例，本机已起 dockerd）。
- 真实 Docker 29.6.2 + `neo4j:5.26-community`（5.26.31），独立 compose 项目与端口：
  - `NEO4J_HEAP_MAX=64G`：约 7 秒报「反复重启」，日志含 `Invalid memory configuration`，提示「内存不够」。
  - 本机先占住 HTTP 端口：未启动容器，报端口被占并给出 `lsof`。
  - 正常 `.env`：约 25 秒就绪，APOC 检查通过，行为同前。
  - 先用一个口令初始化库，再改 `.env` 口令重建容器：约 19 秒报口令不一致（改前要等约 160 秒后只报「健康检查失败」）。
  - `docker-compose.override.yml` 改用 Docker 卷：容器 healthy。
- `./scripts/verify.sh`（basic）：exit 0（按 `src/contracts/toolchain.txt` 装好契约工具链后；`git diff --check` 通过）。

## 风险与下一步

- 退出码 3 的根因是推测，需要用户在 Mac 上用 override 文件验证；若 override 后仍失败，看 `docker compose logs neo4j`。
- 等待中每 15 秒执行一次 `cypher-shell`，首次启动时多几次连接失败，不影响结果。
- 回滚：还原上述两个脚本即可，无数据变更。
