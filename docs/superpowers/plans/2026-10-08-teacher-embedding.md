# Teacher Embedding Implementation Plan

Goal: 教师独立向量设置按本人课程生效，学生页面不变。
Architecture: 教师配置加密入 SQLite；课程解析向量适配器；添加新向量属性后原子切换配置和版本元数据。
Tech Stack: Vue/TypeScript、FastAPI、SQLite、Neo4j、现有 OpenAI compatible adapter。
Spec: docs/superpowers/specs/2026-10-08-teacher-embedding.md

- [x] 任务 1：契约/schema/迁移与教师权限路由，先验证学生拒绝、密钥响应脱敏与维度限制。
- [x] 任务 2：加密仓储、课程配置解析与仅本人课程向量重建；测试失败不切换、锁与不同教师隔离。
- [x] 任务 3：发布/回滚与学生问答按课程解析适配器，保留默认及测试替身兼容；全局离线迁移保护。
- [x] 任务 4：独立教师表单，通用表单风格、供应商/发现/手输模型/维度/测试与保存状态；学生无组件和请求。
- [x] 任务 5：相关测试、合同生成、basic/type-check/build、浏览器角色/窄屏检查；本地备份迁移/重启，交接与 scoped 提交，不推送。

风险验证：服务返回错误维度；迁移中课程新增/锁丢失；学生越权读取密钥；同名不同端点；未配置默认课程。
