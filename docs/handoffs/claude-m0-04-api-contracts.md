# Claude 交接：M0-04 API / SSE / 图谱 / 错误码契约定稿

- **状态**：DONE
- **日期**：2026-09-22
- **范围**：M0-04a~d 全部四项。产出前后端唯一共享契约，解除 M0-02、M0-03、M0-05 的并行阻塞。
- **前置**：ADR-004 命名基线（M0-06）、`specs/course-knowledge-graph.md` 验收条件 1–10。

## 已交付

| 文件 | 内容 | 任务 |
| --- | --- | --- |
| `src/contracts/api.v1.yaml` | OpenAPI 3.1：22 paths / 29 operations / 52 schemas | M0-04a、M0-04c |
| `src/contracts/events.v1.md` | SSE 事件名、顺序保证、进度映射、心跳、终止与重连 | M0-04b |
| `src/contracts/errors.v1.md` | 16 个错误码的 HTTP 状态、触发条件、`details` 结构 | M0-04d |
| `src/contracts/README.md` | 索引、三条硬约束、与 S2 表 6.6 的关系、版本策略 | — |
| `scripts/check_contracts.py` | 契约结构、`$ref` 完整性与不变量校验 | 门禁 |

## 定稿过程中的三项判定

### 1. `NOT_COVERED` 与 `TASK_FAILED` 是领域状态，不是错误码

原 M0-04d 的任务描述把两者列在错误码表里。这与 ADR-003 和 `.claude/rules/backend.md` 冲突：二者要求「返回可机读的未覆盖状态」，而 HTTP 4xx/5xx 会让**「课程资料未覆盖」与「服务故障」在前端无法区分** —— 前者是正常业务结果且必须原样展示给学生，后者需要重试与告警。

定稿为：

- 问答证据不足 → 200 + `ChatResponse.status = "not_covered"`，`citations` 为空数组，`answer` 给出可解释原因
- 任务处理失败 → 200 + `Task.stage = "failed"`，`Task.error` 填 `Error` 对象

两者因此**不在 `ErrorCode` 枚举中**，并由 `check_contracts.py` 强制拦截混入。任务看板的原描述已一并更正。

### 2. SSE 鉴权必须用一次性短时效令牌

`EventSource` 不支持自定义请求头，令牌只能走查询参数，而查询参数会进入访问日志与浏览器历史。因此 `GET /api/tasks/{tid}/events` 的令牌约定为：有效期 ≤60 秒、仅对该任务只读、与常规 Bearer 令牌分离。这一点在 `events.v1.md` 第 1 节明确写出，避免实现时直接把长效令牌塞进 URL。

### 3. 认证方案不依赖 D-03

D-03（登录是否先用本地演示角色）仍未裁定。契约按 Bearer JWT（载荷含 `sub`、`role`）编写 —— 无论登录后端最终是演示角色表还是其他方案，**传输层不变，契约无需返工**。因此本任务未被 D-03 阻塞，也未代为决策。

## 契约要点

- **路径沿用 S2 表 6.6**，避免制造新的 S2↔仓库分歧。S2 为省篇幅把 `PATCH`/`DELETE` 写在集合路径上，本契约展开为 `/{id}` 子路径；这是对缩写的细化，不是分歧。
- **S2 未列但 MVP 必需、已补充的接口**：任务状态轮询兜底 `GET /api/tasks/{tid}`、资料列表、知识点列表（卡片视图，验收条件 5）、学习材料生成（验收条件 7）、版本列表与回滚。
- **`GraphExchange` 一格式三用**：API 响应、G6 适配层输入、图谱导入导出。含 `format_version` 与 `GraphStats`（孤立点数、低置信度数、章节覆盖率），后者即建议中的「图谱质量体检」。
- **进度语义**：`progress` 按阶段分段推进并单调不减，前端直接使用，不得自行换算。分段表见 `events.v1.md` 第 2 节。
- **引用渲染时机**：`citations` 只在 `done` 事件给出最终值，`delta` 阶段正文中的编号可能指向随后被引用校验剔除的条目。**前端必须等 `done` 才能渲染可点击引用**，否则会出现点了跳空的引用。

## 验证

```text
./scripts/verify.sh
  → OK contract checks: OpenAPI 3.1.0 valid, 22 paths, 52 schemas, 181 refs resolved
  → Scaffold verification passed.

openapi-spec-validator 0.9.0  → OpenAPI 3.1.0 spec is VALID
$ref 完整性                    → 181 个引用全部解析，0 悬空
孤立 schema                    → 0
bash -n scripts/verify.sh      → 通过
```

负向测试（每次改动后均已还原，并以 `diff` 比对确认）：

| 注入的错误 | 结果 |
| --- | --- |
| `RelationType` 改用别名 `RELATED` | exit=1，命名漂移门禁在第 1101 行拦截 |
| 删除 `TaskStage` 的 `cancelled` | exit=1，`TaskStage misses ['cancelled']` |
| 把 `NOT_COVERED` 混入 `ErrorCode` | exit=1，`are domain states, not error codes` |
| 制造悬空 `$ref` | exit=1，`unresolved $ref` |
| 在 `api.v1.yaml` 写入 `APPLIES_TO` | exit=1，命名漂移门禁拦截 |
| 在 `errors.v1.md` 写入 `SourceChunk` | exit=1，命名漂移门禁拦截 |

> 首轮负向测试有两例误报为「未拦截」，原因是 `sed` 表达式与文件实际写法不匹配（enum 是内联流式序列、`EXAMPLE_OF` 未加反引号），文件根本没被改动。已用真实注入重测，六项全部确认拦截。

未运行前后端测试：`src/frontend/`、`src/backend/` 仍无实现代码（M0-02/M0-03 未开始）。

## 配置 / API / 数据影响

- **新增契约，无实现代码改动**，不存在迁移问题。
- `scripts/verify.sh` 变更：必需文件增加四项；`contract_docs` 扩展到 `api.v1.yaml` 与 `errors.v1.md`（兑现上一份交接的第 3 条下一步）；新增调用 `check_contracts.py`。
- **新增开发依赖（可选）**：`pyyaml`、`openapi-spec-validator`。`check_contracts.py` 在二者缺失时打印 SKIP 并继续，因此 `verify.sh` 不会因环境差异而失败。M0-03 建 `requirements-dev.txt` 时应固化这两项，CI 必须安装，否则形式校验会被静默跳过。
- 未新增环境变量。

## 风险与下一步

1. **CI 必须安装 `openapi-spec-validator`**，否则形式校验被跳过而门禁看起来仍是绿的。这是当前门禁最大的假阳性来源。
2. **契约与实现的一致性尚无强制手段**。建议 M0-03 用 FastAPI 生成的 OpenAPI 与本文件做 diff，纳入 `verify.sh`；否则实现漂移只能靠人工发现。
3. **D-02 仍阻塞 M1-03a**（模型供应商未裁定），D-03 不再阻塞 M0-03（见判定 3）。
4. `KnowledgePointUpdate`/`RelationUpdate` 用 `minProperties: 1` 表达「至少给一个字段」，OpenAPI 层面无法表达「字段间互斥」等更复杂约束，需在 `services/` 补业务校验。
5. 进度分段表（`parsing` 0–0.10 等）是基于 S2 6.6 耗时预算的**估计值**，M3-04 性能实测后应回填真实比例，否则进度条会在某一阶段长时间停滞。

## 回滚

本次仅新增契约文件与校验脚本，无实现代码与数据影响。

```bash
git checkout -- scripts/verify.sh docs/tasks.md src/contracts/README.md
```

新增文件用 `rm` 逐个移除：`src/contracts/api.v1.yaml`、`src/contracts/events.v1.md`、`src/contracts/errors.v1.md`、`scripts/check_contracts.py`。注意 `verify.sh` 的必需文件检查依赖这四个文件，必须与脚本改动同进同退。
