# K09 交接：示例课程幂等导入（Claude）

- 分支：`claude/impl-k09`（git worktree `.worktrees/impl-k09`），基线 `9fe21bd`（含 `main@f6325fe`）。
- 决定：ADR-077（待 ArvinHan 审阅）。
- 原子清单条目：K09「实现示例课程幂等导入 / 输入：自编课程包 / 输出：一键演示数据 / 验收：重跑不重复；只写示例课；失败可重试；不混入真实资料或删除他课」。

## 交付物

| 文件 | 说明 |
| --- | --- |
| `datasets/demo/manifest.json` | 示例包真源：`schema_version=1`、`notice`（声明自编、不是真实课程资料）、`course`（名称/描述）、`documents`（相对路径 / 标题 / 格式 / 内容 `sha256` / 说明） |
| `datasets/demo/documents/linear-structures.md` | 自编讲义：线性表、栈、队列（Markdown） |
| `datasets/demo/documents/trees.txt` | 自编讲义：树、二叉树、二叉搜索树（TXT） |
| `datasets/demo/README.md` | 示例包说明：自编声明、manifest 结构、格式覆盖面与扩格式方法 |
| `scripts/import-demo.py` | 幂等导入脚本（唯一执行入口，无需命令行密钥） |
| `tests/integration/test_k09.py` | 20 个集成用例（真实 SQLite 临时库；1 条真实 Neo4j 用例） |
| `docs/decisions.md` | ADR-077 |
| `docs/tasks.md` | K09 小节 |
| `docs/handoffs/claude-k09.md` | 本文件 |

**范围说明（超出原子清单的 `allowed_files`，但为交付要求所必需）**：`datasets/demo/documents/*` 两个正文文件与
`datasets/demo/README.md`。原子清单只列了 `datasets/demo/manifest.json`，但「自编课程包」必须有正文文件，
manifest 才有可指向的资料。`docs/*` 三项为任务书显式要求。**未触碰** `src/backend/`、`src/frontend/`、
`src/contracts/`、其他任务的文件锁、K12 的 `docs/runbook.md`（未创建）。

## 示例课程包内容概要

- 课程名：**示例课程：数据结构导论**（ADR-077 定为演示课保留名）；描述见 manifest。
- 资料数：**2 条**；格式：**Markdown + TXT（2 种，满足赛题「格式 ≥ 2 种」）**。
- 内容：线性表 / 栈 / 队列 / 树 / 二叉树 / 二叉搜索树的定义句 + 3 条「学习 X 之前需要先掌握 Y」先修句，
  段落短、句子完整，便于解析器切句与抽取器演示；全部为自编合成素材，无版权与个人信息风险。

## 接口 / 数据变更

- **无** API、契约（`src/contracts/`）、数据库迁移、DTO 变更。改动只在脚本、示例数据与三个文档。
- 复用既有约定：`processing_tasks.idempotency_key`（课程内唯一）作为幂等键载体；
  `courses.name` 作为示例课稳定身份（`courses.name` 无唯一约束，见 ADR-077 已知限制第 8 条）。

## 实现要点（对应验收四条）

1. **重跑不重复**：幂等键 `k09::<课程名>::<资料标题>::<内容 sha256>`；跳过判定 = 同课程内「同标题 + 同
   `content_hash`」。第二次导入整库 `iterdump` 逐行不变、存储目录文件数不变（重复落盘被 C07 补偿删除，无孤儿）。
2. **只写示例课**：写入只经 `services.courses.create_new_course` / `services.materials.upload_material`；
   课名属于其他教师 → 拒绝；教师名下多门同名 → 拒绝；`--course-id` 与名称/`teacher_id` 不符 → 拒绝；
   账号缺失或非 `teacher` → 拒绝（提示跑 `scripts/seed-demo-accounts.py`）。脚本里没有任何删除/覆盖他课的分支。
3. **失败可重试**：所有源文件在**任何写入之前**校验（存在、可读、sha256 一致、标题后缀与格式一致、幂等键 ≤255）；
   校验失败退出 2 且零写入；写入阶段单条失败只影响该条（资料+任务同事务、落盘失败补偿删除），退出 1，重跑补齐。
4. **不混入真实资料**：manifest 的 `notice`、`datasets/demo/README.md` 与用例三处独立声明「自编、不是真实
   课程资料」；用例断言示例课的资料集合恒等于 manifest 声明集合、正文不含绝对路径与 `password` 字样。

## 验证（真实执行）

### 1) 集成用例（真实 Neo4j 5.26 容器 `ss-neo4j-f11` + 真实 SQLite 临时库）

```
SMARTSKETCH_TEST_NEO4J_URI=bolt://localhost:17687 SMARTSKETCH_TEST_NEO4J_USER=neo4j SMARTSKETCH_TEST_NEO4J_PASSWORD=testpassword1 \
  PYTHONPATH=$PWD/src/backend /Users/arvinhan/Desktop/SmartSketch/.venv/bin/python -m pytest tests/integration/test_k09.py -q ; echo "EXIT=$?"
```
```
....................                                                     [100%]
20 passed in 21.11s
EXIT=0
```

不配置 `SMARTSKETCH_TEST_NEO4J_*` 时（真实 Neo4j 用例按既有范式 `pytest.skip`）：
```
...................s                                                     [100%]
19 passed, 1 skipped in 20.82s
EXIT=0
```
（早前一次与后端全量并行时同一命令为 `20 passed in 134.78s`——耗时差来自 CPU 争用，不是用例差异。）

### 2) 后端全量

```
PYTHONPATH=$PWD/src/backend /Users/arvinhan/Desktop/SmartSketch/.venv/bin/python -m pytest tests/backend -q ; echo "EXIT=$?"
```
```
3466 passed, 27 skipped, 1 warning in 579.95s (0:09:39)
EXIT=0
```
（另行一次与集成用例并行的全量运行同为 `3466 passed, 27 skipped`、EXIT=0，耗时 1385.45 s。）

### 3) 手工真跑 `scripts/import-demo.py`（本地一次性库 `/tmp/k09-manual`，Neo4j 指向测试容器）

准备：`python -m app.repositories.sqlite` 迁移 + `SEED_DEMO_PASSWORD=<本机临时口令> scripts/seed-demo-accounts.py`
（口令只作临时本地值，非真实密钥）。

第一次：
```
[demo-import] 示例包：/Users/arvinhan/Desktop/SmartSketch/.worktrees/impl-k09/datasets/demo（schema_version=1）
[demo-import] 导入账号：demo_teacher（teacher）
[demo-import] 目标课程：示例课程：数据结构导论 —— 新建示例课
[demo-import] created  course    示例课程：数据结构导论  course_id=42c997a422de4d5db3ce5505d2ee0831
[demo-import] created  document  线性结构示例讲义.md  format=markdown size=731 task=d14894c633074c7db326da0224af9d3f document_id=a7a2a362583c44839b10c740b0ce5271
[demo-import] created  document  树结构示例讲义.txt  format=txt size=739 task=103b9e364f7a4b2ba71671c6c8f754ed document_id=5d8a0a27b9114ff8b5f173fcc1263b2c
[demo-import] summary created=3 skipped=0 failed=0 course_id=42c997a422de4d5db3ce5505d2ee0831
EXIT=0
```
第二次（幂等）：
```
[demo-import] 目标课程：示例课程：数据结构导论 —— 已存在，跳过
[demo-import] skipped  course    示例课程：数据结构导论（已存在 course_id=42c997a422de4d5db3ce5505d2ee0831）
[demo-import] skipped  document  线性结构示例讲义.md  （已存在相同内容（同标题 + 同 content_hash））
[demo-import] skipped  document  树结构示例讲义.txt  （已存在相同内容（同标题 + 同 content_hash））
[demo-import] summary created=0 skipped=3 failed=0 course_id=42c997a422de4d5db3ce5505d2ee0831
EXIT=0
```

### 4) `git diff --check`

```
git diff --check ; echo "EXIT=$?"   →   EXIT=0（无输出）
```

### 5) `./scripts/verify.sh`

**未跑完**：本 worktree 里 `tests/contracts/test_b14.py` 在 `scripts/verify.sh` 的契约门禁阶段长时间无进展
（150 s 只跑到第 2 个用例，`gen-contracts.sh` 在临时副本里逐用例重跑生成器，且与后端全量并行时有 CPU 争用），
为避免长跑占用并行会话的 CPU 我中止了它。**门禁各步单独实跑均通过**：

```
python3 scripts/check_contracts.py                         → EXIT=0（29 路径 / 121 schema / 359 $ref 全过）
scripts/gen-contracts.sh --check                           → EXIT=0（✓ 生成物与真源一致）
bash tests/hooks/test_block_dangerous.sh                   → EXIT=0（block-dangerous hook tests passed.）
```
本任务不触碰 `src/contracts/`，契约门禁与本次改动无关；**`./scripts/verify.sh` 的全绿结论仍需在无争用环境复跑**。

## 反向篡改自检（9 处，9/9 判红，跑完自动复原）

篡改脚本：临时改 `scripts/import-demo.py` 后跑表内定向用例，再复原并核对 sha256
（最终脚本基线 `37ce98de6d94d330bab292b054a61aa935a857c117e052579b5e9af7a5d9c801`，跑完一致，漏检 0）。

| # | 篡改 | 定向用例 | 结果 | pytest 摘要 |
| --- | --- | --- | --- | --- |
| M1 | 幂等判定只用标题（去掉 `content_hash`） | `test_changed_source_content_is_imported_as_a_new_document` | 判红 | `1 failed in 1.42s` |
| M2 | 幂等键去掉内容 sha256 | `test_first_import_creates_the_course_and_every_document` | 判红 | `1 failed in 1.09s` |
| M3 | 去掉「课名已被他人占用」守卫 | `test_refuses_when_the_demo_course_name_belongs_to_another_teacher` | 判红 | `1 failed in 0.95s` |
| M4 | 真写库时 `DELETE FROM materials WHERE course_id != <示例课>`（删他课资料） | `test_other_courses_are_never_touched_or_deleted` | 判红 | `1 failed in 2.85s` |
| M5 | `--dry-run` 也真写库 | `test_dry_run_reports_the_plan_without_writing_anything` | 判红 | `1 failed in 1.65s` |
| M6 | manifest 与文件 sha256 不一致仍导入 | `test_a_missing_or_corrupted_source_file_is_refused_then_retry_converges` | 判红 | `1 failed in 1.97s` |
| M7 | 写入失败仍 `return 0`（报成功） | `test_a_write_failure_exits_nonzero_and_the_retry_converges` | 判红 | `1 failed in 1.28s` |
| M8 | 先插 `materials` 行再上传（失败留半成品） | `test_a_write_failure_exits_nonzero_and_the_retry_converges` | 判红 | `1 failed in 1.31s` |
| M9 | `--course-id` 守卫失效（允许写非示例课） | `test_refuses_a_course_id_that_is_not_the_demo_course` | 判红 | `1 failed in 1.71s` |

- 红灯阶段（TDD 真实证据）：实现前 `pytest tests/integration/test_k09.py -q` → **14 failed, 5 passed**
  （失败原因均为脚本不存在；其中 3 条「非零退出即通过」的用例属假绿——`--course-id` 不存在、格式不一致、
  学生账号——已加固为断言**拒绝原因**文本，加固后同一篡改会真判红）。
- 篡改矩阵在**最终脚本**上重跑过一遍（上表用时即该次结果），逻辑与首次一致：9/9 判红、复原后 sha256 一致。
- 说明：M4/M8 是刻意的破坏性篡改（不是常见 bug），用来证明「删他课资料」「留半成品」两条验收在测试里真的可判红。

## 风险与下一步

1. **ADR-077 三项待签收**：示例课保留名、内容变化即新增一条资料、少格式 `--dataset` 只告警不阻断。
2. **`datasets/demo/documents/` 两个文件属扩围**（原子清单只列 manifest），需确认接受。
3. **格式只有 2 种**（Markdown + TXT）：PDF/DOCX 需要真实可解析文件才能纳入，未凭空生成二进制；扩格式无需改脚本。
4. **`courses.name` 无唯一约束**：两个导入进程并发首次运行可能各建一门同名课（顺序使用假设，见 ADR-077 第 8 条）。
5. **`./scripts/verify.sh` 未全绿跑完**（见上）；本任务不涉及契约，但建议合并前在无争用环境补跑。
6. **未做**：不跑 worker（导入只入队；解析/抽取由 `python -m app.workers` 按真实链路完成）；示例包的发布/浏览
   端到端留给 K12 runbook 与 K05/K06 E2E。

## 回滚

`git revert` 本分支提交即可撤销 `datasets/demo/`、`scripts/import-demo.py`、`tests/integration/test_k09.py`
与 ADR-077/本节/交接；无数据库迁移需要回退。已导入的演示数据可在界面按 ADR-021 删除资料，
或用 K10 的备份/恢复回到导入前（脚本本身不提供删除能力）。

## 复跑

最终脚本状态下按任务书给的**精确命令**（无管道、显式 `; echo "EXIT=$?"`）复跑：集成 `20 passed`（EXIT=0）、
不配 Neo4j `19 passed / 1 skipped`（EXIT=0）、后端全量 `3466 passed / 27 skipped`（EXIT=0）、
`git diff --check` EXIT=0；数值与上文一致。原始输出存于 `/tmp/k09-integration.log`、`/tmp/k09-nolive.log`、
`/tmp/k09-backend.log`（临时目录，非仓库交付物）。
