# Claude 交接：E04 实现模型调用预算与退避

- task_id: E04（未改 issue、未建 PR、未 push）
- review_status: ready_for_review
- worktree: `/home/user/wt-e04-call-policy`，分支 `claude/e04-call-policy`
- base: 认领提交 `f0814cc`
- 状态：实现与验证完成，待 PR 审查/合并

## 改动文件

| 文件 | 说明 |
| --- | --- |
| `src/backend/app/services/ai/policy.py` | 新建：`ModelCallPolicy`（包装 E02 `ModelClient`）、`BoundModelClient`（`bind(attribution)` 得到的 `ModelClient`）、`BackoffPolicy`、`CircuitBreaker`/`CircuitState`、`CallAttribution`、`CallStore` 协议、错误 `BudgetExceededError`/`CallRecordError`/`ModelUnavailableError`（均继承 `ModelError`，带 `code`）、`new_call_id()`（ULID）、`max_backoff_total`/`max_call_duration_seconds` |
| `src/backend/app/repositories/model_calls.py` | 新建：`SqliteCallStore`（`prewrite` 在一个写事务内查预算并插入 `sent` 行；`finish` 按 `call_id` 覆盖回写）、`CallRecord`/`CallOutcome`、`BudgetRejected`、`billed_for_task`/`billed_for_day`/`get_call`、计费 SQL `BILLED_TOKENS_SQL` |
| `tests/backend/test_e04.py` | 新建：47 个测试函数，参数化后 66 条 |
| `docs/handoffs/claude-e04.md` | 本文件 |
| `docs/tasks.md` | 仅「2026-09-25 第五批并行（Claude）」E04 行的状态与证据列 |

未改 `client.py`、`fake.py`、`compatible.py`、`embeddings.py`、`config.py`、`integrations.md`、迁移（`model_calls` 表沿用 001）。无新依赖。仓储不依赖 `services`（`CallOutcome` 用两个整数列表示 usage）。

## 行为（依据：`docs/integrations.md`「模型接入规则（A07）」、ADR-011 决定 4 与修订 2/3）

1. **每次实际请求**：选角色 → 预写 → 发请求 → 回写。预写生成 ULID `call_id`，写入归属字段、`input_tokens_est = estimate_input_tokens(request)`（E03）与 `max_output_tokens`；`call_seq` 由绑定客户端按 1、2、3… 递增。
2. **预算（软上限）**：`SqliteCallStore.prewrite` 在 `BEGIN IMMEDIATE` 内先查「已用 ≥ 上限」（任务：同 `task_id` 全部记录；每日：北京时间自然日，`created_at` 由 SQLite 求值），成立即 `BudgetRejected`、不写不发；策略层另有 `0` 的前置短路。「已用」含停在 `sent` 的在途估算。问答调用（`task_id` 为空）只查每日预算。`purpose = "embedding"` 的行不计费、不查预算。
3. **预写失败不发请求**：存储抛出的任何异常 → `CallRecordError`（`code = STORAGE_UNAVAILABLE`），供应商未被调用（O12、QA-29、LEASE-27）。
4. **回写**：成功写 `ok`、usage、`model_responded`、耗时；供应商错误写 `error`、错误里带的 usage、错误分类；生成前被拒（`rejected_before_generation`）的分类存为 `"<class>:rejected_before_generation"`。回写失败只记日志、结果照常返回（行停在 `sent`，按估算计，偏保守）。
5. **计费量**（`BILLED_TOKENS_SQL`）：有 usage 取 usage；无 usage 且生成前被拒取 0；其余取 `input_tokens_est + max_output_tokens`（LEASE-28～30）。按 `call_id` 主键去重，预写与回写重放均不增行、不改计费（LEASE-17/25）。
6. **切换矩阵（`complete`）**：超时 / 连接 / 429 / 5xx 在同一供应商重试至多 `max_retries` 次，每次失败计入该供应商熔断；主用耗尽或熔断打开后切备用（须配置了备用客户端且请求模型在 `fallback_models` 中）。401/403、其他 4xx、`malformed_response`：不重试、不切换、不计熔断，原样抛出；鉴权失败记 ERROR 日志。所有可用角色都熔断 → `ModelUnavailableError`（`code = LLM_UNAVAILABLE`，worker 按阶段级临时故障处理）；否则抛最后一个供应商错误（交 L2）。预算拒绝在重试中途发生时立即抛出、不切换（预算主备共用）。
7. **退避**：`delay = min(max, base·2ⁿ) × (0.5 + 0.5·r)`；有 `Retry-After` 时取其值但封顶 `max`。默认 `base = 1 s`、`max = 8 s`，`max` 硬上限 `HARD_MAX_BACKOFF_SECONDS = 30 s`，构造时越界即 `ValueError`。熔断已打开时不再退避、直接切备用。
8. **熔断**：连续失败达 `failure_threshold` 打开；`open_seconds` 后半开，只放行一次试探；试探成功关闭并清零，失败重新打开完整时长。无结论的结束（预算拒绝、鉴权/参数错误、调用方提前关闭流）只释放试探名额。状态在进程内存（A07），`policy.circuit_state(role)`、`policy.model_available(model)` 供 ADR-011 决定 4 判断。
9. **流式**：不做 L1 重试。首个非空增量之前的临时故障或断流 → 计熔断并切备用；已出字后失败 → 计熔断、原样抛出、不切换；鉴权/参数错误不切换。调用方提前 `close()` → 行停在 `sent`、不动熔断，内层流随之关闭。适配器流未以 `StreamDone` 结束按 `stream_interrupted` 处理。
10. **不泄露**：日志只含 `call_id`、角色、模型 ID、错误分类、HTTP 状态；`model_calls` 只存 ID、计数与分类。`repr` 不含密钥。测试用真实 `CompatibleModelClient` + 脚本化传输核对日志与记录中无密钥、提示词、响应正文。

**单次非流式调用耗时上界**：`max_call_duration_seconds(R, T, with_fallback)` = `2 × [(R+1)·T + R·8]`；按样例 `R = 2`、`T = 60 s` 为 `2 × 196 = 392 s`（约 6.5 分钟，A07 原估约 6 分钟未计退避）。

## 接口（给 E05、E06、E12、J03、J05 与装配处）

```python
from app.repositories.model_calls import SqliteCallStore
from app.services.ai.policy import CallAttribution, ModelCallPolicy

policy = ModelCallPolicy.from_settings(settings, primary=primary_client, fallback=fallback_client_or_None,
                                       store=SqliteCallStore(settings.SQLITE_URL))  # 每进程一个，共享熔断状态
client = policy.bind(CallAttribution(course_id=..., task_id=..., chunk_id=..., task_attempt=..., chunk_attempt=...))
result = client.complete(request)        # 同 E02 ModelClient
repair = policy.bind(CallAttribution(..., is_repair=True)).complete(repair_request)   # E05 修复调用：独立记录
qa = policy.bind(CallAttribution(course_id=..., request_id=...))                       # J03/J05：无 task_id
```

- E12：每个块尝试 `bind` 一次；捕获 `ModelUnavailableError` → 阶段级临时故障（不记失败块）；`BudgetExceededError` → 块失败原因 `BUDGET_EXCEEDED`；`CallRecordError` → 存储不可用；其余 `ModelCallError` → L2。
- E05：对输出不合规的结果用 `is_repair=True` 的绑定再调一次；修复调用照常走预算与记录。
- J05：`stream()` 只处理首字前切换；首字超时由 J05 用时钟判断后 `close()` 流（E02 待决 5）。`BudgetExceededError` → `error: BUDGET_EXCEEDED`（QA-28），`CallRecordError` → `STORAGE_UNAVAILABLE`（QA-29），`ModelUnavailableError` 与鉴权错误 → `LLM_UNAVAILABLE`。
- E07：向量调用可复用 `SqliteCallStore`（`purpose = "embedding"` 不计预算）与 `CircuitBreaker`，但**本任务未包装 `EmbeddingClient`**（见待决 6）。

## 命令与实际结果

每次运行均用新的 `PYTHONPYCACHEPREFIX=<scratchpad>/pyc-e04-$RANDOM`，`V=<scratchpad>/venv`。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 红灯 | `PYTHONPATH=$PWD/src/backend $V/bin/python -m pytest tests/backend/test_e04.py -q -p no:cacheprovider`（实现前） | 收集错误 `ImportError: cannot import name 'model_calls'`，exit 非 0 |
| 首次绿灯 | 同上 | 64 passed、1 failed（半开试探失败后重新熔断的时刻被多余退避推迟：熔断已开仍在退避）；改为「熔断已开不退避」并补测 `test_no_backoff_when_breaker_opens_before_switching` |
| 绿灯 | 同上 | **66 passed** |
| 后端全量 | `... -m pytest tests/backend -q -p no:cacheprovider` | **1742 passed**（main 基线 1676 + 本任务 66），1 warning（既有） |
| 契约/工具 | `PATH=$V/bin:<scratchpad>/b15-tools/node_modules/.bin:$PATH ... -m pytest tests/contracts tests/tooling -q -p no:cacheprovider` | **305 passed**（不带该 PATH 时 3 条因缺 `datamodel-codegen` 失败，属环境，与本改动无关） |
| verify | `PATH=$V/bin:<scratchpad>/b15-tools/node_modules/.bin:$PATH ./scripts/verify.sh` | exit 0（`Scaffold verification passed.`） |
| diff | `git diff --check` | exit 0 |

### 反向篡改（改前 `cp` 备份，改回后 `cmp` 一致，每次换新字节码目录）

| # | 篡改 | 结果 |
| --- | --- | --- |
| T1 | `TRANSIENT_ERROR_CLASSES` 加入 `AUTH`（鉴权被重试/切换） | 5 failed |
| T2 | `Retry-After` 不封顶 | 2 failed |
| T3 | 仓储任务预算 `used >= task_budget` 改 `>` | 1 failed |
| T4 | 预写异常被吞掉、继续发请求 | 2 failed |
| T5 | 发请求前 `logger.debug` 输出提示词正文 | 1 failed |

## 待决（未自行拍板）

1. **退避参数的环境变量**：`config.py` 无对应项，本任务以构造参数注入（默认 `base 1 s`、`max 8 s`，硬上限 30 s）。建议登记 `LLM_RETRY_BACKOFF_BASE_SECONDS`（>0）、`LLM_RETRY_BACKOFF_MAX_SECONDS`（≥ base 且 ≤ 30），由 B06/A07 维护者写入 `docs/integrations.md`、`.env.example`、`config.py`，并随 D-02e 签收；同时更新 A07「单次调用耗时上界」为含退避的 392 s。
2. **「生成前被拒」在 `model_calls` 中的表示**：表无状态码列，本任务把这类错误的 `error_class` 存为 `"<class>:rejected_before_generation"`（如 `rate_limited:rejected_before_generation`），计费 SQL 以此后缀判断计 0。需协调方确认该取值格式并写入 `integrations.md`「调用记录」；若改为新增列需迁移。
3. **`malformed_response` 的矩阵行**：A07 矩阵未列。本任务按「不重试、不切换、不计熔断」处理（E03 待决 4 提到 `insufficient_system_resource` 也落此类，按此规则不会切备用）。需确认是否应归入临时故障行。
4. **`LLM_MAX_RETRIES` 无上限**：`config.py` 只要求 ≥ 0。退避单次有上限，但总耗时随重试次数线性增长；是否给 `LLM_MAX_RETRIES` 设上限由 D-02e/B06 定。
5. **回写失败的处理**：本任务只记 ERROR 日志、照常返回结果（行停在 `sent` 按估算计，偏保守）。规格未规定，需确认。
6. **向量调用的策略包装**：A07 矩阵含「向量调用失败：重试同第一行、永不切换、独立熔断」及「向量调用同样记录」。本任务验收只要求包装 `ModelClient`，未包装 `EmbeddingClient`；建议 E07 用本文件的 `CircuitBreaker`、`BackoffPolicy`、`SqliteCallStore`（`purpose = "embedding"`）实现，或另开小任务。另 E03 待决 12：一次 `embed()` 可能对应多次 HTTP 请求，逐请求记录需 E07 保证批大小一致。
7. **`purpose` 枚举**：本任务直接取 `ModelRequest.purpose`；向量用途约定为 `embedding`（`EMBEDDING_PURPOSE`）。E03 待决 8 的枚举仍待协调方写入 `integrations.md`。
8. **fake 模式模型 ID**（E02 待决 1）：`from_settings` 在主用或备用模型 ID 为空时不建立映射（即不切备用）；fake 模式用什么固定 ID 仍待装配处定。
9. **同一主用模型映射到两个不同备用模型**（如 `LLM_EXTRACTION_MODEL == LLM_CHAT_MODEL` 而备用两项不同）：`from_settings` 拒绝构造（`ValueError`）。是否应在 B06 启动校验阶段拒绝，待定。

## 风险

- 熔断状态只在进程内：多 worker 进程各自计数（A07 已接受，`WORKER_PROCESSES` 默认 1）。
- 预算为软上限：并发调用在同一时刻都通过检查时，实际用量至多超出「并发数 × 单次计费量」（A07 已接受）。
- 每次调用两次短连接写 SQLite（预写、回写）；`prewrite` 使用 `BEGIN IMMEDIATE`，高并发下受 `busy_timeout = 5000 ms` 约束，超时即 `CallRecordError`（不发请求）。
- 每日预算按 `created_at` 范围查询（有索引），任务预算按 `task_id` 索引；记录量很大时可再评估汇总表。

## 下一步

- E05：用 `is_repair=True` 的绑定客户端做单次修复；修复调用独立记录、照常计费（LEASE-25）。
- E06/E12：装配每进程一个 `ModelCallPolicy`，每块尝试 `bind`；按上文异常映射接 ADR-011 L2/阶段级临时故障与 `EXTRACTION_INCOMPLETE` 计数。
- J03/J05：`CallAttribution(course_id, request_id)`；改写调用被拒按 J03 超时降级，答案调用被拒返回 `BUDGET_EXCEEDED`。
- B06/A07：登记待决 1 的两个变量；D-02e 签收时确认 392 s 上界。

## 回滚

本任务只新增三个源/测试文件与本交接，未改迁移与既有模块：回滚即还原本提交（`git revert <sha>`），无数据迁移。
