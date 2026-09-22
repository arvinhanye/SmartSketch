# ADR-004：契约以 Pydantic 为单一真源，生成 OpenAPI 与 TypeScript 类型


- **日期**：2026-09-22
- **背景**：`src/contracts/` 目前只有一份说明，没有规定契约用什么语言表达。后端需要 Pydantic 才能在 FastAPI 运行时校验，前端需要 TypeScript 才能做类型检查；若两端各写一份，接口会在 M0-02 与 M0-03 并行初始化后立刻漂移——这正是 `docs/handoffs/codex-m0-project-scaffold.md` 风险第 1 条警告的情况。AGENTS.md §3 已把 `src/contracts/` 判给后端 Agent，§4 要求进度事件格式先在此定义。待决的是四件事：真源用什么写、放在哪、生成物怎么来、变更从哪一步开始。
- **评估方案**：

| 方案 | 真源 | 优点 | 代价 | 结论 |
| --- | --- | --- | --- | --- |
| A. Pydantic → OpenAPI → TS | `src/contracts/v1/python/` 手写 Pydantic v2 | 真源同时就是 FastAPI 的运行时校验模型，线上响应在结构上不可能与契约不一致；不引入第三种语言；`openapi-typescript` 产物无运行时依赖 | 前端类型要等后端先落笔；SSE 事件与图谱交换格式不在 OpenAPI paths 内，需额外导出 JSON Schema | **采纳** |
| B. 手写 OpenAPI YAML 双向生成 | `src/contracts/v1/openapi.yaml` | 语言中立；前端可先于后端开工；评审时人类直接读 YAML | 后端仍需 Pydantic（生成后通常要手改），于是「契约文档」与「运行时校验」是两份产物，必须再写一致性测试才防得住漂移；等于为 MVP 引入第三种语言 | 否决 |
| C. JSON Schema 为真源 | `src/contracts/v1/*.schema.json` | 对 SSE 事件与图谱交换文件表达力最好，工具链成熟；两端都是生成方，无偏向 | 不描述路径、方法、状态码与错误响应，REST 契约仍要第二份文档；Pydantic 与 TS 都成了生成物，两端都可能改生成物绕开真源 | 否决 |

  取舍要点：B 与 C 都把「契约文档」和「运行时校验」拆成两个产物，漂移只能靠额外测试事后兜住；A 让二者是同一个对象，漂移在结构上无从发生。A 的两处弱点都有确定解——SSE 事件与图谱交换格式同样写成 Pydantic 模型，用 `model_json_schema()` 导出 JSON Schema 再转 TS；前端的等待问题用 M0-04a/M0-04b 的顺序拆分解决，而不是让前端另起一份类型。
- **决定**：
  1. **真源**：`src/contracts/v1/python/`，手写 Pydantic v2 模型，覆盖 REST DTO、SSE 任务事件、图谱导入/导出三类，由后端 Agent 单独拥有。`src/backend/app/schemas/` 只放不对外暴露的内部模型；对外 DTO 一律从契约包导入，不得复制或再声明。
  2. **生成物**：`src/contracts/v1/generated/`，含 `openapi.json`、各 `*.schema.json` 与 `typescript/*.d.ts`。该目录内所有文件禁止手工编辑。
  3. **生成命令**：`./scripts/gen-contracts.sh`，`--check` 为只校验模式（重新生成后 `git diff --exit-code`）。由 M0-04a 实现，本 ADR 不实现。
  4. **生成物入库**：入库。前端无需 Python 环境即可取得类型；接口变更在 PR diff 中直接可见、可评审；冷启动 Agent 不必先跑起后端。代价是产物可能与真源不同步，由 `--check` 在 `scripts/verify.sh` 与 CI 中兜底。
  5. **强制规则（接口变更先改真源）**：
     - 任何 REST / SSE / 图谱格式变更，第一步必须改 `src/contracts/v1/python/`；先改前端类型或后端 schemas 属于契约违规。
     - 同一次提交必须同时包含：真源改动、重新生成的产物、受影响的规格或 ADR 更新。
     - `generated/` 出现手工编辑，或 `gen-contracts.sh --check` 不通过，PR 一律拒绝。
     - 前端发现契约缺失或不合用时，不得在 `src/frontend/` 内补类型、改写或用断言绕过，必须按 M0-04b 的反馈路径交回后端 Agent 改真源。
- **后果**：
  - 后端 Agent 成为契约的唯一写入方，前端 Agent 是只读消费方；M0-04 因此拆成顺序执行的 M0-04a / M0-04b，以满足 AGENTS.md §3「不同时编辑同一个功能文件」。
  - 前端在 M0-04a 完成前拿不到契约类型，M0-02 的可做范围限于路由与构建骨架。
  - 新增 `openapi-typescript` 及 JSON Schema→TS 的开发期依赖；`scripts/verify.sh` 需在 M0-04a 增加 `--check` 调用，该改动由后端 Agent 执行。
  - 目录结构、文件命名与版本化规则见 `src/contracts/README.md`。
