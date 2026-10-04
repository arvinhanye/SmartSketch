# A10 一周参赛冲刺 · 精简设计规格

- 日期：2026-10-02；作者：Claude；任务：L00（见 `docs/tasks.md`）。
- 状态：**第 11 节四项已由用户同意（2026-10-02）**；实施计划待用户确认执行方式。计划确认前不写业务代码、不改契约/迁移/上位规则、不调用付费模型。
- 基线：`6ff8a8dfa9e0ce26defef01ae6b3c9ff2f03e620`，分支 `claude/smartsketch-contest-sprint-77644f`，本工作区起始干净。
- 依据：Codex 交接 prompt 与两份审查（只存在于 Codex 工作区，未提交，本规格按绝对路径引用、不复制不改写）：
  - `/Users/arvinhan/.codex/worktrees/e92f/SmartSketch/docs/handoffs/codex-claude-contest-sprint-prompt-2026-10-02.md`
  - `/Users/arvinhan/.codex/worktrees/e92f/SmartSketch/docs/reviews/codex-product-readiness-2026-10-02.md`（R01–R13）
  - `/Users/arvinhan/.codex/worktrees/e92f/SmartSketch/docs/reviews/codex-contest-scope-2026-10-02.md`
- 未做：赛题 DOCX 原文我没有独立复核，范围沿用 Codex 复核报告；统一评分标准附件仍缺，不推断权重。

## 1. 范围确认

**教师闭环**：登录 → 建/选课程 → 配置个人模型 API 并测试 → 上传 PDF/Markdown → 任务进度 → 草稿 → 增删改节点与关系 → 发布 → 学生可见。

**学生闭环**：登录 → 进入已发布课程 → 浏览/搜索图谱 → 定义与来源 → 标记掌握 → 推荐与先修路径可视化 → 配置个人模型 API → 提问 → 有依据回答 → 打开引用、定位图谱节点。

**必保（赛题）**：两种格式（PDF + Markdown 为验收入口，TXT/DOCX 保留）；一章 ≥20 个 AI 知识点、≥3 种关系；实体与关系人工抽样准确率各 ≥70%（按原始 AI 输出统计）；图谱缩放/拖拽/详情/来源；教师修正与发布；掌握持久化与推荐路径可视化；课程有据问答（未覆盖与故障分开）；两门课隔离；60 秒 / 15 秒实测；九类材料。

**不做**：AI 自动出题、题库、判分、错题与成绩；跨课程融合；完整融合消歧（E08–E10）与补漏默认接入（R05 只如实记录）；OCR、PPT 输入；3D、原生移动端、SSO、计费、多模型收藏、供应商自动切换；失败任务重试端点（沿用重新上传）。问答不改掌握进度。

**顺序**：功能与交互闭环先行；轻量美化在第 6 天，且只在两条闭环验收后开始。画布可读、按钮有效、状态与错误引导属于功能，不延后。

## 2. 已核验的现状（只读）

| 事实 | 位置 |
| --- | --- |
| worker 在循环前按全局环境装配一次模型客户端，所有任务共用 | `src/backend/app/workers/runner.py:68-80,140-145` |
| 问答服务按全局环境构建并缓存在 `app.state`，所有用户共用客户端与熔断状态 | `src/backend/app/api/chat.py:52-66` |
| `processing_tasks`、`materials` 没有创建者列；`model_calls` 没有用户列，日预算全站合计 | `migrations/003_tasks.sql`、`001_base.sql`、`repositories/model_calls.py` |
| 模型客户端只发 POST、不跟随重定向，有超时与 8 MiB 响应上限；URL 只做语法校验，不查目的地址 | `services/ai/compatible.py:169-193,830-852` |
| `EMBEDDING_MODE=local` 通过配置校验，但被装配成要求在线地址与 key 的客户端（R03） | `config.py:174`、`services/ai/factory.py:45-52` |
| 向量只在发布与问答时调用，属系统级；向量空间变化被启动门禁拒绝 | `api/versions.py:51`、`api/chat.py:61`、`services/startup.py:25-40` |
| 问答无历史时不调用改写，只有 1 次向量 + 1 次流式生成；15 秒是硬截止，超时返回错误 | `services/qa/rewrite.py:361`、`services/qa/chat.py:101-128` |
| `chat_logs` 已记录完整耗时与首字耗时 | `migrations/014_chat_logs.sql` |
| 历史真实抽取：16 块、35 次调用、输出 68172 token、并发 4、约 329 秒 | `evaluation/reports/extraction-accuracy.md:70-72` |
| 契约 `SourceRef` 已含可选 `text`、`page`、`section_path`，没有资料文件名 | `src/contracts/api.v1.yaml:2125-2154` |
| 推荐响应是有序列表加理由，不含路径/边 | `api.v1.yaml:3122` 起 |
| 本机已有 Neo4j 容器（7687）与主检出的 API（8000）、前端（5173）在运行 | `docker ps`、`lsof` |
| 本工作区没有虚拟环境与 `node_modules`；基础档门禁在系统 Python 下 exit 0 | `ls`、`./scripts/verify.sh` |

## 3. 个人模型配置

### 3.1 方案选择

任务如何绑定凭据，三种做法：

- **A（采用）任务级加密快照**：建任务时把当时的地址、模型名和密文复制到该任务的绑定行。改配置不影响已排队任务；清除配置时一并作废未结束任务的快照。worker 重启后从 SQLite 读回，不依赖内存。
- B 追加式配置版本表，任务引用版本号：语义等价，但清除时要处理多版本残留，表与查询更多。
- C 只绑定配置 ID：改配置会让排队任务静默换模型，交接文件已明确否决。

### 3.2 运行模式

`LLM_MODE` 新增取值 `personal`，作为正式 Web 入口的模式：

- `personal`：没有任何全站大模型客户端。教师任务用任务快照，学生问答用本人配置。未配置时拒绝并给出下一步，**不回退**到 demo 或全站 key。`LLM_*` 的地址、key、模型名变量在此模式下不读取。
- `demo` / `fake`：保持现状，供演示与测试；界面常驻「演示模式」标识，个人配置页说明当前不生效。
- `live`：保留给评测脚本，不作为 Web 正式入口。
- `APP_ENV=production` 允许 `personal` 与 `live`，仍禁止 `fake`/`demo`。

每个用户一份配置：地址、模型名、密钥。同一模型名同时用于抽取与问答。只支持 OpenAI 兼容的 Chat Completions 协议；「已验证」只写真正测过的服务（见第 11 节问题 2）。

### 3.3 数据模型（迁移 `015_user_model_configs.sql`，前向迁移 + 迁移前自动备份，沿用现有机制）

- `user_model_configs`：`user_id` 主键外键、`base_url`、`model`、`key_ciphertext`、`key_nonce`、`key_hint`（末 4 位）、`version`（每次保存 +1）、`updated_at`、`last_test_at`、`last_test_ok`、`last_test_error_class`。
- `task_model_bindings`：`task_id` 主键外键、`user_id`、`config_version`、`base_url`、`model`、`key_ciphertext`、`key_nonce`（可空）、`scrubbed_at`、`scrub_reason`（`terminal` / `revoked`）。与资料、任务在同一个 SQLite 事务内写入。
- `processing_tasks.created_by`、`model_calls.user_id`：可空新列，历史行为空。

回滚：停 API 与 worker，恢复 `backups/*-before-015.sqlite`；迁移文件内附手工 `ROLLBACK` 语句。不涉及 Neo4j。

### 3.4 加密与泄漏面

- AES-256-GCM，关联数据为所有者的 `user_id`，密文挪到别的用户名下即无法解开。任务快照直接复制所有者的密文，上传路径不解密。
- 根密钥来自环境变量 `MODEL_CREDENTIAL_KEY`（32 字节）。`personal` 模式下 API 与 worker 启动时缺失或过短即拒绝启动，与 `AUTH_JWT_SECRET` 同样处理。根密钥更换后旧配置不可解，用户需重新填写；本周不做轮换工具。
- **新增依赖** `cryptography`（锁定版本）。标准库没有认证加密，不自造。
- 密钥只在保存与测试请求体中出现一次。不进响应、日志、`model_calls`、任务 payload、SSE、前端 `localStorage` 或 store 持久化。读取接口只返回 `key_hint`。
- 改地址时必须重新提交密钥，避免已存密钥被改送到新主机。

### 3.5 接口（先改 `src/contracts/api.v1.yaml` 与 `errors.v1.md`，再生成 DTO）

| 操作 | 说明 |
| --- | --- |
| `GET /api/v1/me/model-config` | 返回 `runtime_mode`、`configured`、`base_url`、`model`、`key_hint`、`version`、最近测试结果；不返回密钥 |
| `PUT /api/v1/me/model-config` | 保存或修改；地址经 3.7 校验；不强制先测试通过 |
| `DELETE /api/v1/me/model-config` | 清除并作废本人未结束任务的快照 |
| `POST /api/v1/me/model-config/test` | 用请求体里的值或已存值发 1 次最小对话请求（输出上限 1 token，费用可忽略，界面注明）；每用户每分钟 5 次；只返回 `ok`、错误分类、耗时 |

全部只作用于当前登录用户，路径不带用户 ID，不存在越权读写他人的入口。非 `personal` 模式下若服务端未配置根密钥，读取返回未配置，写入与测试返回 503（`details.reason = credential_store_disabled`）。

错误：新增 `MODEL_CONFIG_REQUIRED`（409，`personal` 模式下未配置即上传或提问）。地址被拒用 `VALIDATION_ERROR` 加 `details.reason`。供应商拒绝密钥沿用 `LLM_UNAVAILABLE` 加 `details.reason = auth`，前端据此提示「检查你的 API 配置」。供应商的请求头与响应体永不回显。

### 3.6 任务绑定语义

| 事件 | 行为 |
| --- | --- |
| 上传 | `personal` 模式下未配置 → 409，不落资料、不建任务；已配置 → 建任务并写快照 |
| 修改配置 | 新任务用新值；已排队或进行中的任务继续用旧快照，界面注明 |
| 清除配置 | 本人未结束任务的快照密文置空（`revoked`）；这些任务在下一个块或小节的尝试开始前失败，`LLM_UNAVAILABLE` + `details.reason = credential_revoked`；按现有规则重新上传 |
| 供应商侧作废旧 key | 任务按鉴权失败终止，不重试、不切换别的 key |
| worker 重启或租约接管 | 从 SQLite 读回快照继续，行为不变 |
| 任务到 `awaiting_review` / `failed` / `cancelled` | 快照密文置空（`terminal`），只留地址、模型名、版本号供审计；worker 每轮维护步骤兜底清理 |

实现：`run_pipeline_once` 的 `toolkit` 参数改为「按租约取工具包」的解析器。`personal` 模式下按任务快照构建客户端与独立的 `ModelCallPolicy`；`demo`/`fake` 仍返回现有全局工具包。状态机与 SSE 语义不动。

### 3.7 问答隔离

- 共享部分（Neo4j 仓储、向量适配器）继续缓存；改写器与生成器按「用户 + 配置版本」取 `ModelCallPolicy`，进程内小容量缓存。熔断状态按用户隔离，一人的坏 key 只影响自己。
- `CallAttribution` 增加 `user_id`，写入 `model_calls`；`personal` 模式下日预算按用户统计，任务预算不变。
- 未配置 → `MODEL_CONFIG_REQUIRED`；学生永不使用教师的 key。
- 提交期间前端禁用发送按钮，防止重复计费（已有行为先核验，缺则补）。

### 3.8 出站地址防护

- 只接受 `https`；不允许内嵌凭据、查询串、片段。
- 解析域名后逐个检查地址，任何一个不是公网地址即拒绝：回环、私网、链路本地（含云元数据 169.254.169.254）、CGNAT、组播、保留段、IPv6 ULA 与 IPv4 映射地址。
- 连接时钉住已检查的 IP，TLS 的 SNI 与证书校验仍用原域名，检查与连接之间的 DNS 变化不生效。保存、测试、每次建连都执行。
- 不跟随重定向（3xx 按错误处理，现有行为）；沿用现有超时与响应上限；并发沿用 `LLM_MAX_CONCURRENCY`。
- 仅测试用：`MODEL_ENDPOINT_ALLOW_PRIVATE=1` 放行回环，供本地假供应商做端到端测试；`APP_ENV=production` 下设置即拒绝启动。

文档与模型输出按不可信数据处理的既有措施（ADR-068 防注入、`ChatMarkdown` 渲染）在 L15 用恶意样本回归，不重写。

### 3.9 需要你确认的规则调整

现有规则与个人配置冲突，建议改写如下，批准后写入 ADR-080 并同步 `AGENTS.md`、`docs/architecture.md`、`docs/integrations.md`、`.env.example`：

- `AGENTS.md` §4「配置只能从环境变量读取」→「基础设施与系统级配置只能从环境变量读取；用户个人模型凭据例外，经受控个人配置接口写入，服务端加密存储，根密钥来自环境变量」。
- `AGENTS.md` §6「密钥只存个人本地环境」→ 增加同一例外，并写明个人凭据不进日志、仓库、前端持久存储。

## 4. 向量方案

**建议：系统级在线向量，本周不实现本地向量。**

- `EMBEDDING_MODE=online`，沿用 D-02c 候选：阿里云百炼 `text-embedding-v4`、1024 维、每批 10 条。客户端已实现，本周首次做真实联调。
- 向量 key 属部署者，走环境变量。用户更换生成模型不影响向量空间。
- 共享检索成本由部署者承担：每次发布对文本块与知识点做一次向量化，每次提问 1 次查询向量。实际 token 用量在 L02 基线中记录。
- R03 处理：`EMBEDDING_MODE=local` 改为配置校验阶段明确拒绝（「本版本未实现本地向量」），文档同步，不再假装支持。写入 ADR-081 并签收 D-02c。
- 不动现有库：冲刺使用独立的 SQLite、`STORAGE_DIR` 和独立 Neo4j 容器（不同 compose 项目名与端口）。现有演示库保留，回滚即切回原环境变量。

备选是本地 `bge-small-zh`：不需要 key，但要新增推理依赖、下载模型，并处理 512 token 截断与现有约 1500 字分块的冲突。一周内风险高，不建议。

## 5. 性能测量

**抽取（目标 ≤60 秒）**

- 计时边界：服务端收到上传请求 → 任务写入 `awaiting_review`。含排队、解析、分块、抽取、直通融合、入库。同时给出分阶段耗时与 `model_calls` 的次数、token、单次延迟。
- 记录：文件格式、页数、字数、块数、模型、并发、机器、网络、日期。只计首次真实处理，使用未处理过的资料，不计缓存命中。
- 现有证据的含义：329 秒 / 35 次调用 / 并发 4，折合单次调用约 37 秒、输出约 1950 token。实体与关系两阶段串行，即使并发拉满，总时长也不低于两个阶段各自最慢的一次调用。**只提高并发到不了 60 秒。**
- 优化顺序，每步重测耗时并复核准确率：① 提高并发；② 小节内实体完成即启动该小节关系抽取，不等全部块；③ 压缩单次输出（证据引文长度、冗余字段、块大小）；④ 换更快的模型；⑤ 单阶段联合抽取（已有消融数据，质量有代价，最后考虑）。
- 不承诺达标。未达标时如实报告差距与条件，不缩成无代表性的资料。

**问答（目标 ≤15 秒）**

- 计时边界：服务端收到请求 → `done` 事件；首字耗时单列。数据取自 `chat_logs`，前端秒表抽样交叉核对。
- 对整份问答测试集报告 p50、p95、最大值和超时次数。超时按失败计，不计入「已回答」。

## 6. 前端闭环修复

| 项 | 做法 |
| --- | --- |
| 个人配置页（R01） | 新路由，教师学生共用：地址、模型名、密钥、测试、保存、清除；只显示脱敏状态。上传页与问答页在未配置时显示引导并禁用提交 |
| 模式标识（R01/R02） | 读 `runtime_mode`，演示模式常驻标识 |
| 来源查看（R04） | 两个图谱页接上 `locateSource`，侧栏显示资料文件名、页码或章节、原文片段。契约给 `SourceRef` 与问答引用加可选 `document_name`，学生无需资料列表权限 |
| 图谱可读性（R06） | 初始视图设最小可读缩放并聚焦，不再整图缩成一条；未选中时收起右栏；高级筛选折叠；搜索后定位并选中。不重写 G6 |
| 问答到图谱（R08） | 知识点按钮跳转 `…/graph?kp=<id>`，图谱页消费该参数并选中节点 |
| 学习路径可视化 | 推荐节点显示顺序序号；选中一条推荐时高亮它的先修链（已掌握/未满足）与学完即解锁的后继及对应 `PREREQUISITE` 边，其余淡化；另给一行「已掌握 → 下一步 → 之后解锁」。数据来自现有图与推荐响应，前端适配层纯函数实现，不新增后端算法 |
| 导航与概览（R09/R07/R10） | 侧栏按当前课程内角色出导航；课程概览显示当前阶段与下一步，去掉重复入口；空态写清「教师按用户名添加」的入课步骤 |
| 推荐文案（R11） | 重要度/难度为缺省 0.5 时不展示成测量值，理由以先修事实为主 |

## 7. 原子任务候选

编号沿用字母序列的下一个字母 L。每项实施前在 `docs/tasks.md` 认领并写输入、输出、风险、验证命令；缺陷先写复现测试。

| ID | 日 | 内容 | 主要文件范围 | 依赖 | 验收 |
| --- | --- | --- | --- | --- | --- |
| L01 | 1 | 隔离环境与基线：按锁文件建虚拟环境、`npm ci`、独立 Neo4j；跑三档门禁并记录 | 无业务文件 | — | 三档门禁真实结果入交接 |
| L02 | 1 | 真实基线：一章资料经网页上传的抽取耗时与问答耗时（需问题 2 的凭据与预算） | `evaluation/reports/` | L01 | 带条件的实测数字 |
| L03 | 1 | ADR-080/081、规则与规格、契约（配置接口、错误码）、DTO 生成；`document_name` 的契约改动随 L12 | `docs/`、`specs/`、`src/contracts/`、`AGENTS.md` | 本规格获批 | 契约门禁通过 |
| L04 | 2 | 迁移 015、加密服务、配置与快照仓储 | `migrations/`、`repositories/`、`services/` | L03 | 加解密、关联数据、回滚测试 |
| L05 | 2 | 出站地址校验与钉 IP 传输 | `services/ai/` | L03 | 内网、元数据、重定向、DNS 变化用例 |
| L06 | 2 | 配置接口四个操作 | `api/`、`schemas/`、`services/` | L04、L05 | 越权、脱敏、无泄漏、限流用例 |
| L07 | 2–3 | `personal` 模式、上传绑定、worker 按任务取工具包、清除与终态清理 | `config.py`、`workers/`、`services/materials.py` | L04 | 改/清配置、重启接管、两教师不同 key 用例 |
| L08 | 3 | 问答按用户取策略、`model_calls.user_id`、按用户日预算 | `api/chat.py`、`services/qa/`、`services/ai/policy.py` | L04 | 两用户并发、一人坏 key 不影响另一人 |
| L09 | 3 | 在线向量联调、`local` 明确拒绝、正式启动入口与模式说明 | `config.py`、`factory.py`、`scripts/` | L01 | 真实检索可用；启动脚本不再静默切 demo |
| L10 | 3 | 前端配置页、未配置引导、模式标识 | `src/frontend/src/` | L06 | 组件测试 + 页面到接口断言 |
| L11 | 3 | 教师闭环走通并修阻断项：PDF 与 Markdown 上传 → 进度 → 草稿 → 修正 → 发布 | 按发现的缺陷定 | L07、L09、L10 | 两种格式各一次真实发布；E2E |
| L12 | 4 | 来源查看（R04） | 图谱两页、`KnowledgeDetail`、后端来源字段 | L03 | 页面可见文件名、位置、片段；权限用例 |
| L13 | 4 | 图谱可读性（R06）与问答节点定位（R08） | `graph/`、图谱页、`ChatView` | — | 20+ 节点可读可选；跳转选中正确节点 |
| L14 | 4 | 学习路径可视化、推荐文案（R11） | `useLearning`、适配层、`Recommendations` | — | 标记掌握后顺序与高亮边更新；多前置用例 |
| L15 | 5 | 课程角色导航与概览（R09/R07/R10）；边界与安全回归；两课程隔离 | `App.vue`、`CoursesView`、`tests/` | L11–L14 | 交接文件第 9 节清单逐项有测试或记录 |
| L16 | 5 | 性能优化与实测、准确率报告、问答测试集 | `workers/`、`prompts/`、`evaluation/` | L11 | 第 5 节报告；未达标项单列 |
| L17 | 6 | 轻量美化（仅在两条闭环验收后） | 样式 | L15 | 不改交互语义，前端测试仍过 |
| L18 | 6 | README、运行手册、九类材料（R12）；材料素材从第 1 天起记录 | `README.md`、`docs/runbook.md`、`docs/submission/` | 持续 | 按文档从零启动成功 |
| L19 | 7 | 冻结：干净环境部署复测、演示走查、未满足项清单 | 文档 | 全部 | 最终验收只列已验证结果 |

止损：第 3 天结束时 L11 未走通，停止 L12 之后的新增项，只修主线。个人 API 若确实挡住赛题闭环，向你提一次带证据的取舍请求，不自行取消。

## 8. 测试策略

- 单元与接口测试用隔离 SQLite、注入的假传输与假模型，不联网。
- `personal` 模式端到端测试用本机假供应商（OpenAI 兼容桩），经 `MODEL_ENDPOINT_ALLOW_PRIVATE` 放行。它证明接线，不证明模型质量。
- 真实模型验收单独记录，只在你确认的预算内运行。历史、模拟、真实三类证据在报告中分列。
- 每个任务跑最小相关测试与 `./scripts/verify.sh`；`full` 与 `integration` 在 L01、L11、L15、L19 各跑一次。不删测试、不改阈值、SKIP 不算 PASS。

## 9. 风险

1. **60 秒抽取**：现有证据显示差距大，且成绩取决于用户自选模型的速度。第 1 天就测，按第 5 节顺序优化，可能最终只能如实报告差距。
2. **在线向量首次真实联调**：客户端只经过假传输测试；供应商差异可能要调整，L09 提前到第 3 天。
3. **改造面**：worker 与问答的客户端装配是全局假设，改为按任务/按用户会碰到大量依赖 `fake` 全局装配的测试。保留 `demo`/`fake` 全局路径以控制回归面。
4. **任务板合并**：Codex 对 `docs/tasks.md` 有未提交改动，与本分支新增段落合并时会冲突，届时两段都保留。
5. **验证环境**：本轮只跑了基础档 `./scripts/verify.sh`（exit 0，用系统 `/opt/anaconda3/bin/python3`，不是项目锁定环境）。`full`、`integration`、前端测试与构建均未跑；L01 完成前不对业务功能下任何 PASS 结论。

## 10. 回滚

- 代码按原子任务提交，可逐个回退。
- 迁移 015 用迁移前备份恢复；新列均可空，旧代码可读新库。
- 运行模式切回 `demo` 即恢复现状；冲刺用独立数据库，不触碰现有演示数据。

## 11. 用户决定（2026-10-02，ArvinHan）

1. **向量方案**：同意。系统级在线向量（阿里云百炼 `text-embedding-v4`、1024 维、每批 10 条），向量 key 由部署者提供；`EMBEDDING_MODE=local` 改为明确不支持。
2. **真实联调**：DeepSeek `deepseek-flash`，基址 `https://api.deepseek.com`。大模型预算上限 30 元。执行口径：按仓库已有估算（25～30 万 token 约 1～1.5 元）取保守单价，累计计费 token 不超过 500 万；`.env` 的 `LLM_DAILY_TOKEN_BUDGET=700000`、`LLM_TASK_TOKEN_BUDGET=500000`；每次真实运行后在交接中登记累计用量。实际花费以供应商控制台为准。
3. **课程资料**：同意自编。课程一沿用「数据结构 第 3 章 栈与队列」，课程二另自编一章，各出文本型 PDF 与 Markdown。
4. **规则与依赖**：同意 3.9 的两条规则改写与新增 `cryptography` 依赖，在 L03 写入 ADR-080 并同步上位文档。

2026-10-03 补充：本机网络到北京地域向量接口 TCP 超时（`claude-l01.md` 发现 3），用户选择恢复该网络路径（地址与 key 不变）；L09 的代码交给 DeepSeek harness 编写（交接 `docs/handoffs/claude-l09-handoff.md`）。

冲刺工作区的 `.env` 已生成（未跟踪、权限 600）。端口与主检出错开：API 8001、前端 5174、Neo4j 7688/7475。`LLM_API_KEY` 与 `EMBEDDING_API_KEY` 留空，由用户本人填写。百炼兼容基址 `https://dashscope.aliyuncs.com/compatible-mode/v1` 凭记忆填写，在 L09 真实联调时核对。

**2026-10-03 L09 核对结果（基址与在线向量已实测可用）**：第 4 节与第 11 节第 1 项的在线向量方案在本机跑通。`.venv/bin/python scripts/check-embedding.py` 返回 `ok model=text-embedding-v4 dimensions=1024 seconds=0.66`（exit 0），即基址 `https://dashscope.aliyuncs.com/compatible-mode/v1`、模型 `text-embedding-v4`、`EMBEDDING_DIMENSIONS=1024`、`EMBEDDING_BATCH_SIZE=10` 四项与 ADR-081 一致，维度与配置相符。此前 L01/L02 记录的「北京地域接口 TCP 超时」已由用户恢复网络路径（地址与 key 未改）。正式入口 `scripts/start.sh` 冒烟通过：API `/health` 返回 `{"status":"ok","version":"0.1.0"}`、`GET /api/v1/me/model-config` 返回 `{"runtime_mode":"personal","configured":false}`、worker 日志无 `Invalid configuration`、前端 5174 返回 200。用量登记见 `docs/handoffs/deepseek-l09.md`。

## 12. 实施计划

- 计划 A（L01–L10，第 1–3 天）：`docs/superpowers/plans/2026-10-02-contest-sprint-a-personal-model-api.md`。
- 计划 B（L11–L15）与计划 C（L16–L19）分别在第 3 天、第 4 天结束时依据实测结果编写，再交用户确认。
