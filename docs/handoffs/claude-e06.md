# Claude 交接：E06 实现补漏实体抽取（gleaning）

- task_id: E06（GitHub issue #86）
- review_status: ready_for_review
- worktree: `/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/e06-gleaning`，分支 `claude/e06-gleaning`
- base: `85adfa7`（第七批认领提交）
- 状态：实现与验证完成，待 PR 审查/合并

## 改动文件

| 文件 | 说明 |
| --- | --- |
| `src/backend/app/services/ai/gleaning.py` | 新增。`EntityGleaner`：块文本 + 首轮 E05 候选 → 遗漏实体差量 |
| `prompts/extract_entities_gleaning.yaml` | 正文替换，版本 1 → **2**：五类闭集、字段长度、证据逐字摘录与 E05 v2 一致；只输出遗漏、不输出已有条目或其变体；已抽取列表同样只当数据 |
| `prompts/MANIFEST.md` | 只改 `extract_entities_gleaning` 一行：版本 2、新摘要 `61a0c8d0…97c7e`、状态 `占位` → `草稿` |
| `tests/backend/test_e06.py` | 新增，61 个用例，只用 E02 `FakeModelClient`（部分经真实 E04 `ModelCallPolicy` + SQLite `model_calls`） |
| `docs/tasks.md` | 只改 E06 行状态与证据列 |
| `docs/handoffs/claude-e06.md` | 本文件 |

E05 文件（`entities.py`、`extract_entities.yaml`、`test_e05.py`）未改动。

## 接口

```python
gleaner = EntityGleaner(client, model=LLM_EXTRACTION_MODEL, max_output_tokens=N,
                        enabled=False, max_rounds=DEFAULT_MAX_ROUNDS,
                        prompts=None, timeout_seconds=None)
result = gleaner.glean(identity: ChunkIdentity, text: str,
                       first_pass: Sequence[EntityCandidate]) -> GleaningResult
entity_name_key(name: str) -> str
```

- 常量：`GLEANING_PROMPT_PURPOSE = "extract_entities_gleaning"`、`GLEANING_PROMPT_VERSION = 2`、`DEFAULT_MAX_ROUNDS = 1`、`MAX_ROUNDS_HARD_LIMIT = 3`。
- `GleaningResult`：`chunk_id`、`added`（`EntityCandidate` 差量，类型与出处结构同 E05）、`stop_reason`、`rounds`、`model_calls`、`duplicates`、`dropped: dict[DropReason, int]`、`failure: ExtractionFailure | None`、`prompt_purpose`/`prompt_version`/`prompt_sha256`（未渲染时为 `None`）、`model_id`；属性 `ok`（`stop_reason` 不是 `budget_exceeded`/`output_invalid`）、`error_code`（仅预算被拒时为 `"BUDGET_EXCEEDED"`）。
- `StopReason`：`disabled`、`empty_chunk`、`no_new_entities`、`max_rounds`、`budget_exceeded`、`output_invalid`。
- 输入校验（均在任何调用之前）：`first_pass` 必须是 `EntityCandidate` 且属于同一课程同一块，否则 `TypeError`/`ValueError`；`text_sha256(text)` 须等于 `identity.text_sha256`。

## 关键决定（依据）

1. **开关用构造参数，默认关闭**：`docs/architecture-review-2026-09-22.md` 只写「补漏独立开关」，`docs/integrations.md` 与 `.env.example` 未登记任何补漏变量。按任务要求不擅自加配置：`enabled: bool = False`，关闭时不渲染提示词、不调用客户端、不写 `model_calls`。取值来源见待决 1。
2. **轮数有界**：`max_rounds` 须为 `1..3` 的 `int`（`bool`、浮点、越界直接 `ValueError`，不静默截断）；默认 1 轮。某轮无新增（全重复、全被丢弃或空数组）即提前停止，不再花预算。
3. **去重（不依赖 E08）**：`entity_name_key` = NFKC（全半角）→ `casefold`（大小写）→ 去掉全部空白。只按名称比对，类型不参与（同名不同类型视为重复，归并交 E08/E10）。同一回复内与跨轮次同样去重，保留先出现者；重复计入 `duplicates`。不做同义词/标点归一（那是 E08 的语义去重范围）。
4. **复用 E05 校验**：直接导入 `entities._parse`、`entities._validate`、`entities._OutputRejected`（模块私有名，未改 E05 文件），因此类型闭集、长度、置信度、证据子串、出处对齐与 E05 完全一致；E05 的 `NAME_MAX_CHARS` 等变更自动生效（提示词需同步升版本）。
5. **输出不合规**：同 E05——同一模型、同一消息修复一次（`purpose = "repair"`），仍不合规即停止，`stop_reason = output_invalid`、`failure = ExtractionFailure(reason, 2)`，`ok = False`；此前轮次已得的差量保留在 `added` 中。条目级不合格只丢弃计数、不触发修复。
6. **预算被拒**：E04 策略在调用前抛 `BudgetExceededError`（未发请求、不写记录）时停止，返回已得差量，`stop_reason = budget_exceeded`、`ok = False`、`error_code = "BUDGET_EXCEEDED"`。依据 A07「预算」：抽取阶段（实体、补漏、关系）被拒调用即本次块尝试失败——由编排方按此处理（见待决 2）。修复调用被拒同样处理。其他 `ModelCallError`/`PolicyError`（超时、熔断、预写失败等）原样抛出，与 E05 一致。
7. **调用记录归属**：本模块不构造归属，调用方传入 `ModelCallPolicy.bind(CallAttribution(course_id, task_id, chunk_id, task_attempt, chunk_attempt))`；请求 `purpose` 取提示词文件名 `extract_entities_gleaning`、修复取 `repair`（E03 交接待决 8 提议、E04 直接落 `ModelRequest.purpose` 的约定）。测试以真实 SQLite 断言每行的课程/任务/块/尝试序号、`call_seq` 递增与 `purpose`。
8. **不泄露**：只记一条 INFO 日志，内容为块 ID、停止原因与计数；块文本、实体名、定义、证据、提示词、模型输出不入日志；`EntityGleaner`/`GleaningResult` 的 `repr` 不含正文（`EntityCandidate` 的 `definition`、`evidence` 本就 `repr=False`）。

## 验证（实际结果）

环境：`S=/private/tmp/claude-501/.../scratchpad`，`python3 -m venv $S/venv-e06 && $S/venv-e06/bin/pip install -e './src/backend[test]'`（自建，未复用他人 venv），运行时 `PYTHONPATH=$PWD/src/backend`、`PYTHONPYCACHEPREFIX` 指向 scratchpad。

| 命令 | 结果 |
| --- | --- |
| 红灯：`pytest tests/backend/test_e06.py -q -p no:cacheprovider`（实现前） | 收集错误 `ModuleNotFoundError: app.services.ai.gleaning`，1 error |
| 首次绿灯 | 59 passed、2 failed——均为测试自身错误（`ModelServerError` 构造参数应为模型 ID；用 `(P2,)` 造的「另一块」与原块 `chunk_id` 相同），改测试后通过 |
| `pytest tests/backend/test_e06.py tests/backend/test_e01.py`（含 MANIFEST 摘要校验，测试修正前） | 128 passed、2 failed（即上一行的两处测试错误）；E01 全部通过 |
| `pytest tests/backend/test_e06.py -q`（修正后） | **61 passed** |
| `pytest tests/backend -q` 全量 | **2338 passed**，1 条既有警告（285 s） |
| `PATH=$S/venv-e06/bin:$PATH ./scripts/verify.sh` | `PASS contracts gate`、`Scaffold verification passed.` |
| `git diff --check` | 通过 |

### 反向篡改（每次先备份，改后运行 `test_e06.py`，再 `cp` 还原并 `cmp` 一致）

| # | 篡改 | 结果 |
| --- | --- | --- |
| T1 | 忽略开关（`if not self._enabled` → `if False`） | 3 failed |
| T2 | 不去重 | 13 failed |
| T3 | 名称键不做 `casefold` | 5 failed |
| T4 | 不捕获 `BudgetExceededError` | 4 failed |
| T5 | 无新增时不提前停止 | 5 failed |
| T6 | 去掉轮数硬上限 | 2 failed |
| T7 | 日志带上新增实体名 | 1 failed |

## 接口 / 数据变更

- 新 Python 接口见上；无 wire 契约、数据库、Neo4j 模型或环境变量变化。
- 提示词 `extract_entities_gleaning` 版本 1 → 2（摘要 `61a0c8d0040e457d8310dc0d9e451769ee89e0b3c004fa73e8278042b3397c7e`）。尚无调用方与持久化缓存，无迁移。

## 风险

- **跨模块导入私有函数**：依赖 `entities._parse`/`_validate`/`_OutputRejected` 的签名；E05 重构这些名字时需同步本模块（测试会失败提示）。建议后续由 E05 负责方把它们提为公共函数（不在本任务文件锁内）。
- **名称键较保守**：只归一空白、大小写、全半角；同义写法（如「栈」与「堆栈」）仍会作为新增，交 E08/E10。
- **证据精确匹配**沿用 E05，可能丢掉细微改写的正确条目（`dropped` 可观察）。
- **`model_calls` 计数**是本模块发出的逻辑调用数，不含 E04 内部 L1 重试/备用调用（与 E05 一致）。
- **`is_repair`**：E04 的 `is_repair` 在 `CallAttribution` 层，同一个绑定客户端内的修复调用行 `is_repair` 仍为假，只能靠 `purpose = "repair"` 区分（E05 同样情况）。

## 待决

1. **补漏开关的取值来源**：文档只有「补漏独立开关」，未登记环境变量（如 `EXTRACTION_GLEANING_ENABLED`、轮数变量）。需协调方决定是否在 `docs/integrations.md`、`.env.example`、B06 设置中新增，还是由 E12/K13（消融实验）按构造参数传入。默认关闭、默认 1 轮、硬上限 3 轮为本任务暂定值，待签收。
2. **补漏失败是否拖垮整块**：A07 规定抽取阶段（含补漏）预算被拒即本次块尝试失败；输出不合规在矩阵中同样是块尝试失败。本模块据此返回 `ok = False` 并保留已得差量，但补漏是可选增强，另一种合理做法是「补漏失败只丢弃补漏结果、保留首轮」。需协调方在 E12 前确认；若改为降级，只需 E12 忽略 `ok`，本模块无需改动。
3. **缓存键**：D09 交接待决 4 指出补漏的 `entities_json` 不在缓存键内。本模块未给缓存键；若 E12 要缓存补漏结果，需先在 D09 增加「附加输入哈希」参数（先改规格）。
4. **输出不合规的错误码映射**：同 E05 待决 3，`ErrorCode` 无对应项，`error_code` 仅在预算被拒时有值。
5. **`purpose` 枚举**：仍按 E03 待决 8 的提议取提示词文件名与 `repair`，待协调方写入 `integrations.md`。

## 下一步

- **E12 编排**：首轮 `EntityExtractor.extract` 成功后，若开关开启，用同一个绑定客户端（同一 `CallAttribution`）调用 `EntityGleaner.glean(identity, text, extraction.candidates)`；把 `extraction.candidates + result.added` 交 E08；`result.ok` 为假时按待决 2 的结论处理（当前文档：本次块尝试失败，`BUDGET_EXCEEDED` 或输出不合规）。
- **K13 消融**：「两阶段 + 补漏」组以 `enabled=True` 构造；`duplicates`、`dropped`、`model_calls` 可直接作为成本/收益统计。
- 可选：把 E05 的 `_parse`/`_validate` 提为公共 API（E05 负责方）。

## 回滚

`git revert` 本任务提交即可：删除 `gleaning.py` 与 `test_e06.py`，恢复提示词版本 1 与 MANIFEST 原行，E06 行恢复 IN PROGRESS。无数据迁移。
