# I01 学习进度仓储交接

- 状态：I01 实现与审查修复完成，待 PR 审查。基线为 `main@0b8aa73`；修复在隔离 worktree 中完成，未携带主工作区的 C07、C10、OPS-01、J02 等未提交文件。
- 交付：`011_progress.sql`、`app/repositories/progress.py`、`test_i01.py`，同步 `specs/learning-path.md`、`docs/architecture.md`、`docs/tasks.md`。
- 数据与接口：`learning_progress` 按 `(user_id, course_id, kp_id)` 保存原始状态和共享 `commit_sequence` 的 `write_seq`。`write_progress_in_transaction(database, ...)` 加入调用方的写事务，供 I02 在同一事务内完成版本复核、覆盖判定与写入；`write_progress(sqlite_url, ...)` 保留自行开事务的便捷用法。同值无覆盖要求时不取号；历史 dormant 行保留，历史上从未属于本课程的脏 ID 在读取时告警并忽略。无 HTTP 或配置变更。
- 审查修复：原 `write_progress` 总是另开 `BEGIN IMMEDIATE`，I02 无法把它与发布版本绑定原子组合。新增一个事务回滚用例先因缺少事务入口而失败；抽出调用方事务入口后，该用例及原有行为均通过。
- 验证：`test_i01.py` 6 passed；`test_i01.py tests/backend/test_g02.py` 28 passed；隔离 worktree 运行 `./scripts/verify.sh` exit 0（含契约生成物检查和 25 项门禁负例）；`git diff --check` exit 0。此次按要求未重跑后端全量。原实现阶段的后端全量结果属于修复前快照，不作为本次验收证据。
- 后续：I02 从 G07 取得发布版节点和谱系，在调用方写事务内判定 `force` 并调用 `write_progress_in_transaction`；指针变化时重新绑定并校验整批。进度投影与 HTTP 422 由 I02/I05 实现。当前历史版本并集读取每次扫描全部已提交快照，MVP 规模可接受。
- 回滚：迁移前停 API/worker，按 C01 流程恢复 `backups/*-before-011.sqlite`。手工删除进度表会丢失学生历史，须先备份；代码回滚只撤销本任务文件和文档，不触碰其他任务。
