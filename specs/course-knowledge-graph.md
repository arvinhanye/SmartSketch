# 功能规格：课程知识图谱 MVP

- **状态**：DRAFT
- **负责人**：产品 / 后端 / 前端共同维护
- **关联任务**：M1-01 ~ M1-05

## 用户故事

作为教师，我能为一个课程上传资料并得到可审核的草稿知识图谱；作为学生，我能只查看已发布图谱，并据此理解学习顺序与每条知识的来源。

## 数据与规则

- 节点至少含：`id`、`course_id`、`name`、`definition`、`confidence`、`status`、`source_refs`。
- 关系至少含：`id`、`course_id`、`type`、`from_id`、`to_id`、`confidence`、`source_refs`。
- `type ∈ {CONTAINS, PREREQUISITE, RELATED_TO, EXAMPLE_OF}`。
- `PREREQUISITE` 语义为 `from_id` 是学习 `to_id` 的前置条件，且同一课程内不得成环。
- 草稿仅教师可编辑；学生 API 只返回已发布版本。

## 验收条件

1. 支持 PDF、DOCX、TXT、Markdown 上传；不支持格式返回明确错误代码。
2. 每次上传返回任务 ID；任务按 `queued → parsing → extracting → merging → awaiting_review → completed/failed` 转换，并能通过 SSE 观察。
3. 图谱查询、编辑和学生浏览均按 `course_id` 隔离。
4. 新增/修改前置关系形成环时操作被拒绝，并返回导致冲突的节点/关系信息。
5. 2D 图谱具备缩放、拖拽、节点详情、关系图例/筛选；节点详情展示至少一个来源。
6. 教师发布后学生可读取该版本；未发布草稿不可由学生读取。

## 待细化

- API 路径、状态 DTO 和错误码由 M0-04 定稿后补入。
- 节点融合阈值、低置信度阈值和版本回滚交互由 M1 设计时补入。
