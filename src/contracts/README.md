# API and event contracts

前后端共享契约。实现代码、Cypher、前端类型**均以本目录为准**；契约先行，接口变更先改这里再写代码（AGENTS.md 第 2 节）。

## 文件

| 文件 | 内容 | 对应任务 |
| --- | --- | --- |
| `api.v1.yaml` | OpenAPI 3.1：全部 REST 路径、DTO schema、图谱交换格式、错误响应 | M0-04a、M0-04c |
| `events.v1.md` | SSE 事件名、顺序保证、心跳、终止与重连语义 | M0-04b |
| `errors.v1.md` | 错误码的 HTTP 状态、触发条件、`details` 结构与前端处理 | M0-04d |

`api.v1.yaml` 是唯一的机器可读源；两份 Markdown 补充 OpenAPI 无法表达的时序与语义。

## 校验

```bash
python3 -c "
from openapi_spec_validator import validate
from openapi_spec_validator.readers import read_from_filename
spec, _ = read_from_filename('src/contracts/api.v1.yaml')
validate(spec); print('valid')
"
```

`./scripts/verify.sh` 已包含该校验与契约不变量检查（关系类型、状态机、错误码闭集）。

## 三条硬约束

1. **命名基线是 ADR-004。** 关系类型只有 `CONTAINS`、`PREREQUISITE`、`RELATED_TO`、`EXAMPLE_OF`，不得引入别名。
2. **两个领域状态不是 HTTP 错误。** 问答证据不足返回 200 + `status = not_covered`；任务失败返回 200 + `stage = failed`。因此 `NOT_COVERED` 与 `TASK_FAILED` 不在 `ErrorCode` 枚举里，详见 `errors.v1.md`。
3. **`course_id` 是第一隔离条件。** 隔离在仓储层强制，`COURSE_FORBIDDEN` 只是第二道防线。

## 与 S2 方案的关系

路径沿用 S2 表 6.6。S2 为节省篇幅把 `PATCH`/`DELETE` 写在集合路径上，本契约按 REST 惯例细化为 `/{id}` 子路径；这是对缩写的展开，不是分歧。

S2 表 6.6 未列出但 MVP 必需、已在此补充的接口：任务状态轮询兜底、资料列表、知识点列表（卡片视图）、学习材料生成、版本列表与回滚。

## 版本策略

破坏性变更（删字段、改语义、改 HTTP 状态、改事件顺序）**新增 v2 文件**，不原地修改 v1：`api.v2.yaml`、`events.v2.md`、`errors.v2.md` 成套发布。新增可选字段与新增错误码为兼容变更，可在 v1 内进行，但前端须有未知 `code` 的兜底分支。
