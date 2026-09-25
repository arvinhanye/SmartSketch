# C03 身份边界与课程访问依赖交接

- 任务与状态：C03，DONE（待审查/集成）。基线 `main@a7a0be0`，在当前工作区实施；原有未提交的 `docs/tasks.md`、`.codex/`、`outputs/` 等其他成果未回退或清理。
- 交付：`src/backend/app/services/access.py` 验证 C13 HS256 JWT 四个载荷字段、算法、签名与时间，按 `sub` 实时回查账号；依据实时课程成员角色和发布状态授权。`src/backend/app/api/dependencies.py` 提供 `current_user`、`teacher_account`、`course_reader`、`course_teacher`、`course_student`、`task_teacher` 和统一错误响应。账号与任务仓储各增加一个只读查询；`app/main.py` 注册访问错误处理器；`docs/architecture.md` 记录接入边界。
- 验证：`.venv/Scripts/python.exe -m pytest tests/backend/test_c03.py -q`：17 passed；`.venv/Scripts/python.exe -m pytest tests/backend -q --tb=short`：1019 passed（两条既有 Starlette/httpx 弃用警告）；Git Bash 运行 `./scripts/verify.sh`：exit 0，契约门禁与生成物检查通过；`git diff --check`：exit 0；独立只读代码审查未发现需修复的问题。
- 接口/数据/配置：无公开 REST、数据库迁移或配置项变化。新增 Python 内部依赖接口；下游路由须复用依赖，而不能从请求 `user_id` 或 JWT `role` 做授权。任务归属读取不返回任务快照。
- 风险与下一步：C04、C07、C10、C11、C15、F07、I02、J07 等路由尚未在本任务接入这些依赖；各实现方按访问矩阵选相应依赖，并在自己的端到端测试中验证最终操作。学生读取的具体已发布版本绑定仍由 A04/F07 执行；C03 仅门禁检查 `published_version` 是否存在。无数据迁移，回滚可撤销新增服务/依赖及仓储只读函数和 `main.py` 处理器注册。
