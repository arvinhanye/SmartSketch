# 交接：前端改版方向 A「工作台」+ 学生自助注册（UI-01、AUTH-01）

- 分支：`claude/frontend-redesign-vzvfus`，基线 `main@fccc1ca`
- 决策：用户在方案对比页（https://claude.ai/artifact/KgH1oJ3mqxSaWhGwZxg3Qi）选定「A + 1」：方向 A 工作台，学生自助注册、教师仍由管理员开通。ADR-079 记录注册决定，**待签收**。

## 交付物

| 范围 | 文件 |
| --- | --- |
| 契约 | `src/contracts/api.v1.yaml`（`register`、`RegisterRequest`、`ErrorCode.USERNAME_TAKEN`）、`errors.v1.md`、生成物 `src/contracts/v1/generated/*` |
| 后端 | `app/api/auth.py`（`register` 路由）、`app/schemas/auth.py`（`RegisterRequest`，闭合）、`app/services/auth.py`（`RegistrationRateLimiter`、`AuthService.register_student`、令牌签发抽到 `_issue`）、`app/main.py`（限流器） |
| 前端 | `App.vue`（登录后左侧导航、退出登录）、`styles.css`（工作台配色令牌与外壳）、`components/AuthLayout.vue`、`views/LoginView.vue`、`views/RegisterView.vue`、`router/index.ts`（`REGISTER_ROUTE`、`guestOnly`）、`api/auth.ts`、`api/http.ts`（注册为公开路径）、三处错误码副本、`views/TeacherGraphView.vue`（三栏）、`components/GraphToolbar.vue`（`vertical`）、`views/StudentGraphView.vue`（右侧学习栏）、`components/Recommendations.vue`（卡片化，评分明细折叠）、`views/ChatView.vue`（知识点名称、出处侧栏）、`composables/useChat.ts`（响应式修复） |
| 文档 | `docs/decisions.md` ADR-079、`specs/identity-access.md` §1.2/§4.2/§4.3、`docs/architecture.md` 枚举表、`docs/tasks.md` |
| 测试 | `tests/backend/test_adr079_register.py`、`tests/frontend/adr079.test.ts`、`tests/frontend/redesign-chat.test.ts`；`tests/frontend/h13.test.ts` 假 `AuthApi` 补 `register` |

## 验证

- `PATH=<openapi-typescript>:.venv/bin:$PATH ./scripts/verify.sh full` → 见 PR 描述中的实际结果。
- `./scripts/gen-contracts.sh`（openapi-typescript 7.4.4）重新生成，`contracts.sh` 通过。
- 真实环境：`scripts/start-demo.sh`（演示模型模式）后用 Playwright 走登录、注册（本地校验与成功注册）、教师图谱编辑、学生图谱、问答（覆盖与未覆盖），截图在 `/mnt/project-files/redesign-0927/`。

## 接口 / 数据变更

- 新增 `POST /api/v1/auth/register`（201 `LoginResponse`；409 `USERNAME_TAKEN`；422；429）。新增错误码 `USERNAME_TAKEN`（兼容变更）。
- 无迁移，沿用 `users` 表。

## 风险

- 注册接口会暴露用户名是否存在（ADR-079 已接受，靠限流缓解）；限流按进程计，多进程只是缓解。
- 没有关闭自助注册的开关；公开部署前如需关闭，另立任务加环境变量。
- G6 画布在大图上整体缩得很小（改版前已存在），本任务只改了画布容器与周边布局。
- 未在 macOS 上实测。

## 回滚

见 ADR-079「回滚」；前端改版为纯样式与布局改动，回滚即撤回对应提交。

## 下一步

- 用户签收 ADR-079。
- 画布可读性（节点标签、初始缩放）另立任务。
