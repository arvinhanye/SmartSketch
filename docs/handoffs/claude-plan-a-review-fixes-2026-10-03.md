# 计划 A 审查修复（D1–D3、N01–N08）交接

```text
task_ids: D1、D2、D3、N01–N08，及问答页既有验收缺口 §3.7（不另编号）
review_status: ready_for_review
author: Claude
依据: /Users/arvinhan/.codex/worktrees/e92f/SmartSketch/docs/reviews/codex-claude-plan-a-2026-10-03.md
      /Users/arvinhan/.codex/worktrees/e92f/SmartSketch/docs/handoffs/codex-claude-plan-a-fix-prompt-2026-10-03.md
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34
branch: claude/smartsketch-plan-a-fixes-e70a34（由 e86f4b9 快进而来，可快进合回 claude/smartsketch-contest-sprint-77644f）
base_commit: e86f4b9ce61ca866211a63dc3aa7c05587f1a966
head_commit: 本文件所在提交（门禁对象为代码提交 959331e1f483b9ec11c28354e502fe4961dea0ac，其后只有文档提交）
推送/合并: 均未做；全部为本地提交
```

会话工具不允许写其他工作树，所以没有直接改冲刺工作树（`smartsketch-contest-sprint-77644f`，开工时 HEAD 为 `e86f4b9` 且干净）。本工作树的 `.venv`、`node_modules`、`src/frontend/node_modules` 是从冲刺工作树 APFS 克隆的，已被 git 忽略；测试时用 `PYTHONPATH=src/backend` 保证导入的是本工作树代码。

## 提交与逐项状态

| 项 | 级别 | 状态 | 提交 | 回归（先红后绿） |
| --- | --- | --- | --- | --- |
| N01 | P1 | 已修 | `0745ea6` | `tests/backend/test_n01_n06.py`：red 8 failed / 2 passed（清除重建后仍发往 A；旧测试成功落到 B）→ green |
| N06 | P2 | 已修 | `0745ea6` | 同上（阻塞传输、清除后同值重建、乱序完成） |
| D1 | P1 | 已修 | `cc26d4c` | `tests/backend/test_d1.py` red 5 failed / 7 passed → green 12；`tests/frontend/d1-d3.test.ts` red 3 → green |
| D3 | P1 | 已修 | `8e539a8` | `tests/backend/test_d3.py` red 14 failed / 4 passed（先加入无行为的接口）→ green 18 |
| N02 | P2 | 已修 | `a787b0b`、`29a10f6` | `tests/backend/test_e12.py` N02 段 red 5 failed（任务进入 merging）→ green；`tests/frontend/h02.test.ts` 凭据原因提示 red 4 → green。`29a10f6` 去掉了并发用例的时序竞争，连跑 5 次均通过 |
| N03 | P2 | 已修 | `45dd86e` | `tests/frontend/n03-n05.test.ts` N03 段 red → green |
| N04 | P2 | 已修 | `45dd86e` | 同上 N04 段（逻辑层与按钮层） |
| N05 | P2 | 已修 | `45dd86e` | 同上 N05 段 |
| §3.7 | 既有缺口 | 已修 | `45dd86e` | `tests/frontend/chat-send-lock.test.ts` red → green |
| N07 | P2 | 已修 | `f580b74` | `tests/backend/test_n07_n08.py` N07 段 red → green |
| N08 | P2 | 已修 | `f580b74` | 同上 N08 段（N07+N08 合计 red 20 failed / 2 passed → green 22） |
| D2 | P2 | 已修 | `959331e` | `tests/backend/test_d2.py` red 9 failed / 1 passed（先加入无行为的接口）→ green 10；`tests/integration/test_d2_publish.py` 在 integration 档通过 |

各阶段的 red/green 日志在会话草稿目录 `.../scratchpad/logs/`，属临时文件；可持续的证据是上面的仓库测试本身。

## 门禁结果（代码 HEAD `959331e`）

命令：

```bash
PYTHON=.venv/bin/python PATH="$PWD/.venv/bin:$PATH" \
PLAYWRIGHT_CHROMIUM_EXECUTABLE="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  ./scripts/verify.sh integration
# 首次运行的端到端因本工作树缺仓库根目录 node_modules（@playwright/test）而 exit 1；
# 从冲刺工作树克隆根 node_modules 后单独补跑：
PYTHON=.venv/bin/python PATH="$PWD/.venv/bin:$PATH" \
PLAYWRIGHT_CHROMIUM_EXECUTABLE="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  scripts/e2e.sh
git diff --check e86f4b9 HEAD
```

| 档位 | 结果 |
| --- | --- |
| 基础档 | PASS：钩子回归、契约门禁（OpenAPI 3.1.0，32 条路径、129 个 schema、385 处 `$ref`，生成物与真源一致）、B08–B14 契约回归 |
| 后端 full（tests/backend + tests/tooling） | PASS：3725 passed、27 skipped（均为 allowed-skips 已登记项，gate 判定通过） |
| 前端 full | PASS：29 个文件、811 个用例全部通过；type-check、build 通过（保留既有的 >500 kB 包体积警告） |
| 集成用例（一次性 Neo4j，端口 17689） | PASS：393 passed、4 skipped（已登记），含 `test_d2_publish.py` |
| 图库后端用例 | PASS：44 passed |
| 端到端 | 首次 FAIL，原因是环境缺 `@playwright/test`，与代码无关；补齐依赖后单独补跑 PASS：学生主线、教师主线 2 passed（演示模型，无费用；日志 `.e2e/20261003-072042`） |
| `git diff --check e86f4b9 HEAD` | exit 0 |

说明：`verify.sh integration` 的同一次运行没有整体 exit 0，端到端是补跑的。全程没有调用真实模型，也没有动真实课程库或冲刺环境的 Neo4j（7688）。

## 接口、数据与文档变更

- **迁移** `016_model_config_revision.sql`：`user_model_configs.revision` 为可空列，已有行随机回填。回滚：停 API 与 worker，恢复 `backups/*-before-016.sqlite`，或执行文件头的 `ROLLBACK` 语句（需 SQLite ≥ 3.35）。
- **契约**（已重新生成 DTO）：
  - `ChatLlmUnavailableReason` 增加 `truncated`。
  - `ModelConfigUpdate` 与 `ModelConfigTestRequest` 的 `model` 字段补充说明：去掉首尾空白后为空时返回 422 `blank`。
  - `errors.v1.md` 中 `LLM_UNAVAILABLE` 的说明同步更新。
- **内部接口**：
  - `EmbeddingRequest.timeout_seconds`
  - `repositories.model_configs.record_test(..., revision=)`
  - `neo4j.read_deadline`
  - `embeddings.embedding_calls` / `EmbeddingRecordError`
  - `factory.build_embedding_adapter`
  - `runtime` store 新增 `startSession` / `claim` / `commitRead` / `commitWrite`
  - `useModelConfig` 导出 `busy`
- **决定与规格**：
  - ADR-082 决定 1–6，依次为：配置身份、截断即生成故障、链路截止时刻、鉴权终止、存储门禁与模型名校验、向量记账。
  - `specs/grounded-qa.md`：O6、QA-16、原因闭集、Q7、Q6.5 均有修订。
- **既有测试改断言**（新行为有意不同）：`test_j06.py` 截断尾句、`test_j10.py` 迁移序号 016、`test_l04.py` 的 `record_test` 签名。

## 风险与未决

1. **D1 输出上限未调**：`ANSWER_MAX_OUTPUT_TOKENS` 仍为 1024。历史真实问题「栈和队列有什么区别」现在会显示「回答过长被截断」，而不是「资料未覆盖」，但仍然答不出来。是否提高上限，或在共用截止时刻内做有限的缩短重试，需要按 15 秒时限和费用实测后由人工决定（ADR-068 待决 1）。
2. **D3 已知边界**：Neo4j 驱动建立连接、取连接池的等待由驱动配置约束（本机实例）；域名解析超时后，解析线程会在系统解析器里自行结束，不会再发出供应商请求。
3. **D2 范围**：离线重新向量化脚本沿用自己的台账，不写 `model_calls`；fake/demo 不出站，所以不记账。
4. **未做的真实验证**：没有在真实供应商或真实向量服务上复测（需要用户确认预算后再做），也没有重测性能和准确率（属计划 C 的 L16）。
5. **N02 也适用于 `live` 模式**：全站 key 遇到 401/403 同样终止任务，不重试。

## 收尾记录（2026-10-03）

- **分支**：本分支已按用户指示快进合回 `claude/smartsketch-contest-sprint-77644f`（`e86f4b9 → d766f40`，没有合并提交）。两个工作树 HEAD 相同，未推送。
- **未提交文件**：无。
- **调用台账**：累计计费 140230 / 5000000 token（L02 抽取 101054、V1 问答 16101、V2 23075）。本轮修复与门禁全程没有真实模型调用；端到端用演示模型，不产生费用。
- **冲刺环境**：SQLite 尚未执行迁移 016，下次 `scripts/start.sh` 启动时会自动备份并迁移。
- **日志**：`verify.sh integration` 的完整日志与补跑的端到端日志在会话草稿目录 `.../scratchpad/logs/verify-integration.log`、`e2e.log`（临时）；端到端运行目录 `.e2e/20261003-072042`（本工作树，git 忽略）。
- **后续计划**：计划 B 规划见 `docs/superpowers/plans/2026-10-03-contest-sprint-b-functional-loop.md`，基线即本版本。

## 下一步

- Codex 复审：base 为 `e86f4b9`，代码 HEAD 为 `959331e`，目前处于 ready_for_review，复审期间这批代码保持不动。
- 复审通过后，把本分支快进合回冲刺分支，再按原流程申请推进计划 B/C（L11–L19）。
