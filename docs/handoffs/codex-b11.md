# B11 图谱编辑与版本契约交接

- 任务：B11（含 A02-R01），实现完成，待 PR 审查/合并。负责人：Codex（`arvinhanye`）；基线：`origin/main@cfec20e`；分支：`codex/b11-graph-contract`；工作树：`/Users/arvinhan/.codex/worktrees/b11-graph-contract/SmartSketch`。
- 文件：`src/contracts/api.v1.yaml`、`src/contracts/v1/generated/`、`tests/contracts/test_b11.py`、`docs/architecture.md`、`specs/course-knowledge-graph.md`、`specs/teacher-review-publish.md`、`docs/tasks.md`、本交接。

## 交付与接口变化

- `Relation` 必带 `status/source/source_refs`；`RelationCreate` 仍由服务端补齐。普通与自动成环降级关系统一为可生成的两分支联合类型；降级分支必须带 `downgraded_from_type=PREREQUISITE` 与 `downgrade_cycle`，且关系本身固定为 `RELATED_TO/low_confidence/ai`。空来源数组可用于人工关系；已有 `SourceRef` 必须能定位。关系端点 ID 不可为空串。
- `KnowledgePoint.revision` 为节点级正整数；`KnowledgePointUpdate` 必带正数 `expected_revision` 和至少一个实际修改字段，冲突 409；与课程级 `draft_revision` 分离。知识点详情至少一条可定位来源。图谱交换格式显式包含可为 null 的 `graph_version`。
- `GraphVersion` 分为发布/回滚两类；回滚类必须带 `source_version`。`PublishResult` 必带 `unchanged` 与三个非负排除计数。`PUBLISH_BLOCKED` 409 带非空 `details.reasons`，闭集含 `invalid_lineage`；环原因必须带链。回滚和所有教师草稿写入端点声明 409。`merged_from` 与 `commit_seq` 仍仅在内部快照/持久层，不进入节点或版本 wire DTO。
- 更新相应规格/架构说明；无数据库迁移、配置或密钥变化。条件字段采用 `oneOf` / `allOf + anyOf`，Python/TypeScript 生成物均保留核心必填约束。

## 验证

- 测试先红：首次 `test_b11.py` 9 项失败，修复后 30 passed；关系空端点/无来源定位负例与生成模型负例均覆盖。
- `PATH="/opt/anaconda3/bin:$HOME/.local/share/smartsketch/contracts-venv/bin:$PATH" PYTEST_ADDOPTS='-p no:cacheprovider' /opt/anaconda3/bin/python -m pytest tests/contracts -q`：162 passed。
- 相同 PATH 环境下 `./scripts/verify.sh`：exit 0（契约 96 schemas、293 refs；门禁负向 24 项；B08/B09/B10/B13 回归通过）。
- `./scripts/gen-contracts.sh --check`：产物与真源一致；`git diff --check`：exit 0。
- 独立只读审查提出的生成类型条件约束与草稿写入 409 问题已修；TypeScript 生成的编辑请求包含交叉类型，`test_b11.py` 防止退化为 `unknown`。

## 风险、下一步与回滚

- 数组首尾同 ID 无法以标准 JSON Schema 的跨元素比较表达。两个环路数组均以 `x-closed-cycle: true` 标记；F13 在降级边持久化/序列化前、G04 在组装 `PUBLISH_BLOCKED` 前必须执行首尾相等校验并加服务层负例。课程/版本归属以及来源块存在性也仍须服务层校验。
- B12 与 B11 共用 YAML/生成物文件锁；先合并本 PR 再开始 B12。F08/F13/G04/G06 消费新的联合 DTO 时，应以 `src/contracts/api.v1.yaml` 和入库生成物为准。
- 无破坏性迁移；若需回滚本契约更改，反向撤销本 PR 并重跑生成、契约测试及 `./scripts/verify.sh`。由 ArvinHan 决定合并。
