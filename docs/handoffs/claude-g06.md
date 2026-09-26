# Claude 交接：G06 回滚、版本列表与发布接口

- review_status: ready_for_review
- task_id: G06
- 分支：`claude/project-thread-sqwla4`（与 G05 同一 PR #264）；base：`main@a44c680`
- 状态：DONE（待 PR 审查/合并）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/versions/rollback.py` | `rollback(ctx, course_id, version, created_by=)`：V6 R2～R7 |
| `src/backend/app/services/versions/materialize.py`（扩围） | `copy_version`（R5，含向量复制、先删后建）、`SourceCopyMissing` |
| `src/backend/app/api/versions.py` | `GET /versions`（listVersions）、`POST /versions/{version}/rollback`（rollbackVersion）、`POST /publish`（publishGraph，扩围）、`publish_context` |
| `src/backend/app/main.py`、`src/backend/app/schemas/contracts.py`（扩围） | 注册路由；导出 `GraphVersion`、`PublishResult` 等契约模型 |
| `tests/backend/test_g06.py` | 15 个用例：三个接口的鉴权、契约形状、错误映射（服务打桩，CI 覆盖） |
| `tests/integration/test_g06.py` | 9 个用例：真实 Neo4j 上的回滚 |
| ADR-041、`docs/tasks.md` | 决定与看板 |

## 验收对照

| 条目 | 用例 |
| --- | --- |
| PUB-3 | `test_rollback_rolls_forward_as_a_new_version`（v1～v5 → 回滚到 v3 得 v6，向量复制、模型未调用） |
| PUB-7 | `test_rollback_to_current_or_identical_content_is_idempotent` |
| PUB-15 | `test_rollback_never_touches_the_draft_and_derives_status` |
| PUB-16 | `test_lock_timeout_in_r6_still_rolls_back_then_publish_corrects` |
| PUB-25 | `test_missing_failed_or_foreign_versions_are_not_found`；接口层 `test_rollback_to_missing_failed_or_foreign_versions_is_404` |
| PUB-26、V12 | `test_broken_source_fails_without_re_embedding[missing_copy/foreign_space]` |
| A03 §3 | `test_rollback_does_not_complete_tasks` |
| 发布与回滚互斥 | `test_rollback_and_publish_exclude_each_other` |
| 版本列表、鉴权、错误映射 | `tests/backend/test_g06.py` |

## 命令与实际结果

`S=<scratchpad>`，`$S/pt.sh` 同 `claude-e12.md`；真实 Neo4j 用 `claude-f04.md` 记录的 Maven harness。

| 命令 | 结果 |
| --- | --- |
| `$S/pt.sh tests/backend/test_g06.py -q` | 15 passed |
| `$S/pt.sh tests/integration/test_g06.py -q`（带 Neo4j 环境变量） | 9 passed |
| `$S/pt.sh tests/backend -q` | 2980 passed |
| `$S/pt.sh tests/integration -q`（带 Neo4j 环境变量） | 157 passed、4 skipped |
| `PATH=$S/venv/bin:$S/tools/node_modules/.bin:$PATH ./scripts/verify.sh` | exit 0 |

反向篡改（改 `rollback.py` 后跑集成 `test_g06.py`，每次恢复）：去掉 R3 幂等（1 failed）；去掉空间核对（1 failed）；R7 不比较摘要就写 r（1 failed）；R7 恒写 -1（1 failed）；回滚执行 T7（1 failed）；不复制副本（4 failed）；不存在的版本不报 404（1 failed）。

## 接口 / 数据变更

- 新增三个 HTTP 路由，形状按 `api.v1.yaml` 既有契约，无契约改动、无迁移。

## 风险

- `copy_version` 首版用 `SET n = properties(k), n.version_id = …` 撞上 `(course_id, version_id, kp_id)` 唯一约束（中间态与源节点重复），已改为映射投影一次写入。
- 发布上下文按应用缓存一个 Neo4j 连接池，与 F07 `graph_reader` 各自一个；如需合并，另行调整。

## 下一步 / 待决

- G07 统一版本解析器（学生读取固定 `version_id`）。
