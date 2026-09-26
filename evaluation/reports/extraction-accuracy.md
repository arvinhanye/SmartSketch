# 知识抽取准确率测试报告

> 本文件是参赛材料「知识抽取准确率的测试报告」（`specs/course-knowledge-graph.md` 验收 7；任务 K02）。
> **当前状态：真实模型已实测并完成人工判定，本次运行三项硬指标都达标。** 这是简化融合下的**初步结论**（见第 2 节「适用范围」）；第 6 节是假模型的管线自检，不是判定。

| 项 | 内容 |
| --- | --- |
| 评测脚本 | `evaluation/evaluate_extraction.py`（仅标准库，不调用模型或网络） |
| 脚本测试 | `tests/backend/test_k02.py`、`tests/backend/test_k02_run.py` |
| 判定口径 | `evaluation/README.md`（K01） |
| 基准材料 | 数据结构（自编示例）第3章「栈与队列」，`evaluation/fixtures/synthetic.json`（D-01 / ADR-026） |
| 模型 | DeepSeek V4.1 Flash，请求 `deepseek-flash`，响应 `deepseek-flash`（D-02a / ADR-027） |
| 判定记录 | `evaluation/reports/k02-live-20260926/judgments.json` |
| 报告日期 | 2026-09-26 |

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
- **提示词迭代材料与最终判定材料**应当不同；相同时须在第 3 节注明（本次不相同）。

## 2. 真实模型判定结果：达标（初步）

| 硬指标 | 阈值 | 实测值 | 结论 |
| --- | --- | --- | --- |
| AI 实体数（简化融合去重后） | ≥ 20 | 74 | 达标 |
| 实体人工准确率（全量 74 条） | ≥ 70% | 74/74 = 100.00% | 达标 |
| 关系人工准确率（全量 63 条） | ≥ 70% | 61/63 = 96.83% | 达标 |
| **总体** | 三项全达标 | — | **达标**（`hard_indicators.verdict`） |

**适用范围。** 本次运行用 `evaluation/run_live_extraction.py` 在本机完成，融合为**简化融合**（`fusion.mode = simplified`：只按 E08 `normalize_name` 主键去重，合并 4 个；不做别名、包含、向量候选和 E10 裁决）。main 上 E12/F13 的 `merging` 目前也是直通（ADR-029），所以完整融合接入后应按第 3 节步骤重跑一次；届时实体数会因别名合并略降，准确率以重跑结果为准。

**与金标的自动比对（辅助指标，不替代人工判定）。** 人工准确率远高于金标精确率，主要因为金标只收本章讲解过的核心知识点（K01 标注约定 1），模型抽出的其他合理知识点在自动指标中计为假阳性，人工判定时判对。

| 口径 | tp | fp | fn | P | R | F1 |
| --- | --- | --- | --- | --- | --- | --- |
| 实体（名称级） | 39 | 35 | 6 | 0.527 | 0.8667 | 0.6555 |
| 实体（有类型） | 37 | 37 | 8 | 0.5 | 0.8222 | 0.6218 |
| 关系 | 11 | 52 | 29 | 0.1746 | 0.275 | 0.2136 |

| 关系类型 | tp | fp | fn | P | R |
| --- | --- | --- | --- | --- | --- |
| `CONTAINS` | 4 | 32 | 8 | 0.1111 | 0.3333 |
| `EXAMPLE_OF` | 2 | 7 | 6 | 0.2222 | 0.25 |
| `PREREQUISITE` | 1 | 0 | 6 | 1.0 | 0.1429 |
| `RELATED_TO` | 4 | 13 | 9 | 0.2353 | 0.3077 |

## 3. 运行记录与复现

| 项 | 内容 |
| --- | --- |
| 基准数据集 `dataset_id` / 章节 | `synthetic-ds-ch3` / 第3章 栈与队列，`is_final_benchmark: true` |
| 是否与提示词迭代材料相同 | 不相同。`extract_entities` v2（E05，2026-09-25）与 `extract_relations` v2（E11，2026-09-26 05:57Z）都早于本标注集（K01，2026-09-26 07:28Z），之后未改提示词、先修表述清单或阈值 |
| `run_id` | `k02-live-20260926T084922Z`（2026-09-26 08:49:22～08:54:51 UTC，本机 macOS） |
| 模型 | 请求 `deepseek-flash`，响应 `deepseek-flash`，`is_fake: false`，无备用供应商 |
| 提示词 | `extract_entities` v2（sha256 `3d7cfca5…9e6`）、`extract_relations` v2（sha256 `be9c7881…3d6`）；输出上限各 4096 token |
| 处理规模 | 16 块、16 个小节；块失败 0；小节失败 1（见第 5 节）；未开 E06 补漏；`section_depth` 0（完整章节路径分组） |
| 丢弃 | 关系：跨小节重复 1、证据不在资料中 2；实体无丢弃；简化融合合并 4 个 |
| 模型调用 | 35 次（实体 16、关系 15、修复 4），全部 ok；usage 输入 27686、输出 68172，计费 95858 token（`calls_without_usage` 0），在 ADR-028 单任务预算 500000 内 |
| 判定人 / 判定日期 | Arvinhan / 2026-09-26（首轮全判对；复核后把 p-r053、p-r055 改判错） |
| 种子 / 样本量 | 20260926；实体 74、关系 63，都不超过 100，**全量检查** |
| predictions.json sha256 | `f4a94c09ed6912e622db925389647955526f5e1311061f7cf7601b8a92f9ae74`（含资料原文证据，未入库） |
| run.json sha256 | `e7736a38938cfabab2570416b9c50016d7d5d3d820de895c74e813af77eb3902` |
| sample.json sha256 | `f594cea4c65627dd899426d88189829551d2df87264c9c86493bf5f2a6723846` |
| judgments.json sha256 | `b2b3d5e482a5a328e1b34882f84c521dc0301e275cc097799aee89f0a173bd80` |
| report.json sha256（带判定） | `1f8f8e399e31800d4b1919fa47cd469a25661b4d554d1e703451d304a528abd8`（`--out` 与标准输出两次一致） |

人工判定在一个逐条展示原文证据、所属小节与金标对照的判定页上完成，判定值由判定人本人点选，Claude 未预填。复现命令：

```bash
python3 evaluation/evaluate_extraction.py sample   --predictions <run>/predictions.json --seed 20260926 --size 100 > <run>/sample.json
python3 evaluation/evaluate_extraction.py score   --gold evaluation/fixtures/synthetic.json --predictions <run>/predictions.json   --judgments evaluation/reports/k02-live-20260926/judgments.json --out <run>/report.json
```

完整融合接入后重跑时，按下文「本机运行步骤」生成新的 predictions.json，重新抽样、判定，并在本节追加一行新的运行记录。

## 4. 逐条判定表

每个抽中条目一行，不删不补。「金标对照」是自动比对结果，仅供参考。判定标准见 `evaluation/README.md` 第 6.3 节。

### 4.1 实体（全量 74 条）

| # | 预测 ID | 名称 | 类型 | 金标对照 | 判定 | 理由 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | p-e001 | 栈和队列是操作受限的线性表 | `concept` | 金标无 | correct |  |
| 2 | p-e002 | 栈和队列的应用场景 | `example` | 金标无 | correct |  |
| 3 | p-e003 | 栈 | `concept` | 一致 | correct |  |
| 4 | p-e004 | 栈顶 | `concept` | 一致 | correct |  |
| 5 | p-e005 | 栈底 | `concept` | 一致 | correct |  |
| 6 | p-e006 | 空栈 | `concept` | 一致 | correct |  |
| 7 | p-e007 | 后进先出 | `theorem` | 类型不同 | correct |  |
| 8 | p-e008 | 栈的基本操作 | `method` | 金标无 | correct |  |
| 9 | p-e009 | 入栈 | `method` | 一致 | correct |  |
| 10 | p-e010 | 出栈 | `method` | 一致 | correct |  |
| 11 | p-e011 | 入栈与出栈的时间复杂度 | `theorem` | 金标无 | correct |  |
| 12 | p-e012 | 顺序栈 | `concept` | 一致 | correct |  |
| 13 | p-e013 | 顺序栈的入栈与出栈操作 | `method` | 金标无 | correct |  |
| 14 | p-e014 | 上溢 | `concept` | 一致 | correct |  |
| 15 | p-e015 | 下溢 | `concept` | 一致 | correct |  |
| 16 | p-e016 | 共享栈 | `concept` | 一致 | correct |  |
| 17 | p-e017 | 链栈 | `concept` | 一致 | correct |  |
| 18 | p-e018 | 链栈的优点与代价 | `theorem` | 金标无 | correct |  |
| 19 | p-e019 | 顺序栈与链栈入栈出栈时间复杂度 | `formula` | 金标无 | correct |  |
| 20 | p-e020 | 出栈序列 | `concept` | 金标无 | correct |  |
| 21 | p-e021 | 合法出栈序列判定 | `theorem` | 一致 | correct |  |
| 22 | p-e022 | 出栈序列计数定理 | `theorem` | 一致 | correct |  |
| 23 | p-e023 | 卡特兰数 | `concept` | 类型不同 | correct |  |
| 24 | p-e024 | 卡特兰数公式 | `formula` | 重复 | correct |  |
| 25 | p-e025 | 出栈序列判断示例 | `example` | 一致 | correct |  |
| 26 | p-e026 | 队列 | `concept` | 一致 | correct |  |
| 27 | p-e027 | 队尾 | `concept` | 一致 | correct |  |
| 28 | p-e028 | 队头 | `concept` | 一致 | correct |  |
| 29 | p-e029 | 先进先出 | `concept` | 一致 | correct |  |
| 30 | p-e030 | 队列的基本操作 | `method` | 金标无 | correct |  |
| 31 | p-e031 | 入队 | `method` | 一致 | correct |  |
| 32 | p-e032 | 出队 | `method` | 一致 | correct |  |
| 33 | p-e033 | 假溢出 | `concept` | 一致 | correct |  |
| 34 | p-e034 | 循环队列 | `concept` | 一致 | correct |  |
| 35 | p-e035 | 循环队列指针后移公式 | `formula` | 一致 | correct |  |
| 36 | p-e036 | 循环队列元素个数计算公式 | `formula` | 金标无 | correct |  |
| 37 | p-e037 | 循环队列判空与判满 | `theorem` | 一致 | correct |  |
| 38 | p-e038 | 循环队列指针变化 | `example` | 一致 | correct |  |
| 39 | p-e039 | 链队列 | `concept` | 一致 | correct |  |
| 40 | p-e040 | 链队列入队操作 | `method` | 金标无 | correct |  |
| 41 | p-e041 | 链队列出队操作 | `method` | 金标无 | correct |  |
| 42 | p-e042 | 链队列的特性 | `theorem` | 金标无 | correct |  |
| 43 | p-e043 | 双端队列 | `concept` | 一致 | correct |  |
| 44 | p-e044 | 双端队列与栈和队列的关系 | `theorem` | 金标无 | correct |  |
| 45 | p-e045 | 栈与队列的逻辑结构 | `concept` | 金标无 | correct |  |
| 46 | p-e046 | 栈的后进先出特性 | `theorem` | 金标无 | correct |  |
| 47 | p-e047 | 队列的先进先出特性 | `theorem` | 金标无 | correct |  |
| 48 | p-e048 | 栈与队列的选用依据 | `method` | 金标无 | correct |  |
| 49 | p-e049 | 栈的典型应用场景 | `example` | 金标无 | correct |  |
| 50 | p-e050 | 队列的典型应用场景 | `example` | 金标无 | correct |  |
| 51 | p-e051 | 顺序存储与链式存储的比较 | `theorem` | 金标无 | correct |  |
| 52 | p-e052 | 顺序实现与链式实现的选用 | `method` | 金标无 | correct |  |
| 53 | p-e053 | 括号匹配算法 | `method` | 一致 | correct |  |
| 54 | p-e054 | 括号匹配成功的判定条件 | `theorem` | 金标无 | correct |  |
| 55 | p-e055 | 括号匹配实例 | `example` | 金标无 | correct |  |
| 56 | p-e056 | 中缀表达式 | `concept` | 一致 | correct |  |
| 57 | p-e057 | 后缀表达式 | `concept` | 一致 | correct |  |
| 58 | p-e058 | 中缀转后缀算法 | `method` | 一致 | correct |  |
| 59 | p-e059 | 后缀表达式求值算法 | `method` | 一致 | correct |  |
| 60 | p-e060 | 表达式求值两步法 | `method` | 金标无 | correct |  |
| 61 | p-e061 | 例3-4 表达式求值 | `example` | 金标无 | correct |  |
| 62 | p-e062 | 递归 | `concept` | 一致 | correct |  |
| 63 | p-e063 | 递归工作栈 | `concept` | 一致 | correct |  |
| 64 | p-e064 | 递归的局限 | `theorem` | 金标无 | correct |  |
| 65 | p-e065 | 递归转非递归 | `method` | 一致 | correct |  |
| 66 | p-e066 | 阶乘的递归计算 | `example` | 一致 | correct |  |
| 67 | p-e067 | 队列的应用场景 | `example` | 金标无 | correct |  |
| 68 | p-e068 | 队列的缓冲作用 | `concept` | 金标无 | correct |  |
| 69 | p-e069 | 银行排队模拟 | `example` | 一致 | correct |  |
| 70 | p-e070 | 先进先出服务次序 | `concept` | 金标无 | correct |  |
| 71 | p-e071 | 操作受限的线性表 | `concept` | 金标无 | correct |  |
| 72 | p-e072 | 顺序与链式实现 | `method` | 金标无 | correct |  |
| 73 | p-e073 | 栈的典型应用 | `example` | 金标无 | correct |  |
| 74 | p-e074 | 队列的典型应用 | `example` | 金标无 | correct |  |

小计：已判定 74 条，正确 74 条，准确率 100.00%（≥ 70% 达标）。

### 4.2 关系（全量 63 条）

| # | 预测 ID | 起点 | 关系类型 | 终点 | 金标对照 | 判定 | 理由 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | p-r001 | 栈 | `CONTAINS` | 栈顶 | 一致 | correct |  |
| 2 | p-r002 | 栈 | `CONTAINS` | 栈底 | 一致 | correct |  |
| 3 | p-r003 | 栈 | `CONTAINS` | 空栈 | 金标无 | correct |  |
| 4 | p-r004 | 栈 | `CONTAINS` | 后进先出 | 金标无 | correct |  |
| 5 | p-r005 | 栈 | `CONTAINS` | 栈的基本操作 | 端点不在金标 | correct |  |
| 6 | p-r006 | 栈的基本操作 | `CONTAINS` | 入栈 | 端点不在金标 | correct |  |
| 7 | p-r007 | 栈的基本操作 | `CONTAINS` | 出栈 | 端点不在金标 | correct |  |
| 8 | p-r008 | 栈顶 | `RELATED_TO` | 栈底 | 金标无 | correct |  |
| 9 | p-r009 | 入栈 | `RELATED_TO` | 栈顶 | 金标无 | correct |  |
| 10 | p-r010 | 出栈 | `RELATED_TO` | 栈顶 | 金标无 | correct |  |
| 11 | p-r011 | 入栈 | `RELATED_TO` | 出栈 | 金标无 | correct |  |
| 12 | p-r012 | 入栈 | `RELATED_TO` | 入栈与出栈的时间复杂度 | 端点不在金标 | correct |  |
| 13 | p-r013 | 出栈 | `RELATED_TO` | 入栈与出栈的时间复杂度 | 端点不在金标 | correct |  |
| 14 | p-r014 | 顺序栈 | `CONTAINS` | 顺序栈的入栈与出栈操作 | 端点不在金标 | correct |  |
| 15 | p-r015 | 上溢 | `RELATED_TO` | 下溢 | 金标无 | correct |  |
| 16 | p-r016 | 上溢 | `RELATED_TO` | 顺序栈 | 一致 | correct |  |
| 17 | p-r017 | 顺序栈 | `RELATED_TO` | 共享栈 | 金标无 | correct |  |
| 18 | p-r018 | 共享栈 | `RELATED_TO` | 上溢 | 一致 | correct |  |
| 19 | p-r019 | 链栈 | `CONTAINS` | 链栈的优点与代价 | 端点不在金标 | correct |  |
| 20 | p-r020 | 链栈 | `CONTAINS` | 顺序栈与链栈入栈出栈时间复杂度 | 端点不在金标 | correct |  |
| 21 | p-r021 | 出栈序列 | `CONTAINS` | 合法出栈序列判定 | 端点不在金标 | correct |  |
| 22 | p-r022 | 出栈序列 | `CONTAINS` | 出栈序列计数定理 | 端点不在金标 | correct |  |
| 23 | p-r023 | 出栈序列计数定理 | `RELATED_TO` | 卡特兰数 | 一致 | correct |  |
| 24 | p-r024 | 卡特兰数 | `CONTAINS` | 卡特兰数公式 | 端点不在金标 | correct |  |
| 25 | p-r025 | 出栈序列判断示例 | `EXAMPLE_OF` | 合法出栈序列判定 | 一致 | correct |  |
| 26 | p-r026 | 出栈序列判断示例 | `EXAMPLE_OF` | 出栈序列计数定理 | 金标无 | correct |  |
| 27 | p-r027 | 队列 | `CONTAINS` | 队尾 | 一致 | correct |  |
| 28 | p-r028 | 队列 | `CONTAINS` | 队头 | 一致 | correct |  |
| 29 | p-r029 | 队列的基本操作 | `CONTAINS` | 入队 | 端点不在金标 | correct |  |
| 30 | p-r030 | 队列的基本操作 | `CONTAINS` | 出队 | 端点不在金标 | correct |  |
| 31 | p-r031 | 队列 | `CONTAINS` | 队列的基本操作 | 端点不在金标 | correct |  |
| 32 | p-r032 | 队列 | `CONTAINS` | 先进先出 | 金标无 | correct |  |
| 33 | p-r033 | 入队 | `RELATED_TO` | 队尾 | 金标无 | correct |  |
| 34 | p-r034 | 出队 | `RELATED_TO` | 队头 | 金标无 | correct |  |
| 35 | p-r035 | 假溢出 | `RELATED_TO` | 循环队列 | 一致 | correct |  |
| 36 | p-r036 | 循环队列 | `CONTAINS` | 循环队列指针后移公式 | 关系类型不同 | correct |  |
| 37 | p-r037 | 循环队列 | `CONTAINS` | 循环队列元素个数计算公式 | 端点不在金标 | correct |  |
| 38 | p-r038 | 循环队列 | `CONTAINS` | 循环队列判空与判满 | 金标无 | correct |  |
| 39 | p-r039 | 循环队列指针变化 | `EXAMPLE_OF` | 循环队列指针后移公式 | 金标无 | correct |  |
| 40 | p-r040 | 循环队列指针变化 | `EXAMPLE_OF` | 循环队列元素个数计算公式 | 端点不在金标 | correct |  |
| 41 | p-r041 | 循环队列指针变化 | `EXAMPLE_OF` | 循环队列判空与判满 | 一致 | correct |  |
| 42 | p-r042 | 链队列 | `CONTAINS` | 链队列入队操作 | 端点不在金标 | correct |  |
| 43 | p-r043 | 链队列 | `CONTAINS` | 链队列出队操作 | 端点不在金标 | correct |  |
| 44 | p-r044 | 链队列 | `CONTAINS` | 链队列的特性 | 端点不在金标 | correct |  |
| 45 | p-r045 | 双端队列 | `RELATED_TO` | 双端队列与栈和队列的关系 | 端点不在金标 | correct |  |
| 46 | p-r046 | 括号匹配算法 | `CONTAINS` | 括号匹配成功的判定条件 | 端点不在金标 | correct |  |
| 47 | p-r047 | 后缀表达式 | `PREREQUISITE` | 后缀表达式求值算法 | 一致 | correct |  |
| 48 | p-r048 | 中缀表达式 | `RELATED_TO` | 后缀表达式 | 金标无 | correct |  |
| 49 | p-r049 | 表达式求值两步法 | `CONTAINS` | 中缀转后缀算法 | 端点不在金标 | correct |  |
| 50 | p-r050 | 表达式求值两步法 | `CONTAINS` | 后缀表达式求值算法 | 端点不在金标 | correct |  |
| 51 | p-r051 | 例3-4 表达式求值 | `EXAMPLE_OF` | 中缀转后缀算法 | 端点不在金标 | correct |  |
| 52 | p-r052 | 例3-4 表达式求值 | `EXAMPLE_OF` | 后缀表达式求值算法 | 端点不在金标 | correct |  |
| 53 | p-r053 | 递归 | `CONTAINS` | 递归工作栈 | 关系类型不同 | incorrect | R2（复核时改判；判定人未勾选编号，依据为复核提示中的关系类型存疑） |
| 54 | p-r054 | 递归 | `CONTAINS` | 递归的局限 | 端点不在金标 | correct |  |
| 55 | p-r055 | 递归 | `CONTAINS` | 递归转非递归 | 关系类型不同 | incorrect | R2（复核时改判；判定人未勾选编号，依据为复核提示中的关系类型存疑） |
| 56 | p-r056 | 递归工作栈 | `RELATED_TO` | 递归的局限 | 端点不在金标 | correct |  |
| 57 | p-r057 | 阶乘的递归计算 | `EXAMPLE_OF` | 递归 | 金标无 | correct |  |
| 58 | p-r058 | 银行排队模拟 | `EXAMPLE_OF` | 先进先出服务次序 | 端点不在金标 | correct |  |
| 59 | p-r059 | 队列的应用场景 | `CONTAINS` | 队列的缓冲作用 | 端点不在金标 | correct |  |
| 60 | p-r060 | 操作受限的线性表 | `CONTAINS` | 栈 | 端点不在金标 | correct |  |
| 61 | p-r061 | 操作受限的线性表 | `CONTAINS` | 队列 | 端点不在金标 | correct |  |
| 62 | p-r062 | 栈 | `CONTAINS` | 栈的典型应用 | 端点不在金标 | correct |  |
| 63 | p-r063 | 队列 | `CONTAINS` | 队列的典型应用 | 端点不在金标 | correct |  |

小计：已判定 63 条，正确 61 条，准确率 96.83%（≥ 70% 达标）。

## 5. 错误类型与改进方向

### 5.1 人工判错

| 条目 | 违反标准 | 说明 |
| --- | --- | --- |
| p-r053 递归 `CONTAINS` 递归工作栈 | R2 | 递归工作栈是系统实现递归的机制，不是「递归」的组成部分，更接近 `RELATED_TO`（金标为 递归工作栈 — 递归 的相关关系） |
| p-r055 递归 `CONTAINS` 递归转非递归 | R2 | 递归转非递归是改写方法，不是「递归」的下位概念，更接近 `RELATED_TO` |

两条都是把「相关」误标为 `CONTAINS`。判定人复核时改判为错，未另写备注；「违反标准」一列依据复核时提示的 R2（关系类型）填写。

### 5.2 金标比对的未命中（按计数从高到低）

| 对象 | 错误类型 | 计数 | 原因分析 | 改进方向 |
| --- | --- | --- | --- | --- |
| 实体 FP | `no_gold_match` | 34 | 模型比金标粒度更细，抽出了小结性、比较性的条目（如「栈与队列的选用依据」「顺序存储与链式存储的比较」），人工判定认为是本章讲过的知识点 | 金标约定只收核心知识点，这部分不算错误；若要压低冗余，在 `extract_entities` 提示词中明确「比较、选用依据、应用场景」是否单独成点 |
| 关系 FP | `unmapped_endpoint` | 33 | 端点是上面那些金标外的实体，关系本身人工判对 | 随实体粒度一起处理；不单独改关系抽取 |
| 关系 FN | `not_predicted` | 18 | 两端都已抽出、但未命中的金标关系共 21 条（含下面 3 条类型不同），其中 12 条的两端证据分属不同小节，而关系按小节抽取，跨小节的边看不到；同小节漏掉的多为「栈 → 入栈」这类，模型改连到了中间节点「栈的基本操作」 | 为跨小节关系增加一轮章节级补抽（E12 编排），小节间共享实体表；提示词中说明基本操作直接挂在所属结构下 |
| 关系 FP | `no_gold_match` | 16 | 端点都能映射，但金标没有这条边（`RELATED_TO` 9、`CONTAINS` 4、`EXAMPLE_OF` 3），人工判定全部为对 | 复核金标是否漏标；提示词中给出「对照/互补」用 `RELATED_TO` 的反例 |
| 关系 FN | `endpoint_not_extracted` | 8 | 缺的端点有两类：一是名称写法不同、自动比对没对上（模型的「例3-4 表达式求值」「括号匹配实例」「循环队列元素个数计算公式」对应金标「表达式求值示例」「括号匹配示例」「循环队列元素个数公式」），二是只作背景出现的概念没抽出（「线性表」「取模运算」「运算符优先级」；模型抽的是「操作受限的线性表」） | 前者靠完整融合的别名归并；后者开启 E06 补漏，或在提示词中要求抽出先修表述里点名的概念 |
| 实体 FN | `not_extracted` | 6 | 金标实体未抽出 | 开启 E06 补漏（本次未开）后对比召回 |
| 关系 FP/FN | `wrong_relation_type` | 3 | 端点对上但类型不同，含 p-r053、p-r055 以及 循环队列 → 循环队列指针后移公式 | 在关系提示词中写清 `CONTAINS` 只用于「组成部分、基本操作、实现方式」，机制、方法论用 `RELATED_TO` |
| 实体 FP/FN | `type_mismatch` | 2 | 「后进先出」标为 theorem（金标 concept）；「卡特兰数」标为 concept 而金标只有「卡特兰数公式」 | 两者人工判定都可接受（README 3.1 两可情形）；提示词中补充「特性」归 concept 的示例 |
| 实体 FP | `duplicate` | 1 | 「卡特兰数」与「卡特兰数公式」都映射到金标「卡特兰数公式」 | 完整融合（E08～E10）接入后应合并或建 `CONTAINS` |

**小节失败。** 「第3章 栈与队列 > 3.3 队列 > 3.3.5 栈与队列的比较」的关系抽取两次都因输出截断（`truncated`，上限 4096 token）失败；该小节 8 个实体照常保留，关系缺失。改进方向：对实体多的小节拆批抽取，或提高关系抽取的输出上限（需在 D-02d 预算内评估）。

**先修关系召回低。** `PREREQUISITE` 金标 7 条只命中 1 条（精确率 1.0，召回 0.14）。原因与 K01 预设的边界用例一致：E11 只保留命中 `PREREQUISITE_CUES` 的前置边，「基于」等表述不在清单中。是否扩充清单仍是待决项（`docs/tasks.md`）。

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

## 本机运行步骤

开发云环境的网络策略拦截 `api.deepseek.com`，真实模型抽取须在能直连供应商的本机运行（ADR-027、ADR-028）。脚本 `evaluation/run_live_extraction.py` 用生产同一批服务完成解析、分块（D03/D08/D09）、实体抽取（E05）与关系抽取（E11），调用经 E04 策略（重试、熔断、预算）发出，输出 predictions.json 交第 3 节的 `sample`、`score` 计分。脚本测试见 `tests/backend/test_k02_run.py`（只用 fake 客户端，不联网）。

> **初步数字，不是最终判定。** 真实融合（E08～E10，由 E12 编排）尚不可用，脚本只做简化融合：按 E08 `normalize_name` 主键去重，保留首次出现的名称与类型，别名、包含、向量候选和模型裁决都不做。因此实体数和准确率只是初步参考。验收 7 的最终判定须经 E12 完整流程把本章处理到 `awaiting_review` 后导出草稿。predictions.json 的 `fusion.mode` 为 `simplified`，写入报告时须注明。

1. **安装后端**（在仓库根目录，Python 3.11+）：

   ```bash
   python3 -m venv .venv && . .venv/bin/activate
   pip install -e './src/backend'
   ```

2. **设置环境变量**（只在当前终端设置，不写入任何文件；密钥不要提交或粘贴到聊天里）：

   ```bash
   export LLM_MODE=live
   export LLM_BASE_URL=https://api.deepseek.com
   export LLM_EXTRACTION_MODEL=deepseek-flash
   export LLM_CHAT_MODEL=deepseek-flash          # 启动校验要求 live 模式同时设置
   read -rs LLM_API_KEY && export LLM_API_KEY    # 交互输入，不留在 shell 历史
   export LLM_TASK_TOKEN_BUDGET=500000           # ADR-028 签收值
   export LLM_DAILY_TOKEN_BUDGET=5000000
   # 可选：LLM_REQUEST_TIMEOUT_SECONDS（默认 60）、LLM_MAX_RETRIES（默认 2）
   ```

   `LLM_API_KEY` 为空时脚本拒绝运行（退出码 2）。若日志出现 `error_class=connection` 而 `curl` 能连上，多半是本机 Python 缺根证书（`CERTIFICATE_VERIFY_FAILED`）：`pip install certifi && export SSL_CERT_FILE="$(python3 -m certifi)"`；有 HTTPS 流量检查的网络改用 `security find-certificate -a -p /System/Library/Keychains/SystemRootCertificates.keychain /Library/Keychains/System.keychain > ~/macos-ca.pem` 并把 `SSL_CERT_FILE` 指向它。连续 5 次连接失败后熔断器会拒绝后续调用，修好后重跑即可。E03 适配器直连供应商，不走 HTTP 代理。脚本的调用记录只在进程内存中计量，日预算只统计本次运行。

3. **运行抽取**：

   ```bash
   RUN=~/smartsketch-k02/$(date +%Y%m%d-%H%M%S) && mkdir -p "$RUN"
   python3 evaluation/run_live_extraction.py \
     --gold evaluation/fixtures/synthetic.json \
     --out "$RUN/predictions.json" --run-log "$RUN/run.json"
   ```

   - 缺省不开 E06 补漏，与生产缺省一致；`--glean-rounds 1` 可开启一轮，开启后须在报告中注明。
   - 关系按完整章节路径分组抽取；`--section-depth 2` 可改为按「章 > 节」分组。
   - 单块或单节失败会记入运行日志，然后继续处理。预算被拒时立即停止（退出码 3），不写 predictions.json。鉴权失败也会停止（退出码 4）。
   - 输出目录放在仓库外（仓库没有忽略运行产物）。predictions.json 含资料原文证据，不要提交。

4. **抽样与计分**：脚本结束时会打印这两条命令。

   ```bash
   python3 evaluation/evaluate_extraction.py sample \
     --predictions "$RUN/predictions.json" --seed 20260926 --size 100 > "$RUN/sample.json"
   python3 evaluation/evaluate_extraction.py score --gold evaluation/fixtures/synthetic.json \
     --predictions "$RUN/predictions.json" --out "$RUN/report.json"
   # 人工判定填好 "$RUN/judgments.json" 后，加 --judgments 重跑 score
   ```

5. **记录**：在第 3 节表格中填写以下信息：
   - 运行日期；
   - `run_id`；
   - 请求的模型 ID（`deepseek-flash`）和响应中实际返回的模型名。后者见 predictions.json 的 `model.responded` 或 run.json 的 `model_calls.responded_models`。`deepseek-flash` 会随供应商更新指向新版本，所以两项都要记；
   - 提示词版本（`prompt_versions`，run.json 另有 `prompt_sha256`）；
   - run.json 的 `chunk_count`、`chunk_failures`、`section_failures` 和 `dropped`；
   - `model_calls` 的调用次数与 token 用量，以及响应是否带 usage（`calls_without_usage`）。usage 的实测结果同时补到 `docs/integrations.md` D-02a 行（由协调方更新）；
   - 注明「简化融合，初步数字」。
