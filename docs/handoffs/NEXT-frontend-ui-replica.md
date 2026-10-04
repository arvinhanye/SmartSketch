# 接手说明：frontend-backend-refactor 前端设计复刻（截至 2026-10-04）

> **给下一位接手者**：本文是唯一入口。先读第 1–2 节了解状态与边界，再按第 5 节恢复环境，
> 按第 6 节执行剩余任务。历史细节见 `deepseek-frontend-migration.md`（本轮完整交接）。

## 1. 一句话状态

**界面迁移与视觉复刻已完成并通过前端验收；系统级门禁与真实后端全链路验收尚未完成。**

- 分支：`frontend-backend-refactor`
- 产品代码最后提交：`0d1b170`（其后为文档提交 `217f67a`）
- 目标基线：`68762e8ab9efdfc20552a94668d7e26deb2e34c5`
- 界面唯一来源：`frontend-ui-revision@27bff16a67fa4e9b96416d3529069832b05e88ac`
- **未推送、未合并、未部署**（截至本文件写入）

## 2. 绝对边界（不得越界）

只允许修改：`src/frontend/src/**`、`tests/frontend/**`、`docs/**`。

以下**一律不得修改**（本期已逐次核对为无差异）：

- `src/backend/**`、`src/contracts/**`（含生成物）
- 数据库迁移、`scripts/**`、`.env.example`、系统运行配置
- 前端 `src/frontend/src/api/**`、`composables/**`、`stores/**`、`router/**`、`main.ts`

**不可恢复的边界**（ADR-080 / ADR-081，已签收）：

- 个人模型凭据只走 `/api/v1/me/model-config`（GET/PUT/DELETE）+ `/test`；密钥服务端加密，**不回显、不落浏览器存储**。
- **不恢复**全局 `/api/v1/api-settings`、向量配置界面、模型发现接口、本地 Ollama/私网地址、保存后重启语义。
- 向量模型是**部署者系统级配置**（环境变量 `EMBEDDING_*`），不是个人设置，**不要加回设置页**。

## 3. 已完成（有证据）

| 范围 | 提交 | 证据 |
| --- | --- | --- |
| 第 1–3 批：外壳/登录、课程页、资料页、成员页 | `ccf5602`…`ffae94d` | 前端测试 |
| F1/F2：资料页拖放取消默认动作、键盘焦点可见 | `25d785f` | h02 新增 4 项（旧代码下失败）；真实浏览器实测轮廓 `solid 2px rgb(156,74,52)` |
| F3：课程概览不再混入全量课程列表 | `f723801` | h01 c1/c2 用例；外部探针通过 |
| F4：成员桌面输入框与按钮同行 | `257aa6d` | 真实浏览器实测底边差 0px；600px 堆叠等宽 |
| 第 4 批：审核队列与版本面板 | `103a322` | h09/h10/h14 |
| 第 5 批：图谱页与画布主题 | `10981d4` | h03–h08/h11/h14/i06；画布底色实测 `rgb(255,253,250)` |
| 第 6 批：问答展示（保留发送锁） | `b27bdb3` | redesign-chat / chat-send-lock / j08 / j09 / l10 / d1-d3 |
| 第 7 批：个人模型设置页适配 | `700d743` | l10 / n03-n05 / d1-d3 |
| U1–U7：精确视觉复刻（认证页、审核外层、API 设置骨架、成员断点、可读性、状态复位、前置文案） | `fd17d50` | 与来源同数据同视窗 **15 项判定全 PASS**（`ui-replica-compare.mjs`） |
| R1–R5：复审回归修正（测试快照隔离、换号隔离、失败上下文、Esc 焦点、弹窗尺寸） | `0d1b170` | 审查方 **4 项独立探针全通过**；真实栈实测 |

**最终前端检查结果**（`0d1b170` 上实测）：两套 `vue-tsc` 0 错误；`29 文件 / 843 项`全通过；外部 F1/F3 探针 2 项通过；审查方 R1–R3 探针 4 项通过；构建成功；`git diff --check` 通过。

## 4. 未完成（下一位的重点）

### N1 [优先] 跑通系统门禁

`scripts/verify.sh` 的三个档位都要跑并记录真实结果：

```bash
# 在 Git Bash 中、仓库根目录执行
bash scripts/verify.sh basic        # 已实测通过（见 §5）
bash scripts/verify.sh full         # 未跑：后端 pytest 全量 + 前端类型/测试/构建
bash scripts/verify.sh integration  # 未跑：一次性 Neo4j 上的集成 + 端到端
```

`basic` 我已实测 **PASS**（见 §5 的环境要求），`full`/`integration` 未跑。

### N2 真实后端全链路逐页验收

用真实后端数据（不是合成夹具）逐页过一遍：

上传 → 解析 → 审核（处理/合并）→ 发布 → 学生图谱/学习状态 → 带引用问答；以及成员增删、个人设置保存/测试/清除。

### N3 视觉对照未覆盖的页面

U1–U5 只对登录/注册/审核/成员/个人设置出了同视窗对照图并判定通过。以下页面**沿用更早一轮「基本一致」的结论，未重新出图**：教师/学生首页、课程概览、资料页、教师/学生图谱、问答页。若要求逐页复刻证据，需补对照截图。

### N4 弹窗键盘路径

只验证了 Esc（R4）。Tab 焦点限制、Shift+Tab、关闭后焦点回触发按钮的完整回放未做。

## 5. 如何恢复环境（已实测可行）

本机实际可用：**Git Bash 在 `D:\Workspace\Git`（不在 PATH）**、**Python 3.13.7 在 `C:\Program Files\Python313`**、**Docker Desktop 29.8**。

> 更正：早前交接里「本机无 Bash / python3 找不到」的说法**不准确**。Git Bash 内 `python3` 完全可用
> （`/c/Program Files/Python313/python3`）。`verify.sh basic` 当初失败的真实原因是：缺少契约工具链依赖、
> Python 用户级 Scripts 目录不在 PATH、以及未设置 UTF-8 输出编码。

### 5.1 让 `verify.sh basic` 通过（已实测）

```powershell
# 1) 装契约工具链（按 src/contracts/toolchain.txt 的版本锁）
& "C:\Program Files\Python313\python3.exe" -m pip install --user -i https://pypi.tuna.tsinghua.edu.cn/simple `
  "pyyaml==6.0.2" "openapi-spec-validator==0.9.0" "jsonschema==4.26.0" "pytest==8.3.5" "datamodel-code-generator==0.26.3"
```

```bash
# 2) 在 Git Bash 中：把用户级 Scripts 加进 PATH 并强制 UTF-8，然后跑门禁
export PATH="/c/Users/asus/AppData/Roaming/Python/Python313/Scripts:$PATH"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
cd "<仓库根>"
bash scripts/verify.sh basic
```

实测输出：`PASS contracts: 契约校验通过：OpenAPI 3.1.0，32 条路径 / 129 个 schema / 385 处 $ref`，
B08/B09/B10/B12/B13/B14 共 **236 项**通过，`Scaffold verification passed.`，**exit 0**。

### 5.2 跑 `full` 需要补的依赖

```powershell
# 后端测试依赖（装进你选定的解释器；backend.sh 认 $PYTHON 变量）
& "<python>" -m pip install httpx==0.28.1 pytest pyyaml==6.0.2 openapi-spec-validator==0.9.0 jsonschema==4.26.0
```

```bash
# 让门禁用它：backend.sh / frontend.sh 的解释器优先级为 $PYTHON → .venv/bin/python → python3
export PYTHON="C:/Program Files/Python313/python3.exe"   # 或你的 venv
bash scripts/verify.sh full
```

`integration` 还需要一次性 Neo4j（脚本自己起，不要指向开发库——相关用例会清库）。

### 5.3 启动前后端做人工验收（已实测可行）

我本轮已用下面这套跑通过完整链路，可直接复用：

```powershell
# 1) 依赖 Neo4j：项目自带 compose（首次必须先建 .env）
cd <仓库根>
docker compose up -d neo4j          # 容器名 smartsketch_src-neo4j-1，映射 127.0.0.1:7474/7687

# 2) 后端解释器（示例用仓库外 venv，避免污染全局）
& "<venv>\Scripts\python.exe" -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple `
  argon2-cffi==25.1.0 cryptography==50.0.2 fastapi==0.141.1 markdown-it-py==4.2.0 neo4j==5.28.2 `
  pdfminer.six==20260107 python-multipart==0.0.32 uvicorn==0.53.0

# 3) 迁移（后端不读 .env，必须先注入进程环境）
$env:PYTHONPATH = "<仓库根>\src\backend"
#    逐行把 .env 的 KEY=VALUE 注入 $env: 之后：
& "<venv>\Scripts\python.exe" -m app.repositories.sqlite            # SQLite 迁移
& "<venv>\Scripts\python.exe" -m app.repositories.graph_migrations  # Neo4j schema + 向量索引

# 4) API 与 worker（各自一个终端）
& "<venv>\Scripts\python.exe" -m app            # http://127.0.0.1:8000
& "<venv>\Scripts\python.exe" -m app.workers    # 需要 WORKER_HEARTBEAT_FILE 指向 Windows 可写路径

# 5) 前端
cd src\frontend; npx vite --port 5173 --strictPort    # http://localhost:5173/
```

**踩过的坑（务必注意）**：

1. **`.env` 必须自己建**：`cp .env.example .env`，并填 `AUTH_JWT_SECRET`（≥32 字节）、
   `MODEL_CREDENTIAL_KEY`（32 字节 URL 安全 base64）、`NEO4J_PASSWORD`。缺失时后端**拒绝启动**。
2. **后端不读 `.env` 文件**，只读进程环境变量——启动前必须逐行注入。
3. **worker 心跳路径**：Windows 上默认 `/tmp/...` 不存在，必须设
   `WORKER_HEARTBEAT_FILE=./storage/worker.heartbeat`（相对启动目录）。
4. **前端只监听 IPv6 `::1`**：用 `http://localhost:5173/`，**不要用 `127.0.0.1:5173`**。
5. **Neo4j 坏数据卷**：容器反复重启、退出码 3、日志只有「Stopped.」时，删掉 `neo4j/data` 与
   `neo4j/logs` 重新初始化即可（我已这样修好过）。
6. **Python 输出编码**：Git Bash 里 `LANG`/`LC_ALL` 未设置时 Python 用 GBK，打印 `✓`/`×`
   会 `UnicodeEncodeError`。设 `PYTHONUTF8=1` 即可。
7. **不要用 PowerShell 5.1 发含中文的 JSON**：`Invoke-WebRequest -Body` 会按系统代码页编码，
   写进库里就是乱码（我踩过，建了一门课名全是问号的测试课）。改用 Node 的 `fetch`。
8. **不要用 PowerShell 的 `Set-Content`/`Get-Content -Raw` 往返改含中文的源文件**：会按 GBK 解码再写回，
   把中文注释变成乱码并加 BOM。改文本一律用编辑工具的字符串替换。

**演示账号**（用 `scripts/seed-demo-accounts.py` 创建，需先设 `SEED_DEMO_PASSWORD`）：
`demo_teacher` / `demo_student` / `demo_student2`。

## 6. 建议的接手顺序

1. 复现 §5.1，确认 `basic` 能在你机器上通过（记录命令与输出）。
2. 补 §5.2 依赖，跑 `full`，把失败逐项定位（**不得改弱断言、不得删测试来变绿**）。
3. 具备 Docker/隔离 Neo4j 后跑 `integration`。
4. 用 §5.3 起真实前后端，按 N2 做逐页人工验收并留存截图。
5. 需要复刻证据的页面按 N3 补对照图；N4 补键盘路径回放。
6. 每完成一块，更新 `docs/handoffs/deepseek-frontend-migration.md` 的对应小节与本文 §4 的勾选状态，
   并只提交本任务文件。

## 7. 可复用的验收工具（都在仓库外 `.review-artifacts/`）

| 脚本 | 用途 |
| --- | --- |
| `ui-replica-compare.mjs` | 与来源 `27bff16` 同数据同视窗自动对照，15 项判定 |
| `ui-verify.mjs` | F2/F4/G6 画布/弹窗尺寸的无头浏览器断言 |
| `live-pages.mjs` / `live-e2e.mjs` | 对真实前后端做逐页截图与「上传→抽取→审核」链路 |
| `r5-dialog-check.mjs` | 弹窗尺寸（22rem/8px/32px）与 Esc 焦点 |
| `r13-real-check.mjs` | 真实栈上复现 R1/R3（保存失败不串入、失败保留上下文） |
| `1b2bd3c-probe.test.ts` + config | 审查方的独立回归探针（4 项） |
| `055d914-probe.test.ts` + config | 更早一轮的独立探针（F1/F3，2 项） |
| `env-probe.sh` | Git Bash 环境探测（python3/编码/pytest） |

## 8. 本次交付的提交

```
217f67a docs: record the review fixes and the exact head
0d1b170 fix(frontend): isolate the connection-test snapshot from save and clear errors   ← 产品代码止于此
1b2bd3c docs: record the visual replica results and the exact head
fd17d50 fix(frontend): restore frontend-ui-revision visual fidelity                      ← U1–U7
（更早的 13 个提交见 deepseek-frontend-migration.md §8）
```

每个批次/修正独立可撤回：用对应提交的 `git revert` 生成新提交，先核对后续依赖；
本轮无数据迁移，不需要数据库或向量空间回退；**禁止硬重置**。
