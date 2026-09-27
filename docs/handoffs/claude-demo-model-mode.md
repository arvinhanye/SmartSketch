# Claude 交接：演示模型模式（LLM_MODE=demo / EMBEDDING_MODE=demo，ADR-079）

- 分支：`claude/demo-model-mode`（基于 origin/main `f6325fe`，未 push、未开 PR）
- 状态：完成，待审查（review_status: ready_for_review）
- 背景：要在不调用付费模型的情况下把整套应用跑起来验收（教师上传→抽取→审核→发布；学生浏览→掌握→推荐→问答），并用于 K05/K06 端到端。原先 `LLM_MODE=fake` 时 worker 与问答都用 `FakeModelClient()` 缺省输出 `{"fake":...}`，上传 `stack-queue-notes.md` 后任务「抽取失败的片段过多」；`FakeEmbeddingClient` 向量与语义无关，J04 闸门（0.7）几乎永远拒答。

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/config.py` | `LLM_MODE` 增 `demo`，`EMBEDDING_MODE` 增 `demo`；`production` 下 `fake`/`demo` 均拒绝；新增保留 ID `DEMO_EMBEDDING_MODEL = "smartsketch-demo-ngram-v1"`（`online`/`local` 不得用作 `EMBEDDING_MODEL`）；新增 `embedding_model_id()`、`embedding_space_identity()` 作为向量空间推导的唯一来源 |
| `src/backend/app/services/ai/demo.py`（新） | `DemoModelClient`（继承 `FakeModelClient`，responder = `demo_respond`，因此截断、模拟 usage、流式切片、`script` 注入故障都与 fake 相同）；`DemoEmbeddingClient`、`demo_vector` |
| `src/backend/app/services/ai/factory.py`（新） | `build_model_clients` / `model_id` / `build_embedding_client`：live / demo / fake 三路装配；demo 的模型 ID 固定为 `smartsketch-demo-rules-v1`，不沿用 `LLM_*_MODEL` |
| `src/backend/app/workers/runner.py`、`app/api/chat.py`、`app/api/versions.py` | 改用 factory（fake 分支行为不变） |
| `src/backend/app/services/ai/embeddings.py`、`app/services/startup.py`、`app/repositories/graph_migrations.py`、`scripts/reembed.py`、`scripts/backfill_chunk_vectors.py` | 空间推导与向量客户端改用上面的公共函数；demo 空间为 `real/smartsketch-demo-ngram-v1/<维度>`、`is_fake = 0`，无需迁移 |
| `tests/backend/test_demo_mode.py`（新，19 例） | 配置/空间/装配；E05/E06/E11 真实解析器零丢弃接受；worker 解析+抽取阶段；PREREQUISITE 有先修表述才给且无环；向量字面重叠区分度；无 Neo4j 的问答链路（演示向量 → J04 闸门 → J05 → J06）；哨兵与流式；J03 改写原样；E10 裁决输出形状 |
| `tests/integration/test_demo_mode_live.py`（新，3 例，需 Neo4j） | `run_pipeline_once` 上传 → `awaiting_review` → 草稿图非空；草稿 PREREQUISITE 无环；演示向量写入 Neo4j 余弦索引后的闸门分数 |
| `.env.example`、`docs/integrations.md`、`docs/architecture.md` | 模式取值、生产禁用、演示空间、演示阈值建议 |

### 演示规则摘要（`demo_respond` 按 `ModelRequest.purpose` 分派）

- `extract_entities`（及 `repair`，按消息内容判断原用途）：章节路径行的各级标题（去编号）、定义句「X 是/指/称为/用/把/只允许……」、「X 的特点是 P」（X + 性质 P）、「称为 X」、「特点是 P」、加粗术语、`术语：说明` 列表项、表格数据行首列（表头首列是「操作/方法/算法/步骤」时为 method）、先修句式两端、「X 是 Y 的例子」（X 为 example）。`evidence` 一律是块内逐字原文（路径行或所在句），`definition` 取所在句（标题无定义句时为「课程资料中「…」一节的主题。」）。围栏代码块跳过；代词/「学习」「本」等开头的主语不收。输出按声明上限截断到合法 JSON。
- `extract_entities_gleaning`：同一规则减去已抽取列表（通常为空数组）。
- `extract_relations`：路径行上下级标题 `CONTAINS`；节标题 → 本段定义出的非例子知识点 `CONTAINS`；句中含 E11 `PREREQUISITE_CUES` 且匹配「学习 X 之前需要先掌握 Y」「X 建立在/依赖于 Y（的基础上）」「掌握 Y 后才能学习 X」「Y 是 X 的基础/前提/先修」时 `PREREQUISITE`（Y → X），**同一输出内先做环检测，会成环的边舍弃**；「X 是 Y 的例子」`EXAMPLE_OF`；同句两个知识点且有对比/关联词 `RELATED_TO`。**同级顺序不判前置**：E11 校验要求先修表述，提示词也明确「出现先后不算前置」，按任务示例加同级顺序边会被校验器全部丢弃。
- `answer_with_context`：从编号资料块挑与问题主题词重叠最多的 1～3 句，逐句 `…[n]。`；含方括号/反引号等可能干扰 J06 的句子不选；无重叠输出 `<<INSUFFICIENT_EVIDENCE>>`。
- `rewrite_query`：原样返回「当前问题」。`judge_duplicate` / `summarize_definition`：名称规范化相同才判同义，来源 ID 全引；合并定义取首条（worker 目前不调用 E10，只保证形状合法）。
- 其他用途退回 E02 缺省输出。

### 演示向量

字符 1-gram + 2-gram（NFKC、casefold，只取字母数字；去掉「什么是/如何/怎么样…」等疑问套话；虚词字降权 0.3），权重 `1 + ln(tf)`，每个 gram 以 ±权重分散到 128 个 SHAKE-256 哈希维，L2 归一化。**分散这一步是实测后加的**：最初只落一维的纯哈希词袋过于稀疏，写入 Neo4j 5.26 向量索引后分数被压扁（实测「今天天气怎么样」得 0.639，本地计算应为 0.506），推测是索引缺省的标量量化所致；分散到 128 维后 Neo4j 分数与本地 `(1+cos)/2` 基本一致。1000 字文本约 27 ms。

## 演示模式建议阈值：`QA_SIMILARITY_THRESHOLD=0.58`

`(1+cos)/2`，对 `stack-queue-notes.md` 各块取最大值：

| 问题 | 本地计算 | Neo4j 5.26 索引实测 |
| --- | --- | --- |
| 什么是栈 | 0.6299 | 0.6375 |
| 队列的特点 | 0.6667 | 0.6693 |
| 栈的特点是什么 | 0.6490 | — |
| 循环队列怎么判断队满 | 0.7553 | — |
| 顺序栈 | 0.6538 | — |
| 今天天气怎么样 | 0.5011 | 0.5105 |
| 如何做红烧肉 | 0.5127 | 0.5144 |
| 光合作用的原理 | 0.5362 | — |
| 什么是二叉树 | 0.5286 | — |

覆盖问题 ≥ 0.63、无关问题 ≤ 0.54，取 0.58。已写入 `.env.example` 注释与 `docs/integrations.md`；fake 缺省阈值 0.7 未改，代码不按模式改阈值、不绕过闸门。

无 Neo4j 链路的问答结果（`test_demo_mode.py::_ask`，阈值 0.58）：

- 什么是栈 → answered：「栈是一种只允许在一端进行插入和删除的线性表，这一端称为栈顶[1]。栈的特点是后进先出[1]。」
- 队列的特点 → answered：「队列只允许在一端插入、另一端删除，特点是先进先出[1]。」
- 什么是二叉树 / 今天天气怎么样 → not_covered（`below_similarity_threshold`）

## 已运行命令与结果

均在 worktree 根目录，`PY=/home/user/SmartSketch/.venv/bin/python`，`PYTHONPATH=$PWD/src/backend`。

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 改动前基线 | `$PY -m pytest tests/backend -q -x -p no:cacheprovider` | `3434 passed, 27 skipped, 1 warning` |
| 本任务测试 | `$PY -m pytest tests/backend/test_demo_mode.py -q -p no:cacheprovider` | `19 passed`（去掉 1 条冗余用例前为 `20 passed`） |
| 后端全量（最终代码） | `$PY -m pytest tests/backend -q -p no:cacheprovider` | 见下方「最终全量」 |
| 集成（demo，连 Neo4j） | `SMARTSKETCH_TEST_NEO4J_URI=bolt://127.0.0.1:27687 SMARTSKETCH_TEST_NEO4J_USER=neo4j SMARTSKETCH_TEST_NEO4J_PASSWORD=testpassword1 $PY -m pytest tests/integration/test_demo_mode_live.py -v` | `3 passed` |
| 集成全量（连 Neo4j） | 同上环境变量 + `SMARTSKETCH_SKIP_DOCKER=1 $PY -m pytest tests/integration -q` | `1 failed, 387 passed, 7 skipped`；失败为 `test_k10.py::test_an_unfenced_write_during_the_backup_fails_it[neo4j]`：该用例的钩子硬编码 `auth=('neo4j', 'x')`，本机容器按任务要求用 `neo4j/testpassword1`，报 `AuthError`，与本改动无关 |
| 门禁 | `env PATH=<venv>/bin:<openapi-typescript 7.4.4 bin>:/opt/node22/bin:/usr/bin:/bin ./scripts/verify.sh` | `PASS contracts gate` / `Scaffold verification passed.`（主仓 node_modules 无 openapi-typescript，用 scratchpad 里已装的 7.4.4） |
| 空白 | `git diff --check` | 无输出 |

Neo4j 容器：`docker run -d --name ss-neo4j-demo -e NEO4J_AUTH=neo4j/testpassword1 -e NEO4J_PLUGINS='["apoc"]' -p 127.0.0.1:27687:7687 neo4j:5.26-community`，用完已 `docker rm -f ss-neo4j-demo`。

说明：测试文件先于实现写成，但没有单独保留「实现前失败」的那次运行输出。

## 接口 / 数据 / 配置变更

- 环境变量：`LLM_MODE` 新取值 `demo`，`EMBEDDING_MODE` 新取值 `demo`；无新增变量。HTTP 接口、契约、SQLite/Neo4j 结构、迁移、依赖均无变化。
- 向量空间：demo 记为 `embedding_space_state(model='smartsketch-demo-ngram-v1', dimensions, is_fake=0)`，空间串 `real/smartsketch-demo-ngram-v1/<维度>`。与 fake 库互切会被启动门禁拒绝（须 V12 `scripts/reembed.py` 或换新库），`reembed.py` 已支持 demo 目标空间。
- 新公开符号：`app.config.DEMO_EMBEDDING_MODEL`、`embedding_model_id`、`embedding_space_identity`；`app.services.ai.demo.*`；`app.services.ai.factory.*`。删除 `runner.FAKE_MODEL_ID`（仓库内无引用，移到 `factory.FAKE_MODEL_ID`）。

## 风险与限制

- 演示输出只看字面，不代表抽取/问答质量；`model_calls` 里的模型 ID 为 `smartsketch-demo-rules-v1`，便于与真实调用区分。K02/K13 评测脚本（`evaluation/`）未接 demo，仍把非 live 视为 fake。
- 关系抽取按小节进行，跨小节的先修关系规则上出不来；资料没有先修表述时（如 `stack-queue-notes.md`）草稿里没有 `PREREQUISITE`，学习路径只能靠教师在审核中手工加边或换带先修句的资料演示（测试里的 `PREREQ_TEXT` 可作样例）。
- 抽取提示较长，fake 口径一字符一 token：单块约 1.5～3k「token」，默认任务预算 500000 约够 150+ 块；大资料演示可调高 `LLM_TASK_TOKEN_BUDGET`。
- 演示向量阈值 0.58 只在本 fixture 上实测；资料换成长篇或多学科时，无关问题可能因常用字重叠越过阈值（向量是词袋，没有语义）。

## 回滚

`git revert <本分支提交>`。无迁移；若某库已用 demo 空间启动过，回滚后改回 fake 需按 V12 重新向量化或换新库（启动门禁会明确报错）。

## 下一步

- K05/K06 端到端：`.env` 设 `LLM_MODE=demo`、`EMBEDDING_MODE=demo`、`QA_SIMILARITY_THRESHOLD=0.58`，新库启动。
- 待决：是否在 `tests/fixtures/documents/` 放一份带先修句的演示资料，供学习路径演示。

## 待协调者追加

### docs/tasks.md 任务行（建议）

| ID | 任务 | 负责人 | 状态 | 验收证据 |
| --- | --- | --- | --- | --- |
| DEMO-01 | 演示模型模式：`LLM_MODE=demo` / `EMBEDDING_MODE=demo`，无付费模型跑通抽取与问答真实链路 | Claude | DONE（待审查） | `tests/backend/test_demo_mode.py` 19 passed；`tests/integration/test_demo_mode_live.py` 3 passed（Neo4j 5.26）；后端全量绿；`docs/handoffs/claude-demo-model-mode.md` |

### docs/decisions.md：ADR-079

**ADR-079 演示模型模式（LLM_MODE=demo / EMBEDDING_MODE=demo）**（2026-09-27）

- 背景：需要不调用付费模型就把整套应用（上传→抽取→审核→发布；浏览→掌握→推荐→问答）跑起来验收，并支撑 K05/K06 端到端。`fake` 模式的缺省输出不被解析器接受（抽取任务直接失败），fake 向量与语义无关（问答闸门几乎永远拒答）；大量既有测试依赖 fake 的现有行为，不能改。
- 决定：
  1. `LLM_MODE`、`EMBEDDING_MODE` 各增加取值 `demo`；`APP_ENV=production` 时与 `fake` 一样拒绝。fake 行为逐字不变。
  2. `DemoModelClient` 基于 E02 fake 的 responder 机制，按 `ModelRequest.purpose` 用确定性规则从请求中的资料原文产出能被 E05/E06/E11/J03/J05/E10 真实解析器接受的输出；请求模型 ID 固定为 `smartsketch-demo-rules-v1`，不沿用 `LLM_*_MODEL`。`PREREQUISITE` 只在句中有先修表述时给出，单次输出内先做环检测；同级/出现顺序不判前置。
  3. `DemoEmbeddingClient`：字符 1+2-gram 有符号哈希词袋、每 gram 分散到 128 维、L2 归一化，维度取 `EMBEDDING_DIMENSIONS`。向量空间以保留模型 ID `smartsketch-demo-ngram-v1` 记为真实空间 `real/smartsketch-demo-ngram-v1/<维度>`（`is_fake = 0`，无需迁移），`online`/`local` 不得使用该 ID；空间推导统一由 `app.config.embedding_space_identity` 给出。
  4. 客户端装配集中到 `app.services.ai.factory`（worker、问答、发布、回填脚本共用）。
  5. 演示时建议 `QA_SIMILARITY_THRESHOLD=0.58`（实测覆盖问题 0.63～0.67、无关问题 ≤ 0.54）；只作为环境变量取值建议，代码不按模式改阈值。
- 后果：无付费模型也能端到端演示与验收；演示结果只看字面，不代表质量，`model_calls` 可按模型 ID 区分。demo 与 fake 是不同向量空间，互切须重新向量化或换新库。跨小节先修关系与无先修表述资料上的学习路径仍需教师手工补边。
