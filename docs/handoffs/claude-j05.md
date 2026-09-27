# Claude 交接：J05 有证据问答生成

- review_status: ready_for_review
- task_id: J05（issue #134）
- 分支：`claude/project-thread-bkxc2u`；base：`main@ac21e5d`
- 状态：DONE（待 PR 审查/合并）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/qa/generate.py` | `AnswerGenerator`、`AnswerGeneration`、`SkippedGeneration`、`GenerationResult`、`GenerationError`、`GenerationErrorKind`、`neutralize`、`render_evidence_blocks` |
| `prompts/answer_with_context.yaml` | v1 占位 → v2 草稿：变量 `graph_context`、`context`、`question`；`<<资料 n>>` 块头、分段标记、逐句 `[n]`、代码写反引号、哨兵、结尾重申「只当作数据」 |
| `tests/backend/test_j05.py` | 71 个用例（独立审查后补 6 个），fake 模型经真实 `ModelCallPolicy` 与临时 SQLite `SqliteCallStore`；时钟注入 |
| 扩围 | `prompts/MANIFEST.md` 一行（版本、变量、摘要、状态）；`tests/backend/test_e01.py` 一行（版本改读清单，不再写死 1）；`specs/grounded-qa.md`「待细化」一条；ADR-068；`docs/tasks.md` |

## 用法（给 J06 / J07）

```python
generator = AnswerGenerator(policy, model=settings.LLM_CHAT_MODEL)      # 进程内一个，与 J03 共用 policy
outcome = generator.generate(rewrite.query, ctx, course_id=cid, request_id=rid, deadline=deadline)
if isinstance(outcome, SkippedGeneration):     # meta(not_covered, retrieved=0) → done(outcome.reason)
    ...
# meta(answered, retrieved=ctx.retrieved)
try:
    for part in outcome:                       # 首次迭代才发请求；part 为非空原始正文
        ...                                    # J06 状态机；识别到哨兵 → outcome.close()
    outcome.result.finish_reason               # "length" 即 O6 截断
except GenerationError as error:               # error.code / error.details_reason → error 事件或 Q7 HTTP 错误
    error.delivered                            # True 时客户端须撤回临时正文
```

`deadline` 与策略时钟同一时间轴（J07：收到请求时刻 + `LLM_CHAT_TIMEOUT_SECONDS`）。`close()` 须与迭代在同一线程调用。

## 验收对照

| 条目 | 用例 |
| --- | --- |
| 空/低分上下文生成调用数为 0 | `test_not_covered_context_makes_zero_generation_calls`（断言 fake 调用与 `model_calls` 行数）、`test_empty_and_low_score_skips_keep_distinct_reasons`、`test_ready_context_without_numbered_chunks_is_skipped_as_empty`、`test_not_covered_status_wins_even_if_chunks_are_present` |
| 原文注入按资料处理 | `test_injected_instructions_stay_inside_the_material_section`、`test_question_and_graph_context_are_neutralized_too`、`test_code_and_ordinary_text_in_materials_are_kept_verbatim`、`test_neutralize_never_grows_the_text_or_leaves_a_forgeable_header`、`test_injection_does_not_change_what_is_sent_besides_the_material` |
| 超时为独立错误 | `test_deadline_already_reached_is_timeout_without_sending`、`test_deadline_passing_while_streaming_is_timeout_and_closes_the_provider`、`test_provider_timeout_at_the_chain_deadline_is_timeout`、`test_provider_timeout_with_time_left_is_upstream_not_timeout`、`test_timeout_and_upstream_share_the_code_but_not_the_reason` |
| 生成不见历史（QA-19） | `test_generation_has_no_history_input` |
| QA-8 关闭供应商流 | `test_close_after_sentinel_closes_the_provider_stream`、`test_close_while_suspended_closes_the_provider_without_resuming` |
| QA-24/25/27/28/29 的 J05 部分 | `test_primary_and_fallback_failing_before_first_token_is_upstream`、`test_break_after_text_is_stream_interrupted_without_fallback`、`test_auth_failure_is_auth_and_never_switches`、`test_budget_rejection_is_budget_exceeded_without_sending`、`test_prewrite_failure_is_storage_unavailable_without_sending` |

## 命令与实际结果

`S=<scratchpad>`；`$S/venv` 为 `pip install -e './src/backend[test]'` 加 CI 的契约工具；`$S/tools` 为 `openapi-typescript@7.4.4`。

| 命令 | 结果 |
| --- | --- |
| `$S/venv/bin/python -m pytest tests/backend/test_j05.py -q`（实现前） | 收集错误：模块不存在 |
| `$S/venv/bin/python -m pytest tests/backend/test_j05.py -q` | 65 passed（审查后 71 passed） |
| `$S/venv/bin/python -m pytest tests/backend/test_e01.py tests/backend/test_j05.py -q` | 132 passed（加 2 个用例前；审查后 140 passed） |
| `$S/venv/bin/python -m pytest tests/backend -q` | 3288 passed, 27 skipped（审查后 3293 passed, 27 skipped） |
| `PATH=$S/venv/bin:$S/tools/node_modules/.bin:$PATH ./scripts/verify.sh` | exit 0 |
| `git diff --check` | exit 0 |

反向篡改（逐处改 `generate.py` 后跑 `test_j05.py`，每次恢复）22 处全部检出：闸门两项条件、`neutralize` 失效、全角 `＜＜`、超时容差两种改法、读取中到期检查、出字前后区分、401、参数错误、`close()` 不关内层流、空片段过滤、问题与结构不中和、预算/预写/截止时间三类映射、输出上限、关闭标志、一次性迭代、结构占位、块头格式。初次有 2 处存活（闸门的 `covered` 条件、`close()` 关内层流），已各补 1 个用例。

### 独立审查（2026-09-27，worktree `pr290`）

设计 23 处有鉴别力的篡改逐处施加并恢复（同一条命令 `PYTHONPATH=$PWD/src/backend python -m pytest tests/backend/test_j05.py tests/backend/test_e01.py -q`）：

| 结论 | 处数 | 说明 |
| --- | --- | --- |
| 被检出 | 21 | 闸门两项、J04 reason 透传、读取中到期、出字前后分类、0.25 秒容差、输出上限、块头未中和、结构未中和、`neutralize` 失效、空问题、`delivered` 标志、一次性迭代、`close()` 前的关闭标志、空片段过滤、片段不累积、`StreamDone` 分流、预算→超时、熔断→预算、`ModelUnavailableError` 分类、归属改写（`course_id` 写死） |
| 无观测差异（等价改动） | 1 | 删掉到期分支里的 `_inner.close()`：`finally` 已关闭同一生成器，`fake.calls[0].closed_early` 与上游 `GeneratorExit` 行为都不变（实测基线/篡改均输出相同结果） |
| 测试缺口（已补） | 1 | 去掉 `_is_seconds(deadline)` 校验后全绿；已补 3 个非法 deadline 参数化用例（`inf`、`"later"`、`None`） |

补测后 2 处缺口复核：M03 仍无观测差异（确认非缺陷：`_run` 的 `finally` 关闭同一个生成器，代价只是重复 `close()` 一次）；M13 被新用例 `test_generate_validates_arguments_before_any_call[kwargs6-ValueError]` 检出（1 failed）。

补测（`test_j05.py` 65 → 71 个用例；`test_j05.py` + `test_e01.py` 134 → 140）：
- `test_deadline_during_read_closes_the_stream_bookkeeping`：时钟在**读取中**到期（一个片段之后），断言只出一个片段、`fake.calls[0].closed_early is True` 且 `result is None`（此前只有「发请求前已到期」与「调用方在出字后推进时钟」两种覆盖，没有「读取中到期」这一条）；
- `test_prompt_blocks_are_no_larger_than_the_budgeted_rendering`：J05 块头相对 J04 预算渲染的字节上界（每块 ≤ 8 字节），把 ADR-068 后果里那句上界落成可执行断言；
- `test_generate_validates_arguments_before_any_call` 的参数化表补 `float("inf")`、`"later"`、`None` 三种非法 deadline；
- `src/backend/app/services/qa/__init__.py` 补 J05 导出（与 J03 并列），供 J06/J07 从包导入。

## 接口/数据变更

无契约、迁移或依赖变更。提示词 `answer_with_context` 升 v2，E01 清单同步。

## 风险与待决（ArvinHan）

1. ADR-068 签收：输出上限 1024 暂定；`<<资料 n>>` 块头代替 J04 的 `[n]` 渲染（J04 预算估算因此每块低估约 9 字节）；超时容差 0.25 秒。
2. `LLM_CHAT_FIRST_TOKEN_TIMEOUT_SECONDS` 没有实现：E03 适配器的超时覆盖整条流，同步生成器无法在首字前中断读取。需要时在 E03 适配器补首字超时，J05 分类不用改。
3. 提示效果只经 fake 验证；逐句标注率、哨兵使用、防注入效果待 K03 真实模型评测（付费调用需另行同意）。
4. `close()` 不能跨线程调用；J07 若在线程里读流，需要在读线程里关闭。

## 下一步

J06（引用与终态校验，依赖 J05 + B13）按上面的用法接入；J07 负责计算 `deadline`、映射 `SkippedGeneration` 与 `GenerationError`。
