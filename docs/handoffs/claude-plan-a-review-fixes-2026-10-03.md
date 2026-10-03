# 计划 A 审查修复（D1–D3、N01–N08）——中途交接

```text
review_status: in_progress（未 ready_for_review）
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34
branch: claude/smartsketch-plan-a-fixes-e70a34（从 e86f4b9 快进；会话工具禁止写冲刺工作树，可快进合回 claude/smartsketch-contest-sprint-77644f）
base: e86f4b9ce61ca866211a63dc3aa7c05587f1a966
commits: 0745ea6 N01/N06 · cc26d4c D1 · 8e539a8 D3 · a787b0b N02
环境: .venv 与 src/frontend/node_modules 由冲刺工作树 APFS 克隆（git 忽略）；PYTHONPATH=src/backend 保证导入本工作树代码
```

## 逐项状态

| ID | 状态 | 证据 |
| --- | --- | --- |
| N01 | 已修 | 迁移 016 `revision`；`tests/backend/test_n01_n06.py` red 8F/2P → green |
| N06 | 已修 | 同上（阻塞传输 + 乱序门控） |
| D1 | 已修 | `LLM_UNAVAILABLE`/`truncated`；契约重生成；`test_d1.py` red 5F → green 12；前端 `d1-d3.test.ts` red 3 → green |
| D3 | 已修 | 传输总预算 + 看门狗、向量/图库剩余预算；`test_d3.py` red 14F/4P → green 18 |
| N02 | 已修 | `test_e12.py` N02 段 red 5F → green；`h02.test.ts` 凭据原因提示 red 4 → green |
| N03 | 待修 | 红测已写：`tests/frontend/n03-n05.test.ts`（未提交，当前 18 failed / 3 passed） |
| N04 | 待修 | 同上 |
| N05 | 待修 | 同上 |
| §3.7 | 待修 | 红测已写：`tests/frontend/chat-send-lock.test.ts`（未提交） |
| N07 | 待修 | 未开始：`run_test` 开头统一 `_cipher(settings)` |
| N08 | 待修 | 未开始：共享校验 strip 后空白 → 422 `model` |
| D2 | 待修 | 未开始 |

## 已验证

- 后端全量（D3 后、N02 前）：`PYTHONPATH=$PWD/src/backend .venv/bin/python -m pytest tests/backend -q -p no:cacheprovider` → 3626 passed, 27 skipped, exit 0。
- N02 后：`tests/backend/test_e12.py tests/backend/test_l07.py` 55 passed。
- 基础门禁（D1 后）：`PYTHON=.venv/bin/python PATH="$PWD/.venv/bin:$PATH" ./scripts/verify.sh` exit 0。
- 前端：d1-d3、j08、j09、h02 通过；`npm run type-check` 通过。前端全量、full、integration、tests/tooling 未跑。

## 接口/数据变更

- 迁移 `016_model_config_revision.sql`（可空列 + 随机回填；回滚见文件头或 `backups/*-before-016.sqlite`）。
- 契约 `ChatLlmUnavailableReason += truncated`；`EmbeddingRequest.timeout_seconds`（内部）；`record_test(..., revision=)`。
- ADR-082 决定 1–4；`specs/grounded-qa.md` O6、QA-16、原因闭集修订。

## 下一步（N03–N05 实现设计，红测即验收）

- `stores/runtime.ts`：增加 `startSession(key)`、`claim()`（owner+generation）、`commitRead(ticket, cfg)`（owner 与 generation 都匹配才写）、`commitWrite(ticket, cfg)`（owner 匹配即写并 generation++）；保留 `apply`。
- `App.vue`：watch `session.accessToken`（不是 role），变化即 `startSession`、中止上一 GET、按 ticket `commitRead`。
- `useModelConfig.ts`：单一 `busy`（loading/saving/testing/clearing）互斥并导出；卸载置 disposed；读用 commitRead、保存/清除用 commitWrite；测试对象：密钥空且地址/模型与已存一致才测已存配置（文案「已保存的配置」），否则要求先保存或填密钥；带密钥测表单（文案「尚未保存」），测试期间表单变动则结果作废（文案含「已修改」）。
- `ModelSettingsView.vue`：三按钮按 `busy !== null` 禁用。
- `useChat.ts`：`ask` 在 `sending` 时直接返回（不再 stop）；`ChatView.vue` 发送按钮加 `sending` 禁用、停止按钮加 `data-test="chat-stop"`；同步修订 `specs/grounded-qa.md` Q6.5。
- 之后 N07、N08、D2，再跑 `verify.sh full`、`integration`（一次性 Neo4j）、`git diff --check`，更新本文件为 ready_for_review。
