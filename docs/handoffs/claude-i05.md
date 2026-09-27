# I05 推荐查询 API 交接（Claude）

- 状态：实现完成，待 PR 审查/合并（issue #128）。分支 `claude/project-thread-98kaqt`，基线 `main@ac21e5d`。
- 交付：
  - `src/backend/app/services/learning/recommend.py`：`get_recommendations`（一次 `resolve_published` → 读绑定版本快照图 → `project_progress` → I03 `eligible_set` → I04 `rank_candidates` → 截断）；`load_version_graph` 按 `version_id` 缓存校验通过的图（`clear_cache`）。
  - `src/backend/app/api/recommend.py`：`getRecommendations`，`limit` 1～50 默认 10，只做协议转换与错误映射。
  - `tests/backend/test_i05.py`：34 个用例，真实迁移 SQLite + 真实应用，版本经 G04 仓储真实提交；完整性用例直接改快照并重算摘要。
  - 范围扩展：`app/main.py` 注册路由；`app/schemas/contracts.py` 导出 `RecommendResponse`；`specs/learning-path.md` 状态行；`docs/architecture.md` `MasteryStatus` 行；`docs/decisions.md` ADR-069；`docs/tasks.md` I05 节。
- 接口/数据：按既有契约实现，无契约、迁移、依赖变更。约定见 ADR-069：图读已提交快照（不读 Neo4j）；仅学生成员；完整性故障与未预期异常 500 `INTERNAL_ERROR` + `details.request_id`。
- 验证（本机 Linux，venv 按 `src/backend[test]` 安装，另装 `datamodel-code-generator==0.26.3`、`openapi-typescript@7.4.4` 供契约门禁）：
  - `python -m pytest tests/backend/test_i05.py -q` → 34 passed。
  - 反向篡改 6 处：投影时重新解析指针（1 failed）、`total_eligible` 取截断后长度（2）、不按 `PREREQUISITE` 过滤边（1）、吞掉图校验错误（5）、截断前按 `kp_id` 重排（1）、去掉服务层 `limit` 校验（4）；均检出，已恢复。
  - `python -m pytest tests/backend -q` → 3257 passed、27 skipped。
  - `./scripts/verify.sh` → `PASS contracts gate`、`Scaffold verification passed.`（未装生成器时 B14 与门禁负向测试因缺工具失败，与本改动无关）。
  - `git diff --check` 干净。
- 风险：每个新版本首次请求解析一次快照 JSON；`project_progress` 每次读本课程全部已提交版本行（沿用 I02）。I04 的 `invalid_number` 在此路径不可达（`load_snapshot` 已校验范围）。
- 下一步：I06 前端消费 `RecommendResponse`；ADR-069 待 ArvinHan 签收。
- 回滚：见 ADR-069「回滚」；无持久层变更。

## 独立审查与修复（2026-09-27，PR #291 审查代理，worktree `.claude/worktrees/pr291`）

- 结论：APPROVE_WITH_NOTES；未发现实现缺陷，未改实现与契约真源，只做测试加固。
- 验证（本机 macOS，`PYTHONPATH=$PWD/src/backend`，解释器 `/Users/arvinhan/Desktop/SmartSketch/.venv/bin/python`）：
  - 自证：`app.services.learning.recommend.__file__` = 本 worktree 的 `src/backend/app/services/learning/recommend.py`。
  - `pytest tests/backend/test_i05.py -q` → 36 passed。
  - `pytest tests/backend -q` → 3259 passed、27 skipped。
- 反向篡改 8 处（每处单独改、跑定向全文件、记录判红后恢复）：解析两次（1 failed）、未发布改 200 `all_mastered`（1）、反转 `kp_id` 并列键（1）、吞掉图校验错误（6）、跳过成环检测（3）、投影改用当前指针（1）、截断后计 `total_eligible`（2）均判红。
- 存活 1 处：删除 `load_version_graph` 的摘要复核（`digest_of(raw) != record.digest`）后仍 34 passed——该检查只在 G07 修订缓存与 I02 谱系缓存已热时才唯一生效，原用例被 `resolve_published`/`_lineage` 更早的同类检查拦住。
- 修复（仅 `tests/backend/test_i05.py`）：新增 `test_graph_read_revalidates_snapshot_with_warm_version_caches`（`digest-column`/`foreign-course` 两例：先预热 resolver 与 progress 缓存、只冷掉 I05 图缓存，再断言 500），并给课程隔离用例补「查询串 `user_id` 不能冒充身份」断言；复跑删除摘要复核与删除他课复核两处篡改均判红。
- 遗留（需人裁决）：app 生成的 OpenAPI 把 500 记为 `Error`，契约真源该响应为 `LearningIntegrityError`；实际响应体经 `LearningIntegrityError` schema 校验一致。I02 `api/progress.py` 同样写法，属全局惯例，未在本次改。
