# Codex 交接：邀请码、悬停性能与行为保持重构

- 日期：2026-11-05；状态：实施中。
- 分支：`codex/invite-hover-refactor`，起点 `445bfc9`（包含界面改版 `ef5e297` 与本轮 Claude 交接）。工作区起始干净；只本地提交，不推送、PR、合并或发布。
- 顺序与范围：GRAPH-HOVER-01 → INVITE-01 → REFACTOR-01，遵循用户明确批准的交接稿；不新增/升级依赖、不改图谱主题色与已有 data-test。

## 基线

| 命令 | 实际结果 | 耗时 |
| --- | --- | --- |
| `npm --prefix src/frontend run type-check` | exit 0 | 23.63s |
| `cd src/frontend && npx vitest --run` | 78 文件、1311 passed；exit 0 | 38.39s |
| `cd src/frontend && npx vite build` | exit 0 | 3.06s |
| `PATH="$PWD/.venv/bin:$PATH" ./scripts/verify.sh` | basic/契约门禁 exit 0 | 223.93s |

完整日志与机读摘要：`/private/tmp/smartsketch-invite-hover-20261105/`。运行时 Node v26.4.0、Python 3.11.9。Docker Desktop 启动后用 `PATH="$HOME/.docker/bin:$PATH" scripts/start-demo.sh --no-open` 启动既有演示环境；模型与向量均 demo，无付费模型请求。

## GRAPH-HOVER-01

- RED：`npm --prefix src/frontend test -- --run ../../tests/frontend/graph-enhancer.test.ts --reporter=dot`，39 条中 14 failed/25 passed；尚未改生产代码时复现停留阈值、重复状态、兜底、数据替换、销毁与异步覆盖问题。
- 原语义断言保留，FakeEnhancedGraph 增加按元素累计状态；状态批次另用于确认差分。
- 优化前真实演示图 64 节点+71 边，1440×900，普通/预览各 10 次移入+移出。使用真实 G6 `Graph.prototype.setElementState` 包裹同步计时、PerformanceObserver 长任务；通过 G6 事件派发做确定性重复，**不是物理鼠标轨迹测量**。
- 普通：20 次均 135 元素，同步 32.2–47.8ms，未记录 >50ms 长任务；预览：20 次均 135 元素，32.2–45.9ms，未记录 >50ms 长任务。详细数组 `hover-metrics.json`；本次未复现历史 63ms 上限，不把历史数值当成本机新基线。
- GREEN：三组定向（graph-enhancer、graph-lifecycle-enhance、graph-canvas-enhanced）3 文件/77 passed；全量前端78 文件/1326 passed，type-check与basic exit0。
- 第1/2项优化后：普通完整进出33.3–58.7ms（135元素，2次>50ms长任务），预览32.6–43.7ms（134元素，无长任务）。快速划过10次零写入，相邻切换10次均20元素、8.5–15.8ms。**全进出目标尚未全部达到；用户已明确选择保留现有淡化，仅交付第1/2项并记录该限制，继续A/C。**
- 首轮优化后采样与baseline环境不一致（basic仍运行且临时开启Vite轮询监听），普通33.4–70.4ms、预览46.3–194.4ms；原始值保留在`after_during_basic`，不作为同环境前后对比。关闭轮询、待测试完成后采集上述`after_idle`，没有删除不利观测。
- 临时探针与index入口已撤回；最终type-check、build、basic均exit0；当前状态写入与停留测试通过不代表全进出性能已解决。

## INVITE-01

已完成：后端新41项与成员/课程相邻回归合计74 passed（33.63s，exit0），覆盖权限复查、并发顺序、历史码与限流；仅既有Starlette/httpx弃用warning。初始测试中发布fixture误用32位version_id（既有要求26位）已纠正，未修改产品约束或旧断言。契约生成（39路径/135 schema）与完整contracts gate exit0；ADR-096、身份规格/架构/错误码先行。迁移020回归先9条missing-table失败，实施后连同旧回滚守卫24 passed。初次fixture PHC格式错误已修正，不当作产品RED。用户已决：允许入未发布课程，提示“教师发布后可见”；保留原列表可见性，已发布课程成功后刷新并高亮。

### 前端与人工验收

- API客户端 → composable → 组件分层；学生入口在继续学习卡下方，仅课程列表页、student账号显示。入课期间禁用重复提交，trim/大写规范化，错误分别呈现；教师成员页保留按用户名添加，并增加查看、复制及二次确认重置。
- 会话、课程、卸载后取消旧请求并忽略迟到回执。复审补修“轮换已提交、响应丢失”场景：网络/超时/坏响应不继续展示旧码，显式重新GET；三项先RED再GREEN。明确500事务回滚场景继续保留原码，旧断言保留。
- 最终新增前端42条通过；原课程/成员/继续学习回归89条通过，HTTP/SSE闭集同步与相邻用例通过。初始全量与backend/basic并行时，l14及student-graph-workbench各一项5秒超时（79文件/1363 passed、2 failed）；保留日志，未调整超时或断言；空闲负载最终全量81文件/1368 passed（46.98s），type-check（28.97s）/build（4.03s）exit0。
- 真实Chrome/demo：教师查看→复制后剪贴板一致→取消重置保留原码→确认重置显示新码；新学生用旧码收到失效提示、带空格小写新码加入已发布课程后刷新与高亮、重复加入提示“已在课程中”；未发布入课成功提示“教师发布后可见”且列表仍只有已发布的一门；点击“开始学习”进入64节点/71关系图谱及知识点详情。
- 截图：验证目录内 `invite-teacher.jpg`、`invite-student.jpg`、`invite-draft.jpg`。未运行Safari/Windows或真实网络断流；响应丢失由可执行回归覆盖。
- 后端完整 `scripts/verify/backend.sh full`：4243 passed、27登记SKIP、1既有warning，884.30s，gate PASS；500声明补充的两项另跑PASS。A的basic exit0（351.81s）。

### 接口、数据与运行限制

- 新增 `POST /api/v1/courses/join`、`GET /api/v1/courses/{cid}/invite-code`、`POST /api/v1/courses/{cid}/invite-code:rotate`；新增两个 DTO 和 `INVITE_CODE_INVALID` / `ALREADY_MEMBER`。结构化比较确认所有旧路径定义不变，旧 schema 仅 ErrorCode 增加两值。教师生成碰撞耗尽的 500 Error 声明在复审中补齐：2 RED → 2 PASS；未算进此前已收集的后端 full。
- 六位码用去歧义的 32 字符随机生成，明文受教师成员权限保护；旧课程首次查看懒生成。020 表保留撤销历史，全局唯一码、每课最多一个活跃码；轮换不移除既有学生。
- 取码、轮换、加入都在 SQLite `BEGIN IMMEDIATE` 内重新检查权限，入课与重置按事务顺序生效。后端 API/服务/仓储分层；邀请码不进入课程列表、详情、日志或前端持久存储。
- 入课每用户10次/60秒、每IP60次/60秒；4096活跃桶上限，容量满时拒绝而不驱逐。限流在单 API 进程内，重启/多进程不共享；IP沿用ASGI可信代理部署边界，应用不自行读取XFF。语法非法JSON在FastAPI解析阶段拒绝，未进入业务限流。
- 回滚：停API/worker并备份SQLite → 执行020中的 `DROP TABLE course_invite_codes;` 和 `DELETE FROM schema_migrations WHERE version = '020';` → 切回旧代码。课程、成员及进度保留；邀请码和撤销历史会丢失，重启该功能需重新分发，不能承诺跨主动删除历史的回滚继续永久撤销。
- 本地浏览器验收准备了合成学生 `invite_accept_20261105` 和“邀请码验收·未发布课程”，只在既有demo环境中；不提交业务库、token或邀请码。没有调用真实模型。

## REFACTOR-01

A 已提交 `d051a47` 后开始，三类分别提交并各跑 type-check、全量vitest、build、backend full、basic。

1. 样式：删除 `graph-workspace.css` 较早的重复 `.gw-hint` 和完全被后条覆盖的 `.gw-list`；保留后条位置和所有有效声明，修正“旧色等于当前token”的过时注释。四组指定样式测试基线32 passed；重构前1440×900图谱/列表与768×900列表截图、全部计算样式已存验证目录。改后type-check、81文件/1368测试、build均exit0；1440×900和768×900下三个受影响元素各569项计算样式逐项相同，截图目视无变化（未做像素级解码比较，本地未装Pillow且未新增依赖）。后端full 4245 passed/27登记SKIP、gate exit0（733.66s）；basic exit0（233.19s）。
2. 纯逻辑：已提取师生两页重复的知识点类型计数/切换，保留整图统计、固定顺序及各自恢复语义；收敛HTTP/任务SSE/问答SSE三份同序30项ErrorCode闭集，保留生成契约完整性检查、消息/details验证和聊天专用错误码。新增H05等价性用例4条，7文件定向260 PASS；独立只读复审确认数组30值逐项同序、无运行时循环依赖，计数数据源/零项/顺序/XOR切换不变。前端全量81文件/1372 PASS（54.29s），type-check/build exit0；backend full 4245 PASS/27登记SKIP、gate exit0（770.63s），basic exit0（275.74s）。Chrome师生两端都验证隐藏55个概念后显示9/64，计数仍保留55，恢复后64/64；教师关系5/71→71/71。未写图数据。
3. 测试：计划用本次绘制/聚焦完成条件替换固定10/30ms等待，并在afterEach销毁裸graph lifecycle。不会改断言、timeout或重试次数；不能将消除固定等待等同于证明所有负载超时的根因。

审计未纳入：页面覆盖层的token重定义和不同硬编码色不等价，不能为去重改变视觉；课程内teacher与账号teacher门槛不同，不能盲目合并鉴权；未找到有充分未引用证据的组件可删，不以文件数量作为重构目标。删除清单仅上述两条无效CSS规则。768px窄屏长用户名会挤压顶栏退出按钮，重构前后截图一致；属于既有布局限制，本次保持视觉范围不改。

## 未完成与下一步

B第1/2项已提交 `2728315`，性能限制由用户确认保留。A已完成前后端、浏览器验收与全量验证，接下来按三类安全候选实施C（样式、共享图例逻辑、测试等待/清理）。
