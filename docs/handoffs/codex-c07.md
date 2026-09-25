# C07 交接：课程资料上传与列表 API

- 状态：DONE（2026-09-26）。
- 交付：`src/backend/app/api/materials.py`、`src/backend/app/services/materials.py`、`src/backend/app/repositories/materials.py`、`src/backend/app/main.py`、`src/backend/pyproject.toml`、`tests/backend/test_c07.py`；同步更新 `docs/architecture.md`、`docs/integrations.md`、`docs/tasks.md`。
- 关键决定：沿用 `src/contracts/api.v1.yaml` 现有 GET/POST 路径与 `Document`/`UploadAccepted` DTO，不新增 REST 字段。POST 先用 C03 课程教师依赖授权，再解析 multipart；解析期间按实际接收字节限制请求体（文件上限外留 16 KiB 表单开销），C05 再精确检查文件大小和格式。同步请求只落盘并用 C06 原子创建 `queued` 任务；长时处理留给 worker。课程列表由仓储按课程 ID 查询。内部重放时删除本次多余文件，建任务失败时补偿删除本次文件。
- 依赖变化：新增运行依赖 `python-multipart==0.0.32`（Apache-2.0），已登记 `docs/integrations.md`；无数据库迁移、环境变量或 REST 契约变化。
- 验证：`tests/backend/test_c07.py` 先因路由缺失 5 failed，接线后 5 passed；审查发现鉴权前 multipart 解析问题后，新增回归先 2 failed，修复后 C07 9 passed。最终 `.venv/Scripts/python.exe -m pytest tests/backend -q --tb=short` 为 1059 passed、2 条既有 Starlette/anyio 弃用警告；`./scripts/verify.sh` 经 Git Bash + `.venv` Python/生成器路径与 UTF-8 环境运行 exit 0（`PASS contracts gate`、`Scaffold verification passed.`）；`pip check` 无损坏依赖；`git diff --check` exit 0。
- 风险与下一步：Starlette multipart 会为单个合法上限内的文件临时占用磁盘；部署时需给临时目录与 `STORAGE_DIR` 留空间。若数据库失败且补偿删除也失败，会有孤儿文件并返回 `STORAGE_UNAVAILABLE`，需运维清理。现有 v1 契约没有再处理/旧修订下线端点，需由后续产品/契约任务决定；C09/C10 应明确任务推进如何同步 `materials.parse_status`。当前每次 HTTP 上传生成独立幂等键；若要支持客户端安全重试，先在契约中定义请求键。
- 回滚：未改迁移或数据模型。代码回滚只撤销上述 C07 自有文件/改动并移除运行依赖声明；已上传的资料与任务不能通过回滚代码删除，须按运营流程单独处理，不覆盖其他工作区改动。
