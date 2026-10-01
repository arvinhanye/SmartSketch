# Windows 运行指南

项目自带的 `scripts/start-demo.sh` 是 **bash 脚本，且只在 Linux 实测过**（见 `docs/runbook.md` 开头
的平台说明）。本文件是 Windows 本地运行的实际做法，由一位在 Windows 11 + Docker Desktop 环境
上完整跑通的人写下，记录的是**实测结论**，不是推测。

## 一、双击启动（推荐）

双击仓库根目录的 **`start-smartsketch.bat`**。

它会依次完成：

1. 检查 Docker Desktop 是否在运行，**没运行就自动启动**；
2. 轮询等待 Docker 引擎就绪（冷启动一般 1–2 分钟，最多等 4 分钟）；
3. `docker compose up -d neo4j` 启动 Neo4j 容器；
4. 调用 `start-dev.ps1`，在**三个独立窗口**里启动 API、worker、前端；
5. 等前端响应后**自动打开浏览器** <http://127.0.0.1:5173>。

| 账号 | 口令 | 角色 |
| --- | --- | --- |
| `demo_teacher` | `smartsketch-demo` | 教师 |
| `demo_student` | `smartsketch-demo` | 学生 |
| `demo_student2` | `smartsketch-demo` | 学生 |

**停止**：关掉那三个服务窗口（API / worker / web）。Neo4j 用
`docker compose stop neo4j`，或直接退出 Docker Desktop。

### 为什么需要 `.bat` 包装

三个不能省的 Windows 细节：

- **双击 `.ps1` 默认是用记事本打开，不是执行**；
- 默认执行策略**禁止运行 `.ps1`**（`UnauthorizedAccess` / `PSSecurityException`）；
- **Docker Desktop 没启动时 Neo4j 不可达**，所有图谱请求会返回
  `503 STORAGE_UNAVAILABLE`，页面看起来像"坏了"，其实只是容器没起。

## 二、三个必须知道的 Windows 差异

这三条是实测踩出来的，**项目文档与 `scripts/start-demo.sh` 都没有覆盖**，缺任何一条都起不来。

### 1. worker 必须设置 `WORKER_HEARTBEAT_FILE`

`src/backend/app/workers/runner.py` 的心跳文件默认值是 **Unix 路径**：

```python
DEFAULT_HEARTBEAT_FILE = "/tmp/smartsketch-worker.heartbeat"
```

在 Windows 上它会被解析成 `\\tmp\smartsketch-worker.heartbeat`（当前盘符根目录），监督进程
`beat.touch()` 直接抛 `FileNotFoundError` 并退出，worker 完全不可用。

代码已提供环境变量覆盖（`runner.py` 的 `HEARTBEAT_ENV`），所以**不需要改代码**，设置即可：

```powershell
$env:WORKER_HEARTBEAT_FILE = 'D:\SmartSketch\.tmp\smartsketch-worker.heartbeat'
```

> `start-dev.ps1` 与 `start-smartsketch.bat` 都已自动设置这一项。

### 2. 应用不读 `.env` 文件，只读环境变量

`src/backend/app/config.py` 的 `load_settings()` 明确声明 *without reading a .env file*。
不载入 `.env` 会有两个后果：

- 缺 `AUTH_JWT_SECRET`（或短于 32 字节）→ **API 拒绝启动**；
- 缺 `NEO4J_PASSWORD` → 连 Neo4j 时 **`AuthError`**（因为读到的口令是空字符串）。

`scripts/start-demo.sh` 用 `set -a; source .env` 解决，Windows 等价做法：

```powershell
Get-Content .env | ForEach-Object {
  if ($_ -match '^([A-Z_][A-Z0-9_]*)=(.*)$') { $v=$Matches[2].Trim(); if($v){ Set-Item "Env:$($Matches[1])" $v } }
}
```

`docs/runbook.md` 只写了 *"Windows 需自行处理 `set -a; source .env` 等 shell 写法"*，
上面这段就是可用写法。

### 3. 后端进程必须从 `src\backend` 启动

`.env` 里的 `SQLITE_URL=sqlite:///./storage/smartsketch.sqlite3` 与 `STORAGE_DIR=./storage`
都是**相对路径**，按进程的当前工作目录解析。从仓库根目录启动会得到**另一个空数据库**
（表现为 `Database has pending migrations (001, ... 014)`）。

所以 API、worker、迁移脚本、`scripts/import-demo.py` 都必须 `cd src\backend` 之后再运行。

## 三、手动启动（不使用脚本）

开三个 PowerShell 窗口，每个都先执行这段公共前置：

```powershell
cd D:\SmartSketch\SmartSketch
Get-Content .env | ForEach-Object {
  if ($_ -match '^([A-Z_][A-Z0-9_]*)=(.*)$') { $v=$Matches[2].Trim(); if($v){ Set-Item "Env:$($Matches[1])" $v } }
}
$env:PYTHONPATH = "$PWD\src\backend"
$env:WORKER_HEARTBEAT_FILE = 'D:\SmartSketch\.tmp\smartsketch-worker.heartbeat'
Set-Location src\backend
```

然后各窗口分别运行：

```powershell
# 窗口 A: API
D:\SmartSketch\SmartSketch\.venv\Scripts\python.exe -m app

# 窗口 B: worker
D:\SmartSketch\SmartSketch\.venv\Scripts\python.exe -m app.workers

# 窗口 C: 前端（见下节，不要直接用 npm run dev）
cd D:\SmartSketch\SmartSketch\src\frontend
node dev-server-no-config.mjs 5173
```

首次或更新代码后，先跑迁移（同样要在 `src\backend` 下）：

```powershell
D:\SmartSketch\SmartSketch\.venv\Scripts\python.exe -m app.repositories.sqlite
D:\SmartSketch\SmartSketch\.venv\Scripts\python.exe -m app.repositories.graph_migrations
```

## 四、前端：`npm run dev` 在受限环境下会崩

Vite 在 Windows 上首次做 realpath 时会执行 `exec("net use")`（见
`node_modules/vite/dist/node/chunks/node.js` 的 `optimizeSafeRealPathSync`，用于识别网络驱动器
映射）。若 shell 受限（不允许用管道捕获子进程输出），该调用抛 `spawn EPERM` 并**直接终止
vite 启动**，`npm run dev`、`npm run build`、`vitest` 全部受影响。

`src/frontend/dev-server-no-config.mjs` 用 `configFile: false` 把配置作为内联对象交给 Vite，
因此既不打包 `vite.config.ts`、也不触发任何 `exec`，等价于原配置的 `plugins` + `server.proxy`：

```powershell
cd src\frontend
node dev-server-no-config.mjs 5173
```

> 在**普通（非受限）**终端里，项目原生的 `npm run dev` 可正常工作，本文件可不用。

## 五、从零搭建需要的东西

| 组件 | 说明 |
| --- | --- |
| WSL 2 | `wsl --install --no-distribution`，或安装 GitHub 上的 `wsl.<版本>.x64.msi` |
| Docker Desktop | 安装时选 **Per-user installation**（免管理员）；装完在 Settings → General 确认用 WSL 2 后端 |
| Docker 镜像加速 | Settings → Docker Engine 加 `"registry-mirrors": ["https://docker.1ms.run"]`，否则拉 `neo4j` 很慢 |
| Python 3.11/3.12 | 建 `.venv` 后装 `src/backend[test]` 依赖。**PyPI 直连慢，用国内镜像** `-i https://pypi.tuna.tsinghua.edu.cn/simple` |
| Node.js 22.22+ / 24.15+ | `npm ci --prefix src\frontend` |
| `.env` | 复制 `.env.example`，填 `NEO4J_PASSWORD`（≥8 位）与 `AUTH_JWT_SECRET`（≥32 位随机串） |

### 大文件下载：用支持断点续传的工具

国内直连 GitHub Releases 与 `desktop.docker.com` 常见**连接中途被重置**，而
`Invoke-WebRequest` 与 BITS **不会续传**，一断就前功尽弃（表现为 `wsl --install` 卡在 0%、
`wsl.msi` 只有 0.66 MB）。可用的做法：

- 走镜像 `https://ghfast.top/<原始 GitHub 链接>`（实测能传大文件且支持 Range 续传）；
- 自己写循环，断线后用 HTTP `Range` 头从已下载字节继续，直到文件完整；
- PostgreSQL/Neo4j 等官方站若返回 403，注意它们可能只让浏览器访问。

## 六、验证是否正常

```powershell
# API 进程可响应（不表示 Neo4j 就绪）
Invoke-WebRequest http://127.0.0.1:8000/health -UseBasicParsing | Select-Object -Expand Content
# 期望: {"status":"ok","version":"0.1.0"}

# 前端反代到 API
Invoke-WebRequest http://127.0.0.1:5173/health -UseBasicParsing | Select-Object -Expand Content

# Neo4j 版本与 APOC（知识融合依赖 apoc.refactor.mergeNodes）
docker compose exec -T neo4j cypher-shell -u neo4j -p <NEO4J_PASSWORD> "RETURN apoc.version()"
```

## 七、已知的 Windows 相关缺陷（未修复）

1. **worker 心跳默认路径是 Unix 的 `/tmp`**（`app/workers/runner.py:58`）——靠环境变量绕开，
   默认值本身应按平台区分。
2. **`datasets/` 未在 `.gitattributes` 里钉 `eol=lf`**——`core.autocrlf=true` 的 Windows 检出会
   改变 `datasets/demo/ch3-stack-queue.md` 的行尾，使其 sha256 与 `manifest.json` 记录的
   不一致，并**级联**影响资料修订 ID、夹具与大量测试（表现为 `test_k09` 失败与上千个夹具错误）。
   临时处理：在本仓库执行 `git config core.autocrlf false` 后 `git reset --hard HEAD`。

这两条值得回上游修，见 `AGENTS.md` 的任务认领流程。
