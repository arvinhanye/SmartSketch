# Claude 交接：B12 进度与推荐契约

- `task_id`: B12
- `review_status`: ready_for_review（待 PR 审查/合并）
- `worktree`: `/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/b-task-subprocess-issue-sync-d87624`，分支 `claude/b12-progress-contract`
- `base_commit`: `main@8eeac3b`（认领提交 `7adec1f`）
- 负责人：ArvinHan（Claude 子代理执行）
- 依据：`specs/learning-path.md` §1～§5、LP-1～20、§7；ADR-014 及修订 1（决定 5～10）；`docs/atomic-task-plan.md` B12 行与 `docs/atomic-tasks.json` B12 `acceptance`。只落实规格列出的接口语义，不改规则。

## 交付物

- `src/contracts/api.v1.yaml`（唯一手改的真源）
  - **进度**
    - `ProgressEntry` 必填 `kp_id, status, own_status, inherited_from, updated_at`，闭合对象：
      - `status` 为有效状态；
      - `own_status` 为 `MasteryStatus | null`；
      - `inherited_from[]` 的项为新 schema `ProgressInheritedSource{kp_id, status}`，闭合，不带 `write_seq`/`commit_seq`；
      - `updated_at` 为 `date-time | null`。
    - `ProgressEntry` 用 `allOf` + `if/then` 约束两条不变式：`own_status` 与 `updated_at` 同为 null；`status` 等于 `own_status`（null 按 unknown）与 `inherited_from[].status` 中的最高者。
    - 新增 `ProgressResponse{graph_version, entries}`，`entries` 至少 1 项。`GET` 与 `PUT /progress` 的 200 都返回它，描述写明“返回 V 中每个节点”。
    - `PUT` 请求为 `minItems: 1` 的 `ProgressUpdate[]`。`ProgressUpdate` 闭合（不接受 `user_id`），`kp_id` 非空。整批拒绝/零写入、重复 `kp_id`、同值写入、发布指针变化后按新版本回传 `graph_version` 均写入操作描述。
    - 两个进度操作都补上 404 `GRAPH_NOT_PUBLISHED` 与 500 `LearningIntegrityError`。
  - **推荐**
    - `RecommendResponse` 改为按 `state` 判别的两支：
      - `RecommendListResponse`：`state = recommendations`，`total_eligible ≥ 1`，列表 1～50 条；
      - `RecommendAllMasteredResponse`：`state = all_mastered`，`total_eligible = 0`，列表为空。
      - 闭集中没有 `no_graph`。
    - `Recommendation` 必填：`kp_id, name, graph_version, score, factors, weighted, unlock_count, reason, reason_facts`。
      - `factors`（`RecommendFactors`）：四个原始分量，各在 [0,1]，属性顺序 u→i→c→e；
      - `weighted`（新增 `RecommendWeightedFactors`）：四个加权分量，只设下限 0，因为权重和允许 1 ± 1e-9；
      - 两者都是 `format: double`，不设 `multipleOf`。`score` 描述写明按 u→i→c→e 求和后逐位相等，只在展示时舍入；
      - `reason_facts`：新增 `RecommendReasonFacts`，含 `primary_factor`、章节 id/名/秩（三者同时为 null）、重要度、中心度与难度；
      - 用 `if/then` 约束 `unlock_count = 0 ⇔ factors.unlock = 0`。
      - 附一个逐位示例：`score 0.725`，反序求和得 `0.7250000000000001`。
    - 推荐操作补上 422（`limit` 越界）与 500 `LearningIntegrityError`；移除 `target` 参数与 `path` 字段（见决定 3）。`LearningPath`、`PathStep` 两个 schema 保留，描述标注“O02 前不被接口引用”。
  - **完整性错误**：新增 `LearningIntegrityError`，形状为 `Error` + `code = INTERNAL_ERROR` + 闭合 `details`（`LearningIntegrityDetails{diagnostic_id}`）。节点 ID 和环路无法放进 `details`。
- `src/contracts/v1/generated/`：用 `./scripts/gen-contracts.sh` 重新生成 `openapi.json`、`python/models.py`、`typescript/openapi.d.ts`。独立 JSON Schema 未变，因为 B12 的 schema 不在 `STANDALONE` 中。
- `tests/contracts/test_b12.py`：93 个用例，覆盖成功、边界与失败路径，也检查生成物和规格标注。
- `scripts/verify/contracts.sh`：按 B08～B13 的先例在 B10 与 B13 之间接入 B12。
- `specs/learning-path.md`：只加状态标注，不改规则。顶部状态行改为“B12 wire 契约已落实”，§7 的 B12 条目下加“B12 已落实”说明。
- **范围扩展**：`src/contracts/errors.v1.md` 的 HTTP `INTERNAL_ERROR` 一行登记了进度与推荐接口的 `details.diagnostic_id`。原因是该文件的实现约束要求 `details` 的结构必须在本文件中有说明，否则真源与错误码文档会不一致。

## 关键决定（请审查）

1. **进度响应从裸数组改为 `ProgressResponse{graph_version, entries}`**。§5 要求成功的 `PUT` 在发布指针变化时“回传新 `graph_version`”，进度响应也须与推荐按同一绑定版本计算。裸数组放不下版本号；在每项上重复版本号冗余，放在响应头又不进类型生成。这是结构上的破坏性变更，目前没有消费者（I02、I06 未实现）。
2. **完整性错误暂用既有 `INTERNAL_ERROR`，`details` 只含 `diagnostic_id`**。§7 写的是“B08 须确定学生读路径完整性错误的公开错误码”，但 B08 没有确定。这里选了不新增错误码的最小方案，字段名沿用规格用语“诊断 ID”。专用码仍待决（见下）。
3. **移除推荐接口的 `target` 参数与 `path` 响应**。依据是 §7 末条：“O01 未批准前……不承诺目标路径 API”。O02（依赖 B12）负责重新定义目标路径契约。这不是替规格拍板，而是按规格删掉候选真源里的越界承诺。
4. **同批重复 `kp_id` 归入 422 `VALIDATION_ERROR`**。这属于请求体本身的校验，不需要查领域数据，与 `errors.v1.md` 对该码的定义一致；JSON Schema 无法表达，由服务端校验。
5. 保留原有的 `name` 与分量键名 `chapter_order`，不改名。新增的 `reason_facts.primary_factor` 是 §4“一句话优先解释加权贡献最大的分量”的结构化事实，并列时的顺序按规格。

## 待决（已登记 `docs/tasks.md` B12 小节）

1. **学生读路径完整性错误的公开码**：继续用 `INTERNAL_ERROR`，还是新增专用码（须同改 `ErrorCode` 与 `errors.v1.md`）？另需确认 `details.diagnostic_id` 的字段名，是否要与问答的 `details.request_id` 统一。需 ArvinHan 决定。
2. **`PUT /progress` 中 `kp_id` 不在绑定发布版时的整批拒绝**（草稿独有、已删除、他课，或发布指针变化后复核失败）：公开码是 422 `VALIDATION_ERROR`、404 还是 409，`details` 形状如何？规格只写了“整批拒绝、零写入”，契约描述中暂写“待定”。需在 I02 之前决定。

## 实际验证（macOS，Python 3，jsonschema 4.26.0，datamodel-codegen 0.26.3，openapi-typescript 7.4.4，tsc 5.9.3）

| 命令 | 结果 |
| --- | --- |
| 改真源前 `python3 -m pytest tests/contracts/test_b12.py -q` | 65 failed / 28 passed（exit 1）。通过的 28 项是旧 `ProgressEntry` 本就会拒的缺字段负例，以及旧的宽松 `RecommendResponse` 什么都接受的正例 |
| 改真源并重新生成后首次运行 | 3 failed / 90 passed。一项是规格标注未加（预期）；另两项是测试缺陷，已在 `e53cbdf` 修正，见下 |
| 最终 `python3 -m pytest tests/contracts/test_b12.py -q` | 93 passed（exit 0） |
| `python3 -m pytest tests/contracts -q` | 255 passed（exit 0） |
| `./scripts/gen-contracts.sh --check` | “生成物与真源一致”（exit 0） |
| `./scripts/verify.sh` | exit 0：门禁负向测试 24 项，B08 5、B09 5、B10 45、B12 93、B13 53 passed，`PASS contracts gate` |
| `tsc --noEmit --strict openapi.d.ts b12_narrow.ts`（借用 `a09-dev-environment-check-8e5e93` worktree 的 `node_modules/.bin/tsc`，文件复制到会话临时目录） | exit 0。检查项：按 `state` 收窄后 `total_eligible` 为 `0`；`@ts-expect-error` 捕获缺 `own_status` 与 `state: "no_graph"` 两个负例 |
| `git diff --check` | exit 0 |

测试缺陷修正（`e53cbdf`）：

- 原先用整段 YAML 的子串判断“无 `path`”，会误命中描述中的链接 `learning-path.md`。改为检查判别分支中没有 `path` 属性，且没有接口引用 `LearningPath`。
- datamodel-codegen 对 OpenAPI 3.1 的必填可空字段生成 `= None` 默认值，因此 Pydantic 断言改为检查字段存在和闭合对象，理由见风险 1。

**反向篡改**（在真源上临时改坏一处，运行 B12 测试，再从备份恢复并确认字节一致；恢复后 93 passed）：

| 篡改 | 结果 |
| --- | --- |
| T1 `all_mastered` 的 `const` 改成 `enum [all_mastered, no_graph]` | 2 failed（`no_graph` 负例、闭集判别） |
| T2 `ProgressEntry` 去掉 `own_status` 必填 | 3 failed |
| T3 推荐列表去掉 `minItems: 1`（空列表冒充全部掌握） | 1 failed |
| T4 `score` 加 `maximum: 1` 与 `multipleOf: 0.0001`（按展示精度舍入） | 8 failed |
| T5 `LearningIntegrityDetails` 去掉 `additionalProperties: false`（外露环路） | 1 failed |
| T6 使 `status = mastered` 的出处不变式失效 | 2 failed |

## API / 数据变更

- 破坏性（wire）变更：
  - `GET`/`PUT /progress` 的响应由数组改为对象；
  - `ProgressEntry` 增加必填字段，`updated_at` 可为 null；
  - `RecommendResponse` 改为按 `state` 判别；
  - `Recommendation` 增加必填字段；
  - 移除 `target` 与 `path`。
- 目前没有前后端消费者（`src/frontend`、`src/backend` 中搜不到这些 schema 的引用）。
- 无数据库、迁移或环境变量变更。

## 风险

1. **Pydantic 生成物不强制“必填可空”**：datamodel-codegen 0.26.3 把 `own_status`、`updated_at` 生成为 `Optional[...] = None`。既有的 `GraphExchange.graph_version` 也是如此；在临时目录试过 `--strict-nullable`，对 3.1 的类型数组无效。I02 实现时不能依赖 Pydantic 发现缺字段；是否修生成链交 B14 处理。
2. **`if/then` 不进生成物**（与 B13 的 `ChatMetaEvent` 相同）。以下约束须由 I01、I02、I04、I05 在服务端保证：
   - `status` 等于最高者；
   - `own_status` 与 `updated_at` 同空；
   - `unlock_count = 0 ⇔ u = 0`；
   - 章节三字段同时为 null。
   生成的 TS 类型中这些位置会出现 `& (unknown & …)`。
3. 以下约束只写在描述里，无法用 schema 表达，由实现与后续测试保证：
   - `inherited_from[]` 的字节序与去重；
   - `entries` 与 V 一一对应；
   - `total_eligible ≥ 列表长度`；
   - 每条推荐的 `graph_version` 与响应一致。
4. 观察到 `tests/contracts/test_b11.py` 没有接入 `scripts/verify/contracts.sh`（门禁只跑 B08、B09、B10、B12、B13）。不属于 B12 范围，未改动，请主会话决定是否另开任务。

## 下一步

- 请 Codex 审查；先决定两项待决，再做 I02（进度 API）与 I05（推荐 API）。
- B14（契约导出与漂移检查）可考虑处理风险 1。

## 回滚

只撤销本分支的 B12 提交（`git revert` 对应 SHA）即可恢复原契约与生成物。无数据库或外部状态。
