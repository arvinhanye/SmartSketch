# F03 图约束、索引与空间写入边界交接

- 任务：F03；负责人：Codex（后端）；状态：完成实现并经一次性 Neo4j 5.26 容器验证。
- 基线：`main@ddbeb82`；开始时工作区无未提交变更。

## 交付与决定

- `src/backend/migrations/neo4j/001_constraints.cypher`：知识点、章节、共享块、关系守卫与四种关系的作用域唯一约束；贡献及修订查询索引。`RelationIdentity` 是 F06 在关系写事务中须 MERGE 的跨类型 `rel_id` 守卫；四种关系本身各有同类型复合唯一约束。
- `src/backend/app/repositories/graph_migrations.py`：逐条幂等迁移、脱敏连接入口、CLI、确定性分空间向量属性与索引、运行时当前空间校验、仅在外部前置检查通过后可建立的迁移上下文。当前空间通过 SQLite 新连接每次读取；上下文在切换或退出后失效。写入检查维度及有限数值，目标节点不存在则报错。
- `tests/integration/test_f03.py`：13 个无容器回归与 1 个可选真实 Neo4j 用例。真实用例覆盖复合唯一、跨版本共存、双空间向量索引与属性并存、迁移上下文失效；只在 `SMARTSKETCH_F03_URI/USER/PASSWORD` 显式设置时运行，并只清理自身标记的节点。
- 更新 `specs/teacher-review-publish.md`、`docs/architecture.md`、`src/backend/README.md`。无 REST/DTO 变更、无 SQLite 数据迁移、无新增依赖或环境变量。

## 验证

- 红灯：新测试首次因 `app.repositories.graph_migrations` 缺失而收集失败；新增 SQLite/CLI 测试分别因符号缺失而失败；连接关闭脱敏与缺失 SQLite 文件测试各先 1 failed。安装项目依赖后，真实 Neo4j 测试首次以向量索引 DDL 少一个 `}` 失败；新增语句大括号结构测试先红后修复。绿灯：`.venv/bin/python -m pytest tests/integration/test_f03.py -q` 离线 **13 passed / 1 skipped**，一次性 Neo4j 5.26 容器中 **14 passed**。
- `python3 -m compileall` 与 `git diff --check` → exit 0。
- `PATH="$PWD/.venv/bin:$PWD/src/frontend/node_modules/.bin:$PATH" ./scripts/verify.sh` → exit 0（契约负例 25 项、B14/B08/B09/B10/B12/B13 回归）。
- `.venv/bin/python -m pytest tests/backend -q` → **2105 passed / 1 warning**（Starlette 的已存在弃用警告）。沙箱内首次运行的 3 failed / 5 errors 均为 `127.0.0.1` 绑定被拒；允许回环监听的同一环境命令全绿。

## 风险、下一步与回滚

- 真实 Neo4j Community 5.26 已验证约束、向量索引和跨版本/跨空间共存；临时容器由 `trap` 删除。DDL 分条执行，不做整批回滚；如果历史数据冲突，停止服务、修复冲突后重跑。不可用时恢复 K10 的 Neo4j 迁移前备份，并核对 SQLite/Neo4j 恢复时间点；不通过删除文件规避失败。
- CLI 从仓库内的 `src/backend/migrations/neo4j/` 读取 DDL；后续 K08 部署打包须确保迁移文件随发布包分发，当前未验证仅安装 wheel 的运行方式。
- F06 首个动作：在同一关系写入事务中 MERGE `RelationIdentity(course_id, version_id, rel_id)`，并确保类型/端点与既有记录一致；仅有数据库守卫唯一约束并不能阻止未来写入者绕过守卫。F14 首个动作：将停机/租约/备份检查传给迁移上下文，先建目标空间索引，再按实际存量重算、核对和切换。
