# A01：裁决契约唯一来源与 ADR 编号

- **task_id**：A01（`docs/atomic-task-plan.md` / `docs/atomic-tasks.json`）
- **状态**：交付完成，**结论未签收**（PROPOSED）。决策人：技术负责人（PLAN-D01）
- **review_status**：ready_for_review
- **worktree**：`/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/adoring-sinoussi-709263`
- **分支 / base**：`claude/adoring-sinoussi-709263` / base `05d214c`（main）
- **交付提交**：`88ea517`（`docs(A01): 裁定契约唯一真源与 ADR 编号（结论待签收）`，4 文件 / 232 行新增）
- **head**：本文件的 head 字段修正另起一个提交，因此 review 的固定基线取 `88ea517`；其后若只有本文件的修正提交，视为同一次交付，未推送
- **类型**：仅文档任务，无代码、无依赖变更、无合并、无网络调用

## 一、范围与交付物

| 文件 | 改动 |
| --- | --- |
| `docs/decisions.md` | 追加 **ADR-004：契约唯一真源与 ADR 编号裁定（待签收）** |
| `docs/architecture.md` | 在「源码映射」与「核心数据模型」之间插入「契约真源与生成物（ADR-004，待签收）」 |
| `docs/tasks.md` | 追加「原子任务认领」小节，写入 A01 的 ID / 负责人 / worktree / base HEAD / 文件锁 |
| `docs/handoffs/claude-a01.md` | 本文件 |

未触碰任何 `src/`、`scripts/`、`specs/` 文件，未改 `docs/atomic-tasks.json`（其 JSON 白名单更新属 A10 导入批次）。

## 二、裁定内容（一句话）

**`src/contracts/api.v1.yaml`（OpenAPI 3.1）为唯一人工编辑真源；Pydantic 与 TypeScript 都是 `v1/generated/` 下的生成物，禁止手改；后端与前端都是只读消费方。** 理由、否决方案与推翻条件见 ADR-004。

## 三、本轮最重要的发现（下一位 Agent 必读）

`docs/atomic-task-plan.md` 写于 2026-09-22 08:33，而 `claude/worktree-contract-conflicts-740adb`（`1bc63ad`，09:22）**已经合并两个契约分支并自行裁定了同一件事**。也就是说：

- A01 的输入「两个分支契约决定」其实是**三份**成果：`bef9b91`（Pydantic-first，0 行契约）、`6ccbe5e`（YAML，1690 行）、`1bc63ad`（合并 + 修复，1835 行，已含生成脚本与生成物）。
- 清单使用 `src/contracts/v1/python/*.py` 作候选定位，是按 Pydantic-first 写的；本条签收后该定位**全部失效**，映射表见 ADR-004「清单路径映射」。
- `740adb` 在 `docs/reviews/claude-review-state.json` 中的状态仍是 `COMPLETION_CANDIDATE_WAIT_STABILITY`（只观察到一次稳定 HEAD，审查未完成），因此本条是「核对后提交签收」，不是把它当既成事实照抄。

## 四、验收对照（A01 验收矩阵）

| 验收条款 | 落点 | 结果 |
| --- | --- | --- |
| 明确真源 | ADR-004 决定第 1 条；`architecture.md` 新节第 1 行 | 满足 |
| 明确生成物 | ADR-004 决定第 2 条（4 类产物、禁改、字节一致） | 满足 |
| 明确写入方 | ADR-004 决定第 3 条（真源=后端 Agent，生成物=脚本，两端只读） | 满足 |
| 原有每个端点有迁移去向 | ADR-004「原有端点的迁移去向」表，22 路径 / 29 操作逐条列出 | 满足 |
| 不擅自删功能 | 加分项端点 `/kp/{kid}/material` 明确「不实现但不从真源删除」；无任何端点被移除 | 满足 |
| ADR 编号冲突有裁定 | ADR-004「ADR 编号裁定」表：撞号的数据模型命名基线改编为 ADR-008；M0-04a/b → M0-09/M0-10 | 满足 |
| 人工决策保留未签收标记 | 标题「（待签收）」+ 顶部签收状态引用块 + tasks.md 认领行注记 | 满足 |

端点与 schema 计数为实测（脚本解析 YAML）：`6ccbe5e` = 22 路径 / 29 操作 / 52 schema / 181 `$ref` / 1690 行；`1bc63ad` = 22 路径 / 29 操作 / 59 schema / 189 `$ref` / 1835 行。两版端点集合相同，差异只在 `/api/` → `/api/v1/` 前缀与 schema 细化。

## 五、实际运行的命令与结果

```text
./scripts/verify.sh        exit 0（Scaffold verification passed；改动前后各一次）
git diff --check           exit 0（改动前后各一次）
```

本仓库当前**没有** A01 的自动化验收脚本；清单给出的单项命令就是上面两条加「逐条核对验收矩阵与源文档」，后者以第四节的对照表形式给出，人工可复核。无测试新增——A01 不产生可执行代码。

## 六、接口 / 数据 / 配置变更

无运行时变更。**潜在的未来变更**（签收后才生效，本轮未执行）：

1. 清单中 B08～B14、O02、O05 的文件范围从 `src/contracts/v1/python/*.py` 改为 `api.v1.yaml` + `v1/generated/`。
2. `src/contracts/generate.py`（清单中 B14 的候选文件）**不再需要**，它属于被否决的「FastAPI 导出 openapi.json」路线。
3. 新增两个开发期依赖 `datamodel-code-generator`、`openapi-typescript`，**安装需人工授权**。

## 七、未完成 / 风险

- **签收未完成**：PLAN-D01 仍待技术负责人。未签收前不得开工 B08～B14。
- **合并未执行**：本轮未合并任何分支；集成基线与合并权是 PLAN-D04 / A10 的范围。
- **契约内容未复验**：本条只裁定「怎么表达、谁写」。`740adb` 的 R03/R04 修复（引用非空、事件判别联合）仍须 B08/B10/B13 用负例测试复验；跨课程/跨版本引用校验 schema 表达不了，必须在服务层做。
- **生成链未实测**：两个生成器本机未安装，`gen-contracts.sh` 的 Pydantic/TS 阶段在任何分支上都**没有跑通过**，只在降级模式下打印未完成标记。不要把 `740adb` 的「生成物入库」当成已验证。
- **合入注意（2026-09-22 更正）**：写这份交接时，main 的 Codex PLAN-01 改动还停在工作区未提交，原文因此写着「必须按 diff 叠加，不要整文件覆盖」。这些改动已提交为 main 的 `9ddcef8`，那条警告作废——本 worktree 基于 `05d214c`，合入时是一次正常的三方合并。需要注意的仍然是：`docs/architecture.md` 与 `docs/tasks.md` 两侧都有新增（main 侧是顶部入口段与 PLAN-01／「待确认决策」节，本侧是契约真源节与原子任务认领节），位置不重叠但同文件，合并时逐段核对；`docs/decisions.md` 只有本侧改动，可直接带入。

## 八、下一位 Agent 的首个动作

1. **技术负责人**：在 `docs/decisions.md` ADR-004 末尾签收或驳回。驳回请直接写在「推翻条件」下方，说明命中哪一条。
2. 签收后，下一个可执行叶子任务是 **A02**（统一路径前缀和领域枚举，依赖 A01）；A02 若推翻 `/api/v1` 前缀，必须同步改 ADR-004 的端点表。
3. 不依赖本条的任务（B01 前端骨架、B05 后端 health、F05 纯 DAG、D02～D07 解析器）可并行认领，但仍须各自单独认领与文件锁。

## 九、回滚

仅四个文档文件，无持久层与依赖变更。回滚：

```text
git -C <本 worktree> revert --no-edit 88ea517
```

若本文件的 head 修正已另有提交，先 revert 该提交再 revert `88ea517`。不要使用 reset 或清理命令——本仓库有多个并行 worktree，stash 栈也是共享的。
