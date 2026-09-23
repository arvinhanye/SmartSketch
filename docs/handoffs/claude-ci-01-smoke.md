# CI-01 冒烟：Codex 新增 GitHub Actions 的首次托管运行

- **task_id**：CI-01 冒烟验证（CI-01 本身属 Codex，见 `docs/handoffs/codex-ci-01.md`；本文件只补「GitHub 首次运行待确认」这一项的证据）
- **状态**：DONE。托管运行成功，临时分支已删除；此后 CI-01 已入库，main 的 push 与 PR 的 pull_request 两条触发路径均已实测通过（见第六节，2026-09-23 更新）
- **review_status**：ready_for_review
- **worktree**：`/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/adoring-sinoussi-709263`
- **分支 / base**：`claude/ci-01-smoke` / base `bfa236c`（`origin/main`）
- **head_commit**：本文件随单独提交入库（`git log -1 -- docs/handoffs/claude-ci-01-smoke.md` 可查），与 A02 的 PR #2 无关
- **类型**：验证任务。仓库内只新增本交接文件；未修改 `ci.yml`、`scripts/verify.sh`，也未提交 main checkout 中 Codex 的任何改动

## 一、被测对象

| 项 | 值 |
| --- | --- |
| 文件 | main checkout `/Users/arvinhan/Desktop/SmartSketch` 中**未跟踪**的 `.github/workflows/ci.yml`（Codex CI-01） |
| 内容指纹 | `shasum -a 256` 前 16 位 `5b4a148dd0a67aac`；冒烟提交里的副本与之逐字节一致 |
| 触发 | `push`、`pull_request`、`workflow_dispatch`；权限 `contents: read` |
| 步骤 | `actions/checkout@v7` → `actions/setup-python@v7`（3.12）→ `bash -n scripts/verify.sh` → `./scripts/verify.sh` |

## 二、GitHub 托管运行（决定性证据）

用户选择「临时分支冒烟」。做法是用底层命令在临时 index 上组装提交，全程不切换分支，也不碰任何工作区：`bfa236c` 的树加上 `ci.yml` 原文，commit-tree 生成 `073bb02`（只多这一个文件），推送到临时分支 `ci-smoke/ci-01`，触发 push 运行。

| 项 | 结果 |
| --- | --- |
| 运行 | [#35814451582](https://github.com/arvinhanye/SmartSketch/actions/runs/35814451582)，event `push`，head `073bb02` |
| 结论 | **success**；job「Repository scaffold」2026-09-23T03:28:21Z → 03:28:27Z，约 6 秒 |
| 步骤 | Set up job、Check out repository、Set up Python、Check verification script syntax、Verify repository scaffold、两个 Post 步骤、Complete job，全部 success |
| 运行环境 | `ubuntu-24.04`（image 20260907.300.1）；`Successfully set up CPython (3.12.14)` |
| verify 输出 | `Scaffold verification passed.` |
| 注解 | 1 条 notice，无 warning 或 error：`ubuntu-latest` 自 2026-10-19 起迁移到 Ubuntu 26 |
| 清理 | `git push origin --delete ci-smoke/ci-01` 已执行；`git ls-remote --heads origin 'ci-smoke/*'` 为空。运行记录保留在 Actions 历史中 |

## 三、本地预检（托管运行前）

| 检查 | 命令 / 方法 | 结果 |
| --- | --- | --- |
| YAML 解析、触发器、权限、步骤 | PyYAML `safe_load` | PASS |
| action 版本存在 | `gh api repos/actions/{checkout,setup-python}/git/ref/tags/v7` 与 `releases/latest` | 两个 `v7` 标签都存在；最新版为 checkout v7.0.1、setup-python v7.0.0（2026-07-20） |
| `verify.sh` 所需 24 个文件均已提交 | `git cat-file -e bfa236c:<f>` 与 `13d586e:<f>` 逐个检查 | 全部存在；`scripts/verify.sh` 索引模式 `100755` |
| 仅含已提交文件的快照 | `git archive bfa236c` / `git archive 13d586e` 解压后用 `env -i … LANG=C.UTF-8` 运行 `bash -n` 与 `verify.sh` | 两份快照均 exit 0 |
| 情形 A：Codex 提交 CI-01 后的 main | 在 scratch clone 中把 main checkout 的 8 项未提交改动（`git ls-files -m -o --exclude-standard`）叠加到 `bfa236c` 并提交 | `bash -n` exit 0、`verify.sh` exit 0 |
| 情形 B：PR #2 合入情形 A | 同一 clone 中 `git merge` A02 分支 `13d586e` | 无冲突；合并结果 `bash -n` exit 0、`verify.sh` exit 0；A02 章节与 Codex 的 CI 说明都保留 |
| 负例：门禁能变红 | 同一 clone 中临时移走 `docs/product.md` / 把 `.mcp.json` 写坏 / 给脚本副本追加语法错误 | `verify.sh` exit 1、`verify.sh` exit 1、`bash -n` exit 2；恢复后 exit 0 |

本机没有 `act`、`docker`、`actionlint`，所以本地无法起容器运行 Actions。托管运行前的结论只基于上表的模拟。

## 四、API / 数据 / 配置变更

无。远端曾短暂存在临时分支 `ci-smoke/ci-01`，已删除。

## 五、风险与下一步

1. **CI 仍未入库**：`ci.yml` 仍是 main checkout 的未跟踪文件，属于 Codex 的 CI-01 交付，本文件不代为提交。Codex 或负责人提交并推送后：
   - push 到 main 即会运行；
   - PR #2（A02）要推一个新提交才会触发 `pull_request` 运行。情形 B 预测结果为通过。
   - **已更新（2026-09-23）**：负责人已提交并推送为 `b345a34`，预测均已兑现，见第六节。
2. **运行器迁移提示**：`ubuntu-latest` 将于 2026-10-19 起迁到 Ubuntu 26。当前 CI 只用 bash 与 Python，受影响概率低；若要环境固定，可改为 `ubuntu-24.04`，由 CI-01 负责人决定。
3. **CI 覆盖面**：与 Codex 交接一致，现阶段绿灯只代表骨架文件、JSON 与文档约束通过，不代表前后端可构建或可测试。
4. **任务板未改**：CI-01 的认领行在 main checkout 未提交的 `docs/tasks.md` 中。本分支不改 `docs/tasks.md`，避免与 Codex 的未提交改动和 PR #2 冲突。建议 Codex 把该行的「GitHub 首次运行待确认」改为引用本交接。**截至 2026-09-23**，`b345a34` 中该行仍写「DONE（待 GitHub 首次运行确认）」，本分支仍不代改。
5. **过程记录**：模拟阶段有一条命令含 `rm -rf`（只清理会话 scratch 目录），被项目的 PreToolUse 钩子 `block-dangerous.sh` 拦截。之后改用新建目录，不再删除。另发现钩子只截取 `command` 字段中第一个 `"` 之前的内容，因此更早一条同样含 `rm -rf` 的 scratch 清理命令没有被拦下。该命令只作用于会话 scratch 目录，未影响仓库。这个匹配缺陷是否修复由钩子负责人决定。**已更新（2026-09-23）**：经用户指派，已由 HOOK-01 修复（PR #3，`3c2dfab`，交接 `docs/handoffs/claude-hook-01.md` 随该 PR 入库）。

## 六、后续进展（2026-09-23 更新）

| 项 | 结果 |
| --- | --- |
| CI-01 入库 | 负责人提交并推送为 `b345a34`（`ci: add scaffold GitHub Actions workflow`）；其中 `ci.yml` 与本文冒烟版本逐字节一致；workflow `CI` 已注册，状态 active |
| main 的 push 运行 | [#35815254690](https://github.com/arvinhanye/SmartSketch/actions/runs/35815254690)（head `b345a34`）success；ubuntu-24.04 / CPython 3.12.14；`Scaffold verification passed.` |
| PR #2 的 pull_request 运行 | 把 `origin/main` 合入 A02 分支（`cd1ecd6`，无冲突）后触发 [#35816358187](https://github.com/arvinhanye/SmartSketch/actions/runs/35816358187) success；同一推送的 push 运行 #35816355088 success。第三节情形 B 的预测成立 |
| PR #3 的 pull_request 运行 | HOOK-01 修复分支（`3c2dfab`）[#35816330323](https://github.com/arvinhanye/SmartSketch/actions/runs/35816330323) success，日志中可见 `block-dangerous hook tests passed.`；push 运行 #35816325210 success |
| 尚未实测 | `workflow_dispatch`（手动触发） |
| 新观察 | 同仓库分支上的 PR 每次推送会触发**两次**运行（`push` 与 `pull_request` 各一次），结果一致，属于重复消耗。是否把 `push` 限定为 main，由 CI-01 负责人决定 |

## 七、回滚

仓库内只新增本文件：`git revert <本提交>`。临时分支已删除，无需再处理。不要使用 reset、clean 或 stash 清理；stash 栈与其他 worktree 共享。
