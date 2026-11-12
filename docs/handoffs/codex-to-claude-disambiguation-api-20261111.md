# Claude 接口交接：生成消歧审核与自动合并撤销

日期：2026-11-11。任务 DISAMBIG-BE-03，Codex 当前分支 `codex/knowledge-disambiguation`，基线 `31a7e6c`，承接 BE-01/02 未提交成果。Claude 审核页核对基线为 `d102915`（F1–F5 修复）。本批不自动提交、合并或推送，不写 Claude 工作树。

后端、契约与最小客户端已实现；最终门禁结果见下方验证记录。**自动合并默认仍关闭**，真实模型质量、人工减负与生成耗时没有在本批签收。

## 先接什么

你现有的 `reviewApi.getQueue` 和 `resolve` 路径不变，接到本批后端后立即使用同一套过滤后列表、totals 与分页。保留并排对比、来源计数、只记录真实处理结果、预览新鲜度和并发请求隔离修复。

主工作树前端改动仅：新增 `src/frontend/src/api/disambiguation.ts`；`useReview.ts` 的原因文案表增加两行。**不要用主工作树旧版 `useReview.ts` 整文件覆盖你的新版**。取新增客户端与本批契约生成物，在你的文案表追加：

```ts
semantic_uncertain: '同义关系仍需确认',
merge_blocked: '同义提案未通过自动合并约束',
```

覆盖概况、自动历史和撤销控件是下一步 UI 接入点；它们不在 `d102915` 现有页面里，本批没有重写你的页面布局。不要继续把空队列单独解释为“所有消歧已完成”。手动合并预览仍为当前既有行为，不能将下面的自动合并撤销预览当作手动合并计划。

## 已落地接口

所有路径均以 `/api/v1/courses/{cid}` 开头，要求当前课程 teacher 成员；学生 403 ROLE_FORBIDDEN，非成员 403 COURSE_FORBIDDEN，未登录 401。GET 不调用模型，不因打开页面产生模型费用。

| 方法与后缀 | operationId / 客户端方法 | 用途 |
| --- | --- | --- |
| GET `/review` | getReviewQueue / 既有 getQueue | 原三栏与分页，新增 `disambiguation`；条目可带 `analysis` |
| POST `/review/actions` | resolveReviewItem / 既有 resolve | 原二元审核动作；totals 与过滤后列表同源 |
| GET `/review/disambiguation` | getDisambiguationCoverage / getCoverage | 与同一草稿队列里的覆盖摘要一致 |
| GET `/review/merges?limit=50&cursor=…` | listAutomaticMerges / listMerges | 持久自动合并历史；limit 1–200，不透明游标 |
| POST `/review/merges/{plan_id}/{group_id}/undo-preview` | previewAutomaticMergeUndo / previewUndo | 计算当前可撤销性、影响 ID 和冲突，不修改图 |
| POST `/review/merges/{plan_id}/{group_id}/undo` | undoAutomaticMerge / undo | 再次验证并执行单组合并撤销 |

真源为 `src/contracts/api.v1.yaml`，生成 TS 在 `src/contracts/v1/generated/typescript/openapi.d.ts`。不要手工编辑生成物。新增客户端各方法接受既有 `RequestControl`，`signal` 原样传递，错误原样抛出。

## 审核列表与语义字段

`ReviewQueue` 原五个必需字段不变：三栏数组、totals、next_cursors；新增可选 `disambiguation`，当前后端每次都返回。分页仍按 similarity 降序、两端 ID 升序，处理后刷新列表与所有 totals。

- 有效语义分析：DIFFERENT 和已自动合并项不列入疑似重复；只列 UNCERTAIN，或判断 SAME 但未满足自动映射/整组/图安全约束的二元提案。
- 技术失败、未召回、预算截断不冒充 UNCERTAIN，也不逐对转交教师；通过覆盖概况显示缺口。
- 无分析、计划未提交/跳过、任务可见性变化、草稿修订变化或撤销后，不继续用旧结论隐藏条目。返回 `queue_mode=legacy`，保留原有词面候选作为兼容人工入口。
- 教师“不是重复”仍生效；动作返回 changed=false 仍按你已修好的未变化反馈处理。
- 新原因 `semantic_uncertain` / `merge_blocked` 对应上方文案。旧 `same_key` / `alias` / `containment` 保留。语义候选无需词面命中；其 similarity 可为 0，只是排序信号，不是“0% 同义”或概率。

条目可选 `analysis`：`plan_id`、`verdict`（SAME/UNCERTAIN）、`basis`（material/model_knowledge/mixed）、`reasons[]`、`differences[]`、`constraints[]`。原因/差异是模型生成的说明，按普通文本展示，不能当 HTML。双侧完整定义与可定位来源继续走已有节点详情接口；这里没有新增“可信术语库”。

## 覆盖状态：必须区分的单位

| 字段 | 含义 |
| --- | --- |
| `status` | not_analyzed：无可用分析；complete：当前计划所定义的全部原始成员交叉对完成裁决；partial：存在未完成；stale：旧结论不适用于当前草稿 |
| `queue_mode` | semantic：有效分析驱动；legacy：名称规则兼容队列 |
| `draft_revision` | 当前课程草稿修订号，撤销请求使用这个课程修订，**不是节点 revision** |
| `plan_id` / `task_id` | 当前有效分析归属；无有效分析为 null |
| `total_pairs` / `examined_pairs` / `completed_pairs` | 单位 original_member_pairs；先前合并组内部不重复计数；完整不等于模型判定正确 |
| `same_pairs` / `different_pairs` / `uncertain_pairs` | 完成裁决的原始成员对数，不等于可见卡片数；SAME 不保证已合并 |
| `technical_unchecked_pairs` | 当前计划总对数减完成裁决数，包含未召回、截断、失败和保护规则延后；不与 uncertain 混合 |
| `auto_merged_groups` | 当前计划实际新增的合并组数，**不是整个课程历史累计数** |
| `review_pairs` / `legacy_candidates` | 单位可见节点对；当前实际语义待办数 / 兼容词面候选数 |
| `recall` | 单位 visible_node_pairs；total_pairs、retrieved_pairs、truncated_pairs、limited_queries、missing_channels 单独展示，不与原始成员对混用 |
| `reasons[]` | 技术/保护缺口代码；有未知代码时仍显示“检查未覆盖”，不据此猜成同义或不同 |

无有效分析时相关计数为 **null**，不要转换成 0 或 100%。complete 描述当前计划裁决覆盖；missing_channels 仍可说明召回通道缺失，不是模型质量保证。当前 API 没有“自动补检查”按钮对应的重试端点；不要绑定一次 GET 冒充重试。

本批采用课程级保守失效：无关教师编辑也可能使旧分析失效并恢复 legacy 候选。它不会误用旧 DIFFERENT 隐藏新义项，但可能增加重复检查；后续节点级依赖缓存需另行验证。

## 自动历史与撤销流程

历史响应为 `{draft_revision, items, next_cursor}`。每项有 `plan_id`、`group_id`、`task_id`、`canonical_id`、`members`（KnowledgePointRef 数组）、`status=applied/undone`、`created_at`、`undone_at`。`members` 是**本次合并的输入节点**；输入节点本身可能是此前自动合并组，本次撤销恢复它们，不展开撤销之前的合并。历史可持久查询，独立于页面内存的“本次已处理”。状态 applied 不保证现在无冲突，须预览。

1. 读历史并让教师选择一组；使用历史或最新覆盖响应的 `draft_revision`。
2. 调用 previewUndo，body 严格为 `{ "expected_revision": N }`。N 是非负整数，不接受 bool、null、字符串数字或额外 force 字段。
3. `ready` 时展示 affected_ids；`conflict` 时展示 conflicts 并阻止直接执行；`already_undone` 刷新历史，不展示再次成功。
4. 用户确认后调用 undo，使用预览返回的 current_revision。后端再次取得课程锁和校验，预览不是免检承诺。
5. `undone` 且 changed=true 才展示成功；`already_undone` 且 changed=false 展示“此前已撤销”。刷新历史、三栏、覆盖及草稿图，作废正在展示的旧预览。

`FusionUndoResult`：`plan_id`、`group_id`、`status`、`changed`、`current_revision`、`affected_ids[]`、`conflicts[]`。冲突每项有 reason，可有 kind=nodes/edges/evidence、ids。已落地 reason 包括 stale_revision、affected_content_changed、dependent_content_changed、prerequisite_cycle。

| 情况 | 返回与前端处理 |
| --- | --- |
| 预览发现冲突 | 200 conflict；显示差异，不显示“可撤销” |
| 执行时相关内容变化 | 409 REVISION_CONFLICT，details 为 FusionUndoResult；刷新并重新预览 |
| 提交围栏/租约变化 | 409 REVISION_CONFLICT，details.reason=snapshot_changed；不一定有完整差异 |
| 课程写锁忙 | 409 COURSE_BUSY；保留当前操作，稍后重试 |
| 组不在该课程、未应用或不存在 | 404 NOT_FOUND；不披露其他课程对象 |
| 存储暂不可用 | 503 STORAGE_UNAVAILABLE；不推断成功 |
| 网络中断/超时 | 结果未知，重新读历史确认；重复执行已撤销组幂等 |

撤销保留后来无关贡献；相关教师修改、锁定、删除、新关系或依赖映射会触发冲突。比较目前包含完整相关属性，重向量化也可能导致保守冲突。没有 force 模式。不改变任务 awaiting_review/completed 或已发布快照；学生看到变化仍须正常发布。

## 验证与交付边界

- 定向后端/HTTP/存储撤销：62 passed；新增 API 前先有缺失路由失败回归。后续补充的投影后完整成员聚合回归亦先失败再修复，最终视图/HTTP 回归 50 passed（18.91s）。
- 隔离 Neo4j 生成到审核/HTTP 撤销与既有 F11/融合：71 passed（50.44s），使用显式 fake 模型；实际读 API 未追加模型调用。
- 当前前端接口/H09：45 passed；当前前端 type-check 通过。
- Claude `d102915` 的临时兼容副本加本批契约/新客户端/两行标签：5 文件 89 passed（8.78s）。首次 type-check 因临时副本未复制跨目录测试 helper 失败，补同一 helper 后 type-check exit 0。
- 基础门禁 `PATH="$PWD/.venv/bin:$PATH" ./scripts/verify.sh` exit 0，包含契约生成一致性与 25 项负向测试。`git diff --check`、测试索引校验通过。
- 独立终审无 Critical/Important/Minor；审查者另行运行视图/HTTP 50 passed（16.88s）。最后的实际 API/F11 集成重跑 50 passed（28.26s）。这些与上方用例重叠，不相加为独立覆盖数量。
- 首次后端全量 exit 1：4487 passed / 27 skipped / 1 failed（695.27s）。唯一失败是分层门禁：新路由直接创建仓储、服务直接执行 BEGIN。已将 SQL 快照事务下沉仓储，把仓储构造移入服务上下文工厂，未修改门禁或新增豁免。修复后分层/视图/HTTP/存储/撤销定向检查 73 passed（21.99s）；实际 Neo4j API/F11 复验 50 passed（60.25s），exit 0。
- 最终 `PATH="$PWD/.venv/bin:$PATH" scripts/verify/backend.sh full`：**4488 passed / 27 skipped / 1 条既有弃用警告**，706.57s，`PASS backend gate (full)`、exit 0。27 项为已登记的 Neo4j 依赖测试，本批隔离 API/F11 回归已实际执行覆盖。原失败日志与通过日志分别保留，不将首次失败改记为通过。
- Claude 原工作树 242 个前端源码/测试文件最终哈希一致；本轮两个一次性 Neo4j 容器均已删除，开发容器保留。临时兼容副本未作为分支合入。
- 执行日志 `/private/tmp/disambig3-*.log` 为临时证据，不是长期归档。

未做：真实模型质量/人工审核量/速度验收、新概况/历史/撤销控件的浏览器实走、服务端手动合并计划、自动补检查任务接口。没有写开发课程或开启自动合并，也没有覆盖你的前端；临时兼容副本仅用于测试，不能当作已合并分支。

复验入口（从仓库根目录运行；集成测试的 `SMARTSKETCH_TEST_NEO4J_*` 必须指向一次性测试实例）：

```sh
PATH="$PWD/.venv/bin:$PATH" ./scripts/verify.sh
PATH="$PWD/.venv/bin:$PATH" scripts/verify/backend.sh full
.venv/bin/python -m pytest tests/tooling/test_backend_layering.py tests/backend/test_disambiguation_review.py tests/backend/test_disambiguation_api.py tests/backend/test_fusion_storage.py tests/backend/test_fusion_undo.py -q
.venv/bin/python -m pytest tests/integration/test_disambiguation_review_api.py tests/integration/test_fusion_pipeline.py tests/backend/test_f11.py -q
npm --prefix src/frontend test -- --run ../../tests/frontend/disambiguation-api.test.ts ../../tests/frontend/h09.test.ts
npm --prefix src/frontend run type-check
```

## 实施取舍与回滚

按执行记录顺序：复用当前未提交后端工作区（整合时保留双方文件）；课程级保守失效（可能重复词面审核）；内部 v1 原因枚举同步扩展（客户端类型/标签须同步，限定例外见 ADR-100）；因无提交区间而使用工作文件前后差异做独立审查（审查不能只看 HEAD）。

终审边界逐项裁定：真实模型质量/耗时/审核减负未签收（没有真实调用）；新概况/历史/撤销控件由 Claude 接入（API 已交付，不冒充已做可视交互）；不全面重审既有手动预览与 BE-01/02（本批依赖路径有回归）；长门禁由执行方负责（审查意见不能替代实际退出码）。没有搁置的审查 Minor。自动开关保持关闭，延续已有取消/租约/预算保护。

本批无新迁移。回退本批后端/契约/接口适配后，BE-02 计划与撤销审计仍保留；不自动重做或反向执行已经确认的撤销。不要回退到不识别 BE-02 物理草稿指针的旧代码，相关存储回滚须遵循 BE-02 交接。
