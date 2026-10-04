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
| `LLM_MODE` / `EMBEDDING_MODE` | 演示用 `demo`；正式运行用 `personal` / `online`；服务端统一密钥用 `live` / `online` | 见第 3 节 |
| `QA_SIMILARITY_THRESHOLD` | 演示模式用 `0.58`；真实向量保持 `0.7` | ADR-076 实测 |

## 2. 启动

### 一键启动（演示入口 `scripts/start-demo.sh`，推荐试用）

> `scripts/start-demo.sh` 是**演示入口**：不联网、不计费。正式运行（教师与学生各自填模型 API）用 `scripts/start.sh`，见下一节。

```bash
git clone https://github.com/arvinhanye/SmartSketch.git && cd SmartSketch
scripts/start-demo.sh
```

只需要 Docker（已启动）、Python 3.11/3.12、Node.js 22.22+。脚本依次完成：创建 `.venv` 并安装后端（跳过 anaconda 的 Python）→ `npm ci` 前端 → 没有 `.env` 时按 `.env.example` 生成演示配置（随机 Neo4j 口令与登录签名密钥）→ `dev-up.sh` → SQLite 与 Neo4j 迁移 → 预置演示账号 → 后台启动 API 与 worker → 导入演示课程 → 启动前端并打开浏览器。

- 账号 `demo_teacher` / `demo_student` / `demo_student2`，首次建号的口令缺省 `smartsketch-demo`（用 `SEED_DEMO_PASSWORD=… scripts/start-demo.sh` 自定）。账号已存在时沿用原口令，脚本不重置。
- 本次进程一律用演示模型（`LLM_MODE=demo`、`EMBEDDING_MODE=demo`、`QA_SIMILARITY_THRESHOLD=0.58`），不改 `.env`，不产生付费调用。已有 `.env` 只会在 `AUTH_JWT_SECRET` 为空或过短时补一行随机值。
- 可重复执行：已装依赖、已建账号、已导入课程都复用（导入报告 `publish_unchanged: true`）。
- `Ctrl+C` 停止 API、worker 与前端；Neo4j 保留运行，停止用 `scripts/dev-down.sh`。
- 选项：`--live` 用真实大模型（见下）、`--personal` 进正式模式（等价于 `scripts/start.sh`，见下）、`--no-import` 跳过课程导入、`--no-open` 不开浏览器；`DEMO_WEB_PORT` 改前端端口。日志在 `.demo/logs/`。`--live` 与 `--personal` 互斥。
- 与手动步骤一样，后端进程从 `src/backend` 启动，相对的 `SQLITE_URL`/`STORAGE_DIR` 落在 `src/backend/storage/`，与下文手动方式共用同一份数据。
- 若 Neo4j 库此前用 `fake` 或真实向量建过，API 会因向量空间不一致拒绝启动（见第 3 节），此时换新库或运行 `scripts/reembed.py`。

### 一键启动，真实大模型（`--live`）

网页里没有「接入 API」的设置项：模型密钥只放在服务端 `.env`，由 worker 在抽取时调用。步骤：

1. 在 `.env` 填 `LLM_API_KEY=<DeepSeek 密钥>`；`LLM_BASE_URL`、`LLM_EXTRACTION_MODEL`、`LLM_CHAT_MODEL` 保持示例值（D-02a）。
2. `scripts/start-demo.sh --live`。脚本启动前检查主用四项，缺一项就退出；本次进程用 `LLM_MODE=live`。
3. 教师登录 → 课程 → 资料 → 上传 PDF/DOCX/TXT/Markdown；状态变为已完成后，到「审核」与「编辑图谱」查看草稿。

- 向量：`.env` 的 `EMBEDDING_MODE` 为 `online` 时照用，否则沿用演示向量（`local` 已不支持，会被配置校验拒绝并指出 `EMBEDDING_MODE`，见第 3 节与 ADR-081）。沿用演示向量时与演示课程同一向量空间，不必换库，问答阈值仍用 0.58。
- `--live` 不自动导入演示课程：首次导入会用真实模型抽取整套示例资料。已导入过的演示课程照常可用。
- macOS 上未设置 `SSL_CERT_FILE` 时，脚本用 `.venv` 里的 certifi 根证书（缺时自动安装），免得 HTTPS 调模型报证书错误。
- 每上传一份资料就会产生付费调用，受 `LLM_TASK_TOKEN_BUDGET`、`LLM_DAILY_TOKEN_BUDGET` 限制。

### 一键启动，正式模式（个人模型 API，`scripts/start.sh`）

正式运行用 `scripts/start.sh`（等价于 `scripts/start-demo.sh --personal`）：**每个教师与学生登录后在网页里填自己的模型 API**（ADR-080），不由部署者统一配一份密钥；向量是系统级的在线向量，key 由部署者提供（ADR-081）。该脚本不导入演示课程，也不使用演示模型。

```bash
scripts/start.sh                 # 默认自动打开浏览器
scripts/start.sh --no-open       # 不打开浏览器
```

启动前 `.env` 需要这些变量（缺任一则以中文原因退出，**不会静默落到演示模型或演示向量**）：

| 变量 | 取值 | 说明 |
| --- | --- | --- |
| `EMBEDDING_MODE` | `online` | `demo`／`local` 都会被拒绝 |
| `EMBEDDING_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 阿里云百炼兼容基址（2026-10-03 实测可用） |
| `EMBEDDING_API_KEY` | 部署者的向量 key | 与用户的模型 key 无关，不共享给学生 |
| `EMBEDDING_MODEL` | `text-embedding-v4` | 维度由 `EMBEDDING_DIMENSIONS`（`1024`）决定，建索引后不可换 |
| `MODEL_CREDENTIAL_KEY` | 32 字节 URL 安全 base64 | 加密用户模型密钥的根密钥；**空着时脚本自动写入随机值** |

- 脚本本次进程用 `LLM_MODE=personal`、`APP_ENV=development`，并**不读取** `LLM_BASE_URL`／`LLM_API_KEY`／`LLM_*_MODEL`。
- `MODEL_CREDENTIAL_KEY` 为空时脚本自动写入一行随机值，并提示「更换它会使已保存的个人模型配置失效」：换掉它，已保存的用户配置与未结束任务的快照密文都解不开，用户要重新填写（ADR-080，本轮不做轮换工具）。
- 未保存个人模型 API 的账号：上传资料与提问返回 409「需要配置模型」（`MODEL_CONFIG_REQUIRED`），**不回退**到演示或全站 key。教师与学生登录后先在「模型 API 设置」保存自己的 API。
- 「模型 API 设置」里的「关闭模型思考」（ADR-090）：对 DeepSeek 等支持 `thinking` 字段的接口，开启后每次生成请求追加 `thinking: {"type": "disabled"}`，抽取与问答通常明显更快、更省 token。默认关闭；其他接口可能不认这个字段，保存前先「测试连接」。开关在上传时随任务快照，进行中的任务不受之后的修改影响。
- 上线前用下面这条命令确认在线向量真的可用（只发 1 次请求，只打印模型、维度与耗时，不打印 key 与向量）：

```bash
.venv/bin/python scripts/check-embedding.py     # 期望：ok model=text-embedding-v4 dimensions=1024 seconds=…
```

  退出码：`0` 成功；`2` 配置非法或不是 `online`；`3` 调用失败（按错误分类排查：`auth` 看 key，`invalid_request` 看基址路径或 `dimensions`）。脚本自己读仓库根的 `.env`，不覆盖已在环境中的变量，也不需要先 `source .env`。

- 与演示入口一样：`Ctrl+C` 停止 API、worker 与前端，Neo4j 保留运行；日志在 `.demo/logs/`。
- 2026-10-03 在 macOS 冒烟通过：API `/health` 返回 `{"status":"ok","version":"0.1.0"}`、`GET /api/v1/me/model-config` 返回 `{"runtime_mode":"personal","configured":false}`、worker 日志无 `Invalid configuration`、前端返回 200（端口来自 `.env`：API 8001、前端 5174）。

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
| 正式（个人模型 API） | `personal` | `online` | 用户各自的模型额度 + 部署者的向量用量 | 教师与学生各自填自己的模型 API（ADR-080）。进程内没有全站模型客户端，未配置的账号被 409 拒绝 |
| 真实（服务端统一密钥） | `live` | `online` | 按量计费 | 部署者统一配一份 `LLM_*` 抽取与问答；需 `LLM_*`、`EMBEDDING_*` 变量（见 `docs/integrations.md`），付费调用须负责人同意 |

`EMBEDDING_MODE=local` **不可用**：枚举值保留只为给出明确的拒绝，配置校验阶段即失败并指出变量名，不再留到首次调用才报错（ADR-081：本轮不实现本地向量客户端）。

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
| 启动或 `scripts/start.sh` 报 `Invalid configuration: EMBEDDING_MODE`（或提示「`--personal` 需要在 .env 设 `EMBEDDING_MODE=online`」） | `.env` 写了 `EMBEDDING_MODE=local` | `local` 本轮不实现，改成 `online` 并填 `EMBEDDING_BASE_URL`／`EMBEDDING_API_KEY`／`EMBEDDING_MODEL`（ADR-081） |
| 上传资料或提问返回 409「需要配置模型」 | `LLM_MODE=personal` 下该账号还没保存自己的模型 API | 登录后在「模型 API 设置」保存服务地址与密钥；这是设计行为，不会回退到演示模型（ADR-080） |
| `scripts/check-embedding.py` 退出码 3，`auth` | 向量 key 无效或过期 | 换 `EMBEDDING_API_KEY`；key 属部署者，不共享给学生 |
| `scripts/check-embedding.py` 退出码 3，`connection`／`timeout` | 本机到向量供应商的网络不通 | 确认基址可达（如 `nc -z -G 8 dashscope.aliyuncs.com 443`）；不要改地址或换供应商来绕过，先修网络路径 |
| API 启动报向量空间不一致 | 换了 `EMBEDDING_MODE`/模型但沿用旧库 | 用新 Neo4j 库，或 `scripts/reembed.py` |
| 资料一直「排队中」 | worker 没在运行 | 启动 `python -m app.workers`；已排队任务会被领取 |
| 问答总是「资料未覆盖」 | 阈值与向量模式不匹配，或课程未发布 | 演示模式设 `QA_SIMILARITY_THRESHOLD=0.58`；先发布 |
| 学生看不到课程 | 未加入课程或课程从未发布 | 教师在「管理成员」添加学生并发布 |
| 发布返回 409 课程忙 | 另一写操作持有课程写锁 | 稍后重试；卡住超过租约时长（`PUBLISH_LEASE_SECONDS`）会自动回收 |
| 前端页面接口全部失败 | 开发服务器没反代到 API | 确认 API 在 8000，或设 `SMARTSKETCH_API_TARGET` 后重启 `npm run dev` |
| `dev-up.sh` 报端口 7474/7687 被占用，或容器停在 created、Docker 报 `port is already allocated` | 本机另有 Neo4j：另一个目录里的 SmartSketch 副本（Docker Desktop 上 `lsof` 只显示 `com.docker`）、Neo4j Desktop 或 Homebrew | 脚本会列出占端口的容器，`docker stop <容器名>` 停掉（不删数据）；非容器用 `lsof -nP -iTCP:7474 -iTCP:7687 -sTCP:LISTEN` 找；或在 `.env` 设 `NEO4J_HTTP_PORT`/`NEO4J_BOLT_PORT`（改 Bolt 端口时同步改 `NEO4J_URI`） |
| Neo4j 反复重启，日志有 `Invalid memory configuration`，或 `OOMKilled=true` | Docker 可用内存小于 1G 堆 + 512M 页缓存 | `.env` 设 `NEO4J_HEAP_MAX=512M`、`NEO4J_PAGECACHE=256M`，或调大 Docker Desktop 内存；再 `docker compose up -d --force-recreate neo4j` |
| Neo4j 反复重启，退出码 3，日志在 `Logging config in use` 后直接 `shutdown initiated by request`，没有 ERROR | Neo4j 初始化日志时出错（退出码 3 且无 ERROR 只有这一条代码路径）。2026-10-01 macOS 实例：之前反复崩溃后 `neo4j/data`、`neo4j/logs` 留下坏状态；原版镜像、APOC、内存设置单独测试都正常，换全新目录即启动 | 无数据要保留时 `docker compose down`，把 `neo4j/data`、`neo4j/logs` 挪走（`mv neo4j/data neo4j/data.bak-$(date +%s)`）后重启；用了下方 Docker 卷的改用 `docker compose down -v` |
| `dev-up.sh` 报「Neo4j 拒绝了 .env 里的 NEO4J_PASSWORD」 | `neo4j/data` 首次初始化时用的口令与现在 `.env` 不一致，改 `.env` 不会改库里的口令 | 改回原口令；或无数据要保留时 `docker compose down && mv neo4j/data neo4j/data.bak-$(date +%s)` 后重启 |

### 可选：数据与日志改存 Docker 卷

不想把 `neo4j/data`、`neo4j/logs` 放在项目目录里时，可在仓库根目录建 `docker-compose.override.yml`（已在 `.gitignore` 中，compose 自动读取），让 Neo4j 改用 Docker 管理的卷：

```yaml
services:
  neo4j:
    volumes:
      - neo4j-data:/data
      - neo4j-logs:/logs
volumes:
  neo4j-data:
  neo4j-logs:
```

然后 `docker compose down && scripts/start-demo.sh`。日志改用 `docker compose logs neo4j` 查看；`scripts/dev-down.sh --destroy` 会删除这两个卷。撤销：删掉该文件后重启，数据回到 `neo4j/data`。

## 9. 限制

- macOS、Windows 未实测；Windows 需自行处理 `set -a; source .env` 等 shell 写法（可用 WSL）。
- 方式 A（容器）在真实 Docker 守护进程上尚未跑通验证（K08 遗留）。
- 演示模型只按规则抽取中文定义句，不代表真实模型的抽取质量；赛题指标以 K02 真实模型判定为准。
- 融合（E08–E10）的自动合并阈值 D-08 未定，当前流水线为简化融合。
- 真实模型的性能（K04）需在本机付费运行后登记。


### 计划 C 思考开关上线与回滚（ADR-090）

先停止指定 API/worker，再用现有迁移入口升级017/018（每步自动备份）。核对个人配置开关默认关闭；保存时省略保留已存值。已有教师任务沿用任务创建时开关，新学生问答按配置revision刷新。

关闭开关即可停止追加供应商字段，但这不会追溯修改正在进行任务的快照；先等任务结束或按既有取消流程结束。代码退回018之前时，需停服务后恢复018前备份，或严格执行018中的删列/删迁移记录步骤（SQLite>=3.35）；不要仅删schema_migrations记录。恢复备份会丢失备份之后写入的数据，先另存当前库并经人工确认。关闭思考后的真实速度和质量尚待新测量；连接成功不等于供应商确实关闭推理。
