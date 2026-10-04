# 冲刺计划 C：可靠性、性能与技术冻结（第三阶段）

```text
status: 用户 2026-10-03 确认，逐任务执行中
owner: Claude（本地代码与测试）；DeepSeek harness（真实生成与在线向量测量）；用户（预算、人工判定、策略决定）
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34
branch: claude/plan-c-reliability（自 ec1291a 新建；包含 9ca6e88 功能基线）
base: ec1291a
inputs: docs/handoffs/codex-claude-plan-c-start-prompt-2026-10-03.md、docs/handoffs/codex-plan-b-closeout.md、
        docs/reviews/codex-plan-b-96f3885-closeout.md、ADR-080～088
```

## 0. 范围与边界

- **九类参赛材料暂缓**（ADR-088），不作为本阶段任务或完成条件。测试集、原始输出、准确率判定、性能证据、预算台账和技术交接照常保留。
- **美化轻量化**（用户 2026-10-03）：本阶段不做视觉重设计；C05 只修与功能相关的界面缺陷。技术指标达标后由用户另开前端设计任务。
- 不做：自动出题、题库、判分；3D；跨课程融合与完整消歧；管理员统一生成模型配置；大规模重构；未经确认升级依赖。
- 不重复第二阶段已完成的工作：D1–D3、B-R1～B-R6、L15、2048 上限（ADR-086）。
- **付费调用**：本会话不发真实生成或在线向量请求。每轮由 DeepSeek 执行，交接写明题目、资料、模型、次数、增量止损与累计上限，经用户确认后才运行。最新已知生成累计 648168 / 5000000，向量 11943 另计。
- **环境**：独立端口 18100 / 15273 / 17788 / 17789 / 18990；一次性 Neo4j；隔离 SQLite。不在测量工作区运行脚本，不读凭据，不停共享服务。
- **执行纪律**：默认单会话顺序执行。每项按「失败测试 → 最小修复 → 回归 → 本地原子提交 → 看板 + `docs/handoffs/claude-cNN.md`」推进。接口、模型或语义变更先改规格/ADR/契约；生成物只由工具生成。不推送、不合并、不快进其他分支。

## C01 测量工具与预算分账（B-EVAL-01，纯离线）

- **C01-1 失败用例。** 用 `evaluation/raw/l15/codex-closeout-audit.json` 生成临时 SQLite 与 HTTP 响应夹具，覆盖：
  - 错误响应编号取 `details.request_id`；`outcome` / `error_code` / `error_reason` 分开记录，并与 chat_logs 关联；
  - `18:16:00.314Z` 落在起点 `18:16:00Z` 之内；有结束边界或固定请求 ID 集合，防止后续调用污染；
  - 生成与向量分账；缓存命中不新增账；中断、失败的尝试照样计费；缺失 usage 记为「未知」而不是 0；
  - 工具 exit 0 不等于所有题都答成功；
  - 离线重算必须得到 11 请求、19 调用 = 9 生成 + 10 向量、生成 28951、向量 59。
- **C01-2 实现。** 扩展 `evaluation/measure_web_flow.py`：
  - `ask` 保存脱敏后的完整结局；
  - 新增 `audit`：只读 SQLite（`mode=ro` + `query_only`），时间用 `julianday` 比较；
  - 输出逐题 JSON 与 p50 / p95 / 最大值、成功 / 未覆盖 / 失败数，注明分母与分位算法；
  - 硬止损只计生成 token，遇未知 usage 即停。
- **C01-3 首字三列。**
  - 客户端完整响应；
  - 服务端首个 delta（`chat_logs.first_delta_latency_ms`）；
  - 客户端 SSE 首个 delta：新增 `ask --stream`，用假 SSE 服务验证。
  - 浏览器可见首字未实测时写「未测」。
- **文件**：`evaluation/measure_web_flow.py`、`evaluation/README.md`、`tests/tooling/test_c01_measure.py`、`tests/backend/test_l02_measure.py`（回归）。
- **验证**：新增与回归用例；`./scripts/verify.sh basic`。
- **风险**：误读真实库。工具只接受显式路径，且只读打开。
- **回滚**：revert，不涉及数据。

## C02 问答稳定性（B-QA-01）

- **C02-1 离线定位（只出诊断，不改代码）。** 用比较题「栈和队列有什么区别」与 course1 Markdown，在演示检索下装配同一提示词，统计：
  - 资料块数、上下文 token、图谱上下文长度；
  - 规则 1「每句标注」带来的冗长；
  - 2048 输出是否包含思考 token：核对客户端请求参数与 usage 字段，不凭猜测删除思考内容；
  - `chat_logs` 现有字段能否分出改写、向量、检索、生成首 delta 各段。
- **C02-2 最小修法（先给理由、成本、ADR 草案，经用户确认后实施）。**
  - 预计方向：提示词 v3（比较题按要点对照、限长，每句仍要有出处）和/或资料去冗余。
  - 先红后绿；同步提示词版本与 `prompts/MANIFEST.md`。
  - 回归覆盖：截断仍判 `error/truncated` 并撤回；JSON 与 SSE 一致；15 秒总截止；请求中断；切课换号；auth / upstream / timeout；多轮历史；预算边界。
  - 不擅自放宽校验或超时，不加自动重试，不切模型，不再加大上限。
- **C02-3 分段耗时。** 优先用现有字段或结构化日志；必须加字段（迁移）时另写 ADR 并请用户确认。
- **C02-4 DeepSeek 交接。** 原十题加比较题重复 3 次。按上一轮十题约 29000 token 估算，建议增量止损 45000；累计上限由用户定。
- **候选文件**：`prompts/answer_with_context.yaml`、`src/backend/app/services/qa/generate.py`、`src/backend/app/services/qa/context.py` 及测试。
- **外部依赖**：用户确认 C02-2 策略与 C02-4 预算。

## C03 PDF 复测与 60 秒指标（B-PDF-01 / L16）

- **C03-1 DeepSeek 交接：修复后两份 PDF 各抽取一次。**
  - 记录 `headings/2`、repair、先修关系、孤立节点、耗时、usage。
  - 按 648168 起算，旧 850000 停止线只剩 201832，旧整轮预估 250000 会越线。建议先跑较小的 course2，单份止损 110000，看实耗再定 course1；也可由用户调整停止线。
- **C03-2 离线阶段分解。** 用 C01 工具，从任务时间戳与 `model_calls` 拆出排队、解析、分块、实体、关系、repair、融合入库各段；明确赛题「解析 + 知识抽取」口径，不靠排除真实 AI 耗时凑达标。
- **C03-3 最小优化。**
  - 按测得的瓶颈，先看 repair 率、输出冗余、重复上下文。
  - 并发或小节流水线只在测得瓶颈后提出，并先确认。
  - 保持任务取消、租约接管与重启、快照撤销、鉴权终止、DAG、来源完整性。
  - 候选文件：`src/backend/app/workers/extract_task.py`、实体/关系抽取服务及提示词。
- **C03-4 DeepSeek 修复后复测（预算另报）。** 首轮仍超 60 秒时，如实报告差距与下一步取舍，不缩成无代表性的资料。

## C04 新版本准确率（B-QUALITY-01）

- **C04-1** 用 `evaluation/evaluate_extraction.py sample`，对 `evaluation/raw/l11/` 未改写草稿冻结样本（种子、模型、提示词版本），生成判定模板。Claude 的辅助判定标为 `claude-assist`；**人工判定由用户签收**。
- **C04-2** C03 的新快照单独抽样、分开计算。实体、关系各自对照 70%；数量、类型覆盖、回答成功率不替代准确率。

## C05 剩余交互问题（轻量，不做视觉重设计）

- **C05-1** 教师有未保存编辑时，搜索定位先确认。取消则保持旧选择与视口；确认则选择与视口一起切换。覆盖换课、节点被删除。文件 `TeacherGraphView.vue` 及测试。
- **C05-2** 问答右栏长来源复用 `SourceViewer` 的 600 字折叠，保留文本渲染、文件名、位置与引用定位。
- **C05-3** 视口外的解锁节点：路径行名称可点击定位，不承诺全部节点同时可见。
- **C05-4** 同一章同时上传 PDF 与 Markdown 时，在上传页给出重复提示，不做融合。
- 原 L17 视觉美化移出本阶段，由用户在技术达标后另开前端设计任务。

## C06 技术门禁与冻结（L19 技术部分；L18 延期）

- 最终稳定 HEAD：相关测试、type-check / build、full、整次 integration（含演示与个人模式假供应商端到端）。实际 exit 0 才写通过，SKIP 与 PASS 分列，不删测试、不加跳过。
- 在新隔离目录（新 SQLite、一次性 Neo4j）从零启动，复测两条闭环。
- 真实性能与质量结论单列，来源为 DeepSeek 报告与人工签收。未达标保持 OPEN。
- 交接 `docs/handoffs/claude-plan-c-handoff-to-codex.md`：base/head、改动、PASS/SKIP/FAIL、真实指标、预算、未决项、下一步。

## 分工

| 执行方 | 内容 |
| --- | --- |
| Claude 本地 | C01；C02-1～3；C03-2～3；C04 抽样工具与辅助判定；C05；C06 |
| DeepSeek | C02-4、C03-1、C03-4（以及任何真实生成或在线向量测试） |
| 用户 | 各轮预算；C02 策略 ADR；C03 是否并发；C04 人工判定；合并或推送 |

## 回滚

每个子任务独立提交，可单独 revert。本计划预计不新增迁移；若需要，先写 ADR 与回滚步骤，交用户决定。
