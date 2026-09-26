# Claude 交接：E11 实现关系两阶段抽取

- task_id: E11
- review_status: ready_for_review
- 分支：`claude/project-thread-sp1d3a`（与 H02、H12 同一 PR，各自独立提交）
- base: `origin/main@5072a48`，之后合入含 E10（PR #253，`cc53c8d`）的最新 main；本任务不导入 E10 代码，只在 MANIFEST 相邻行解决了一处文本冲突
- 状态：实现与验证完成，待 PR 审查/合并

## 改动文件

| 文件 | 说明 |
| --- | --- |
| `src/backend/app/services/ai/relations.py` | 新增。`RelationExtractor`：小节实体 ID 表 + 来源块 → 四类关系候选；输入隔离校验、输出修复一次、逐条拦截 |
| `prompts/extract_relations.yaml` | 正文替换，版本 1 → **2**：方向定义与方向反例、先修表述、证据逐字摘录、置信度、只用实体表 ID |
| `prompts/MANIFEST.md` | **超出文件锁**：只改 `extract_relations` 一行（版本 2、新摘要、`占位` → `草稿`），理由同 E05 交接关键决定 1（`test_e01.py` 逐行核对摘要） |
| `docs/submission/prompt-engineering.md` | **超出文件锁**：按 K14 交接第 3 条同步——总览行、新增 §3.4、从 §4 占位表移除该行 |
| `tests/backend/test_e11.py` | 新增，47 个用例，只用 E02 `FakeModelClient` |
| `docs/tasks.md` | 本批认领与证据 |
| `docs/handoffs/claude-e11.md` | 本文件 |

## 输入与输出

```python
extractor = RelationExtractor(client, model=LLM_EXTRACTION_MODEL, max_output_tokens=N,
                              prompts=None, timeout_seconds=None)
result = extractor.extract(course_id: str,
                           entities: Sequence[SectionEntity],   # (entity_id, course_id, name, type)
                           chunks: Sequence[SourceChunk])       # (ChunkIdentity, text)
```

- `RelationExtraction`：`course_id`、`candidates`、`dropped: dict[RelationDropReason, int]`、`failure: ExtractionFailure | None`（`ok`）、`prompt_purpose`/`prompt_version`/`prompt_sha256`、`model_id`、`model_calls`（0/1/2）。
- `RelationCandidate`：`from_id`、`to_id`（语义同契约 `Relation`：`PREREQUISITE` 为 from 是 to 的前置）、`type`、`evidence`、`confidence: float | None`、`source: RelationSource`（课程、资料、修订、块 ID、证据半开区间、证据覆盖的 D08 `ChunkSource`）。
- `RelationDropReason`：`not_object`、`invalid_type`、`invalid_endpoint`、`dangling_endpoint`、`self_loop`、`invalid_evidence`、`evidence_not_in_sources`、`invalid_confidence`、`prerequisite_without_cue`、`reversed_direction`、`duplicate`。
- 整体输出不合规沿用 E05 `FailureReason`（`invalid_json`/`invalid_structure`/`truncated`）与 `ExtractionFailure`。
- `ModelCallError`（含 E04 预算拒绝）原样抛出，与 E05 一致。

## 关键决定

1. **跨课拦截分两层**：输入中任一实体或块的 `course_id` 与参数不同、块文本哈希不符、实体 ID 重复、实体类型不在五类闭集 → `ValueError`，不调用模型（调用方错误，同 E05 哈希校验）。模型输出里的他课 ID 不在实体表内，按「悬空端点」丢弃。
2. **草稿可见性 V**（ADR-011 修订 1）：本模块不读图库；E12 取实体表时按 V 过滤后传入。
3. **自环**：两端相同直接丢弃计数（`specs/course-knowledge-graph.md` DAG-9「规则校验阶段直接删除」），不进入 F13 降级算法。
4. **仅提及不判前置**：提示词写明规则；代码层对 `PREREQUISITE` 要求证据含 `PREREQUISITE_CUES` 中的先修表述（NFKC + casefold 子串匹配），否则丢弃。宁缺勿错：前置边会进入 DAG 与学习路径。并列提及仍可以作为 `RELATED_TO` 保留。
5. **方向**：代码不翻转方向。`EXAMPLE_OF` 的 to 端是 `example` 类而 from 端不是 → 判为颠倒并丢弃；`PREREQUISITE`/`CONTAINS` 方向无法由类型判断，只靠提示词中的方向反例，测试固定「原样保留 from/to，不交换」。
6. **重复边**：`(from_id, to_id, type)` 只留首条合格者（不合格的首条不占位）；`RELATED_TO` 视为无向。反向的两条 `PREREQUISITE`（二元环）不在此去重，交 F13 按 ADR-009 降级送审。
7. **证据**：须为某个来源块文本的连续子串（精确匹配，按块顺序取首个命中），跨块拼接丢弃；出处对齐复用 E05 `_layout`/`_sources_for`。
8. **无缓存键**：关系抽取的输入是多块 + 实体表，D09 `extraction_cache_key` 只覆盖单块；按 D09 交接待决 4，不在调用方拼接，缓存方案交 E12/D09 先改规格。
9. 空输入（实体 < 2 或没有非空白块）直接返回空结果，0 次调用。

## 验证（实际结果）

环境：scratchpad 虚拟环境（`pip install -e './src/backend[test]'` 加 CI 契约工具），`PYTHONPATH` 由可编辑安装提供。

| 命令 | 结果 |
| --- | --- |
| `python -m pytest tests/backend/test_e11.py tests/backend/test_e01.py -q` | 116 passed（含 E01 清单/摘要逐行核对） |
| `python -m pytest tests/backend -q` | 2702 passed，1 条既有警告 |
| `./scripts/verify.sh`、`git diff --check` | 见 PR 描述与 `docs/tasks.md` 本批记录（与 H02、H12 合并后统一运行） |

说明：实现与测试在同一轮写成，没有保留「实现前红灯」的记录；改用反向篡改证明测试有效。

### 反向篡改（每次先备份，改回后 `cmp` 一致）

| # | 篡改 | 结果 |
| --- | --- | --- |
| T1 | 不删自环 | 1 failed |
| T2 | 不拦悬空端点 | 2 failed |
| T3 | 不要求先修表述 | 1 failed |
| T4 | 不判 `EXAMPLE_OF` 方向 | 1 failed |
| T5 | 不去重 | 2 failed |
| T6 | `RELATED_TO` 按有向去重 | 1 failed |
| T7 | 不校验实体课程 | 1 failed |
| T8 | 不校验块课程 | 1 failed |
| T9 | 不修复 | 5 failed |

## 接口 / 数据变更

- 新 Python 接口见上；无 wire 契约、数据库或 Neo4j 模型变化。
- 提示词 `extract_relations` 1 → 2，摘要 `be9c788194869a7421e3058dc73923608697995bb50e662de6a60d1b6cc963d6`。

## 风险

- **先修表述清单**是本任务暂定（规格未给），可能漏掉合法的前置表述（召回下降）或放过含「基础」一词的并列句；需 K02 在自编标注集上观察 `prerequisite_without_cue` 丢弃量后调整（改清单不需升提示词版本）。
- **E10 已合入**：合并 main 时 `prompts/MANIFEST.md` 相邻行冲突已解决（两边内容各自保留）。`docs/submission/prompt-engineering.md` 中 `judge_duplicate`/`summarize_definition` 仍记为 v1 占位，E10 未同步，不在本任务范围。
- fake 模式默认 JSON 没有 `relations`，未脚本化时会修复一次后以 `invalid_structure` 失败（与 E05 相同的现状）。

## 待决

1. `PREREQUISITE_CUES` 的正式清单与是否对 `CONTAINS` 也做表述约束（产品/协调方）。
2. 小节范围与实体表上限：「小节」由 E12 按章节路径分组；实体数、块数、提示词长度上限未定，过长时如何切分交 E12。
3. 失败的 `ExtractionFailure` 映射到哪个错误码，同 E05 待决 3。
4. 关系抽取结果的缓存键（见关键决定 8）。

## 下一步

- **E12**：按小节聚合 E05/E06 实体，经 E08～E10 融合得到实体 ID 表（按 V 过滤），与该小节块一起调用 `extract`；`failure` 非空按 L2 块尝试失败处理；候选 `status`/`source=ai` 与低置信度判定交 F04（D-08 阈值）。
- **F13**：写入前对 `PREREQUISITE` 候选做环检测与降级（ADR-009），把 `source.sources` 转 `SourceRef`。
- **K01/K02**：统计 `dropped` 各原因，评估关系准确率（赛题 ≥ 70%）。

## 回滚

`git revert` 本任务提交：删除新文件，恢复提示词版本 1、MANIFEST 原行与 K14 记录。无数据迁移。
