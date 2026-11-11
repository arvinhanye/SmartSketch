# OPT-04 测试文件索引交接

- 状态：DONE（本地未提交；未推送、未开 PR）。负责人：Codex。日期：2026-11-05。
- 分支：`codex/opt-04-test-index`；基线：`ad63341`。
- 工作区：`/Users/arvinhan/.codex/worktrees/opt-04-test-index/SmartSketch-main`。主工作区正用于 OPT-02，本任务使用独立 worktree。
- 输入：已阅读 `AGENTS.md`、`docs/tasks.md`、测试规则，以及本地 `claude/code-structure-review-handoff-49e73a@0796917` 的 `docs/handoffs/claude-code-structure-review-codex-handoff.md` OPT-04 节；后者尚未合入本基线，因此从该分支读取。

## 交付物与决定

| 文件 | 内容 |
| --- | --- |
| `tests/INDEX.md` | 224 个文件的路径、被测模块/功能一句话、规格/ADR/任务关联；backend 115、frontend 82、integration 27。 |
| `tests/tooling/test_test_index.py` | 一条完整性测试：三个非递归 glob 与索引条目双向一致，额外拒绝重复、错误链接及无效文件列格式。 |
| `docs/tasks.md` | 本工作区 OPT-04 认领、范围、完成状态与验收证据。 |
| `docs/handoffs/codex-opt-04.md` | 本交接。 |

索引依据测试文件头部文档字符串/用途注释、import、describe 名称，不从文件名猜任务编号；无明确来源的关联或具体功能标「待确认」。57 行的关联列含「待确认」（其中 2 行已知任务/ADR，但规格条款路径待确认）；具体功能不足时只登记导入模块。复核时收紧了若干覆盖描述，尤其没有把集成测试中的自动写入锁守卫记到 `tests/backend/test_f08.py`。

所有原测试文件保留原名、原内容。未修改产品代码、接口、数据模型、环境变量或依赖，无需修改功能规格或 ADR。

## 实际验证

环境沿用主工作区 `.venv`：Python 3.11.9、pytest 9.1.1；无需安装依赖。下列命令均在本工作区执行。

| 命令 / 检查 | 结果 |
| --- | --- |
| `/Users/arvinhan/Desktop/SmartSketch-main/.venv/bin/python -m pytest tests/tooling/test_test_index.py -q`（尚未创建索引） | 1 failed，明确报 `Missing tests/INDEX.md`，确认守卫生效。 |
| 同命令（索引完成后） | 1 passed，最终运行 0.46 秒、无警告。 |
| 临时目录中的完整样例、漏项、失效文件、重复项、错误链接、无效格式 | 6/6 符合预期；完整样例通过，五类异常均抛出对应断言，不修改真实索引。 |
| `PATH="/Users/arvinhan/Desktop/SmartSketch-main/.venv/bin:$PATH" ./scripts/verify.sh` | 默认 basic，exit 0；hooks、契约结构与漂移、25 项门禁负例、B14/B08/B09/B10/B12/B13 回归通过，输出 `PASS contracts gate`、`Scaffold verification passed.`。 |
| `git diff --check` | 通过。 |

basic 日志：`/private/tmp/opt04-verify.log`。其中 pytest 缓存写入受到沙箱限制，出现 `PytestCacheWarning`，全部断言仍通过且退出码为 0；新索引测试在获准写缓存后复跑，无警告。本任务未运行 full/integration 产品回归，也未调用真实模型、Neo4j 或 Docker。

独立核对：142 个 Python 条目引用的规格路径/ADR 均出现在对应头部文档字符串；前端 82 个文件的头注释、import、describe 证据已核对。完整性守卫经另一代理只读检查，无实质问题。

## OPT-03 同步与下一步

本分支保持 `ad63341` 基线，未包含 OPT-03；结束时检查本地分支和提交记录，未检出 OPT-03 同期合入。本轮没有合并其他任务，也没有推送或创建 PR。

下一位 Agent 的首个动作：检查目标集成分支是否已包含 OPT-03 或其他测试文件变化。若有，基于合并后的三个范围重新读取头部/import/describe 并生成 `tests/INDEX.md`，不要只补文件名；重新运行索引完整性测试与 `./scripts/verify.sh`。未来新增/删除/移动测试时也同步索引。该守卫已由既有 `scripts/verify/backend.sh` 的 `tests/tooling` 收集范围纳入 full 门禁；basic 不自动运行它，因此保留上述定向测试命令。

改动可逐文件撤销：移除本次新增的索引、tooling 测试和交接，删除 `docs/tasks.md` 中本任务节即可；不涉及迁移或用户数据。
