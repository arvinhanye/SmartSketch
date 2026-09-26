# 功能规格：教师审核与图谱发布

- **状态**：DRAFT。「图谱版本与跨库发布协议」一节由 A04 提交，**ADR-012 已签收**（ArvinHan，2026-09-23；修订 1 修复 Codex A04-R01/R02，同日签收）；节点加锁、并发编辑、审核队列排序等仍是桩（见「待细化」）
- **负责人**：产品 / 后端 / 前端共同维护
- **关联任务**：M1-05；A04（版本与发布协议）；实现方 B08、B11、C01、F02、F03、G01～G07、H10、I01、J01
- **底稿**：本文件以 `claude/worktree-contract-conflicts-740adb` `978671e` 的同名草稿桩为底稿（与 `209be9` 同文），保留原有章节与验收编号。A10 导入时以本文件为准，不再合入桩的旧文本。

## 用户故事

作为教师，我能在学生看不到的草稿上修正 AI 生成的图谱，确认无误后发布；发布后再修改时学生仍看旧版本，直到我重新发布。作为学生，我任何时候看到的都是一个完整、已被教师确认过的版本。

## 数据与规则

### 三态流转

| 状态 | 含义 | 学生可见性 |
| --- | --- | --- |
| **草稿**（`draft`） | 从未发布过 | 不可见 |
| **已发布**（`published`） | 草稿的可发布部分与当前发布版一致 | 可见当前发布版 |
| **修订中**（`revising`） | 已发布过，草稿又被修改 | **仍看当前发布版**，教师重新发布后更新 |

```text
草稿 ──发布──→ 已发布 ──教师再次修改──→ 修订中 ──重新发布──→ 已发布
                  ↑                                      │
                  └──── 回滚：以历史版本内容前滚为新版本 ────┘
```

关键不变量：**只要曾经发布过，学生就始终能读到某个完整版本**。「修订中」不得让学生看到半成品，也不得让学生读不到任何东西。

课程状态不单独存储，按 [V7](#v7-课程状态推导) 从修订号推导。

### 节点加锁

**教师手动修改过的节点加锁，后续自动流程不覆盖。** 这是人机协同的核心约束：重新上传资料、重跑抽取、重跑融合，都不得改写加锁节点。加锁是自动流程的边界，不是并发锁；与下文的**课程写锁**（并发互斥）是两回事。

> **F08 落实（ADR-035，2026-09-26）**：锁整个节点（全部字段与来源），不连带关系；任何成功的教师修改都加锁。解锁只能经单独的 `unlockKnowledgePoint` 显式进行，没有过期。两名教师先后编辑同一节点时，后写者的 `expected_revision` 过期 → 409 `REVISION_CONFLICT`，带当前内容，不覆盖。教师新建知识点必须带至少一条已提交的本课程来源。

### 审核队列

列出三类待处理项，支持一键通过 / 拒绝 / 合并：

- 低置信度关系
- 疑似重复知识点
- 孤立知识点

> **F10 落实（ADR-047，2026-09-26）**：合并把被合并节点的入边与出边改接到主节点，同类型同端点去重（主节点原有的关系保留字段，贡献与来源取并集），迁移后的 `PREREQUISITE` 验环，成环 409 `CYCLE_DETECTED`；来源全部迁到主节点；主节点加锁并维护展平的 `merged_from`；可选 `expected_revisions` 过期 409 `REVISION_CONFLICT`。任何失败都不部分提交。

> **F09 落实（ADR-048，2026-09-26）**：删除只清理草稿中的节点、与它相连的全部草稿关系（含关系身份）、来源关联与 `merged_from`；已发布版本的副本与快照不变。不存在、不可见或他课的节点 404；并发删除同一节点恰有一次成功；可选查询参数 `expected_revision` 过期 409 `REVISION_CONFLICT`。

队列不阻塞发布。发布时只有 `low_confidence` 项被排除在快照外（[V3](#v3-发布集合与快照)）；「疑似重复」与「孤立知识点」只提示，不排除、不阻塞。

### 一致性

- 所有修改经后端统一接口写入；每次草稿写入都持有课程写锁（[V4](#v4-草稿写入与课程写锁)）。
- 修改记录写入日志（谁、何时、改了什么）。
- 新增或修改 `PREREQUISITE` 时**实时做环检测**，成环则拒绝并提示环路（AGENTS.md §4、ADR-009）。

## 图谱版本与跨库发布协议（A04 / ADR-012）

> **签收状态：已签收**，ArvinHan，2026-09-23（ADR-012）。依赖本节的实现任务（G01～G07、F02/F03 的版本作用域、C01 的版本表）以本节为准；改动本节须先改 ADR-012。

本节回答 PLAN-D02：版本怎么标识、快照放在哪里、发布与回滚分哪几步、失败怎么补偿，以及读请求绑定哪个版本。SQLite 与 Neo4j 之间没有跨库事务（ADR-002），所以协议只有**一个提交点**：SQLite 中切换发布指针的那个事务。提交点之前的任何失败，学生都看不到。

### V1 术语与标识

| 术语 | 定义 |
| --- | --- |
| `version_id` | 内部版本标识，ULID 字符串。每次发布或回滚**开始时**生成，**永不复用**。Neo4j 作用域、请求绑定、问答日志与缓存键都用它 |
| `version` | 面向用户的整数版本号，按课程独立编号。**只在提交时分配**（`max + 1`），失败的尝试不占号，因此**编号无空洞**。API 路径、`GraphVersion`、`PublishResult`、`Course.published_version`、`GraphExchange.graph_version` 都是它 |
| 草稿 | Neo4j 中 `version_id = "draft"` 的数据。`"draft"` 是保留值，不是 ULID |
| 发布尝试 | `graph_versions` 中尚未到达终态的一行，其 `version_id` 即本次尝试的 ID |
| 发布集合 | 草稿中将进入快照的部分，规则见 V3 |
| 快照 | 发布集合的规范化 JSON，存于 SQLite，是版本内容的**真相** |
| 摘要 | 快照规范化字节的 sha256，格式 `sha256:<64 位小写十六进制>` |
| 发布指针 | `courses.published_version_id`，学生默认读取的版本 |
| 课程写锁 | A06 定义的 `course_locks`（`specs/task-processing.md` §8.5），本协议扩大其持有方（V4） |

### V2 存储布局

**SQLite**

`graph_versions`（表名由 G02 迁移定，字段语义以此为准）：

| 字段 | 说明 |
| --- | --- |
| `version_id` | 主键 |
| `course_id` | 课程 |
| `version` | 提交前为 NULL；`UNIQUE(course_id, version)` |
| `kind` | `publish` / `rollback` |
| `source_version` | 仅回滚：被回滚到的 `version` |
| `state` | `preparing` → `materialized` → `committed`；任一步失败为 `failed` |
| `expires_at` | 尝试租约到期时间，心跳每 `PUBLISH_LEASE_SECONDS / 3` 续约；终态后不再使用 |
| `snapshot_json`、`digest` | 快照与摘要；发布在 P7 写入，回滚在建立尝试时从源版本复制 |
| `node_count`、`edge_count`、`excluded` | 统计；`excluded` 见 V3 |
| `draft_revision` | 建快照时读到的草稿修订号（仅发布） |
| `task_watermark` | 建快照时读到的任务水位（仅发布；A03 §3） |
| `embedding_space` | 本版本知识点向量所在的向量空间（V12）；重新向量化后随之更新 |
| `failure_reason`、`cleanup_pending` | 失败原因；Neo4j 清理未完成时为真 |
| `created_by`、`created_at`、`committed_at` | 审计 |
| `commit_seq` | 提交序号：P11 / R7 在提交事务内从 `commit_sequence` 取号；提交前为 NULL，非空时唯一。同一课程内版本号越大、提交序号越大（ADR-012 修订 3） |

- 部分唯一索引：同一 `course_id` 至多一行 `state ∈ {preparing, materialized}`。这是「同一课程同时只有一个发布或回滚」的唯一机制。
- `failed` 行保留作审计，不参与版本列表；`committed` 行永不删除（MVP 不回收旧版本，见 V8）。

`courses` 增加：

| 字段 | 说明 |
| --- | --- |
| `published_version_id` | 发布指针；从未发布为 NULL |
| `published_version` | 与指针同事务维护的整数版本号，供列表直接读取 |
| `draft_revision` | 草稿修订号，每次草稿写入在持锁后、写 Neo4j 前加 1（V4） |
| `published_from_revision` | 当前发布版对应的草稿修订号；-1 表示「已知与草稿不同」 |

`commit_sequence`（ADR-012 修订 3）：单行表 `(singleton = 1, value)`，建表迁移插入 `(1, 0)`。版本提交（P11、R7）与进度写入（`specs/learning-path.md` §5）只在各自的写事务内执行 `UPDATE commit_sequence SET value = value + 1 WHERE singleton = 1 RETURNING value` 取号；全库一个序列，不分课程。事务回滚则号不被占用。

**Neo4j**

- 知识点、关系、章节都带 `course_id` 与 `version_id`。约束：`(course_id, version_id, kp_id)` 唯一（章节同理）；关系在同一版本内按 `rel_id` 唯一。约束迁移归 F03。
- F03 以 Neo4j 5 的复合唯一约束落实 `KnowledgePoint(course_id, version_id, kp_id)`、`Chapter(course_id, version_id, chapter_id)` 与关系 `(course_id, version_id, rel_id)`；`Chunk(course_id, chunk_id)` 跨版本共享且唯一。DDL 各条可重复执行，失败后先修复冲突数据再重跑，不能自动删库或清除既有约束。
- `kp_id`、`rel_id`、`chapter_id` **跨版本不变**：发布只复制，不改 ID。
- 文本块节点（标签名 `Chunk`，按 ADR-016 已统一）**不带 `version_id`，由所有版本共享**，每个文本块带所属的 `revision_id`。每个版本以自己的 `EVIDENCE` 边从知识点指向文本块；关系的来源以文本块 ID 列表属性保存。
- **资料修订**：`(material_id, 内容哈希, 解析器版本)` 确定一个修订，由此确定性生成 `revision_id`。文本块 ID 由「`revision_id` + 块序号」确定性生成（修订 A06 §8.4 的原公式「文档 ID + 解析器版本 + 块序号」）：同一任务重跑、或同内容同解析器再处理，得到同 ID 同文本；内容或解析器版本变化即新 ID。解析器版本为含分块版本的复合版本（ADR-018），因此分块规则或参数变化也即新 ID。
- **文本块不可变**：一个文本块 ID 的原文与定位一经写入永不改变。写入已存在的 ID 时比对内容哈希，不一致即拒绝写入并报错（只可能是实现缺陷）。
- **文本块删除保护**（修订 A06 §8.6）：失败或取消任务的来源块，只有当其修订不属于任何已到 `awaiting_review` / `completed` 的任务、也不在任何 `committed` 版本的修订列表中时才删除；否则保留。
- 已发布副本**只含快照字段 + 知识点向量 + 作用域字段**，不复制置信度、审核状态、锁、贡献记录（ADR-011 修订 1）等草稿元数据。
- 所有业务查询必须同时以 `course_id` 和 `version_id` 为参数；`version_id = "draft"` 只能出现在教师鉴权通过的路径上（F02 验收）。

### V3 发布集合与快照

**发布集合**：

**可见性前提**（ADR-011 修订 1）：以下各条只考察草稿中**可见**的元素与来源关联，有效任务集合 V 取本课程 T6 提交序号 ≤ 本次任务水位的 `awaiting_review` / `completed` 任务（在 P4 持锁读取的前提下与「当前全部有效任务」相同，此处写明以免实现另取）。未 T6、已失败或待清理任务的贡献一律不计入。

1. 资料修订：本课程中任务已到 `awaiting_review` 或 `completed`、且 T6 提交序号 ≤ 本次任务水位的任务所产生的**全部**资料修订（A03 §3）。水位以外的修订整体不在本版本内。同一资料的旧修订只要仍满足本条就仍在版本内；下线旧修订见「待细化」。
2. 知识点：`status ∈ {draft, approved}`。`low_confidence` 与 `rejected` 排除；被排除节点的 `merged_from` 一并不进入本版本，这些来源在本版本中为 dormant（ADR-012 修订 3）。
3. 关系：`status ∈ {draft, approved}`，且两个端点都在第 2 条的集合内。端点因 `low_confidence` 或 `rejected` 被排除的关系**连带排除**。
4. 章节：发布集合中知识点引用到的章节。
5. 「疑似重复」「孤立知识点」照常纳入（本规格「审核队列」）。

排除计数 `excluded = {low_confidence_nodes, low_confidence_edges, cascaded_edges}` 写入版本行并在 `PublishResult` 返回（B11 加字段）。只删边不会产生新环，排除不影响 DAG 性质。

**校验**（任一不通过 → 409 `PUBLISH_BLOCKED`，`details.reasons` 逐条列出，尝试行记 `failed`）：

| `reasons[].kind` | 条件 |
| --- | --- |
| `cycle` | 发布集合中的 `PREREQUISITE` 成环，附环路（ADR-009 / DAG-11） |
| `dangling_endpoint` | 关系端点在草稿中根本不存在（区别于被排除，属草稿不变量被破坏） |
| `invalid_source_ref` | 来源引用的文本块不存在、不属于本课程，或其 `revision_id` 不在第 1 条的修订集合内 |
| `empty_graph` | 发布集合没有任何知识点 |
| `invalid_lineage` | 谱系违反不变式：来源是本快照的节点、同一来源出现在两个节点的 `merged_from` 中，或节点的 `merged_from` 含其自身（属草稿不变量被破坏）（ADR-012 修订 3） |

`details.reasons` 为非空数组，元素至少包含闭集 `kind`；`cycle` 必须附首尾同节点的 `cycle` ID 链，其余原因可附 `relation_id`、`kp_id`、`chunk_id` 定位。B11 将该结构写入真源。`manual` 条目可有空 `source_refs`，但已有引用必须全部有效。
`cycle` 首尾同 ID 是跨数组元素等值约束，JSON Schema 不负责比较；G04 组装 `PUBLISH_BLOCKED` 前必须验证，契约以 `x-closed-cycle: true` 标记这一服务端不变量。

**快照格式**（`snapshot_format = 1`）：

```json
{
  "snapshot_format": 1,
  "course_id": "c_01",
  "revisions": [{"revision_id": "rev_01", "material_id": "m_01",
                 "content_hash": "sha256:…", "parser_version": "…"}],
  "chapters": [{"chapter_id": "ch_01", "title": "…", "order": 1, "parent_id": null}],
  "nodes": [{"kp_id": "kp_01", "name": "…", "aliases": ["…"], "type": "concept",
             "definition": "…", "difficulty": 0.4, "importance": 0.8,
             "chapter_id": "ch_01", "source_refs": ["chunk_01"],
             "merged_from": ["kp_07"]}],
  "edges": [{"rel_id": "r_01", "type": "PREREQUISITE", "from_id": "kp_01",
             "to_id": "kp_02", "source_refs": ["chunk_02"]}]
}
```

- 只含**学生可见的内容字段**。字段清单以 B11 迁移后的 `KnowledgePoint` / `Relation` / `Chapter` 为准；今后新增学生可见字段必须同时加入快照，并把 `snapshot_format` 加 1。
- **不含**：`status`、`confidence`、锁、`source`（`ai`/`manual`）、修订号、时间戳、向量，以及可由图推导的字段（`level`、统计）。因此教师只点「通过」而内容不变时，摘要不变。
- **例外 `merged_from`**（ADR-012 修订 3）：每个知识点都有，为 `kp_id` 集合，含义是**本版本中归属到该节点的全部合并来源，链已展平**（`a` 并入 `b`、`b` 再并入 `c` 后，`c.merged_from = ["a", "b"]`）。它不是学生可见字段，而是为进度投影（`specs/learning-path.md` §5）随版本保存的元数据，不进入 `KnowledgePoint` wire DTO。草稿中由 F10 合并时维护、F09 删除时丢弃；直接父子关系只记在 F12 审计日志。
- `revisions` 纳入摘要：只新增资料或再处理出新修订、不改图，也会产生新版本，因为问答可检索的范围变了。尚无任何实现，修订 1 直接修订格式 1，`snapshot_format` 不升号。

**规范化与摘要**：UTF-8；对象键按字典序；紧凑分隔符（无空白）；不转义非 ASCII；空值显式写 `null`，不省略键；`revisions`、`chapters`、`nodes`、`edges` 分别按各自 ID 升序（`revisions` 按 `revision_id`）；集合语义的数组（`aliases`、`source_refs`、`merged_from`）去重后升序，空集写 `[]`；数值按存储值原样输出。摘要 = `sha256:` + 规范化字节的 sha256。快照本身就以规范形态存储，读出即可复算摘要。`snapshot_format` 变化会使摘要变化，升级后的首次发布即使内容相同也产生新版本，这是预期行为。

### V4 草稿写入与课程写锁

A06 §8.5 的课程写锁原定只在两处持有：`persisting` 的「Neo4j 写入 + T6」与发布的「建立快照 + 读取水位」。本协议把持有方扩大为**所有草稿写入**（ADR-012 对 ADR-011 决定 6 的修订），并规定发布与回滚何时持锁：

| 持有方 | 持锁区间 | 等锁方式 |
| --- | --- | --- |
| worker `persisting`（含失败清理） | 不变，见 A06 §8.4、§8.5 | 不变：轮询退避，上限由持锁者租约决定 |
| 教师草稿写入（节点/关系编辑、合并、审核通过/拒绝、加锁/解锁） | 取锁 → `draft_revision + 1` → 一个 Neo4j 写事务 → 释放 | 最多等待 `COURSE_LOCK_WAIT_SECONDS`，超时 409 `COURSE_BUSY` |
| 发布 | 仅 P3～P5：读修订号、水位、发布集合与向量 | 同上 |
| 回滚 | 仅 R6：读修订号与草稿摘要 | 同上；超时不失败，按 R6 降级 |

- 修订号在**写 Neo4j 之前**加 1：若 Neo4j 写入失败或进程崩溃，最坏结果是课程被判为 `revising`，下一次发布走幂等路径即可纠正；反方向（改了草稿但修订号没变）不可能发生。
- 持锁期间适用 A06 §8.2 的本地截止规则：持锁者在锁到期前必须完成或放弃 Neo4j 写入。API 侧持锁者沿用 `course_locks` 的同一租约时长与心跳。
- `COURSE_BUSY` 的 `details.holder ∈ {publish, rollback, persisting, edit}`，前端据此提示「正在发布」或「资料入库中」，用户可重试。
- `draft_revision` 是课程级计数，与 B11 的节点级 `expected_revision`（乐观并发）不是一回事，互不替代。

### V5 发布步骤

`POST /api/v1/courses/{cid}/publish`（同步，响应 `PublishResult`）：

| 步骤 | 动作 | 存储 | 失败时 |
| --- | --- | --- | --- |
| P1 | 鉴权：本课程教师（A05） | — | 403 |
| P2 | 生成 `version_id`，插入尝试行 `state=preparing, kind=publish, expires_at=现在+PUBLISH_LEASE_SECONDS`；开始心跳 | SQLite | 部分唯一索引冲突 → 409 `PUBLISH_IN_PROGRESS` |
| P3 | 取课程写锁（有界等待） | SQLite | 超时 → 尝试行 `failed`，409 `COURSE_BUSY` |
| P4 | 持锁读取：`draft_revision` 记为 r；当前最大 T6 提交序号记为任务水位 w；按 V3 读取发布集合，知识点向量读入内存 | SQLite + Neo4j | 读失败 → 释放锁，尝试行 `failed`，5xx |
| P5 | 释放课程写锁 | SQLite | 释放失败无妨，锁到期自动失效 |
| P6 | 按 V3 校验 | 内存 | 409 `PUBLISH_BLOCKED`，尝试行 `failed` |
| P7 | 生成快照与摘要。**摘要等于当前发布版摘要，且当前发布版的 `embedding_space` 等于当前向量空间** → 幂等路径（见下）；摘要相等而空间不等说明 V12 的不变式被破坏，5xx 并告警，不走幂等；否则写入尝试行的 `snapshot_json`、`digest`、`draft_revision=r`、`task_watermark=w`、统计与 `embedding_space` | SQLite | 写失败 → 尝试行 `failed`（写不进去则由清扫收尾），5xx |
| P8 | 物化：在**一个 Neo4j 写事务**内按快照与内存向量创建 `(course_id, version_id)` 下的章节、知识点、关系与 `EVIDENCE` 边。之前先补齐快照修订列表内**全部文本块**的 `Chunk` 节点与当前空间向量，只为缺向量的块调用模型；这些节点跨版本共享、可重复写入，C1 不删除（G08，ADR-066） | Neo4j | C1 |
| P9 | 核对：读回 `(course_id, version_id)` 复算摘要，必须等于 P7；向量数 = 知识点数，且全部属于当前向量空间（V12），维度等于该空间维度；快照修订列表内每个文本块都有 `Chunk` 节点、`revision_id` 与当前空间向量（G08） | Neo4j | C1 |
| P10 | 尝试行 `state=materialized` | SQLite | C1 |
| P11 | **提交点**，一个 SQLite 事务（见下） | SQLite | C1 |
| P12 | 停止心跳，返回 200 `PublishResult{version, published_at, stats, excluded, unchanged:false}` | — | — |

**P11 提交事务**，全部成立才提交，否则整体回滚并转 C1：

1. 尝试行满足 `state = materialized AND expires_at > 现在`，更新为 `committed`，`version = 本课程已提交最大 version + 1`，写 `committed_at`，并从 `commit_sequence` 取号写入 `commit_seq`（ADR-012 修订 3）；
2. 发布指针 CAS：`UPDATE courses SET published_version_id = 本尝试, published_version = 新号, published_from_revision = r WHERE course_id = ? AND published_version_id IS 读取时的旧值`，影响 1 行；
3. T7：`course_id = 本课程 AND stage = awaiting_review AND T6 提交序号 ≤ w` 的任务全部转 `completed`（A03 §3）。

**幂等路径**（P7 摘要未变）：一个 SQLite 事务内删除本尝试行（它从未成为版本）、执行 T7（水位 w）、`published_from_revision = r`，条件为发布指针仍是读取时的值、且尝试行仍为 `preparing`（未被清扫判失败）；条件不成立则整体回滚，按 5xx 返回，教师重试即可；返回 200 `PublishResult{version: 当前版本, unchanged: true}`。不产生版本号，不写 Neo4j。

**C1 补偿**（发布与回滚共用，可重复执行）：

1. 条件更新尝试行：`state ∈ {preparing, materialized}` → `failed`，写 `failure_reason`。影响 0 行说明已被提交或已被清扫处理，C1 到此结束，**不得**删除 Neo4j 数据。
2. 删除 Neo4j 中 `(course_id, 本尝试 version_id)` 的全部节点与关系（不碰共享文本块）。
3. 第 2 步失败时置 `cleanup_pending = true`，由清扫重试。

先改 SQLite 再删 Neo4j，是为了与 P11 的条件互斥：两者都以同一行的条件更新为准，恰有一方成功。**发布指针在 C1 中从不改变，学生继续读旧版本。** 发布失败不改变任何任务状态（A03 §3）。

### V6 回滚步骤

`POST /api/v1/courses/{cid}/versions/{version}/rollback`，以版本 k 的内容**前滚**为新版本：

| 步骤 | 动作 | 失败时 |
| --- | --- | --- |
| R1 | 鉴权：本课程教师 | 403 |
| R2 | 在本课程内查 `version = k AND state = committed` 的行 | 404 `NOT_FOUND`。查询按 `course_id` 限定，他课版本号同样 404，不泄露存在性 |
| R3 | k 的摘要等于当前发布版摘要（两者空间必然都等于当前空间，见 V12）→ 200 `PublishResult{version: 当前版本, unchanged: true}`，不产生版本号。覆盖「回滚到当前版本」与「回滚到内容相同的旧版本」 | — |
| R4 | 插入尝试行 `kind=rollback, source_version=k`，`snapshot_json`、`digest`、`embedding_space` 从 k 复制，`state=preparing`；开始心跳 | 409 `PUBLISH_IN_PROGRESS` |
| R5 | 物化：在一个 Neo4j 写事务内把 `(course_id, k 的 version_id)` 复制到 `(course_id, 本尝试)`，**向量一并复制，不调用模型**；复制前核对 **k 自身记录的** `embedding_space` 等于当前向量空间，随后按 P9 核对并置 `materialized` | 源副本缺失，或 k 的空间不等于当前空间（V12 不变式被破坏）→ C1 + 告警，5xx；**不得**静默重算向量。其他失败 → C1 |
| R6 | 取课程写锁（有界等待），读 `draft_revision` 记为 r，按 V3 复算草稿发布集合的摘要 d，释放锁 | 等锁超时或读失败**不使回滚失败**：按 d 未知处理 |
| R7 | 提交点：与 P11 的第 1、2 条相同（含取号写 `commit_seq`）；`published_from_revision = (d 等于新版本摘要 ? r : -1)`；**不执行 T7**（A03 §3：回滚不改变任务状态） | C1 |

- 回滚**不修改草稿**。回滚后若草稿与新版本不同，课程为 `revising`，教师下次发布的是自己的草稿。
- 新版本在列表中显示为「v(n+1)，回滚自 vk」（`GraphVersion.kind`、`source_version`，B11 加字段）。

### V7 课程状态推导

| 条件 | `CourseStatus` |
| --- | --- |
| `published_version_id IS NULL` | `draft` |
| `draft_revision = published_from_revision` | `published` |
| 其余 | `revising` |

三个字段都在 SQLite，推导不需要访问 Neo4j。实现可以缓存结果，但不得把 `status` 作为独立真相另行写入。

### V8 读取绑定

- **学生请求**（图谱、推荐、问答）在请求开始时**只读一次**发布指针，得到 `(version_id, version)` 及该版本的修订列表（版本不可变，修订列表可按 `version_id` 缓存）。此后所有 Neo4j 查询、引用解析、缓存键都用这个 `version_id`，请求途中不再读指针；响应带回 `graph_version`。实现集中在 G07 的版本解析器，图谱、推荐、问答共用。
- **从未发布**：学生请求返回 404 `GRAPH_NOT_PUBLISHED`，不是空图谱。
- **`?version=n`**：教师与学生都可以读取本课程任一 `committed` 版本；n 不存在、未提交或属他课 → 404 `NOT_FOUND`。省略时教师读草稿，学生读发布指针。**草稿只有教师能读。**
- **长请求**：MVP 不回收任何 `committed` 版本，请求绑定的版本在处理期间不会消失。将来引入回收时，保留期必须长于最长请求时长，且不得回收当前指针指向的版本；这是回收功能的前置条件，须另立 ADR。
- **向量检索**：
  - 知识点向量随版本复制，查询后按 `course_id` 与 `version_id` 过滤；
  - 文本块向量共享，在发布 P8 补齐（G08，回滚不补，源版本发布时已补齐），查询后按 `course_id` 过滤，并只保留 `revision_id` 属于该版本修订列表的文本块。不按 `material_id` 过滤：同一资料可能有版本之外的新修订（Codex A04-R01）；
  - 查询向量按当前向量空间计算；运行时只存在一个空间（V12）；
  - Neo4j 向量索引做不到先过滤再检索，因此采用「多取再过滤」，取多少由 J01 实测召回后确定。
- **跨版本对应**：`kp_id`、`rel_id` 跨版本不变。进度如何在版本间对应、节点删除或改名后如何处理，归 A08；问答日志记录 `version_id`，引用撤回协议归 A09。

### V9 崩溃恢复与清扫

清扫并入 worker 的周期回收步骤（A06 §8.6），按课程逐个处理，不跨课程批量删除：

1. `state ∈ {preparing, materialized} AND expires_at < 现在` 的尝试行执行 C1。与 P11 的互斥由 C1 第 1 步保证。
2. `cleanup_pending = true` 的行重试 C1 第 2 步，成功后清除标记。
3. Neo4j 中 `version_id ≠ "draft"`、而 SQLite 对应行为 `failed` 的数据，执行 C1 第 2 步。
4. Neo4j 中找不到任何对应 SQLite 行的 `version_id`：**只告警，不自动删除**。这只会在 SQLite 从较早备份恢复后出现，需要人工确认两库的恢复时间点（K10）。
5. `committed` 行在 Neo4j 缺副本（例如 Neo4j 从较早备份恢复）：告警。若它是当前指针，学生读请求返回 5xx，**不得回退到草稿或其他版本**。从 `snapshot_json` 重建副本需要重算知识点向量，重建流程归 K10。

### V10 与其他任务的接口

| 对象 | 本协议的要求 | 去向 |
| --- | --- | --- |
| A03 任务生命周期（PR #5，ADR-010） | 发布持锁读取任务水位，并在 P11 与幂等路径执行 T7；回滚不执行 T7；发布失败不改任务状态 | 与 A03 §3 一致，无需改 A03 |
| A06 课程写锁（PR #6，ADR-011） | 持有方扩大到所有草稿写入；API 侧持锁者有界等待 | ADR-012 修订 ADR-011 决定 6；`specs/task-processing.md` §8.5 与 ADR-011 引言已加注指向 ADR-012 |
| B08 公共错误码 | 新增 `PUBLISH_IN_PROGRESS`（409，同课程已有发布或回滚在进行）与 `COURSE_BUSY`（409，课程写锁有界等待超时，`details.holder`） | B08 已写入 `api.v1.yaml` 并重新生成 |
| B11 图谱与版本契约 | `PublishResult` 加 `unchanged`、`excluded`；`GraphVersion` 加 `kind`、`source_version`；回滚端点补 409 响应；`PUBLISH_BLOCKED` 的 `details.reasons` 结构（V3 表）；快照字段清单与 DTO 对齐 | B11 |
| A07 配置 | `PUBLISH_LEASE_SECONDS`（整数 ≥ 15，默认 60）、`COURSE_LOCK_WAIT_SECONDS`（整数 ≥ 0，默认 5）；非法值拒绝启动 | 登记到 `.env.example` 与 `docs/integrations.md` |
| A08 / A09 | `kp_id` 跨版本稳定；请求绑定单一 `version_id` | 进度与引用的跨版本规则 |
| A10 | 文本块标签名；本文件替换 `740adb`/`209be9` 的桩 | 导入批次 |
| K10 备份恢复 | 两库恢复时间点对齐；按快照重建缺失副本 | K10 |
| G02 | 原计划的 `preparing/ready` 两态改为本节的 `preparing/materialized/committed/failed` | G02 |
| A06 来源块（ADR-011） | 块 ID 改由 `revision_id` + 块序号生成；失败/取消任务的来源块按 V2 删除保护保留 | 修订 1 修订 ADR-011 决定 5、7 的对应部分；`specs/task-processing.md` §8.4 `parsing` 行与 §8.6 已改并加注 |
| A07 向量空间 | 换空间按 V12 离线重新向量化，不产生新内容版本 | `docs/integrations.md` 两处已改 |
| A08 进度继承（ADR-014 修订 1 决定 9、10） | 快照节点的 `merged_from` 与共享序列 `commit_sequence`：B11 在 `PUBLISH_BLOCKED` 加 `invalid_lineage`，不给 `KnowledgePoint` 加 `merged_from`；F10/F09 维护草稿谱系，F12 记直接父子；G01 快照、摘要与校验；G02 `commit_seq`；G03 P8/P9 含 `merged_from`；G04/G06 取号；I01 `write_seq`；I02/I05 按 `specs/learning-path.md` §5 | ADR-012 修订 3（2026-09-24 签收） |
| B06 / D09 / D10 / E07 / F03 | B06 启动门禁；D09/D10 按修订生成块 ID 并检查不可变；E07 按「空间标识 + 文本哈希」缓存向量；F03 允许新旧空间属性与索引并存，写入向量时核对空间标识（修订 2） | 各任务实现 |

### V11 验收（PUB-n）

独立编号，不占用下方主验收序号。括号内为落地测试的任务。

- 成功路径
  - **PUB-1**（G04）首次发布：草稿有 3 个 `approved` 知识点、2 条边 → 200，`version = 1`，`unchanged = false`；学生读到这 3 个点；`Course.status = published`；Neo4j 中该 `version_id` 下恰有 3 个点、2 条边。
  - **PUB-2**（G04）修订后重新发布：v1 已发布，教师改一个定义 → 状态 `revising`，学生仍读 v1；发布 → `version = 2`，学生读 v2，v1 行与 Neo4j 副本仍在。
  - **PUB-3**（G06）回滚前滚：已有 v1～v5，指针在 v5，回滚到 v3 → 新版本 `version = 6`，内容与 v3 相同，`kind = rollback`，`source_version = 3`；学生读 v6；v1～v5 不变。
  - **PUB-4**（G04）T7：发布成功后，水位以内的 `awaiting_review` 任务为 `completed`，水位以外的不变（与 A03 TASK-2、TASK-22 一致）。
- 边界路径
  - **PUB-5**（G04）内容未变再发布 → 200，`unchanged = true`，`version` 为当前号；不新增版本行，不写 Neo4j；`revising` 变回 `published`。
  - **PUB-6**（G04）教师只把一个 `draft` 项改为 `approved`、内容不变 → 摘要不变，走 PUB-5。
  - **PUB-7**（G06）回滚到当前版本，或回滚到与当前版本摘要相同的旧版本 → 200，`unchanged = true`，不产生版本号。
  - **PUB-8**（G01）排除：草稿含 1 个 `low_confidence` 点 X 和 1 条 `low_confidence` 边，X 另连 2 条 `approved` 边 → 快照不含 X 与这 3 条边；`excluded = {low_confidence_nodes: 1, low_confidence_edges: 1, cascaded_edges: 2}`。
  - **PUB-9**（G01）「疑似重复」与「孤立知识点」照常进入快照，不阻塞发布。
  - **PUB-10**（G01）规范化：同一图以不同插入顺序、不同 `aliases` 顺序构造，摘要相同；改任一学生可见字段，摘要不同；只改 `confidence` 或 `status`（不跨越排除边界），摘要不变。
  - **PUB-11**（G01）只新增一份资料（任务已到 `awaiting_review`）而不改图 → 摘要不同，发布产生新版本。
  - **PUB-12**（G04）版本号无空洞：v1 已发布，一次发布在 P8 失败，下一次成功 → 新版本为 2。
  - **PUB-13**（G07）请求绑定：学生推荐请求已解析到 v1，此时 v2 提交 → 该请求内所有查询仍用 v1 的 `version_id`；下一次请求读到 v2。
  - **PUB-14**（F07、G07）学生 `?version=1`（v1 已提交、指针在 v2）→ 200；学生读草稿的任何方式 → 拒绝；`?version=99` → 404 `NOT_FOUND`。
  - **PUB-15**（G06）回滚不动草稿：草稿有未发布修改时回滚 → 草稿不变，状态 `revising`；草稿与新版本内容相同时回滚 → 状态 `published`。
  - **PUB-16**（G06）R6 等锁超时 → 回滚照常成功，状态为 `revising`；随后发布走幂等路径纠正为 `published`（草稿确与新版本相同时）。
  - **PUB-17**（J01）问答检索 v1 时，v1 之后才上传的资料的文本块不进入候选；知识点向量只命中 v1 副本。
  - **PUB-28**（D10、J01）v1 发布后同一资料换内容再处理，新任务到 `awaiting_review`、v2 未发布 → v1 检索不到新修订的任何文本块；v1 引用的旧文本块原文与定位不变（Codex A04-R01 回归）。
  - **PUB-29**（D10、J01）同一资料内容不变、解析器版本升级后再处理 → 产生新修订与新块 ID；v1 检索结果不变。
  - **PUB-30**（D10）同内容同解析器再处理 → 块 ID 与原文完全相同，不新增文本块；向已存在的块 ID 写入不同内容 → 拒绝并报错。
- 失败路径
  - **PUB-18**（G05）在 P7、P8、P9、P10、P11 分别注入失败 → 每次都满足：发布指针不变，学生仍读旧版本；Neo4j 中没有该尝试的 `version_id` 残留（或 `cleanup_pending = true` 且清扫后没有）；尝试行为 `failed`；任务状态不变。
  - **PUB-19**（G05）进程在 P8 之后、P11 之前崩溃 → 尝试租约到期后清扫执行 C1；指针不变；此后可再次发布。
  - **PUB-20**（G05）P11 与清扫竞争：尝试租约刚过期时同时执行 P11 与清扫 → 恰有一方成功；若 P11 成功，副本不被删除；若清扫成功，P11 回滚、指针不变。
  - **PUB-21**（G04）并发发布：同一课程两个发布同时发起 → 一个成功，另一个 409 `PUBLISH_IN_PROGRESS`；发布与回滚并发同理。
  - **PUB-22**（F08、G04）发布 P3～P5 持锁期间教师编辑 → 编辑等待；超过 `COURSE_LOCK_WAIT_SECONDS` 返回 409 `COURSE_BUSY`，`details.holder = publish`；P5 之后（物化期间）编辑立即成功，且不进入本次快照。
  - **PUB-23**（G01、G04）发布集合含 `PREREQUISITE` 环 → 409 `PUBLISH_BLOCKED`，`details.reasons` 含 `cycle` 与环路；不产生版本（与 DAG-11 一致）。
  - **PUB-35**（G04、F02）发布集合排除不可见贡献：草稿中有任务 A 的内容，A 在 T6 前崩溃（或已失败、`cleanup_pending = true`）→ 快照不含 A 独有的节点、边与来源关联；与已提交任务共享的元素照常纳入，但只带可见的来源。
  - **PUB-24**（G01）来源引用指向他课文本块，或所属修订不在本次修订集合内的文本块 → 409 `PUBLISH_BLOCKED`，`invalid_source_ref`；发布集合为空 → `empty_graph`。
  - **PUB-25**（G06）回滚到不存在的版本、`failed` 尝试或他课版本号 → 404 `NOT_FOUND`，无任何写入。
  - **PUB-26**（G06）回滚源版本的 Neo4j 副本缺失 → 回滚失败并告警；不调用向量模型，指针不变。
  - **PUB-27**（F02）任一学生读路径的 Cypher 缺少 `version_id` 参数，或以 `"draft"` 作参数 → 仓储层拒绝执行。
  - **PUB-31**（C09、D11）处理同一修订的另一任务失败或取消 → v1 固定的文本块不被删除；修订未被任何进入审核的任务或已提交版本使用时才删除。
  - **PUB-32**（B06 API 启动门禁；C09 worker 入口复用；离线命令归后续重新向量化任务）`EMBEDDING_MODEL` 或 `EMBEDDING_DIMENSIONS` 改变而未重新向量化 → API 与 worker 均拒绝启动，并指出记录空间、配置空间与需运行的离线重新向量化操作（Codex A04-R02 回归前半）。
  - **PUB-33**（E07、F03、G04、G06）M1 下发布 v1、v2 后重新向量化到 M2 → 所有版本行 `embedding_space = M2`；内容未变再发布走幂等；回滚到 v1 成功且不调用模型；用 M2 查询能检索到 v1、v2 的结果（Codex A04-R02 回归后半）。
  - **PUB-34**（E07、F03）重新向量化中途失败（向量调用失败或 Neo4j 写失败）→ 当前空间仍为 M1，旧索引与旧向量完好，用 M1 配置可正常启动与检索；重新运行复用已算好的向量并完成切换。
  - **PUB-36**（E07、F03、C09）中断任务跨切换接管（Codex FIX-R02 回归）：任务 A 在 `extracting` 中断、租约已过期，已写入 20 个文本块；另有失败任务 B 尚未回收的 5 个块，以及 `persisting` 崩溃留下的不可见草稿知识点 → 停机重新向量化到 M2 后，这些块与节点全部有 M2 向量；切换后 A 被接管，全程只按 M2 计算与写入，不产生 M1 向量；A 提交后，用 M2 检索能命中它的全部文本块。
  - **PUB-37**（E07、F03）核对按存量：人为让一个文本块在第 3 步后仍缺 M2 向量（或维度不符）→ 第 4 步失败，不切换，当前空间仍为 M1；补算后重跑通过。
  - **PUB-38**（E07、F03）同维度换模型：M1、M2 维度相同 → 切换后同一段文字不命中 M1 的缓存条目，按 M2 重算；带 M1 空间标识的向量写入被拒绝，即使维度相同。
  - **PUB-39**（F03、E07）迁移写入与运行时写入分开核对（Codex FIX-R03 回归）：当前空间 M1、迁移目标 M2 → 命令在迁移上下文中写入带 M2 标识的向量到 M2 属性成功，M1 的属性与索引不变；同一时刻经运行时写入路径写带 M2 标识的向量被拒绝（当前空间仍为 M1）；在迁移上下文中写带 M1 标识的向量到 M2 属性被拒绝；第 5 步提交后，用原迁移上下文再写入被拒绝。

### V12 向量空间切换（重新向量化）

> 修订 1 新增（Codex A04-R02）。**向量空间** = `EMBEDDING_MODEL` + `EMBEDDING_DIMENSIONS`（A07「模型版本与向量空间」）。向量是内容的派生数据，不在摘要内；重算向量不改变任何版本的内容，也不产生新版本。
> 修订 2（Codex FIX-R02，ADR-012 修订 2）：迁移目标改为 Neo4j 实际存量并按存量核对；空间标识随向量写入缓存与中间产物。

- **单一空间不变式**：运行时只有一个当前向量空间。Neo4j 中**实际存储**的全部文本块（不论所属任务的状态）、全部草稿知识点（含尚未可见或已不可见的，ADR-011 修订 1）与全部 `committed` 版本的知识点副本，其向量都在这个空间里；缓存与中间产物中的向量只在带当前空间标识时才可使用（见下「空间标识随向量走」）。SQLite 记录当前空间（单行），版本行记录 `embedding_space`。
- **启动门禁**（B06 提供共享检查、API 在 lifespan 调用；C09 worker 入口须调用）：API 与 worker 启动时比对配置空间与记录空间。不一致 → 拒绝启动，指出两边的值并提示运行重新向量化命令；尚无记录（首次启动）→ 写入配置空间。运行时不切换空间。换空间用离线命令 `scripts/reembed.py`（F14，实现约定见 ADR-038）。
- **重新向量化命令**（离线）：
  1. 前置条件同 A06 §8.7：没有未过期的任务租约、课程写锁或发布尝试，先停 API 与 worker；执行前备份 SQLite（`VACUUM INTO` + `integrity_check`）与 Neo4j（K10 流程）。
  2. 为新空间建独立的向量属性与索引；**切换前不改动旧空间的属性与索引**。属性与索引的命名由 F03/E07 定，必须能与旧空间并存。
  3. 在**迁移上下文**中（见下「空间标识随向量走」，修订 2 补注）按新空间计算并写入 Neo4j 的**实际存量**：全部文本块（包括失败、取消任务尚未回收的块，以及中断任务已写入的块）、全部草稿知识点节点（不论可见性）、全部 `committed` 版本的知识点副本。目标集合按存量枚举，**不**从任务状态推导（修订 2：原按「已到审核或完成的任务所产生的修订」推导，漏掉了中断与失败任务留下的块）。按文本哈希去重，同一段文字只算一次；已写入的向量在重跑时复用。调用记入 `model_calls`，不计入预算（A07）。
  4. 核对按 Neo4j 实际存量进行，不从任务状态推导：三类节点中缺新空间向量、或维度不等于新空间维度的数量都为 0，且复查的存量总数与第 3 步开始时一致（停机期间不应有写入）。任一不满足即失败，不进入第 5 步。
  5. 一个 SQLite 事务内把当前空间改为新空间，并把全部 `committed` 版本行的 `embedding_space` 改为新空间。**这是切换的唯一提交点。**
  6. 删除旧空间的索引与属性，并清除 E07 向量缓存中旧空间的条目；失败可重试，不影响新空间（残留的旧空间缓存按下条规则不会被使用）。
  7. 第 5 步之前任何失败：记录空间仍是旧空间，用旧配置可照常启动；修正后重新运行。
- **空间标识随向量走**（修订 2）：E07 的向量缓存键为「空间标识 + 文本哈希」，只以文本哈希作键会在切换后命中旧空间的向量。保存在 Neo4j 节点之外的向量（缓存、任务中间产物）都带空间标识，读取时与当前空间不符即丢弃、按当前空间重算，不得写入 Neo4j。F 组写入向量时必须同时给出空间标识，并按写入上下文核对（维度相同的两个模型只比对维度无法区分，因此不能只核对维度）。由此，中断任务在切换后被接管时不会写回旧空间的向量；它已写入的文本块已在第 3 步迁移，重跑时按块 ID 复用。
  - **运行时写入**（API 与 worker 的全部写入）：空间标识必须等于 SQLite 记录的当前空间，否则拒绝并指出两边的值。运行时写入路径不接受任何其他空间，也不提供绕过参数。
  - **迁移写入**（只用于重新向量化命令第 3 步；修订 2 补注，Codex FIX-R03）：命令在第 1 步前置条件满足后建立迁移上下文，固定本次的目标空间（配置中的新空间）；此时 SQLite 记录的当前空间仍是旧空间。迁移写入只写目标空间的向量属性与索引，向量的空间标识必须等于目标空间，否则拒绝；不得写入或改动旧空间的属性与索引（第 6 步删除除外）。迁移上下文只存在于命令进程内，API 与 worker 无法取得；第 5 步提交或命令退出后即失效。
  - F03 向量属性/索引名称以空间标识 SHA-256 前 16 个十六进制字符派生，属性为 `embedding_<suffix>`，索引分别为 `chunk_embedding_<suffix>`、`kp_embedding_<suffix>`；新旧空间命名不相同。运行时写入每次读取 SQLite 当前空间，迁移上下文每次写入复查当前空间仍为建立时的旧空间；目标空间切换后旧上下文失效。向量维度必须等于空间声明维度。
- **与发布、回滚的关系**：P7 幂等路径与 R3 只在「摘要相等且空间相同」时成立；P9 与 R5 核对的都是版本自己的 `embedding_space` 与当前空间。启动门禁保证这些条件在正常运行中恒成立；一旦不成立即视为不变式被破坏，按 5xx 告警处理，不静默拒绝回滚，也不走幂等返回。

## 验收条件

### 成功路径

1. 草稿 → 已发布：学生可读该版本，内容与教师发布时一致（PUB-1）。
2. 已发布 → 教师修改 → 修订中：**学生仍读到上一发布版本**，读不到修改内容（PUB-2）。
3. 修订中 → 重新发布：学生读到新版本，**旧快照仍然保留**（PUB-2）。
4. 回滚到任一历史版本后，学生读到该版本的内容；回滚以前滚方式产生新版本号（PUB-3）。
5. 教师手动改过的节点被加锁；重跑抽取或融合后，该节点内容不变。
6. 审核队列能列出低置信度关系、疑似重复、孤立节点三类，且通过/拒绝/合并后队列相应更新。

### 边界路径

7. 课程从未发布过，学生请求 → 返回 404 `GRAPH_NOT_PUBLISHED`。**不是 500，不是空图谱**：空图谱会被前端渲染成「这门课没有知识点」，语义完全不同。
8. 审核队列为空 → 可以直接发布，不得强制要求处理项；队列不空也可以发布，`low_confidence` 项不进入快照（PUB-8、PUB-9）。
9. 回滚到当前正在生效的版本 → 幂等，200 + `unchanged: true`，不产生版本号（PUB-7）。
10. 两名教师同时编辑同一节点 → 冲突策略见「待细化」；**至少不得静默覆盖**，后写者必须知道自己覆盖了什么。
11. 加锁节点在教师**主动解锁**后可被自动流程更新；解锁必须是显式动作。
12. 发布一个与当前发布版完全相同的图谱 → 幂等，200 + `unchanged: true`，不产生新快照（PUB-5）。

### 失败路径

13. 学生调用教师端的编辑或发布接口 → 拒绝，返回明确错误码。
14. 发布时图谱含 `PREREQUISITE` 环 → **拒绝发布**并指出环上的节点/关系；不得发布出一个有环的版本（PUB-23）。
15. 跨课程 `course_id`（教师尝试编辑非自己课程的节点）→ 拒绝。
16. 快照写入失败 → **整个发布失败**，发布指针不变；不得停在「已发布但无快照」的半状态（PUB-18）。
17. 物化或核对中途失败 → Neo4j 中不留下该尝试的数据，失败留下可重试的记录（PUB-18、PUB-19，ADR-002）。
18. 回滚到不存在的版本 → 404 并指出（PUB-25）。

## 待细化

- ~~快照的存储形态~~：已由 A04 定为「SQLite 规范化快照为真相 + Neo4j 按版本物化副本」，全量保存、MVP 不回收（V2、V8，ADR-012）。
- ~~回滚是否产生新版本号~~：前滚，产生新号；回滚到当前版本幂等（V6）。
- **下线旧资料修订**：资料换内容再处理后，旧修订只要仍在发布集合第 1 条的范围内，新旧两份原文都可被检索。若需要让教师下线旧修订（及引用它的来源），须另定操作与规则，归 C06/C07。
- ~~**加锁的粒度**~~：整个节点（全部字段与来源），不连带关系（ADR-035 决定 3）。
- ~~**解锁方式**~~：教师显式解锁，单独接口，无过期策略（ADR-035 决定 4）。
- ~~**并发编辑冲突策略**~~：B11/F08 的 `expected_revision`（节点级乐观锁），过期 → 409 `REVISION_CONFLICT` 并返回当前内容（ADR-035 决定 2）。与 V4 的课程写锁互补：写锁只保证单次写入与发布互斥，不解决两名教师先后覆盖同一字段。
- **「修订中」是否允许多个并存**：多名教师各自修订同一课程时的语义。当前模型只有一份草稿。
- **审核队列的排序与分页**：按置信度、按章节还是按类型。
- **低置信度阈值**：`specs/course-knowledge-graph.md` 也把它列为待细化，两处需同批定稿。
- ~~**manual 条目是否必须有来源**~~：教师新建知识点必须带至少一条来源（ADR-035 决定 5）；V3 仍只校验已有引用有效。
- **旧版本回收**：MVP 不做；将来要做须满足 V8 的前置条件并另立 ADR。
- **API 路径与 DTO**：以 `src/contracts/api.v1.yaml` 为准（ADR-004）；本节新增字段与错误码按 V10 交给 B08/B11。
