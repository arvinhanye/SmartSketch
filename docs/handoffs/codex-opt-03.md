# OPT-03：后端测试辅助与初始化收敛

- task_id：OPT-03；负责人：Codex；状态：DONE；验收日期：2026-11-10。
- 分支：`codex/opt-03-test-fixtures`；基线：`codex/opt-02-test-waits@eca579c`。
- 工作区：`/Users/arvinhan/.codex/worktrees/opt-03-test-fixtures/SmartSketch-main`。基线工作区干净，OPT-02 测试改动已在 `51ef5cb` 提交，最新 `eca579c` 包含个人模式 E2E 修复。OPT-02 未完成的浏览器/完整 integration 验收维持原记录，本任务不代为签收。
- 已读：AGENTS、`.claude/rules/testing.md`、`tests/backend/conftest.py`、任务看板及身份/任务规格；基线不存在 `tests/INDEX.md`。原需求通过 `git show claude/code-structure-review-handoff-49e73a:docs/handoffs/claude-code-structure-review-codex-handoff.md` 的 OPT-03 节核对。
- 范围：仅后端测试辅助/初始化、消费者及本任务文档；产品代码、接口、数据模型和依赖清单不变。

## 基线与计数口径

所有命令在上述 worktree 根目录运行。`.venv`、根目录和前端 `node_modules` 以忽略的符号链接复用本机已安装依赖。

```bash
PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend --collect-only -q \
  > .demo/opt-03/baseline-collect.log 2>&1
tail -1 .demo/opt-03/baseline-collect.log
PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend -q -p no:cacheprovider \
  > .demo/opt-03/baseline-tests.log 2>&1
```

- 基线收集：**4072 tests collected**。
- 基线运行：**4045 passed, 27 skipped**，567.82 秒；完整 pytest 结果保存在日志中。运行期间会话切换，原进程句柄已失效，未将缺失的外层退出码补写为实测值。

以下统计限定 Python 源码定义/直接调用，避免把 import 别名、字节码和新共享实现混进“各测试文件的重复数”。最终同时列出共享实现的数量，不能只通过改名宣称消除了重复。

```bash
for name in _url _account _rewrite _settings _insert_task; do
  grep -rE "^[[:space:]]*def ${name}\\(" tests/backend --include='*.py' | wc -l
done
grep -rlE '(^|[^[:alnum:]_])migrate\(' tests/backend --include='*.py' | wc -l
grep -rlE 'create_app\(' tests/backend --include='*.py' | wc -l
```

| 指标 | 基线 | 完成后 |
| --- | ---: | ---: |
| 后端收集用例 | 4072 | 4072 |
| `_url` 定义 | 12 | 0 |
| `_account` 定义 | 10 | 0 |
| `_rewrite` 定义 | 8 | 0 |
| `_settings` 定义 | 6 | 4 |
| `_insert_task` 定义 | 5 | 2 |
| 直接 `migrate(...)` 的文件 | 63 | 23 |
| 直接 `create_app(...)` 的文件 | 27 | 16 |

新增共享实现分别为 `sqlite_url`、`make_account`、`rewrite_schema_refs`、`worker_settings`、`insert_queued_task`，各 1 份。因此五类辅助的**总实现份数（包括共享实现）为 41 → 11**，并非仅按改名后的本地定义数计算。迁移文件数 23 包括共享 `helpers/sqlite.py`，应用工厂文件数 16 包括共享 `conftest.py`；测试消费者分别为 22 和 15 个。

最终收集 **4072 项**，与基线相同。额外结构检查确认所有原断言 AST、测试函数名、参数签名及参数化装饰器不变。逐 ID 比对中，`test_c05.py` 的 3 项、`test_d11.py` 的 1 项 ZIP 参数包含 `ZipFile.writestr` 自动生成的时间戳，原始 ID 会随收集时间改变；核对 ZIP 构造函数及参数定义均未变后，仅对这 4 项做精确限定的归一化，其他 4068 个 ID 严格相同。

## 合并原则与状态隔离

- 保留调用点的 `_url` 等本地 import 别名，避免改写断言；相同实现迁入 `tests/backend/helpers/`。账号辅助中的 `name` / `username` 参数拼写不同，但全部调用均为位置参数，UUID、占位哈希及仓储调用相同。
- SQLite 初始化保留原 URL、迁移时机、SQL 种子和清理方式。fixture 默认 function 作用域，临时数据库依赖 pytest 的 `tmp_path`；不缓存数据库，不提高作用域。
- 应用初始化只合并连续的环境变量设置和创建步骤，保留各文件的 TestClient 上下文、状态替身和生命周期顺序。
- 不增加或删除测试，不修改断言。已比较测试名称、断言 AST、参数化定义及收集 ID（仅上述 4 项时间戳归一化）。54 个消费者文件、6 个 helper 模块和 conftest 之外，仅本任务文档变化。

## 未合并及原因

- `_settings`：`test_e03.py` 是 live HTTP 主供应商及 17 秒超时；`test_l07.py` 是个人模型基础配置；`test_l08.py` 额外设置零重试和单次失败熔断；`test_n01_n06.py` 只增加零重试。它们默认值和用途不同，保留本地实现。仅 `test_d11.py` / `test_e12.py` 的 15 秒任务租约设置等价。
- `_insert_task`：`test_c07.py` 接收 World、阶段、时间并推导 progress/cancel；`test_c16.py` 依赖数据库默认时间且返回 None。保留这两份。`test_c10.py` / `test_c11.py` / `test_td02.py` 的固定时间字符串相等，返回任务 ID，才合并。
- 迁移顺序、版本返回值、备份、旧数据库升级与启动门禁测试保留直接迁移：B05/B06、C01/C02/C02-reasoning/C02b/C06/C09/C13/C16、D10、E12、F11、G02、J10、N01/N06，以及 `test_migration_rollbacks.py`、安装/邀请码迁移测试。`test_demo_mode.py` 对 demo 自有 URL 的准备、`test_f12.py` 对场景对象 URL 的准备也保留，避免改动这些不同的生命周期。特殊 SQL 种子和 Neo4j 依赖仍在消费者中。
- C10/C11/C16 内捕获本地 URL 的嵌套 `account` 工厂、返回 user ID 的其他账号夹具，以及有不同默认角色的 `_user` 没有强行变成通用账号 fixture。
- 特殊应用启动验证、导入失败、动态环境切换、嵌套客户端工厂和带其他 monkeypatch 步骤的初始化保留原实现。

## 分批验证

每批只迁一类辅助，使用以下命令逐批运行。**27 批最终全部通过**；账号首批的失败及修复重跑单独保留。`.demo/opt-03/batches.jsonl` 保存每批完整命令、文件清单、退出码和 pytest 摘要，日志同目录。失败即停止进入下一批。

```bash
PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD/src/backend" \
  .venv/bin/python -m pytest -q -p no:cacheprovider <该批测试文件>
```

文件均位于 `tests/backend/`；表中省略 `test_` 前缀和 `.py` 后缀。

| 批次 | 文件 | 实际结果（exit 0） |
| --- | --- | --- |
| url-01 | c01, c02, c09, c10 | 129 passed |
| url-02 | c11, c13, c14, c16 | 153 passed |
| url-03 | d10, d11, e12, td02 | 136 passed |
| rewrite-01 | c10, c11, f07, f08 | 166 passed |
| rewrite-02 | f11, g06, i02, i05 | 97 passed, 27 skipped |
| account-01-retry | adr021, adr022, c07, c15 | 102 passed |
| account-02 | f07, f08, g06 | 105 passed |
| account-03 | i02, i05, relations_api | 120 passed |
| settings-01 | d11, e12 | 86 passed |
| task-01 | c10, c11, td02 | 93 passed |
| fixture-01 | adr079_register, c02, c10, c13 | 126 passed |
| fixture-02 | c14, d11, e12 | 112 passed |
| fixture-03 | c02b_disable_thinking, d2, l04 | 33 passed |
| fixture-04 | l07, l08, n01_n06 | 30 passed |
| migration-01 | adr021, adr022, c03, c04 | 63 passed |
| migration-02 | c07, c10, c11, c15 | 147 passed |
| migration-03 | c16, course_detail, td02, enum_input_validation | 129 passed |
| migration-04 | f07, f08, f11, relations_api | 162 passed, 27 skipped |
| migration-05 | g02, g04_sqlite, g05_sqlite, g06 | 45 passed |
| migration-06 | g07, i01, i02, i05 | 100 passed |
| migration-07 | d1, d3, demo_mode, c02_reasoning | 67 passed |
| migration-08 | e04, e06, j03, j05 | 305 passed |
| migration-09 | l06, l12, n07_n08, k09 | 59 passed |
| migration-10 | 264_cleanup_lock, invite_codes, worker_persist_fence | 89 passed |
| app-01 | adr079_register, c03, c04, course_detail | 50 passed |
| app-02 | c10, c11, c15, c16 | 128 passed |
| app-03 | f08, i02, invite_codes, relations_api | 189 passed |

### 已记录的失败尝试

账号辅助首批迁移的第一次运行得到 `1 failed, 101 errors`（exit 1）。原因是本地迁移工具按子串改名，将共享辅助内部的 `insert_account` 误改为不存在的 `insertmake_account`。该批失败后自动停止，未进入下一批；已改为按完整标识符替换并恢复调用，原失败日志 `account-01.log` 保留，重跑记录为 `account-01-retry.log`。没有更改断言或产品实现。修正后首批 102 项通过，之后两批分别 105、120 项通过。

额外的 ID 审计有两次辅助脚本失败：第一次错误要求含 ZIP 时间戳的 ID 完全相等；第二次识别范围还包含一项静态损坏 ZIP。限定为 4 项真实生成的 ZIP、同时验证参数定义/构造函数后，完整审计通过。这不是 pytest 用例失败；两个原始审计日志分别保留在 `final-structure-initial.log`、`final-structure-matcher.log`。

## 随机顺序验证

当前环境未安装 pytest-randomly，未增加项目依赖。临时验证工具和日志保存在本工作区忽略目录 `.demo/opt-03/`，不进入提交。临时插件 `opt03_order.py` 用 `random.Random(seed).shuffle(items)` 在最后的收集 hook 打乱顺序，记录收集顺序和 `pytest_runtest_logstart` 的实际执行顺序；不重置产品使用的随机数发生器。

实际执行命令如下，`<54 个修改文件>` 为上方批次表的去重并集，也保存在 `random-files.json`；实际命令的完整参数数组保存在 `acceptance.jsonl`：

```bash
PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD/src/backend:$PWD/.demo/opt-03" \
  .venv/bin/python -m pytest -q -p no:cacheprovider -p opt03_order \
  --opt03-seed=20261110 <54 个修改文件>
PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD/src/backend:$PWD/.demo/opt-03" \
  .venv/bin/python -m pytest -q -p no:cacheprovider -p opt03_order \
  --opt03-seed=20261111 <54 个修改文件>
```

- seed 20261110：**1545 passed, 27 skipped**，480.34 秒，exit 0。
- seed 20261111：**1545 passed, 27 skipped**，459.67 秒，exit 0。
- 两轮均执行全部 1572 项、覆盖全部 54 个修改文件，实际执行顺序与收集记录一致；忽略同一 DOCX 的生成时间戳后，用例集合相等，**1572 个位置全部不同**。核对记录 `random-order-audit.json`；27 项均为原 F11 Neo4j 条件跳过。
- helper/conftest 本身不收集用例，通过上述消费者两轮执行覆盖。未提高任何 fixture 作用域；SQLite 每次仍来自 function 级 `tmp_path`，保留现有逐用例迁移，未宣称获得运行加速。

## 最终验收与交接

```bash
PATH="$PWD/.venv/bin:$PATH" GOCACHE="$PWD/.demo/opt-03/go-build-cache" \
  ./scripts/verify.sh full
python3 .demo/opt-03/audit.py
git diff --check
```

- `verify.sh full`：**PASS，exit 0**。使用工作区内 Go 缓存的完整重跑自然结束：钩子/契约通过，启动器单测与 vet 通过，后端与工具测试 **4254 passed / 27 登记 skip**（679.44 秒），前端 **82 文件 / 1375 passed**，类型检查与构建通过。首轮启动器因系统 `~/Library/Caches/go-build` 不在可写范围而失败；该轮已主动停止（外层退出码 143），没有把未完成的后端/前端阶段计为通过。保留日志 `verify-full-cache-permission.log` 和进程清理记录 `verify-full-cache-permission-stop.json`。只停止核实属于本任务的进程树，未改项目脚本。
- 结构审计：PASS，4072 项数量/参数定义不变、断言不变、改动均在授权范围。
- `git diff --check`：PASS。
- 61 个测试源文件的 SHA256 与两轮随机测试之后冻结的版本一致；最终差异仅测试与本任务文档。已完成作者自查，没有产品、接口、模型或依赖变更。
- 本任务验收无未完成项；OPT-02 的浏览器/完整 integration 状态不在本次签收范围。交付为本分支本地提交，提交信息末尾保留 `Co-Authored-By: Codex <noreply@openai.com>`；不推送、不创建 PR。

回滚只需撤销本任务的测试和文档提交；无产品迁移或数据回滚。
