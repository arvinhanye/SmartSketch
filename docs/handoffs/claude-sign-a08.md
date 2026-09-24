# 交接：签收 A08 §7 与 ADR-014 两项细则（ADR-014 修订 1）

- `task_id`: A08 签收
- `status`: 完成。ArvinHan 于 2026-09-23 签收，记为 ADR-014 修订 1（决定 5～10）。
- `worktree`: `/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/codex-a08-check-0ae6d7`，分支 `claude/a08-signoff`，base `f9dfc8f`（PR #19 合并后的 main）。

## 签收内容

| 项 | 决定 | 由谁选定 |
| --- | --- | --- |
| 缺失属性中性值（决定 5） | `importance`/`difficulty` 缺失时取 0.5 | 按 §7 原提案签收 |
| 权重来源（决定 6） | 四个 `RECOMMEND_WEIGHT_*` 环境变量，缺省为 S2 值；全站统一，不做课程级配置 | ArvinHan 从三个方案中选定 |
| 推荐上限（决定 7） | 默认 10，最大 50 | 按 §7 原提案签收 |
| 进度接口字段（决定 8） | GET/PUT 返回 V 中全部节点；有效 `status`、`own_status`、`inherited_from[]`、可空 `updated_at` | 按 §7 原提案签收 |
| 细则 1：显式写入覆盖继承（决定 9） | 以来源“本次连续归属”的起算版本为界：主节点自身记录写在其后，就覆盖该来源 | ArvinHan 从三个方案中选定（R15 的两种读法加“不设覆盖”） |
| 细则 2：谱系存放位置（决定 10） | 发布快照节点字段 `merged_from` | 按 §7 原提案签收 |

以下内容由 Claude 从上述决定推导，未单独询问。签收人如有异议，请修改 ADR-014 修订 1：

- 四个权重变量**成组**校验：都不设或都为空时用缺省值，只设一部分则拒绝启动。沿用 `LLM_FALLBACK_*` 的“全空或全填”惯例。
- 变量名 `RECOMMEND_WEIGHT_UNLOCK`、`_IMPORTANCE`、`_CHAPTER`、`_EASE`。
- 被覆盖的来源不列入 `inherited_from[]`。§5 原文写的是“实际归属到此节点且有原始行的来源”，签收后收窄为“未被覆盖的来源”，这样 `inherited_from[]` 与 `status` 一致。
- 覆盖按来源逐个判定；起算版本在读取时计算，可按 `version_id` 缓存，不写入快照（快照在提交前生成，此时拿不到提交序号）。
- 写入序号与提交序号取自 SQLite 中同一个单调序列。这是细则 1 能够判定的前提，具体落在 ADR-012 的下一次修订和 C01/I01。
- 推论：合并生效后，学生对主节点的任何显式写入都会覆盖当前全部来源。所以原 LP-18（“写 unknown 仍为 mastered”）改为“写 unknown 即为 unknown”，“被来源顶回”只出现在主节点记录写于合并之前的情形。

## 交付物

- `docs/decisions.md`：ADR-014 开头加修订说明，文件末尾新增“ADR-014 修订 1”（背景、评估方案、决定 5～10、后果、推翻条件、签收）。
- `specs/learning-path.md`：
  - 状态行改为已签收；
  - §1 权重来源与 `limit`，§3 缺失中性值；
  - §5 新增覆盖规则，`inherited_from[]` 与响应示例按新规则改写，合并行加覆盖说明；
  - §6 修订 LP-5、LP-9、LP-18，新增 LP-20（R15 的回滚后再合并序列）；
  - §7 改为“接口与已签收事项”。
- `docs/integrations.md`：新增“学习推荐权重”一节，在“启动校验”中加一条，在名称来源中补一句。
- `.env.example`：新增四个权重变量，样例为 S2 缺省值。
- `docs/tasks.md`：
  - A08 行改为 DONE，第 3 轮复审的引用改为 PR #17 `acb257c`（原引用写的是本地分支名）；
  - 新增“A08 签收”行及后续项；
  - REVIEW-A08-R2 行标注已签收。

## 已运行命令与结果

| 命令/核对 | 位置 | 结果 |
| --- | --- | --- |
| `git switch -c claude/a08-signoff origin/main` | 本 worktree | 基于 `f9dfc8f`，原分支 `claude/codex-a08-check-0ae6d7` 的内容已全部在 main 中 |
| `git diff origin/main...origin/claude/fix-r01-r02`、`...origin/claude/a10-integration-map` | 本 worktree | 确认 #16、#18 在 `decisions.md`、`integrations.md` 中的改动位置（见“风险”） |
| `grep` 规格中的“待签收/尚未签收/提案/待 §7/最高值规则” | 本 worktree | 无残留 |
| `./scripts/verify.sh` | 本 worktree | exit 0 |
| `git add -N` 新交接后执行 `git diff --check` | 本 worktree | exit 0 |
| `grep -nE '[[:blank:]]+$'` 检查改动的文件 | 本 worktree | 无匹配 |
| Python 核对 `.env.example` 与 `integrations.md` 的四个权重；LP 编号 | 本 worktree | 值一致，和为 1；LP-1～20 连续 |
| 临时索引 + `git commit-tree` + `git merge-tree` 分别试合并 #16、#18 | 本 worktree | 见“风险与待决” |

## 接口/数据变更

只在规格中定义，本次不改契约文件或代码：

- 新增环境变量四个；
- `ProgressEntry` 新增字段交 B12；
- 进度行写入序号与版本提交序号交 ADR-012 的下一次修订和 C01/I01。

## 风险与待决

- **合并冲突**（用临时提交对象 `git merge-tree` 实测，没有移动任何分支）：
  - 与 #18：`decisions.md` 末尾冲突。#18 追加 ADR-016，本分支追加 ADR-014 修订 1，后合并的一方保留两段，顺序为 ADR-014 修订 1 在前、ADR-016 在后。
  - 与 #16：`tasks.md` 末尾冲突，两边都追加了任务行，保留两边即可。`decisions.md` 与 `integrations.md` 能自动合并。
- **谱系尚未落库**：`merged_from` 和共享序列都要等 ADR-012 修订后才能实现；在此之前 F10/B11/G04/G06/I01 不应开工。
- **已知取舍**：推翻条件 1 描述了“取消了又回来”的情形——学生降级主节点后，教师回滚再合并，来源的状态会重新参与取最高。这是所选方案的有意结果。

## 下一位 Agent 的首个动作

由 A04 负责人修订 ADR-012：在快照节点中加入 `merged_from` 并纳入摘要，在版本提交事务中从共享序列取提交序号。编号排在 #16 的 ADR-012 修订 2 之后。

## 回滚

对本分支的提交执行 `git revert`，即可撤销 ADR-014 修订 1 以及规格、集成文档、`.env.example`、任务板的相应改动。本次没有数据或依赖变更。

## 第二轮：Codex REVIEW-14 修复（A08S-R01 / A08S-R02）

- **task_id**：A08 签收的审查修复，A1～A10 收尾的一部分
- **review_status**：ready_for_review（以交付提交为准）
- **worktree / 分支**：同上，`claude/a08-signoff`。先把 Codex 审查时的未提交差异原样提交为 `445478e`，本轮修改在其上
- **审查报告**：主目录 `docs/reviews/codex-claude-a08-signoff-f9dfc8f-2026-09-24-0123z.md`（尚未入库）

| 问题 | 修改 |
| --- | --- |
| **A08S-R01**（P2）同值 `PUT` 可能被当作幂等跳过，合并前已有 B=`unknown` 时覆盖不了继承 | `specs/learning-path.md` §5 新增「同值写入」：不能只凭原始 `status` 相同跳过；在提交时的最终绑定版本上，节点仍有未被覆盖的来源时，同值写入是一次显式写入，取新写入序号并覆盖来源；没有时才为无操作（不取序号、不改 `updated_at`），因此重放从第二次起为无操作。LP-16 指向该判定；LP-18 补上「合并前 unknown → 继承为 mastered → 同值 PUT → unknown 且 A 被覆盖 → 重放无操作」的串联回归。`docs/decisions.md` 决定 9 下加补注，**待 ArvinHan 签收** |
| **A08S-R02**（P3）任务板 A08 行已是 DONE，说明段仍列已签收参数为待决 | `docs/tasks.md` 该段改为历史基线，指向「A08 签收」行，当前依赖列为 ADR-012 下一次修订、B12、C01/I01；「A08 签收」行状态注明补注待签收，并追加本轮修复说明 |

补注是从已签收的决定 9（“合并生效后学生对 `p` 的任何显式写入都会覆盖来源”）推导出的：同值写入也是显式写入，只有在确实没有可覆盖的来源时才可以不落库。没有改变决定 9 的方向。

**验证**（本 worktree）：

```text
python3 check_a08s.py .（修改前）        11 FAIL / exit 1
python3 check_a08s.py .（修改后）        ALL PASS / exit 0
python3 neg_a08s.py . <scratch>         6 个篡改副本全部 exit 1，各自命中目标断言
./scripts/verify.sh                      exit 0
git diff --check                         exit 0
python3 -m json.tool docs/atomic-tasks.json   exit 0
```

两个脚本在会话草稿区，未入库。断言覆盖 §5 判定条文的四个要素（原始值、覆盖关系、写入序号、最终绑定版本）、旧措辞已替换、LP-16/18、LP 编号连续 1～20、ADR 补注、任务板历史段与当前依赖。仍只有规格，没有实现或自动化测试。

**下一步**：ArvinHan 签收补注后，把 ADR 补注与任务行的「待签收」改为已签收；请 Codex 按交付提交复核。
