# SmartSketch 运行手册（K12）

本手册说明如何把智绘学途跑起来、导入演示课程、做验收与恢复。逐功能的验收证据见 [acceptance.md](acceptance.md)。

> **已测平台**：`scripts/start-demo.sh` 与下列各节只有 **Linux（x86_64，Ubuntu 系云端容器，Python 3.11、Node 22、Docker 29、Neo4j 5.26.31）** 上完整跑过本手册的「方式 B」「演示导入」「门禁」「端到端」各节（2026-09-27）。macOS 与 Windows **未实测**；「方式 A」（`docker compose --profile app`）尚未在真实 Docker 守护进程上跑通过，见文末「限制」。

## 1. 准备

| 依赖 | 版本 | 用途 |
| --- | --- | --- |
| Python | 3.11 或 3.12 | 后端 API、worker、脚本 |
| Node.js | 22.22+ 或 24.15+ | 前端构建、Vite、Playwright |
| Docker | 任意能跑 `neo4j:5.26-community` 的版本 | Neo4j（图谱与向量索引） |

```bash
git clone https://github.com/arvinhanye/SmartSketch.git && cd SmartSketch
python3 -m venv .venv && source .venv/bin/activate
pip install -e 'src/backend[test]'
npm ci --prefix src/frontend
npm ci                      # 仓库根目录：只有 Playwright（端到端用）
cp .env.example .env        # 然后编辑 .env，见下
```

`.env` 至少改这几项（其余保持示例值即可）：

| 变量 | 取值 | 说明 |
| --- | --- | --- |
| `NEO4J_PASSWORD` | 本机自定，≥ 8 位 | 仅本机使用，不提交 |
| `AUTH_JWT_SECRET` | ≥ 32 位随机串，如 `python3 -c 'import secrets;print(secrets.token_urlsafe(48))'` | 登录令牌签名 |
| `LLM_MODE` / `EMBEDDING_MODE` | 演示用 `demo`；真实模型用 `live` / `online` | 见第 3 节 |
| `QA_SIMILARITY_THRESHOLD` | 演示模式用 `0.58`；真实向量保持 `0.7` | ADR-076 实测 |

## 2. 启动

### 一键启动（推荐，演示模式）

```bash
git clone https://github.com/arvinhanye/SmartSketch.git && cd SmartSketch
scripts/start-demo.sh
```

只需要 Docker（已启动）、Python 3.11/3.12、Node.js 22.22+。脚本依次完成：创建 `.venv` 并安装后端（跳过 anaconda 的 Python）→ `npm ci` 前端 → 没有 `.env` 时按 `.env.example` 生成演示配置（随机 Neo4j 口令与登录签名密钥）→ `dev-up.sh` → SQLite 与 Neo4j 迁移 → 预置演示账号 → 后台启动 API 与 worker → 导入演示课程 → 启动前端并打开浏览器。

- 账号 `demo_teacher` / `demo_student` / `demo_student2`，首次建号的口令缺省 `smartsketch-demo`（用 `SEED_DEMO_PASSWORD=… scripts/start-demo.sh` 自定）。账号已存在时沿用原口令，脚本不重置。
- 本次进程一律用演示模型（`LLM_MODE=demo`、`EMBEDDING_MODE=demo`、`QA_SIMILARITY_THRESHOLD=0.58`），不改 `.env`，不产生付费调用。已有 `.env` 只会在 `AUTH_JWT_SECRET` 为空或过短时补一行随机值。
- 可重复执行：已装依赖、已建账号、已导入课程都复用（导入报告 `publish_unchanged: true`）。
- `Ctrl+C` 停止 API、worker 与前端；Neo4j 保留运行，停止用 `scripts/dev-down.sh`。
- 选项：`--live` 用真实大模型（见下），`--no-import` 跳过课程导入，`--no-open` 不开浏览器；`DEMO_WEB_PORT` 改前端端口。日志在 `.demo/logs/`。
- 与手动步骤一样，后端进程从 `src/backend` 启动，相对的 `SQLITE_URL`/`STORAGE_DIR` 落在 `src/backend/storage/`，与下文手动方式共用同一份数据。
- 若 Neo4j 库此前用 `fake` 或真实向量建过，API 会因向量空间不一致拒绝启动（见第 3 节），此时换新库或运行 `scripts/reembed.py`。

### 一键启动，真实大模型（`--live`）

网页里没有「接入 API」的设置项：模型密钥只放在服务端 `.env`，由 worker 在抽取时调用。步骤：

1. 在 `.env` 填 `LLM_API_KEY=<DeepSeek 密钥>`；`LLM_BASE_URL`、`LLM_EXTRACTION_MODEL`、`LLM_CHAT_MODEL` 保持示例值（D-02a）。
2. `scripts/start-demo.sh --live`。脚本启动前检查主用四项，缺一项就退出；本次进程用 `LLM_MODE=live`。
3. 教师登录 → 课程 → 资料 → 上传 PDF/DOCX/TXT/Markdown；状态变为已完成后，到「审核」与「编辑图谱」查看草稿。

- 向量：`.env` 的 `EMBEDDING_MODE` 为 `online`/`local` 时照用，否则沿用演示向量（D-02c 向量供应商未签收；DeepSeek 不提供向量接口）。沿用演示向量时与演示课程同一向量空间，不必换库，问答阈值仍用 0.58。
- `--live` 不自动导入演示课程：首次导入会用真实模型抽取整套示例资料。已导入过的演示课程照常可用。
- macOS 上未设置 `SSL_CERT_FILE` 时，脚本用 `.venv` 里的 certifi 根证书（缺时自动安装），免得 HTTPS 调模型报证书错误。
- 每上传一份资料就会产生付费调用，受 `LLM_TASK_TOKEN_BUDGET`、`LLM_DAILY_TOKEN_BUDGET` 限制。

### 方式 B：本机进程，手动（已测）

```bash
./scripts/dev-up.sh                                   # 启动 Neo4j 并检查 APOC
set -a; source .env; set +a                           # 把 .env 导入当前 shell（后端只读环境变量）
cd src/backend
python -m app.repositories.sqlite                     # SQLite 迁移
python -m app.repositories.graph_migrations           # Neo4j 约束与向量索引
SEED_DEMO_PASSWORD='换成你的演示口令' python ../../scripts/seed-demo-accounts.py
python -m app            &                            # API：127.0.0.1:8000
python -m app.workers    &                            # worker：处理上传资料
cd ../frontend && npm run dev                         # 前端：http://localhost:5173（/api 反代到 8000）
```

浏览器打开 <http://localhost:5173>，用 `demo_teacher` / `demo_student` / `demo_student2` 与上面的口令登录。

macOS 上若用真实模型，额外执行 `source .venv/bin/activate`（不要用 anaconda 的 Python）与 `export SSL_CERT_FILE="$(python3 -m certifi)"`。

### 方式 A：容器（K08，未在真实守护进程上验证）

```bash
docker compose --profile app up -d --build            # neo4j + migrate + api + worker + web(nginx:8080)
docker compose --profile app run --rm -e SEED_DEMO_PASSWORD='口令' api python /app/scripts/seed-demo-accounts.py
```

打开 <http://localhost:8080>。若构建失败，退回方式 B，并把错误贴到任务看板。

## 3. 模型模式

| 模式 | `LLM_MODE` | `EMBEDDING_MODE` | 费用 | 适用 |
| --- | --- | --- | --- | --- |
| 演示 | `demo` | `demo` | 无 | 本地验收、端到端测试、演示。规则抽取（中文定义句、标题层级、先修句式）与字符 n-gram 向量，结果确定（ADR-076） |
| 假 | `fake` | `fake` | 无 | 单元测试；上传后抽取必失败，**不要用来验收** |
| 真实 | `live` | `online` | 按量计费 | 正式抽取与问答；需 `LLM_*`、`EMBEDDING_*` 变量（见 `docs/integrations.md`），付费调用须负责人同意 |

演示向量与假向量、真实向量属于不同向量空间：**同一个 Neo4j 库不能直接换模式**，启动时会被拒绝。换模式时用新库，或按 F14 运行 `scripts/reembed.py`。

## 4. 导入演示课程（K09）

API 与 worker 都在运行时：

```bash
python scripts/import-demo.py            # 读取 datasets/demo/manifest.json
```

它会创建「【示例】数据结构：栈与队列」（教师 `demo_teacher`，学生 `demo_student`、`demo_student2`），上传自编资料、等待 worker 处理、发布 v1，最后打印 JSON 报告。可以重复执行：已有的课程、成员、资料不会重复，未变的草稿不会产生新版本；处理失败的资料在下次执行时重新上传。它只写这一门课，不删除任何数据。

| 退出码 | 含义 | 处理 |
| --- | --- | --- |
| 0 | 导入完成 | — |
| 1 | 拒绝或失败（stderr 有原因） | 常见：账号未预置 → 先跑 `seed-demo-accounts.py`；等待超时 → 确认 worker 在跑后重跑 |
| 2 | 配置错误或未迁移 | 按提示迁移、检查环境变量 |

## 5. 质量门禁（K11）

```bash
./scripts/verify.sh                 # basic：骨架 + 钩子回归 + 契约（CI「Repository scaffold」）
./scripts/verify.sh full            # + 后端全量 + 前端类型检查/全量/构建
./scripts/verify.sh integration     # + 一次性 Neo4j 上的集成用例 + K05/K06 端到端
```

测试报告由 `scripts/verify/gate.py` 判定：**零测试、任何失败、未在 `scripts/verify/allowed-skips.txt` 登记原因的跳过**都判失败。契约门禁需要 `openapi-typescript@7.4.4` 与 `datamodel-code-generator==0.26.3`（版本见 `src/contracts/toolchain.txt`）。

## 6. 端到端（K05/K06）

```bash
scripts/e2e.sh                                   # 两条主线
scripts/e2e.sh tests/e2e/student.spec.ts         # 只跑学生主线
```

脚本自带一次性 Neo4j、私有 SQLite 与存储目录（`.e2e/<时间>/`），用演示模型启动 API、worker 与前端构建产物，再跑 Playwright。失败时截图、trace 与三份服务日志都留在该目录。离线环境浏览器版本与 `@playwright/test` 不一致时，用 `PLAYWRIGHT_CHROMIUM_EXECUTABLE` 指定 Chromium。

## 7. 备份与恢复（K10）

先停 API 与 worker，再：

```bash
scripts/backup-demo.sh --out backups/k10                         # SQLite + Neo4j 一致时间点备份
scripts/restore-demo.sh --from backups/k10/<备份目录> \
  --sqlite-target /tmp/restore.sqlite3 --neo4j-uri bolt://127.0.0.1:<空库端口>   # 恢复到隔离副本并核对
```

恢复默认不覆盖任何已有库；覆盖需要 `--replace-existing --confirm <备份 ID>`，并会先对目标做安全副本。细节见脚本头注释与 `docs/handoffs/claude-k10.md`。

## 8. 故障与恢复

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 上传后状态「处理失败：抽取失败的片段过多」 | `LLM_MODE=fake` | 改 `demo` 或 `live` 后重新上传 |
| API 启动报向量空间不一致 | 换了 `EMBEDDING_MODE`/模型但沿用旧库 | 用新 Neo4j 库，或 `scripts/reembed.py` |
| 资料一直「排队中」 | worker 没在运行 | 启动 `python -m app.workers`；已排队任务会被领取 |
| 问答总是「资料未覆盖」 | 阈值与向量模式不匹配，或课程未发布 | 演示模式设 `QA_SIMILARITY_THRESHOLD=0.58`；先发布 |
| 学生看不到课程 | 未加入课程或课程从未发布 | 教师在「管理成员」添加学生并发布 |
| 发布返回 409 课程忙 | 另一写操作持有课程写锁 | 稍后重试；卡住超过租约时长（`PUBLISH_LEASE_SECONDS`）会自动回收 |
| 前端页面接口全部失败 | 开发服务器没反代到 API | 确认 API 在 8000，或设 `SMARTSKETCH_API_TARGET` 后重启 `npm run dev` |

## 9. 限制

- macOS、Windows 未实测；Windows 需自行处理 `set -a; source .env` 等 shell 写法（可用 WSL）。
- 方式 A（容器）在真实 Docker 守护进程上尚未跑通验证（K08 遗留）。
- 演示模型只按规则抽取中文定义句，不代表真实模型的抽取质量；赛题指标以 K02 真实模型判定为准。
- 融合（E08–E10）的自动合并阈值 D-08 未定，当前流水线为简化融合。
- 真实模型的性能（K04）需在本机付费运行后登记。
