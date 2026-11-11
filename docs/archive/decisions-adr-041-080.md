# ADR 原文归档 · 041-080

> 正文及原始顺序逐字保留；包含历史决定及其后续修订，不因归档宣告生效或失效。查询入口：[ADR 索引](../decisions.md)。

> 原文中的“本文件”“下文”沿用迁移前文义；跨卷条目请通过 ADR 索引按编号定位。

<a id="adr-041"></a>

<!-- OPT-01 original adr-041 begin -->
## ADR-041：G06 回滚、版本列表与发布接口的实现约定

- **日期**：2026-09-26
- **背景**：V6 规定了 R1～R7，但没有写死：R5 怎样复制副本和向量；R6 在草稿不可发布时怎么办；回滚的 `PublishResult` 中 `excluded`、`stats` 取什么；`POST /publish` 路由归谁（ADR-034 第 8 条待决）；各类失败映射成哪个 HTTP 状态。
- **决定**：
  1. 回滚编排在 `services/versions/rollback.py`，复用 G04 的 `PublishContext`、心跳、`load_draft`，以及 G05 的 `compensate` 和 `reclaim_expired`（插入尝试行前先回收本课程过期的尝试）。
  2. R5 为 `materialize.copy_version`：在一个 Neo4j 写事务内，先删除本尝试的副本，再按标签把源版本的章节、知识点（含向量属性）、`EVIDENCED_BY` 与四类关系复制过来，写入时用映射投影改写 `version_id`（避免与唯一约束冲突）。源版本的知识点数必须等于快照中的数量，否则报 `SourceCopyMissing`，整体回滚。复制前核对 k 自身记录的向量空间，不符则告警并返回 5xx；两种情况都不调用向量模型。复制后按 P9 用 k 的快照核对。
  3. R6 中，等锁超时、读草稿失败，或草稿本身不可发布（`SnapshotBlocked`），都按「d 未知」处理，`published_from_revision = -1`，回滚照常进行。
  4. 回滚的 `PublishResult` 取自新版本行：`excluded`、`stats` 是从 k 复制来的统计值；幂等时返回当前版本行的统计。
  5. `POST /api/v1/courses/{cid}/publish` 并入 `api/versions.py`（ArvinHan 2026-09-26 同意），与回滚、列表共用教师鉴权和错误映射：
     - `PUBLISH_BLOCKED`、`PUBLISH_IN_PROGRESS`、`COURSE_BUSY` 返回 409；
     - 回滚源不存在、为失败尝试或属于他课，返回 404 `NOT_FOUND`，在连 Neo4j 之前就判定；
     - 原因链中含图库仓储错误时返回 503 `STORAGE_UNAVAILABLE`；
     - 其余失败返回 500 `INTERNAL_ERROR`，响应体不带内部原因。
  6. 发布上下文（Neo4j 仓储、向量适配器、当前空间读取器、租约与等锁配置）在第一次请求时构建，并缓存在 `app.state.publish_context`；这样没有 Neo4j 时应用也能启动。向量客户端在 `EMBEDDING_MODE=fake` 时用 `FakeEmbeddingClient`，否则用 `CompatibleEmbeddingClient.from_settings`。
- **后果**：教师端的发布、回滚、版本列表三个接口全部可用；学生读取仍按 F07 当前实现解析版本，统一解析器归 G07。
- **回滚**：撤销 `api/versions.py`、`services/versions/rollback.py`、`materialize.copy_version`，以及 `main.py` 与 `schemas/contracts.py` 各一处改动；无数据迁移。
- **签收**：第 5 条的路由归属由 ArvinHan 2026-09-26 同意；其余由 Claude 选定并在交接中报告。

<!-- OPT-01 original adr-041 end -->

<a id="adr-045"></a>

<!-- OPT-01 original adr-045 begin -->
## ADR-045：K13 抽取消融的付费调用确认与单阶段对照组

- **日期**：2026-09-26
- **背景**：ADR-028 只确认了抽取准确率评测（K02）的付费调用，其他用途须单独确认。K13 要在同一标注集上对比单阶段、两阶段、两阶段加补漏三种配置，需要真实模型各跑一遍；原子清单没有给出「单阶段」的定义，生产代码里也没有一次同时抽实体和关系的提示词。
- **决定**：
  1. ArvinHan 确认为 K13 消融发起付费调用：ADR-026 的「栈与队列」一章，ADR-027 的主用模型，三组各跑一次；预算沿用 ADR-028 的签收值（单组按单任务 500000 token，三组合计计入每日 5000000 token）。估算合计 25～30 万 token、约 1～1.5 元，以实测为准。密钥只在执行者本机的 `LLM_API_KEY`，不入库。
  2. 单阶段定义为「每块一次调用，同时输出实体与块内关系」，提示词放在 `evaluation/prompts/extract_joint.yaml`（消融专用，不进 `prompts/`，不接入生产）。字段、类型与关系规则逐条照抄 `extract_entities` v2 与 `extract_relations` v2，只改两处措辞（证据来源、空结果格式），由 `tests/backend/test_k13.py` 核对。逐条校验复用 E05/E11 的实现。单阶段每块的输出上限取两阶段两类调用上限之和（8192）。
  3. 两阶段组直接调用 K02 `run_live_extraction.run`，补漏组开启 E06 一轮。三组共用简化融合、E04 调用策略与 `evaluate_extraction.py` 的自动比对。
- **后果**：消融结论只针对简化融合。完整融合（E08～E10）接入 `merging` 后，各组数字和组间差距都可能变化，届时需重跑并在报告追加记录。人工判定三组的工作量约为 K02 的三倍，报告以自动比对为主要对照，人工判定按需补做。
- **回滚**：撤销 `evaluation/ablation.py`、`evaluation/prompts/extract_joint.yaml` 与测试；撤回付费确认后不得再用真实模型运行消融。
- **签收**：ArvinHan 2026-09-26 在会话中回复「确认」（第 1 条）；第 2、3 条由 Claude 选定并在交接中报告。

<!-- OPT-01 original adr-045 end -->

<a id="adr-046"></a>

<!-- OPT-01 original adr-046 begin -->
## ADR-046：J01 文本块向量检索的「多取再过滤」与补足召回

- **日期**：2026-09-26
- **背景**：V8 规定文本块向量各版本共享、查询后按 `course_id` 与绑定版本修订列表过滤，并说明 Neo4j 向量索引做不到先过滤再检索，「取多少由 J01 实测召回后确定」。一次取固定条数时，他课或版本外的近邻可能把本课结果挤出窗口，召回不足。
- **决定**：
  1. 检索在 `repositories/vector_search.py` 的 `search_chunks`：查询 `chunk_embedding_<suffix>` 索引，在同一条 Cypher 中按 `course_id` 与 `revision_id IN 修订列表` 过滤（不按 `material_id`），返回文本块 ID、修订、资料 ID 与相似度。
  2. 初始取 `limit × fetch_factor` 条；过滤后不足 `limit` 且索引返回满额时，按 `fetch_factor` 倍扩大重查，直到凑满、索引取尽或到达 `max_fetch`。封顶时记告警并返回已有结果，不报错。`fetch_factor = 4`、`max_fetch = 1000` 为占位值，待 J04 用真实课程实测召回后调整。
  3. 查询向量必须属于调用方传入的当前空间，维度与数值在查询前校验（V12）；只接受已发布版本作用域，草稿作用域拒绝。
  4. `score` 为 Neo4j 余弦相似度归一到 `[0, 1]` 的值，索引为近似检索。相关度阈值和「可定位」条件（Q3.1 第 3 条）由 J04/J06 判断，本函数不做。
- **后果**：跨课与旧版本文本块不会进入候选；本课文本块被大量近邻挤压时，最多多查几轮。按当前实现，运行时没有任何环节为文本块写向量（只有 F14 迁移时会写），检索在接上写入之前只会返回空结果。
- **回滚**：撤销 `repositories/vector_search.py` 与 `tests/integration/test_j01.py`；无数据迁移。
- **签收**：由 Claude 选定并在交接中报告；第 2 条的占位值待 J04 实测后确认。

<!-- OPT-01 original adr-046 end -->

<a id="adr-047"></a>

<!-- OPT-01 original adr-047 begin -->
## ADR-047：F10 合并知识点与重接边

- **日期**：2026-09-26
- **背景**：契约已有 `mergeKnowledgePoints`（`MergeRequest{primary_id, merged_ids}`），只说「名称并入别名，关系与来源取并集后迁移到主节点」。未定的是：重接后撞上的关系怎样去重、字段取谁；合并后怎样验环；不可见（失败任务留下）的关系与来源怎么处理；合并谱系 `merged_from`（ADR-012 修订 3）怎样维护；并发冲突与失败时怎样保证不部分提交；节点不存在时返回什么。
- **决定**：
  1. **写入顺序**同 ADR-035（V4）：输入校验 → 课程写锁（持有方 `edit`，超时 409 `COURSE_BUSY`）→ 读 V → 一个 Neo4j 写事务（先锁 `DraftWriteGuard`，再读、校验、验环，全部通过后才 `draft_revision + 1`，然后写）。校验、冲突、成环都在加修订号之前抛出，事务回滚，草稿与 `draft_revision` 不变；写入语句中途失败同样整体回滚。
  2. **输入**：`merged_ids` 至少一个、不重复、不含主节点；`MergeRequest` 新增可选 `expected_revisions`（知识点 ID → 读到的 `revision`，键须是本次涉及的节点），任一不符 → 409 `REVISION_CONFLICT`（`details` 同 ADR-035，`kp_id` 为第一个不符的节点，主节点先查）；`MergeRequest` 加 `additionalProperties: false`。主节点或被合并节点不存在、不可见或属于他课 → 422 `VALIDATION_ERROR`，`details.fields` 为 `primary_id` 或 `merged_ids.<i>`，`reason = not_found`（与 ADR-035 的 `chapter_id` 同口径，契约不加 404）。加锁节点照常可合并（锁只约束自动流程）。
  3. **重接**：被合并节点一端换成主节点；两端都在「主节点 + 被合并节点」内的关系删除。新 `rel_id` 按「课程 + 类型 + 起点 + 终点」重新派生，ADR-009 降级来的关系按 `PREREQUISITE` 派生（保留降级约定）。ID 相同或「类型 + 端点」相同的关系合为一条：主节点原有的关系胜出；否则按「可见 → 状态 approved > draft > low_confidence > rejected → 人工 → 置信度高 → rel_id 小」取胜出者。胜出者提供类型与字段；`contrib_tasks`、`contrib_manual`、`source_pairs` 取并集，修订号取最大值加 1。旧的 `RelationIdentity` 删除，新的建立。迁移后的关系不置 `contrib_manual`（除非某条原本就是），不改变其来源归属。
  4. **验环**：用 F05 `check_candidates`：现有边 = 可见、未拒绝的 `PREREQUISITE` 去掉被改写的；候选 = 新形态中可见、未拒绝的 `PREREQUISITE`。成环 → 409 `CYCLE_DETECTED`，`details.cycle` 为闭合链路。草稿本已成环时同样拒绝（与 F06 一致）。
  5. **不可见的关系与来源照样迁移**，贡献原样保留，迁移后仍不可见，由失败任务的清理（§8.4 撤销）处理；不参与验环。
  6. **主节点**：主名与其他字段不变；被合并节点的名称与别名依次并入别名（精确去重，不含主名）；`merged_from` = 主节点、被合并节点及其 `merged_from` 的并集（展平、升序、不含主节点）；`contrib_tasks` 取并集；`locked = true`、`contrib_manual = true`、修订号加 1。被合并节点从草稿删除（`DETACH DELETE`，只删 `version_id = draft`）；已发布副本与共享文本块不动。
  7. **来源**：被合并节点的全部 `EVIDENCED_BY` 迁到主节点，按 `(task_id, chunk_id, evidence_start, evidence_end)` 去重，保留原 `task_id`（人工来源仍无 `task_id`）。
  8. 审计日志（直接父子关系）归 F12，本任务不记录。
- **后果**：合并是一次原子的草稿写入，会使已发布课程变为 `revising`；发布时 G01 按 `merged_from` 生成谱系。已知限制：(a) 被合并节点的 `kp_id` 若被后续抽取任务再次写入，F04 会重建该节点，与主节点的 `merged_from` 冲突，发布时报 `invalid_lineage`（F04 尚不查谱系）；(b) 迁移关系上的 `downgrade_cycle` 保留原节点 ID，可能引用已被合并的节点；(c) 合并数量没有上限。
- **回滚**：撤销 `services/graph/merge_nodes.py`、`repositories/graph_edit.py` 中 F10 段（`transaction`、`read_nodes` 至 `delete_merged_nodes`）、`api/graph_nodes.py` 的合并路由、`schemas/contracts.py` 一行、契约（`MergeRequest.expected_revisions`、`additionalProperties`、合并描述、`errors.v1.md` 两处措辞）并重新生成；无 SQLite 迁移与 Neo4j DDL。已合并的数据无法自动拆回，需按 F12 审计或备份恢复。
- **签收**：待 ArvinHan 审阅（以上约定由 Claude 选定并在交接中报告）。

<!-- OPT-01 original adr-047 end -->

<a id="adr-048"></a>

<!-- OPT-01 original adr-048 begin -->
## ADR-048：F09 删除知识点与关系清理

- **日期**：2026-09-26
- **背景**：契约已有 `deleteKnowledgePoint`（204，无请求体），规格只说「草稿写入持课程写锁」「`merged_from` 由 F09 删除时丢弃」。未定的是：删除哪些关系与数据、会不会波及已发布版本、节点不存在/不可见/他课时返回什么、并发删除与 `expected_revision` 怎么处理、不可见（失败任务留下）的关系是否一并清理。
- **决定**：
  1. **写入顺序**同 ADR-035/047：输入校验 → 课程写锁（持有方 `edit`，超时 409 `COURSE_BUSY`）→ 读 V → 一个 Neo4j 写事务（锁 `DraftWriteGuard` → 读目标 → 核对 → `draft_revision + 1` → 以修订号为条件删除）。校验失败不写任何数据，也不加 `draft_revision`。
  2. **范围只限草稿**（`version_id = draft`）：节点、与它相连的全部草稿关系（含对 V 不可见的，否则会留下悬空边）及其 `RelationIdentity`、节点的 `EVIDENCED_BY` 与 `merged_from`。已发布版本的副本（同 `kp_id`/`rel_id`、不同 `version_id`）、SQLite 版本行与快照、发布指针、共享文本块都不动；删除使已发布课程变为 `revising`，学生在重新发布前仍读旧版本。
  3. **明确结果**：节点不存在、对 V 不可见、属于他课，或只存在于已发布版本 → 404 `NOT_FOUND`；空白 ID 同样 404。删除成功 204。同一课程的删除经课程写锁与守卫串行，并发删除同一节点恰有一次 204，其余 404；删除与合并（F10）并发时二者之一先完成，另一方按「节点不存在」处理（合并 422 `not_found`，删除 404）。
  4. **乐观并发**：新增可选查询参数 `expected_revision`（整数 ≥ 1）；与当前修订号不一致 → 409 `REVISION_CONFLICT`（`details` 同 ADR-035），不删除。非法值 → 422。省略时不核对，保持契约原有的无参数调用可用。
  5. 加锁节点照常可删（锁只约束自动流程）；删除不做环检测（只删边不会产生新环）。审计日志归 F12。
- **后果**：删除是一次原子的草稿写入。已知限制：被删节点的 `kp_id` 若被后续抽取任务再次写出，F04 会重建该节点（教师删除不留墓碑）；失败任务留下的不可见关系随节点删除，清理任务再撤销时找不到它们，属预期（撤销对不存在的元素无操作）。
- **回滚**：撤销 `services/graph/delete_node.py`、`repositories/graph_edit.py` 中 `_TX_DELETE_NODE` 与 `delete_draft_node`、`api/graph_nodes.py` 的删除路由与 `_run` 的 204 分支、契约（`expected_revision` 查询参数、422 响应、描述、`errors.v1.md` 一处措辞）并重新生成；无 SQLite 迁移与 Neo4j DDL。已删除的草稿数据只能从备份恢复或由教师重建。
- **签收**：待 ArvinHan 审阅（以上约定由 Claude 选定并在交接中报告）。

<!-- OPT-01 original adr-048 end -->

<a id="adr-049"></a>

<!-- OPT-01 original adr-049 begin -->
## ADR-049：I01 学习进度仓储的实现约定

> **未采用（2026-09-26）**：`main` 已合入 Codex 的 I01 实现（PR #272，见 `docs/handoffs/codex-i01.md`），本 ADR 描述的实现（第九批 `9b9231e`）在合并时未采用；以下内容仅作 I02 设计读时投影的参考，不构成现行约定。

- **日期**：2026-09-26
- **背景**：`specs/learning-path.md` §5 与 ADR-014 修订 1、ADR-012 修订 3 规定了进度的存法（按 `(user_id, course_id, kp_id)`、不按版本复制）、读时投影（合并继承、显式写入覆盖、dormant、脏行）与写入规则（整批校验、同值写入、指针途中变化后复核），但没有定：表名与列、一次写入事务取几个写入序号、投影放在哪一层、脏行判定用哪些 ID、读写怎样拿到一致的版本历史。
- **决定**：
  1. 迁移 `011_progress.sql` 建表 `learning_progress(user_id, course_id, kp_id, status, write_seq, updated_at)`，主键 `(user_id, course_id, kp_id)`，外键指向 `users`、`courses`；`status` 限三值，`write_seq ≥ 1`。`commit_sequence` 沿用迁移 010，本迁移不建也不回滚它。
  2. **一个写入事务取一个 `write_seq`**，本批实际写入的各行共用；全部为无操作时不取号。决定 9 只比较 `write_seq > T`，事务内不可能插入版本提交，所以每行各取一号与共用一号结果相同，共用可少占序号。
  3. 仓储 `app/repositories/progress.py` 同时提供读时投影 `project_progress(sqlite_url, user_id, bound)`（`bound` 为 G07 `PublishedVersion`）与写入 `write_progress(sqlite_url, user_id, course_id, updates)`。原始行、本课程全部已提交版本的节点集、`merged_from` 与提交序号在同一个 SQLite 事务里读出；投影本身是纯计算，I02/I05 直接复用，不再各自实现。
  4. 归属与起算版本：来源 `m` 在绑定版本中属于 `p.merged_from` 即归属 `p`；从绑定版本起按版本号逐个往前，`m` 连续属于 `p.merged_from` 的最早版本为 `k`。被覆盖判定为 `p.write_seq > commit_seq(k)`。
  5. 脏行：原始行的 `kp_id` 不在本课程任何已提交版本的**节点**集中，记一条 WARNING（含 `kp_id` 列表与 `diagnostic_id`），投影时忽略，也不作为继承来源；只在历史版本出现过的行是 dormant，不告警。
  6. 绑定版本违反修订 3 决定 16（来源是本版本节点或含自身、同一来源归属两个节点）、`V = ∅`、任何已提交版本的快照缺失、摘要不符、不可解析或属于他课，均抛 G07 的 `VersionIntegrityError`（500 `INTERNAL_ERROR`），不输出部分进度。已提交版本解析后的节点集与谱系按 `(sqlite_url, version_id)` 缓存（LRU 256）。
  7. 写入在一个 `BEGIN IMMEDIATE` 事务里读发布指针，指针所指版本即「提交时的最终绑定版本」：请求开始后指针变化时，自然按新版本复核。目标不在该版本 → `ProgressNotInPublishedVersion`（`details()` 为契约 `ProgressNotInPublishedVersionDetails`，只报下标），整批零写入；课程不存在、从未发布分别为 `AccessDenied` 404 `NOT_FOUND`、`GRAPH_NOT_PUBLISHED`。
  8. 同值写入：仅当该节点已有自身行、状态相同且投影中 `inherited_from` 为空时为无操作（A08S-R01），不取号、不改 `updated_at`。节点没有自身行时写 `unknown` 不是同值（`own_status` 由 `null` 变为 `unknown`），照常写入。
  9. 仓储不做鉴权与成员判断，`user_id` 由调用方从已认证会话传入（I02）。批次项必须恰为 `{kp_id, status}`，多余字段（如 `user_id`）整批拒绝。
- **后果**：I02 的路由只做鉴权、调用 `write_progress` 并映射错误；I05 在同一请求内先 `resolve_published` 再 `project_progress`，把 `view.mastered` 交给 I03/I04。投影计算放在仓储层是因为 I01 文件范围只有仓储；若以后要把纯投影移到 `services/learning/`，接口不变。
- **回滚**：按迁移 011 文件头的 `ROLLBACK` 行回滚（`test_i01.py` 已验证，会丢失全部学生进度），或恢复 `backups/*-before-011.sqlite`；撤销 `repositories/progress.py` 与 `tests/backend/test_i01.py`。
- **签收**：待 ArvinHan 审阅（以上约定由 Claude 选定并在交接中报告）。

<!-- OPT-01 original adr-049 end -->

<a id="adr-050"></a>

<!-- OPT-01 original adr-050 begin -->
## ADR-050：J02 图结构检索的匹配规则与子图上限

- **日期**：2026-09-26
- **背景**：规格只写了「并行混合检索：图谱结构检索（前置/包含/相关）」，并把「图谱扩展跳数」列为待细化（J01/J02/J04）。J03 只产出改写后的整句问题，没有关键词抽取；H4 的 `kp_id` 只用于引导检索。需要确定如何从术语找到知识点、沿哪些关系扩展、扩展到多大，以及如何保证只读绑定的发布版本。
- **决定**：
  1. 检索在 `repositories/graph_search.py` 的 `search_subgraph(repo, scope, revision_ids, terms, *, seed_kp_ids, max_hops, max_nodes, max_seeds, max_evidence, relation_types)`，入参风格与 J01 `search_chunks` 一致：`scope` 为 G07 `PublishedVersion.graph_scope()`，`revision_ids` 为其修订列表。只接受已发布版本作用域，草稿作用域拒绝；所有查询按 `(course_id, version_id)` 匹配节点与关系。
  2. 种子：名称或别名（去首尾空白、小写）与某术语相等、包含在某术语中，或包含某个至少 2 个字的术语。排序为：显式 `seed_kp_ids`（属于本版本）> 相等 > 名称在术语中 > 术语在名称中；同级名称长者优先，再按 `kp_id`。单字名称（如「栈」）也能命中，但排在长名称之后。不在本版本的 `seed_kp_ids` 忽略并记 INFO 日志（H4）。
  3. 扩展：从种子逐跳无向扩展，缺省只沿规格列出的 `CONTAINS`、`PREREQUISITE`、`RELATED_TO`，`EXAMPLE_OF` 须调用方显式开启；同一跳内按 `kp_id` 取前者。返回的关系是结果节点间的全部四类关系。
  4. 上限在 Cypher 的 `LIMIT` 中生效：`max_hops` 缺省 2、硬上限 3；`max_nodes` 缺省 30、硬上限 200；`max_seeds` 缺省 `min(10, max_nodes)`；证据块 `max_evidence` 缺省 60、硬上限 500。任一上限截掉内容时 `truncated = true`。以上缺省值均为占位，由 J04 按上下文预算与评测调整。
  5. 证据块取节点的 `EVIDENCED_BY` 文本块，并只保留 `revision_id` 属于修订列表的（纵深防御，Q3.1 第 2 条）。「可定位」条件与阈值仍由 J04/J06 判断。无匹配返回空子图，不报错。
- **后果**：图检索不依赖模型调用，也不需要全文索引。匹配时逐个扫描版本内的知识点，课程规模在数千点以内时开销可以接受。子串匹配会带来少量误命中（如问题中出现「堆」），种子上限与排序可以压低这类误命中的影响。关键词抽取接入后，J04 可以把关键词与改写后的问题一起作为 `terms` 传入。
- **回滚**：撤销 `repositories/graph_search.py` 与 `tests/integration/test_j02.py`；无数据迁移。
- **签收**：由 Claude 选定并在交接中报告；第 2～4 条的匹配规则与占位值待 J04 实测后确认。

<!-- OPT-01 original adr-050 end -->

<a id="adr-051"></a>

<!-- OPT-01 original adr-051 begin -->
## ADR-051：H06 知识点详情与来源浏览的展示约定

- **日期**：2026-09-26
- **背景**：H06 要把画布点击的知识点 ID（H04 `nodeClick`）变成定义、关系与原文来源的详情抽屉。契约 `SourceRef` 要求页码或章节至少其一（ADR-003），但前端仍可能收到不合契约或无法定位的来源；已发布版本的来源不带原文片段（ADR-033 后果）；`SourceRef` 只有 `document_id` 没有资料名；目前也没有原文阅读器。快速切换节点时多个详情请求会并发返回。
- **决定**：
  1. 新增 `api/knowledgeDetail.ts` 只封装 `getKnowledgePoint`，经 `KNOWLEDGE_DETAIL_API_KEY` 注入；未注入时组件用 `HTTP_CLIENT_KEY` 的会话客户端构造，不改 `main.ts`。前端不传版本，草稿/发布由后端按身份决定（ADR-030）。
  2. 来源只展示可定位的：`document_id`、`chunk_id` 非空，且页码为正整数或章节路径非空；无效页码不显示但有效章节仍保留。不满足的丢弃并提示「另有 N 条未显示」；全部无法定位时明确提示，不给定位按钮。不补页码、章节或原文；资料名由页面经 `documentNames` 传入，没有时显示「资料 <document_id>」。
  3. 点击来源不在组件内打开原文，而是发出 `locateSource({ documentId, chunkId, page?, sectionPath? })` 并标记当前来源（`aria-pressed`）；原文阅读器接线留给页面任务（H11）。点击关联知识点发出 `selectKnowledgePoint`，由页面改选中并联动画布。
  4. 迟到请求隔离：每次选择递增序号并中止上一次请求，同时绑定课程作用域（`useCourseStore().beginRequest()`）；只有序号与作用域都仍有效时写入。响应的 `id`/`course_id` 与请求不符按数据异常处理，不展示。课程变了而选择没变时回到空态。
  5. 所有服务端文本以插值渲染，不用 `v-html`；原文片段按名称与别名做字面量切分高亮（`<mark>`），不拼 HTML、不解释正则。
  6. 错误只给固定文案：`NOT_FOUND`、`GRAPH_NOT_PUBLISHED` 不可重试；网络/超时/5xx/数据异常可重试；`COURSE_FORBIDDEN` 发出 `courseForbidden` 交页面处理，组件不清课程上下文。
- **后果**：详情组件可独立挂到任何图谱页；资料名、原文定位跳转与画布联动都由页面负责。学生看已发布版本时来源只有位置没有片段，这是后端既定行为，不是前端缺陷。
- **回滚**：删除 `src/frontend/src/api/knowledgeDetail.ts`、`components/KnowledgeDetail.vue`、`composables/useKnowledgeDetail.ts`、`tests/frontend/h06.test.ts` 与本 ADR；无依赖、契约或数据变更。
- **签收**：待 ArvinHan 审阅（以上约定由 Claude 选定并在交接中报告）。

<!-- OPT-01 original adr-051 end -->

<a id="adr-052"></a>

<!-- OPT-01 original adr-052 begin -->
## ADR-052：H05 图谱筛选、选中与布局切换

- **日期**：2026-09-26
- **背景**：H05 要求搜索、按关系等条件筛选、层次/力导向布局切换，验收为「筛选后无悬空边、清空恢复、切换布局不丢选中态」；H03/H04 把 `rejected`/`low_confidence` 的样式与过滤留给 H05。ADR-040 的画布只有固定层次布局，节点副本只带 `id`/`data`，没有选中概念；G6 v5 中配置项的节点样式优先级高于数据里的 `style`，所以不能靠逐节点 `style` 表达状态。
- **决定**：
  1. 筛选是 `composables/useGraphFilters.ts` 中的纯函数 `filterGraph(适配图, 条件, 选中)`，输入是 H03 适配图，不接触后端响应。知识点可见 ⇔ 类型、审核状态、章节均被选中且名称包含搜索词（NFKC、小写、去首尾空白后包含匹配；空白串等于不搜索）；关系可见 ⇔ 类型、审核状态被选中且两端可见。输出保持输入顺序。
  2. 默认条件为全部四类关系、五类知识点、四种审核状态、全部章节——驳回项默认可见但淡化；调用方可用 `initial` 改默认（如教师视图默认隐藏驳回），`clear` 回到该默认。章节下拉只列图中出现的章节，标题取 `GraphExchange.chapters`，缺失时用 ID，另有「未分章」。
  3. 状态经 G6 元素 `states` 表达：审核状态 `rejected`（节点灰色虚线框、透明度 0.4；边透明度 0.3）、`lowConfidence`（节点橙色虚线框；边透明度 0.6），选中 `selected`（深蓝粗框加光晕），数组中审核状态在前、选中在后。样式配置在 `buildGraphOptions` 的 `node.state`/`edge.state`；生命周期复制数据时保留 `states` 的副本。
  4. 选中与布局存在组合式中，独立于筛选条件：清空、切换布局都不改选中；筛选隐藏选中节点时保留选中并由 `selectedHidden` 提示；新图里已无该知识点时清除选中。
  5. 布局切换：`GraphCanvas` 新增 `layout` 属性（缺省 `hierarchical`），`lifecycle.setLayout` 在串行链上执行 `graph.setLayout` → `graph.layout()` → `fitView`，不重建、不 `setData`；连续切换只落在最后一次；G6 加载期间切换则建好后补做一次；未建图时建图即用新布局。力导向为 `d3-force`（连边距离 120、斥力 -300、碰撞半径 40）。`CanvasGraph` 的 `setLayout`/`layout` 为可选成员，替身不实现时切换不生效，已有测试替身无需改动。
  6. `GraphToolbar.vue` 是受控组件（`v-model` 条件、`v-model:layout`、`clear`），只发出新对象不改 props；关系图例与按关系筛选合一，颜色、线型、箭头取自 `RELATION_STYLES`；审核状态图例与画布状态样式一致；可见数量区为 `aria-live="polite"`。
- **后果**：筛选每次变化都会 `setData` 并按当前布局重新布局，节点位置不保持（小图可接受）。页面接入（教师/学生图谱页）留给 H11 等视图任务；H06 详情可直接用 `nodeClick` → `select`。
- **回滚**：删除 `composables/useGraphFilters.ts`、`components/GraphToolbar.vue`、`tests/frontend/h05.test.ts`；`git checkout <base> -- src/frontend/src/graph/lifecycle.ts src/frontend/src/components/GraphCanvas.vue` 还原画布扩展；无依赖或数据变更。
- **签收**：待 ArvinHan 审阅（以上约定由 Claude 选定并在交接中报告）。

<!-- OPT-01 original adr-052 end -->

<a id="adr-053"></a>

<!-- OPT-01 original adr-053 begin -->
## ADR-053：H08 教师连边编辑的乐观更新与冲突呈现

- **日期**：2026-09-26
- **背景**：H08 要求「成环错误高亮冲突路径；服务拒绝时撤销临时边；无组件 Cypher」。关系接口（`createRelation`/`updateRelation`/`deleteRelation`）只有契约，后端路由尚未实现；关系请求体不带 `expected_revision`。画布生命周期（H04）复制边样式但只复制节点的 `id`/`data`，画布上无法单独给节点着色；G6 的拖线交互需要改 `lifecycle.ts` 的建图参数，不在 H08 文件锁内。
- **决定**：
  1. 新建 `api/relations.ts` 封装三个关系接口；`composables/useRelationEditor.ts` 持有全部编辑状态，`components/RelationEditor.vue` 只渲染并调用组合式方法。
  2. 乐观更新以「叠加层」实现：请求期间在课程 store 的草稿图上叠加一条临时改动（新边、改后的边或移除），不写入 store；成功后把服务端返回的关系合并进 store **当时**的图（`setGraph`，改方向时服务端可能派生新 ID，以响应为准），失败即丢弃叠加层。一次只允许一个写请求。
  3. 409 `CYCLE_DETECTED`：`details.cycle`（首尾相同、沿边方向）转成名称路径以 `role="alert"` 有序列出；环上相邻两点之间未拒绝的 `PREREQUISITE` 边、以及本次被修改的关系，在 `canvasData` 中以冲突色（`#ff4d4f`、线宽 3）绘出。`details` 不合规时只提示、不高亮。
  4. `REVISION_CONFLICT`、`NOT_FOUND`、`DANGLING_ENDPOINT`：撤销改动、置 `stale`，并调用 `onRefreshNeeded` 由页面重新加载草稿图；`DUPLICATE_RELATION` 标出 `details.existing_id`；`COURSE_FORBIDDEN` 清空当前课程交调用方回课程列表；其余错误码给固定文案，不回显服务端 `message`。
  5. 「拖线」先以「在画布上依次点选起点、终点」（`GraphCanvas` 的 `nodeClick` → `pickNode`）加表单实现；节点高亮以面板路径列表与 `highlightedNodeIds` 提供。
- **后果**：H08 不改 H04 文件即可与 `GraphCanvas` 组合；画布上的冲突节点着色与真正的 G6 拖线需在 `lifecycle.ts` 增加节点样式透传与 `create-edge` 行为（后续任务）。后端关系路由落地后，若返回的错误码或 `details` 与契约不同，须先改契约。
- **回滚**：删除 `api/relations.ts`、`composables/useRelationEditor.ts`、`components/RelationEditor.vue` 与 `tests/frontend/h08.test.ts`，删去本 ADR；无数据或契约变更。
- **签收**：待 ArvinHan 审阅（以上约定由 Claude 选定并在交接中报告）。

<!-- OPT-01 original adr-053 end -->

<a id="adr-054"></a>

<!-- OPT-01 original adr-054 begin -->
## ADR-054：K10 备份与恢复演练的一致性栅栏、两条 Neo4j 路径与不覆盖原则

- **日期**：2026-09-26
- **背景**：K10 要求 SQLite 与 Neo4j 的备份对应同一时间点、发布指针与已提交版本一致，恢复在隔离副本中核对引用/图/进度，且不覆盖用户库。两库之间没有分布式事务；Neo4j 社区版的 `neo4j-admin database dump/load` 只能在数据库停止时执行，社区版也不能单独停一个库。F14（ADR-038）以 `--neo4j-backup-confirmed` 暂代 Neo4j 备份；G05 把孤儿副本与缺副本的处理留给 K10。
- **决定**：
  1. **栅栏**：备份先持有全部课程的写锁（`course_locks`，持有者 `k10-backup-<备份 ID>`，按 L/3 续约）——发布 P3、回滚、图编辑与 T6 写图都要这把锁；并与 F14 第 1 步同口径拒绝活动任务租约、他人的活动写锁、任何 `preparing`/`materialized` 尝试（含过期未补偿的，先跑 G05）。拒绝时退出码 2，不写任何文件。
  2. **同一时间点的判定**：G0 读 Neo4j 全图摘要 → S1 用 SQLite 在线备份 API（单步、一个读事务）复制整库 → 导出 Neo4j → G2 摘要必须等于 G0 → S3 再做一次在线备份，逐表内容摘要必须等于 S1 → 写锁仍由本次持有。任一不等即判定有写入绕过了写锁，整份备份作废（退出码 1，`.partial` 目录删除），不尝试「修补」。代价：栅栏期间被拒的发布仍会留下一行 `failed` 尝试，使该次备份作废，需重跑（测试已覆盖）。副本中删去本次的锁行。
  3. **发布指针**：每门课的 `published_version_id` 必须是本课程 `committed` 且版本号一致的行，且该版本的 Neo4j 副本按快照用 G03 P9 `materialize.verify` 复核通过（节点、边、来源引用、向量维度），否则备份失败。非当前版本复核失败、未提交尝试的孤儿副本、没有 SQLite 行的 `Chunk` 只记为警告写入清单（G05 留给 K10 的两类残留在此报告，不自动删除或重建）。Neo4j 中出现 SQLite 快照里没有的课程也视为不一致而失败。
  4. **两条 Neo4j 路径**：缺省经 Bolt 导出为 gzip JSON 行（结构语句、节点、关系；元素 ID 只用于文件内连线），任何可连接的 Neo4j 都能用，且可在进程内 harness 上测试；`--neo4j-container NAME` 走 neo4j-admin：停容器 → `docker run --rm --volumes-from NAME <同镜像> neo4j-admin database dump neo4j` → 启容器 → 等 Bolt，停机期间写锁仍持有，重启后摘要必须等于停机前。两条路径的清单都含同一套检查结果（图摘要与 SQLite 行级摘要与路径无关），恢复端一视同仁地核对。属性只接受标量与标量列表，遇到时间、空间等类型直接失败（当前代码不写这些类型）。
  5. **不覆盖**：恢复脚本的 Neo4j 目标必须以 `--neo4j-uri` 显式给出（不读 `NEO4J_URI`）；SQLite 目标必须不存在、Neo4j 目标必须没有节点，否则退出码 2 且不做任何改动。覆盖需同时给 `--replace-existing` 与 `--confirm <备份 ID>`，目标须已停机（同第 1 条），并先把目标整体做一份 K10 备份到安全目录（`--allow-inconsistent`，允许记录已损坏的状态），撤销覆盖即从该安全副本再恢复一次。
  6. **恢复核对**：先校验清单中每个文件的 SHA-256（不符即拒绝，不动目标）；装入后用 `backup-demo.sh --inspect` 重新检查目标，并与清单逐项比较：SQLite 完整性、外键、结构、逐表行级摘要（含今后的进度表，不依赖具体表名）、发布指针；Neo4j 图摘要、计数与结构（清单中的结构必须存在）；一致性结论（复核通过的版本、指针错误、孤儿副本、悬空文本块）。有差异则退出码 1 并在报告中列出，副本不得使用。
  7. 备份目录 0700、文件 0600，含账号口令散列等，放在已被忽略的 `backups/` 下或仓库外，不得提交或外传。
- **后果**：恢复演练在本机可重复：Bolt 路径在进程内 Neo4j 上测试，neo4j-admin 路径在一次性 `neo4j:5.26-community` 容器上测试（无 Docker 时跳过）。Bolt 导出要全图扫描两次（G0 与导出），只适合演示规模；大库应走 neo4j-admin 路径，但要停 Neo4j。compose 部署下 SQLite 在 `app-data` 卷内，宿主机需先把卷挂到可运行脚本的容器里（见交接），整套 compose 的实机演练待人工复验。
- **回滚**：删除 `scripts/backup-demo.sh`、`scripts/restore-demo.sh`、`tests/integration/test_k10.py`；无迁移、无契约与依赖变更，已生成的备份目录可直接删除。
- **签收**：待 ArvinHan 审阅（以上约定由 Claude 选定并在交接中报告）。

<!-- OPT-01 original adr-054 end -->

<a id="adr-055"></a>

<!-- OPT-01 original adr-055 begin -->
## ADR-055：G08 遗留修复——部署时建向量索引、P9 核对索引与块身份、按版本补齐命令

- **日期**：2026-09-27
- **背景**：#283 对 G08（ADR-066）的独立审查发现三处缺口。
  1. 生产环境不建向量索引：`ensure_vector_indexes` 只在 `scripts/reembed.py` 和测试夹具里调用。部署的 `migrate` 步骤只执行 `CREATE CONSTRAINT`/`CREATE INDEX`，结果 P9 通过、J01 检索却因为索引不存在而报 503。
  2. 「重新发布一次即可补齐」不成立：内容未变的发布走 P7 幂等路径，不经过 P8；被新修订取代的旧修订也再不会进入快照。
  3. P9 只查 `revision_id IS NULL`，取值错误查不出来（J01 会静默丢掉该块），也不查 `document_id`。
- **决定**：
  1. `python -m app.repositories.graph_migrations` 在执行约束迁移之后，调用 `ensure_current_vector_indexes`：读取 SQLite 记录的当前空间（首次运行时按 `EMBEDDING_*` 初始化，与 API 启动一致），创建该空间的知识点与文本块两个向量索引，并用 `db.awaitIndexes` 等待上线。配置与记录不符时拒绝，提示先运行 `scripts/reembed.py`，不为未记录的空间建索引。DDL 仍只在部署步骤执行，请求路径不执行 DDL。
  2. P9 的 `verify_chunks` 增加两项核对，任一不满足即按 `VerificationError` 走 C1，提示运行迁移命令：
     - 当前空间的文本块向量索引存在且为 `ONLINE`；
     - 每个块节点的 `revision_id` 和 `document_id` 与 SQLite 一致。
  3. `index_chunks` 写入时，直接用 SQLite 的 `revision_id`、`document_id` 覆盖节点上的值。块 ID 由修订派生（D09），覆盖是安全的。
  4. 新增运维命令 `scripts/backfill_chunk_vectors.py`：按已提交版本，对快照修订列表调用 `index_chunks`。
     - 默认处理全部课程的全部已提交版本，可用 `--course`、`--version` 缩小范围，`--dry-run` 只统计缺向量的块、不调用模型；
     - 同一课程的修订去重后只处理一次；
     - 版本记录的空间与当前空间不符时拒绝（V12）；
     - 写入是对共享、不可变块的幂等 `MERGE`，服务运行中也可以执行。
  5. 幂等发布路径保持纯 SQLite，不补块向量。旧版本统一由第 4 条的命令补齐。
- **后果**：部署后，发布版的块都可以被检索；索引缺失或不在线时，发布在 P9 就失败，不会让学生端静默查不到。集成测试夹具（`test_g04.py`）要自己建 `fake/4` 的索引，模拟部署步骤。审查提到的「首次发布超过尝试租约」不会发生：发布全程由 `_heartbeat` 按租约的 1/3 续约。
- **回滚**：撤销 `graph_migrations.ensure_current_vector_indexes` 与 `main()` 中的调用、`chunk_vectors` 的两项核对与覆盖写、`scripts/backfill_chunk_vectors.py`。已经创建的索引和已写入的向量可以保留，不影响其他读取。
- **签收**：由 Claude 选定（ArvinHan 2026-09-26 同意修复这些遗留，协调者 2026-09-27 转达开工）。

<!-- OPT-01 original adr-055 end -->

<a id="adr-060"></a>

<!-- OPT-01 original adr-060 begin -->
## ADR-060：F11 审核队列的三栏定义、排序分页与单项处理

- **日期**：2026-09-26
- **背景**：契约只有 `getReviewQueue`（三栏，无参数），规格只说「列出低置信度关系、疑似重复知识点、孤立知识点，支持一键通过 / 拒绝 / 合并」，并把「审核队列的排序与分页」列为待细化。未定的是：三栏各按什么条件入列、疑似重复怎样判定、队列存不存、怎样排序与分页才能在教师边处理边翻页时不漏不重、单项处理走哪个接口、处理后怎样离开队列、重复操作返回什么。关系编辑路由 `/relations` 尚未实现，也不能指望前端借它来处理低置信度关系。
- **决定**：
  1. **实时计算，不另存队列**。请求开始时读 V，从草稿读可见节点与关系（F07 `GraphReader`，与 `getGraph` 同一可见性），再扣掉 SQLite `review_dismissals`（迁移 013）中教师记下的处理。
  2. **三栏**：（a）低置信度关系：状态 `low_confidence`、两端都未被拒绝的可见关系，含 ADR-009 降级关系，附 `source_refs`；（b）疑似重复：未被拒绝的可见节点两两比对，用 E08 名称归一（`same_key` / `alias` / `containment`），另把已存的 `aliases` 逐个归一，名称或别名的归一键相交也算 `alias`，原因取最强者；`similarity` 对前两者为 1，包含候选为有效字符比 较短/较长；以一对为单位（`candidates` 恰两项，按 ID 升序），新增必填 `reason`。向量相似（E09）等 D-08 阈值定稿后再接入；（c）孤立知识点：未被拒绝、且没有「关系未拒绝、另一端可见且未拒绝」的相连关系的可见节点，即发布后在图中没有一条边的节点。
  3. **排序**：低置信度关系 `(confidence 升序, id)`，疑似重复 `(similarity 降序, 小 ID, 大 ID)`，孤立知识点 `(name, id)`，都按码点比较、与存储顺序无关。
  4. **分页**为键集分页：`limit`（1～200，默认 50）；不带 `kind` 时三栏各返回第一页，带 `kind` 时只填该栏，`cursor` 取上一页 `next_cursors` 中该栏的值（不透明的 base64url JSON，编码本栏最后一条的排序键），下一页取排序键严格大于它的条目。`cursor` 无 `kind`、无法解析或属于另一栏 → 422。`totals` 始终是三栏完整条数。处理掉已看过的条目不会让后续条目被跳过或重复；排在游标之前的新条目要重新从第一页读才看到。
  5. **单项处理**新增 `POST /courses/{cid}/review/actions`（`resolveReviewItem`，`ReviewAction` 按 `item` 区分）：低置信度关系 `approve` / `reject` 改状态为 `approved` / `rejected`，登记人工贡献（此后自动流程不再降级或改写它）、关系修订号加 1；疑似重复 `merge` 以 `primary_id`（必须是这一对之一）调用 F10 `merge_nodes`（ADR-047 的规则与错误原样适用），`reject` 记为「不是重复」；孤立知识点 `approve` 记为「确认保留」，`reject` 把节点置 `rejected`，按 ADR-035 加锁、登记人工贡献、修订号加 1。
  6. **写入顺序**：图写入（关系状态、节点拒绝）同 ADR-035：课程写锁（超时 409 `COURSE_BUSY`）→ 读 V → 一个 Neo4j 写事务（锁守卫 → 读 → 判断仍在队列 → `draft_revision + 1` → 条件写）。「不是重复」「确认保留」只写 SQLite，不取课程写锁、不加草稿修订号、不影响发布。批准或拒绝的都是已在环检测范围内的关系（`low_confidence` 的 `PREREQUISITE` 本就参与验环），只维持或删除前置边，不会成环，不再验环。
  7. **结果**：条目已不在队列中（不存在、不可见、端点已拒绝、已被其他动作处理、不是疑似重复的一对）→ 404 `NOT_FOUND`；同一动作已经生效（关系已是目标状态、节点已拒绝、已记过、被合并节点已并入主节点的 `merged_from`）→ 200、`changed = false`，不写入。响应带处理后的 `totals`，前端刷新后数量一致。
  8. 审计日志归 F12，本任务不记录。
- **后果**：队列与草稿永不脱节，代价是每次读取都要全量读草稿并做 O(n²) 名称比对（面向单课程规模）。「确认保留」按节点 ID 记，节点此后又失去所有边也不会再次入列；「不是重复」按一对 ID 记，节点被合并或删除后留下的记录无害。已拒绝的节点与关系不再出现在任何一栏，恢复要通过节点/关系编辑。
- **回滚**：撤销 `services/graph/review.py`、`repositories/review.py`、`api/review.py`、`main.py` 与 `schemas/contracts.py` 的引用、`api/graph_nodes.py` 的 `_run` 字典分支、契约（`getReviewQueue` 参数与 `ReviewQueue` 字段、`resolveReviewItem` 与相关 schema）并重新生成；迁移 013 按文件头 `ROLLBACK` 行回滚（只丢失「不是重复」「确认保留」记录，条目重新入列）或恢复 `backups/*-before-013.sqlite`。已批准、拒绝或合并的图数据不会自动恢复。
- **签收**：待 ArvinHan 审阅（以上约定由 Claude 选定并在交接中报告）。
<!-- OPT-01 original adr-060 end -->

<a id="adr-061"></a>

<!-- OPT-01 original adr-061 begin -->
## ADR-061：F12 图编辑审计日志的存储、跨库顺序与脱敏

- **日期**：2026-09-26
- **背景**：F12 要求图编辑审计「谁/何时/何版本/变更摘要齐全；跨库失败可重试；不记录秘密」。教师写入（F08 新建/修改/解锁、F09 删除、F10 合并）改的是 Neo4j 草稿，而课程 `draft_revision` 与用户、课程都在 SQLite，两库之间没有分布式事务。ADR-012 修订 3 与 ADR-047 规定合并的**直接**父子关系只记在 F12 审计里（快照只存展平的 `merged_from`）；ADR-034 第 7 条已定发布不写本日志。
- **决定**：
  1. **存储**：SQLite 新表 `graph_edit_logs`（迁移 `012_edit_logs.sql`），一行一次教师写入：`event_id`、`course_id`、`actor_id`（`users.id`）、`action ∈ {create, update, unlock, delete, merge}`、`kp_id`（合并为主节点）、`draft_revision`（写入后的课程草稿修订号）、`kp_revision_before/after`、`state ∈ {pending, committed, aborted}`、`summary`（JSON 对象）、`failure_reason`、`resolved_by ∈ {writer, reconcile}`、`created_at`/`resolved_at`（ISO-8601 UTC）。行只追加：触发器禁止删除，结束后的行禁止修改。课程隔离靠 `course_id` 条件；分页以自增 `seq` 为游标。
  2. **只记真实写入**：持锁并校验通过、即将加 `draft_revision` 时才记；校验失败、`REVISION_CONFLICT`、404、成环、未加锁节点的解锁等不写数据的请求不记。
  3. **跨库顺序**：`draft_revision + 1` 与 `pending` 行在**同一个** SQLite 事务写入（`edit_logs.begin`，取代写入路径上的 `bump_draft_revision`），所以审计的版本号与课程修订号严格一致，且 V4「先加修订号再写 Neo4j」不变。Neo4j 写入返回后置 `committed`（附写后修订号与最终摘要）或 `aborted`（附错误码或异常类名，不含消息）。置状态的 SQLite 更新以 `state = 'pending'` 为条件，可重复执行；失败时退避重试（0.05/0.2/0.5 s），仍失败只记日志、**不**让已提交的编辑报错（否则客户端重试只会得到 `REVISION_CONFLICT`），行留在 `pending`。
  4. **对账**：每次教师写入取得课程写锁后、做任何读写之前，先把本课程遗留的 `pending` 行对照 Neo4j 判定（`audit.reconcile`）：`create` 看节点是否存在；`update`/`merge` 看主节点是否已加锁且修订号恰为写前 + 1；`unlock` 看节点是否已解锁；`delete` 看节点是否已不可见。持锁时没有其他教师写入插进来，自动流程又不改加锁节点，所以判定确定。判定未生效的记 `aborted`、原因 `not_applied`。**前提补充（独立审查 2026-09-26 M1）**：「判定确定」还依赖**本课程的写锁未被夺**。`course_locks` 的续约在 `renew` 返回 `False` 时静默返回、写入继续（`repositories/course_locks.py`），而租约默认 60 秒、每 20 秒续约（`config.py`）；若写入方在 `begin` 之后停顿超过租约时长，另一教师可先取锁并**抢在对账前**把这条 `pending` 判为 `aborted`（`not_applied`），而停顿方的 Neo4j 写入随后仍可能成功（条件更新只校验节点 `revision`，未被触碰的节点不冲突）——此时「图已改、审计写 `aborted`」，且该行已被冻结触发器保护，**后续对账无法纠正**。窗口要求写入停顿超过租约时长，实际概率低，但后果不可逆。处置选项（待签收）：(a) 如实把该窗口写进本 ADR 的后果与交接，接受残留风险（当前选择）；(b) 对账跳过 `created_at` 晚于本次取锁时刻的行；(c) 续约失败即中止写入。
  5. **摘要白名单与脱敏**：只记知识点的 `name/aliases/type/definition/importance/difficulty/status/chapter_id` 与锁状态；修改记提交字段的前后值；新建记字段与来源块及区间；删除记被删节点字段与删除的关系数；合并记主节点、直接被合并节点（ID、名称、修订号）、展平谱系与重接/来源迁移计数。贡献、向量、令牌、请求头一律不进。字符串先去掉形似密钥的片段（`sk-…`、`Bearer …`、JWT、`AKIA…`、argon2 散列、私钥块，以及 `password=`/`token:` 等赋值的值）换成 `[REDACTED]`，再截断到 500 字符；列表最多 50 项。**已知缺口（独立审查 2026-09-26 L1/L3/L4，待补）**：`secret_key`/`credential`/`cookie`/`session` 类关键词、URI 内嵌口令（`scheme://user:pass@host`）、空格分隔的 `--password value`、中文「密码：」目前**不**被脱敏；`merged` 列表未按 50 项截断（`create_summary` 已截断）；`create` 摘要不含锁状态。
  6. `EditContext` 增加可选 `actor_id`；API 路由传入调用者；为 `None`（内部调用、既有测试）时不记审计，只加草稿修订号，行为与 F08～F10 相同。
- **后果**：每次教师写入多一次 SQLite 读（查遗留 `pending`，通常为空）和一次更新。进程在 `begin` 之后、下一次同课程教师写入之前崩溃时，该行保持 `pending`，直到下一次写入对账；审计读接口与关系编辑（F06 路由未实现）的审计尚未覆盖。脱敏是模式匹配，不能识别任意形态的秘密；教师在定义里写入的普通个人信息仍会原样记录。**租约被夺时的错记窗口见决定 4 的前提补充**：图已改而审计为 `aborted` 且行被冻结，不可自动纠正。审计行的只追加由两个触发器保证，但 `INSERT OR REPLACE` 可绕过（SQLite 默认 `recursive_triggers = 0`），属防御纵深缺口、当前无调用路径。
- **回滚**：`git revert` 本任务提交；数据库按迁移文件头部的 `ROLLBACK:` 行在停机时执行（会丢失审计历史，先导出），或从 `backups/*-before-012.sqlite` 恢复。无 Neo4j DDL、契约或依赖变更。
- **签收**：待 ArvinHan 审阅（以上约定由 Claude 选定并在交接中报告）。**需明确签收**：决定 4 前提补充中的租约被夺窗口如何处置（当前选择 (a) 如实记录、接受残留风险）；脱敏缺口与只追加绕过是否在本轮补。
<!-- OPT-01 original adr-061 end -->

<a id="adr-062"></a>

<!-- OPT-01 original adr-062 begin -->
## ADR-062：H07 教师节点编辑面板的保存、冲突与锁交互

- **日期**：2026-09-26
- **背景**：H07 要把 F08（`updateKnowledgePoint`/`unlockKnowledgePoint`，ADR-035）与 F09（`deleteKnowledgePoint`，ADR-048）接成教师编辑面板，验收为「字段错误、revision 冲突、锁/解锁；失败不假装保存成功」。PATCH 必带节点级 `expected_revision`，冲突时 409 `REVISION_CONFLICT` 的 `details.current` 只含名称、别名、类型、定义、状态、锁与重要度/难度，不含章节与来源；删除的 `expected_revision` 可选；保存成功后服务端把节点锁定。
- **决定**：
  1. 新增 `api/nodeEdit.ts` 封装读、改、解锁、删四个契约操作，经 `NODE_EDIT_API_KEY` 注入；未注入时组件用 `HTTP_CLIENT_KEY` 的会话客户端构造，不改 `main.ts`。删除总是带上读到的修订号。
  2. 不做乐观更新：表单是本地副本，只有服务端确认（且响应 `id`/`course_id` 与请求一致）后才更新基准、写回课程 store 中的图谱（改节点或删节点及相连边）并显示成功提示。任何失败都保留表单修改并写明「未保存/未解锁/未删除」；网络中断与超时写明「不能确认是否已保存」并提供重新加载，不猜测结果。
  3. 只提交改过的字段：名称、定义去首尾空白后比较；别名按行、逗号、顿号分隔并去空项、去重；重要度、难度须为 0～1，已有值不能清空（PATCH 不接受 null）。本地校验错误在首次提交后显示；服务端 422 `details.fields` 按首段字段名落到对应输入框（`aria-invalid` + `aria-describedby`），编辑该字段后清除，认不出的字段给表单级错误。
  4. 保存遇 `REVISION_CONFLICT`：不覆盖，列出「你的修改 / 最新内容」逐字段差异并阻止再次保存，直到教师选择「采用最新内容」（丢弃本地修改）或「保留我的修改」（以 `current_revision` 为基准重新提交；教师没改过的字段跟随最新内容，不把他人的修改改回去；与最新一致的字段不再提交）。解锁、删除遇冲突时同样换到最新基准并请教师确认后再操作。`details` 形状不完整时只提示重新加载。
  5. 锁：面板显示锁定状态；保存成功后提示「已锁定，自动抽取不会覆盖」；只有已锁定节点显示「解锁」；服务端返回仍锁定时不提示已解锁。
  6. 删除须二次确认（`role=alertdialog`），说明相连关系会一并删除，有未保存修改时额外提示。404 时说明「已不存在」并请页面刷新图谱，不提示「已删除」。
  7. 一次只允许一个写请求；切换知识点或课程时中止在途请求，晚到结果（序号 + 课程作用域）丢弃，不写 store、不提示成功。错误只给固定文案，不回显服务端 message；服务端文本全部插值渲染。
- **后果**：面板可独立挂到教师图谱页；接入页面由新补登的 H14「实现教师图谱编辑页」负责（D-17）；H11 是学生端浏览页，不挂本面板。`details.current` 不含章节，采用最新内容时章节沿用本地已知值；新建知识点仍缺来源块选择接口（F08 待决），本面板只编辑已有节点。
- **回滚**：删除 `src/frontend/src/api/nodeEdit.ts`、`components/NodeEditor.vue`、`composables/useNodeEditor.ts`、`tests/frontend/h07.test.ts` 与本 ADR；无依赖、契约或数据变更。
<!-- OPT-01 original adr-062 end -->

<a id="adr-063"></a>

<!-- OPT-01 original adr-063 begin -->
## ADR-063：H11 学生图谱页只读已发布版本、图/卡片共用筛选与选中

- **日期**：2026-09-26
- **背景**：H11 要求学生浏览已发布图谱并可在图与卡片之间切换，验收为「无发布、空图、分页卡片、键盘可用；任何入口不取草稿」。契约 `getGraph` 在省略 `version` 时对课程内教师返回草稿；`GET /kp/{kid}` 与 `GET /kp` 都没有版本参数，同样按课程内角色决定读草稿还是发布版。课程内角色与账号类型无关（教师账号可以在别的课做学生），路由守卫只能按账号类型引导。H04 画布不可键盘操作，H04/H06 交接把键盘可达留给 H11 卡片视图。
- **决定**：
  1. 新建 `api/graph.ts` 的 `PublishedGraphApi.getPublished(cid, version)`，`version` 必填且须为正整数（否则不发请求），前端没有任何不带版本读图的封装。
  2. `composables/useStudentGraph.ts` 先读课程详情：`my_role ≠ student` 显示「此页面向学生」且不发图谱与详情请求；`published_version = null` 显示「尚未发布」且不发图谱请求；否则按 `published_version` 读图，响应的 `course_id`、`graph_version` 必须与请求一致（草稿的 `graph_version` 为 null，会被拒绝），不一致按数据异常处理。`GRAPH_NOT_PUBLISHED` 显示「尚未发布」，`NOT_FOUND`（版本在读图前被回滚/替换）提示重新加载，`COURSE_FORBIDDEN` 回课程列表并提示。
  3. 卡片由同一份已发布图经 `toKnowledgeCards` 派生（章节目录顺序 → 层级 → 名称 → ID），不调用没有版本参数的 `GET /kp`；详情抽屉复用 H06，只在学生角色下出现。
  4. 图与卡片共用 H05 `useGraphFilters` 的筛选与选中：在图上选中后切到卡片，卡片跳到选中项所在页；工具栏新增 `showStatuses` 属性（缺省 true），学生页关闭审核状态筛选。
  5. `KnowledgeCards.vue` 分页（缺省每页 12）并可完整键盘操作：卡片是原生按钮（Enter/空格选中），卡片组只占一个 Tab 位，方向键移动且越过页边自动翻页，Home/End 到本页首尾，PageUp/PageDown 翻页；列表变短时页码收回最后一页。
  6. 路由新增 `/courses/:cid/graph`（`STUDENT_GRAPH_ROUTE`，`anyAccountRole`），课程页只对课程内学生显示「浏览课程图谱」入口；草稿防护不依赖路由守卫。
- **后果**：课程内教师不能用本页预览学生所见（需要详情接口加版本参数后再开放）。图谱按课程详情里的版本号读取，详情接口按后端当前发布版读取，两次请求之间若恰好发布新版本，详情可能来自新版本（详情响应不带版本号，前端无法校验）。
- **回滚**：删除 `api/graph.ts`、`composables/useStudentGraph.ts`、`components/KnowledgeCards.vue`、`views/StudentGraphView.vue`、`tests/frontend/h11.test.ts`；还原 `router/index.ts`、`main.ts`、`views/CoursesView.vue`、`components/GraphToolbar.vue` 的本任务改动并删去本 ADR；无契约、数据或依赖变更。
- **签收**：待 ArvinHan 审阅（以上约定由 Claude 选定并在交接中报告）。
<!-- OPT-01 original adr-063 end -->

<a id="adr-064"></a>

<!-- OPT-01 original adr-064 begin -->
## ADR-064：I02 掌握标记 API 的访问角色、写事务内绑定与错误形状

- **日期**：2026-09-26
- **背景**：I02 实现 `GET`/`PUT /api/v1/courses/{cid}/progress`（`specs/learning-path.md` §5，ADR-014 修订 1 决定 8、9，ADR-017 决定 4、5）。契约未写明教师能否读写进度、同批重复 `kp_id` 的 `reason` 取值，以及“发布指针在写入期间变化时按新版本复核”的实现方式；I01 仓储只提供原始行与调用方事务入口。
- **决定**：
  1. 两个接口都用 `course_student` 依赖：只有本课程学生成员可读写**自己**的进度；教师成员 403 `ROLE_FORBIDDEN`，非成员 403 `COURSE_FORBIDDEN`，课程从未发布 404 `GRAPH_NOT_PUBLISHED`。身份只取自令牌；请求项带 `user_id` 因 `ProgressUpdate` 闭合而 422 `extra_forbidden`，查询串中的 `user_id` 不被读取。
     **本条覆盖的规格条目**：`specs/identity-access.md` §2.3 第 2 条中「运行时客户端即使多传了这类字段，也只能被忽略」这一表述，以及 `specs/identity-access.md` IAM-14（§4 失败路径）中请求体夹带 `user_id` 时的预期「只改动 A 的进度」——两者都改为本条的 422 零写入。覆盖依据是契约 `api.v1.yaml` `PUT /progress` 的 422 说明（「带 `user_id` 等多余字段」属整批零写入）与 `specs/learning-path.md` §5；被覆盖的两处已就地加覆盖声明。该规格自称「访问矩阵与身份规则的唯一规范表述…不一致时回改契约，不改本文」，本 ADR 未按其路径回改契约，属单方面覆盖，待裁决；「不得从请求读取调用者身份」「不得在请求 schema 中定义 `user_id`」两条不在覆盖范围内。
  2. `PUT` 先查同批重复（通用 422，`details.fields` 每个重复出现项一项 `{in: "body", field: "<i>.kp_id", reason: "duplicate"}`，首次出现项不列），再开 `BEGIN IMMEDIATE`，在持有写锁后按 G07 重新解析发布指针。发布/回滚提交同样需要写锁，因此这就是提交时的最终绑定版本，请求开始后提交的新版本自然用于整批复核；不另做“先绑定、失败再重试”的循环。
  3. 投影在服务层 `app/services/learning/progress.py`（`project_progress` 供 I05 推荐复用，保证同版本同投影）：已提交快照的节点集与谱系按 `version_id` 缓存；原始行经 I01 `read_progress` 读取。同值写入仍有未被覆盖的来源时以 I01 的 `force` 写入，否则交仓储判为无操作。成功后在提交之后按最终绑定版本重新投影返回。
  4. 已提交版完整性故障（快照缺失/摘要不符/不可解析/他课、`V = ∅`、谱系违反修订 3 决定 16）以及这两个接口内其他未预期异常，一律 500 `INTERNAL_ERROR`，`details` 只含 `request_id`（`uuid4().hex`），具体原因与节点 ID 只进服务端日志。
- **后果**：教师端若需要查看某学生进度，须另开接口与规格；I05 推荐直接调用 `project_progress` 即可与 `GET /progress` 同投影。每次投影仍扫描本课程全部已提交版本的版本行（快照解析有缓存），MVP 规模可接受。
- **回滚**：删除 `app/api/progress.py`、`app/services/learning/progress.py`、`tests/backend/test_i02.py`，撤回 `app/main.py` 的路由注册与 `app/schemas/contracts.py` 的两行导出，删去本 ADR；无迁移、无契约与依赖变更，已写入的进度行保留。
- **签收**：决定 1 的 `user_id` 裁决已签收——**(A) 保持 422**（ArvinHan，2026-09-27）：实现、契约与 `test_i02.py` 不变，`specs/identity-access.md` §2.3 第 2 条与 IAM-14 已按 (A) 改写。决定 1 其余部分（教师成员读写进度一律 403）与决定 2～4（含同批重复 `kp_id` 的 `reason = duplicate`）亦已签收（ArvinHan，2026-09-27）。**本 ADR 全部已签收（ACCEPTED）**。以下为裁决前的原始记录。**待裁决项（决定 1 ↔ `specs/identity-access.md`，2026-09-26 独立审查 M-2 提出）**：`specs/identity-access.md` §2.3 第 2 条与 IAM-14 要求请求体中多余的 `user_id`「只能被忽略」，而契约与 `specs/learning-path.md` §5 要求 422 零写入；本 ADR 决定 1 单方面取了 422，并已在该规格这两处就地加覆盖声明。请裁决二者之一：**(A) 保持 422**——现状，实现与契约不变，由产品/协调 Agent 确认覆盖声明并修正 IAM-14 的预期；**(B) 改为忽略**——须同步改 `api.v1.yaml` 该操作的 422 说明、`specs/learning-path.md` §5 与 `tests/backend/test_i02.py::test_body_user_id_is_rejected_with_zero_writes`，并撤回上述覆盖声明。裁决前实现不改。
<!-- OPT-01 original adr-064 end -->

<a id="adr-065"></a>

<!-- OPT-01 original adr-065 begin -->
## ADR-065：J04 检索合并、相关度闸门与上下文预算

- **日期**：2026-09-26
- **背景**：规格 Q1 定义了候选集合 H 与允许引用集合 A，P5 规定 H 为空走 `no_retrieval_hit`、H 非空但无候选达到阈值走 `below_similarity_threshold`，主验收第 8 条要求超出 token 预算时截断后仍可定位、每个编号有效。但规格没有说明：只有图证据（没有相似度）的块如何参与阈值判断，预算截断以什么为单位，以及预算放不下任何块时如何处理。阈值与预算的具体值仍是待细化项（K01）。
- **决定**：
  1. 实现在 `services/qa/context.py` 的 `build_context(course_id, revision_ids, vector_hits, subgraph, load_chunks, threshold, budget, estimate_tokens)`。阈值与 `ContextBudget(chunk_tokens, graph_tokens, max_chunks)` 由调用方传入，**不设缺省值**，测试一律用 fake 值；真实值待 K01 标注集调参后由 J07 配置。
  2. 合并去重：J01 向量命中与 J02 子图证据按 `chunk_id` 合并，保留全部出处（`origins` 为 `vector` / `graph`，`kp_ids` 为经 `EVIDENCED_BY` 关联的知识点），相似度取最大值。
  3. Q3.1 以 SQLite 中的块为准复核：课程相同、`revision_id` 在绑定版本修订列表内、可定位（第一个能给出 `page` 或 `section_path` 的出处）。读不到的块也剔除。通过者构成 H，各类剔除分别计数。
  4. **只有向量相似度能打开闸门**：H 中至少一个向量候选的 `score ≥ threshold`（含等号）才进入生成。只来自图证据的块没有相似度，闸门打开后作为补充排在达标向量块之后；有相似度但未达标的块不论是否也来自图，都不进 A。这样用词相近但无关的问题（主验收第 9 条）不会因图谱子串匹配而绕过阈值。**闸门打开后，这些无相似度的图证据块会获得编号并进入 A，即成为可被引用的证据**（J06 的三项复核只查课程、修订、可定位，不查阈值）；这相对规格 Q1「从 H 中选出、达到阈值」的字面是**扩大**，属有意取舍（偏向少答错、保留完整证据链），已同步写入 `specs/grounded-qa.md` Q3.1，并要求 K03 把「引用来自图证据块」单列统计。
  5. 预算以**整块**为单位：块的文本与定位从不截断，放不下的块跳过，继续尝试后面较小的块，直到 `max_chunks`。token 缺省按渲染后整块的 UTF-8 字节数估算（E03 口径，只会高估）。闸门已开但一个块都放不下时，同样按 `below_similarity_threshold` 拒答（wire 原因是闭集），记 WARNING，`stats.over_budget` 可区分。**该分支的 `reason` 与「相似度不达标」不同义，属 wire 语义合并**：`reason` 是闭集且 J10 只记 `reason`（`stats` 不出进程），故 K03 与 J10 必须另记 `over_budget` 与候选数，才能把预算拒答与阈值拒答分流，否则 QA-6/QA-7 的机器面统计会把两者混为一类。不映射 `BUDGET_EXCEEDED`：O11/QA-28 的预算是 A07 的 **LLM 调用计费预算**（语义是「不发请求」，HTTP 层错误），与「上下文窗口装不下证据」无关。
  6. 图谱子图渲染为无编号的行（节点在前、关系在后），行内容剔除类标记与哨兵，按行计入独立的 `graph_tokens` 预算；节点放不下时不渲染任何关系。拒答时仍返回全部命中知识点 ID，供 Q4 `related_kp_ids` 导航。
- **后果**：J05 拿到的编号 `1..k` 与 A 一一对应，J06 可用 `by_index` 复核并构造引用。运行时尚无环节为文本块写向量（J01 待决），接上前向量检索为空，任何问题都会以 `no_retrieval_hit` 或 `below_similarity_threshold` 拒答；这一缺口不在本任务内补。图证据不能单独打开闸门，因此向量召回不足时，即使图谱命中也会拒答，这是有意偏向少答错。**已知遗留**（独立审查 2026-09-26 提出，未在本次实现内修）：`kp_ids` 只取 J02 子图 evidence 内的知识点（`context.py`），对「仅向量命中且不在子图 evidence 内」的块为空，与 Q4 「∪ J02 命中知识点」的字面相比覆盖面偏窄，J06/J07 需知悉，必要时补反向查询；测试全部使用 fake loader，未覆盖真实 `get_chunks` 的 keyword-only 接线。
- **回滚**：撤销 `src/backend/app/services/qa/context.py` 与 `tests/backend/test_j04.py`；无迁移、无契约与依赖变更。
- **签收**：待 ArvinHan 审阅。**需明确签收的两点**：第 4 条的「图证据块在闸门打开后可获得编号并被引用」（相对 Q1 字面的扩大）；第 5 条的「预算 0 块复用 `below_similarity_threshold`」属 wire 语义合并、必须由 K03/J10 另记 `over_budget` 分流。若否决任一条，先改规格再改 `services/qa/context.py`。
<!-- OPT-01 original adr-065 end -->

<a id="adr-066"></a>

<!-- OPT-01 original adr-066 begin -->
## ADR-066：发布时补齐文本块向量（G08）

- **日期**：2026-09-26
- **背景**：J01 检索文本块向量（ADR-046），但运行时没有任何环节写文本块向量。F04 只为被知识点引用的块建 `Chunk` 节点，不写向量；G03 只算知识点向量；只有 F14 迁移会重写已有的文本块向量。不补这一步，问答检索永远为空。
- **决定**：
  1. 新增任务 G08（ArvinHan 2026-09-26 同意）。在发布 P8 写副本之前，`services/versions/chunk_vectors.index_chunks` 按快照修订列表，从 SQLite 读出全部文本块：
     - 先查 Neo4j，找出缺节点、缺 `revision_id`、缺当前空间向量或维度不对的块；
     - 只为这些块调用向量模型；
     - 按每批 200 块分批 `MERGE` 节点，并写入向量和缺失的 `document_id`、`revision_id`。
  2. 文本块节点与向量跨版本共享，写入可以重复执行。发布失败时它们保留，C1 不删除，清扫也不处理。
  3. P9 增加核对：快照修订列表内的每个文本块都要有节点、`revision_id` 和当前空间下维度正确的向量，否则按 `VerificationError` 走 C1。
  4. 回滚不补齐，也不核对文本块：回滚不得调用向量模型（PUB-26），源版本在发布时已经补齐。
  5. 放在发布阶段而不是抽取阶段：只有发布版需要被学生检索；向量调用与知识点向量一起放在锁外；抽取与持久化阶段的状态机和取消点不变。
- **后果**：首次发布要为课程全部文本块算一次向量，耗时随资料量增长；之后只算新修订的块。本 ADR 之前已经提交的版本没有文本块向量；**「重新发布一次即可补齐」不成立**（独立审查 2026-09-26 证伪：草稿摘要未变时 P7 的幂等路径在 P8 之前返回，`publish.py` 不补齐；草稿有改动时补的是**新快照**的修订列表，被新修订取代掉的旧修订永远补不上；回滚按 PUB-26 也不补）。补齐需按修订列表的独立入口（如 `scripts/reembed.py` 的按版本补齐子命令），或在发布一个仍包含这些修订的新版本时顺带完成。回滚到这样的旧版本时检索结果不全，MVP 阶段没有真实数据，暂可接受，但不得再按「重新发布即可」操作。另：批次中途失败会在库里留下「部分块有向量」（不属任何版本副本、`materialize` 也不会删 `Chunk`），可重试续做。
- **回滚**：撤销 `services/versions/chunk_vectors.py` 和 `publish.py` 中的两处调用；已经写入的文本块向量可以留在库中，不影响其他读取，F14 迁移时照常处理。
- **签收**：新增任务由 ArvinHan 2026-09-26 同意；放在发布阶段及以上细节由 Claude 选定，并在交接中报告。

<!-- OPT-01 original adr-066 end -->

<a id="adr-067"></a>

<!-- OPT-01 original adr-067 begin -->
## ADR-067：教师图谱编辑页的草稿读取、共享图与未保存确认（H14）

- **日期**：2026-09-27
- **背景**：D-17 补登 H14，把 H06 详情、H07 节点编辑面板、H08 连边编辑挂到一个教师页面上。三者都以课程 store 的 `graph` 为基准并在成功后写回；此前没有任何页面读草稿图。契约 `getGraph` 省略 `version` 时课程内教师读草稿，学生读最新发布版。
- **决定**：
  1. 路由 `/courses/:cid/graph/edit`（`TEACHER_GRAPH_ROUTE`），`meta.accountRole = 'teacher'`；页面再按 `Course.my_role === 'teacher'` 判断，读图时 `ROLE_FORBIDDEN` 同样按非教师处理。课程页只对课程内教师显示入口。
  2. 草稿读取用独立的 `DraftGraphApi`（`DRAFT_GRAPH_API_KEY`），与学生页的 `PublishedGraphApi` 分开注入。响应必须 `course_id` 一致且 `graph_version` 为 null，否则按数据异常丢弃，避免把发布版本当草稿编辑。
  3. 草稿写入课程 store，画布取 `useRelationEditor().canvasData`（含保存中的临时边与成环冲突标色）再经 `useGraphFilters` 筛选。保存/删除/连边成功时编辑器写回 store，画布自动同步；失败时 store 不变。
  4. 编辑器要求刷新时只替换草稿、保留当前画布，失败给提示；刷新在途时若 store 已被编辑器写回，丢弃这份响应并重新拉取。课程上下文被清空（`COURSE_FORBIDDEN`、会话过期）而仍停在本页时显示错误态。
  5. 右侧面板分「详情 / 编辑知识点 / 编辑关系」三个页签。节点编辑面板用 `v-show` 常驻，切页签不丢修改；「编辑关系」页签下画布点击用于点选起点和终点，不改变知识点选中。
  6. H07 `NodeEditor` 新增 `defineExpose({ dirty })`（扩围一行）。有未保存修改时换节点或关闭面板先弹页内确认（`useSelectionGuard`）；离开路由或换课用 `window.confirm`；刷新或关闭标签页挂 `beforeunload`。被拒或会话失效时强制离开，不再询问。
- **后果**：详情页签选中节点时，常驻的节点编辑面板也会读一次同一知识点（请求翻倍，体量小，接受）。离开本页不清空课程 store 里的草稿；目前学生页用自己的状态，不受影响，但以后若有页面直接读 `store.graph`，需先按角色重新加载。页面只经假 API 验证，未与真实后端联调（后端 `/relations` 路由尚不存在，见 H08）。
- **回滚**：撤销 `views/TeacherGraphView.vue`、`composables/useTeacherGraph.ts`、`tests/frontend/h14.test.ts`，以及 `api/graph.ts`、`router/index.ts`、`main.ts`、`views/CoursesView.vue`、`components/NodeEditor.vue` 中的对应增量；无迁移、契约与依赖变更。
- **签收**：ArvinHan 2026-09-27 签收（三页签布局、页内确认 + 离开确认、刷新在途遇写入则重拉，均按原方案）。

<!-- OPT-01 original adr-067 end -->

<a id="adr-068"></a>

<!-- OPT-01 original adr-068 begin -->
## ADR-068：J05 有证据问答生成的提示结构、防注入与故障分类

- **日期**：2026-09-27
- **背景**：J05 位于 J04（编号上下文）与 J06（引用校验与终态）之间，原子验收为「空/低分上下文生成调用数为 0；原文注入按资料处理；超时为独立错误」。规格 Q3.4、Q5、Q8 H3 已规定哨兵、终态矩阵与「生成不见历史」，但没有规定：提示中如何编号资料、资料里的伪造块头与哨兵如何处理、流式故障怎样落到 `details.reason`，以及 J05 与 J06 的分工边界。E01 的 `answer_with_context` v1 是占位正文。
- **决定**：
  1. 实现在 `services/qa/generate.py`：`AnswerGenerator.generate(question, context, course_id, request_id, deadline)`。J04 上下文不是 `ready` 或没有编号块时返回 `SkippedGeneration(reason)`，**不渲染提示、不绑定策略、不写 `model_calls`**；否则返回尚未发请求的 `AnswerGeneration`，首次迭代才流式调用（J07 先发 `meta`）。接口没有历史参数（H3）。
  2. **J05 只产出原始正文**：引用归一化、暂扣、哨兵判定、逐句覆盖与终态构造全部归 J06。`AnswerGeneration` 逐个产出非空片段，`close()` 关闭供应商流（J06 识别哨兵后、J07 客户端断开时调用）；正常结束后 `result` 给出拼接正文与 `finish_reason`（`length` 即 O6 截断）。
  3. 提示 `answer_with_context` 升到 v2（草稿），变量 `graph_context`、`context`、`question`，单条 user 消息。资料以 `<<资料 n>>（定位）` 为块头编号，n 与 J04 编号相同；知识点结构无编号且写明不能被引用；三部分各有 `<<…>>`/`<<…结束>>` 分段，结尾重申「只当作数据」。不用 J04 的 `[n]（定位）` 渲染，是为了让块号只出现在块头里：资料原文中的 `[3]`、代码 `a[1]` 保持原样，不会被当成块号。
  4. **原文注入按资料处理**：资料原文、结构上下文与问题中能伪造分段、块头或哨兵的开头（`<<`/`＜＜` 后接 `资料`、`课程资料`、`知识点结构`、`学生问题`、`INSUFFICIENT_EVIDENCE`）把 `<<` 换成 `«`，长度不增加；其余字符（含 `cout << x`）不动。注入文本不删除，仍作为数据留在资料段内。J06 的引用原文取自文本块数据，不受替换影响。
  5. 请求 `purpose = answer_with_context`、`response_format = text`、输出上限 `ANSWER_MAX_OUTPUT_TOKENS = 2048`（2026-10-03 ADR-086 修订，按已批准的调高方向定稿）；不设单次超时，由 E04 按链路剩余时间补上。经 `bind(CallAttribution(course_id, request_id), deadline=...)` 调用，首字前切备用、出字后不切由 E04 保证。
  6. **故障分类**（`GenerationErrorKind` 闭集，`code` 与 `details_reason` 直接对应契约）：E04 截止时间、读取中链路到期、无状态码且剩余时间 ≤ 0.25 秒的供应商超时 → `timeout`；401/403 → `auth`；首字前其他供应商故障（含 408、熔断、主备都失败）→ `upstream`；出字后 → `stream_interrupted`；预算拒绝 → `BUDGET_EXCEEDED`；预写失败 → `STORAGE_UNAVAILABLE`；400/404/422 与意外异常 → `INTERNAL_ERROR`。`delivered` 标明故障前是否已出字，供 J07/J09 撤回。**超时是独立错误**：与 `upstream` 同为 `LLM_UNAVAILABLE`，以 `details.reason` 区分，不新增错误码（Q5 说明）。
- **后果**：J06 拿到的是可逐段处理、可随时关闭的原始流；J07 只需把 `SkippedGeneration` 映射为 `meta(not_covered)` + `done`，把 `GenerationError` 映射为 `error` 事件或 Q7 的 HTTP 错误。J04 预算按 J04 的 `render_evidence()`（`[n]（定位）` 块头、每块以 `\n\n` 结尾）估算，实际提示的块头是 `<<资料 n>>（定位）` 且只有末块少一个 `\n\n`，故每块差 8 字节、末块再多 2 字节，上界为 `max_chunks × 8 + 2` 字节（独立审查按字节实测，已由 `test_prompt_blocks_are_no_larger_than_the_budgeted_rendering` 断言）。资料原文里的 `<<` 被换成 `«`（每个发生替换的 `<<` 少 1 字节），只会缩小该差值。`LLM_CHAT_FIRST_TOKEN_TIMEOUT_SECONDS` 尚无实现：E03 适配器的超时覆盖整条流，同步生成器无法在首字前中断读取；将来补上时，其超时因剩余时间充足会被归为 `upstream`，与本 ADR 一致。`close()` 须与迭代在同一线程调用（生成器不可跨线程关闭），J07 用线程读流时需另行安排。提示只经 fake 模型验证，逐句标注与防注入的实际效果待 K03 真实模型评测（付费调用需另行同意）。
- **回滚**：撤销 `services/qa/generate.py`、`tests/backend/test_j05.py`，把 `prompts/answer_with_context.yaml` 与 `prompts/MANIFEST.md` 对应行恢复为 v1，`tests/backend/test_e01.py` 一行恢复；无迁移、契约与依赖变更。
- **签收**：待 ArvinHan 审阅。需确认：输出上限已由 ADR-086 确认为 2048；以 `<<资料 n>>` 块头代替 `[n]` 渲染；超时判定的 0.25 秒容差。
- **后果**：J06 拿到的是可逐段处理、可随时关闭的原始流；J07 只需把 `SkippedGeneration` 映射为 `meta(not_covered)` + `done`，把 `GenerationError` 映射为 `error` 事件或 Q7 的 HTTP 错误。块头比 J04 估算用的 `[n]` 多约 9 字节/块，J04 预算按 J04 渲染估算，实际提示略大，差值有上界（`max_chunks × 9` 字节），可接受。`LLM_CHAT_FIRST_TOKEN_TIMEOUT_SECONDS` 尚无实现：E03 适配器的超时覆盖整条流，同步生成器无法在首字前中断读取；将来补上时，其超时因剩余时间充足会被归为 `upstream`，与本 ADR 一致。`close()` 须与迭代在同一线程调用（生成器不可跨线程关闭），J07 用线程读流时需另行安排。提示只经 fake 模型验证，逐句标注与防注入的实际效果待 K03 真实模型评测（付费调用需另行同意）。
- **回滚**：撤销 `services/qa/generate.py`、`tests/backend/test_j05.py`，把 `prompts/answer_with_context.yaml` 与 `prompts/MANIFEST.md` 对应行恢复为 v1，`tests/backend/test_e01.py` 一行恢复；无迁移、契约与依赖变更。
- **签收**：待 ArvinHan 审阅。需确认：输出上限已由 ADR-086 确认为 2048；以 `<<资料 n>>` 块头代替 `[n]` 渲染；超时判定的 0.25 秒容差。

<!-- OPT-01 original adr-068 end -->

<a id="adr-069"></a>

<!-- OPT-01 original adr-069 begin -->
## ADR-069：I05 推荐查询从绑定版本的已提交快照读图，一次解析、全量排序后截断

- **日期**：2026-09-27
- **背景**：I05 要求「请求全程同版本」「截断稳定」「未发布 404 与全掌握区别」「已提交图损坏 5xx」「有环明确错误」。G07 规定请求开始解析一次发布版；I02 的 `project_progress` 已按绑定版本投影进度（谱系取自已提交快照）；I03/I04 是纯函数。尚未确定的是推荐的图数据（节点属性、`PREREQUISITE` 边、章节树）从哪里读。
- **决定**：
  1. `GET /api/v1/courses/{cid}/recommend` 仅学生成员可用（`course_student`，与 ADR-064 一致），教师 403；从未发布为 404 `GRAPH_NOT_PUBLISHED`，与 200 `state = all_mastered` 区分。
  2. 请求开始时调用一次 `resolve_published`；图取自该 `version_id` 在 SQLite 中的已提交快照（摘要复核后 `load_snapshot`），**不读 Neo4j 副本、不读草稿**。快照不可变、与 I02 投影所用谱系同源，因此图、进度投影、理由与响应 `graph_version` 必然同版本；推荐接口不依赖 Neo4j 可用。校验通过的图按 `(sqlite_url, version_id)` 缓存，损坏的不缓存。
  3. 节点集由 I03 `build_prerequisite_graph` 做全图校验，只取 `type = PREREQUISITE` 的边；另核对投影节点集与图节点集一致。I04 对**全部**候选排序后才截断到 `limit`，`total_eligible` 为截断前总数；排序键 `(-score, chapter_rank, kp_id)` 是全序，`limit = k` 的结果恰为 `limit = 50` 结果的前 `k` 条。
  4. `limit` 默认 10、范围 1～50（ADR-014 修订 1 决定 7），越界或非整数为通用 422 `VALIDATION_ERROR`（`fields[].field = "limit"`）。权重只取启动时校验过的 `RECOMMEND_WEIGHT_*`，请求不能传。
  5. 已提交版完整性故障——快照缺失、摘要不符、不可解析、他课、`V = ∅`、环、自环、悬空端点、章节树损坏、未知章节、谱系违反修订 3 决定 16——以及其他未预期异常，一律 500 `INTERNAL_ERROR`，`details` 只含 `request_id`；错误种类（如 `cycle`）与环路节点只写服务端日志（ADR-017 决定 4、§1）。
- **后果**：推荐不受 Neo4j 副本物化或补偿状态影响；代价是每个新版本首次请求需解析一次快照 JSON（之后命中缓存），MVP 规模可接受。快照里 `importance`/`difficulty` 的范围已由 `load_snapshot` 校验，越界值在读快照时即成为 500，I04 的 `invalid_number` 分支在此路径上不会触发。候选为空只可能是 `M = V`（DAG 必有入度 0 的点），因此 `all_mastered` 与 `total_eligible = 0` 等价。
- **回滚**：撤销 `app/services/learning/recommend.py`、`app/api/recommend.py`、`tests/backend/test_i05.py`，以及 `app/main.py` 的路由注册、`app/schemas/contracts.py` 的一行导出；无迁移、契约与依赖变更。
- **签收**：待 ArvinHan 签收（第 2 条「图读快照而非 Neo4j」与第 1 条教师 403 为 Claude 选定）。

<!-- OPT-01 original adr-069 end -->

<a id="adr-070"></a>

<!-- OPT-01 original adr-070 begin -->
## ADR-070：教师审核队列页的数量口径、单写与合并交互（H09）

- **日期**：2026-09-27
- **背景**：F11（ADR-060）提供了 `getReviewQueue`（三栏、键集分页、完整 `totals`）与 `resolveReviewItem`（通过 / 拒绝 / 合并 / 不是重复 / 确认保留）。H09 的验收是「三类空态、重复操作、合并冲突；刷新后数量一致」。未定的是：页面显示的数量从哪来、处理后其他栏的连带变化怎样同步、连点与并发怎样防、合并时怎样选主节点、成环等冲突怎样呈现、关系两端只有 ID 时显示什么。
- **决定**：
  1. **页面与入口**：`/courses/:cid/review`（`REVIEW_ROUTE`，仅教师账号）；课程内角色非教师时不读队列。课程页只对课程内教师显示「审核队列」入口。三栏上下排列，顶部有带数量的栏目导航。
  2. **数量以服务端为准**：栏目数量只取服务端 `totals`（读队列、加载更多、处理结果都带回），本地不加减，所以刷新页面后的数量与处理后显示的一致。
  3. **一次只处理一条**：任一处理在途时所有处理按钮禁用，同一条连点只发一次；在途的刷新与加载更多作废。服务端返回 `changed = false`（同一动作此前已生效）时照常移除该条，提示「此前已处理」。
  4. **连带变化不在本地猜**：拒绝关系、拒绝孤立知识点、合并成功后，以及条目已不在队列（404）、修订冲突、422、网络中断或超时（无法确认结果）后，重新读取三栏第一页，条数取「当前已加载的最大栏条数」（不少于 50，不超过 200）。通过关系、不是重复、确认保留不影响其他栏，不重新读取。加载更多遇 422（游标失效）也从第一页重读。
  5. **合并**：疑似重复先点「合并…」展开主知识点单选（默认第一项），说明「名称并入别名，关系与来源迁到主知识点，主知识点被锁定，合并后不能自动拆回」，确认后才提交 `merge` + `primary_id`；不带 `expected_revisions`（`ReviewDuplicateAction` 契约没有该字段）。
  6. **冲突呈现**：409 `CYCLE_DETECTED` 把 `details.cycle` 换成名称路径显示在该条下，条目保留、不重读，教师可改为「不是重复」或去图谱编辑页调整前置关系；`COURSE_BUSY` 提示稍后重试；`REVISION_CONFLICT` 提示并重读。只按错误码给固定文案，不回显服务端 message。
  7. **名称**：关系只有两端 ID，页面同时读草稿图谱（`DraftGraphApi`）仅用于 ID → 名称；读取失败不影响审核，退回显示 ID。合并后重读时一并刷新名称。
- **后果**：每次影响其他栏的处理多一次队列读取与一次草稿读取（单课程规模可接受）。重读只取第一页窗口，已加载超过 200 条的栏会截到 200 条并给出「加载更多」。本页不写课程 store 的草稿图，教师图谱编辑页进入时自行重读草稿，不会看到合并前的旧图。
- **回滚**：撤销 `views/ReviewView.vue`、`composables/useReview.ts`、`api/review.ts`、`router/index.ts` 与 `main.ts` 的注册、`views/CoursesView.vue` 的入口、`tests/frontend/h09.test.ts`；无契约、后端或数据变更。
- **签收**：待 ArvinHan 审阅（以上约定由 Claude 选定并在交接中报告）。
<!-- OPT-01 original adr-070 end -->

<a id="adr-071"></a>

<!-- OPT-01 original adr-071 begin -->
## ADR-071：关系编辑 HTTP 路由（F06-API）

- **日期**：2026-09-27
- **背景**：契约 `src/contracts/api.v1.yaml` 从 A10 起就定义了 `createRelation`（POST 201）、`updateRelation`（PATCH 200）、`deleteRelation`（DELETE 204）与 `RelationCreate`/`RelationUpdate`/`Relation`，但后端 HTTP 层从未实现：F06 交付的是服务层与仓储层的「锁草稿 → 读图 → 校验 → 环检测 → 写入」单事务（ADR-025），F11 的审核动作只覆盖低置信度关系的 approve/reject。前端 H08/H14 因此只能按契约写客户端与假实现，H14 交接明确记着「**仅假 API 验证**（后端尚无 `/relations` 路由）」；ADR-061 的待决项也写着「关系编辑（F06 路由未实现）……接入审计留给对应任务」。本任务就是那个任务。
- **决定**：
  1. **路由位置**：新建 `src/backend/app/api/relations.py`（`prefix="/api/v1/courses/{cid}"`），在 `app/main.py` 注册；operationId 与契约逐字一致。路由只做协议转换与依赖注入：课程教师依赖、错误码到 HTTP 的映射、PATCH 请求体的逐字段校验。
  2. **服务与仓储分层**：新增 `services/graph/edit_relation.py`（编排：课程写锁、审计时序、响应组装）与 `repositories/graph_relation_edit.py`（Cypher：按 `rel_id` 读一条可见关系、删除关系与其 `RelationIdentity`、同身份改状态）。关系写入复用 F06 的 `apply_relations`（同一事务内的守卫锁、端点校验、重复关系、DAG 环检测与 `MERGE`），不另写一套写入路径。
  3. **修改语义**：`type`/`from_id`/`to_id` 任一变化即关系身份变化（§8.4 的 `rel_id` 由「课程 + 类型 + 起点 + 终点」派生）→ 同一事务内**先删**旧关系与旧身份，再按新身份写一条人工关系（`source = manual`，保留原 `confidence` 与 `status`）；先删后写也让环检测看见真实的边集（反转 `A → B` 为 `B → A` 时两条边不会同时存在而误报成环）。只改 `status` 时同身份**就地改**（置 `source = manual`、`contrib_manual = true`、修订号 +1），`source_pairs`（AI 的来源证据）因此不丢——改状态不该删掉来源。目标状态与当前一致且关系已是人工 → 空操作：不写入、不加修订号、不记审计（同 F08 的解锁语义）。
  4. **环检测**：新建与改向走 F06 的 `check_candidates`；把 `rejected` 的 `PREREQUISITE` 边恢复为有效时，服务层按同一组读者（`read_visible_nodes` + `read_prerequisite_graph`）重新验环——`rejected` 的边不参与环检测，恢复它等于重新加边（规格 DAG-7），且再拒绝时不降级任何边。自环：`PREREQUISITE` 由 F06 报 409 `CYCLE_DETECTED`（`details.cycle` 首尾同 ID，验收 DAG-9）；其余三种类型没有自环语义，报 422 的字段错误。
  5. **错误映射**：409 `CYCLE_DETECTED`（`details.cycle`）、409 `DUPLICATE_RELATION`（`details.existing_id`）、422 `DANGLING_ENDPOINT`（`details.missing`；`src/contracts/errors.v1.md` 给该码的 HTTP 状态就是 422，契约的 422 响应也是 `Error`）、409 `COURSE_BUSY`（`details.holder`）、404 `NOT_FOUND`（不存在或对本课草稿不可见）、403/401 同 `graph_nodes.py`。Neo4j 不可达 → 503 `STORAGE_UNAVAILABLE`，与既有图路由一致，但**契约未声明**（F11 审查 D-4 已记录同类差异）；本任务不改契约真源。
  6. **PATCH 是闭合可编辑集**：契约的 `RelationUpdate` 只列四个可编辑字段且 `minProperties: 1`，但生成模型既不禁止多余键也不区分显式 `null`，因此按 `graph_nodes.py` 对 `KnowledgePointUpdate` 的同一做法逐字段检查；`course_id`、`id`、`revision` 这类路由无法实施的键返回 422 `extra_forbidden`，而不是静默丢弃（后者会让客户端以为改动已生效）。POST 的 `RelationCreate` 契约未写 `additionalProperties: false`，多余键按契约忽略，与 `createKnowledgePoint` 口径一致。
  7. **审计接入（ADR-061）**：三种写入都经 `audit.begin/commit`：`actor_id` 为调用教师、`draft_revision` 恰加一、摘要是关系白名单状态（`type`/`from_id`/`to_id`/`status`/`source`，另附 `rel_id` 与关系修订号）。`graph_edit_logs.action` 是迁移 012 的**数据库级** CHECK 闭集，新增动作要重建表，所以关系行复用 `create`/`update`/`delete`，靠摘要里的 `entity = "relation"` 与节点行区分；`reconcile` 对关系行用摘要里的 `after` 与图里当前状态逐项比对判定是否生效（关系没有随写入变化的节点修订号），`kp_revision_before/after` 对关系行为 NULL。
  8. **审计时序**：关系路由把 `audit.begin` 放在**同一 Neo4j 写事务内、写入语句之后**。这样成环、悬空端点、重复关系这些写入前的拒绝既不加草稿修订号也不留审计行（与 F08～F10 的「拒绝不写、不记」一致），而 `begin` 之后的失败照旧由 `abort`/`reconcile` 收尾；`commit` 失败仍只记日志、行留 `pending`，**已提交的编辑不回滚**。
  9. **响应体来自真实图**：由写事务内读回的关系（`read_relation_detail`）与 SQLite 文本块（`read._chunks` + `_source_ref`）组装，不回声请求体；`confidence`/`status`/`source`/`source_refs` 与 `RelationStandard`/`RelationDowngraded` 的 `oneOf` 约束一致。
- **后果**：
  - H14 的「仅假 API 验证」缺口关闭：前端 `api/relations.ts` 与 `useRelationEditor.ts` 现在有真实后端。但**仍未做真实前后端联调**（前端测试依旧注入假实现），教师页对真实 `/relations` 的端到端行为未在浏览器里验证。
  - 审计行对关系存 `rel_id` 到 `kp_id` 列、两个修订号列为 NULL：审计消费者必须先看摘要的 `entity` 才知道 `kp_id` 的含义。
  - 改 `type` 或方向会重置关系 `revision` 为 1 并丢弃 `source_pairs`（新身份 = 新的人工断言；`confidence` 与 `status` 保留）；只改 `status` 保留来源证据。这是「关系身份由四元组派生」的直接后果，已写入本 ADR 的后果段。
  - 契约未声明 503；自环（非 `PREREQUISITE`）与 `InvalidRelationError` 兜底各引入一个未在 `errors.v1.md` 登记的领域 `reason`（`self_loop`、`invalid_relation`）。契约真源在本任务冻结，两处待签收。
  - 关系写入的守卫节点序号按调用计两次（仓储层事务先加锁，`apply_relations` 在同一事务里再加一次，与 F13 的 `_write_draft` 相同）；锁只加一次，序号只是簿记。
- **回滚**：撤销 `src/backend/app/api/relations.py`、`src/backend/app/services/graph/edit_relation.py`、`src/backend/app/repositories/graph_relation_edit.py`、`tests/backend/test_relations_api.py`、`tests/integration/test_relations_api.py`，以及 `main.py`（2 行路由注册）、`schemas/contracts.py`（2 行导出）、`services/graph/audit.py`（关系摘要、`_applied_relation`、`reconcile` 分派）中的增量；无迁移、无契约、无依赖变更，回滚后 H14 回到「仅假 API 验证」。
- **签收**：待 ArvinHan。
<!-- OPT-01 original adr-071 end -->

<a id="adr-072"></a>

<!-- OPT-01 original adr-072 begin -->
## ADR-072：PR #264 独立审查四项遗留的处置（sweep 调度、无来源手工节点、空清理解锁、重跑状态保护）

- **2026-10-08 修订（ADR-094，已实施并验证）**：决定 3 的 worker `cleanup_failed_task` 无贡献预读快路径撤销；取消后服务端仍可能迟到提交。该入口统一取得课程守卫及 DraftWriteGuard，无条件幂等撤销，在专用有截止事务确认提交/退出后清标记；失败/不确定保留标记。其余决定不变；真实网络、恢复及最终整次门禁已通过，限定围栏风险 CLOSED。

- **日期**：2026-09-27
- **背景**：G05/G06（PR #264）的独立审查留下四项未在本 PR 处理的遗留（`docs/tasks.md` 的「G05 待决」与 `docs/handoffs/claude-g05.md`）：`reconcile.sweep` 没有调度实现；无来源的人工节点详情返回 500；`cleanup_failed_task` 在没有任何需要撤销的贡献时仍要等课程写锁；任务重跑把教师已裁决的状态写回 `draft`。四项都落在既有契约、规格与测试范围内，但各自有需要选定的实现口径，故合并为一条 ADR。
- **决定**：
  1. **`sweep` 接入 worker 周期回收（A06 §8.6）**。在 `app/workers/runner.py` 新增 `PublishSweep`，接在 `run_loop` 已有的 `maintenance` 挂点（ADR-039 第 3 条预留）上，每轮主循环后用 `time.monotonic` 检查一次；距上次执行满 `PUBLISH_SWEEP_INTERVAL_SECONDS` 才真正调用 `reconcile.sweep`。周期与开关只从环境变量读：整数 ≥ 0，缺省 `3600`（§8.6 的「建议每小时一次」），`0` 表示不启用周期清扫（发布与回滚前的 `reclaim_expired` 仍在，ADR-036 第 6 条）。选「缺省启用」的理由：`sweep` 从不删除已提交版本与租约内的尝试（ADR-036 第 3 条），可重复执行（无变化时第二次不写库），并逐课程隔离失败，所以周期性运行是安全的，而「不启用」才会让 `cleanup_pending` 与过期尝试长期堆积。**错误隔离**：`sweep` 自身逐课程记日志继续；`PublishSweep.__call__` 再兜一层 `except Exception`（含 `list_course_ids` 的 SQLite 故障），只记日志、绝不抛回 `run_loop`；下次时间在调用**之前**排定，故障时按周期重试而不是每轮都打 Neo4j。时钟与清扫函数可注入，测试用假时钟确定性地证明「到点才调用」与「抛错不打断主循环」；真实子进程按小时触发的端到端验证不在单测内（由 K08 的进程测试与同一挂点覆盖）。
  2. **无来源手工节点的详情表示**。**不采用**放宽 `KnowledgePointDetail.source_refs` 的 `minItems: 1`（选项 a）：那会直接推翻既有负例 `tests/contracts/test_b11.py::test_node_detail_requires_locatable_source`，而那条负例正是「AI 节点不得缺来源」的完整性不变量；OpenAPI 3.0 也没有 `if/then` 能表达「只有 `source = ai` 才要求 ≥ 1」。**采用**新增响应形状：契约加 `KnowledgePointDetailWithoutSource`（与 `KnowledgePointDetail` 字段相同，`source_refs` 为 `maxItems: 0` 的**显式空数组**），`getKnowledgePoint` 的 200 改为两者的 `oneOf`；`KnowledgePointDetail` 原样不动。真源改后按 ADR-004 用 `scripts/gen-contracts.sh` 重新生成并入库，`--check` 与 `scripts/verify/contracts.sh` 保持一致。服务端 `read_knowledge_point` 用**读到的原值** `source` 判定：`manual` 且一条可定位来源都没有 → 200 空态；其他情况（含发布副本缺 `source` 属性）→ 仍抛 `SourceUnavailable` → 500 `INTERNAL_ERROR`。**残留代价**：一个操作有两种成功形状，客户端要处理联合（生成的 TS 两种都有；前端 `useKnowledgeDetail` 本就容忍 `source_refs: []`）；「只有手工节点可以为空」无法写进契约，由服务端与测试（`test_ai_node_...`、`test_published_copy_...`）兜住。`GET /graph` 聚合路径本来就不带 `source_refs`，补回归测试。
  3. **没有实际工作的清理不取锁**。`graph_relations.task_has_contributions` 新增一条存在性读，谓词与 `_REVOKE_RELATIONS`/`_REVOKE_NODES` 一一对应（节点/关系的 `contrib_tasks`、本任务的 `EVIDENCED_BY`）。`cleanup_failed_task` 先读：无工作 → 直接 `clear_cleanup_pending` 并返回，**不取课程写锁、不等待**；有工作 → 完全沿用原路径（取锁 → 同一写事务里 `lock_draft` + `revoke_task` → 清标记）。**一致性论证**：只有 `persisting` 会写某任务的贡献，且只在它持有租约期间；T9 清空租约，而 `claim_next` 只领取 `parsing/extracting/merging/persisting` 的任务，`failed` 任务永不再被领取，所以判断发生在 T9 之后时「没有贡献」是最终结论——把判断放在锁外不会漏掉撤销。并发清理可能都读到「有工作」，它们在锁上串行，`revoke_task` 幂等。读失败（Neo4j/SQLite 不可用）返回 `False`、保留 `cleanup_pending`，不取锁。真实清理的锁保护、ADR-025 的守卫串行与租约语义均不变。
  4. **任务重跑不把教师已裁决的状态降级**。根因在 `graph_nodes._WRITE_BATCH`：任务写入对未被加锁的节点无条件写 `n.status = row.status`，于是**已解锁**的已裁决节点（典型路径是 F08 改状态置 `locked = true` 后再 `unlockKnowledgePoint`，ADR-035 决定 4）被重跑写回 `draft`。关系侧本来安全（`graph_relations._MERGE` 对任务写入不写 `r.status`，`contrib_manual` 让 `revoke_task` 保留它），仍补回归测试。修法：先算「本次最终状态」——已有的 `approved`/`rejected` 原样保留，其余沿用候选状态；`changed` 与这个最终状态比较，所以内容未变的重跑既不改状态也不加 `revision`（保持幂等）。内容、别名与来源仍按候选更新；只保护 `approved`/`rejected`，`draft`/`low_confidence` 的自动语义不变；加锁节点仍完全不动（F04/ADR-024 决定 4）。ADR-060 的「确认保留」存在 SQLite `review_dismissals`、按 `kp_id` 记，确定性 ID 在重跑间稳定且 `persisting` 不触碰它，永久性不受影响。**产品取舍（需签收）**：重跑**会**改写「已裁决但已解锁」节点的内容与来源，只冻结状态。理由是 `unlock` 的存在就是为了让自动流程重新更新内容（ADR-035）；若要连内容一起冻结，就需要新的图标记，本 ADR 不选。
- **后果**：worker 缺省每小时对全部课程执行一次 `sweep`，`failed` 尝试的残留副本与 `cleanup_pending` 因此能自行收敛；孤儿副本与已提交版本缺副本仍只告警，人工处理归 K10。`getKnowledgePoint` 多一种成功形状，契约生成物必须与真源同步（ADR-004）。没有需要撤销的贡献的失败任务不再空等最多一个锁租约；有工作的清理仍按课程串行。教师对节点/关系的裁决在任务重跑后保持，`draft`/`low_confidence` 仍跟随自动流程。
- **回滚**：四项各自独立提交，可单独 `git revert`。① 撤销 `runner.PublishSweep`/`build_maintenance` 与 `run_loop` 的默认接线、`Settings.PUBLISH_SWEEP_INTERVAL_SECONDS`、`.env.example` 与 `docs/integrations.md` 的对应行、测试；② 撤销 `read_knowledge_point` 的分支、契约的 `KnowledgePointDetailWithoutSource` 与 200 的 `oneOf`、`schemas/contracts.py` 的导出与重新生成的产物、测试；③ 撤销 `graph_relations.task_has_contributions` 与 `cleanup_failed_task` 的前置判断；④ 撤销 `_WRITE_BATCH` 的状态列与 `changed` 计算。四项都无 SQLite/Neo4j DDL 与数据迁移；已写入的数据不回滚（重跑覆盖过的状态按当时的草稿内容为准）。
- **签收**：待 ArvinHan 审阅。**需明确签收**：(a) `sweep` 缺省启用且周期 3600 秒（`PUBLISH_SWEEP_INTERVAL_SECONDS=0` 才关闭）；(b) 契约新增 `KnowledgePointDetailWithoutSource` 与 200 的两种响应形状（不改 `KnowledgePointDetail` 的 `minItems: 1`）；(c) 重跑允许改写「已裁决但已解锁」节点的内容，只冻结 `approved`/`rejected` 状态。

<!-- OPT-01 original adr-072 end -->

<a id="adr-073"></a>

<!-- OPT-01 original adr-073 begin -->
## ADR-073：H10 发布历史与前滚式回滚的教师交互

- **日期**：2026-09-27
- **背景**：G06 已提供发布、历史列表、回滚端点；H09 审核页提示「可以直接发布」，但没有实际入口。H10 需要在发布失败时保留旧标识、草稿修订期间说明学生仍见旧版，并在回滚前明确目标版本。
- **决定**：在 `/courses/:cid/review` 嵌入 `VersionPanel`，不新增路由。先通过 `Course.my_role` 核对教师身份，再读版本列表；按版本号降序展示 `publish` 与 `rollback/source_version`。学生当前可见版本只取 `Course.published_version`；发布或回滚成功后重读课程详情与版本列表，只有刷新后的指针与响应版本一致、且该版本出现在历史中才确认成功。失败、网络结果不明或刷新不一致时保留上次确认的标识；超时、断网或刷新未确认时禁用继续写入直到人工刷新核对。课程教师权限丧失时清除旧历史与操作入口。回滚先选择历史版本，在页内确认目标版本、前滚生成新版本且不改变草稿，再调用后端。切课和卸载作废旧请求。
- **后果**：审核页会额外读取课程详情与版本列表，但无需修改现有契约或 G06 后端。学生页仍按课程发布指针读旧版，教师面板明确说明 `revising` 状态。发布/回滚成功后若刷新异常，界面不猜测新指针，提示重新核对。
- **回滚**：撤销 `api/versions.ts`、`composables/useVersions.ts`、`components/VersionPanel.vue` 与审核页/应用注入接线；不涉及数据库迁移或契约变更。
- **签收**：用户 2026-09-27 确认审核页内嵌、服务端指针为准和回滚前展示目标版本。

<!-- OPT-01 original adr-073 end -->

<a id="adr-075"></a>

<!-- OPT-01 original adr-075 begin -->
## ADR-075：学生掌握标记与推荐的乐观写入、版本绑定与理由展示（I06）

- **编号说明**：ADR-074 由仍在审查中的 PR #295（J10 问答日志）占用；本分支的 `main` 上最大号为 ADR-073，为避免 #295 合入后撞号，本 ADR 直接取 075（原任务约定「当前最大号 +1」，当时最大号即 074）。
- **日期**：2026-09-27
- **背景**：I05 已交付 `GET /recommend`、I02 已交付 `GET/PUT /progress`（有效状态、`own_status`、`inherited_from[]`、`graph_version`），H11 的学生图谱页只读已发布版本。I06 要把「掌握标记」（学生自报事实的写入）与「下一步推荐」（可解释列表）接到该页上，并满足原子清单验收：「失败撤销乐观标记；切课后旧推荐不覆盖；理由与服务分量一致」。写路径的版本绑定出现一处**契约与验收字面表述的冲突**：清单验收条目 5 写「PUT progress 请求带 `graph_version`」，但 `src/contracts/api.v1.yaml` 的 `updateProgress` 请求体是 `ProgressUpdate[]`（`kp_id` + `status`，`additionalProperties: false`），该操作的 `query` 为 `never`，后端 `write_progress` 也没有版本参数——版本由服务端在请求时解析（`specs/learning-path.md` §5「请求事务所见的当前已发布版」）。契约真源是约束，故本 ADR 明确实现口径并把偏差标为**需签收**。
- **决定**：
  1. **乐观标记 + 失败完整回滚，单一在途写入**。`useLearning.setMastery` 先本地写入新状态（画布状态色与按钮立即变化），再 `PUT /progress`（单条 `[{kp_id, status}]`）。成功后以响应重新投影的 `entries` 为准（服务端权威）；网络/超时/4xx/5xx 一律**回滚到写前的服务端已知状态**，只给按错误码固定的文案，绝不回显服务端 `message`。`busyKpId` 非空时新的写入请求直接忽略，页面按它禁用全部掌握按钮：同一节点连点只发一次。
  2. **版本绑定的实现口径（替代「请求带 `graph_version`」的字面做法）**。① 只在 `graphVersion` 非 null 时读写——草稿页、未发布、版本未知时组合式既不读也不写，页面也不渲染可点击入口；② `PUT` 请求体严格按契约只含 `kp_id` 与 `status`，**不自造 `graph_version` 字段或查询参数**（自造字段会被 `additionalProperties: false` 拒绝，未声明的查询参数会被服务端忽略而给出虚假的安全感）；③ 每条响应（`PUT` 的 `graph_version`、`GET /progress` 与 `GET /recommend` 的 `graph_version`）都与显示版本比对，不一致即视为「显示中的图已过期」：丢弃该投影、置 `versionStale`，并请页面重新读图（`onVersionStale`），**不把新版本的投影套到旧图上**；④ 422 `VALIDATION_ERROR` 且 `details.fields[].reason = not_in_published_version`（草稿独有/已删除/他课，或写入期间发布指针变化）→ 回滚乐观状态后重新读进度与推荐，给固定文案「该知识点已不在当前发布版本中，已撤销标记并刷新进度。」；⑤ 版本不一致的重载请求只发一次，直到某次读到的版本与显示版本一致才复位，避免服务端版本始终不收敛时的重载死循环。
  3. **切课隔离沿用 `CourseRequestScope` + 请求序号**（照抄 `useReview`）。读进度、读推荐、写进度三类请求各自带序号并绑定课程作用域；切课后作用域失效且序号前进，课程 A 的迟到响应（推荐或进度）不写入课程 B 的界面。
  4. **推荐理由只展示服务端事实**。`reason` 整句原样渲染；事实行逐条来自 `reason_facts`（`unlock_count`、`importance`、`centrality`、`difficulty`、章名/章秩、`primary_factor`），四类加权分量与 `score` 原样取 `weighted`/`score`。前端**不**用 `factors` 乘权重、**不**重算 `score`、**不**据 `unlock_count` 反推解锁度；只有展示时按 4 位小数舍入。
  5. **判定顺序与不可写态**（`specs/learning-path.md` §4）：401/403 与未发布（404 `GRAPH_NOT_PUBLISHED`）不进入列表状态；已提交版完整性故障（500 `INTERNAL_ERROR`）只提示 `details.request_id`，不回显细节；`V ≠ ∅` 且全部掌握是 200 `state = all_mastered` 的**空态**；其余是 200 `state = recommendations`。本课程教师（`GraphExchange` 视图已经拦截）或学习接口返回 403 `ROLE_FORBIDDEN` 时，掌握标记与推荐区连同按钮一起消失，只给说明文案——掌握标记是学生行为。
  6. **学习接口未注入时页面退回 H11 原状**。`PROGRESS_API_KEY`/`RECOMMEND_API_KEY` 都缺失（例如既有 H11 测试的注入集）时，`useLearning` 不发任何请求、`learningGraph` 原样返回筛选结果，页面不渲染标记与推荐区。这样新增功能不改变既有页面在旧注入下的行为。
  7. **画布状态色集中在图适配层**。`CanvasElementState` 追加 `mastered`/`learning`/`notStarted`/`recommended`，颜色只在 `graph/lifecycle.ts` 的 `buildGraphOptions` 定义一处；`applyLearningStates` 只把服务端投影的掌握状态与推荐集合翻译成状态名（学习状态在前，筛选/选中状态叠加在后），因此测试断言的是「元素的 `states` 来自服务端状态」，而不是硬编码颜色。
- **后果**：掌握标记在弱网下会短暂显示后回滚，但界面与服务端投影始终可解释；发布指针在读或写期间变化时页面会重新读图而不是混算两个版本。`PUT` 不带版本号意味着服务端仍以「请求时的当前发布版」为准，客户端只能**事后**发现版本不一致（响应比对 + 422）——这是契约现状的代价，若要让服务端强制按客户端绑定版本写入，需要先扩展契约（新增版本参数）并与后端同步，另开任务。学习接口未注入时静默退回 H11 原状，若某一注入集只提供其中一个键，功能整体不启用（两个接口缺一不可，推荐依赖进度投影）。
- **回滚**：撤销 `api/progress.ts`、`api/recommend.ts`、`composables/useLearning.ts`、`components/Recommendations.vue` 与 `StudentGraphView.vue`/`main.ts` 的接线，并撤销 `graph/lifecycle.ts` 的四个状态与样式即可；不涉及契约、数据库迁移或后端。
- **签收**：待 ArvinHan 审阅。**需明确签收**：(a) 版本绑定按决定 2 的「响应比对 + 422 重读」实现，而非在 `PUT` 请求体里自造 `graph_version`（契约无此字段）；(b) 学习接口未注入时页面静默退回 H11 原状；(c) 掌握标记的三态按钮（未开始/学习中/已掌握）直接把 `MasteryStatus` 写回，不引入第四种状态或「跳过先修」操作。

<!-- OPT-01 original adr-075 end -->

<a id="adr-076"></a>

<!-- OPT-01 original adr-076 begin -->
## ADR-076：演示模型模式（`LLM_MODE=demo`、`EMBEDDING_MODE=demo`）

- **日期**：2026-09-27
- **背景**：`LLM_MODE=fake` 的缺省输出不含抽取所需结构，上传资料必然「抽取失败的片段过多」；假向量与语义无关，J04 相似度闸门几乎永远拒答。结果是云端与本机都无法在不付费的情况下把教师→学生主线跑通，K05 教师 E2E 自合入起从未真正执行过。
- **决定**：
  1. 新增取值 `LLM_MODE=demo` 与 `EMBEDDING_MODE=demo`；`APP_ENV=production` 下与 `fake` 一样被拒绝。`fake` 行为不变。
  2. 演示模型（`app/services/ai/demo.py`）按 `ModelRequest.purpose` 用确定性规则产出通过真实解析器校验的输出：标题层级、中文定义句、「X 的特点是 P」、先修句式（同一输出内先做环检测），问答从上下文块里选与问题重叠最多的 1～3 句并逐句标注引用，无重叠输出不足证据哨兵。模型 ID 固定 `smartsketch-demo-rules-v1`。
  3. 演示向量为字符 1/2-gram 哈希词袋（每个 gram 分散到 128 维后 L2 归一化），向量空间记为 `real/smartsketch-demo-ngram-v1/<维度>`，与 fake、真实空间互不混用。
  4. 演示模式建议 `QA_SIMILARITY_THRESHOLD=0.58`（实测覆盖问题 ≥ 0.63、无关问题 ≤ 0.54）；代码不按模式改阈值、不绕过闸门，只在 `.env.example`、runbook 与 `scripts/e2e.sh` 里设置。
- **后果**：K05/K06 端到端、K09 示例导入与本地验收可在无付费调用下跑通；演示结果不代表真实模型的抽取质量（赛题指标仍以 K02 真实模型判定为准）。同一 Neo4j 库换模式会被启动门禁拒绝，须用新库或 F14 `scripts/reembed.py`。
- **回滚**：删除 `demo.py`、`factory.py` 及其调用点改回原装配，去掉两个枚举值；无迁移、无契约变更。
- **签收**：ArvinHan 2026-09-27 签收（阈值 0.58 与「演示模式可用于验收演示」两点）。

<!-- OPT-01 original adr-076 end -->

<a id="adr-077"></a>

<!-- OPT-01 original adr-077 begin -->
## ADR-077：质量门禁分档与测试报告判定（K11）

- **日期**：2026-09-27
- **背景**：`scripts/verify.sh` 只覆盖骨架与契约；前后端测试在 CI 各自跑，但「零测试」「已实现模块被静默跳过」不会让门禁变红；集成用例与端到端没有入口。
- **决定**：
  1. `scripts/verify.sh [basic|full|integration]`（或 `VERIFY_MODE`）：`basic` 为现状（CI 骨架任务）；`full` 加 `scripts/verify/backend.sh`、`frontend.sh`；`integration` 再加 `scripts/verify/integration.sh`（一次性 Neo4j 上的 `tests/integration`、F11 图库用例与 K05/K06 端到端）。未知模式退出 2。
  2. 所有测试报告（pytest `--junitxml`、vitest JUnit）经 `scripts/verify/gate.py` 判定：执行数低于下限（零测试）、任何失败或错误、原因未登记在 `scripts/verify/allowed-skips.txt`（按模式）的跳过，都判失败。登记表每行写明原因。
  3. CI 前后端任务改跑 `backend.sh full` / `frontend.sh full`，新增 `Integration and E2E` 任务跑集成档（Docker 起 Neo4j，Playwright Chromium，失败时上传 `.e2e/` 证据）。
  4. 集成档固定 `SMARTSKETCH_SKIP_DOCKER=1`：F01 dev-up（占用开发端口）与 K08 镜像构建在登记表中列为允许跳过，需本机手动运行。
- **后果**：新增的 `pytest.skip`/`it.skip` 若未登记会让门禁变红；CI 多一个约 10–20 分钟的任务。`test_k10.py` 子进程钩子改用与 fixture 相同的 Neo4j 凭据（原硬编码 `x` 只在无认证实例上成立）。
- **回滚**：`verify.sh` 去掉模式分支即回到 basic；CI 恢复原 pytest/vitest 命令并删除 integration 任务。
- **签收**：ArvinHan 2026-09-27 签收（CI 增加集成任务的时长与登记表两条 Docker 跳过）。

<!-- OPT-01 original adr-077 end -->

<a id="adr-078"></a>

<!-- OPT-01 original adr-078 begin -->
## ADR-078：示例课程幂等导入的识别与重试口径（K09）

- **日期**：2026-09-27
- **背景**：K09 要求一键导入演示数据：重跑不重复、只写示例课、失败可重试、不混入真实资料或删除他课。契约没有资料幂等键，再处理只能重新上传（D-16）；worker 队列是全局共享的。
- **决定**：
  1. 清单 `datasets/demo/manifest.json` 固定课程名、教师、学生与资料；资料必须位于清单目录内且 SHA-256 与清单一致，否则在任何写入前拒绝。
  2. 课程按（教师 `demo_teacher`、课程名）识别；同名多于一门时拒绝，交人工处理。成员已存在则跳过。
  3. 资料按内容哈希找该课最新任务：存在且未失败/取消即跳过；失败或取消则重新上传（新资料、新任务）。从不删除资料、课程或他课数据。
  4. 导入脚本只入队并等待 worker 处理，不自己领取任务（全局队列里可能有他课任务）；超时退出 1，提示确认 worker 后重跑。
  5. 全部资料处理完后调用 G05 发布；草稿未变时发布返回已有版本（`unchanged`）。
- **后果**：导入依赖 worker 在运行；失败重试会在该课留下失败的旧资料记录（与教师手动重新上传一致）。
- **回滚**：删除 `scripts/import-demo.py`、`app/services/demo_import.py`、`datasets/demo/`；已导入的示例课需教师在界面上处理（本任务不提供删除）。
- **签收**：ArvinHan 2026-09-27 签收。

<!-- OPT-01 original adr-078 end -->

<a id="adr-079"></a>

<!-- OPT-01 original adr-079 begin -->
## ADR-079：学生自助注册，教师账号仍由命令行开通（部分取代 ADR-013 决定 1）

- **日期**：2026-09-27
- **背景**：ADR-013 规定「没有注册端点」，账号只能用 `scripts/manage-accounts.py` 创建。演示和真实试用时，新学生无法自己上手，只能等管理员逐个开号。用户在前端改版讨论中选定方案「学生自助注册，教师由管理员开」（ArvinHan，2026-09-27，线程回复「A + 1」）。
- **选项**：

  | 选项 | 结论 | 理由 |
  | --- | --- | --- |
  | 学生自助注册，教师仍走命令行 | **采纳** | 学生能自己上手；教师可建课、看全部草稿，开号仍需管理员把关 |
  | 学生自助注册 + 教师凭一次性邀请码注册 | 否决（本轮） | 多一张邀请码表与生成、核销、过期规则；教师数量少，命令行够用 |
  | 保持不开放 | 否决 | 用户明确要注册页 |

- **决定**：
  1. 新增 `POST /api/v1/auth/register`（operationId `register`，`security: []`），请求体 `RegisterRequest {username, password}` 为闭合对象，不接受 `role` 等字段；**只创建账号类型为 `student` 的账号**。
  2. 字段规则沿用 `specs/identity-access.md` §1.1/§1.4：用户名 3～32 位 `[A-Za-z0-9_.-]`，入库前转小写；口令 8～128 字符，argon2id 慢哈希。不合规返回 422 `VALIDATION_ERROR`，`details.fields` 指出字段，不回显取值。
  3. 用户名（转小写后）已存在返回 409，新增错误码 `USERNAME_TAKEN`。这会暴露用户名是否存在；登录接口的防枚举（§1.3）不变，接受注册接口这一处泄露，靠第 5 条限流缓解。
  4. 成功返回 201 与登录相同的 `LoginResponse`，前端直接进入学生首页。注册**不**让学生进入任何课程：入课仍由课程教师按用户名添加（ADR-013 决定 4 不变）。
  5. 限流：每个 API 进程一个滑动窗口，60 秒内最多 60 次注册尝试（成功与失败都计，因为每次都可能付一次慢哈希），超出返回 429 `RATE_LIMITED` 与 `Retry-After`。不按 IP 计数：校园网 NAT 下全班同一出口 IP，按 IP 会挡住整班同时注册。与登录限流一样只是缓解手段。
  6. 教师账号、协作教师、停用、重置口令仍只由命令行管理；前端注册页写明「教师账号由管理员开通」。
- **后果**：
  - 契约：`api.v1.yaml` 新增 `register`、`RegisterRequest`，`ErrorCode` 增加 `USERNAME_TAKEN`；`errors.v1.md`、`docs/architecture.md` 枚举表同步；生成物已重新生成。
  - 规格：`specs/identity-access.md` §1.2「没有注册端点」改为本条，访问矩阵加 `register` 行，「明确不做」中的「开放注册」收窄为「教师自助注册」。
  - 前端：新增 `/register` 页，登录页加入口；三处前端错误码副本加 `USERNAME_TAKEN`。
  - 无数据迁移：沿用 `users` 表。
  - 未做：部署级开关（如关闭自助注册的环境变量）；需要时另立任务。
- **回滚**：删除 `api/auth.py` 的 `register` 路由、`schemas/auth.py` 的 `RegisterRequest`、`services/auth.py` 的 `RegistrationRateLimiter`/`register_student`、`main.py` 一行限流器、`tests/backend/test_adr079_register.py`，撤回契约与生成物、错误码副本、前端注册页和路由；已自助注册的学生账号保留，可用 `manage-accounts.py disable` 停用。
- **签收**：待 ArvinHan 签收（方案已由用户在线程中选定）。

<!-- OPT-01 original adr-079 end -->

<a id="adr-080"></a>

<!-- OPT-01 original adr-080 begin -->
## ADR-080：个人模型凭据与 `LLM_MODE=personal`

- **日期**：2026-10-02
- **背景**：参赛版是教师与学生共用的 Web 应用。用户要求教师、学生各自接入自己的模型 API，不由管理员统一决定模型，也不把教师密钥共享给学生（ArvinHan，2026-10-02）。现有实现里 worker 与问答服务都按进程级环境变量装配一份模型客户端（`workers/runner.py`、`api/chat.py`），`AGENTS.md` §4 规定「配置只能从环境变量读取」、§6 规定「密钥只存个人本地环境」，与该要求冲突。规格：`docs/superpowers/specs/2026-10-02-contest-sprint-design.md`。
- **选项**（任务如何绑定凭据）：

  | 选项 | 结论 | 理由 |
  | --- | --- | --- |
  | 任务级加密快照：建任务时复制所有者当时的地址、模型名与密文 | **采纳** | 改配置不影响已建任务；清除可逐任务作废；worker 重启后从 SQLite 读回，不依赖内存 |
  | 追加式配置版本表，任务引用版本号 | 否决 | 语义等价，但清除要处理多版本残留，表与查询更多 |
  | 任务只绑定配置 ID | 否决 | 改配置会让排队任务静默换模型或换 key |

- **决定**：
  1. 新增运行模式 `LLM_MODE=personal`：进程内没有任何全站大模型客户端。教师任务使用任务快照，学生问答使用本人配置；未配置时上传与提问返回 409 `MODEL_CONFIG_REQUIRED`，不回退到 `demo`、`fake` 或任何全站 key。此模式下不读取 `LLM_*` 的地址、key 与模型名变量。`demo`、`fake`、`live` 的全局装配路径不变；`APP_ENV=production` 允许 `personal` 与 `live`。
  2. 每个用户一份配置（服务地址、模型名、密钥），同一模型名用于抽取与问答，只支持 OpenAI 兼容的 Chat Completions 协议。密钥用 AES-256-GCM 加密存入 SQLite `user_model_configs`，关联数据为所有者的 `user_id`；根密钥来自环境变量 `MODEL_CREDENTIAL_KEY`（32 字节，URL 安全 base64），`personal` 模式下缺失或非法即拒绝启动。读取接口只返回密钥末 4 位；修改服务地址时必须重新提交密钥。
  3. 任务快照 `task_model_bindings` 与资料、任务在同一个 SQLite 事务内写入，内容是所有者当时配置的密文副本。修改配置只影响之后新建的任务。清除配置时，在同一事务里把本人未结束任务的快照密文置空（`revoked`）；这些任务在下一个块或小节的尝试开始前以 `LLM_UNAVAILABLE`、`details.reason = credential_revoked` 终止。快照缺失为 `credential_missing`，无法解密为 `credential_unreadable`。任务进入 `awaiting_review`、`completed`、`failed` 或 `cancelled` 后，worker 把快照密文置空（`terminal`），只留地址、模型名与配置版本号。任务状态机与 SSE 语义不变，不新增重试端点。
  4. 问答按「用户 + 配置版本」缓存各自的调用策略，熔断状态互不影响。`model_calls` 增加 `user_id`，`processing_tasks` 增加 `created_by`；`personal` 模式下 `LLM_DAILY_TOKEN_BUDGET` 按用户统计，`LLM_TASK_TOKEN_BUDGET` 不变。
  5. 用户填写的地址只接受 `https`，不得带凭据、查询串或片段；解析域名后任一地址不是公网地址即拒绝（回环、私网、链路本地含云元数据地址、CGNAT、组播、保留段、IPv6 ULA 与 IPv4 映射地址）。保存、测试与每次建连都执行；连接钉住已校验的 IP，TLS 仍校验原域名；不跟随重定向。`MODEL_ENDPOINT_ALLOW_PRIVATE` 只用于本机假供应商测试，`APP_ENV=production` 下为真即拒绝启动。
  6. 规则调整：`AGENTS.md` §4 改为「基础设施与系统级配置只能从环境变量读取；用户个人模型凭据是唯一例外」，§6 增加同一例外。个人凭据不进响应、日志、`model_calls`、任务 payload、SSE、前端持久存储与仓库。
  7. 新增后端依赖 `cryptography`（锁定版本）。标准库没有认证加密，不自造。
- **后果**：
  - 契约：新增 `/api/v1/me/model-config`（读取、保存、清除）与 `/api/v1/me/model-config/test`；`ErrorCode` 增加 `MODEL_CONFIG_REQUIRED`；上传与问答增加 409 响应；`errors.v1.md` 同步。
  - 数据：迁移 `015_user_model_configs.sql`，两张新表与两个可空新列；历史行的新列为空。
  - 更换 `MODEL_CREDENTIAL_KEY` 会使已保存的配置与未结束任务的快照无法解密，用户需重新填写；本轮不做根密钥轮换工具。
  - 测试连接会向用户的服务发 1 次输出上限为 1 token 的请求，每用户每分钟至多 5 次，不计入 `model_calls`。
  - 未做：多配置收藏、多协议、供应商自动切换、按用户的配额管理界面。
- **回滚**：停 API 与 worker，恢复 `backups/*-before-015.sqlite`（或执行迁移文件内的 `ROLLBACK` 语句），回退相关提交，`LLM_MODE` 改回原值。新列均可空，旧代码可读新库。
- **签收**：ArvinHan 2026-10-02 同意规则调整、任务快照方案与新增 `cryptography`（冲刺规格第 11 节）。

<!-- OPT-01 original adr-080 end -->
