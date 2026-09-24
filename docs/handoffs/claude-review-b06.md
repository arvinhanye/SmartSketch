# 交接：审查 B06（PR #21）、同步 main 与集成修复

- `task_id`: REVIEW-B06
- `status`: 审查完成；两项 P2 需 ArvinHan 签收后才能合入；集成缺陷已修
- `审查目标`: `origin/B06` @ `4142156`（PR #21，kongsc；含 B05 提交 `e8ce796`）。B06 自身提交为 `ca353b1`、`2930052`，`4142156` 是它合入旧 main（`f9dfc8f`）
- `同步`: 把已同步 main 的 B05 分支合入 B06，冲突 3 处（见下）；随后一个集成修复提交

## 冲突处理

- `.env.example`：两段都保留，即 B06 的 `PUBLISH_LEASE_SECONDS`、`COURSE_LOCK_WAIT_SECONDS`，以及 main 的 `RECOMMEND_WEIGHT_*` 四项。
- `specs/teacher-review-publish.md`：「单一空间不变式」取 main 的修订 2 文本（B06 分支上是旧版）；「启动门禁」保留 B06 的职责标注（见 B06-R02）。
- `docs/tasks.md`：M0-02 行取 main，M0-03 行取 B06；B05、B06 两节放在文末。

## 集成修复（Claude，提交 `dbfb63d`）

同步后 `test_env_example_covers_every_setting` 失败：main 按 ADR-014 修订 1 在 `.env.example` 登记了 `RECOMMEND_WEIGHT_*`，B06 的 `Settings` 没有这些字段。`docs/integrations.md`「启动校验」写明了四项成组规则，属于 B06 的范围，所以在 B06 分支内补齐：

- 四项都不设或都为空时，`Settings.recommend_weights` 返回 S2 缺省值 `(0.35, 0.25, 0.20, 0.20)`；四项都设时按固定顺序使用所设值。
- 以下情况拒绝启动，并只报告四个变量名：只设一部分；有负数或非有限值；全为 0；和偏离 1 超过 `1e-9`。
- 新增 11 个用例，先 RED（12 failed，含原失败用例）后 GREEN。反向篡改：放宽和的容差 → 2 条失败；不把空串当未设置 → 1 条失败。

请 kongsc 知悉这次改动；如果希望由自己实现，可以撤销这一提交后另行提交。

## 已运行命令与结果（macOS，Python 3.13.5）

| 命令/核对 | 结果 |
| --- | --- |
| `python -m pytest tests/backend -q` | 58 passed（B05 3 + B06 55） |
| `./scripts/verify.sh`、`git diff --check origin/main HEAD` | exit 0 |
| `python -m app`（`SQLITE_URL` 指向 scratchpad） | `/health` 200；SQLite 写入 `embedding_space_state = (1, '', 1024, 1)`，即 fake 空间 |
| 同一 SQLite，`EMBEDDING_MODE=local EMBEDDING_MODEL=bge-m3` 再启动 | exit 3，`mismatch: recorded fake/1024, configured bge-m3/1024; 需运行离线重新向量化命令` |
| `LLM_MODE=live LLM_API_KEY=sk-secret-XYZ`，其余不设 | exit 1，只列出缺失变量名；日志中密钥出现 0 次 |
| 只设 `RECOMMEND_WEIGHT_UNLOCK=1` | exit 1，列出四个权重变量名 |

## 审查意见

- **B06-R01（P2，需签收）**：原子清单给 B06 的范围只有 `config.py` 和 `test_b06.py`；实际还新增了 SQLite 表 `embedding_space_state`，在 API 启动（lifespan）时建表并写入，走的不是迁移。它承担规格要求的「SQLite 记录当前空间（单行）」，设计合理：`BEGIN IMMEDIATE`、单行 CHECK、不一致时不改旧记录。但这是一个数据模型决定：表名不在 ADR-008 / A10 命名基线里，而且要求 C01 的 `001_base.sql` 与迁移运行器接管此表。需要签收表名与「C01 接管」约定，建议写进 ADR-012 补注或命名基线。
- **B06-R02（P2，需签收）**：B06 改了已签收的 `specs/teacher-review-publish.md`（ADR-012）两处职责标注。PUB-32 与「启动门禁」改为：B06 提供共享检查，API 在 lifespan 调用，C09 的 worker 入口必须调用，离线命令归后续重新向量化任务。规则本身没变，只是拆分职责，但按惯例已签收规格的文字改动需要签收。
- **B06-R03（P3）**：模块级 `app = create_app()` 在导入时读取并校验环境变量，这是有意为之且有测试覆盖。代价是任何 `import app.main` 在非法环境下都会抛错，后续工具和脚本应改为导入 `create_app`。
- **B06-R04（P3）**：默认 `SQLITE_URL` 是相对路径，按进程工作目录解析；README 和 `.env.example` 已写明，API 与 worker 需从同一目录启动。

## 下一步

- ArvinHan 签收 B06-R01、R02 后，先合 PR #14，再合 PR #21。
- C01 认领时须接管 `embedding_space_state`；C09 的 worker 入口须调用 `validate_embedding_space`。
