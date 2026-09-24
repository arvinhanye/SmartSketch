# A04：定义图谱版本和跨库发布协议

- **task_id**：A04（`docs/atomic-task-plan.md` / `docs/atomic-tasks.json`）
- **状态**：DONE。决定已由 ArvinHan 于 2026-09-23 在会话中逐项确认并签收，记为 **ADR-012**；PLAN-D02 关闭
- **review_status**：ready_for_review
- **worktree**：`/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/a04-f5f479`
- **分支 / base**：`claude/a04-f5f479` / base `931361d`（= 开工时的 `origin/main`）
- **head_commit**：交付提交 `110f243`（PR #7）；随后合入 A06 分支 `ab04053`（含 A03）并解决冲突，见第九节。交付提交时的内容指纹：`git diff 931361d 110f243 -- docs/architecture.md docs/decisions.md docs/tasks.md specs/teacher-review-publish.md | shasum -a 256` 前 16 位 `791dfb30d6658cfa`
- **类型**：仅文档任务，无代码、无依赖变更、无合并、无网络调用（`git fetch` 除外）

## 一、范围与交付物

| 文件 | 改动 |
| --- | --- |
| `specs/teacher-review-publish.md` | main 新建。以 `740adb` `978671e` 的同名草稿桩为底稿（与 `209be9` 同文），保留原章节与主验收 1～18；新增「图谱版本与跨库发布协议（A04 / ADR-012）」V1～V11，含验收 PUB-1～27（成功 4 / 边界 13 / 失败 10）；主验收 7、8、9、12、16、17 改为指向 PUB 用例；「待细化」划掉快照形态与回滚编号两项 |
| `docs/architecture.md` | 新增「图谱版本与跨库发布（A04 / ADR-012）」结论表；核心数据模型补版本作用域；数据流第 3、4 步补发布提交点与请求绑定 |
| `docs/decisions.md` | **范围扩展**：新增 ADR-012（已签收）；ADR-004 端点表下加一行指针，其余正文未改 |
| `docs/tasks.md` | A04 认领行、PLAN-D02 改为已关闭、A04 决定与后续项两条 |
| `docs/handoffs/claude-a04.md` | 本文件 |

**范围扩展说明**：清单给 A04 的文件锁只有规格与架构两份。AGENTS.md §6 要求已确认选择写入 ADR，因此新增 ADR-012，与 A02 的做法相同。编号取 012，因为 ADR-010（A03，PR #5）与 ADR-011（A06，PR #6）已在未合入 main 的分支上签收。未触碰 `src/`、`scripts/`、`.env.example`、`docs/integrations.md`、`docs/atomic-tasks.json`，也未改任何其他 worktree 或分支。

## 二、决定内容（签收人 ArvinHan，2026-09-23）

| 问题 | 决定 |
| --- | --- |
| 存储（PLAN-D02 核心） | SQLite `GraphVersion.snapshot_json` 是版本内容的真相，附 sha256 摘要；Neo4j 按 `(course_id, version_id)` 物化副本；知识点向量随版本复制，文本块不可变、各版本共享 |
| 标识 | 内部 `version_id`（ULID，永不复用）；对外整数 `version`，提交时分配 `max+1`，无空洞 |
| 回滚编号 | 前滚为新版本号；目标摘要等于当前发布版则幂等，不产生新号 |
| 重复发布 | 发布集合摘要等于当前发布版则幂等，返回 `unchanged: true`；只与当前发布版比较 |
| 回滚与草稿 | 草稿不动；课程状态按草稿摘要是否等于新版本判定 |
| 并发 | 同课程至多一个发布/回滚（部分唯一索引，409 `PUBLISH_IN_PROGRESS`）；草稿写入与建快照共用 A06 课程写锁，发布只在读草稿期间持锁；API 侧有界等待，超时 409 `COURSE_BUSY` |
| 低置信度 | 排除 `low_confidence` 与因此悬空的边；疑似重复、孤立节点只提示 |

**会话中途的一次方案修正（已向用户说明并获确认）**：第 2 节最初把发布租约放在 Neo4j Course 节点上。写文档前核对到 A06（PR #6）已签收 SQLite `course_locks`，并把「发布方何时持锁」交给 A04；它是持有期间才写的互斥锁，不存在我当初担心的「先查锁再写」空隙。因此改为复用 A06 的锁，并把持有方扩大到所有草稿写入（ADR-012 决定 6 修订 ADR-011 决定 6）；同时纳入 A03 的任务水位与 T7。

**实施细化（在确认方向内由本任务定稿，已随 ADR-012 一并签收）**：
- `PUBLISH_BLOCKED` 的 `reasons[].kind` 增加 `dangling_endpoint`、`invalid_source_ref`、`empty_graph` 三种，与 `cycle` 并列（V3）。
- 回滚的 R6 等锁超时不使回滚失败，状态保守判为 `revising`，下次发布走幂等路径纠正（PUB-16）。
- Neo4j 有版本副本而 SQLite 无对应行时只告警不删除（V9 第 4 条）。
- `PUBLISH_LEASE_SECONDS` 默认值：第 4 节讨论时说的是 120 秒；改为尝试行心跳续约之后，它只决定崩溃后多久被清扫，取 60 秒，与 A06 的 `TASK_LEASE_SECONDS` 一致。

## 三、验收对照（A04 验收矩阵）

| 验收条款 | 落点 | 结果 |
| --- | --- | --- |
| 图读版本 | V2 作用域、V8 读取绑定、PUB-13/14/27 | 满足 |
| 向量读版本 | V2（知识点向量随版本、文本块共享）、V3 `materials`、V8 向量检索、PUB-17 | 满足；「多取再过滤」召回待 J01 实测，已列入 ADR-012 推翻条件 |
| 指针切换 | V5 P11 单事务 CAS、PUB-20/21 | 满足 |
| 失败补偿 | V5 C1、V9 清扫、PUB-18/19/20/26 | 满足 |
| 回滚编号 | V1、V6、PUB-3/7/12 | 满足 |
| 决策前不写仓储 | 本任务无任何代码；实现归 G01～G07、F02/F03 | 满足 |
| 人工决策保留未签收标记 | 交付时各处标「待签收」；ArvinHan 书面签收后统一改为「已签收」，签收行齐全 | 满足 |

## 四、实际运行的命令与结果

```text
./scripts/verify.sh                 改动后 exit 0（block-dangerous hook tests passed / Scaffold verification passed）
git diff --check                    exit 0（只覆盖已跟踪文件）
git add <四个文件> && git diff --cached --check
                                    exit 0（覆盖新建的规格文件）
python3 check_a04.py <spec> <740adb 978671e api.v1.yaml> <A03 6345ce1 task-processing.md>
        <A06 ab04053 task-processing.md> <全部远端分支 ADR 文本> docs/architecture.md docs/decisions.md
                                    正例 exit 0，ALL PASS（41 项）
  负例 1：把 PUB-14 改名              exit 1：PUB 编号不连续
  负例 2：把 COURSE_BUSY 换成 LOCK_TIMEOUT
                                    exit 1：出现真源与声明集合外的错误码
  负例 3：删掉「### V6」标题           exit 1：V1～V11 不齐
```

源文件经 `git show` 导出到会话 scratch 目录，未改动任何 worktree。核对脚本第一版把两个环境变量名误判为错误码（1 FAIL），已在脚本中声明配置变量集合后重跑，上面是修正后的结果；另有一次在 zsh 下 `$ARGS` 未分词导致脚本没收到参数，改用 bash 数组重跑，那次 exit 1 不计。脚本全文见附录。

## 五、接口 / 数据 / 配置变更

无运行时变更，无契约文件改动（main 尚无 `api.v1.yaml`）。受本决定约束的未来变更：

1. **B08**：`ErrorCode` 新增 `PUBLISH_IN_PROGRESS`、`COURSE_BUSY`（核对确认真源中尚无）。
2. **B11**：`PublishResult` 加 `unchanged`、`excluded`；`GraphVersion` 加 `kind`、`source_version`（核对确认尚无）；回滚端点补 409（核对确认尚无）；定义 `PUBLISH_BLOCKED` 的 `details.reasons` 结构；快照字段清单与 DTO 对齐。
3. **A07**：`PUBLISH_LEASE_SECONDS`（≥15，默认 60）、`COURSE_LOCK_WAIT_SECONDS`（≥0，默认 5），登记到 `.env.example` 与 `docs/integrations.md`。
4. **G02**：版本行状态改为 `preparing/materialized/committed/failed`（清单原写 `preparing/ready`）。
5. **A10**：统一文本块标签 `SourceChunk` / `Chunk`；本规格替换 `740adb`/`209be9` 的草稿桩。（原列的 §8.5 加注已在第九节完成。）

## 六、未完成 / 风险

- **修订已签收的 ADR-011**：课程写锁持有方扩大到教师编辑。A06 的 LEASE-10 只测了发布与 `persisting` 之间的互斥，教师编辑持锁的用例在本规格 PUB-22；A06 规格本身不在本任务文件锁内，未改。
- **向量召回**：Neo4j 向量索引不能先过滤，「多取再过滤」在版本多、课程多时召回可能下降，由 J01 实测；达不到时回到 ADR-012。
- **存储增长**：MVP 不回收已提交版本，Neo4j 副本随版本数线性增长；回收须另立 ADR。
- **与 A03/A06 的合并**：本分支已合入 A06 分支 `ab04053`（含 A03 `6345ce1`），见第九节。若 PR #5、#6 在合入 main 前再被修改，或以 squash 方式合入，本 PR 需要重新同步 main 并复核 V4、V5、V10。
- **未验证**：协议只有规格与验收用例，没有实现或自动化测试（属 G01～G07、F02/F03、J01）。

## 七、下一位 Agent 的首个动作

1. 请 Codex 按本交付提交审查五个文件；修复另开一轮。
2. B08/B11 认领时先处理第五节第 1、2 条的契约缺口，G01 依赖 B11。
3. A10 导入批次按第五节第 5 条处理注记与桩替换。

## 八、回滚

仅文档改动，无持久层与依赖变更。提交后首选 `git revert <A04 交付提交>`。提交前如需手工恢复，只还原本任务触碰的文件并删除两个新文件：

```text
git -C <本 worktree> restore --staged --worktree --source 931361d -- docs/architecture.md docs/decisions.md docs/tasks.md
rm <本 worktree>/specs/teacher-review-publish.md <本 worktree>/docs/handoffs/claude-a04.md
```

不要使用 reset 或 stash 清理；stash 栈与其他 worktree 共享。

## 九、签收后：合入 A03/A06 分支并解决冲突

用户签收后要求提交、开 PR，并把未合并的 PR 一并合并。

- 已提交 `110f243` 并开 PR #7（base `main`）。
- 当时 open 的 PR：#5（A03，base `main`）、#6（A06，base 为 A03 分支的叠放 PR），两者 CI 均 pass、`MERGEABLE`/`CLEAN`；A03 第二轮修复与 A06 均尚待 Codex 复核（`review_status: ready_for_review`）。
- **合并 #5/#6 未执行**：`gh pr merge` 被 Claude Code auto mode 的权限分类器以「未经审查合并」拒绝，未尝试绕过，交由用户决定。
- 用 `git merge-tree` 预演：main ← #5 ← #6 均无冲突；再合 #7 在 `docs/architecture.md`、`docs/decisions.md`、`docs/tasks.md` 冲突（双方在同一位置追加）。
- 因此在本分支 `git merge --no-ff origin/claude/a06-worker-lease` 并解决冲突：ADR 按 010、011、012 排列；PLAN-D02 取本任务版本、PLAN-D03 取 A03/A06 版本；认领行按 A03、A06、A04 排列；架构文档数据模型取 A06 的 SQLite 清单并补本任务的 `GraphVersion`/`Course` 说明。#5、#6 以普通 merge commit 合入 main 后，#7 可无冲突合并。
- **范围扩展（两行注记）**：A06 规格改为直接进入 main、不再经 A10 导入，因此在 `specs/task-processing.md` §8.5「只有两处持锁」下与 `docs/decisions.md` ADR-011 引言各加一行指向 ADR-012 的修订注记，正文未改；ADR-012「后果」与规格 V10 同步改写。

## 十、第二轮：Codex 审查修复（A04-R01 / A04-R02）

- **task_id**：A04-R01/R02 修复
- **状态**：DONE。修复方案由 ArvinHan 于 2026-09-23 在会话中逐项选择并签收，记为 **ADR-012 修订 1**（决定 9～12）
- **review_status**：ready_for_review
- **worktree / 分支**：同上 worktree，分支 `claude/a04-r01-r02-fix`，base `0630664`（= 合入 #5～#9 后的 `origin/main`）
- **审查报告**：主目录 `docs/reviews/codex-claude-a04-4b2ccb5-2026-09-23-0730z.md`（目标提交 `110f243` / `4b2ccb5`，尚未入库）

**核对结论**：两条均成立，根因比报告更深。R01：A06 的块 ID 不含内容，同一资料换内容再处理会原地覆盖已发布版本引用的原文；失败任务按 A06 §8.6 删除来源块，也可能删掉处理同一内容的已发布块。R02：查询向量总按当前模型计算，换模型后所有旧空间向量（含当前发布版）都无法检索。

| 编号 | 选择（用户签收） | 落点 |
| --- | --- | --- |
| R01 | 按资料修订固定：块 ID = `revision_id` + 块序号，文本块不可变；快照 `revisions` 取代 `materials`；检索按 `revision_id` 过滤；失败任务来源块加删除保护（否决：快照直接列全部 `chunk_id`） | 规格 V2、V3、V8、V10，PUB-17、24、28～31；A06 §8.4 `parsing` 行与 §8.6；ADR-011 引言加注 |
| R02 | 离线全量重新向量化 + 启动门禁：运行时只有一个空间，向量是派生数据，重算不产生新版本（否决：只迁移当前版；运行时按需补算） | 规格 V2、V5、V6、V8、新增 V12，PUB-32～34；A07 `docs/integrations.md` 两处 |

**范围扩展**：`specs/task-processing.md` 的两行（A06 条文）与 `docs/integrations.md` 的两处（A07 条文），各带修订注记；原因是修复必须改动块 ID 公式、删除规则与「换模型」的去向说明，只改 A04 规格会留下互相矛盾的条文。

**验证**：

```text
./scripts/verify.sh                         exit 0
git add … && git diff --cached --check      exit 0
python3 check_a04.py（第二版，见附录）       正例 exit 0，55 项 ALL PASS
  负例 A：检索改回按 material_id 过滤         exit 1
  负例 B：P9 改回「等于当前配置」             exit 1
  负例 C：删掉 PUB-33                        exit 1
```

脚本第二版首跑出现 4 项 FAIL，均为脚本自身问题并已修正：把 `EMBEDDING_*` 配置变量当成错误码；`### ADR-012 修订 1` 标题使 `## ADR-012` 子串计数为 2；架构签收行措辞已改；`task-processing.md` 状态表另有一行以 `` `parsing` `` 开头。规格本身未因此改动。第二版的 A03/A06 输入改用本分支 `specs/task-processing.md`（已含 A03/A06 正文）。

**遗留**：
- 「下线旧资料修订」未定义（规格「待细化」，交 C06/C07）：资料换内容后新旧原文都可检索。
- 「重新向量化命令」在原子清单中没有对应叶子任务，交 A10 补登。
- Codex 的 A06-R01/R02（图元素清理与 `cleanup_pending` 可见性）不在本轮范围，仍未修；A04 发布读取草稿的风险随之仍在。
- 协议仍只有规格与验收用例，没有实现或自动化测试。

**下一步**：请 Codex 按本轮提交复核 A04-R01/R02；修复另开一轮。

## 十一、第三轮：Codex 复审修复（FIX-R02）

- **task_id**：FIX-R02 修复（Codex REVIEW-09）
- **状态**：DONE。方向由 ArvinHan 于 2026-09-23 在会话中选定（按实际存量全部重算），记为 **ADR-012 修订 2**（决定 13、14）；书面条文（含下列推导细则）由 ArvinHan 于 2026-09-23 签收
- **review_status**：ready_for_review（以交付提交为准，提交前不生效）
- **worktree / 分支**：`.claude/worktrees/quirky-dijkstra-eca5de`，分支 `claude/fix-r01-r02`，base `1a47eb2`（= 合入 PR #12 后的 `origin/main`）
- **head_commit / 指纹**：与 FIX-R01 同一交付提交，见 `docs/handoffs/claude-a07.md` 第十节
- **审查报告**：主目录 `docs/reviews/codex-claude-a04-fixes-1012b6f-2026-09-23-1215z.md`（目标提交 `02bc228`，尚未入库）

**核对结论**：成立。V12 第 3 步按「已到审核或完成的任务」推导目标，但失败任务的块在回收前保留，中断任务的块在接管时复用，它们只有旧空间向量。启动门禁只比对 SQLite 记录的空间，发现不了。另有两处报告未提及、本轮一并修复：

1. E07 按文本哈希缓存向量（修订 1 的实现依赖），键中没有空间，切换后同一段文字会命中旧空间的缓存。
2. F 组写入前只比对索引维度，两个模型维度相同时，旧空间的向量能通过核对。

| 选择（用户签收） | 否决 | 落点 |
| --- | --- | --- |
| 目标按 Neo4j 实际存量枚举（全部文本块、全部草稿知识点、全部已提交版本副本），第 4 步按存量核对；缓存键与节点外的向量带空间标识，写入按空间标识拒绝 | 先排空任务队列、目标仍按任务状态推导：运维上要等待或取消全部任务，推导集合与存量仍可能不一致，缓存问题照样要修 | `specs/teacher-review-publish.md` V12 的引言、不变式、第 3/4/6 步与新增「空间标识随向量走」，V10 一行，PUB-36～38；`docs/integrations.md`「模型版本与向量空间」一处；`docs/architecture.md` 向量空间一行；`docs/decisions.md` ADR-012 修订 2 与三处指针 |

**范围扩展**：`docs/integrations.md`（A07 条文）与 `docs/architecture.md` 各一处，原因同上一轮：只改 A04 规格会留下互相矛盾的写入核对与架构结论。

**由方向推导、未单独询问的细则**（已随书面条文签收）：

1. 草稿知识点按存量迁移时**不论可见性**，包括 T6 前崩溃留下的和失败后尚未回收的节点。
2. 第 4 步除了「缺新空间向量数为 0」，还要求复查时的存量总数与第 3 步开始时一致（停机期间不应有写入）。
3. 第 6 步清理旧空间时一并清除旧空间的缓存条目；即使清理失败，残留条目也因空间标识不符而不会被使用。
4. F 组写入向量必须附空间标识，与当前空间不符即拒绝，不再只核对维度。

**验证**：与 FIX-R01 同批运行，命令与结果见 `docs/handoffs/claude-a07.md` 第十节。本项相关的断言：V12 不变式与第 3/4/6 步、「空间标识随向量走」、PUB-36～38 编号连续（1～38）、V10、integrations 写入核对、architecture 一行、ADR-012 修订 2 与三处指针；负例 N3（第 3 步改回按任务推导）、N4（删 PUB-36）、N5（写入改回只比维度）均 exit 1。

**遗留**：
- 「重新向量化命令」在原子清单中仍没有叶子任务，交 A10 补登（修订 1 已记）。
- 缓存与中间产物的具体存放位置尚未定义（E07、E 组），本轮只规定「带空间标识、不符即重算」。
- 仍只有规格与验收用例，没有实现或自动化测试。

**下一步**：请 Codex 按交付提交复核 FIX-R02；修复另开一轮。

## 十二、第四轮：Codex 复核修复（FIX-R03）与 PR #16 解冲突

- **task_id**：FIX-R03 修复（Codex REVIEW-10），A1～A10 收尾的一部分
- **状态**：DONE；ADR-012 修订 2 补注（决定 14a）已由 ArvinHan 2026-09-24 签收。补注只澄清决定 14 的适用范围，不改变已签收的方向
- **review_status**：ready_for_review（以交付提交为准）
- **worktree / 分支**：`.claude/worktrees/wrap-fix-pr16`，分支 `claude/fix-r01-r02`；base `5186e09`，先合入 `origin/main@f9dfc8f`（提交 `77310d2`），再做本轮修改
- **审查报告**：主目录 `docs/reviews/codex-claude-fix-r01-r02-5186e09-2026-09-23-1252z.md`（尚未入库）

**解冲突**：PR #16 与 main 只在 `docs/tasks.md` 文末冲突（main 追加了 A08 一节）。保留两边：main 的 A08 一节在前，FIX-R01/R02 一节在后并补回表头。`docs/decisions.md` 自动合并，ADR 顺序为 011 修订 1～3 → 012 修订 1、2 → 013 → 014。

**核对结论**：FIX-R03 成立。V12 第 3 步要在当前空间仍为 M1 时写入 M2 向量，第 5 步才切换，而决定 14 要求所有 F 组写入的空间标识等于当前空间。

| 修改 | 落点 |
| --- | --- |
| 空间标识按写入上下文核对：运行时写入只接受当前空间，无绕过参数；迁移写入只存在于重新向量化命令进程内，固定目标空间，只写目标空间的属性与索引，不动旧空间，第 5 步提交或命令退出后失效 | `specs/teacher-review-publish.md` V12 第 3 步、「空间标识随向量走」下两条子项 |
| 回归用例 | PUB-39：迁移上下文写 M2 成功且 M1 不变；同时运行时写 M2 被拒；迁移上下文写 M1 向量到 M2 属性被拒；第 5 步后旧上下文写入被拒 |
| 同步 | `docs/integrations.md` 写入核对注明唯一例外；`docs/architecture.md` 向量空间一行；`docs/decisions.md` ADR-012 修订 2 补注 |

**验证**（均在本 worktree 运行）：

```text
python3 check_fixr03.py .（修改前）        13 FAIL / exit 1
python3 check_fixr03.py .（修改后）        ALL PASS / exit 0
python3 neg_fixr03.py . <scratch>         6 个篡改副本全部 exit 1，各自命中目标断言
python3 check_fix.py .（本文件所在分支 claude-a07.md 附录 D）   ALL PASS / exit 0（加入 PUB-39 未破坏 FIX-R01/R02 的断言）
./scripts/verify.sh                        exit 0
git diff --check                           exit 0
```

两个脚本在会话草稿区，未入库；断言覆盖第 3 步措辞、两种写入的规则、PUB-39 四种情形与位置、integrations / architecture / ADR / 任务板四处同步。仍只有规格与验收用例，没有实现或自动化测试。

**遗留**：F03 实现两种写入上下文与 PUB-39；重新向量化命令（A10 批 0 补登）持有迁移上下文。

**签收**：ArvinHan 2026-09-24 在会话中签收补注，本节、ADR 与任务行已同步。

**下一步**：请 Codex 按交付提交复核 FIX-R03。

## 附录：`check_a04.py`（核对脚本全文，第二版）

用法与第一版相同：`python3 check_a04.py <spec> <api.v1.yaml> <A03 task-processing.md> <A06 task-processing.md> <全部 ADR 文本> <architecture.md> <decisions.md>`；第二版另读工作目录下的 `specs/task-processing.md` 与 `docs/integrations.md`，需在仓库根目录运行。

```python
import re, sys, yaml
spec_path, yaml_path, a03, a06, adrs, arch, dec = sys.argv[1:8]
spec=open(spec_path,encoding='utf-8').read()
y=yaml.safe_load(open(yaml_path,encoding='utf-8'))
sch=y['components']['schemas']; paths=y['paths']
fails=[]
def ok(c,msg):
    print(('PASS ' if c else 'FAIL ')+msg)
    if not c: fails.append(msg)
# 1 契约现状
ok(set(sch['PublishResult']['properties'])>={'version','published_at','stats'},'PublishResult 现有 version/published_at/stats')
ok('unchanged' not in sch['PublishResult']['properties'] and 'excluded' not in sch['PublishResult']['properties'],'PublishResult 尚无 unchanged/excluded（交 B11 属实）')
ok('kind' not in sch['GraphVersion']['properties'] and 'source_version' not in sch['GraphVersion']['properties'],'GraphVersion 尚无 kind/source_version（交 B11 属实）')
ok('published_version' in sch['Course']['properties'],'Course.published_version 存在')
ok('graph_version' in sch['GraphExchange']['properties'],'GraphExchange.graph_version 存在')
ok(sch['CourseStatus']['enum']==['draft','published','revising'],'CourseStatus 三值与 V7 一致')
ok('low_confidence' in sch['KnowledgePointStatus']['enum'],'KnowledgePointStatus 含 low_confidence')
codes=set(sch['ErrorCode']['enum'])
new={'PUBLISH_IN_PROGRESS','COURSE_BUSY'}
ok(not (codes & new),'新错误码尚不存在于真源（交 B08 属实）')
used=set(re.findall(r'`([A-Z][A-Z_]{3,})`',spec)) - {'PREREQUISITE','RELATED_TO','CONTAINS','EXAMPLE_OF','EVIDENCE','NULL','ULID'}
config={'PUBLISH_LEASE_SECONDS','COURSE_LOCK_WAIT_SECONDS','EMBEDDING_MODEL','EMBEDDING_DIMENSIONS'}  # A07 配置变量，非错误码
unknown=used-codes-new-config
ok(not unknown,f'规格中出现的大写错误码均在真源或声明的新增集合内 {sorted(unknown)}')
rb=paths['/api/v1/courses/{cid}/versions/{version}/rollback']['post']['responses']
ok('409' not in rb,'回滚端点尚无 409（交 B11 属实）')
for p in ['/api/v1/courses/{cid}/publish','/api/v1/courses/{cid}/versions','/api/v1/courses/{cid}/versions/{version}/rollback']:
    ok(p in paths,f'端点存在 {p}')
ok(any(pr.get('name')=='version' for pr in paths['/api/v1/courses/{cid}/graph']['get']['parameters']),'GET /graph 有 version 参数（V8 ?version=）')
for v in re.findall(r'`(draft|published|revising)`',spec): pass
# 2 A03
t3=open(a03,encoding='utf-8').read()
ok('任务水位' in t3 and 'T7' in t3,'A03 定义任务水位与 T7')
ok('版本回滚不改变任务状态' in t3,'A03：回滚不改变任务状态（R7 不执行 T7）')
ok('发布失败（含 409 `PUBLISH_BLOCKED`）不改变任何任务状态' in t3,'A03：发布失败不改任务状态')
ok('与发布指针切换同一 SQLite 事务' in t3,'A03：T7 与指针切换同事务（P11）')
# 3 A06
t6=open(a06,encoding='utf-8').read()
ok('### 8.5 课程写锁' in t6 and 'course_locks' in t6,'A06 §8.5 课程写锁存在')
ok('**只有两处持锁**' in t6 and '发布方在何时取锁、持锁多久由 A04 决定' in t6,'A06：两处持锁、发布持锁时机归 A04（ADR-012 修订对象属实）')
ok('到达 `awaiting_review` 的任务的来源块 | 永久保留' in t6,'A06 §8.6：来源块永久保留（V2 共享文本块前提）')
ok(re.search(r'`TASK_LEASE_SECONDS` \| 整数，≥ 15 \| 60',t6) is not None,'A06 租约默认 60，与 PUBLISH_LEASE_SECONDS 默认同构')
ok('周期执行' in t6 and '回收步骤' in t6,'A06 有周期回收步骤（V9 并入处）')
# 4 ADR 编号
alla=open(adrs,encoding='utf-8').read()
ok('ADR-010：任务生命周期' in alla and 'ADR-011：worker' in alla,'ADR-010/011 已被 A03/A06 占用')
ok('## ADR-012' not in alla,'远端任何分支均未使用 ADR-012')
d=open(dec,encoding='utf-8').read()
ok(len(re.findall(r'^## ADR-012',d,re.M))==1 and '**签收**：ArvinHan 2026-09-23' in d,'本分支 ADR-012 唯一且已签收')
# 5 规格结构
pub=[int(x) for x in re.findall(r'\*\*PUB-(\d+)\*\*',spec)]
ok(sorted(pub)==list(range(1,35)) and len(pub)==len(set(pub)),f'PUB 编号为 1..34 且不重复（实际 {len(pub)} 个）')
for k in ['成功路径','边界路径','失败路径']:
    ok(k in spec.split('### V11')[1].split('## 验收条件')[0],f'V11 含{k}')
ok(all(f'### V{i} ' in spec for i in range(1,13)),'V1～V12 齐全')
main_acc=[int(x) for x in re.findall(r'^(\d+)\. ',spec.split('## 验收条件')[1].split('## 待细化')[0],re.M)]
ok(main_acc==list(range(1,19)),'原桩主验收 1～18 编号保留')
ok('ADR-012 已签收' in spec.split('\n')[2],'规格状态行标记已签收')
a=open(arch,encoding='utf-8').read()
ok('## 图谱版本与跨库发布（A04 / ADR-012）' in a and '**签收状态：已签收**，ArvinHan，2026-09-23（ADR-012，含修订 1）' in a,'架构文档 A04 节存在且已签收')
ok('PREREQUISITE' in a,'架构文档仍含 PREREQUISITE（verify 依赖）')
# 6 验收覆盖 A04 条款
for term,label in [('读取绑定','图/向量读版本'),('向量检索','向量读版本'),('CAS','指针切换'),('C1 补偿','失败补偿'),('前滚','回滚编号')]:
    ok(term in spec,f'A04 验收条款「{label}」有落点：{term}')
# 7 修订 1（A04-R01/R02）
tp=open('specs/task-processing.md',encoding='utf-8').read()
integ=open('docs/integrations.md',encoding='utf-8').read()
ok('"materials"' not in spec and '"revisions"' in spec,'R01：快照以 revisions 取代 materials')
v8=spec.split('### V8 ')[1].split('### V9 ')[0]
ok('`revision_id` 属于该版本修订列表' in v8 and '不按 `material_id` 过滤' in v8,'R01：检索按 revision_id 过滤且明确不按 material_id')
ok('其 `revision_id` 不在第 1 条的修订集合内' in spec,'R01：invalid_source_ref 按修订判定')
row=[l for l in tp.splitlines() if l.startswith('| `parsing` |') and '来源块 ID' in l]
ok(len(row)==1 and '资料修订 ID + 块序号' in row[0] and '文档 ID + 解析器版本 + 块序号' not in row[0],'R01：A06 §8.4 parsing 行已改为按资料修订生成块 ID')
drow=[l for l in tp.splitlines() if l.startswith('| `failed` / `cancelled` 任务的来源块')]
ok(len(drow)==1 and '则保留' in drow[0],'R01：A06 §8.6 删除保护已写入')
ok('PUB-28' in spec and '换内容再处理' in spec and 'PUB-31' in spec,'R01：再处理与删除保护回归用例存在')
ok('### V12 向量空间切换' in spec and '拒绝启动' in spec.split('### V12 ')[1],'R02：V12 存在且含启动门禁')
p9=[l for l in spec.splitlines() if l.startswith('| P9 |')][0]
ok('当前配置' not in p9 and '当前向量空间' in p9,'R02：P9 按当前向量空间核对')
ok('k 自身记录的** `embedding_space`' in spec,'R02：R5 核对源版本自身空间')
ok('且当前发布版的 `embedding_space` 等于当前向量空间' in spec,'R02：幂等路径要求空间相同')
ok('`embedding_model`、`embedding_dim`' not in spec and '| `embedding_space` |' in spec,'R02：版本行以 embedding_space 取代模型与维度两字段')
ok('生成新向量版本（A04）' not in integ and '生成新的向量版本（A04）' not in integ and integ.count('V12')>=2,'R02：A07 两处已指向 V12')
ok('PUB-32' in spec and 'PUB-33' in spec and 'PUB-34' in spec,'R02：换模型回归用例存在')
ok('### ADR-012 修订 1' in d and d.split('### ADR-012 修订 1')[1].split('## ADR-013')[0].count('**签收**：ArvinHan 2026-09-23')==1,'ADR-012 修订 1 存在且已签收')
print('\nRESULT:', 'ALL PASS' if not fails else f'{len(fails)} FAIL'); sys.exit(1 if fails else 0)
```
