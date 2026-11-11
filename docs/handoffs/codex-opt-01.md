# OPT-01：任务看板与 ADR 原文归档

- task_id：OPT-01；负责人：Codex；状态：DONE（仅本地单提交，未推送、未开 PR）。
- 分支：`codex/opt-01-doc-archive`；基线：`ad633416e436a23f28172db3bd5a11757fe573e0`。
- 独立工作树：`/Users/arvinhan/.codex/worktrees/opt-01-doc-archive/SmartSketch-main`。

## 基线与开工核对

开工执行 `git status --short --branch`、`git log -10 --date=short --format=… -- docs/tasks.md docs/decisions.md …`、`git branch -avv`、`gh pr list --state open --limit 100 --json number,title,headRefName,baseRefName,files,url`。当时工作区干净，当前分支 `claude/home-topbar-nav` 指向 `ad63341`；唯一打开且修改 tasks.md 的 PR 是 [#337](https://github.com/arvinhanye/SmartSketch/pull/337)，其 `0796917` 仅新增结构审查交接稿和 OPT 表，尚未合入当前分支。

用户确认采用当前分支，并原样带入 #337 的交接稿与 OPT 表。随后观察到其他聊天在共享工作区切换 OPT-02／OPT-05 分支并写认领记录，因此用宿主 create_worktree 从已确认的 `ad63341` 隔离本任务；未移动、覆盖或提交共享目录的未提交改动。OPT-01 开始时已标 `IN_PROGRESS / Codex`，最终更新为 DONE。本次包含两份已授权的 #337 文档增量；不是合并该 PR。

## 交付与保留规则

- [当前任务看板](../tasks.md)：顶部原状态摘要、138 行未关闭条目/风险原文摘录、FORMAL 最新结论/待办、OPT 认领表和原节标题索引。最终 UTF-8 大小 **59,494 字节**，小于 60,000 字节；迁移输入为 508,516 字节（本地原文件 506,920 + #337 表 1,596）。旧状态未擅自改写；K05/J09/J10/K04、父任务 TODO 和待视觉签收继续保留。已由 C 阶段明确接管/关闭的 B 阶段旧 OPEN 行留在归档，不重复复活为当前任务。
- 任务原文：[2026-09](../archive/tasks-2026-09.md)、[2026-10](../archive/tasks-2026-10.md)、[2026-11](../archive/tasks-2026-11.md)。新增 11 月卷是因为用户选择的最新本地基线含 11 月内容；早期无显式日期的骨架/决策/认领节归九月。共 160 个源二级节，按原月内顺序完整保留。
- 用户另外确认：FORMAL 整节已达 41,024 字节，与完整索引及活动条目无法同时满足 60 KB；因此保留最新发布结论及全部已识别待办，早期进展归档。启动后配置向量、服务器部署、受控代理/网络出口取舍保留；自动重试已实现；最新候选未重测业务闭环、Safari/部分视口未覆盖等边界也保留。
- 为避免拆散复合进度段、表格、审查上下文，归档按**完整历史节**保存，看板保留活动原文摘录副本。归档是固定历史快照，不是第二份活动认领表；修改状态只改当前看板。此策略完整保留原始字节，重建时实际使用看板摘录与归档其余内容。
- [ADR 索引](../decisions.md)：360,811 → **24,935 字节**；84 条 ADR 的编号、标题、日期、原文签收状态、一句话及正文锚点。采用全部正文分卷，不仅移动 superseded 项：大量长 ADR 仍有效，仅移动失效项无法明显减少入口负担；索引能直接到达现行条文，正文语义不变。
- 正文卷：[001–040](../archive/decisions-adr-001-040.md)、[041–080](../archive/decisions-adr-041-080.md)、[081–120](../archive/decisions-adr-081-120.md)。保留原始缺号、092/091 顺序、所有三级修订/签收行，以及 094 与 095 间的非 ADR 发行节。归档不代表撤销；摘要仅供检索，状态栏不推定新的批准。
- 六处原始相对 Markdown 链接保持逐字不变，新增六个简短导航页（包括 archive/reviews/ 下三页）转到现有文件，避免历史 href 失效。新增导航锚点/源区块标记不属于原正文；卷首注明“本文件/下文/末节”指迁移前原文件，跨卷经索引定位。

## 依赖与引用

- `tests/tooling/test_worker_network_ci.py` 扫描 decisions 入口及全部 `decisions-adr-*.md` 正文卷；拒绝空扫描、重复编号和索引/正文集合不一致，缺卷不会假绿。
- `scripts/verify.sh` 保留两个入口文件检查，新增六个正文卷存在检查；原有 `M0-01 | DONE` 断言改读九月归档。`scripts/verify/frontend.sh` 仅更新历史定位注释。
- `tests/backend/test_e08.py`、`test_e09.py` 仅修改首行文档字符串的历史路径。
- architecture、frontend-ui-handoff、prompt-engineering、course-knowledge-graph、identity-access 和 contracts README 中明确指向历史正文的引用改到对应卷；普通索引入口及历史提交的文件清单不批量改写。
- 全库 tasks.md/decisions.md 引用审计包含 tracked 与新增未忽略文件；原有可点击的旧文件 `#fragment` 引用为 0。新增导航链及锚点另做完整检查。
- 无产品逻辑、API、DTO、数据模型、依赖、环境配置变化。仅按本任务授权调整 tooling 验证逻辑和文档引用；AGENTS.md 与 CLAUDE.md 全文未改。

## 原文零丢失验证

一次性脚本、输入快照、映射清单和日志仅在仓库外 `/private/tmp/smartsketch-opt-01/`，**不提交**：

```sh
python3 /private/tmp/smartsketch-opt-01/verify_archive.py \
  /Users/arvinhan/.codex/worktrees/opt-01-doc-archive/SmartSketch-main
```

脚本逐段校验归档的原文 SHA-256，再将看板中 34,011 字节活动摘录与归档其余部分按**原文件顺序**拼回；原 OPT 行由归档历史快照提供，当前认领状态及新增索引不混入源正文。ADR 按原顺序取全部 85 个二级节（84 ADR + 1 发行节），前导标题来自新入口。比较重建文本与迁移前快照：

| 原文件 | 原始/重建字节 | 原始与重建 SHA-256（相同） | diff |
| --- | --- | --- | --- |
| tasks.md（含授权带入的 OPT 表） | 508,516 | `93ff292df24747e237038f6c6a18c80e1efca9a06fc5b78a1aa97fc141e90815` | 0 字节 |
| decisions.md | 360,811 | `3b070362d30d08434b4be7a746009423ad11ee489391296ee5c31db04b5a6a82` | 0 字节 |

`tasks.reconstructed.diff` 与 `decisions.reconstructed.diff` 均为空，不只是正文“意义相同”。没有改写原文中的错字、旧状态或旧相对链接。新增索引/导航/当前状态是新内容，完整历史仍逐字可还原。临时目录可能被系统清理；持久证据为本提交的所有原文块及上述散列，原始输入也可从基线提交和 #337 的 12 行增量重建。

## 实际验证

- `PATH=/Users/arvinhan/Desktop/SmartSketch-main/.venv/bin:$PATH PYTHONPATH=src/backend ./scripts/verify.sh`：**exit 0，contracts gate PASS、Scaffold verification passed**（沙箱无法写入 pytest 缓存，产生 PytestCacheWarning；不影响断言结果）；日志 `/private/tmp/smartsketch-opt-01/verify-basic.log`。
- `PYTHONPATH=src/backend /Users/arvinhan/Desktop/SmartSketch-main/.venv/bin/pytest tests/tooling/test_worker_network_ci.py -q -p no:cacheprovider`：**3 passed**（5.05 秒）；同文件改前基线 3 passed（4.68 秒）。
- 外部临时故障注入：有效输入通过；跨卷重复 ADR、缺失正文卷、全部正文为空、入口与归档撞号四种均被正确拒绝，未修改实际仓库来制造故障。
- 上述重建脚本：两份 diff 为空；**306 个导航链接及目标锚点有效**。
- `python3 docs/reviews/validate_atomic_plan.py`：PASS，142 项原子任务、依赖无环、JSON/Markdown 一致、214 个所辖链接可达。
- `git diff --check`：PASS；暂存后也检查所有新归档；源码与最终差异范围检查无产品代码变动。
- `AGENTS.md`、`CLAUDE.md` 与基线逐字相同；导入的 Claude 交接稿与 #337 逐字相同。
- 未运行 full/integration、浏览器或真实模型调用；本任务未改变产品行为，不声称历史未验收事项已经验收。

## 共同契约建议（等待用户确认，未实施）

AGENTS.md §2 第 1 条建议：

> 阅读本文件、`docs/tasks.md`（当前看板）以及本次涉及的 `specs/<feature>.md`；历史任务仅在需要时通过归档索引查阅 `docs/archive/`。

另建议后续一起核对 §6：新增 ADR 正文写入对应编号段归档卷，并在 `docs/decisions.md` 更新索引；当前 §6 的原字句本轮也未改。CLAUDE.md 的入口规则保持原样。

## 风险、下一步与回滚

- 看板中的历史遗留有些混合“已实现”与“尚未签收”子句；本次保留原文与归档入口，不替用户批量关闭。逐项改变状态属于后续认领。
- #337 的交接增量及并行 OPT-02/04/05 的认领后续整合可能冲突。整合者先保留当前各任务最新状态，再依本索引将历史内容定位到归档，禁止以本分支快照覆盖其他任务的新记录。
- 下一位先读当前看板及对应任务交接；本任务是否推送/开 PR，以及 AGENTS 措辞是否采用，均留待用户明确指示。
- 回滚：对本任务这一个提交执行常规 `git revert`；没有迁移或运行数据变更。归档后的新认领/新 ADR 若已发生，回滚前须先保留它们，不能直接覆盖。
