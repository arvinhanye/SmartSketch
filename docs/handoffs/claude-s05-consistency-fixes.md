# Claude 交接：S-05 hook 解析缺陷与路径不一致修复

- **状态**：DONE
- **日期**：2026-09-22
- **范围**：重写 `.claude/hooks/block-dangerous.sh` 修掉三个已实测确认的缺陷；修正 `README.md` 目录树与协作流程中的失效路径；统一 `AGENTS.md` §3 角色表的路径歧义。附 `.env.example` 与 `docs/integrations.md` 的一致性核对结果（只报告）。

## 已交付

| 文件 | 改动 |
| --- | --- |
| `.claude/hooks/block-dangerous.sh` | 重写：python3 解析 JSON、空白规范化、命令位置匹配、fail-open |
| `README.md` | 目录树重写（删 `.codex/`，补 S-03/S-04 新增目录）；协作方式三处路径更新 |
| `AGENTS.md` | §3 角色表：裸 `workers/` → `src/backend/app/workers/`；「评测资产」→ 真实路径 |

未触碰 `.env.example`、`docs/integrations.md` 的变量表、`docs/tasks/`、`docs/decisions/`、`src/`。

## 一、hook 重写

### 根因

改造前用 sed 正则从 JSON 抠 command 字段，`[^"]*` 在**第一个转义引号处截断**。于是 `git commit -m "fix" ...` 只抠到 `git commit -m \`，后半段整个漏检。加上匹配是纯子串比较，同时存在漏报和误报。

### 四项修改

1. **python3 解析 JSON** 取 `tool_input.command`，不再用正则抠字段。仓库其余地方（`verify.sh` 的 JSON 校验）已依赖 python3，保持一致。
2. **空白规范化**：换行先显式转成 `;`（保住分隔语义），再把连续空白压成单空格，消除多打一个空格的绕过。
3. **命令位置匹配**：只在字符串开头，或 `;` `&` `|` `(` `)` `{` `}` 之后匹配（`&&` 与 `||` 的末字符分别是 `&` 和 `|`，一并覆盖）。不加结尾边界是故意的——`rm -rfv`、`git clean -fd` 同样危险。
4. **fail-open**：JSON 非法、`python3` 缺失、检查脚本异常一律放行并向 stderr 说明。取舍已写进脚本注释：**这是共享工作区的便利护栏，不是安全边界**——人始终在回路里，任何人都能在终端直接跑同样的命令。解析失败就全面阻断会让工具遇到任何意外输入即不可用，代价远大于漏掉一次本该人工确认的命令。

输出契约未变：拦截 → stdout 输出 `{"decision":"block","reason":"..."}` 且 exit 0；放行 → 无 stdout 且 exit 0。`reason` 文案增加了命中的模式名，便于排查。

### 一处必要的偏离：五条模式拆成两组

按「只在命令位置匹配」实现后，实测发现 **`psql -c 'DROP DATABASE prod'` 被放行**——这是覆盖缩小，与「不要缩小范围」冲突。

根因：`DROP DATABASE` 是 SQL 片段而非 shell 命令，**永远只会作为参数出现，永远不可能落在 shell 命令位置**。对它用位置匹配等于把这条模式废掉。

因此按「危险是否取决于 shell 位置」拆成两组：

| 组 | 模式 | 匹配方式 |
| --- | --- | --- |
| `SHELL_PATTERNS` | `git reset --hard`、`git clean -f`、`rm -rf`、`git push --force` | 命令位置匹配 |
| `ANYWHERE_PATTERNS` | `DROP DATABASE` | 整串匹配（同改造前） |

五条模式一条不少、一条不多。代价是在文本里提到 `DROP DATABASE` 会误报——与改造前行为一致。

### 实测结果（真实输出）

**任务指定的四个用例：**

| # | 命令 | 期望 | 实际 |
| --- | --- | --- | --- |
| 1 | `rm -rf /tmp/x` | 拦截 | **拦截** |
| 2 | `rm  -rf /tmp/x`（双空格） | 拦截 | **拦截** |
| 3 | `git commit -m "fix" && rm -rf build` | 拦截 | **拦截** |
| 4 | `echo never rm -rf anything` | 放行 | **放行** |

用例 1～3 的 stdout 均为：

`{"decision": "block", "reason": "Shared-workspace protection: blocked pattern 'rm -rf'. Use a reviewed, scoped command instead."}` ，`[exit=0]`

用例 4 无 stdout 输出，`[exit=0]`。

**其余模式与命令位置回归：**

| 命令 | 期望 | 实际 |
| --- | --- | --- |
| `git reset --hard origin/main` | 拦截（模式 1，开头） | **拦截** |
| `cd x; git clean -fd` | 拦截（模式 2，分号后） | **拦截** |
| `psql -c 'DROP DATABASE prod'` | 拦截（模式 4，整串匹配） | **拦截** |
| `git push --force-with-lease` | 拦截（模式 5，无结尾边界） | **拦截** |
| `git log --oneline \| grep 'reset --hard'` | 放行（不在命令位置） | **放行** |
| `echo 'git push --force' > notes.txt` | 放行（不在命令位置） | **放行** |
| `ls; echo done` | 放行（普通命令） | **放行** |

**fail-open 路径**（三条均无 stdout、`exit=0`）：

| 输入 | stderr |
| --- | --- |
| `not json at all {{{` | `block-dangerous: stdin 不是合法 JSON（JSONDecodeError），本次放行且未做检查` |
| `{"tool_name":"Read","tool_input":{"file_path":"a.md"}}` | （无，静默放行） |
| `[]` | `block-dangerous: stdin JSON 顶层不是对象，本次放行且未做检查` |

`bash -n .claude/hooks/block-dangerous.sh` → passed。

### 两次真实误报（本会话内实际发生）

新 hook 在本任务中**拦下了我自己的两条命令**，两次都不是 bug，而是设计取舍的真实代价：

1. 测试台里有一行 echo 标签，单引号内含 `&&` 加危险模式。引号内的 `&&` 被当成真分隔符，其后的模式落在命令位置。剥离引号确实能消除这类误报，但会同时放过 `bash -c` 包裹的破坏性命令——属于缩小覆盖。选择保留覆盖、接受误报。
2. 用 bash heredoc 写这份交接文件时，正文里的命令示例位于**行首**。换行是任务明确规定的命令位置分隔符，于是正文被当成命令拦下。

第 2 条的影响面值得注意：**在文档密集的仓库里，用 heredoc 写含命令示例的 Markdown 会被拦**。绕过方式不是放宽 hook，而是**改用 Write 工具**（PreToolUse matcher 只匹配 Bash）——本文件即用 Write 写入。

### 已知残留缺口（有意未扩大范围）

1. `rm -fr`、`rm -r -f` 等等价写法不在五条模式内。
2. `DROP DATABASE` 区分大小写，小写形式漏检。
3. 引号内的分隔符被当作真分隔符（见上，取舍已说明）。
4. heredoc/多行文本的每一行都算命令位置（见上，符合任务规定）。

缺口 1、2 在改造前就存在，本次遵守「保持五条模式、不要缩小范围」未做扩展。若要收敛，建议单独立任务并重跑本文件的全部用例。

## 二、README 修正

- **删掉 `.codex/`**：实测 `ls -d .codex` 在 worktree 与主仓库**都不存在**。改为在树下方一句说明「Codex Desktop 若在本机生成，它是可选的本地目录、不提交」，避免新 Agent 去找一个不存在的目录。
- **补齐 S-03/S-04 新增结构**：`docs/decisions/`、`docs/tasks.md + tasks/`、`docs/handoffs/`、`tests/`、`prompts/`、`evaluation/`、`datasets/`、`scripts/verify/`、`NOTICE`、`docker-compose.yml`、`.claude/{rules,hooks}/`、`.env.example`、`.gitignore`、`README.md` 自身，并把 `src/backend/app/` 展开到五个分层。
- **协作方式**：第 2 步改为「在 `docs/tasks/<里程碑>.md` 认领，只改自己那一行」；第 5 步后补一句「新增内容一律新建文件」并指向 §3 写争用规则；本地配置段补上原始课程资料与评测报告不提交。

验收（按缩进还原完整路径后双向比对）：

| 检查 | 结果 |
| --- | --- |
| README 列了但实际不存在 | 无 |
| 根目录实际存在但 README 未列 | 无 |

树中共 31 个条目，全部核对。

## 三、AGENTS.md §3 路径歧义

`数据与 AI Agent` 一行由 `src/backend/app/services/`、`workers/`、评测资产 改为 `src/backend/app/services/`、`src/backend/app/workers/`、`prompts/`、`evaluation/`、`datasets/`。

裸 `workers/` 既可读成仓库根的 `workers/`，也可读成 `src/backend/app/workers/`；`docs/architecture.md` 源码映射表写的是后者，统一成后者。所有权表里的路径歧义就是所有权冲突。「评测资产」是描述性说法，替换为 S-04 建好的真实路径，并补上 `prompts/` 的归属。

验收：§3 的 12 个路径**全部真实存在**；其中 `src/backend/app/services/`、`src/backend/app/workers/`、`src/contracts/`、`src/frontend/` 与 `architecture.md` 源码映射表逐字一致。

## 四、一致性核对（只报告，未修改）

| 检查 | 结果 |
| --- | --- |
| `.env.example` 变量数 | 30 |
| `docs/integrations.md` 未收录的变量 | 无 |
| 文档中出现但 `.env.example` 没有的变量 | 无 |

**逐项对齐，无差异，M0-05 负责人无需处理。**（M0-05 仍因本机无容器运行时而 BLOCKED，与本次核对无关。）

## 五、未解决 / 建议

1. **`docs/architecture.md` 源码映射表不含 `tests/`、`prompts/`、`evaluation/`、`datasets/`。** 这四个目录已在 AGENTS.md §3 有归属，但架构文档的映射表只覆盖 `src/`。不算矛盾，但补上会更完整——该文件不在本次可改清单内，建议由产品/协调 Agent 处理。
2. **hook 的四条残留缺口**（见上），建议单独立任务；特别是第 4 条会影响后续 Agent 写文档，应写进协作约定。
3. **本次未在 `docs/tasks/` 登记 S-05 行**：`docs/tasks/` 在本次禁止触碰清单内，需协调 Agent 补一行，证据指向本文件。

## 回滚

只改一个 hook 与两份文档，无数据、无依赖、无契约影响。用 `git revert` 撤回本次提交即可；手工回滚则还原三个文件。

注意：还原 hook 会同时恢复三个绕过缺陷。若只是想临时关掉拦截，改 `.claude/settings.json` 的 PreToolUse 配置，而不是把 hook 退回有缺陷的版本。

## 下一位 Agent 的首个动作

- **任何 Agent**：hook 现在会真正拦住组合命令里的破坏性片段。若被误拦（引号内含分隔符、或 heredoc 正文含命令示例），**改写命令或改用 Write 工具**，不要去改 hook 放宽规则。
- **协调 Agent**：补 S-05 任务行；考虑把 `tests/`、`prompts/`、`evaluation/`、`datasets/` 补进 `docs/architecture.md` 的源码映射表。
