# L15 问答 2048 真实模型实测

```text
task_id: L15 问答实测（依据 docs/handoffs/codex-plan-b-deepseek-qa.md）
review_status: ready_for_review
worktree: /Users/arvinhan/.codex/worktrees/plan-b-takeover/SmartSketch
branch: codex/plan-b-takeover（仅本地提交，未推送、未合并、未改业务代码）
base_commit: 257750e（测量 checkout 的 HEAD，工作区干净）
head_commit: 本任务提交
author: DeepSeek harness
changed_files:
  - evaluation/reports/l15-qa-2048-real.md（新增，本轮主交付）
  - evaluation/raw/l15/question-evidence.json（新增，10 题脱敏证据：终态、耗时、usage、引用定位、回答正文）
  - docs/handoffs/deepseek-l15-qa-2048.md（本文件）
```

## 首个动作的落实（交接要求先做）

1. **L11-7 最新报告**：`docs/handoffs/claude-l11-7-deepseek-retest.md` 仍是**未执行**的交接（`review_status: handoff`），没有复测报告，因此本轮没有可引用的 L11-7 数字。
2. **预算累计**：Codex 账本（`docs/handoffs/codex-plan-b-ledger.md`）明确「本地只使用演示模型/假供应商」「真实测量交 DeepSeek，无付费调用」，因此起点为 L11-6 的 **619217**。用户确认本轮**增量硬止损 80000、累计上限 699217**。
3. **测量 checkout 是否含本轮修复**：已确认。前置断言通过——`ANSWER_MAX_OUTPUT_TOKENS = 2048`（exit 0），HEAD `257750e`，`git status` 干净、`git diff --stat` 为空。

## 交付与结果

10 题全部跑完（数据结构 5、操作系统 5，各含 1 题课外），**无停止项**，脚本 exit 0。

| 终态 | 题数 |
| --- | --- |
| `answered` | 7 |
| `error` / `LLM_UNAVAILABLE` / `truncated`（HTTP 503） | 1 |
| `not_covered` / `below_similarity_threshold`（课外） | 2 |
| `timeout` / `upstream` / `auth` | 0 |

- **完整耗时**：10 题全部 ≤ 15 秒（最慢 10.27 秒，已作答 7 题 3169～9500 ms，中位 5167 ms）→ 15 秒链路时限**达标**。
- **首字耗时**：已作答 7 题 3028～9287 ms（中位 5020 ms），**全部未达 S2 的 ≤3 秒目标**。
- **课外问题**：两题均按 `below_similarity_threshold` 在 0.5～0.7 秒拒绝，**未发起生成调用**。
- **课程隔离**：数据结构 4 条引用全指向 `ch3-stack-queue.md`，操作系统 6 条全指向 `ch2-process-thread.md`，无跨课引用；`graph_version` 全为 1。
- **逐题出处**：7 题 `answered` 的 `invalidation_subtype` 全为 NULL（逐句校验通过），未因提高上限放宽校验；抽查两题的引用章节与内容相符。

## 发现（只记录，未修）

1. **2048 仍未解决比较类问题，且结局不稳定**：数据结构「栈和队列有什么区别」在 2048 下依旧撞顶 → `error/truncated`（503）。更关键的是**同一个问题「什么是栈」在同一门课上出现两种结局**——被中断的第一次尝试输出 2048 → `truncated`；改正请求头后重跑 → `answered`。2048 对这门课处在临界位置。
2. **D1 的故障分类按 ADR-082 决定 2 修好了**：截断且校验不通过时终态为 `error` + `LLM_UNAVAILABLE` + `details.reason = truncated` + HTTP 503，`chat_logs` 记 `error_reason/truncated/invalidation_subtype`。两种子类本轮都被实际触发（`no_markers`、`uncited_sentence`），与 ADR 描述逐条一致。
3. **首字与新目标差距大**：7 题无一达到 3 秒，最慢 9287 ms。这是独立于上限的时延问题，建议单列处理。
4. **D2 记账在问答侧正确、缓存不重复记账**：10 行 `embedding` 的 `request_id` 全部与 `chat_logs` 对应；11 个请求只产生 10 行——重复提问的第二次**没有新增行**（缓存命中）。

## 用量

| 项 | 值 |
| --- | --- |
| 本轮生成计费 | **28951 token**（9 次 `answer_with_context`，输入 18764 + 输出 10187） |
| 起点累计 | 619217（L11-6 后，Codex 无付费调用） |
| **累计（预算口径）** | **648168 / 5000000**；本轮上限 699217，**未越线** |
| 本轮向量（另计） | `embedding` 10 行 / 59 token；累计 11943 |
| 费用 | 仓库无核对过的单价，按规格第 11 节的保守估算约 0.1～0.15 元（以供应商控制台为准） |

含 1 次被中断的尝试（客户端漏发 `Accept: application/json`，服务端仍完成并记录，2558 + 2048 token）。它照实计入本轮，未用来替代任何一题的结果。

## 环境与同步（交接第 3 节的执行说明）

交接写「在用户准备的测量 checkout 执行」，并要求先由用户安排代码与数据的同步。核对后发现**没有任何 checkout 同时具备两者**：`codex/plan-b-takeover`（2048）无 `.env`、无数据库；冲刺 checkout（`5a34fec`）有数据但常量仍是 1024（交接也明确禁止在它上面直接测 2048）。经用户明确授权，我按以下方式同步，**未合并、未快进、未推送、未改业务代码**：

1. 把冲刺 checkout 的 `.env`（权限 600）与 SQLite（含上传资料）复制进测量 checkout；两者都被该 checkout 的 `.gitignore` 忽略，未进入版本库，密钥未打印、未提交。
2. **直接起 API 与 worker**，复用冲刺工作树已在 7688 上运行的 Neo4j：`start.sh` 会调 `dev-up.sh` 用本 checkout 的 compose 项目名另起 Neo4j，与那个实例抢端口。Neo4j 容器未被停止或改动（它不属于本次任务）。
3. 两边迁移一致（各 16 条，016 已应用），本轮**未产生新迁移**。
4. 为两门被测课补加 `demo_student` 成员（HTTP 201，无模型费用）——原成员只有 `demo_teacher`。
5. 未改现有数据库内容（不清理、不重向量化、不重新抽取）。

启动脚本与测量脚本都在 `.demo/l15-qa/`（Git 忽略）：`run-services.sh`、`ask_capture.py`。

## 证据路径

| 内容 | 路径 |
| --- | --- |
| 报告 | `evaluation/reports/l15-qa-2048-real.md` |
| 逐题脱敏证据（终态、耗时、usage、引用定位、回答正文、被中断的尝试） | `evaluation/raw/l15/question-evidence.json` |
| 原始逐题完整响应（含引用块原文） | `.demo/l15-qa/responses.jsonl`（Git 忽略） |
| 本轮汇总 | `.demo/l15-qa/summary.json`（Git 忽略） |
| 服务日志 | `.demo/l15-qa/logs/{api,worker}.log`（Git 忽略） |

## unverified

- **准确率未判定**：本轮只测问答；L11-6 的四份抽取原始输出待 L16 人工判定。
- **抽取 ≤60 秒未达标**（L11-6：83.97 / 200.37 / 75.51 / 162.54 秒），本轮未重测，结论不变。
- **L11-7 PDF 复测未执行**，其交接仍在待办；本轮不重复抽取。
- 与 1024 的对比**不是严格 A/B**：旧 L02 记录用的是另一门课、另一份资料与更早的提示版本，报告里已注明条件差异；严格 A/B 需另行申请预算，本轮未改交付分支常量。
- 首字耗时只取 `chat_logs.first_delta_latency_ms`（服务端记录），未用 JSON 到达时间；未单独抓完整 SSE 流做逐事件核对。
- 未验证发布路径（本轮无发布）；`publish:<version_id>` 行是同步进来的 L11-6 数据。

## api_and_data_changes

无。未改接口、契约、迁移、业务代码或测试。仅新增报告、证据文件与本交接；测量 checkout 的未跟踪文件为 `.env`、`src/backend/storage/`、`.demo/`（均 Git 忽略）。

## rollback

回退本提交即可。测量 checkout 的 `.env` 与 `src/backend/storage/` 是同步进来的未跟踪文件，删除它们即回到同步前状态；测量 checkout 的 git 历史未引入任何业务改动。共享的 Neo4j 未被改动。

## next_action

1. **决定 2048 之后怎么办**：本轮证明它没解决比较类问题且结局不稳定（同一问题两种结局）。建议在 L16 里把上限调整与首字时延一起按 15 秒时限重新实测，而不是继续单独调上限。
2. **首字耗时单列**：7/7 未达 3 秒，最慢 9.3 秒，与上限无关。
3. **补 L11-7 复测**（PDF 段落合并后的真实复测，交接仍在待办），完成后再做 L16 准确率判定。
4. 推送与合并待用户授权。
