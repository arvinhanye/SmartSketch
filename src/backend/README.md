# Backend

B05 已建立 FastAPI 应用工厂与匿名 `GET /health`。B06 在应用创建时从环境变量加载类型化设置并拒绝非法值；默认 fake 模式无需真实模型密钥。当前健康检查仅确认 API 进程可响应；数据库连接与业务路由由后续任务实现。

从仓库根目录创建虚拟环境并安装测试依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e './src/backend[test]'
.\.venv\Scripts\python.exe -m pytest tests/backend/test_b05.py -q
.\.venv\Scripts\python.exe -m pytest tests/backend/test_b06.py -q
```

从仓库根目录启动；相对 `SQLITE_URL` 路径以这个目录为基准，API 和后续 worker 必须使用同一个 SQLite 文件：

```powershell
$env:PYTHONPATH = (Resolve-Path ./src/backend).Path
.\.venv\Scripts\python.exe -m app
```

健康检查响应为 `{"status":"ok","version":"0.1.0"}`。`app/` 后续模块须遵守根目录 `AGENTS.md`。

设置只读取进程环境变量，不自动加载 `.env` 文件；变量名、无敏感样例和取值约束见根目录 `.env.example` 与 `docs/integrations.md`。`python -m app` 使用 `API_HOST` 和 `API_PORT`；直接使用 Uvicorn CLI 时仍须自行传入监听参数。无效环境设置在应用导入/创建时抛出只含变量名的 `SettingsError`，密钥字段在设置对象的 `repr` 中打码。启动阶段检查 SQLite 中的向量空间；空间不一致时拒绝服务，保留原记录，待离线重新向量化。worker 入口建立时须调用同一检查函数。
