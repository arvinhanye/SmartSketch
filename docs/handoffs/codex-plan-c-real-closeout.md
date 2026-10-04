# Codex：计划 C 真实测量接手与本地收尾交接

```text
date: 2026-10-04
worktree: /Users/arvinhan/.codex/worktrees/plan-c-takeover/SmartSketch
branch: codex/plan-c-takeover
base: 95e0797
measurement_reference: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-c03b-measure
measurement_branch: deepseek/plan-c-thinking-disabled
measurement_commit: 88f9f6f (只读、不合并)
minor_01_commit: 72f7430
minor_02_commit: a6b19b7
test_fixture_commit: 3742a4e
test_fixture_typing_commit: 043c274
paid_generation_calls_this_turn: 0
paid_embedding_calls_this_turn: 0
generation_system_total: 844451
approved_cumulative_cap: 900000
remaining_generation_tokens: 55549
embedding_separate_total: 12005
stage_c_status: OPEN
technical_freeze: WAITING_USER_SIGNOFF / NOT_PERFORMED
```

## 先读与下一步选择

本轮复核报告：`docs/reviews/codex-plan-c-88f9f6f-closeout.md`；数值/22份证据哈希：`evaluation/raw/codex-plan-c-closeout/audit.json`；可复现只读脚本同目录`audit.py`。原始总交接仍在测量工区 `docs/handoffs/deepseek-plan-c-to-codex.md`，不能把它的未保留阶段日志、错中位数或轮次标签当新增确定性证据。

**本轮已交付**：SQLite/JSON核对、阶段耗时定位范围与未归因说明、两项Minor最小修复及RED→GREEN、v3开启基线缺口/预算提案。完整门禁结果见下面最终栏；只有该栏填入本轮结果才算本轮工程门禁完成。

**不再自动重测**：course2 PDF20.90秒/32842token、course1 PDF28.08秒/40292token；两轮repair0；问答13题11answered/2not_covered/0error、完整max3.34秒、服务端首delta max2918ms、SSE max2927ms。本轮工程回归不是这些真实指标的替代物。

**校正记录**：全13题完整响应p50=1.62秒/服务端1613ms；answered11题完整max=3.34秒、p50=1.66秒；首delta p50服务端1342/SSE1346ms。浏览器可见首字未测。原`source="ai"`仅origin；本轮68/76点检查点来源已反查同课chunk定位，Neo4j实际详情source_refs未独立复核。

## 已解决 Minor 与回滚

- C-MINOR-01（`72f7430`）：失败usage的reasoning_tokens回写`usage_reasoning`，保留null/0；总计费仍输入+输出、不重复计推理；没有新的正文保存、retry或预算逻辑。
- C-MINOR-02（`a6b19b7`）：来源显示字段改变时重新600字折叠，同值新对象保留展开；实际ChatView切换正确，纯文本渲染不变。
- API/DTO/迁移/架构无变化。回滚选择仅`git revert`对应提交；无需还原018或业务库。未执行回滚；撤销后会恢复原Minor表现。

## 耗时仍 OPEN

- 报告course1 persisting6471ms/course2 1037ms；SQLite独立确认末模型→review分别6.487/1.054秒，支持尾段幅度，不定位子因。当前worker.log只有82字节一行、0条阶段日志，SQLite也无阶段历史表。代码阶段包含候选读、课程锁、Neo4j完整事务、SQLite T6及释放。没有证据拆给某个子步骤，不为猜测改锁/索引/重试。
- 旧C03-1非模型18.742秒、末模型→awaiting_review15.643秒已由旧JSON+SQLite核对；15.6秒不是L11-6，根因仍未确定。本轮没同幅复现不等于根因消失；course1仍有6.471秒未归因。
- 原测量文件/日志保持原样，未补造日志。未来先安排子步骤脱敏埋点与原样归档再决定是否需真实复现；本轮不扩展该代码。

## 人工签收与可判定性缺口

以下均不是 Codex/Claude 自动签收项：
1. 两份C04工作表，由用户**全量**人工判定：
   - 测量工区`evaluation/raw/c04/course1-pdf-h2-thinking-off-worksheet.md`：76实体+61关系。
   - 同目录`course2-pdf-h2-thinking-off-worksheet.md`：68实体+58关系。
   - 实体/关系各≥70%；保留predictions对应原始未编辑草稿，辅助必须标`claude-assist`。
2. 是否补v3+思考开启同13题基线；是否要相邻on/off26题对照。
3. 是否补关闭思考下的Markdown抽取；现有MD发布版本QA不代替它。
4. 是否采浏览器渲染可见首字；SSE值不代称。
5. 是否额外只读核验持久化后图谱详情来源，以及未归因耗时缺口如何处置。
6. 上述签收/缺口处理后是否冻结第三阶段。**当前stage_c_status仍OPEN，不自动冻结/推送/合并。**

## 付费前必须重新确认

最新已发生台账：746357→844451，批准累计900000，剩55549；向量11946→12005另计；新增unknown0。推理null表示未返回，不是0。两次PDF+一整轮QA三题组与总交接“四轮”未附分组定义，未据此凭空增加第四次付费测量或开销。

最小v3思考开启13题方案与完整预算算式见报告§5：已知输入+输出封顶46407；11条调用全未知时估算118052；保守13条最大调用估算+一条余量182056。建议供用户选择：单轮新增185000/累计1030000；相邻26题新增352000/累计1200000。**这不是预算授权，也没有执行。** 当前55549不足以覆盖保守方案，不发请求。

重新授权必须明确增量停止线、累计上限、向量额度/计量口径与当前台账。串行、题前题后计费检查/下一题余量；预算拒绝/认证失败即停，不自动重试、不调额；unknown按估算记入；后端软上限非硬预留。保持同课程/版本/模型/v3/2048/15秒/对话历史，缓存状态与冷启动记录保留。只改学生开关，结束恢复true，不改教师开关，不复制真实凭据/业务库进隔离门禁目录。

## 本轮验证与最终复核

- 只读审计上述命令exit0，82新增调用/13请求、预算/迁移/结构/来源候选/20引用/最近秩统计一致。
- 后端失败路径8参数回归先RED4 failed/4 passed；完整`test_c02_reasoning.py` GREEN18 passed。
- 前端来源切换先RED5 failed/11 passed；完整`l12.test.ts` GREEN16 passed。
- 首轮完整门禁：**exit1**，个人E2E3 passed/1 failed；其余层通过，计数见审查报告。日志`/private/tmp/plan-c-real-closeout-integration.log`保留。已按trace/API定位为同测试用户5次/分钟限流、Retry-After3；仅本机测试调度修复`3742a4e`，17新增回归RED13failed/4passed→GREEN，与来源回归合计33passed。不放宽生产限流/断言；认证/预算不重试，最多按应用Retry-After延迟再试一次。第二次完整门禁**exit1**（运行用例全部通过，测试替身TS2345）；仅显式字典类型修正`043c274`后，完整frontend类型/934tests/build exit0。前两轮失败均保留；第三次整次门禁在043c274稳定树**exit0**，日志`/private/tmp/plan-c-real-closeout-integration-confirmed.log`，计数见下表。两个测试提交回滚先043c274再3742a4e，不改业务库。隔离门禁端口18700/15873/18388/19590/18389，测试临时库、一次性Neo4j与本机假供应商；原测量API/库未操作。
- 一次新上下文只读审查已完成：Critical0、Important0；1项计划最终检查框提前勾选的文档Minor已先恢复待完成，最终exit0回填后才标完成。审查独立核验22份哈希/SQLite预算/统计，未运行服务或测试。最终仅报告本轮实际PASS/登记SKIP/FAIL，不沿用旧计数。

九类参赛材料、视觉重设计仍在范围外。保留工作副本供后续接手；不要同步、合并或推送测量分支。旧credential权限/轮换提示仍交原持有人，不读取密钥内容。

### 完整门禁复现命令（仅本工作副本、本机假供应商）

```bash
cd /Users/arvinhan/.codex/worktrees/plan-c-takeover/SmartSketch
env -u VERIFY_NEO4J_URI -u VERIFY_NEO4J_USER -u VERIFY_NEO4J_PASSWORD \
  -u LLM_MODE -u EMBEDDING_MODE -u E2E_NEO4J_URI -u E2E_LLM_MODE -u E2E_EMBEDDING_MODE \
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src/backend" PYTHON=.venv/bin/python \
  PATH="$PWD/.venv/bin:$PWD/node_modules/.bin:$PATH" \
  E2E_API_PORT=18700 E2E_WEB_PORT=15873 E2E_NEO4J_PORT=18388 \
  E2E_PROVIDER_PORT=19590 VERIFY_NEO4J_PORT=18389 \
  PLAYWRIGHT_CHROMIUM_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  ./scripts/verify.sh integration
```

本工作副本无`.env`与`src/backend/storage/smartsketch.sqlite3`；仅临时测试库。本轮核验shell里MODEL_CREDENTIAL_KEY/DEEPSEEK_API_KEY/LLM_API_KEY/EMBEDDING_API_KEY/AUTH_JWT_SECRET均未设置（只查是否存在，不查值）；个人E2E由脚本生成随机测试密钥，model URL固定127.0.0.1本机假供应商。运行前检查自己的端口；不在测量工区执行这段命令。

### 最终稳定树完整门禁（043c274）

`./scripts/verify.sh integration` **实际exit0**；最终日志`/private/tmp/plan-c-real-closeout-integration-confirmed.log`。basic契约、type-check、build均通过。

| 层 | PASS | 登记SKIP | FAIL |
| --- | ---: | ---: | ---: |
| backend+tooling | 3870 | 27 | 0 |
| frontend（38文件） | 934 | 0 | 0 |
| integration | 393 | 4 | 0 |
| backend-live | 44 | 0 | 0 |
| 演示E2E | 2 | 0 | 0 |
| 个人本机假供应商E2E | 4 | 0 | 0 |

31项均为既有登记SKIP，不算PASS，无新增SKIP/删用例/断言放宽。前两次exit1与最终exit0的日志路径、SHA-256/大小、回归与备份检查摘要在`evaluation/raw/codex-plan-c-closeout/verification.json`。弃用/jsdom/构建大chunk等既有警告保留，未依赖升级。

本地工程收尾完成，不等于准确率签收或技术冻结：**stage_c_status仍OPEN**，真实生成与在线向量增量均0。后续保留工作副本，按用户签收/测量缺口决策再推进冻结，当前不推送、不合并。
