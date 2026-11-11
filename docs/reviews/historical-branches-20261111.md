# 剩余15个历史分支审查与处置（2026-11-11）

基线 main `f9447860589d450aee34d4b2bf1532fdb21cb033`。有效改动已由 [PR #345](https://github.com/arvinhanye/SmartSketch/pull/345) 合入 main（代码 `e0022ab`，合并 `9dccc30`）；最终代码 10 项 CI 全部通过。下表 15 个历史分支已按原 SHA lease 原子删除，执行后逐项远端复核成功。完整结果见 [交接](../handoffs/codex-historical-branches-20261111.md) 及恢复目录操作日志。

不以落后提交数或patch-id独有作为删除/合并的唯一依据；核对merge-base差异、现行规格、主线实现和替代提交。全历史bundle已校验，路径为主检出 `.demo/historical-branch-cleanup-20261111/all-branches.bundle`（8,744,692 bytes）。

| 历史分支 | 原SHA | 决定 | 可核查依据 |
| --- | --- | --- | --- |
| `claude/check-pending-prs-tasks-1ba7fe` | `79ba1bfb9e64b6ac99da97c299c777e7bcb12787` | 已替代 | D03/D04 DONE 已在9月归档看板；integrations.md 文档解析依赖表已含完整四格式与PDF实际依赖，旧待合并PDF状态不能恢复。 |
| `claude/impl-j08` | `02357d78de7d9986fdb54ad50d662684868d7cea` | 已纳入并增强 | main 481d3ff 已引入 #300；现chatStream保留分片/EOF/终态合同，另有fc4876a同分片取消修复。 |
| `claude/impl-k09` | `8eb9b9f27fdb5ab07e1a70cd5b4629f9efdcee66` | 提取后删除 | 仅提取sqlite3审计写失败隔离；新版ADR-078导入和K04基准取代旧方案，不改变现行用户/课程作用域及相对目录语义。 |
| `claude/laughing-ptolemy-4x1c7g` | `4ca834058de73c9ebad1fadc73ec99dce5b5115c` | 归档后删除 | 仅有旧K08验证记录；原文归档到docs/archive/branch-evidence-20261111，明确不是当前验收；fake限制已由demo模式取代。 |
| `claude/worktree-contract-conflicts-740adb` | `978671eecd16176ad880e03e3efee4839c1e89d7` | 已替代 | 按已签收ADR-016/A10映射分批引入；契约生成b801553、Neo4j环境7f76237、当前门禁和实际模块取代旧桩。旧fail-open钩子、任务拆目录和旧状态机不可恢复。 |
| `codex/j02-graph-search` | `aec5045eaa0e48d75a2037e62e1d544b311d9b16` | 已替代 | 旧#273由#274与ADR-050取代；published-only/课程版本隔离、3跳200点上限和证据检索已有当前实现，不恢复旧32点128边语义。 |
| `codex/j08-chat-stream` | `3303cefcb9930246d1e4eb21d04b138faf7643e0` | 旧认领记录 | 唯一提交只新增J08 CLAIMED看板；J08已在main完成，不能把旧认领覆盖当前状态。 |
| `codex/k05-teacher-e2e` | `442daf7384efb17e0a54a9fcc0e8e5aa4068af50` | 已替代 | 固定英文fixture专用K05_FAKE_EXTRACTION已由ADR-076的通用demo客户端及现E2E入口替代。 |
| `codex/login-visual-refresh` | `89c885b37e30c80eb8432cafaca39ebd74b0ddf4` | 已替代 | 新版UI-PINE/LoginLayout保留关闭通知，旧AuthLayout/暖纸主题已被当前登录壳替代；未声称旧像素与新布局一致。 |
| `feat/api-settings-page` | `0fa61e8a11acc4928eb3853ab5b30a46499e7d1a` | 已替代 | 全局明文配置与浏览器localStorage密钥不采用；当前个人加密凭据、教师课程向量配置、模型发现与地址防护覆盖有效需求。 |
| `frontend-backend-refactor` | `16a110940cd4de70a4ab08900633954d13e83f90` | 提取后删除 | 提取完成后配置编辑使旧连接结果失效、RELATED_TO审核文案无向；其余页面/暖纸主题由新版UI与工作台替代。 |
| `frontend-ui-revision` | `27bff16a67fa4e9b96416d3529069832b05e88ac` | 已替代 | 共用无向关系显示修复统一提取；旧全局API设置、固定模型维度白名单及旧页面布局不覆盖当前安全实现。 |
| `jmy1.0-2026-10-01` | `a690e418a462e386fb64d7dccf81112bc4798736` | 已替代 | 四个Windows开发启动文件与10-02逐字重复，D盘硬编码/无配置Vite入口由当前Go安装启动器替代。 |
| `jmy1.0-2026-10-02` | `322ec231c3dbb288359d4f5b5065568b87a7f5c7` | 提取后删除 | 提取文本资料LF、系统临时心跳、控制台编码、JUnit collection skip正文；不移路径锚定/旧全量Windows门禁，新增精确Windows回归。 |
| `jmy1.0-2026-10-08` | `a459d673ee6e55a668c067a30545bf7f6fb98e6b` | 修复整合后删除 | 用户本轮明确签收安全级联；按ADR-097修复不可见根、预览失效扩大删除、前端迟到响应/重复确认，并补真实Neo4j与前端测试。 |

## 选定移植与验收

- 级联删除：新增ADR-097，保留默认单点与既有发布边界；预览token绑定课程/根/草稿修订/可见任务/计划，持锁事务先核对后写入；前端目标与请求代次隔离。用户确认记录在规格与ADR。
- 问答日志：只有SQLite审计写异常被隔离，JSON/SSE原结果不被二级日志故障替换；warning无问题/答案/异常正文。正常持久日志仍保持每请求一条，存储故障不虚报写入成功。
- 前端：完成后编辑模型配置清除旧连接结果，保留保存/清除失败与连接测试结果的隔离；RELATED_TO使用无向文案，其余三关系保持方向。
- Windows：仅datasets的Markdown/JSON钉LF，不把PDF当文本；心跳默认使用系统临时目录，显式环境覆盖与Docker路径不变；契约结果可在旧代码页输出；JUnit真实原因仍须allowlist匹配。精确Windows CI不冒充完整Windows后端或双击安装验收。

## 历史文档/契约分支补核

`claude/worktree-contract-conflicts-740adb` 的92个路径均在当前A10映射中有落点；其中23个来源blob能在main可达历史中找到，6个仍与main当前文件逐字节相同。当前`tests/contracts/test_contracts.py`仍有S07-R06在UTF-8 locale下缺生成物必须失败的回归；`scripts/gen-contracts.sh`保留`${OUT}/${name}`的退出码修复，B14与所有B08～B13测试加严了原门禁。
旧NOTICE中的“尚未借用任何代码”、过时源路径/参考项目和2026-09里程碑不能作为当前事实搬入；模板字段也与现PromptLibrary的6字段格式不兼容。资产/源码/测试目录说明已有当前架构、prompts/MANIFEST、evaluation/README和tests/INDEX承担。旧任务/ADR桩只保存在恢复bundle，不重启O01等未批准产品范围。

## 审查覆盖与限制

| 组 | OCR reviewable | 复核 | 未逐行复核 |
| --- | ---: | ---: | ---: |
| 前端4分支 | 84 | 84 | 0（excluded中的5个长任务/计划账簿只查范围，不逐行移植） |
| 问答/导入/E2E 4分支 | 13 | 13 | 0；另核对26个excluded文档/测试 |
| Windows/级联3分支 | 26 | 26 | 0；含excluded共44项核对 |
| 历史文档/契约4分支 | 30 | 25 | 5个旧OpenAPI真源及生成JSON不重复逐行代码审查：其blob已在main历史中，当前真源/生成门禁优先，未搬旧契约 |

审查覆盖是分支文件出现次数，不是唯一文件数；静态样式取舍不等于浏览器像素验收。完整preview、规则、文件清单、报告与红绿日志保存到上述恢复目录。历史文档原文不是本轮执行结果。

## 恢复与删除约束

删除前核对远端SHA仍与表中相同，dry-run后采用逐SHA force-with-lease和atomic删除；不强推main，不删除其他工作区文件/环境。未被main直接包含的原始分支仍可从完整bundle取回：`git fetch /绝对路径/all-branches.bundle refs/remotes/origin/<branch>:refs/heads/recovery/<name>`。新功能只把有效改动移植到当前实现，不把旧分支整树并入。

实际执行记录：`delete-15-dry-run.log`、`delete-15-execute.log`、`delete-15-result.json`；最终代码 CI 为 `final-code-ci.json`。bundle SHA-256 为 `36b95943976d5bf30522307823f13b7714e861d76b69214ccb11fb051bc91dec`（另存 `bundle-integrity.json`）。删引用后 main 保持 `9dccc30` 未变化；本次收尾文档只追加证据，不再改变产品行为。
