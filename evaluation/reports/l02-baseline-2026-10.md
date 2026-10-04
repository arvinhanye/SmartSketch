# L02 网页链路真实基线（2026-10-02）

> **状态：抽取与问答均已实测。** 抽取为 2026-10-02 首测（第 2、3 节，原样保留）；发布与问答为 2026-10-03 补测（第 4 节），此前阻塞的原因是本机到北京地域向量接口的 TCP 连接超时，该网络路径已于 2026-10-03 恢复（ADR-081 决定 1 的签收口径）。本报告每次测量只有一次运行，不是多次取优；问答第 3 题的重复现象在 4.4 单独说明。

## 1. 测试条件

| 项 | 取值 |
| --- | --- |
| 日期 | 2026-10-02（America/New_York），任务创建于 08:20:42Z |
| 代码 | `52aa4db`（业务代码与 `6ff8a8d` 相同） |
| 机器 | Intel Core i7-9750H（12 逻辑核）、16 GB 内存、macOS 26.6.2 |
| 网络 | 本机当前网络直连 `api.deepseek.com`（未经代理配置） |
| 启动方式 | `scripts/start-demo.sh --live --no-open`：API、worker、前端各一个进程；独立 SQLite 与 Neo4j（7688） |
| 大模型 | 请求 `deepseek-flash`，响应 `deepseek-flash`；`LLM_MODE=live`，无备用供应商 |
| 并发与重试 | `LLM_MAX_CONCURRENCY=4`、`LLM_MAX_RETRIES=2`、`TASK_CHUNK_MAX_ATTEMPTS=2` |
| 提示词 | `extract_entities` v2、`extract_relations` v2；未开补漏（E06），融合直通 |
| 资料 | `datasets/demo/ch3-stack-queue.md`（自编「数据结构 第 3 章 栈与队列」），Markdown，11779 字节、111 行、16 个文本块共 5819 字符 |
| 测量工具 | `evaluation/measure_web_flow.py extract`，经 HTTP 接口上传并每 0.5 秒轮询任务快照 |
| 首次处理 | 是。新建课程、新库，没有抽取缓存可命中 |

计时边界：发出上传请求 → 任务快照 `stage = awaiting_review`。含排队、解析、分块、抽取、直通融合与入库。

## 2. 抽取结果

**总耗时 141.72 秒，目标 ≤60 秒，未达标（超出约 82 秒）。**

| 阶段 | 起止（UTC） | 耗时 | 依据 |
| --- | --- | --- | --- |
| 排队、解析、分块 | 08:20:42.3 → 08:20:43.7 | 约 1.4 秒 | 任务 `created_at` 到第一条 `model_calls` |
| 抽取（实体 + 关系 + 修复） | 08:20:43.7 → 08:22:18.1 | 约 94.4 秒 | `model_calls` 首条创建到末条完成 |
| 直通融合与入库 | 08:22:18.1 → 08:23:03.8 | 约 45.7 秒 | 末条模型调用完成到任务 `updated_at` |

模型调用（`model_calls`，全部 `ok`）：

| 用途 | 次数 | 输入 token | 输出 token | 单次延迟 最小 / 平均 / 最大 |
| --- | --- | --- | --- | --- |
| `extract_entities` | 16 | 10293 | 29479 | 3.1 / 8.5 / 17.2 秒 |
| `extract_relations` | 15 | 16140 | 34545 | 4.7 / 10.5 / 20.3 秒 |
| `repair`（输出不合规后的修复） | 3 | 2454 | 8143 | 11.7 / 12.2 / 12.8 秒 |
| 合计 | 34 | 28887 | 72167 | — |

检查点：16 个块全部 `done`，16 个小节全部 `done`，没有失败块。

草稿图谱（教师接口 `GET /courses/{cid}/graph`，原始 AI 输出，未经人工修改）：

- 知识点 82 个：`concept` 36、`method` 15、`example` 13、`theorem` 12、`formula` 6。
- 关系 73 条、4 种类型：`CONTAINS` 40、`RELATED_TO` 20、`EXAMPLE_OF` 11、`PREREQUISITE` 2。

数量指标（≥20 个知识点、≥3 种关系）在这次运行中满足。**准确率本次没有人工判定**，不能据此声称 ≥70%；历史报告 `extraction-accuracy.md` 是另一条评测链路上的结果。

## 3. 对 60 秒目标的含义

1. 抽取阶段 94 秒里，34 次调用的延迟总和约 330 秒，并发 4 时的理论下限约 83 秒，与实测接近。提高并发是最直接的手段：两个阶段各自最慢的一次调用是 17 秒与 20 秒，加上 3 次约 12 秒的修复，并发足够时抽取阶段的下限在 40 至 50 秒。
2. **入库阶段 45.7 秒是之前没有记录过的开销**，与模型无关。82 个知识点和 73 条关系写入 Neo4j 用了这么久，值得在 L16 先看写入是否逐条往返。它不解决，仅靠提高并发到不了 60 秒。
3. 与 2026-09-26 的历史记录（约 329 秒，另一条脚本链路）相比，这次单次调用平均延迟从约 37 秒降到 9 至 10 秒。供应商响应速度在变，同一配置隔天重测可能有明显出入。
4. `PREREQUISITE` 只有 2 条。学习路径推荐依赖前置关系，这个数量对路径可视化偏少，L14 与 L16 需要关注。

## 4. 问答与发布（2026-10-03 补测，`--live` + 在线向量）

### 4.1 条件

| 项 | 取值 |
| --- | --- |
| 日期 | 2026-10-03（America/New_York），发布于 06:17:08Z，提问于 06:18:37–06:18:51Z |
| 代码 | `f1f4a71`（含 L09 `ea9484c`；业务代码与首测相同） |
| 机器与网络 | 同首测；本机到 `dashscope.aliyuncs.com:443` 本次可达 |
| 启动方式 | `scripts/start-demo.sh --live --no-open`；API 8001、前端 5174、Neo4j 7688 |
| 大模型 | 抽取与问答均 `LLM_MODE=live`、请求 `deepseek-flash` |
| 向量 | `EMBEDDING_MODE=online`、`text-embedding-v4`、1024 维、每批 10 条（ADR-081） |
| 课程与账号 | 首测的课程 `2ace598581f349ec9943dea90bc7fdf1`（82 知识点 / 73 关系），提问账号 `demo_student`（本次加入课程） |
| 测量工具 | `evaluation/measure_web_flow.py ask`，逐题单次请求；服务端数字取自 `chat_logs` |

### 4.2 发布（在线向量在真实链路上的首次使用）

**`POST /courses/{cid}/publish` → HTTP 200，耗时 21.17 秒**，`version=1`、`node_count=82`、`edge_count=73`、`unchanged=false`，排除项 `low_confidence_nodes/edges/cascaded_edges` 均为 0（没有 `PUBLISH_BLOCKED`，未改图谱）。

发布确实完成向量化，Neo4j 侧核对（只读）：

| 项 | 结果 |
| --- | --- |
| 带向量的节点 | `KnowledgePoint` 82、`Chunk` 16 |
| 向量属性与索引 | 属性 `embedding_e01842f40f41e0ee`；索引 `kp_embedding_…`（KnowledgePoint）、`chunk_embedding_…`（Chunk） |
| 带向量的知识点版本 | 全部 82 个属于已发布快照 `01M406GWNMMXH58EZM5ND6WJGS`（草稿 82 个不带向量） |
| 被向量化的文本量 | 知识点 `name+definition` 合计 3964 字符；文本块 16 个（文本存 SQLite，首测记为 5819 字符） |

**未记录（缺陷，见 4.5）**：发布期的向量调用没有写入 `model_calls`，无法从记账拿到真实用量。

### 4.3 五题结果（一次运行，照实记录）

| # | 问题 | 结果 | 服务端 `latency_ms` | 首字 `first_delta_latency_ms` | 引用数 |
| --- | --- | --- | --- | --- | --- |
| 1 | 什么是栈？ | `answered` | 6122 | 5879 | 1 |
| 2 | 循环队列如何判断队满？ | `answered` | 5128 | 4698 | 1 |
| 3 | 栈和队列有什么区别？ | **`not_covered`（`all_citations_invalidated`）** | 5949 | —（无有效增量） | 0 |
| 4 | 入栈操作的时间复杂度是多少？ | `answered` | 2189 | 2069 | 2 |
| 5 | 光合作用的原理是什么？ | `not_covered`（`below_similarity_threshold`） | 399 | — | 0 |

- **完整耗时：中位数（p50）5.13 秒，最大 6.12 秒，最小 0.40 秒。** 五题全部 ≤ 15 秒（赛题上限）且全部 ≤ 10 秒（S2 目标值），**这一项达标**。
- **首字耗时：已作答的三题为 5.88 / 4.70 / 2.07 秒。** S2 的首字目标是 ≤ 3 秒，**三题中两题未达标，最大超出约 2.9 秒**。未作答的两题没有首字（回答被撤回前没有对外的有效增量）。
- 期望「前 4 题 `answered`、第 5 题 `not_covered`」中，**第 5 题符合预期，第 3 题不符**（详见 4.4）。
- 第 5 题在检索阶段即被拒，**没有发起模型调用**（`model_calls` 无对应行），未产生付费调用。

### 4.4 第 3 题：结论被撤回（可复现）

「栈和队列有什么区别？」返回 `not_covered` / `all_citations_invalidated`，但**资料确实覆盖该问题**：`datasets/demo/ch3-stack-queue.md:71` 整段讲的就是二者的区别（「二者的区别只在于允许进行插入和删除的位置不同……适合用栈……适合用队列」）。

服务端记录（`chat_logs`）与调用记录（`model_calls`）指向同一个原因：

| 证据 | 值 |
| --- | --- |
| `chat_logs.invalidation_subtype` | `no_markers`（回答里一个可校验的引用标记都没有） |
| `chat_logs.truncated` | `1`（生成被截断） |
| `chat_logs.unknown_citation_count` | `0`（不是「引用了不存在的来源」，而是压根没有标记） |
| `model_calls` 该次输出 token | **1024，正好等于上限 `ANSWER_MAX_OUTPUT_TOKENS`（`services/qa/generate.py:116`）** |
| 同批第 1、2、4 题的输出 token | 464 / 858 / 246，均未触顶 |

因果链：比较类问题需要更长的作答 → 输出撞上 1024 上限被截断 → 截断发生前没有产生任何引用标记 → `citations.finalize()`（`services/qa/citations.py:286`）判定 `no_markers`，按 ADR-003 的硬契约**整篇撤回**为 `not_covered`，学生看到「生成的回答无法与课程资料对应，已撤回」。注意 `truncated` 只被记录，**不参与**该分支判定，所以即使模型答对了内容也会被撤回。

复现：同一问题再问一次，结果逐项相同（`all_citations_invalidated` / `no_markers` / `truncated=1` / 输出 token 1024），**确定性复现，不是抖动**。该次复跑只作诊断，不计入 4.3 的基线数字。

影响面：任何「需要较长作答且引用标记出现在末尾」的问题都可能被撤回；不是本课程或本题独有。

### 4.5 附带发现：发布期向量调用未记账

ADR-011 修订 2 决定 12 要求「每次实际发出的供应商调用（LLM 与向量）一条 `model_calls` 记录，发请求前预写 `call_id`」。本次发布确实调用了向量服务（Neo4j 侧 82 + 16 个节点已带向量、发布耗时 21.17 秒），但 `model_calls` 中 `task_id IS NULL` 的行只有 5 条 `answer_with_context`，**没有任何向量用途的行**。后果：向量用量对预算统计不可见，发布成本无法核对。按本轮边界，只记录不修。

### 4.6 问答用量（`model_calls`，`task_id IS NULL`）

| 用途 | 次数 | 输入 token | 输出 token |
| --- | --- | --- | --- |
| `answer_with_context`（4.3 的五题里的 4 次作答） | 4 | 10101 | 2592 |
| `answer_with_context`（4.4 的诊断复跑） | 1 | 2384 | 1024 |
| 发布期向量调用 | 未记录 | 未记录 | 未记录（按字符数估算约 0.65～1 万 token，仅为上界估计） |

## 5. 用量

- 抽取（2026-10-02）：计费 token 101054（输入 28887 + 输出 72167）。
- 发布与问答（2026-10-03）：问答 `model_calls` 计费 **16101**（输入 12485 + 输出 3616），含 4 次基线作答与 1 次诊断复跑；发布期向量调用未记账，按字符数估算约 0.65～1 万 token（估计值，非测量值）。
- **冲刺累计计费 token：101054 + 16101 = 117155**（另有未记账的发布向量用量约 0.65～1 万），上限 500 万。

## 6. 复现

```bash
scripts/start-demo.sh --live --no-open          # 需要 .env 的 LLM_API_KEY
MEASURE_PASSWORD=<演示口令> .venv/bin/python evaluation/measure_web_flow.py extract \
  --base-url http://127.0.0.1:8001 --username demo_teacher --password-env MEASURE_PASSWORD \
  --course-name "L02 基线" --file datasets/demo/ch3-stack-queue.md
sqlite3 src/backend/storage/smartsketch.sqlite3 \
  "SELECT purpose, count(*), sum(usage_input), sum(usage_output), max(latency_ms) FROM model_calls WHERE task_id='<TASK_ID>' GROUP BY purpose;"
```

发布与问答（2026-10-03 补测，`<CID>` 用下面的课程 ID）：

```bash
scripts/start-demo.sh --live --no-open                    # 需要 .env 的 LLM_API_KEY 与在线向量三项
TOKEN=$(curl -s -X POST http://127.0.0.1:8001/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"demo_teacher","password":"<演示口令>"}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')
curl -s -X POST http://127.0.0.1:8001/api/v1/courses/<CID>/publish -H "Authorization: Bearer $TOKEN"   # 计时看这里
curl -s -X POST http://127.0.0.1:8001/api/v1/courses/<CID>/members -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"username":"demo_student"}'
printf '%s\n' "什么是栈？" "循环队列如何判断队满？" "栈和队列有什么区别？" "入栈操作的时间复杂度是多少？" "光合作用的原理是什么？" > .demo/logs/l02-questions.txt
MEASURE_PASSWORD=<演示口令> .venv/bin/python evaluation/measure_web_flow.py ask \
  --base-url http://127.0.0.1:8001 --username demo_student --password-env MEASURE_PASSWORD \
  --course-id <CID> --questions .demo/logs/l02-questions.txt
sqlite3 -header -column src/backend/storage/smartsketch.sqlite3 \
  "SELECT question, outcome, reason, invalidation_subtype, truncated, latency_ms, first_delta_latency_ms FROM chat_logs ORDER BY created_at DESC LIMIT 5;"
```

本次的课程 `2ace598581f349ec9943dea90bc7fdf1`、任务 `205f9311572846b8bc192ff1f67e244f` 保留在冲刺工作区的本地库里，供后续发布与问答补测使用。2026-10-03 补测后该课程已发布为 v1（82 知识点 / 73 关系）并加入 `demo_student`。
