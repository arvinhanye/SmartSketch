# Codex 交接：计划 C 验收复审四项修复

- 日期：2026-10-04；task_id：C-ACC-FIX-54。
- 状态：DONE（本轮四项修复与独立门禁）；用户手工检查待执行，整阶段仍 OPEN。
- 基线：54a7c67；分支：codex/plan-c-acceptance-fixes。
- 工作区：/Users/arvinhan/.codex/worktrees/plan-c-acceptance-review/SmartSketch。
- stage_c_status：OPEN；technical_freeze：NOT_PERFORMED。

## 当前依据与交付

本文件是本轮当前交接。Claude 原交接 claude-plan-c-acceptance-closeout.md 保留不改，其中 §3C 的空 judge 模板和 §6 的待用户签收仅反映初始时间点，不作为当前状态；§2/§10 的签收登记已由只读重算确认。此前 Codex 复审报告为历史 REQUEST_CHANGES，本修复报告说明后续处置。

- 代码：c04_signoff.py 拒绝重复行号/ID、非七列/畸形行；convert 全所选课程预检通过后才写结果。persist_graph.py 异常退出/解锁抛错也完成计时，业务控制语义不变。
- 测试：签收新增24例、计时新增4例；保留所有旧断言与skip规则。
- 文档：tasks 当前状态、C04 README、decisions；未代写 Claude 交接。
- 修复报告：docs/reviews/codex-plan-c-acceptance-fixes.md。
- 本机启动/检查清单：docs/handoffs/codex-plan-c-manual-start.md（用本修复目录、独立端口/新库、scripts/start.sh 正式个人 API 模式）。
- 可复现只读核验：evaluation/raw/codex-c-acc-fixes/checks.py、checks.json；旧复审资产保留不覆盖。

## 已运行验证

- RED：签收23 failed/16 passed；计时4 failed/6 passed。两类失败均复现对应原缺陷。
- GREEN：签收与准确率46 passed；最终四文件61 passed，exit0。
- checks.py：exit0，27种原基线业务路径等价；异常表格拒绝、失败批次零写入；四源哈希/263条签收及报告一致；30+5辅助依据关系确认；源分支/测量库状态不变。
- bash -n 启动/停止脚本、git diff --check：exit0。实际真实个人模式启动未执行，不把脚本语法通过当成真实供应商验证。
- 完整隔离 `./scripts/verify.sh integration` exit0：backend+tooling3921 passed/27登记skip、frontend934（38文件，type-check/build通过）、integration393/4登记skip、backend-live44、演示E2E2、个人假供应商E2E4。日志 /private/tmp/codex-c-acc-fixes-integration.log；本轮独立执行，不借用 Claude/上轮 PASS，31登记skip不算PASS。

具体命令、日志与限制见修复报告。没有 API/DTO/契约/迁移/依赖变化，没有业务/签收数据修改；未复制真实配置/业务库/课程正文。真实生成/向量新增0，生成844451/批准900000（余55549），向量12005另计；不推送合并。

## 下一步与人工决策

用户要求先修复、自行检查后决定冻结。用户按本轮启动指南建立独立本机检查环境；生成/连接测试/发布向量化/问答可能收费，先决定新增预算再做真实操作，不重复旧两门全量测量。

人工准确率已签收：arvin 逐条复核后采纳辅助判定，不是独立盲判。course1 实体64/76、关系58/61；course2 实体61/68、关系45/58。三项不补测继续未测，不外推 PDF/SSE 指标；历史慢段根因仍OPEN、草稿来源不外推发布副本。技术冻结必须由用户明确决定，本轮未执行。

下一位 Agent 的首个动作：阅读本文件和启动指南，核对用户手工检查反馈，不自动发模型/向量请求。新问题单独复现再修，不把失败用例删掉或放宽；冻结登记另轮按用户决定执行。

## 回滚

本轮代码修复没有迁移或数据变化。要回到修复前行为，可在自己的独立工作区检出54a7c67（先保留本轮提交和手工检查数据）；不回退 Claude/测量分支，不清空共享图库，不删除现有签收证据。停止手工检查用 Ctrl+C / 指南里的本项目 dev-down.sh，保留新库数据。
