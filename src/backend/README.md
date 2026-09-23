# Backend

B05 已建立 FastAPI 应用工厂与匿名 `GET /health`。B06 在应用创建时从环境变量加载类型化设置并拒绝非法值；默认 fake 模式无需真实模型密钥。当前健康检查仅确认 API 进程可响应；数据库连接与业务路由由后续任务实现。

从仓库根目录创建虚拟环境并安装测试依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e './src/backend[test]'
.\.venv\Scripts\python.exe -m pytest tests/backend/test_b05.py -q
.\.venv\Scripts\python.exe -m pytest tests/backend/test_b06.py -q
```

本地启动：

```powershell
Set-Location src/backend
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

健康检查响应为 `{"status":"ok","version":"0.1.0"}`。`app/` 后续模块须遵守根目录 `AGENTS.md`。

设置只读取进程环境变量，不自动加载 `.env` 文件；变量名、无敏感样例和取值约束见根目录 `.env.example` 与 `docs/integrations.md`。无效设置在应用导入/创建时抛出只含变量名的 `SettingsError`，密钥字段在设置对象的 `repr` 中打码。
