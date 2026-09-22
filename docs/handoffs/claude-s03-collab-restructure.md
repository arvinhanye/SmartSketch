# Claude 交接：S-03 协作写争用改造

- **状态**：DONE
- **日期**：2026-09-22
- **范围**：把 `docs/decisions.md`、`docs/tasks.md`、`scripts/verify.sh` 三个「每个 Agent 每个任务都要改」的单文件拆成目录；`verify.sh` 改造为分发器，必需文件清单改为按领域分文件的数据驱动清单；删除脆弱断言；同步流程文档。

## 已交付

| 文件 | 改动 |
| --- | --- |
| `docs/decisions/` | 新建。5 条 ADR 一条一文件 + `README.md` 索引。原 `docs/decisions.md` 已 `git rm` |
| `docs/tasks/M0.md`、`M1.md`、`open-questions.md` | 新建。任务按里程碑分文件，未决问题独立成文件 |
| `docs/tasks.md` | 退化为索引 + 状态约定 + 列含义 + 新增任务规则 |
| `scripts/verify.sh` | 改造为分发器，只负责依次调用四个子脚本并汇总 |
| `scripts/verify/{structure,backend,frontend,contracts}.sh` | 新建。后三者未初始化时打印 SKIP 并 `exit 0` |
| `scripts/verify/manifests/{core,backend,frontend,contracts}.txt` | 新建。必需文件清单数据化，每个 Agent 只改自己领域那份 |
| `AGENTS.md` | §2 认领路径、§3 所有权 + 新增「写争用规则」小节、§5 完成标准、§6 决策路径 + 分支合并提案 |
| `CLAUDE.md`、`README.md` | 同步新路径与新门禁描述 |
| `docs/handoffs/claude-s01-*.md`、`claude-m0-05-*.md` | 各追加一行 S-03 路径变更说明；历史记录原文未改写 |

未触碰 `src/`、`specs/`、`docs/product.md`、`docs/architecture.md`、`docs/integrations.md`、`.env.example`、`.claude/hooks/`。

## 迁移完整性

- **ADR**：按 `^## ADR-(\d+)：` 正则切分，不假设数量，实际迁移 5 条（S-01 追加的 ADR-004、ADR-005 也在内）。逐行比对原文与拆分结果：**非空行 56 vs 56，完全一致**，无改写。
- **任务**：原 16 个 ID（M0-01/02/03/04a/04b/05/06、S-01、M1-01～05、D-01/02/03）**全部保留，零丢失**。新增 S-03、M0-07、D-04、D-05、D-06。
- **新增两列**：截止日期、阻塞关系，覆盖全部任务行。

## 截止日期与 S2 对照

按你提供的 S2 表 4.2 填写。**仓库编号与 S2 编号含义不同**，对照已写进各里程碑文件开头：

| | 仓库含义 | 对应 S2 阶段与窗口 |
| --- | --- | --- |
| 仓库 M0 | 协作与应用骨架 | 只对应 S2 **M0 需求与设计**（09-16 ～ **09-19**）交付物中的「项目骨架 / 开发环境」一项；S2 M0 的需求确认、方案初稿、系统设计不在本任务板上 |
| 仓库 M1 | 课程资料到草稿图谱 | 横跨两段：M1-01/02/04 与 M1-03 抽取部分 → S2 **M1 主链路打通**（09-20 ～ **09-26**）；M1-03 融合消歧、M1-05 图谱编辑 → S2 **M2 功能完善**（09-27 ～ **10-02**） |

**逾期情况（今日 2026-09-22）**：

- 仓库 M0 的窗口 09-19 已关闭，**逾期 3 天**，仍有 6 项未完成（M0-02、M0-03、M0-04a、M0-04b、M0-05、M0-06）。它们同时是 S2 M1 的前置，实际必须在 09-26 前补齐。
- **D-01（演示课程脱敏资料）约定「M1 开始前」，S2 M1 已于 09-20 开始，逾期 2 天**，已在 open-questions.md 标为「逾期」。M1-02 起的所有任务都需要真实资料才能验收。
- S2 还有 M3 测试与优化（10-03 ～ 10-05）、M4 材料定稿（10-06 ～ 10-08），本仓库任务板完全不覆盖，已记为 D-06。

## 门禁改造的取舍

1. **删除 `grep 'M0-01 | DONE'`**。它检查的是「任务板自称完成」，本身没有验证价值，却把 CI 绑在一张 Markdown 表格的精确空格上。已实测：给 M0-01 后加一个对齐空格，旧断言即失败。
2. **`PREREQUISITE` 断言保留但改为双标记全文匹配**：`grep -qiE 'PREREQUISITE'` 加 `grep -qiE 'DAG|无环|成环|有向无环'`，不区分大小写、不锚定行首或表格格式。校验的是「架构文档确实说明了无环约束」这个事实，而不是它写成什么格式。
3. **`.claude/settings.local.json` 的忽略检查改用 `git check-ignore -q`**，不再 grep `.gitignore` 的某一行。顺带把 `.env` 也纳入同一检查。
4. **分发器跑完全部子脚本再汇总**，不首错即停——一次就能看到所有问题。任一子脚本非零即整体非零。
5. **清单覆盖不减反增**：原 24 项必需文件 → 现 28 项（新增 `docker-compose.yml`、`docs/tasks/` 三个文件，`docs/decisions.md` 换成 `docs/decisions/README.md`）。

## 已运行命令与真实结果

```text
./scripts/verify.sh
  structure  → core 24 / backend 2 / frontend 1 / contracts 1，合计 28 项，✓ 结构检查通过
  backend    → SKIP：后端尚未初始化（M0-03）
  frontend   → SKIP：前端尚未初始化（M0-02）
  contracts  → SKIP：契约真源尚未创建（M0-04a）
  → All verification checks passed.   [exit=0]

bash -n scripts/verify.sh scripts/verify/*.sh   → passed
/usr/bin/env bash --version                     → GNU bash 3.2.57（macOS 自带，脚本在此版本下实测可用）

四个子脚本单独运行 → 全部 exit=0，后三者打印 SKIP

排版编辑测试：把 "| M0-01 |" 改成 "| M0-01  |"（列对齐）
  旧断言 grep 'M0-01 | DONE'  → 失败（这正是过去会让门禁红掉的情形）
  新门禁 ./scripts/verify.sh  → PASS  ✓

反向测试（确认门禁不是空转）：
  临时移走 docs/tasks/M1.md → exit=1，✗ 缺少必需文件（core 清单）：docs/tasks/M1.md
  临时损坏 .mcp.json        → exit=1，✗ JSON 无法解析：.mcp.json
  两项均已还原，复跑 → All verification checks passed.

ADR 迁移逐行比对 → 非空行 56 vs 56，✓ 完全一致
任务 ID 迁移检查 → 原有 16 项缺失 0 项
```

## 未解决：一处越界引用

`src/contracts/README.md:3` 仍写着「格式决策见 `docs/decisions.md` 的 ADR-004」，该文件已删除，这是一条**真实失效的引用**。

本任务明确禁止触碰 `src/`，且 `src/contracts/` 按 AGENTS.md §3 与 ADR-004 归后端 Agent 单一写入。**我没有改它**，而是登记为 **M0-07**（Backend Agent，截止 09-26）。在它修掉之前，全仓库 `grep 'decisions.md'` 还会有这一条命中。

其余命中均非失效引用：`AGENTS.md:40` 是「写争用规则」里描述历史的正文；两份旧交接是当时的真实记录，已各追加一行路径变更说明而非改写；`M0-07` 那行是任务描述本身。

## 分支与合并（提案，未生效）

按要求写成 5 行放进 `AGENTS.md` §6，**没有自行拍板**：`main` 是否设保护、谁有合并权、是否需要 remote，全部作为 **D-04** 留给项目负责人确认。提案本身在标题就标明「未生效」。

## 风险与未完成项

1. `backend.sh` / `frontend.sh` 在**已初始化**时只打印占位提示并 `exit 0`，不是真门禁。M0-02 / M0-03 落地时，对应 Agent 必须把 pytest / vue-tsc / lint 填进去，否则会形成「门禁全绿但什么都没测」的假象。已在脚本内写明。
2. 可以给 `structure.sh` 加一条「全仓不得出现指向 `docs/decisions.md` 的引用」断言，但那会因为 M0-07 未完成而立刻红掉，所以本次没加。M0-07 完成后值得补上。
3. ADR 编号目前靠人工取最大值 +1，两个 worktree 并行时可能撞号。`docs/decisions/README.md` 写了处理方式（后合并者改号），但没有自动化检查。
4. 截止日期全部来自 S2 表 4.2，其中的年份按当前日期推定为 2026；若 S2 实际指向其他年份需整体修正。

## 回滚

只改文档与脚本，无数据影响。需要撤回时：

```bash
git revert <本次提交>          # 推荐：ADR 与任务表会一并恢复为单文件
```

手工回滚则需：恢复 `docs/decisions.md`（内容 = `docs/decisions/ADR-*.md` 按编号顺序拼接，把 `# ADR-` 改回 `## ADR-` 并补回顶层标题）、把 `docs/tasks/` 三个文件合回 `docs/tasks.md`、还原 `scripts/verify.sh` 并删除 `scripts/verify/`，再回退 `AGENTS.md`、`CLAUDE.md`、`README.md`。不要使用全局重置或清理命令。

## 下一位 Agent 的首个动作

- **任何 Agent**：认领任务改 `docs/tasks/<里程碑>.md` 里自己那一行，**不要重排整张表**；新决策新建 `docs/decisions/ADR-<编号>-<slug>.md`，不要追加进别人的文件。
- **Backend Agent**：顺手做掉 M0-07（一行引用修正），然后按 M0.md 的阻塞关系走 M0-03 → M0-04a。补自己的门禁只需改 `scripts/verify/backend.sh` 与 `manifests/backend.txt`，不必碰 `scripts/verify.sh`。
- **Frontend Agent**：同理，只改 `scripts/verify/frontend.sh` 与 `manifests/frontend.txt`。
- **项目负责人**：确认 D-04（分支与合并）与 D-01（已逾期的脱敏资料），两者都在挡住并行协作与 M1 验收。
