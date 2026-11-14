# PR #351 审查修复交接

- 日期：2026-11-14；负责人：Codex；原 PR head：`a1f086487d00f497d721b5bf0adacb65b21664a4`。
- 范围：只修复 R351-1～5 及同一操作的串行保护；不改后端、契约、数据库、权限或可撤销操作范围。
- 工作位置：固定 head 的独立临时快照 `/tmp/smartsketch-pr351-review-snapshot`；未改主工作区、未提交或推送。合并与任务看板由协调者处理。

## 交付

1. `useEditHistory`：运行代次使 `clear()` / 作用域释放后的晚到结果失效；旧请求收尾不能解锁新运行。允许步骤返回固定失败原因，提供 `invalidateRedo()`。
2. 新增 `useNodeHistory`：节点历史写入从视图移到组合式逻辑；PATCH、解锁都带课程作用域和可取消信号，每个 await 后检查所有者。确认响应先同步到当前草稿；部分成功或写入异常仍读回实际状态。图谱或面板读回失败不报告完整成功、不添加该步重做。
3. `useTeacherGraph.refresh()` 与 `useNodeEditor.reload()` 返回可等待的成功状态；历史步骤等待图谱与当前面板读回，使用新的修订号重做。
4. `NodeEditor` 在历史操作中禁用字段及写按钮；教师页编辑面板暂时不可交互；`useRelationHistory` 拒绝插入普通关系写入。已有节点写入、新建与删除在途时也阻止启动历史操作。
5. 任意新的成功节点写入都清空重做，包括不可逆的空字段首次保存、解锁、新建和删除。
6. 独立复审补充：新建只在有效刷新成功后自动选中；删除在确认成功时立即清空被删节点，刷新结束后不再改变选中。保护切课和同课程改选后的草稿。

## 文件所有权

- `src/frontend/src/composables/useEditHistory.ts`
- `src/frontend/src/composables/useNodeHistory.ts`（新增）
- `src/frontend/src/composables/useNodeEditor.ts`
- `src/frontend/src/composables/useTeacherGraph.ts`
- `src/frontend/src/composables/useRelationHistory.ts`
- `src/frontend/src/components/NodeEditor.vue`
- `src/frontend/src/views/TeacherGraphView.vue`
- `tests/frontend/edit-history.test.ts`
- `tests/frontend/h14.test.ts`
- `specs/course-knowledge-graph.md`
- 本交接文件

## 验证证据

永久测试复用已有两个模块的夹具，新增 23 条：历史清空和释放；四个阶段（PATCH、unlock、图谱 GET、面板 GET）的切课与卸载；输入保护；不可记录保存和解锁清空重做；部分成功同步；慢 / 失败读回；历史期间关系写入串行；新建跨课程及删除跨课程 / 同课程改选后的迟到刷新。临时审查文件已移到测试目录外，不随补丁交付。

| 检查 | 结果 |
| --- | --- |
| 修复前两个测试模块（新增回归后） | exit 1；15 failed / 105 passed（120）；`/tmp/smartsketch-pr351-fixes-red.log` |
| 关系串行保护单独红阶段 | exit 1；1 failed / 16 passed（17）；`/tmp/smartsketch-pr351-fixes-red-serialization.log` |
| 两个测试模块修复后 | exit 0；2 文件 / 121 passed；`/tmp/smartsketch-pr351-fixes-green2.log` |
| `npm --prefix src/frontend run type-check` | exit 0；测试 ES2022 类型兼容问题修正后；`/tmp/smartsketch-pr351-fixes-typecheck2.log` |
| 首轮 `scripts/verify/frontend.sh full` | exit 2：开头测试类型错误；随后 90 文件 / 1572 passed，build 成功。该轮不计作完整门禁通过 |
| 第一轮修复完整门禁 | exit 0；type-check、90 文件 / 1572 passed、build 全部通过；`/tmp/smartsketch-pr351-fixes-frontend-final.log` |
| 复审新增回归红阶段 | exit 1；3 failed（过滤运行，其余 104 条未执行）；`/tmp/smartsketch-pr351-fixes-callback-red.log` |
| 复审修复后两个完整测试模块 | exit 0；2 文件 / 124 passed；`/tmp/smartsketch-pr351-fixes-callback-green.log` |
| 复审修复后最终完整门禁 | exit 0；type-check、90 文件 / 1575 passed、build 全部通过；`/tmp/smartsketch-pr351-fixes-frontend-reviewed.log` |

复现命令（快照根目录）：

```bash
./src/frontend/node_modules/.bin/vitest run --config src/frontend/vitest.config.ts tests/frontend/edit-history.test.ts tests/frontend/h14.test.ts --reporter=dot
PYTHON=/Users/arvinhan/Desktop/SmartSketch-main/.venv/bin/python scripts/verify/frontend.sh full
```

## 限制与回滚

- 自动化使用真实 Vue 页面、组合式逻辑和课程 store，API 为可控替身；修订测试明确校验 `expected_revision`。未声称连接真实后端或完成真实画布 / 窄屏 / 读屏视觉验收。
- 请求取消与晚到隔离只能阻止前端继续执行和采用响应，不能回滚后端已经提交的请求。部分成功时显示实际已确认状态并提示核对。
- 全量日志包含既有负路径 Vue / jsdom 提示及构建大 chunk 提醒；不属于此次修复的测试失败。
- 回滚仅还原本修复补丁；没有数据库迁移、依赖变更或持久化历史格式变更。
- 独立复审、更新分支 / CI / 合并由协调者执行；本交接不表示已经合并。
