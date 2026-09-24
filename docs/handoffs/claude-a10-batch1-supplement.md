# A10 批 1 补：问答规格加回契约门禁

- **task_id**：A10-批1补（ADR-016 修订 1 决定 1；A1～A10 收尾登记的后续项）
- **状态**：DONE
- **review_status**：ready_for_review（以交付提交为准）
- **worktree / 分支**：`.claude/worktrees/batch1-qa`，分支 `claude/batch1-grounded-qa`，base `548c4f8`（`origin/main`，含 PR #20 A09 与 PR #22 批 1）
- **类型**：门禁脚本与测试。不改契约真源、生成物、规格正文

## 一、改动

| 文件 | 变更 |
| --- | --- |
| `scripts/check_contracts.py` | `NAMING_DRIFT_DOCS` 加入 `specs/grounded-qa.md`，扫描文档由 9 份增至 10 份 |
| `tests/contracts/test_contracts.py` | 测试工作区 `WORKSPACE_FILES` 加入该规格；新增 `NAMING_GUARDED_SPECS`（四份规格，独立列出，不从门禁导入）；新增两项负例：每份规格追加一处 `SourceChunk` 后门禁必须失败；每份规格缺失时门禁必须失败 |
| `docs/tasks.md` | 本任务一节 |

加回之前先核对过：`specs/grounded-qa.md` 当前不含 `RELATED`、`APPLIES_TO`、`SourceChunk`，所以加入扫描不会让 main 变红。

## 二、验证（先红后绿）

```text
新增两项测试，扫描清单尚未改              22/24：两项失败，失败项都只列出 specs/grounded-qa.md
                                          （其余三份规格已受保护，说明负例本身有效）
扫描清单加入 grounded-qa.md               24/24
精简为每份规格一个别名后：
  用 HEAD 版门禁（无扫描项）运行两项测试    两项均失败，只列出 grounded-qa.md
  恢复扫描项                              两项均通过
./scripts/verify.sh                       exit 0（命名基线 10 份文档，负向测试 24 项，约 70 秒）
git diff --check                          exit 0
```

最初每份规格注入两个别名（`SourceChunk`、`RELATED`），后来精简为只注入 `SourceChunk`：ADR-016 修订 1 只要求每个文件一处错误命名负例；`RELATED` 已由现有的 `test_naming_alias_in_contract_doc_fails` 覆盖；而每注入一次都要单独启动一次门禁，精简可以减少测试耗时。

本地运行环境：生成器 `datamodel-codegen` 在独立 venv 中，只把这一个命令通过 PATH 暴露给 `verify.sh`，门禁依赖用系统 `python3`（与 A10 交接中的注意事项相同）。

## 三、风险与后续

- 以后新增规格时，要同时加进门禁的扫描清单和测试的 `NAMING_GUARDED_SPECS`，否则缺文件负例不会覆盖到它。两边清单有意分开维护。
- 负向测试总耗时随受保护文件数线性增长，目前约 70 秒。
- 下一步：请 Codex 复核本提交；B11（A02-R01）可在同一契约真源上开始。

## 四、回滚

`git revert <交付提交>`：只撤销扫描清单一行、测试改动和任务行。不涉及数据或依赖。
