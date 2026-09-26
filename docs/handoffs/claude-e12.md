# Claude 交接：E12 抽取阶段编排与检查点

- review_status: ready_for_review
- task_id: E12
- 分支：`claude/project-thread-sqwla4`；base：PR #255 头 `52db31c`（含 E11、ADR-021、ADR-022，尚未合入 main）
- 状态：DONE（待 PR 审查/合并）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/workers/extract_task.py` | `run_extract_stage`（`extracting` 阶段编排）、`load_candidates`（待持久化候选）、`task_entity_id`、`exceeds_threshold`、`ExtractLimits`、`ExtractionToolkit`、`run_once`（解析 + 抽取一体的「运行一次」入口） |
| `src/backend/app/repositories/extraction_checkpoints.py` | 检查点读写；写入必须在调用方已 fence 的事务里 |
| `src/backend/migrations/008_extraction_checkpoints.sql` | 新表 `task_chunk_checkpoints`，不可变与课程作用域触发器，随任务级联删除；文件头写明回滚步骤 |
| `tests/backend/test_e12.py` | 37 个用例 |
| `docs/decisions.md` ADR-023、`specs/task-processing.md` §8.4 一段 | 检查点结构、小节划分、失败口径 |

## 行为要点

1. 块阶段：跳过已有检查点的块；其余块在线程池并发处理，在途上限 `LLM_MAX_CONCURRENCY`。每块最多 `TASK_CHUNK_MAX_ATTEMPTS` 次尝试，每次 `policy.bind` 一个带 `task_attempt`/`chunk_attempt` 的客户端；E05 的修复调用经 `is_repair=True` 的绑定单独记录。
2. 块失败码：输出不合规 `EXTRACTION_INCOMPLETE`；其余模型错误 `LLM_UNAVAILABLE`；`BudgetExceededError` 立即失败 `BUDGET_EXCEEDED`、不重试。`ModelUnavailableError`（熔断）与 `CallRecordError` 不记失败块，停止派发后主动释放（最后一次尝试转 T9 耗尽码）。
3. 边界：每块结束在一个 `leased_transaction` 里先读取消标志，为真则丢弃在途结果并 T8；否则写检查点与进度（块阶段占区间 80%，小节 20%）。超阈值即提前 T9，`details = {chunks_failed, chunks_total, threshold, by_code?}`；失败块全是 `LLM_UNAVAILABLE` 时用该码。
4. 小节：成功块按「修订 + 章节标题路径」分组；实体表按 `task_entity_id`（任务 + E06 规范化名称）去重。小节关系失败只记检查点，不计入阈值（ArvinHan 在会话卡片上选定）。
5. 阶段边界：C08 `stage_done` → T4 `merging`（仍持有租约）或 T8。

## 接口（给 merging / F04 / F13 / C11）

```python
from app.workers.extract_task import ExtractionToolkit, ExtractLimits, load_candidates, run_extract_stage
toolkit = ExtractionToolkit(policy=policy,                       # 每进程一个 ModelCallPolicy
                            entities=lambda c: EntityExtractor(c, model=..., max_output_tokens=...),
                            relations=lambda c: RelationExtractor(c, model=..., max_output_tokens=...),
                            gleaner=None)                        # 或返回 enabled=True 的 EntityGleaner
outcome = run_extract_stage(url, lease, toolkit=toolkit, limits=ExtractLimits.from_settings(settings))
candidates = load_candidates(url, course_id=..., task_id=...)   # entities / relations / failed_chunks / failed_sections
```

`TaskEntity.entity_id` 是任务内临时 ID；关系端点使用同一 ID。`merging` 需要把它们映射到草稿 `kp_id`（融合后）。

## 命令与实际结果

`S=<scratchpad>`；`$S/pt.sh` = `PYTHONPATH=src/backend PYTHONPYCACHEPREFIX=$S/pyc-$RANDOM $S/venv/bin/python -m pytest -p no:cacheprovider`；venv 按 `pip install -e "src/backend[test]" 'datamodel-code-generator==0.26.3'` 建立。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 基线 | `$S/pt.sh tests/backend -q`（合入 ADR-022 前） | 2757 passed |
| 红灯 | `$S/pt.sh tests/backend/test_e12.py -q`（实现前） | 收集错误 `ImportError: cannot import name 'extract_task'` |
| 绿灯 | 同上 | 37 passed；连跑 5 次均 37 passed |
| 后端全量 | `$S/pt.sh tests/backend -q` | 2801 passed，1 个既有 warning |
| verify | `PATH=$S/venv/bin:$S/tools/node_modules/.bin:$PATH ./scripts/verify.sh`（`openapi-typescript@7.4.4` 装在 `$S/tools`） | exit 0；不带该 PATH 时 `test_b14` 因缺生成器失败，属环境 |

### 反向篡改（改后跑 `test_e12.py`，改回 `cmp` 一致）

| # | 篡改 | 结果 |
| --- | --- | --- |
| T1 | 不跳过已有检查点的块 | 2 failed |
| T2 | 并发上限 +2 | 7 failed |
| T3 | 边界不读取消标志 | 2 failed |
| T4 | 阈值比较 `>` 改 `>=` | 7 failed |
| T5 | 预算被拒仍重试 | 1 failed |
| T6 | 熔断打开记为失败块 | 2 failed |
| T7 | 小节关系失败计入阈值 | 1 failed |
| T8 | 修复调用不走 `is_repair` 绑定 | 1 failed |

## 数据与接口变更

- 新迁移 008（仅新增表与触发器）；无 REST/SSE 契约、环境变量或依赖变更。
- 若 main 合并前已有 008，按 D-10 改号为新的最大号 + 1（测试按文件名后缀定位迁移）。
- ADR 编号 023：若 PR #255 线程再新增 ADR，合并时顺延。

## 待决 / 风险

1. **快照与 SSE 计数**：`chunks_done`、`chunks_failed`、`failed_chunks` 尚未进 `Task` 快照与事件（C11 交接待决 3）。数据已在检查点表，`load_candidates().failed_chunks` 给出定位，C11 接列即可。
2. **模型调用缓存**：未实现（E05 待决 4、E11 待决 8）。已结束的块不会重调，但块中途崩溃后该块会重新计费。
3. **小节规模**：实体表与提示词长度无上限（E11 待决 2）。长章节可能超出模型上下文，需要定切分规则。
4. **小节关系失败的展示**：只在检查点与 `failed_sections` 中，契约无对应字段。
5. **保留期清理**：§8.6 的检查点清理未实现。
6. **生产装配**：`ExtractionToolkit` 的模型 ID、输出上限、补漏开关尚无启动入口与环境变量（E06 待决 1），`run_once` 需调用方传入。
7. **`merging` 承接**：`run_once` 推进到 `merging` 后交还租约；在 `merging` worker 出现前，回收/领取会反复拿到它（同 D11 交接风险 1 的形态）。

## 下一步

- F04/F13 与 `merging`：从 `load_candidates` 取候选，把 `tent_…` 映射到草稿节点。
- C11：快照与事件补 `chunks_done`/`chunks_failed`/`failed_chunks`。

## 回滚

停 API 与 worker，恢复 `backups/*-before-008.sqlite`，或执行迁移 008 文件头的 `ROLLBACK` 行（`test_e12.py` 已验证）；撤销本分支提交。处于 `extracting` 的任务之后会从阶段开头重跑。
