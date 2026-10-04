# L15 问答 2048 真实模型实测（2026-10-03）

> **状态：10 题全部跑完，无停止项。** 个人模式真实生成模型（DeepSeek `deepseek-flash`，学生个人配置，ADR-080）+ 部署者在线向量（阿里云百炼 `text-embedding-v4`，ADR-081）。输出上限已由 ADR-086 定为 **2048**（本轮实测断言 `ANSWER_MAX_OUTPUT_TOKENS == 2048`）。**不宣称赛题全达标**：抽取 ≤60 秒仍未达标、准确率待人工判定（第 6 节）。

## 1. 命令、版本与退出码

```bash
# 测量 checkout（codex/plan-b-takeover，含本轮修复）
git status --short                       # 空（干净）
git rev-parse HEAD                       # 257750e185f43d547bf9045558d9adc4a183201d
git diff --stat                          # 空
PYTHONPATH="$PWD/src/backend" .venv/bin/python -c \
  'from app.services.qa.generate import ANSWER_MAX_OUTPUT_TOKENS; assert ANSWER_MAX_OUTPUT_TOKENS == 2048; print(ANSWER_MAX_OUTPUT_TOKENS)'
# → 2048，exit 0
```

| 项 | 值 |
| --- | --- |
| 测量 checkout | `/Users/arvinhan/.codex/worktrees/plan-b-takeover/SmartSketch` |
| 分支 / HEAD | `codex/plan-b-takeover` / `257750e`（工作区干净，`git diff --stat` 为空） |
| 常量核对 | `ANSWER_MAX_OUTPUT_TOKENS = 2048`（断言通过，exit 0） |
| 问答链路时限 | `LLM_CHAT_TIMEOUT_SECONDS = 15` |
| 运行模式 | `runtime_mode = personal`；学生 `configured = true`（`deepseek-flash`） |
| 课程 | 复用 L11-6 已发布的两门 Markdown 课程，**未重新抽取、未重新向量化、未改现有数据库** |
| 题目 | 数据结构 5 题、操作系统 5 题（各含 1 题课外） |
| 退出码 | 测量脚本 exit 0；10 题无停止（`stopped = None`） |

**与交接的一处环境说明**：交接写「在用户准备的测量 checkout 执行」并建议 `scripts/start.sh --no-open`。实际情况是**没有任何 checkout 同时具备修复代码与数据**：`codex/plan-b-takeover`（2048）没有 `.env` 也没有数据库；冲刺 checkout（`5a34fec`）有数据但常量仍是 1024。经用户明确授权后，我把 `.env` 与 SQLite（含上传资料）同步进测量 checkout，并**直接起 API 与 worker**（等价运行手册方式 B 的后两个进程）复用冲刺工作树已在 7688 上运行的 Neo4j——`start.sh` 会调 `dev-up.sh` 用本 checkout 的 compose 项目名去起 Neo4j，与那个实例抢端口。Neo4j 容器未被停止或改动。两边迁移一致（各 16 条，016 已应用），未产生新迁移。

## 2. 十题实测

`elapsed` 为客户端「发出请求 → 收到完整响应」；`服务端耗时`/`首字` 取自 `chat_logs`。`status` 列对 503 显示错误码，其余为响应 `status` 字段。

| # | 课程 | 问题 | 终态 | elapsed | 服务端耗时 | 首字 | 引用 | request_id |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 数据结构 | 什么是栈 | `answered` | 8.24 秒 | 8224 ms | 7828 ms | 2 | `01M41FR9CM2BT6CKQ6HY4C93YP` |
| 2 | 数据结构 | 栈和队列有什么区别 | **`error` / `LLM_UNAVAILABLE` / `truncated`（HTTP 503）** | 10.27 秒 | 10255 ms | 9762 ms（出字后撤回） | 0 | `01M41FRHE0X39SFJZ1AKAYEERQ` |
| 3 | 数据结构 | 顺序栈入栈需要检查什么 | `answered` | 9.51 秒 | 9500 ms | 9287 ms | 1 | `01M41FRVEWY7EMGX7RCZ5AZB63` |
| 4 | 数据结构 | 循环队列如何判断空与满 | `answered` | 5.11 秒 | 5098 ms | 4816 ms | 1 | `01M41FS4RAPGHK1ADRT2A02P20` |
| 5 | 数据结构 | 今天天气怎么样（课外） | `not_covered` / `below_similarity_threshold` | 0.54 秒 | 524 ms | — | 0 | `01M41FS9R01P03B54QXZKJEDGV` |
| 6 | 操作系统 | 什么是进程 | `answered` | 3.18 秒 | 3169 ms | 3028 ms | 1 | `01M41FSA97G121ZQZ1FHDTRXFW` |
| 7 | 操作系统 | 进程和线程有什么区别 | `answered` | 6.86 秒 | 6840 ms | 6537 ms | 3 | `01M41FSDCJ5KTASCXB8RY98YC4` |
| 8 | 操作系统 | 进程有哪些基本状态 | `answered` | 3.75 秒 | 3742 ms | 3460 ms | 1 | `01M41FSM2WH6CN5GTPY71J1EH9` |
| 9 | 操作系统 | PCB 保存哪些信息 | `answered` | 5.18 秒 | 5167 ms | 5020 ms | 1 | `01M41FSQREDSW12Y61V3AJTGB3` |
| 10 | 操作系统 | 怎么制作红烧肉（课外） | `not_covered` / `below_similarity_threshold` | 0.66 秒 | 646 ms | — | 0 | `01M41FSWTTSGVZ03YPBPN6GDWE` |

**终态分布**：`answered` 7、`error/truncated` 1、`not_covered` 2；没有 `timeout`、没有 `upstream`、没有 `auth`。

- **完整耗时**：已作答 7 题 3169～9500 ms（中位 5167 ms）；截断那题 10255 ms；两题课外 524/646 ms。**10 题全部 ≤ 15 秒** —— 15 秒链路时限按实际完整耗时判定**达标**（最慢 10.27 秒，为上限的 68%）。
- **首字耗时**：已作答 7 题为 3028 / 3460 / 4816 / 5020 / 6537 / 7828 / 9287 ms（中位 5020 ms）。S2 的首字目标是 ≤3 秒，**7 题全部未达标**，最小的一题也超出 28 ms，最大为目标的 3.1 倍。截断那题在 9762 ms 时已出字，随后整篇撤回（`delivered` 后撤回由 J07/J09 负责）。
- **课外问题**：两题都在检索阶段按 `below_similarity_threshold` 拒绝，0.5～0.7 秒返回，**没有发起生成调用**（只各发 1 次查询向量），未产生生成费用。

## 3. 比较类题在 2048 下的表现（本轮重点）

| 问题 | 1024 时（旧 L02 记录，**不同课程/资料**） | 2048 本轮实测 |
| --- | --- | --- |
| 数据结构「栈和队列有什么区别」 | `not_covered` / `all_citations_invalidated`（输出撞 1024） | **仍是失败**，但终态变为 `error` / `LLM_UNAVAILABLE` / `truncated`（HTTP 503），输出 2048 撞顶，`invalidation_subtype = uncited_sentence` |
| 操作系统「进程和线程有什么区别」 | 未测过 | **`answered`**，6840 ms，3 条引用，输出未撞顶 |

结论要分两层写清楚：

1. **故障分类确实按 ADR-082 决定 2 修正了**：截断且逐句出处校验不通过时，终态从旧的 `not_covered/all_citations_invalidated`（检索资料不足的语义）改成 `error` + `LLM_UNAVAILABLE` + `details.reason = truncated` + HTTP 503，`chat_logs` 记 `error_reason = truncated`、`truncated = 1`。两种子类在本轮都被实际触发：数据结构 Q2 是 `uncited_sentence`（有有效标记但存在缺标记的结论单元）。这与 ADR 描述逐条一致。
2. **2048 并没有让比较类问题普遍可答**：数据结构的比较题依旧撞顶失败。而且**同一门课、同一个问题「什么是栈」在本轮出现两种结局**——被中断的第一次尝试（客户端漏发 `Accept: application/json`，服务端仍完成并记录）输出 2048 撞顶 → `error/truncated`（`invalidation_subtype = no_markers`，request_id `01M41FNT0S7EEYCSSGV6HQYWST`）；改正请求头后重跑同一问题 → `answered`。**说明 2048 对这门课的问答处在临界位置，结局不稳定**，不是「2048 已够用」。

> 关于那次被中断的尝试：它计入本轮费用（第 5 节），终态取自 `chat_logs`；它不替代任何一题的结果，作为非确定性的证据单列在 `evaluation/raw/l15/question-evidence.json` 的 `aborted_first_attempt`。

## 4. 逐题出处核对（未因提高上限而放宽校验）

- 7 题 `answered` 的 `invalidation_subtype` 全为 NULL，即逐句出处校验通过（每句话都带有效标记）；这一点由服务端校验强制，**不因上限提高而放宽**。
- 抽查两题，引用与内容对得上、且都在本课内：
  - 数据结构「什么是栈」→ `[1] ch3-stack-queue.md :: 第3章 栈与队列 > 3.2 栈 > 3.2.1 栈的定义 > 第1段`、`[4] … > 3.6 本章小结 > 第1段`。回答 6 句，句句带标记。
  - 操作系统「进程和线程有什么区别」→ `[1] … > 2.4.2 进程与线程的比较 > 第1段`、`[2] … > 2.4.1 线程的定义 > 第1段`、`[5] … > 2.2.4 进程切换 > 第1段`。比较题恰好命中「进程与线程的比较」这一节。
- **课程隔离**：数据结构的 4 条引用全部指向 `ch3-stack-queue.md`，操作系统的 6 条全部指向 `ch2-process-thread.md`，**没有跨课引用**。`graph_version` 全部为 `1`，与两门课当前的发布版本一致。
- 每题的回答正文、引用清单（文件名 + 章节路径 + chunk_id）已存 `evaluation/raw/l15/question-evidence.json`；引用块的原文不在该文件，可按章节路径在 `datasets/contest/` 对应文件里核。

## 5. 用量、D2 向量记账与累计

**生成模型（预算口径）**

| 项 | 值 |
| --- | --- |
| 本轮调用 | `answer_with_context` **9 次**（8 题作答 + 1 次被中断尝试；两题课外未生成） |
| 本轮输入 / 输出 | 18764 / 10187 → **28951 token** |
| 单次输出上限 | `max_output_tokens = 2048`；实际最大输出 2048（即 2 次撞顶） |
| 本轮之前累计 | **619217** |
| **累计** | **619217 + 28951 = 648168 / 5000000**（本轮上限 `min(619217+80000, 5000000) = 699217`，**未越线**） |

**D2 在线向量（单列，按 ADR-082 决定 6 不计入生成预算）**

| 项 | 值 |
| --- | --- |
| 本轮 `embedding` 行 | **10 行**，status 全 `ok`，输入合计 **59 token** |
| 归属 | `request_id` = 对应问答的 `request_id`，**10 行的 request_id 全部能在 `chat_logs` 找到**；`user_id`/`task_id` 为空、`max_output_tokens = 0`，与决定 6 一致 |
| 发布向量 | 本轮**没有发布**，因此没有新的 `publish:<version_id>` 行。库中现有 20 行是 L11-6 两门 Markdown 课程发布留下的（随同步的数据库一起进来），未新增 |
| **缓存命中不新增行** | 11 个问答请求只产生 10 行——重复提问（两次「什么是栈」）的第二次**没有新增 embedding 行**，说明查询向量命中缓存且未记账。这与决定 6「缓存命中不发请求、不新增行」一致 |
| 累计 | 11884 + 59 = **11943 token**（另计） |

**费用估计**：仓库没有核对过的向量/生成单价，累计以 token 计（用户决定的口径）。按规格第 11 节记录的保守估算（25～30 万 token 约 1～1.5 元），本轮 28951 token 约 **0.1～0.15 元**；实际以供应商控制台为准。

## 6. 单列：历史 L11 抽取与准确率（不宣称赛题全达标）

- **抽取 ≤60 秒仍未达标**：L11-6 实测两门课 × 两种格式为 83.97 / 200.37 / 75.51 / 162.54 秒，四份全部超过 60 秒（详见 `evaluation/reports/l11-teacher-loop-2026-10.md`）。本轮不重复抽取，**不改变该结论**。
- **准确率待人工判定**：L11-6 的四份原始 AI 输出在 `evaluation/raw/l11/`，PDF 段落合并修复后的复测（L11-7）仍未执行。本轮只测问答，不做准确率判定。
- 赛题三项里，本轮能支持的是问答侧：**10 题完整耗时全部 ≤15 秒**；知识点 ≥20、关系 ≥3 种由 L11-6 覆盖（75/71/71/74 与 4/3/4/3）；**抽取 ≤60 秒未达标**；准确率未判定。因此**不宣称赛题指标全达标**。

## 7. 复现

```bash
# 测量 checkout：codex/plan-b-takeover @ 257750e（需 .env 与含两门已发布课程的 SQLite）
git rev-parse HEAD && git status --short
PYTHONPATH="$PWD/src/backend" .venv/bin/python -c \
  'from app.services.qa.generate import ANSWER_MAX_OUTPUT_TOKENS; assert ANSWER_MAX_OUTPUT_TOKENS == 2048'
# 起 API 与 worker（复用已在运行的 Neo4j；不要用 start.sh，它会为本 checkout 另起 Neo4j 抢端口）
# 学生须是两门课的成员且已保存自己的模型 API
MEASURE_PASSWORD=<演示口令> .venv/bin/python .demo/l15-qa/ask_capture.py --since <起始UTC> --cap 80000
# 官方汇总口径（本轮的同一批问题未再用它跑第二遍，以免重复付费）：
MEASURE_PASSWORD=<演示口令> .venv/bin/python evaluation/measure_web_flow.py ask \
  --base-url http://127.0.0.1:8001 --username demo_student --password-env MEASURE_PASSWORD \
  --course-id <CID> --questions <问题文件>
```

```sql
SELECT request_id, course_id, outcome, reason, error_code, error_reason, truncated,
       invalidation_subtype, latency_ms, first_delta_latency_ms
FROM chat_logs WHERE created_at >= '<起始UTC>' ORDER BY created_at;

SELECT request_id, purpose, status, max_output_tokens, usage_input, usage_output, latency_ms
FROM model_calls WHERE created_at >= '<起始UTC>' ORDER BY created_at;
```

被测课程（复用 L11-6，未改动）：数据结构 `4f32542066b44f4890cb6f6d765971ed`（发布 v1，75 节点 / 66 边）、操作系统 `777c327ca1a247cea7ae36a69ec4a106`（发布 v1，71 节点 / 55 边）。本轮为该两门课补加了 `demo_student` 成员（HTTP 201，无模型费用）。
