# Claude A02 / HOOK-01 固定提交审查（2026-09-23 05:28 UTC）

## 范围与结论

- **A02**：`adoring-sinoussi-709263`，交付提交 `13d586e`（基线 `bfa236c`），固定四文档差异 SHA256 `da3e81763e33d5793d3b1736199e07d71b20666c886edece4c3ce9896751fada`。当前 worktree `cd1ecd6` 仅后续合入 main 的 CI 提交；本批只审 A02 四文档及交接，不把 CI 作为 Claude A02 改动。HEAD、dirty diff、Claude 交接集合指纹两次观察一致；交接标记 `ready_for_review` 并引用固定交付提交。
- **HOOK-01**：同一项目会话产生的独立固定提交 `3c2dfab`（基线 `b345a34`），交接标记 `ready_for_review`；当前 checkout 不在该分支，因此从提交对象读取 hook、测试、门禁和交接，在隔离临时目录运行提交中的测试。仅确认命令提取修复的范围，既有 S07-R12 包装命令漏检及交接列出的等价拼写绕过仍开放。
- 05:28 UTC 会话在最近 `stop_hook_summary` 后已有新 user 活动；**不宣称当前会话/整轮结束**。这份报告只覆盖两个已固定的 ready 提交。S-07 既有待审范围亦未在本批完成。

## 新问题

### A02-R01 P2：关系必需字段的规格与契约不一致

- **目标提交 / 位置**：`13d586e`，`specs/course-knowledge-graph.md:14,22-24`，并见 `docs/architecture.md:77-79`；对照待导入真源 `978671e:src/contracts/api.v1.yaml:1309-1333`。
- **触发条件**：服务按 YAML `Relation` schema 返回仅含 `id/course_id/type/from_id/to_id/confidence` 的关系，不含 `status`、`source` 或 `source_refs`；该对象符合当前 `required` 列表，却不满足 A02 新规格的“关系至少含”以及按 `source/status` 判定可降级边的规则。用本机已有 PyYAML 读取真源，确认三字段均列在 `properties`、均不在 `required`；A02 的逐值枚举核对没有覆盖字段必需性。
- **影响**：生成的消费者类型可把这三字段视为可缺省；worker/审核端无法可靠区分受保护的人工/已确认边与可自动降级边，也可能丢失来源，导致 DAG 降级和审核实现各自猜测默认值。此处是尚未导入/实现前的契约缺口，不是声称线上已发生误降级。
- **最小修复**：B11 在 YAML 真源把 `status`、`source`、`source_refs` 加入 `Relation.required`（若需允许空来源，则显式规定适用场景并与规格对齐）；重生成并加“缺任一字段拒绝”的 schema 负例。`RelationCreate` 仍可由服务端补齐这些字段，不必要求教师提交它们。

## 已验证及剩余边界

```text
A02 ./scripts/verify.sh                         exit 0，仅 scaffold 检查
A02 git diff --check bfa236c..13d586e          exit 0
A02 固定四文档 diff SHA256                       与交接前 16 位 da3e81763e33d579 一致
HOOK-01 bash -n hook/test                       exit 0
HOOK-01 提交中的 tests/hooks/test_block_dangerous.sh  14 PASS，exit 0（隔离临时目录；未执行测试中的危险命令文本）
HOOK-01 git diff --check b345a34..3c2dfab     exit 0
```

本批未运行数据库、模型、网络或真实 Bash 危险命令，未安装依赖，未修改 Claude worktree。HOOK-01 的解析修复在所测 14 个输入上成立；原有固定子串规则仍不能等同完整命令安全边界。A02 并发 DAG 写入、课程权限、发布版本、任务取消/重试、双存储及问答来源尚无新增运行时代码可审，后续实现批次再验证；既有报告问题不重复立项。
