# 计划 C（第三阶段）进度与移交 Codex

```text
from: Claude
to: Codex
date: 2026-10-04
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34
branch: claude/plan-c-reliability（用户确认自 ec1291a 新建；包含 9ca6e88）
base: ec1291a
head: 本交接所在提交（之前最后一个代码提交 bba1108 是 ADR-090）
uncommitted: 方案 B（ADR-090）的实现，见 §3.1，未提交、后端全量 1 例失败
plan: docs/superpowers/plans/2026-10-03-contest-sprint-c-reliability-performance.md
paid_calls_by_claude: 0（全部真实生成与在线向量测量由 DeepSeek harness 执行）
not pushed / not merged
```

## 1. 已完成并提交

| 任务 | 提交 | 内容与验证 |
| --- | --- | --- |
| C00 基线 | `005bf18` | 新分支；`verify.sh basic` exit 0；计划与看板认领 |
| C01 测量工具 | `fade07b` `76fcf89` `e709ccb` `312cccb` | `measure_web_flow.py`：<br>• `audit` 只读关联 `chat_logs` 与 `model_calls`：请求编号兼容 `details.request_id`，按 UTC 时刻 + 结束边界或固定请求 ID 筛选，生成与向量分账；<br>• 未知 usage 不当 0，止损按系统计费口径估算；<br>• 最近秩分位与分母；首字三列口径；分段耗时；推理列；<br>• `ask --stream/--out/--audit-db/--cap/--round-started-at`；`audit-task` 拆解抽取任务。<br>离线重算 L15：11 请求、19 调用 = 9+10，生成 28951，向量 59 |
| C02-1 诊断 | `ea278c1` | `evaluation/reports/c02-qa-diagnosis.md`：可见回答每字 2.9～17 个输出 token，推断为不可见推理占输出预算 |
| C02-2 A 推理埋点 | `0469bad`（ADR-089） `33177c0` | 迁移 017：`model_calls` 加四个可空列；只计字数与时刻，不存推理正文；回答与 SSE 不变 |
| C02-2 C 提示词 v3 | `088a601` | `answer_with_context` v3：直接作答、比较题逐点对照、通常不超过 300 字；出处规则不变 |
| 阶段耗时日志 | `f8c549f` | 问答 `chat prepare phases`、worker `task stage done`；只写 INFO，不改行为、无迁移 |
| 方案 B 前置探测 | `8f0fc14` `bae1948` `407e980` | `evaluation/probe_thinking.py` 与交接；探测结果后的修补：区分连不上与字段被拒，https 优先 certifi |
| C04-1 准确率工具 | `ef39f98` | `draft_to_predictions.py` 与 `evaluate_extraction.py judge-report`（无金标；`claude-assist` 判定标为非人工验收）。工作表在 `evaluation/raw/c04/` |
| C05 交互修复 | `ce378bc` `1a8da3f` `c7f15e4` `3101b54` | 未保存修改时搜索定位先确认；问答出处用 `SourceViewer` 600 字折叠；路径行「之后解锁」可点击定位；同章不同格式重复上传提示 |
| 文档 / 复核 | `458b961` `b16b759` `e24739b` `bba1108` 等 | DeepSeek 测量交接、两轮复核记录、ADR-090 |

最近一次完整验证（`e24739b` 之后、方案 B 之前）：
- 后端全量 3838 passed / 27 skipped（已登记）；
- 前端全量 37 文件 911 passed，type-check、build 通过（chunk 体积告警为既有）；
- **整次 `verify.sh integration` 本阶段尚未运行。**

## 2. DeepSeek 真实测量结果（已复核）

| 轮次 | 提交 | 结论 | 复核 |
| --- | --- | --- | --- |
| C02-4 问答 v3 | `16d9ebd` | 只测 1 题即停（冷启动首问超时；当时 usage 未知止损规则过严，已由 `312cccb` 修正）。推理埋点有值 | `docs/reviews/claude-deepseek-c02-4-c03-1.md`：查询向量后有 8.15 秒无调用记录的空档，样本只有一个，不推广为链路结论 |
| C03-1 course2 PDF | `72fed5e` | PDF 修复生效：关系 25→59、`PREREQUISITE` 0→5、孤立 39→3；83522 token；91.34 秒，仍超 60 秒 | 抽取输出 80% 是推理；两次关系调用 4096 全是推理，引发 2 次 repair；末次模型调用到待审核还有 15.6 秒未归因 |
| C02b 思考参数探测 | `3d38015` | 只有 `thinking: {"type": "disabled"}` 有效：推理 1121 字 → 0、输出 512 → 49、2895 → 513 ms；另三种字段被静默忽略 | 已核对原始行，未见密钥 |

预算（生成；向量另计 11946）：
- 系统计费口径 **746357 / 5000000**：743806 + 探测 2551，探测直连不进 `model_calls`，为手工台账；
- 记录口径 734241：只计已知 usage。

用户批准过的累计上限 803168 尚余约 56800。**下一轮付费测量需要用户另批预算。**

## 3. 未完成的任务

### 3.1 方案 B（ADR-090，「关闭模型思考」）：已实现、未提交，后端全量 1 例失败

用户 2026-10-04 批准进入方案 B；ADR-090 已提交（`bba1108`）。工作区里未提交的改动：

| 文件 | 内容 |
| --- | --- |
| `src/contracts/api.v1.yaml` 与三份生成物 | `ModelConfig` / `ModelConfigUpdate` / `ModelConfigTestRequest` 增加可选 `disable_thinking`；生成物由 `scripts/gen-contracts.sh` 生成（exit 0），未手改 |
| `src/backend/migrations/018_model_config_disable_thinking.sql` | `user_model_configs`、`task_model_bindings` 各加 `disable_thinking INTEGER NOT NULL DEFAULT 0` |
| `src/backend/app/services/ai/compatible.py` | `THINKING_DISABLED`、`thinking_body()`、构造参数 `extra_body`（深拷贝；不得覆盖 `model`、`messages`、输出上限、`stream`、`stream_options`、`response_format`） |
| `src/backend/app/repositories/model_configs.py` | 保存（省略保留已存值，新建默认关）、读取、任务快照都带开关 |
| `src/backend/app/services/model_configs.py`、`api/model_config.py` | 保存与连接测试都传开关：测试表单按表单值，测试已存配置用已存值 |
| `src/backend/app/services/qa/user_models.py`、`workers/toolkits.py` | 问答与抽取按开关构造客户端；抽取用任务快照的值 |
| `src/frontend/src/composables/useModelConfig.ts`、`views/ModelSettingsView.vue` | 复选框「关闭模型思考」与说明。开关与已存值不同才发送；测试已存配置但开关已改时先要求保存（与 N05 同一原则） |
| `tests/backend/test_c02b_disable_thinking.py`、`tests/frontend/l10.test.ts` | 后端 10 例：惰性桩后 10 例全红，实现后全绿；前端 2 例先红后绿 |
| `docs/runbook.md` | 增加一行开关说明。这次写入是在用户中断那条命令时已经执行的，内容与 ADR-090 一致；是否保留由接手者决定 |

验证现状：
- 定向：`test_c02b_disable_thinking` 加 L06/L07/L08/N01-N06/N07-N08/E03/J10 回归共 384 passed；`l10` + `n03-n05` 29 passed；type-check exit 0。
- **后端全量（含 `tests/contracts`）：1 failed / 4153 passed / 27 skipped。** 失败的是 Claude 自己在 C02-2 写的 `tests/backend/test_c02_reasoning.py::test_migration_017_adds_nullable_reasoning_columns`：它断言「最后一个迁移是 017」，加了 018 后必然失败。与 `test_j10` 曾经的问题相同。
  - 修法：把 `assert files[-1].startswith("017_")` 改为 `assert any(f.startswith("017_") for f in files)`，或与迁移目录编号最大的文件比较。属测试写法问题，不是行为缺陷。
- **未运行**：改动后的前端全量、build、整次 integration（含个人模式假供应商端到端）。
  - 假供应商 `scripts/fake_provider.py` 只读 `messages` / `max_tokens` / `response_format`，预计忽略 `thinking` 字段，未实测。

接手步骤建议：
1. 修上面那个断言；
2. 后端全量；
3. 前端全量、type-check、build；
4. 确认后按「契约与迁移与后端」「前端」「运行手册」拆成原子提交；
5. 更新 `docs/tasks.md` 与 `docs/handoffs/claude-plan-c-c02.md`。

### 3.2 方案 B 的真实验证（需用户批预算，交 DeepSeek）

建议一轮内做两件事：
- 抽取：用开关开启重跑 course2 PDF；再按用户先前决定，在 B 完成后跑 course1 PDF；
- 问答：十题加比较题 3 次。开跑前做一次不计统计的预热请求，避免冷启动混入。

开关开 / 关的对照可只做比较题。对照指标：输出 token 与推理 token、repair 次数、抽取总耗时与各阶段（用 `audit-task` 和新的阶段日志）、问答截断率与首字。

粗估：
- 关闭思考后输出约降为原来的 1/5，单份 PDF 可能 3～4 万 token，问答一轮约 1～2 万；
- 现余额度 56800 不够两份 PDF 加问答。请用户定新的累计上限，按单份止损 + 整轮止损执行。

### 3.3 C02-4 重跑（问答 v3）

没有完成原计划的 13 题。等方案 B 提交后与 §3.2 合并为一轮。工具已修：未知 usage 计估算，不再整轮停止；`--round-started-at` 共用整轮止损。

### 3.4 C03-2 / C03-3（60 秒指标）

- 已有：`audit-task` 与阶段耗时日志（`f8c549f`）。
- 未有：两段未归因时间的定位——问答首问查询向量后的 8.15 秒、抽取末次模型调用后的 15.6 秒（后者包括融合与入库，或在等课程锁）。需要下一轮真实运行的 worker / api 日志。
- 60 秒仍未达：C03-1 为 91.34 秒。方案 B 预计大幅缩短模型跨度，先测再决定是否需要提高并发（`LLM_MAX_CONCURRENCY` 现为 4）或做阶段流水线；**按计划须先测得瓶颈并请用户确认**。

### 3.5 C04 准确率（需用户人工判定）

三份当前版本草稿均 ≤100 条，按 README §6.2 全量检查，工作表在 `evaluation/raw/c04/`：

| 草稿 | 知识点 | 关系 |
| --- | --- | --- |
| course1 MD | 75 | 66 |
| course2 MD | 71 | 55 |
| course2 PDF headings/2 | 74 | 59 |

- 人工判定由用户签收。Claude 辅助判定未做，可按需先做，须标 `claude-assist`。
- 若方案 B 改变了抽取结果（开关开启后的新草稿），应对新草稿另行判定，与旧草稿分开计算。

### 3.6 C06 技术门禁与冻结：未开始

- 最终 HEAD 的整次 `verify.sh integration`（含演示与个人模式假供应商端到端）；
- 新隔离目录从零启动复测两条闭环；
- 本阶段终版交接。

## 4. 注意事项与风险

- **测量数据在本工作区**：DeepSeek 在本工作树运行过服务，`src/backend/storage/smartsketch.sqlite3`（被 git 忽略）含真实运行数据；`.demo/c02/` 有运行日志。
  - 复核时只以 `mode=ro` 读白名单列；不要清理或重建，也不要在其上跑会写库的测试；
  - 迁移 017 已在该库执行，备份在 `src/backend/storage/backups/`；迁移 018 尚未在该库执行，下次启动服务会执行。
- **交接文件命名**：本阶段统一 `claude-plan-c-*.md`。`claude-c01.md`～`claude-c13.md` 等属于原子清单同号任务。本阶段曾误覆盖 `claude-c02.md` 的工作区副本，未提交，已原样恢复。
- 探测工具与测量工具都只用标准库；探测直连供应商，调用不进 `model_calls`，需手工记账。
- 默认端口被另一会话占用：端到端与集成用独立端口 18100 / 15273 / 17788 / 17789 / 18990。
- 发现但未处理：DeepSeek 忽略目录里的旧采集脚本 `.demo/l11-6/collect.py`（冲刺工作树）写死演示口令，并把缺失 usage 当 0；Codex 工作树 `.demo/l15-qa/measure-password` 是 644 权限的明文口令文件。均未读取或改动，建议用户处理。

## 5. 常用命令

```bash
# 后端全量（隔离环境变量）
env -u LLM_MODE -u EMBEDDING_MODE PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src/backend" \
  .venv/bin/python -m pytest tests/backend tests/tooling tests/contracts -q -p no:cacheprovider
# 前端
cd src/frontend && npx vitest run && npm run type-check && npm run build
# 契约生成
PATH="$PWD/.venv/bin:$PATH" ./scripts/gen-contracts.sh
# 整次门禁（独立端口）
E2E_API_PORT=18100 E2E_WEB_PORT=15273 E2E_NEO4J_PORT=17788 E2E_PROVIDER_PORT=18990 VERIFY_NEO4J_PORT=17789 \
PYTHON=.venv/bin/python PATH="$PWD/.venv/bin:$PATH" \
PLAYWRIGHT_CHROMIUM_EXECUTABLE="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
./scripts/verify.sh integration
```
