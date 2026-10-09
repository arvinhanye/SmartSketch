LOOP: PARTIAL

# 正式模式业务闭环验收报告（真实 DeepSeek + 在线向量，隔离安装）

```text
from: DeepSeek harness
to: Claude
date: 2026-10-09
task: docs/handoffs/claude-formal-loop-deepseek-handoff.md
previous: docs/handoffs/deepseek-formal-embedding-network-20261009.md、docs/handoffs/deepseek-formal-embedding-baseline-20261009.md
installation: 隔离安装 id 74694b2cb256134c，网站 http://127.0.0.1:18080
code: 分支 claude/release-launcher-merge（未推送）
判定: LOOP: PARTIAL —— R1–R12 全部"必须通过"行均通过；非阻塞问题见 §5
生成类用量: 112,491 / 800,000 token（14.1%）
embedding 请求: 任务流水线 16 次 + 门禁/探测约 14 次（均短文本）
对话/抽取 token（DeepSeek）: 全部计入上述 112,491
auth 类错误: 0 次（仅 R10 故意注入的无效密钥返回 auth，符合预期）
密钥读取/打印/复制: 0（凭据文件读取后即删，报告只含 key_hint 末 4 位）
产品代码/测试/契约/迁移/启动器/默认配置改动: 0
用户系统网络/Docker Desktop 设置改动: 0
```

## 1. 汇总表（R1–R12）

| # | 步骤 | 结果 | 证据位置 | 耗时 |
| --- | --- | --- | --- | --- |
| R1 | 教师登录 + 模型 API 设置 + 网页测试连接 | ✅ 通过 | 页面 `/settings/model`；截图 `r1-04-after-login.png`、`r1-05-model-settings.png`、`r1-06-test-result.png` | 登录 <1s；测试连接 **1251 ms** |
| R2 | 创建课程 + 上传示例章节 + 任务推进到待审核 | ✅ 通过 | 任务 `70fb45a0…`；阶段 `extracting→persisting→awaiting_review` | **总计 114 s**（详见 §3.1） |
| R3 | 图谱质量抽样 | ✅ 通过（准确率达标） | 图谱 API + 抽样判定（§3.2） | 图谱查询 1.5 s |
| R4 | 审核队列 → 发布 v1 | ✅ 通过 | `POST /publish` → `version=1`，71 点/62 边，excluded 全 0 | **12.83 s** |
| R5 | 草稿/发布隔离 | ✅ 通过 | 教师改名 `revision=2`；学生仍见原名，`graph_version=1` | <1 s |
| R6 | 学生注册 + 未配置模型被拦 | ✅ 通过 | `409 MODEL_CONFIG_REQUIRED` + 页面"去设置"引导 | 0.05 s |
| R7 | 加入课程 + 学生保存个人配置 | ✅ 通过 | `configured=true`、`key_hint=061f`，GET 无明文 | <1 s |
| R8 | 学生浏览图谱 + 标记 2 个掌握 + 刷新保持 | ✅ 通过 | API 2 点 `mastered`；**UI 再标记 1 点后刷新 3/71**；截图 `student-07/08` | UI 点击 <4 s |
| R9 | 学生问答 4 课内 + 1 课外 | ✅ 通过 | 4/4 `answered` 带引用；1/1 `not_covered` 0 引用（§3.3） | 最长 11.0 s（<15 s 口径） |
| R10 | 无效密钥路径（非阻塞） | ✅ 通过 | `{"ok":false,"error_class":"auth"}`，不回显服务端原文 | 0.55 s |
| R11 | 重启 api + worker 后持久化 | ✅ 通过 | 6/6 项保持（令牌/版本/图谱/进度/改名/成员关系） | 重启到 healthy **12 s** |
| R12 | 四容器日志卫生 | ✅ 通过 | `sk-`=0、`Bearer`=0、`key/secret/token`=0；长串均为 request_id | — |

全部 12 行通过；判定为 **PARTIAL** 而非 PASS 的原因是非阻塞问题（§5 观察 1–2：内部事件状态不一致、向量配置口径），不影响闭环结论。

## 2. 用量表

| 时点 | 生成类累计 | embedding 调用 | 说明 |
| --- | --- | --- | --- |
| 启动时 | 0 | 0 | `model_calls` 空表（验收前已确认） |
| R1 之后 | 0（+测试连接 1 次极小请求） | 0 | 网页"测试连接"输出 1 token |
| R2 之后 | 96,458 | 10 | extract_entities 18 次（含 2 次失败重试）、repair 3 次、extract_relations 16 次 |
| R9 之后（最终） | **112,491** | 16 | answer_with_context 6 次（含 R9 探测 1 次） |

明细（最终）：

| purpose | 调用 | in | out | 小计 |
| --- | --- | --- | --- | --- |
| extract_entities | 18（16 ok + 2 error） | 10,293 | 22,054 | 32,347 |
| extract_relations | 16 | 16,342 | 34,747 | 51,089 |
| repair | 3 | 2,793 | 10,229 | 13,022 |
| answer_with_context | 6（5 ok + 1 sent） | 13,073 | 2,960 | 16,033 |
| **生成类合计** | **43** | **42,501** | **69,990** | **112,491（14.1% 上限）** |
| embedding（不计入生成类） | 16 | 7,156 | 0 | — |

未触及 800,000 停止线；每步开始前均核算，最大单步消耗为 R2（96k）与 R9（16k）。

## 3. 关键明细

### 3.1 R2 阶段耗时（从数据库 `model_calls` 时间线与任务快照重建）

| 阶段 | 起止（UTC） | 耗时 | 证据 |
| --- | --- | --- | --- |
| 解析 + 分块 | 14:22:22 → 14:22:24 | ~2 s | 任务创建后 2 s 内首个模型调用发起 |
| 抽取实体（含 2 次连接失败重试） | 14:22:24 → 14:22:58 | 34 s | 18 次 `extract_entities` |
| 融合/修复 | 14:22:58 → 14:23:49 | 51 s | 3 次 `repair` |
| 抽取关系 | 14:23:13 → 14:23:58 | 45 s | 16 次 `extract_relations`（与融合部分重叠） |
| 持久化写入 | 14:23:58 → 14:24:02 | ~4 s | 任务 `stage=persisting progress=0.8`（10:24:01 观测） |
| 进入待审核 | 14:24:02 → 14:24:16 | ~14 s | 任务 `stage=awaiting_review progress=0.95`（10:24:18 观测） |
| **端到端** | **14:22:22 → 14:24:16** | **114 s** | `created_at` → `updated_at` |

观测到的阶段序列：`extracting → persisting → awaiting_review`（轮询 3 s 一次，未观测到独立 `parsing`/`fusing` 标签；融合表现为 `repair` 调用与 `progress` 停滞段）。`progress` 取值 0.125→0.95 共 20+ 个中间值，**非固定跳变**，与后台真实进度一致。

### 3.2 R3 抽样明细

图谱规模：**71 知识点 / 62 关系**；关系类型 `CONTAINS 29 / RELATED_TO 22 / EXAMPLE_OF 10 / PREREQUISITE 1`；知识点 `concept 28 / method 15 / example 12 / theorem 11 / formula 5`；`confidence` 0.80–0.95（均 0.91）；**孤立点 3**；`PREREQUISITE` 1 条、DFS 检测 **0 环 ✅**。

**抽样 10 个知识点**（对照源材料逐条判定）：

| # | 知识点 | 定义摘要 | 判定 |
| --- | --- | --- | --- |
| 1 | 循环队列判空与判满 | front==rear 队空；(rear+1)%MaxSize==front 队满 | ✅ 与性质 3.2 一致 |
| 2 | 队列的基本操作 | 初始化/判空/入队/出队/读队头 | ✅ 一致 |
| 3 | 双端队列 | 两端都可插入删除的线性表 | ✅ 一致 |
| 4 | 表达式求值的两步方法 | 中缀转后缀 + 后缀求值 | ✅ 与 3.4.2 末段一致 |
| 5 | 共享栈上溢条件 | 两栈顶相遇才上溢 | ✅ 一致 |
| 6 | 循环队列元素个数计算公式 | (rear-front+MaxSize)%MaxSize | ✅ 一致 |
| 7 | 顺序栈的主要缺点 | "上溢说明预分配的空间不足，是顺序栈的主要缺点" | ⚠️ **轻度失真**：源材料说"上溢说明预分配空间不足"，被表述成"上溢是缺点"（因果倒置的简化） |
| 8 | 括号匹配算法 | 扫描+栈，栈空且扫描完才匹配 | ✅ 与 3.4.1 一致 |
| 9 | 入栈 | 栈顶插入新元素 | ✅ 一致 |
| 10 | 队尾 | 允许插入的一端 | ✅ 一致 |

**知识点准确率 9/10 = 90%**。

**抽样 10 条关系**：

| # | 关系 | 类型/置信度 | 判定 |
| --- | --- | --- | --- |
| 1 | 栈与队列的实现方式 → 栈 | RELATED_TO 0.5 | ✅ |
| 2 | 栈与队列的选用原则 → 队列的应用场景 | RELATED_TO 0.7 | ✅ 合理 |
| 3 | 递归工作栈 → 递归 | RELATED_TO 0.7 | ⚠️ 偏弱（含蕴含关系，用 RELATED_TO 可接受但张力弱） |
| 4 | 栈的后进先出特性 → 队列的先进先出特性 | RELATED_TO 0.8 | ✅ 对照关系正确 |
| 5 | 循环队列 → 循环队列指针变化实例 | CONTAINS 0.5 | ✅ 对应例 3-2 |
| 6 | 栈与队列的选用原则 → 栈的应用场景 | RELATED_TO 0.7 | ✅ |
| 7 | 循环队列 → 循环队列判空与判满 | CONTAINS 0.6 | ✅ |
| 8 | 链队列 → 链队列入队操作 | CONTAINS 0.7 | ✅ |
| 9 | 循环队列指针变化实例 → 循环队列指针后移公式 | EXAMPLE_OF 0.6 | ⚠️ 偏弱（公式属实例所用规则，非实例的"例子"） |
| 10 | 队列的基本操作 → 出队 | CONTAINS 0.9 | ✅ |

**关系准确率 8/10 = 80%**。两项抽样均高于 70% 标红线。

另记录产品自带审核队列发现的问题（与我的抽样一致）：疑似重复 1 组（「队列的典型应用」vs「队列的典型应用场景」相似度 0.778），孤立点 3 个。

### 3.3 R9 五问明细

| # | 范围 | 问题 | final.status | 引用数 | 首字 | 总耗时 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 课内 | 栈的操作特性是什么？ | `answered` | 1 | 2647 ms | 2.77 s |
| 2 | 课内 | 循环队列判断队满的条件是什么？ | `answered` | 1 | 3957 ms | 4.12 s |
| 3 | 课内 | 链栈与顺序栈相比有什么优点？ | `answered` | 3 | 10516 ms | 10.99 s |
| 4 | 课内 | 表达式求值通常分哪两步？ | `answered` | 1 | 2697 ms | 2.87 s |
| 5 | 课外 | 二叉树的三种遍历方式分别是什么？ | **`not_covered`**（`reason=insufficient_evidence`） | **0** | — | 5.06 s |

引用均可溯源到源材料章节（例：`ch3-stack-queue.md · 第3章 栈与队列 > 3.2 栈 > 3.2.1 栈的定义 > 第1段`）。课外问题界面文案为"资料未覆盖 / 检索到的课程资料不足以回答这个问题 / 这条回答没有出处"，并给出"在图谱中查看"引导（截图 `student-04-qa-2.png`）。**全部 5 问总耗时 < 15 s 验收口径**，最慢 10.99 s。

## 4. 失败与重做记录

| 项 | 情况 | 处理 | 是否影响判定 |
| --- | --- | --- | --- |
| 网络门禁（§3） | 第 1 轮 5 次探测中出现 **1 次 `connection`（4.00 s）**，连续计数归零；随后 3 次连续 `ok` 放行 | 按 §3 规则等待并要求连续 3 次 ok，未硬上传 | 否 |
| R2 抽取阶段 | `model_calls` 记录 **2 次 `extract_entities` 状态 `error`、`error_class=connection`**（14:22 时段） | 产品内部重试后成功（16 次 ok）；未做人工重做 | 否（但见观察 1） |
| R9 课外问题 | `meta` 事件上报 `status=answered`，与 `done.final.status=not_covered` 矛盾 | 前端按 `final` 渲染，用户可见结果为"资料未覆盖"；作为内部一致性问题记录 | 否 |
| R10 测试连接 | 注入无效密钥 → `error_class=auth` | 未保存、未污染已存配置（`key_hint=5c37` 不变），未重试 | 否 |
| 我的工具问题（非产品） | ① zsh `read -p` 不可用导致凭据空值；② PATCH kp 缺 `expected_revision`；③ 进度 PUT 载荷形状；④ 进度 GET 字段名；⑤ canvas 渲染导致文本选择器选不中节点 | 均为我的调用方式错误，逐项修正后重做（产品返回 422/提示均正确） | 否 |
| 阶段观测 | 轮询 3 s 一次，未捕获独立 `parsing`/`fusing` 标签 | 用 `model_calls` 时间线 + `progress` 序列重建（§3.1），未编造阶段 | 否 |

网络门禁等待总时长：本轮共进行 **2 轮门禁**（R2 前、R9 前），均一次通过（各自连续 3 次 ok，累计等待 < 1 分钟）。

## 5. 观察（体验问题与待决定事项）

1. **`meta` 事件状态与最终状态不一致（建议修）**：课外问题 `meta.status=answered`、`done.final.status=not_covered`。当前前端以 `final` 为准，用户可见结果正确；但任何依赖 `meta` 的消费方（含未来的流式 UI、埋点、第三方客户端）都会把"未覆盖"读成"已回答"。建议 `meta` 不预置 `answered`，或明确文档化"以 final 为准"。
2. **向量模型配置的两套口径（需澄清）**：验收开始前 `GET /api/v1/me/embedding-config` 返回 `configured=false`，而 R1 的页面显示"**向量模型已配置** · text-embedding-v4 · 1024 维 · 密钥 ••••Xo3G"。即 `configured=false` 时界面仍展示"已配置"。需确认这是"继承安装级默认值即视为已配置"的有意设计还是展示瑕疵。
3. **同一页面两个同名"测试连接"按钮**：通用模型区块与向量模型区块各有一个"测试连接"，无上下文区分，自动化定位有歧义（我显式限定为左侧通用模型区块）。建议按钮文案区分（如"测试通用模型连接"）。
4. **登录态未持久化**：登录后 `storageState` 中 **0 cookie、无 localStorage**，刷新/新会话需重新登录。对真人无碍，但对自动化与"刷新后仍在"类验收有影响（R8 的刷新验证依赖服务端重新取会话，仍然通过）。
5. **审核队列未清空也能发布**：队列中尚有 1 个疑似重复 + 3 个孤立点，`POST /publish` 仍返回 200 成功。若产品意图是"必须处理完队列才能发布"，则为缺陷；若是有意允许带警告发布，建议在发布确认页展示队列摘要。
6. **图谱页节点为 canvas 渲染**：无法通过可访问性文本定位，只能点选推荐列表或搜索；从无障碍/自动化角度建议为节点提供 DOM 镜像或 aria 标签。
7. **网络偶发失败会打进来（但被吸收）**：本次至少 3 次 `connection` 级失败（门禁 1 次、R2 抽取 2 次），产品内部重试全部吸收，最终 0 任务失败。鉴于前两份报告已确认"产品对向量调用没有重试"，建议明确记录**哪些路径有重试、哪些没有**（本次观测到抽取有、问答未见）。
8. **R2 未观测到独立"解析"阶段标签**：任务从 `extracting` 起步，`progress` 从 0.125 开始。若规格要求展示"解析"阶段，需确认其是否应作为独立可见阶段。

## 6. 密钥与边界声明

- **未读、未打印、未复制**安装目录 `.env` 的任何内容；凭据仅经环境变量/一次性文件进入内存，用完即删（最后一次删除后文件不存在）。
- 报告与日志中**不含任何明文密钥或口令**；仅出现 `key_hint` 末 4 位（教师 `5c37`、学生 `061f`）与掩码形式 `••••5c37`。学生口令由 `secrets.token_urlsafe` 生成，只写入受保护文件供登录使用，未打印。
- 截图前已确认页面无明文密钥输入框内容（R1 截图中的 API Key 输入框为空，页脚提示"密钥加密保存在服务端"）。
- 未改产品代码、测试、契约、迁移、启动器、`.env.example`、默认配置；未提交、未推送、未合并、未发布。
- `LLM_MODE=personal`、`EMBEDDING_MODE=online` 未改；未降级为 `demo`/`fake`/`local`；未更换供应商/模型/向量地址。
- 未动其他 Docker 资源；未重启 Docker Desktop；未 `down -v`、未删卷。R11 仅重启本安装的 `api-1` 与 `worker-1`，web/neo4j 未动。
- 全程 0 次 `auth` 类"真实配置被拒"错误（R10 的 auth 来自故意注入的无效密钥，属预期）。

## 7. 交付物清单（截图与数据）

- 截图（16 张，存放于 **`/tmp/formal-loop-artifacts/shots/`**，工作区外，避免污染 git）：`r1-01-entry.png`、`r1-02-login.png`、`r1-03-login-filled.png`、`r1-04-after-login.png`、`r1-05-model-settings.png`、`r1-06-test-result.png`、`student-01-home.png`、`student-02-course.png`、`student-03-graph.png`、`student-03-qa.png`、`student-04-qa-1.png`、`student-04-qa-2.png`、`student-graph-after-click.png`、`student-06-node-selected.png`、`student-07-mark-mastered.png`、`student-08-after-reload.png`
- 走查脚本（7 个，**`/tmp/formal-loop-artifacts/scripts/`**，可复跑）：`ui-r1.cjs`、`ui-loop.cjs`、`ui-graph-probe.cjs`、`ui-mark.cjs`、`ui-mark2.cjs`、`ui-mark3.cjs`、`r9-chat.py`
- 数据：`/tmp/r9-results.json`（5 问原始事件）
- 令牌（供 Claude 复核，8 小时有效）：`/tmp/formal-loop-token`（教师）、`/tmp/formal-student-token`（学生，权限 644 建议用后即删）
- 中间产物（非交付）：课程 `62c2d58b698f495f9dfdfbb15bc4ebbc`、任务 `70fb45a0…`、文档 `d735ea17…`，均留在隔离安装内供 Claude 复核

## 8. 给 Claude 的下一步建议

1. 按 §5 逐项判定观察 1–2 是否属于要修的问题（两者都是"用户可见结果正确、内部/展示口径不一致"型）。
2. 若确认 §5-5（带未处理队列发布）为缺陷，需要补充"发布前必须处理队列"的规格与测试。
3. 业务闭环本身已跑通：上传 → 抽取 → 融合 → 持久化 → 审核 → 发布 v1 → 学生浏览/标记/问答，全部有服务端与界面双证据。
4. 用量余量充足（112,491 / 800,000），若需要更长的抽取评测或多轮问答，预算允许。
