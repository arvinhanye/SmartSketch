# Codex 交接：C06 资料和任务创建事务

- `task_id`: C06（GitHub issue #63）
- `review_status`: ready_for_review
- `pull_request`: https://github.com/arvinhanye/SmartSketch/pull/209
- `worktree`: `/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/c06-material-task-transaction`
- `branch`: `codex/c06-material-task-transaction`
- `base_commit`: `04f8ac6`（最新 `origin/main`）
- `review_commit`: `4ed5890`（C06 实现与测试；后续分支提交仅补交接/任务板）
- `scope`: 资料仓储、任务仓储、`003_tasks.sql`、C06 测试；另将 C13 迁移测试中的默认迁移序列断言同步到 003，原因和文件锁扩展已写入 `docs/tasks.md`。

## 交付与关键决定

- `materials.py` 将 C05 `StoredFile` 元数据写入 `materials`；不持久化绝对路径。
- `tasks.py` 以一个连接执行 `BEGIN IMMEDIATE`，在同一事务中插入资料与初始 `queued` 任务；任何失败都会回滚两者。
- `003_tasks.sql` 建立 `materials` 与 `processing_tasks`，任务对资料使用 `(course_id, document_id)` 外键，并以 `UNIQUE(course_id, idempotency_key)` 隔离幂等键。
- 同课程重复键返回既有 material/task，并标记 `created=False`；不同课程可使用相同键创建各自记录。上传调用方遇到重放时，应删除这次新落盘但未被引用的存储文件。
- 资料初始 `parse_status` 为 `queued`。再处理入口及 `Document.parse_status` 后续跟随哪个任务仍留给 C07 范围决议；本任务没有加再处理路径。
- 迁移号按 D-10 以 `origin/main@04f8ac6` 的最大迁移 `002` 选为 `003`；若合并前 main 新增更高编号，按 D-10 重新编号并重跑迁移测试。

## 验证（实际结果）

- `PATH=/private/tmp/c06-venv/bin:$PATH PYTHONPATH=src/backend python3 -m pytest -p no:cacheprovider tests/backend/test_c06.py -q`：`5 passed`。
- C01+C06 受影响回归：`23 passed`；修正 C13 迁移序列测试后，相关 6 项再次通过。
- `PATH=/private/tmp/c06-venv/bin:$PATH PYTHONPATH=src/backend python3 -m pytest -p no:cacheprovider tests/backend -q`：`725 passed, 1 warning`。警告为现有 Starlette/httpx TestClient 弃用提示。
- `PATH=/private/tmp/c06-venv/bin:$PATH ./scripts/verify.sh`：`Scaffold verification passed`；契约门禁、24 项负例、B08/B09/B10/B13 回归均通过。
- `git diff --check`：通过。
- 测试依赖安装在 `/private/tmp/c06-venv`，没有改仓库依赖声明。系统 `python3` 初始没有 pytest 与契约工具，最终验证均通过隔离环境执行。

## 风险、回滚、下一步

- C07 接入时应调用 `create_material_task()`，并在异常或 `created=False` 时补偿删除未被记录引用的刚落盘文件。
- C01 迁移为只向前：上线 003 前停止 API/worker 并按既有迁移器备份；需要数据库回滚时停止进程并以 003 前备份替换数据库后重启。没有提交 down 脚本。
- 首个后续动作：C07 接上上传 API 与 `FileStorage`，完成存储文件补偿；同时确定再处理与 `parse_status` 语义。
