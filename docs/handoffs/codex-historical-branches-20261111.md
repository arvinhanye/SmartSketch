# MAIN-INTEGRATE-02：历史分支有效改动整合

状态：实现和逐分支审查完成，完整门禁、主线合入与分支删除进行中。基线 main `f9447860589d450aee34d4b2bf1532fdb21cb033`；用户已授权清理，并明确批准修复后纳入级联删除。分支原 SHA 与逐项依据见 [审计](../reviews/historical-branches-20261111.md)。

## 交付与决定

- ADR-097 / F09：默认单点删除保持 204；教师可预览并明确选择级联删除仅因当前节点而失去全部可见 CONTAINS 父节点的后代。共享后代保留，其他关系不触发级联，遍历不按固定深度静默截断。
- 新增 `GET /courses/{cid}/kp/{kid}/delete-impact`；级联 DELETE 必须附 `cascade=true` 和预览 token，成功返回删除清单。token 绑定课程、根节点、草稿修订、有效任务与草稿内容；课程锁和 Neo4j 事务守卫内重算，变化返回 409，确认失效时不写删除审计、不增加修订。托管事务重试只记一次审计。
- 前端把预览绑定请求代次、账号、课程和节点；默认单点，明确勾选才级联。409 刷新预览并要求再次点击，不自动重放删除。发布快照和共享来源块保持。
- 问答 SQLite 审计存储故障不覆盖既定 JSON/SSE 结果，日志仅记录请求 ID、结果种类和异常类型；不把故障说成成功持久化。
- 模型设置编辑后清除过期连接结果；审核页 RELATED_TO 不再显示方向箭头。其余三种关系方向与保存/清除错误隔离保持。
- 跨平台移植仅包含 Markdown/JSON 的 LF、系统临时心跳路径、旧控制台编码与 JUnit collection skip 真实原因处理。PDF 不转文本；相对目录语义不变。新增 Windows 精确回归 job，不声称完整 Windows 安装验收。
- K08 旧作者验证原文归档并标注时效；其余旧界面、明文全局配置、契约桩、已替代实现只保留在完整历史 bundle。

## 已执行验证

- 问答日志：失败回归 7 failed / 12 passed → J10/J07/D1/D3 50 passed。
- 前端两项移植：失败回归 9 failed / 55 passed → L10/H09/N03–N05 81 passed。
- 跨平台：最初 6 failed / 5 passed → portability/K11 31 passed。独立复核用真实 pytest 报告发现 tuple 包装遗漏；补回归 1 failed / 1 passed 后修复，最终 portability/K11 **33 passed**。未知原因、空原因和普通 message 优先规则未放宽。
- 级联初版：后端定向 21 passed；F08/F12/级联关联 110 passed；前端新套 12 passed、关联 230 passed；契约生成与类型检查通过。独立复核发现预览提前对账、单删入口漏传修订号，故这些结果不是最终验收。
- 级联修复：后端 3 failed / 1 passed → 26 passed，F12 对账子集 15 passed；独立原探针加级联 28 passed，旧 F12 默认行为 2 passed。前端透传/页面接线先 5 failed / 73 passed → node-deletion/H14/H07 **139 passed**。重新生成的契约校验通过。
- 测试索引 1 passed；`git diff --check` 通过。
- 首次完整命令：`PATH="$PWD/.venv/bin:$PATH" PYTHON="$PWD/.venv/bin/python" E2E_PYTHON="$PWD/.venv/bin/python" GOCACHE=/tmp/smartsketch-historical-go-cache PLAYWRIGHT_CHROMIUM_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' ./scripts/verify.sh integration`。为修复独立复核发现而在契约回归阶段主动中断（2 passed 后 KeyboardInterrupt，剩余进程树已终止），不能记为通过。原日志 `/tmp/smartsketch-historical-integration.log`；修复后重新运行。
- 独立复核：Windows 门禁、级联后端两个 P2 已经原反例重跑关闭；单删漏修订号已补精确参数和两模式页面回归。根代理复核最终透传实现，QA 日志、E2E 新增选择器/等待/数据边界另有独立审查；当前无已知未关闭代码问题。真实 Neo4j、真实浏览器和 Windows 仍待相应运行，不能以 mock/静态复核代替。
- 新一轮完整门禁已启动，日志 `/tmp/smartsketch-historical-integration-final.log`；包含新增真实 Neo4j 8 项，以及教师 E2E 发布后默认单删/明确级联/已发布学生版本保留的真实浏览器回归。
- PR #345 首轮前端 84 文件 / 1443 条测试及 build 通过，但新增 H14 断言对 `get()` 返回值调用 `exists()` 不符合 Vue Test Utils 类型，类型门禁失败；改为 `find().exists()`，存在性断言保持。修复后 `npm --prefix src/frontend run type-check` exit 0；等待新 head CI，未将首轮 job 记为通过。

## 接口、配置与数据

契约真源、OpenAPI、Python/TypeScript 生成物同步更新；无迁移、依赖升级、付费调用、既有课程数据操作。默认心跳文件改为平台临时目录下 `smartsketch-worker.heartbeat`；显式 `WORKER_HEARTBEAT_FILE` 仍优先，容器路径不变。所有图库验收只用隔离测试容器与合成课程。

## 恢复与剩余步骤

主检出 `.demo/historical-branch-cleanup-20261111/` 保存 15 个精确 SHA、逐分支清单、原始引用和已通过 `git bundle verify` 的完整 `all-branches.bundle`（8,744,692 bytes），以及审查/红绿日志。恢复示例：`git fetch /绝对路径/all-branches.bundle refs/remotes/origin/<branch>:refs/heads/recovery/<name>`。

下一步：等待完整门禁和独立复核，修复确定问题，PR 通过后合 main；使用精确 SHA lease 原子删除 15 个旧引用并核对远端。未通过前不得把待删清单写成已删除。代码可回退本轮提交；回退代码不能恢复用户未来主动删除的业务数据。旧真实模型、窄屏、读屏等未完成验收不因本轮合并自动关闭。
