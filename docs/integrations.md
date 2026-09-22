# 外部集成、MCP 与环境变量

## 当前状态

当前骨架不绑定任何有密钥的外部服务；`.mcp.json` 保持空服务清单，确保可安全共享。新增服务前，在本文件记录用途、数据边界、环境变量、开发替代方案、调用方和回滚方式。

本地依赖由根目录 `docker-compose.yml` 编排（M0-05），只含 Neo4j 一个服务；SQLite 是嵌入式文件，不需要容器。

## 运行时环境变量

变量名与占位值维护在根目录 `.env.example`，本表与之逐项对齐。真实值只放本机 `.env` 或密钥管理系统；`.env` 已被 `.gitignore` 忽略。

### 应用运行

| 变量 | 用途 | 是否敏感 |
| --- | --- | --- |
| `APP_ENV` | 运行环境标识（development / test / production） | 否 |
| `API_HOST`、`API_PORT` | FastAPI 监听地址与端口 | 否 |
| `WEB_ORIGIN` | 允许的前端来源，用于 CORS | 否 |

### 本地落盘

| 变量 | 用途 | 是否敏感 |
| --- | --- | --- |
| `STORAGE_DIR` | 原始课程资料落盘根目录；默认 `./storage`，已被 `.gitignore` 忽略 | 否（目录内是真实课程资料，不得提交） |
| `SQLITE_URL` | SQLite 连接串，默认指向 `STORAGE_DIR` 下的库文件 | 否（不含凭据时） |

### Neo4j 连接（应用读取）

| 变量 | 用途 | 是否敏感 |
| --- | --- | --- |
| `NEO4J_URI` | Bolt 连接地址 | 否 |
| `NEO4J_USER` | Neo4j 用户名 | 否/视环境而定 |
| `NEO4J_PASSWORD` | Neo4j 密码；同时用于容器首次初始化，长度需 ≥ 8 | 是 |
| `NEO4J_DATABASE` | 目标数据库名，社区版固定单库，默认 `neo4j` | 否 |

### Neo4j 容器（仅 `docker-compose.yml` 插值，应用不读）

| 变量 | 用途 | 是否敏感 |
| --- | --- | --- |
| `NEO4J_IMAGE_TAG` | 镜像版本，固定次版本避免成员间 APOC 版本错配 | 否 |
| `NEO4J_BOLT_PORT`、`NEO4J_HTTP_PORT` | 映射到宿主机的 Bolt / Browser 端口 | 否 |
| `NEO4J_HEAP_MAX`、`NEO4J_PAGECACHE` | JVM 堆与页缓存上限，按本机内存调整 | 否 |

### 主用大模型（OpenAI 兼容）

| 变量 | 用途 | 是否敏感 |
| --- | --- | --- |
| `LLM_BASE_URL` | 主用供应商的 API 基址 | 否 |
| `LLM_API_KEY` | 主用供应商密钥 | 是 |
| `LLM_EXTRACTION_MODEL` | 知识点/关系抽取所用模型 | 否 |
| `LLM_CHAT_MODEL` | 课程问答所用模型 | 否 |

### 备用大模型

主模型不可用或被限流时切换。之所以是独立四项而非复用主用变量：备用供应商通常是另一家，基址、密钥和模型名都不同，单数的 `LLM_BASE_URL` 表达不了主/备两套。

| 变量 | 用途 | 是否敏感 |
| --- | --- | --- |
| `LLM_FALLBACK_BASE_URL` | 备用供应商的 API 基址 | 否 |
| `LLM_FALLBACK_API_KEY` | 备用供应商密钥 | 是 |
| `LLM_FALLBACK_EXTRACTION_MODEL` | 备用抽取模型 | 否 |
| `LLM_FALLBACK_CHAT_MODEL` | 备用问答模型 | 否 |

### 调用约束

| 变量 | 用途 | 是否敏感 |
| --- | --- | --- |
| `LLM_REQUEST_TIMEOUT_SECONDS` | 单次模型调用超时；超时计入失败并触发重试/切备用 | 否 |
| `LLM_MAX_CONCURRENCY` | 并发调用上限，由信号量控制以适配供应商限流 | 否 |
| `LLM_MAX_RETRIES` | 单次调用的重试次数，耗尽后切换备用模型 | 否 |

### 向量模型

与对话模型独立选型：向量维度一旦建索引就固定，不能跟着对话模型一起换，因此单独一组变量。

| 变量 | 用途 | 是否敏感 |
| --- | --- | --- |
| `EMBEDDING_BASE_URL` | 向量模型供应商的 API 基址，可与 `LLM_BASE_URL` 不同 | 否 |
| `EMBEDDING_API_KEY` | 向量模型供应商密钥 | 是 |
| `EMBEDDING_MODEL` | 向量模型名 | 否 |
| `EMBEDDING_DIMENSIONS` | 向量维度，**必须与所选模型一致**，且与 Neo4j 向量索引定义一致；改动需重建索引 | 否 |

## 本地依赖环境

### 前置条件

- 任意可跑 compose 文件的容器运行时：Docker Desktop、OrbStack 或 Podman。仓库不绑定具体产品，脚本会依次尝试 `docker compose`、`docker-compose`、`podman-compose`。
- 首次启动需要网络：Neo4j 镜像会按 `NEO4J_PLUGINS` 拉取与自身版本匹配的 APOC Core。

### 首次初始化

```bash
cp .env.example .env
```

然后至少改一处：把 `NEO4J_PASSWORD` 换成本机密码（长度 ≥ 8）。该值同时用于容器首次初始化和应用连接，两处必须一致。**首次启动后再改密码不会生效**——容器只在数据目录为空时初始化凭据，改密码需要先按下面的销毁步骤清空 `neo4j/data`。

### 启动

```bash
./scripts/dev-up.sh
```

脚本依次完成：创建 `STORAGE_DIR`、`neo4j/data`、`neo4j/logs`（三者都在 `.gitignore` 忽略范围内）→ `compose up -d neo4j` → 轮询健康检查 → 自动执行 APOC 校验。成功后输出 Browser 地址与 Bolt 地址。

SQLite 不需要任何启动步骤：后端进程按 `SQLITE_URL` 直接打开文件，目录由上面的脚本建好。

### 验证 APOC 已加载

APOC 是 **M1-03 知识融合的硬前置**：该任务要用 `apoc.refactor.mergeNodes`，而 Neo4j 社区版不自带 APOC。`dev-up.sh` 会自动跑一次，也可单独执行：

```bash
./scripts/check-apoc.sh
```

脚本在容器内执行 `RETURN apoc.version()`，打印版本号即通过，非零退出即未装载。排查顺序：

```bash
docker compose ps                        # 容器是否 healthy
docker compose logs neo4j | grep -i apoc # 插件下载是否失败（常见原因是首次启动无网络）
```

### 停止

```bash
./scripts/dev-down.sh
```

停止容器并保留数据，重新 `./scripts/dev-up.sh` 即可继续。

### 销毁数据（回滚）

```bash
./scripts/dev-down.sh --destroy           # 删除 Neo4j 数据卷与 neo4j/data、neo4j/logs
./scripts/dev-down.sh --destroy-storage   # 以上 + 删除 STORAGE_DIR（SQLite 业务库与已上传资料）
```

两条都要求交互式输入大写 `DESTROY` 才执行。

> **风险**：不可恢复，且仓库不备份这些目录。`--destroy` 会清掉全部图谱、任务与图谱版本；`--destroy-storage` 还会清掉 SQLite 里的课程、进度、问答记录以及所有已上传的原始课程资料。用于换密码、换镜像版本或需要干净重建的场景；日常停机用不带参数的 `./scripts/dev-down.sh`。销毁后下次启动会重建空实例并重新下载 APOC，因此需要网络。

## 计划集成

| 集成 | 用途 | 接入前置条件 |
| --- | --- | --- |
| Neo4j | 课程知识图谱、向量索引、前置关系遍历 | 已由 `docker-compose.yml` 定义本地实例；生产部署与备份策略待定 |
| APOC | `apoc.refactor.mergeNodes` 等融合能力（M1-03） | 已随镜像装载并由 `scripts/check-apoc.sh` 校验 |
| OpenAI 兼容 LLM API | 抽取、问答、关键词 | 确认主/备供应商、预算、重试与脱敏策略（D-02） |
| 向量模型 API | 来源片段向量化与检索 | 确认模型与维度，维度定稿后才能建 Neo4j 向量索引 |
| 文档解析库 | PDF/DOCX/TXT/Markdown 解析 | 确认页码/标题定位保留方式 |
