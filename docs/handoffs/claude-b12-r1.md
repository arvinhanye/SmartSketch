# Claude 交接：B12-R1 进度契约错误细节修订

- `task_id`: B12-R1（issue #223）
- `review_status`: ready_for_review（待 PR 审查/合并）
- `worktree`: `/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/b12-r1-progress-errors`，分支 `claude/b12-r1-progress-errors`
- `base_commit`: `d446ecc`（ADR-017 提交）
- 负责人：ArvinHan（Claude 子代理执行）
- 依据：ADR-017 决定 4、5；`specs/learning-path.md` §5、LP-12、LP-16；`docs/handoffs/claude-b12.md` 待决 1、2。只落实 ADR 已定的内容，不改其他规则。

## 交付物

- `src/contracts/api.v1.yaml`（唯一手改的真源）
  - **决定 4**：`LearningIntegrityDetails` 的 `diagnostic_id` 改名为 `request_id`，仍是闭合对象、必填；类型与问答 `ChatErrorDetails.request_id` 相同（`string`，`minLength: 1`，无 `format`/`pattern`）。
    - `LearningIntegrityError` 描述改为“既有 `INTERNAL_ERROR`，不新增专用码”，并写明读路径先投影再计算、`ProgressOutsideGraphError` 视为缺陷按本错误返回。
    - 三个学习读接口（`GET`/`PUT /progress`、`GET /recommend`）的 500 描述改为“只返回请求 ID（`details.request_id`）”。
  - **决定 5**：`PUT /progress` 的 422 不再引用通用 `ValidationError` 响应，改为 `ProgressValidationError`。新增 3 个 schema，命名沿用 B10 `TaskNotCancellableError`/`Task*Details` 与 B13 `Chat*Error`/`Chat*Details` 的先例：
    - `ProgressValidationError`：`Error` + `code = VALIDATION_ERROR` + `if/then`。只有当 `details.fields` 含 `reason = not_in_published_version`，或 `details` 带 `graph_version` 时，`details` 才必须是下述专用结构。schema 校验失败、同批重复等通用 422 不收窄（写法同 B13 `ChatUnavailableError`）。
    - `ProgressNotInPublishedVersionDetails{fields, graph_version}`：闭合；`fields` 至少 1 项；`graph_version ≥ 1`。
    - `ProgressNotInPublishedVersionField{in, field, reason}`：闭合；`in = "body"`；`field` 匹配 `^\[(0|[1-9][0-9]*)\]\.kp_id$`；`reason = "not_in_published_version"`。
    - 操作描述与 422 描述写明：草稿独有、已删除、他课三种情况同一 `reason`，不暴露他课是否存在；写入期间发布指针变化同样返回此错误；同批 `kp_id` 重复仍按 B12 已定的通用 422；客户端处置为重新 `GET /progress`。
- `src/contracts/errors.v1.md`：
  - HTTP `INTERNAL_ERROR` 行：`diagnostic_id` 改为 `request_id`，“专用码待定”改为“不新增专用码，ADR-017 决定 4”。
  - `VALIDATION_ERROR` 节：登记领域校验 reason `not_in_published_version`，包括字段表、示例、三种情况同一 reason，以及不用 404/409 的理由。
- `src/contracts/v1/generated/`：用 `./scripts/gen-contracts.sh` 重新生成 `openapi.json`、`python/models.py`、`typescript/openapi.d.ts`。独立 JSON Schema 未变，因为这些 schema 不在 `STANDALONE` 中。
- `specs/learning-path.md`（只做状态与细节标注，不改其他规则）：
  - §5 末尾加“目标不在当前发布版的拒绝码”一段，写明 422 与 `details` 结构。
  - LP-12 期望列补一句：先投影到当前发布版节点集再计算；`ProgressOutsideGraphError` 视为缺陷，按 `INTERNAL_ERROR` 返回。
  - §7 B12 标注下新增“B12-R1 已落实”说明：规格所称“诊断 ID”在 wire 上即 `details.request_id`。
- `tests/contracts/test_b12.py`：93 个用例增至 122 个，见下。

## 测试（先红后绿）

新增或修改的用例：

- 完整性错误：
  - 正例：带 `request_id`；
  - 负例：只用 `diagnostic_id`、`request_id` 与 `diagnostic_id` 并存、空串、多带 `cycle`/`kp_id`、错码；
  - `request_id` 定义与问答完全相同；
  - 真源和三份生成物中都不再出现 `diagnostic_id`；
  - 500 描述提到 `request_id`。
- 422 正例：多项、单项、`graph_version = 1`。另有 3 个通用 422 仍被接受（schema `enum`、`json_invalid`、无 `details`），用来证明没有过度收窄。
- 422 负例，共 17 个：
  - 缺 `graph_version`；`graph_version` 为 0 或字符串；
  - `details` 多出字段；某项多出 `input`（回显输入）；
  - `reason` 为 `not_found` 或 `missing`；与其他 reason 混排；
  - `in = query`；`field` 为 `[0].status`、`[-1].kp_id`、`[01].kp_id`；空 `fields`；
  - 错码 `NOT_FOUND`、`PUBLISH_IN_PROGRESS`；
  - 只有 reason、没有 `graph_version`；带 `graph_version` 但 reason 是其他值。
- 结构断言：两个新 schema 闭合，且只含 ADR 规定的字段。
- 生成物：
  - Pydantic：`ProgressNotInPublishedVersionDetails` 接受正例，拒绝 4 个负例；`LearningIntegrityError` 拒绝 `diagnostic_id`；
  - TS：`request_id: string`，`in: "body"`，`reason: "not_in_published_version"`；
  - `openapi.json` 与真源一致（新增 3 个 schema）。
- 文档：`errors.v1.md` 登记；规格 §5、LP-12 与 §7 的 B12-R1 标注。

| 阶段 | `python3 -m pytest tests/contracts/test_b12.py -q` |
| --- | --- |
| 改真源前（只改测试） | 34 failed / 88 passed（exit 1） |
| 改 YAML 后、重新生成前 | 6 failed / 116 passed：生成物未重新生成、文档与规格未改，属预期；另有一项检出真源描述中残留的 `diagnostic_id` 字样，已删除 |
| 最终 | 122 passed（exit 0） |

**反向篡改**：在真源上临时改坏一处，跑 B12 测试，再从备份恢复。每次恢复后用 `filecmp` 核对，最后用 `cmp` 与备份逐字节比较（exit 0），恢复后 122 passed。

| 篡改 | 结果 |
| --- | --- |
| T1 `LearningIntegrityDetails` 允许 `diagnostic_id` 与 `request_id` 并存 | 4 failed |
| T2 `ProgressNotInPublishedVersionDetails` 去掉 `graph_version` 必填 | 4 failed |
| T3 `reason` 的 `const` 放宽为 `enum [not_in_published_version, not_found]` | 3 failed |
| T4 删去 `if` 中“带 `graph_version` 即触发专用结构”的分支 | 5 failed |

## 实际验证（macOS，Python 3，datamodel-codegen 0.26.3，openapi-typescript 7.4.4，tsc 5.9.3）

| 命令 | 结果 |
| --- | --- |
| `python3 -m pytest tests/contracts/test_b12.py -q` | 122 passed（exit 0） |
| `python3 -m pytest tests/contracts -q` | 288 passed（exit 0） |
| `python3 -m pytest tests/contracts tests/tooling -q` | **1 failed / 301 passed（exit 1）**：失败项为 `tests/tooling/test_b07.py::test_dispatcher_reports_aggregate_status[0-PASS]`，原因是已有缺陷，与本任务无关，见风险 1 |
| `./scripts/gen-contracts.sh --check` | “生成物与真源一致”（exit 0） |
| `./scripts/verify.sh` | exit 0：B14 3、门禁负向 25 项，B08 5、B09 5、B10 45、B12 122、B13 53 passed，`PASS contracts gate` |
| `tsc --noEmit --strict openapi.d.ts b12r1_narrow.ts`（借用 `a09-dev-environment-check-8e5e93` worktree 的 `src/frontend/node_modules/.bin/tsc`，文件复制到会话临时目录） | exit 0。正例：`request_id`、完整 422 细节；`@ts-expect-error` 捕获 4 个负例：`diagnostic_id`、`reason: "not_found"`、缺 `graph_version`、`code: "NOT_FOUND"` |
| `git diff --check` | exit 0 |

## API / 数据变更

- **破坏性（wire）变更**：
  - `LearningIntegrityDetails.diagnostic_id` 改名为 `request_id`；
  - `PUT /progress` 的 422 响应 schema 由通用 `Error` 改为 `ProgressValidationError`（`code` 固定为 `VALIDATION_ERROR`）。
- **目前无消费者**：`src/frontend`、`src/backend` 中搜不到 `diagnostic_id`、`LearningIntegrityDetails`、`ProgressValidationError` 的引用；I02、I05 尚未实现。按 ADR-017 “后果”原地修改，不升 v2。
- 无数据库、迁移或环境变量变更。

## 风险

1. **`tests/tooling` 在基线上已失败（与本任务无关，未修，超出文件锁）**：
   - 现象：B14 把 `tests/contracts/test_b14.py` 接入 `scripts/verify/contracts.sh`，但 `tests/tooling/test_b07.py` 第 141 行 `shell_workspace` 夹具的占位清单只有 B08/B09/B10/B12/B13，没有 `test_b14.py`。于是门禁在夹具里报 “file or directory not found: tests/contracts/test_b14.py”，返回 1。
   - 已在临时 worktree 中按基线 `d446ecc` 复现同样的失败；`origin/main@130e6b6` 的夹具清单也缺这一项。
   - 修复只需一行：清单加 `"test_b14.py"`。与 B12 合并前复核补丁同类，请协调方另行处理。
2. **`field` 路径写法与 C13 全局校验处理器不一致**：
   - ADR-017 决定 5 原文为 `[<i>].kp_id`，本任务按原文实现：`pattern ^\[(0|[1-9][0-9]*)\]\.kp_id$`。
   - 但 `errors.v1.md` 对 `field` 的定义是“字段点路径，如 `items.0.name`”；`src/backend/app/main.py` 的 `_field_reason` 用 `".".join(loc[1:])` 生成路径。因此同一接口上，第 0 项的 schema 错误会是 `0.kp_id`，发布版校验错误却是 `[0].kp_id`。
   - 前端若按 `field` 定位，需要处理两种写法。建议协调方决定：保持 ADR 原文，还是勘误为 `<i>.kp_id`（统一为点路径）。若勘误，只需改 `ProgressNotInPublishedVersionField.field` 的 `pattern`、3 处描述、`errors.v1.md`、规格 §5 与测试夹具。
3. **`if/then` 不进生成物**（与 B12、B13 相同）：
   - `ProgressValidationError` 的 Pydantic/TS 类型只约束 `code`，`details` 仍是开放对象；“出现该 reason 或 `graph_version` 时 `details` 必须是专用结构”只由 JSON Schema 保证。
   - I02 应直接用 `ProgressNotInPublishedVersionDetails` 模型构造 `details`，以获得闭合校验。
4. 以下约束只写在描述里，由 I02 保证：`fields` 覆盖全部不在发布版中的项、`<i>` 与请求下标一致、`graph_version` 为复核所用版本。

## 待决（需人工决定）

- 风险 1：谁来修 `test_b07.py` 夹具（一行，超出本任务文件锁）。
- 风险 2：`field` 采用 `[<i>].kp_id`（ADR 原文）还是 `<i>.kp_id`（C13 点路径）。

## 下一步

- 请 Codex 审查。I02（进度 API）按决定 5 与 `ProgressNotInPublishedVersionDetails` 实现；I05 按决定 4 先投影再调用 I03。

## 回滚

`git revert` 本分支的 B12-R1 提交即可恢复到 B12 契约（`diagnostic_id` 与通用 422）及对应生成物。无数据库或外部状态。
