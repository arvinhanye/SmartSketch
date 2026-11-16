# RELATION-RESUME-01：关系超时与消歧结果恢复

日期 2026-11-15；负责人 Codex；基线 main `d9d16ca` + 本线程预算补丁。用户明确授权修复、更新本机后自行测试。状态：本机已部署，基础/后端全量门禁通过，真实模型由用户重测；不涉及模型 API 设置页面或公开 DTO。

## 根因与交付

第三章重测任务 `da0a4f113b694a75bb846c83e84edfbe` 已成功上传，8 个块完成；「概念 方法与适用条件」29 个实体的小节关系请求 10 次在约 60 秒超时，两次熔断释放后反复重做局部消歧。后两轮又出现 49 次成功裁决，15 分 50 秒后用户取消。原完整小节检查点只能在关系完成后写入，因此中间裁决无法复用。

- 新增 `LLM_RELATION_TIMEOUT_SECONDS=180`（有限正数），只对普通/归一化关系及其修复请求生效；实体和语义裁决沿用 60 秒。两个生产工厂统一接入现有 RelationExtractor timeout 参数，租约心跳在长请求期间继续续租。
- 新增 SQLite 024 `task_section_decisions`：完整裁决逐对保存，任务删除级联、行不可变、冲突不覆盖。SAME 完成独立复核后才能保存；failed/deferred/中断双判不能当作成功缓存。
- 缓存按课程、任务、小节、完整输入摘要和实体对隔离。摘要含全部候选与来源、模型/提示词、输入/输出预算、召回参数和缓存协议版本；工厂附带非敏感端点/主备模型/模式/个人思考开关身份。变化后不误复用。
- 读写分别使用短租约事务，检查课程、阶段、当前 token、有效期及取消；凭据守卫在事务前执行。网络调用不持有 SQLite 写锁。保存失败按 storage 暂停处理；旧租约与撤销凭据不能写入或命中缓存。
- 已完成的小节仍使用原完整检查点；未完成小节恢复时仅请求尚无完整裁决的对。复用决策保留原审计信息，不新增虚假的模型调用记录。缓存不是最终合并批准。

## 验证

- 关系超时 RED 8 failed / 1 passed；context 接线 RED 4 failed / 5 passed。修复后关系、E11、预算、裁决、B06 组合 **141 passed**。
- 分析恢复 RED **10 failed**（旧分析接口没有缓存），GREEN **10 passed**：中途故障保留完整对、JSON 往返、材料/模型/提示词/预算/端点变更失效，未完成同义复核与失败不缓存。
- 存储与回退组合 **52 passed**，包括两个旧迁移回退夹具按新版本倒序回退。缓存 worker **6 passed**：真实临时 SQLite、关系超时熔断、换租约接管，以及取消/token/过期/阶段/跨课程围栏。
- 完整重试反例：禁用缓存后接管又发出 3 次 resolve_duplicate，断言按预期失败；启用后只发出 1 次 extract_normalized_relations，0 次重复裁决。反例 `.demo/relation-resume-20261115/reclaim-without-cache-red.log`。测试初版的参数/模拟输出截断问题已纠正，不把这些夹具错误计为产品缺陷。
- 独立复审 16/16 文件，无确认缺陷；独立临时 SQLite 3 项通过：网络期间无写锁、撤销凭据后禁止保存、撤销后禁止读取复用。未访问真实模型。
- 部署容器 Python 3.12.16 中用隔离临时 SQLite + FakeModelClient 实走缓存：首次 1 次裁决、重新构造缓存后 0 次重放，报告完全一致；临时库自动删除，无实际模型调用。
- 实际维护回退脚本在隔离 SQLite 上执行 024→023→024 成功；只移除缓存与迁移记录，迁移器重新应用正常。
- 基础门禁：`PATH="/Users/arvinhan/Desktop/SmartSketch-main/.venv/bin:$PATH" ./scripts/verify.sh` exit 0，含 25 项负向检查及全部契约回归。后端 `PYTHON=/Users/arvinhan/Desktop/SmartSketch-main/.venv/bin/python scripts/verify/backend.sh full` exit 0，**4626 passed、27 skipped、1 warning**，1675.31 秒；27 项跳过通过门禁校验，警告为现有 Starlette TestClient/httpx 弃用提示。日志位于 `.demo/relation-resume-20261115/basic.log` 与 `backend-full.log`。上述组合有重叠，不相加计数。

## 本机部署与数据保护

- 新镜像 `smartsketch-backend:relation-resume-d9d16ca`，ID `sha256:6a4c5bddb0e83ffcbf95271c23ac6c2f92082f0ab4b46af25324d622b4626ca9`。构建源为 main 归档 + 当前后端修复白名单，含新迁移/仓储/缓存文件；没有真实资料、`.env` 或密钥。运行中的全部 13 个修改文件哈希与构建输入一致。
- 在确认无处理中的生成任务后停止 API/worker，使用迁移器生成一致性备份并仅应用 024；备份 `/data/backups/20261115T155122573101Z-before-024.sqlite`，`integrity_check=ok`，旧 schema=023。备份留在原应用数据卷，不复制到仓库。
- 迁移前后 processing_tasks/materials/chunks/model_calls/task_chunk_checkpoints/fusion_plans/task_relation_revisions 七张业务表的行数与内容 SHA256 一致，任务状态未变；取消任务没有恢复或重跑。
- API/worker 实际配置：关系超时 180、通用超时 60；此前输出 4096000、完整请求字节 24000000、窗口 64000、任务 token 500000000、日 token 5000000000 均保留。DeepSeek 抽取请求仍遵守 393216 输出上限。
- 原地址 `http://127.0.0.1:8080` 的健康检查返回 ok，worker 健康命令通过；前端继续 main `d9d16ca`，Nginx 已 reload 刷新后端地址。未请求真实模型，真实耗时与图谱效果留给用户重测。

## 使用与恢复

本次仍是本机测试补丁，未提交/推送/发布。请直接刷新当前页面，新建空白测试课程重新导入第三章；取消任务不能自动续跑。缓存将在本次新任务内部的后续失败接管/重启中生效，不跨任务复用旧模型结果。

原发行启动器仍绑定旧包，不能用于重建这份 schema024 本机测试环境；旧镜像不知道新迁移，回退须先移除024缓存。维护命令位于本工作树忽略目录 `.demo/relation-resume-20261115/`：

- 可双击 `.demo/relation-resume-20261115/启动本机修复版.command` 重新启动当前版本；脚本语法检查通过。
- 当前版本重新启动：`python3 .demo/relation-resume-20261115/upgrade.py start`。
- 首次升级已完成；流程为 `stop` → `migrate` → `start`。迁移前必须先停 API/worker，不能在活跃生成中执行。
- 回退到上一份 1000 倍预算镜像：确认无正在处理的任务后运行 `python3 .demo/relation-resume-20261115/upgrade.py rollback`；停止 API/worker，以当前镜像执行 `rollback_024.py`（先备份，拒绝活动租约），再启动旧预算镜像并 reload Nginx。只回退缓存，不删除课程、资料、模型调用或图谱数据。禁止直接调用上一轮旧 `switch_backend.py` 绕过迁移回退。

后续需由用户真实生成确认 180 秒是否覆盖本模型该小节的耗时，检查关系数量、孤立率、重复和误合并；若服务商超过 180 秒仍可能超时，工程回归不等于真实模型质量或时长已验收。
