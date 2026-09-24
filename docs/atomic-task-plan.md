# SmartSketch 单轮可执行原子任务清单

共 **141 个叶子任务**，其中 **133 个主线任务、8 个条件性加分任务**。这是实施计划，不是已完成列表，也不承诺 AI 自动保证正确。每次只选一个依赖已验收的叶子任务；用负例、真实命令、人工决策和独立审查形成可靠性边界。机器可读版见 [atomic-tasks.json](atomic-tasks.json)。

## 使用规则

1. 本清单所有项初始为 **PROPOSED / 未认领**；原任务 M0/M1 是父任务，下面是叶子任务，编号不覆盖分支中已有的 M0-04a/S-06。认领时在主任务板写 ID、负责人、目标 worktree/HEAD 与文件锁。不要一次认领整组。
2. 一轮通常只实现一个函数、一个小服务、一种解析格式、一个 UI 交互或一项契约迁移。目标为约 30–90 分钟的可测工作量，不是完成时限承诺；若需要改变第二项领域规则、超过约 6 个手写功能文件、等待外部决策或复杂迁移，先细分为 a/b 子项。B01 初始化工具产生的锁文件/模板和 B14 生成物除外，仍不得夹带业务。
3. **A01 是路线门**：ADR-004 已选 YAML-first：`src/contracts/api.v1.yaml` 是唯一人工编辑的机器可读契约；B08～B14/O02/O05 先改真源，再用脚本生成 `src/contracts/v1/generated/`，不得手写生成物。批 1 导入真源与生成链后才能执行这些契约任务。模型预算、快照存储、登录、worker 等同理先决策再实现。
4. 表内给的是允许编辑的功能文件；每项另允许自己的测试、对应规格的本任务段落、任务板状态和自己的交接文件。共享文件一次一个写入者。完整白名单在 JSON，范围改变须记录，不通过宽泛目录授权顺手重构。
5. 每项最终都须在当前 checkout 或已记录的目标 worktree 运行 `./scripts/verify.sh`、`git diff --check` 和表内单项命令，记录退出码与 PASS/SKIP。表内测试路径和 npm 命令是**待创建的验收契约**，当前骨架未具备这些测试，绝非已经跑通。
6. 前端统一命令由 B02 建立并保证发现外层 tests/frontend；后端 pytest 配置由 B05 建立；集成夹具由对应首个 integration 任务建立；E2E 脚本/配置在 K05 建立，若环境适配超出单轮就先拆 K05a。使用测试假模型；真实服务/付费调用、依赖安装按环境审批，不暗中做。
7. 完成证据 = 可运行成果 + 至少成功/边界/失败各一例 + 所有依赖版本 + 实际命令结果 + 交接。仅文档任务用可核查决策表/映射表验收，未签收决定不得写成确定结论。无人拍板不妨碍不依赖该决定的其他任务。
8. 更新 `docs/handoffs/<agent>-<id>.md`：task_id、worktree、base/head、范围、测试结果、待定/风险、首个后续动作；如需审查，添加 ready_for_review 与固定提交或 dirty 指纹。一次任务完成不自动提交、合并或宣称父里程碑完成。
9. 回滚：只恢复自己触碰的功能；数据库/依赖变更提供先备份后定向恢复步骤。禁止以删测试或 reset 他人改动实现“通过”。

## 阶段和原任务映射

| 原父任务/范围 | 叶子任务组 | 说明 |
| --- | --- | --- |
| M0-02 前端骨架 | B01～B04、B15 | UI 与测试各自单轮 |
| M0-03 后端骨架 | B05～B06 | 身份决定不应阻塞无状态 health |
| M0-04 共享契约 | A01～A03、B07～B14 | 先解决两个分支冲突，再复用现有契约 |
| M0-05 开发环境 | F01、K07 | 配置文件存在不等于容器验收通过 |
| M1-01 上传与课程 | C01～C16 | 身份、文件、事务、队列、SSE 分开；C13～C16 补齐登录、账号、成员和票据 |
| M1-02 解析分块 | D01～D11 | 四种格式独立测，避免一个任务包办 |
| M1-03 抽取融合 | E01～E12、F04、F13～F14 | fake 接口先行，模型真实效果另评测 |
| M1-04 DAG | F05～F06 | 纯函数和数据库并发分别验收 |
| M1-05 教师审核发布 | F07～F12、G01～G07、H07～H10 | 服务、快照、补偿、UI 顺序交接 |
| main 尚缺的学生端主线 | H11～H12、I01～I06、J01～J10 | 属现有 MVP，不当新增加分范围 |
| S2 M3/M4 交付 | K01～K19 | 回归、实测、部署、数据恢复、消融和参赛材料 |
| 可选范围 | O01～O08 | 未批准不执行；不挤占主线 |

## A10 批 0 清单缺口处理

| 缺口 | 承接任务 | 说明 |
| --- | --- | --- |
| G-1 本地身份与成员 | C13～C16、H12、H13 | 登录、账号命令、成员 API/页面、前端登录与会话（H13，D-09 补登）与 SSE 票据分开验收 |
| G-2 离线重新向量化 | F14 | 按 ADR-012 修订 1 对存量草稿和已提交版本核对 |
| G-3 消融实验 | K13 | 三种抽取阶段配置使用同一标注集 |
| G-4 参赛材料与合规 | K14～K19 | 提示词、图谱示例、S2、S1/PPT/视频、S5、合规分别交付 |
| G-5 `event_tickets` 命名基线 | A10 批 5 | 属已签收命名文档对齐，无需新实现任务 |
| G-6 身份环境变量 | C13 | 在登录实现中补 `.env.example`、`docs/integrations.md` 与启动校验 |

## 推荐调度顺序

先 A01 确认契约方向，A02/A03 同步术语，A10 记录每批导入计划；继而 B01/B05 骨架，再按依赖图取可执行项。F05 纯 DAG、解析器等可在其依赖就绪后独立执行，但本次未启动其他 Agent。A10 不是要求把两个分支一次性合并。

下表输入→输出写明单一完成物；“验收/负例”是该轮停止条件。所有代码任务同时承担表内测试文件（JSON 白名单已列出）。JSON 中的旧绝对路径以仓库根目录为逻辑前缀，执行时映射到当前 checkout，不能当作本机固定路径。

## A 决策与基线对齐（10 项）

| ID 与单轮任务 | 依赖 | 输入 → 输出 | 功能文件范围 | 验收与负例 | 单项命令 |
| --- | --- | --- | --- | --- | --- |
| **A01 裁决契约唯一来源与 ADR 编号** | 无 | 两个分支契约决定 → 一条生成方向及迁移映射 | `docs/decisions.md`<br>`docs/architecture.md` | 明确真源、生成物、写入方；原有每个端点有迁移去向，不擅自删功能 | `git diff --check；逐条核对 A01 验收矩阵与源文档，人工决策保留未签收标记` |
| **A02 统一路径前缀和领域枚举** | A01 | 现有 YAML/状态规格 → API 前缀与 wire 枚举表 | `specs/course-knowledge-graph.md`<br>`docs/architecture.md` | 同步 persisting/cancelled/未覆盖大小写；人工编辑造环与自动候选降级区别明确 | `git diff --check；逐条核对 A02 验收矩阵与源文档，人工决策保留未签收标记` |
| **A03 定义任务生命周期和取消协议** | A02 | 现有 SSE 时序 → 状态转换表与取消竞争语义 | `specs/task-processing.md` | 区分处理完成和人工审核完成；定义部分失败、取消请求/取消完成、重复取消与重连 | `git diff --check；逐条核对 A03 验收矩阵与源文档，人工决策保留未签收标记` |
| **A04 定义图谱版本和跨库发布协议** | A01 | S2 快照表/双库存储 → version_id、快照位置、发布步骤 | `specs/teacher-review-publish.md`<br>`docs/architecture.md` | 定义图/向量读版本、指针切换、失败补偿、回滚编号；决策前不写仓储 | `git diff --check；逐条核对 A04 验收矩阵与源文档，人工决策保留未签收标记` |
| **A05 定义课程成员与本地身份边界** | A01 | 两个分支登录决定 → 身份、成员、角色访问矩阵 | `specs/identity-access.md`<br>`docs/decisions.md` | 明确演示角色或账号模式；禁止仅相信请求 user_id；不扩展生产 SSO | `git diff --check；逐条核对 A05 验收矩阵与源文档，人工决策保留未签收标记` |
| **A06 定义 worker 租约和幂等机制** | A03 | 任务生命周期 → 原子领取、超时接管、阶段重试规则 | `specs/task-processing.md`<br>`docs/decisions.md` | 明确单机/多进程边界、重试上限与去重；迁移前有备份/回滚说明 | `git diff --check；逐条核对 A06 验收矩阵与源文档，人工决策保留未签收标记` |
| **A07 落实模型配置形状与预算决策入口** | A01 | S2 主备与向量方案 → 配置名/类型/切换矩阵 | `docs/integrations.md`<br>`.env.example` | 包括 embedding 维度、模型版本、超时/限并发/预算；真实值由负责人确认，不写密钥 | `git diff --check；逐条核对 A07 验收矩阵与源文档，人工决策保留未签收标记` |
| **A08 定义推荐评分与进度跨版本规则** | A04 | S2 四项公式 → 完整纯函数规格 | `specs/learning-path.md` | 定义实际解锁数、归一化零分母、同分键、空态、节点删除/改名及人工跳过先修 | `git diff --check；逐条核对 A08 验收矩阵与源文档，人工决策保留未签收标记` |
| **A09 定义问答终态和引用撤回协议** | A02, A04 | R03/R04 与 S2 → 流式状态/正文/引用结构 | `specs/grounded-qa.md` | answered 必有定位来源；临时正文失败后清除；空检索不调用生成；与未知引用区分 | `git diff --check；逐条核对 A09 验收矩阵与源文档，人工决策保留未签收标记` |
| **A10 整理已有成果导入顺序与任务映射** | A01, A02, A03, A04, A05 | 两个 worktree diff → 分文件复用/冲突/补测列表 | `docs/tasks.md`<br>`docs/reviews/branch-integration-map.md` | 不自动 merge；明确 ADR/S-06 编号冲突、每批最多一个功能边界、决策签收人 | `git diff --check；逐条核对 A10 验收矩阵与源文档，人工决策保留未签收标记` |

## B 应用骨架与契约（15 项）

| ID 与单轮任务 | 依赖 | 输入 → 输出 | 功能文件范围 | 验收与负例 | 单项命令 |
| --- | --- | --- | --- | --- | --- |
| **B01 初始化前端构建和单个挂载页面** | A01 | Vue/Vite 约定 → 可构建空应用 | `src/frontend/package.json`<br>`src/frontend/tsconfig.json`<br>`src/frontend/vite.config.ts`<br>`src/frontend/index.html`<br>`src/frontend/src/main.ts`<br>`src/frontend/src/App.vue` | 锁定依赖；挂载烟测和 type-check/build 成功，无业务页面 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run build；浏览器挂载烟测，正式测试脚本由 B02 建立` |
| **B02 初始化前端测试配置** | B01 | 空应用 → tests/frontend 可被实际发现 | `src/frontend/vitest.config.ts`<br>`src/frontend/package.json` | 包含仓库外层 tests/frontend；故意失败用例使命令非 0；不是零用例通过 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/b02.test.ts` |
| **B03 建立路由壳和角色入口** | B02, A05 | 身份访问矩阵 → 教师/学生空路由 | `src/frontend/src/router/index.ts`<br>`src/frontend/src/views/TeacherHome.vue`<br>`src/frontend/src/views/StudentHome.vue` | 直接进入错误角色页有提示；不将前端路由判断当后端鉴权 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/b03.test.ts` |
| **B04 建立 Pinia 课程上下文** | B02 | 课程 ID 切换 → 状态清理和请求作用域 | `src/frontend/src/stores/course.ts` | 切课清除旧图/问答，晚到响应不覆盖新课；无请求写入组件 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/b04.test.ts` |
| **B05 初始化后端应用工厂与 health** | A01 | FastAPI 约定 → health 路由与响应 | `src/backend/pyproject.toml`<br>`src/backend/app/main.py`<br>`src/backend/app/api/health.py` | 无密钥可测 GET /health；测试 app 工厂不触发网络连接 | `python3 -m pytest tests/backend/test_b05.py -q` |
| **B06 建立后端设置加载与验证** | B05, A07 | 环境变量表 → 类型化 settings | `src/backend/app/config.py` | 非法端口/预算/维度显式错误；缺真实模型配置时 fake 模式可测；日志无密钥 | `python3 -m pytest tests/backend/test_b06.py -q` |
| **B07 修复校验缺依赖假绿** | A01, B05 | R02 与分支门禁 → 显式 PASS/SKIP/FAIL | `scripts/check_contracts.py`<br>`scripts/verify/contracts.sh`<br>`src/backend/pyproject.toml` | 缺依赖、坏引用、坏枚举非 0；骨架跳过显式标注；在选定基线落地，不保留双门禁 | `python3 -m pytest tests/tooling/test_b07.py -q` |
| **B08 迁移公共错误和来源契约** | A01, A02, B05 | 已有错误/SourceRef → 选定真源公共类型 | `src/contracts/api.v1.yaml`<br>`src/contracts/errors.v1.md`<br>`src/contracts/v1/generated/` | page 正整数或 section 非空；4 类关系闭集；错误码与未覆盖领域状态分开；重新生成 | `python3 -m pytest tests/contracts/test_b08.py -q` |
| **B09 迁移课程与资料 REST 契约** | B08, A05 | 现有课程/文档端点 → DTO 和路径声明 | `src/contracts/api.v1.yaml`<br>`src/contracts/v1/generated/` | 列表/创建/上传/读取有成功与失败响应；不从零重写已有字段；重新生成 | `python3 -m pytest tests/contracts/test_b09.py -q` |
| **B10 迁移任务与 SSE 契约** | B08, A03 | 任务转换表 → 判别事件 DTO | `src/contracts/api.v1.yaml`<br>`src/contracts/events.v1.md`<br>`src/contracts/v1/generated/` | 每种事件必填字段不同；空 payload 拒绝；取消请求和终态区别正确；重新生成 | `python3 -m pytest tests/contracts/test_b10.py -q` |
| **B11 迁移图谱编辑和版本契约** | B08, A04 | 现有图节点关系接口 → 作用域/修订号 DTO | `src/contracts/api.v1.yaml`<br>`src/contracts/v1/generated/` | 跨版本标识齐全；编辑携带 expected_revision；端点与来源校验负例；重新生成 | `python3 -m pytest tests/contracts/test_b11.py -q` |
| **B12 迁移进度和推荐契约** | B08, A08 | 进度/推荐规格 → DTO | `src/contracts/api.v1.yaml`<br>`src/contracts/v1/generated/` | 区分未发布错误与全部掌握空态；已提交空图按发布快照完整性故障处理，不增加 `no_graph` wire 状态；未舍入 double 分量按 `u→i→c→e` 求和逐位等于评分，仅展示舍入；重新生成 | `python3 -m pytest tests/contracts/test_b12.py -q` |
| **B13 迁移问答与事件契约** | B08, A09 | R03/R04 → 响应判别联合 | `src/contracts/api.v1.yaml`<br>`src/contracts/events.v1.md`<br>`src/contracts/v1/generated/` | answered 空引用拒绝、无定位拒绝、空事件拒绝；最终替换正文有字段；重新生成 | `python3 -m pytest tests/contracts/test_b13.py -q` |
| **B14 建立契约导出与漂移检查** | B09, B10, B11, B12, B13 | 选定真源 → OpenAPI/Schema/TS 生成物 | `src/contracts/api.v1.yaml`<br>`scripts/gen-contracts.sh`<br>`scripts/gen_contracts.py`<br>`src/contracts/v1/generated/` | 两次输出一致；只检查模式不改工作文件；临时篡改生成物必被检出；重新生成 | `python3 -m pytest tests/contracts/test_b14.py -q` |
| **B15 建立前端 HTTP 客户端** | B02, B14 | 生成 TS 契约 → 请求封装 | `src/frontend/src/api/http.ts` | 类型化错误、超时/取消、认证失败处理；组件不自行拼路径 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/b15.test.ts` |

## C 课程资料与持久任务（16 项）

| ID 与单轮任务 | 依赖 | 输入 → 输出 | 功能文件范围 | 验收与负例 | 单项命令 |
| --- | --- | --- | --- | --- | --- |
| **C01 建立 SQLite 连接和迁移运行器** | B06, A04, A06 | 业务模型决定 → 连接/迁移版本表 | `src/backend/app/repositories/sqlite.py`<br>`src/backend/migrations/001_base.sql` | 临时数据库迁移可重复；事务回滚；备份后恢复命令可验证 | `python3 -m pytest tests/backend/test_c01.py -q` |
| **C02 实现课程和成员仓储** | C01, A05 | 课程/成员字段 → scoped CRUD | `src/backend/app/repositories/courses.py`<br>`src/backend/migrations/002_courses.sql` | 课程成员唯一；同用户不同课程角色独立；读写外键正确 | `python3 -m pytest tests/backend/test_c02.py -q` |
| **C03 实现身份边界与课程访问依赖** | C02, B09, C13 | 访问矩阵 → 身份/权限依赖与服务 | `src/backend/app/api/dependencies.py`<br>`src/backend/app/services/access.py` | 伪造 user_id、非成员、学生编辑均拒绝；按 A05 决定接入身份，不自行选登录方案 | `python3 -m pytest tests/backend/test_c03.py -q` |
| **C04 实现课程列表和创建 API** | C03 | 课程仓储 → 两个薄路由 | `src/backend/app/api/courses.py`<br>`src/backend/app/services/courses.py` | 仅列可访问课程；创建者成员写入同事务；无业务 SQL 留在路由 | `python3 -m pytest tests/backend/test_c04.py -q` |
| **C05 实现文件落盘边界** | B06 | 上传字节流 → 文件元数据 | `src/backend/app/services/file_storage.py` | 路径穿越、伪扩展名、超限/中断流失败且无半文件；生成随机存储名 | `python3 -m pytest tests/backend/test_c05.py -q` |
| **C06 实现资料和任务创建事务** | C01, B10 | 合法文件元数据 → material + queued task | `src/backend/app/repositories/materials.py`<br>`src/backend/app/repositories/tasks.py`<br>`src/backend/migrations/003_tasks.sql` | 数据库写入失败不留孤儿记录；重复请求的幂等键按课程隔离 | `python3 -m pytest tests/backend/test_c06.py -q` |
| **C07 实现上传及资料列表 API** | C03, C05, C06, B09 | 上传请求 → task_id/资料列表 | `src/backend/app/api/materials.py`<br>`src/backend/app/services/materials.py` | 非法格式/课程越权拒绝；存盘或建任务失败可补偿；长处理不堵请求 | `python3 -m pytest tests/backend/test_c07.py -q` |
| **C08 实现状态迁移纯函数** | A03, B10 | 当前状态 + 事件 → 新状态 | `src/backend/app/services/task_state.py` | 所有合法边覆盖；非法跳转、进度倒退、终态再写失败 | `python3 -m pytest tests/backend/test_c08.py -q` |
| **C09 实现 worker 原子领取与租约** | C06, C08, A06 | queued/过期任务 → 单 worker 所有权 | `src/backend/app/repositories/task_leases.py` | 两个连接争同任务只有一个成功；旧租约 token 禁止续写；到期可接管 | `python3 -m pytest tests/backend/test_c09.py -q` |
| **C10 实现任务取消服务与 API** | C09, C03 | 取消请求 → 持久取消意图/终态 | `src/backend/app/services/task_cancel.py`<br>`src/backend/app/api/task_cancel.py` | queued/运行中/完成后/重复取消；取消和写入竞争有确定结果 | `python3 -m pytest tests/backend/test_c10.py -q` |
| **C11 实现任务查询与 GET SSE** | C08, C03, B10, C16 | task 状态 → 快照/心跳/终态流 | `src/backend/app/api/tasks.py`<br>`src/backend/app/services/task_events.py` | 先验证课程权限；重连快照；终态关闭；断开释放监听器 | `python3 -m pytest tests/backend/test_c11.py -q` |
| **C12 实现前端任务流客户端** | B15, C11 | SSE 字节 → 任务状态订阅 | `src/frontend/src/api/taskEvents.ts` | 分片帧/CRLF/心跳/重连；终态和卸载关闭；旧课程事件不污染当前课 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/c12.test.ts` |
| **C13 实现本地账号登录与访问令牌签发** | C01, B09, B06, A05 | 账号与口令 → 经过校验的 Bearer 令牌 | `src/backend/app/api/auth.py`<br>`src/backend/app/services/auth.py`<br>`src/backend/app/repositories/accounts.py`<br>`src/backend/migrations/008_accounts.sql`<br>`src/backend/app/config.py`<br>`.env.example`<br>`docs/integrations.md` | 正确口令可登录；错口令、停用账号、超过 5 次/60 秒拒绝；密钥只读环境变量且迁移可恢复 | `python3 -m pytest tests/backend/test_c13.py -q` |
| **C14 实现账号管理命令与演示账号种子** | C13 | 本地账号管理决定 → 可重复执行的账号命令与演示种子 | `scripts/manage-accounts.py`<br>`scripts/seed-demo-accounts.py` | 创建/停用可复查；重复种子不重复；缺 SEED_DEMO_PASSWORD 非 0；不提交真实口令 | `python3 -m pytest tests/backend/test_c14.py -q` |
| **C15 实现课程成员管理 API** | C03, C04, B09 | 教师成员管理请求 → 列出、添加、移除成员 | `src/backend/app/api/members.py`<br>`src/backend/app/services/members.py` | 仅课程教师可改；重复添加幂等且不降级教师；跨课与非成员拒绝 | `python3 -m pytest tests/backend/test_c15.py -q` |
| **C16 实现 SSE 一次性票据申领** | C03, C06, B10 | 已授权的任务请求 → 一次性且绑定任务的事件票据 | `src/backend/app/api/event_tickets.py`<br>`src/backend/app/repositories/event_tickets.py`<br>`src/backend/migrations/009_event_tickets.sql` | 仅保存票据哈希；60 秒过期；重复、跨任务或普通 Bearer 查询票据拒绝；迁移可恢复 | `python3 -m pytest tests/backend/test_c16.py -q` |

## D 解析与分块（11 项）

| ID 与单轮任务 | 依赖 | 输入 → 输出 | 功能文件范围 | 验收与负例 | 单项命令 |
| --- | --- | --- | --- | --- | --- |
| **D01 定义解析输出与自编 fixture** | B08 | 四格式定位需求 → ParsedBlock/来源规则 | `src/backend/app/services/parsers/models.py` | 无页码格式用章节/段落；fixtures 自编不含真实课程和个人资料 | `python3 -m pytest tests/backend/test_d01.py -q` |
| **D02 实现 TXT 编码与标题解析** | D01 | UTF-8/GBK 文本 → 定位段落 | `src/backend/app/services/parsers/txt.py` | 空文、坏编码、无标题、中文编号标题；保留行号和章节 | `python3 -m pytest tests/backend/test_d02.py -q` |
| **D03 实现 Markdown AST 解析** | D01 | Markdown → 标题路径/段落块 | `src/backend/app/services/parsers/markdown.py` | 代码块中的 # 不当标题；表格/列表保留；空文有明确结果 | `python3 -m pytest tests/backend/test_d03.py -q` |
| **D04 实现 DOCX 段落和表格解析** | D01 | 自编 DOCX → 章节/段落来源 | `src/backend/app/services/parsers/docx.py` | 标题样式、表格、损坏 zip；避免编造页码；嵌入内容有范围说明 | `python3 -m pytest tests/backend/test_d04.py -q` |
| **D05 实现 PDF 正文与页码提取** | D01 | 文本 PDF → 分页文本行 | `src/backend/app/services/parsers/pdf.py` | 多页、空白、加密、损坏及扫描件明确返回状态；不声称已有 OCR | `python3 -m pytest tests/backend/test_d05.py -q` |
| **D06 实现 PDF 标题判定** | D05 | 行字号/字重/正则 → 章节树 | `src/backend/app/services/parsers/pdf_headings.py` | 正文加粗不误做所有标题；标题跨页、无字号层级有退路 | `python3 -m pytest tests/backend/test_d06.py -q` |
| **D07 实现重复页眉页脚清洗** | D05 | 分页行 → 清洗文本与位置映射 | `src/backend/app/services/parsers/cleanup.py` | 重复正文不被误删；删除页码不丢原始页定位；支持关掉清洗 | `python3 -m pytest tests/backend/test_d07.py -q` |
| **D08 实现章节内语义分块** | D02, D03, D04, D06, D07 | 定位段落 → 约1500字/200重叠块 | `src/backend/app/services/chunking.py` | 跨章不混、超长句/段、空输入；来源映射可回到原文 | `python3 -m pytest tests/backend/test_d08.py -q` |
| **D09 实现块身份与缓存键** | D08, A07 | 块内容/出处/版本 → 身份与抽取缓存键 | `src/backend/app/services/chunk_identity.py` | 同文不同页有独立出处；跨课程不复用身份；提示词/模型变更失效 | `python3 -m pytest tests/backend/test_d09.py -q` |
| **D10 实现来源块持久化** | D09, C01 | 定位块 → 可查询 Chunk | `src/backend/app/repositories/chunks.py`<br>`src/backend/migrations/004_chunks.sql` | 重复重试不重复写；按课程/文档定位；删除资料策略不破坏已发布引用 | `python3 -m pytest tests/backend/test_d10.py -q` |
| **D11 实现解析阶段 worker 编排** | C09, C10, D10 | 已领取任务 → parsing 完成检查点 | `src/backend/app/workers/parse_task.py` | 解析失败/取消/重启均落状态；只做解析阶段不顺手接真实 LLM | `python3 -m pytest tests/backend/test_d11.py -q` |

## E 模型抽取与融合（12 项）

| ID 与单轮任务 | 依赖 | 输入 → 输出 | 功能文件范围 | 验收与负例 | 单项命令 |
| --- | --- | --- | --- | --- | --- |
| **E01 建立版本化提示词装载器** | A07, B06 | 模板与变量 → 可追踪 prompt | `src/backend/app/services/ai/prompts.py`<br>`prompts/MANIFEST.md` | 缺变量/未知版本报错；记录模板摘要；8 类清单统一 evaluation/evals 命名 | `python3 -m pytest tests/backend/test_e01.py -q` |
| **E02 建立模型接口和 fake 适配器** | E01 | 抽取/对话请求 → 统一结果结构 | `src/backend/app/services/ai/client.py`<br>`src/backend/app/services/ai/fake.py` | 固定输入输出可复现；超时/坏 JSON/限流可模拟；无需密钥 | `python3 -m pytest tests/backend/test_e02.py -q` |
| **E03 实现兼容 API 适配器** | E02 | A07 接入配置 → HTTP 模型调用 | `src/backend/app/services/ai/compatible.py` | 先核对选定供应商官方协议；用 mock transport 测超时/错误/结构；真实调用需另行配置 | `python3 -m pytest tests/backend/test_e03.py -q` |
| **E04 实现模型调用预算与退避** | E03, C01 | 请求/额度 → 有界重试和熔断 | `src/backend/app/services/ai/policy.py`<br>`src/backend/app/repositories/model_calls.py` | 429/5xx 有界退避，鉴权错误不重试；预算零不发请求；日志无 token/原文 | `python3 -m pytest tests/backend/test_e04.py -q` |
| **E05 实现块级实体抽取** | E02, D09 | chunk → 有来源的规范实体候选 | `src/backend/app/services/ai/entities.py`<br>`prompts/extract_entities.yaml` | 五类实体、字段范围、证据必须来自输入；坏 JSON 修复最多一次 | `python3 -m pytest tests/backend/test_e05.py -q` |
| **E06 实现补漏实体抽取** | E05 | 原块/首轮实体 → 遗漏实体差量 | `src/backend/app/services/ai/gleaning.py`<br>`prompts/extract_entities_gleaning.yaml` | 不开启时零调用；只加遗漏不复制已有实体；预算和轮数有上限 | `python3 -m pytest tests/backend/test_e06.py -q` |
| **E07 实现向量适配与维度检查** | E02, A07 | 文本批次 → 带模型版本的向量 | `src/backend/app/services/ai/embeddings.py` | 维度不符、空批次、部分失败明确；在线/本地切换可 fake 验证 | `python3 -m pytest tests/backend/test_e07.py -q` |
| **E08 实现名称归一和重复候选** | E05 | 实体名称/定义 → 归一键与候选对 | `src/backend/app/services/fusion/normalize.py` | 全半角/空格/括号处理；名称包含只列候选，误合并反例保留 | `python3 -m pytest tests/backend/test_e08.py -q` |
| **E09 实现向量候选分层** | E07, E08 | 相似度/阈值 → 自动/裁决/保留三组 | `src/backend/app/services/fusion/candidates.py` | 课程隔离；阈值顺序非法拒绝；边界等号有明确规则 | `python3 -m pytest tests/backend/test_e09.py -q` |
| **E10 实现重复裁决与定义归并** | E09, E04 | 候选对/证据 → 同义判断与统一定义 | `src/backend/app/services/fusion/judge.py`<br>`prompts/judge_duplicate.yaml`<br>`prompts/summarize_definition.yaml` | 裁决有理由；定义仅用证据；假同义/坏输出保持独立并进入审核 | `python3 -m pytest tests/backend/test_e10.py -q` |
| **E11 实现关系两阶段抽取** | E10, E05 | 小节实体 ID 表 + 来源块 → 四类关系候选 | `src/backend/app/services/ai/relations.py`<br>`prompts/extract_relations.yaml` | 悬空端点/跨课/自环/重复边拦截；仅提及不判前置；方向反例 | `python3 -m pytest tests/backend/test_e11.py -q` |
| **E12 实现抽取阶段编排和检查点** | D11, E04, E11 | 解析检查点 → 待持久化候选 | `src/backend/app/workers/extract_task.py` | 每块失败可局部重试；并发上限；取消边界；重跑不重复扣计/污染来源 | `python3 -m pytest tests/backend/test_e12.py -q` |

## F 图存储与教师编辑（14 项）

| ID 与单轮任务 | 依赖 | 输入 → 输出 | 功能文件范围 | 验收与负例 | 单项命令 |
| --- | --- | --- | --- | --- | --- |
| **F01 复用本地 Neo4j 环境并验证** | A10 | 分支 Compose/脚本 → 可启动依赖 | `docker-compose.yml`<br>`scripts/dev-up.sh`<br>`scripts/check-apoc.sh` | 先审原脚本；配置检查、健康检查、停启数据仍在；真实容器命令需环境满足 | `python3 -m pytest tests/integration/test_f01.py -q` |
| **F02 实现 Neo4j 驱动与作用域仓储** | F01, B06, A04 | 连接设置 → 参数化图查询入口 | `src/backend/app/repositories/neo4j.py` | 所有业务 query 接收 course/version；断线明确错误；不把凭据写日志 | `python3 -m pytest tests/backend/test_f02.py -q` |
| **F03 建立图唯一约束和索引迁移** | F02, B11 | 图模型 → 可重复执行迁移 | `src/backend/migrations/neo4j/001_constraints.cypher`<br>`src/backend/app/repositories/graph_migrations.py` | 同作用域 ID 唯一；版本不同可共存；迁移失败有回滚/修复说明 | `python3 -m pytest tests/integration/test_f03.py -q` |
| **F04 实现草稿节点和来源批写** | F03, E12 | 实体候选 → 草稿节点/来源关联 | `src/backend/app/repositories/graph_nodes.py` | 重试幂等；教师锁不覆盖；跨课程源被拒绝；批量部分失败有记录 | `python3 -m pytest tests/integration/test_f04.py -q` |
| **F05 实现 DAG 环检测纯函数** | B11 | 节点/前置边 + 候选边 → 合法或环路径 | `src/backend/app/services/graph/dag.py` | 自环、三节点环、反转造环、断开图、大链条；复杂度边界明确 | `python3 -m pytest tests/backend/test_f05.py -q` |
| **F06 实现关系事务写入与并发防环** | F04, F05 | 关系候选/当前 revision → 已校验边 | `src/backend/app/repositories/graph_relations.py`<br>`src/backend/app/services/graph/relations.py` | 两个连接并发 A→B/B→A 至少一方冲突；校验与提交同写入序列 | `python3 -m pytest tests/integration/test_f06.py -q` |
| **F07 实现草稿图读取与详情服务** | F04, F06, C03 | course/version/filter → 图与节点出处 | `src/backend/app/services/graph/read.py`<br>`src/backend/app/api/graph.py` | 明确教师草稿和学生发布读入口；返回空图/尚未发布区别；来源定位完整 | `python3 -m pytest tests/backend/test_f07.py -q` |
| **F08 实现教师节点编辑与手改锁** | F07, B11 | expected_revision + patch → 新 revision | `src/backend/app/services/graph/edit_node.py`<br>`src/backend/app/api/graph_nodes.py` | 后写冲突不覆盖；教师修改置锁；显式解锁单独权限；自动流程守锁 | `python3 -m pytest tests/backend/test_f08.py -q` |
| **F09 实现节点删除与关系清理** | F08 | 节点 ID/revision → 删除草稿节点 | `src/backend/app/services/graph/delete_node.py` | 只清同版本边；已发布快照不变；不存在/跨课/并发删除明确结果 | `python3 -m pytest tests/integration/test_f09.py -q` |
| **F10 实现节点合并与重接边** | F08, F06 | 重复节点集合 → 合并节点和来源并集 | `src/backend/app/services/graph/merge_nodes.py` | 迁移入出边后去重并验环；锁/冲突时不部分提交；来源不丢 | `python3 -m pytest tests/integration/test_f10.py -q` |
| **F11 实现审核队列和单项处理** | F10 | 草稿候选 → 三类审核项 | `src/backend/app/services/graph/review.py`<br>`src/backend/app/api/review.py` | 低置信度/重复/孤立分类；通过拒绝合并后队列变化；分页稳定 | `python3 -m pytest tests/backend/test_f11.py -q` |
| **F12 实现图编辑审计日志** | F08, F09, F10, C01 | 图编辑事件 → 审计记录 | `src/backend/app/repositories/edit_logs.py`<br>`src/backend/app/services/graph/audit.py` | 谁/何时/何版本/变更摘要齐全；跨库失败可重试；不记录秘密 | `python3 -m pytest tests/backend/test_f12.py -q` |
| **F13 完成图持久化 worker 阶段** | F04, F06, E12, C08 | 抽取候选 → persisting/awaiting_review | `src/backend/app/workers/persist_graph.py` | 失败重跑幂等；取消不标已完成；部分块失败策略严格按 A03 | `python3 -m pytest tests/integration/test_f13.py -q` |
| **F14 实现离线重新向量化命令** | E07, D10, F03, G04 | 已提交版本与来源块及目标向量空间 → 可核对的离线向量空间切换 | `scripts/reembed.py` | 停机运行；完整枚举草稿及已提交版本；失败保留旧空间；校验维度、数量、版本并给出回滚步骤 | `python3 -m pytest tests/integration/test_f14.py -q` |

## G 发布版本和补偿（7 项）

| ID 与单轮任务 | 依赖 | 输入 → 输出 | 功能文件范围 | 验收与负例 | 单项命令 |
| --- | --- | --- | --- | --- | --- |
| **G01 实现快照序列化和摘要** | A04, B11, F07 | 草稿图/来源 → 可验证快照 | `src/backend/app/services/versions/snapshot.py` | 字段顺序稳定；缺端点/来源/环拒绝；完整 roundtrip 不丢属性 | `python3 -m pytest tests/backend/test_g01.py -q` |
| **G02 实现版本元数据与发布操作记录** | G01, C01 | 快照摘要 → preparing/ready 元数据 | `src/backend/app/repositories/versions.py`<br>`src/backend/migrations/005_versions.sql` | 相同幂等键不重复版本；唯一课程版本；失败可查 | `python3 -m pytest tests/backend/test_g02.py -q` |
| **G03 实现版本图与向量构建** | G02, F03, E07 | 快照 → 隔离的版本图/索引 | `src/backend/app/services/versions/materialize.py` | 构建期间学生仍读旧版；维度/模型版本不一致失败；重试不重复图 | `python3 -m pytest tests/integration/test_g03.py -q` |
| **G04 实现原子发布指针切换** | G03, F05, F12 | ready 版本 → 当前 published_version | `src/backend/app/services/versions/publish.py` | 先验 DAG/来源再切指针；任一前置失败保留旧指针；并发发布有冲突 | `python3 -m pytest tests/integration/test_g04.py -q` |
| **G05 实现发布失败补偿与恢复** | G04 | 失败操作记录 → 重试/清理未激活版本 | `src/backend/app/services/versions/reconcile.py` | 模拟 SQLite/Neo4j 各阶段失败；补偿幂等；不清仍被读的旧版本 | `python3 -m pytest tests/integration/test_g05.py -q` |
| **G06 实现回滚和版本列表 API** | G05, C03 | 历史版本 → 列表或指针回滚 | `src/backend/app/api/versions.py`<br>`src/backend/app/services/versions/rollback.py` | 不存在/跨课版本拒绝；回滚当前版按 A04 幂等；保留历史审计 | `python3 -m pytest tests/backend/test_g06.py -q` |
| **G07 实现统一发布版本解析器** | G04 | 学生课程请求 → 固定 version_id | `src/backend/app/services/versions/resolver.py` | 无发布版明确状态；请求中发布新版本不混读；图/问答/路径复用 | `python3 -m pytest tests/backend/test_g07.py -q` |

## H 教师与学生图谱界面（12 项）

| ID 与单轮任务 | 依赖 | 输入 → 输出 | 功能文件范围 | 验收与负例 | 单项命令 |
| --- | --- | --- | --- | --- | --- |
| **H01 实现课程首页和创建表单** | B03, B04, B15, C04 | 课程 API → 课程卡片/创建交互 | `src/frontend/src/views/CoursesView.vue`<br>`src/frontend/src/composables/useCourses.ts` | 加载/空/错/禁止访问；重复点提交不重复创建；切课正确 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/h01.test.ts` |
| **H02 实现资料上传和进度页面** | H01, C07, C12 | 上传响应/task SSE → 阶段和取消界面 | `src/frontend/src/views/MaterialsView.vue`<br>`src/frontend/src/composables/useMaterials.ts` | 非法格式提示、失败重试、取消中/已取消分开；离开关闭流 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/h02.test.ts` |
| **H03 实现契约到 G6 数据适配** | B14, F07 | Graph DTO → 独立 G6 数据 | `src/frontend/src/graph/adapter.ts` | 四类边样式、方向、缺端点、空图、稳定 ID；不修改输入对象 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/h03.test.ts` |
| **H04 实现 G6 生命周期组件** | H03 | 适配图 → 可缩放拖拽画布 | `src/frontend/src/components/GraphCanvas.vue`<br>`src/frontend/src/graph/lifecycle.ts` | 挂载/更新/销毁；反复切页不泄漏；resize 后布局正确 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/h04.test.ts` |
| **H05 实现图搜索筛选与布局切换** | H04 | 搜索词/类型/章节 → 图可见集合 | `src/frontend/src/composables/useGraphFilters.ts`<br>`src/frontend/src/components/GraphToolbar.vue` | 筛选后无悬空边；清空恢复；层次/力导向切换不丢选中态 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/h05.test.ts` |
| **H06 实现知识点详情和来源浏览** | H04, F07 | 节点 ID → 定义/关系/原文抽屉 | `src/frontend/src/components/KnowledgeDetail.vue`<br>`src/frontend/src/composables/useKnowledgeDetail.ts` | 点击来源定位页/章节；未知来源不伪造；XSS 文本不执行；迟到请求隔离 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/h06.test.ts` |
| **H07 实现教师节点编辑面板** | H06, F08, F09 | 详情/patch → 保存/删除交互 | `src/frontend/src/components/NodeEditor.vue`<br>`src/frontend/src/composables/useNodeEditor.ts` | 字段错误、revision 冲突、锁/解锁；失败不假装保存成功 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/h07.test.ts` |
| **H08 实现教师连边编辑交互** | H04, F06 | 拖线/类型/反转 → 关系请求 | `src/frontend/src/components/RelationEditor.vue`<br>`src/frontend/src/composables/useRelationEditor.ts` | 成环错误高亮冲突路径；服务拒绝时撤销临时边；无组件 Cypher | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/h08.test.ts` |
| **H09 实现审核队列和节点合并 UI** | F10, F11, H07 | 审核项 → 单项动作与结果 | `src/frontend/src/views/ReviewView.vue`<br>`src/frontend/src/composables/useReview.ts` | 三类空态、重复操作、合并冲突；刷新后数量一致 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/h09.test.ts` |
| **H10 实现发布历史和回滚 UI** | G06, H09 | 版本 API → 发布/历史/回滚界面 | `src/frontend/src/components/VersionPanel.vue`<br>`src/frontend/src/composables/useVersions.ts` | 发布失败保持旧标识；修订中学生仍见旧版；回滚前显示目标版本 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/h10.test.ts` |
| **H11 实现学生图谱和卡片视图** | H05, H06, G07 | 发布图 → 图/卡片切换 | `src/frontend/src/views/StudentGraphView.vue`<br>`src/frontend/src/components/KnowledgeCards.vue` | 无发布、空图、分页卡片、键盘可用；任何入口不取草稿 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/h11.test.ts` |
| **H12 实现课程成员管理页面** | C15, B15, H01 | 课程成员 API → 教师成员列表与增删操作 | `src/frontend/src/views/MembersView.vue`<br>`src/frontend/src/api/members.ts` | 教师可添加和移除；学生无入口；权限失败明确提示；重复提交不重复成员 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/h12.test.ts` |
| **H13 实现前端登录页与会话存储** | C13, B15, B03, B04 | 登录端点 + A05 §2.4 → 登录页、会话读写与 401 回登录 | `src/frontend/src/views/LoginView.vue`<br>`src/frontend/src/stores/session.ts`<br>`src/frontend/src/api/auth.ts`<br>`src/frontend/src/router/index.ts`<br>`src/frontend/src/main.ts` | 令牌与 LoginResponse.user 只存 sessionStorage（不存 localStorage/Cookie）；登录后按 user.role 进首页；401、429 分别明确提示；收到 401 清会话与课程上下文并回登录页；口令/令牌不写日志；不解析 JWT 做授权 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/h13.test.ts` |

## I 进度与可解释推荐（6 项）

| ID 与单轮任务 | 依赖 | 输入 → 输出 | 功能文件范围 | 验收与负例 | 单项命令 |
| --- | --- | --- | --- | --- | --- |
| **I01 实现学习进度仓储** | C01, A08, G07 | 当前用户/知识点状态 → 进度记录 | `src/backend/app/repositories/progress.py`<br>`src/backend/migrations/006_progress.sql` | 用户/课程隔离，重复写幂等，未知节点拒绝；版本迁移按 A08 | `python3 -m pytest tests/backend/test_i01.py -q` |
| **I02 实现掌握标记 API** | I01, C03, B12 | 标记请求 → 当前进度 | `src/backend/app/services/learning/progress.py`<br>`src/backend/app/api/progress.py` | 拒绝请求冒用他人 user_id；改标后可重算；不能标草稿独有点 | `python3 -m pytest tests/backend/test_i02.py -q` |
| **I03 实现可学集合纯函数** | A08, F05 | 发布 DAG + M → 可学候选 | `src/backend/app/services/learning/eligible.py` | M 空/全掌握/孤立点/多前置/环/外课 ID；不擅改用户掌握集合 | `python3 -m pytest tests/backend/test_i03.py -q` |
| **I04 实现四项评分和结构化理由** | I03 | 候选/图/参数 → 排序及分量 | `src/backend/app/services/learning/ranking.py` | 零分母、全零权重、同分、真实解锁数；分量求和等于 score；理由不用 LLM | `python3 -m pytest tests/backend/test_i04.py -q` |
| **I05 实现推荐查询 API** | I02, I04, G07 | 用户课程 → 候选列表与明确空态 | `src/backend/app/services/learning/recommend.py`<br>`src/backend/app/api/recommend.py` | 请求全程同版本；截断稳定；未发布 404 与全掌握区别；已提交图损坏 5xx；有环明确错误 | `python3 -m pytest tests/backend/test_i05.py -q` |
| **I06 实现掌握标记与推荐 UI** | I05, H11 | 进度/推荐 → 学习状态色/推荐高亮 | `src/frontend/src/composables/useLearning.ts`<br>`src/frontend/src/components/Recommendations.vue` | 失败撤销乐观标记；切课后旧推荐不覆盖；理由与服务分量一致 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/i06.test.ts` |

## J 可信问答（10 项）

| ID 与单轮任务 | 依赖 | 输入 → 输出 | 功能文件范围 | 验收与负例 | 单项命令 |
| --- | --- | --- | --- | --- | --- |
| **J01 建立发布来源向量检索** | G07, G03, E07 | 问题向量 + course/version → 来源候选 | `src/backend/app/repositories/vector_search.py` | 先限定作用域或可靠过滤并补足召回；跨课/旧版本结果不进入上下文 | `python3 -m pytest tests/integration/test_j01.py -q` |
| **J02 实现图结构检索** | G07, F07 | 术语/知识点 → 有界子图 | `src/backend/app/repositories/graph_search.py` | 跳数和节点数有上限；只返回同课程发布版；无匹配返回空 | `python3 -m pytest tests/integration/test_j02.py -q` |
| **J03 实现多轮问题改写** | E04, E01 | 有限历史+问题 → 检索问题 | `src/backend/app/services/qa/rewrite.py`<br>`prompts/rewrite_query.yaml` | 历史裁剪、指代失败保留原问题、超时降级；不接受历史中的系统角色 | `python3 -m pytest tests/backend/test_j03.py -q` |
| **J04 实现检索合并与上下文预算** | J01, J02, J03, A09 | 两路候选 → 编号证据上下文 | `src/backend/app/services/qa/context.py` | 去重保留出处；低分/空上下文返回未覆盖；阈值用 fake；token 预算不截断定位 | `python3 -m pytest tests/backend/test_j04.py -q` |
| **J05 实现有证据问答生成** | J04, E04 | 上下文 → 待校验答案 | `src/backend/app/services/qa/generate.py`<br>`prompts/answer_with_context.yaml` | 空/低分上下文生成调用数为0；原文注入按资料处理；超时为独立错误 | `python3 -m pytest tests/backend/test_j05.py -q` |
| **J06 实现引用和终态校验** | J05, B13 | 待校验答案/允许引用集合 → 最终响应 | `src/backend/app/services/qa/citations.py` | 未知编号/外课/旧版/空引用；全部失效则未覆盖并清除答案；有效来源定位可解 | `python3 -m pytest tests/backend/test_j06.py -q` |
| **J07 实现问答 POST SSE API** | J06, C03 | 课程问题 → meta/delta/done/error | `src/backend/app/api/chat.py`<br>`src/backend/app/services/qa/stream.py` | 协议事件有序；断连释放任务；无自动重复生成；失败终态不展示已验证答案 | `python3 -m pytest tests/backend/test_j07.py -q` |
| **J08 实现问答 fetch 流客户端** | J07, B15 | 任意网络分片 → 类型化事件 | `src/frontend/src/api/chatStream.ts` | UTF-8跨字节、CRLF、多行data、空帧、异常EOF、取消；不自动重放提问 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/j08.test.ts` |
| **J09 实现问答与引用联动 UI** | J08, H06 | 流/最终引用 → 对话和出处面板 | `src/frontend/src/views/ChatView.vue`<br>`src/frontend/src/composables/useChat.ts` | 临时文字标识；引用失败终态替换；Markdown/XSS过滤；切课清上下文 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/j09.test.ts` |
| **J10 实现问答审计与统计** | J07, C01 | 完成/失败事件 → 可检索日志 | `src/backend/app/repositories/chat_logs.py`<br>`src/backend/migrations/007_chat_logs.sql` | 课程用户隔离、版本/耗时齐全；日志留存与脱敏明确；重试不重复统计 | `python3 -m pytest tests/backend/test_j10.py -q` |

## K 评测部署与交付（19 项）

| ID 与单轮任务 | 依赖 | 输入 → 输出 | 功能文件范围 | 验收与负例 | 单项命令 |
| --- | --- | --- | --- | --- | --- |
| **K01 建立自编标注集及评测口径** | A07, E11, J06, I04 | 自编材料 → 标注格式与指标定义 | `evaluation/README.md`<br>`evaluation/fixtures/synthetic.json` | 区分实体/关系准确召回、引用有效/支持度、未覆盖混淆矩阵；阈值不在测试集调 | `git diff --check；逐条核对 K01 验收矩阵与源文档，人工决策保留未签收标记` |
| **K02 实现抽取和融合离线评测** | K01, E11 | 预测/金标 → 分项指标报告 | `evaluation/evaluate_extraction.py` | 空分母、ID匹配、四类型分组；固定输入重复结果一致；假模型不充真实效果 | `python3 -m pytest tests/backend/test_k02.py -q` |
| **K03 实现可信问答离线评测** | K01, J06 | 问题/答案/证据 → 质量指标 | `evaluation/evaluate_qa.py` | 编号存在不等于支持结论；包含注入/不覆盖负例；支持人工复核与假阳性记录 | `python3 -m pytest tests/backend/test_k03.py -q` |
| **K04 实现全链路阶段性能测量** | F13, J07, E04 | 固定约2万字fixture → 阶段耗时/token报告 | `evaluation/benchmark_pipeline.py` | 注明机器/模型/并发/样本数/p50/p95；区分目标与实测；付费执行另行确认 | `python3 -m pytest tests/backend/test_k04.py -q` |
| **K05 建立教师主线 E2E** | H02, H08, H09, H10, F13 | 自编四格式资料 → 上传到发布用例 |  | fake模型也走真实服务；成环拒绝、失败重试、发布可见；保留失败证据 | `npm --prefix src/frontend run test:e2e -- ../../tests/e2e/teacher.spec.ts` |
| **K06 建立学生主线 E2E** | I06, J09, H11, K05 | 已发布课程 → 浏览/掌握/推荐/问答 |  | 跨课程拒绝；草稿不可见；旧发布版稳定；无来源答案不完成显示 | `npm --prefix src/frontend run test:e2e -- ../../tests/e2e/student.spec.ts` |
| **K07 复用并审查环境启停脚本** | F01, A10 | 已有 dev-up/down → 启停行为修正 | `scripts/dev-up.sh`<br>`scripts/dev-down.sh`<br>`scripts/_dev-common.sh` | 普通停止保留数据；删除卷需要显式确认；缺 env 给提示；不覆盖个人 .env | `python3 -m pytest tests/tooling/test_k07.py -q` |
| **K08 实现前后端与 worker 容器配置** | K07, B05, B01, F13 | 可运行应用 → 镜像/Compose 服务 | `src/backend/Dockerfile`<br>`src/frontend/Dockerfile`<br>`docker-compose.yml` | 按 A06 运行worker；容器健康检查；密钥只在后端；前端构建不含密钥 | `python3 -m pytest tests/integration/test_k08.py -q` |
| **K09 实现示例课程幂等导入** | K05, K06 | 自编课程包 → 一键演示数据 | `scripts/import-demo.py`<br>`datasets/demo/manifest.json` | 重跑不重复；只写示例课；失败可重试；不混入真实资料或删除他课 | `python3 -m pytest tests/integration/test_k09.py -q` |
| **K10 建立备份和恢复演练** | G05, K08 | 临时双库/文件 → 可恢复快照集 | `scripts/backup-demo.sh`<br>`scripts/restore-demo.sh` | 一致时间点和发布指针；恢复在隔离副本验证引用/图/进度；不覆盖用户库 | `python3 -m pytest tests/integration/test_k10.py -q` |
| **K11 接入实际质量门禁** | B07, B14, K05, K06 | 各层真实测试 → 单入口汇总 | `scripts/verify.sh`<br>`scripts/verify/backend.sh`<br>`scripts/verify/frontend.sh` | 已实现模块无静默SKIP；零测试视为缺口；失败退出非0；基础/集成模式明确 | `python3 -m pytest tests/tooling/test_k11.py -q` |
| **K12 编写部署验收和演示说明** | K08, K09, K10, K11 | 已测命令/指标 → 运行手册和验收矩阵 | `docs/runbook.md`<br>`docs/acceptance.md` | 逐功能指向真实证据；Windows/macOS/Linux仅列已测平台；限制和恢复步骤齐全 | `git diff --check；逐条核对 K12 验收矩阵与源文档，人工决策保留未签收标记` |
| **K13 实现抽取消融实验** | K02, E06 | 同一自编标注集与三种抽取配置 → 单阶段、两阶段、两阶段加补漏的对照报告 | `evaluation/ablation.py`<br>`evaluation/reports/ablation.md` | 同数据同指标记录三组结果、成本与版本；空样本和失败组明确；不得把 fake 效果充真实结果 | `python3 -m pytest tests/backend/test_k13.py -q` |
| **K14 整理提示词工程完整记录** | E01, E05, E06 | 已实际使用的提示词和版本 → 可追溯的提示词工程材料 | `docs/submission/prompt-engineering.md` | 记录版本、用途、输入输出和修改依据；不含密钥或真实课程资料；引用实际评测证据 | `git diff --check；逐条核对 K14 验收矩阵与源文档` |
| **K15 整理图谱构建示例** | K05, K09 | 已验证的演示课程和图谱 → 带来源的构建示例 | `docs/submission/graph-example.md` | 展示上传、审核、发布与来源；使用自编数据；图与文本可追溯同一版本 | `git diff --check；逐条核对 K15 验收矩阵与源文档` |
| **K16 形成 S2 技术方案定稿** | K04, K13, K14, K15 | 已验证的实现与评测证据 → 与当前代码一致的 S2 定稿 | `docs/submission/S2-final.md` | ADR-008 命名与现行协议一致；性能写实测条件；未实现功能不写为已完成 | `git diff --check；逐条核对 K16 验收矩阵与源文档` |
| **K17 制作 S1 概要、展示稿与演示视频** | K12, K15, K16 | 运行手册与演示课程 → 可重复演示的概要、PPT 与视频 | `docs/submission/S1-overview.md`<br>`docs/submission/demo-script.md`<br>`docs/submission/S1-overview.pptx`<br>`docs/submission/demo-video.mp4` | 视频与 PPT 展示同一已验证版本；失败场景不剪成成功；链接和文件可打开 | `git diff --check；人工核对 S1、PPT、视频与运行手册` |
| **K18 整理 S5 团队过程材料** | K12 | 任务板、交接与审查记录 → 可追溯的团队过程材料 | `docs/submission/S5-team-process.md` | 任务分工、审查和修复均指向真实提交或交接；不泄露个人敏感路径 | `git diff --check；逐条核对 S5 记录与提交` |
| **K19 执行提交材料合规自检** | K14, K15, K16, K17, K18 | 完整参赛材料 → 去标识化与原创承诺检查记录 | `docs/submission/compliance.md` | 检查真实姓名路径、密钥、第三方素材许可和原创承诺；未通过项列出负责人和修复证据 | `git diff --check；逐项核对 K19 合规清单` |

## O 可选加分项（8 项）

| ID 与单轮任务 | 依赖 | 输入 → 输出 | 功能文件范围 | 验收与负例 | 单项命令 |
| --- | --- | --- | --- | --- | --- |
| **O01 确认目标路径和学习材料范围** | K06 | S2加分项/分支ADR → 独立准入决定 | `docs/decisions.md`<br>`docs/tasks.md` | 明确是否纳入、优先级、预算、字段变更；未批准时后续 O 项不执行 | `git diff --check；逐条核对 O01 验收矩阵与源文档，人工决策保留未签收标记` |
| **O02 定义目标路径契约** | O01, B12 | 目标t/已掌握M → 祖先子图和步骤DTO | `specs/learning-path.md`<br>`src/contracts/api.v1.yaml`<br>`src/contracts/v1/generated/` | 是否包含目标、目标已掌握、环/缺点、并列顺序全部明确；重新生成契约；重新生成 | `python3 -m pytest tests/contracts/test_o02.py -q` |
| **O03 实现目标路径算法与API** | O02, I05 | 目标/发布DAG/M → Kahn有序步骤 | `src/backend/app/services/learning/target_path.py`<br>`src/backend/app/api/recommend.py` | 多前置祖先完整；不重复、不越课、无环；目标已掌握按规格 | `python3 -m pytest tests/backend/test_o03.py -q` |
| **O04 实现目标路径编号高亮** | O03, I06 | 有序步骤 → 图步骤编号与导航 | `src/frontend/src/components/TargetPath.vue` | 筛选不丢必要前置说明；切目标/课程清旧路径；键盘可操作 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/o04.test.ts` |
| **O05 定义学习材料缓存与审核契约** | O01, B13 | 按需讲解/练习 → 来源/审核/缓存模型 | `specs/study-material.md`<br>`src/contracts/api.v1.yaml`<br>`src/contracts/v1/generated/` | 包含version/prompt/model缓存键；发布前教师审核；未覆盖和失败有区别；重新生成 | `python3 -m pytest tests/contracts/test_o05.py -q` |
| **O06 实现学习材料生成与缓存服务** | O05, J06, E04 | 知识点证据 → 讲解/示例/3题答案解析 | `src/backend/app/services/study_material.py`<br>`prompts/gen_study_material.yaml` | 证据不足不生成；题量正确；引用校验；缓存换版本失效；mock测预算 | `python3 -m pytest tests/backend/test_o06.py -q` |
| **O07 实现学习材料审核与读取API** | O06, C03 | 生成内容/教师决策 → 可读审核结果 | `src/backend/app/api/study_material.py`<br>`src/backend/app/repositories/study_material.py` | 学生仅见已审核；教师拒绝可回查；并发审核冲突；创建数据库迁移另拆如超范围 | `python3 -m pytest tests/backend/test_o07.py -q` |
| **O08 实现材料按需入口与审核UI** | O07, J09, H09 | 材料状态 → 请求/审核/显示界面 | `src/frontend/src/components/StudyMaterial.vue`<br>`src/frontend/src/composables/useStudyMaterial.ts` | 生成中/失败/未覆盖/待审核区分；三题解析可读；无凭证或秘密入前端 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/o08.test.ts` |

## 单任务派发模板

```text
只完成原子任务 <ID>，不要顺手执行后续任务。
目标 checkout：<绝对路径>；基线 HEAD：<sha>。
先读 AGENTS.md、任务板、相关规格及依赖任务交接；确认依赖验收完毕。
输入、预期输出、允许文件、验收条件：采用 atomic-tasks.json 的本任务条目。
先写一个会失败的目标测试，再实现，最后跑单项测试、verify.sh、diff --check。
缺决策/新领域变更/超过单轮范围时记录并拆分，不虚构缺失接口。
结束记录实际命令、PASS/SKIP/FAIL、未验证范围，写自己的交接文件。
仅在固定提交/差异范围且没有继续写入时标记 ready_for_review，交给 Codex 审查。
未经另行要求，不合并、不推送、不改其他人的文件。
```

## 当前人工决策门

- 契约源与分支合并基线：A01/A10；优先处理，因为会影响所有消费者。
- 身份实现及成员权限：A05；两个分支决定不同步，不能依聊天推断。
- 模型接入取值、向量维度和预算：A07；fake 工作可先行，真实接入/评测须确认。
- 发布版本/快照形态、worker 策略：A04/A06；实现前同步架构。
- 示例课程/资料：既有 D-01；自编单元 fixture 不等于真实课程质量验收。
- 加分项：O01；主线完成前不抢占。
