# K08 复验交接：真实镜像构建与整套启动（Claude）

- 分支：`claude/laughing-ptolemy-4x1c7g`，基线 `main@7261514`（K08 已由 PR #270 合入）。
- 目的：补跑 K08 交接中「未运行」的项——真实镜像构建、`docker compose --profile app up`、容器内健康检查、nginx 配置语法检查。
- 本次**只做验证，不改任何实现文件**；只新增本文件并更新 `docs/tasks.md` K08 待决项。

## 环境

- Linux 云容器，Docker Engine 29.3.1（本次手动起 `dockerd`），Compose v5.1.1，Python 3.11 venv。
- 沙箱限制（与 K08 实现无关）：
  1. 出站 HTTPS 经 TLS 重签代理，构建容器内 pip/npm 不信任其 CA。处理：另建**仅本机**的派生基底 `sandbox-py:3.12`（`python:3.12-slim-bookworm` + CA 与 `PIP_CERT`）、`sandbox-node:24`（`node:24-bookworm-slim` + `NODE_EXTRA_CA_CERTS`），经 Dockerfile 已有的 `PYTHON_IMAGE` / `NODE_IMAGE` 构建参数传入；仓库 Dockerfile 未改。
  2. Docker Hub 对本机 IP 返回 `429 Too Many Requests`。处理：从 `mirror.gcr.io` 拉同名镜像（node、nginx-unprivileged、neo4j）并在本地打回原标签。

## 验证结果

| 检查 | 命令 / 做法 | 结果 |
| --- | --- | --- |
| 后端镜像构建 | `docker build -f src/backend/Dockerfile --build-arg PYTHON_IMAGE=sandbox-py:3.12 -t smartsketch-backend:local .` | 成功；`User=smartsketch`（uid 10001） |
| 前端镜像构建 | `docker build -f src/frontend/Dockerfile --build-arg NODE_IMAGE=sandbox-node:24 -t smartsketch-frontend:local .` | 成功（`npm ci` + `vite build`） |
| nginx 语法 | `docker run --rm --add-host api:127.0.0.1 smartsketch-frontend:local nginx -t` | `syntax is ok` / `test is successful` |
| 前端镜像不含密钥 | 镜像内 `env` 无 key/secret/password/token；静态资源 grep `LLM_API_KEY\|NEO4J_PASSWORD\|JWT_SECRET\|sk-` | 只命中 `task-…` 等误报，无密钥 |
| 整套启动 | `cp .env.example .env`（填 `AUTH_JWT_SECRET`）；`docker compose --profile app up -d --no-build` | migrate `Exited (0)`（SQLite 001–011、Neo4j 12 条）；api/worker/web/neo4j 均 `healthy` |
| 未填 `AUTH_JWT_SECRET` | 同上但保留 `.env.example` 的空值 | api 拒绝启动（`SettingsError: AUTH_JWT_SECRET … at least 32 bytes`），web 因依赖不健康不启动——符合启动门禁与 `docs/integrations.md` 说明 |
| web 静态 / SPA 回落 | `curl :8080/`、`curl :8080/courses/abc/graph` | 均 200 `text/html` |
| 反代健康检查 | `curl :8080/health` | 200 `{"status":"ok","version":"0.1.0"}` |
| 反代 API 鉴权 | `curl :8080/api/v1/courses`（无令牌） | 401 `UNAUTHENTICATED` |
| 登录→建课→上传 | 挂载 `scripts/` 运行 `seed-demo-accounts.py`；`POST /auth/login`、`POST /courses`、`POST /courses/{cid}/documents`（Markdown） | 全部成功，返回 `task_id` |
| worker 领取任务 | 轮询 `GET /tasks/{tid}` | worker 领取并执行解析→分块→抽取；在 `LLM_MODE=fake` 下以 `EXTRACTION_INCOMPLETE` 失败（见「发现」2） |
| SSE 经 nginx | `POST /tasks/{tid}/event-ticket` 后 `curl -N /tasks/{tid}/events?ticket=…` | 200 `text/event-stream`，无缓冲收到 `event: error` 终态事件 |
| worker 进程数 | `WORKER_PROCESSES=3` 重建 worker，容器内列 `/proc` | 监督进程 PID 1 + 3 个子进程，非 root |
| 子进程崩溃 | 对一个子进程 `SIGKILL` | 日志 `worker child worker-0 exited with -9`，其余子进程停止，容器由 `restart: unless-stopped` 拉起（RestartCount 0→1），重新 healthy |
| 优雅停止 | `docker compose stop worker`（空闲） | 0.6 s 退出，exit 0，三个子进程均记录 `stopped after N rounds` |
| 数据卷持久化 | `docker compose --profile app down`（不带 `-v`）后再 `up` | 课程仍在，账号可登录；migrate 输出 `Applied migrations: none`（幂等） |
| K08 测试 | `python -m pytest tests/integration/test_k08.py -q` | 21 passed，1 failed：`test_images_build` 因 Docker Hub `429` 无法解析 `python:3.12-slim-bookworm` 元数据（环境限流，不是实现缺陷；等价的手动构建见上） |
| 相关回归 | `SMARTSKETCH_SKIP_DOCKER=1 python -m pytest tests/backend/test_b06.py tests/tooling tests/integration/test_f01.py tests/integration/test_k08.py -q` | 117 passed，4 skipped（与原交接一致） |
| 门禁 | `./scripts/verify.sh`（PATH 含 `datamodel-code-generator==0.26.3`、`openapi-typescript@7.4.4`） | exit 0 |

## 发现（未修复，留给后续任务决定）

1. **镜像不含 `scripts/`**：`seed-demo-accounts.py`、`manage-accounts.py` 等账号管理脚本不在后端镜像里，容器部署下没有开箱的方式建账号。本次用 `docker compose --profile app run --rm --no-deps -v "$PWD/scripts:/app/scripts:ro" -e SEED_DEMO_PASSWORD=… api python /app/scripts/seed-demo-accounts.py` 绕过（脚本按 `parents[1]/src/backend` 找代码，挂到 `/app/scripts` 可用）。建议 K12 运行手册写入该命令，或另开任务把脚本打进镜像。
2. **`LLM_MODE=fake` 下的整套服务跑不出图谱**：fake 客户端未脚本化时 JSON 模式返回 `{"fake","purpose","digest"}`，不是合法抽取结果，任务必然以 `EXTRACTION_INCOMPLETE` 结束。这与容器无关（同一代码路径），但意味着**容器演示要真实模型**（`LLM_MODE=live`），或另建 fake 演示响应器。建议 K12 标注。
3. `test_images_build` 依赖 Docker Hub 直连；在有限流或 TLS 代理的环境下会失败。未改测试（非缺陷），仅记录。

## 未运行

- `LLM_MODE=live` 的端到端抽取、发布与问答（无模型密钥，也不在 K08 范围）。
- 非空闲时的优雅停止（在途任务超过 90 s 宽限期被强杀后按租约接管，ADR-039 第 2 条），本次未构造长任务。
- macOS/Windows Docker Desktop。

## 接口 / 数据变更

无。

## 清理

`docker compose --profile app down -v` 已删除测试容器、网络和 `app-data` 卷；临时 `.env` 已删除。沙箱派生基底镜像只在本机、不入库。

## 下一步

- K08 原「真实构建未跑」待决项可关闭；发现 1、2 交给 K12（运行手册/验收）或新任务。
