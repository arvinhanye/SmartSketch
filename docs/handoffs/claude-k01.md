# Claude 交接：K01 建立自编标注集及评测口径

- task_id: K01
- review_status: ready_for_review
- 分支：`worktree-agent-a8d2475865592e1f8`（子代理工作树，未推送），基线 `claude/project-thread-sp1d3a@754ff23`（含 E11）
- 负责人：ArvinHan（Claude 子代理，由协调会话分派，与 K02 并行）
- 日期：2026-09-26
- 状态：口径与开发集完成；**最终基准材料待 D-01、真实模型评测待 D-02、问答标注待 J06**

## 改动文件

| 文件 | 说明 |
| --- | --- |
| `evaluation/README.md` | 新增。评测口径唯一来源：标注集格式、类型/方向定义、标注约定、预测与判定文件格式、实体/关系匹配、P/R/F1 与空分母、赛题两项硬指标、抽样方法、判定标准（E1～E5、R1～R6）、判定对象与材料隔离、失败路径、问答指标（待 J06） |
| `evaluation/fixtures/synthetic.json` | 新增。自编开发集：数据结构第 3 章「栈与队列」全文（Markdown，3141 个汉字）+ 金标 45 个实体、40 条关系 |
| `docs/handoffs/claude-k01.md` | 本文件 |

未改 `docs/tasks.md`（由协调会话更新），未碰 K02 的 `evaluate_extraction.py`、`tests/backend/test_k02.py`、`evaluation/reports/`。

## 数据集概况

`dataset_id = synthetic-ds-ch3`，`is_final_benchmark = false`，`note` 写明最终材料由 D-01 决定。正文为自编原创：定义、基本操作、顺序栈/链栈、出栈序列性质与计数定理、卡特兰数公式、循环队列（假溢出、指针后移与元素个数公式、判空判满性质）、链队列、双端队列、栈与队列比较、括号匹配、中缀转后缀、后缀求值、递归工作栈、6 道例题。

| 实体类型 | 数量 | 关系类型 | 数量 |
| --- | --- | --- | --- |
| concept | 25 | CONTAINS | 12 |
| method | 8 | PREREQUISITE | 7 |
| example | 6 | EXAMPLE_OF | 8 |
| theorem | 3 | RELATED_TO | 13 |
| formula | 3 | | |
| **合计** | **45** | **合计** | **40** |

边界用例：7 条 `PREREQUISITE` 中 6 条证据命中 E11 `PREREQUISITE_CUES`（需要先、先掌握、先理解、前提、基础），`g-r03`（栈 → 括号匹配算法，证据「基于栈的后进先出特性」）**不命中**，E11 会以 `prerequisite_without_cue` 丢弃，用来观测清单造成的召回损失；例 3-2、例 3-4 各有两条 `EXAMPLE_OF`；`RELATED_TO` 13 条无向边。

## 关键决定

1. **口径细节**（任务说明未写明、由本任务确定，K02 须一致）：
   - 关系端点映射只用**名称级**一对一匹配成功的预测实体；重复与多余假阳性实体不映射，其关系计为假阳性（README 5.1 第 5 条）。
   - 所有指标只统计 `source = "ai"` 的条目，其他来源只报数量（README 第 4 节）。
   - 实体按类型分组只在带类型变体上做；`precision` 与 `recall` 均为 0 时 `F1 = 0`，任一为 `null` 时 `F1 = null`。
   - 准确率达标用整数比较 `correct × 10 ≥ 7 × n`；实体与关系各自新建 `Random(seed)`；样本缺判定写「判定不完整」。
   - 关系一对一：同一金标关系重复命中计重复假阳性；方向相反的有向关系判错。
2. **金标只收被讲解的知识点**，顺带提到的术语（单链表、广度优先遍历、作业调度、组合数）不收；因此自动指标是开发信号，硬指标以人工判定为准（README 3.3 第 1 条、E1）。
3. **判定标准 R5 允许上下文指代**（「该算法」、例题正文），因为金标自身有若干条这样的证据（如 `g-r05`「该算法需要先理解运算符优先级」、例题内的 `EXAMPLE_OF` 证据）；否则金标会违反自己的判定标准。
4. 金标之外追加一个可选字段 `note`（人读说明，脚本不解析），其余字段严格按协调会话给定格式。

## 验证（实际结果）

构建与自检脚本放在会话 scratchpad（`k01/build.py`、`k01/check.py`、`k01/tamper.py`），不进仓库。

| 命令 | 结果 |
| --- | --- |
| `python3 k01/build.py evaluation/fixtures/synthetic.json` | 生成 45 实体、40 关系 |
| `python3 k01/check.py evaluation/fixtures/synthetic.json` | **ALL PASS**：JSON 可解析；ID 唯一且格式为 `g-eNN`/`g-rNN`；端点存在、无自环、无重复边（`RELATED_TO` 按无向）；85 条证据均为原文子串；实体 ≥ 30 覆盖五类、关系 ≥ 25 覆盖四类；名称/别名归一化后不跨实体冲突；`PREREQUISITE` 无环；汉字数 3141（3000～5000） |
| `python3 k01/tamper.py …`（4 个篡改副本：证据加字、端点悬空、ID 重复、删光 `EXAMPLE_OF`） | 4 个均 exit 1 |
| 同脚本对金标 `PREREQUISITE` 证据跑 E11 `PREREQUISITE_CUES`（NFKC + casefold） | 6 条命中，`g-r03` 不命中（预期） |
| `./scripts/verify.sh`（scratchpad venv 装 `src/contracts/toolchain.txt` 所列版本 + npm `openapi-typescript@7.4.4`，经 `env PATH=…` 运行） | exit 0，`PASS contracts gate`、`Scaffold verification passed.`（系统 Python 缺工具时 exit 1，属环境问题） |
| `git add -N evaluation && git diff --check` | exit 0 |

复现自检的最小命令（不依赖 scratchpad 脚本）：

```bash
python3 -c "import json;d=json.load(open('evaluation/fixtures/synthetic.json'));t={x['id']:x['text'] for x in d['documents']};g=d['gold'];assert all(x['evidence'] in t[x['document_id']] for x in g['entities']+g['relations']);print(len(g['entities']),len(g['relations']))"
```

## 接口 / 数据变更

无代码、契约、数据库或 Neo4j 变化。新增 `evaluation/` 目录与两份文件；预测/判定文件格式定义于 README 第 4 节，由 K02 读取。

## 风险

- 开发集由同一作者编写正文与金标，可能偏向「标准写法」，对真实教材的泛化有限；最终数值只能来自 D-01 材料。
- 若 K02 并行实现时对第 1 条关键决定中的细节取了不同解释，两边须以 README 为准对齐（尤其端点映射与 `source` 过滤）。
- 本开发集今后用于提示词迭代；若 D-01 最终选的也是本章，报告必须注明「迭代材料与判定材料相同」（README 6.4）。
- `g-r03` 反映 E11 先修表述清单缺「基于」；是否加入属 E11 待决 1，本任务不改代码。

## 待决

1. **D-01**：最终基准课程与章节（产品负责人）。签收后另建 `fixtures/<dataset>.json`，不改本开发集。
2. **D-02**：模型供应商与预算；真实模型运行前另取付费确认。
3. **J06**：问答链路完成后补问答标注（问题、覆盖真值、期望引用），指标口径已在 README 第 8 节。
4. E11 `PREREQUISITE_CUES` 是否加入「基于」等表述（E11 待决 1）。

## 下一步

- **K02**：按 README 第 5～6 节实现 `evaluate_extraction.py`，用本集金标做 fake 联调；首个动作是核对第 1 条关键决定的五个细节与脚本一致。
- **协调会话**：在 `docs/tasks.md` 登记 K01 状态与证据，标注 D-01、J06 仍开放。

## 回滚

`git revert <本提交>`：删除 `evaluation/README.md`、`evaluation/fixtures/synthetic.json` 与本交接文件。无数据迁移、无依赖变更。

## 后续：D-01 已定（2026-09-26）

ArvinHan 决定直接用本章作最终判定材料（ADR-026）。`synthetic.json` 的 `is_final_benchmark` 改为 `true`、`note` 同步；README 第 1 节与第 6 节、报告、`specs/course-knowledge-graph.md` 验收 7 随之更新。上文「签收后另建 `fixtures/<dataset>.json`，不改本开发集」不再适用。
