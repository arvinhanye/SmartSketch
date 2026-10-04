# Plan C 真实结果复核与 Minor 收尾计划

> **For agentic workers:** 使用 superpowers:executing-plans 顺序实施，用户已明确要求本轮按序执行；不派实现 Agent。

**Goal:** 只读核验88f9f6f的真实结果，修复两项明确Minor，保持stage_c_status OPEN直到用户签收。
**Architecture:** 复用codex/plan-c-takeover@95e0797；测量工区仅只读，不合并。失败路径只补计量列；SourceViewer以显示来源字段变化重置折叠，保持同来源状态。
**Tech Stack:** Python/FastAPI/SQLite、Vue3/TypeScript/Vitest。
**Spec:** 用户本轮六部分任务；docs/integrations.md调用记录/ADR-089；specs/grounded-qa.md；本计划不改变API或数据模型。

## Global Constraints
- 真实模型/在线向量请求0；源工区、业务库、共享Neo4j与发布版本0写入；预算以最新总交接为准844451/900000，向量12005另计。
- 准确率只由用户签收；浏览器首字、Markdown及v3+思考开对照待用户决定；不推送不合并。
- 无日志支撑则标未归因；既有原始报告数字误差仅在Codex校正记录，不覆盖DeepSeek产物。

## Review Focus
- 供应商推理token缺失或0保持None/0区别，不增计总费用。
- 失败/流中断路径只计数、不泄推理正文，不改变retry/截止。
- Vue新对象但同内容不重置展开；不同片段/文档/位置重新折叠；不改变纯文本渲染。
- 各种计时与统计分母分开，冷启动仍纳入；模型跨度不累加。
- 同期资料/版本/提问/历史/缓存状态对照，预算和签收不得默认为批准。

### Task 1: 证据与归因（不重跑）
- [x] mode=ro/query_only白名单SQLite，与PDF/QA JSON、工作表数量/哈希逐项核对；保存仅脱敏数值与证据哈希的Codex审计产物。
- [x] 核阶段日志存留、run_persist_stage/_write_draft与锁/事务代码；记录可定位范围及证据不足；校正统计/轮数文案。
### Task 2: C-MINOR-01
- [x] tests/backend/test_c02_reasoning.py新增失败流usage_reasoning=90/0/None（流式/非流式），实际写库/计费110/未知为空；先RED。
- [x] policy.py _finish_error仅补usage_reasoning；相同回归GREEN。
### Task 3: C-MINOR-02
- [x] tests/frontend/l12.test.ts增加展开A→B600字折叠、B位置/文本正确、同值新对象保持展开；现有ChatView用例加入切换来源；先RED。
- [x] SourceViewer.vue watch显示字段变化重置expanded；原用例与新增GREEN。
### Task 4: 对照测量缺口
- [x] 同13题、v3、2048、15秒、同课程/模型的思考开启对照方案，附已有input_tokens_est+输出上限保守估算、未知/在途余量、人工决策；不执行。
### Task 5: 最终验证/交接
- [x] 一次新上下文只读最终审查；定向、./scripts/verify.sh integration（一次性本地假供应商）与git diff --check；逐项写实际PASS/SKIP/FAIL。
- [x] 原子提交修复；更新tasks/自己的三份交接审查、新增实测复核报告。用户准确率未签收时stage_c_status OPEN。

### 最终门禁发现的范围修订（仅测试）
- 首轮完整门禁exit1：个人E2E同教师账户第六次连接测试触发5次/60秒限流；API429、trace Retry-After3，原成功断言未满足，保留失败产物。
- 新回归17例先RED13failed/4passed（仅接口stub），补本机HTTP127.0.0.1测试夹具有界RATE_LIMITED等待/一次再试；认证/预算/其他错误不重试，非本机发请求前阻断；原配置成功/错误/保存/刷新断言保留并新增HTTP200断言。
- [x] 新夹具17例与原来源16例GREEN；第二次完整integration最终结果后记录，不放宽限流、不增skip，不修改生产业务代码。

最终整次integration exit0，计数与前两轮失败见审查/交接及verification.json；阶段仍OPEN。
