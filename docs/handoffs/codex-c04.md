# C04 课程列表与创建 API 交接

- 状态与基线：本分支功能完成并通过本地验证；`codex/c04-courses-api` 基于 C03 提交 `44f77cf`，其父提交为当前本地 main `a7a0be0`。初版 C04 提交 `54a8e77`；随后根据独立审查补显式 null 边界。C03 PR #216 仍以 main 为目标且未合并；C04 不能据此声称合并后集成通过。
- 改动文件：`src/backend/app/api/courses.py`、`src/backend/app/services/courses.py`、`src/backend/app/schemas/contracts.py`、`src/backend/app/main.py`、`tests/backend/test_c04.py`、`docs/architecture.md`、`docs/tasks.md`、本交接。`main.py` 为注册路由扩围，schema 加载器为消费生成 Python DTO 扩围，均已在任务板登记。
- 接口与数据：沿用 `src/contracts/api.v1.yaml` 的 `GET /api/v1/courses`（200 `Course[]`）和 `POST /api/v1/courses`（201 `Course`、`CourseCreate` 请求）及既有 401/403/422 错误；未改 REST 真源、生成物、SSE、图谱或迁移。`my_role` 取课程成员行，创建只允许教师账号。学生成员课程仅在 `published_version` 非空后列出，状态按 V7 从发布指针和修订号推导。C02 仓储在单事务写课程与创建者教师成员。生成模型可选但不可为 null 的 `kp_count` 未有真实计数时省略。
- 调用链：H01 `CoursesView`/`useCourses` → B15 API 客户端/生成 TS 类型 → FastAPI `api/courses.py` → C03 当前身份/教师账号依赖 → `services/courses.py` → C02 `repositories/courses.py` → SQLite `courses`/`course_members`。无 worker、Neo4j、SSE。路由不含业务 SQL。
- 验证：隔离 SQLite 的 HTTP 用例覆盖创建与成员事务、跨课程列表过滤、学生未发布过滤、教师账号的学生成员角色、无令牌/学生创建拒绝、伪造字段、姓名边界、显式 `description: null` 拒绝和成员插入失败回滚；响应与生成 Python `Course` 及生成 OpenAPI JSON schema 匹配。首个用例在实现前因 404 失败；null 用例在修复前失败；最终 C04 10 passed。C03 基线 17 passed；后端全量 1029 passed（两条既有 Starlette/httpx 弃用警告）。`scripts/gen-contracts.sh --check` exit 0。`scripts/verify.sh` 首次在 Windows GBK 控制台遇 `UnicodeEncodeError` exit 1，设置 `PYTHONIOENCODING=utf-8` 后 exit 0，契约负例 24 项通过。前端类型检查/构建与 CI 未运行，合并后验证未运行。详见任务板命令。
- 风险：运行时代码从仓库 `src/contracts/v1/generated/python/models.py` 加载生成模型；后续 K08 打包时必须把生成物纳入镜像/安装布局。C03 PR #216 未合并，因此 C04 尚不能单独以 main 为基线提交一个只含 C04 差异的 PR。
- 回滚：无数据迁移；仅撤销本分支 C04 差异即可，保留 C03、其他任务分支及现有数据库。
- 下一位成员的首个动作：项目负责人合并 C03 PR #216 后，将 C04 分支更新到新的 main，检查 PR diff 只含 C04、确认 `app/main.py` 无冲突，重新运行 C04 定向测试、后端全量、契约检查、`verify.sh` 与 CI，然后创建/审查一个以 main 为目标的 C04 PR。最终合并仍由项目负责人执行。
