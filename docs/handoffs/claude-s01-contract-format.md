# Claude 交接：S-01 契约格式与单一真源

- **状态**：DONE
- **日期**：2026-09-22
- **范围**：确定 `src/contracts/` 的表达格式、单一真源、目录与命名规则、版本化策略与强制变更流程；统一文档处理任务状态机；把 M0-04 拆成互不重叠的顺序子任务。仅产出决策与结构约定，未写任何模型、脚本或 DTO 字段。

## 已交付

| 文件 | 改动 |
| --- | --- |
| `docs/decisions.md` | 追加 ADR-004（契约真源与生成链）、ADR-005（任务状态机统一） |
| `src/contracts/README.md` | 重写：真源/生成物分工、目录结构、文件与类型命名、三类契约约束、双层版本化、强制变更流程 |
| `docs/tasks.md` | M0-04 拆为 M0-04a / M0-04b；新增 M0-06（同步 specs 状态机）与 S-01（本任务）；表下增加所有权与顺序说明 |
| `docs/architecture.md` | 仅契约相关段落：`src/backend/app/schemas/` 与 `src/contracts/` 两行职责、关键质量边界前三条 |

未触碰 `src/frontend/`、`src/backend/app/`、`scripts/verify.sh`、`.env.example`、`specs/`。

## 关键决定

1. **真源 = `src/contracts/v1/python/` 的手写 Pydantic v2 模型**，生成物 = `src/contracts/v1/generated/`（OpenAPI JSON、JSON Schema、TS 类型），生成命令 `./scripts/gen-contracts.sh`，生成物入库且禁止手改。取舍理由见 ADR-004 的三方案对比：核心判据是 B（手写 OpenAPI YAML）与 C（JSON Schema）都会让「契约文档」与「FastAPI 运行时校验模型」变成两个产物，漂移只能靠额外一致性测试事后兜住；A 让二者是同一个对象，漂移在结构上无从发生。A 的代价（SSE 与图谱格式不在 OpenAPI paths 内、前端要等后端）分别用 `model_json_schema()` 导出和 M0-04a/M0-04b 顺序拆分解掉。
2. **写入方唯一**：`src/contracts/` 只由后端 Agent 写入，前端是只读消费方，契约需求走交接文件回送。这是把 AGENTS.md §3「不同时编辑同一个功能文件」落到契约目录上的具体做法。
3. **双层版本化**：主版本用目录 `v1/`（对应 `/api/v1`），次版本用 SSE 事件与图谱文件内的 `schema_version` 字段；README 给出破坏/非破坏变更判定表。

## 规格冲突的处理与取舍理由

冲突：`specs/course-knowledge-graph.md` 验收条件 2 的状态机是 `queued → parsing → extracting → merging → awaiting_review → completed/failed`；参考方案 S2 §4.3.2 另有「入库中」「已取消」，§6.5 还有 `POST /api/tasks/{tid}/cancel`。

结论（ADR-005）：`queued → parsing → extracting → merging → persisting → awaiting_review → completed`，任一非终态可转 `failed`，并预留终态 `cancelled`。

- **采纳「入库中」→ `persisting`**：它不是凭空多一个状态，而是 `docs/architecture.md` 数据流第 2 步已有的真实阶段（DAG 校验 → 写入草稿图谱）。该阶段跨 Neo4j 与 SQLite 两个存储（ADR-002），失败原因（前置关系成环被拒、图库不可用、部分写入需补偿）与解析/抽取/融合完全不同。合并进 `merging` 的代价是教师看到失败时无法知道卡在抽取还是入库，而这恰恰是 MVP 里最需要可解释的一步。语义上对应 `docs/product.md` 教师流程的「校验」，展示文案定为「校验入库」。
- **保留 `cancelled` 但不实现取消**：取消端点要求 worker 协作式中断、跨两存储的部分写入补偿，以及「取消与完成竞争」的处理，超出 AGENTS.md §1 的 MVP 目标，所以 MVP 不做 `POST /api/v1/tasks/{task_id}/cancel`。但枚举值必须现在就占位：按 ADR-004，状态枚举属于 SSE 契约，而枚举增值会打断前端的穷尽分支，是破坏性变更——以后补就得升 v2。占位是向后兼容的，成本只有前端多渲染一个终态分支。
- **已知代价**：v1 里存在一个当前不可达的枚举值，无法被状态转换测试覆盖，且可能诱使后续 Agent 顺手实现取消。缓解方式写进契约：显式标注「预留，MVP 不产生」，并要求后端有一条测试断言 worker 不会发出该状态。

## 已运行命令与结果

```text
./scripts/verify.sh   → Scaffold verification passed.
git status --short    → 4 个受版本控制文件被修改，1 个交接文件新增；无其他 Agent 文件被触碰
```

## API / 数据 / 配置影响

- 未定义任何端点、字段或数据库结构；本任务只约束它们将来写在哪、叫什么、怎么改。
- 预告两项将由 M0-04a 引入的变更：新增 `./scripts/gen-contracts.sh`，以及在 `scripts/verify.sh` 中增加 `gen-contracts.sh --check` 调用（该脚本归后端 Agent 改）。
- 新增开发期依赖（尚未安装）：`openapi-typescript`、JSON Schema→TS 转换工具。
- 无环境变量或密钥变更。

## 未完成项与风险

1. `specs/course-knowledge-graph.md` 验收条件 2 仍是旧状态机，「待细化」还引用已拆分的 M0-04。`specs/` 归产品/协调 Agent，本任务未改，已登记为 **M0-06**。在它完成前，规格与 ADR-005 不一致，实现方以 ADR-005 为准。
2. `docs/handoffs/codex-m0-project-scaffold.md` 风险第 1 条仍写「先由前后端共同完成 M0-04」。交接文件是历史记录且归 Codex，未修改；该条已由 ADR-004 与 M0-04a/M0-04b 取代。
3. `scripts/verify.sh` 目前不校验契约生成物是否同步；在 M0-04a 加上 `--check` 之前，「生成物入库」这条规则只靠人工评审保证。
4. 前端在 M0-04a 完成前拿不到契约类型，M0-02 的可做范围限于路由与构建骨架；若前端提前自造类型，即回到本任务要消除的漂移。
5. 生成脚本的具体工具链（`openapi-typescript` 版本、JSON Schema→TS 选型）未定，由 M0-04a 决定并在交接文件记录。

## 下一位 Agent 的首个动作

**后端 Agent（M0-04a）**：先读 ADR-004、ADR-005 与 `src/contracts/README.md` §2–§4，再按 §2 的目录创建 `v1/python/`，从 `common.py`（含 `TaskStatus` 枚举，取值即 ADR-005 的九个状态，含预留的 `cancelled`）起草，然后写 `scripts/gen-contracts.sh` 并提交生成物。

## 回滚

本任务只改文档与说明，无破坏性变更。需要撤回时，逐个还原上表四个文件并删除本交接文件；不要使用全局重置或清理命令，以免影响其他 Agent 的改动。
