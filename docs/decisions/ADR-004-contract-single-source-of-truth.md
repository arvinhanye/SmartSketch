# ADR-004：契约以 OpenAPI YAML 为单一真源，生成 Pydantic 与 TypeScript

> **本文已于 2026-09-22 改判。** 首版决定「手写 Pydantic 为真源」（下表方案 A）。同日合并
> `claude/tech-plan-review-improvements-ff30e0` 时发现，该分支已按方案 B 冻结了一份 1690 行的
> `src/contracts/api.v1.yaml`，两侧各自规定了互斥的唯一真源——codex 审查 R01（P1）。协调人裁定
> 采用 **B′：YAML 真源 + 生成 Pydantic**。首版的方案对比与否决理由原样保留在「评估方案」，
> 改判理由见「为什么推翻首版」。

- **日期**：2026-09-22（首版）／2026-09-22 改判
- **背景**：`src/contracts/` 起初只有一份说明，没有规定契约用什么语言表达。后端需要 Pydantic 才能在 FastAPI 运行时校验，前端需要 TypeScript 才能做类型检查；若两端各写一份，接口会在 M0-02 与 M0-03 并行初始化后立刻漂移——这正是 `docs/handoffs/codex-m0-project-scaffold.md` 风险第 1 条警告的情况。AGENTS.md §3 已把 `src/contracts/` 判给后端 Agent，§4 要求进度事件格式先在此定义。待决的是四件事：真源用什么写、放在哪、生成物怎么来、变更从哪一步开始。
- **评估方案**：

| 方案 | 真源 | 优点 | 代价 | 首版结论 |
| --- | --- | --- | --- | --- |
| A. Pydantic → OpenAPI → TS | `src/contracts/v1/python/` 手写 Pydantic v2 | 真源同时就是 FastAPI 的运行时校验模型，线上响应在结构上不可能与契约不一致；不引入第三种语言；`openapi-typescript` 产物无运行时依赖 | 前端类型要等后端先落笔；SSE 事件与图谱交换格式不在 OpenAPI paths 内，需额外导出 JSON Schema；`openapi.json` 要等 FastAPI 应用存在才能导出 | 首版采纳，**已推翻** |
| B. 手写 OpenAPI YAML 双向生成 | `src/contracts/api.v1.yaml` | 语言中立；前端可先于后端开工；评审时人类直接读 YAML | 后端仍需 Pydantic（生成后通常要手改），于是「契约文档」与「运行时校验」是两份产物，必须再写一致性测试才防得住漂移 | 首版否决，**已改判采纳（见 B′）** |
| C. JSON Schema 为真源 | `src/contracts/v1/*.schema.json` | 对 SSE 事件与图谱交换文件表达力最好，工具链成熟；两端都是生成方，无偏向 | 不描述路径、方法、状态码与错误响应，REST 契约仍要第二份文档；Pydantic 与 TS 都成了生成物，两端都可能改生成物绕开真源 | 否决 |

- **为什么推翻首版**：
  1. 首版否决 B 的**唯一理由**是「后端仍需 Pydantic（生成后通常要手改），于是有两份产物」。这个前提可以直接消掉：Pydantic 不手写、不手改，由 `datamodel-code-generator` 从 YAML 生成，并套用首版对前端生成物的同一条规则——生成物入库、禁止手工编辑、`--check` 兜底。前端不许手写 TS，后端就同样不许手写对外 DTO。前提被消掉之后，B 的否决理由不成立，称之为 **B′**。
  2. 方案 A 的「真源即运行时校验对象」这一优势，要等 FastAPI 应用存在才能兑现（`openapi.json` 由应用导出）。而契约必须在 M0-04 冻结，此时应用还不存在——A 在当前阶段无法自洽地产生生成物。
  3. 迁移成本不对称：`api.v1.yaml` 已有 22 条路径、52 个 schema、181 处 `$ref`，且已被逐行审查；`v1/python/` 一行未写。选 A 要现在付一次翻译成本并重新审一遍，选 B′ 成本为零。
  4. B′ 同时解掉 A 的第二项代价：SSE 事件与图谱交换格式在 YAML 里就是 `components/schemas`，`gen-contracts.sh` 直接摘成独立 JSON Schema，不需要先有 Python 对象。
- **决定**：
  1. **真源**：`src/contracts/api.v1.yaml`（OpenAPI 3.1），由后端 Agent 单独拥有，是**唯一允许人工编辑的机器可读契约**。`events.v1.md` 与 `errors.v1.md` 是它的配套文档，只写 OpenAPI 表达不了的时序与语义，不重复定义结构。
  2. **生成物**：`src/contracts/v1/generated/`，含 `openapi.json`、各 `*.schema.json`、`python/` 下的 Pydantic v2 模型与 `typescript/` 下的 `.d.ts`。该目录内所有文件禁止手工编辑。
  3. **两端都是只读消费方**：后端从 `v1/generated/python/` 导入对外 DTO，`src/backend/app/schemas/` 只放不对外暴露的内部模型；前端从 `v1/generated/typescript/` 导入类型，不在 `src/frontend/` 内重写、断言或 `any` 绕过。首版「后端是唯一写入方、前端是只读方」的不对称关系随之取消——**唯一写入方是 `api.v1.yaml` 本身**。
  4. **生成命令**：`./scripts/gen-contracts.sh`，`--check` 为只校验模式（重新生成后比对，不一致即非 0 退出）。生成必须可重复：同一份 YAML 生成两次字节一致。
  5. **生成物入库**：入库。前端无需 Python 环境即可取得类型；接口变更在 PR diff 中直接可见、可评审；冷启动 Agent 不必先跑起后端。代价是产物可能与真源不同步，由 `--check` 在 `scripts/verify/contracts.sh` 与 CI 中兜底。
  6. **工具链版本锁定**：生成器及其版本记录在 `src/contracts/toolchain.txt`。缺工具时 `gen-contracts.sh` **必须非 0 退出**，不得静默跳过（codex 审查 R02 的教训）；仅在显式传入 `--allow-scaffold` 时降级，且必须打印未完成验收标记。
  7. **强制规则（接口变更先改真源）**：
     - 任何 REST / SSE / 图谱格式变更，第一步必须改 `src/contracts/api.v1.yaml`；先改前端类型或后端 schemas 属于契约违规。
     - 同一次提交必须同时包含：真源改动、重新生成的产物、受影响的规格或 ADR 更新。
     - `v1/generated/` 出现手工编辑，或 `gen-contracts.sh --check` 不通过，PR 一律拒绝。
     - 前端发现契约缺失或不合用时，不得在 `src/frontend/` 内补类型、改写或用断言绕过，必须按 M0-10 的反馈路径交回后端 Agent 改真源。
  8. **REST 路径前缀统一为 `/api/v1`**，与生成物目录 `v1/` 同步升级。首版沿用 S2 表 6.6 的 `/api/...` 无版本前缀，与 `docs/architecture.md`、ADR-006 的 `/api/v1/...` 冲突，本次以 `/api/v1` 收敛。
- **后果**：
  - M0-04 的四个子任务（REST DTO / SSE 事件 / 图谱交换 / 错误码）在 `api.v1.yaml` 冻结时已完成。生成链改编为 **M0-09**（`gen-contracts.sh` 与入库生成物），前端消费改编为 **M0-10**，二者顺序执行。
  - 前端不再需要等后端写模型——YAML 已冻结，M0-09 产出生成物后即可消费；A 方案「前端要等」的代价消失。
  - 新增开发期依赖：`datamodel-code-generator`（YAML→Pydantic）、`openapi-typescript`（YAML→TS），版本锁在 `src/contracts/toolchain.txt`。
  - 首版写进 `docs/handoffs/claude-s01-contract-format.md` 的推理（尤其「B 会产生两份产物」）已被本次改判取代。交接文件是历史记录，不回改；以本 ADR 为准。
  - 目录结构、文件命名与版本化规则见 `src/contracts/README.md`。
