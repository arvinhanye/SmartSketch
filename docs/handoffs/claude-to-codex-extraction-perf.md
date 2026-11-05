# Claude → Codex 交接：图谱生成提速（EXTRACT-PERF-01，2026-11-05）

## 1. 目标与基线

- 用户反馈：上传资料到「待审核」仍然偏慢。赛题/规格目标：示例章节 **≤60 秒**（`docs/tasks.md` B-QUALITY-01、C03 中「抽取 ≤60 秒」一直未达）。
- 工作区 `~/Desktop/SmartSketch-main`。代码基线 `ad63341`（`claude/home-topbar-nav`，已含邀请码与界面改版）。写本稿时该目录正处于 **OPT-05 后端分层**（`codex/opt-05-backend-layering`，未提交），它改动了 `services/versions/chunk_vectors.py`、`materialize.py`、`repositories/versions.py` 等发布相关文件。
- 起点：**先让 OPT-05 提交完成**，再从 OPT-05 的提交新建 `codex/extraction-perf`；不要在 OPT-05 未提交时切分支或混改。若必须并行，用 `git worktree` 从 `ad63341` 另开目录，并在 OPT-05 合入前不碰发布向量化（P1 第 5 项）相关文件。
- 本交接稿、prompt 和 `docs/tasks.md` 末尾 EXTRACT-PERF-01 一节目前是未跟踪/未提交改动，混在 OPT-05 工作区里：OPT-05 提交时请不要带上它们，留给 EXTRACT-PERF-01 的第一个提交。
- 先读：`AGENTS.md`、`docs/tasks.md`（C03、B-QUALITY-01、B-EVAL-01）、`specs/task-processing.md`（阶段、检查点、租约）、`specs/course-knowledge-graph.md`、ADR-011、ADR-080/082/089/090。

### 已有实测（`evaluation/reports/l02-baseline-2026-10.md`，示例章节 `datasets/demo/ch3-stack-queue.md`，11.8 KB）

| 段 | 耗时 | 备注 |
| --- | --- | --- |
| 排队、解析、分块 | 约 1.4 秒 | 16 个文本块，共 5819 字符（平均每块约 360 字） |
| 抽取（实体 + 关系 + 修复） | 约 94.4 秒 | 34 次调用：实体 16 次（p50 8.5 秒）、小节关系 15 次（p50 10.5 秒）、修复 3 次（约 12 秒）；延迟总和约 330 秒，并发 4 的理论下限约 83 秒 |
| 直通融合与入库（merging） | 约 45.7 秒 | 与模型无关；后来 course1 实测 6.5 秒、另一次 15.6 秒，**根因一直 OPEN** |
| 合计 | 141.7 秒 | 正式模式另一次实测 114 秒（`docs/handoffs/deepseek-formal-loop-20261009.md`） |
| 发布（publish，含向量化） | 21.2 秒 | 不计入「生成」，但教师端体感相关 |

## 2. 代码现状（Claude 阅读结论，需你核实）

- `src/backend/app/workers/extract_task.py`：
  - 块阶段用 `_Dispatcher`（`ThreadPoolExecutor`，上限 `LLM_MAX_CONCURRENCY`，默认 **4**）逐块调用实体抽取；补漏 `gleaner` 在 personal 工具包里没有装配（`workers/toolkits.py`），即每块 1 次调用。
  - **小节关系阶段要等全部块结束才开始**（第二个 `_Dispatcher`），两段之间是屏障：最慢的一块拖住所有小节。
  - 每块、每节一个 SQLite 检查点事务（`_write_unit`），并读取消标志。
- `src/backend/app/services/chunking.py`：`DEFAULT_TARGET_CHARS = 1500`，但按章节路径切分，示例章节的块平均只有约 360 字，调用次数多、每次固定开销占比大。
- `workers/toolkits.py`：`MAX_OUTPUT_TOKENS = 4096`；`thinking_body(binding.disable_thinking)`，**默认不关闭思考**（DeepSeek 思考模式会明显增加延迟，ADR-090）。
- `workers/persist_graph.py`：节点与关系已按批 `UNWIND` 写入；`run_persist_stage` 已有一行 `persist steps` INFO 日志（candidates / plan / chunks / lock_wait / lease_check / neo4j / t6 / lock_release / task_release / total 毫秒），但**还没有人用它定位过慢段**。
- `services/ai/embeddings.py`：按 `EMBEDDING_BATCH_SIZE`（默认 10）**逐批串行**请求（约 223 行循环）。
- `workers/runner.py`：空闲轮询 `IDLE_SECONDS = 2.0`；需核实阶段之间是否在同一次领取里连续推进，还是每阶段重新排队、最多多等 2 秒。

## 3. 任务

### P0 先测量，再动手（必做）

1. 用**本机假供应商**复现结构性耗时，不花钱：`scripts/fake_provider.py`（OpenAI 兼容，支持请求头 `X-Fake-Delay` 或 `sk-fake-slow`），给每次调用固定延迟（建议 8 秒，接近真实 p50），跑示例章节，记录：每块/每节的开始与结束时间、排队等待、两阶段之间的空等、merging 各步（`persist steps` 日志）、阶段交接的轮询等待。
2. 产出一张「时间都花在哪」的分解表（假供应商与历史真实数据并列），写进交接与 `evaluation/reports/`。
3. 真实模型复测会产生费用，**必须先问用户并确认预算**，不要自行调用付费模型。

### P1 不影响抽取质量的优化（做完一项测一项）

1. **去掉块阶段与小节阶段之间的屏障**：某个小节的全部块完成后立即派发该小节的关系抽取，与其余块的实体抽取共用同一并发池；检查点、取消、阈值判定（失败块比例超限提前终止）、接管续跑语义不变。
2. **并发上限**：评估把 `LLM_MAX_CONCURRENCY` 默认值调到 8（或按供应商可配），验证 429 限流与熔断（`services/ai/policy.py`）行为正确、预算计数不变。改默认值属于配置变更，写进 ADR 与 `.env.example`。
3. **merging 慢段**：用 `persist steps` 定位是锁等待、Neo4j 往返、批大小、索引还是 SQLite 读；必要时用 Neo4j `PROFILE` 看写入语句。只做不改结果的修复（批量、索引、减少往返）。
4. **阶段交接**：若每阶段都要重新排队，改为同一租约内连续推进或在提交后立即唤醒，避免 2 秒轮询。
5. **发布向量化**：在不超过供应商限流的前提下并发批次（有界并发），保持缓存、记账（`model_calls`）、截止时间语义（ADR-082 决定 3、决定 6）不变。
6. **修复调用**：统计输出不合规的原因；若可在不改提示词语义的前提下减少修复（例如供应商支持时用 JSON 输出模式），先用离线夹具回归，再列为候选。

### P2 会影响质量的方案（只评估、给数据，**不得直接改默认行为**，交用户决定）

- 合并过小的块（例如同一章内凑到接近 1500 字）以减少调用次数。
- 抽取任务默认关闭思考模式。
- 实体与关系合并为一次调用。

上述任何一项都可能改变抽取结果，而人工准确率已签收（course1 实体 64/76、关系 58/61；course2 实体 61/68、关系 45/58，≥70% 是赛题硬指标）。如要采用，必须先给出离线/假供应商对比与真实小样本对比，写进 `docs/tasks.md` 未决项，由用户拍板。

## 4. 约束

- 不改接口契约、任务状态机、SSE 事件格式（`src/contracts/`）；不改抽取提示词与输出校验规则（P2 经用户同意除外）。
- 检查点、取消生效时延、失败阈值、租约丢失、凭据失效（ADR-080/082）等现有行为必须保持；改并发相关代码先补能复现的测试（线程交错、取消、阈值提前终止、接管续跑）。
- 不新增或升级依赖；不放宽、删除测试断言；不调用付费模型（除非用户批准）。
- 只在 `codex/extraction-perf` 本地提交，每类改动单独提交；不推送、不开 PR、不合并。

## 5. 验收与交付

- 每项改动后：`scripts/verify/backend.sh full`、`./scripts/verify.sh`（basic；涉及 Neo4j 写入时跑 integration）、前端 type-check 与 vitest（如有前端改动）。
- 假供应商固定 8 秒延迟下，示例章节上传 → 待审核的前后对比；目标结构性耗时（非模型部分）显著下降，并给出按 P1 每项拆分的收益。
- 在 `docs/tasks.md` 认领 EXTRACT-PERF-01，写验收证据；交接写 `docs/handoffs/codex-extraction-perf.md`：分解表、每项改动的收益、未采用方案及原因、需要用户决定的事项（真实复测预算、P2 方案）。
