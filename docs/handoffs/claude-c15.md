# Claude 交接：C15 实现课程成员管理 API

- review_status: ready_for_review
- task_id: C15（GitHub issue #162）
- worktree：`.claude/worktrees/c15-course-members`，分支 `claude/c15-course-members`
- base：认领提交 `bdcf165`；head：本交接所在提交
- 状态：DONE（待 PR 审查/合并）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/members.py` | §3.3 规则：`list_course_members`、`add_student_member`（按用户名、角色固定 `student`、已是成员原样返回）、`remove_student_member`（只删学生成员） |
| `src/backend/app/api/members.py` | `GET/POST /api/v1/courses/{cid}/members`、`DELETE /api/v1/courses/{cid}/members/{uid}`，operationId 为 `listMembers`、`addMember`、`removeMember`；授权复用 C03 的 `course_teacher` 依赖 |
| `src/backend/app/main.py` | 只加路由的 import 和 `include_router` 两行 |
| `tests/backend/test_c15.py` | 26 个用例 |

没有改仓储、迁移或契约。复用了 C02 的 `list_members`、`add_member`、`get_member`、`remove_member`，C13 的 `find_by_username`，以及 `services.auth.normalize_username`。

## 关键决定

- **授权顺序**按 §4.1：401 `UNAUTHENTICATED` → 非成员或课程不存在时同形 403 `COURSE_FORBIDDEN` → 学生成员（包括账号类型是教师、但在本课是学生成员的人）403 `ROLE_FORBIDDEN`。
- **添加**：用户名先转小写再查（与登录一致）。用户名不存在和账号已停用返回同一个 404 `NOT_FOUND`。新加入返回 201。已是成员（任意角色）时返回 200 和原成员行，角色和 `added_by` 都不变，所以教师成员不会被降级。请求体里多余的 `role` 字段被忽略，新成员一律是 `student`。教师账号可以作为学生成员加入（§3.2.1）。
- **学生账号只能做学生成员**：API 从不写 `teacher` 成员行。C02 的仓储触发器仍会拒绝写入（`RoleNotAllowed`），测试里有覆盖。
- **移除**：目标不是本课成员（包括只是别的课的成员）返回 404 `NOT_FOUND`。目标是教师成员（包括自己）返回 403 `ROLE_FORBIDDEN`，成员关系不变。学生成员被删除后返回 204、响应体为空。检查之后、删除之前若被并发删除，返回 404。
- **DTO**：`CourseMember` 和 `MemberAdd` 直接取自生成的契约模块。`app/schemas/contracts.py` 目前没有把这两个模型再导出，它又不在本任务的文件锁内，所以 `services/members.py` 通过 `contracts._module` 取用，没有另写一套 DTO。

## 验证（实际命令与结果）

在 worktree 根目录执行，`S` 是本会话 scratchpad，其中新建了独立的 venv（`python3 -m venv $S/venv`，并在本 worktree 执行 `pip install -e './src/backend[test]'`）：

| 命令 | 结果 |
| --- | --- |
| 实现前：`PYTHONPATH=$PWD/src/backend $S/venv/bin/python -m pytest tests/backend/test_c15.py -q` | 25 failed、1 passed（先写测试，确认失败；通过的那个是仓储触发器用例） |
| 实现后：同一命令 | 26 passed |
| `PYTHONPATH=$PWD/src/backend $S/venv/bin/python -m pytest tests/backend -q` | 2547 passed，1 warning（starlette 的 httpx 弃用提示） |
| `PATH=$S/venv/bin:$PATH ./scripts/verify.sh` | `PASS contracts gate`、`Scaffold verification passed.` |
| `git diff --check` | 无输出 |

## 接口与数据变化

- 新实现契约中已经存在的 3 个操作，契约没有变化。
- 没有数据模型或迁移变化。

## 与任务说明不一致之处（按规格实现）

- 派工说明写的是「非成员/课程不存在 404 同形拒绝」，而 `specs/identity-access.md` §4.1、§4.2、§4.3 与契约（`listMembers` 等只声明了 403）规定，路径带 `cid` 时返回 **403 `COURSE_FORBIDDEN`**。按规格实现为 403，并且两种情形同形。只有「移除的目标不是成员」和「添加时用户名不存在」返回 404 `NOT_FOUND`。

## 风险

- 移除时先读角色、再按 `(course_id, user_id)` 删除，两步不在同一事务里。如果命令行工具恰好在两步之间把该学生改成教师，这个教师行可能被删掉。MVP 中 API 不会改角色，只有命令行会改，窗口很小。要彻底消除，需要在仓储里加 `DELETE ... AND role = 'student'` 形式的函数，但这需要改 `repositories/courses.py`，超出本任务文件锁，所以没有改。
- `contracts._module` 是私有属性访问；以后若 `app/schemas/contracts.py` 调整了加载方式，需要同步修改。

## 待决

1. 是否在 `app/schemas/contracts.py` 中导出 `CourseMember`、`MemberAdd`（后端契约负责方决定；导出后把 `services/members.py` 的取用改为普通 import 即可）。
2. 是否给 C02 仓储补一个「只删学生成员」的原子删除函数，以消除上面的竞态（需要改 `repositories/courses.py`）。
3. 派工说明里「非成员 404」与规格「403 `COURSE_FORBIDDEN`」不一致，请协调方确认以规格为准。

## 回滚

`git revert` 本任务提交，或删除 `api/members.py`、`services/members.py`、`tests/backend/test_c15.py`，并从 `main.py` 移除那两行。不涉及数据库迁移。

## 下一步

- 前端成员管理页面可以直接对接这 3 个操作。
- `getCourse`（`GET /api/v1/courses/{cid}`）尚未实现。本任务的「移除后失去访问」用例改用 `listDocuments` 验证成员检查。
