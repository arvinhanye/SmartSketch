# 测试文件索引

用于从测试文件名查找被测模块或功能。范围为以下三个非递归匹配模式：

- `tests/backend/test_*.py`
- `tests/frontend/*.test.ts`
- `tests/integration/test_*.py`

描述和关联依据来自文件头文档字符串/用途注释、import 与 describe 名称；任务编号不从文件名推测。缺少明确关联或无法确定具体功能的地方标为「待确认」。编号和条款保留源文件口径，不表示整份规格已被该文件覆盖。

维护时同步新增、删除或移动的条目；来源注释、import 或 describe 改动后重新核对描述。若 OPT-03 与本任务同期合入，后合入方需基于合并后的文件重新生成索引。文件列统一使用以仓库相对路径为标签的 Markdown 链接，链接目标相对本文件。

校验命令：`python3 -m pytest tests/tooling/test_test_index.py -q`。该检查拒绝漏项、失效或范围外条目、重复条目、错误链接及无效条目格式。任务和验证记录见 [OPT-04 交接](../docs/handoffs/codex-opt-04.md)。

## 后端

| 文件 | 被测模块或功能（一句话） | 对应规格 / ADR / 任务 ID |
| --- | --- | --- |
| [`tests/backend/test_264_cleanup_lock.py`](backend/test_264_cleanup_lock.py) | 图持久化清理遵循 ADR-094 定义的执行顺序与课程锁边界。 | ADR-094；ADR-072 |
| [`tests/backend/test_adr021.py`](backend/test_adr021.py) | 资料列表返回最新任务 ID，并支持删除尚未贡献图谱内容的资料。 | ADR-021 |
| [`tests/backend/test_adr022.py`](backend/test_adr022.py) | 上传策略接口下发 UPLOAD_MAX_BYTES 配置的上传大小上限。 | ADR-022 |
| [`tests/backend/test_adr079_register.py`](backend/test_adr079_register.py) | 学生自助注册接口及账号创建、注册限流行为。 | ADR-079 |
| [`tests/backend/test_disambiguation_generation.py`](backend/test_disambiguation_generation.py) | 生成阶段语义分析预算、真实覆盖、来源核查与每次调用凭据保护。 | ADR-098；DISAMBIG-BE-01 |
| [`tests/backend/test_extraction_windows.py`](backend/test_extraction_windows.py) | 完整请求预算、Unicode 窗口覆盖、完整实体对及超限前置拒绝。 | ADR-101；DISAMBIG-BE-04 |
| [`tests/backend/test_extraction_window_worker.py`](backend/test_extraction_window_worker.py) | 窗口来源还原、原子结果、调用守卫及接管策略固定。 | ADR-101；DISAMBIG-BE-04 |
| [`tests/backend/test_disambiguation_review.py`](backend/test_disambiguation_review.py) | 有效语义审核、三态与技术覆盖、过期回退及过滤后计数。 | ADR-100；DISAMBIG-BE-03 |
| [`tests/backend/test_disambiguation_api.py`](backend/test_disambiguation_api.py) | 覆盖/历史/撤销 HTTP 的教师权限、严格参数、分页与冲突协议。 | ADR-100；DISAMBIG-BE-03 |
| [`tests/backend/test_disambiguation_mentions.py`](backend/test_disambiguation_mentions.py) | 提及身份、同名异义保护、旧检查点兼容与关系输入限定语。 | ADR-098；DISAMBIG-BE-01 |
| [`tests/backend/test_disambiguation_resolution.py`](backend/test_disambiguation_resolution.py) | 三态语义、差异复核、双侧引用和长输入/输出失败保护。 | ADR-098；DISAMBIG-BE-01 |
| [`tests/backend/test_disambiguation_metrics.py`](backend/test_disambiguation_metrics.py) | 消歧判定指标中误判和技术未检查分母的完整性。 | ADR-098；DISAMBIG-BE-01 |
| [`tests/backend/test_disambiguation_recall.py`](backend/test_disambiguation_recall.py) | 混合召回通道、课程/向量空间隔离和预算。 | ADR-099；DISAMBIG-BE-02 |
| [`tests/backend/test_disambiguation_mapping.py`](backend/test_disambiguation_mapping.py) | 完整组校验、来源保留和合并诱发图环拦截。 | ADR-099；DISAMBIG-BE-02 |
| [`tests/backend/test_fusion_generation.py`](backend/test_fusion_generation.py) | 向量物理调用前取消保护。 | ADR-099；DISAMBIG-BE-02 |
| [`tests/backend/test_fusion_storage.py`](backend/test_fusion_storage.py) | 物理草稿指针、不可变计划与过期保护，以及取消/失败资料的计划安全清理。 | ADR-099；DISAMBIG-BE-02 |
| [`tests/backend/test_graph_projection.py`](backend/test_graph_projection.py) | 新草稿副本写入和可见性协议。 | ADR-099；DISAMBIG-BE-02 |
| [`tests/backend/test_fusion_undo.py`](backend/test_fusion_undo.py) | 单组合并逆向差异、修订号单调递增、独立组撤销及后续内容冲突。 | ADR-099；DISAMBIG-BE-02 |
| [`tests/backend/test_b05.py`](backend/test_b05.py) | FastAPI 应用工厂与健康检查契约。 | B05 |
| [`tests/backend/test_b06.py`](backend/test_b06.py) | 环境变量配置读取、启动校验及向量空间验证。 | B06 |
| [`tests/backend/test_c01.py`](backend/test_c01.py) | SQLite 连接、向前迁移与可恢复备份。 | C01 |
| [`tests/backend/test_c02_phase_logs.py`](backend/test_c02_phase_logs.py) | 问答准备与抽取任务各阶段的结构化耗时日志。 | C02-3；C03-2 |
| [`tests/backend/test_c02_prompt_v3.py`](backend/test_c02_prompt_v3.py) | answer_with_context v3 问答提示词装配及简洁作答规则。 | C02-2；ADR-089；C02-4 |
| [`tests/backend/test_c02_reasoning.py`](backend/test_c02_reasoning.py) | 模型推理字数和 token 用量计量，以及首次推理和可见内容耗时记录。 | C02-2；ADR-089 |
| [`tests/backend/test_c02.py`](backend/test_c02.py) | 课程与成员仓储的唯一性、跨课程角色独立性、外键和学生角色限制。 | C02；[specs/identity-access.md](../specs/identity-access.md)；ADR-013；IAM-24 |
| [`tests/backend/test_c02b_disable_thinking.py`](backend/test_c02b_disable_thinking.py) | 个人模型的关闭思考开关、配置保存、任务快照及问答缓存失效。 | ADR-090；C02b |
| [`tests/backend/test_c03.py`](backend/test_c03.py) | 基于真实 SQLite 记录的身份认证与课程授权。 | C03 |
| [`tests/backend/test_c04.py`](backend/test_c04.py) | 课程 HTTP 契约、访问规则与 SQLite 事务边界。 | C04 |
| [`tests/backend/test_c05.py`](backend/test_c05.py) | 文件存储的格式校验、大小限制、原子写入与随机存储名。 | C05 |
| [`tests/backend/test_c06.py`](backend/test_c06.py) | 资料与初始 queued 任务的原子创建。 | C06 |
| [`tests/backend/test_c07.py`](backend/test_c07.py) | 课程资料上传和资料列表 API。 | C07 |
| [`tests/backend/test_c08.py`](backend/test_c08.py) | 文档处理任务状态机的纯状态转换。 | C08；ADR-010 |
| [`tests/backend/test_c09.py`](backend/test_c09.py) | worker 原子领取任务、租约管理及相关状态转换。 | C09；[specs/task-processing.md](../specs/task-processing.md)；ADR-011 |
| [`tests/backend/test_c10.py`](backend/test_c10.py) | 任务取消服务与 API 的幂等性、状态边界、课程隔离及领取竞争。 | C10；[specs/task-processing.md](../specs/task-processing.md)；[specs/identity-access.md](../specs/identity-access.md)；C09；TASK-6；TASK-8 |
| [`tests/backend/test_c11.py`](backend/test_c11.py) | 任务查询与 SSE 的票据授权、快照、状态事件、心跳及断开清理。 | C11；[specs/task-processing.md](../specs/task-processing.md)；[specs/identity-access.md](../specs/identity-access.md)；C03；C16 |
| [`tests/backend/test_c13.py`](backend/test_c13.py) | 本地账号登录、密码校验与 HS256 访问令牌签发。 | C13；[specs/identity-access.md](../specs/identity-access.md) |
| [`tests/backend/test_c14.py`](backend/test_c14.py) | 账号管理命令与幂等演示账号初始化。 | C14；[specs/identity-access.md](../specs/identity-access.md) |
| [`tests/backend/test_c15.py`](backend/test_c15.py) | 课程成员列表、添加与移除 API 的教师授权、幂等性和课程隔离。 | C15；[specs/identity-access.md](../specs/identity-access.md) |
| [`tests/backend/test_c16.py`](backend/test_c16.py) | SSE 一次性票据的申领、哈希存储、核销及迁移恢复。 | C16；[specs/identity-access.md](../specs/identity-access.md)；C11 |
| [`tests/backend/test_chat_question_limit.py`](backend/test_chat_question_limit.py) | ChatRequest 拒绝超长问题，并将其作为 422 输入错误处理。 | M11；C2 |
| [`tests/backend/test_course_detail.py`](backend/test_course_detail.py) | 课程详情 getCourse 接口的读取行为。 | 待确认 |
| [`tests/backend/test_d01.py`](backend/test_d01.py) | 解析输出模型的来源定位、合法边界及自编文档 fixture 约束。 | D01 |
| [`tests/backend/test_d02.py`](backend/test_d02.py) | TXT 编码检测、标题层级解析与来源行号保留。 | D02 |
| [`tests/backend/test_d03.py`](backend/test_d03.py) | Markdown AST 转为 ParsedDocument，并保留块类型、章节路径与来源行号。 | D03；D01 |
| [`tests/backend/test_d04.py`](backend/test_d04.py) | DOCX 段落、标题与表格解析，以及损坏和危险输入处理。 | D04 |
| [`tests/backend/test_d05.py`](backend/test_d05.py) | PDF 正文、物理页码与版面信息提取及不可读文档处理。 | D05；D01；D07 |
| [`tests/backend/test_d06.py`](backend/test_d06.py) | PDF 标题识别、章节树构建与带章节路径的解析输出。 | D06；D05；D07 |
| [`tests/backend/test_d07.py`](backend/test_d07.py) | 重复 PDF 页眉页脚清洗，并保留物理页码和原文位置映射。 | D07；D05 |
| [`tests/backend/test_d08.py`](backend/test_d08.py) | 按章节切分文档块，并保留精确的解析块来源偏移。 | D08 |
| [`tests/backend/test_d09.py`](backend/test_d09.py) | 验证资料修订 ID、块 ID 与抽取缓存键。 | D09；ADR-012 |
| [`tests/backend/test_d1.py`](backend/test_d1.py) | 回答截断与出处校验组合下的生成故障、有效回答和资料未覆盖分类。 | D1；ADR-082；ADR-015 |
| [`tests/backend/test_d10.py`](backend/test_d10.py) | 来源块持久化及其不可变性、隔离和删除约束。 | D10；ADR-012；ADR-018；[specs/teacher-review-publish.md](../specs/teacher-review-publish.md)；[specs/task-processing.md](../specs/task-processing.md) |
| [`tests/backend/test_d11_upload_config.py`](backend/test_d11_upload_config.py) | 上传单文件大小上限与资料存储根目录配置落地。 | D-11 |
| [`tests/backend/test_d11.py`](backend/test_d11.py) | 解析阶段 worker 串联文件读取、解析、分块、持久化和检查点状态转换。 | D11；[specs/task-processing.md](../specs/task-processing.md)；ADR-011；ADR-012；ADR-018；[specs/teacher-review-publish.md](../specs/teacher-review-publish.md)；C09；D08；D09；D10；TASK-14；LEASE-4；LEASE-7 |
| [`tests/backend/test_d2.py`](backend/test_d2.py) | 共享向量请求按调用记账，区分缓存、批次和课程请求归属。 | D2；ADR-011；ADR-082 |
| [`tests/backend/test_d3.py`](backend/test_d3.py) | 问答全链路共享单调时钟截止时间，并限制向量请求、图库读取和 HTTP 传输。 | D3；ADR-082 |
| [`tests/backend/test_demo_mode.py`](backend/test_demo_mode.py) | 无网络演示模型的配置、抽取、向量检索和带出处问答行为。 | ADR-076；E05；E06；E11；J06 |
| [`tests/backend/test_e01.py`](backend/test_e01.py) | 版本化提示词按用途和版本查找、严格渲染并计算模板摘要。 | E01 |
| [`tests/backend/test_e02.py`](backend/test_e02.py) | 模型请求、结果和错误分类接口及确定性 fake 适配器。 | E02；A07；ADR-011；E04 |
| [`tests/backend/test_e03.py`](backend/test_e03.py) | OpenAI 兼容的聊天与向量适配器、传输错误映射和向量批处理校验。 | E03；A07；ADR-011；E02；ADR-017 |
| [`tests/backend/test_e04.py`](backend/test_e04.py) | 模型调用策略的退避、主备切换、熔断、预算及调用记账。 | E04；E02；A07；ADR-011；[specs/task-processing.md](../specs/task-processing.md)；[specs/grounded-qa.md](../specs/grounded-qa.md)；O12 |
| [`tests/backend/test_e05.py`](backend/test_e05.py) | 块级实体抽取、输出校验与来源身份关联。 | E05；[specs/course-knowledge-graph.md](../specs/course-knowledge-graph.md)；[specs/task-processing.md](../specs/task-processing.md)；E02 |
| [`tests/backend/test_e06.py`](backend/test_e06.py) | 补漏实体抽取的轮次、停止条件、输出校验和预算调用记录。 | E06；A07；E05；E02 |
| [`tests/backend/test_e07.py`](backend/test_e07.py) | 向量调用的批处理、向量空间完整性及批次失败恢复。 | E07 |
| [`tests/backend/test_e08.py`](backend/test_e08.py) | 实体名称归一化与重复候选识别，仅列候选而不执行合并。 | E08 |
| [`tests/backend/test_e09.py`](backend/test_e09.py) | 同课程同向量空间实体配对的阈值分层、计数与隔离校验。 | E09 |
| [`tests/backend/test_e10.py`](backend/test_e10.py) | 同课程实体证据对的模型裁决与配对校验。 | E10 |
| [`tests/backend/test_e11.py`](backend/test_e11.py) | 两阶段关系抽取及悬空、跨课程、自环、重复和前置方向校验。 | E11；E02 |
| [`tests/backend/test_e12.py`](backend/test_e12.py) | 抽取阶段 worker 编排、实体和关系检查点、取消及局部重试边界。 | E12；[specs/task-processing.md](../specs/task-processing.md)；ADR-011；E04；E05；E06；E11；TASK-4；TASK-9；TASK-10；TASK-13；LEASE-2；LEASE-6；LEASE-11 |
| [`tests/backend/test_extraction_concurrency_default.py`](backend/test_extraction_concurrency_default.py) | 默认并发 8 与环境覆盖对实际在途请求的约束。 | EXTRACT-PERF-01；[specs/task-processing.md](../specs/task-processing.md)；ADR-011 |
| [`tests/backend/test_extraction_perf_scheduler.py`](backend/test_extraction_perf_scheduler.py) | 共享池重叠、阈值、取消、接管、鉴权与调用记账。 | EXTRACT-PERF-01；[specs/task-processing.md](../specs/task-processing.md)；ADR-011 |
| [`tests/backend/test_enum_input_validation.py`](backend/test_enum_input_validation.py) | 图谱节点、关系与审核接口在编辑 IO 前拒绝非法枚举输入。 | 待确认 |
| [`tests/backend/test_f02.py`](backend/test_f02.py) | 验证 Neo4j 图仓储的作用域边界。 | F02 |
| [`tests/backend/test_f05.py`](backend/test_f05.py) | DAG 纯函数检测候选前置关系是否成环，并返回闭合环路径。 | F05；[specs/course-knowledge-graph.md](../specs/course-knowledge-graph.md)；DAG-1；DAG-8；DAG-9；DAG-10；B11 |
| [`tests/backend/test_f07.py`](backend/test_f07.py) | 图谱与知识点读取接口，以及模拟图读取器记录的课程作用域。 | F07；D10 |
| [`tests/backend/test_f08.py`](backend/test_f08.py) | 教师知识点编辑、修订冲突与手工编辑锁的显式解锁。 | F08；ADR-035；F04 |
| [`tests/backend/test_f09_cascade.py`](backend/test_f09_cascade.py) | 级联删除预览的可见范围、共享后代、令牌冲突、权限与事务重试。 | F09；ADR-097 |
| [`tests/backend/test_f11.py`](backend/test_f11.py) | 审核队列分类、游标分页与单项通过、拒绝和合并处理。 | F11；ADR-060 |
| [`tests/backend/test_f12.py`](backend/test_f12.py) | 教师图谱编辑审计日志及跨 Neo4j、SQLite 写入失败后的可重试记录。 | F12；ADR-061 |
| [`tests/backend/test_g01.py`](backend/test_g01.py) | 发布快照集合、阻断原因、规范化序列化、摘要及完整往返恢复。 | G01；[specs/teacher-review-publish.md](../specs/teacher-review-publish.md) |
| [`tests/backend/test_g02.py`](backend/test_g02.py) | 版本元数据与发布、回滚尝试的 SQLite 持久化和幂等约束。 | G02；[specs/teacher-review-publish.md](../specs/teacher-review-publish.md) |
| [`tests/backend/test_g04_sqlite.py`](backend/test_g04_sqlite.py) | 发布流程所需的 SQLite 草稿状态读取、T7 与课程忙锁持有者查询。 | G04 |
| [`tests/backend/test_g05_sqlite.py`](backend/test_g05_sqlite.py) | 清扫器使用的 SQLite 过期尝试和课程列表查询。 | G05 |
| [`tests/backend/test_g05_sweep_schedule.py`](backend/test_g05_sweep_schedule.py) | worker 周期清扫调度、失败隔离、禁用开关及环境变量配置。 | A06；ADR-036；ADR-072 |
| [`tests/backend/test_g06.py`](backend/test_g06.py) | 版本列表、发布和回滚 HTTP 接口及真实 SQLite 版本列表读取。 | G06 |
| [`tests/backend/test_g07.py`](backend/test_g07.py) | 统一发布版本解析器，确保单次请求内图谱、推荐和问答使用固定版本。 | G07；[specs/teacher-review-publish.md](../specs/teacher-review-publish.md) |
| [`tests/backend/test_g08_index.py`](backend/test_g08_index.py) | 文本块向量索引在线状态校验。 | G08；ADR-055 |
| [`tests/backend/test_i01.py`](backend/test_i01.py) | 原始掌握进度的仓储持久化与事务语义。 | I01 |
| [`tests/backend/test_i02.py`](backend/test_i02.py) | 掌握进度读写 API、读时投影、课程隔离与发布指针变化后的整批复核。 | I02；[specs/learning-path.md](../specs/learning-path.md)；ADR-017；G04；G06 |
| [`tests/backend/test_i03.py`](backend/test_i03.py) | 学习路径可学集合纯函数，按直接前置与已掌握集合筛选知识点。 | I03；[specs/learning-path.md](../specs/learning-path.md) |
| [`tests/backend/test_i04.py`](backend/test_i04.py) | 学习路径四项评分、稳定排序及结构化推荐理由。 | I04；[specs/learning-path.md](../specs/learning-path.md) |
| [`tests/backend/test_i05.py`](backend/test_i05.py) | 推荐查询 API 的版本一致性、稳定截断、课程隔离和损坏图错误处理。 | I05；[specs/learning-path.md](../specs/learning-path.md)；G04 |
| [`tests/backend/test_install_backup.py`](backend/test_install_backup.py) | `app.tools.install_backup` 的卷备份与恢复接口。 | 待确认 |
| [`tests/backend/test_install_bootstrap.py`](backend/test_install_bootstrap.py) | `app.services.install_bootstrap` 与 `app.tools.bootstrap_teacher` 的初始化入口。 | 待确认 |
| [`tests/backend/test_install_probe.py`](backend/test_install_probe.py) | app.tools.install_probe 的安装状态探测。 | 待确认 |
| [`tests/backend/test_invite_codes.py`](backend/test_invite_codes.py) | 课程邀请码 HTTP 行为、猜测限制及事务顺序。 | ADR-096 |
| [`tests/backend/test_invite_migration.py`](backend/test_invite_migration.py) | 020 迁移保持已撤销邀请码不可用，并保留既有课程成员关系。 | 待确认 |
| [`tests/backend/test_j03.py`](backend/test_j03.py) | 多轮问答检索问题改写及任意故障时退回原问题。 | J03；[specs/grounded-qa.md](../specs/grounded-qa.md)；A07；ADR-011；ADR-015；E02；E04 |
| [`tests/backend/test_j04.py`](backend/test_j04.py) | 两路检索候选合并、上下文预算与允许引用的证据集合构建。 | J04；[specs/grounded-qa.md](../specs/grounded-qa.md)；ADR-065；J01；J02 |
| [`tests/backend/test_j05.py`](backend/test_j05.py) | 基于编号证据的流式问答生成、资料注入处理及超时错误。 | J05；[specs/grounded-qa.md](../specs/grounded-qa.md)；ADR-068；E02；E04 |
| [`tests/backend/test_j06.py`](backend/test_j06.py) | `app.services.qa.citations` 的引用流相关接口。 | 待确认 |
| [`tests/backend/test_j07.py`](backend/test_j07.py) | 问答生成终止边界上的整条链路截止时间处理。 | J07 |
| [`tests/backend/test_j10.py`](backend/test_j10.py) | 问答结果持久化及 SQLite 写入失败时保持 JSON/SSE 原响应和脱敏日志。 | J10；[specs/grounded-qa.md](../specs/grounded-qa.md) |
| [`tests/backend/test_k02_run.py`](backend/test_k02_run.py) | 本机抽取运行脚本的离线验证，覆盖输出、失败继续、预算停止与凭据保护。 | K02；E02 |
| [`tests/backend/test_k02.py`](backend/test_k02.py) | 抽取与融合离线评测的匹配、分项指标、阈值判定和可复现性。 | K02；[specs/course-knowledge-graph.md](../specs/course-knowledge-graph.md)；K01 |
| [`tests/backend/test_k03.py`](backend/test_k03.py) | evaluation.evaluate_qa 的问答负例与人工语义复核。 | K03 |
| [`tests/backend/test_k04.py`](backend/test_k04.py) | evaluation.benchmark_pipeline 的 SSE 耗时与报告汇总。 | K04 |
| [`tests/backend/test_k09.py`](backend/test_k09.py) | 演示课程导入的幂等性、课程范围限制、重试及资料替换拒绝。 | K09 |
| [`tests/backend/test_k13.py`](backend/test_k13.py) | 抽取消融实验脚本的离线分组评测、校验复用、失败隔离及凭据保护。 | K13；E02；E05；E11 |
| [`tests/backend/test_l02_measure.py`](backend/test_l02_measure.py) | 测量脚本的 multipart 编码与任务终态判定纯函数。 | L02 |
| [`tests/backend/test_l04.py`](backend/test_l04.py) | 迁移 015、模型凭据加密、用户模型配置及任务快照仓储。 | L04；ADR-080 |
| [`tests/backend/test_l05.py`](backend/test_l05.py) | 用户模型地址的语法、公网地址判定、解析后校验与 IP 固定。 | L05；ADR-080 |
| [`tests/backend/test_l06.py`](backend/test_l06.py) | 个人模型配置 API 的本人隔离、脱敏、地址校验、连接测试及限流。 | L06；ADR-080 |
| [`tests/backend/test_l07.py`](backend/test_l07.py) | 上传任务模型配置快照、worker 模型绑定及配置变更和重启接管语义。 | L07；ADR-080 |
| [`tests/backend/test_l08.py`](backend/test_l08.py) | 问答使用个人模型配置，且熔断、预算和调用记录按用户隔离。 | L08；ADR-080 |
| [`tests/backend/test_l09.py`](backend/test_l09.py) | 不支持 local 向量模式及 personal 模式的启动配置约束。 | L09；ADR-081 |
| [`tests/backend/test_l11_datasets.py`](backend/test_l11_datasets.py) | worker 使用的解析器对比赛资料中文、页码和章节的读取。 | L11 |
| [`tests/backend/test_l11_pdf_reflow.py`](backend/test_l11_pdf_reflow.py) | PDF 自动换行续行的段落合并，保留标题判断与页码定位。 | L11-7；ADR-084；L11-6 |
| [`tests/backend/test_l12.py`](backend/test_l12.py) | 知识点来源和问答引用附带同课资料文件名及查名失败降级。 | L12；ADR-085 |
| [`tests/backend/test_l14_reason.py`](backend/test_l14_reason.py) | 推荐理由区分缺失属性的中性默认值与实际标注值。 | L14-3；R11；ADR-014 |
| [`tests/backend/test_l15.py`](backend/test_l15.py) | 权限隔离、不可信文件名及图读取作用域的回归覆盖。 | L15 |
| [`tests/backend/test_migration_rollbacks.py`](backend/test_migration_rollbacks.py) | 007 起数据库迁移的手工回滚说明约定。 | 待确认 |
| [`tests/backend/test_model_discovery.py`](backend/test_model_discovery.py) | app.services.model_configs 的模型发现，使用模拟 GET 响应。 | 待确认 |
| [`tests/backend/test_n01_n06.py`](backend/test_n01_n06.py) | 模型配置 revision 在清除重建后保持唯一，且约束问答缓存和测试结果写入。 | N01；N06；ADR-082 |
| [`tests/backend/test_n07_n08.py`](backend/test_n07_n08.py) | 凭据存储未启用时连接测试提前返回 503，空白模型名返回 422 且不出站。 | N07；N08 |
| [`tests/backend/test_relations_api.py`](backend/test_relations_api.py) | 课程关系增改删 API 的权限、前置成环检测、课程锁、审计与错误契约。 | F06；[specs/course-knowledge-graph.md](../specs/course-knowledge-graph.md)；F06-API；F12 |
| [`tests/backend/test_td02.py`](backend/test_td02.py) | 任务行读取 SQL 的仓储迁移、课程隔离、取消比较交换及层间依赖约束。 | TD-02；C10；D11 |
| [`tests/backend/test_teacher_embeddings.py`](backend/test_teacher_embeddings.py) | 教师嵌入模型配置的授权与真实响应维度校验。 | 待确认 |
| [`tests/backend/test_worker_graph_transaction.py`](backend/test_worker_graph_transaction.py) | worker 显式图事务的作用域、守卫校验及禁止回调重试。 | 待确认 |
| [`tests/backend/test_worker_persist_config.py`](backend/test_worker_persist_config.py) | `app.config` 的配置加载接口（具体配置范围待确认：无头部说明）。 | 待确认 |
| [`tests/backend/test_worker_persist_fence.py`](backend/test_worker_persist_fence.py) | 确定性的任务租约截止与跨存储提交防护。 | R1；ADR-093 |
| [`tests/backend/test_worker_persist_transport.py`](backend/test_worker_persist_transport.py) | `app.repositories.persist_transport` 的同步持久化传输接口。 | 待确认 |

## 前端

| 文件 | 被测模块或功能（一句话） | 对应规格 / ADR / 任务 ID |
| --- | --- | --- |
| [`tests/frontend/disambiguation-api.test.ts`](frontend/disambiguation-api.test.ts) | 消歧客户端参数、取消信号、冲突透传与审核原因兼容。 | ADR-100；DISAMBIG-BE-03 |
| [`tests/frontend/adr079.test.ts`](frontend/adr079.test.ts) | 学生自助注册页面与注册接口客户端。 | ADR-079 |
| [`tests/frontend/answer-card.test.ts`](frontend/answer-card.test.ts) | AnswerCard 单条回答的状态标签、下一步、复制与重试。 | UI-QA-01 |
| [`tests/frontend/app-graph-shell.test.ts`](frontend/app-graph-shell.test.ts) | App 中图谱与已升级课程页面的暗色外壳。 | 待确认 |
| [`tests/frontend/auth-graph-motion.test.ts`](frontend/auth-graph-motion.test.ts) | 认证页装饰图的运动逻辑。 | 待确认 |
| [`tests/frontend/b02.test.ts`](frontend/b02.test.ts) | 前端 Vitest 配置、全局 setup 与 npm test 退出码。 | B02 |
| [`tests/frontend/b03.test.ts`](frontend/b03.test.ts) | 应用路由外壳、角色入口与路由守卫提示。 | B03 |
| [`tests/frontend/b04.test.ts`](frontend/b04.test.ts) | 课程上下文 store。 | B04 |
| [`tests/frontend/b15.test.ts`](frontend/b15.test.ts) | HTTP 客户端的路径、请求响应、错误、认证、取消超时及课程作用域联动。 | B15；B04 |
| [`tests/frontend/c12.test.ts`](frontend/c12.test.ts) | 任务 SSE 的解析、事件运行时校验与订阅。 | C12 |
| [`tests/frontend/canvas-edit.test.ts`](frontend/canvas-edit.test.ts) | 画布直接操作的状态逻辑、编辑浮层组件，以及关系线点击、节点右键与节点位置的画布接线。 | UI-GRAPH-EDIT-02；specs/course-knowledge-graph.md |
| [`tests/frontend/chat-question-limit.test.ts`](frontend/chat-question-limit.test.ts) | 问答输入框与契约保持一致的 2000 字问题长度上限。 | M11/C2 |
| [`tests/frontend/chat-send-lock.test.ts`](frontend/chat-send-lock.test.ts) | 问答发送期间的逻辑层与页面防重复提交，并保留显式停止。 | 待确认 |
| [`tests/frontend/chat-sources.test.ts`](frontend/chat-sources.test.ts) | chatSources 的回答状态文字、当前回答出处与复制内容。 | UI-QA-01 |
| [`tests/frontend/chat-ui-qa.test.ts`](frontend/chat-ui-qa.test.ts) | 问答页当前回答的出处、状态与失败卡、复制及输入区结构。 | UI-QA-01 |
| [`tests/frontend/course-page-ui.test.ts`](frontend/course-page-ui.test.ts) | 课程页面的行列表与创建面板。 | 待确认 |
| [`tests/frontend/d1-d3.test.ts`](frontend/d1-d3.test.ts) | 前端问答故障分类，区分截断、链路超时与资料未覆盖。 | D1/D3；ADR-082 |
| [`tests/frontend/edit-history.test.ts`](frontend/edit-history.test.ts) | 撤销 / 重做的顺序、失败、快捷键、清空/释放代次与关系操作串行保护。 | UI-GRAPH-UNDO-04；specs/course-knowledge-graph.md |
| [`tests/frontend/graph-canvas-enhanced.test.ts`](frontend/graph-canvas-enhanced.test.ts) | GraphCanvas 增强模式与教师页沿用的普通模式。 | 待确认 |
| [`tests/frontend/graph-chapter-layout.test.ts`](frontend/graph-chapter-layout.test.ts) | 章节分区布局 computeLayout 的真实 dagre 引擎、边界、替换引擎与规模对比。 | 待确认 |
| [`tests/frontend/graph-detail-layout.test.ts`](frontend/graph-detail-layout.test.ts) | 知识点详情在不同场景中的关闭入口与自适应布局规则。 | 待确认 |
| [`tests/frontend/graph-direct-edit.test.ts`](frontend/graph-direct-edit.test.ts) | 成环预判与节点命中纯函数；学生预览卡“就此提问”与问答页预填。 | UI-GRAPH-EDIT-02 |
| [`tests/frontend/graph-enhancer.test.ts`](frontend/graph-enhancer.test.ts) | 图谱增强器的展示装饰、语义缩放、标签排布、视口适应、悬停与章节外框。 | 待确认 |
| [`tests/frontend/graph-find.test.ts`](frontend/graph-find.test.ts) | 图谱查找（高亮而非隐藏、别名、候选、逐个定位）、画布快捷键、学生页视图状态写入地址与面板宽度记忆。 | UI-GRAPH-FIND-01；specs/course-knowledge-graph.md |
| [`tests/frontend/graph-fit.test.ts`](frontend/graph-fit.test.ts) | 图谱范围适应 computeFit 与底部边距 bottomPad。 | 待确认 |
| [`tests/frontend/graph-focus-states.test.ts`](frontend/graph-focus-states.test.ts) | 图谱邻接查询、预览选中与章节搜索焦点、悬停淡化及标签优先级。 | 待确认 |
| [`tests/frontend/graph-label-plan.test.ts`](frontend/graph-label-plan.test.ts) | 图谱标签排布 planLabels。 | 待确认 |
| [`tests/frontend/graph-layout-composable.test.ts`](frontend/graph-layout-composable.test.ts) | useGraphLayout 图谱布局组合逻辑。 | 待确认 |
| [`tests/frontend/graph-lifecycle-enhance.test.ts`](frontend/graph-lifecycle-enhance.test.ts) | 增强图谱生命周期中的布局位置、数据事件、尺寸变化、视口与销毁。 | 待确认 |
| [`tests/frontend/graph-obstacles.test.ts`](frontend/graph-obstacles.test.ts) | 图谱遮挡区域注册 createObstacleRegistry 与 useGraphObstacle 组合逻辑。 | 待确认 |
| [`tests/frontend/graph-options.test.ts`](frontend/graph-options.test.ts) | buildGraphOptions 的图谱新主题配置。 | 待确认 |
| [`tests/frontend/graph-presentation.test.ts`](frontend/graph-presentation.test.ts) | 图谱节点与边的展示装饰、掌握状态、角标、章节和标签。 | 待确认 |
| [`tests/frontend/graph-radial-layout.test.ts`](frontend/graph-radial-layout.test.ts) | 径向布局引擎与默认推荐径向布局的判断。 | 待确认 |
| [`tests/frontend/graph-scale.test.ts`](frontend/graph-scale.test.ts) | 图谱屏幕尺寸下限 scaleFloors 与标签放大系数 labelScale。 | 待确认 |
| [`tests/frontend/graph-tab-stops.test.ts`](frontend/graph-tab-stops.test.ts) | 图谱画布退出 Tab 顺序的无障碍处理及生命周期接入。 | UI-QA-01 |
| [`tests/frontend/graph-theme.test.ts`](frontend/graph-theme.test.ts) | 图谱主题的 CSS token 与画布一致性、对比度、节点类型标记和字体。 | 待确认 |
| [`tests/frontend/graph-workbench-components.test.ts`](frontend/graph-workbench-components.test.ts) | 图谱工作台的浮层与展示组件。 | 待确认（原文仅写「任务 14」，未指明所属计划） |
| [`tests/frontend/h01.test.ts`](frontend/h01.test.ts) | 课程 API、列表状态、创建表单、切换课程与路由接入。 | H01 |
| [`tests/frontend/h02.test.ts`](frontend/h02.test.ts) | 课程资料 API、上传校验与进度、取消重试、删除和同章重复上传提示。 | H02；ADR-022；ADR-021；C05-4 |
| [`tests/frontend/h03.test.ts`](frontend/h03.test.ts) | 图谱适配器的四类边样式、方向、缺端点、课程隔离、稳定 ID 与输入保护。 | H03 |
| [`tests/frontend/h04.test.ts`](frontend/h04.test.ts) | 图谱生命周期的挂载、更新、尺寸变化、销毁、失败、节点点击及 GraphCanvas 组件。 | H04 |
| [`tests/frontend/h05.test.ts`](frontend/h05.test.ts) | 图谱筛选、节点图例、章节选项、布局切换及工具栏与画布联动。 | H05 |
| [`tests/frontend/h06.test.ts`](frontend/h06.test.ts) | 知识点详情 API、来源视图模型、迟到请求隔离与详情组件。 | H06 |
| [`tests/frontend/h07.test.ts`](frontend/h07.test.ts) | 节点编辑 API、表单差异、加载保存、修订冲突、锁定解锁、删除与组件交互。 | H07 |
| [`tests/frontend/h08.test.ts`](frontend/h08.test.ts) | 关系 API 与关系编辑器的选点、乐观更新、组件和分层约束。 | 待确认 |
| [`tests/frontend/h09.test.ts`](frontend/h09.test.ts) | 审核队列 API 与页面的加载空态、单项处理、重复合并、分页和迟到响应。 | 待确认 |
| [`tests/frontend/h10.test.ts`](frontend/h10.test.ts) | 图谱版本 API、版本面板与审核页集成。 | H10 |
| [`tests/frontend/h11.test.ts`](frontend/h11.test.ts) | 学生已发布图谱页面的 API、状态、图卡切换、卡片分页与键盘操作。 | H11 |
| [`tests/frontend/h12.test.ts`](frontend/h12.test.ts) | 课程成员 API、入口守卫、列表状态、添加移除学生与新版成员页布局。 | H12 |
| [`tests/frontend/h13.test.ts`](frontend/h13.test.ts) | 会话存储、令牌注入、401 处理与登录页面。 | H13 |
| [`tests/frontend/h14.test.ts`](frontend/h14.test.ts) | 教师草稿图谱的选中保护、详情联动、连边、布局和面板；历史写入/读回、切课隔离、部分成功、草稿与迟到回调保护。 | C05-1 |
| [`tests/frontend/home-topbar-nav.test.ts`](frontend/home-topbar-nav.test.ts) | 课程之外的课程列表与模型设置页移除侧栏，并在顶栏提供品牌和模型 API 入口。 | UI-PINE-01 |
| [`tests/frontend/i06.test.ts`](frontend/i06.test.ts) | 学习进度 API、掌握状态视觉与乐观标记、推荐解释和列表及切课隔离。 | I06 |
| [`tests/frontend/invite-code-api.test.ts`](frontend/invite-code-api.test.ts) | 邀请码契约 API 客户端。 | 待确认 |
| [`tests/frontend/invite-code-state.test.ts`](frontend/invite-code-state.test.ts) | 邀请码功能的异步边界。 | 待确认 |
| [`tests/frontend/invite-code-ui.test.ts`](frontend/invite-code-ui.test.ts) | 学生输码入课与教师邀请码面板。 | 待确认 |
| [`tests/frontend/j08.test.ts`](frontend/j08.test.ts) | 问答 fetch 流客户端的载荷校验、事件文法、开流、分片、终态与取消。 | J08 |
| [`tests/frontend/j09.test.ts`](frontend/j09.test.ts) | useChat 问答页状态组合逻辑。 | J09 |
| [`tests/frontend/l10.test.ts`](frontend/l10.test.ts) | 模型 API 设置页、未配置时的引导与关闭模型思考开关。 | L10；ADR-090 |
| [`tests/frontend/l11.test.ts`](frontend/l11.test.ts) | 节点选择器、基于选中知识点来源的新建节点与发布阻断原因。 | L11；L11-3；L11-4；ADR-035 |
| [`tests/frontend/l12.test.ts`](frontend/l12.test.ts) | 知识点与问答来源的文件名映射、查看器及长引用折叠规则。 | L12；R04；ADR-085；C05-2 |
| [`tests/frontend/l13-kp-link.test.ts`](frontend/l13-kp-link.test.ts) | 问答知识点链接跳转图谱、消费 kp 参数并保持课程和图谱版本一致。 | L13-4；R08 |
| [`tests/frontend/l13.test.ts`](frontend/l13.test.ts) | 图谱可读初始视口、搜索定位与高级筛选折叠。 | L13-1；L13-2；L13-3；R06 |
| [`tests/frontend/l14.test.ts`](frontend/l14.test.ts) | 学习路径计算、画布路径和焦点、推荐解释、视口保持及解锁节点定位。 | L14；R11；L14-1；L14-2；L14-3；C05-3 |
| [`tests/frontend/l15-creation-scope.test.ts`](frontend/l15-creation-scope.test.ts) | useCourses 与 useChat 组合逻辑模块相关测试；具体功能待确认。 | 待确认 |
| [`tests/frontend/l15.test.ts`](frontend/l15.test.ts) | 按课程角色展示侧栏、课程阶段和下一步、入课空态及不可信文本来源处理。 | [specs/identity-access.md](../specs/identity-access.md)；L15；R07；R09；R10；L15-1；L15-2；L15-3；L15-5 |
| [`tests/frontend/lazy-view.test.ts`](frontend/lazy-view.test.ts) | 路由页面按需加载。 | 待确认 |
| [`tests/frontend/local-view.test.ts`](frontend/local-view.test.ts) | useLocalView 局部图视图、知识点集合与图范围限制。 | 待确认 |
| [`tests/frontend/login-scrollbar-style.test.ts`](frontend/login-scrollbar-style.test.ts) | 登录页表单栏滚动条与页面溢出的样式约束。 | 待确认 |
| [`tests/frontend/merge-preview.test.ts`](frontend/merge-preview.test.ts) | 合并两个知识点前后局部图的前端推算（改接、去重、别名、相邻知识点上限）。 | UX-REVIEW-DEDUP-01；ADR-047 |
| [`tests/frontend/model-discovery.test.ts`](frontend/model-discovery.test.ts) | ModelSettingsView 模型设置页的服务商卡片式单选。 | UI-PINE-01 |
| [`tests/frontend/model-settings-ui.test.ts`](frontend/model-settings-ui.test.ts) | 模型设置页面的分区、可访问性与随账号角色变化的文案。 | 待确认 |
| [`tests/frontend/n03-n05.test.ts`](frontend/n03-n05.test.ts) | 模型运行状态的账号隔离、保存测试清除互斥以及测试对象与表单一致性。 | N03；N04；N05 |
| [`tests/frontend/nav-icons.test.ts`](frontend/nav-icons.test.ts) | 导航入口图标按去向保持唯一。 | 待确认 |
| [`tests/frontend/node-type-legend.test.ts`](frontend/node-type-legend.test.ts) | 教师图谱页节点类型图例组件。 | 待确认 |
| [`tests/frontend/node-deletion.test.ts`](frontend/node-deletion.test.ts) | 显式级联删除确认、预览迟到与切换隔离，以及冲突后重新确认。 | F09；ADR-097 |
| [`tests/frontend/plan-b-review.test.ts`](frontend/plan-b-review.test.ts) | KnowledgeDetail 与 useLearning 模块相关测试；具体功能待确认。 | 待确认 |
| [`tests/frontend/planCConfigTestRetry.test.ts`](frontend/planCConfigTestRetry.test.ts) | 本机 E2E 配置测试的共享限流窗口工具。 | 待确认 |
| [`tests/frontend/preview-focus.test.ts`](frontend/preview-focus.test.ts) | usePreviewFocus 预览焦点组合逻辑。 | 待确认 |
| [`tests/frontend/redesign-chat.test.ts`](frontend/redesign-chat.test.ts) | ChatView 问答页改版的展示行为。 | 待确认 |
| [`tests/frontend/register-layout.test.ts`](frontend/register-layout.test.ts) | 学生注册页外观、结构及与登录页版式的一致性。 | 待确认 |
| [`tests/frontend/resume-learning.test.ts`](frontend/resume-learning.test.ts) | 学生课程列表继续学习主卡的课程选择、进度推荐读取与失败隐藏。 | UI-PINE-01 |
| [`tests/frontend/review-dedup.test.ts`](frontend/review-dedup.test.ts) | 审核页疑似重复的并排对比组件与合并预览小图。 | UX-REVIEW-DEDUP-01；specs/teacher-review-publish.md |
| [`tests/frontend/source-counts.test.ts`](frontend/source-counts.test.ts) | 知识点来源数量的按需读取、缓存、失效与课程隔离。 | UX-REVIEW-DEDUP-01（DEDUP-FIX F2） |
| [`tests/frontend/student-graph-workbench.test.ts`](frontend/student-graph-workbench.test.ts) | 学生图谱工作台的预览详情、局部视图、图例筛选、章节聚焦、响应式面板与可访问性。 | 待确认 |
| [`tests/frontend/teacher-embedding-settings.test.ts`](frontend/teacher-embedding-settings.test.ts) | 教师模型设置页的向量设置可见性、表单与同名按钮区分。 | 待确认 |
| [`tests/frontend/toast-notice.test.ts`](frontend/toast-notice.test.ts) | ToastNotice 提示与自动消失逻辑，以及审核页固定弹窗避免布局位移的样式。 | 待确认 |
| [`tests/frontend/ui-batch2-styles.test.ts`](frontend/ui-batch2-styles.test.ts) | 教师图谱详情与资料上传框的样式回归。 | UI-BATCH2-01 |
| [`tests/frontend/ui-rollout-shell.test.ts`](frontend/ui-rollout-shell.test.ts) | 课程和模型设置页面的应用外壳推广范围。 | 待确认 |
| [`tests/frontend/use-copy-feedback.test.ts`](frontend/use-copy-feedback.test.ts) | useCopyFeedback 复制成功提示自动消失与失败提示保留。 | UI-QA-01 |
| [`tests/frontend/use-follow-latest.test.ts`](frontend/use-follow-latest.test.ts) | useFollowLatest 底部自动跟随、上翻保留阅读位置与回到最新提示。 | UI-QA-01 |

## 集成

| 文件 | 被测模块或功能（一句话） | 对应规格 / ADR / 任务 ID |
| --- | --- | --- |
| [`tests/integration/test_fusion_projection.py`](integration/test_fusion_projection.py) | 真实 Neo4j 独立草稿副本往返、幂等和事务回滚。 | ADR-099；DISAMBIG-BE-02 |
| [`tests/integration/test_disambiguation_review_api.py`](integration/test_disambiguation_review_api.py) | 真实 Neo4j 生成到审核/历史/HTTP 撤销闭环及教师编辑保护。 | ADR-100；DISAMBIG-BE-03 |
| [`tests/integration/test_fusion_pipeline.py`](integration/test_fusion_pipeline.py) | 真实 Neo4j 生成映射、T6 原子性、接管、跨任务、单组/独立组撤销与节点修订。 | ADR-099；DISAMBIG-BE-02 |
| [`tests/integration/test_extraction_window_fusion.py`](integration/test_extraction_window_fusion.py) | 真实 Neo4j 抽取缺口阻断合并、缓存失效及审核覆盖原因。 | ADR-101；DISAMBIG-BE-04 |
| [`tests/integration/test_d2_publish.py`](integration/test_d2_publish.py) | 验证发布时文本块与知识点向量调用的计费记录，以及重复发布和回滚复制向量不新增调用。 | D2；ADR-082 |
| [`tests/integration/test_demo_mode_live.py`](integration/test_demo_mode_live.py) | 验证演示模型上传到 worker 草稿生成的完整流程及 Neo4j 向量相似度阈值。 | ADR-076 |
| [`tests/integration/test_f01.py`](integration/test_f01.py) | 验证本地 Neo4j 环境的 Compose、dev-up 脚本与 APOC 检查。 | F01 |
| [`tests/integration/test_f03.py`](integration/test_f03.py) | 验证图数据库 schema 迁移与向量空间边界。 | F03 |
| [`tests/integration/test_f04.py`](integration/test_f04.py) | 验证草稿节点与来源批量写入的幂等性、教师锁保护及课程隔离。 | F04；[specs/task-processing.md](../specs/task-processing.md) §8.4；[specs/teacher-review-publish.md](../specs/teacher-review-publish.md)；ADR-011 修订 1 |
| [`tests/integration/test_f06.py`](integration/test_f06.py) | 验证草稿关系在同一事务与课程守卫锁下写入，并阻止并发写入形成环。 | F06；[specs/course-knowledge-graph.md](../specs/course-knowledge-graph.md)；[specs/task-processing.md](../specs/task-processing.md) §8.4；ADR-009；ADR-025 |
| [`tests/integration/test_f07_live.py`](integration/test_f07_live.py) | 验证真实 Neo4j 上 GraphReader 的草稿可见性与已发布版本副本查询。 | F07 |
| [`tests/integration/test_f08.py`](integration/test_f08.py) | 验证教师编辑的修订号条件更新、人工锁与贡献登记，以及自动写入对锁的遵守。 | F08；ADR-035 |
| [`tests/integration/test_f09.py`](integration/test_f09.py) | 验证删除草稿知识点仅清理同版本关系，保留发布快照并区分缺失、跨课与并发删除。 | F09；ADR-048 |
| [`tests/integration/test_f09_cascade.py`](integration/test_f09_cascade.py) | 真实 Neo4j 上的级联删除、共享节点与发布隔离、预览失效、回滚和并发确认。 | F09；ADR-097 |
| [`tests/integration/test_f10.py`](integration/test_f10.py) | 验证知识点合并的边迁移、去重、防环、来源保留与失败原子性。 | F10；ADR-047 |
| [`tests/integration/test_f12.py`](integration/test_f12.py) | 验证删除和合并的图编辑审计、事务失败记录与持锁对账补齐。 | F12；ADR-061；ADR-012 修订 3 |
| [`tests/integration/test_f13.py`](integration/test_f13.py) | 验证 worker 合并与持久化阶段的重试幂等、取消、部分失败、降级与清理。 | F13；[specs/task-processing.md](../specs/task-processing.md) §3、§8.4、§8.5；ADR-009；ADR-029 |
| [`tests/integration/test_f14.py`](integration/test_f14.py) | 验证离线重新向量化命令的停机约束、全量枚举、提交失败保护与回滚提示。 | F14；[specs/teacher-review-publish.md](../specs/teacher-review-publish.md) V12；PUB-39 |
| [`tests/integration/test_g03.py`](integration/test_g03.py) | 验证将快照物化为隔离且带向量的版本图，以及旧版本可读、向量校验与重试幂等。 | G03；[specs/teacher-review-publish.md](../specs/teacher-review-publish.md) V5 P8/P9；V12 |
| [`tests/integration/test_g04.py`](integration/test_g04.py) | 验证发布在 DAG 与来源校验后原子切换指针，失败保留旧指针并拒绝并发发布。 | G04；[specs/teacher-review-publish.md](../specs/teacher-review-publish.md) V5；PUB-1/2/4/5/6/12/21/22/23/35 |
| [`tests/integration/test_g05.py`](integration/test_g05.py) | 验证跨 SQLite/Neo4j 发布失败补偿及清理器的幂等性和可读版本保护。 | G05；[specs/teacher-review-publish.md](../specs/teacher-review-publish.md) V5 C1；V9；PUB-18/19/20 |
| [`tests/integration/test_g06.py`](integration/test_g06.py) | 验证历史版本回滚生成前滚版本、拒绝缺失或跨课版本并保留历史。 | G06；[specs/teacher-review-publish.md](../specs/teacher-review-publish.md) V6；PUB-3/7/15/16/25/26 |
| [`tests/integration/test_g08_backfill.py`](integration/test_g08_backfill.py) | 验证历史已提交版本的文本块向量回填、空间不匹配拒绝与 dry-run 不调用模型。 | G08；ADR-066；V12（规格路径待确认） |
| [`tests/integration/test_g08.py`](integration/test_g08.py) | 验证发布为版本内所有文本块建立当前空间向量索引，跳过已有索引并在失败时保留旧指针。 | G08；ADR-066；V5 P8/P9（规格路径待确认） |
| [`tests/integration/test_j01.py`](integration/test_j01.py) | 验证已发布版本的文本块向量检索按课程和修订列表隔离，并补取候选填满召回。 | J01；[specs/teacher-review-publish.md](../specs/teacher-review-publish.md) V8；[specs/grounded-qa.md](../specs/grounded-qa.md) Q3.1；ADR-046 |
| [`tests/integration/test_j02.py`](integration/test_j02.py) | 验证单一已发布版本的结构检索限制跳数和节点数，隔离草稿、其他版本与课程。 | J02；[specs/grounded-qa.md](../specs/grounded-qa.md) Q1；Q8 H4；ADR-050 |
| [`tests/integration/test_k08.py`](integration/test_k08.py) | 验证后端、前端和 worker 容器配置、镜像文件布局及 worker 启动、心跳与停止处理。 | K08；A06 §8.1 |
| [`tests/integration/test_k09.py`](integration/test_k09.py) | 验证演示导入通过真实 worker 与发布流程运行，重复导入不改变结果。 | K09 |
| [`tests/integration/test_k10.py`](integration/test_k10.py) | 验证备份写入栅栏与发布指针一致性，以及隔离恢复、引用核验和覆盖保护。 | K10；ADR-054 |
| [`tests/integration/test_relations_api.py`](integration/test_relations_api.py) | 验证真实 Neo4j/SQLite 上关系 API 的身份、锁内防环、来源、删除和读回响应。 | F06；ADR-071 |
| [`tests/integration/test_worker_persist_fence.py`](integration/test_worker_persist_fence.py) | 验证真实 Neo4j 提交与回滚，以及公共事务边界注入故障时的持久化行为。 | ADR-093 |
| [`tests/integration/test_worker_persist_transport.py`](integration/test_worker_persist_transport.py) | 验证 worker 持久化链路在真实 Bolt 传输故障下的行为。 | 待确认 |

