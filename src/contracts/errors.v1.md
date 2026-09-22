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
| 任务处理失败 | 200 + `Task.stage = "failed"`，`Task.error` 填 `Error` 对象 | ADR-004 状态机 |

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
| `NOT_FOUND` | 404 | 课程、资料、任务、知识点或关系不存在 | 提示并返回上一级 |
| `GRAPH_NOT_PUBLISHED` | 404 | 学生读取尚未发布的课程图谱 | 提示「课程尚未发布」，不暴露草稿存在与否 |

> `GRAPH_NOT_PUBLISHED` 用 404 而非 403，避免向学生泄露「该课程存在但你看不到」这一信息。

### 上传与解析

| 码 | HTTP | 触发条件 | 前端处理 |
| --- | --- | --- | --- |
| `UNSUPPORTED_FORMAT` | 415 | 扩展名或嗅探结果不属于 PDF/DOCX/TXT/Markdown | 在上传组件内高亮该文件，列出支持格式 |
| `FILE_TOO_LARGE` | 413 | 超出单文件上限 | 提示上限值，`details.limit_bytes` 给出数值 |
| `VALIDATION_ERROR` | 422 | 请求体不满足 schema | 定位到具体字段，`details.fields` 给出字段级说明 |

### 图谱编辑

| 码 | HTTP | 触发条件 | `details` | 前端处理 |
| --- | --- | --- | --- | --- |
| `CYCLE_DETECTED` | 409 | 新增或修改 `PREREQUISITE` 会使前置关系成环 | `cycle`: 节点 ID 链路，首尾同一节点 | **在图谱上高亮该环路**并拒绝保存 —— 规格验收条件 4 要求返回冲突信息，不是简单报错 |
| `DANGLING_ENDPOINT` | 422 | 关系端点不存在，或不属于同一课程 | `missing`: 缺失的端点 ID | 提示端点无效 |
| `DUPLICATE_RELATION` | 409 | 同课程内已存在同类型同方向的关系 | `existing_id` | 提示已存在，可跳转至该关系 |
| `NODE_LOCKED` | 409 | 自动流程试图覆盖 `locked = true` 的节点 | `kp_id` | 仅后台流程触发，前端一般不可见 |

### 任务与发布

| 码 | HTTP | 触发条件 | 前端处理 |
| --- | --- | --- | --- |
| `TASK_NOT_CANCELLABLE` | 409 | 对已处于终态的任务调用取消 | 刷新任务状态，隐藏取消按钮 |
| `PUBLISH_BLOCKED` | 409 | 发布前校验未通过，如存在未解决的环冲突 | `details.reasons` 列出阻塞项，引导至审核队列 |

### 外部依赖

| 码 | HTTP | 触发条件 | 前端处理 |
| --- | --- | --- | --- |
| `RATE_LIMITED` | 429 | 触发模型 API 或本服务限流 | 读 `Retry-After`，指数退避后重试 |
| `LLM_UNAVAILABLE` | 503 | 主模型与备用模型均不可用 | 提示稍后重试；构图场景下任务转 `failed` 并保留已完成的块 |

---

## 实现约束

- 错误码为**闭集**。新增码必须先改 `api.v1.yaml` 的 `ErrorCode` 枚举与本文件，再写实现。
- 路由层只做协议转换：领域异常在 `services/` 抛出，由统一异常处理器映射为 `Error`（`.claude/rules/backend.md`）。
- `message` 面向用户，不得泄露堆栈、SQL、Cypher、文件路径或模型提示词。
- `details` 可选；若提供，其结构须在本文件中有对应说明，不得随实现漂移。

## 变更策略

删除错误码或改变其 HTTP 状态属于破坏性变更，需新增 `errors.v2.md` 并同步 `api.v2.yaml`。新增错误码为兼容变更，但前端必须有兜底分支处理未知 `code`。
