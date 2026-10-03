# Claude 交接：Windows 可移植性修复（WIN-01）

- review_status: 待独立审查
- 分支：`fix/windows-worker-and-eol`（基线 `main@2a67189`）
- 范围：后端 worker 心跳默认路径、`datasets/` 行尾属性、Windows 可移植性 CI job，以及为让该 job 通过而必须一并修复的 4 处测试/脚本 Windows 缺陷

## 背景与问题来源

在 Windows 11 23H2（中文区）+ Docker Desktop 上把项目从零跑通时，发现**这套代码从未在 Windows 上验证过**
（`docs/runbook.md` 开头即注明 macOS/Windows 未实测），于是暴露出若干**只在 Windows 出现、CI 无法捕获**的缺陷。
本批次修掉其中 5 处，并补上能防它们回归的 CI job。

## 交付物

| # | 缺陷 | 影响 | 修改 |
| --- | --- | --- | --- |
| 1 | `DEFAULT_HEARTBEAT_FILE` 硬编码 Unix 路径 `/tmp/smartsketch-worker.heartbeat` | Windows 解析为 `\\tmp\...`（不存在），`supervise()` 的 `beat.touch()` 抛 `FileNotFoundError`，**worker 根本起不来**，上传资料永远停在 `queued` | `src/backend/app/workers/runner.py`：改为 `Path(tempfile.gettempdir()) / "smartsketch-worker.heartbeat"`（POSIX 上仍是 `/tmp`，行为不变） |
| 2 | `datasets/` 未钉 `eol=lf` | `core.autocrlf=true` 的检出把 `ch3-stack-queue.md` 变成 CRLF，其 sha256 与 `manifest.json` 记录不符；修订 ID 由内容哈希派生，于是**级联**导致 `test_k09` 失败与 **1268 个 error** | `.gitattributes` 增 `datasets/** text eol=lf` |
| 3 | `tests/tooling` 无 bash 平台守卫，且直接执行 `.sh` | 收集期 `ModuleNotFoundError: termios`（K07 用 `pty`）**打断整个门禁**；`test_b07`/`test_k11` 直接跑 `.sh` 得 `OSError [WinError 193]` | `tests/tooling/test_k07.py` 按平台显式跳过；新增 `tests/tooling/conftest.py` 提供 `bash` 夹具（`SMARTSKETCH_BASH` → `shutil.which`，并**拒绝 WSL 的 `System32\bash.exe`**，它不是 Git Bash）；`test_b07.py`/`test_k11.py` 改用该夹具 |
| 4 | 工具链脚本按 locale 编码输出 `✓` | `scripts/check_contracts.py` 的 **PASS 路径**在中国区 Windows（GBK）抛 `UnicodeEncodeError` 并以非零码退出，门禁把"通过"判成失败 | `scripts/check_contracts.py`：仅在当前流编码无法表示 `✓` 时切 UTF-8 |
| 5 | 测试用 `subprocess.run(..., text=True)` 未固定编码 | 子进程按 locale 编码 stdout/stderr；中文 Windows（GBK）与 GitHub runner（cp1252）下，含中文（`栈`）或 `✓` 的输出令脚本崩溃，用例失败却指向被测代码 | `tests/backend/conftest.py` 设 `PYTHONIOENCODING=utf-8`（`setdefault`，尊重显式设置）；`test_k02.py` 四处调用改显式 `encoding="utf-8"` |
| 6 | `gate.py` 丢弃模块级跳过的真实原因 | pytest 把模块级跳过记成 `message="collection skipped"`、真正原因放在**元素文本**里；门禁只读 `message`，于是合法跳过被判红，而放宽白名单又会放行所有模块级跳过 | `scripts/verify/gate.py` 新增 `skip_reason()`：属性无信息时回落到元素文本 |
| 7 | 无 Windows CI | 上述缺陷**不可能被 CI 发现**（三个 job 全是 `ubuntu-latest`） | `.github/workflows/ci.yml` 增 `platform-windows` job（`windows-latest`，跑 `scripts/verify/backend.sh full`，需 Neo4j 的用例不在其中） |

新增文件：`tests/backend/test_worker_heartbeat.py`（7 个用例）、`tests/tooling/conftest.py`。

## 验证

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 心跳红灯 | `pytest tests/backend/test_worker_heartbeat.py`（修改实现前） | 5 failed，报错即 `FileNotFoundError: '\\tmp\\smartsketch-worker.heartbeat'` |
| 心跳绿灯 | 同上（修改后） | **7 passed** |
| 心跳独立复核 | 直接调用 `runner.heartbeat_path()` 后 `touch()` | 默认路径 `D:\SmartSketch\.tmp\smartsketch-worker.heartbeat`，绝对路径、父目录存在且可写、`health()==0` |
| 行尾属性 | `git check-attr` + sha256 + `test_k09.py` | `eol: lf`；哈希 `4847e2…` 与清单一致；**9 passed** |
| tooling 门禁 | `pytest tests/tooling` + `gate.py tooling full` | **29 passed / 7 skipped**，`PASS tooling gate (full)` |
| 门禁负例 | 构造未登记原因的 JUnit | 仍判红（未放宽门禁） |
| 后端全量 | `pytest tests/backend tests/tooling` | **1 failed, 3532 passed, 34 skipped**（基线 3496 passed；唯一失败是 `test_e03` 的连接类用例，见下） |
| 跨 locale | 分别以 `gbk` / `utf-8` / 未设置运行 `test_k02` + `test_b07` + `test_k07` | 全绿（`cp1252` 组合已由 conftest 修复覆盖） |

**唯一失败与本批次无关**：`tests/backend/test_e03.py::test_stdlib_transport_connection_refused` 期望连接被
**拒绝**，而受限环境把回环连接变成**超时**（拿到 `ModelTimeoutError` 而非 `ModelConnectionError`）。
与改动无关，在 CI 上应通过。

## 接口 / 数据 / 配置变更

- **无契约变更**（未动 `src/contracts/`），无数据库迁移，无依赖升级。
- 行为变更仅一处：`DEFAULT_HEARTBEAT_FILE` 的取值按平台派生；`WORKER_HEARTBEAT_FILE` 覆盖语义不变。
- 无新增必需环境变量；`SMARTSKETCH_BASH` 为**可选**（仅 Windows 上跑 tooling 测试时需要）。

## 风险与遗留

1. **Windows CI job 未经真实运行**：本机受限环境无法执行 Git Bash（`couldn't create signal pipe, Win32 error 5`），
   因此 `platform-windows` job 只做到「YAML 结构校验 + 在 Python 里逐步复现 `backend.sh` 的两条命令」。
   首次推送后须核对真实 CI 结果；若 `windows-latest` 上 Git Bash 行为有差异，最可能需要调整的是
   `PYTHON`/`bash` 的解析路径。
2. **其余 locale 相关调用点未逐一固定编码**：`tests/backend` 还有 8 处、`tests/tooling` 2 处、`tests/contracts` 1 处
   `subprocess.run(..., text=True)` 未指定 `encoding=`。当前靠 conftest 的 `PYTHONIOENCODING` 兜住，
   若将来有子进程输出非 ASCII 且父进程断言也含非 ASCII，需要按 `test_k02` 的做法在调用点显式固定。
3. **`pty` 与 bash 类用例在 Windows 上跳过**：K07 全模块（Windows 无 pty）与 tooling 的 bash 用例
   （无 Git Bash 时）带登记原因跳过；**Linux CI 仍必须执行**，未削弱覆盖率。
4. **同组第二个缺陷（相对路径锚点）已修**，见下节。

## 追加修复：相对 SQLITE_URL / STORAGE_DIR 的锚点（同批次第二项）

**问题**：`SQLITE_URL=sqlite:///./storage/smartsketch.sqlite3` 与 `STORAGE_DIR=./storage` 是相对路径，
而 `repositories.sqlite.database_path()` 用 `Path(raw).resolve()`、`FileStorage.__init__` 用
`path.resolve()`，两者都按**进程 CWD** 解析。于是同一份配置按启动目录解析成两个库：

| 启动目录 | 解析结果 | 后果 |
| --- | --- | --- |
| `src/backend`（`docs/runbook.md` 与 `scripts/start-demo.sh` 的写法） | `src/backend/storage/smartsketch.sqlite3` | 正确，有迁移与数据 |
| 仓库根目录（`scripts/import-demo.py`、`seed-demo-accounts.py` 的自然用法） | `<repo>/storage/smartsketch.sqlite3` | **全新空库**，脚本报 `Database has pending migrations (001, ... 014)` |

**修法**：两处都把**相对**路径锚定到后端根 `src/backend`；绝对路径（容器内的 `/data/...`、
测试夹具的 tmp 路径）不受影响。仓库在其它地方早已是这个范式：`sqlite.MIGRATIONS_DIR`、
`ai.prompts.DEFAULT_PROMPTS_DIR`、`schemas.contracts._PATH` 均锚定源码位置。

- `repositories/sqlite.py`：新增 `BACKEND_ROOT`，`database_path()` 对相对路径加锚。
- `services/file_storage.py`：新增 `BACKEND_ROOT`，`FileStorage.__init__` 对相对 root 加锚。

**验证**：新增 `tests/backend/test_config_path_anchor.py`，改动前 **4 failed**（含端到端子进程用例
直接打印出"同一配置解析出两个库"），改动后 **5 passed**；真实端到端从仓库根运行
`scripts/seed-demo-accounts.py` 输出 `exists, unchanged` 且退出码 0（旧实现报"待迁移"）。
后端全量 **3537 passed / 34 skipped**。

## 调研后**决定不改**的一项：同名测试文件

`tests/backend` 与 `tests/integration` 有 5 组同名文件（`test_f08/f12/g06/k09/relations_api.py`），
混跑会触发 pytest `import mismatch`。但调研结论是**不应改名**：

1. 这是仓库**有意的约定**，不是疏漏——`docs/tasks.md:1459` 明确写着
   「同名（同 F08～F13 惯例），必须按目录分开跑，否则 pytest import mismatch」，
   且 F08～F13 全部遵循；
2. 语义上同名是对的：同一功能的两个层次（backend = 真实 app + SQLite / 内存假图；
   integration = 真实 Neo4j 5.26）；
3. 文档与任务板有 **26 处**引用这些路径，改名会大面积制造不一致。

也评估过用 `__init__.py` 把两个目录变成不同的包来消除混跑冲突（实测**确实有效**：混跑可收集），
但它连带要求改 **9 处跨测试导入**（`test_f12.py` 导 `test_f08`、`test_g05/g06/g08*` 导 `test_g04` 等）
并引入 `pythonpath`/`consider_namespace_packages` 配置，**风险大于收益，已回退**（回退后混跑恢复为
仓库记录的既有行为，全量测试无回归）。如需彻底消除，应作为独立任务连同跨测试导入一起改造。

## 下一步

1. 推送后在 CI 上确认 `platform-windows` job 通过，并核对 `ubuntu` 三个 job 无回归（`.gitattributes`、
   `check_contracts.py`、**相对路径锚点**三处改动需要重点看：契约门禁与任何依赖 CWD 的脚本）。
2. 独立审查建议重点看：`skip_reason()` 的回落逻辑是否可能**放宽**门禁；`test_k07.py` 的跳过是否会在
   Linux 上误触发（判据应为 `sys.platform == "win32"`，与 pty 可用性无关）；相对路径锚点是否影响
   容器内以绝对路径配置的部署（预期不影响，`/data/...` 是绝对路径）。
3. 后续可承接：上述「同名测试文件 + 9 处跨测试导入」的独立改造，以及把其余 locale 调用点在改动到
   附近文件时顺手固定编码。
