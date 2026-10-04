# C02-4 问答提示词 v3 与推理埋点真实复测（2026-10-04）

> **状态：按交接的停止条件在第 1 题后停止（exit 3），未完成 13 题的复测。** 停止原因不是预算用尽，而是**出现 1 次 usage 未知的生成调用**——交接第 5 节把这一条列为停止条件，工具自动拦下并退出 3。按第 4 节「照实记录，不重跑」，本轮到此为止，剩余 12 题未测。
>
> 本轮拿到的最有价值证据：**推理埋点确实有值**（`reasoning_chars=346`、`first_reasoning_ms=757`），且 15 秒链路预算被**推理之外**的环节吃掉——生成阶段只分到 1.84 秒。

## 1. 命令、版本与退出码

```bash
# 测量 checkout：claude/plan-c-reliability（本交接所在提交）
git log --oneline -1                     # 458b961
PYTHONPATH=src/backend .venv/bin/python -c \
  'from app.services.qa.generate import ANSWER_MAX_OUTPUT_TOKENS as m, ANSWER_PROMPT_VERSION as v; assert (m, v) == (2048, 3); print(m, v)'
# → 2048 3，exit 0
# 迁移：启动时 Applied migrations: 017；备份 20261004T025422637900Z-before-017.sqlite（integrity ok，16 条迁移）
# 开跑前生成累计 = 648168（交接要求的硬校验值）✓
export ROUND=2026-10-04T02:54:51.000Z
.venv/bin/python evaluation/measure_web_flow.py ask --base-url http://127.0.0.1:8001 --username demo_student \
    --password-env MEASURE_PASSWORD --course-id 4f32542066b44f4890cb6f6d765971ed \
    --questions .demo/c02/c02-course1.txt --stream --out evaluation/raw/c02/course1.jsonl \
    --audit-db src/backend/storage/smartsketch.sqlite3 --cap 45000 --round-started-at "$ROUND"
# → 第 1 题后 exit 3；course2 / repeat 两组按 `|| break` 未开跑
```

| 项 | 值 |
| --- | --- |
| checkout / HEAD | `smartsketch-plan-a-fixes-e70a34` / `458b961`（干净） |
| 常量核对 | `ANSWER_MAX_OUTPUT_TOKENS=2048`、`ANSWER_PROMPT_VERSION=3`（断言 exit 0） |
| 迁移 | 017 已执行；新列 `usage_reasoning`/`reasoning_chars`/`first_reasoning_ms`/`first_content_ms` 就位 |
| 开跑前生成累计 | **648168**（与交接一致，未开跑即校验通过） |
| 实际停止原因 | `存在 1 次 usage 未知的生成调用，无法确认额度，停止` |
| 已完成题数 | **1 / 13**（course1 第 1 题） |
| 退出码 | ask = **3**（按定义：因止损、usage 未知或拿不到响应而停止） |

## 2. 唯一一题的逐项结果

问题「什么是栈」（数据结构，`4f325420…`）：

| 字段 | 值 |
| --- | --- |
| 结局 | `error` |
| `error_code` / `error_reason` | `LLM_UNAVAILABLE` / **`timeout`** |
| 完整响应（客户端） | **15.02 秒**；服务端 `latency_ms` 15015 ms |
| 服务端首个 delta（`first_delta_latency_ms`） | **null**（没有对外发出过有效增量） |
| 客户端 SSE 首个 delta | **null** |
| 首次推理（`first_reasoning_ms`） | **757 ms** ✅ 有值 |
| 推理字符数（`reasoning_chars`） | **346** ✅ 有值 |
| 首次可见内容（`first_content_ms`） | **null**（到截止都没产出可见内容） |
| 推理 token（`usage_reasoning`） | **null**（未返回） |
| 输入 / 输出 token | **null / null（usage 未知）** |
| 引用数 / 可见回答字数 | 0 / 0 |
| `request_id` | `01M42DBVSGW9B82KW7QXJ9WZZ4` |

**15 秒预算的实际去向**（`audit-records.json` 的时间拆分，自洽相加 = 15015 ms）：

| 环节 | 耗时 | 占 15 秒 |
| --- | --- | --- |
| 查询向量 `embedding` | **4 925 ms** | 33% |
| 其余（检索、上下文装配、提示渲染等残差） | **8 250 ms** | 55% |
| 生成 `answer_with_context` | **1 840 ms** | 12% |

生成被截止时间切断时，它已经产出 346 字符推理（首个推理在 757 ms），但**从未产出可见内容**。

## 3. 对 C02-4 三个问题的回答

1. **供应商是否返回推理内容或推理 token？** —— **内容能观测到，token 数没有**。`reasoning_chars` 与 `first_reasoning_ms` 都写入了值，说明新埋点确实抓到了推理增量；但同一行的 `usage_reasoning = null`，即这次响应没有返回推理 token 计数。**样本只有 1 次且是失败调用**，不能据此推断成功调用也不返回。C02-1 的「推理吃掉 2048 输出预算」在**问答链路上本轮未获证实**（没走到生成完成）。
2. **提示词 v3 下比较题重复 3 次的结局** —— **未测**。停止发生在第 1 题，`repeat` 组按 `|| break` 未开跑。交付物里没有 `repeat.jsonl`（不补跑）。
3. **首字三列口径** —— 本轮给出了一个「什么都没出」的基线：服务端首个 delta = null、客户端 SSE 首个 delta = null、首次可见内容 = null，而**首次推理 = 757 ms**。即：新埋点能在「没有任何可见输出」的情况下把推理起点定量下来，这正是 C02-1 需要的那类观测；但它也说明**首字三列在超时场景下会全空**，只有推理列有值。

## 4. 与 L15（v2）的对照（不是严格 A/B）

| 项 | L15（v2，2026-10-03） | C02-4（v3，2026-10-04） |
| --- | --- | --- |
| 同一问题「什么是栈」 | `answered`，8.24 秒，2 条引用 | **`error/timeout`，15.02 秒** |
| 查询向量耗时 | 该轮 embedding 最大 3510 ms | 本轮 **4925 ms** |
| 生成耗时 | —（正常出字） | 1840 ms 后被截止切断 |

两次运行的时间、网络与供应商状态都不同，**不做因果结论**。但要指出一个与提示词无关的观察：本轮光是**查询向量（4.9 秒）+ 检索装配残差（8.25 秒）就占了 13.2 秒**，生成只剩 1.84 秒——即使提示词与推理行为完全不变，这个分配也几乎不可能产出答案。**「15 秒内答不完」在这道题上首先是链路预算分配问题，其次才是推理预算问题。**

## 5. 用量与预算

| 项 | 值 |
| --- | --- |
| 本轮生成计费（已记录） | **0 token**（1 次生成调用 usage 未知，不计） |
| 本轮 `usage` 未知的生成调用 | **1 次**（`status=error`、`error_class=timeout`） |
| 本轮向量（另计） | 1 行 / 3 token |
| 本轮 cap | 45000（**远未触及**） |
| 跑完累计（记录值） | **648168**（与开跑前相同） |

**记账口径提醒**：那 1 次超时调用在供应商侧很可能已产生计费（已出 346 字符推理），但本地记为未知、**不计入累计**。因此「648168」是**记录口径**的累计，不等于供应商控制台的实际用量。C03-1 的开跑前核对因此有 1 次未计入的调用（已在其报告中写明）。

## 6. 证据路径

| 内容 | 路径 |
| --- | --- |
| 逐题结果（course1，1 题） | `evaluation/raw/c02/course1.jsonl` |
| 合并副本（同上，供 `audit --records`） | `evaluation/raw/c02/all.jsonl` |
| 时间窗审计（含 ledger 与 reasoning 列存在性） | `evaluation/raw/c02/audit-window.json` |
| 按请求 ID 关联的审计（含时间拆分与推理列） | `evaluation/raw/c02/audit-records.json` |
| course2 / repeat | **不存在**（未开跑，不补） |

`audit-window.json` 的按时间窗关联得到 0 个请求（窗口内 `request_ids` 为空），有效关联来自 `audit-records.json`（按记录里的 request_id）——**用 `--records` 那份读结论**。

## 7. 复现

```bash
export ROUND=$(date -u +%Y-%m-%dT%H:%M:%S.000Z)
.venv/bin/python evaluation/measure_web_flow.py ask --base-url http://127.0.0.1:<api端口> --username demo_student \
  --password-env MEASURE_PASSWORD --course-id 4f32542066b44f4890cb6f6d765971ed \
  --questions <c02-course1.txt> --stream --out evaluation/raw/c02/course1.jsonl \
  --audit-db <库路径> --cap 45000 --round-started-at "$ROUND"
.venv/bin/python evaluation/measure_web_flow.py audit --db <库路径> --records evaluation/raw/c02/all.jsonl
```

## 8. 未验证 / 限制

- 13 题里只跑了 1 题；比较题 3 次重复、p50/p95、推理 token 占比、可见回答字数等**都没有数据**。
- 「推理是否被供应商返回 token 数」只有 1 个失败样本，且为 null；成功调用是否返回**未验证**。
- 与 L15 的对照**不是严格 A/B**（时间、网络、供应商状态不同），报告只做对照不给因果。
- 本轮没有测「推理占输出比例」；该比例在 **C03-1 的抽取链路**上首次拿到实测值（79.9%，见 C03-1 报告）——那是抽取，不是问答，不能直接外推。
- `audit-window.json` 的时间窗关联为 0 请求，这是工具的窗口语义所致，不是数据缺失（`audit-records.json` 已正确关联）。
