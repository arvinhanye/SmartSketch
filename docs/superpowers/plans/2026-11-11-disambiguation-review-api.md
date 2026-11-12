# 消歧审核与撤销 API 实施计划

> Use superpowers:executing-plans. 连续执行，保留当前后端分支和已有未提交工作，不自动提交/推送。

**Spec:** `specs/generation-disambiguation.md` 第 7 节。
**Goal:** 消费生成阶段结论，减少词面伪重复；公开覆盖、自动合并历史和安全撤销接口，兼容 Claude 新审核页。
**Architecture:** 领域服务判断计划时效/聚合原始成员并形成审核视图；路由只做 DTO/错误转换；共享 OpenAPI 生成类型；复用 BE-02 撤销事务。

## Global Constraints
- 保留 Claude 工作树及布局、并排对比、预览、来源加载修复；本地前端只加接口封装和原因标签。
- 不触发真实模型、迁移开发数据、改默认自动开关或发布；技术缺口与语义不确定分开。
- 读取不推理；过期不隐藏；课程隔离、权限、锁、冲突与幂等都须测。

## Review Focus
- prepared/skipped、任务失效、后续教师修改和撤销后，旧结论不能隐藏当前候选。
- 原始成员交叉对缺项、DIFFERENT、UNCERTAIN、失败混合时，不误算完整也不把失败改成语义未决。
- 过滤后的 totals、游标、resolveReviewItem 使用同一队列定义；历史接口不能跨课泄漏快照。
- 撤销端点不得绕过教师鉴权或严格修订号校验；409/503 不会提前宣告成功，重复执行幂等。

## Task 1: 语义审核与覆盖视图
**Files:** `services/fusion/review.py`、`services/graph/review.py`、`repositories/fusion.py`、后端测试。
**Interfaces:** 当前头 + 最新已提交计划 → 有效语义对/覆盖摘要；`read_queue` 和动作 totals 共用。
- [x] RED：有效/过期/未提交/失效任务；三态/技术失败/整组合并；摘要单位与未知计数；分页与动作一致。
- [x] GREEN：无模型读取、保守时效、聚合语义候选、兼容 legacy。
- [x] 验证：新纯函数回归 + F11 分类/分页，预期全通过。

## Task 2: HTTP 契约与撤销服务适配
**Files:** `src/contracts/api.v1.yaml` 及生成物、`api/fusion_review.py`、schema 导出、历史仓储/服务、HTTP 测试。
**Interfaces:** 覆盖 GET、分页历史 GET、undo-preview/undo POST；所有参数和错误见规格。
- [x] RED：契约 DTO、教师/跨课、严格输入、ready/conflict/already_undone、锁/存储故障。
- [x] GREEN：复用现有事务、分页列表、错误映射；不暴露物理地址。
- [x] 验证：新 HTTP 与契约回归，预期全通过。

## Task 3: 集成与前端接口交接
**Files:** 新集成测试、前端新接口文件/原因标签、对应接口测试、Codex 交接和任务/规格/ADR。
**Interfaces:** 真实生成 T6 → 过滤/覆盖/历史 → 撤销 HTTP → 读取恢复；Claude getQueue/resolve 保持兼容。
- [x] RED→GREEN：真实 Neo4j 生成-审核-撤销闭环及后续修改冲突；前端客户端参数/取消信号。
- [x] 独立最终审查一次；重要发现失败回归后修复；基础、后端全量、相关隔离集成、前端类型/接口检查。
- [x] 完整接口交接、实际验证与限制，检查最终差异；保留未提交成果。

实际验收与首轮分层失败/修复记录见 `docs/handoffs/codex-to-claude-disambiguation-api-20261111.md`。后端全量最终 4488 passed / 27 skipped，exit 0；本批未验收真实模型质量和新控件的浏览器交互。
