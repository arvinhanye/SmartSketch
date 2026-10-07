# 任务稿：UI 升级第二批（其余页面推广）——给接手 Agent

- 发起：Claude（前端/协调）。接手：任一前端 Agent（Codex、Claude 或其他）。状态：**样板页已完成并开 Draft PR #321；第二批尚未开工**。
- 日期：2026-10-07。仓库：`arvinhanye/SmartSketch`。基线：`main@bdb89c4`；样板页分支 `claude/smartsketch-frontend-init-0d2af9`，PR [#321](https://github.com/arvinhanye/SmartSketch/pull/321)（Draft，未合并，HEAD `ab60183`）。
- 本文由发起方写入；你的交接请写 `docs/handoffs/<你的 agent 名>-<任务>.md`，不要代写别人的。

## 1. 你要做什么

把样板页（学生图谱页）确立的设计体系推广到其余页面，**一次一个阶段、一个阶段一条分支一个 Draft PR**。阶段顺序与范围：

| 阶段 | 内容 | 依赖 |
| --- | --- | --- |
| R1 | 外壳通用化（所有登录后页面共用暗色顶栏 + 图标栏）、浅色内容表面、通用件；回归样板页遗留项 | #321 的分支 |
| R2 | 课程列表与课程主页（`CoursesView`） | R1 |
| R3 | 模型 API 设置（`ModelSettingsView`） | R1 |
| R4 | 课程问答（`ChatView`、暗色页） | R1 |
| R5 | 教师图谱页（`TeacherGraphView` + 编辑面板） | R1、R2 |
| R6 | 资料、审核与发布、成员 | R1 |
| R7 | 认证页对齐 + 收口（删旧样式、旧变量） | R2–R6 |

优先级：用户最初指定「我的课程 / 模型 API 设置 / 课程列表」优先，所以 R1 之后先做 R2、R3。R3、R4、R6 彼此独立，可并行（同一文件不要同时改）。

**这不是代码级计划。** 每个阶段开工前，你要先用 `superpowers:writing-plans`（或同等做法）写出该阶段的代码级计划，经负责人确认后再动代码。

## 2. 必读（按顺序）

1. `AGENTS.md`、`CLAUDE.md`、`.claude/rules/frontend.md`、`.claude/rules/testing.md`、`docs/tasks.md`（UI-GRAPH-PILOT-01 段）。
2. `docs/frontend-ui-handoff.md`（总览：参考软件、设计方案、进度、边界、已知坑）。
3. **`docs/superpowers/plans/2026-10-07-ui-rollout-batch2.md`（你的主依据：每阶段的版面、默认决定、保留钩子、测试影响、验收、任务拆分）**。
4. `docs/superpowers/specs/2026-10-06-graph-workbench-design.md`（tokens、px 规范、交互、动效、验收口径）。
5. `docs/handoffs/codex-ui-graph-pilot-01.md`（样板页实际做了什么、踩坑、证据）。
6. 认证页既有工作（R7 前别改行为）：`docs/handoffs/codex-ui-login-01.md`、`codex-ui-auth-art-02.md`、`codex-ui-auth-motion-03.md`。

## 3. 边界（不得越过）

- 只改前端的视觉与交互。**不改** `src/contracts/`、后端、数据库、业务规则；不新增接口字段、数据模型、依赖；不引入 UI/图标库（图标用 `AppIcon`）。
- 需要「新数据」才能做的展示一律不做，记入计划里的「第二批外」：课程主页进度/待审核摘要、问答示例问题、教师图谱「版本」页签等。
- 业务红线：掌握状态服务端确认前不显示成功；问答必带来源、`not_covered` 与服务错误分开显示；关系仅四类且 `PREREQUISITE` 为 DAG；课程隔离；密钥不进前端持久存储。
- 保留每个页面既有 `data-test` 钩子；必须变更时在阶段计划里列出并同步测试与端到端。
- 问答页是暗色页，不得继承 `--gw-*`；认证页的动态图谱、登录页视口行为、`prefers-reduced-motion` 停用逻辑不得回退。
- 不改全局 `--color-*`，直到 R7 收口且负责人批准。

## 4. 每个阶段的固定流程

1. 在 `docs/tasks.md` 认领（建议 ID 前缀 `UI-ROLLOUT-`），从 #321 的分支（或前一阶段分支）拉新分支。
2. 写该阶段代码级计划 → 负责人确认。
3. **先写失败测试**，确认失败，再实现，再跑验证命令。既有断言只在「样式/结构/文案随设计变化」处更新并写明原因，**不放宽、不删除**。
4. 验收：`type-check`、全量前端测试、`build`、`./scripts/verify.sh`；四个宽度（1440×900、1280×800、768、390）× 加载/空/错误/未授权 × 教师/学生（按页面）的目测与截图；键盘与焦点；页面**实际渲染色**对比度（文字 ≥4.5:1、必要图形 ≥3:1）；200% 缩放；减少动效；修改前后截图（需要真实实例时由负责人提供，没有就写「未做」）。
5. 写交接（交付物、实际运行的命令与结果、与计划的差异、未验证范围、风险、回滚）；更新 `docs/tasks.md` 与规格对应小节；必要时追加 ADR。
6. 开 Draft PR（**仅在负责人明确指示后** 提交、推送、开 PR）；等确认再进入下一阶段。

## 5. 基线（开工前先自己复核，结果与此不符就先停下说明）

- 样板页后前端：`npm --prefix src/frontend run type-check` 通过；`npm --prefix src/frontend run test -- --run` **57 个文件 / 1144 条**通过；`npm --prefix src/frontend run build` 通过（G6 chunk >500 kB 提示是既有现象）；`./scripts/verify.sh` 基础档通过。
- `./scripts/verify.sh full` 在 Codex 本机后端部分失败（argon2 `InvalidHashError`，环境问题，非前端）。默认 Python 3.11 可能缺 `yaml`/`pytest`，可用已有的 3.13 做命令级 PATH 覆盖，**不要安装新依赖**。
- 看真实 G6：启动 Vite 后打开 `/preview/prod.html?size=100`（`src/frontend/preview/`，合成数据、不连后端、未跟踪、不进构建）。

## 6. 已知坑（摘要，细节见交接）

- G6 5.1.1：`hull` 插件不能移除；标签开关用布尔 `label`；`getZoom()` 在初始化/销毁中会抛；小地图销毁要延后。
- 全站旧样式（`button:hover:not(:disabled)`、`.app-main > section`）特异性低但无处不在：新样式一律带作用域前缀并显式覆盖。
- `:inert` 关闭写 `true`、打开写 `undefined`；章节布局异步，测试用 `vi.waitFor`；画布位置从无到有只由 `ready` 建图。
- 推荐编号「1. 名称」是有意设计；掌握状态文案是「未学习」。

## 7. 遇到这些先停下来问负责人，不要自行决定

需要新数据/新接口/新业务；既有测试必须放宽才能通过；既有钩子必须变更；用户可见文案要改；需要新依赖；任何提交/推送/开 PR；需要真实实例或登录凭据的验收（凭据问题未解决，**不要猜测或重置账号**）；与计划/规格冲突；不确定某个设计是否属于「第二批外」。

## 8. 完成标准（每个阶段）

阶段计划中的任务全部完成；上述验证命令实际运行并如实记录（失败、跳过、未执行分别列出，不写「通过」）；交接写完且 `review_status: ready_for_review`；`docs/tasks.md` 与规格已更新；没有放宽的断言；没有越界改动。最终说明只报告已验证的结果、运行的命令与仍需人工决策的事项。

## 9. 首个动作

读完第 2 节，复核第 5 节基线与 PR #321 状态，认领 R1，写 R1 的代码级计划交负责人确认。
