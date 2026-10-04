# Codex：计划 C 验收复审问题修复

- 日期：2026-10-04；任务 C-ACC-FIX-54。
- 基线：54a7c67；工作分支 codex/plan-c-acceptance-fixes。
- 工作区：/Users/arvinhan/.codex/worktrees/plan-c-acceptance-review/SmartSketch。
- 依据：docs/reviews/codex-claude-plan-c-acceptance-54a7c67.md；用户已明确先修复、自行检查后决定冻结。
- 不改 Claude/测量工作区、不推送合并、不发真实生成或在线向量调用。

## 1. 四项修复

| 问题 | 本轮处理与证据 |
| --- | --- |
| P2-01 工作表结构漏检 | evaluation/c04_signoff.py:69–91 在构造字典前拒绝重复行号/ID，数据行严格七列，非数字/非法 ID 的表格数据行拒绝；保留正常转义、合法判定及 apply_marks 字节保留行为。新增 10 例：实体/关系重复冲突及顺序、八列/六列/畸形追加行 |
| P2-02 批量转换部分写入 | evaluation/c04_signoff.py:203–255 拆为只读预检/计算与最终写出；任一所选课程失败即退出，尚未写任何结果。新增 12 例覆盖默认/两种显式顺序、任一课程未填/缺副本且四份旧结果不变；1 例失败批次不新增文件，1 例合法批次两课完整写出 |
| P3-01 异常解锁计时缺失 | src/backend/app/workers/persist_graph.py:517–545 用主体 finally 起表、上下文退出 finally 停表；进入持锁上下文失败不虚构解锁阶段。新增 4 例覆盖 Neo4j 异常、租约丢失、解锁 SQLite 异常、未捕获 KeyError，断言 >=20ms、清理先后、T6/事务是否执行与返回/异常传播。计时不改变入库控制语义 |
| P3-02 文档当前/历史状态混杂 | docs/tasks.md 顶部明确当前状态、更新四项旧状态与不补测边界；C04 README 表格更新为 arvin 已签收，描述复核后采纳辅助判定。Codex 新交接为当前依据，明确覆盖 Claude 旧交接 §3C/§6 的初始待签收叙述；按交接所有权规则保留 Claude 交接原文，不代写它。决策记入 docs/decisions.md |

没有新增 API/DTO/契约/迁移/依赖。图谱提取功能与个人 API 模式保持原实现；本轮不改抽取提示词或数据质量判定。

## 2. 实际定向验证与证据

- 签收回归 RED：23 failed / 16 passed，全部失败为原缺陷（重复/形状未拒绝，批量覆盖旧结果）；日志 /private/tmp/codex-c-acc-fixes-signoff-red.log，exit 1。
- 签收 + 准确率 GREEN：46 passed；日志 /private/tmp/codex-c-acc-fixes-signoff-green.log，exit 0。
- 计时回归 RED：4 failed / 6 passed，均因 lock_release_ms 缺失；日志 /private/tmp/codex-c-acc-fixes-logs-red.log，exit 1。
- 最终指定四文件：61 passed；日志 /private/tmp/codex-c-acc-fixes-targeted-final.log，exit 0。相对原33例新增28例，不删用例/不放宽断言/不新增skip。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src/backend .venv/bin/python -m pytest \
  tests/backend/test_c02_phase_logs.py tests/tooling/test_c_acc_sources.py \
  tests/tooling/test_c04_signoff_sheet.py tests/tooling/test_c04_accuracy.py \
  -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src/backend .venv/bin/python \
  evaluation/raw/codex-c-acc-fixes/checks.py
```

只读核对脚本 exit 0，结果存 evaluation/raw/codex-c-acc-fixes/checks.json：27 种入库业务路径与 4a6308b 的调用顺序、参数、返回/异常一致；异常工作表全部拒绝，失败批次 changed_files=[]；正常转义与清空行字节保持；四处只读 connect 异常后恢复。两课原 predictions/worksheet 哈希与测量区一致；263 条用户判定及报告全部重算一致；30 条判错依据同文，5 条移除复核注释。course1 64/76、58/61；course2 61/68、45/58。测量主库哈希仍与已存 before/after 一致，WAL 0；源分支/工作区前后状态一致。未重新连接共享 Neo4j。

**探测勘误**：旧复审脚本“额外列”探测实际上向合法依据列加文字；本轮新脚本修正为真正的第八列，且有原代码 RED 证据。旧复审资产保留；勘误已加到 Codex 自己的旧报告，不改真实签收或测量文件。

现有启动脚本 bash -n 检查 exit 0；正式个人 API 实际启动/真实供应商连接本轮未执行。详见 docs/handoffs/codex-plan-c-manual-start.md。

## 3. 完整门禁

稳定代码树整次 `./scripts/verify.sh integration` **exit 0**，本轮独立运行；不借用旧门禁结果。

| 层 | 本轮 PASS | 登记 SKIP |
| --- | ---: | ---: |
| backend + tooling | 3921 | 27 |
| frontend（38 文件，type-check/build） | 934 | 0 |
| integration | 393 | 4 |
| backend-live | 44 | 0 |
| 演示 E2E | 2 | 0 |
| 个人本机假供应商 E2E | 4 | 0 |

31 条既有登记 SKIP 不算 PASS，无新增 skip 或依赖升级。既有 Starlette/httpx 弃用提示、前端大 bundle 警告保留，不以调整依赖/放宽阈值掩盖。

执行前确认本目录无 `.env` 和业务 SQLite、隔离端口空闲。下列命令实际运行，日志 `/private/tmp/codex-c-acc-fixes-integration.log`，退出码同名前缀 `.exit`；只用一次性 Neo4j、临时测试库与本机假供应商：

```bash
cd /Users/arvinhan/.codex/worktrees/plan-c-acceptance-review/SmartSketch
/usr/bin/env -i HOME="$HOME" USER="$USER" LANG=en_US.UTF-8 \
  PATH="$PWD/.venv/bin:$PWD/node_modules/.bin:$HOME/.docker/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src/backend" PYTHON=.venv/bin/python \
  E2E_API_PORT=19000 E2E_WEB_PORT=16073 E2E_NEO4J_PORT=18588 \
  E2E_PROVIDER_PORT=19790 VERIFY_NEO4J_PORT=18589 \
  PLAYWRIGHT_CHROMIUM_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  /bin/bash ./scripts/verify.sh integration
```

个人假供应商 E2E 实际通过 PDF/MD 上传到发布/学生可见、取消后重传、鉴权失败终止、两课隔离，仍不等于新真实模型测量。测试目录 `.e2e/20261004-065518`、`.e2e/20261004-065634` 是忽略产物。

四项状态分开登记：**工程门禁通过：是；真实测量已完成：是（既有两 PDF 与当前配置13题，未新增）；人工准确率已签收：是（复核后采纳辅助判定，非独立盲判）；技术冻结已执行：否。**

## 4. 未验证与剩余边界

- 预检失败零写入不是跨文件磁盘事务；预检通过后的磁盘 I/O 故障仍可能留下部分输出。并发外部编辑输入不属于锁定快照承诺。
- 只补了未来异常解锁计时；course1 的 6471ms 与旧末段 15.643 秒历史根因仍 OPEN。
- 新 Markdown 关闭思考抽取、浏览器可见首字、v3 思考开启基线三项按用户决定不补测，保持未测；PDF 20.90/28.08 秒不外推 MD，SSE 783–2927ms 不称为页面首字。
- 真实发布副本的出处语义与真实供应商个人模式本机人工检查本轮没有执行。已存草稿来源核验只证明可定位与课程隔离。
- 台账保持生成 844451 / 900000，向量 12005 另计；本轮新增真实调用均0。
- 用户 arvin 人工准确率已签收（逐条复核后采纳辅助判定，非独立盲判），但不等同技术冻结。
- stage_c_status OPEN；technical_freeze NOT_PERFORMED。用户下一步按本轮启动指南检查，明确反馈后再决定冻结；九类参赛材料、美化与生产部署加固不在本修复轮范围。
