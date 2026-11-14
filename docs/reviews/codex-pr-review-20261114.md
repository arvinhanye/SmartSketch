# 开放 PR 审核：2026-11-14

结论：本轮审核完成，合并阻塞。共确认 7 项 P2；未推送、未合并、未修改产品代码。#350 本批没有确认的新缺陷，但不能绕过其依赖 #348 合入 main。

| PR | 固定 head | 审核结论 | 处置 |
| --- | --- | --- | --- |
| [#348](https://github.com/arvinhanye/SmartSketch/pull/348) | `04286ec9aae4db818e67109a2d82ad73b8f6c620` | 2 项 P2 | 保留开放，修复后复审 |
| [#350](https://github.com/arvinhanye/SmartSketch/pull/350) | `27339d928691fbd676189e7879e4591da399d449` | 本批未发现 P1/P2，依赖 #348 | 保留开放，暂不改 base |
| [#351](https://github.com/arvinhanye/SmartSketch/pull/351) | `a1f086487d00f497d721b5bf0adacb65b21664a4` | 5 项 P2 | 保留开放，修复后复审 |

主线基线 `50e6cba066eafdb6341ba746dc11549dc0e6118a`。#348 的 merge-base 为 `31a7e6c260c0a3b63f4466d28812cf59f6dc12b2`；#350 相对 #348 head 审核；#351 相对主线基线审核。审查时无既有 review submission、inline review thread 或会话评论。本次结论保存在仓库文档，未代用户发布 GitHub 评论。

## #348：生成消歧与安全撤销

### R348-1 [P2] 撤销必须保持节点修订号不复用

位置：[undo.py:75–77](https://github.com/arvinhanye/SmartSketch/blob/04286ec9aae4db818e67109a2d82ad73b8f6c620/src/backend/app/services/fusion/undo.py#L75)。

逆向补丁直接复制历史节点，包括旧 `revision`。可复现序列：a+b 合并后 a 的修订号为 2；教师读取此版本；撤销将修订号恢复为 1；随后 a+c 合并又得到 2。原编辑请求的 `expected_revision=2` 被现行 `edit_node._current` 接受，虽然 aliases/merged_from 已由 b 变为 c，可能覆盖新内容。

最小修复方向：给撤销涉及的节点分配未使用过的新修订号，并使后续撤销重建/冲突比较兼容该策略。回归需覆盖合并→读取→撤销→不同成员再合并→旧请求被拒绝，不能只断言草稿整体修订号增加。

### R348-2 [P2] 取消或失败资料的计划引用阻断删除

位置：[021_fusion_projections.sql:17](https://github.com/arvinhanye/SmartSketch/blob/04286ec9aae4db818e67109a2d82ad73b8f6c620/src/backend/migrations/021_fusion_projections.sql#L17)。

`fusion_plans.task_id` 默认 RESTRICT，但既有资料删除事务在任务已 failed/cancelled、无贡献且清理完成后直接删除 `processing_tasks`。生成 prepared 计划后在 T5 前取消，或 persisting 最终失败并完成清理，会在该删除路径触发 `IntegrityError: FOREIGN KEY constraint failed`。全后端没有计划删除路径；相同条件、没有计划的资料可正常删除。

最小修复方向：在现有贡献/处理中/待清理校验之后，删除任务之前，清理对应未生效计划；也可评估外键级联，但需明确迁移与审计保留规则。回归须包含有/无计划的失败和取消资料，以及有效图谱贡献仍禁止删除的对照。

两项均在固定 head 的临时快照复现，协调者独立复跑得到相同结果。租约到期但未接管时的调用行为因规格允许的 token fencing 边界不够明确，未列为正式缺陷。

## #351：图谱撤销重做

以下反例均挂载实际 Vue 页面，使用注入 API 替身控制响应顺序；没有修改 PR 源码。涉及修订的反例显式校验 `expected_revision`。

### R351-1 [P2] 撤销在途期间的新输入被丢弃

位置：[TeacherGraphView.vue:326–329](https://github.com/arvinhanye/SmartSketch/blob/a1f086487d00f497d721b5bf0adacb65b21664a4/src/frontend/src/views/TeacherGraphView.vue#L326)。保存名称后开始延迟的撤销，再在仍可编辑的输入框键入新文字；响应后的 `reload()` 无条件丢弃新草稿。开始时检查 dirty 无法保护请求在途期间的输入。

修复方向：在整个操作期间锁定相关编辑，或响应时保护/确认新草稿；回归覆盖延迟 PATCH/unlock 期间继续输入。

### R351-2 [P2] 切课清空历史后，晚到响应复活旧记录

位置：[useEditHistory.ts:69–71](https://github.com/arvinhanye/SmartSketch/blob/a1f086487d00f497d721b5bf0adacb65b21664a4/src/frontend/src/composables/useEditHistory.ts#L69)。课程 A 撤销在途时切到 B，watcher 虽清空历史，旧 run 完成后仍向目标栈加入 A 的 step。B 出现 A 的重做记录和成功提示。

修复方向：给历史执行绑定 generation/课程作用域，clear、切课、卸载后忽略晚到结果。这里只确认历史污染，不据此宣称必然发生跨课程写入。

### R351-3 [P2] 不可撤销的新保存仍须清空旧重做

位置：[TeacherGraphView.vue:338–340](https://github.com/arvinhanye/SmartSketch/blob/a1f086487d00f497d721b5bf0adacb65b21664a4/src/frontend/src/views/TeacherGraphView.vue#L338)。名称 A 保存为 B 后撤销，再保存名称 C 并首次填写原值 undefined 的 difficulty；此分支直接返回，没有清空 redo。旧“重做 B”仍可执行，将已保存的 C 改回 B。

修复方向：所有成功的新写入均使旧 redo 失效；是否能进入 undo 是另一判断。保留接口不支持恢复空字段的现有约束。

### R351-4 [P2] 撤销部分成功后没有同步真实状态

位置：[TeacherGraphView.vue:326–332](https://github.com/arvinhanye/SmartSketch/blob/a1f086487d00f497d721b5bf0adacb65b21664a4/src/frontend/src/views/TeacherGraphView.vue#L326)。PATCH 已还原字段，后续 unlock 返回 409 时，catch 跳过刷新，页面仍显示旧名称/修订，服务器已改变，历史却被移除。

修复方向：任何一步可能已写入后重新读取真实状态，并区分部分完成；回归包含 PATCH 成功而 unlock 冲突、课程忙或网络失败。

### R351-5 [P2] 图谱刷新未完成便开放重做

位置：[TeacherGraphView.vue:328–330](https://github.com/arvinhanye/SmartSketch/blob/a1f086487d00f497d721b5bf0adacb65b21664a4/src/frontend/src/views/TeacherGraphView.vue#L328)。`teacher.refresh()` 的公开实现返回 void，因此 await 没有等待 GET 草稿图谱。PATCH/unlock 已把修订从 2 增至 4，而旧图仍为 2 时，立即重做会发送旧修订，被后端拒绝并丢弃有效 redo。

修复方向：真正等待刷新，或用已确认响应更新节点/修订后再结束历史操作。回归必须让图谱 GET 延迟，并让 API 替身校验修订号。

## 验证与覆盖

使用 Open Code Review delegate 的文件筛选和规则解析，随后逐文件人工审查。按 PR 分计生产文件：#348 为 43/43、#350 为 17/17、#351 为 8/8，均无 skipped；这些不是去重后的仓库文件数。OCR 默认排除的测试/文档按相关性另行阅读；#351 的全部 6 个补充文件均检查。

| 实际执行 | 结果 |
| --- | --- |
| #348 与 main 的本地试合并快照：`PATH="$PWD/.venv/bin:$PATH" ./scripts/verify.sh` | exit 0；契约与生成物、负向门禁、基础检查通过 |
| 同快照：消歧/融合/投影/分层定向 pytest | exit 0；150 passed，1 条既有弃用警告 |
| #348 固定 head：删除与修订复现脚本，协调者复跑 | exit 0；无计划资料删除成功；有计划抛外键错误；revision 2→1→2，旧请求被接受 |
| #350 固定 head：`test_extraction_windows.py`、`test_extraction_window_worker.py` | exit 0；24 passed，含真实 SQLite 回滚保护 |
| #351 固定 head：`edit-history.test.ts`、`h14.test.ts` | exit 0；101 passed |
| #351 固定 head：5 条新增反例，协调者独立复跑 | exit 1；5 failed，逐一对应上述缺陷 |
| #348/main 快照：`scripts/verify/frontend.sh full` | exit 1；类型检查通过，Vitest/构建因共享 node_modules 缓存写入 EPERM 未完成，未计通过 |
| `git diff --check` | 通过 |

初查 #348/#350 的 GitHub CI 全通过；#348 因 `docs/tasks.md` 冲突不可直接合并。试合并只需保留双方任务段落；前端 `useReview.ts` 自动合并后相对 main 仅增加两条原因标签。试合并已撤销，未把存在缺陷的版本留在主线。

#351 唯一初始 CI 失败为既有 `test_cipher_round_trip_and_binding_to_user`：将密文末字节替换为零，遇原字节已为零就没有真正篡改。使用合成测试密钥复现；改成翻转一位后鉴别正常拒绝。该项不是 #351 新增缺陷，原失败记录保留；本轮仅重跑原失败 Backend job，没有修改测试或加密实现。重跑最终状态见交接。

本轮未新跑真实 Neo4j、真实模型、真实浏览器、窄屏/读屏或跨浏览器验收；fake 测试不代表这些已通过。自动消歧和自动合并的默认开关未改；不因默认关闭而忽略启用路径的缺陷。

本地证据位于 `.demo/pr-review-20261114/`，包括逐文件 JSON 清单、日志、`smartsketch-pr348-reproduce.py`、`pr351-regressions.test.ts`。临时固定快照为 `/tmp/smartsketch-pr348-snapshot`、`/tmp/smartsketch-pr350-fixed`、`/tmp/smartsketch-pr351-review-snapshot`。复现不得使用真实课程或真实凭据。

下一步：先修复 #348 两项与 #351 五项并保留失败回归；复审新 head、通过 CI 后合并 #348，再将 #350 更新基线至 main 并复验。#351 可独立修复后合并。无 API/数据模型决定或规格行为被本次审查更改。
