# C02-4 问答 v3 与推理埋点真实复测

```text
task_id: C02-4（依据 docs/handoffs/claude-plan-c-c02-4-deepseek-qa-retest.md）
review_status: ready_for_review（本轮按停止条件提前结束，见下）
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34
branch: claude/plan-c-reliability（仅本地提交，未推送、未合并、未改业务代码）
base_commit: 458b961
head_commit: 本任务提交
author: DeepSeek harness
changed_files:
  - evaluation/reports/c02-qa-v3-real.md（新增）
  - evaluation/raw/c02/{course1.jsonl,all.jsonl,audit-window.json,audit-records.json}（新增）
  - docs/handoffs/deepseek-c02-4.md（本文件）
```

## 结果一句话

**按交接第 5 节的停止条件在 13 题里的第 1 题后停止（exit 3）**，停止原因不是预算（45000 分文未用），而是**出现 1 次 usage 未知的生成调用**。按第 4 节「照实记录，不重跑」，未补跑 course2 与 repeat 两组。

## 命令与版本

| 项 | 结果 |
| --- | --- |
| HEAD / 工作区 | `458b961` / 干净 |
| 常量断言 | `ANSWER_MAX_OUTPUT_TOKENS=2048`、`ANSWER_PROMPT_VERSION=3` → exit 0 |
| 迁移 | 启动时 `Applied migrations: 017`；备份 `20261004T025422637900Z-before-017.sqlite`（integrity ok、16 条迁移） |
| 开跑前生成累计 | **648168**（硬校验通过，未开跑即核对） |
| 实际停止原因 | `存在 1 次 usage 未知的生成调用，无法确认额度，停止` |
| 退出码 | ask = **3** |

## 唯一一题（数据结构「什么是栈」）

- 结局 `error` / `LLM_UNAVAILABLE` / **`timeout`**；客户端 15.02 秒、服务端 15015 ms。
- **首字三列**：服务端首个 delta = null、客户端 SSE 首个 delta = null、**首次可见内容 = null**；
  而 **首次推理 = 757 ms、推理字符数 = 346**（新埋点有值）。
- 推理 token `usage_reasoning = null`；输入/输出 usage **均未知**。
- 15 秒预算去向：**查询向量 4925 ms（33%）+ 其余残差 8250 ms（55%）+ 生成 1840 ms（12%）**。

## 发现（只记录，未修）

1. **推理埋点确实抓得到推理增量**：`reasoning_chars=346`、`first_reasoning_ms=757` 都写入成功；但同一行 `usage_reasoning` 为 null——**内容能观测、token 数这次没返回**。样本仅 1 次且是失败调用，不能推广到成功调用。
2. **「15 秒答不完」首先是链路预算分配问题**：这道题上光查询向量 + 检索装配就占了 13.2 秒，生成只分到 1.84 秒。即使提示词与推理行为不变，这个分配也几乎不可能产出答案。C02-1 的「推理吃掉 2048 输出预算」在问答链路上**本轮未获证实**（没走到生成完成）。
3. **usage 未知会被工具的止损规则拦下**：这是设计行为（额度不可确认即停），代价是整轮复测只能拿到 1 个数据点。若希望这类超时调用也能继续跑，需要先定义「超时调用如何估算计费」（ADR-011 修订 3 已有估算方向，但本工具按「未知即停」处理）。

## 用量

| 项 | 值 |
| --- | --- |
| 生成计费（已记录） | **0 token**（1 次调用 usage 未知） |
| 生成调用（usage 未知） | 1 次 |
| 向量（另计） | 1 行 / 3 token |
| 本轮 cap | 45000，**未触及** |
| 跑完累计（记录口径） | **648168**（与开跑前相同） |

**口径提醒**：那次超时调用已产出 346 字符推理，供应商侧可能已计费，但本地记为未知、不计入累计。648168 是记录口径。

## 未验证 / 限制

- 13 题只跑 1 题：比较题 3 次重复、p50/p95、推理 token 占比、可见回答字数**均无数据**。
- 「供应商是否返回推理 token」只有 1 个失败样本（null），成功调用未验证。
- 与 L15（v2）的对照不是严格 A/B，只做对照不给因果。
- `audit-window.json` 按时间窗关联得到 0 请求（窗口语义所致），有效关联在 `audit-records.json`。

## api_and_data_changes

无业务改动。数据侧：迁移 017 已应用到测量库（含备份）；新增 1 条 `chat_logs`、1 条生成调用、1 条向量调用。

## rollback

回退本提交。测量库可用 `src/backend/storage/backups/20261004T025422637900Z-before-017.sqlite` 回到迁移 017 之前；本轮数据仅 3 行，不影响既有课程与发布版本。

## next_action

1. **是否重跑由用户决定**：按交接「不重跑」，我没有补跑。若重跑，建议先定「超时调用的计费口径」，否则同一条止损规则会再次在第 1 题拦下。
2. **首字/时延的进一步定位**：本轮指向链路预算分配（向量 4.9 秒 + 残差 8.25 秒），与 C02-1 猜的推理预算不是同一处；建议下一步先查那 8.25 秒残差里有什么。
3. 其余见 C03-1 交接（同一 checkout、同一轮次）。
