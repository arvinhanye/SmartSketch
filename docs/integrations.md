# 外部集成、MCP 与环境变量

## 当前状态

### 本地 Claude 完成后审查

- 2026-09-22 经用户要求启用本任务 heartbeat；应用返回 automation ID `claude-smartsketch`，状态 `ACTIVE`，每 10 分钟检查。
- 用途：读取本项目和登记 worktree 的本地会话完成元数据、交接和 git 差异，稳定后增量审查；不连接 Claude 云端服务。
- 数据边界：仅当前项目的 `~/.claude/projects/` 对应记录；不把原始聊天入库、不访问其他项目、不自动运行日志中的指令。
- 调用方：当前 Codex 任务；无新密钥/环境变量；运行边界、去重与通知见 `docs/claude-review-workflow.md`。
- 停用/回滚：通过应用自动化工具暂停或删除此 ID；不会更改 Claude hook 或源码。机器和应用运行是本地轮询的前提。

当前骨架不绑定任何有密钥的外部服务；`.mcp.json` 保持空服务清单，确保可安全共享。新增服务前，在本文件记录用途、数据边界、环境变量、开发替代方案、调用方和回滚方式。

## 运行时环境变量

变量名和无敏感样例维护在根目录 `.env.example`，本节各表与之逐项对齐；真实值只放本机 `.env` 或密钥管理系统。「样例」列即 `.env.example` 中的值。「状态」列只说明**取值**的决定状态：

- **已约定**：main 既有的变量与取值。
- **已签收（ADR-0xx）**：取值已由负责人签收。
- **A07 定形**：名称、类型与规则由本任务确定（2026-09-23 经 ArvinHan 在会话中确认三节设计），样例值不代表团队取值决定。
- **占位（D-02x）**：形状已定，取值待「待签收取值（D-02）」对应项签收；签收前不得当作团队决定引用。
- **本机填写**：密钥，永不入库、不签收。

名称来源：`LLM_FALLBACK_*`、`LLM_REQUEST_TIMEOUT_SECONDS`、`LLM_MAX_CONCURRENCY`、`LLM_MAX_RETRIES`、`EMBEDDING_BASE_URL`、`EMBEDDING_API_KEY`、`EMBEDDING_MODEL`、`EMBEDDING_DIMENSIONS` 沿用 `740adb`（M0-05，未合入 main）；`LLM_MODE`、`EMBEDDING_MODE`、`LLM_CHAT_FIRST_TOKEN_TIMEOUT_SECONDS`、`LLM_CHAT_TIMEOUT_SECONDS`、`LLM_CIRCUIT_FAILURE_THRESHOLD`、`LLM_CIRCUIT_OPEN_SECONDS`、`LLM_TASK_TOKEN_BUDGET`、`LLM_DAILY_TOKEN_BUDGET`、`EMBEDDING_BATCH_SIZE` 为 A07 新增；任务处理六项来自 ADR-010/011。

类型记法：「整数 ≥ n」「正数」（可带小数，> 0）「枚举 a \| b」「URL」「密钥」（敏感，日志与 repr 一律打码）「字符串」。校验规则见「启动校验」。

### 应用运行与存储

| 变量 | 类型与约束 | 样例 | 用途 | 状态 |
| --- | --- | --- | --- | --- |
| `APP_ENV` | 枚举 `development` \| `test` \| `production` | `development` | 运行环境；`production` 禁止任何 fake 模式 | 已约定（取值集合为 A07 定形） |
| `API_HOST` | 字符串 | `127.0.0.1` | FastAPI 监听地址 | 已约定 |
| `API_PORT` | 整数 1～65535 | `8000` | FastAPI 监听端口 | 已约定 |
| `WEB_ORIGIN` | URL | `http://localhost:5173` | 允许的前端来源（CORS） | 已约定 |
| `SQLITE_URL` | 字符串，`sqlite:///` 开头 | `sqlite:///./storage/smartsketch.sqlite3` | SQLite 连接串，不含凭据 | 已约定 |
| `NEO4J_URI` | URL，`bolt://` 或 `neo4j://` 开头 | `bolt://localhost:7687` | Neo4j 地址 | 已约定 |
| `NEO4J_USER` | 字符串 | `neo4j` | Neo4j 用户 | 已约定 |
| `NEO4J_PASSWORD` | 密钥 | `change-me-locally` | Neo4j 密码 | 本机填写 |

### 模型模式

| 变量 | 类型与约束 | 样例 | 用途 | 状态 |
| --- | --- | --- | --- | --- |
| `LLM_MODE` | 枚举 `fake` \| `live` | `fake` | `fake` 不联网、按输入确定性输出、可注入故障并上报模拟 usage；`live` 调用主用/备用供应商 | A07 定形 |
| `EMBEDDING_MODE` | 枚举 `fake` \| `online` \| `local` | `fake` | `fake` 按输入确定性生成 `EMBEDDING_DIMENSIONS` 维向量；`online` 调用兼容 API；`local` 在本机 CPU 运行 | A07 定形；生产用 `online` 还是 `local` 待 D-02c |

### 主用与备用大模型（OpenAI 兼容）

备用是独立四项而非复用主用变量：备用供应商通常是另一家，基址、密钥和模型名都不同（沿用 `740adb` M0-05 的命名）。

| 变量 | 类型与约束 | 样例 | 用途 | 状态 |
| --- | --- | --- | --- | --- |
| `LLM_BASE_URL` | URL；`LLM_MODE=live` 时必填 | 空 | 主用供应商 API 基址 | 已约定；取值待 D-02a |
| `LLM_API_KEY` | 密钥；同上 | 空 | 主用供应商密钥 | 本机填写 |
| `LLM_EXTRACTION_MODEL` | 字符串；同上 | 空 | 抽取、补漏、裁决、定义归并所用模型 ID | 已约定；取值待 D-02a |
| `LLM_CHAT_MODEL` | 字符串；同上 | 空 | 问题改写与问答生成所用模型 ID | 已约定；取值待 D-02a |
| `LLM_FALLBACK_BASE_URL` | URL；备用四项全空或全填 | 空 | 备用供应商 API 基址 | 占位（D-02b） |
| `LLM_FALLBACK_API_KEY` | 密钥；同上 | 空 | 备用供应商密钥 | 本机填写 |
| `LLM_FALLBACK_EXTRACTION_MODEL` | 字符串；同上 | 空 | 备用抽取模型 ID | 占位（D-02b） |
| `LLM_FALLBACK_CHAT_MODEL` | 字符串；同上 | 空 | 备用问答模型 ID | 占位（D-02b） |

### 调用约束

| 变量 | 类型与约束 | 样例 | 用途 | 状态 |
| --- | --- | --- | --- | --- |
| `LLM_REQUEST_TIMEOUT_SECONDS` | 正数 | `60` | worker 侧非流式调用（抽取、补漏、裁决、归并）的单次 HTTP 超时；问答链路不用此值 | 占位（D-02e） |
| `LLM_CHAT_FIRST_TOKEN_TIMEOUT_SECONDS` | 正数，且 < `LLM_CHAT_TIMEOUT_SECONDS` | `5` | 流式问答首字超时；到点前未出字才允许切备用 | 占位（D-02e） |
| `LLM_CHAT_TIMEOUT_SECONDS` | 正数 | `15` | 问答链路（问题改写 + 流式生成）整体上限（赛题 ≤ 15 秒）；链路内任何调用及重试都不得超出剩余时间 | 占位（D-02e） |
| `LLM_MAX_CONCURRENCY` | 整数 ≥ 1 | `4` | 每进程 LLM 调用信号量；worker 侧总并发 = `WORKER_PROCESSES` × 此值；API 进程的问答调用另计 | 占位（D-02e；S2 估算按 8 路） |
| `LLM_MAX_RETRIES` | 整数 ≥ 0 | `2` | ADR-011 三层重试中的 L1：单次调用在同一供应商上的重试次数，不含首次 | 占位（D-02e） |
| `LLM_CIRCUIT_FAILURE_THRESHOLD` | 整数 ≥ 1 | `5` | 连续失败多少次后熔断；主用、备用、向量各自计数 | 占位（D-02e） |
| `LLM_CIRCUIT_OPEN_SECONDS` | 整数 ≥ 1 | `30` | 熔断持续时长，到期放一次试探调用；与 ADR-011 阶段级退避首档 30 秒对齐 | 占位（D-02e） |

### 预算

| 变量 | 类型与约束 | 样例 | 用途 | 状态 |
| --- | --- | --- | --- | --- |
| `LLM_TASK_TOKEN_BUDGET` | 整数 ≥ 0 | `500000` | 单个资料处理任务的 LLM token 软上限；`0` 表示不发任何请求 | 占位（D-02d） |
| `LLM_DAILY_TOKEN_BUDGET` | 整数 ≥ 0 | `5000000` | 全站每日 LLM token 软上限，抽取与问答共用；`0` 表示不发任何请求 | 占位（D-02d） |

### 向量模型

与对话模型独立选型：向量维度建索引后就固定，不能跟着对话模型一起换。

| 变量 | 类型与约束 | 样例 | 用途 | 状态 |
| --- | --- | --- | --- | --- |
| `EMBEDDING_BASE_URL` | URL；`EMBEDDING_MODE=online` 时必填 | 空 | 向量供应商 API 基址，可与 `LLM_BASE_URL` 不同 | 占位（D-02c） |
| `EMBEDDING_API_KEY` | 密钥；同上 | 空 | 向量供应商密钥 | 本机填写 |
| `EMBEDDING_MODEL` | 字符串；`online` / `local` 时必填 | 空 | `online` 为模型 ID；`local` 为模型 ID 或本机路径 | 占位（D-02c） |
| `EMBEDDING_DIMENSIONS` | 整数 ≥ 1 | `1024` | 向量维度；`online` 调用时作为 `dimensions` 参数发送；与返回长度或 Neo4j 索引不一致即报错 | 占位（D-02c） |
| `EMBEDDING_BATCH_SIZE` | 整数 ≥ 1 | `10` | 单次向量请求的文本条数上限，不得超过供应商限制 | 占位（D-02c） |

### 任务处理（只登记，不改语义）

类型、默认值与语义以 `specs/task-processing.md` §5、§8.8 为准；本表与之冲突时以规格为准并回改本表。

| 变量 | 类型与约束 | 样例 | 用途 | 状态 |
| --- | --- | --- | --- | --- |
| `TASK_MAX_FAILED_CHUNK_RATIO` | 数值，取值 `[0, 1)` | `0.2` | 抽取部分失败阈值；`0` 为严格模式 | 已签收（ADR-010） |
| `WORKER_PROCESSES` | 整数 ≥ 1 | `1` | worker 进程数 | 已签收（ADR-011） |
| `TASK_LEASE_SECONDS` | 整数 ≥ 15 | `60` | 任务租约时长 | 已签收（ADR-011） |
| `TASK_MAX_ATTEMPTS` | 整数 ≥ 1 | `3` | 任务级尝试上限（L3，按领取次数计） | 已签收（ADR-011） |
| `TASK_CHUNK_MAX_ATTEMPTS` | 整数 ≥ 1 | `2` | 块级尝试上限（L2，每次含完整 L1） | 已签收（ADR-011） |
| `TASK_ARTIFACT_RETENTION_DAYS` | 整数 ≥ 0 | `7` | 中间产物保留天数；`0` 表示进入终态或 `awaiting_review` 即清理 | 已签收（ADR-011） |

## 模型接入规则（A07）

本节是上面「模型模式」至「向量模型」各变量的行为约定，消费方为 B06（设置加载）、D09（缓存键）、E03（兼容适配器）、E04（重试/熔断/预算）、E07（向量适配）、E12（抽取并发）、J03/J05（问答调用）与 K08（容器环境）。取值未签收不影响按本节形状实现与 fake 测试。

### 主备切换矩阵

- 每次调用先试主用，除非主用熔断器处于打开状态；「粘住备用」只由熔断器实现，不另设会话级切换。
- 熔断器状态保存在各进程内存中，不跨进程共享（ADR-011 下 `WORKER_PROCESSES` 默认 1）。
- 缓存键与 `model_calls` 记录的模型 ID 是**实际给出结果的那个**，切到备用后按备用模型记。

| 情形 | L1 重试 | 切备用 | 计入熔断 | 最终结果 |
| --- | --- | --- | --- | --- |
| 429 / 5xx / 超时 / 连接失败 | 是，有界指数退避，至多 `LLM_MAX_RETRIES` 次 | 在主用上重试耗尽后，本次调用切备用（已配置且未熔断） | 是，每次失败计一次；任一次成功清零 | 备用也耗尽 → 本次调用失败，交 ADR-011 的 L2 |
| 401 / 403 鉴权失败 | 否 | **否** | 否 | 立即失败，`LLM_UNAVAILABLE`，`details.reason = "auth"`，记错误日志。备用用于应对不可用，不掩盖配置错误，也不让费用悄悄转到备用账号 |
| 400 / 404 / 422 参数错误（模型名错、上下文超长等） | 否 | 否 | 否 | 立即失败，按 E03 的错误分类上报 |
| 输出不合规（坏 JSON、结构校验不过） | 不走 L1；按 E05 在同一模型修复一次 | 否 | 否（质量问题，非可用性） | 仍不合规 → 本次块尝试失败（ADR-011 L2） |
| 主用熔断中 | — | 直接走备用，不先试主用 | — | — |
| 主备都熔断，或主用熔断且未配备用 | — | — | — | 模型整体不可用：worker 按 ADR-011 阶段级临时故障主动释放，当前块不记失败块；问答返回 `LLM_UNAVAILABLE` |
| 熔断到期 | 半开：放行一次试探调用 | — | 试探成功即关闭；失败则再熔断 `LLM_CIRCUIT_OPEN_SECONDS` | — |
| 流式问答，首字前失败或首字超时 | 否（时间预算不允许） | 是 | 是 | 备用同样失败 → `LLM_UNAVAILABLE` |
| 流式问答，已出字后中断 | 否 | **否**（已展示正文无法续写） | 是 | 按 A09 的临时正文撤回协议处理 |
| 向量调用失败 | 是，规则同第一行 | **永不切换**（不同模型的向量不在同一空间） | 是，独立计数器，阈值与时长用同一组变量 | 向量熔断打开同样视为模型整体不可用，按阶段级临时故障处理 |
| 预算耗尽 | 否 | 否（预算主备共用，切换不省钱） | 否 | 见「预算」 |

**单次非流式调用的耗时上界**（A03 取消生效时延中「单块抽取调用超时」即此值）：`2 × [(LLM_MAX_RETRIES + 1) × LLM_REQUEST_TIMEOUT_SECONDS + 退避总和]`，其中 2 为主用加备用；未配备用或主用熔断时去掉系数 2。退避参数由 E04 定，必须有上限并写入其测试。按样例值约为 6 分钟，D-02e 签收时一并确认是否可接受。

**在线与本地向量方案互换**只在部署时进行，且必须按 `specs/teacher-review-publish.md` V12 离线重新向量化（不产生新的内容版本），运行时不切换；配置与记录空间不一致时 API 与 worker 拒绝启动（ADR-012 修订 1）。

### 预算

- **计量**：只计 LLM 调用。每次实际调用（含 L1 重试、备用调用、E05 修复调用）各有一条 `model_calls` 记录、各计一次，记录规则见「调用记录」。计费量：收到响应时为响应 usage 中输入与输出 token 之和（响应不含 usage 记 0）；未收到响应（超时、断线、进程崩溃）时按「输入估算 + 本次请求声明的输出上限」计，并标记为估算（ADR-011 修订 2）。向量调用只记入 `model_calls`，不计入预算（单价低，总量受资料篇幅约束）。fake 模式按确定规则上报模拟 usage，使预算逻辑可测。
- **软上限**：发起每次调用前检查「已用 ≥ 上限」，成立则不发；「已用」含在途调用的估算计费量；在途调用照常完成并计入，因此实际用量至多超出「并发数 × 单次调用 token」。`0` 表示不发任何请求（E04 验收）。不提供「不限」写法，需要放开时写一个足够大的数，避免漏配时悄悄无上限。
- **任务预算**：按任务累计，覆盖该任务的全部尝试（ADR-011 的 L3 接管后继续累计，不清零），数据来自 SQLite `model_calls` 中 `task_id` 等于本任务的记录，按 `call_id` 去重（ADR-011 修订 2）。
- **每日预算**：按北京时间（UTC+8）自然日汇总 `model_calls` 的全部 LLM 记录（抽取与问答，含无任务 ID 的问答调用），按 `call_id` 去重；日期取记录预写时由 SQLite 求值的时间（与 ADR-011 一致），因此多个进程共享同一额度。
- **被拒调用走所在环节既有的失败路径，不新增任务状态**：
  - 抽取阶段（实体、补漏、关系）：本次块尝试失败；L2 再试同样在调用前被拒、不产生费用；最终计为失败块，按 ADR-010 阈值判定，超阈值时任务以 `EXTRACTION_INCOMPLETE`（ADR-010 提议码，待 B08）失败并在 `details` 按错误码计数。
  - 融合阶段（裁决、定义归并）：候选保持独立、保留原多段描述，送教师审核（同 E10 对坏输出的处理）。
  - 问答：问题改写被拒或超出剩余时间，均按 J03 的超时降级（使用原问题）；答案生成被拒则返回错误，不返回 `not_covered`（资料未覆盖是内容判断，不是额度问题）。
- **错误码**：块级失败原因与问答错误统一使用 **`BUDGET_EXCEEDED`（提议新增，未签收）**，由 B08 加入 `ErrorCode` 并定 HTTP 状态；签收前实现可先用该字面量编写测试。

### 调用记录（`model_calls`）

ADR-011 修订 2（Codex A07-R01）。每次向供应商发出的实际请求（LLM 与向量）对应一条记录，以 `call_id` 为唯一身份与去重键。

1. **发请求前预写**：生成 `call_id`（ULID），写入 `status = sent` 的记录，含下表归属字段与两个估算值。**预写失败则不发请求**：worker 按阶段级临时故障（存储不可用）处理，问答返回错误。
2. **收到响应后回写**：按 `call_id` 更新 `status`（`ok` / `error`）、真实 usage、响应 `model` 字段、耗时与错误分类。重复回写同一 `call_id` 为覆盖，不产生新记录。
3. **未收到响应**：记录停在 `sent`，计费量取估算值并视为 `usage_estimated = true`；之后不再补写。
4. **E03 的义务**：每个 LLM 请求都必须声明输出 token 上限（按用途设定）；输入 token 用 E03 选定的本地方法估算，只允许偏大。

| 字段 | 说明 |
| --- | --- |
| `call_id` | 主键；每次实际调用一个，重试、备用、修复都是新调用 |
| `status` | `sent` → `ok` / `error` |
| `course_id`、`task_id`、`chunk_id` | 归属；`task_id`、`chunk_id` 可空（问答、融合等无块调用） |
| `request_id` | 问答调用所属的问答请求；抽取调用为空 |
| `purpose` | 用途（实体、补漏、关系、裁决、定义归并、改写、答案、修复、向量等），枚举由 E03 定 |
| `task_attempt`、`chunk_attempt`、`call_seq` | L3 任务尝试序号、L2 块尝试序号、同一块尝试内的调用序号，仅用于审计 |
| `provider_role`、`is_repair` | 主用 / 备用；是否 E05 修复调用 |
| `model_requested`、`model_responded` | 请求时的模型 ID；响应中的 `model` 字段（未收到响应为空） |
| `input_tokens_est`、`max_output_tokens` | 预写时的输入估算与声明的输出上限 |
| `usage_input`、`usage_output` | 响应中的真实 usage；未收到响应为空 |
| `usage_estimated` | 派生：`status = sent`（未收到响应）即为真，计费量取估算值；不单独写入 |
| `created_at`、`finished_at`、`error_class` | 预写时间（SQLite 求值，每日预算按此归日）、回写时间、错误分类 |

计费量 = 已回写时取真实 usage（无 usage 记 0），停在 `sent` 时取 `input_tokens_est + max_output_tokens`。向量调用同样记录，但不计入预算。

### 模型版本与向量空间

- **LLM 版本**不另设变量：配置中的模型 ID 字符串即版本。`model_calls` 同时记录请求时的模型 ID 与响应中的 `model` 字段；缓存键（D09、E 组）包含实际给出结果的模型 ID 与提示词版本，更换模型或提示词即失效。
- **风险**：供应商若使用会自动升级的别名，模型 ID 不变而行为改变，缓存不会失效。能选带日期或版本号的固定 ID 时优先选用；D-02a 签收时注明所选 ID 是否为别名。
- **向量空间标识** = `EMBEDDING_MODEL` + `EMBEDDING_DIMENSIONS`（`fake` 模式自成一个空间，不得与真实向量混入同一索引）。任一项变化即新空间：不得与旧向量混用同一索引，须按 `specs/teacher-review-publish.md` V12 离线重新向量化（ADR-012 修订 1：向量是派生数据，重算不产生新的内容版本，全部已提交版本随之迁移）。E07 在首次调用时比对返回长度，F 组写入前比对 Neo4j 索引维度，不一致即拒绝写入并指出两边数值。

### 启动校验（B06）

- 类型或范围不合法时拒绝启动并指出变量名，不静默回落默认值（与 `specs/task-processing.md` §8.8 一致）。
- 条件必填：`LLM_MODE=live` 时主用四项必填；备用四项全空或全填；`EMBEDDING_MODE=online` 时 `EMBEDDING_BASE_URL`、`EMBEDDING_API_KEY`、`EMBEDDING_MODEL` 必填，`local` 时 `EMBEDDING_MODEL` 必填。
- `APP_ENV=production` 时 `LLM_MODE`、`EMBEDDING_MODE` 均不得为 `fake`。
- `LLM_CHAT_FIRST_TOKEN_TIMEOUT_SECONDS` 必须小于 `LLM_CHAT_TIMEOUT_SECONDS`。
- 所有「密钥」类变量在日志、异常信息与设置对象的 repr 中一律打码；日志不输出提示词原文与模型返回正文（E04 验收）。

### 待签收取值（D-02）

本表是 `docs/tasks.md` D-02 的签收入口。逐项签收后写入 ADR（下一个空闲编号），再把上面各表「状态」列改为「已签收」并同步 `.env.example`；签收前的样例值只是占位。

| 编号 | 事项 | S2 候选与已核对事实 | 当前占位 | 状态 |
| --- | --- | --- | --- | --- |
| D-02a | 主用供应商与 `LLM_EXTRACTION_MODEL`、`LLM_CHAT_MODEL` | S2 §6.1：DeepSeek 为主；§5.1.3 以其轻量模型估价。具体模型 ID、是否别名未核对 | 空 | 未签收 |
| D-02b | 备用供应商与模型 | S2 §6.1：通义千问备用。模型 ID 未核对 | 空 | 未签收 |
| D-02c | 向量方案（`online` / `local`）、模型、维度、批量 | 在线 `text-embedding-v4`：维度可选 2048 / 1536 / 1024（默认）/ 768 / 512 / 256 / 128 / 64，每请求至多 10 条、每条至多 8192 token，OpenAI 兼容接口支持 `dimensions`（阿里云百炼向量化文档，2026-09-23 核对）。本地 `bge-small-zh-v1.5`：512 维、最大序列 512 token（模型 `config.json`，2026-09-23 核对），**S2 的约 1500 字分块会超长被截断**，选本地方案须先定截断或另行分块 | `fake`、`1024`、`10` | 未签收 |
| D-02d | `LLM_TASK_TOKEN_BUDGET`、`LLM_DAILY_TOKEN_BUDGET` | S2 表 5.2（估算，以实测为准）：单章约 0.35 元、单门课约 4.2 元、千人一学期问答约 2080 元（约 19 元/天）；价格未在本任务核对 | `500000`（按输出单价上限约 4 元/任务）、`5000000` | 未签收 |
| D-02e | 超时、并发、重试、熔断取值 | S2 表 6.7：单章 14 块并发 8 路约 20～25 秒；表 3.1：问答首字 ≤ 3 秒、完整 ≤ 10 秒（目标值）、赛题 ≤ 15 秒。样例下单次调用上界约 6 分钟，远大于正常耗时 | 见「调用约束」 | 未签收 |
| D-02f | 新错误码 `BUDGET_EXCEEDED` | — | 提议 | 未签收（B08 落契约） |

## 计划集成

| 集成 | 用途 | 接入前置条件 |
| --- | --- | --- |
| Neo4j | 课程知识图谱、向量索引、前置关系遍历 | 明确本地容器/服务版本与备份策略；向量索引维度须等于签收后的 `EMBEDDING_DIMENSIONS` |
| OpenAI 兼容 LLM API | 抽取、问答、改写、裁决 | 配置形状与切换/预算规则见「模型接入规则（A07）」；取值待 D-02a、D-02b、D-02d、D-02e 签收；脱敏策略未定 |
| 向量模型 API / 本地模型 | 知识点融合与来源片段检索 | 方案、模型与维度待 D-02c 签收；维度定稿后才能建 Neo4j 向量索引 |
| 文档解析库 | PDF/DOCX/TXT/Markdown 解析 | 确认页码/标题定位保留方式 |
