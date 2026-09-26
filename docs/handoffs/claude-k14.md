# Claude 交接：K14 整理提示词工程完整记录

- task_id: K14（GitHub issue #167）
- review_status: ready_for_review
- 分支：`claude/k14-prompt-record`；base：认领提交 `bdcf165`（父提交 main@`d624208`）
- 状态：DONE（待 PR 审查/合并）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `docs/submission/prompt-engineering.md` | 新增。提示词总览、E01 共同机制与防注入措施、3 个在用提示词（草稿）的逐项记录、4 个占位与 1 个未建用途、评测证据汇总、已知缺口 |
| `docs/handoffs/claude-k14.md` | 本文件 |
| `docs/tasks.md` | 只改第八批 K14 行的状态与证据列 |

未改提示词、代码、MANIFEST 或其他文档。

## 覆盖范围

- **在用（服务层已固定版本取用，均为「草稿」）**：`extract_entities` v2（E05 `EntityExtractor`）、`extract_entities_gleaning` v2（E06 `EntityGleaner`）、`rewrite_query` v2（J03 `QueryRewriter`）。每条记录版本与摘要、前一版本摘要、用途、调用方与版本常量、输入变量、调用参数、输出格式与校验、防注入措施、修改依据（提交/PR/交接）、评测证据。
- **占位（无业务调用方）**：`extract_relations`、`judge_duplicate`、`summarize_definition`、`answer_with_context`，均为 E01 v1，如实标为「不代表提示词效果」。
- **未建**：`gen_study_material`（待 O01）。
- 注明三个在用服务尚未接入 E12 编排或 J07 装配，只在 fake 测试中被调用。

## 核对方法与结果

1. **版本、摘要、变量、状态、调用方版本常量**：脚本（会话 scratchpad 中的 `check.py`，未提交）用 `PromptLibrary` 装载 `prompts/` 下 7 个文件，逐一核对「MANIFEST 行的版本与摘要 = 装载器计算值」「摘要与全部变量名出现在文档中」「三个调用方的 `*_PROMPT_VERSION` 常量 = 文件版本」，并检查文档中不含密钥形态文本。结果：7 个文件全部一致，3 个调用方常量均为 2，与文件一致；输出 `ALL OK`，无密钥形态文本。
2. **前一版本摘要**：从 `d07afc2` 取出 v1 文件放入临时目录用装载器计算，`extract_entities` `917967d5…`、`extract_entities_gleaning` `7d07e241…`、`rewrite_query` `8ccf7c23…`，与 `git show d07afc2:prompts/MANIFEST.md` 一致。
3. **调用方完整性**：`grep -rn PromptLibrary src/ --include='*.py'` 只命中 `prompts.py`（装载器本身）、`entities.py`、`gleaning.py`、`qa/rewrite.py`。`grep` 这三个服务类名，`src/` 中除自身与 `qa/__init__.py` 导出外无引用。
4. **提交与 PR**：`git log --follow -- prompts/<用途>.yaml` 得到 `d07afc2`（E01）、`caa74e9`（E05）、`1b383c1`（E06）、`b5bcdee`（J03）；PR 号取自合并提交：#182 `dc20326`、#236 `d5bda28`、#245 `59b2e5a`、#242 `8985a16`。`4370295`（J03 绑定 E04 截止时间）经 `git log --merges --ancestry-path` 确认随 #242 合入，而不是 #243。`git diff --stat d624208 bdcf165 -- prompts src` 为空，基线内提示词无变化。
5. **评测证据复跑**：`PYTHONPATH=$PWD/src/backend PYTHONPYCACHEPREFIX=<scratchpad>/pyc-k14 <主仓库 .venv, Python 3.11.9>/bin/python -m pytest tests/backend/test_{e01,e05,e06,j03}.py -q -p no:cacheprovider`：合计 **288 passed**；单独运行 e01 69、e05 63、e06 61、j03 95 passed。j03 比 J03 交接的 94 多 1 条，为 TD-01 跟进新增的 `test_policy_retries_stop_before_the_reserved_time`（交接「TD-01 跟进」节已记）。
6. **真实评测**：`evaluation/` 目录在基线中不存在；`docs/atomic-tasks.json` 中 K02、K03、K13 状态为 `PROPOSED`。文档明确写「尚无真实模型评测」，未给任何效果指标。
7. **其他引用**：`docs/integrations.md` 第 229、242 行，`specs/grounded-qa.md` 第 25、355 行，ADR-015 决定 2、3、6 与修订 1 决定 9，各交接的决定编号与待决编号，均已对照原文核对行号或编号。

## 验证

| 命令 | 结果 |
| --- | --- |
| 上面第 5 项 pytest | 288 passed |
| `python3 check.py`（第 1 项） | `ALL OK` |
| `git diff --check` | 通过 |
| `./scripts/verify.sh` | 见 PR 描述与下方记录 |

## 未覆盖项

- 没有真实模型输出样例、效果指标或成本数据（依赖 K02、K03、K13 与 D-02a/b 模型签收）。
- 未记录模型 ID 与温度：提示词文件不含这些字段，模型由调用方构造参数给定，D-02a/b 尚未签收。
- 未导入分支上的 `prompts/README.md`（E01 交接「需协调方处理」第 1 条）；本文以现行装载器格式为准。

## 待决（需协调方）

1. 提示词从「草稿」改「在用」须等 K02/K03 评测；届时本文第 3、5 节需补评测结果与版本。
2. 文档第 6 节列出的各交接待决（修复模板、字段长度上限、补漏开关、J03 暂定参数、输入侧注入检测、单版本布局、fake 默认输出、分支 README）仍未决定，K14 只做引用。
3. 后续 E10/E11/J05 替换占位提示词后，需更新本文第 1、3、4 节（建议由各任务在升版本的同一 PR 中同步，或由 K16 定稿前统一更新）。

## 回滚

只新增两个文档并改 `docs/tasks.md` 一行：`git revert <提交>` 即可。无代码、数据或依赖变更。
