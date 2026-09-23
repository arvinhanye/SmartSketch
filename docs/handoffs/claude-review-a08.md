# 交接：审查 Codex A08（推荐评分与进度跨版本规则）

- `task_id`: REVIEW-A08
- `status`: 审查完成；结论为暂不建议签收
- `worktree`: `/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/worktree-meaning-7a61bc`（`claude/codex-a08-check-ade85c`），base `1a47eb2`，本轮未提交
- `审查目标`: `/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/codex-a08-learning-path` @ `1a47eb2` + 未提交的三处改动；文件指纹见报告“范围与结论”

## 交付物

- `docs/reviews/claude-codex-a08-2026-09-23.md`：P2×4（R01～R04）、P3×6（R05～R10），以及已核实无误的清单。
- `docs/tasks.md`：在“Claude 审查批次”表中增加 REVIEW-A08 行。
- 未修改 Codex 的 worktree，也没有提交、合并或推送。

## 已运行命令与结果

| 命令/核对 | 位置 | 结果 |
| --- | --- | --- |
| `./scripts/verify.sh`（先读脚本，确认只做只读检查） | Codex worktree | exit 0 |
| `git diff --check` | Codex worktree | exit 0 |
| `grep -nP "[ \t]+$"` 检查两个新文件 | Codex worktree | 无匹配 |
| `shasum -a 256` 两个新文件及 `git diff docs/tasks.md` | Codex worktree | 已记入报告 |
| pypdf 抽取 S2 PDF 全文（写入 scratchpad，不入库） | 主目录 PDF | 38 页；§6.4.7 在第 30～31 页 |
| 参考脚本按 §2/§3 公式计算（写入 scratchpad，不入库） | 本机 python3 | 星形中心点的中心度在 N=2..50 时都为 0.5，3000 个随机 DAG 最大值也为 0.5（R02）；LP-2 解锁数为 1/0；随机 DAG 中候选之间先修边 0 条 |
| `git show 978671e:src/contracts/api.v1.yaml` | 仓库对象 | 用于核对 `kp/merge`、`PUT /progress`（批量）、`importance/difficulty` `[0,1]`、`Chapter` 字段 |

参考脚本没有入库。复现方法：用 §2 的 `Eligible`、§3 的 `unlock_count` 和 `centrality` 公式，在星形图（一个中心点，其余点都是它的直接后继）上计算中心点的中心度即可。

## 复核（PR #13 开出后）

- Codex worktree 的三个文件指纹不变，PR 上没有评论，尚无人开始修复。
- 按源文档逐条复核 R01～R10，均成立，没有撤回项。复核依据：A04 V3 第 139 行与 PUB-24、V6 的 R2/R4、V9 第 265 行、ADR-004 选定的 `740adb` YAML 真源。
- R01 补充了根源：B12 验收中的“无图”（`docs/atomic-task-plan.md:70`）须由协调方同步修改。

## 产品签收（ADR-014）

- ArvinHan 于 2026-09-23 在会话中决定：R02 的中心度分母改为 `N−1`；R03 改为按合并来源继承进度。Claude 把两项写入 `docs/decisions.md` **ADR-014**（背景、方案、决定、后果、推翻条件），并在报告 R02/R03 处与任务板 REVIEW-A08 行标注“已签收”。
- ADR-014 中由 Claude 从决定推导、未经单独询问的内容：
  - 0.5/0.5 拆分沿用 A08 提案，签收时未改动；
  - “取最高状态”来自审查报告给出的选项（2）；
  - “读时投影、不改写进度行”和“来源重新出现时不继承”是为保持 A08 §2 不变量与回滚一致性而作的推导。

  签收人如有异议，修改 ADR-014。
- 交给 A08 修复提出、另行签收的两项细则：学生如何取消继承来的状态；谱系存放在快照字段还是课程级表。
- 未修改 Codex 的 `specs/learning-path.md`；公式与验收由 Codex 按 ADR-014 写入。

## 接口/数据变更

无。

## 风险与待决

- R03 的合并进度策略和 R02 的中心度定义都属于产品决定，须由产品负责人签收，不能由审查方代为决定。
- 本轮审查的是未提交快照。Codex 修改后指纹会变，须按新指纹重新审查。

## 下一位 Agent 的首个动作

请 Codex 按报告修复 A08-R01～R04（R05～R10 可同批处理），更新 `docs/handoffs/codex-a08.md` 的指纹和逐项核对证据，然后请 Claude 复审。

## 回滚

删除本轮新增的报告和本交接，并删掉 `docs/tasks.md` 中的 REVIEW-A08 行。
