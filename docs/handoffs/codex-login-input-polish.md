# LOGIN-INPUT-POLISH 认证页焦点与全站界面文字选择

- 日期：2026-11-15；负责人：Codex；基线：`5cc6d08`。
- 状态：DONE；修改、自动检查、Docker 浏览器及用户视觉验收通过。用户于 2026-11-15 明确授权提交、推送及创建 PR；分支 `codex/ui-text-selection`，发布结果以对应 PR 为准，不自动合并。

## 改动与决定

- `src/frontend/src/styles/selection.css`（新增）、`src/frontend/src/App.vue`：统一禁止认证页静态文字、顶栏/导航、静态标题、表单标签、工具栏文字拖选；不在整个 app/body 上禁止选择。
- 输入框、文本域、可编辑区域显式恢复 `user-select: text`；问答正文及其标题、知识详情标题、来源查看器、课程名、用户名保留选择；邀请码保留 `user-select: all`，同时提供 WebKit 前缀。
- `LoginView.vue`、`RegisterView.vue`：用户名、密码、确认密码取消黄色焦点外框，保留绿色下划线；按钮和链接原有键盘焦点提示保持。
- `specs/identity-access.md` 与 `docs/tasks.md` 同步本次范围。认证逻辑、API、数据模型、依赖均未修改。

## 自动检查

- `PATH=/Users/arvinhan/Desktop/SmartSketch-main/.venv/bin:$PATH ./scripts/verify.sh`：exit 0，基础门禁通过。
- `npm --prefix src/frontend run type-check`：exit 0。
- `npm --prefix src/frontend run test -- --run --config /private/tmp/smartsketch-login-vitest.mts --testTimeout 30000`：91 文件 / 1578 用例通过，exit 0，无 skip。首轮误用默认 5 秒时限，4 条图谱用例超时；按仓库 `scripts/verify/frontend.sh` 既定 30 秒设置完整重跑通过，未修改测试或产品逻辑。
- 临时 Vitest 配置导入仓库原配置，仅移除会匹配本工作树 `.codex` 路径的 `**/.*/**` 排除规则；未改仓库测试配置。此环境问题与前轮一致。
- `docker build -f src/frontend/Dockerfile -t smartsketch-frontend:ui-selection-20261115 .`：exit 0，包含生产构建。
- 最后补充学生图谱课程名的选择例外、课程入口和说明面板控件规则后，`student-graph-workbench.test.ts graph-find.test.ts h01.test.ts` 定向复核 3 文件 / 78 用例通过（同上临时配置与 30 秒时限），重新构建 Docker 镜像并更新两个前端，exit 0。未把 78 条与全量 1578 条相加计数。
- `git diff --check` 通过；变更仅限 4 个前端文件与规格/任务/交接（共 7 文件）。
- 用户验收通过后的提交前复核：认证/课程/图谱相关用例 7 文件 / 137 用例通过，exit 0；日志 `/private/tmp/smartsketch-selection-precommit.log`。远端 main 仍为 `5cc6d08`，无需整合新的主线改动。

## Docker 与实际浏览器验收

- `http://127.0.0.1:8081/`：当前源码前端，容器 `smartsketch-ui-selection-preview-20261115`，连接既有后端。原 `8080` 应用未修改；前轮预览容器已停止并保留为 `smartsketch-login-input-polish-20261115-before-shared`，方便回退。
- `http://127.0.0.1:8082/`：独立 Compose 项目 `smartsketch-ui-selection-20261115`，专属 SQLite/Neo4j 卷。使用本轮前端与已安装 `rc-55c0c17` 后端，真实 API/worker/Neo4j，LLM/向量使用内置 demo 模式，无外部模型调用。
- 本地启动配置：`.demo/ui-selection/compose.yaml` 和 `acceptance.env`，均被忽略；配置文件仅测试环境使用，不提交。
- 隔离库执行既有迁移/演示账号种子，再通过 `scripts/import-demo.py` 导入仓库自编课程，发布 v1；64 个知识点、71 条关系。真实账号和原业务库未改。
- 登录与注册：静态欢迎文字拖选为空；注册 3 个输入框 `outline: none`、输入可全选/删除，绿色下划线保留。登录真实测试账号成功。
- 课程、成员：标题和导航拖选为空；课程名称输入框及简介文本域可全选编辑；取消新建后无额外课程写入；邀请码点击全选，复制按钮显示“邀请码已复制”。
- 资料、审核、设置：静态标题 `user-select: none`；设置地址输入 `user-select: text`，焦点为绿色，未保存模型配置或调用外部服务。
- 教师图谱：工具栏搜索输入可全选编辑，知识正文实际拖选成功，出处片段可选中；只查看详情，无修改图谱。
- 学生问答：用内置 demo 模型回答“栈和队列有什么区别？”，回答正文与引用原文实际拖选成功，复制按钮显示“已复制回答和出处”。仅测试库产生本次问答记录。
- 最终镜像复核：学生图谱搜索可全选编辑；课程名称标题为 `user-select: text`；注册页、教师成员页和学生图谱已在浏览器打开并保留，分别对应 8081 业务后端预览与 8082 隔离示例环境。
- 自动审批拒绝读取现有剪贴板以备份/恢复，因可能接触任务外私人内容；后续不读取剪贴板，通过选区、输入编辑和复制按钮成功反馈完成验收。没有绕过审批。
- 截图：`/private/tmp/smartsketch-selection-register.jpg`、`smartsketch-selection-invite.jpg`、`smartsketch-selection-source.jpg`、`smartsketch-selection-answer.jpg`（均位于 `/private/tmp/`）。日志：`/private/tmp/smartsketch-selection-{verify,types,tests-final,build,up,seed}.log`；首轮超时日志保留在 `smartsketch-selection-tests.log`。
- 最后复核日志：`/private/tmp/smartsketch-selection-final-targeted.log`、`smartsketch-selection-build-final.log`、`smartsketch-selection-refresh.log`（均位于 `/private/tmp/`）。

## 后续与回滚

- 用户视觉验收已通过；按授权在 `codex/ui-text-selection` 提交本次 7 个文件、推送并开 PR，合并需后续指示。
- 此验收针对界面选择与焦点行为，未评估真实模型质量或跨浏览器兼容性；未读取剪贴板来逐字节比对复制结果。
- 无产品数据库迁移。代码按本任务差异回退；停止本轮预览容器可重启保留的旧预览。隔离示例栈可用其 Compose 单独停止；勿删除或操作原软件的数据卷。
