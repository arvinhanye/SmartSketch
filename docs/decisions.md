# 架构决策记录（ADR）

## ADR-001：前端采用 Vue 3 + AntV G6 的 2D 图谱

- **日期**：2026-09-22
- **背景**：当前赛题 MVP 需要稳定呈现关系、筛选和编辑；早期方案中的 3D 模式会增加渲染与交互复杂度。
- **决定**：使用 Vue 3、TypeScript、Vite 和 AntV G6，只交付 2D 图谱。
- **后果**：优先建设图谱可读性与审核体验；后续若引入 3D，作为独立规格与 ADR。

## ADR-002：Neo4j + SQLite 双存储

- **日期**：2026-09-22
- **背景**：图谱遍历/向量检索与业务任务、进度、版本的数据访问模式不同。
- **决定**：Neo4j 保存图谱与向量索引，SQLite 保存课程业务、任务、进度和版本元数据。
- **后果**：跨存储操作由服务层编排，必须记录失败状态并支持重试/补偿。

## ADR-003：可信问答以来源引用为硬契约

- **日期**：2026-09-22
- **背景**：课程问答必须可复核，不能仅依赖模型生成内容。
- **决定**：问答 API 要么返回至少一个可定位来源，要么返回 `NOT_COVERED`。
- **后果**：检索、提示词和响应 DTO 都需要来源字段；引用校验纳入测试。

## ADR-004：契约唯一真源与 ADR 编号裁定

> **签收状态：已签收（ACCEPTED）**，ArvinHan，2026-09-22。签收行见本条正文末尾。
> 本条由原子任务 **A01** 提交，签收后成为生效的团队决定：接口变更第一步必须改 `src/contracts/api.v1.yaml`，清单中 `src/contracts/v1/python/*.py` 的候选路径按下方「清单路径映射」改读。
> **签收范围**：本条关闭 PLAN-D01 中的「唯一源」与「ADR 编号」两项。PLAN-D01 的第三项「API 前缀」本条只记录现状 `/api/v1`，最终裁定仍属 A02，**不因本条签收而关闭**。

- **日期**：2026-09-22
- **背景**：main（`05d214c`）只有协作骨架，`src/contracts/` 下只有一份说明，没有任何机器可读契约。同日三个 Claude worktree 各自产出了互斥或重叠的契约成果，且其中两份都自称「唯一真源」：

  | 分支 | HEAD | 契约形态 | 自称的人工编辑真源 | 规模 |
  | --- | --- | --- | --- | --- |
  | `claude/multi-agent-contract-format-209be9` | `bef9b91` | 只有 `src/contracts/README.md` 的格式约定与目录规划，无实际契约文件 | `src/contracts/v1/python/`（手写 Pydantic v2） | 0 行契约 |
  | `claude/tech-plan-review-improvements-ff30e0` | `6ccbe5e` | 已冻结 OpenAPI 3.1 YAML + 错误码/事件时序文档 | `src/contracts/api.v1.yaml` | 1690 行，22 路径 / 29 操作 / 52 schema / 181 `$ref` |
  | `claude/worktree-contract-conflicts-740adb` | `1bc63ad` | 上面两支的合并 + 按 codex R01～R05 的修复，含生成脚本与生成物 | `src/contracts/api.v1.yaml` | 1835 行，22 路径 / 29 操作 / 59 schema / 189 `$ref` |

  本条**不是第四次重新发明**。`740adb` 已在 2026-09-22 09:22（`1bc63ad`）以「协调人裁定」的名义选定 YAML 真源并改写了 ADR-004；但该裁定 (1) 未并入 main，(2) 在 `docs/reviews/claude-review-state.json` 中仍是 `COMPLETION_CANDIDATE_WAIT_STABILITY`（只观察到一次稳定 HEAD，未完成审查），(3) 晚于 `docs/atomic-task-plan.md`（08:33 写成）——清单因此仍按 Pydantic-first 的候选路径书写。A01 的职责是：核对该裁定是否成立、把它提交给技术负责人签收，并把编号冲突与路径映射一次定清，避免第四套接口。

- **评估方案**（A/B/C 的原始对比来自 `209be9` 的 ADR-004 首版，原样保留其否决理由，便于复核本次是否只是换个说法）：

  | 方案 | 人工编辑真源 | 优点 | 代价 | 本次结论 |
  | --- | --- | --- | --- | --- |
  | A. Pydantic → OpenAPI → TS | 手写 `src/contracts/v1/python/` | 真源同时是 FastAPI 运行时校验模型，响应结构不可能偏离契约；不引入第三种语言 | `openapi.json` 要等 FastAPI 应用存在才能导出，而契约必须先于应用冻结；SSE 事件与图谱交换不在 OpenAPI paths 内，仍需单独导出 JSON Schema | 否决 |
  | B. 手写 OpenAPI YAML 双向生成 | `src/contracts/api.v1.yaml` | 语言中立；前端不等后端；人类可直接评审 | 首版的否决理由：后端仍要 Pydantic，生成后通常手改，于是「契约」与「运行时校验」是两份会漂移的产物 | 见 B′ |
  | B′. B + Pydantic 也是生成物、禁止手改 | `src/contracts/api.v1.yaml` | 消掉 B 唯一的否决前提：Pydantic 由 `datamodel-code-generator` 生成，套用与前端生成物同一条规则（入库、禁改、`--check` 兜底）；SSE 事件与图谱格式直接从 `components/schemas` 摘成独立 JSON Schema | 新增两个开发期生成器依赖；生成物入库后可能与真源不同步，需门禁兜底 | **采纳** |
  | C. JSON Schema 为真源 | `src/contracts/v1/*.schema.json` | 对事件与交换文件表达力最好，两端都是生成方 | 不描述路径、方法、状态码与错误响应，REST 契约仍要第二份文档 | 否决 |

- **为什么采纳 B′ 而不是清单默认的 Pydantic-first**（四条可核查依据）：
  1. 首版否决 B 的**唯一**理由是「后端仍需手写并手改 Pydantic」。该前提可直接消掉：Pydantic 不手写、不手改。前提消失后否决理由不成立。
  2. A 的核心优势「真源即运行时校验对象」要等 FastAPI 应用存在才能兑现，而契约必须在骨架阶段冻结（B08～B13 的依赖方 B15/C12 都要先拿到类型）。A 在当前阶段无法自洽地产出生成物。
  3. 迁移成本不对称且可量化：YAML 侧已有 22 路径 / 29 操作 / 59 schema / 189 `$ref` 并已逐行审查；`v1/python/` 一行未写。选 A 要先付一次翻译成本再重审一遍，选 B′ 成本为零。
  4. B′ 顺带解掉 A 的第二项代价：SSE 事件与图谱交换在 YAML 中就是 `components/schemas`，无需先有 Python 对象即可导出 JSON Schema。

- **决定**：
  1. **真源**：`src/contracts/api.v1.yaml`（OpenAPI 3.1），**唯一允许人工编辑的机器可读契约**。`src/contracts/errors.v1.md`、`src/contracts/events.v1.md` 是配套文档，只写 OpenAPI 表达不了的时序与语义，不重复定义结构。
  2. **生成物**：`src/contracts/v1/generated/`，含 `openapi.json`、`schemas/*.schema.json`、`python/`（Pydantic v2）、`typescript/`（`.d.ts`）。该目录内所有文件**禁止手工编辑**。
  3. **写入方**：真源由后端 Agent 单独拥有并人工编辑；生成物只由 `./scripts/gen-contracts.sh` 写。前端与后端都是**只读消费方**——后端从 `v1/generated/python/` 导入对外 DTO，`src/backend/app/schemas/` 只放不对外暴露的内部模型；前端从 `v1/generated/typescript/` 导入类型，不得在 `src/frontend/` 内重写、断言或用 `any` 绕过。
  4. **生成命令**：`./scripts/gen-contracts.sh`，`--check` 为只校验模式（重新生成后比对，不一致即非 0 退出）；同一份 YAML 生成两次必须字节一致。生成器版本锁在 `src/contracts/toolchain.txt`；缺工具必须非 0 退出，仅 `--allow-scaffold` 可降级且必须打印未完成验收标记（B07 的验收条件）。
  5. **变更顺序（硬规则）**：任何 REST / SSE / 图谱格式变更，第一步必须改 `api.v1.yaml`；同一次提交必须同时包含真源改动、重新生成的产物、受影响的规格或 ADR。生成物出现手工编辑、或 `--check` 不通过，一律拒绝合入。
  6. **不双写**：本条签收后，`v1/python/` 作为「手写真源」的方案作废；清单中指向该目录的路径按下方映射表改读为 YAML 真源 + 生成物，不得同时维护两套。

- **ADR 编号裁定**（解决两个分支对 ADR-004 赋予不同含义的撞号）：

  | 编号 | 主题 | 来源 | 处置 |
  | --- | --- | --- | --- |
  | ADR-001～003 | Vue3+G6 / 双存储 / 来源引用 | main `05d214c` | 不动，三个分支内容一致 |
  | **ADR-004** | 契约唯一真源 | `209be9` 首版（Pydantic）→ `740adb` 改判（YAML） | **即本条**，采纳 B′；首版的方案对比保留在上表以便复核 |
  | ADR-005 | 任务处理状态机 | `209be9` | 保留编号；内容待 A03 复核后随 A10 导入 |
  | ADR-006 | MVP 实现任务取消（修订 ADR-005 第 2 条） | `209be9` | 保留编号；与 A03/A06 一并复核 |
  | ADR-007 | 学习材料生成纳入范围（加分项） | `209be9` | 保留编号；是否同步 main 由 PLAN-D05 / O01 决定，本条不代批 |
  | **ADR-008** | 数据模型命名基线 | `ff30e0` 原 ADR-004 | **撞号改编为 ADR-008**（后合并方改号），编号与 `740adb` 一致；内容待 A02 复核 |

  同批撞号的任务编号一并记录，避免下一位 Agent 用错号：`209be9` 的 M0-04a/M0-04b（起草契约真源与生成链 / 前端消费生成类型）改编为 **M0-09 / M0-10**，与 `ff30e0` 的 M0-04a（REST DTO）区分。

- **ADR 文件形态裁定**：`740adb` 已把单文件 `docs/decisions.md` 拆成 `docs/decisions/ADR-<编号>-<slug>.md` 一条一文件（拆写争用点）。**本条认可该形态为目标形态**，但迁移动作属于 A10 的导入批次，不在 A01 范围内。因此：在 A10 导入前，main 继续使用本文件；导入时本条 ADR-004 **整条替换为指向 `docs/decisions/ADR-004-contract-single-source-of-truth.md` 的索引行，不得留下第二份正文**。

- **原有端点的迁移去向**（22 路径 / 29 操作，逐条有去向，无删除；「去向」指签收后由哪个原子任务负责把该端点的 schema 校核补齐到真源）：

  | 端点（真源中的路径） | 操作 | 去向任务 | 说明 |
  | --- | --- | --- | --- |
  | `/health` | GET | B05 | 唯一不带 `/api/v1` 前缀的端点，保持不变 |
  | `/api/v1/auth/login` | POST | C03 | 登录形态取决于 A05/D-03，端点保留不删 |
  | `/api/v1/courses` | GET, POST | B09 / C04 | |
  | `/api/v1/courses/{cid}` | GET | B09 / C04 | |
  | `/api/v1/courses/{cid}/documents` | GET, POST | B09 / C07 | 上传返回 task_id |
  | `/api/v1/tasks/{tid}` | GET | B10 / C11 | |
  | `/api/v1/tasks/{tid}/events` | GET | B10 / C11 | SSE；事件结构在 `components/schemas` + `events.v1.md` |
  | `/api/v1/tasks/{tid}/cancel` | POST | B10 / C10 | |
  | `/api/v1/courses/{cid}/graph` | GET | B11 / F07 | |
  | `/api/v1/courses/{cid}/kp` | GET, POST | B11 / F07、F08 | |
  | `/api/v1/courses/{cid}/kp/{kid}` | GET, PATCH, DELETE | B11 / F07、F08、F09 | PATCH 携带 `expected_revision` |
  | `/api/v1/courses/{cid}/kp/merge` | POST | B11 / F10 | |
  | `/api/v1/courses/{cid}/kp/{kid}/material` | POST | O05 | 加分项端点；O01 未批准前不实现，**但不从真源删除** |
  | `/api/v1/courses/{cid}/relations` | POST | B11 / F06 | |
  | `/api/v1/courses/{cid}/relations/{rid}` | PATCH, DELETE | B11 / F06 | |
  | `/api/v1/courses/{cid}/review` | GET | B11 / F11 | |
  | `/api/v1/courses/{cid}/publish` | POST | B11 / G 组 | 快照协议待 A04 |
  | `/api/v1/courses/{cid}/versions` | GET | B11 / G 组 | |
  | `/api/v1/courses/{cid}/versions/{version}/rollback` | POST | B11 / G 组 | |
  | `/api/v1/courses/{cid}/progress` | GET, PUT | B12 / I 组 | |
  | `/api/v1/courses/{cid}/recommend` | GET | B12 / I 组 | 评分公式待 A08 |
  | `/api/v1/courses/{cid}/chat` | POST | B13 / J 组 | `answered` / `not_covered` 判别联合 |

  路径前缀现状：`ff30e0` 用 `/api/`，`740adb` 已统一为 `/api/v1/`，与 `docs/architecture.md`、目录 `v1/` 同步。本条按 `/api/v1/` 记录现状，**前缀与 wire 枚举大小写的最终裁定属 A02**，A02 若推翻需同时更新本表。

  > **A02 已裁定（ADR-009，2026-09-22 签收，见本文件下文）**：维持 `/api/v1`，本表无需改动；上方编号表中「ADR-008 内容待 A02 复核」的结果也记在 ADR-009「后果」。

- **清单路径映射**（`docs/atomic-task-plan.md` 使用规则第 3 条要求：选 YAML-first 时，先把 B08～B14、O02、O05 的候选路径映射到实际真源）：

  | 清单任务 | 清单中的候选路径（Pydantic-first 假设） | 签收后的实际真源位置 | 该任务改做什么 |
  | --- | --- | --- | --- |
  | B08 | `src/contracts/v1/python/common.py` | `api.v1.yaml` 的 `components/schemas`（错误模型、错误码枚举、`SourceRef`/`Citation`、关系类型闭集）+ `errors.v1.md` | 校核并补齐公共 schema 的约束与负例测试，不新建 Python 文件 |
  | B09 | `.../courses.py` | `api.v1.yaml` 中 `/courses*`、`/courses/{cid}/documents` 的 paths 与关联 schema | 同上 |
  | B10 | `.../tasks.py` | `api.v1.yaml` 中 `/tasks/*` 的 paths + `TaskEvent` 判别联合 + `events.v1.md` §2 转换表 | 同上 |
  | B11 | `.../graph.py` | `api.v1.yaml` 中 `/graph`、`/kp*`、`/relations*`、`/review`、`/publish`、`/versions*` + `GraphExchange` schema | 同上 |
  | B12 | `.../learning.py` | `api.v1.yaml` 中 `/progress`、`/recommend` 及其 schema | 同上 |
  | B13 | `.../chat.py` | `api.v1.yaml` 中 `/chat` + `ChatResponse`/`ChatEvent` 的 `oneOf` 判别联合 + `events.v1.md` §3 | 同上 |
  | B14 | `scripts/gen-contracts.sh`、`src/contracts/generate.py`、`v1/generated` | `scripts/gen-contracts.sh` + `scripts/gen_contracts.py` + `src/contracts/toolchain.txt` + `v1/generated/` | **`src/contracts/generate.py` 不再需要**（它属于「FastAPI 导出 openapi.json」的 A 方案）；改为验收两次生成字节一致与 `--check` 可检出篡改 |
  | O02 | `.../learning.py`（目标路径） | `api.v1.yaml` 新增目标路径 schema + `specs/learning-path.md` | O01 批准后才动；仍先改真源再生成 |
  | O05 | `.../study_material.py` | `api.v1.yaml` 中已存在的 `/kp/{kid}/material` + 新增缓存/审核 schema + `specs/study-material.md` | 同上 |

- **后果**：
  - 清单中所有 `src/contracts/v1/python/*.py` 的文件范围按上表改读；对应任务的验收从「写 Pydantic 模型」变为「改 YAML 真源 + 重新生成 + 负例测试」。JSON 白名单需在 A10 导入批次随之更新，本条不代改 `docs/atomic-tasks.json`。
  - 新增两个开发期依赖：`datamodel-code-generator`（YAML→Pydantic）、`openapi-typescript`（YAML→TS）。**安装需人工授权**，属 M0-09 第一步；未安装前生成链只能在 `--allow-scaffold` 下降级并打印未完成标记，不得当作通过。
  - B07（修复校验缺依赖假绿）与本条同向：门禁必须区分 PASS / SKIP / FAIL，缺依赖非 0 退出。
  - 本条只裁定「契约怎么表达、谁写、生成什么」。**不裁定**契约内容本身是否正确：`740adb` 的 R03/R04 修复（引用非空、事件判别联合）仍须由 B08/B10/B13 用负例测试复验；schema 表达不了的「引用确属同一课程同一发布版本」必须在服务层实现，不因本条签收而视为已满足。

- **需要人拍板、本条不代批的事项**：
  1. ~~PLAN-D01 的签收本身~~——已于 2026-09-22 由 ArvinHan 签收，见本条末尾。
  2. PLAN-D04：以哪个 worktree 作为集成基线、分批合并顺序与合并权——本条**不触发任何合并**。
  3. 两个生成器的安装授权（M0-09）。
  4. ADR-005/006/007 的内容是否原样同步 main（分别属 A03/A06、PLAN-D05）。

- **推翻条件**（出现以下任一，本条应重开而不是打补丁）：
  1. `740adb` 的 codex 审查结论推翻 `api.v1.yaml` 的内容基线（例如 R03/R04 修复被判不成立）。
  2. 团队决定不把生成物入库；那时 A 与 B′ 的成本对比需重算。
  3. `datamodel-code-generator` 无法从本 YAML 生成可用的 Pydantic v2 模型（B′ 的前提「Pydantic 不手改」失效），此时应回到 A 并承担翻译成本。

- **签收**：ArvinHan 2026-09-22

### ADR-004 生成链实测补注（2026-09-22，**不改变上面的结论，也不构成签收**）

写 ADR-004 时两个生成器本机未安装，「生成物入库」在任何分支上都**没有跑通过**。经授权安装后已实测，结果记录如下，供签收时参考。安装位置：`datamodel-code-generator==0.26.3` 在独立 venv `~/.local/share/smartsketch/contracts-venv`（Python 3.11.9，不动 conda base）；`openapi-typescript@7.4.4` 全局装在 npm prefix `/usr/local`。测试在 scratch 副本中进行，**未修改 `740adb` 的 worktree**。

| 验证项 | 结果 |
| --- | --- |
| 完整生成（不带 `--allow-scaffold`） | exit 0，四个阶段全部产出，无 `INCOMPLETE` 标记 |
| 两次生成字节一致 | PASS（6 个产物 SHA256 全等） |
| `--check` 与真源同步 | exit 0 |
| 篡改检出（`openapi.json` / `python` / `typescript/openapi.d.ts` / `schemas/TaskEvent.schema.json` 各加一个换行） | 四项均非 0 退出，恢复后 exit 0 |
| 生成的 Pydantic 可用性 | import 成功，54 个 `BaseModel` 子类，pydantic 2.13.5 |

- **「推翻条件」第 3 条不触发**：`datamodel-code-generator` 能从本 YAML 生成可用的 Pydantic v2 模型，B′ 的前提「Pydantic 不手改」成立。ADR-004 的结论维持不变（本补注写成时仍待签收，此后已于 2026-09-22 由 ArvinHan 签收）。
- **实测暴露两个缺陷，已在 `740adb` 的 `8865686` 修复**（经用户授权直接改该分支；本仓库的 ADR 不随之改动）。**注意**：第 2 项的修复在 UTF-8 locale 下引入了新的假绿，已在 `978671e` 修复，见下方第 4 条：
  1. `gen-contracts.sh` 的 `--output "$dest/python"` 产出的是一个**没有扩展名的文件** `python`，不是 ADR-004 第 2 条写的 `python/` 目录。内容是合法 Pydantic v2，但按当前路径**无法被 import**。修法：先 `mkdir -p "$dest/python"` 再 `--output "$dest/python/models.py"`，产出内容与修复前逐字节相同，只是落点变了。
  2. `--check` 在产物**缺失**（而非内容不同）时退出码是 2 而不是 1，且「跑 gen-contracts.sh 重新生成」那行提示不会打印——`set -euo pipefail` 下第二次 `diff` 的非 0 退出会让脚本在到达 `exit 1` 前就中止。门禁仍然是红的，不是假绿，但操作者丢了修复提示。修法：把该 `diff` 裹进 `{ ... || true; }`，并为「产物缺失」单独给一条明确信息。
  3. 附带修：两处 `diff` 加 `-x __pycache__`。`python/` 变成目录后，任何人 import 过生成的模型都会在里面留下字节码缓存，那不是契约漂移。
  4. **更正（2026-09-22，Codex S07-R06）**：`8865686` 对第 2 项的修复在 **UTF-8 locale** 下引入了新的假绿。「生成物缺失」那行写成 `"$OUT/$name（…"`，macOS 自带的 bash 3.2 在 UTF-8 locale 下把全角「（」的字节并入变量名，`set -u` 中止；而 bash 3.2 进入 EXIT trap 时 `$?` 已是 0，于是缺产物时 `--check` exit 0，`verify.sh` 输出 "All verification checks passed"。上面那组验证只在 C locale 下跑过，所以漏了。已在 `740adb` 的 `978671e` 修复：变量加花括号，EXIT trap 加「没走到脚本结尾即按失败处理」的守卫，并加先红后绿的回归测试；C / en_US.UTF-8 / zh_CN.UTF-8 下缺产物均实测 exit 1。
- **仍未修（留给 B14 / M0-09）**：`--check` 只遍历本次生成出来的阶段，`v1/generated/` 顶层多出的**整个陈旧阶段目录**检不出来（阶段**内部**多出的陈旧文件能检出）。
- **`740adb` 已入库的 `v1/generated/` 不完整**：只有 `openapi.json` 与 3 个 `schemas/*.json`，缺 `python/` 与 `typescript/`（它们是在降级模式下被跳过的）。这 4 个文件与真源实测一致，但对该分支跑 `--check` 现在会非 0 退出。补齐入库是 M0-09 的动作。
- **版本漂移**：`src/contracts/toolchain.txt` 锁 `jsonschema==4.23.0`，本机校验侧解释器（conda base Python 3.13.5）装的是 4.26.0；`pyyaml` 6.0.2、`openapi-spec-validator` 0.9.0 与锁一致。是否收紧由 B07 处理。

## ADR-009：API 路径前缀、wire 枚举大小写与前置关系成环分流

> **签收状态：已签收（ACCEPTED）**，ArvinHan，2026-09-22。本条由原子任务 **A02** 提交，关闭 PLAN-D01 的第三项「API 前缀」（前两项已由 ADR-004 关闭，PLAN-D01 至此全部关闭）。
> 规范表只有一份，在 `docs/architecture.md`「API 前缀与 wire 枚举」；成环算法与验收在 `specs/course-knowledge-graph.md`「前置关系成环处理」。本条只记录决定与理由，不复制表格。

- **日期**：2026-09-22
- **背景**：ADR-004 裁定了契约「怎么表达、谁写」，但把三处内容漂移留给 A02：
  1. **路径前缀**：S2 表 6.6 与 `ff30e0` 用 `/api/...`；`740adb` 与 ADR-004 端点迁移表用 `/api/v1/...`。
  2. **枚举大小写与遗漏**：AGENTS.md §4、ADR-003、`.claude/rules/backend.md` 写 `NOT_COVERED`，而 YAML 真源的 wire 值是 `status: "not_covered"`；main 的规格状态机缺 `persisting` 与 `cancelled`（Codex R05）；`740adb` 的 `src/contracts/README.md` 写 `not_covered_reason`，YAML 字段却是 `reason`。
  3. **前置关系成环**：S2 规则校验写「出现环时保留置信度较高的边，最弱的边降级为'相关'并进入审核」；`740adb` 的 ADR-005 却把「前置关系成环被拒」列为 `persisting` 的失败原因，按字面读就是一条模型错边让整份资料的任务失败。架构审查把它列为「自动策略与规格待对齐」。
- **评估方案**：

  | 问题 | 方案 | 结论 | 理由 |
  | --- | --- | --- | --- |
  | 前缀 | `/api/v1` | **采纳** | 与真源文件名 `api.v1.yaml`、生成物目录 `v1/`、ADR-004 端点表一致，零迁移成本；主版本号有唯一可见位置 |
  | 前缀 | `/api`（S2 原样） | 否决 | 要改 ADR-004 端点表与 `740adb` 的 22 条路径；v2 时只能靠请求头区分版本 |
  | 未覆盖 | wire `not_covered` | **采纳** | 符合「只有错误码与关系类型大写」的统一规则；YAML、`events.v1.md` 与判别联合 mapping 都不用改 |
  | 未覆盖 | wire `NOT_COVERED` | 否决 | `ChatStatus` 会成为唯一大写的状态枚举，规则出现例外；需改 YAML、事件文档与 discriminator |
  | 自动成环 | 降级不失败 | **采纳** | 与 S2 一致；错边进入审核队列，教师可见可改；任务不因一条低置信度边作废 |
  | 自动成环 | 整个任务 `failed` | 否决 | 一条模型错边就让整份资料的处理作废，教师只能重跑 |
  | 自动成环 | 丢弃成环边 | 否决 | 教师看不到被丢弃的关系，违反「AI 生成、教师审核」的人机协同原则 |

- **决定**：
  1. **前缀**：所有 REST 与 SSE 端点为 `/api/v1`，唯一例外 `GET /health`。S2 的 `/api/...` 视为省略版本号的缩写。ADR-004 端点迁移表不改。
  2. **大小写规则**：UPPER_SNAKE 只用于 `ErrorCode` 与 `RelationType`；其余所有 wire 枚举值（含 SSE 事件名、判别字段取值）一律 lower_snake。
  3. **概念名与 wire 值分离**：`NOT_COVERED`、`TASK_FAILED` 是共同契约中的概念名，wire 分别是 `status: "not_covered"` + `reason`、`stage: "failed"` + `error`，都不是错误码。新代码、测试与前端分支只用 wire 值。AGENTS.md、ADR-003 与角色规则的措辞不改，由架构文档的映射表对照。
  4. **`TaskStage` 取 9 个值**：`queued`、`parsing`、`extracting`、`merging`、`persisting`、`awaiting_review`、`completed`、`failed`、`cancelled`，终态为后三者。转换触发者、取消竞争与重连语义归 A03，本条不定。
  5. **成环按来源分流**：
     - 人工编辑（新建、改类型、改端点、反转、恢复 `rejected`、合并重接边、自环）成环 → 409 `CYCLE_DETECTED` + `details.cycle`，不自动修复；
     - 自动候选成环 → 在环上未经教师确认的 `ai` 边（`status ∈ {draft, low_confidence}`）中选置信度最低者（并列取 `id` 最小），改为 `RELATED_TO` + `low_confidence` 送审核，逐环重复直到无环，任务继续到 `awaiting_review`；
     - 环上无可降级边（草稿已违反不变量）→ 任务 `failed`，`CYCLE_DETECTED`；
     - 发布时仍有环 → 409 `PUBLISH_BLOCKED`。
- **后果**：
  - `740adb` ADR-005 第 1 条中「前置关系成环被拒」作为 `persisting` 失败原因，收窄为「环上无可降级边」这一种情形。A10 导入 ADR-005 时在其文首加注指向本条，不改原文。
  - `740adb` `src/contracts/README.md` 的 `not_covered_reason` 须改为 `reason`（以 YAML 为准），随 A10 导入或 B13 修正。
  - **契约缺口**：`Relation` 没有字段记录「原为 `PREREQUISITE`、因哪条环降级」，审核队列无法向教师解释降级。B11 须先在 `api.v1.yaml` 增加字段并重新生成，F13 才能实现降级。
  - F05（DAG 纯函数）须同时提供「返回环路」与「按本条规则选出待降级边」两种能力；F06（人工写入）只用前者。
  - **ADR-008 复核**（ADR-004 编号表要求 A02 复核）：关系类型、任务状态机、枚举命名与本条一致。唯一差异是 main `docs/architecture.md` 的 Neo4j 文本块标签写 `SourceChunk`，ADR-008 写 `Chunk`。它不是 wire 枚举，本条不裁定，交 A10 导入 ADR-008 时统一。
- **推翻条件**：
  1. 评测或试用显示自动降级大量误伤真实前置关系（例如教师在审核中把降级边改回 `PREREQUISITE` 的比例很高）。此时应重开第 5 条，而不是调参数掩盖。
  2. 需要同时对外提供两个主版本时，前缀规则随 v2 的 ADR 一并重审。
- **签收**：ArvinHan 2026-09-22

## ADR-013：本地账号登录、账号类型与课程内角色分离、教师按用户名加学生、SSE 一次性票据

> **签收状态：已签收（ACCEPTED）**，ArvinHan，2026-09-23。本条由原子任务 **A05** 提交，关闭 D-03。决定方向由 ArvinHan 在会话中逐项选择（登录方式、角色粒度、学生入课方式、教师不开放问答、票据方案），书面条文随后签收。
> 规范表述只有一份，在 `specs/identity-access.md`（访问矩阵、判定顺序、票据协议、IAM-1～25 验收）。本条只记录决定与理由，不复制矩阵。
> **编号说明**：ADR-010、ADR-011 由 A03、A06 使用（PR #5、#6）；A04 的草稿曾与 A03 同撞 010，按 ArvinHan 2026-09-23 的安排预留 012 给 A04，A04 已在 PR #7 改用 **ADR-012**。本条取 013。四者合入 main 时 ADR-010～013 连续、互不重叠。

- **日期**：2026-09-23
- **背景**：
  1. **D-03 从未裁定**。main 与 `209be9` 只把「登录是否先采用本地演示角色」列为待确认；`ff30e0` 与 `740adb` 的契约按用户名 + 口令换 Bearer JWT 编写，并声明「传输层不依赖 D-03」，同样没有裁定。架构审查把它记为「演示登录/正式本地账户决定分支不同步」。
  2. **角色粒度自相矛盾**。S2 表 6.2 同时有 `users.role` 和 `courses_members.role`；契约只有全局 `Role`，JWT 载荷带 `role`，并规定「学生只返回已发布课程」，即学生不需要成员关系就能看到全部已发布课程。而原子清单 C02 要求「同用户不同课程角色独立」。两种读法不能同时成立。
  3. **SSE 鉴权无法落地**（Codex S07-R07 P1）。`events.v1.md` 要求一次性短时效令牌走查询参数，但契约既没有签发端点，也没有给事件操作声明查询参数，该操作仍继承全局 Bearer。A03 的规格把签发端点与作用域、跨课程访问任务的拒绝方式（TASK-19）明确移交给 A05。
  4. 原子清单对 A05 的验收：明确演示角色或账号模式；禁止仅相信请求中的 `user_id`；不扩展生产 SSO。
- **评估方案**：

  | 问题 | 方案 | 结论 | 理由 |
  | --- | --- | --- | --- |
  | 登录方式 | 本地账号 + 预置演示账号 | **采纳** | 与 S2 的 `users.password_hash`、契约 `LoginRequest` 完全一致，契约零返工；演示账号由种子脚本创建，口令来自环境变量 |
  | 登录方式 | 纯演示角色（点按钮进入，无口令） | 否决 | 任何人都能成为教师；需改 `LoginRequest` 契约；课程隔离的演示失去说服力 |
  | 登录方式 | 本地账号 + 演示模式一键填充 | 否决 | 在采纳方案上多一个前端开关和配置项，演示收益小 |
  | 角色粒度 | 账号类型 + 课程内角色 | **采纳** | 满足 C02；与 S2 两张表一致；课程内授权每次回查成员表，移出课程或停用账号立即生效 |
  | 角色粒度 | 仅全局角色 | 否决 | 需改写 C02 验收；教师无法在他人课程里以学生身份旁听，助教类场景日后难以扩展 |
  | 学生入课 | 教师按用户名添加 | **采纳** | 课程隔离语义清楚，`COURSE_FORBIDDEN` 对学生也有意义；只需三个成员操作和一个小页面 |
  | 学生入课 | 选课码自助加入 | 否决 | 多出选课码生成、轮换与防暴力猜测的规则，超出 MVP |
  | 学生入课 | 已发布课程对所有学生开放 | 否决 | 学生侧没有「成员」概念，多课程隔离只剩草稿可言 |
  | 学生入课 | 只由种子脚本写入成员 | 否决 | 教师无法在界面管理学生，演示与真实使用都不便 |
  | SSE 鉴权 | 不透明一次性票据存 SQLite | **采纳** | 真正一次性；API 多进程也成立；实现只需一张表和一条条件更新 |
  | SSE 鉴权 | 限定任务的短时效 JWT | 否决 | 无状态，有效期内可重放，达不到 `events.v1.md` 要求的一次性 |
  | SSE 鉴权 | 改用 Cookie 鉴权 | 否决 | 引入第二套鉴权与 CSRF 防护，偏离契约的 Bearer 方案 |

- **决定**：
  1. **登录**：本地账号，用户名 + 口令，口令慢哈希存储；登录成功签发 HS256 JWT（`sub`、`role`、`iat`、`exp`），默认有效期 8 小时，无刷新令牌，注销由前端丢弃令牌完成。没有注册端点；账号由命令行管理，演示账号由幂等种子脚本创建，口令只从环境变量 `SEED_DEMO_PASSWORD` 读取。登录失败统一 401，同一用户名连续失败 5 次后 60 秒内返回 429。
  2. **身份唯一来源**：调用者身份只来自已验证的访问令牌（或已核销的事件票据）。服务端每次请求按 `sub` 回查用户，已停用即 401。请求体、查询参数、路径、自定义请求头中的任何 `user_id` 或角色都不得用来确定调用者；作用于本人数据的请求体不含 `user_id`。
  3. **两层角色**：`users.role` 是账号类型，只决定默认首页和能否新建课程；课程内一切授权只看 `course_members.role`，每次请求回查。令牌里的 `role` 仅作前端路由提示，服务端不据此授权。学生账号只能做学生成员；教师账号可以在别的课程做学生成员。
  4. **成员管理**：新建课程时创建者在同一事务成为教师成员；`courses.teacher_id` 只用于展示。教师成员按用户名添加学生（已是成员则幂等返回、不改角色），只能移除学生成员；协作教师 MVP 只由命令行管理。学生被移除后数据保留，重新加入恢复。
  5. **授权判定与错误语义**：身份 → 定位课程 → 成员关系 → 课程内角色 → 发布状态 → 子资源作用域，先失败者决定响应。路径带 `cid` 的非成员（含课程不存在）→ 403 `COURSE_FORBIDDEN`；按 `tid` 定位的非成员 → 404 `NOT_FOUND`，不回任务快照；角色不符 → 403 `ROLE_FORBIDDEN`；学生访问从未发布的课程 → 404 `GRAPH_NOT_PUBLISHED`。不新增错误码。
  6. **访问矩阵**：教学资料、任务、图谱编辑、审核、发布与版本、成员管理仅教师成员；进度、推荐、问答仅学生成员，**教师成员不开放**；图谱与知识点读取两者皆可，学生只读已发布版本。学生的课程列表只含曾经发布过的课程，每项带 `my_role`。
  7. **SSE 票据**：`POST /api/v1/tasks/{tid}/event-ticket` 用 Bearer 申领，返回 ≥128 位随机票据，60 秒有效，库中只存哈希；`GET .../events?ticket=` 覆盖全局 Bearer，用一条条件更新原子核销，核销后重新校验账号与成员关系再开流。常规访问令牌永不进 URL。
- **后果**：
  - **契约**（真源尚未进入 main，本条不改）：B08 改 `bearerAuth` 说明、为所有 Bearer 操作补 `401`、新增 `eventTicket` 安全方案；B09 为 `Course` 加必填 `my_role`，改 `listCourses` 描述，`login` 补 `429`，新增 `listMembers`、`addMember`、`removeMember` 与 `CourseMember`、`MemberAdd`；B10 新增 `issueEventTicket` 与 `EventTicket`，让 `streamTaskEvents` 覆盖全局安全方案，并把 `events.v1.md` §1 的 `token` 改为 `ticket`。落实后 ADR-004 端点迁移表由 22 路径 / 29 操作增至 24 路径 / 33 操作，新增行随 A10 导入时补登，本条不改 ADR-004 正文。
  - **数据**：`users` 在 S2 字段外增加 `created_at`、`disabled_at`；`course_members` 增加 `added_by`、`created_at`；新增表 `event_tickets`。前两张表已在 ADR-008 命名基线内，`event_tickets` 须补登到 `docs/architecture.md` 命名基线（该文件现由 A04 持锁，交 A10 导入时一并处理）。
  - **配置**：`AUTH_JWT_SECRET`（必需，≥32 字节，缺失拒绝启动）、`AUTH_ACCESS_TOKEN_TTL_SECONDS`、`SEED_DEMO_PASSWORD`，写入 `.env.example` 与 `docs/integrations.md` 由 A07 或 C03 完成。
  - **原子清单缺口**：登录端点与令牌签发、账号命令行与演示账号种子、成员管理 API、成员管理页面、票据申领端点，清单中均无承接任务（ADR-004 只把 `/auth/login` 交给 C03，而 C03 的文件范围只有依赖注入与访问服务）。须由协调 Agent 拆分编号后再认领。
  - **依赖方验收因此变具体**：C02（学生账号不能做教师成员）、C03（伪造 `user_id`、非成员、学生编辑均拒绝，见 IAM-14～16）、C04（创建者成员同事务）、C11（票据核销与 TASK-19）、I02（拒绝冒用他人 `user_id`）、B03（前端路由不当作后端鉴权）、K06（跨课程拒绝）。
  - **D-03 关闭**：本条已签收，`docs/tasks.md` 中 D-03 与 `ff30e0` 的 M0-07 中「本地演示角色登录」一项随之关闭；M0-07 的「LLM 供应商与主备」一项仍属 D-02，不受影响。该分支说的「回写 ADR-005」在 ADR-004 编号裁定后已不适用（ADR-005 现为「任务处理状态机」），登录决定改记于本条。
- **已知限制**（接受，写入规格）：
  1. 令牌被盗后在到期前（≤8 小时）一直有效，缓解手段是命令行停用账号。
  2. 登录限流计数在 API 进程内存，多进程部署时各自计数，只是缓解手段。
  3. SSE 流开启后不再复查成员关系；教师在连接期间被移出课程，已开的流持续到 `awaiting_review` 关流为止。
- **推翻条件**：
  1. 需要对外部署给真实师生使用，或需要接入学校统一身份认证时，本条整体重开（届时需要生产级 SSO，超出本阶段边界）。
  2. 教师普遍需要在发布前用问答检验效果，重开决定 6 中「教师成员不开放问答」一行。
  3. 学生规模大到按用户名逐个添加不可行（例如一门课上百人），重开决定 4，考虑批量导入或选课码。
- **签收**：ArvinHan 2026-09-23
