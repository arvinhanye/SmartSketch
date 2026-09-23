# HOOK-01：修复 `block-dangerous.sh` 的命令提取漏检

- **task_id**：HOOK-01（用户直接指派；缺陷在 CI-01 冒烟时发现，见 `docs/handoffs/claude-ci-01-smoke.md` 第五节）
- **状态**：DONE
- **review_status**：ready_for_review
- **worktree**：`/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/adoring-sinoussi-709263`
- **分支 / base**：`claude/fix-block-dangerous-hook` / base `b345a34`（`origin/main`，已含 CI-01）
- **head_commit**：本文件随修复提交一并入库（`git log -1 -- docs/handoffs/claude-hook-01.md` 可查）

## 一、缺陷与根因

| 项 | 内容 |
| --- | --- |
| 现象 | 命令里只要在危险片段**之前**出现双引号，钩子就放行。例：`echo "hi" && rm -rf …`、`git commit -m "wip" && git reset --hard` |
| 根因 | 钩子用 `sed 's/.*"command"…"\([^"]*\)".*/\1/p'` 从**原始 JSON** 截取 `command`。命令里的双引号在 JSON 中是 `\"`，`[^"]*` 在第一个引号处停止，只抽到 `echo \` 这样的前缀，后面的内容从未进入匹配 |
| 次生缺陷 | 抽取失败时 `command` 为空，`case` 落到放行分支，也就是说解析失败时默认放行（fail-open） |
| 复现 | 按 Claude Code PreToolUse 输入格式构造 6 条 JSON 喂给钩子：引号在前的 3 条全部放行，抽取结果都是以 `\` 结尾的半截字符串 |
| 引入时间 | 初始化提交 `05d214c` 起即如此，之后未改动 |

## 二、修复（只改根因）

| 文件 | 改动 |
| --- | --- |
| `.claude/hooks/block-dangerous.sh` | 用 `python3` 的 `json` 解码取 `tool_input.command`，替代正则截取；解码失败（非 JSON、空输入、结构不对）时输出 `decision: block`，即 fail-closed；拦截规则的 5 个子串**原样保留**；文件模式保持 `100755` |
| `tests/hooks/test_block_dangerous.sh` | 新增回归测试，14 条用例：拦截 11 条（基线 1、引号之后或引号内 6、多行 1、带空格 JSON 1、非 JSON 1、空输入 1），放行 3 条（普通命令、含引号普通命令、无 `command` 字段） |
| `scripts/verify.sh` | 经用户同意，在末尾运行 `tests/hooks/test_block_dangerous.sh`：失败或文件缺失时打印全部用例结果并 exit 1；通过时打印其结论行 `block-dangerous hook tests passed.`，便于在 CI 日志中确认已执行。CI-01 的 workflow 调用 `verify.sh`，因此 CI 自动覆盖该回归测试 |
| `docs/tasks.md` | 新增「协作安全修复」小节与 HOOK-01 行，位置在 CI-01 小节之后，避开 PR #2 改动的行 |

依赖：`python3`。`scripts/verify.sh` 已依赖它，不是新增依赖。已用 anaconda 3.13.5 与 macOS 系统 `/usr/bin/python3` 3.9.6 验证。

## 三、实际运行的命令与结果

```text
tests/hooks/test_block_dangerous.sh（修复前）  10 FAIL / 4 PASS，exit 1 —— 失败均为「期望 block，实际 allow」
tests/hooks/test_block_dangerous.sh（修复后）  14 PASS，exit 0
env -i PATH=/usr/bin:/bin LC_ALL=C tests/hooks/test_block_dangerous.sh   exit 0（系统 Python 3.9 + C locale）
会话内实时探针：echo "live-probe" && echo git reset --hard …（只打印文本）  被钩子拦截
./scripts/verify.sh   exit 0（已包含钩子回归测试）
git diff --check      exit 0
接入门禁的反向验证（scratch 副本）：换回旧钩子 → verify exit 1，报 10 条 FAIL；移走测试文件 → verify exit 1
```

**测试本身的一次假绿（已修）**：测试初版用 `payload | expect`，`expect` 在管道子 shell 中运行，`fail=1` 传不回主 shell。于是在 10 条 FAIL 的情况下仍打印 passed 并 exit 0。这是在 RED 阶段发现的，改为用重定向喂输入后，才得到上面正确的 RED（exit 1）。脚本内有注释说明，后续修改不要改回管道。

## 四、仍然存在的限制（未修，属另一个问题）

修复只保证钩子能看到完整命令。**拦截规则**仍是 5 个固定子串，下列等价写法实测会放行（探针只把字符串交给钩子判定，未执行任何命令）：

| 放行的写法 | 对应被拦的写法 |
| --- | --- |
| `rm -fr`、`rm -r -f`、`rm -Rf`、`rm  -rf`（双空格） | `rm -rf` |
| `git push -f`、`git push origin +main` | `git push --force` |
| `git clean -xdf`、`git clean -df` | `git clean -f` |
| `git reset  --hard`（双空格） | `git reset --hard` |
| `drop database`（小写） | `DROP DATABASE` |
| `git checkout -- .` | 不在规则内 |

同时，子串匹配会误拦**只是提到**危险字样的命令，例如 `echo rm -rf is just text`。与修复前行为一致，未改变。

是否扩展规则（例如改为按 token 解析或加正则）是一个独立的策略决定，建议另立 HOOK-02，不在本任务内顺手改。

## 五、风险

- **fail-closed 的代价**：如果运行环境没有 `python3`，或钩子输入格式变化导致无法解码，**所有 Bash 调用都会被拦**。这是有意的选择：安全钩子看不懂输入时不应放行。恢复方式：用编辑工具（不经 Bash 钩子）修改或回退本文件。
- **共享门禁变更**：`scripts/verify.sh` 属于 CI-01 的共享门禁，本任务经用户同意加了两行。之后 `verify.sh` 依赖 `tests/hooks/test_block_dangerous.sh` 存在且可执行，移动或重命名该测试须同步修改 `verify.sh`。
- 钩子由各 worktree 自己分支上的副本生效。本修复只对已合入它的 checkout 生效，其他 worktree 在同步 main 之前仍是旧版本。

## 六、下一步

1. 请 Codex 审查本提交。
2. 确认本 PR 的 CI 运行（pull_request）通过，确认日志中执行了钩子回归测试。
3. 决定是否立 HOOK-02 扩展拦截规则（见第四节）。

## 七、回滚

`git revert <本提交>`，一次性恢复旧钩子与旧 `verify.sh`，并删除测试与本文件。**不要只回退钩子而保留 `verify.sh` 的新行**，否则门禁会因为回归测试失败而一直红。不要使用 reset、clean 或 stash 清理；stash 栈与其他 worktree 共享。
