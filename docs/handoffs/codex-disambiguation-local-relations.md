# DISAMBIG-BE-05：局部规范化与受影响关系重抽

原始负责人 Codex；本地实施基线 `27339d9`，原分支 `codex/disambiguation-local-relations`。以下保留 2026-11-11 本地工程验收记录；当时 BE-04 的 [PR #350](https://github.com/arvinhanye/SmartSketch/pull/350) 依赖未合并的 #348。2026-11-14 两个依赖均已进入 main，用户授权本批整合、复审及发布，进展见 [主线整合交接](codex-be05-main-integration-20261114.md)。未编辑 Claude 工作树或前端/公开契约。

## 行为与边界

- 关系生成前使用局部 complete-link 语义卡，保留每个原始提及的 ID、名称、定义、证据。局部结论来自既有双判与出处约束，不需要人工术语库；最终自动合并仍由全局成员校验和图约束决定。
- 新 `extract_normalized_relations@1` 输出原始成员端点。卡内不同成员间的关系不被隐藏，可直接否决误合并。规范化模式下坏端点、坏类型或不唯一出处须修复一次，仍失败则整单元失败；重复边可去重。旧 `extract_relations@2` 兼容不变。
- 关系表分窗保留整张语义卡，不能拆掉成员限定；单卡超限则登记技术缺口。来源可显式指定块与偏移，未指定只接受窗口内唯一匹配，最终仍恢复原始来源偏移。
- 首个检查点固定算法版本；旧任务无标记时保持旧语义。全局拆分后，只在原 merging 阶段重抽受影响小节，使用原始独立实体表；语义判定不重复，整组与图校验重跑。新冲突继续传播；已经拆分的成员禁止重新并回。
- 每小节本轮最多重抽一次，最多 32 小节；相同完整输入的关系版本缓存跨接管复用。结果按小节精确选择 initial/revision/omitted 一版，旧新版不叠加。失败或超限保留节点、弃用依赖旧映射的关系并禁止本任务自动合并，报告技术缺口，不制造 UNCERTAIN 或把因技术原因暂缓的 SAME 塞入合并审核；保留真实语义 UNCERTAIN。
- 计划缺失或草稿头过期时，未经确认的规范化关系不能进入原始图回退。独立重抽版本可以保留。撤销快照保存原始端点，撤销后关系回到原始成员。

## 内部接口与 Claude 对接

公开 HTTP/DTO 不变。本批没有新增必须迁移的前端接口。覆盖概况、自动历史与撤销控件仍是 [BE-03 交接](codex-to-claude-disambiguation-api-20261111.md) 中交给 Claude 的 UI 接入项，当前两份审核页面尚未消费这些新控件，不将后端返回状态表述为页面已经展示。

- 生成 section 检查点增加 `normalization` 与 `relation_input_digest`，元数据增加 `normalization_version=1`。
- 融合计划增加 `analysis_input_digest`、`relation_selection`、`relation_coverage`。初始关系摘要绑定全实体/来源、模型/提示词、输出预算、窗口策略与映射。
- 既有消歧覆盖接口的 `reasons` 可出现 `relation_reextraction_incomplete`、`relation_reextraction_failed`、`relation_reextraction_limit`、`relation_dependency_stale`。属于系统覆盖状态，不是需要教师逐对判断的语义不确定。
- 原有功能开关默认关闭；新工厂只在自动合并开启时启用局部卡。关闭开关接管已有固定任务时仍清算依赖，但不自动合并，不调用消歧模型。
- 稳定缓存保证的是已写完的版本；进程在模型返回后、版本提交前崩溃仍可能重复这次调用，沿用检查点的至少一次执行边界。

## 数据、回滚和保护

新增迁移 `023_relation_revisions.sql`，表 `task_relation_revisions` 保存不可变重抽版本；课程隔离、结果/失败约束和任务删除级联；写入由 merging 租约事务围栏。原始检查点不修改。

只在隔离测试库应用迁移。真实环境升级前停止服务并备份；回滚优先恢复备份，手动回滚按迁移文件的 `ROLLBACK` 语句在事务内执行。保护检查拒绝仍有固定规范化的非终态任务；先完成或取消。若同时退回 022，必须先回滚 023，再回滚 022，不修改已发布迁移内容。回滚会失去关系版本审计，保留备份；测试覆盖拒绝活动任务、终态回滚后原检查点保留及重新迁移。

取消、租约过期、凭据撤销、鉴权失败、熔断和调用记录失败保持任务级语义，不写伪成功版本；不在课程图锁内请求模型。测试用容器与开发数据库隔离。

## 验证记录（工程验收完成）

- 局部卡/严格关系/E01/E11：126 passed；检查点/窗口/E12/调度：85 passed。
- 新仓储/清算/真实 worker 等任务门禁：24 passed。
- 真实 Neo4j 初始 27 passed；扩展 worker/Neo4j 16 passed；实际图环传播与整卡窗口另有定向回归。
- 定向组合首轮 96 passed / 1 failed：旧 022 回滚夹具没有先退新增 023，重新应用 022 被迁移顺序守卫正确拒绝。修复仅让回滚按 023→022 顺序执行，原有断言保留；后续定向和回滚重应用已通过，见下面记录。
- 迁移修复后定向组合 97 passed（36.51s）；回滚与重应用定向 21 passed（2.47s）。
- 一次独立终审：审查全部 35 个文件（包括新增文件），1 Important、0 Critical/Minor、无搁置判断。多轮重抽可能让已拆开成员重新合并；新增三成员组跨小节反例先失败，修复为每轮累计所有局部组的拆分禁配，相关 13 passed（3.92s）。修复后新功能/真实 Neo4j 回归 63 passed（31.35s）。
- `PATH="$PWD/.venv/bin:$PATH" ./scripts/verify.sh`：exit 0。最终 `PYTEST_ADDOPTS=-x PATH="$PWD/.venv/bin:$PATH" ./scripts/verify/backend.sh full`：**4550 passed / 27 登记跳过 / 1 既有 Starlette 弃用警告，704.79s，PASS backend gate (full)，exit 0**。

## 仍待后续验收

本批只证明工程边界、版本选择和保护路径。没有调用真实模型，不宣称误合并率、重复减少比例、人工审核量或真实生成耗时已达标。下一步按完整方案开展带标注的真实材料/模型评测和手动合并计划；保留性能计量，不恢复硬性生成时间目标。

旧 v2 关系模式对重复引文仍沿用首匹配（DISAMBIG-FU-REL-01）；新规范化及重抽模式已加严格定位。该兼容边界没有伪装为旧任务全部完成来源消歧。


本批验证的复现入口（显式使用当前工作树源码，避免共享虚拟环境导入其他检出）：

```sh
export PYTHONPATH="$PWD/src/backend:$PWD"
# 本批全部新测试（模型均为 fake）
.venv/bin/python -m pytest tests/backend/test_local_normalization.py tests/backend/test_normalized_relations.py tests/backend/test_local_normalization_worker.py tests/backend/test_relation_revisions.py tests/backend/test_relation_reconciliation.py tests/backend/test_relation_reextract_worker.py -q
# 仅在隔离 Neo4j 环境变量已设置时执行图库验证，未配置不会算通过
.venv/bin/python -m pytest tests/integration/test_local_relations_pipeline.py tests/integration/test_fusion_pipeline.py -q
.venv/bin/python -m pytest tests/integration/test_f13.py -q
PATH="$PWD/.venv/bin:$PATH" ./scripts/verify.sh
PATH="$PWD/.venv/bin:$PATH" ./scripts/verify/backend.sh full
git diff --check
```

终审使用基线到当前工作区的差异包并纳入全部新增文件，因本批尚未提交，标准提交区间为空；若遗漏新文件会使审查不完整，因此同时核对了新文件清单。独立审查已覆盖全部 35 个文件。最后验收已核对 30 个源码/提示词/测试文件哈希，文档记录更新不影响该比对。


终审修复期间的接口补查还发现一项减负缺陷：重抽失败使自动合并整体关闭，但已完整判定 SAME 的节点仍生成 merge_blocked 审核项。真实 Neo4j 端到端和 SAME/UNCERTAIN/DIFFERENT 单元反例均已先复现；修复只过滤关系覆盖 partial 时因此暂缓的 SAME，保留真实 UNCERTAIN。首轮后端 full 因源码需修复主动终止（pytest 15 / 门禁 exit 1，缺终态报告），不计为通过；修复后重跑整个后端门禁。


第二轮全量检查暴露旧计时测试的隔离缺失：它替换了所有阶段与仓储，却没有替换新增的“是否有已固定规范化任务”读取，访问 `sqlite:///unused` 报无检查点表。单项先复现，再补该读取的测试替身；所有阶段/计时断言保持不变，整个计时文件 10 passed（0.81s）。真实关闭开关接管测试使用完整数据库，仍已通过。该轮全量检查主动停止（门禁 exit 1），最终重跑设置 `PYTEST_ADDOPTS=-x`，任何失败立即退出；通过仍要求全量执行完和跳过清单检查通过。


## 最终状态与证据复用

BE-05 工程验收 DONE，本地未提交、未推送；工作区保持可继续修改，不清理本地计划记录。上述独立终审问题和追加端到端问题均完成同一修复阶段的 RED→GREEN；没有延期 Minor，也没有搁置判断。最终视图/清算/真实 Neo4j 38 passed（8.80s），旧入库 Neo4j 30 passed（17.40s）；全量后端终态如上。basic、最终后端 full、哈希及范围检查全部 exit 0。两次中止的 full 都不计为通过。

30 个源码/提示词/测试文件与最终完整验收哈希一致。完整门禁与专项实际运行后，最后的任务记录检查只复核这些结果和文件哈希，不无意义地再跑一遍已通过的全量测试；若结果对应旧源码就不能复用，本次已排除该风险。前端/契约差异为空，Claude 工作树未编辑。只删除本批创建的临时 Neo4j `smartsketch-disambig5-20261111` 及其临时卷；开发容器保留。旧计时夹具意外生成的空 SQLite 文件已核实无表后删除。
