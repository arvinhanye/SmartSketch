你在 SmartSketch（智绘学途）仓库工作，目录 `~/Desktop/SmartSketch-main`。任务：图谱生成（上传资料 → 待审核）提速，目标示例章节 ≤60 秒。

开始前先读：
1. `AGENTS.md`（必须遵守）
2. `docs/tasks.md`（C03、B-QUALITY-01、B-EVAL-01 与末尾最新状态）
3. `docs/handoffs/claude-to-codex-extraction-perf.md`（本次交接：已有实测、代码现状、分优先级的任务、约束、验收）
4. `evaluation/reports/l02-baseline-2026-10.md`（141.7 秒的耗时分解）

工作方式：
- 先确认 OPT-05 后端分层（`codex/opt-05-backend-layering`）已提交；再从它新建分支 `codex/extraction-perf`。OPT-05 提交时不要带上本交接稿、本 prompt 和 `docs/tasks.md` 末尾 EXTRACT-PERF-01 一节，它们放进本任务的第一个提交。若 OPT-05 尚未完成，按交接稿 §1 用 worktree 并避开发布向量化文件。
- 先测量再优化：用 `scripts/fake_provider.py` 给每次模型调用固定约 8 秒延迟，跑 `datasets/demo/ch3-stack-queue.md`，产出「时间花在哪」的分解表（块抽取、小节关系、两阶段空等、merging 各步 `persist steps`、阶段交接等待、发布向量化）。不要调用付费模型；需要真实复测时先问我并确认预算。
- 只做交接稿 P1 中不影响抽取结果的优化，做完一项测一项、单独提交：去掉块阶段与小节阶段的屏障、评估并发上限、定位并修复 merging 慢段、去掉阶段交接轮询等待、发布向量化有界并发、减少输出修复。
- P2（合并小块、默认关闭思考、实体与关系合并调用）会影响已签收的准确率，只评估并给出对比数据，不要改默认行为，交我决定。
- 改并发与调度代码前先写能复现的测试（取消、失败阈值提前终止、接管续跑、租约丢失、凭据失效）；不改接口契约、任务状态机、SSE 格式、提示词；不新增或升级依赖；不放宽或删除测试断言。
- 每项改动后跑 `scripts/verify/backend.sh full` 与 `./scripts/verify.sh`（涉及 Neo4j 写入时跑 integration）；需要 Docker 时先 `export PATH="$HOME/.docker/bin:$PATH"`。
- 在 `docs/tasks.md` 认领 EXTRACT-PERF-01；最后写 `docs/handoffs/codex-extraction-perf.md`。只本地提交，不推送、不开 PR、不合并，不使用破坏性 git 命令。
- 遇到需要我决定的事（真实复测预算、P2 方案、配置默认值变化、范围不清）停下来问我。

最后回复我：耗时分解表（优化前后）、每项优化的实际收益、运行的验证命令与结果、提交列表、需要我决定的事项。
