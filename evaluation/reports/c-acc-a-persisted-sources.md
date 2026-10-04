# C-ACC-A：持久化后知识点详情出处的只读核验（2026-10-04）

> **结论：两门课草稿持久化后的每个 AI 知识点，在 API 详情路径上都有可定位的本课出处；未发现悬空、跨课或空出处。** 这是实际落库数据的核验，不再只是检查点核对。它不判断出处语义是否正确，那属于 C04 人工判定。

## 1. 方法

- **读取路径**：直接调用 `app.services.graph.read.read_knowledge_point`，即 API `GET /courses/{cid}/kp/{kid}` 的服务函数。作用域是草稿、教师读取，与教师在页面上看到的详情相同。图谱经 `GraphReader` 与 `Neo4jRepository.read` 读取，走读路由，服务器拒绝写入。
- **数据源**：
  - 图谱：共享 Neo4j `bolt://localhost:7688`。连接变量按用户授权从测量区 `.env` 只取 `NEO4J_URI`、`NEO4J_USER`、`NEO4J_PASSWORD` 载入进程，不打印、不写盘、不复制。
  - SQLite：测量区 `src/backend/storage/smartsketch.sqlite3`。详情路径依赖的 SQLite 连接临时换成只读：`mode=ro&immutable=1` 加 `PRAGMA query_only`。运行前后 SHA-256 相同，由工具断言；`-shm`、`-wal` 的大小与修改时间也不变。
- **范围**：测量提交 `88f9f6f` 的两门课。

  | 课程 | 课程 ID | 有效任务 |
  | --- | --- | --- |
  | course1 PDF | `ee9633a27f23407dbb30fee6c9a6490b` | `fc66ece9…` |
  | course2 PDF | `5772f37ff9e041e0bb5e5606ba4587b0` | `4ca2a373…` |

  两门课都没有发布，只有草稿。
- **没有**调用生成或向量服务，没有改共享 Neo4j、课程草稿或发布版本，没有复制凭据、业务库或课程正文。

## 2. 结果

| 项 | course1 PDF | course2 PDF |
| --- | ---: | ---: |
| 草稿实际知识点（持久化后） | **76** | **68** |
| `source` 生成方式标签 | `ai` 76 | `ai` 68 |
| 详情 `source_refs` 至少一条可定位来源的 AI 知识点 | **76 / 76** | **68 / 68** |
| `source_refs` 条数 | 79 | 76 |
| 其中带页码 / 带章节 / 带文件名 | 79 / 79 / 79 | 76 / 76 / 76 |
| 证据边 `EVIDENCED_BY` / 涉及文本块 | 79 / 15 | 76 / 14 |
| AI 知识点无可定位来源 | 0 | 0 |
| 悬空块（SQLite 本课查不到） | 0 | 0 |
| 文档不属于本课 | 0 | 0 |
| 指向他课块的证据边 | 0 | 0 |
| 详情读取失败 | 0 | 0 |

- 知识点数与 DeepSeek 报告、检查点核对的 76 / 68 一致。
- `source="ai"` 只是生成方式标签。上表第 4 行起统计的是详情接口真正返回的 `source_refs`，两者分开计数。
- 摘要哈希 `refs_digest`：按「知识点、块、文档、页码、章节」排序后的 SHA-256。course1 `12c49a83d716a5b2…`，course2 `6cbad132c52488e6…`，全文见证据文件，用于日后复跑比对。

## 3. 证据与复现

- 证据：`evaluation/raw/c-acc-a/sources.json`。只含编号、计数、哈希、测量库路径与只读方式，不含课程正文或口令。
- 工具：`evaluation/audit_persisted_sources.py`；测试 `tests/tooling/test_c_acc_sources.py`（5 passed）。
  - 测试覆盖：计数与标签分离、缺来源 / 悬空 / 他课文档 / 跨课边的检出、输出不含正文且摘要稳定、只读连接拒绝写入且不改文件、详情路径确实经过只读连接并在结束后恢复。
- 复现（在执行工作区，需用户授权读取测量区 `.env` 的三个连接变量）：

  ```bash
  M=/Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-c03b-measure
  env -u NEO4J_URI -u NEO4J_USER -u NEO4J_PASSWORD PYTHONPATH=$PWD/src/backend .venv/bin/python \
    evaluation/audit_persisted_sources.py --db $M/src/backend/storage/smartsketch.sqlite3 --env-file $M/.env \
    --course ee9633a27f23407dbb30fee6c9a6490b --course 5772f37ff9e041e0bb5e5606ba4587b0 \
    --out evaluation/raw/c-acc-a/sources.json
  ```

  本次实际退出码 0，`defect_items: 0`。运行中 Neo4j 对 `importance`、`difficulty` 各报 421 条「属性不存在」提示：抽取不写这两个属性，详情按缺失处理，与已知行为一致，不是错误。

## 4. 限制

- 只核验这两门课的**草稿**。它们没有发布，所以发布副本里的出处（版本副本只存块 ID 列表）不在本次范围。
- 「可定位」只说明出处指向本课真实资料的页码或章节，**不说明原文确实支持该知识点**；语义正确与否由 C04 人工判定。
- `immutable=1` 假定核验期间没有进程写测量库：测量服务已停，WAL 为 0 字节，前后哈希一致。
