# 细化进度与取消后继续实施计划

**Goal:** 教师能看见实际正在处理的步骤、完成数和等待时长，并在取消完成后继续原任务。
**Architecture:** 从现有调用账本/检查点/缓存派生独立 activity 快照，不改 SSE v1 wire；显式 resume 事务重置本轮取消和重试基线，保留 task_id、累计用量和所有可复用结果。
**Tech Stack:** FastAPI、SQLite、Vue 3、TypeScript；无新依赖。
**Spec:** `specs/task-processing.md` §9，ADR-103。

## 约束与审查重点

- 复用当前工作树，保护前几轮未提交修复；不提交/推送/合并或调用真实模型。
- 旧租约不可写，取消不自动继续，双击恢复不能创建第二任务；累计调用/预算不能归零。
- 凭据已清理或轮换须重新核验；模型端点/名称/思考配置变化拒绝混用旧结果。
- 停留百分比时，实际在途请求计时更新；断线/已取消不伪装正在运行。
- 取消前发出的成功请求在有效租约下保存，但取消后不得发出新模型请求。

## 1. 恢复生命周期（resume_backend）

- [x] 在 `tests/backend/test_task_resume.py` 写红例：取消恢复同 ID、权限和配置变化拒绝、调用累计、并发恢复、旧租约。
- [x] 新增 `api/task_resume.py`、`services/task_resume.py`、`repositories/task_resume.py`；更新 `services/task_state.py` 与 `repositories/task_leases.py`；025 新增 `resume_attempt_base`/`resume_count`，包含可回退说明。
- [x] POST `/api/v1/tasks/{tid}/resume` 返回现有 Task；错误 `TASK_NOT_RESUMABLE` 的 reason 为 not_cancelled/worker_active/artifacts_missing/model_config_changed。
- [x] 跑定向生命周期、取消、凭据与迁移回归。

## 2. 可观察进度（progress_backend）

- [x] 在 activity 后端测试中先覆盖当前在途请求、5/6 小节、111 个完整裁决、过期租约/旧 attempt/跨课程隔离。
- [x] 新增 task_activity 路由、service/repository，GET `/api/v1/tasks/{tid}/activity` 返回契约 TaskActivity。
- [x] 完成数只统计当前 task_revisions 的检查点；消歧只报完整数量，不伪造总数；active 请求按当前 attempt、有效租约聚合。
- [x] 读模型测试通过，不新增 worker 高频写和数据库表。

## 3. 取消期间结果保存（主代理）

- [x] 红例：取消发生于模型请求期间，完整语义裁决和成功关系检查点仍保存；旧租约/已终态/撤销凭据拒写。
- [x] 调整 `workers/extraction/state.py`、`decision_cache.py`、`dispatch.py`，只保留已完成结果，不继续模型调用、不推进取消进度。
- [x] 取消后 resume 的集成回归确认已有裁决和小节零重复模型调用。

## 4. 前端（progress_frontend）

- [x] 红例：活动详情轮询、秒级等待、刷新已取消任务、恢复防双击、旧响应隔离、错误显示。
- [x] API client 消费生成类型；资料卡显示实际步骤/实体块数/关系小节数/消歧数量/等待时间，终态冻结，断线明确提示。
- [x] activity 每 3 秒轮询；resume 成功重新创建 SSE/详情订阅，旧回调失效。
- [x] 前端测试、类型检查与构建。

## 5. 契约、验收与部署（主代理）

- [x] 先更新 API 真源及规格，再运行生成器；不手改生成物。
- [x] 运行 basic、全量后端与前端门禁；一次独立复审；查看最终差异。
- [x] 确认无处理任务、备份迁移025；构建 main+白名单修复的 API/worker/web 镜像，更新本机。
- [x] 验证运行哈希、业务数据保留、服务健康与浏览器详情/继续入口；真实模型留给用户。
- [x] 更新任务看板与交接，说明复用范围、实际验证和回退命令。

## 收尾证据

本机部署、数据保留、浏览器入口与所有定向回归完成。basic与前端全量门禁通过；后端全量4687通过、27登记跳过、1条旧取消丢弃断言失败，修正测试后完整scheduler14项通过。原full的exit1保留记录，没有伪称full全绿，也没有因仅修改测试断言而重复整套扫描。详见交接记录。
