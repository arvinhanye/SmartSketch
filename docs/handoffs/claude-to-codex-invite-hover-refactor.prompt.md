你在 SmartSketch（智绘学途）仓库工作，目录 `~/Desktop/SmartSketch-main`。这是 11 月 21 日决赛答辩前的一个开发任务，包含三项工作：课程邀请码、图谱悬停卡顿修复、全局代码优化重构。

开始前必须先读：
1. `AGENTS.md`（共同工作契约，必须遵守）
2. `docs/tasks.md`（任务看板，末尾几节是最新状态）
3. `docs/handoffs/claude-to-codex-invite-hover-refactor.md`（本次任务的完整交接稿：需求、约束、已定位的根因、验收标准、顺序）
4. `docs/handoffs/claude-ui-pine-01.md`（上一轮界面改版的交接）

工作方式：
- 从分支 `claude/ui-pine-redesign` 的最新提交（含本交接稿；界面改版在 `ef5e297`）新建分支 `codex/invite-hover-refactor`，在新分支上工作。
- 先跑基线并记录结果：`npm --prefix src/frontend run type-check`、在 `src/frontend` 下 `npx vitest --run`、`npx vite build`、仓库根目录 `PATH="$PWD/.venv/bin:$PATH" ./scripts/verify.sh`。需要 Docker 时先 `export PATH="$HOME/.docker/bin:$PATH"`。
- 按顺序做：
  1. 任务 B（图谱悬停卡顿）：交接稿第 3 节已给出根因与修复顺序。只做第 1、2 项（差分更新 + 停留阈值）；第 3 项会改变交互，先问我。
  2. 任务 A（邀请码，只做「学生在课程列表页输码入课」和「教师查看/复制/重置邀请码」，不做注册时填码）：先改 `src/contracts/api.v1.yaml` 并重新生成，再写 ADR-096 与 `specs/identity-access.md`，再写带 `-- ROLLBACK:` 的迁移 020，然后后端、前端、测试。
  3. 任务 C（全局代码优化重构）：行为不变、视觉不变、契约不变；按交接稿第 4 节的优先级小步进行，每一类改动单独提交，每次提交前全量测试通过。
- Bug 修复先写能复现的测试；不得删除或放宽现有断言来让测试通过；不新增或升级依赖；不改 `graph/theme.ts` 与 `--gw-*` 图谱色值；保留所有 `data-test` 钩子。
- 每项任务在 `docs/tasks.md` 认领一节（INVITE-01、GRAPH-HOVER-01、REFACTOR-01），完成时写验收证据；最后写交接 `docs/handoffs/codex-invite-hover-refactor.md`。
- 可以在新分支上本地提交；不要推送、不要开 PR、不要合并；不使用破坏性 git 命令；不提交密钥、数据库或构建产物。
- 遇到需要我决定的事（交互变化、依赖变化、契约破坏性变更、范围不清），停下来问我，不要自行决定。

最后回复我：每项任务做了什么、实际运行的验证命令与结果（含悬停优化前后的耗时数据）、提交列表、仍未完成或需要我决定的事项。
