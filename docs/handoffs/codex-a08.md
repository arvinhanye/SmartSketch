# A08 交接：推荐评分与跨版本进度（第 3 轮复审通过）

- `task_id`: A08；`status`: R01～R14 第 3 轮复审通过，无新 P1/P2；待 §7 产品签收；R15 不在本轮范围。
- `worktree`: `/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/codex-a08-learning-path`；`branch`: `codex/a08-learning-path`；base HEAD `1a47eb2`。
- `审查依据`: 第 1 轮 `claude/codex-a08-check-ade85c@8901371` 报告、第 2 轮 PR #13 `dc0bef8` 的 `docs/reviews/claude-codex-a08-r2-2026-09-23.md`、第 3 轮 `claude/codex-a08-check-0ae6d7@acb257c` 复审（R11～R14 通过）与已签收 ADR-014。ADR-014 已随 `origin/main@6881ffe` 合入本分支，不另造同号决定。
- `文件锁/范围`: `specs/learning-path.md`、`docs/atomic-task-plan.md` 的 B12/I05 行、`docs/atomic-tasks.json` 的 B12/I05 `acceptance`、`docs/tasks.md` 的 A08 行及下方说明、本交接。均在本 worktree，未修改 main、其他 worktree 或 `src/`。

## 输入、输出、依赖、风险

- 输入：S2 §6.4.7、A04 V3/V8/V9 与 ADR-012、A02 三态进度、候选 YAML 真源、Claude A08-R01～R14、ADR-014。
- 输出：LP-1～19 的可学/评分/进度投影/批量写入规格，及 B12/I05 在 Markdown 与 JSON 中一致的验收；无 DTO、仓储、迁移或发布快照代码变更。
- 依赖：B08/B12 迁移公开错误与响应；F10/B11/G04/G06 在谱系存放位置签收后实现版本化谱系。
- 风险：§7 的缺值 0.5、权重来源、推荐上限、进度响应字段名与 `updated_at` 可空语义，以及显式降级覆盖继承、谱系存放位置仍未签收。已签收的 ADR-014 只确立中心度分母和最高状态读时继承，不等于这些细则已批准。R15 涉及细则 1，提案文字保持不变。

## Claude R01～R10 修复映射与逐项核对

| 报告项 | 修订位置 | 核对证据 |
| --- | --- | --- |
| R01 空发布图不可达 | §4、§6 LP-11；`docs/atomic-task-plan.md` B12 行 | A04 V3 `empty_graph` 阻断发布；回滚只复制已提交版；`V=∅` 归 5xx 完整性故障，无 `no_graph` 正常态。 |
| R02 中心度分母 | §3、LP-14 | ADR-014 用 `(in+out)/(N−1)`；星形中心 1、叶子 `1/(N−1)`，`N≤1` 为 0。 |
| R03 合并进度 | §1、§5、LP-9、§7 | 主节点沿用 `primary_id`，谱系链读时取最高状态，来源重现即各用自身原始行；显式降级与谱系存放列为未签收细则。 |
| R04 投影/外课冲突 | §1、§5、LP-12 | `recommend` 只接收 `V` 内投影；仓储用本课程全部 committed ID 并集区分 dormant 与脏行，脏行告警忽略；写入外课 ID 整批拒绝。 |
| R05 章节层级 | §3、LP-15 | `parent_id` 树/森林前序，每层 `(order,chapter_id)`；单节点仅一个可空 `chapter_id`，删去跨章假设。 |
| R06 学生图损坏 | §1、§4、LP-12 | 5xx + 诊断 ID；环/悬空 ID 仅在服务端日志，不复用教师 409。 |
| R07 浮点确定性 | §1、§3、LP-6 | 权重校验后原样使用，按 `u→i→c→e` 顺序求和，未舍入精确同分才进入次级键。 |
| R08 进度接口 | §5、LP-8、LP-16 | `ProgressUpdate[]` 整批原子、同批重复拒绝；历史行保留为仓储断言，不虚构 `GET ?version`。 |
| R09 量纲与字段 | §3、§7 | 使用现有 `importance`/`difficulty` `[0,1]` 基线；仅缺失中性值待签收。 |
| R10 交付过程 | 本文件、任务板 A08 行 | A08 行移至 A07-R01 后；本表给出逐项核对，文件与差异指纹见下，不再声称无证据的“8/8 PASS”。 |

## Claude 第 2 轮 R11～R14 修复映射

| 报告项 | 修订位置 | 核对证据 |
| --- | --- | --- |
| R11 进度接口原始/有效状态 | §5、LP-17/18、§7 | GET/PUT 对 V 每个节点回有效 `status`、可空 `own_status`、`inherited_from[]`；`updated_at` 为自身行时间，无自身行为空；PUT B=unknown 被 A=mastered 继承覆盖可机读。字段和时间语义交 B12 落地。 |
| R12 谱系终止与合法性 | §5、LP-19 | 整链无 V 节点时来源 dormant；每来源至多一个主节点、谱系无环，否则 5xx 与诊断 ID。 |
| R13 wire 舍入 | §3、`docs/atomic-task-plan.md` B12 行、JSON B12 `acceptance` | wire 传未舍入 double，加权分量按 `u→i→c→e` 求和逐位等于 `score`，只在前端展示舍入；两份 B12 验收一致。 |
| R14 任务清单副本 | `docs/atomic-task-plan.md` B12/I05 行、JSON B12/I05 `acceptance` | B12 Markdown/JSON 同文；I05 两份均明确未发布 404、全掌握与已提交图损坏 5xx。JSON 只改两条 `acceptance` 字符串。 |

## 验证与指纹

| 核对 | 结果 |
| --- | --- |
| `./scripts/verify.sh` | exit 0；`block-dangerous hook tests passed.`、`Scaffold verification passed.` |
| `git diff --check` | exit 0。 |
| `python3 -m json.tool docs/atomic-tasks.json > /dev/null` | exit 0。 |
| `grep -nP "[ \t]+$" specs/learning-path.md docs/handoffs/codex-a08.md` | exit 2：本机 BSD `grep` 不支持 `-P`；改用下行等价检查。 |
| `grep -nE '[[:blank:]]+$' specs/learning-path.md docs/handoffs/codex-a08.md` | exit 1，无匹配（两个未跟踪新文件也已覆盖）。 |
| `grep -rn -e 无图 -e 暂无图 docs/atomic-task-plan.md docs/atomic-tasks.json` | exit 1，无匹配。 |
| B12/I05 验收与 LP 编号核对 | Python 解析 JSON 并逐字对比两行 Markdown `acceptance`：B12、I05 均一致；LP-1～19 连续且各一行；exit 0。此为文档检查，不代表 I01～I06 实现测试。 |
| `specs/learning-path.md` SHA-256 | `1a9c54780c5364ef31c78f165b5f564cbd07bb720649dc4f228ee593373767a3` |
| `docs/atomic-task-plan.md` SHA-256 | `b6d778208c967f16247aa89027ad52edf8b73fa741224a7429abd053d505c694` |
| `docs/atomic-tasks.json` SHA-256 | `690045e13423c234e994b41237640090289980d25c79f57ed45845c3d979042d` |
| `docs/tasks.md` | A08 行已更新为第 3 轮复审通过；提交前以 `git diff --check` 核对。 |

## 下一步与回滚

1. Claude 第 3 轮已复审 R11～R14，结论为均已修复、无新 P1/P2；报告在 `claude/codex-a08-check-0ae6d7@acb257c`，该审查分支的报告是否另行入库由协调方处理。
2. 产品负责人签收 §7 的缺值中性值、权重来源、推荐上限、进度响应新增字段名及 `updated_at` 语义，以及 ADR-014 两项细则；R15 留待细则 1 签收前处理。谱系位置若采纳快照字段，先修订 ADR-012 与快照格式，再交 F10/B11/G04/G06/I01 实现。
3. 回滚仅定向撤销本轮五个文档文件的 A08 改动；无迁移、依赖升级、数据写入或密钥变更，不触碰其他工作树/未提交内容。
