# C02（B-QA-01）问答稳定性：诊断、推理埋点与提示词 v3 交接

```text
task_id: C02-1 / C02-2 / C02-3（C02-4 真实复测已写交接给 DeepSeek，未执行）
review_status: ready_for_review
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34
branch: claude/plan-c-reliability（base ec1291a）
author: Claude
paid_calls: 0
decision: 用户 2026-10-03 选择方案 A（推理埋点）+ C（提示词 v3），批准 C02-4 预算 45000、C03-1 预算 110000
```

## 交付物

| 子任务 | 内容 |
| --- | --- |
| C02-1 | `evaluation/reports/c02-qa-diagnosis.md`：可见回答每字 2.9～17 个输出 token，首个 delta ≈ 生成耗时；推断为不可见推理占用 2048 预算并推迟可见内容 |
| C02-3 | `evaluation/measure_web_flow.py audit` 逐请求拆出查询向量 / 生成 / 其余耗时（现有字段，无迁移） |
| C02-2 A | ADR-089；迁移 `017_model_call_reasoning.sql`（四个可空列）。`client.py`：`Usage.reasoning_tokens`、`ModelResult.reasoning_chars`、`StreamReasoning`（只带字数）。`compatible.py`：解析 `reasoning_content` / `reasoning` 与 `completion_tokens_details.reasoning_tokens`。`policy.py`：记录首次推理 / 首次可见内容时刻并回写，**不转发**推理事件。`repositories/model_calls.py`：回写新列 |
| C02-2 C | `prompts/answer_with_context.yaml` v3（规则 6～8：直接作答、不复述、不输出推理过程、比较题逐点对照、通常不超过 300 字；v2 规则原样保留）；`ANSWER_PROMPT_VERSION = 3`；`prompts/MANIFEST.md` 版本与摘要 |
| C02-4 准备 | `audit` 读推理列（旧库自动降级为未知）；`ask --round-started-at` 让一轮多次调用共用止损窗口；交接 `docs/handoffs/claude-plan-c-c02-4-deepseek-qa-retest.md` |
| C03-2 工具 | `audit-task`：按任务拆用途跨度、repair、usage、块数、派生非模型耗时（为 C03-1 交接准备，详见 `claude-plan-c-c03.md`） |

## 不变的部分

- 输出上限 2048（ADR-086）、15 秒总截止、出处逐句校验与截断判定（ADR-082 决定 2）。
- 不加自动重试，不切换学生模型，不放宽校验。
- 推理正文不进入回答、日志、数据库或前端；SSE 契约与 JSON 响应不变。
- 计费公式不变：`usage_reasoning` 是 `usage_output` 的一部分，不另计。

## 验证

- `tests/backend/test_c02_reasoning.py` 10 例：先加惰性数据类型后 7 failed（另 3 例验证不变行为，先就通过）→ 实现后全过。
- `tests/backend/test_c02_prompt_v3.py` 3 例：3 failed → 全过。
- `tests/tooling/test_c02_c03_measure.py` 8 例：7 failed → 全过（其中 1 例是实现后拆分出来的未完成调用边界）。
- 回归：`test_e01`、`test_e03`、`test_e04`、`test_j05`、`test_j10`、`tests/tooling` 通过。
- 后端全量（`tests/backend tests/tooling`，`env -u LLM_MODE -u EMBEDDING_MODE`）：**3825 passed / 27 skipped**（skip 与此前登记的 27 项相同），exit 0。
- 提交：`33177c0`（A）、`088a601`（C）、`e709ccb`（测量工具），ADR `0469bad`。

### 随之调整的测试

- `test_e01`：MANIFEST 版本与摘要随 v3 更新（按清单规则「改模板须升版本并更新摘要」）。
- `test_j10.py` 夹具原写死「最后一个迁移为 016」，改为与迁移目录中编号最大的文件比较，新增迁移不必再改。
- `test_c01_measure.py` 一处账本断言改为子集比较（账本新增推理字段）。

## 风险与限制

- 推断尚未证实：供应商可能根本不返回推理内容或推理 token，那时新列为空，只能从「输出 token 远多于可见字数」间接判断。
- 提示词 v3 对推理模型的约束力未知，假模型通过不代表真模型更短或更快。
- 迁移 017 需要在测量环境启动时执行（自动备份）；回滚步骤见迁移文件与 ADR-089。

## 下一步

- DeepSeek 执行 C02-4（`claude-plan-c-c02-4-deepseek-qa-retest.md`），报告到达后据推理数据决定是否进入方案 B（思考控制，需用户决定）。
- C03-1 交接已备（`claude-plan-c-c03-1-deepseek-pdf-retest.md`）。
