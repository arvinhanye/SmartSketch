# L00 A10 一周参赛冲刺 · 设计规格交接

```text
task_id: L00
review_status: ready_for_review（规格与计划 A 已获用户确认，随 Task 0 提交）
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-contest-sprint-77644f
base_commit: 6ff8a8dfa9e0ce26defef01ae6b3c9ff2f03e620
head_commit: 同 base；有未提交变更（下列四个文档；另有未跟踪且被忽略的 .env）
changed_files:
  - docs/superpowers/specs/2026-10-02-contest-sprint-design.md（新增）
  - docs/tasks.md（新增 L00 一节）
  - docs/superpowers/plans/2026-10-02-contest-sprint-a-personal-model-api.md（新增）
  - docs/handoffs/claude-l00-sprint-design.md（本文件）
  - .env（新增，未跟踪、被 .gitignore 忽略，权限 600；不含任何供应商密钥）
```

## 交付与关键决定

- 设计规格：`docs/superpowers/specs/2026-10-02-contest-sprint-design.md`。
- 实施计划 A（L01–L10）：`docs/superpowers/plans/2026-10-02-contest-sprint-a-personal-model-api.md`；计划 B、C 在第 3、4 天结束时编写。
- 方案（规格第 11 节四项决定已获用户同意，其余细节随计划 A 待确认）：`LLM_MODE=personal`；每用户一份加密配置；任务级加密快照绑定；问答按「用户 + 配置版本」隔离策略与熔断；出站地址解析后校验并钉 IP；系统级在线向量，`local` 明确拒绝；原子任务候选 L01–L19。
- 上下文来源是 Codex 工作区的未提交文档（`/Users/arvinhan/.codex/worktrees/e92f/SmartSketch/docs/handoffs/codex-claude-contest-sprint-prompt-2026-10-02.md` 及其引用的两份审查），本工作区没有复制它们。

## 验证

| 命令 | 结果 |
| --- | --- |
| `git status --short`（开始时） | 干净 |
| `git rev-parse HEAD` | `6ff8a8dfa9e0ce26defef01ae6b3c9ff2f03e620` |
| `./scripts/verify.sh` | exit 0，基础档 PASS；使用系统 `/opt/anaconda3/bin/python3`，不是项目锁定环境 |
| `git diff --check` | exit 0（只覆盖已跟踪的 `docs/tasks.md`；两个新增文件未跟踪，不在检查范围内） |

只读核验的源码事实及位置列在规格第 2 节。

## unverified

- `./scripts/verify.sh full`、`integration`、后端与前端测试、类型检查、构建、E2E：均未运行（本工作区无虚拟环境与 `node_modules`）。
- 真实模型、真实向量、任何性能数字：未测。规格中的 329 秒来自历史报告 `evaluation/reports/extraction-accuracy.md`，不是本轮结果。
- 赛题 DOCX 原文：未独立复核，沿用 Codex 复核报告。

## api_and_data_changes

无。规格提出的接口（`/api/v1/me/model-config` 四个操作、`MODEL_CONFIG_REQUIRED`、`SourceRef.document_name`）、迁移 015、新环境变量与新依赖 `cryptography` 都尚未实施（本轮无接口、数据或配置代码变更）。

## open_questions

- 规格第 11 节四项已由用户同意（2026-10-02）：在线向量、DeepSeek `deepseek-flash`、预算 30 元、自编资料、规则调整与 `cryptography`。
- 待用户：在 `.env` 填写 `LLM_API_KEY` 与 `EMBEDDING_API_KEY`（L02 与 L09 的真实联调依赖它们）。
- 累计真实模型计费 token：0（本轮未调用模型）。

## rollback

仅文档变更，无破坏性修改。撤回即删除三个新增文档、移除 `docs/tasks.md` 的 L00 一节，并删除工作区根目录的 `.env`。

## next_action

用户确认计划 A 与执行方式 → 从 Task 0 提交文档开始，按 L01 → L10 推进；每个任务一份 `claude-l<nn>.md` 交接。确认前不认领 L01–L19、不写业务代码。
