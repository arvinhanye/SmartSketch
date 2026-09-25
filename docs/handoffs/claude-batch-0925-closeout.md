# Claude 交接：2026-09-25 批次收尾（B12、F05、E02、D06、D07、C02 与 FIX-MIGRATE-LEASE）

- 状态：DONE，全部已合入 main；本文件供 Codex 与后续任务接手
- 合并后基线：`main@a7a0be0`（PR #206 合并提交）
- 协调方：ArvinHan（Claude 执行）；各任务由 Claude 子代理实现，协调方复核、同步分支并合并

## 1. 已合入

| 任务 | Issue | PR | 合并提交 | 交接 |
| --- | --- | --- | --- | --- |
| B12 迁移进度和推荐契约 | #54 | #202 | `d633160` | `docs/handoffs/claude-b12.md` |
| F05 DAG 环检测纯函数 | #97 | #203 | `b4ed883` | `docs/handoffs/claude-f05.md` |
| D07 重复页眉页脚清洗 | #76 | #204 | `003dd20` | `docs/handoffs/claude-d07.md` |
| E02 模型接口和 fake 适配器 | #82 | #207 | `aaae534` | `docs/handoffs/claude-e02.md` |
| D06 PDF 标题判定 | #75 | #208 | `1ffda90` | `docs/handoffs/claude-d06.md` |
| FIX-MIGRATE-LEASE 迁移器租约检查 | — | #212 | `4e42a5d` | `docs/handoffs/claude-fix-migrate-lease.md` |
| C02 课程和成员仓储 | #59 | #206 | `a7a0be0` | `docs/handoffs/claude-c02.md` |

六个 issue 均已关闭并标 `status:done`。C02 原分配 539210（09-24 回复“正在做”，远端无分支），经 ArvinHan 授权转由 Claude 执行，已在 #59 通知对方。

## 2. 合并后 main 复核（`a7a0be0`）

| 命令 | 结果 |
| --- | --- |
| `PYTHONPATH=<worktree>/src/backend <venv>/bin/python -m pytest tests/backend -q` | 1002 passed |
| `python3 -m pytest tests/contracts tests/tooling -q` | 269 passed |
| `./scripts/gen-contracts.sh --check` | exit 0 |
| `./scripts/verify.sh` | exit 0 |
| `docs/tasks.md` 冲突标记 | 0 |

venv 按 `src/backend/pyproject.toml` 的 `[test]` 依赖安装；系统 `python3` 未装后端包时，`python3 -m pytest tests/backend/...` 会报 `No module named 'app'`（E01、D05 起一直如此）。**`PYTHONPATH` 须用绝对路径**：`test_e02.py` 的跨进程用例以 `tests/backend` 为 cwd 起子进程，相对路径会失效。

## 3. 合并前发现并处理的问题

1. **B12 × B07 门禁夹具**：B12 把 `test_b12.py` 接入 `scripts/verify/contracts.sh`，但 `tests/tooling/test_b07.py` 的 `shell_workspace` 夹具只为已接入的契约测试放占位，缺 `test_b12.py`，dispatcher PASS 用例返回 1。`verify.sh` 与 CI 都不跑 `tests/tooling`，所以未检出。已在 #202 补一行。**后续接入门禁的契约任务（B14、O02、O05 等）须同步更新该夹具，并跑 `tests/tooling`。**
2. **C01 迁移器 × C06 任务表**：C01 的 `_check_no_live_leases` 要查 `processing_tasks.lease_expires_at`，C06（#209）建表时尚无租约列（C09 才加），导致 003 之后任何迁移都报 `Cannot inspect processing_tasks lease state`。#212 改为只检查有租约列的表；有列但查询失败仍拒绝迁移。**C09 加租约列时，请补一条真实表上“有效租约阻止迁移”的回归**。
3. **迁移编号撞号（D-10）**：C06 先合入占用 003，C02 改为 `004_courses.sql`。C06 与 C02 原本都把迁移全集写死在断言里，已改为只断言本任务相关前缀或临时目录：
   - `test_c13.py`：用只含 001、002 的临时目录；
   - `test_c06.py`：夹具只断言前三项；
   - `test_c02.py`：用只含 001～004 的目录。

   **后续新增迁移（C09、C16、G02 等）不应再断言真实迁移目录的全集。**
4. **任务板追加冲突**：本批与 D-11（#205）、C14（#210）、F01（#211）都在 `docs/tasks.md` 末尾追加小节，多次冲突，均按“两节都保留、先合入的在前”解决。批次小节在五个分支中先统一为同一版本，再合并，避免逐行冲突。

## 4. 待 ArvinHan 决定（未决）

| 来源 | 问题 | 何时必须定 |
| --- | --- | --- |
| B12 | 学生读路径完整性错误的公开码：暂用 `INTERNAL_ERROR` + `details.diagnostic_id`；是否改专用码、是否与问答 `details.request_id` 统一字段名 | I02/I05 前 |
| B12 | `PUT /progress` 的 `kp_id` 不在绑定发布版时，整批拒绝用 422/404/409 中哪个，以及 `details` 形状 | I02 前 |
| B12 | 确认破坏性变更：进度响应改为 `{graph_version, entries}`；移除推荐接口 `target`/`path`（目标路径交 O02） | B15/H 组消费前 |
| E02 | 模型接口为同步形式（无 ADR 规定同步/异步）；`LLM_MODE=fake` 时模型 ID 由谁填；缓存键用请求还是响应的模型 ID | E03/E04/D09 前 |
| D06/D07 | D11 按“提取 → D07 清洗 → D06 判定”串联；`pdf/1+headings/1` 与 `cleanup/1` 如何并入 `parser_version` | D11 前 |
| C02 | `courses.published_version_id` 是否引用 G02 版本表（SQLite 补外键需重建表）；`docs/architecture.md` 是否补登 `users`、`course_members` | G02 前 |

## 5. 已知风险

- datamodel-codegen 0.26.3 不强制“必填但可空”（B12 的 `own_status`、`updated_at` 生成为默认 `None`），I02 不能靠 Pydantic 发现缺字段，可交 B14 处理。
- `tests/contracts/test_b11.py` 未接入 `scripts/verify/contracts.sh`（B12 子代理观察，未处理）。
- D07 会误删页边带内最外侧、只有数字不同且跨 3 页以上的正文行。

## 6. 下一步可认领

- **B14**（依赖 B09～B13 已齐）：可占用 `api.v1.yaml` 与生成物文件锁。
- **F06**（依赖 F05）、**E03/E04**（依赖 E02）、**C03/C04/C15**（依赖 C02）、**C09**（见上文第 3 节第 2 条）。
- 本批遗留的远端分支 `claude/batch-0925-claims`（认领提交 `38ef62d` 已随各 PR 进入 main）可删除。

## 回滚

各任务独立回滚：对相应 PR 的合并提交执行 `git revert -m 1 <sha>`。C02 涉及迁移 004，回滚方法见 `docs/handoffs/claude-c02.md`，用 `backups/*-before-004.sqlite` 恢复。若回滚 #212，003 之后的迁移将再次无法应用。
