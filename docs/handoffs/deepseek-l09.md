# L09 在线向量、拒绝 `local`、正式启动入口

```text
task_id: L09
review_status: ready_for_review
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-contest-sprint-77644f
branch: claude/smartsketch-contest-sprint-77644f（仅本地提交，未推送）
base_commit: 8c61bcf
head_commit: 本任务提交
author: DeepSeek harness
根据: docs/handoffs/claude-l09-handoff.md（Claude 未实现，转交本 harness）
changed_files:
  - src/backend/app/config.py（仅 _check_rules 中 local 一处，见 6.2）
  - tests/backend/test_l09.py（新增 3 例）
  - tests/backend/test_b06.py（仅 6.3 三处；不删用例）
  - scripts/check-embedding.py（新增，755）
  - scripts/start.sh（新增，755）
  - scripts/start-demo.sh（--personal、根密钥补齐、模式分支、按模式区分的启动提示）
  - docs/runbook.md、docs/integrations.md
  - docs/superpowers/specs/2026-10-02-contest-sprint-design.md（第 11 节补记 L09 核对结果）
  - docs/tasks.md（L09 认领与完成）
```

## 交付

- **`EMBEDDING_MODE=local` 在配置校验阶段被拒**：`load_settings` 抛 `SettingsError`，信息指出 `EMBEDDING_MODE`，不再留到首次调用才失败（ADR-081 决定 2）。枚举值保留。
- **`scripts/check-embedding.py`**：按交接第 5 节第 1 条的修正版实现——自己按字面值读仓库根 `.env`（不覆盖已在环境中的变量，不当 shell 执行），macOS 上未设 `SSL_CERT_FILE` 时自动用 certifi。只打印模型、维度与耗时，不打印 key 与向量。退出码 0 成功 / 2 配置非法或不是 `online` / 3 调用失败。
- **`scripts/start.sh`**：正式入口（5 行包装，`exec start-demo.sh --personal "$@"`）。
- **`scripts/start-demo.sh --personal`**：`LLM_MODE=personal` + `APP_ENV=development`；启动前校验 `EMBEDDING_MODE=online` 与四项变量，缺任一以中文原因退出，**不静默落到演示模型或演示向量**；与 `--live` 互斥；不导入演示课程；`MODEL_CREDENTIAL_KEY` 为空时自动写入随机值；macOS 上补 certifi 根证书；启动提示按模式区分（personal 不再显示「演示环境」，改为提示先到「模型 API 设置」保存自己的模型 API）。
- 文档：`runbook.md` 新增「一键启动，正式模式」一节（所需变量表、根密钥说明、`check-embedding.py` 用法与退出码、冒烟结果），模式表补 `personal` 行，第 62 行「`online`/`local` 时照用」改为只有 `online`，故障表补 5 行；`integrations.md` 删掉 `EMBEDDING_MODEL` 的 `local` 义务、五项状态改为已签收（ADR-081）并写入实测可用的基址。

## 关键决定与对交接的三处偏离（均有理由，请复核）

1. **互斥写成显式 `if`**：交接 6.5 给的是 `((live)) && ((personal)) && die "…"`。在 `set -e` 下该写法依赖「`&&` 列表中非末位命令失败不触发退出」的细节，改成 `if ((live)) && ((personal)); then die …; fi`，语义相同且不依赖该细节。
2. **`--help` 的 sed 范围 2,19 → 2,20**：头部注释因新增 `--personal` 用法行多一行，不改则帮助文本被截掉最后一行（`兼容 macOS 自带的 bash 3.2` 那行）。
3. **`--live` 分支的 `case "${EMBEDDING_MODE:-}" in online|local)` 保持不动**：交接只要求改 runbook 的表述，未要求改这里。保留 `local` 是有意的——它会走到配置校验并被拒、错误信息指出 `EMBEDDING_MODE`；若从 case 删掉，`local` 会落进 `*)` 被静默改成演示向量，反而违反 ADR-081「不再假装支持」。已在脚本注释与交接里说明。

另外，交接未点名但属 L09 所有权范围内的少量补充：runbook 模式表新增 `personal` 行与 5 行故障排查、`integrations.md` 填了实测可用的基址样例值。未改 L03–L08、L10 已提交的任何文件。

## verification

| 命令 | 实际结果 |
| --- | --- |
| `pytest tests/backend/test_l09.py`（Step 2，改前） | **1 failed, 2 passed**——`test_local_embedding_is_rejected_with_a_clear_name` 报 `DID NOT RAISE SettingsError`，与计划预期一致 |
| `pytest tests/backend/test_l09.py tests/backend/test_b06.py tests/backend/test_e07.py tests/backend/test_demo_mode.py` | **93 passed**（改前同批为 3 failed、87 passed；`test_e07.py`、`test_demo_mode.py` 无需改动，与交接 6.3 一致） |
| `pytest tests/backend tests/tooling`（互斥门禁） | **3648 passed, 27 skipped, 0 failed**（14:16）。等于 L08 基线 3645 + 本次新增 3 例；`tests/backend` 单独 3586 passed / 27 skipped / 0 failed。见下方「环境与沙箱」第 1 条 |
| `.venv/bin/python scripts/check-embedding.py` | **exit 0**：`ok model=text-embedding-v4 dimensions=1024 seconds=0.66`（首次）与 `seconds=0.41`（复跑） |
| `scripts/start.sh --no-open` | **正式模式起全**：API `/health` → `{"status":"ok","version":"0.1.0"}`；`GET /api/v1/me/model-config` → `{"runtime_mode":"personal","configured":false}` ← 这是「确实跑在 personal 而非 demo/live」的正面证据；前端 5174 → HTTP 200；`worker.log` 与 `api.log` 中 `Invalid configuration` 计数 **0**；停止后 8001/5174 均已释放、无残留进程，Neo4j 按设计保留运行 |
| `scripts/start.sh --live` | exit 1，`错误：--live 与 --personal 不能同时使用` |
| `EMBEDDING_MODE=demo scripts/start.sh --no-open` | exit 1，`错误：--personal 需要在 .env 设 EMBEDDING_MODE=online 并填写 …（ADR-081）。`——「正式入口不静默切 demo」的直接验证 |
| `EMBEDDING_MODE=local scripts/start.sh --no-open` | exit 1，同上（ADR-081 拒绝 `local`） |
| 缺 `EMBEDDING_API_KEY` 的 `--personal` 启动 | exit 1，`错误：--personal 需要在 .env 填写 EMBEDDING_API_KEY。`（用临时假 `.env` 触发；真实 `.env` 以 `mv` 让位并在同一命令的 `trap` 中还原，事后已逐键核对长度一致、无残留文件） |
| `PATH="$PWD/.venv/bin:$PATH" ./scripts/verify.sh` | **exit 0**：`block-dangerous hook tests passed.` / `PASS contracts gate` / `Scaffold verification passed.` |

## 环境与沙箱（两条与 L09 无关、但会挡住下一位 Agent 的发现）

1. **PTY 被沙箱挡住，4 个 tooling 用例失败**：`pytest tests/backend tests/tooling` 在受限沙箱下会得到 `4 failed, 3644 passed, 27 skipped`，4 条全是 `tests/tooling/test_k07.py` 的交互式用例，报 `OSError: out of pty devices`。**已确认为环境限制、与 L09 无关**：`kern.tty.ptmx_max` 为 511 而当时仅 3 个 tty 在用，用一个不含本仓库任何代码的 `.venv/bin/python -c "import pty; pty.openpty()"` 也直接报同一错误；放开沙箱后这 18 条 `test_k07.py` 全部通过（18 passed），同一命令随即得到 3648 passed / 0 failed。`test_k07.py` 不引用本次改动的任何文件。
2. **`./scripts/verify.sh` 裸跑会红**：`scripts/verify/contracts.sh` 里硬编码 `python3`，而本机 PATH 首位是 `/usr/local/bin/python3`（3.11.9），它没有 `pyyaml`/`pytest`/`jsonschema`/`openapi-spec-validator`，于是契约门禁报 `ModuleNotFoundError: No module named 'yaml'` 与 `No module named pytest`（25 项负向测试只过 3 项）。把工作区文档指定的解释器放到 PATH 首位即恢复：`PATH="$PWD/.venv/bin:$PATH" ./scripts/verify.sh` → exit 0。L08 交接记录的裸跑 exit 0 应是其 shell 里 `python3` 解析到别的解释器（PATH 里有 `/opt/anaconda3/bin`）。**未改 `contracts.sh`**：它不在 L09 的文件所有权内，交给下一位或用户决定（可选修法：`PYTHON="${PYTHON:-python3}"` 并全文替换）。

## 预算与用量登记

- 本次真实向量调用 **2 次**（`check-embedding.py` 两次成功执行），单条文本 11 个汉字，两次约 22 计费 token；**LLM 调用 0 次**，无付费抽取与问答。
- `check-embedding.py` 直接调 `build_embedding_client`，不经过 E04 的预写/回写路径，因此 `model_calls` 无新增记录；用量只在此登记。
- 冲刺累计：101054（L02 抽取）+ 约 22 ≈ **101076 / 5000000**。

## unverified

- **只验证了 1 次向量请求连通**，没有跑通整条「发布课程 → 向量化 → 学生提问检索」的真实闭环；本任务的验收口径以计划 Task 9 Step 7 为准（1 次真实请求返回配置维度）。真实检索可用性的完整证据仍待 L02 问答基线补测。
- `verify.sh full` 与 `integration` 档未跑（本次只跑后端全量与基础档；前端未改动）。集成档需 Docker 与 Playwright 浏览器。
- `--live` 端到端未重跑（本次只改了它的向量注释与 mode 分支结构；真实抽取是付费调用，未触发）。
- `--personal` 的逐变量缺失校验只实测了 `EMBEDDING_API_KEY` 一条路径，其余三项走同一 `for` 循环，未逐一触发。
- 未验证任何账号在 personal 模式下保存个人模型 API 之后的上传/问答（属 L10 走查与 L02 补测范围）。

## 本任务对工作区的副作用（可复现，非破坏性）

- `.env`（Git 忽略、权限 600）由 `scripts/start.sh` 自动补写了 `MODEL_CREDENTIAL_KEY`（44 字符 base64 = 32 字节）。**此前为空**；本轮尚无任何已保存的个人模型配置，因此清空它不会使任何东西失效。其余 `.env` 内容未被改动。
- 冒烟运行执行了 SQLite/Neo4j 迁移与演示账号预置；三者均为「已存在，未变」（`exists, unchanged`）。未上传资料、未发布课程、未写入向量索引。
- Neo4j 容器仍在运行（`scripts/start-demo.sh` 的设计行为），停止用 `scripts/dev-down.sh`。

## api_and_data_changes

- **无契约、无迁移、无 DTO 变更**，`src/contracts/` 未动。
- 唯一语义变更：`EMBEDDING_MODE=local` 从「必填模型名即可通过」变为「配置校验即拒绝」，错误信息含 `EMBEDDING_MODE`。
- 新增运维入口：`scripts/start.sh [--no-open]`、`scripts/start-demo.sh --personal`、`.venv/bin/python scripts/check-embedding.py`。

## rollback

1. `src/backend/app/config.py`：把 `elif settings.EMBEDDING_MODE == "local":`（含注释两行）还原为 `elif settings.EMBEDDING_MODE == "local" and not _has_value(settings.EMBEDDING_MODEL): invalid.add("EMBEDDING_MODEL")`。
2. `tests/backend/test_b06.py` 三处还原（参数表 `EMBEDDING_MODE`→`EMBEDDING_MODEL`；用例名改回 `test_complete_fallback_and_local_embedding_are_accepted` 且向量改回 `local`；worker 用例两处 `online` 改回 `local` 并去掉 `EMBEDDING_BASE_URL`/`EMBEDDING_API_KEY`）；删除 `tests/backend/test_l09.py`。
3. 删除 `scripts/start.sh`、`scripts/check-embedding.py`；`scripts/start-demo.sh` 与四份文档回退本提交。
4. 数据不受影响（无迁移、无破坏性变更）。`.env` 的 `MODEL_CREDENTIAL_KEY` 可留可清；清空只影响「已保存的个人模型配置」，本轮尚无此类数据。
5. 整提交回退：`git revert <本提交>`。

## next_action

1. **L02 问答基线补测**（现向量已可达）：发布本地库里的课程 `2ace598581f349ec9943dea90bc7fdf1`（任务 `205f9311572846b8bc192ff1f67e244f`，82 知识点 / 73 关系草稿），添加 `demo_student`，再跑 `evaluation/measure_web_flow.py ask`，结果追加到 `evaluation/reports/l02-baseline-2026-10.md`。注意：用 `scripts/start.sh` 起服务时 `demo_student` 必须先在设置页保存自己的模型 API，否则提问会返回 409「需要配置模型」（这是本轮验证过的设计行为）。
2. **L10 真实页面走查**：计划 Task 10 Step 9 的六步，补到 `docs/handoffs/claude-l10.md`。
3. **用户决定**：本分支的提交与推送授权（本次只做本地提交，未推送、未合并）；`scripts/verify/contracts.sh` 的 `python3` 硬编码是否修（见「环境与沙箱」第 2 条）。
