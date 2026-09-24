# 契约（Contracts）

本目录是 SmartSketch 前后端共享协议的**单一真源**。`src/frontend/` 与 `src/backend/` 的所有对外数据结构都以此处为准；两边都不得自行定义同名结构。格式决策见 [ADR-004](../../docs/decisions.md)，命名基线见同文件 ADR-016；状态转换以 [任务处理规格](../../specs/task-processing.md) 为准。

## 1. 真源与生成物

| | 位置 | 谁写 | 规则 |
| --- | --- | --- | --- |
| 真源 | `api.v1.yaml` | 后端 Agent | 手写 OpenAPI 3.1；**唯一允许人工编辑的机器可读契约** |
| 时序文档 | `events.v1.md`、`errors.v1.md` | 后端 Agent | 只写 OpenAPI 表达不了的语义，不重复定义结构 |
| 生成物 | `v1/generated/` | `./scripts/gen-contracts.sh` | 入库，但**禁止手工编辑**；前后端都只读消费 |

| 文件 | 内容 | 对应任务 |
| --- | --- | --- |
| `api.v1.yaml` | OpenAPI 3.1：全部 REST 路径、DTO schema、图谱交换格式、错误响应 | M0-04a、M0-04c |
| `events.v1.md` | SSE 事件名、顺序保证、心跳、终止与重连语义 | M0-04b |
| `errors.v1.md` | 错误码的 HTTP 状态、触发条件、`details` 结构与前端处理 | M0-04d |
| `toolchain.txt` | 生成器及锁定版本；缺工具时门禁必须失败而不是跳过 | M0-09 |

- 后端从 `v1/generated/python/` 导入对外 DTO，不在 `src/backend/app/schemas/` 重复定义；该目录只放不对外暴露的内部模型。
- 前端从 `v1/generated/typescript/` 导入类型，不在 `src/frontend/` 内重写、断言或 `any` 绕过。
- 生成命令：`./scripts/gen-contracts.sh`（`--check` 为只校验模式：重新生成后比对，不一致即非 0 退出）。
- **两端都是只读消费方。** 唯一写入方是 `api.v1.yaml` 本身，不是某个 Agent。

## 2. 目录结构

```text
src/contracts/
├── README.md                     # 本文件：格式、命名、版本化与变更流程
├── api.v1.yaml                   # ★ 真源（手写 OpenAPI 3.1）
├── events.v1.md                  # 时序语义：SSE 事件顺序、终止、重连
├── errors.v1.md                  # 错误码闭集与前端处理
├── toolchain.txt                 # 生成器版本锁
└── v1/generated/                 # ☆ 生成物（入库、只读）
    ├── openapi.json              # api.v1.yaml 的 JSON 形式，供工具链消费
    ├── schemas/<Name>.schema.json # 逐个 component schema 摘出的独立 JSON Schema
    ├── python/                   # datamodel-code-generator 生成的 Pydantic v2 模型
    └── typescript/               # openapi-typescript 生成的 .d.ts
```

## 3. 新东西放哪、叫什么

| 你要定义的东西 | 放进 | 命名 |
| --- | --- | --- |
| HTTP 请求体 / 响应体 | `api.v1.yaml` 的 `components.schemas` | `XxxRequest` / `XxxResponse` / `XxxItem` |
| 一种新的 SSE 事件载荷 | 同上，并在 `events.v1.md` 的事件表加一行 | `XxxEvent`，注册进该域的事件联合类型 |
| 跨端点复用的枚举、错误码、来源引用、分页 | 同上 | `XxxStatus` / `XxxType` / `ErrorCode` / `SourceRef` |
| 图谱导入或导出的文件格式 | 同上 | `GraphExport` / `GraphImportRequest` |
| 任何 Pydantic 模型或 TypeScript 类型 | 不手写 | 改真源后跑 `./scripts/gen-contracts.sh` |

命名规则：schema 名 PascalCase 并带用途后缀（`Request`、`Response`、`Item`、`Event`、`Error`）；枚举成员小写下划线，值即线上传输值。

## 4. 三条硬约束

1. **命名基线是 ADR-008。** 关系类型只有 `CONTAINS`、`PREREQUISITE`、`RELATED_TO`、`EXAMPLE_OF`，不得引入别名。
2. **两个领域状态不是 HTTP 错误。** 问答证据不足返回 200 + `status = not_covered`；任务失败返回 200 + `stage = failed`。因此 `NOT_COVERED` 与 `TASK_FAILED` 不在 `ErrorCode` 枚举里，详见 `errors.v1.md`。
3. **`course_id` 是第一隔离条件。** 所有课程域资源的请求或路径中必须带课程标识；隔离在仓储层强制，`COURSE_FORBIDDEN` 只是第二道防线。

## 5. 三类契约

### 5.1 REST DTO

- 路径前缀 `/api/v1`，与生成物目录 `v1/` 同步升级（ADR-004 第 8 条）。
- 每个端点必须声明成功响应与错误响应两类模型；错误使用统一错误模型与 `ErrorCode` 枚举，不得每个端点各发明一套。
- 问答响应必须能表达「带来源」与 `not_covered` 两种结果，且**两者的结构约束不同**：`answered` 至少一条引用，`not_covered` 引用为空并给出机读原因（ADR-003，见 §5.4）。

### 5.2 SSE 事件

AGENTS.md §4 要求进度事件格式先在本目录定义，后端与前端才能实现。

**任务状态机取值**（转换、取消与关流规则以 [任务处理规格](../../specs/task-processing.md) 为准）：

```text
queued → parsing → extracting → merging → persisting → awaiting_review → completed
         └── parsing～persisting ──→ failed
         └── queued～merging ──→ cancelled
```

- 终态：`completed`、`failed`、`cancelled`。终态之后不再发送该任务的进度事件。
- `persisting` 覆盖「DAG 校验 + 写入草稿图谱」，展示文案「校验入库」；前置关系成环导致的拒绝发生在此阶段。
- `cancelled` 是**正常可达终态**，由 `POST /api/v1/tasks/{tid}/cancel` 触发；`queued` 由 API 直接取消，处理中由 worker 在检查点响应。`persisting` 与 `awaiting_review` 不可取消。

**事件契约约束**：

- 每个事件自描述：能独立判断事件类型、所属任务、发生时间，不依赖连接上下文。
- 状态事件必须携带当前状态枚举值；失败事件必须携带可机读的错误码与可读原因。
- 事件按任务单调推进，消费者必须能丢弃迟到或重复的事件。
- 消费者必须**忽略未知字段与未知事件类型**，这是同一主版本内新增事件的前提。
- **每种事件有独立的载荷 schema 且 `required` 非空**，不允许一个宽松对象兼任所有事件（codex 审查 R04）。时序与终态语义见 `events.v1.md`。

### 5.3 图谱导入 / 导出

- 与 REST 分开建模：它是可落盘、可离线校验的文件格式，不是某个端点的响应体。
- 必须自带 `schema_version` 与课程标识，使一份导出文件脱离 API 也能被校验和导入。
- 关系类型只允许 ADR-008 的四类；导入时必须校验 `PREREQUISITE` 无环，并能报出导致冲突的节点/关系。
- 节点与关系必须携带来源引用，导出后仍可追溯到原文（ADR-003）。

### 5.4 来源引用的结构约束（ADR-003）

来源要求不能只写在 description 里——描述文字不构成 schema 约束，生成的客户端与结构校验不会拦住无依据的答案（codex 审查 R03）。因此：

- `ChatResponse` 按 `status` 分支：`answered` 的 `citations` **`minItems: 1`**；`not_covered` 的 `citations` 必须为空数组且必须给出 `reason`。
- 每条引用必须可定位：`page ≥ 1` 与非空 `section_path` **至少有一个**，两者都不接受 `null`。
- schema 只是第一道防线。「引用确属同一课程、同一发布版本」由服务层校验，schema 表达不了。

## 6. 版本化

两层，缺一不可：

1. **主版本 = 文件名与 URL 前缀**。`api.v1.yaml` 对应 REST 前缀 `/api/v1` 与生成物目录 `v1/`。破坏性变更新建 `api.v2.yaml`、`events.v2.md`、`errors.v2.md` 成套发布，`v1` 保留到前端迁移完成；删除旧版本需要新的 ADR。
2. **次版本 = 字段**。SSE 事件与图谱交换文件带 `schema_version`（形如 `"1.3"`），其主版本号必须与所在目录一致。REST 不带该字段，主版本由 URL 前缀表达。

| 变更 | 判定 | 做法 |
| --- | --- | --- |
| 新增可选字段 | 非破坏 | `schema_version` 次版本 +1 |
| 新增端点 | 非破坏 | 次版本 +1 |
| 新增事件类型 | 非破坏 | 次版本 +1；依赖消费者忽略未知类型 |
| 删除或重命名字段 | 破坏 | 升 v2 |
| 可选改必填、收紧类型 | 破坏 | 升 v2 |
| 枚举增删值、改变语义 | 破坏 | 升 v2 |

**枚举一次定稿原则**：枚举增值会打断前端的穷尽分支，属于破坏性变更，因此同一枚举的取值要在 v1 一次性定全。任务状态机的九个取值（含 `cancelled`）在 ADR-005 一次定稿，正是这条规则的结果。

## 7. 变更流程（强制）

1. 改 `api.v1.yaml`。先改前端类型或后端 schemas 属于契约违规。
2. 跑 `./scripts/gen-contracts.sh` 重新生成，产物一并提交。
3. 同一次提交同时更新受影响的规格、`docs/architecture.md` 或 ADR。
4. 跑 `./scripts/verify.sh`（其中 `scripts/verify/contracts.sh` 会跑 `check_contracts.py` 与 `gen-contracts.sh --check`）。
5. 前端若发现契约缺失或不合用，**不在前端本地修补**，通过交接文件把需求回送后端 Agent，由后端 Agent 改真源后重新生成。

`v1/generated/` 出现手工编辑，或 `--check` 不通过，PR 一律拒绝。

## 8. 与 S2 方案的关系

路径沿用 S2 表 6.6，但统一加上 `/api/v1` 前缀（ADR-004 第 8 条）。S2 为节省篇幅把 `PATCH`/`DELETE` 写在集合路径上，本契约按 REST 惯例细化为 `/{id}` 子路径；这是对缩写的展开，不是分歧。

S2 表 6.6 未列出但 MVP 必需、已在此补充的接口：任务状态轮询兜底、资料列表、知识点列表（卡片视图）、学习材料生成、版本列表与回滚。

## 9. 当前状态

- 真源 `api.v1.yaml` 已冻结（22 条路径）；`events.v1.md`、`errors.v1.md` 配套发布。
- 生成物与 `scripts/gen-contracts.sh` 已由 **A10 批 1 / M0-09 第二步** 导入并纳入 CI；前端消费生成类型由 **B15** 后续验证。
