# 计划 A 未完成项检查：V1 问答基线、V2 真实页面走查、V3 完整门禁

```text
task_ids: V1（L02 问答基线补测）、V2（L10 真实页面走查）、V3（业务改动后的完整门禁与端到端）
review_status: ready_for_review
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-contest-sprint-77644f
branch: claude/smartsketch-contest-sprint-77644f（草稿 PR arvinhanye/SmartSketch#317；仅本地提交，未推送）
base_commit: f1f4a71
head_commit: 本任务提交
author: DeepSeek harness
根据: docs/handoffs/claude-plan-a-verification-handoff.md
changed_files:
  - evaluation/reports/l02-baseline-2026-10.md（V1：状态改为「抽取与问答均已实测」，第 4 节重写为实测结果，第 5 节用量更新，第 6 节补发布与问答复现命令；第 1–3 节抽取数据原样保留）
  - docs/tasks.md（L02、L10 状态与验收证据；计划 A 一节追加 V3 结果）
  - docs/handoffs/deepseek-plan-a-verification.md（本文件）
```

三项都是验证，**未改任何业务代码、测试、契约、迁移或启动脚本**。发现的问题只记录在下面，未修。

## V1：L02 问答基线补测（`--live`）

**结论：通过；有一项与预期不符（第 3 题），已定位到可复现的产品缺陷。**

### 命令与结果

| 步骤 | 命令 | 实际结果 |
| --- | --- | --- |
| 启动 | `scripts/start-demo.sh --live --no-open` | API 8001 就绪、前端 5174 就绪；`LLM_MODE=live`、向量 `online` |
| 发布 | `POST /api/v1/courses/2ace598581f349ec9943dea90bc7fdf1/publish` | **HTTP 200，21.17 秒**，`version=1`、`node_count=82`、`edge_count=73`，排除项全 0，**没有** `PUBLISH_BLOCKED` |
| 加学生 | `POST …/members` `{"username":"demo_student"}` | HTTP 201 |
| 提问 | `evaluation/measure_web_flow.py ask`（4 题课内 + 1 题课外） | 见下表，exit 0 |

五题（一次运行，照实记录；`latency_ms` 与首字取自服务端 `chat_logs`）：

| # | 问题 | 结果 | 完整耗时 | 首字耗时 | 引用 |
| --- | --- | --- | --- | --- | --- |
| 1 | 什么是栈？ | `answered` | 6.12 秒 | 5.88 秒 | 1 |
| 2 | 循环队列如何判断队满？ | `answered` | 5.13 秒 | 4.70 秒 | 1 |
| 3 | 栈和队列有什么区别？ | **`not_covered`（`all_citations_invalidated`）** | 5.95 秒 | 无 | 0 |
| 4 | 入栈操作的时间复杂度是多少？ | `answered` | 2.19 秒 | 2.07 秒 | 2 |
| 5 | 光合作用的原理是什么？ | `not_covered`（`below_similarity_threshold`） | 0.40 秒 | 无 | 0 |

- **完整耗时：p50 5.13 秒、最大 6.12 秒。** 五题全部 ≤ 15 秒（赛题）且 ≤ 10 秒（S2 目标值），**达标**。
- **首字耗时：5.88 / 4.70 / 2.07 秒**，S2 目标 ≤ 3 秒，**三题中两题未达标，最大超出 2.9 秒**。
- 发布耗时 21.17 秒（向量化 82 知识点 + 16 文本块，在线向量的真实链路首用）。
- 发布同时把 V1 抽取留下的任务 `205f9311572846b8bc192ff1f67e244f` 从 `awaiting_review` 推进到 `completed`，与 ADR-010 决定 2 一致（附带观察，非本次要求）。

### 发现 1（产品缺陷，未修）：比较类问题被整篇撤回

第 3 题本应 `answered`，实际 `not_covered`，而**资料确实讲了这个区别**（`datasets/demo/ch3-stack-queue.md:71` 整段就是「二者的区别只在于允许进行插入和删除的位置不同……适合用栈……适合用队列」）。证据链：

| 证据 | 值 |
| --- | --- |
| `chat_logs.reason` / `invalidation_subtype` | `all_citations_invalidated` / `no_markers` |
| `chat_logs.truncated` | `1`（生成被截断） |
| `chat_logs.unknown_citation_count` | `0`（不是引错来源，是没有任何引用标记） |
| 该次 `model_calls.usage_output` | **1024，正好等于上限** `ANSWER_MAX_OUTPUT_TOKENS`（`src/backend/app/services/qa/generate.py:116`） |
| 同批第 1、2、4 题输出 | 464 / 858 / 246，均未触顶 |

因果：比较类问题作答更长 → 输出撞上 1024 上限被截断 → 截断前没有产生任何引用标记 → `services/qa/citations.py:286` 判 `no_markers`，按 ADR-003 的硬契约整篇撤回。注意 `truncated` 只被记录、**不参与**该分支判定，所以即使内容正确也会被撤回。

复现（确定性，不是抖动）：同一问题再问一次，`outcome`/`reason`/`invalidation_subtype`/`truncated`/输出 token 逐项相同。该次复跑只作诊断，不计入上表基线数字。

### 发现 2（记账缺口，未修）：发布期向量调用未写入 `model_calls`

ADR-011 修订 2 决定 12 要求每次实际发出的供应商调用（LLM 与向量）都预写一条 `model_calls`。本次发布确实调用了向量服务（Neo4j 上 82 + 16 个节点已带向量、发布耗时 21.17 秒），但 `model_calls` 中 `task_id IS NULL` 只有 5 条 `answer_with_context`，**没有任何向量用途的行**。后果：向量用量对预算不可见。

### 用量（V1）

`answer_with_context` 5 次（4 次基线 + 1 次诊断复跑）= 输入 12485 + 输出 3616 = **16101 token**；发布向量未记账，按被向量化文本 9783 字符估算约 0.65～1 万 token（估计值）。

### 证据路径

`.demo/logs/l02-ask.jsonl`、`.demo/logs/l02-questions.txt`、`.demo/logs/verify-l09-handoff.log` 同级目录；报告正文 `evaluation/reports/l02-baseline-2026-10.md` 第 4、5 节。

## V2：L10 真实页面走查（personal 模式）

**结论：六步全部符合设计。**

用 `scripts/start.sh --no-open` 启动（`runtime_mode=personal`、`configured=false` 已先行核对），用真实 Chromium（Playwright，`PLAYWRIGHT_CHROMIUM_EXECUTABLE` 指向本机 Chrome）驱动 `http://localhost:5174`。密钥纪律：DeepSeek key 只在内存中从 `.env` 读出后填入密码框，**未出现在命令行、日志、截图或本文件**；截图存 `.demo/v2/`（Git 忽略）。

| 步 | 实测结果 | 截图 |
| --- | --- | --- |
| 1 | 侧栏「模型 API 设置」可见且带「未配置」；资料页显示引导「上传前需要先配置你的模型 API…去设置」，上传按钮禁用。**personal 模式下没有演示模式标识**（符合设计） | `01-teacher-sidebar.png`、`01b-teacher-materials-guide.png` |
| 2 | 填 DeepSeek 地址 + `deepseek-flash` + key → 测试连接**成功（585 毫秒）** → 保存 → 状态「已配置：deepseek-flash · 密钥 ••••+末 4 位」（末 4 位只在 `.demo/v2/` 的截图里，不写进本文件），密钥输入框清空；**刷新后仍为脱敏状态、密钥框仍为空**、侧栏「未配置」标记消失 | `02-settings-saved.png`、`02b-settings-after-reload.png` |
| 3 | `localStorage`/`sessionStorage` 只有 1 个键 `smartsketch.session`（登录令牌），**不含密钥**；抓到 6 次 `GET /api/v1/me/model-config` 全部 HTTP 200 且**响应体不含密钥**（形如 `{"runtime_mode":"personal","configured":true,…,"key_hint":"<末 4 位>",…}`）；`PUT` 响应同样不含密钥 | `03-storage-and-network.png` |
| 4 | 上传 `tests/fixtures/documents/stack-queue-notes.md`（1002 字节）→ 任务推进到**待审核**（任务 `ca973a357979431bba2f2b4d587e2d5c`，服务端 `stage=awaiting_review` 一致） | `04-upload-awaiting-review.png` |
| 5 | `demo_student` 登录 → 问答页显示引导且发送禁用；保存自己的配置后引导消失，提问「什么是栈？」得到**带引用（1 条）的回答** | `05a-student-chat-guide.png`、`05b-student-answer.png` |
| 6 | 教师清除配置 → 状态变「尚未配置」；资料页重新显示引导、上传按钮禁用、侧栏「未配置」标记回来；直连接口上传返回 **HTTP 409 `MODEL_CONFIG_REQUIRED`** | `06a-clear-confirm.png`、`06c-step6-recheck.png` |

**关于第 6 步的一次 FAIL**：首轮自动化跑出 `10/11 通过`，唯一 FAIL 是第 6 步断言「资料页引导存在」为 false。核对截图后确认**是我的脚本竞态**——我在 `[data-test="materials-page"]` 出现后立即断言，而引导在 `pageStatus` 离开 loading 后的 `v-else` 分支里才渲染，截图本身显示引导是存在的。已用修正后的等待条件单独复检第 6 步：**PASS**（引导、去设置链接、按钮禁用、侧栏标记、409 全部符合），复检脚本只加载页面、不产生模型调用。**产品无此缺陷。**

### 用量（V2）

上传抽取任务 `ca973a357979431bba2f2b4d587e2d5c`：`extract_entities` 6 次 + `extract_relations` 5 次 + `repair` 1 次 = 输入 7509 + 输出 12311 = **19820 token**；学生提问 1 次 = 输入 2502 + 输出 753 = **3255 token**。合计 **23075 token**。另有 2 次「测试连接」（输出上限 1 token，按 ADR-080 不计入 `model_calls`）。

## V3：完整门禁与端到端

**结论：通过，退出码 0，无失败项。**

```bash
PYTHON=.venv/bin/python PATH="$PWD/.venv/bin:$PATH" \
PLAYWRIGHT_CHROMIUM_EXECUTABLE="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  ./scripts/verify.sh integration > .demo/logs/verify-integration-planA.log 2>&1; echo "integration=$?"
# → integration=0
```

| 档位 | 实际结果 |
| --- | --- |
| 基础档（骨架 + 钩子 + 契约） | `block-dangerous hook tests passed.`；`PASS contracts`：OpenAPI 3.1.0、32 条路径 / 129 个 schema / 385 处 `$ref`；B14 生成与漂移回归通过、门禁负向测试 25 项通过；B08 5 / B09 5 / B10 45 / B12 125 / B13 53 全通过 |
| 后端全量 | **3648 passed, 27 skipped**（13:05）→ `PASS backend gate (full)` |
| 前端全量 | 26 个文件 **782 passed** → `PASS frontend gate (integration)` |
| 集成用例 | **392 passed, 4 skipped**（13:35）→ `PASS integration gate (integration)` |
| 图库后端用例 | **44 passed**（41.41 秒）→ `PASS backend-live gate (integration)` |
| 端到端 | **2 passed (2.4m)**：`student.spec.ts`「学生浏览已发布图谱、标记掌握、获得推荐并得到带出处的回答；看不到草稿与他课」52.5 秒；`teacher.spec.ts`「教师上传四格式资料、编辑并审核图谱、拒绝成环关系，发布后学生可见」1.2 分钟 → `✓ 端到端通过` |
| 总结 | `Verification (integration) passed.`，退出码 0 |

- 端到端用演示模型，不产生费用；本次 `verify.sh integration` 未产生任何真实模型调用。
- 证据：`.demo/logs/verify-integration-planA.log`、端到端运行目录 `.e2e/20261003-030121/`（报告提到的失败才需保留，本次无失败）。
- **无失败清单**，因此没有需要保留的失败证据，也未修改任何代码或测试。
- 说明：`PATH` 前置 `.venv/bin` 与更宽的沙箱权限都是环境要求——契约门禁硬编码 `python3`（`deepseek-l09.md`「环境与沙箱」第 2 条），`tests/tooling/test_k07.py` 的 4 个交互式用例在受限沙箱下会被拒绝分配 PTY（同上第 1 条）。放宽后这两项均通过；本次后端全量 3648 passed 与 L09 的记录完全一致。

## 累计计费 token

| 段 | token |
| --- | --- |
| L02 抽取（2026-10-02） | 101054 |
| V1 问答（含 1 次诊断复跑） | 16101 |
| V2 上传抽取 + 学生提问 | 23075 |
| **小计** | **140230 / 5000000** |
| 未记账（发布期向量，估计） | 约 0.65～1 万 |

## unverified

- 发布期向量 token 无实测值（未记账），报告里只有字符数估算。
- 问答第 3 题的缺陷只做了触发与定位，未做修复验证（按本轮边界不修）。
- PDF 格式抽取仍留给 L11；抽取准确率仍无人工判定。
- 主检出（8000/5173/7687）全程未触碰。

## api_and_data_changes

无。三项都是测量：未新增/修改接口、契约、迁移与业务代码。副作用仅限冲刺工作区的本地数据（课程 `2ace598581f349ec9943dea90bc7fdf1` 已发布为 v1 并加入 `demo_student`；新增一份资料与一个任务；`demo_teacher`、`demo_student` 各自保存了个人模型配置 —— 后者在 V2 第 6 步已清除教师那份，学生那份保留）。

## rollback

回退本提交即可（只有一个报告、一个交接与 `docs/tasks.md` 的状态行）。本地数据可用 `scripts/backup-demo.sh` 或直接忽略，不影响主检出。

## next_action

1. **修「比较类问题被整篇撤回」**：建议单独认领——先写复现测试（较长的比较类回答撞上 1024 上限即被撤回），再决定是提高 `ANSWER_MAX_OUTPUT_TOKENS`、在截断时改判（例如按已有片段给部分回答）、还是让引用标记更早出现。
2. **补发布期向量记账**（ADR-011 修订 2 决定 12），否则向量成本无法核对。
3. 首字耗时 2/3 未达 S2 的 ≤3 秒目标，需要与「完整耗时已达标」一起评估优化顺序。
4. 推送与合并待用户授权。
