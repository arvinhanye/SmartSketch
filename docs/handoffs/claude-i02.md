# I02 掌握标记 API 交接（Claude）

- 状态：实现完成，待 PR 审查/合并（issue #125）。分支 `claude/project-thread-fqm6l4`，基线 `main@a7d8075`。
- 交付：
  - `src/backend/app/services/learning/progress.py`：读时投影 `project_progress`（供 I05 复用）、`get_progress`、批量写入 `update_progress`；已提交快照的节点集与谱系按 `version_id` 缓存（`clear_cache`）。
  - `src/backend/app/api/progress.py`：`getProgress`、`updateProgress`，仅做协议转换与错误映射。
  - `tests/backend/test_i02.py`：24 个用例，真实迁移 SQLite + 真实应用，版本经 G04/G06 仓储真实提交。
  - 范围扩展：`app/main.py` 注册路由；`app/schemas/contracts.py` 导出 `ProgressResponse`、`ProgressUpdate`；`services/learning/__init__.py` 文档串；`specs/learning-path.md` 状态行；`docs/architecture.md` `MasteryStatus` 行；`docs/decisions.md` ADR-064；`docs/tasks.md` I02 节。
- 接口/数据：按既有契约实现，无契约、迁移、依赖变更。约定见 ADR-064：仅学生成员可用；`PUT` 在 `BEGIN IMMEDIATE` 内按 G07 重新解析发布指针后整批复核；重复 `kp_id` 为通用 422 `reason = duplicate`；完整性故障与其他未预期异常为 500 `INTERNAL_ERROR` + `details.request_id`。
- 验证（本机 Linux，`.venv` 按 `src/backend[test]` 安装）：
  - `python -m pytest tests/backend/test_i02.py -q` → 24 passed。
  - 反向篡改 8 处（去掉 `force`、连续归属回溯、覆盖判定、不在发布版拒绝、重复检查、谱系缺陷判定、脏行告警、绑定版本号复核）检出 7 处；存活 1 处为绑定版本号复核（G07 已校验，冗余防护）。
  - `python -m pytest tests/backend tests/contracts -q` → 3414 passed、3 failed；3 项失败均为本机缺契约生成器（`datamodel-code-generator`、`openapi-typescript`）。按 `src/contracts/toolchain.txt` 装上后这 3 个文件 28 passed。
  - `./scripts/verify.sh`（生成器在 PATH 上）→ `PASS contracts gate`、`Scaffold verification passed.`
  - `git diff --check` 干净。
- 风险：投影每次读取本课程全部已提交版本行（快照解析已缓存），MVP 规模可接受；`PUT` 在持有写锁时用独立连接读取指针、版本与进度行（WAL 下读者不阻塞，写锁保证其间无其他提交）。
- 下一步：I05 推荐按同一绑定版本调用 `project_progress(...).mastered`；I06 前端消费 `ProgressResponse`；ADR-064 待签收。
- 回滚：见 ADR-064「回滚」；无持久层变更。
