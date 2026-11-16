# TASK-CONTINUE-01：处理详情与取消后继续

2026-11-15，Codex。基线 main `d9d16ca` 加前两轮本机预算/关系超时/消歧缓存修复。用户明确授权实现、验证并更新本机，再由用户真实测试。状态：本机实现、部署及验证收尾完成，真实模型生成由用户重测。未提交、推送、合并；模型 API 设置页面未修改。

## 交付

- `GET /api/v1/tasks/{tid}/activity`：当前步骤、资料块/关系小节完成与失败数量、已保存消歧对、在途请求数量/起始时间、退避时间和 worker 活动状态。只读现有账本与当前任务修订，无新增模型调用和逐秒写库。
- 资料卡每3秒刷新详情、每秒更新时间；刷新已取消任务也能看到已保存结果。网络断开不伪装仍在实时更新；使用请求/订阅代次隔离取消前的迟到消息。
- `POST /api/v1/tasks/{tid}/resume`：继续原任务，同task_id、资料、检查点和缓存；仅已取消且无残留租约、无待清理/T6提交时允许。失败/已完成任务不恢复。
- personal模式仅原创建教师可继续；重新校验当前凭据，允许密钥轮换，端点/模型/思考设置变化拒绝复用。累计模型调用及预算不清零。
- SQLite025新增resume_attempt_base/resume_count，实际attempt继续单调，每次显式继续获得有限自动重试额度。回退拒绝有效租约及任何仍活动的已恢复任务。
- 取消期间原在途完整裁决、成功块/小节在原有效租约和凭据保护下保存，不推进取消进度、不写图谱、不发新请求。旧模式和消歧模式均统一物理请求前取消/租约守卫。

接口与状态机规范见 `specs/task-processing.md` §9、ADR-103、`src/contracts/api.v1.yaml`；SSE v1结构保持不变。实施计划见 `docs/superpowers/plans/2026-11-15-task-continue.md`。

## 已有验证证据

- 恢复生命周期有效RED25 failed/6 passed；生命周期/租约/取消/迁移组合290 passed（1项现有Starlette弃用警告）；最后契约/回退/真实恢复重点4 passed。
- 真实临时SQLite、resume_task→claim_next→run_extract_stage：关系请求中取消后继续，新增模型调用0；首对消歧中取消后继续，仅剩2对消歧及1次关系调用。使用FakeModelClient，没有付费调用。
- activity缺端点RED14 failed/1 passed；范围/缺修订RED2 failed/1 passed；修复后17 passed。只读用户旧任务得到58.33%、8/8块、5/6小节、111对消歧、无在途请求、可继续。
- 取消保留结果初始RED5 failed/2 passed；补齐并发收尾后14 passed。初版夹具的lease三字段约束问题已纠正，不计产品缺陷。
- 独立审查发现旧模式取消后仍能发repair；正式回归复现后统一所有模式守卫，独立原反例1 passed。没有绕过鉴权、旧租约或取消来获得结果。
- 中途组合测试在025注释修改时出现迁移checksum漂移，以及尚未合入的activity范围修复失败；不计作最终门禁结果。最终源码冻结后重新运行完整门禁。
- 最终取消边界与既有 E12 回归 `PYTHONPATH=src/backend:. ... -m pytest tests/backend/test_cancelled_result_reuse.py tests/backend/test_e12.py -q`：57 passed，exit 0（200.35秒），包含旧模式取消后不启动 repair。
- 前端首次定向140 passed；随后补状态竞态回归。前端全量91文件/1596 passed、零skip，gate PASS；最后提示边界追加2例后定向h02+c12+l10共170 passed（14.86秒）。最终类型检查与生产构建均exit0，仅既有大chunk警告；后端全量最终4687 passed、27 skipped、1旧取消断言失败（1658.28秒，原命令exit1）；该断言按新需求更新后完整scheduler文件14 passed。其余用例通过，产品源码未变，未为测试断言调整重复整套全量。前端早期默认5秒超时的裸全量已停止，最终按30秒超时、2workers重跑完整回归通过。
- 最终后端全量扫描发现旧scheduler测试仍要求取消后丢弃晚到结果；定向RED复现1 failed，按新需求仅更新测试预期，并增加取消/租约失效均不发新请求、不推进进度的断言，完整scheduler文件14 passed（18.32秒、exit0）。生产源码与已部署镜像未变。原full结果与该修复复测分开记录，不把原full伪记为exit0。
- 最后前端交叉复查覆盖刷新已取消任务、同ID继续、防双击、旧SSE代次、activity状态版本隔离和断线/终态计时，未发现确定功能问题。
- 部署脚本独立审计发现回退先停服务再拒绝的可用性问题；已加停机前无活动任务检查，回退命令失败时恢复当前版本服务。正常升级路径审计未发现确定数据风险。

## 用户旧任务

「测试，第三章1.1」任务 `a3cab66a0b014bc29d6c5b80bceed6b7` 保留8块、111对消歧和5个小节检查点，可直接继续。旧代码在取消后丢弃了第6节的134秒响应，数据库只有调用用量，没有响应正文，升级不能追回；该节需再次请求，已保存部分可复用。升级不自动继续任务，由用户点击按钮。

## 部署及回退

维护脚本与证据位于忽略目录 `.demo/task-continue-20261115/`。构建来源为main归档加已核对源代码白名单，不含资料、数据库、环境密钥或依赖目录。升级前检查无活动生成任务，停止API/worker，自动备份并迁移025，再更新API/worker/web。

维护入口：`python3 .demo/task-continue-20261115/upgrade.py start`；可双击同目录 `启动本机修复版.command`。回退用 `upgrade.py rollback`，先停止服务、备份并执行025回退保护，再恢复上一份relation-resume后端与main前端。不能直接用旧启动器对025数据库启动旧镜像。

实际部署（2026-11-15 17:13 UTC）：

- API/worker：`smartsketch-backend:task-continue-d9d16ca`，镜像 `sha256:e86253ab46f8633ea20da149f3d7cd73c2d21a8d1939f3ceb289045a536d64bb`。
- web：`smartsketch-frontend:task-continue-d9d16ca`，镜像 `sha256:8d5bb57629fef4e7e2aa79143c34520d1cc63a9eed251c7345278f52113fc70a`。两个镜像均构建成功，41项源代码摘要与工作区一致；容器内27项后端/DTO修改摘要再次一致。
- SQLite025前备份：容器 `/data/backups/20261115T171341843919Z-before-025.sqlite`，`integrity_check=ok`、备份最高版本024。025迁移成功；八张业务表的行数/SHA256和任务状态全部一致。验证脚本首次把生成Enum与字符串直接比较导致断言失败，修正脚本为`.value`后exit0，未改产品代码。
- API/worker/web/Neo4j四服务healthy，`GET http://127.0.0.1:8080/health` 返回ok；仍保持关系180秒、其他60秒及此前1000倍预算。
- Ahn浏览器原第三章资料页刷新后显示58%、资料块8/8、关系小节5/6、已保存消歧111对和“继续处理”。未点击继续、未发真实模型请求；部署后model_calls摘要不变。
- 旧`.demo/relation-resume-20261115/启动本机修复版.command`已指向本轮新启动入口，原内容已留备份；不要直接调用旧upgrade.py来启动旧后端。
- `./scripts/verify.sh` basic exit0：真源/生成物一致、25项负向门禁及B08/B09/B10/B12/B13回归通过。后端全量原始结果及唯一旧断言修复复测见上方，日志`backend-final.log`与`cancel-inflight-scheduler-green.log`，不将原始full门禁记为绿。27项Neo4j/integration跳过按项目full配置登记；本轮未跑真实模型或Neo4j完整集成。

真实生成耗时和图谱质量仍由用户测试。
