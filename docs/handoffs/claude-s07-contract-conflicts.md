# S-07：合并两个 worktree 并消解契约冲突

- **task_id**：S-07
- **review_status**：ready_for_review
- **worktree**：`/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/worktree-contract-conflicts-740adb`
- **分支**：`claude/worktree-contract-conflicts-740adb`
- **base_commit**：`05d214c`（main）
- **合并进来的两支**：`bef9b91`（multi-agent-contract-format）、`6ccbe5e`（tech-plan-review-improvements）
- **输入**：`docs/reviews/codex-claude-initial-2026-09-22.md` 的 R01 ～ R05
- **提交**：`2fbf325`（合并与解冲突）+ 本轮修复提交

## 一、协调人裁定（R01 的前置）

R01 需要协调人二选一，已确认：**`src/contracts/api.v1.yaml` 为唯一真源，Pydantic 与
TypeScript 由它生成**。修复交付形态：在本 worktree 合并两支后统一修复，产出一条可进 main
的集成分支。

ADR-004 据此改写，**保留首版的三方案对比表与否决理由**，并写明推翻首版的四条依据。要点：
首版否决 YAML 的唯一理由是「后端仍需手写 Pydantic，于是有两份产物」——这个前提可以直接消掉，
Pydantic 不手写而是生成，套用首版对前端生成物的同一条规则（入库、禁改、`--check` 兜底）。

## 二、逐项修复与验证

| 项 | 修复 | 实测验证 |
| --- | --- | --- |
| **R01** P1 唯一真源 | ADR-004 改写为 YAML 真源；撞号的「数据模型命名统一」改编为 **ADR-008**（按 `decisions/README.md` 第 4 条「后合并的一方改号」）；`docs/decisions.md` 单文件形式废除；22 条路径统一加 `/api/v1` 前缀；新增 `scripts/gen-contracts.sh` 与 `src/contracts/toolchain.txt` | 生成两次字节一致（SHA256 相同）；人为在生成物尾部加一个换行后 `--check` exit 1；恢复后 exit 0 |
| **R02** P1 缺依赖静默放行 | `check_contracts.py` 缺依赖时**失败**，仅 `--allow-scaffold` 可降级并打印 `INCOMPLETE` 未完成验收标记；`gen-contracts.sh` 同样约定 | 复现：`PATH=/usr/bin:/bin ./scripts/verify.sh` 原先打印 SKIP 后 exit 0。修复后同一条件 exit 1 |
| **R03** P1 来源只是描述 | `ChatResponse` 拆成 `ChatAnswered`（`citations.minItems: 1`）与 `ChatNotCovered`（`maxItems: 0` + 必填机读 `reason`），`oneOf` + `discriminator: status`；`SourceRef`/`Citation` 用 `anyOf` 要求 `page ≥ 1` 或非空 `section_path` 至少一个，去掉 `null` | 报告原文两个负例被 jsonschema 拒绝；带页码、只带章节两种真实引用通过 |
| **R04** P2 事件容许空载荷 | `ChatEvent` 拆成 `ChatMetaEvent`/`ChatDeltaEvent`/`ChatDoneEvent`/`ChatErrorEvent`，`oneOf` + `discriminator: event`，每个 `required` 非空；`done` 携带 `final`（完整 `ChatResponse`）作为权威正文；`events.v1.md` §3 重写，新增「最终正文的替换协议」 | `{}` 被拒；文档旧例（done 带裸 `answer`）被拒；引用全失效降级为 `not_covered` + `all_citations_invalidated` 的例子通过 |
| **R05** P2 状态机不一致 | 合并本身已让规格补齐 `persisting`/`cancelled`；另在 `events.v1.md` §2 新增**规范转换表**（含触发者、终态集合、`queued` 取消由谁执行、`cancel_requested` 标志位、取消与完成竞争）；`TaskEvent` 增加 `cancel_requested` | 门禁逐文件检查 9 个状态名同时出现在契约、时序文档、架构与规格；删掉任一即 exit 1 |

## 三、门禁自身的测试

`tests/contracts/test_contracts.py`，20 条，不需要 pytest 即可运行。第一条是
**测试的测试**——先证明未被破坏的临时工作区是绿的，否则所有「必须失败」的用例都会假阳性通过。
缺依赖用 `tests/contracts/_shim/sitecustomize.py` 屏蔽 import 模拟，不动本机环境。

## 四、实际运行的命令与结果

```text
./scripts/verify.sh                                   exit 0（structure PASS / backend SKIP /
                                                      frontend SKIP / contracts PASS）
python3 scripts/check_contracts.py                    exit 0
PATH=/usr/bin:/bin python3 scripts/check_contracts.py exit 1（缺 PyYAML，修复前是 exit 0）
./scripts/gen-contracts.sh --allow-scaffold           exit 0，产出 4 个文件
./scripts/gen-contracts.sh --check                    exit 1（缺 datamodel-codegen，未降级）
./scripts/gen-contracts.sh --check --allow-scaffold   exit 0
python3 tests/contracts/test_contracts.py             20/20 通过，exit 0
```

契约规模：OpenAPI 3.1.0，22 条路径 / 59 个 schema / 189 处 $ref，openapi-spec-validator 0.9.0 通过。

## 五、接口与数据变更（破坏性）

契约尚未被任何实现消费，因此这些变更的迁移成本为零，未升 v2：

1. **全部 REST 路径加 `/api/v1` 前缀**。
2. **`ChatResponse` 由单一对象改为 `oneOf` 两分支**，`not_covered` 新增必填 `reason`。
3. **`ChatEvent` 由宽松对象改为 `oneOf` 四分支**，`done` 的载荷结构完全改变（`final` 包住最终响应）。
4. **`SourceRef`/`Citation` 的 `page`/`section_path` 不再接受 `null`**，且两者必须至少有一个。
5. `TaskEvent` 新增可选 `cancel_requested`（非破坏）。

## 六、未验证 / 未完成

- **Pydantic 与 TypeScript 生成未实测**：`datamodel-code-generator` 与 `openapi-typescript`
  本机未安装，两个阶段在 `--allow-scaffold` 下被跳过并打印 `INCOMPLETE`。版本已锁在
  `src/contracts/toolchain.txt`。**安装需要人工授权**，是 M0-09 的第一步。
  装好后要删掉 `scripts/verify/contracts.sh` 里的 `--allow-scaffold`，让缺工具直接红掉。
- **服务层校验未实现**：schema 只是第一道防线。「引用确属同一课程、同一发布版本」schema
  表达不了，必须在服务层做（M2-08）。R03 的这一条验收尚未满足。
- **codex 首轮未覆盖的范围仍未覆盖**：`docker-compose.yml`、`scripts/dev-*.sh`、
  `.claude/hooks/block-dangerous.sh` 的完整审查，见 `docs/reviews/claude-review-state.json`
  的 `pending_paths`。本轮没有动这些文件。
- **M0-06 只完成一部分**：`specs/course-knowledge-graph.md` 的状态机与「待细化」已同步，
  其余三份规格只改了失效的 ADR 引用，未逐条比对。

## 七、合并带来的编号变更（下一个 Agent 必读）

| 原编号 | 现编号 | 原因 |
| --- | --- | --- |
| tech-plan 的 ADR-004（数据模型命名统一） | **ADR-008** | 与 multi-agent 的 ADR-004 撞号 |
| multi-agent 的 M0-04a（起草契约真源 + 生成链） | **M0-09** | 与 tech-plan 的 M0-04a（REST DTO）撞号 |
| multi-agent 的 M0-04b（前端消费生成类型） | **M0-10** | 同上 |
| 原 M1-05（教师审核与发布） | **M2-02 ～ M2-04** | 按 S2 阶段划分归入 M2 |
| 原 M1-07（学习材料生成） | **M2-11** | 依赖 M2-06 的学习路径推荐 |

`docs/handoffs/` 里更早的记录保留原编号，不回改——它们是当时的真实记录。

## 八、下一位 Agent 的首个动作

**Backend Agent，M0-09**：按 `src/contracts/toolchain.txt` 安装两个生成器（需人工授权），
跑 `./scripts/gen-contracts.sh`，把 `python/` 与 `typescript/` 产物入库，然后删掉
`scripts/verify/contracts.sh` 第 2 步的 `--allow-scaffold`。

## 九、回滚

本轮是一次合并 + 一次修复提交，未删除任何他人文件（`docs/decisions.md` 与 `evals/README.md`
的内容分别迁入 `docs/decisions/ADR-008-*.md` 与 `evaluation/README.md`，无丢失）。
回滚用 `git revert` 这两个提交即可；两个源分支 `bef9b91`、`6ccbe5e` 未被改动，仍可独立检出。
不要用重置或清理命令——本仓库有多个并行 worktree。
