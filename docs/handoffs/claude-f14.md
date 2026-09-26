# Claude 交接：F14 离线重新向量化命令

- 分支：`claude/project-thread-200r6n`，base `main@95d5c9a`
- 规格：`specs/teacher-review-publish.md` V12、PUB-39；实现约定 ADR-038

## 交付物

- `scripts/reembed.py`：V12 第 1～7 步。`run(...)` 供测试注入驱动与向量客户端，`main()` 为命令行入口（`--neo4j-backup-confirmed`）。迁移写入只经 F03 `GraphVectorWriter.migration`，不另开写入口。
- `tests/integration/test_f14.py`：内存图替身覆盖全部路径（不需要 Docker）；`test_live_*` 两个用例连真实 Neo4j（`SMARTSKETCH_F14_URI/USER/PASSWORD`，**会清空该库**，只能指向一次性实例）。
- ADR-038；V12 启动门禁一句与后端 README 一句改为指向本命令。

## 命令与实际结果

`S=<scratchpad>`；`$S/pt.sh` = `PYTHONPATH=src/backend PYTHONPYCACHEPREFIX=$S/pyc-$RANDOM $S/venv/bin/python -m pytest -p no:cacheprovider`；真实 Neo4j 用 `claude-f04.md` 记录的 Maven `neo4j-harness:5.26.0`（`bolt://127.0.0.1:7687`，无鉴权）。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 红灯 | `$S/pt.sh tests/integration/test_f14.py -q`（实现前） | 收集错误：`scripts/reembed.py` 不存在 |
| 绿灯（无真库） | 同上 | 30 passed、2 skipped |
| 绿灯（真库） | `SMARTSKETCH_F14_URI=bolt://127.0.0.1:7687 SMARTSKETCH_F14_USER=neo4j SMARTSKETCH_F14_PASSWORD=x $S/pt.sh tests/integration/test_f14.py -q` | 32 passed |
| 后端全量 | `$S/pt.sh tests/backend -q` | 2962 passed |
| 集成全量 | 设 `SMARTSKETCH_TEST_NEO4J_*` 与 `SMARTSKETCH_F03_*` 跑 `tests/integration` | 165 passed、5 skipped |
| verify | `PATH=$S/venv/bin:$S/tools/node_modules/.bin:$PATH ./scripts/verify.sh` | exit 0 |
| diff | `git diff --check` | 通过 |

### 反向篡改（改后跑 `test_f14.py`，改回 `cmp` 一致）

| # | 篡改 | 结果 |
| --- | --- | --- |
| T1 | 不迁移已提交副本 | 13 failed |
| T2 | 不查未完成的发布尝试 | 3 failed |
| T3 | 不比对前后存量 | 1 failed |
| T4 | 草稿也复用旧的目标向量 | 2 failed |
| T5 | 不改已提交版本的 `embedding_space` | 1 failed |
| T6 | 不删旧空间属性 | 3 failed |
| T7 | 不查缺向量/维度 | 1 failed |
| T8 | 不核对版本副本数 | 2 failed |
| T9 | 提交前不复查记录空间 | 1 failed |

## 接口 / 数据变更

- 无 SQLite 迁移、无 Neo4j DDL 文件变更、无契约或依赖变更。命令运行时写 `embedding_space_state` 单行与已提交版本行的 `embedding_space`（010 触发器允许），新建/删除 `chunk_embedding_*`、`kp_embedding_*` 向量索引与 `embedding_*` 属性。
- 测试专用变量 `SMARTSKETCH_F14_URI/USER/PASSWORD` 不进 `.env.example`。

## 风险 / 待决

- 没有做任何真实模型调用；在线模式下命令会用 `EMBEDDING_BASE_URL/API_KEY` 产生付费向量调用，只在操作者运行时发生。
- K10 Neo4j 备份脚本未实现，暂靠 `--neo4j-backup-confirmed` 由人确认。
- 失败尝试残留的副本换空间后没有向量，等 G05 清理。
- 无法检测 API/worker 进程是否真的停了，只能以租约、写锁、发布尝试为代理；运行中出现写入会被第 4 步的存量比对或第 5 步复查拦下。

## 下一步

- ArvinHan 审阅 ADR-038 并决定是否合并。
- K10 落地后把 Neo4j 备份接进第 1 步。
