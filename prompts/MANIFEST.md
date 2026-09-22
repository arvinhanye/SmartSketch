# 提示词索引

一行一个提示词。新增时在表末**加一行**并新建 `prompts/<id>.yaml`（见 [`README.md`](README.md)）。

下表 8 项来自参考方案 **表 6.8 提示词清单**（S2 §6.7），`id` 与用途照录，命名沿用方案的下划线风格。

| # | id | 用途 | 关键设计 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | `extract_entities` | 块级知识点抽取 | 角色设定、类型定义、示例、JSON 格式；「只抽课程知识，忽略人名页码」 | TODO |
| 2 | `extract_entities_gleaning` | 补漏抽取 | 只输出上一轮遗漏或错误的内容 | TODO |
| 3 | `extract_relations` | 小节级关系抽取 | 传入实体表；四类关系判定准则与反例；端点必须来自实体表；输出证据与置信度 | TODO |
| 4 | `judge_duplicate` | 同义知识点裁决 | 输入两个知识点的名称与定义，输出是否相同及理由 | TODO |
| 5 | `summarize_definition` | 多段定义合并 | 基于原文合并为一段统一定义 | TODO |
| 6 | `rewrite_query` | 问题改写 | 结合历史对话补全指代，提取关键术语 | TODO |
| 7 | `answer_with_context` | 问答生成 | 只依据资料、强制引用编号、不足时明确告知（对应 ADR-003 的 `NOT_COVERED`） | TODO |
| 8 | `gen_study_material` | 讲解与练习题 | 基于原文、匹配难度、附答案解析 | TODO |

## 与仓库现状的两处出入

1. **`answer_with_context` 一个提示词同时承担「作答」与「资料不足时明确告知」**，方案没有把覆盖度判定拆成独立提示词。ADR-003 要求「要么带来源、要么返回 `NOT_COVERED`」，因此该判定必须写进这一个提示词的输出约定，而不是另起一个。
2. ~~`gen_study_material` 在 MVP 范围里没有对应能力~~ — **已决议**：[ADR-007](../docs/decisions/ADR-007-study-material-bonus-scope.md) 把学习材料生成纳入范围并定位为加分项，对应任务 M1-07。生成内容受 ADR-003 约束，必须基于原文并给出来源，不得凭模型常识编练习题。

## 状态含义

`TODO` 未开始 → `DRAFT` 有正文但未过评测 → `ACTIVE` 已上评测且在用 → `DEPRECATED` 停用但保留历史。

进入 `ACTIVE` 前必须在 `datasets/` 的标注集上跑过 `evaluation/` 的对应评测，并在 YAML 的 `changelog` 里留下版本—改动—效果记录。
