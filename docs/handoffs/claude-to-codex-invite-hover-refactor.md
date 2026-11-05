# Claude → Codex 交接：课程邀请码、图谱悬停卡顿、全局代码优化（2026-11-05）

## 1. 背景与基线

- 项目：智绘学途（SmartSketch），11 月 21 日决赛答辩。先读 `AGENTS.md`、`docs/tasks.md`、相关 `specs/`。
- 工作区：`~/Desktop/SmartSketch-main`，git 已接上 GitHub（`origin`），当前分支 `claude/ui-pine-redesign`，最新提交 `ef5e297`（青松明黄界面改版，UI-PINE-01，未推送）。**请从该分支最新提交（含本交接稿）新建分支** `codex/invite-hover-refactor` 工作，不要改写 `claude/ui-pine-redesign` 的历史。
- 改版背景：`docs/handoffs/claude-ui-pine-01.md`、计划 `docs/superpowers/plans/2026-11-04-ui-pine-redesign.md`。界面色板用 `--ui-*`（`styles/tokens.css`），图谱画布颜色在 `graph/theme.ts` 与 `--gw-*`，**图谱展示样式不改**（用户已决）。
- 基线验证（`ef5e297`）：前端 vitest 78 文件 / 1311 条通过；`npm --prefix src/frontend run type-check`、`vite build`、`./scripts/verify.sh`（basic）通过。全量并发时 `h14` / `l14` / `student-graph-workbench` 偶发 5 秒超时，单独重跑通过。
- 环境注意：Docker Desktop 更新后 `docker` 不在 PATH，需 `export PATH="$HOME/.docker/bin:$PATH"`；`.venv` 已补装 `src/backend[test]`；演示环境 `scripts/start-demo.sh --no-open`，账号见脚本头注释。

## 2. 任务 A：课程邀请码（只做「学生输码入课」与「教师查看/重置邀请码」）

用户已决（2026-11-02、11-05）：入课改用邀请码；**本期不做注册时填码**；按用户名添加成员的旧方式保留。

### 需求

1. **教师**：在课程（概览页或成员页，建议成员页「添加学生」旁）看到本课邀请码，可复制、可重新生成；重新生成后旧码立即失效。只有本课教师可见可操作。
2. **学生**：学生课程列表页（`CoursesView`，`resume-card` 下方）放「加入课程」卡片：输入邀请码 → 加入 → 刷新列表并高亮新课程。错误要分开提示：码不存在或已失效、已在课程中、请求过于频繁。设计参考 v3 课程进入页（https://claude.ai/artifact/Vg9yqHzdfAgEVvu1bAKnRV 的 Courses 画板）：6 位大号输入框 + 「加入」按钮，无说明长文。

### 约束（项目规则）

- 先改契约再写代码：`src/contracts/api.v1.yaml`（OpenAPI 为真源）→ 重新生成 `src/contracts/v1/generated/*` → 契约门禁通过。错误码补进 `src/contracts/errors.v1.md`。
- 新 ADR（当前最大编号 ADR-095，新建 ADR-096）写在 `docs/decisions.md`：码的格式（建议 6 位，去掉易混字符 0/O/1/I）、存储（建议只存哈希或明文 + 唯一约束，二选一并说明理由）、失效与重置、限流、课程隔离、与按用户名添加的关系。
- 规格更新：`specs/identity-access.md`（加入课程的路径与错误）。
- 迁移：新文件 `src/backend/migrations/020_*.sql`，**必须带 `-- ROLLBACK:` 步骤**（已有守卫测试覆盖 007 起的回滚）。
- 后端分层：`api → schemas → services → repositories`，路由不写业务规则；所有查询按 `course_id` 隔离；教师接口校验本课教师身份。
- 建议接口（以契约为准，可调整命名）：
  - `GET /api/v1/courses/{cid}/invite-code`（本课教师）→ `{code, rotated_at}`
  - `POST /api/v1/courses/{cid}/invite-code:rotate`（本课教师）→ 新码
  - `POST /api/v1/courses/join`（学生）`{code}` → 加入的课程（复用 `Course` schema）；错误：`INVITE_CODE_INVALID` 404/422、`ALREADY_MEMBER` 409、`RATE_LIMITED` 429。
- 防猜码：按用户与 IP 限流（参考登录限流 `services/auth.py` 的做法），错误不泄露课程是否存在。
- 前端分层：`api/`（新 `inviteCode.ts` 或并入 `members.ts`/`courses.ts`）、`composables/`、组件；保留既有 `data-test`；新控件加 `data-test`。

### 验收

- 后端：成功、码错误、码已轮换、已是成员、非学生账号、跨课越权、限流的用例；迁移前进/回滚。
- 前端：加入成功刷新列表、各错误文案、提交中禁用；教师端复制与重置（重置需二次确认）。
- 端到端（可选但推荐）：教师取码 → 学生注册 → 输码入课 → 看到图谱。

## 3. 任务 B：图谱悬停卡顿（2026-11-03 已定位，用户当时决定暂不修，现在修）

- 现象：学生图谱页鼠标移到节点上卡顿，预览状态下同样。
- 已实测根因（前端，与后端无关，悬停期间无网络请求）：`src/frontend/src/graph/enhancer.ts` 的 `applyHover()`（约 296 行）每次 `node:pointerenter` 与延迟 60ms 的 `endHover()` 都把 `hoverStateMap()`（`graph/focusStates.ts:111`）生成的**全部节点与边**（示例课程 64 + 71 = 135 个）整份交给 G6 `setElementState`。G6 对传入的每个元素都重算样式，与状态是否变化无关：整份 135 个即使不变也要 42ms；只传 1 个元素约 1.8ms。单次移入/移出主线程 47–63ms（长任务），小地图跟随重绘只占 3–6ms。
- 修复要求（按顺序，前两项必做）：
  1. 只把状态真正变化的元素交给 `setElementState`（记住上一次已应用的状态表做差分）。
  2. 悬停淡化加停留阈值（约 120ms 内离开则不触发），快速划过不触发全图淡化；保留现有 60ms 防闪与 `canvas:pointermove` 兜底。
  3. 若做完 1、2 仍有可感知卡顿，再提出「只高亮悬停节点及邻居、不淡化其余」的方案——**这会改变交互，须先问用户，不要直接改**。
- 验收：在演示环境 1440×900 下给 `Graph.prototype.setElementState` 计时（方法见上：动态 import `/node_modules/.vite/deps/@antv_g6.js?v=<hash>` 后包裹原型方法），普通与预览状态各移入/移出 10 次，记录前后耗时；目标单次 ≤16ms 或无 >50ms 长任务。补单元测试覆盖差分（只传变化元素）与停留阈值。已知问题条目在 `docs/tasks.md` 末尾「已知问题（2026-11-03 实测…）」，修完更新它。

## 4. 任务 C：全局代码优化与重构（行为不变）

目标：答辩前让代码更易读、更少重复、更稳，**不改功能、不改接口契约（任务 A 新增的除外）、不改视觉**。

- 原则：
  - 每一项重构都必须有测试兜底；先跑基线，改完结果一致。不得为通过而删除或放宽测试断言。
  - 小步提交：一类改动一个提交，提交说明写清动机与影响范围，便于单独回滚。
  - 不新增依赖，不升级依赖版本（如确有必要，单独提出并说明回滚步骤）。
  - 不动 `graph/theme.ts` 与 `--gw-*` 色值；不改 `data-test` 钩子。
- 建议优先级（先做收益大、风险小的）：
  1. 前端样式：`styles/ui.css` 末尾是 UI-PINE-01 的覆盖层，与 `styles/graph-workspace.css`、`styles.css` 有重复和优先级叠加；合并同一选择器、去掉已无效的规则（如 `.app-topbar__logo`、旧 `--color-*` 只剩少量引用），把写死的颜色（`#747a87`、`#5b5bd6` 等仍在 `graph-workspace.css`、`Recommendations.vue`、`ChatView.vue`、`AnswerCard.vue`）换成 tokens。验收：样式守护测试（`graph-detail-layout`、`login-scrollbar-style`、`ui-batch2-styles`、`graph-theme`）全过，关键页面截图前后一致。
  2. 前端逻辑：`views/` 里过长的单文件（如 `StudentGraphView.vue`、`TeacherGraphView.vue`、`CoursesView.vue`）把可测的纯逻辑抽到 `composables/`；消除重复的错误文案映射与请求取消样板。
  3. 后端：路由层残留的业务判断下沉到 `services/`；重复的课程成员/角色校验收敛到 `services/access.py`；查询按 `course_id` 隔离的写法统一。
  4. 测试工具：前端测试里重复的挂载 helper（会话、路由、注入）提到共享 helper；修 `h14`/`l14`/`student-graph-workbench` 并发超时的等待方式（避免固定等待）。
  5. 冗余与死代码：未引用的组件、函数、样式；用工具查（`vue-tsc`、`rg`）并在交接里列出删除清单。
- 每项完成后跑：前端 type-check、全量 vitest、build；后端 `scripts/verify/backend.sh full`；`./scripts/verify.sh`（basic，必要时 integration）。

## 5. 顺序与交付

1. 任务 B（最小、最独立）→ 2. 任务 A（契约 → ADR/规格 → 迁移 → 后端 → 前端 → 测试）→ 3. 任务 C（逐项小步）。
- 每个任务在 `docs/tasks.md` 认领一节（建议编号 `INVITE-01`、`GRAPH-HOVER-01`、`REFACTOR-01`），写输入、输出、风险、验证命令与验收证据。
- 交接写 `docs/handoffs/codex-invite-hover-refactor.md`：交付物、实际运行的命令与结果、接口/数据变更、迁移回滚步骤、风险、未完成项。
- **不推送、不开 PR、不合并**，除非用户明确指示；不使用破坏性 git 命令；不提交密钥、数据库、构建产物。
- 遇到需要用户决定的事（交互变化、依赖升级、契约破坏性变更），写进 `docs/tasks.md` 的未决项并停下来问。
