# 错误码契约 v1

- **版本**：1.0.0，与 `api.v1.yaml` 同步发布
- **枚举来源**：`api.v1.yaml` 的 `ErrorCode`。本文件为每个码补充 HTTP 状态、触发条件与前端处理建议。

## 响应体

所有 HTTP 错误统一返回 `Error`：

```json
{
  "code": "CYCLE_DETECTED",
  "message": "新增前置关系会形成学习环路",
  "details": { "cycle": ["kp_12", "kp_30", "kp_45", "kp_12"] }
}
```

`code` 供程序分支，`message` 供用户阅读，`details` 可选且结构随 `code` 而定。

---

## ⚠️ 不是错误的两个状态

这是本契约最容易被实现错的地方。以下两种情况 **HTTP 状态为 200**，必须以可机读的领域状态返回，而不是抛错：

| 情况 | 正确做法 | 依据 |
| --- | --- | --- |
| 问答证据不足 | 200 + `ChatResponse.status = "not_covered"`，`citations` 为空，`answer` 给出可解释原因 | ADR-003、`.claude/rules/backend.md` |
| 任务处理失败 | 200 + `Task.stage = "failed"`，`Task.error` 填 `Error` 对象 | ADR-005 状态机 |

`NOT_COVERED` 与 `TASK_FAILED` 因此**不在 `ErrorCode` 枚举中** —— 它们是状态，不是错误码。把它们做成 HTTP 4xx/5xx 会让「资料未覆盖」与「服务故障」在前端无法区分，直接违反可信问答的硬契约。

---

## 错误码表

### 认证与授权

| 码 | HTTP | 触发条件 | 前端处理 |
| --- | --- | --- | --- |
| `UNAUTHENTICATED` | 401 | 缺少令牌、令牌过期或签名无效 | 清除本地令牌，跳登录页 |
| `ROLE_FORBIDDEN` | 403 | 角色不允许该操作，如学生调用教师端编辑接口 | 提示无权限，不重试 |
| `COURSE_FORBIDDEN` | 403 | 访问不属于当前用户的课程；多课程隔离的兜底防线 | 提示无权限，返回课程列表 |

> 课程隔离在仓储层按 `course_id` 强制过滤（`.claude/rules/backend.md`）。`COURSE_FORBIDDEN` 是**第二道**防线，不是唯一防线；不得依赖它来实现隔离。

### 资源

| 码 | HTTP | 触发条件 | 前端处理 |
| --- | --- | --- | --- |
| `NOT_FOUND` | 404 | 课程、资料、任务、知识点或关系不存在；审核项已不在审核队列中（ADR-060） | 提示并返回上一级 |
| `GRAPH_NOT_PUBLISHED` | 404 | 学生读取尚未发布的课程图谱 | 提示「课程尚未发布」，不暴露草稿存在与否 |

> `GRAPH_NOT_PUBLISHED` 用 404 而非 403，避免向学生泄露「该课程存在但你看不到」这一信息。

### 上传与解析

| 码 | HTTP | 触发条件 | 前端处理 |
| --- | --- | --- | --- |
| `UNSUPPORTED_FORMAT` | 415 | 扩展名或嗅探结果不属于 PDF/DOCX/TXT/Markdown | 在上传组件内高亮该文件，列出支持格式 |
| `FILE_TOO_LARGE` | 413 | 超出单文件上限 | 提示上限值，`details.limit_bytes` 给出数值 |
| `VALIDATION_ERROR` | 422 | 请求体、查询、路径、请求头或 Cookie 参数不满足 schema | 按 `details.fields` 定位到具体字段，结构见下 |

`VALIDATION_ERROR` 的 `details` 固定为 `{"fields": [...]}`，每个出错位置一项，顺序与校验器报告的顺序相同：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `in` | string | 出错的请求部位：`body`、`query`、`path`、`header`、`cookie`；无法归入任何部位时为空串 |
| `field` | string | 该部位内的字段点路径，如 `password`、`items.0.name`；整个部位出错（缺少请求体、JSON 无法解析）时为空串 |
| `reason` | string | 机读原因，取 Pydantic 错误类型，如 `missing`、`string_too_long`、`too_long`、`int_parsing`、`json_invalid` |

```json
{
  "code": "VALIDATION_ERROR",
  "message": "请求参数不符合要求，请检查标注的字段",
  "details": { "fields": [{ "in": "body", "field": "password", "reason": "missing" }] }
}
```

- **不回显输入**：`details` 不含提交的值或校验器的原文说明，口令等敏感字段只以字段名出现。
- `reason` 的取值随校验库而定，不是闭集。前端按 `in` 与 `field` 定位字段，遇到不认识的 `reason` 显示通用提示。
- 本服务自己在业务校验中产生的**领域 `reason`** 不是校验库取值，须在本文登记后使用：`details.fields[].reason` 上当前已登记的是 `duplicate` 与 `not_in_published_version`（都在 `PUT /progress`，见下）。其他错误码的领域取值写在各自的行内（如 `DOCUMENT_NOT_DELETABLE` 的 `details.reason`）。
- 由后端全局请求校验处理器统一产生（C13 引入），所有路由都用这个形状。

**领域校验 reason `not_in_published_version`**（`PUT /progress`，ADR-017 决定 5）：请求体通过 schema 校验后，若有目标 `kp_id` 不在请求事务所见的当前发布版中，整批拒绝、零写入，返回 422 `VALIDATION_ERROR`，`details` 为闭合对象（`api.v1.yaml` 的 `ProgressValidationError` / `ProgressNotInPublishedVersionDetails`）：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `fields[]` | array | 每个不在发布版中的请求项一项，固定为 `{in: "body", field: "<i>.kp_id", reason: "not_in_published_version"}`，`<i>` 为请求数组下标，与上表 `field` 的点路径写法一致（ADR-017 勘误）；不与其他 `reason` 混排 |
| `graph_version` | integer | 请求事务所见的当前发布版本号；写入期间发布指针变化时为复核所用的新版本 |

```json
{
  "code": "VALIDATION_ERROR",
  "message": "部分知识点不在当前发布的课程图谱中，请刷新后重试",
  "details": {
    "fields": [{ "in": "body", "field": "0.kp_id", "reason": "not_in_published_version" }],
    "graph_version": 4
  }
}
```

- 草稿独有、已删除、他课三种情况同一 `reason`，不暴露他课节点是否存在；写入期间发布指针变化、目标不在新版本时同样返回此错误。
- 不用 404（`/progress` 资源本身存在）也不用 409：客户端处置都是重新 `GET /progress` 后再提交。
- 同批 `kp_id` 重复不用这个 `details` 形状，见下条。

**领域校验 reason `duplicate`**（`PUT /progress`，ADR-064 决定 2）：请求体通过 schema 校验后，若同一批次里同一个 `kp_id` 出现多次（无论状态是否相同），整批拒绝、零写入，返回 422 `VALIDATION_ERROR`；`details` 只有 `fields`、不带 `graph_version`，沿用上表的通用形状（`api.v1.yaml` 的 `ProgressValidationError`）：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `fields[]` | array | 每个**重复出现**的请求项一项，固定为 `{in: "body", field: "<i>.kp_id", reason: "duplicate"}`，`<i>` 为请求数组下标，写法同上表 `field`；首次出现的那一项不列 |

```json
{
  "code": "VALIDATION_ERROR",
  "message": "请求参数不符合要求，请检查标注的字段",
  "details": { "fields": [{ "in": "body", "field": "2.kp_id", "reason": "duplicate" }] }
}
```

- 与 `not_in_published_version` 一样是整批拒绝、零写入；`message` 用全局 422 的通用文案，不回显 `kp_id` 的值。
- 检查在开启写事务之前完成（ADR-064 决定 2），因此本错误不涉及发布版本，不带 `graph_version`。

### 图谱编辑

| 码 | HTTP | 触发条件 | `details` | 前端处理 |
| --- | --- | --- | --- | --- |
| `CYCLE_DETECTED` | 409 | 新增或修改 `PREREQUISITE`（含合并知识点后重接的边，ADR-047）会使前置关系成环 | `cycle`: 节点 ID 链路，首尾同一节点 | **在图谱上高亮该环路**并拒绝保存 —— 规格验收条件 4 要求返回冲突信息，不是简单报错 |
| `DANGLING_ENDPOINT` | 422 | 关系端点不存在，或不属于同一课程 | `missing`: 缺失的端点 ID | 提示端点无效 |
| `DUPLICATE_RELATION` | 409 | 同课程内已存在同类型同方向的关系 | `existing_id` | 提示已存在，可跳转至该关系 |
| `NODE_LOCKED` | 409 | 自动流程试图覆盖 `locked = true` 的节点 | `kp_id` | 仅后台流程触发，前端一般不可见 |
| `REVISION_CONFLICT` | 409 | 教师编辑、解锁、合并或删除知识点时 `expected_revision`（合并为 `expected_revisions`）与当前节点修订号不一致：期间已有他人写入（ADR-035、ADR-047、ADR-048） | `kp_id`、`expected_revision`、`current_revision`、`current`（当前的 `name`、`aliases`、`type`、`definition`、`status`、`locked`，以及存在时的 `importance`、`difficulty`） | 不覆盖；向用户展示 `current` 与本地修改的差异，确认后以 `current_revision` 重新提交 |

### 任务与发布

| 码 | HTTP | 触发条件 | 前端处理 |
| --- | --- | --- | --- |
| `TASK_NOT_CANCELLABLE` | 409 | 任务正在入库（`persisting`）、已处理结束（`awaiting_review`）或已处于终态时调用取消；`details: {stage, reason}` 为闭集，见 `api.v1.yaml` 的 `TaskNotCancellableError` | 按 `details.stage` 刷新任务状态，隐藏取消按钮 |
| `DOCUMENT_NOT_DELETABLE` | 409 | 删除资料时该资料仍有未结束的任务，或已有任务处理结束（`awaiting_review`/`completed`）而产生了图谱贡献（ADR-021）；`details: {stage, reason}`，`reason` 为 `processing`、`contributed` 或 `cleanup_pending`（失败任务的图谱清理未完成） | 按 `details.stage` 刷新资料状态，隐藏删除按钮 |
| `PUBLISH_BLOCKED` | 409 | 发布前校验未通过，如存在未解决的环冲突 | `details.reasons` 列出阻塞项，引导至审核队列 |
| `PUBLISH_IN_PROGRESS` | 409 | 同一课程已有发布或回滚进行中 | 等待当前操作结束后刷新版本列表 |
| `COURSE_BUSY` | 409 | 获取课程写锁的有界等待超时 | `details.holder` 标明持锁操作；稍后重试 |

任务处理失败仍按上文返回 200 的 `Task.error`，其中 `code` 可为下列值，不把任务失败变成 HTTP 错误：

| 码 | 触发条件 | `details` |
| --- | --- | --- |
| `DOCUMENT_UNREADABLE` | 文档损坏、加密或无可提取文本 | `reason` 为 `corrupted`、`encrypted` 或 `no_text` |
| `EXTRACTION_INCOMPLETE` | 抽取失败块超阈值，且并非全部由模型不可用导致 | `chunks_failed`、`chunks_total`、`threshold`、按错误码计数 |
| `STORAGE_UNAVAILABLE` | 图库或数据库不可用、写入失败 | 重试耗尽时另含 `attempts`、`stage` |
| `INTERNAL_ERROR` | 未预期的处理错误 | 不包含堆栈、密钥或原文 |
| `TASK_ATTEMPTS_EXHAUSTED` | 连续租约过期，原因不明且任务尝试耗尽 | `attempts`、`stage` |

### 外部依赖

| 码 | HTTP | 触发条件 | 前端处理 |
| --- | --- | --- | --- |
| `RATE_LIMITED` | 429 | 触发本服务限流（如登录失败限流）。供应商返回的 429 不外露：按 A07 矩阵首字前切备用，最终失败为 `LLM_UNAVAILABLE`（问答 `details.reason = upstream`） | 读 `Retry-After`，指数退避后重试 |
| `LLM_UNAVAILABLE` | 503 | 主模型与备用模型均不可用 | 提示稍后重试；构图场景下任务转 `failed` 并保留已完成的块 |
| `BUDGET_EXCEEDED` | 429 | 调用前发现任务或当日 token 预算已耗尽；不再发模型请求 | 提示额度耗尽；问答返回错误，抽取按失败块规则处理，不自动重试 |
| `STORAGE_UNAVAILABLE` | 503 | 同步请求的存储依赖不可用 | 提示稍后重试；异步任务按上表返回 200 快照 |
| `INTERNAL_ERROR` | 500 | 同步请求遇到未预期错误；学习进度与推荐接口遇到已提交版完整性故障（含 V=∅）也用此码（`LearningIntegrityError`，不新增专用码，ADR-017 决定 4） | 显示通用失败提示，服务端日志保留诊断信息；进度与推荐接口的 `details` 为闭合对象，只含 `request_id`（与问答 `details.request_id` 同名同型，用于日志关联），不含节点 ID 或环路 |

---

## 实现约束

- 错误码为**闭集**。新增码必须先改 `api.v1.yaml` 的 `ErrorCode` 枚举与本文件，再写实现。
- 路由层只做协议转换：领域异常在 `services/` 抛出，由统一异常处理器映射为 `Error`（`.claude/rules/backend.md`）。
- `message` 面向用户，不得泄露堆栈、SQL、Cypher、文件路径或模型提示词。
- `details` 可选；若提供，其结构须在本文件中有对应说明，不得随实现漂移。

## 变更策略

删除错误码或改变其 HTTP 状态属于破坏性变更，需新增 `errors.v2.md` 并同步 `api.v2.yaml`。新增错误码为兼容变更，但前端必须有兜底分支处理未知 `code`。
