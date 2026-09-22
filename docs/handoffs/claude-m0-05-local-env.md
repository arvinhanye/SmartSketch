# Claude 交接：M0-05 本地依赖环境

- **状态**：**BLOCKED**（交付物齐全，APOC 实测未完成）
- **日期**：2026-09-22
- **范围**：新建 `docker-compose.yml` 编排 Neo4j 5 社区版并装载 APOC，补齐 `.env.example` 缺失变量，同步 `docs/integrations.md` 环境变量表与本地启动/停止/销毁流程，新增三个开发脚本。

## 已交付

| 文件 | 改动 |
| --- | --- |
| `docker-compose.yml` | 新建。Neo4j 5.26 社区版，`NEO4J_PLUGINS='["apoc"]'`，端口与凭据读 `.env`，数据绑定到已忽略的 `neo4j/data`、`neo4j/logs`；后端/前端服务以注释占位 |
| `.env.example` | 12 → 30 个变量：新增 `STORAGE_DIR`、`NEO4J_DATABASE`、Neo4j 容器 5 项、`EMBEDDING_*` 4 项、`LLM_FALLBACK_*` 4 项、`LLM_REQUEST_TIMEOUT_SECONDS`/`LLM_MAX_CONCURRENCY`/`LLM_MAX_RETRIES` |
| `docs/integrations.md` | 环境变量表按组重写，与 `.env.example` 30 项逐项对齐；新增「本地依赖环境」（前置条件、首次初始化、启动、APOC 验证、停止、销毁回滚） |
| `scripts/dev-up.sh` | 新建。建目录 → `compose up -d neo4j` → 轮询健康检查 → 自动跑 APOC 校验 |
| `scripts/check-apoc.sh` | 新建。容器内执行 `RETURN apoc.version()`，失败即非零退出 |
| `scripts/dev-down.sh` | 新建。默认保留数据；`--destroy` / `--destroy-storage` 需输入大写 `DESTROY` |
| `scripts/_dev-common.sh` | 新建。共用的 compose 命令探测与 `.env` 加载 |
| `docs/tasks.md` | M0-05 行改为 BLOCKED 并附阻塞原因与解除方式 |

未触碰 `scripts/verify.sh`、`src/`、`docs/decisions.md`、`.gitignore`。

## 关键决定

1. **APOC 用 `NEO4J_PLUGINS` 而不是挂载 `neo4j/plugins`**。`.gitignore` 只忽略了 `neo4j/data/` 与 `neo4j/logs/`，绑定 plugins 目录会在工作区留下未忽略的新目录，而 `.gitignore` 不在本任务的可改文件内。改用镜像自带的插件装载机制，由镜像拉取与自身版本匹配的 APOC Core——代价是首次启动需要网络，已写进文档。
2. **镜像固定为 `5.26-community`（LTS）**，不用 `5-community` 浮动标签。成员间拉到不同 5.x 会导致 APOC 版本错配，这类问题排查成本远高于手动升版本。
3. **数据卷路径写死不做成变量**。端口和凭据按要求读环境变量，但 `./neo4j/data`、`./neo4j/logs` 硬编码，避免有人把数据目录指到会被提交的位置。
4. **只放开 `apoc.*` 的 unrestricted，不设置 procedures allowlist**。allowlist 默认放行全部；一旦设成 `apoc.*` 会连带挡掉向量检索要用的 `db.index.vector.*`。
5. **SQLite 不进 compose**。它是嵌入式文件，本地只需 `STORAGE_DIR` 存在，由 `dev-up.sh` 创建。
6. **后端/前端服务只写注释占位**。M0-02 / M0-03 尚未初始化，仓库里没有 Dockerfile 也没有 `package.json` / `pyproject.toml`，写成启用状态会让 `docker compose up` 直接失败。

## 已运行命令与真实结果

```text
docker --version / docker compose version / docker-compose  → command not found
podman / colima / nerdctl / lima                            → 均不存在
/Applications/Docker.app 、 /Applications/OrbStack.app       → No such file or directory

python3 -c "yaml.safe_load(open('docker-compose.yml'))"
  → YAML OK — services: ['neo4j']
    image: neo4j:${NEO4J_IMAGE_TAG:-5.26-community}
    volumes: ['./neo4j/data:/data', './neo4j/logs:/logs']
    plugins: ["apoc"]

bash -n scripts/_dev-common.sh scripts/dev-up.sh scripts/dev-down.sh scripts/check-apoc.sh
  → passed

./scripts/verify.sh                       → Scaffold verification passed.  [exit=0]
  （工作区不存在 .env，未填写任何密钥）

git check-ignore -v neo4j/data/x          → .gitignore:35:neo4j/data/
git check-ignore -v neo4j/logs/x          → .gitignore:36:neo4j/logs/
git check-ignore -v storage/x             → .gitignore:33:storage/
git check-ignore -v .env                  → .gitignore:2:.env
  （建目录探测后 git status 无新增未忽略项，探测目录已清理）

.env.example ↔ docs/integrations.md 对齐  → 30 个变量，文档未收录 0 项，文档多出 0 项
```

### APOC 验证：未通过（真实输出）

```text
$ ./scripts/dev-up.sh
错误：本机没有可用的容器编排命令（docker compose / docker-compose / podman-compose）。
      安装 Docker Desktop、OrbStack 或 Podman 后重试。
      本仓库不依赖任何具体产品，只要求命令行能跑 compose 文件。
[exit=1]

$ ./scripts/check-apoc.sh
错误：本机没有可用的容器编排命令（docker compose / docker-compose / podman-compose）。
      安装 Docker Desktop、OrbStack 或 Podman 后重试。
      本仓库不依赖任何具体产品，只要求命令行能跑 compose 文件。
[exit=1]
```

**`RETURN apoc.version()` 没有跑起来，没有版本号可报。** 这是 M0-05 标 BLOCKED 的唯一原因。

## 阻塞原因与解除方式

本机未安装任何容器运行时：Docker Desktop、OrbStack、Podman、colima、nerdctl 全部不存在。

另外排除过两条替代路径，都不可行：

- `/Applications/Neo4j Desktop 2.app` 已安装，但从未运行过（无 `~/Library/Application Support/Neo4j Desktop`），bundle 内不含 `neo4j` / `cypher-shell` / APOC jar——实例和插件都要首次启动时通过图形界面下载，无法在本会话中无人值守验证。
- 本机 JDK 为 Temurin 25，而 Neo4j 5 支持 Java 17 / 21，手动跑 tarball 也起不来；且在用户机器上装 JDK 与 Neo4j 超出本任务范围。

**解除方式**：在装有容器运行时的机器上执行

```bash
cp .env.example .env    # 改掉 NEO4J_PASSWORD
./scripts/dev-up.sh     # 末尾会自动跑 check-apoc.sh
```

把 `RETURN apoc.version()` 的真实输出补进本文件，并把 `docs/tasks.md` 的 M0-05 改为 DONE。在此之前 **M1-03 不具备开工条件**。

## API / 数据 / 配置影响

- 新增 18 个环境变量，全部只写变量名与无敏感占位值；`LLM_API_KEY`、`LLM_FALLBACK_API_KEY`、`EMBEDDING_API_KEY`、`NEO4J_PASSWORD` 在文档中标为敏感。仓库内无任何真实密钥。
- `EMBEDDING_DIMENSIONS` 与 Neo4j 向量索引定义强耦合：建索引后改这个值需要重建索引，已写进文档。
- 无数据库迁移，无契约变更（本任务不触碰 `src/contracts/`）。
- `docker compose` 的健康检查命令里会内联 `NEO4J_PASSWORD`，因此该密码对 `docker inspect` 可见。它本来就通过 `NEO4J_AUTH` 存在于容器环境中，未引入新的暴露面，但不要把生产密码放进本地 `.env`。

## 销毁数据的回滚步骤

```bash
./scripts/dev-down.sh                     # 停止，保留数据（日常用这条）
./scripts/dev-down.sh --destroy           # 删除 Neo4j 数据卷与 neo4j/data、neo4j/logs
./scripts/dev-down.sh --destroy-storage   # 以上 + 删除 STORAGE_DIR（SQLite 与已上传资料）
```

两条 `--destroy` 均要求交互式输入大写 `DESTROY`，脚本只删仓库内的固定相对路径。

> **风险**：不可恢复，仓库不备份这些目录。`--destroy` 清掉全部图谱、任务与图谱版本；`--destroy-storage` 还会清掉课程、学习进度、问答记录和所有已上传的原始课程资料。适用场景仅限：改 Neo4j 密码（凭据只在数据目录为空时初始化）、换镜像大版本、需要干净重建。销毁后首次启动会重新下载 APOC，需要网络。
>
> 撤回本任务的代码改动则无需销毁数据：逐个还原上表文件并删除新增脚本即可；不要使用全局重置或清理命令。

## 风险与未完成项

1. **compose 文件从未真正启动过。** YAML 语法、脚本语法、`.gitignore` 覆盖和变量对齐都已实测，但镜像标签是否可拉取、健康检查是否如期转 healthy、APOC 是否装载成功，全部未经运行时验证。第一个有容器环境的人可能仍需微调。
2. `dev-up.sh` 的健康检查轮询依赖 `compose ps --format json` 的输出里含 `"Health"` 字段。该字段在 Docker Compose v2 存在，podman-compose 未必兼容；用 podman 的成员可能需要改这段。
3. 首次启动必须联网下载 APOC。离线环境需要改为预置 jar，届时要同时改 `.gitignore`（不在本任务可改范围）。
4. `EMBEDDING_DIMENSIONS=1024` 只是占位值，必须与实际选定的向量模型一致；模型选型仍挂在 D-02。

## 下一位 Agent 的首个动作

- **有容器环境的成员（解除 M0-05）**：`cp .env.example .env` → 改 `NEO4J_PASSWORD` → `./scripts/dev-up.sh`，把 APOC 版本号回填本文件并把 M0-05 转 DONE。
- **后端 Agent（M0-03）**：`.env.example` 已提供全部连接变量，可直接按 `NEO4J_URI` / `NEO4J_DATABASE` / `SQLITE_URL` 接线；补全 `docker-compose.yml` 里注释掉的 `backend` 服务。
- **数据/AI Agent（M1-03）**：在 `./scripts/check-apoc.sh` 通过之前不要开工，`apoc.refactor.mergeNodes` 没有 APOC 就不存在。

---

> **S-03 后路径变更**：本文提到的 `docs/decisions.md` 与 `docs/tasks.md` 已拆成 `docs/decisions/` 与 `docs/tasks/`。上文表格是当时的真实记录，不做改写；后续操作请按新路径，见 `docs/handoffs/claude-s03-collab-restructure.md`。
