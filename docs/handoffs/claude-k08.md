# K08 交接：前后端与 worker 容器配置（Claude）

- 分支：`claude/project-thread-cd4etm`，基线 `main@95d5c9a`。
- 决定：ADR-039（待 ArvinHan 审阅）。

## 交付物

- `src/backend/Dockerfile`：API 与 worker 共用；按仓库布局放迁移、生成 DTO、提示词；只装运行依赖；非 root；`GET /health` 健康检查。
- `src/frontend/Dockerfile` + `src/frontend/nginx.conf`：Vite 构建 + 非 root nginx（8080），`/api/` 反代到 `api:8000`，SSE 关闭缓冲，SPA 回落。
- `docker-compose.yml`：`app` profile 下新增 `migrate`、`api`、`worker`、`web` 与 `app-data` 卷；neo4j 不变。
- `.dockerignore`：排除 `.env*`、`.git`、运行数据、依赖目录。
- **范围扩展** `app/workers/runner.py` + `__main__.py`：常驻 worker 入口（启动门禁、监督 `WORKER_PROCESSES` 个子进程、心跳健康检查、SIGTERM 停止领取、`maintenance` 挂点）。
- `tests/integration/test_k08.py`：compose/Dockerfile 静态检查、按 Dockerfile `COPY` 重放镜像布局并启动 API 查 `/health`、worker 入口行为、真实构建（需 Docker）。

## 验证（本机，Linux，Python 3.11 venv）

| 命令 | 结果 |
| --- | --- |
| `python -m pytest tests/integration/test_k08.py -q` | 21 passed, 1 skipped（`test_images_build`：无 Docker 守护进程） |
| `python -m pytest tests/backend -q` | 2962 passed |
| `python -m pytest tests/backend/test_b06.py tests/tooling tests/integration/test_f01.py tests/integration/test_k08.py -q` | 117 passed, 4 skipped |
| `./scripts/verify.sh`（PATH 含 `datamodel-code-generator==0.26.3` 与 `openapi-typescript@7.4.4`） | exit 0 |
| `docker compose --profile app config`（临时 `.env`，随后删除） | exit 0；web 无 environment/env_file |

- 先失败后修复：初版把实现放在 `__main__.py`，`python -m app.workers` 实跑时子进程报 `Can't get attribute '_child_main' on <module '__main__'>`；改为 `runner.py` 后由 `test_module_entry_spawns_real_children` 覆盖。

## 未运行

- 镜像真实构建、`docker compose --profile app up`、容器内健康检查、nginx 配置语法检查：本环境只有 docker CLI，没有守护进程。

## 接口/数据变更

- 无 API、契约或数据模型变更。新增 compose 变量 `WEB_PUBLISH_PORT`、镜像内变量 `WORKER_HEARTBEAT_FILE`（登记于 `docs/integrations.md`「应用容器（K08）」）。

## 风险与下一步

- worker 优雅停止不主动释放在途任务，被强杀后等一个租约接管（ADR-039 第 2 条）；如需 §8.3 的主动释放，须在各阶段加协作式取消点。
- G05 清扫接入 `run_loop(maintenance=...)` 由后续任务决定。
- K10（备份恢复演练）依赖本任务，可基于 `app-data` 卷设计。

## 回滚

见 ADR-039「回滚」。
