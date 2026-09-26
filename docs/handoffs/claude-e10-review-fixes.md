# E10 审查修正交接（Claude）

- 负责人：Claude；分支 `claude/project-thread-9f2hs5`，基线 `codex/e10-fusion-design@0388853`（PR #253 head）。
- 范围：PR #253 审查发现的 4 个非阻塞问题，修正后并入 PR 分支再合并。

## 交付

1. `src/backend/app/services/fusion/judge.py`：定义归并提示词的 `definitions` 每侧带 `name`，`name` 变量在两侧不同名时为「左 / 右」；原先只传左侧名称。提示词正文与变量未变，版本与 MANIFEST 摘要不动。
2. 同文件：`FusionJudge` 新增可选 `timeout_seconds`，与 E05 抽取/补漏一致地写入每次 `ModelRequest`（含修复调用）；默认 `None` 保持原行为。
3. `docs/decisions.md`：删除 ADR-017「签收」与「勘误」之间误插的空行，恢复原列表。
4. `docs/superpowers/plans/2026-09-26-e10-fusion-judge.md`：移除 Codex 专用 skill 引用；目录保留，因 `docs/tasks.md` E10 行把设计与计划文件列为交付物。
5. `tests/backend/test_e10.py`：先加两条红例（两侧名称进入归并提示词、超时传到每次请求），修正后转绿。

## 验证

| 命令 | 结果 |
| --- | --- |
| `.venv/bin/python -m pytest tests/backend/test_e10.py -q`（修正前） | 2 failed, 26 passed |
| 同上（修正后） | 28 passed |
| `.venv/bin/python -m pytest tests/backend -q` | 2683 passed, 1 个既有警告 |
| `PATH=<openapi-typescript@7.4.4>:.venv/bin:$PATH ./scripts/verify.sh` | `PASS contracts gate`，`Scaffold verification passed.` |
| `git diff --check` | exit 0 |

## 接口、风险、下一步

- 接口仅新增可选关键字参数，E12 调用方可传入阶段超时；无 DTO、迁移或依赖变更。
- 回滚：撤销本提交即可。
