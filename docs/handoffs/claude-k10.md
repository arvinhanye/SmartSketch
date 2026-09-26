# Claude 交接：K10 备份与恢复演练

- review_status: ready_for_review
- task_id: K10
- 分支：`task/k10`（本地，未 push），base `ddae1ed`（`main@0b8aa73` + 第九批认领）
- 决定：ADR-054（待 ArvinHan 审阅）
- 依赖：G05（发布补偿与清扫，孤儿副本/缺副本留给 K10）、K08（容器配置）、K07（本地 Neo4j 启停）、F14（`--neo4j-backup-confirmed` 暂代 K10）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `scripts/backup-demo.sh` | 一致时间点备份。bash 外壳 + 内嵌 Python（文件锁只有 `.sh`，故不另建模块）。缺省 Bolt 导出；`--neo4j-container` 走 neo4j-admin dump；另有 `--inspect`（只读检查一对库，打印 JSON）与 `--export-graph`（只导出图）两个子模式供恢复脚本调用 |
| `scripts/restore-demo.sh` | 恢复到隔离副本并逐项核对；默认拒绝覆盖；`--replace-existing --confirm <备份 ID>` 才覆盖，且先做安全备份 |
| `tests/integration/test_k10.py` | 20 个用例：离线拒绝 7、Bolt 路径 12（进程内 Neo4j，会清库）、neo4j-admin 路径 1（一次性 Docker 容器，无 Docker 时跳过） |
| `docs/decisions.md`（扩围） | 追加 ADR-054 |

## 用法

```bash
# 备份（先停 API 与 worker；SQLITE_URL、NEO4J_URI/USER/PASSWORD 取自环境）
scripts/backup-demo.sh --out backups/k10                              # Bolt 导出
scripts/backup-demo.sh --out backups/k10 --neo4j-container <容器名>   # neo4j-admin 离线 dump（会停启容器）
# 最后一行 stdout = 备份目录 backups/k10/k10-<UTC>-<hex>/{sqlite.db, graph.jsonl.gz | neo4j/neo4j.dump, manifest.json}

# 恢复演练到隔离副本（Neo4j 目标必须显式、且无节点；SQLite 目标必须不存在）
scripts/restore-demo.sh --from backups/k10/<ID> --sqlite-target /tmp/drill/restored.sqlite3 \
    --neo4j-uri bolt://127.0.0.1:<空实例端口> [--neo4j-container <空容器>] --report /tmp/drill/report.json
# 目标凭据：RESTORE_NEO4J_USER / RESTORE_NEO4J_PASSWORD（缺省沿用 NEO4J_*）
```

退出码两脚本一致：0 完成/核对一致；1 失败（备份不留目录；恢复报告列差异，副本不得使用）；2 拒绝（未改动任何东西）。

## 验收对照

| 验收 | 实现 | 用例 |
| --- | --- | --- |
| 一致时间点 | 持有全部课程写锁；拒绝活动租约、他人写锁、`preparing`/`materialized` 尝试（F14 第 1 步同口径）；G0 图摘要 → S1 SQLite 在线备份 → 导出/dump → G2 = G0 → S3 逐表 = S1 → 锁仍在 | `test_backup_refuses_while_anything_can_still_write[4 种]`、`test_a_publish_during_the_backup_is_rejected_by_the_fence`、`test_an_unfenced_write_during_the_backup_fails_it[neo4j/sqlite_progress/sqlite_course]` |
| 发布指针 | 指针须为本课 committed 且版本号一致，其副本按快照 `materialize.verify` 复核；否则备份失败 | `test_backup_records_one_point_in_time_and_the_publish_pointer`、`test_a_pointer_without_its_copies_fails_the_backup` |
| G05 残留 | 孤儿副本、非当前版本缺副本、悬空 Chunk 记为警告，恢复后原样复现 | `test_leftovers_are_recorded_and_restored_as_they_were` |
| 隔离副本核对引用/图/进度 | 文件 SHA-256 → 装入 → `--inspect` 重查，与清单比较 SQLite 逐表行级摘要（进度表不依赖表名，用探针表代 I01）、结构、指针；图摘要/计数/结构；版本复核、孤儿、悬空引用 | `test_restore_into_an_isolated_copy_verifies_references_graph_and_progress`、`test_a_damaged_backup_is_refused_or_fails_verification`、`test_a_forged_sqlite_copy_fails_the_progress_comparison` |
| 不覆盖用户库 | 目标存在/非空即拒绝；Neo4j 目标不读 `NEO4J_URI`；覆盖需 `--replace-existing` + `--confirm <ID>` + 目标停机 + 先安全备份 | `test_restore_refuses_non_empty_targets_without_touching_them`、`test_replacing_needs_the_backup_id_and_keeps_safety_copies`、`test_restore_requires_an_explicit_neo4j_target` |
| neo4j-admin 真实路径 | 一次性 `neo4j:5.26-community` 容器：dump（停源容器）→ load 到另一容器 → Bolt 核对；源容器恢复服务、用户 SQLite 不变 | `test_neo4j_admin_dump_and_load_round_trip` |

## 命令与实际结果

`S=/tmp/claude-0/.../scratchpad`；`$S/pt.sh` = 共享 venv 的 pytest（`PYTHONPATH=src/backend`）；真实 Neo4j 为进程内 harness `bolt://127.0.0.1:7689`（`SMARTSKETCH_TEST_NEO4J_URI/USER/PASSWORD`，`neo4j`/`x`）；Docker 29.3.1 + `neo4j:5.26-community`，容器 `k10-src-*`（7697）/`k10-dst-*`（7698），`NEO4J_AUTH=none`，用例结束 `docker rm -f -v` 删除。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 红灯 | `$S/pt.sh tests/integration/test_k10.py -q`（脚本不存在） | 19 failed |
| 绿灯 | 同上（带 Neo4j 环境变量，Docker 可用） | 见下方「收尾」 |
| verify | `PATH=$S/venv/bin:$S/tools-f10/bin:$S/tools-f10/node_modules/.bin:$PATH ./scripts/verify.sh` | Scaffold verification passed（exit 0） |
| diff | `git diff --check`（含新文件 intent-to-add） | 通过 |
| 语法 | `bash -n scripts/backup-demo.sh scripts/restore-demo.sh` | 通过 |

收尾结果：

| 命令 | 结果 |
| --- | --- |
| `$S/pt.sh tests/integration/test_k10.py -q`（Neo4j 环境变量，Docker 可用） | **20 passed**（129 s；含 neo4j-admin 容器用例，结束后无残留容器） |
| `$S/pt.sh tests/integration -q --ignore tests/integration/test_k10.py --deselect tests/integration/test_k08.py::test_images_build`（另设 `SMARTSKETCH_F03_*`、`SMARTSKETCH_F14_*` 指向 7689） | 222 passed |
| `$S/pt.sh tests/integration/test_k08.py::test_images_build -q` | 1 failed：本机 Docker 刚启用，镜像构建内 `pip install` 无法联网（build 容器未经代理/CA）；此前因无守护进程一直 skip，与 K10 无关，K08 镜像实机构建仍待人工复验 |
| `$S/pt.sh tests/backend -q` | 3096 passed（与基线一致） |

实现中先失败后修复的三处：`properties(n)` 是 dict 未被接受；导入时关系行在节点批次写入前取映射（KeyError）；admin load 时备份目录 0700 使容器内 uid 7474 读不到 dump（改为私有临时目录下暂存 0644 副本，用后删除）。

### 反向篡改（临时改脚本后跑相关用例，改回后字节比对一致）

| # | 篡改 | 结果 |
| --- | --- | --- |
| T1 | 不取课程写锁 | 1 failed |
| T2 | 不比较 Neo4j 前后摘要 | 1 failed |
| T3 | 不做 SQLite 复查 | 2 failed |
| T4 | 指针错误不阻断 | 1 failed |
| T5 | 快照保留本次锁行 | 1 failed |
| T6 | 不拒绝未完成尝试 | 2 failed |
| T7 | 接受非空 Neo4j 目标 | 1 failed |
| T8 | 接受已存在的 SQLite 目标 | 1 failed |
| T9 | 不校验文件 SHA-256 | 1 failed |
| T10 | 不比较图摘要 | 1 failed |
| T11 | 覆盖前不做安全备份 | 1 failed |
| T12 | 不核对 `--confirm` 备份 ID | 1 failed |
| T13 | 不比较 SQLite 逐表摘要 | 首轮 0 failed（漏检）→ 新增 `test_a_forged_sqlite_copy_fails_the_progress_comparison` 后 1 failed |

13 项全部检出。

## 接口 / 数据变更

- 无迁移、无契约、无依赖变更；未改 `docker-compose.yml`、`reembed.py` 或其他执行者文件。
- 备份运行期间向 `course_locks` 写入持有者 `k10-backup-<ID>` 的锁行（结束即释放，副本中删去）。
- 新环境变量只在脚本内使用、不进 `.env.example`：`PYTHON`（解释器）、`DOCKER`（docker 命令）、`RESTORE_NEO4J_USER/PASSWORD`（恢复目标凭据）、`K10_AFTER_SNAPSHOT_HOOK`（仅演练/测试并发写）；测试专用 `SMARTSKETCH_K10_DOCKER_PORTS`。

## 风险

- 栅栏期间被拒的发布仍写一行 `failed` 尝试，使该次备份作废（按设计从严：SQLite 任何变化都判不一致），需停机后重跑。
- Bolt 路径全图扫描两次（G0 与导出）且在内存中保留元素 ID 映射，只适合演示规模；大库用 neo4j-admin 路径（需停 Neo4j）。
- Neo4j 属性只支持标量与标量列表；将来若写入时间/空间类型，导出会明确失败，需扩展。
- 备份含账号口令散列等敏感数据：目录 0700、文件 0600；neo4j-admin dump 文件属主为容器内 uid 7474，非 root 宿主用户可能无法删除，需 `sudo` 或 `docker run --rm -v ... alpine rm`。
- 覆盖用户库时，若 Neo4j 装入后 SQLite 恢复前中断，两库暂时不一致；此时从安全副本（`--safety-dir` 下的 K10 备份）再恢复一次。

## 待决 / 待人工复验

- **compose 整套实机演练未跑**：K08 部署下 SQLite 在 `app-data` 卷，宿主机看不到。建议流程（待复验）：
  ```bash
  docker compose --profile app stop api worker
  docker compose --profile app run --rm --no-deps -v "$PWD/scripts:/app/scripts:ro" -v "$PWD/backups:/backups" \
      api bash /app/scripts/backup-demo.sh --out /backups     # Bolt 路径；镜像内 K10_ROOT=/app 与布局一致
  ```
  `/backups` 需对镜像用户 uid 10001 可写；neo4j-admin 路径需要宿主机 docker，不能在该容器内执行（可在宿主机用 `--neo4j-container <compose 的 neo4j 容器>` 并把 SQLite 卷另行挂出），列为待人工决定。
- 缺省 `--out backups/k10` 相对当前目录；`.gitignore` 未忽略 `backups/`（`*.sqlite*`、`*.db` 已忽略，但 `graph.jsonl.gz`、`manifest.json` 未忽略）。建议协调者在 `.gitignore` 加 `backups/`（不在本任务文件锁内，未改）。
- I01 `011_progress.sql` 合并后无需改脚本（逐表复制与核对）；可在 I01 之后把测试中的探针表换成真实进度表。

## 下一步

- **F14 衔接（未改 `reembed.py`）**：把第 1 步的 `--neo4j-backup-confirmed` 换成 `--k10-backup <目录>`：reembed 读取清单并调用 `backup-demo.sh --inspect` 比较当前 SQLite 逐表摘要与 Neo4j 图摘要，相等才证明备份正是当前（停机后）状态，再继续；ROLLBACK_STEPS 中「按 K10 流程恢复」改为 `restore-demo.sh --replace-existing --confirm <ID>`。
- G05 残留（孤儿副本、缺副本）目前只在清单警告中报告；自动删除孤儿或按快照重建副本仍需单独任务。
- ArvinHan 审阅 ADR-054。

## 回滚

删除 `scripts/backup-demo.sh`、`scripts/restore-demo.sh`、`tests/integration/test_k10.py`、本交接，并撤下 `docs/decisions.md` 末尾 ADR-054；无迁移。已生成的备份目录可直接删除；若备份中途被强杀，残留的 `k10-backup-*` 锁行在租约（缺省 600 秒）到期后自动失效，残留的 `.<ID>.partial` 目录可删除。
