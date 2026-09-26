# 知识抽取准确率测试报告

> 本文件是参赛材料「知识抽取准确率的测试报告」的正式骨架（`specs/course-knowledge-graph.md` 验收 7；任务 K02）。
> **当前状态：真实模型判定「未实测」。** 下文第 6 节的数字只来自假模型的管线自检，**假模型不充真实效果**，不能用来证明达标。

| 项 | 内容 |
| --- | --- |
| 评测脚本 | `evaluation/evaluate_extraction.py`（仅标准库，不调用模型或网络） |
| 脚本测试 | `tests/backend/test_k02.py` |
| 判定口径 | `evaluation/README.md`（K01） |
| 基准材料 | 待 D-01 签收（一门课程的完整一章） |
| 模型 | 待 D-02 签收 |
| 报告日期 | 2026-09-26（骨架） |

## 1. 判定口径（摘要）

完整口径以 `evaluation/README.md` 为准，本节只摘要脚本实际实现的规则。

- **赛题硬指标**：
  - 实体数：`predictions.entities` 中 `source == "ai"` 的条目（融合去重后）不少于 20 个；恰为 20 个达标。
  - 准确率：人工判定 `correct / 已判定条数`，实体和关系分别计算，各自不低于 70%；恰为 70% 达标。比较用 `fractions.Fraction` 精确进行，7/10 达标，69/100 未达标。
  - 三项都达标才算「达标」。任一项不足写「未达标」并给出差距（`gap`）。
- **判定状态**：`model.is_fake` 为真时，结论一律写「不可用于判定（假模型）」，不看数值。否则实体数 < 20 或任一准确率 < 70% 即「未达标」；按 `judgments.seed` 重算的抽中项有缺判时写「判定不完整」；没有判定时准确率为 `null`，结论写「未判定」。准确率只统计抽中项，样本外的判定不计。
- **统计范围**：各指标只统计 `source == "ai"` 的条目，其他来源只在 `counts.non_ai_*` 中报告数量。
- **抽样**：`sample` 子命令对 `source == "ai"` 的实体、关系分别抽样。条目先按 `id` 排序，再用 `random.Random(seed)` 抽取，默认种子 20260926，默认样本量 100。总体不超过样本量时全量检查（`mode: "full"`）。
- **与金标比对（辅助指标，不替代人工判定）**：
  - 名称经 NFKC、casefold 并去除全部空白后，与金标名或任一别名相同即命中。
  - 按预测的输入顺序一对一配对，已被占用的金标再次命中记为重复（FP）。
  - 输出名称级与有类型两种口径。有类型口径沿用同一组配对，类型也相同才算 TP。
- **关系比对**：端点经名称级配对映射到金标 ID。`RELATED_TO` 无向，`CONTAINS`、`PREREQUISITE`、`EXAMPLE_OF` 有向。端点无法映射的关系记为 FP。
- **输出**：tp/fp/fn/precision/recall/F1，分总体、五类实体、四类关系。类型为空也列出。分母为 0 时写 `null`，小数保留 4 位。键排序，相同输入逐字节一致。
- **提示词迭代材料与最终判定材料**应当不同；相同时须在第 3 节注明。

## 2. 真实模型判定结果：未实测

**状态：未实测。** 原因：

1. **D-01（基准章节）未签收**：用哪门课的哪一章尚未确定，所以最终判定材料不存在。K01 的合成夹具不是最终基准（`is_final_benchmark: false`）。
2. **D-02（模型供应方）未签收**：还没有可用于判定的真实模型。
3. **付费调用须另行确认**：D-01、D-02 签收后，真实模型调用仍须用户单独确认才能执行。

因此本报告**不给出**实体数、实体准确率或关系准确率的实测值，也不作「达标」或「未达标」的结论。

| 硬指标 | 阈值 | 实测值 | 结论 |
| --- | --- | --- | --- |
| AI 实体数（融合去重后） | ≥ 20 | 未实测 | 未判定 |
| 实体人工抽样准确率 | ≥ 70% | 未实测 | 未判定 |
| 关系人工抽样准确率 | ≥ 70% | 未实测 | 未判定 |
| **总体** | 三项全达标 | — | **未实测** |

## 3. 解除阻塞后的复现步骤

前提：D-01、D-02 已签收，付费调用已获用户确认；把该章处理到 `awaiting_review`，并导出草稿为 predictions.json（`model.is_fake: false`）。

```bash
# 1) 固定种子抽样，生成人工判定清单与 judgments 模板
python3 evaluation/evaluate_extraction.py sample \
  --predictions <run>/predictions.json --seed 20260926 --size 100 > <run>/sample.json

# 2) 判定人按 evaluation/README.md 的标准填写 <run>/judgments.json
#    （值只能是 "correct" 或 "incorrect"；run_id 必须与 predictions 一致）

# 3) 计分与硬指标判定
python3 evaluation/evaluate_extraction.py score \
  --gold <benchmark>.json --predictions <run>/predictions.json \
  --judgments <run>/judgments.json --out <run>/report.json
```

完成后在第 2 节填写实测值和 `hard_indicators.verdict`，在第 4 节逐条列出抽样判定，在第 5 节填写错误统计。同时记录以下信息：

| 项 | 填写 |
| --- | --- |
| 基准数据集 `dataset_id` / 章节 | |
| 是否与提示词迭代材料相同 | |
| `run_id` / 模型 ID / 提示词版本 | |
| 判定人 / 判定日期 | |
| 种子 / 样本量 / 全量或抽样（实体、关系各一） | |
| `report.json` 的 sha256 | |

## 4. 逐条判定表（模板）

每个被抽中的条目列一行，不删不补。判定标准见 `evaluation/README.md`。

### 4.1 实体

| # | 预测 ID | 名称 | 类型 | 判定（correct / incorrect） | 理由（incorrect 时必填） |
| --- | --- | --- | --- | --- | --- |
| 1 | | | | | |

小计：已判定 __ 条，正确 __ 条，准确率 __（≥ 70% 达标）。

### 4.2 关系

| # | 预测 ID | 起点 | 关系类型 | 终点 | 判定（correct / incorrect） | 理由（incorrect 时必填） |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | | | | | | |

小计：已判定 __ 条，正确 __ 条，准确率 __（≥ 70% 达标）。

## 5. 错误类型与改进方向

脚本在 `report.json` 的 `errors` 中按下表统计金标比对的未命中原因（`details` 中有逐条结果）。真实模型的计数待实测后填写。

| 对象 | 错误类型（字段） | 含义 | 实测计数 | 改进方向 |
| --- | --- | --- | --- | --- |
| 实体 FP | `type_mismatch` | 名称命中金标但类型不同 | 待实测 | 在 `extract_entities` 提示词中补充五类实体的判别示例（如「递归」是方法而非概念）；审核页突出类型 |
| 实体 FP | `duplicate` | 同一知识点被重复抽出（含别名） | 待实测 | 加强 E08/E09/E10 融合：别名归一、同义裁决；在抽取阶段按章节合并同名 |
| 实体 FP | `no_gold_match` | 金标中没有的条目（可能是冗余，也可能是金标遗漏） | 待实测 | 人工复核后区分「模型冗余」与「金标漏标」；冗余多时收紧提示词中的知识点粒度定义 |
| 实体 FN | `not_extracted` | 金标实体未被抽出 | 待实测 | 启用或调整 E06 补漏（gleaning）；检查分块边界是否切断定义 |
| 实体 FN | `type_mismatch` | 抽出了但类型错 | 待实测 | 同实体 FP 的 `type_mismatch` |
| 关系 FP | `unmapped_endpoint` | 端点实体没有匹配到金标 | 待实测 | 先改善实体抽取与融合；关系抽取只引用已确认的实体 ID |
| 关系 FP / FN | `reversed_direction` | 有向关系方向相反 | 待实测 | 在关系提示词中明确「A 是 B 的先修」「A 是 B 的例子」的方向约定并给反例 |
| 关系 FP / FN | `wrong_relation_type` | 端点相同，关系类型不同 | 待实测 | 细化四类关系的判别标准；对 `PREREQUISITE` 与 `RELATED_TO` 的边界给示例 |
| 关系 FP | `duplicate` | 同一金标关系被重复预测 | 待实测 | 写入草稿前按（起点、终点、类型）去重，`RELATED_TO` 按无序对去重 |
| 关系 FP | `no_gold_match` | 端点都能映射，但金标无此关系 | 待实测 | 人工复核是冗余还是金标漏标；要求模型为关系给出原文证据 |
| 关系 FN | `endpoint_not_extracted` | 金标关系的端点实体未被抽出 | 待实测 | 同实体 FN |
| 关系 FN | `not_predicted` | 端点都在，但关系未被抽出 | 待实测 | 扩大关系抽取的上下文窗口；跨块关系另行补抽 |

赛题允许存在冗余和错误，但要求说明改进方向。实测后按计数从高到低排序，只保留实际出现的改进项。

## 6. 管线自检（假模型，不是判定）

> **这不是准确率判定。** 以下数据由 K01 自编标注集 `evaluation/fixtures/synthetic.json` 按固定规则扰动出的假模型预测（`model.is_fake: true`）算得，判定由自检脚本全部填为 `correct`，不是人工判定。它只用来确认计分管线端到端可运行、错误分类有效、假模型即使数值全部达标也被拒绝判定。**假模型不充真实效果。**

- 扰动规则（生成脚本在会话 scratchpad，不入仓库；按下列规则可重建）：金标实体按顺序编号 k，`k % 5 == 4` 的漏掉；`k % 7 == 3` 的类型改为五类中的下一类；追加 1 个取首个有别名实体的别名的重复项、2 个金标没有的实体（「链式前向星」「哈希冲突」）、1 个 `source = "manual"` 的实体。关系保留两端都在的金标关系，其中第一条 `PREREQUISITE` 反向、第一条 `CONTAINS` 改为 `RELATED_TO`，再追加 1 条端点不在金标里的关系。
- 运行：`run_id = selfcheck-fake-synthetic`，`dataset_id = synthetic-ds-ch3`。命令依次为 `sample --predictions pred.json`、`score --gold evaluation/fixtures/synthetic.json --predictions pred.json --judgments judg.json --out report.json`，exit 0。
- 确定性：`--out` 写文件与写到标准输出两次运行，sha256 都是 `843f52298de774fe0eee547b512e0dd385d280ceeb3411514323993647718fde`。

| 口径 | tp | fp | fn | P | R | F1 |
| --- | --- | --- | --- | --- | --- | --- |
| 实体（名称级） | 36 | 3 | 9 | 0.9231 | 0.8 | 0.8571 |
| 实体（有类型） | 31 | 8 | 14 | 0.7949 | 0.6889 | 0.7381 |
| 关系 | 25 | 3 | 15 | 0.8929 | 0.625 | 0.7353 |

- 计数：金标 45 个实体、40 条关系；预测 40 个实体（其中 1 个非 AI，不计入指标）、28 条关系。
- 错误分类：
  - 实体 FP：`type_mismatch` 5、`no_gold_match` 2、`duplicate` 1；实体 FN：`not_extracted` 9、`type_mismatch` 5。
  - 关系 FP：`reversed_direction` 1、`wrong_relation_type` 1、`unmapped_endpoint` 1；关系 FN：`endpoint_not_extracted` 13、`reversed_direction` 1、`wrong_relation_type` 1。
- 硬指标输出：AI 实体数 39、实体准确率 39/39、关系准确率 28/28，数值全部过线，但结论为 **「不可用于判定（假模型）」**，`passed: null`。
