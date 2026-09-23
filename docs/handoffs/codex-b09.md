# B09 交接：课程与资料 REST 契约

- task_id：B09
- 状态：DONE（本地，审查问题已修复，待集成）
- 工作树：`C:/Users/asus/Desktop/SmartSketch/.worktrees/b09-contracts`，分支 `kongsc/b09-contracts`
- 基线：`kongsc/b08-contracts@21253f8`；B09 初次交付 `77156c9`，本轮纳入 B08 修复 `15dacce`
- 审查修复：B09 专项测试已接入统一门禁；本轮完成后以新提交为准

## 交付物与决定

- `src/contracts/api.v1.yaml`：`Course.my_role` 必填；课程列表仅返回调用者有成员关系的课程，学生成员的课程须曾发布；登录增加 429，课程详情 404 明确 `GRAPH_NOT_PUBLISHED`。
- 增加 `listMembers`、`addMember`、`removeMember` 三个操作及 `CourseMember`、`MemberAdd`、`UserId`。新成员仅按用户名添加为学生；已是成员时 200 返回原角色，新加入时 201；只能移除学生，成功为 204。
- 现有课程创建、详情、资料列表与上传响应保持原路径和 DTO；`tests/contracts/test_b09.py` 固定其成功、认证、权限和上传失败响应。请求 schema 不定义表示调用者身份的 `user_id` 字段。
- 重新生成 OpenAPI JSON、Python 模型与 TypeScript 类型；同步 `src/contracts/README.md` 的路径数及 `specs/identity-access.md` 的 B09 状态。
- 审查修复将 `tests/contracts/test_b09.py` 纳入 `scripts/verify/contracts.sh`；并纳入 B08 的 429 响应语义及 B08 门禁修复。

## 验证

- 测试先红：`python -m pytest tests/contracts/test_b09.py -q` 为 4 failed（缺角色字段、成员操作与 DTO 等）。
- 实现后：`python -m pytest tests/contracts/test_b09.py tests/contracts/test_b08.py -q` 为 8 passed。
- `python scripts/check_contracts.py`：24 条路径、61 个 schema、234 处 `$ref`，结构与命名检查通过。
- `./scripts/gen-contracts.sh --check`：生成物与真源一致。
- `./scripts/verify.sh`：hook 回归、契约结构、生成物漂移和 22 项契约负例通过，exit 0。
- `git diff --check`：exit 0。

审查修复轮：先确认统一门禁没有调用 B09 测试，再补入执行；`./scripts/gen-contracts.sh --check` PASS；`./scripts/verify.sh` exit 0（22 项门禁负例、B08 5 项、B09 4 项）。

Windows 上通过 Git Bash 和临时命令别名运行 `.sh`；别名不属于交付物。

## 接口、风险与下一步

- 本轮只改变协议和生成类型，不新增数据库迁移、运行时端点或环境变量。`Course.my_role` 是新必填字段，后续 C04/C03 必须按课程成员行填充，前端用它选择课程视图。
- A10 批 1 仍待集成；B09 已纳入 B08 修复，集成时仍须保留 A10 → B08 → B09 的依赖顺序。实际成员权限、列表过滤和事务语义由 C03/C04/C15 实现；契约测试不证明运行时行为。
- 首个后续动作：按依赖执行 B10 或推动 B05/A10 与 B08/B09 集成，再做后端运行时联调。
