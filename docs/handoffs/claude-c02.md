# Claude 交接：C02 课程和成员仓储

- `task_id`: C02（GitHub issue #59）
- `review_status`: ready_for_review（合并前须先处理「需协调方处理」第 1 条）
- `worktree`: `/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/c02-course-repo`，分支 `claude/c02-course-repo`
- `base`: `38ef62d`（认领提交，基于 main `8eeac3b`）；`head` 以分支最新提交为准
- 依据：`specs/identity-access.md` §3.1～§3.3、§4.4、IAM-5/8/24；ADR-013；D-10；`specs/teacher-review-publish.md`「`courses` 增加」；`src/contracts/api.v1.yaml` 的 `Course`、`CourseCreate`、`CourseMember`；C01 迁移器（`connect()` 已开启 `PRAGMA foreign_keys = ON`，本任务测试也断言了这一点）；C13 的 `users` 表

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/migrations/004_courses.sql`（原 003，见下「合并前改号」） | 新表 `courses`、`course_members`，索引 `idx_course_members_user_id`，两个 IAM-24 触发器 |
| `src/backend/app/repositories/courses.py` | `create_course`、`get_course`、`list_member_courses`、`get_member`、`list_members`、`add_member`、`remove_member`；记录类型 `CourseRecord`、`MemberRecord`；异常 `UnknownUser`、`UnknownCourse`、`RoleNotAllowed`（均继承 `ValueError`） |
| `tests/backend/test_c02.py` | 21 个用例（成功、边界、失败路径） |

## 表结构

`courses`：

| 列 | 约束 | 来源 |
| --- | --- | --- |
| `id` | TEXT 主键，长度 32～64；仓储用 `uuid4().hex` 生成 | 规格 §4.1「课程 ID 是随机串」；长度约束与 C13 `users.id` 一致 |
| `name` | NOT NULL，长度 1～120 | `CourseCreate.name` |
| `description` | 可空，长度 ≤ 1000 | `CourseCreate.description` |
| `teacher_id` | NOT NULL，外键 → `users(id)` | §3.2.3，只用于展示 |
| `created_at` | UTC ISO 字符串，默认当前时间 | 与 `users` 同格式 |
| `published_version_id` | 可空，暂无外键 | teacher-review-publish「`courses` 增加」 |
| `published_version` | 可空，≥ 1；与 `published_version_id` 同为空或同非空（表级 CHECK） | 同上，「与指针同事务维护」 |
| `draft_revision` | NOT NULL，默认 0，≥ 0 | 同上 |
| `published_from_revision` | 可空（-1 表示「已知与草稿不同」，由 G 组写） | 同上 |

`course_members`（§3.1）：`course_id` → `courses(id)`、`user_id` → `users(id)`、`role ∈ {teacher, student}`、`added_by` → `users(id)`（可空，命令行添加时为空）、`created_at`；主键 `(course_id, user_id)`。外键都没有 `ON DELETE` 动作（`NO ACTION`，即有成员行时不能删课程或用户）。

## 关键决定

1. **IAM-24 在数据库层用触发器保证。** `BEFORE INSERT` 和 `BEFORE UPDATE OF role, user_id`：当 `role = 'teacher'` 而对应账号类型不是 `teacher` 时 `RAISE(ABORT)`。规格要求「包括经命令行」也要拒绝，放在触发器里，任何写入路径（仓储、C14 命令行、手写 SQL）都绕不过去。用户不存在时触发器不拦，交给外键报错，这样错误能区分开。仓储把触发器错误转为 `RoleNotAllowed`。
2. **建课与创建者成员行同一事务**（`BEGIN IMMEDIATE`），供 C04 的 IAM-2 使用。创建者是学生账号时成员行被触发器拒绝，课程行随之回滚；测试已断言数据库无变化。「只有教师账号能建课」的检查仍归 C04 服务层，这里只是兜底。
3. **`add_member` 返回 `(行, 是否新建)`；已是成员时原样返回，不改角色、`added_by`、`created_at`**（`ON CONFLICT DO NOTHING`）。C15 可以直接据此返回 200/201（§3.3、IAM-8）。
4. **不删课程，删除不级联。** 规格没有删除课程的操作，仓储也不提供；外键用默认 `NO ACTION`：有成员行的课程和用户都删不掉。用户本来就只停用不删除（§1.1），`added_by` 引用的用户也受保护。
5. **仓储不写业务规则**：§4.4 学生只见已发布课程的过滤（C04）、按用户名添加时拒绝停用账号（C15）、只能移除学生成员和「每门课至少一个教师」（C15/C14），都留给调用方。`list_member_courses` 返回用户所在的全部课程及其课程内角色，不过滤。
6. **发布指针列放在本迁移。** 规格把它们定义在 `courses` 上，C04 列课程需要 `published_version`，而 C04 没有迁移文件。这几列只建列，不写任何发布逻辑；`published_version_id` 的外键须由 G02 建 `graph_versions` 后再决定（SQLite 加外键要重建表，见风险）。
7. **`created_at` 相同时按 `rowid` 排序**，成员列表按加入顺序输出，结果稳定。

## 实际运行的命令与结果（macOS，Python 3.13.5）

环境：`python3 -m venv <scratchpad>/venv-c02 && <venv>/bin/pip install -e './src/backend[test]'`；下表中的 `pytest` 都指该 venv 的 `python -m pytest`。系统 `python3` 没有安装 `app` 包，`python3 -m pytest tests/backend/test_c02.py -q` 在收集阶段报 `ModuleNotFoundError`（exit 2），与本任务无关，以往交接也都用 venv。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 基线（开工前） | `pytest tests/backend -q` | 720 passed，exit 0 |
| 红灯（只有测试） | `pytest tests/backend/test_c02.py -q` | exit 2，收集阶段 `ImportError: cannot import name 'courses' from 'app.repositories'`，0 passed |
| 绿灯 | `pytest tests/backend/test_c02.py -q` | 21 passed，exit 0 |
| 反向篡改 M1 | 删掉两个 IAM-24 触发器 | 2 failed（`test_create_course_is_atomic_when_the_member_row_is_rejected`、`test_student_account_can_never_be_a_teacher_member`） |
| 反向篡改 M2 | `remove_member` 的 DELETE 去掉 `course_id` 条件 | 2 failed（`test_one_user_holds_independent_roles_in_different_courses`、`test_reads_and_deletes_are_scoped_by_course`） |
| 反向篡改 M3 | `ON CONFLICT DO NOTHING` 改为 `DO UPDATE SET role, added_by` | 1 failed（`test_member_is_unique_per_course_and_readding_changes_nothing`） |
| 反向篡改 M4 | `course_members.course_id` 外键加 `ON DELETE CASCADE` | 2 failed（外键结构用例、删除受限用例） |
| 恢复 | 从备份拷回并 `shasum -c` | 两个文件校验一致；复跑 21 passed |
| 全部后端 | `pytest tests/backend -q` | **1 failed / 740 passed，exit 1**。失败的是 `test_c13.py::test_migration_002_adds_users_after_001_and_keeps_a_restorable_backup`：`assert ['002', '003'] == ['002']`（见「需协调方处理」第 1 条） |
| 门禁 | `./scripts/verify.sh` | `Scaffold verification passed.`，exit 0 |
| 空白 | `git diff --check`（新文件已 `git add -N`） | exit 0 |
| 回滚演练 | 临时库：用只含 001、002 的目录迁移，写一个用户，再迁移到 003 并建课；删除库文件及 `-wal`/`-shm`，换成 `backups/*-before-003.sqlite` | `pending_migrations` 返回 `['003']`，用户保留，`courses` 表不存在 |

## 数据模型变更与回滚

- 新增迁移 `003_courses.sql`：两张新表、一个索引、两个触发器，不改已有表。C01 迁移器在应用前自动生成 `backups/<时间>-before-003.sqlite` 并做完整性检查（测试已验证备份中没有新表、原有数据保留）。
- **回滚**：停止 API 与 worker，按 `src/backend/README.md`「SQLite 迁移与恢复」，把数据库文件（连同 `-wal`、`-shm`）换成 `before-003` 备份；代码回退到不含 `003_courses.sql` 的提交，否则启动门禁会因有未执行迁移而拒绝启动。迁移器只向前，不写 down 脚本。回滚会丢掉迁移后写入的课程与成员数据。
- **D-10**：当前 main 最大编号为 002，本迁移取 003。**合并前若 main 已有 003（或更大），须改名为新的「最大 + 1」**，同步改 `test_c02.py` 里的 `"003"`、`003_courses.sql`、`before-003` 三处，并重跑迁移测试。
- 无接口、配置、依赖变化。

## 需协调方处理

1. **`tests/backend/test_c13.py` 与任何新迁移冲突（越出本任务文件锁，未修改）。** `test_migration_002_adds_users_after_001_and_keeps_a_restorable_backup` 对真实迁移目录断言 `migrate(...) == ["002"]` 以及 `schema_migrations` 恰为 `["001", "002"]`。只要新增 003，它就会失败，C06、C16 等后续迁移也一样。和 C13 当初处理 `test_c01.py` 的做法相同，建议改为对只含 001、002 的临时目录断言，例如：

   ```python
   # 用只含 001、002 的目录代替真实目录
   upto_002 = tmp_path / "upto-002"
   upto_002.mkdir()
   for name in ("001_base.sql", "002_accounts.sql"):
       (upto_002 / name).write_bytes((BACKEND / "migrations" / name).read_bytes())
   assert migrate(_url(path), upto_002) == ["002"]
   assert migrate(_url(path), upto_002) == []
   ```

   用例的其余断言不变。

   **已处理（协调方，2026-09-25，范围扩展）**：按上述方案以单独提交并入本分支，只改该用例的迁移目录（`through-002`），其余断言不变；协调方复跑 `tests/backend` 741 passed（venv，`PYTHONPATH=src/backend`）。
2. **`docs/architecture.md` 未改**：「核心数据模型」SQLite 一行没有单列 `course_members`、`users`（ADR-013 后果里记着「`users`、`course_members` 已在 ADR-008 命名基线内」）。按共享文件规则不改，交 A10/协调方判断是否补登。
3. **`published_version_id` 的外键**：G02 建 `graph_versions` 后，要不要让 `courses.published_version_id` 引用它，由 G02 决定。SQLite 不能给已有列加外键，只能重建表，所以尽早决定为好；不加也行，发布指针靠 CAS 事务维护。

## 风险与未验证

- 触发器只在写 `course_members` 时检查账号类型。若日后允许修改 `users.role`（MVP 不支持），教师改成学生后已有的教师成员行不会被拦截。
- `create_course`、`add_member` 出错后通过回查判断是哪个外键失败（SQLite 不报外键名），与 C13 的做法相同。回查在回滚之后进行，并发删除用户时可能归错类，但 MVP 没有删除用户的路径。
- 没有在 Windows 或 CRLF 检出上运行；`.gitattributes` 已把迁移文件固定为 LF。
- 没有做并发压力测试。`add_member` 在 `BEGIN IMMEDIATE` 内先插入再读取，同一成员并发添加时只有一个返回 `created=True`，但这点没有专门的测试。

## 下一步

- **C03**：`get_member(course_id, user_id)` 返回 `None` 即非成员（403 `COURSE_FORBIDDEN`），否则按 `.role` 判定课程内角色；课程不存在同样返回 `None`，满足 IAM-16「不存在的课程也给 403」。
- **C04**：建课调用 `create_course`（先检查账号类型是教师）；列课程用 `list_member_courses`，再过滤掉「角色为 `student` 且 `published_version is None`」的项（§4.4）；`my_role` 就是返回的角色。`status` 按 ADR-012 决定 7 从三个修订列推导。
- **C15**：添加学生前用 `accounts.find_by_username` 查出用户，停用或不存在就返回 404，再调用 `add_member(role="student", added_by=调用者)`，按 `created` 返回 201 或 200；移除前用 `get_member` 确认目标是学生。

## 合并前改号与同步（协调方，2026-09-25）

- Codex 的 C06（PR #209）先合入 main，占用 `003_tasks.sql`。按 D-10，本任务迁移改名为 **`004_courses.sql`**；上文「003」「before-003」在合并后均应读作「004」「before-004」（回滚用 `backups/*-before-004.sqlite`）。
- `test_c02.py` 迁移用例改为：先用只含 001～003 的目录迁移，再用只含 001～004 的目录断言只应用 `004`，后续迁移不再影响该用例。
- `test_c13.py`：C06 把断言写死为 `["002", "003"]` / `["001", "002", "003"]`，合并时取本分支「只含 001、002 的临时目录」写法并把 `schema_migrations` 断言恢复为 `["001", "002"]`。
- `test_c06.py`（范围扩展）：夹具 `assert migrate(url) == ["001", "002", "003"]` 改为只断言前三项，否则 004 加入后 C06 全部用例报错。
- 同步时发现 main 缺陷：C01 迁移器对无 `lease_expires_at` 列的 `processing_tasks`（C06 建、C09 才加租约列）报 `Cannot inspect processing_tasks lease state`，使 003 之后任何迁移都无法应用。已在 `claude/fix-migrate-lease-guard` 单独修复（先写复现测试），并并入本分支；见 `docs/handoffs/claude-fix-migrate-lease.md`。
