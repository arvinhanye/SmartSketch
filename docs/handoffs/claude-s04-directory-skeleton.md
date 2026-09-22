# Claude 交接：S-04 目录骨架落地

- **状态**：DONE
- **日期**：2026-09-22
- **范围**：把 `AGENTS.md` §3 角色表与 `docs/architecture.md` 源码映射表里**指向但并不存在**的路径全部建出来，并补上 `tests/`、`prompts/`、`evaluation/`、`datasets/`、`NOTICE`。只建目录与约定，不写业务代码、不装依赖、不初始化前后端框架。

## 问题

所有权表只有在路径真实存在时才可执行。改造前 `src/backend/app/` 下只有一个 `__init__.py`，`tests/`、`prompts/`、评测资产目录全部不存在——并行的 Agent 只能各自发明目录名，而 §5 完成标准却要求「运行最小相关测试」。

## 已交付

| 路径 | 内容 |
| --- | --- |
| `src/backend/app/{api,schemas,services,repositories,workers}/` | 各含 `__init__.py` 与 5 行 README，逐条对应源码映射表「不应包含」列与 `.claude/rules/backend.md` 的分层方向 |
| `tests/{backend,frontend,contracts}/` | 各含 README（命名约定、归属、运行方式）；`tests/README.md` 含六项优先覆盖清单 |
| `prompts/` | `README.md`（版本化与「版本—改动—效果」约定）、`TEMPLATE.yaml`（字段骨架）、`MANIFEST.md`（8 项，全 TODO） |
| `evaluation/` | `README.md` + `reports/`（报告产出位置，内容不入库） |
| `datasets/` | `README.md` + `raw/`（原始资料位置，内容不入库） |
| `NOTICE` | 两个参考项目的来源与许可，以及借用代码时的四项强制动作 |
| `.gitignore` | 新增 `datasets/raw/*`、`evaluation/reports/*`，各保留 `.gitkeep` |
| `scripts/verify/manifests/*.txt` | 新增条目；必需文件 28 → **48 项** |
| `scripts/verify/{backend,frontend}.sh` | 按任务要求预留测试调用点（注释形式，当前仍 SKIP） |

未触碰 `src/frontend/`、`src/contracts/` 内容、`docs/decisions/`、`scripts/verify.sh` 本体。

## 关键决定

1. **不创建 `pyproject.toml` / `package.json`**。运行器配置属于 M0-03 与 M0-02。`backend.sh` / `frontend.sh` 里以注释写出将来要启用的命令（`pytest tests/backend`、`vue-tsc` 等），两端初始化时取消注释即可，不必改 `scripts/verify.sh` 本体。
3. **测试目录按被测对象分，与 `src/` 所有权边界对齐**，而不是按测试类型（unit/integration）分。后者会让两个 Agent 同时写进同一个目录，正是 S-03 要消除的写争用。
4. **提示词是代码资产，一个提示词一个 YAML**，业务代码按 `id` 加载，正文不进 `src/`。新增提示词新建文件而非追加，与 AGENTS.md §3「写争用规则」一致。
5. **标注集与原始资料严格分开**：可入库的是标注元数据（知识点名、关系三元组、来源定位 `{document_id, page, section}`），不可入库的是教材原文。`datasets/README.md` 明确要求「来源用引用而不是原文」，需要正文判定时截取不超过一句并注明出处。
6. **`NOTICE` 先建后用**。当前确实没有复制任何第三方代码，文件如实写明这一现状；真正借用时有确定的登记位置，不必事后补。

## 后端分层 README 的「不放什么」

逐条对应源码映射表的「不应包含」列：

| 层 | 不放 |
| --- | --- |
| `api/` | 业务编排与领域规则（→ `services/`）、Cypher 与查询字符串拼接（→ `repositories/`）、对外 DTO 定义（→ `src/contracts/`） |
| `schemas/` | 对外 DTO 的重复定义或再声明、持久化实现、业务规则 |
| `services/` | HTTP 与框架细节、Cypher 与 SQL、提示词正文（→ `prompts/`） |
| `repositories/` | 产品策略与业务判断、HTTP 细节、跨存储事务编排 |
| `workers/` | Web 请求处理、领域规则、直接拼 Cypher |

每份 README 都写了依赖方向 `api → schemas → services → repositories`，不得反向。

## 已运行命令与真实结果

```text
./scripts/verify.sh
  structure → core 31 / backend 13 / frontend 2 / contracts 2，合计 48 项，✓ 结构检查通过
  backend / frontend / contracts → SKIP（三端均未初始化）
  → All verification checks passed.   [exit=0]

bash -n scripts/verify/*.sh              → passed
python3 -c "yaml.safe_load(prompts/TEMPLATE.yaml)" → 可解析，14 个字段

验收 A — docs/architecture.md 源码映射表 7 个路径
  ✓ src/frontend/  ✓ src/backend/app/api/  ✓ .../schemas/  ✓ .../services/
  ✓ .../repositories/  ✓ .../workers/  ✓ src/contracts/      → 全部存在

验收 B — AGENTS.md §3 角色表所有权路径
  ✓ docs/  ✓ docs/tasks/  ✓ specs/  ✓ src/backend/  ✓ src/backend/app/services/
  ✓ src/contracts/  ✓ src/frontend/  ✓ tests/
  ✗ workers/（裸路径，歧义，按任务要求留给 S-05）
  「评测资产」→ evaluation/ + datasets/ 均已存在

验收 C — git status 中的待提交文件 29 个
  课程资料/二进制（pdf/docx/pptx/xlsx/png/zip/db/…）→ 无 ✓
  超过 20KB 的文件 → 无 ✓

.gitignore 实测
  datasets/raw/textbook.pdf     → IGNORED
  datasets/raw/.gitkeep         → tracked（目录得以保留）
  evaluation/reports/run.md     → IGNORED
  evaluation/reports/.gitkeep   → tracked
  datasets/cs101/nodes.jsonl    → tracked（标注集应当入库）

任务给定的路径检查 python3 -c "..." → exit=0
```

## 未解决 / 需要确认

1. **`prompts/MANIFEST.md` 已按方案原文改正**（见下节「表 6.8 核对结果」）。原先的 8 个 `id` 是推导的，已全部替换为方案表 6.8 的真实名称。
2. **`gen_study_material`（讲解与练习题）在 `docs/product.md` 的 MVP 范围里没有对应能力**，任务板也没有承接它的任务。是方案范围大于当前 MVP，还是 MVP 漏了一项，需要产品/协调 Agent 判定。已写进 `prompts/MANIFEST.md`，但**未登记为未决问题**——`docs/tasks/` 不在本次可改文件清单内。
2. **`AGENTS.md` §3 的裸 `workers/` 仍然不存在**。它既可读成 `src/backend/app/workers/`（已建），也可读成仓库根的 `workers/`。按任务要求留给 **S-05**，本次未动。
3. **`tests/` 的所有权有交叉**。§3 把 `tests/` 整体判给测试 Agent，但 `tests/backend/README.md` 被放进 `manifests/backend.txt`（由后端 Agent 维护）。这样划是为了让每个 Agent 只改自己那份清单，但与 §3 的字面表述不完全一致，建议与 `workers/` 一并在 S-05 澄清。
4. **本任务没有在 `docs/tasks/M0.md` 加 S-04 行**：`docs/tasks/` 不在本次可改文件清单内。需要协调 Agent 补一行，证据指向本交接文件。
5. **本仓库自有代码的许可未定**，`NOTICE` 末尾已写明；确定前不要对外分发。

## 表 6.8 核对结果

交接初稿里的 8 个 `id` 是按仓库文档推导的，当时标注为「待核对」。随后拿到方案原文核对完毕：

- **清单实际是 S2 §6.7 的表 6.8「提示词清单」，不是表 6.10**（任务描述里的编号有误）。
- 命名风格是**下划线**而非连字符，已统一；`prompts/README.md` 与 `TEMPLATE.yaml` 的说明同步改正。
- 推导结果与原文的出入：

| 推导 | 原文 | 情况 |
| --- | --- | --- |
| `knowledge-point-extraction` | `extract_entities` | 对应，改名 |
| — | `extract_entities_gleaning`（补漏抽取） | **漏了一项**，已补 |
| `relation-extraction` | `extract_relations` | 对应，改名 |
| `entity-merge-disambiguation` | `judge_duplicate` | 对应，改名 |
| `definition-normalization` | `summarize_definition` | 对应，改名 |
| `query-keyword-expansion` | `rewrite_query` | 对应，改名 |
| `qa-answer-with-citation` | `answer_with_context` | 对应，改名 |
| `qa-coverage-judge` | — | **多推了一项**：方案把「资料不足时明确告知」并入 `answer_with_context`，未拆成独立提示词 |
| `learning-path-rationale` | — | **多推了一项**：方案无此提示词 |
| — | `gen_study_material`（讲解与练习题） | **漏了一项**，已补；但 MVP 范围内无对应能力 |

另外补进 `prompts/README.md` 的方案 §6.7 迭代路径：
`零样本 → 加入类型定义 → 加入示例 → 加入反例与「仅提到不算前置」准则 → 两阶段拆分`。

顺带核对 S-03 填的里程碑日期：方案表 4.2 与 `docs/tasks/M0.md`、`M1.md` 所记**完全一致**（M0 9.16–9.19、M1 9.20–9.26、M2 9.27–10.2、M3 10.3–10.5、M4 10.6–10.8）。方案未写年份，2026 仍为按当前日期的推定。

方案原文（`智绘学途_S2解决方案 copy.pdf`，位于主仓库根目录）**不入库**：已加入 `.gitignore` 的 `*.pdf` 规则，并写进本机 `.git/info/exclude` 以立即生效。

## 回滚

只新增目录、文档与清单条目，无数据影响、无依赖变更。

```bash
git revert <本次提交>
```

手工回滚则需：删除 `tests/`、`prompts/`、`evaluation/`、`datasets/`、`NOTICE` 与 `src/backend/app/` 下五个新建包，还原 `.gitignore`、四份 manifest 与 `scripts/verify/{backend,frontend}.sh`。注意 `.gitignore` 的还原要一并确认没有课程资料因此变成可提交状态。

## 下一位 Agent 的首个动作

- **Data/AI Agent**：先用方案表 6.10 核对并改正 `prompts/MANIFEST.md` 的 8 个 `id`，再复制 `TEMPLATE.yaml` 起草第一个提示词。改动必须带 `changelog` 四项，并在 `datasets/` 的标注集上重跑评测——标注集本身受 D-01 阻塞（已逾期）。
- **Backend Agent（M0-03）**：分层包已就位，直接按 `api → schemas → services → repositories` 填代码；初始化完成后取消 `scripts/verify/backend.sh` 里预留调用点的注释，并把新增必需文件加进 `manifests/backend.txt`。
- **Frontend Agent（M0-02）**：同理，改 `scripts/verify/frontend.sh` 与 `manifests/frontend.txt`，测试写进 `tests/frontend/`。
- **协调 Agent（S-05）**：澄清 `workers/` 与 `tests/` 的所有权表述，并补 S-04 的任务行。
