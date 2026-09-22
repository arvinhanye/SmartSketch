# 契约（Contracts）

本目录是 SmartSketch 前后端共享协议的**单一真源**。`src/frontend/` 与 `src/backend/` 的所有对外数据结构都以此处为准；两边都不得自行定义同名结构。格式决策见 `docs/decisions.md` 的 ADR-004，任务状态机见 ADR-005。

## 1. 真源与生成物

| | 位置 | 谁写 | 规则 |
| --- | --- | --- | --- |
| 真源 | `v1/python/` | 后端 Agent | 手写 Pydantic v2 模型；唯一允许人工编辑的契约代码 |
| 生成物 | `v1/generated/` | `./scripts/gen-contracts.sh` | 入库，但**禁止手工编辑**；前端只读消费 |

- 后端从 `v1/python/` 导入 DTO，不在 `src/backend/app/schemas/` 重复定义对外模型。
- 前端从 `v1/generated/typescript/` 导入类型，不在 `src/frontend/` 内重写、断言或 `any` 绕过。
- 生成命令：`./scripts/gen-contracts.sh`（`--check` 为只校验模式：重新生成后 `git diff --exit-code`，不一致即失败）。

## 2. 目录结构

```text
src/contracts/
├── README.md                      # 本文件：格式、命名、版本化与变更流程
└── v1/
    ├── python/                    # ★ 真源（手写 Pydantic v2）
    │   ├── __init__.py            # 对外导出清单
    │   ├── common.py              # 跨类别复用：枚举、错误模型、来源引用、分页
    │   ├── rest_<resource>.py     # 一类 REST 资源一个文件
    │   ├── events_<domain>.py     # 一个事件域一个文件
    │   └── graph_exchange.py      # 图谱导入/导出格式
    └── generated/                 # ☆ 生成物（入库、只读）
        ├── openapi.json           # 由 FastAPI 应用导出
        ├── events-<domain>.schema.json
        ├── graph-exchange.schema.json
        └── typescript/
            ├── openapi.d.ts       # openapi-typescript 生成
            ├── events-<domain>.d.ts
            └── graph-exchange.d.ts
```

`v1/python/` 与具体模型文件由 M0-04a 创建；当前目录只有本说明。

## 3. 新文件放哪、叫什么

| 你要定义的东西 | 放进 | 文件命名 | 类型命名 |
| --- | --- | --- | --- |
| HTTP 请求体 / 响应体 | `v1/python/rest_<资源单数>.py` | `rest_course.py`、`rest_material.py`、`rest_task.py`、`rest_graph.py`、`rest_qa.py` | `XxxRequest` / `XxxResponse` / `XxxItem` |
| 一种新的 SSE 事件 | `v1/python/events_<域>.py` | `events_task.py` | `XxxEvent`，并注册进该域的事件联合类型 |
| 跨文件复用的枚举、错误码、来源引用、分页 | `v1/python/common.py` | 固定 | `XxxStatus` / `XxxType` / `ErrorCode` / `SourceRef` |
| 图谱导入或导出的文件格式 | `v1/python/graph_exchange.py` | 固定 | `GraphExport` / `GraphImportRequest` |
| 任何 TypeScript 类型 | 不手写 | — | 改真源后跑 `./scripts/gen-contracts.sh` |

命名规则：文件名小写下划线并带类别前缀（`rest_` / `events_`）；类名 PascalCase 并带用途后缀（`Request`、`Response`、`Item`、`Event`、`Error`）；枚举成员小写下划线，值即线上传输值。拿不准资源该不该单独成文件时，优先新建文件而不是往 `common.py` 堆。

## 4. 三类契约

### 4.1 REST DTO

- 路径前缀 `/api/v1`，与目录 `v1/` 同步升级。
- 每个端点必须声明成功响应与错误响应两类模型；错误使用 `common.py` 的统一错误模型与错误码枚举，不得每个端点各发明一套。
- 所有课程域资源的请求或路径中必须带 `course_id`（AGENTS.md §4、`.claude/rules/backend.md` 的课程隔离要求）。
- 问答响应必须能表达「带来源」与 `NOT_COVERED` 两种结果（ADR-003）。

### 4.2 SSE 任务事件

AGENTS.md §4 要求进度事件格式先在本目录定义，后端与前端才能实现。

**任务状态机（v1 规范，ADR-005）**：

```text
queued → parsing → extracting → merging → persisting → awaiting_review → completed
         └── 任一非终态 ──→ failed
         └── （v1 预留，MVP 不产生）──→ cancelled
```

- 终态：`completed`、`failed`、`cancelled`。终态之后不再发送该任务的进度事件。
- `persisting` 覆盖「DAG 校验 + 写入草稿图谱」，展示文案「校验入库」；前置关系成环导致的拒绝发生在此阶段。
- `cancelled` 为**预留终态**：MVP 不产生，也没有取消端点。前端必须把它当终态渲染，后端必须有测试断言 worker 不会发出该状态。实现取消功能前需先立规格与任务。

**事件契约约束**（具体字段由 M0-04a 定稿，此处只定不可违反的约束）：

- 每个事件自描述：能独立判断事件类型、所属任务、发生时间与 schema 版本，不依赖连接上下文。
- 状态事件必须携带当前状态枚举值；失败事件必须携带可机读的错误码与可读原因。
- 事件按任务单调推进，消费者必须能丢弃迟到或重复的事件。
- 消费者必须**忽略未知字段与未知事件类型**，这是同一主版本内新增事件的前提。

### 4.3 图谱导入 / 导出

- 与 REST 分开建模：它是可落盘、可离线校验的文件格式，不是某个端点的响应体。
- 必须自带 `schema_version` 与 `course_id`，使一份导出文件脱离 API 也能被校验和导入。
- 关系类型只允许 `CONTAINS`、`PREREQUISITE`、`RELATED_TO`、`EXAMPLE_OF`；导入时必须校验 `PREREQUISITE` 无环，并能报出导致冲突的节点/关系。
- 节点与关系必须携带来源引用，导出后仍可追溯到原文（ADR-003）。

## 5. 版本化

两层，缺一不可：

1. **主版本 = 目录**。`v1/` 对应 REST 前缀 `/api/v1`。破坏性变更新建 `v2/`，`v1/` 保留到前端迁移完成；删除旧版本需要新的 ADR。
2. **次版本 = 字段**。SSE 事件与图谱交换文件带 `schema_version`（形如 `"1.3"`），其主版本号必须与所在目录一致。REST 不带该字段，主版本由 URL 前缀表达。

| 变更 | 判定 | 做法 |
| --- | --- | --- |
| 新增可选字段 | 非破坏 | `schema_version` 次版本 +1 |
| 新增端点 | 非破坏 | 次版本 +1 |
| 新增事件类型 | 非破坏 | 次版本 +1；依赖消费者忽略未知类型 |
| 删除或重命名字段 | 破坏 | 升 `v2/` |
| 可选改必填、收紧类型 | 破坏 | 升 `v2/` |
| 枚举增删值、改变语义 | 破坏 | 升 `v2/` |

**枚举一次定稿原则**：枚举增值会打断前端的穷尽分支，属于破坏性变更，因此同一枚举的取值要在 v1 一次性定全。`cancelled` 被预留而非留待以后补，正是这条规则的结果（ADR-005）。

## 6. 变更流程（强制）

1. 改 `v1/python/` 的真源。先改前端类型或后端 schemas 属于契约违规。
2. 跑 `./scripts/gen-contracts.sh` 重新生成，产物一并提交。
3. 同一次提交同时更新受影响的规格、`docs/architecture.md` 或 ADR。
4. 跑 `./scripts/verify.sh`（M0-04a 起该脚本包含 `gen-contracts.sh --check`）。
5. 前端若发现契约缺失或不合用，**不在前端本地修补**，通过交接文件把需求回送后端 Agent，由后端 Agent 改真源后重新生成。

`generated/` 出现手工编辑，或 `--check` 不通过，PR 一律拒绝。

## 7. 当前状态

- 格式、目录与版本化规则已定稿（ADR-004、ADR-005）。
- 模型与生成脚本尚未创建：由 **M0-04a**（后端 Agent 起草真源与 `scripts/gen-contracts.sh`）交付，**M0-04b**（前端 Agent 消费生成类型并回送反馈）验证。本目录只由 M0-04a 写入。
