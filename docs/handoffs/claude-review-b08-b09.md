# 交接：审查 B08/B09（kongsc）、同步 main 并修正 getCourse 404 语义

- `task_id`: REVIEW-B08-B09
- `status`: 审查通过；按 ArvinHan 授权开 PR 并合入
- `审查目标`: `origin/kongsc/b09-contracts` @ `e1c1814`，含 `kongsc/b08-contracts` @ `15dacce`。两个分支都没有开 PR；B09 已合入 B08，一个 PR 覆盖两项任务
- `交接背景`: ArvinHan 2026-09-24 起接手后端；B10 起的后端任务负责人记为 ArvinHan（Claude 执行）

## 同步

合入 `origin/main@afb9760`（含 PR #14、#21），只有 `docs/tasks.md` 冲突：main 各节保持原位，B08、B09 两节接到文末。`.github/workflows/ci.yml` 自动合并（B09 在 scaffold job 安装 `pytest==8.3.5`）。

## 审查结论

- **契约真源**：
  - B08：`ErrorCode` 新增 8 个码；补齐 Bearer 说明、受保护操作的 401、`eventTicket` 安全方案；共享 429 区分 `RATE_LIMITED` 与 `BUDGET_EXCEEDED`。
  - B09：`Course.my_role` 必填；新增成员三操作与 `CourseMember`、`MemberAdd`、`uid`；登录补 429。
  - 与 `specs/identity-access.md` §7、`specs/task-processing.md` §6、ADR-012 交 B08 的项逐条对上。`MemberAdd` 只有 `username`，不含调用者身份。
- **规格与文档改动**：都是 A03/A04/A05/A07 事先要求 B08/B09 完成时顺带做的状态标注（「提议新增」改为「已纳入 B08」，架构 `ErrorCode` 行同步），规则没有变。
- **门禁**：`scripts/verify/contracts.sh` 每次执行 B08、B09 回归；CI 装锁定版 `pytest`，GitHub 运行已验证。

## Claude 修正（本 PR 内）

- **B09-R01（P2，已修）**：`getCourse` 的 404 描述原写「资源不存在，或学生成员读取从未发布的课程」，与已签收的 `specs/identity-access.md` §4.1 第 3、5 步及 IAM-16 冲突：课程不存在与非成员同为 403 `COURSE_FORBIDDEN`，这样 403 不泄露课程是否存在，404 只来自 `GRAPH_NOT_PUBLISHED`。契约是唯一真源，不改会误导 C03/C04 的实现。
  - 先加 `test_get_course_404_is_only_unpublished_for_students`，失败（1 failed / 4 passed）。
  - 再改描述，并用 `./scripts/gen-contracts.sh` 重新生成 `openapi.json`、`openapi.d.ts`。
  - 之后 5 passed，`--check` 一致。

## 已运行命令与结果（macOS）

| 命令 | 结果 |
| --- | --- |
| `./scripts/verify.sh`（合并后、修正后各一次） | exit 0：契约结构、生成物一致、22 项门禁负例、B08 5 passed、B09 5 passed |
| `./scripts/gen-contracts.sh --check` | 生成物与真源一致 |
| `python -m pytest tests/backend -q` | 58 passed（B05/B06 不受契约改动影响） |
| `git diff --check` | exit 0 |

## 其他意见（P3，不阻塞）

- **B08-R01**：scaffold job 的契约工具装 `pytest==8.3.5`，后端包的测试依赖是 `pytest==9.1.1`。两者在不同 job 里，暂不冲突；以后统一版本时一起改 `toolchain.txt`。
- **B09-R02**：`streamTaskEvents` 仍继承全局 Bearer，只补了 401；改为 `eventTicket` 属于 B10 的范围，已在规格 §7 中列出。

## 下一步

- 合入后开始 B10（任务与 SSE 契约），依次是 B11、B13、B12，最后 B14。
