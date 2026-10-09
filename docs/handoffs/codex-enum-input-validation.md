# 非法枚举输入 HTTP 500 修复

- 日期：2026-10-09；任务：ENUM-INPUT-422；负责人：Codex。
- 用户要求：修复原审查第 2 项；仅本地实施，无本轮 PR/推送/合并/部署授权。
- 基线：已合并 #324 的 `origin/main=2e4d1c20`；复用干净受管工作区，新分支 `codex/enum-input-validation`。原 worker 修复/其他成员内容不变。

## 根因与最小修复

节点 PATCH `type/status`、关系 PATCH `type/status`、审核 POST `item` 在检查字符串之前执行 frozenset/dict 成员判断，数组或对象触发未捕获 `TypeError: unhashable type`。直接调用三个原解析入口及真实 HTTP 均复现；HTTP 回归 20 failed/65 passed，失败均为 500 代替 422。

- `src/backend/app/api/graph_nodes.py`：字符串 guard 短路后才查询枚举；非法值保留原 `enum`。
- `src/backend/app/api/relations.py`：字符串检查前移，类型闭集随后判断；既有 `string_type`/`enum` 与显式 null 的 `null_forbidden` 不变。
- `src/backend/app/api/review.py`：判别字段先检查字符串，未知类型/字符串走既有 `union_tag_invalid`，缺失保留 `missing`。
- 未扩大枚举、隐式转换字符串、捕获/隐藏任意 TypeError 或改服务业务规则；无 wire、模型、迁移、依赖、前端变化。`specs/teacher-review-publish.md` 补充既有契约边界验收，不改变 OpenAPI 真源。

## 回归与证据

新增 `tests/backend/test_enum_input_validation.py`：真实 FastAPI 请求、真实 SQLite/身份/课程权限；仅禁止进入图编辑上下文（不替换校验器）。12 类坏值×6字段/动作=72 请求，逐个核对 422/VALIDATION_ERROR/真实字段/原原因，SQL trace 无写语句、全库快照不变、无图上下文进入。另 7 项合法闭集正向控制与 6 项 401/403 权限顺序；共 85 项。

测试先行时首次夹具口令哈希不满足库 CHECK，已修正为项目既有合法测试 hash；该轮错误不是产品 RED。修正后 `red-http.log` 为 20 个真实 HTTP 500，直接解析器 TypeError 亦复现，然后才修改实现。历史日志不覆盖。

首轮相关选择 222 passed/27 既有图库登记 skip；随后细化合法 duplicate reject 控制，不带仅 merge 可用的 primary_id。最终测试版本 85 passed，全量后端使用同一最终 API/测试版本通过，结果见下节。

证据目录 `/private/tmp/smartsketch-enum-validation-20261009/`：`red.log`（夹具错误）、`red-http.log`（真实 RED）、`green.log`/`targeted.xml`、`enum-final.log`/`enum-final.xml`、`basic.log`、`backend-full.log`、`backend-summary.json` 及 `source-before.json`/`source-after.json`。全量门禁读取 XML 完成判定后自动清理；临时捕获未成功，因此没有归档 `backend-full.xml`，验收依据为完整 pytest/gate 日志、实际退出码与源码哈希。

## 验证命令与最终结果

- 临时锁定解释器 `/private/tmp/smartsketch-pr324-venv/bin/python`；`PYTHONPATH=src/backend`、禁用额外 pytest 插件/缓存；未修改开发环境依赖。
- `python -m pytest tests/backend/test_enum_input_validation.py tests/backend/test_f08.py tests/backend/test_relations_api.py tests/backend/test_f11.py -q -p no:cacheprovider`（相关选择；图库项不配置时按原登记跳过）。
- 最终 `python -m pytest tests/backend/test_enum_input_validation.py -q -p no:cacheprovider`。
- `./scripts/verify.sh`；`scripts/verify/backend.sh full`；`git diff --check`。
- 未运行真实 Neo4j 集成/E2E；本缺陷在图 IO 前拒绝，零上下文/零 SQL 写入由真实 HTTP 回归验证，合法图编辑由原 F08/关系 API 回归覆盖。无新增 skip，不称为全量 integration/CI 通过。

- 最终新增测试：**85 passed**，无 skip；basic 实际 **exit 0**（含 contracts gate）。
- 全量 backend+tooling：**4149 passed/27 既有登记 skip/1 既有 FastAPI TestClient 弃用 warning**，613.07s，`PASS backend gate (full)`、**exit 0**。三份 API 与新测试的门禁前后 SHA256 相同；最终 diff-check 通过。
- 独立只读审阅：无 Critical/Important。Minor 建议为缺失 item 精确原因增加常驻 HTTP 回归；本轮以临时单项探针补验，**1 passed**，断言 422/body.item/missing、零图上下文、无 SQL 写入/全库不变；尚未加入常驻 CI（该缺失分支实现未改变，非本次修复的阻塞项）。首次临时探针因不在 tests/backend 下、未加载 conftest 测试密钥收集失败；显式使用既有测试密钥后通过，两个日志均保留。
- 审阅边界已落实：全量结果由执行者确认；真实图库/E2E 未执行、不外推为通过；审计/跨库一致性/其他截止问题不在本轮；提交、PR、合并、部署未执行。无需数据/接口迁移或额外人工设计决定。

## 回退与边界

仅恢复本轮三份 API 的校验顺序并撤销对应测试/规格补充即可，无数据或迁移回滚；恢复旧代码会重新暴露数组/对象的 HTTP 500。保留已合并 worker 改动与其他成员代码。不自动提交/推送/开 PR/合并，不改其他中严重程度发现，也不改变 stage_c_status OPEN、technical_freeze NOT_PERFORMED。

## 提交与 PR 发布补充（2026-10-09）

用户最新要求「提交并开PR」，覆盖本记录前述仅本地修改的历史边界。此次提交/正常推送仅包含三份 API、85 项新测试、规格、任务状态与本交接共七份文件，目标 `main`，保留分支与受管工作区。不合并/部署/冻结；先前 #324 条件合并授权不外推到新 PR，远程 CI 结果仍以 GitHub 实测为准。发布前复验与远程基线核对结果将在完成后补充。

发布前已抓取 `main=2e4d1c20`（仍为修复分叉），没有同名分支的既有 PR。再次完整执行 basic **exit 0**、backend+tooling **4149 passed/27 既有登记 skip/1 既有 warning，exit 0**（708.00s）；三 API 与新测试 SHA256 前后相同，diff-check 通过。证据 `/private/tmp/smartsketch-enum-pr-publish-20261009/` 的 `basic.log`、`backend-full.log`、前后 manifest 与 `verification-summary.json`；未归档临时全量 XML。提交仅上述七份文件，下一步正常推送与 PR 创建，不将此本地结果外推为远程 CI 通过。

发布已完成：修复提交 `7e03526f25110f9798c29b5b09abebd1834354d0` 已正常推送，[PR #329](https://github.com/arvinhanye/SmartSketch/pull/329) 已创建并附加，OPEN/非草稿，`codex/enum-input-validation` → `main`。GitHub 初始实测 MERGEABLE，七份文件符合范围，八项 push/pull_request CI 排队/运行；不将其记为通过。后续这两份状态文档补充不改产品/测试 SHA，分支和工作区保留，未合并/部署/冻结。下一位首个动作：检查该 PR 最终 head 的全部 CI 与审阅结论，再取得针对新 PR 的合并指示。

最终发布状态文档版再次运行 `./scripts/verify.sh`，实际 exit 0，日志 `final-basic.log`；diff-check 通过，产品/新测试仍匹配全量后端验收 manifest。

## PR #329 条件合并授权（2026-10-09）

用户最新要求「CI通过就合并」，覆盖前述发布但不合并的历史边界，仅限 #329。核对精确 head/base 与所有 CI，包含最终状态文档 head；全部 SUCCESS 且合并条件满足后正常执行 GitHub merge commit，精确匹配受测 head，保留 pinned worker 历史祖先、分支与受管工作区。不绕过保护、不强推、不部署/冻结；实际合并提交和时间以 GitHub PR 记录为准。

已发布 `b835c456` 的 push `37916694886` 与 pull_request `37916702362` 八项检查均 SUCCESS；实测 base `2e4d1c20`，MERGEABLE/CLEAN。实际 CI：后端 4149 passed/27 原登记 skip、前端 1227 passed/66 文件及 type-check/build、integration 462 passed/4 原登记 skip、backend-live 44、演示 E2E 2、个人 E2E 4。原「本地未跑图库/E2E」记录仍为本地范围，最终远程 CI 已补足这部分证据；产品/新测试与已验收 SHA 相同。证据 `/private/tmp/smartsketch-enum-merge-20261009/` 的两份完整 CI 日志与 PR 精确 head/base/check 快照。

本授权/证据补充只有两份文档变化，提交前 basic 与 diff-check 再验证，推送后仍等待最终 head 的全部 CI 独立成功，精确匹配合并，最终合并记录保留在 GitHub PR；不因旧 head 全绿绕过最终文档 head 检查。
