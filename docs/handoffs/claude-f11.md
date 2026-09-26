# Claude 交接：F11 审核队列和单项处理

- **任务**：F11（依赖 F10），issue #103
- **分支**：`claude/project-thread-bd1f83`，base `main@a7d8075`
- **决策**：ADR-060（待 ArvinHan 审阅）；SQLite 迁移号 013 由协调者预分配

## 1. 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/graph/review.py` | 三栏分类 `classify`（纯函数）、键集游标 `encode_cursor`/`decode_cursor`/`page`、`read_queue`、单项处理 `resolve_relation`/`resolve_duplicate`/`resolve_isolated` |
| `src/backend/app/api/review.py` | `GET /courses/{cid}/review`（`getReviewQueue`，`kind`/`cursor`/`limit`）与 `POST /courses/{cid}/review/actions`（`resolveReviewItem`），逐字段校验请求体 |
| `tests/backend/test_f11.py` | 17 个无服务器用例（分类、排序、游标、分页稳定、迁移回滚、记录唯一性）+ 23 个真实 Neo4j + SQLite 用例（经 API） |
| 扩围 `src/backend/app/repositories/review.py` | SQLite `review_dismissals` 读写；事务内 Cypher：`read_relation`、`set_relation_status`、`read_isolation`、`reject_node` |
| 扩围 `src/backend/migrations/013_review_dismissals.sql` | 「不是重复」「确认保留」记录表，文件头带 `ROLLBACK` 行 |
| 扩围 `api/graph_nodes.py` | `_run` 增加「返回字典即原样作为响应体」一个分支，供审核动作复用错误映射 |
| 扩围 `main.py`、`schemas/contracts.py` | 注册路由；导出 `ReviewActionResult`、`ReviewItemKind`、`ReviewQueue` |
| 扩围契约 | `getReviewQueue` 参数与 422；`ReviewQueue` 增 `totals`、`next_cursors`；`SuspectedDuplicate`（一对、必填 `reason`）；新增 `resolveReviewItem`、`ReviewAction`（按 `item` 区分的三种动作）、`ReviewActionResult`、`ReviewItemKind`、`ReviewCounts`；`errors.v1.md` 的 `NOT_FOUND` 措辞；`gen-contracts.sh` 重新生成三份生成物 |
| 扩围文档 | `docs/decisions.md` ADR-060；`specs/teacher-review-publish.md`「审核队列」F11 落实、待细化「排序与分页」划掉、验收 6 标注；`docs/tasks.md` F11 记录 |

## 2. 行为要点

1. 队列不存储，每次按 V 从草稿实时计算，再扣除 SQLite 中的教师处理记录。
2. 三栏：低置信度关系（`low_confidence`、两端未拒绝）；疑似重复（E08 名称归一 + 已存别名，`same_key`/`alias` 的 `similarity` 为 1，`containment` 为有效字符比）；孤立知识点（发布后没有一条边的未拒绝节点：被拒绝的边、通往已拒绝节点的边不算）。
3. 排序固定，键集分页：处理掉已看过的条目后翻页不漏不重。游标与 `kind` 必须成对，否则 422。
4. 关系 `approve`/`reject` 与孤立节点 `reject` 是图写入：课程写锁 → 一个写事务（守卫锁 → 读 → 仍在队列 → `draft_revision + 1` → 条件写）。「不是重复」「确认保留」只写 SQLite，不取锁、不加草稿修订号。疑似重复 `merge` 直接调 F10 `merge_nodes`。
5. 已不在队列 → 404；同一动作已生效 → 200 `changed = false`，不写入。响应带处理后的 `totals`。

## 3. 验证

`S=/tmp/claude-0/-home-user-SmartSketch/3b257340-ef57-5b32-bdaf-42a0ecaa4e10/scratchpad`：`$S/venv` 为 `pip install -e "src/backend[dev]"` 加契约工具链（版本同 `src/contracts/toolchain.txt`），`$S/node_modules` 为 `openapi-typescript@7.4.4`。Neo4j 为本地 `docker run neo4j:5.26-community`。`N="SMARTSKETCH_TEST_NEO4J_URI=bolt://127.0.0.1:7687 SMARTSKETCH_TEST_NEO4J_USER=neo4j SMARTSKETCH_TEST_NEO4J_PASSWORD=testpassword"`。

| 步骤 | 命令（在 `src/backend` 下运行 pytest） | 结果 |
| --- | --- | --- |
| F11 | `$N python -m pytest ../../tests/backend/test_f11.py -q` | 40 passed |
| 无真库 | `python -m pytest ../../tests/backend/test_f11.py -q` | 17 passed, 23 skipped |
| 后端 + 契约 | `$N python -m pytest ../../tests/backend ../../tests/contracts -q` | 3433 passed |
| 集成全量 | `$N python -m pytest ../../tests/integration -q` | 336 passed、3 skipped、2 failed：`test_k08.py::test_images_build`（本机 Docker 构建镜像，与本任务无关）；`test_k10.py::test_an_unfenced_write_during_the_backup_fails_it[neo4j]`（用例的钩子写死密码 `x`，本机容器密码不同，与本任务无关） |
| 契约生成物 | `./scripts/gen-contracts.sh --check` | 生成物与真源一致 |
| 门禁 | `./scripts/verify.sh` | exit 0 |
| 空白 | `git diff --check` | 无输出 |

### 反向篡改（`$S/tamper.py`，每处改完跑 `test_f11.py`，再原样还原）

20 处中 19 处检出：包括端点已拒绝的关系仍入列、关系排序忽略置信度、忽略已存别名、已拒绝节点参与比对、被拒绝的边算相连、忽略「确认保留」、游标用 `>=`（翻页死循环）、重复批准不幂等、非低置信度关系也可处理、不加草稿修订号、关系不登记人工贡献、有边的节点也能拒绝、拒绝节点不加锁、非候选对也能记「不是重复」、重复合并不幂等、多余字段被接受、`totals` 为 0、包含候选相似度为 1，以及孤立判定不排除已拒绝邻居（补强用例后检出）。存活 1 处：去掉游标中的栏目检查——三栏排序键形状互不相同，形状检查已能拒绝他栏游标，属等价变异。

## 4. 接口与数据变更

- REST：`getReviewQueue` 新增查询参数 `kind`、`cursor`、`limit` 与 422；响应新增必填 `totals`、`next_cursors`，`suspected_duplicates` 每项恰两个候选并带 `reason`（前端尚无使用者）。新增 `POST /review/actions`（`resolveReviewItem`）：200 `ReviewActionResult`；404 `NOT_FOUND`；409 `COURSE_BUSY`，合并另有 `REVISION_CONFLICT`、`CYCLE_DETECTED`；422 `VALIDATION_ERROR`；503 `STORAGE_UNAVAILABLE`。
- SQLite：迁移 013 新表 `review_dismissals(course_id, kind, item_key, dismissed_by, dismissed_at)`。
- Neo4j：无 DDL。关系处理改 `status`、置 `contrib_manual = true`、`revision + 1`；节点拒绝置 `status = rejected`、`locked = true`、`contrib_manual = true`、`revision + 1`。

## 5. 风险

1. 每次读队列都要全量读草稿并做 O(n²) 名称比对，面向单课程规模；课程很大时需要缓存或把候选落库。
2. 疑似重复只看名称（E08），语义相近但名称不同的重复要等 E09 向量候选（D-08 阈值）接入。
3. 「确认保留」按节点 ID 永久生效，节点此后失去所有边也不会再次入列。
4. 排在游标之前的新条目在当前翻页中看不到，需要从第一页重新读取。

## 6. 待决

- ADR-060 待 ArvinHan 签收（尤其：疑似重复不含向量相似；新增 `resolveReviewItem` 而不是借用尚未实现的 `/relations`；「确认保留」的永久性）。
- D-08 阈值定稿后，是否把 E09 向量候选并入疑似重复栏。
- 审计日志归 F12。

## 7. 下一步

H09（审核队列 UI）按 `ReviewQueue` / `resolveReviewItem` 接入：三栏空态用 `totals`，翻页用 `next_cursors`，处理后用响应中的 `totals` 刷新计数。

## 8. 回滚

按 ADR-060「回滚」：撤销本分支的代码与契约改动并重新生成；迁移 013 按文件头 `ROLLBACK` 行回滚（`test_f11.py` 已验证，只丢失处理记录），或恢复 `backups/*-before-013.sqlite`。已批准、拒绝或合并的图数据不会自动恢复。
