# 功能规格：课程知识图谱 MVP

- **状态**：DRAFT（「前置关系成环处理」与枚举取值已由 A02 签收，见 ADR-009）
- **负责人**：产品 / 后端 / 前端共同维护
- **关联任务**：M1-01 ~ M1-05

## 用户故事

作为教师，我能为一个课程上传资料并得到可审核的草稿知识图谱；作为学生，我能只查看已发布图谱，并据此理解学习顺序与每条知识的来源。

## 数据与规则

- 节点至少含：`id`、`course_id`、`name`、`definition`、`confidence`、`status`、`source_refs`。
- 关系至少含：`id`、`course_id`、`type`、`from_id`、`to_id`、`confidence`、`status`、`source`、`source_refs`。`status` 与节点共用 `draft | low_confidence | approved | rejected`，`source ∈ {ai, manual}`；下文成环处理依赖这两个字段。
- `type ∈ {CONTAINS, PREREQUISITE, RELATED_TO, EXAMPLE_OF}`。
- `PREREQUISITE` 语义为 `from_id` 是学习 `to_id` 的前置条件，且同一课程内不得成环。
- 草稿仅教师可编辑；学生 API 只返回已发布版本。
- 所有端点前缀 `/api/v1`（`/health` 除外）；枚举取值与大小写以 `docs/architecture.md`「API 前缀与 wire 枚举」为准，本规格不另列一份。

### 前置关系成环处理（A02 / ADR-009）

**参与环检测的边**：同一课程草稿中 `type = PREREQUISITE` 且 `status ≠ rejected` 的边。

**可被自动降级的边**：`source = ai` 且 `status ∈ {draft, low_confidence}`，即未经教师确认的 AI 边。`source = manual` 或 `status = approved` 的边视为教师已确认，自动流程**永不**改动它们。

人工编辑与自动候选按来源区分处理，二者不可混用：

| 来源 | 触发路径 | 处理 | 结果 |
| --- | --- | --- | --- |
| **人工编辑** | 新建关系（`POST /api/v1/courses/{cid}/relations`）；改关系类型为 `PREREQUISITE`、改端点、反转方向、把 `rejected` 恢复为有效（`PATCH .../relations/{rid}`）；合并知识点后重接边（`POST .../kp/merge`）；`from_id = to_id` 的自环 | 写入前检测；成环则整个操作不写入 | 409 `CYCLE_DETECTED`，`details.cycle` 为首尾相同的节点 ID 链。**不自动修复，不降级任何边**，由教师自行决定改哪条 |
| **自动候选** | worker `persisting` 阶段写入草稿前 | 按下方降级算法逐环消解 | 任务照常进入 `awaiting_review`；被降级的边进入审核队列「低置信度关系」 |
| **自动候选，但环上没有可降级边** | 同上 | 不降级已确认边 | 任务 `failed`，`error.code = CYCLE_DETECTED`，带 `details.cycle`。只可能在草稿已违反不变量时出现 |
| **发布** | `POST .../publish` | 发布前全图复检 | 409 `PUBLISH_BLOCKED`，`details.reasons` 含环路；不产生版本 |

**降级算法**（自动候选专用，结果必须可复现）：

1. 自动候选中的自环（`from_id = to_id`）在抽取规则校验阶段直接删除并记日志（S2「删除自环」），不进入本算法。
2. 把本批候选与草稿中现有的参与边合成一张图，按边 `id` 升序遍历邻接做 DFS 找环。
3. 找到环后，在环上的可降级边里选 `confidence` 最低者；并列时取 `id` 字典序最小者。
4. 把该边 `type` 改为 `RELATED_TO`、`status` 改为 `low_confidence`，保留 `from_id`、`to_id`、`confidence`、`source_refs`。
5. 重复 2～4 直到无环，再写入草稿。每轮只降级一条，不承诺全局降级条数最少。

教师把降级边改回 `PREREQUISITE` 属于人工编辑，走上表第一行：环仍在则 409，环已被其他修改打破则允许。

**成环处理验收**（独立编号，不占用下方主验收序号）：

- 成功路径
  - **DAG-1** 已有有效边 B→C、C→A，教师新建 A→B → 409 `CYCLE_DETECTED`，`details.cycle` 为 `[A, B, C, A]` 的某个旋转；草稿无任何变化。
  - **DAG-2** 自动抽取产出 A→B（0.9）、B→C（0.8）、C→A（0.4），均为 `ai`/`draft` → C→A 变为 `RELATED_TO` + `low_confidence`，另两条保持 `PREREQUISITE`；任务到 `awaiting_review`，审核队列出现 C→A。
- 边界路径
  - **DAG-3** 环上可降级边置信度并列 → 降级 `id` 字典序最小者；同一输入重跑，降级结果完全相同。
  - **DAG-4** 教师已确认 A→B、B→C（`manual` 或 `approved`），自动候选 C→A 置信度 0.95 → 仍降级 C→A；已确认边不变。
  - **DAG-5** 一批候选含两个环（共享边或互相独立）→ 逐环消解直到无环；任务不失败。
  - **DAG-6** 教师把 DAG-2 中被降级的 C→A 改回 `PREREQUISITE`：A→B、B→C 仍有效时 409；教师先把 B→C 置为 `rejected` 后再改则允许。
  - **DAG-7** `status = rejected` 的 `PREREQUISITE` 边不参与环检测；把它恢复为有效且会成环 → 409。
  - **DAG-8** 已有 A→B、B→C，教师合并 A 与 C → 合并后形成 M→B→M，409，合并不生效。
  - **DAG-9** 自动候选自环 A→A → 规则校验阶段删除，不降级、不使任务失败；教师新建自环 A→A → 409，`details.cycle = [A, A]`。
- 失败路径
  - **DAG-10** `persisting` 时草稿中已存在一个全由已确认边组成的环 → 任务 `failed`，`error.code = CYCLE_DETECTED` 并带环路；不静默降级已确认边。
  - **DAG-11** 发布时图中含环（任意来源）→ 409 `PUBLISH_BLOCKED`，不产生新版本，学生仍读旧版本。

## 验收条件

1. 支持 PDF、DOCX、TXT、Markdown 上传；不支持格式返回明确错误代码。
2. 每次上传返回任务 ID；任务按 `queued → parsing → extracting → merging → persisting → awaiting_review → completed` 转换。处理阶段（直到 `awaiting_review`、`failed` 或 `cancelled`）可通过 SSE 观察；`awaiting_review` 表示处理完成，SSE 在此关流；`completed` 由教师发布触发，通过任务查询 `GET /api/v1/tasks/{tid}` 或课程发布状态观察，不经已有 SSE 连接送达；`failed` 只能从 `parsing`～`persisting` 转入，`cancelled` 只能从 `queued`～`merging` 转入。终态为 `completed`、`failed`、`cancelled`。转换表、取消协议、部分失败与重连见 `specs/task-processing.md`（A03 / ADR-010）。
3. 图谱查询、编辑和学生浏览均按 `course_id` 隔离。
4. 人工新增/修改前置关系形成环时操作被拒绝，并返回导致冲突的节点/关系信息；自动候选成环按上方「前置关系成环处理」降级，不拒绝整个任务。
5. 2D 图谱具备缩放、拖拽、节点详情、关系图例/筛选；节点详情展示至少一个来源。
6. 教师发布后学生可读取该版本；未发布草稿不可由学生读取。

## 待细化

- API 前缀已定为 `/api/v1`（A02 / ADR-009）；状态 DTO 与错误码以 `src/contracts/api.v1.yaml` 为准（目前在 `740adb` 分支，随 A10 导入 main）。
- **降级边的来源标记（交 B11）**：`Relation` 目前没有字段记录「原为 `PREREQUISITE`、因哪条环降级」，审核队列无法向教师解释为何出现一条 `RELATED_TO`。须先在 `api.v1.yaml` 增加字段（例如原类型与环路）并重新生成，F13 才能实现降级；不得用 `definition` 等自由文本字段临时承载。
- 降级条数是否计入任务统计：`TaskCounts` 暂无对应字段，随上一条同批决定。
- 节点融合阈值、低置信度阈值和版本回滚交互由 M1 设计时补入。
