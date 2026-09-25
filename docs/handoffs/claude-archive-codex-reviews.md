# Claude 交接：Codex 审查记录入库与本地遗留清理

- 日期：2026-09-25
- 分支 / base：`claude/archive-codex-reviews` / `origin/main@8eeac3b`
- 角色：协调方，按 ArvinHan「处理掉」主目录与 Codex B07 工作目录遗留改动的要求执行

## 背景

`docs/claude-review-workflow.md` 第 6 条规定，Codex 审查循环只把报告写在主目录，不提交。任务板原注明「由 Codex 自行提交」，但一直没有入库，同时主目录 `main` 已落后 `origin/main` 221 个提交。多份 Claude 交接用「主目录 `docs/reviews/…`（尚未入库）」引用这些报告。

## 交付物

| 文件 | 来源 | 处理 |
| --- | --- | --- |
| `docs/reviews/codex-claude-*.md`（24 份，REVIEW-03～26） | 主目录未跟踪文件 | 原样复制入库，内容未改 |
| `docs/handoffs/codex-review-03.md`～`26.md`（24 份） | 同上 | 原样复制入库。这些是 Codex 的交接，Claude 只做搬运，没有代写 |
| `docs/reviews/claude-review-state.json` | 主目录的修改版（`updated_at` 2026-09-25T05:05Z，main 上是 2026-09-23） | 以主目录版本覆盖 |
| `docs/tasks.md` | 主目录修改里的 REVIEW-03～26 共 24 行 | 追加到「Claude 审查批次」表末；原「由 Codex 自行提交」一行改为已代为入库 |
| `.gitignore` | — | 新增 `~$*`，忽略 Office 锁文件（主目录里的赛题 docx 在 Word 中打开时会生成 `~$…docx`） |

有意**没有**带入的内容：主目录 `docs/tasks.md` 里的「B07 IN PROGRESS」行和「B07 执行约定」。那是认领时的旧状态，B07 已由 PR #187 完成，main 上已有 DONE 记录。

入库前用正则扫描了疑似密钥（`api_key`、`secret`、`token`、`password`、`sk-…`），没有命中。

## 主目录同步（本 PR 合并后执行）

1. 把主目录的未跟踪文件和两个修改文件备份到会话临时目录。
2. 逐个确认与 `origin/main` 的入库版本字节一致（`tasks.md` 除外，它只有 REVIEW 行和过时的 B07 内容）。
3. 移除本地副本，再 `git pull --ff-only`。

## Codex B07 工作目录

`~/.codex/worktrees/b07-contract-gate/SmartSketch`（游离 HEAD `148fa9f`）里有 2026-09-24 13:47 的 B07 草稿，与最终合入的四个文件都不同，已被 PR #187 取代。

- 已用临时索引生成快照提交，存为**仅本地**分支 `archive/b07-contract-gate-draft`（`938c80c`），包含未跟踪的 `tests/tooling/`。工作目录本身没改。
- 删除该工作目录被权限拦下（不可逆本地删除），**待 ArvinHan 决定**。确认后执行：

```bash
git worktree remove --force /Users/arvinhan/.codex/worktrees/b07-contract-gate/SmartSketch
```

## 验证

见 PR 描述：`./scripts/verify.sh` 与 `git diff --check`。

## 风险

- 如果 Codex 审查自动化还在运行，下一轮会继续在主目录写 `claude-review-state.json` 和新报告。主目录同步后它读到的是入库版本，内容与它最后写入的一致，不影响续跑；但新报告仍会以未跟踪文件出现，需要定期入库。
- 已入库的旧交接仍写着「主目录 `docs/reviews/…`（尚未入库）」，属于历史记录，没有改；现在按仓库内同名路径就能找到。

## 回滚

还原本 PR 即可。B07 草稿可从本地分支 `archive/b07-contract-gate-draft` 找回。
