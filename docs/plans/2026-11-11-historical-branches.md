# 历史分支有效改动整合计划

**目标**：完成 MAIN-INTEGRATE-02 的 15 分支审查，移植仍有用的独有改动，按证据清理旧引用。
**基线**：main f944786；用户已授权整合与删除，并单独确认安全级联删除方案。
**规格**：specs/teacher-review-publish.md F09 扩展 / ADR-097；其余修复保持现行接口与行为边界。

- [x] 冻结15分支SHA、完整bundle校验；三组只读审查并统一记录。
- [x] 问答审计：services/qa/audit.py、test_j10.py；sqlite3写失败不覆盖JSON/SSE原结果，脱敏告警；先红后绿。
- [x] 前端旧修复：useModelConfig.ts/l10.test.ts完成后表单编辑清空旧测试结果；ReviewView.vue/h09.test.ts仅RELATED_TO无向；先红后绿。
- [x] Windows最小移植：仅文本数据钉LF（不处理PDF）、平台临时心跳、契约输出编码、JUnit collection skip正文；test_portability.py与精确Windows CI验证，不改变相对数据目录语义。
- [x] F09：按ADR-097移植旧删除预览/计划/弹窗，修复根可见性、预览并发与前端乱序；契约先改后生成，真实Neo4j与前端回归。
- [x] 保留有价值的历史K08验证材料，明确其是旧分支记录而非当前验收；完成15分支审计及恢复表。
- [x] 定向与完整门禁、自审及独立安全复核；最终代码10项CI通过、PR #345合main；SHA lease原子删除15历史分支并复核。完整本地命令浏览器启动因权限失败，原E2E两组经正常权限补跑2+4通过，原exit 1如实保留。

**约束**：不整体搬回旧视觉设计、全局API密钥localStorage、旧模板/任务桩或有损路径锚定；不读密钥、不升级依赖、不调用付费模型、不操作现有课程数据。共享规格/ADR/看板/测试索引由协调者写；各实施方独占自己的功能文件。

**回滚与验证边界**：删除引用从主检出.demo/historical-branch-cleanup-20261111/all-branches.bundle恢复；代码回退不恢复已明确删除的业务数据。模拟/真实Neo4j/浏览器/Windows CI分别记录，不能互相冒充。
