# 交接：审查 B05（PR #14）并同步 main

- `task_id`: REVIEW-B05
- `status`: 审查通过，无 P1/P2；待 ArvinHan 授权合入
- `审查目标`: `origin/codex/b05-fastapi-health-github` @ `e8ce796`（PR #14，kongsc）
- `同步`: 合入 `origin/main@dddafb3`，只有 `docs/tasks.md` 冲突（M0-02 行取 main、M0-03 行取 B05；文末保留 main 各节，B05 节接在最后）

## 已运行命令与结果（macOS，Python 3.13.5，依赖装在 scratchpad 虚拟环境）

| 命令/核对 | 结果 |
| --- | --- |
| `pip install -e './src/backend[test]'`、`pip check` | exit 0 |
| `python -m pytest tests/backend/test_b05.py -q`（仓库根目录） | 3 passed |
| `python -m pytest -q`（`src/backend` 内，验证 `testpaths`） | 3 passed |
| `uvicorn app.main:app` + curl | `GET /health` 200 `{"status":"ok","version":"0.1.0"}`；`GET /api/v1/health` 404；`POST /health` 405 |
| `./scripts/verify.sh`、`git diff --check` | exit 0 |
| 与契约核对 | `src/contracts/v1/generated/openapi.json` 的 `/health`：tag `auth`、`operationId` `getHealth`、`security: []`、内联 `{status: enum[ok], version: string}`，与实现一致。契约为内联 schema，没有生成模型可以消费，手写 `HealthResponse` 不违反 ADR-004 |

## 审查意见（均为 P3，不阻塞）

- **B05-R01**：按 README 做可编辑安装会生成 `src/backend/smartsketch_backend.egg-info/`，`.gitignore` 未忽略，容易被误提交。建议加 `*.egg-info/`。
- **B05-R02**：`src/backend/README.md` 只给了 PowerShell 命令；macOS/Linux 需要 `.venv/bin/python` 写法。
- **B05-R03**：CI 仍只跑 `scripts/verify.sh`，后端 pytest 不在门禁内；由 CI-02 一并处理。

## 下一步

- 授权后合入 PR #14，再合入 PR #21（B06 叠在 B05 之上，见 `claude-review-b06.md`）。
