# Claude 复核：DeepSeek harness 的计划 A 未完成项检查（`92aa8bc`）

- 日期：2026-10-03；复核者：Claude；对象：`92aa8bc`（交接 `docs/handoffs/deepseek-plan-a-verification.md`，依据 `docs/handoffs/claude-plan-a-verification-handoff.md`）。
- 结论：**通过**。只改了交接允许的三个文档，没有改代码；结论与本地证据一致。检查发现的两个缺陷已登记为计划 A 遗留项（第 3 节），未在本次修复。

## 1. 范围核对

| 项 | 结果 |
| --- | --- |
| 改动文件 | `docs/handoffs/deepseek-plan-a-verification.md`（新增）、`docs/tasks.md`（L02、L10 两行与 V3 一节）、`evaluation/reports/l02-baseline-2026-10.md`（状态行、第 4、5 节与结尾说明） |
| 业务代码、测试、契约、迁移、脚本 | 未改 |
| 基线报告 | 抽取数据原样保留；只替换了交接要求替换的部分 |

## 2. 证据抽查（本地数据库与日志）

| 结论 | 抽查结果 |
| --- | --- |
| 发布成功，82 个知识点、73 条关系 | `graph_versions`：课程 `2ace…bc7fdf1` 有 version 1、kind publish、82/73 |
| 问答完整耗时 p50 5.13 秒、最大 6.12 秒 | `chat_logs` 五题：6122、5128、5949、2189、399 毫秒，中位数 5128 |
| 第 3 题被整篇撤回且可复现 | 两次提问均为 `not_covered`、`all_citations_invalidated`、`no_markers`、`truncated = 1` |
| 课外题按预期未覆盖 | `not_covered`、`below_similarity_threshold`，399 毫秒 |
| V3 完整门禁通过 | `.demo/logs/verify-integration-planA.log` 末行 `Verification (integration) passed.`；端到端 2 passed |

## 3. 登记的遗留缺陷（未修，需单独认领）

| 编号 | 缺陷 | 影响 | 建议 |
| --- | --- | --- | --- |
| D1 | 答案超过 `ANSWER_MAX_OUTPUT_TOKENS = 1024`（`services/qa/generate.py:116`）被截断后，引用校验判定「全部引用无效」，整篇撤回并报 `not_covered`。资料实际覆盖该问题 | **高**：把生成故障显示成「资料未覆盖」，违反「资料未覆盖与服务故障分开显示」的硬要求；比较类问题容易触发 | 先写复现测试（假模型返回超长、引用在截断点之后的回答），再在「截断」与「无依据」之间区分处理：至少不能归为 `not_covered`。是否调整输出上限或提示词，需结合 15 秒时延一起定 |
| D2 | 发布时的向量调用不写入 `model_calls` | 低：用量登记不全，发布向量化的费用无法从调用记录统计 | 核对 ADR-011 修订 2 决定 12 的原意后再定是否补记 |
| D3 | 问答准备阶段的查询向量调用不受 15 秒链路截止约束（见 `claude-deepseek-l09-2026-10-03.md` 第 3 节） | 中：向量服务不可达时提问会挂数分钟 | 同前 |

另：首字耗时 5.88、4.70、2.07 秒。赛题只要求完整响应 ≤15 秒，本次已满足；首字 ≤3 秒是项目自定的体验目标，3 题中 2 题未达到，记为观察项。

## 4. 计划 A 状态

L00–L10 全部完成，完整门禁（含端到端）在业务改动后通过。遗留 D1–D3 与抽取 60 秒未达标（实测 141.72 秒）进入后续计划。累计计费 token 140230 / 5000000。
