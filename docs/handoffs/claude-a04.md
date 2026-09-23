# A04：定义图谱版本和跨库发布协议

- **task_id**：A04（`docs/atomic-task-plan.md` / `docs/atomic-tasks.json`）
- **状态**：DONE。决定已由 ArvinHan 于 2026-09-23 在会话中逐项确认并签收，记为 **ADR-012**；PLAN-D02 关闭
- **review_status**：ready_for_review
- **worktree**：`/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/a04-f5f479`
- **分支 / base**：`claude/a04-f5f479` / base `931361d`（= 开工时的 `origin/main`）
- **head_commit**：尚未提交（改动已暂存）。内容指纹：`git diff --cached 931361d -- docs/architecture.md docs/decisions.md docs/tasks.md specs/teacher-review-publish.md | shasum -a 256` 前 16 位 `791dfb30d6658cfa`
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
5. **A10**：导入 A06 的 `specs/task-processing.md` 时在 §8.5「只有两处持锁」旁加注指向 ADR-012；统一文本块标签 `SourceChunk` / `Chunk`；本规格替换 `740adb`/`209be9` 的草稿桩。

## 六、未完成 / 风险

- **修订已签收的 ADR-011**：课程写锁持有方扩大到教师编辑。A06 的 LEASE-10 只测了发布与 `persisting` 之间的互斥，教师编辑持锁的用例在本规格 PUB-22；A06 规格本身不在本任务文件锁内，未改。
- **向量召回**：Neo4j 向量索引不能先过滤，「多取再过滤」在版本多、课程多时召回可能下降，由 J01 实测；达不到时回到 ADR-012。
- **存储增长**：MVP 不回收已提交版本，Neo4j 副本随版本数线性增长；回收须另立 ADR。
- **与 A03/A06 分支的合并**：本规格引用 A03 §3、A06 §8.5/§8.6 的条文，它们仍在 PR #5、#6 未合入 main。若二者在合入前被修改，需要复核 V4、V5、V10。
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

## 附录：`check_a04.py`（核对脚本全文）

用法：`python3 check_a04.py <spec> <api.v1.yaml> <A03 task-processing.md> <A06 task-processing.md> <全部 ADR 文本> <architecture.md> <decisions.md>`；依赖 PyYAML。源文件导出方式：`git show 978671e:src/contracts/api.v1.yaml`、`git show 6345ce1:specs/task-processing.md`、`git show ab04053:specs/task-processing.md`；ADR 文本为遍历 `git branch -r` 后拼接各分支的 `docs/decisions.md` 与 `docs/decisions/*.md`。

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
config={'PUBLISH_LEASE_SECONDS','COURSE_LOCK_WAIT_SECONDS'}  # A07 配置变量，非错误码
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
ok(d.count('## ADR-012')==1 and '**签收**：ArvinHan 2026-09-23' in d,'本分支 ADR-012 唯一且已签收')
# 5 规格结构
pub=[int(x) for x in re.findall(r'\*\*PUB-(\d+)\*\*',spec)]
ok(pub==list(range(1,len(pub)+1)) and len(pub)>=20,f'PUB 编号连续 1..{len(pub)}')
for k in ['成功路径','边界路径','失败路径']:
    ok(k in spec.split('### V11')[1].split('## 验收条件')[0],f'V11 含{k}')
ok(all(f'### V{i} ' in spec for i in range(1,12)),'V1～V11 齐全')
main_acc=[int(x) for x in re.findall(r'^(\d+)\. ',spec.split('## 验收条件')[1].split('## 待细化')[0],re.M)]
ok(main_acc==list(range(1,19)),'原桩主验收 1～18 编号保留')
ok('ADR-012 已签收' in spec.split('\n')[2],'规格状态行标记已签收')
a=open(arch,encoding='utf-8').read()
ok('## 图谱版本与跨库发布（A04 / ADR-012）' in a and '**签收状态：已签收**，ArvinHan，2026-09-23（ADR-012）' in a,'架构文档 A04 节存在且已签收')
ok('PREREQUISITE' in a,'架构文档仍含 PREREQUISITE（verify 依赖）')
# 6 验收覆盖 A04 条款
for term,label in [('读取绑定','图/向量读版本'),('向量检索','向量读版本'),('CAS','指针切换'),('C1 补偿','失败补偿'),('前滚','回滚编号')]:
    ok(term in spec,f'A04 验收条款「{label}」有落点：{term}')
print('\nRESULT:', 'ALL PASS' if not fails else f'{len(fails)} FAIL'); sys.exit(1 if fails else 0)
```
