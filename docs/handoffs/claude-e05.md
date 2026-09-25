# Claude 交接：E05 实现块级实体抽取

- task_id: E05（未 push、未开 PR、未改 issue）
- review_status: ready_for_review
- worktree: `/home/user/wt-e05-entity-extraction`，分支 `claude/e05-entity-extraction`
- base: `f0814cc`（第五批认领提交）
- 状态：实现与验证完成，待 PR 审查/合并

## 改动文件

| 文件 | 说明 |
| --- | --- |
| `src/backend/app/services/ai/entities.py` | 新增。`EntityExtractor`：块 → 有来源的规范实体候选；输出校验、修复一次、缓存键 |
| `prompts/extract_entities.yaml` | 正文替换，版本 1 → **2**：五类闭集、字段长度、证据逐字连续摘录、置信度、无实体时输出空数组 |
| `prompts/MANIFEST.md` | **超出文件锁**：只改 `extract_entities` 一行（版本 2、新摘要、状态 `占位` → `草稿`）。理由见「关键决定 1」 |
| `tests/backend/test_e05.py` | 新增，63 个用例，只用 E02 `FakeModelClient` |
| `docs/tasks.md` | 只改 E05 行状态与证据列 |
| `docs/handoffs/claude-e05.md` | 本文件 |

## 输入与输出

```python
extractor = EntityExtractor(client, model=LLM_EXTRACTION_MODEL, max_output_tokens=N,
                            prompts=None, timeout_seconds=None)
result = extractor.extract(identity: ChunkIdentity, text: str) -> EntityExtraction
extractor.cache_key(identity, model_id=None) -> str   # 调用前查缓存用
```

- 输入：D09 `ChunkIdentity`（课程、资料、修订、块 ID、文本哈希、D08 出处）+ 块文本。`text_sha256(text)` 必须等于 `identity.text_sha256`，否则 `ValueError` 且不调用模型。
- `EntityExtraction`：`chunk_id`、`candidates`、`dropped: dict[DropReason, int]`、`failure: ExtractionFailure | None`（`ok` 属性）、`prompt_purpose`/`prompt_version`/`prompt_sha256`、`model_id`（给出结果那次调用所请求的模型，D09 `cache_model_id`）、`cache_key`（仅成功时有）、`model_calls`（0/1/2）。
- `EntityCandidate`：`name`、`type`（`concept|theorem|formula|method|example`）、`definition`、`evidence`、`confidence: float | None`、`source: EntitySource`。
- `EntitySource`：`course_id`、`document_id`、`revision_id`、`chunk_id`、`evidence_start`/`evidence_end`（证据在块文本中的半开区间，首次出现）、`sources`（证据覆盖到的 D08 `ChunkSource`，用于取 `page`/`section_path`；无法对齐时退回整块全部出处）。
- `DropReason`：`not_object`、`invalid_name`、`invalid_type`、`invalid_definition`、`invalid_evidence`、`evidence_not_in_chunk`、`invalid_confidence`。
- `FailureReason`：`invalid_json`、`invalid_structure`（非对象或没有 `entities` 数组）、`truncated`（`finish_reason = length`）。
- 模型调用错误（`ModelCallError` 各子类，含修复调用中的）原样抛出，不转为 `failure`：它们属于 L1/E04 与熔断判定，不是输出质量问题。

## 关键决定（依据）

1. **改 MANIFEST 一行（超出文件锁）**：E01 规定「改正文必须升版本……同一提交同时改调用方的版本号与本表的版本和摘要」，`tests/backend/test_e01.py::test_every_template_file_is_in_manifest_and_loads_with_default_root` 逐行比对摘要。占位版本 1 的输出格式没有 `type`，不改正文就拿不到五类类型；改正文而不改 MANIFEST 则 E01 测试失败。所以只改了这一行（版本、摘要、状态），其余行与说明未动。协调方若不接受，回滚这一行需同时回滚 yaml 与 `ENTITY_PROMPT_VERSION`。
2. **类型闭集**取契约 `KnowledgePointType`（`src/contracts/api.v1.yaml`，S2 表 6.3）；只接受小写原样，`Concept` 等变体丢弃计数，不做归一。
3. **证据**：去首尾空白后必须是块文本的连续子串（`str.find`，精确匹配，不做空白/标点/全半角归一）。改写、跨段拼接、资料里没有的都丢弃并计入 `evidence_not_in_chunk`。块文本含 D-13 章节路径前缀，摘录前缀也算原文（提示词里明确允许）。
4. **修复一次**：输出不合规（坏 JSON、顶层结构不对、截断）→ 用**同一模型**（`result.model_requested`）、**同一消息**再调一次，`purpose = "repair"`；仍不合规返回 `failure`，恰好 2 次调用。条目级不合格只丢弃、不触发修复。修复调用不带新的提示词文字（MANIFEST 规定正文只经装载器取用，且清单固定 8 类），因此实际效果是「同一提示再请求一次」，见待决 2。
5. **截断**视为不合规：`finish_reason = length` 时即使碰巧能解析也不采信（输出可能缺条目）。
6. **空块**（空串或全空白）直接返回 `ok`、空列表、0 次调用、无缓存键。模型返回 `{"entities": []}` 同样是 `ok` 空列表。
7. **缓存键**只算不存：成功时 `cache_key = extraction_cache_key(identity, purpose, version, sha256, cache_model_id(result))`；`cache_key(identity)` 供调用前查找（默认本实例模型）。失败不给键，避免把失败写进缓存。
8. **出处对齐**按 D08 `_render` 的拼接格式（每段「章节路径\n正文」、段间 `\n\n`）用 `ChunkSource` 的长度与 `locator.section_path` 重建各段区间；总长不符时退回整块全部出处，宁粗不错。
9. **不泄露**：`definition`、`evidence` 不进 `repr`；失败只有原因码与尝试次数；模块不写日志。

## 验证（实际结果）

环境：`V=/tmp/claude-0/-home-user-SmartSketch/f5e8fe9b-ebac-5377-b10c-8bfbef53bfde/scratchpad/venv`，每次运行前换新的 `PYTHONPYCACHEPREFIX=…/scratchpad/pyc-e05-$RANDOM`，未向 venv 安装任何东西。

| 命令 | 结果 |
| --- | --- |
| 红灯：`PYTHONPATH=$PWD/src/backend $V/bin/python -m pytest tests/backend/test_e05.py -q -p no:cacheprovider`（实现前） | 收集错误 `ModuleNotFoundError: app.services.ai.entities`，1 error |
| 绿灯：同上（实现后） | **63 passed** |
| `tests/backend/test_e05.py tests/backend/test_e01.py` | 132 passed（E01 清单/摘要校验覆盖新版本） |
| `tests/backend` 全量 | **1739 passed**，1 条既有警告（基线 1676 + 本任务 63） |
| `tests/contracts tests/tooling`（PATH 含 venv 与 `b15-tools/node_modules/.bin`） | **305 passed**（首次未设 PATH 时 3 条生成器用例因缺 `datamodel-codegen` 失败，与本改动无关，设 PATH 后通过） |
| `PATH=$V/bin:…/b15-tools/node_modules/.bin:$PATH ./scripts/verify.sh` | 退出码 0，`Scaffold verification passed.` |
| `git diff --check`；新文件行尾空白检查 | 通过 |

实现过程中测试自身的两处错误已改正（不是实现缺陷）：跨段证据用例原先截取的区间落在同一段；`float("inf")` 经 `json.dumps` 变成 `Infinity`，属坏 JSON 而非越界置信度，改为单独用例 `1e400`（合法 JSON，解析为 inf）。

### 反向篡改（每次先 `cp` 备份，改回后 `cmp` 与备份一致，每次换新的字节码目录）

| # | 篡改 | 结果 |
| --- | --- | --- |
| T1 | 证据不在块内时仍按位置 0 收下（去掉子串校验） | 2 failed |
| T2 | 不修复，首次不合规即失败 | 14 failed |
| T3 | 修复后仍坏时再修一次（共 3 次调用） | 10 failed |
| T4 | 类型比较改为 `type_.lower()`（放宽大小写） | 2 failed |
| T5 | 长度上限 `>` 改 `>=`（边界值被拒） | 3 failed |
| T6 | 截断不视为不合规 | 1 failed |

## 接口 / 数据变更

- 新 Python 接口见「输入与输出」；无 wire 契约、数据库或 Neo4j 模型变化。
- 提示词 `extract_entities` 版本 1 → 2，摘要 `3d7cfca562e1f3685e1def3915215d922dec2f94b72dc57037bc10903dd059e6`；依 D09，缓存键随之变化（尚无持久化缓存，无迁移）。

## 风险

- **fake 模式端到端**：E02 fake 的默认 JSON 输出（`{"digest","fake","purpose"}`）没有 `entities`，`LLM_MODE=fake` 下未脚本化的抽取会修复一次后以 `invalid_structure` 失败（测试 `test_fake_default_json_output_is_not_accepted_as_entities` 固定了这一现状）。E12/K 组做 fake 端到端时需提供 responder 或另行决定 fake 默认输出。
- **出处对齐依赖 D08 拼接格式**：`_layout` 复刻 `chunking._render` 的格式；D08 改拼接方式须升 `CHUNKER_VERSION`，届时若总长对不上会退回整块出处（不会指错，但变粗）。D08-P3（每段重复拼章节路径）若改为每窗口一次，本模块的对齐需同步调整。
- **证据精确匹配**可能丢掉模型在空白、全半角上有细微差别的正确条目；实际丢弃率需在 K02 评测中观察。
- 自报的 `confidence` 可信度有限，本模块只校验范围，不据此判定 `low_confidence`。

## 待决

1. **字段长度上限**：规格与契约都没有给知识点名称、定义、证据的长度范围。本任务暂定 `NAME_MAX_CHARS = 64`、`DEFINITION_MAX_CHARS = 500`、`EVIDENCE_MAX_CHARS = 500`（去首尾空白后计字符），并写进提示词 v2。需要产品/协调方签收或给出正式值（改值须同步升提示词版本）。
2. **修复调用的提示词与用途名**：目前修复 = 同一模型重发同一消息，`purpose = "repair"`（E02 `ModelRequest` 注释中的示例；E03 交接待决 8 提议的用途枚举尚未落地，`ModelRequest` 也没有 `is_repair` 字段）。若要带上坏输出与纠错指令，需要新建修复模板（清单从 8 类扩为 9 类，改 E01 测试与 MANIFEST），由协调方决定；E04 记录 `model_calls.is_repair` 时可按 `purpose == "repair"` 判定。
3. **失败块错误码**：`FailedChunk.code` 取 `ErrorCode`，而输出不合规（`invalid_json`/`invalid_structure`/`truncated`）在枚举里没有对应码（`EXTRACTION_INCOMPLETE` 是任务级）。E12 需要决定映射，或经 B 组在契约中新增错误码。
4. **缓存存储**：本任务只计算缓存键，不实现存取；由谁（E12 或 D10/C 组仓储）在 SQLite 持久化抽取缓存、失败是否缓存，待定。
5. **`confidence` 的来源**：规格要求节点有 `confidence`，但没有说由模型自报还是由融合/规则计算，也没有低置信度阈值。本模块把模型自报值（可空）原样交出；E10/F04 使用前需确认。
6. **MANIFEST 一行越锁**（见关键决定 1），请协调方确认接受。
7. **D08-P3**：章节路径每段重复还是每窗口一次，本任务未改动分块，保持现状；提示词已说明路径行是上下文。

## 下一步

- **E06 补漏**：复用 `EntityExtractor` 的校验逻辑（可把 `_validate`/`_parse` 提为公共函数，或在 E06 中以相同规则调用），把首轮 `candidates` 序列化为 `entities_json`；补漏结果同样经证据子串校验。
- **E08 名称归一**：输入 `EntityCandidate.name`/`definition`/`type`，按 `(course_id, 归一名)` 找候选对；同一块内重名条目本任务不去重，交 E08。
- **E12 编排**：每块调用前用 `extractor.cache_key(identity)` 查缓存；调用 `extract`；`ModelCallError` 按 E04/L1 与熔断规则处理；`result.failure` 非空即本次块尝试失败（L2，`TASK_CHUNK_MAX_ATTEMPTS`），按待决 3 映射错误码；成功时以 `result.cache_key` 写缓存，候选的 `source.sources` 转 `SourceRef`（`locator.to_source_fields()` + `chunk_id` + `document_id`，`text` 可取 `evidence`）。
- **K02 评测**：统计 `dropped` 各原因占比，用于迭代提示词（改正文须升版本并更新 MANIFEST）。

## 回滚

`git revert` 本任务提交即可：删除新文件、恢复提示词版本 1 与 MANIFEST 原行。无数据迁移。
