# PR-FIX-MERGE-04 修复与合并交接

- 状态：DONE。用户已授权修复七项问题、通过测试与独立复审后依序合并 #348 → #350 → #351。
- 初始主线：`50e6cba`。初始 heads：#348 `04286ec`、#350 `27339d9`、#351 `a1f0864`。
- 输入：[原始审核](../reviews/codex-pr-review-20261114.md)；[修复计划](../superpowers/plans/2026-11-14-pr-review-fixes.md)。原始失败记录保留，不能把原报告的未通过状态追改成历史通过。

## 所有权与实现

后端修复在当前隔离工作树实施；前端在 `/tmp/smartsketch-pr351-review-snapshot` 固定 head 快照内实施，随后仅应用其指定补丁。原始工作树、未提交 BE-05 和 Claude 的工作树不在范围内。

#348 的任务看板与 main 冲突通过保留双方记录解决；`useReview.ts` 相对 main 仅有两条原因标签。后端修复保留精确冲突比较，只为真正改变/恢复的节点分配新修订号；不相关节点保留当前状态，因此无需加入忽略修订或修改历史审计的机制。资料删除先经过现有状态/贡献/清理检查，再保护已提交、已生效和带撤销审计计划，只清理本课程、本资料失败/取消任务的未生效计划。

前端修复与验证由专项交接记录。没有公共 API、依赖或迁移变更，没有真实模型调用或开发库修改。Docker 验证仅使用测试脚本创建的一次性 Neo4j。

## 已有验证证据

- 后端新增回归：旧实现 10 failed / 19 passed，失败位置对应原缺陷；修复后相关模块 106 passed。
- #348/main 兼容前端 full：90 文件、1532 passed，类型检查与构建通过，exit 0。
- 测试索引检查通过；无新增文件时仅更新描述。
- 基础门禁 exit 0；后端独立复审通过，无 P1/P2。独立实验覆盖 90 次反复合并/撤销、所有旧修订令牌拒绝、共享边双组撤销和 20 组真实 SQLite 删除矩阵。后端 full 4504 passed / 27 登记 skip，门禁输出 PASS；外层 zsh 包装器在记录退出码时误用只读变量导致 wrapper exit 1，未改记整个包装器成功。隔离 Neo4j 504 passed / 4 登记 skip + 44 live passed，exit 0；新 head 的 20 项 CI 全绿。完整日志在 `.demo/pr-fixes-20261114/`。

## 合并记录

#348 已以 expected head `bfa83179e02efbccfffa198aca3863afb591db9b` 合并，main 合并提交 `d63116fb9cb23c5d25d334f9e8d2c3d62d9a9f52`。

#350 已 retarget main，并合入上述主线；冲突只涉及任务记录、测试索引和 `setup_task` 的两个新增关键字参数（同时保留 `window_policy`、`names`）。生产代码、后端/集成测试、契约与预先验证的组合快照逐文件相同；54 条定向、basic、32 条真实 Neo4j 已通过。新 head `6641160` 的 20 项 CI 全部通过，已合并为 `2789f61c045400592c03d748f8e288abfc0c857a`。

#351 五项及复审新增回调边界均已修复，独立复审无剩余 P1/P2，固定原 head 快照全量 1575 passed。整合后 10 个已复审源码/测试/规格 SHA256 完全一致，387 个后端/测试/契约文件与已复审 #350 head 完全一致；唯一冲突为任务看板并保留双方记录。组合版本前端 91 文件 / 1578 passed，门禁 PASS、类型检查无错误、构建成功；中断导致该次终端退出码不可恢复，使用完整日志记录各阶段实际结果，最终新 head CI 另行确认。基础门禁已补跑完成，exit 0（`pr351-integrated-basic-final.exit`）；#351 head `ffe967752d9428f701c8b662a660be3e3b32ab51` 的 20 项 CI 全部 SUCCESS，已合并为 `383d584e198170e65f9aa8c723c126edc66f2dc5`。

所有 PR 都使用 expected-head SHA 校验合并，不绕过保护规则。

## 风险与回退

真实模型质量、窄屏、读屏和跨浏览器验收不由此轮回归证明。无本轮数据库 schema 变更；代码回退须遵守原迁移 021 的投影兼容约束，不能把新物理草稿直接交给不识别它的旧版本。任何部署或真实数据回退均不在此次自动合并范围。

## 最终复核与记录

- 原七项问题均已修复并有永久回归；前端复审新增的迟到新建/删除回调问题也先红后绿修复。后端与前端修复的独立复审均无剩余 P1/P2。
- 整合核验：以已批准的前端修复提交 `ce0ab40` 为基准，最终前端仅增加 #348 的 `api/disambiguation.ts`、`useReview.ts` 两条原因标签与对应接口测试，三者与已合并 main 完全一致；10 个复审哈希保持不变。后端/契约/相关测试与已合并 #350 完全一致。
- 额外尝试的独立整合复核因代理额度限制未启动成功，未将其记为通过；整合核验由协调者完成，保留此前已完成且文件哈希未变化的独立修复复审。记录见 `.demo/pr-fixes-20261114/pr351-final-integration-verification.json`。
- 最终合并状态：#348 → #350 → #351 全部 MERGED；主线 `383d584e198170e65f9aa8c723c126edc66f2dc5` 与测试 head `ffe967752d9428f701c8b662a660be3e3b32ab51` 的 Git tree 完全一致（`888f73082b2c74ffd2c18cdf3487d84b1de7a654`）。GitHub 开放 PR 为 0。

## 最终远端证据与归档

| PR | 经 CI 验证的 head | 主线合并提交 | 合并前检查 |
| --- | --- | --- | --- |
| [#348](https://github.com/arvinhanye/SmartSketch/pull/348) | `bfa83179` | `d63116f` | 20 项 SUCCESS |
| [#350](https://github.com/arvinhanye/SmartSketch/pull/350) | `66411600` | `2789f61` | 20 项 SUCCESS |
| [#351](https://github.com/arvinhanye/SmartSketch/pull/351) | `ffe96775` | `383d584` | 20 项 SUCCESS |

最终 #351 PR CI [run 43596927324](https://github.com/arvinhanye/SmartSketch/actions/runs/43596927324)：后端 **4529 passed / 27 登记 skip**；前端 **1578 passed**、类型检查与构建通过；Neo4j 集成 **507 passed / 4 登记 skip**，backend-live **44 passed**；浏览器 E2E **2 + 4 passed**；Windows 后端可移植检查 **13 passed**。所有门禁均成功；既有弃用/负路径警告没有记作新失败。另一个 push 触发的运行也成功。

合并后任务状态、计划勾选和原审核报告的闭环附录在本工作树本地归档，不再为记录最终合并 SHA 创建第四个 PR；产品修复、测试、规格与合并前验收记录已随三个 PR 进入主线。原始工作树与未提交批次未改动，未删除分支。
