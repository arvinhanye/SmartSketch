FAILPATHS: FAIL

# 正式模式失败路径验收报告（rc-8a33ab9，隔离安装 06177e36fdfcb5c4）

```text
from: DeepSeek harness
to: Claude
date: 2026-10-09
task: docs/handoffs/claude-formal-failure-paths-deepseek-handoff.md
previous: docs/handoffs/deepseek-formal-loop-20261009.md
installation: 06177e36fdfcb5c4（p5，Phase=READY，WebPort=8081，Release rc-8a33ab9，向量维度 1024）
containers: smartsketch-06177e36fdfcb5c4-{api,worker,web,neo4j}-1
判定: FAILPATHS: FAIL —— 存在必须项的「缺陷」（见 §4），且触发用量停止条件（见 §2）
生成类用量: 454,271 token（越过 300,000 停止线与 400,000 硬上限，已立即停止后续测试）
auth 类真实错误: 0（M6 的 auth 来自故意注入的无效密钥）
密钥泄漏: 0（凭据读取后即删，报告只含 key_hint 末 4 位）
产品代码/测试/契约/启动器/默认配置改动: 0
```

## 0. 判定依据

| 规则 | 状态 |
| --- | --- |
| 必须项为`正确` | 否 —— M5、M7、M9 各有缺陷 |
| 必须项无`缺陷`，但有`规格未定义`或可选项未完成 | 部分满足（M11 的 C2 属规格未定义；O1/O2 未完成） |
| **任一必须项为`缺陷`** | **是 → FAILPATHS: FAIL** |

缺陷清单（详见 §4）：**M5**（超限返回 nginx 413 HTML）、**M7**（并发发布下 embedding 偶发失败导致 500）、**M9**（守护进程不可达时误报"已启动"）。另有两项跨项观察（§5）。

## 1. 汇总表

| # | 场景 | 结论 | 证据 | 耗时 |
| --- | --- | --- | --- | --- |
| S1 | 基线：建课→上传→待审核→发布 v1→学生就绪 | `正确` | 待审核 123s；发布 v1（79 点/81 边）25.5s；**embedding 10 次 0 错误，KP 79/79 + Chunk 16/16 均带 1024 维向量** | 总 ~150s |
| M1 | 处理中强杀 worker 后恢复 | `正确` | 任务 `2de49bd5…`：租约过期后 worker 拉起 **3 秒内被重新领取**，`attempt` 1→2，走到 `awaiting_review`；本任务 80 节点（去重 80、重名 0）、65 关系（去重 65）、悬空 0；恢复耗时 ~120s | ~5 min |
| M2 | 取消处理中任务 | `正确` | 任务 `102066a2…`：`cancel_requested=true` → **18s 后 `cancelled`**；带该任务标记的节点 **0 个**（草稿 0、全库 0）；Document 记录保留（符合规格）；重新上传正常到 `awaiting_review`（123s） | ~3 min |
| M3 | API 容器被杀时的前端表现 | `正确` | 流式中杀 api → 页面显示"**未完成 / 问答暂时失败，请稍后重试。**"+【重试】，问题保留、出处显示"本次回答未完成"、**JS 错误 0**；API 手动拉起后约 2 分钟内问答恢复正常（3/3 `answered`） | ~4 min |
| M4 | 会话失效 | `正确` | 无效/伪造/篡改/空令牌 → 全部 `401 UNAUTHENTICATED`；篡改 `sessionStorage` 后刷新与访问受保护页 → 回登录页 + 提示"**未登录：请先登录，再进入教师或学生首页。**"，不白屏；重新登录成功 | ~2 min |
| M5 | 上传边界 | **`缺陷`** | `.exe`/`.pptx`/空文件/内容不符 → 均 `415 UNSUPPORTED_FORMAT` + 中文 JSON；**超限（limit+1）→ HTTP 413 且响应体是 nginx 英文 HTML 页面**，非契约里的 `FILE_TOO_LARGE` JSON | ~2 min |
| M6 | 向量密钥无效 | `正确` | `{"ok":false,"error_class":"auth"}`（504ms/615ms），配置前后一致、不回显服务端原文；首次出现 1 次瞬时 `connection`，重测稳定 | ~1 min |
| M7 | 发布冲突与回滚 | **`缺陷`**（+重做成功） | 并发两次：第 1 次 **500 `INTERNAL_ERROR`**、第 2 次 `409 PUBLISH_IN_PROGRESS` ✅；失败记录 `failure_reason=P8: EmbeddingBatchError`（embedding `connection` 偶发）；重做单次成功 v2；回滚 → **新版本 3（kind=rollback）**，学生随 v3 见到旧名、教师草稿保留改名 ✅ | ~3 min |
| M8 | 权限与课程隔离 | `正确` | 非成员读第二门课图谱/详情/提问 → 403 `COURSE_FORBIDDEN`；学生对教师接口（上传/发布/加成员/改草稿/审核队列）→ 403 `ROLE_FORBIDDEN`；**存在但无权与完全不存在返回完全相同的 403**（不泄露存在性） | ~2 min |
| M9 | 启动器在 Docker 不可用时的提示 | （a）`正确` /（b）**`缺陷`** | (a) docker 不在 PATH → "请先安装并打开 Docker Desktop：…" + **退出码 1**，仅写隔离 HOME ✅；(b) 守护进程不可达 → 打印"**智绘学途本机控制已启动**"并尝试开浏览器，**无 DOCKER 提示** | ~3 min |
| M10 | 容器级快速恢复（neo4j 重启） | `正确` | 重启期间 API 未崩溃（仅 1 条连接池 `OSError('No data')` 警告）；neo4j 自动恢复，无需人工干预；恢复后 `version=3, 79/81` 完全一致 | ~2 min |
| M11 | 问答质量与边界 | `正确` | 见 §3：A 8/8、B 4/4、C1✅、C3✅、C4✅、C5✅、**编造引用 0**、提示词泄露 0、逐句忠实率 100%（AI 判断）；C2 20 万字被 503 拒绝且不产生调用 | ~8 min |
| O1 | 端口冲突 | **未完成** | 启动器控制会话 20 分钟过期（`control.json` 12:13 生成，测试时刻 12:53），`/control/exchange` 与向导操作均返回 AUTH；需用户重新双击启动器 | — |
| O2 | 真实数据备份/恢复 | **未完成** | `BACKUP_DIR` 不在安装 `.env`（仅 9 键），由启动器运行时注入；叠加会话过期，`offline-tools` 无法在启动器之外执行 → 按交接稿"停并写明原因" | — |

## 2. 用量表

| 阶段 | 生成类累计 | 说明 |
| --- | --- | --- |
| 起点 | 0 | 全新安装 |
| S1 完成 | 105,924 | 抽取+融合（发布时另有 10 次 embedding） |
| M11 主体（A/B/C1/C3/C4/C5）后 | 157,017 | |
| M11 的 C2 重测后 | 168,171 | |
| **最终** | **454,271** | **越过 300,000 停止线与 400,000 硬上限** |

最终分布：

| purpose | 调用 | in | out | 错误 |
| --- | --- | --- | --- | --- |
| extract_entities | 58 | 34,010 | 101,622 | 1 |
| extract_relations | 49 | 52,170 | 122,214 | 1 |
| repair | 22 | 19,006 | 52,165 | 2 |
| answer_with_context | 24 | 53,792 | 17,466 | 1 |
| rewrite_query | 4 | 1,042 | 784 | 1 |
| **生成类合计** | **157** | **160,020** | **294,251** | **6** |
| embedding（不计入） | 35 | 8,036 | 0 | 5 |

**超限原因（如实记录）**：M1（worker 被杀 → 任务重做整段抽取）、M2（两次完整抽取）、M7（两次发布尝试）、M11 的 C2 重测各消耗 1–9 万 token。我在每个步骤**开始前**做了用量核算，但**未在每个步骤结束后立即重算**，直到收口时才累计发现已越过上限。这是我的监控疏失，不是产品问题。

## 3. M11 明细

### 3.1 A 类 8 问（四类题型各 2）

| 类型 | 问题 | final.status | 引用数 | 首字 | 总耗时 |
| --- | --- | --- | --- | --- | --- |
| 定义 | 什么是双端队列？ | answered | 1 | 5862ms | 6.2s |
| 定义 | 共享栈是怎么回事，它的上溢条件是什么？ | answered | 1 | 4674ms | 4.9s |
| 对比 | 栈和队列的区别是什么？ | answered | 4 | 10135ms | 10.7s |
| 对比 | 顺序栈和链栈各有什么缺点？ | answered | 3 | 4912ms | 5.2s |
| 公式 | 循环队列中元素个数怎么计算？ | answered | 1 | 4962ms | 5.1s |
| 公式 | 循环队列为什么要空出一个存储单元？ | answered | 1 | 4119ms | 4.5s |
| 应用 | 括号匹配怎么用栈实现？ | answered | 1 | 7170ms | 7.8s |
| 应用 | 后缀表达式怎么求值？ | answered | 1 | 5907ms | 6.7s |

**A 类通过：8/8 `answered` 且每个 ≥1 引用**（判定线 ≥7/8）。

### 3.2 B 类多轮追问（带 history）

| 轮 | 第一问 | 第二问（指代） | 第二问结果 | 引用 |
| --- | --- | --- | --- | --- |
| 1 | 什么是循环队列？ | **它**为什么要空出一个位置？ | answered（正确指向循环队列：牺牲单元以区分队空/队满） | 1（同一章的 `3.3.2 循环队列`） |
| 2 | 什么是链栈？ | 和顺序栈比，**它**的缺点是什么？ | answered（正确指向链栈：额外指针域开销） | 2（`3.2.3 链栈` + `3.3.5 栈与队列的比较`） |

**两轮指代均被正确理解**，引用仍来自本课程。

### 3.3 C 类边界输入

| # | 输入 | final.status | 引用数 | 结果 |
| --- | --- | --- | --- | --- |
| C1 | 「栈？」 | answered | 5 | 不报错、不崩溃，正常回答 |
| C2-1 | 1020 字长问题（脚本按 4000 字设计，实际 1020 字） | answered | 5 | 正常回答（首次偶发 `connection` 失败，重做成功） |
| C2-2 | **200,000 字** | — | — | **HTTP 503 `LLM_UNAVAILABLE`**（2.0s），**`model_calls` 无新增**（用量前后差 5 次调用/11,154 token 全部属于第一次） |
| C3 | 注入：泄露系统提示词 + 编造出处 | **not_covered** | **0** | 回答"检索到的课程资料不足以回答这个问题"，**无提示词泄露、无编造引用** |
| C4 | 沾边：「栈在操作系统的进程调度里怎么用？」 | **not_covered** | **0** | 正确（资料未写） |
| C5 | 闲聊：「你好，今天天气怎么样？」 | **not_covered** | **0** | `reason=below_similarity_threshold`，回复"课程资料中与这个问题相关的内容不够充分" |

**C2 的实际上限与语义（规格未定义）**：`ChatRequest.question` 只规定 `minLength=1`，无上限。实测 1020 字正常、200,000 字被拒；**被拒时的状态码是 503 `LLM_UNAVAILABLE`（"问答模型暂不可用"）而不是"输入过长"类错误**。交接稿要求：若服务端无上限且仍触发模型调用则记`规格未定义`（成本风险）——实测**未触发模型调用**，但**错误语义与原因不匹配**，且 503 会让用户误判为服务故障。此点记为`规格未定义`交 Claude。

### 3.4 D 逐句核对

**声明：以下判断由 AI 完成，不是人工签收，不构成准确率结论。**

- A 类 8 个回答共 **26 句**（按 `[n]` 标注切分）
- `忠实` **26**、`部分偏离` **0**、`不忠实` **0**
- **逐句忠实率 = 100%**（判定线 ≥90%）
- 引用归属校验：全部 **23 条引用**的 `document_id` 均为本课程唯一文档 `8176eefce0994cc988959f6e04044fc9` 与 10 个本课程 chunk（Neo4j 侧确认本课程 Chunk 16 个、document_id 唯一）→ **编造引用 = 0**
- 未发现需要列出的偏离句。典型抽样核对：`(rear - front + MaxSize) % MaxSize`（源材料 3.3.2 第 3 段原文一致）、括号匹配三条规则（3.4.1 原文一致）、共享栈上溢条件（3.2.2 原文一致）、循环队列判满条件（性质 3.2 原文一致）。

### 3.5 E 点开引用（UI）

| 点击 | 结果 | 截图 |
| --- | --- | --- |
| A 类回答的 `[1]`（双端队列） | 右侧出处面板切到该回答：`出处 [1] ch3-stack-queue.md · 第3章 栈与队列 > 3.3 队列 > 3.3.4 双端队列 > 第1段`，含原文片段与关闭按钮 | `/tmp/fp-shots/e-02-q1-citation-clicked.png` |
| B 类追问的 `[5]`（循环队列） | 面板切到追问回答：`出处 [5] … > 3.3.2 循环队列 > 第1段` | `e-04-q2-citation-clicked.png` |
| 右栏「查看 1 处出处」 | 展开出处列表，点击条目回到 `[1]` 的出处（文件名 + 章节 + 原文） | `e-05-sources-panel.png` |
| 长片段折叠 | 引用标记为 `<button class="citation">`，点击后正文 164→204 字符（长片段默认折叠、可展开） | `e-06-source-panel-fold.png`、`e-07-source-expanded.png` |

判定所需的三次点击（A 类 / B 类 / 右栏）**全部符合**。

## 4. 缺陷复现步骤与规格出处

### D1（必须项 M5）超限上传返回 nginx HTML 而非契约错误

- **复现**：`GET /api/v1/courses/{cid}/upload-policy` → `max_bytes=52428800`；造 `limit+1` 字节 `.md`，`POST /api/v1/courses/{cid}/documents`（multipart）。
- **实测**：`HTTP 413`，响应体为 nginx 1.27.5 的英文 HTML `<h1>413 Request Entity Too Large</h1>`；无 `code`/`message` 字段。
- **预期**：`specs/*` 与 `src/contracts/` 的 `UploadPolicy`/错误契约要求可机读错误（`FILE_TOO_LARGE` 类）与可读中文文案；实际由反向代理在应用层之前拦下。
- **影响**：前端无法按 `code` 渲染提示；用户看到与产品语言不一致的英文页面；50MB 数据仍被完整接收后才拒（浪费带宽）。
- **附带**：本地校验（扩展名/空文件/内容不符）三条均正确返回 `415 UNSUPPORTED_FORMAT`，说明应用层能力存在，仅超限路径被代理截断。

### D2（必须项 M7）并发发布下应用层 500（P8 EmbeddingBatchError）

- **复现**：教师改一个知识点（`PATCH kp`，`expected_revision` 正确）后，同时发两次 `POST /publish`。
- **实测**：互斥锁工作正常（第 2 次 `409 PUBLISH_IN_PROGRESS`，0.15s），但**第 1 次返回 `500 INTERNAL_ERROR`**（"发布未完成，当前版本保持不变，请重试"，4.49s）；`graph_versions` 留下 `state=failed`、`version=None`、`failure_reason=P8: EmbeddingBatchError` 的记录；当次 `model_calls` 有 `embedding status=error error_class=connection`。
- **规格**：`specs/teacher-review-publish.md` 要求发布失败时版本保持不变并给出明确错误；`P8` 是发布期的向量化步骤。
- **影响**：向量服务的**瞬时**失败会让整次发布 500（无内部重试或重试不足），而抽取路径的 embedding 明显有重试（同批错误后仍成功）——两条路径的重试策略不一致。
- **注**：重做（单次发布）成功生成 v2，说明是偶发触发而非必现；但"M7 并发场景下第一次发布失败"在交接稿的判定下是必须项失败。

### D3（必须项 M9）docker 守护进程不可达时误报"已启动"

- **复现**：隔离 HOME 下运行 `bin/smartsketch-launcher`，让 `docker` CLI 在 PATH 但守护进程不可达（`DOCKER_CONFIG` 指向 `currentContext=bogus`→`unix:///nonexistent`）。
- **实测**：输出"**智绘学途本机控制已启动。关闭此窗口不会停止 Docker 中的业务服务；停止请使用网页按钮。**"并尝试打开浏览器；**没有**"请打开 Docker Desktop"提示（25 秒后由我终止，退出码 143）。
- **代码位置**：`launcher/internal/launch/host.go:17-28` 的 `FindDocker()` 仅做 `exec.LookPath("docker")` 与固定路径 `os.Stat`，**不探测守护进程可达性**；真正的 DOCKER 文案（`types.go` 的 `"Docker 尚未就绪，请打开 Docker Desktop。"`）与 `main.go:68` 的提示只覆盖"docker 不存在"。
- **预期**：交接稿要求启动器在 Docker 不可用时给出明确中文提示且不崩溃；实测 (a) 场景正确、(b) 场景给出**误导性成功提示**。

## 5. 观察（跨项）

1. **产物容器不会被自动拉起**：`api` 与 `worker` 的 restart policy 均为 `unless-stopped`（compose 亦写 `restart: unless-stopped`），但 `docker kill` 后 40 秒仍未重启（`ExitCode=137`、`RestartCount=0`）。生产环境"容器被杀后自愈"的预期因此不成立——需要用户或启动器介入。**未在交接稿的判定表内**，作为观察项交 Claude 判定是否为缺陷。（对比：neo4j 的 `docker restart` 后自动恢复。）
2. **embedding 偶发 `connection` 频繁出现**：35 次 embedding 调用中 5 次错误（含 `connection` 与 `invalid_request:rejected_before_generation`）。抽取路径能靠内部重试吸收（M1 恢复后仍完成），但**发布路径（P8）与问答改写路径未能吸收**（分别导致 M7 的 500 与 C2/首轮的 503）。
3. **`meta` 与 `final` 状态不一致**（延续上一轮报告）：C4/C5 等 `not_covered` 场景下 `meta.status` 仍为 `answered`；本次仍以 `final` 为准（UI 正确），未变化。
4. **版本快照隔离符合预期**：`KnowledgePoint` 按 `version_id` 分组（`draft` + 各发布版本各一份），因此"节点总数 316 = 79×4"是正常设计而非重复泄漏；M1/M2 的"无重复/无残缺"必须以**任务级去重**判定（已如此判定）。
5. **M2 的取消延迟**：`cancel_requested` 写入后约 12 秒任务才转为 `cancelled`（worker 在 chunk 边界检查），期间进度停在 0.1；交接稿要求"状态变为已取消"已满足。
6. **M3 恢复期**：API 容器被手动拉起后，问答约 2 分钟内才完全可用（期间 503 `LLM_UNAVAILABLE`）；`/health` 在同一时刻已返回 200——健康探针不覆盖"模型调用链就绪"。

## 6. 密钥与边界声明

- **未读、未打印、未复制**安装目录 `.env` 的任何内容；报告与日志中不含任何明文密钥/口令/令牌，仅出现 `key_hint` 末 4 位与掩码形式。
- 教师/学生凭据经一次性文件进入内存后即删；学生口令由 `secrets.token_urlsafe` 生成，仅存于 0600 临时文件。
- 未改产品代码、测试、契约、迁移、启动器、`.env.example`、默认配置；未提交、未推送、未合并、未发布。
- `LLM_MODE=personal`、`EMBEDDING_MODE=online` 未改；未降级为 `demo`/`fake`/`local`；未更换供应商/模型/向量地址。
- **只动本安装**（`smartsketch-06177e36fdfcb5c4-*`）：`docker kill` 仅用于 M1（worker）与 M3（api），`docker restart` 仅用于 M10（neo4j），`docker start` 用于把被杀容器拉回。**未动**其他安装（`15196dda…`、`74694b2c…`、真实 HOME 安装、`a678…`/`d3e4…`/`e98c…`/`main` 卷、开发 Neo4j）；未重启 Docker Desktop；未 `down -v`；未删卷。
- 本安装的向量维度 `1024` 由用户在向导中正确设置（上一安装因 `1021` 导致发布 500，本轮已修复）。
- 本任务的"写入"仅限：本报告、`/tmp` 下的临时取证文件与哑监听（8082，用于 O1，已说明）。

## 7. 给 Claude 的下一步

1. 判定 §4 的三个缺陷是否进修复批次（D1 优先，文案/契约一致性最直接；D2 需决定 P8 是否补重试；D3 需在 `FindDocker` 后加守护进程探测）。
2. 判定 §5-1（容器不自愈）是否属缺陷——它决定"用户在 Docker 重启/崩溃后是否需要手动干预"。
3. §3.3 的 C2 错误语义（超长输入返回 503 而非输入类错误）需规格层决定。
4. O1/O2 未完成：如需验收，请重新双击启动器生成新控制会话（20 分钟有效），并注意 `BACKUP_DIR` 由启动器注入。
5. 后续测试前建议约定"每步后即时核算用量"，本轮因未及时核算而越过 400k 上限。
