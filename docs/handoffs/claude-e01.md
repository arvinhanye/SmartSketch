# Claude 交接：E01 建立版本化提示词装载器

- task_id: E01（GitHub issue #81，协调方已认领）
- review_status: ready_for_review
- worktree: `.claude/worktrees/a05-aa1561`，分支 `claude/e01-prompts`
- base: `68affa8`（origin/main，Merge PR #179）
- head: `d07afc2`（实现）+ 本交接提交
- 状态：实现与验证完成，待审查；未合并、未改 issue、未改 `docs/tasks.md`

## 改动文件

| 文件 | 说明 |
| --- | --- |
| `src/backend/app/services/ai/__init__.py` | 新包，只有文档字符串 |
| `src/backend/app/services/ai/prompts.py` | 装载器 `PromptLibrary`、`PromptTemplate`、`RenderedPrompt` 与 4 类错误 |
| `prompts/MANIFEST.md` | 8 类清单、格式、摘要与升版本规则、命名依据 |
| `prompts/{extract_entities,extract_entities_gleaning,extract_relations,judge_duplicate,summarize_definition,rewrite_query,answer_with_context}.yaml` | 7 个占位模板（version 1） |
| `tests/backend/test_e01.py` | 69 条测试 |
| `docs/handoffs/claude-e01.md` | 本文件 |

## 关键决定

1. **8 类清单的依据**：`docs/architecture-review-2026-09-22.md`「提示词工程 | 8 类版本化提示词 | … S2/分支清单」；分支 `prompts/MANIFEST.md`（`39560b7` 引入，A10 映射 `docs/reviews/branch-integration-map.md` 第 109 行标为「批 3 导入，E01 的输入」）照录 S2 §6.7 表 6.8 的 8 个 id；`docs/atomic-task-plan.md` 中 E05/E06/E10/E11/J03/J05/O06 的 `prompts/*.yaml` 文件名与之逐一对应。
2. **命名选 `evaluation`**：S-07 合并提交 `2fbf325` 写明「evals/ 并入 evaluation/」，`claude-s07-contract-conflicts.md` 记录 `evals/README.md` 迁入 `evaluation/README.md`；原子清单 K01～K04、K13 产物都在 `evaluation/`；分支 `TEMPLATE.yaml` 的评测字段也叫 `evaluation`。装载器拒绝 `evals:` 字段，`evaluation` 值必须在 `evaluation/` 下；测试断言 yaml 中不出现 `evals`。
3. **不新增依赖**：`pyproject.toml` 无 PyYAML 且在文件锁外，模板采用 YAML 严格子集，自写解析器只接受 6 个字段、固定两格缩进的 `|` 块。已在临时 venv 装 PyYAML 6.0.2 核对 7 个文件逐字段一致后卸载（未进项目依赖）。
4. **单文件单版本**：计划文件名为 `prompts/<id>.yaml`，因此一个用途只保留当前版本；调用方固定版本号，传入其他版本报 `PromptVersionError`（信息含可用版本）。旧正文靠 git 追溯。版本用正整数（分支 README 写「语义化版本」，此处按「改正文 +1」简化，如需语义化版本请协调方指出）。
5. **摘要只覆盖正文**：sha256(解析后正文 UTF-8)，CRLF/LF 一致，改 `purpose`/注释不变。MANIFEST 记摘要，测试核对表与文件一致。
6. **占位符 `{{name}}`**：JSON 示例的单花括号不受影响；其余 `{{` 视为写错；声明变量与正文占位符须完全相等；渲染单遍替换，值中的占位符不再展开。
7. **不把 `course_id` 放进提示词**：分支骨架要求课程域提示词必填 `course_id`，但课程隔离由代码与仓储保证，写进正文只会让相同内容的提示因课程不同而不同；缓存键另含课程。
8. **`gen_study_material` 不建文件**：原子清单规定 O01 未批准时 O 项不执行；MANIFEST 保留一行「未建：待 O01 准入」，装载器报未知用途。
9. **错误与日志安全**：错误信息只含文件名/字段名/变量名，不回显正文或变量值；`RenderedPrompt.text` 与 `PromptTemplate.template` 不进 `repr`（配合 E04「日志不输出提示词原文」）。

## 红绿记录

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 基线 | `<venv>/bin/python -m pytest tests/backend -q` | 76 passed |
| 红 | `<venv>/bin/python -m pytest tests/backend/test_e01.py -q`（仅有测试） | 收集错误：`ModuleNotFoundError: No module named 'app.services.ai'`，exit 2 |
| 绿 | 同上（实现后，重新 `pip install -e` 使新子包可见） | 69 passed |
| 全量 | `<venv>/bin/python -m pytest tests/backend -q` | 145 passed，1 warning（既有），exit 0 |
| 门禁 | `./scripts/verify.sh`（系统 python3 3.13.5） | `Scaffold verification passed.`，exit 0 |
| 空白 | `git diff --check` | exit 0 |

`<venv>` 为会话临时目录中的 `python3 -m venv`，`pip install -e './src/backend[test]'`；之后已 `rm -r src/backend/smartsketch_backend.egg-info`，未提交。

## 接口（给 E02～E12、J03、J05、O06）

```python
from app.services.ai.prompts import PromptLibrary, PromptError

PROMPT_VERSION = 1                      # 调用方固定，升版本时与 MANIFEST 同一提交修改
lib = PromptLibrary()                   # 默认根目录为仓库 prompts/；测试可传 tmp 目录
rendered = lib.render("extract_entities", PROMPT_VERSION, {"chunk_text": text})
rendered.text                           # 发给模型的正文，不写日志
rendered.purpose, rendered.version, rendered.template_sha256   # 缓存键与审计用
```

- 错误：`PromptNotFoundError`（未知/非法用途）、`PromptVersionError`（未知版本或版本非 int）、`PromptVariableError`（缺失/多余/非字符串）、`PromptTemplateError`（文件格式错误，信息含文件名），共同基类 `PromptError`。
- **E02/E03**：`model_calls.purpose` 枚举由 E03 定，可与本清单用途名对齐；缓存键建议 `purpose@version` + `template_sha256` + 模型 ID（`docs/integrations.md`「模型版本与向量空间」）。
- **E05/E06/E10/E11/J03/J05**：替换自己的 yaml 正文，`version` +1，同一提交更新 MANIFEST 的版本、变量、摘要与状态，以及调用方的版本常量；变量可按需改名，但须与正文占位符一致。新增字段（`model`、`temperature` 等）须先改 `prompts.py` 解析器与 MANIFEST「文件格式」。
- **J05**：占位正文已含哨兵 `<<INSUFFICIENT_EVIDENCE>>`、`[n]` 逐句标注、反引号代码与注入声明，且无 `history` 变量；测试 `test_answer_prompt_carries_sentinel_and_citation_contract` 守住这三点。
- **J03**：传入的 `history` 须已剔除类标记与哨兵（ADR-015 决定 6），装载器不做清洗。
- **O06**：O01 准入后新建 `prompts/gen_study_material.yaml`，并把 `test_e01.py` 中 `NOT_YET_CREATED` 清空、MANIFEST 行补全。

## 需协调方处理

1. **A10 批 3 与本任务重叠**：批 3 计划导入分支 `prompts/MANIFEST.md`、`prompts/README.md`、`prompts/TEMPLATE.yaml`。`MANIFEST.md` 已由本任务按 main 现状重写，批 3 应以本版为准、不再导入分支版；`README.md` 中「语义化版本」「每个提示词须含 model/temperature/changelog」与本装载器的 6 字段格式不一致，导入前需统一（或由 K14 负责）。若导入 `TEMPLATE.yaml`，装载器不会读它（按用途名取文件），测试已将其排除。
2. `docs/tasks.md` 的 E01 状态与验收证据未改（在文件锁外），请协调方登记。
3. `docs/architecture.md` 模块表尚无 `prompts/` 一行（批 3 负责）。
4. `atomic-task-plan.md` 的验证命令 `python3 -m pytest tests/backend/test_e01.py -q` 需在装有后端依赖的环境里执行；已有 editable 安装的环境需重新 `pip install -e` 才能看到新子包 `app.services.ai`。

## 未验证项与风险

- 占位正文未经任何模型或评测验证，不代表效果；K14 不得把占位版本当作「已使用的提示词」。
- 自写 YAML 子集解析器只核对了本仓库 7 个文件与测试样例的 PyYAML 一致性；子集之外的写法一律报错而不是猜测，后续作者可能觉得限制多。
- 单版本设计下无法在同一进程并存两个版本（例如 A/B 或 K13 消融），届时需扩展为多版本文件布局并改本装载器。
- 未用系统 python3 跑 pytest（系统环境无后端依赖）。

## 回滚

只新增文件、无迁移与依赖变更：`git revert` 本分支提交即可。
