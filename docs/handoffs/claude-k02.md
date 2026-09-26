# Claude 交接：K02 实现抽取和融合离线评测

- task_id: K02
- review_status: ready_for_review
- 分支：`worktree-agent-abf836328c15db676`（基线 `claude/project-thread-sp1d3a`，基线提交 `cc53c8d`）
- 状态：脚本与测试完成；**真实模型判定未实测**（D-01、D-02 未签收，付费调用须另行确认）
- 并行关系：K01（`evaluation/README.md`、`evaluation/fixtures/`）由另一 Agent 同时编写，本任务未触碰；`docs/tasks.md` 由协调方更新。

## 交付物

| 文件 | 内容 |
| --- | --- |
| `evaluation/evaluate_extraction.py` | 新增。只用标准库，含 `score` 和 `sample` 两个子命令。对外函数：`normalize_name`、`score`、`sample`、`dumps`、`main`、`EvaluationInputError` |
| `tests/backend/test_k02.py` | 新增。46 条用例加 1 条可选用例：有 K01 夹具时加载，缺失时 `pytest.skip`。夹具全部内联，按文件路径导入被测模块 |
| `evaluation/reports/extraction-accuracy.md` | 新增。「知识抽取准确率的测试报告」骨架，写明「未实测」及原因，并附复现命令、逐条判定表模板、错误类型与改进方向，以及假模型管线自检（明确标注不是判定） |
| `docs/handoffs/claude-k02.md` | 本文件 |

## 关键决定（实现口径）

1. **实体配对**：名称归一化为 NFKC、casefold、去全部空白，与金标名或别名相同即命中。
   - 按预测输入顺序一对一配对。同名有多个空闲金标时优先类型一致的，其余按金标顺序。
   - 有类型口径**沿用名称级的同一组配对**，类型也相同才算 TP。类型错的先到者同样占用金标，后到的同名预测记为 `duplicate`（测试 `test_one_to_one_follows_input_order`）。
2. **关系端点映射**：只有名称级配对成功的预测实体才映射。被判为重复的预测实体不映射，挂在它上面的关系记为 `unmapped_endpoint`。融合应在抽取评测之前去重，所以这样更严格。
3. **错误原因的优先级**：
   - 关系 FP：`unmapped_endpoint` > `duplicate` > `reversed_direction`（仅有向类型）> `wrong_relation_type`（端点无序相同，类型不同）> `no_gold_match`。
   - 关系 FN：`endpoint_not_extracted` > `reversed_direction` > `wrong_relation_type` > `not_predicted`。
   - 所有原因键始终输出，计数可为 0。
4. **分组计数归属**：TP 与 FN 计入金标类型，FP 计入预测类型。
5. **F1 计算**：F1 = 2tp/(2tp+fp+fn)，分母为 0 时为 `null`。precision 为 `null`（没有预测）但存在 FN 时，F1 为 0.0。
6. **硬指标**：
   - `entity_count` 只数 `source == "ai"` 的实体。
   - 准确率用 `Fraction` 与 7/10 比较。未通过的项给出 `gap`：实体数为差几个，准确率为与 0.70 的差。
   - `model.is_fake` 优先级最高，此时结论为「不可用于判定（假模型）」，`passed: null`。
   - 实体或关系任一侧没有判定（包括判定对象为空）时，结论为「未判定」，`passed: null`，即使实体数已不达标也是如此（按领队口径）。
7. **抽样**：实体、关系分别用独立的 `random.Random(seed)`，总体只取 `source == "ai"` 的条目，先按 id 排序。输出按 id 排序，并附 `judgments_template`：值为 `null`，必须填成 `correct` 或 `incorrect` 才能通过 `score` 校验。
8. **输入校验**（退出码 2，stderr 以 `evaluate_extraction: 错误：` 开头，stdout 为空）：
   - 未知实体或关系类型；实体、关系 ID 重复；悬空端点。
   - `dataset_id` 不一致；`judgments.run_id` 与 predictions 不一致。
   - 判定 ID 不存在，或判定值不合法。
   - 文件不可读，或不是合法 JSON。
9. **输出扩展**：K02 输出比领队给的格式多两项：`details`（逐条结果）与 `counts`，供报告第 4、5 节使用。输入格式完全按 K01 约定，未扩展。

## 先红后绿证据

1. 先写 `tests/backend/test_k02.py`，此时 `evaluation/evaluate_extraction.py` 不存在，收集阶段报 `FileNotFoundError`（1 error）。
2. 放入只含同名函数、全部 `raise NotImplementedError` 的桩，得到 **46 failed, 1 skipped**。
3. 实现后得到 **46 passed, 1 skipped**。跳过的是 K01 夹具可选用例，因为 `evaluation/fixtures/synthetic.json` 在本基线中不存在。

## 实际命令与结果

venv 为会话 scratchpad 中的 `venv/`，下文记作 `$VENV`。

| 命令 | 结果 |
| --- | --- |
| `$VENV/bin/python -m pytest tests/backend/test_k02.py -q -p no:cacheprovider`（桩） | 46 failed, 1 skipped |
| 同上（实现后） | 46 passed, 1 skipped |
| `git diff --check` | 无输出，通过 |
| `python3 evaluation/evaluate_extraction.py score ...`（自检，见报告第 6 节） | exit 0；`--out` 与标准输出两次运行的 sha256 相同：`13ee80cb…4d91c87` |
| `python3 evaluation/evaluate_extraction.py sample --predictions ...` | exit 0；7 个实体，`mode: "full"` |
| `PATH=$VENV/bin:/usr/bin:/bin ./scripts/verify.sh` | **FAIL contracts gate**，原因是环境缺工具，与本任务无关，详见下方说明 |

`verify.sh` 的必需文件检查与 hooks 检查都通过，B12、B13 契约回归通过。B14 的两条用例与门禁负向用例失败，原因是本容器没有 `openapi-typescript`：`scripts/gen-contracts.sh` 报「缺少生成器 openapi-typescript」，主仓库也没有 `node_modules`。本任务没有改动 `src/contracts/`、`scripts/` 或任何生成物。需要在装有 `openapi-typescript@7.4.4` 的环境重跑确认。

**自检输入的构造方法**：scratchpad 中的 `k02/make.py` 未入仓库，它写出 3 个文件：

- 金标：7 个实体、5 条关系，章节为「栈与队列」。
- 预测：`is_fake: true`，含别名、全角、空格、类型错、重复、多余实体，以及反向、错类型、未映射端点三种关系错误。
- 判定：由脚本写出，不是人工判定。

报告第 6 节已列出全部指标，想复现可按该节描述手写同样的数据。

## 接口 / 数据 / 配置变更

无 API、DTO、数据库或配置变更。新增的顶层目录 `evaluation/` 与 K01 共用。报告 JSON 的结构见脚本 `score()` 的返回值（`schema_version: 1`）。

## 风险

- **K01 格式同步**：本脚本按领队转述的 K01 格式实现。K01 合入后，若 `evaluation/README.md` 的字段或判定口径不同（例如判定值不只 `correct`/`incorrect`，或抽样对象包含非 AI 条目），需要同步修改脚本与测试。合入后应运行可选用例 `test_k01_synthetic_fixture_validates_if_present`：它用金标自身构造假预测，检查 fn 为 0。若金标内同名条目重复，该用例可能失败，需要看夹具。
- **金标命名冲突**：金标中两个实体归一化后同名或同别名时，按金标顺序先后配对，不报错。
- **融合评测**：「融合」只间接体现在 `duplicate` 计数与 AI 实体数上。E08 到 E10 的候选对与同义裁决没有单独的评测指标（例如合并对的精确率）。这部分没有纳入 K02 验收，如需要应拆子任务。

## 未决 / 待协调方处理

1. D-01（基准章节）、D-02（模型供应方）签收，以及付费调用确认，之后才能按报告第 3 节执行真实判定并填写第 2、4、5 节。
2. `docs/tasks.md` 中 K02 的状态与证据由协调方更新；本任务按要求未改。
3. `verify.sh` 的 B14 契约门禁需要在装有 `openapi-typescript` 的环境复跑。
4. 「无判定但实体数已不达标」时结论写「未判定」还是「未达标」：目前按领队口径写「未判定」，`entity_count.passed` 单独显示为 false。如需改为「未达标」，请协调方决定。

## 下一步（下一位 Agent 的首个动作）

K01 合入后，运行 `python -m pytest tests/backend/test_k02.py -q`，确认可选用例不再跳过且通过，并对照 `evaluation/README.md` 核对第「关键决定」节各条是否一致。

## 回滚

只新增 4 个文件，没有修改已有文件：`git revert <本提交>` 即可。无迁移、依赖或数据变更。
