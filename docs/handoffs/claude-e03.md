# Claude 交接：E03 实现兼容 API 适配器

- task_id: E03（GitHub issue #83；未改 issue、未建 PR）
- review_status: ready_for_review
- worktree: `.claude/worktrees/e03-compatible-api`，分支 `claude/e03-compatible-api`
- base: `36670a3`（认领提交 `54b37d8`）
- head: 本交接所在提交（实现、测试、交接、任务板同一提交）
- 状态：实现与验证完成，待 PR 审查/合并

## 改动文件

| 文件 | 说明 |
| --- | --- |
| `src/backend/app/services/ai/compatible.py` | 新建：`CompatibleModelClient`（实现 E02 的 `ModelClient`）、可注入传输协议 `HttpTransport`/`HttpResponse`、标准库默认传输 `StdlibTransport`、输入估算 `estimate_input_tokens` |
| `tests/backend/test_e03.py` | 新建：68 个测试函数，参数化后 173 条 |
| `docs/handoffs/claude-e03.md` | 本文件 |
| `docs/tasks.md` | 仅「2026-09-25 第二批并行（Claude）」E03 表的状态与证据列 |

未改 `client.py`、`fake.py`、`embeddings.py`、`config.py`、`pyproject.toml`、`.env.example`、`docs/integrations.md`、`scripts/verify.sh`。未新增任何依赖（运行时只用标准库 `http.client`/`ssl`/`json`）。

## 关键决定（依据）

1. **只做「一个请求 → 一次供应商调用」**。重试、主备切换、熔断、预算、`model_calls` 预写/回写都归 E04（`docs/integrations.md`「模型接入规则」，atomic E04 行）。适配器不记日志、不重试。
2. **每个请求都声明输出上限**（`integrations.md`「调用记录」第 4 条、ADR-011 修订 2）：请求体总带 `max_tokens = ModelRequest.max_output_tokens`；构造参数 `max_tokens_field="max_completion_tokens"` 可切到 OpenAI 新字段名（见待决 2）。
3. **输入估算只偏大**：`estimate_input_tokens(request) = 32 + Σ(内容 UTF-8 字节数 + 角色名长度 + 16)`。依据：字节级 BPE 分词器（OpenAI、DeepSeek、Qwen 系）每个 token 至少覆盖 1 个 UTF-8 字节，故字节数是内容 token 数的上界；每条消息 16、每次请求 32 覆盖对话模板的角色标记和回复引导。中文约 3 字节/字，估算约为真实值的 2～5 倍，按 ADR-011 修订 2「估算只会偏保守」属有意方向。供 E04 预写 `input_tokens_est`。
4. **流式请求请求 usage**（ADR-011 修订 3）：`stream=true` 时总带 `stream_options: {"include_usage": true}`；usage 取任一 chunk 中最后一个可解析的 `usage`（OpenAI 在 `choices` 为空的末尾 chunk 给出，也兼容放在带 `finish_reason` 的 chunk 里）。
5. **错误分类与 E02 一致**（`integrations.md`「调用记录」第 5 条）：

   | 情形 | 错误类 | `status_code` | 生成前被拒 |
   | --- | --- | --- | --- |
   | 408 | `ModelTimeoutError` | 408 | 否 |
   | 429（`Retry-After` 秒数写入 `retry_after_seconds`） | `ModelRateLimitedError` | 429 | 是 |
   | 401 / 403 | `ModelAuthError` | 原值 | 是 |
   | 其余 4xx（400、404、413、422 等） | `ModelInvalidRequestError` | 原值 | 400/404/413/422 是，其余（如 402/409）否 |
   | 5xx | `ModelServerError` | 原值 | 否 |
   | 客户端超时（套接字超时或整体时限到期），流前流中都算 | `ModelTimeoutError` | 空 | 否 |
   | 发请求或收非流式响应时连接失败（拒绝、DNS、重置、`http.client` 异常） | `ModelConnectionError` | 空 | 否 |
   | 流已以 200 打开后：未到 `[DONE]` 就结束、连接重置、`error` 事件 | `ModelStreamInterruptedError` | 空 | 否 |
   | 协议层无法解析：非 JSON、结构不对、`finish_reason` 不是 `stop`/`length`、200 带 `error` 对象、1xx/3xx/204、超过 `max_response_bytes`（默认 8 MiB）、流的 `Content-Type` 不是 `text/event-stream` | `ModelMalformedResponseError` | 响应状态（不在 100～599 时为空） | 否 |

   「生成前被拒」直接复用 E02 的 `rejected_before_generation`（由状态码派生），测试断言在全部映射中被拒集合恰为 `{400,401,403,404,413,422,429}`。错误响应体（至多读 64 KiB）中的 `usage` 附到错误上（「错误响应带 usage 也照此计」）。
6. **缺 usage 不是失败**：usage 缺失、为 null、字段缺失、负数、布尔、小数、字符串一律视为 `None`，调用照常成功，由 E04 按修订 3 取估算。`model` 字段缺失或非字符串时 `model_responded = None`。
7. **超时是整体时限**：`timeout_seconds`（缺省用构造参数，`from_settings` 取 `LLM_REQUEST_TIMEOUT_SECONDS`）从发请求起算，每次读取只给剩余时间，读后再核对时钟，慢速滴流的响应也不会超出（问答链路由 J05 传剩余时间）。时钟可注入。
8. **流是惰性的**：`stream()` 返回生成器，第一次 `next()` 才发请求；`close()` 立即释放连接；`StreamDone` 前已关闭连接。收到 `[DONE]` 后不再读取。
9. **坏 JSON 输出不是调用失败**：与 E02 一致，内容本身是坏 JSON 时返回正常 `ModelResult`（有 usage），`result.json()` 抛 `ModelOutputError` 供 E05 修复。`reasoning_content` 等额外字段忽略，不并入正文。
10. **日志安全**：模块不记日志；错误一律在 `except` 之外 `raise … from None` 抛出（无 `__cause__`/`__context__`），只含模型 ID、状态码、usage、`Retry-After`；`repr(client)` 只含 URL。密钥要求为可打印 ASCII 且无空格：否则 `http.client` 会抛出携带密钥原文的 `UnicodeEncodeError`，且换行可注入请求头。`base_url` 拒绝凭据、查询串、片段，错误信息不回显取值。
11. **向量 HTTP 不在本任务**：见待决 1。

## 接口（给 E04、E05、J03、J05、B06 装配处）

```python
from app.services.ai.compatible import CompatibleModelClient, estimate_input_tokens

primary = CompatibleModelClient.from_settings(settings)                    # LLM_BASE_URL / LLM_API_KEY
fallback = CompatibleModelClient.from_settings(settings, role="fallback")  # 未配置时 ValueError（点名变量）
est = estimate_input_tokens(request)       # E04 预写 input_tokens_est；max_output_tokens 取 request 本身
result = primary.complete(request)         # 或 for event in primary.stream(request): ...
```

- 测试注入：`CompatibleModelClient(base_url, key, transport=..., clock=...)`；传输只需实现 `open(url, body, headers, timeout) -> HttpResponse`（`status`、`header(name)`、`read(amount, timeout)`、`close()`），超时抛 `TimeoutError`，连接问题抛 `OSError`/`http.client.HTTPException`。
- E04：按 `error.error_class`、`error.rejected_before_generation`、`error.usage`、`ModelRateLimitedError.retry_after_seconds` 执行切换矩阵与计费。

## 协议字段及来源

| 字段 | 取值 | 来源（2026-09-25 核对） |
| --- | --- | --- |
| 端点 | `POST {base_url}/chat/completions`，`Authorization: Bearer <key>` | OpenAI OpenAPI 规范 `openai/openai-openapi` `openapi.yaml`（GitHub raw）；platform.openai.com 文档页返回 403，未能直接读取 |
| `max_tokens` / `max_completion_tokens` | OpenAI 标 `max_tokens` 为 Deprecated，由 `max_completion_tokens` 取代；DeepSeek 只接受 `max_tokens` | 同上；DeepSeek API 文档 `api-docs.deepseek.com/api/create-chat-completion` |
| `response_format` | `{"type": "json_object"}`（OpenAI、DeepSeek 均支持） | 同上 |
| `stream_options.include_usage` | OpenAI：末尾 chunk 带 usage 且 `choices` 为空，其余 chunk `usage` 为 null；DeepSeek：同样支持，除最后一个外 `usage` 为 null | 同上 |
| `finish_reason` | OpenAI：`stop`/`length`/`tool_calls`/`content_filter`/`function_call`；DeepSeek 另有 `insufficient_system_resource`、`aborted` | 同上 |
| `usage` | `prompt_tokens`、`completion_tokens`（及 `total_tokens`、明细） | 同上 |
| 流结束 | `data: [DONE]` | OpenAI 流式约定（同上规范与 SDK 行为） |

通义千问（DashScope 兼容模式）文档本次访问失败（连接被拒），未核对。

## 命令与实际结果

环境：会话 scratchpad 中独立 venv（`python3 -m venv`，按 `pyproject.toml` 逐个安装运行时与测试依赖，不安装本包、不碰共享 venv），以绝对路径 `PYTHONPATH=<worktree>/src/backend` 运行。系统 python3 3.13.5。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 基线 | `<venv>/bin/python -m pytest tests/backend -q` | 1002 passed，1 warning（既有），exit 0 |
| 红（无实现） | `<venv>/bin/python -m pytest tests/backend/test_e03.py -q` | 收集错误 `No module named 'app.services.ai.compatible'`，exit 2 |
| 红（只含名字的桩） | 同上 | 171 failed，exit 1（其余 2 条参数化后在实现阶段新增，见下） |
| 绿 | 同上 | 173 passed，exit 0 |
| 全量 | `<venv>/bin/python -m pytest tests/backend -q` | 1175 passed，1 warning（既有），exit 0 |
| 门禁 | `./scripts/verify.sh` | `Scaffold verification passed.`，exit 0 |
| 空白 | `git diff --check` | exit 0 |
| 类型 | `mypy --strict --python-version 3.11 app/services/ai/compatible.py`（本机 anaconda mypy，非项目门禁） | 本文件无问题；报出的 1 条在 `app/config.py:96`（既有的多余 `type: ignore`，不属本任务） |

实现过程中的一次修正：测试密钥原含中文，`StdlibTransport` 用例因 `http.client` 以 latin-1 编码请求头而抛出带密钥原文的 `UnicodeEncodeError`。据此把密钥校验收紧为可打印 ASCII、无空格，并新增 `sk-密钥`、`sk abc` 两个负例（171 → 173 的来源）。

篡改检出（逐项篡改 → 运行 E03 测试 → 从备份恢复并 `cmp` 核对逐字节一致，恢复后 173 passed）：

| 篡改 | 检出 |
| --- | --- |
| T1 流式请求不带 `stream_options.include_usage` | 2 failed |
| T2 请求体不声明输出上限 | 7 failed |
| T3 读超时误归为连接/中断错误 | 2 failed |
| T4 输入估算按字符数而非 UTF-8 字节 | 1 failed |
| T5 错误响应丢弃 usage | 1 failed |

回环测试：默认 `StdlibTransport` 只对 `127.0.0.1` 上的本地 `http.server` 测试（非流式、分块 SSE 流式、429 + `Retry-After`、0.2 秒超时、端口拒绝连接），不联网、不需密钥。

## 待决 / 需实测（未自行拍板）

1. **向量 HTTP 客户端无人认领**：E02 交接写「E03 实现 `ModelClient`/`EmbeddingClient`」，而 E07（#217）的 `EmbeddingAdapter` 只包装注入的 `EmbeddingClient`、不做 HTTP；atomic E03 行只写「HTTP 模型调用」。本任务按指示只做对话侧。`EMBEDDING_MODE=online` 的 `POST {EMBEDDING_BASE_URL}/embeddings`（带 `dimensions`）需协调方决定归 E03 续作还是新叶子任务；实现时可复用本文件的 `HttpTransport`、超时与错误映射。
2. **`max_tokens` 与 `max_completion_tokens`**：默认 `max_tokens`（DeepSeek 只认它，OpenAI 标为已弃用且 o 系列不接受）。D-02a/b 签收时按所选供应商确认；如需按配置切换，要在 `integrations.md`/`.env.example` 登记变量并在装配处传入（本任务不改这些文件）。
3. **流式 usage 是否返回**：OpenAI 与 DeepSeek 文档称支持 `include_usage`；通义千问兼容模式未核对。D-02a/b 签收时实测并注明（ADR-011 修订 3）。
4. **`finish_reason` 超出 E02 的 `stop`/`length`**：`content_filter`、`tool_calls`、`insufficient_system_resource`、`aborted` 目前一律按 `malformed_response` 失败（保留 usage）。其中 `insufficient_system_resource` 语义更接近服务端故障、`content_filter` 更接近内容问题；是否要在 E02 增加类别或结局，需 E04/J05 决定（改 `client.py` 须另开任务）。
5. **缺 `[DONE]` 的流**：按严格规则视为中断（`stream_interrupted`）。若某供应商以 `finish_reason` 结束但不发 `[DONE]`，所有流式调用都会失败，需实测。
6. **`Retry-After` 只解析秒数**：HTTP 日期格式视为缺失（`None`），由 E04 用自身退避。
7. **输入估算的覆盖面**：不含供应商在服务端注入的隐藏系统提示；JSON 模式下若供应商追加说明文字也未计入。K 组若有真实 usage，可据此核对偏差是否始终为正。
8. **`purpose` 枚举**（`integrations.md` 写「枚举由 E03 定」）：本任务未落代码。提议取 E01 提示词文件名（`extract_entities`、`extract_entities_gleaning`、`extract_relations`、`judge_duplicate`、`summarize_definition`、`rewrite_query`、`answer_with_context`）加 `repair`（或以 `is_repair` 区分而沿用原用途）与 `embedding`，需协调方确认后写入 `integrations.md`，由 E04 落到 `model_calls`。
9. **JSON 模式的提示要求**：OpenAI 的 `json_object` 要求消息中出现 “JSON” 字样，否则返回 400；由各提示词模板保证（E01/E05），适配器不改写消息。
10. **TLS 证书错误**归为 `connection`，按切换矩阵会被重试、计入熔断；配置错误也会被当作可用性故障，可在 E04 视需要单列。

## 风险

- 估算明显偏大，供应商不返回 usage 时预算会提前触顶（ADR-011 修订 3 已接受的保守方向）。
- `StdlibTransport` 每次调用新建连接（无连接池），高并发时有握手开销；需要时可注入带连接复用的传输，不影响适配器。
- 真实供应商未联调（取值待 D-02a），协议差异只能在签收后实测确认。

## 下一步

- 协调方：审查并合并；把待决 1、2、4、8 登记到 `docs/tasks.md` 未决问题。
- E04 首个动作：用 `estimate_input_tokens` 与 `request.max_output_tokens` 预写，包装 `CompatibleModelClient`，按错误类实现切换矩阵（可继续用 E02 的 fake 或本测试中的脚本化传输）。

## 回滚

只新增文件，无迁移、无依赖变化：`git revert` 本分支的 E03 提交即可（任务板 E03 行随之回到 IN PROGRESS）。
