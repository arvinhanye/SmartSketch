# 计划 C 下一轮真实测量交接（方案 B）

> **2026-10-04 最新状态覆盖（88f9f6f接手）**：原“下一轮测量”已经完成，不按本文旧步骤重跑。详见 `docs/handoffs/codex-plan-c-real-closeout.md` 与 `docs/reviews/codex-plan-c-88f9f6f-closeout.md`；最新生成844451/批准900000、余55549，向量12005另计。本轮两项Minor已修（72f7430、a6b19b7）。stage_c_status仍OPEN（准确率未签收），浏览器首字/v3开启完整基线/MD补测与冻结交用户。以下保留的是上一轮历史记录；旧预算与OPEN Minor状态不再代表当前，不能据其再发付费请求。

日期：2026-10-04。原计划状态：已执行并接手（88f9f6f）；下文旧预算/等待状态仅保留历史。本文件是执行准备，不是付费调用或数据同步授权。用户2026-10-04明确选择：本地收尾后再确认真实测量预算。

## 1. 采用的基线与旧文件

采用 `codex/plan-c-takeover` 的最终代码提交（见同目录 `codex-plan-c-takeover.md`），包含 Claude `082323a` 与 ADR-090 未提交实现的核对副本、迁移断言修正及补充回归。先核对提交；不要只取 Claude 旧 HEAD，那不含方案 B。

参考 `claude-plan-c-handoff-to-codex.md`、`claude-plan-c-c02-4-deepseek-qa-retest.md`、`claude-plan-c-c03-1-deepseek-pdf-retest.md`。旧文件的预算起点、迁移017最后、未知usage立即停、输出目录规则，由本交接覆盖；题目/资料与评价边界保留。原始证据不覆盖。

## 2. 预算与停止规则（执行前用户确认）

- 最新已知生成 **746357 / 5000000**（系统计费口径），含 C02-4 未知调用估算12116、直连probe手工2551。只统计SQLite已知usage会漏账。
- 最新向量11946，另计。旧批准累计上限803168，余56811，不能自动提高。
- 填写用户确认值：`GENERATION_BASELINE`、`APPROVED_TOTAL_CAP`、`ROUND_GENERATION_CAP`、测量 checkout/数据路径、是否允许模型配置保存/迁移/重启。实际起点有新调用时先更新台账再确认。
- 建议分轮：先course2 PDF一次（参考上轮83522、建议增量停止线110000），复核后决定course1 PDF预算；问答原十题+比较题三次参考停止线45000。这些是估算建议，不是批准；旧余额不够照旧线运行一份PDF。
- 失败/中断/预热/测试连接都是有成本的请求；按系统计费口径算未知usage，向量独立，禁止记0。直连探测额外手工入账。
- 任务预算和客户端停止线都可能被在途调用突破：PDF有并发，ask在题后检查。留出并发/下一问输入估算与输出上限的保守余量，确保批准的累计额度容纳最坏在途请求；额度不足不发下一次。收到预算拒绝、认证/配置失败即停，不自动重试、不调高额度。
- `reasoning_tokens=null` 是供应商未返回，不是0；本次probe只观测到reasoning_chars=0，不证明计费推理token为0。

## 3. 环境与开关

由用户指定测量工作区和真实资料/发布数据的保留方式。不在 Codex 的隔离门禁目录复制凭据或业务库，不清空共享 Neo4j，不占已有端口，不自行同步/快进 Claude 分支。

1. 停止本次指定API/worker后备份，按现有迁移机制升级到018；核对 schema_migrations 中017与018都存在、迁移校验无漂移。数据回滚见018文件注释/迁移前备份。
2. 教师/学生分别通过个人配置接口保存 `disable_thinking=true`（地址/模型不变，API key省略即可沿用；仅限已存在同地址配置）。GET验证开关 true，不打印密钥。**保存开关本身不发模型请求；测试连接另收费**。
3. 教师开关在创建新任务前设置，旧任务快照不追溯。学生新问答通过配置revision刷新客户端。确认问答仍2048、提示词v3、15秒截止，PDF解析 `pdf/2,cleanup/1,headings/2`。
4. 重启指定API/worker以加载最终代码；保持已批准模型、向量空间/维度与发布版本，不切换模型、不加重试、不放宽出处。

## 4. PDF轮

- 先course2：`datasets/contest/course2-os-ch2/ch2-process-thread.pdf`，一次。
- 用户批准追加后course1：`datasets/contest/course1-ds-ch3/ch3-stack-queue.pdf`，一次。
- 使用现有 `measure_web_flow.py extract`，启动worker时任务级预算用批准值；`audit-task --db ... --task-id ... --client-elapsed-seconds ...` 读取本轮记录。库只读audit，不查凭据表。
- 新目录 `evaluation/raw/c03b/` 保存提取响应、任务audit、**编辑/发布前原始草稿**和脱敏阶段日志；不得覆盖 `evaluation/raw/c03/` 与 headings/2 旧草稿。
- 记录排队、解析、分块、实体、关系、repair、融合入库、总墙钟；并发跨度不能相加冒充总时长。保留AI耗时，特别解释旧末段15.6秒是否重现。
- 统计知识点/关系、四种关系覆盖、孤立、repair、截断、来源完整性、DAG、generation/embedding。≤60秒以真实赛题口径验收，不缩成不代表课程的片段。
- 全部新草稿单独生成C04 predictions/工作表；真实性能与人工准确率分开。

## 5. 问答轮

沿用旧交接的两门已发布课程，先验证 course_id/version；原十题 + 「栈和队列有什么区别」重复三次。默认只测开关开启状态；开启/关闭的额外对照请求另经预算确认，不把不同时间的旧轮当严格A/B。

- 从新启动后第一问开始保存冷启动证据；不预热掩盖首问超时。若用户批准预热，则仍计费/保存，冷/热样本分层，不能从失败分母中静默删除。
- 同一轮共享 `ROUND_STARTED_AT`。用 `ask --stream --out ... --audit-db ... --cap <批准增量> --round-started-at ...`；三组course1/course2/repeat沿用旧题目，每组执行后核预算，再开下一组。新目录 `evaluation/raw/c02b-qa/`。
- 补齐 `audit --records` 固定请求集合与 `[since,until)` audit；核对错误的 `details.request_id`、chat_logs/model_calls关联。unknownusage按最新工具的billed_tokens估计，不触发旧的「一律立即停止」规则；停止取决于计费额度与异常种类。
- 每题：answered/not_covered/error、error_reason、截断撤回、可见回答/引用、首次推理/首次可见内容、服务端首delta、客户端SSE首delta、完整响应、生成/向量用量。浏览器可见首字未采集就写未测，客户端SSE不冒充浏览器渲染。
- 成功/未覆盖/失败分列，p50/p95/max采用最近秩且注明分母；首delta≤3秒、全链路≤15秒与回答质量分别判定。解释旧向量后8.15秒空档是否重现，不能先认定冷启动或锁是根因。

## 6. 交付与限制

新报告 `evaluation/reports/c03b-pdf-thinking-disabled.md`、`evaluation/reports/c02b-qa-thinking-disabled.md`；新交接 `docs/handoffs/deepseek-plan-c-thinking-disabled.md`。各轮写base/head、次数、真实停止原因、预算起止/手工补账/未知估计/向量、证据路径、模型与开关状态。无新增业务代码，无推送/合并。

C04须用户对新原始快照的实体/关系各≥70%签收；<=100全量检查，超出用既定种子抽样。辅助判断标claude-assist，不冒充人工。通过本地门禁或单次probe，不等于真实性能与质量验收；未达标项继续OPEN。九类参赛材料、前端视觉重设计仍在本轮之外。
