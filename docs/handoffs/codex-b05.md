# Codex 交接：B05 后端应用工厂与健康检查

- 任务与状态：B05 DONE；父任务 M0-03 仍为 IN PROGRESS（B06 待做）。
- 分支与基线：`codex/b05-fastapi-health`，base `50a15c9`；本任务在该分支本地提交。
- 范围：`src/backend/pyproject.toml`、`src/backend/app/main.py`、`src/backend/app/api/health.py`、`tests/backend/test_b05.py`。为保证包结构与可复现启动，增加 `app/api/__init__.py` 并更新 `src/backend/README.md`；同步更新任务板与架构说明。

## 交付与决定

- `create_app()` 和模块级 `app` 可供 Uvicorn 加载；构造应用不读取密钥，也不连接外部服务。
- 匿名 `GET /health` 返回 HTTP 200、`status: "ok"` 和非空 `version`；`/api/v1/health` 未注册，错误方法返回 405。版本与 FastAPI 应用元数据使用同一值。
- 响应形状沿用 `740adb` 分支既有的 `/health` OpenAPI 定义及 ADR-009 的路径例外。main 尚待 A10 导入契约真源，因此 `HealthResponse` 是过渡模型；A10/B14 导入生成 DTO 后应替换。未引入新 ADR 或第二套契约决策。
- 只表示 API 进程可响应，不检查 SQLite、Neo4j 或模型服务的就绪状态。B06 负责后续类型化设置与启动校验。

## 实际验证

| 命令或方法 | 结果 |
| --- | --- |
| `python -m venv .venv`；`.\.venv\Scripts\python.exe -m pip install -e './src/backend[test]'` | 成功，依赖装在被忽略的仓库内 `.venv` |
| `.\.venv\Scripts\python.exe -m pytest tests/backend/test_b05.py -q` | 3 passed；2 条上游 deprecation warning |
| 从 `src/backend` 运行 `..\..\.venv\Scripts\python.exe -m pytest -q` | 3 passed；证明 `pyproject.toml` 的测试发现配置可用 |
| Git Bash 中导出 `python3` 函数（本机只提供 `python`）后执行 `./scripts/verify.sh` | `block-dangerous hook tests passed.`、`Scaffold verification passed.`，exit 0 |
| `.\.venv\Scripts\python.exe -m pip check`、`git diff --check` | 均 exit 0 |
| `uvicorn app.main:app --host 127.0.0.1 --port 8123`，随后 HTTP GET | 服务成功启动；`200 application/json`，正文 `{"status":"ok","version":"0.1.0"}` |

本机 Python 为 3.13.7。直接依赖版本：FastAPI 0.141.1、Uvicorn 0.53.0；测试依赖：HTTPX 0.28.1、pytest 9.1.1。两条 warning 来自 Starlette/TestClient 与 AnyIO 的弃用提示，本任务测试没有失败。

## 接口、数据与风险

- 新增接口：`GET /health`，匿名可访问，HTTP 200 JSON `{status: "ok", version: string}`。没有数据库迁移或数据写入；没有新增密钥或运行时环境变量。
- 完整 `api.v1.yaml` 尚未进入 main，健康响应模型在契约生成物落地前须保持与上游定义一致。B06 未完成，不能据此声称 M0-03 全部验收。
- 本地 Git Bash 缺少 `python3` 可执行名；本次仅在验证命令的 shell 内提供临时等价函数，没有改仓库脚本。

## 下一步与回滚

- B06 实现环境变量加载与启动校验；A10/B14 导入契约真源并替换临时健康响应模型；后续 CI 扩展到真实后端测试时复用 `tests/backend/test_b05.py`。
- 回滚仅需撤销本任务提交；无数据库、密钥或外部服务状态需要恢复。
