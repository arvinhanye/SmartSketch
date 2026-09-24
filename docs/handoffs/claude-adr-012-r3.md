# Claude 交接：起草 ADR-012 修订 3（快照谱系 `merged_from` 与共享提交序号）

- `task_id`: ADR-012 修订 3（ADR-014 修订 1 决定 9、10 交办；解除 B11 阻塞）
- `review_status`: 已签收（ArvinHan 2026-09-24 在会话中签收，未改动决定 15～25），随 PR #179 合并
- `branch`: `claude/adr-012-r3`，base `248b895`（main）
- 负责人：ArvinHan（Claude 起草）

## 交付物

- `docs/decisions.md`：ADR-012 引言加「修订 3」一行；新增「ADR-012 修订 3」一节，决定 15～25（接续修订 2 的决定 14）。
- `specs/teacher-review-publish.md`：V2 增加 `commit_seq` 列与 `commit_sequence` 表；V3 的发布集合第 2 条、校验表（`invalid_lineage`）、快照示例、字段例外说明与规范化规则加入 `merged_from`；V5 P11 第 1 条与 V6 R7 写明取号；V10 增加交办行。每处都标「ADR-012 修订 3，待签收」。
- `specs/learning-path.md`：§7 细则 1、2 改为指向修订 3（顺带把细则 1 里写错的「G05」改为 G04 的 P11、G06 的 R7）。
- `docs/tasks.md`：新增本任务一节。

## 需要签收的决定（摘要）

| 决定 | 内容 | 主要取舍 |
| --- | --- | --- |
| 15 | 每个快照知识点有 `merged_from`：本版本中归属到它的**全部**来源，链已展平 | 否决「只存直接父子」：中间节点不在版本中时链会断 |
| 16 | 不变式：来源不是本快照节点、至多归属一个节点、不含自身；P6 违反 → 409 `PUBLISH_BLOCKED` 的 `invalid_lineage` | 与 `dangling_endpoint` 同属草稿不变量被破坏 |
| 17 | 草稿维护：合并 `m→p` 时 `p.merged_from ∪= {m} ∪ m.merged_from`；删除 `p` 时丢弃 | 回滚不改草稿；版本谱系随快照回退 |
| 18 | 被排除节点的 `merged_from` 不进入本版本 | 来源在该版本为 dormant |
| 19 | 纳入摘要，集合数组规则，空为 `[]`；不升 `snapshot_format` | 同修订 1：尚无实现 |
| 20 | 不进 `KnowledgePoint` wire DTO | 学生经 `inherited_from[]` 看到效果；以后可追加 |
| 21 | 进度投影读 SQLite 快照中的 `merged_from`，按 `version_id` 缓存 | 快照是真相 |
| 22 | 全库单行表 `commit_sequence`，写事务内 `UPDATE … RETURNING` 取号 | 否决每课程计数器、日志表、时间戳 |
| 23 | 版本行 `commit_seq`：P11 / R7 取号；幂等路径、C1、失败尝试不取号 | 同课程内版本号与提交序号同向递增 |
| 24 | 进度行 `write_seq`：写入事务内取号；同值无操作不取号 | 与 A08S-R01 一致 |
| 25 | `commit_sequence` 由 G02 与 I01 中先实现者建表；迁移编号在任务板预留 | T6 提交序号不受影响 |

## 设计推演（对照已签收验收）

- **LP-9 链式合并**：`a→b` 发布后 `b.merged_from=[a]`；再 `b→c` 发布后 `c.merged_from=[a,b]`，C 继承 A、B 的最高状态。
- **LP-19 删除**：`a→b` 后删除 `b`，`b.merged_from` 随之丢弃，之后的版本中 A 不归属任何节点（dormant）。
- **LP-20 回滚后再合并**：v2 `B.merged_from=[A]`；v3 回滚到 v1，快照中 A、B 各自可见、谱系为空；草稿不变，v4 再次发布时 `B.merged_from=[A]`。从 v4 往前查：v4 归属、v3 不归属 → 起算版本 `k = v4`，界 `T` 为 v4 的 `commit_seq`。学生在 v4 之前写的 `B=unknown` 序号小于 `T`，不覆盖 A；之后再写则覆盖。与 LP-20 的期望一致。
- **「中间节点在版本中则停在中间节点」**：由构造保证。来源一经合并就从草稿删除；如果中间节点 `b` 在某个版本中，说明产生该版本的草稿里 `b` 尚未被合并，`b` 不会出现在更远节点的 `merged_from` 里。回滚复制的是旧快照整体，内部同样自洽。

## 已运行命令与结果

| 命令 | 结果 |
| --- | --- |
| `./scripts/verify.sh` | exit 0（命名基线 10 份文档无同义别名，门禁负例、B08～B13 回归通过） |
| `git diff --check` | exit 0 |
| 决定编号核对 | 修订 1、2 用到决定 14；本修订为 15～25，节内引用逐一核对 |

## 未决与风险

- 决定 15（展平而非直接父子）、20（不上 wire）、22（全库单行计数器）三项取舍已随整条签收。
- `docs/architecture.md`「图谱版本与跨库发布」一节只写结论，本次未改；签收后若需要，可补一句指向修订 3。
- 签收后 B11 可开工，须同时并入 A02-R01。

## 签收

- ArvinHan 2026-09-24 在会话中签收并要求合并（「签收 #179 并合并」）；决定 15～25 未改动。
- 签收时把 `docs/decisions.md`、`specs/teacher-review-publish.md`、`specs/learning-path.md`、`docs/tasks.md` 中的「待签收」改为已签收，并在 ADR-014 修订 1「后果」与任务板 A08 行的后续项中注明已完成。
- B11 由此解除阻塞（issue #53 改回 `status:pending`）。

## 回滚

本分支只改文档；关闭 PR 或撤销提交即可。
