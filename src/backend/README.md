# Backend

B05 已建立 FastAPI 应用工厂与匿名 `GET /health`。当前健康检查仅确认 API 进程可响应；配置加载、数据库连接与业务路由由后续任务实现。

从仓库根目录创建虚拟环境并安装测试依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e './src/backend[test]'
.\.venv\Scripts\python.exe -m pytest tests/backend/test_b05.py -q
```

本地启动：

```powershell
Set-Location src/backend
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

健康检查响应为 `{"status":"ok","version":"0.1.0"}`。`app/` 后续模块须遵守根目录 `AGENTS.md`。
