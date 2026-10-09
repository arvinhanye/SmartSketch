# 历史 CI 失败修复
review_status: ready_for_review
task_id: CLAUDE-CI-REPAIR-20261008
日期：2026-10-08；负责人：Claude。基线：PR #323 head `f76020f`（#321→main、#322→#321、#323→#322，均 OPEN 未合并；main `bdb89c4` 是其祖先，故以 #323 head 为基线并快进）。

## 根因分类
| 失败 | 判定 | 处理 |
| --- | --- | --- |
| `b03.test.ts` 未登录提示 4 项 | 测试宿主过时：提示已由登录页（`main.ts` 注入的 `LoginView`）浮动承载，测试没注入登录页也没装 Pinia，RouterView 为空 | 宿主与生产一致：注入 `LoginView`、`createPinia()`、认证桩；断言改为不出现教师/学生首页标题 |
| `graph-detail-layout.test.ts` 35% | 旧断言：用户已确认默认 25% + 可调宽（`--gw-panel-width`） | 断言改为 `var(--gw-panel-width, 25%)` 与分隔条位置；未恢复固定 35% |
| `test_c02b…upgrade_from_017` | 旧断言：期望仅应用 `["018"]` | 改为“018 排第一且应用 018 之后的全部待应用迁移” |
| `test_f12` / `test_g02` / `test_f13` 回滚重放 | **真实缺陷**：`019_teacher_embedding_configs.sql` 没有 `-- ROLLBACK:` 行，其它迁移（007–018）都有。回滚到更早版本时 019 的历史行留下，随后 `migrate()` 正确拒绝“应用比已应用版本更旧的迁移” | 给 019 补 4 行回滚（删触发器×2、删表、删历史行）；新增 `tests/backend/test_migration_rollbacks.py`（007 起每个迁移必须有回滚且含历史行删除；全部迁移逆序回滚后可重放）。迁移顺序防线未改 |
| E2E 登录 `getByLabel('密码')` | 测试选择器歧义：显隐按钮的无障碍名称“显示密码”含子串 | `exact: true`；按钮名称保持清晰，不改组件 |
| E2E 教师用例卡在创建课程 | 过时步骤：新版课程页把创建表单收进弹层 | 先点 `[data-test=course-create-open]` |
| E2E 个人模式搜索 | 过时步骤：新版图谱页“搜索回车只定位并预览，查看详情才打开” | 断言预览卡名称，再点“查看详情” |

## 迁移 019 的兼容与回滚（需要人工注意）
- 修改的是**已存在**的迁移文件，迁移校验和随之变化。019 只存在于未合并的 PR #323，仅 Codex 原开发机的开发库已应用过旧 019；该库再启动会报 `Migration 019 checksum changed`。表结构完全相同，只多了注释。处理办法二选一：① 用 `docs/handoffs/codex-teacher-embedding.md` 记录的迁移前备份恢复后重新迁移；② 在确认该库没有其它漂移后，由维护者手工更新其 `schema_migrations.checksum`。本任务**没有**也不会修改任何真实库的迁移记录。
- 回滚本任务：`git revert` 对应提交即可；回滚 019 本身的手工步骤已写在文件头 `ROLLBACK:` 行（会删除教师向量覆盖配置表，教师需重填；Neo4j 向量属性不删）。

## 验证（实际命令与结果）
- `.venv/bin/python -m pytest tests/backend/test_c02b_disable_thinking.py tests/backend/test_f12.py tests/backend/test_g02.py tests/backend/test_d10.py -q`：100 passed；`tests/backend/test_migration_rollbacks.py`：14 passed。
- RED/GREEN：f12/g02 在修复前复现 `MigrationError`；新守卫测试在还原旧 019 时 2 项失败（019 缺回滚、逆序回滚重放失败），补回滚后 14 项全过。
- `npx vitest run tests/frontend/b03.test.ts tests/frontend/graph-detail-layout.test.ts`：通过。
- E2E：`scripts/e2e.sh tests/e2e/teacher.spec.ts tests/e2e/student.spec.ts`（登录修复后学生全流程通过；教师用例在课程创建处失败→修复步骤后在评审环境通过，含 4 格式上传、成环拒绝、发布、学生可见）；`E2E_LLM_MODE=personal scripts/e2e.sh tests/e2e/personal.spec.ts` 隔离重跑 4/4 通过。
- 全量门禁结果见 `docs/tasks.md` 验收与 `claude-ui-review-20261008.md` 的“最终门禁”。

## 未验证 / 风险
- 登录失败不再遮蔽下游：本轮已实际跑过上传→审核→发布→学生问答（演示模型），但没有真实供应商兼容性证据。
- 首次个人模式 E2E 在与后端/前端全量门禁并发时出现 2 项负载超时和 1 项 Neo4j 503（`STORAGE_UNAVAILABLE`）；隔离重跑通过。结论：该套件对 CPU/Docker 争用敏感，门禁请单独执行。

## 下一步
合并前由人工决定 019 校验和的处理方式（见上）；PR 链仍需按 #321→#322→#323 顺序处理，本任务不推送、不合并。
