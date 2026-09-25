# Claude 交接：E02 建立模型接口和 fake 适配器

- task_id: E02（GitHub issue #82；未改 issue、未建 PR）
- review_status: ready_for_review
- worktree: `.claude/worktrees/e02-ai-client`，分支 `claude/e02-ai-client`
- base: `8eeac3b`（认领提交 `38ef62d`）
- head: `c87ae5c`（实现与测试）+ 本交接提交
- 状态：实现与验证完成，待 PR 审查/合并

## 改动文件

| 文件 | 说明 |
| --- | --- |
| `src/backend/app/services/ai/client.py` | 统一请求/结果/流事件/向量请求结果、类型化错误、`ModelClient` 与 `EmbeddingClient` 协议 |
| `src/backend/app/services/ai/fake.py` | `FakeModelClient`、`FakeEmbeddingClient`、`FakeReply`、`FakeEmbedding`、`FakeCall`、`BAD_JSON_TEXT` |
| `tests/backend/test_e02.py` | 65 条测试 |
| `docs/handoffs/claude-e02.md` | 本文件 |
| `docs/tasks.md` | 仅「2026-09-25 并行批次」E02 表的状态与证据列 |

`ai/__init__.py` 已由 E01 建立，未改。未新增依赖，未改共享文件。

## 关键决定（依据）

1. **适配器只做「一个请求 → 一次供应商调用」**。重试、主备切换、熔断、预算、`model_calls` 预写/回写都在 E04（`docs/integrations.md`「模型接入规则」、atomic E04 行）。E02 只暴露 E04 判断所需的事实，不在异常上编码「是否重试/是否切备用」这类策略，以免与 E04 冲突。
2. **`ModelRequest.max_output_tokens` 必填**：`integrations.md`「调用记录」第 4 条要求每个 LLM 请求声明输出上限（预写估算用）。其余字段：`purpose`（小写标识符，与 E01 用途名同形；`model_calls.purpose` 枚举仍由 E03 定）、`model`（请求的模型 ID，非空）、`messages`（`system`/`user`/`assistant`）、`response_format`（`text`/`json`）、`timeout_seconds`（可空；worker 用 `LLM_REQUEST_TIMEOUT_SECONDS`，问答用剩余时限，由调用方传入）。
3. **结果带两个模型 ID**：`ModelResult.model_requested`、`model_responded`（响应中的 `model` 字段，可空），对应 `model_calls` 的 `model_requested`/`model_responded`。`usage: Usage | None`，`None` 表示响应无可解析 usage，由 E04 按估算或 0 计费（ADR-011 修订 3）。`finish_reason ∈ {stop, length}`（grounded-qa O6 用 `length`）。
4. **错误分类**（`ErrorClass`，一类对应切换矩阵一行）：`timeout`（含 408）、`connection`、`rate_limited`（429，可带 `retry_after_seconds`）、`server`（5xx）、`auth`（401/403）、`invalid_request`（其余 4xx，含 400/404/413/422）、`stream_interrupted`、`malformed_response`（协议层无法解析）。每类限制可用状态码，错配即 `ValueError`。`rejected_before_generation` 由状态码 ∈ `{400,401,403,404,413,422,429}` 派生（`integrations.md`「调用记录」第 5 条）。错误可携带错误响应中的 `usage`（「错误响应带 usage 也照此计」）。
5. **坏 JSON 不是调用失败**：矩阵把「输出不合规」列为质量问题、不走 L1、不计熔断。调用成功并计费，`ModelResult.json()` 严格解析（拒绝 NaN/Infinity），失败抛 `ModelOutputError(reason="invalid_json")` 并附上 `result`（含 usage），供 E05「修复最多一次」使用。
6. **同步接口**：worker 是子进程（ADR-011），问答的 SSE 可用 Starlette 在线程池迭代同步生成器。流是生成器：错误在迭代中抛出，调用方用 `close()` 提前结束（J05 哨兵后关闭）。
7. **向量接口也放在这里**：`EmbeddingRequest(model, texts, dimensions)`、`EmbeddingResult(vectors, model_requested, model_responded, usage)`，因为向量调用同样进 `model_calls`、同样适用切换矩阵的错误分类，且 fake 文件归 E02 所有。维度核对、空批次处理、批量上限、部分失败都留给 E07；fake 可脚本化返回错误维度，不替 E07 隐藏不一致。
8. **fake 规则**（`integrations.md`：fake「按输入确定性输出、可注入故障并上报模拟 usage」）：
   - 摘要用 sha256，覆盖 purpose、model、response_format 和全部消息；跨进程一致（测试用不同 `PYTHONHASHSEED` 的子进程核对）。
   - 默认输出：文本模式 `[fake <purpose> <digest16>]`；JSON 模式 `{"digest":…,"fake":true,"purpose":…}`。
   - 模拟 usage：1 字符 = 1 token（输入为全部消息字符数，输出为返回字符数）。这是 fake 规则，不是分词估算。
   - 遵守输出上限：超出即截断到 `max_output_tokens` 个字符并置 `finish_reason = "length"`。
   - 脚本：`script(*steps, purpose=None)`，步骤为文本、`FakeReply` 或 `ModelCallError` 实例；先取本用途队列，再取通用队列，再用 `responder`，最后用默认输出。`FakeReply` 可指定 `chunks`、`usage`（含 `None`）、`model_responded`（模拟别名）、`error_after_chunks=(n, error)`（流在 n 个 delta 后出错；`complete()` 不论 n 都抛出）。
   - 记录：`calls` 中每条有 `kind`、`request`、`outcome`（`ok`/错误类/`closed`/`pending`）、`chunks_delivered`、`closed_early`。
   - 超时是立即抛出 `ModelTimeoutError`，不真实等待；线程安全（加锁）。
9. **日志安全**：`Message.content`、`ModelResult.text`、`StreamDelta.text`、`EmbeddingRequest.texts`、`EmbeddingResult.vectors`、`FakeReply.text/chunks` 都不进 `repr`；错误信息只含错误类、模型 ID 与状态码。

## 接口（给 E03～E07、E10～E12、J03、J05、O06）

```python
from app.services.ai.client import Message, ModelRequest, ModelCallError, ModelOutputError, StreamDelta, StreamDone
from app.services.ai.fake import FakeModelClient, FakeReply, BAD_JSON_TEXT

req = ModelRequest(purpose="extract_entities", model=model_id,
                   messages=[Message("user", rendered.text)],
                   max_output_tokens=2048, response_format="json")
result = client.complete(req)          # ModelResult：text / model_requested / model_responded / usage / finish_reason
data = result.json()                   # 失败 → ModelOutputError（.result 仍可计费）
for event in client.stream(req):       # StreamDelta* 然后 StreamDone(result)；错误在迭代中抛出
    ...

fake = FakeModelClient()
fake.script(ModelRateLimitedError(model_id), BAD_JSON_TEXT, FakeReply('{"entities": []}'))
```

- **E03**：实现 `ModelClient`/`EmbeddingClient`，把 HTTP 结果映射到上述错误类（`408` → `ModelTimeoutError(status_code=408)`；`413` → `ModelInvalidRequestError(status_code=413)`；无法解析 → `ModelMalformedResponseError`），流式请求 usage。
- **E04**：按 `error_class` 与 `rejected_before_generation` 执行切换矩阵与计费；fake 的 `calls` 与模拟 usage 可直接测预算与熔断。
- **E05**：用 `result.json()` 捕获 `ModelOutputError` 后发一次修复调用（`purpose` 由 E03 的枚举决定）。
- **E07**：`FakeEmbeddingClient` 给出 `(model, dimensions, text)` 决定的单位向量；用 `FakeEmbedding(vectors=…)` 模拟维度不符。
- **J05**：`FakeReply(chunks=…)` 脚本化逐块输出；`calls[i].closed_early` 断言哨兵后关闭（QA-8）；`error_after_chunks` 模拟出字后中断（QA-25）。

## 命令与实际结果

环境：会话 scratchpad 中独立 venv（`python3 -m venv`，`pip install './src/backend[test]'` 后卸载本包，只留依赖），以 `PYTHONPATH=<worktree>/src/backend` 运行，避免共享 venv 的 editable 安装指向其他 worktree（首次运行曾发现 `app` 被解析到 `d06-pdf-headings`，已改用独立 venv 重测）。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 基线 | `<venv>/bin/python -m pytest tests/backend -q` | 720 passed，exit 0 |
| 红 | `<venv>/bin/python -m pytest tests/backend/test_e02.py -q`（只有测试） | 收集错误 `ModuleNotFoundError: No module named 'app.services.ai.client'`，exit 2 |
| 绿 | 同上（实现后） | 65 passed，exit 0 |
| 全量 | `<venv>/bin/python -m pytest tests/backend -q` | 785 passed，1 warning（既有），exit 0 |
| 门禁 | `./scripts/verify.sh`（系统 python3 3.13.5） | `Scaffold verification passed.`，exit 0 |
| 空白 | `git diff --check` | exit 0 |
| 类型 | `mypy --strict --python-version 3.11 app/services/ai/client.py app/services/ai/fake.py`（本机 anaconda mypy，非项目门禁） | no issues |
| 系统解释器 | `python3 -m pytest tests/backend/test_e02.py -q`（系统 python3 无后端依赖、未安装本包） | `No module named 'app'`，exit 2；与 E01 交接第 4 条相同，属环境问题 |

篡改检出（逐项篡改 → 运行 E02 测试 → 恢复，恢复后 65 passed、文件逐字节一致）：

| 篡改 | 检出 |
| --- | --- |
| 生成前被拒集合去掉 413 | 1 failed |
| 摘要改用 `hash()` | 1 failed（跨进程一致性） |
| 不按输出上限截断 | 2 failed |
| `json()` 接受 NaN/Infinity | 3 failed |
| 流提前关闭不记录 | 1 failed |

## 待决（未自行拍板）

1. **fake 模式下的模型 ID**：`LLM_MODE=fake` 时 `LLM_*_MODEL` 可为空，而 `ModelRequest.model` 要求非空。fake 模式由谁、用什么固定 ID（如 `fake`）填充，影响 D09 缓存键与 `model_calls.model_requested`，需在 E03/E04 的装配处定，建议同时写入 `integrations.md`。向量同理（`embedding_space_state` 的 fake 行 `model` 为空串，ADR-012）。
2. **缓存键用哪个模型 ID**：`integrations.md` 写「实际给出结果的那个」，未说明取 `model_requested`（成功那次调用所请求的）还是 `model_responded`（响应字段，可能是别名展开）。E02 两者都给，由 D09/E 组定。
3. **生成参数**：规格未定 `temperature` 等参数，本接口未加；若 E03 核对供应商协议后需要，应先在规格中定义再扩展 `ModelRequest`（需改 client.py，届时另开任务或由 E03 认领该文件）。
4. **`purpose` 枚举**：按 `integrations.md` 由 E03 定；E02 只校验小写标识符格式。
5. **首字超时**：接口不区分首字超时与整体超时（都是 `ModelTimeoutError`），由 J05/E04 用时钟判断；如需区分字段，由 J05 提出。

## 风险

- fake 的 1 字符 = 1 token 与真实分词差异大，只用于逻辑测试；K 组不得把 fake 结果或用量当真实数据。
- 同步接口若将来问答改为纯 asyncio 实现，需要包装层；目前无 ADR 约定同步/异步，本选择写在此处供审查。
- `ModelResult.json()` 只做 JSON 语法检查，结构校验由各调用方负责。

## 下一步

- 协调方：审查并合并；登记待决 1、2 到 `docs/tasks.md` 未决问题。
- E03 首个动作：读本交接「接口」节，按错误类映射 HTTP 结果。

## 回滚

只新增文件，无迁移、无依赖变化：`git revert` 本分支两个提交（实现、交接/任务板）即可。
