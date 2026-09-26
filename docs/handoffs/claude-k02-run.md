# Claude 交接：K02 本机真实模型抽取脚本

- task_id: K02（真实模型运行准备）
- review_status: ready_for_review
- 分支：`claude/project-thread-sp1d3a`，基线 `ba5c7d0`
- 状态：脚本与测试完成，fake 模式端到端跑通。**真实模型尚未调用**：开发云环境的网络策略拦截 `api.deepseek.com`，须由用户在本机运行（ADR-027、ADR-028）。
- 未改动：`docs/tasks.md`、`docs/decisions.md`（由协调方更新）。

## 交付物

| 文件 | 内容 |
| --- | --- |
| `evaluation/run_live_extraction.py` | 新增。`--gold G --out P [--run-log L]`。流程：取 `documents[0].text` → D03 `parse_markdown` → D08 `chunk_blocks` → D09 `assign_chunk_identities` → 逐块 E05 `EntityExtractor`（可选 E06）→ 简化融合 → 按章节路径分组调 E11 `RelationExtractor` → 写 predictions.json 与运行日志，打印 `sample`/`score` 命令 |
| `tests/backend/test_k02_run.py` | 新增。13 条用例，只用 E02 fake 或脚本化客户端，不联网 |
| `evaluation/reports/extraction-accuracy.md` | 追加「本机运行步骤」一节：环境变量、安装、运行、抽样与计分命令，并说明结果来自简化融合，只是初步数字；要求记录日期和响应模型名 |

## 关键决定

1. **客户端**：`LLM_MODE=live` 用 E03 `CompatibleModelClient.from_settings`，配置了备用四项时同时建备用；`LLM_MODE=fake` 用 E02 `FakeModelClient` 加脚本内的确定性应答 `fake_responder`。两种模式都外包 E04 `ModelCallPolicy.from_settings`，重试、熔断、预算取环境变量。每块用 `CallAttribution(task_id=run_id, chunk_id=…)` 绑定，任务预算按整次运行计。
2. **`is_fake`**：只有主客户端是 `CompatibleModelClient` 时才为假。测试在 live 配置下注入 fake 客户端时，输出仍标为 `is_fake: true`。
3. **密钥**：先于 `load_settings` 检查 live 模式的 `LLM_API_KEY`，为空即退出码 2。报错只写变量名。`Runtime.__repr__` 不含客户端，输出和日志不写密钥（有测试覆盖）。
4. **调用记录**：`MemoryCallStore` 实现 E04 `CallStore`，预算判定（`used >= limit`）和计费规则与 `SqliteCallStore` 相同（ADR-011 修订 3）。不读写应用 SQLite，因此**日预算只统计本次运行**，运行日志中注明了这一点。
5. **简化融合**：按 E08 `normalize_name(...).key` 去重，保留首次出现的名称、类型、定义和证据。类型冲突只计数（`type_conflicts_kept_first`）。predictions.json 带 `fusion.mode = "simplified"` 和说明（README 格式允许额外字段，`validate_predictions` 通过）。
6. **关系分组**：缺省按块的完整 `section_titles` 分组。基准章每个小节正好一块，所以是 16 组。`--section-depth N` 可按前 N 级分组。跨组按（from, to, type）去重，`RELATED_TO` 无向；重复计入 `dropped.relations.cross_section_duplicate`。前置边做一次 `find_cycle`，结果只记在 `prerequisite_cycle`，不删边。
7. **停止条件**：以下三种情况立即停止，只写运行日志，不写 predictions.json：
   - `BudgetExceededError`：退出码 3；
   - `CallRecordError`：退出码 4；
   - `ModelAuthError`：退出码 4。

   其余 `ModelError`，以及修复后仍不合规的输出，都按块或按节记录后继续。
8. **输出上限**：实体与关系调用各声明 4096 token（规格未给值，本脚本暂定），可用 `--entity-max-output-tokens`、`--relation-max-output-tokens` 调整。
9. **E06 补漏**：已接上，但缺省关闭（`--glean-rounds 0`），与生产缺省 `enabled=False` 一致。开启后，预算拒绝同样会停止运行；补漏失败时保留首轮实体，并记为 `stage: gleaning`。

## 验证（venv：scratchpad/venv，在 `src/backend` 下运行）

| 命令 | 结果 |
| --- | --- |
| 先写测试：`python -m pytest ../../tests/backend/test_k02_run.py -q` | 红：12 errors（脚本不存在） |
| 实现后同上（加上后补的 gleaning 用例） | 绿：13 passed |
| `python -m pytest ../../tests/backend/test_k02_run.py ../../tests/backend/test_k02.py -q` | 65 passed |
| `LLM_MODE=fake python evaluation/run_live_extraction.py --gold evaluation/fixtures/synthetic.json --out <s>/predictions.json --run-log <s>/run.json` | exit 0。16 块、0 失败块；16 组、0 失败组；实体 18（合并 9）、关系 12（全为 RELATED_TO）；28 次调用（实体 16、关系 12） |
| `python evaluation/evaluate_extraction.py score --gold … --predictions <s>/predictions.json` | exit 0，结论「不可用于判定（假模型）」 |
| `git diff --check` | 无输出 |
| `PATH=<venv>/bin:$PATH ./scripts/verify.sh` | FAIL：B14 生成与漂移回归缺生成器 `openapi-typescript`。改动暂存后在基线上重跑，同样失败，与本任务无关；B13 通过 |

fake 结果只验证流程，不能证明达标。

## 接口、数据与配置变更

无。没有改动 API、数据模型、环境变量或依赖。脚本只读取已登记的 `LLM_*` 变量。

## 风险与待决

- 真实运行的数字来自简化融合，只能作初步参考。验收 7 的最终判定仍须经 E12 完整流程处理到 `awaiting_review`。
- E03 `StdlibTransport` 不走 HTTP 代理，本机必须能直连 `api.deepseek.com`。
- 4096 的输出上限是暂定值；块或节较大时可能出现 `truncated`，会记录在运行日志的 `chunk_failures`/`section_failures` 中。
- 日预算看不到当天其他进程的用量（内存计量）。

## 下一步（首个动作）

用户在本机按报告「本机运行步骤」执行，把 run.json 的日期、响应模型名、usage 情况与计分结果回填到报告第 2、3 节。usage 实测结果另由协调方补到 `docs/integrations.md` D-02a 行。
