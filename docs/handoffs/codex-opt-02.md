# OPT-02：测试等待稳定性

- task_id：OPT-02；负责人：Codex；状态：IN_PROGRESS（浏览器20轮仍受阻；完整integration前次取消，尚无自然结束结果；个人模式E2E已另项修复并通过）；收尾核对日期：2026-11-10。
- 分支：`codex/opt-02-test-waits`；基线：`ad63341`。
- 交付工作区：`/Users/arvinhan/.codex/worktrees/opt-02-test-waits/SmartSketch-main`。
- 原目录开始时干净。过程中用户确认另一个会话在执行 OPT-05，共享检出也切到 OPT-05。本任务从原基线建立独立工作区，只带入自己的测试和文档；产品改动不属于本任务。
- 已迁出原目录中的本任务测试副本和 OPT-02 认领段：逐文件核对其内容仍为本任务版本、没有暂存变更、对应文件的 HEAD 仍与基线相同后才恢复；OPT-05 产品、文档和新测试全部保留。迁出备份与核对结果在 `.demo/opt-02/moved-source-tests.patch`、`source-move-result.json`。
- 已读 AGENTS、测试规则、任务/问答规格。指定 Claude 交接文件不在基线分支，已通过 `git show claude/code-structure-review-handoff-49e73a:docs/handoffs/claude-code-structure-review-codex-handoff.md` 阅读 OPT-02。
- 无产品、API、数据模型、配置或依赖清单变更；本轮仅补充验收证据与任务记录，按用户要求提交到当前分支，不推送、不开 PR。

## 2026-11-10 后续修复

用户随后授权先验证方案再修复隐藏控件问题。`E2E-PERSONAL-01`只更新个人模式测试的高级选项操作，真实教师/学生页面方案检查通过，个人模式E2E **4 passed，exit 0，约1.7分钟**，基础门禁exit 0；见[独立交接](codex-e2e-personal-01.md)。下文此前失败/取消结果保留为历史证据，不改写为通过。21px产品布局问题仍OPEN，浏览器20轮仍受阻，本次没有重跑整条integration，OPT-02保持IN_PROGRESS。

## macOS：先复现，再定位，再修复

原测试在两个 `python3 -c` 子进程里分别取 `time.monotonic()` 后相减。默认 PATH 使用 Anaconda Python 3.13.5，首次及随后5次均通过；改成系统 PATH 后，macOS Python 3.9.6 的单调读数约为进程启动后的0.04秒，两个进程的基准不同，旧测试稳定测得约0.011秒。根因是测试跨进程相减时钟，停止脚本实际执行了两秒宽限期。

修改前复现命令（3次失败）：

```bash
PATH=/usr/bin:/bin:/usr/sbin:/sbin .venv/bin/python -m pytest -p no:randomly -q \
  tests/tooling/test_stop_procs.py::test_grace_period_is_not_shortened_by_shell_seconds_rounding
```

证据：`/private/tmp/smartsketch-opt02-root/stop-system-path-baseline*.log`。修复后同一系统 PATH 下整个文件连续20轮通过，每轮4项。现在由同一 pytest 进程计时，子服务通过 stdout 报告信号处理器就绪，父进程通过 stdin 放行停止；不再睡0.3/0.5秒猜测启动完成。子服务等待终止信号，保留真实两秒断言和近墙钟整秒边界的等待。

反证：仅在 /private/tmp 生成使用旧 SECONDS 整数截止的停止脚本变体，让新测试读取它；新测试如预期失败，证明仍能发现真实的宽限期缩短。仓库 scripts/_stop-procs.sh 未修改。

## 初始31处逐项记录

已运行指定的 `grep -rnE "time\.sleep\(|waitForTimeout\(" tests`：31处源代码，另有一个未跟踪 .pyc 二进制匹配。以下行号均为 ad63341 基线，路径相对于 tests/。原始清单曾存于 `/private/tmp/smartsketch-opt02-root/initial-waits.txt`；重启后从同一 Git 基线重新导出的31项在 `.demo/opt-02/initial-waits-regenerated.txt`，最终 grep 的4项在 `.demo/opt-02/final-waits.txt`。

| 原始位置 | 处理 | 条件或理由 |
| --- | --- | --- |
| backend/test_c02_phase_logs.py:47 | 修改 | 向量日志计时改目标模块局部假时钟。 |
| backend/test_c02_phase_logs.py:119 | 修改 | pipeline 阶段计时改假时钟，原日志断言保留。 |
| backend/test_c02_phase_logs.py:154 | 修改 | 子步骤替身推进假时钟。 |
| backend/test_c02_phase_logs.py:192 | 修改 | 释放锁日志计时改假时钟。 |
| backend/test_c02_phase_logs.py:260 | 修改 | 失败路径解锁计时改假时钟，清理/异常断言保留。 |
| backend/test_d11.py:490 | 修改 | 已有轮询统一为共享 wait_until，等 renewals >= 1。 |
| backend/test_d3.py:62 | 修改 | DNS 用可释放 Event 阻塞，客户端仍测真实超时；清理等待 resolver 完成。 |
| backend/test_d3.py:90 | 保留+注释 | 消耗真实连接时间，验证多地址共享一个真实截止时间。 |
| backend/test_d3.py:171 | 删除等待 | 替身所有调用都是默认零延迟，sleep(0) 无业务等待条件。 |
| backend/test_d3.py:216 | 保留+注释 | 检验 embedding/HTTP 链路的实际耗时上界和 timeout 预算。 |
| backend/test_d3.py:277 | 修改 | 改写耗尽预算用局部假时钟，保留不派发 embedding 的断言。 |
| backend/test_e03.py:938 | 修改 | HTTP 响应阻塞到 fixture 释放 Event，保留真实0.2秒超时和返回上界。 |
| backend/test_e12.py:134 | 修改 | 首批并发请求用 Barrier 精确重叠；并发上限断言加强。 |
| backend/test_e12.py:984 | 修改 | 等实际 dispatcher 观察鉴权失败进入 halt=auth 后再释放在途请求。 |
| e2e/personal.spec.ts:33 | 保留，文件不改 | 已是服务器 Retry-After 真实退避；helper 校验本机供应商、429/RATE_LIMITED、1–60秒、最多重试一次，已有用途注释。 |
| frontend/teacher-viewport.browser.cjs:44 | 修改 | 等 aria-busy=false 且 data-zoom 存在，确认真实图谱完成初始化。 |
| frontend/teacher-viewport.browser.cjs:54 | 修改 | 等 ne-definition 可见，确认编辑表单加载。 |
| frontend/teacher-viewport.browser.cjs:71 | 修改 | 等900宽视口生效，且实际 canvas 尺寸与容器一致。 |
| frontend/teacher-viewport.browser.cjs:74 | 修改 | 等还原视口生效，且实际 canvas 尺寸与容器一致。 |
| frontend/teacher-viewport.browser.cjs:88 | 修改 | 等 ne-empty 可见，确认编辑器已关闭。所有条件等待有30秒上限，原布局断言不变。 |
| integration/bolt_fault_proxy.py:330 | 修改 | 共享轮询；子进程探测连通/迁移/查询，以整轮剩余时间限制并可kill+wait回收，迁移包装后的暂态异常才重试。 |
| integration/test_f13.py:240 | 修改 | 轮询数据库课程锁确已续期，保留原续期断言。 |
| integration/test_k08.py:271 | 修改 | 轮询 API /health 并检查进程存活；日志文件避免超时分支读取活进程 stdout 卡死。 |
| integration/test_k08.py:352 | 修改 | 子进程等终止信号，独立60秒alarm看门狗保证supervisor回归也不会无限join。 |
| integration/test_k08.py:379 | 修改 | 等 heartbeat 文件；观察线程失败也发 SIGTERM 清理，错误传回主测试。 |
| integration/test_k10.py:589 | 修改 | 复用带子进程硬截止的Bolt探测；仅在容器设置函数内导入，避免影响pytest外的发布探针。 |
| integration/test_worker_persist_transport.py:105 | 修改 | SQLite writer 等提交成功或停止事件，5秒截止，仅重试 BUSY/LOCKED。 |
| tooling/test_l11_fake_provider.py:51 | 修改 | 原固定次数轮询改单调截止 /health 轮询，检查进程存活，失败也清理。 |
| tooling/test_stop_procs.py:30 | 修改 | 子服务等信号，就绪握手替代 shell 启动睡眠。 |
| tooling/test_stop_procs.py:50 | 修改 | 同上，起止计时移到同一 pytest 进程。 |
| tooling/test_stop_procs.py:53 | 保留、移位+注释 | 父进程真实等到墙钟秒末，触发 Bash SECONDS 舍入；假时钟不能推进 shell 时钟。 |

共享辅助 tests/waiting.py 使用单调截止和明确超时描述，返回首个满足条件的值；调用方只捕获预期暂态错误。假时钟只替换目标模块对象，不修改全局 time，不影响真实 socket/watchdog。

源代码匹配由31处减到4处：27处替换/移除，4处保留（D3两处真实预算、stop-procs墙钟边界、个人模式服务器Retry-After）。已有条件轮询也统一到共享辅助，未把sleep简单换成另一个固定延时。

交叉复核及真实验证补修：迁移驱动异常会包装为GraphMigrationError，需沿cause/context分类；Neo4j单次探测最初设置10秒上限，真实运行会中断尚在建索引的DDL，重试产生IndexWithNameAlreadyExists。已先增加预算回归并看到RED，再改为完整剩余预算（总120/180秒上限不变），不再人为提前杀DDL。K10的pytest外发布钩子导入测试模块时缺仓库根路径，已通过独立子进程复现ModuleNotFoundError，并将辅助导入局部化；原备份/发布断言保留。这些均是测试辅助问题，产品代码未改。

附带测试清理：E03 单次 HTTP 请求结束后仍读取已关闭 keep-alive socket，诊断复现 ConnectionResetError [Errno 54]。测试 handler 现在明确关闭连接，fixture 释放阻塞事件并 join 线程；产品传输未改。修正后整个文件重新20轮。旧日志位于 /private/tmp/smartsketch-opt02-backend/before-http-cleanup/。

## 前序验证结果与命令（保留历史，最新结果见收尾复验）

使用现有 `.venv` 和根目录/前端 `node_modules`，隔离目录通过符号链接复用已安装依赖，清单与锁文件未变。基本循环每个文件独立执行20次、失败立即停止，失败日志保留；`test_file` 对应下表的 `tests/` 路径：

```bash
for i in {1..20}; do
  PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=src/backend \
    .venv/bin/python -m pytest -p no:randomly -q "$test_file" > "$log_dir/$i.log" 2>&1 || exit 1
done
```

`test_stop_procs.py` 的20轮特意将 PATH 改为 `/usr/bin:/bin:/usr/sbin:/sbin`，仍用 `.venv/bin/python -m pytest` 启动。F13 的20轮向专用可清空实例设置 `SMARTSKETCH_TEST_NEO4J_URI/USER/PASSWORD` 后运行相同循环。

重启后的实际命令如下。运行器逐轮使用 `-p no:randomly -p no:cacheprovider -q -rs`，清除 `SMARTSKETCH_SKIP_DOCKER`；K10 自建带 `smartsketch.opt02=true` 标签的独立数据库，并使用 17691/17692 端口做 dump/load，finally 删除该实例；transport 的 fixture 每轮自建、核对所有权并删除数据库。

```bash
.venv/bin/python .demo/opt-02/repeat.py proxy
.venv/bin/python .demo/opt-02/repeat.py k08
.venv/bin/python .demo/opt-02/repeat.py k10
.venv/bin/python .demo/opt-02/repeat.py transport
# 第二次重启前 K10 已完成19轮；核对所有测试 SHA256 未变后，仅重跑被中断的第20轮。
.venv/bin/python .demo/opt-02/resume-repeat.py k10
PATH="$PWD/.venv/bin:$PATH" ./scripts/verify.sh full
PATH="$PWD/.venv/bin:$PATH" PYTHON="$PWD/.venv/bin/python" E2E_PYTHON="$PWD/.venv/bin/python" \
  VERIFY_NEO4J_PORT=17689 \
  E2E_NEO4J_PORT=17687 E2E_API_PORT=18002 E2E_WEB_PORT=15175 E2E_PROVIDER_PORT=18902 \
  PLAYWRIGHT_CHROMIUM_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  ./scripts/verify.sh integration
```

完整失败尝试使用相同 integration 命令，但未设置 `PYTHON`、`E2E_PYTHON`（exit 1）；上方显式绝对路径的额外重跑最终在基线阻塞确认后主动停止（exit 143）。独立 E2E 诊断命令如下：教师/学生完整结束为2 passed；个人模式首项失败后停止余下诊断（1 failed、1 interrupted、2未运行，exit 130），不算完整个人模式验收。

```bash
export PATH="$PWD/.venv/bin:$PATH" E2E_PYTHON="$PWD/.venv/bin/python" \
  E2E_NEO4J_PORT=17697 E2E_API_PORT=18007 E2E_WEB_PORT=15179 E2E_PROVIDER_PORT=18907 \
  PLAYWRIGHT_CHROMIUM_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
scripts/e2e.sh tests/e2e/teacher.spec.ts tests/e2e/student.spec.ts
E2E_LLM_MODE=personal scripts/e2e.sh tests/e2e/personal.spec.ts
```

浏览器复现命令（先启动当前工作区的 Vite 于 5182）：

```bash
E2E_BASE_URL=http://127.0.0.1:5182 \
  PLAYWRIGHT_MODULE="$PWD/node_modules/playwright" \
  PLAYWRIGHT_CHROMIUM_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  node tests/frontend/teacher-viewport.browser.cjs
```

原版对照使用 `git show ad63341:tests/frontend/teacher-viewport.browser.cjs` 导出脚本，唯一诊断增量是打印390宽的测量值；相同环境执行，原断言和固定等待不变。

| 文件 | 20轮状态 | 每轮结果 |
| --- | --- | --- |
| backend/test_d3.py | PASS 20/20 | 18 passed |
| backend/test_c02_phase_logs.py | PASS 20/20 | 10 passed |
| backend/test_d11.py | PASS 20/20 | 42 passed |
| backend/test_e12.py | PASS 20/20 | 44 passed |
| backend/test_e03.py | PASS 20/20（最终清理修正版） | 291 passed |
| tooling/test_stop_procs.py | PASS 20/20，故意使用系统 PATH | 4 passed |
| tooling/test_l11_fake_provider.py | PASS 20/20 | 13 passed |
| tooling/test_worker_bolt_proxy.py | PASS 20/20（最终预算修正版） | 14 passed |
| integration/test_f13.py | PASS 20/20 | 每轮30 passed，含真实Neo4j，无skip |
| integration/test_k08.py | PASS 20/20 | 每轮23 passed，包含真实API/web镜像构建，无skip |
| integration/test_k10.py | PASS 20/20 | 每轮20 passed，含真实 Bolt 与 neo4j-admin dump/load，无skip；19轮+中断后补跑最后1轮 |
| integration/test_worker_persist_transport.py | PASS 20/20 | 每轮65 passed，真实网络故障/围栏，无skip |
| frontend/teacher-viewport.browser.cjs | BLOCKED，尚未20轮全绿 | 改动版及原始基线都在390px原有布局断言失败；四种宽视口通过 |

- 五个后端文件合计8100通过，100份最终日志无失败和后台异常；目录 /private/tmp/smartsketch-opt02-backend/。
- 两个 tooling 文件合计340通过；日志 /private/tmp/smartsketch-opt02-root/{stop,provider}-repeat-*.log。
- F13日志与运行器：/private/tmp/smartsketch-opt02-root/f13-*、run-f13.py。
- 重启后 proxy、K08、K10、transport 循环的每轮日志和机器可读汇总：`.demo/opt-02/repeats/<suite>-{01..20}.log`、`<suite>-summary.json`。
- 两个共享辅助 `tests/waiting.py`、`tests/integration/bolt_fault_proxy.py` 不直接收集测试，通过消费者文件的20轮验证；后者另有 tooling 的14项探测/异常/预算/子进程回收回归。
- full：PASS（exit 0）；后端4254 passed/27登记skip，前端82文件/1375 passed，类型检查、构建、启动器与契约通过。持久日志`.demo/opt-02/verify-full.log`。
- integration：FAIL（完整命令 exit 1），真实集成463 passed/4登记skip，图库后端44 passed；E2E因相对解释器路径无法启动。持久日志 `.demo/opt-02/verify-integration-relative-python-failure.{log,exit}`。补设绝对解释器后的独立教师/学生E2E为2 passed；个人模式首项复现基线隐藏控件超时，随后停止额外诊断，结果为1 failed/1 interrupted/2未运行（exit 130）。
- 额外完整重跑：主动停止（exit 143），不是通过；理由是上述基线阻塞已确认，不再重复同一组长超时。日志 `.demo/opt-02/verify-integration-extra-retry-stopped.{log,exit}`，停止理由 `verification-stop-reason.json`。因此不能将分阶段通过的结果合称为 integration 全绿。
- 最终 `git diff --check`：PASS。
- 早期后端/tooling循环在原目录执行，最终测试文件字节与隔离目录一致；隔离目录的总门禁仅基于本任务测试和原产品基线。
- 集成仅使用任务自建可清空实例，不连接开发库；本任务容器和额外验证进程已清理，最终 Docker 清单仅剩原开发容器。不调用付费模型。

**环境中断与证据位置**：本机于2026-11-05 07:16:53（America/New_York）重启，早期/private/tmp日志和后台验证进程已丢失。上方已完成20轮的数目来自当时实际工具回显，不宣称丢失日志仍可打开。恢复后的证据保存在本工作区忽略目录`.demo/opt-02/`：`stop-original-red.log`重新证明原始Mac用例失败，`stop-final-green.log`证明修后4项通过；`browser-{original,final}.log`保存同基线布局失败；`probe-budget-{red,green}.log`与`k10-probe-import-{red,green}.log`保存两项测试辅助修复；最终循环日志在`repeats/`，完整门禁结果在`verify-full.log`和`verify-integration-relative-python-failure.{log,exit}`。`.demo/opt-02/final-test-sha256.json`记录最终测试版本，收口核对全部一致。所有未完成或主动停止的尝试均未计为通过。

第二次系统重启时间为2026-11-05 20:50:31（America/New_York）。此前 K10 已完整完成19轮，第20轮只输出19个进度点；集成门禁也未结束。中断尝试不计通过：日志分别归档至 `repeats/interrupted-second-reboot/` 与 `verify-integration-interrupted-second-reboot.log`。恢复后核对15个测试/辅助文件的 SHA256 全部未变，补跑 K10 第20轮，并从头重新运行 `./scripts/verify.sh integration`。两只遗留 K10 容器经创建时间、17691/17692端口和停止状态核对后删除，未操作开发容器。

2026-11-09 恢复时，确认 K10 补跑已结束（20 passed，340.70秒），全部12个 Python 测试文件均已完成20轮，共11480个测试通过；但11月5日晚重跑的 integration 门禁又在后端基础检查约15%时被环境中断，没有退出结果。该次日志归档为 `verify-integration-interrupted-nov05-evening.log`，不计通过；重新核对15个文件 SHA256 与4份持久20轮汇总均未变化后，再次完整运行集成门禁。

11月9日第一次完整门禁得到明确退出码1：后端4254、前端1375、真实集成463（4项登记skip）及图库后端44均通过，但 E2E 启动时 `scripts/verify/integration.sh` 将相对 `.venv/bin/python` 传给 E2E，后者在 `cd src/backend` 后执行该路径失败。证据为 `verify-integration-relative-python-failure.{log,exit}`。源码未改；已验证绝对解释器在切换目录后可运行，并显式设置上述 `PYTHON`、`E2E_PYTHON` 发起额外完整重跑。独立个人模式诊断确认下述基线失败后，停止额外诊断与额外门禁重跑，未合并各阶段结果宣称整体通过。

## 未完成与交接

浏览器基线阻塞：同一隔离前端、同一 Chrome、相同只读 API 夹具，原始 ad63341 脚本（保留600ms等待）也在390×844时失败于 `initial.mapTop >= initial.canvasTop`。实际 mapTop=495.671875，canvasTop=516.671875，小地图上缘越出画布21px；1920、1440、1366、1024宽通过。重启后再次对照复现，持久证据为 `.demo/opt-02/browser-original.log`、`browser-final.log`、`browser-comparison.json`。未删/放宽断言、未改产品布局；当前不能把浏览器改动称为20轮通过。初次冷启动修改版还曾在5秒图谱就绪条件处超时，条件等待已恢复正常30秒动作预算；这是布局测试，不以渲染耗时为验收目标。

产品侧定位线索（只读检查）：`src/frontend/src/styles/ui.css:259` 将移动端 `.gw-tool` 高度设为44px；`GraphCanvas.vue` 的控件列有5个按钮、4个6px间距，总高244px，并固定距底16px。原版实测画布高度239px，因此 `244 + 16 - 239 = 21px`，与越界量一致。这是现有布局尺寸冲突的证据，不是继续等待就能满足的就绪条件。后续需产品侧处理390宽布局，再运行浏览器脚本20轮；本任务不调整产品CSS或降低断言。

个人模式 E2E 的另一项基线阻塞：设置绝对解释器后，教师/学生端到端2项通过；个人模式首项在 `personal.spec.ts:27` 的 `setChecked(true)` 等待480000ms后失败。Trace 明确报告 `[data-test=mc-disable-thinking]` 存在但不可见；`ModelSettingsView.vue:84` 将它放在默认折叠的 `<details class="mc-advanced">` 内，旧测试未展开高级选项。`git diff --exit-code ad63341 -- tests/e2e/personal.spec.ts src/frontend/src/views/ModelSettingsView.vue src/frontend/src/components/ModelPicker.vue` 确认三文件均与原基线一致。失败发生在第33行保留的 Retry-After 等待之前，与本任务的等待替换无关。证据：`.demo/opt-02/personal-hidden-option-repro.json`、`e2e-personal-absolute.log` 及 `.e2e/20261109-030901/playwright/` 中的截图/trace。后续另行适配个人模式 E2E 的高级选项操作，本任务不扩大为设置页流程改造。

此前保留可审查的测试改动与失败证据。2026-11-09 本轮收尾状态按用户要求统一为 IN_PROGRESS；浏览器布局缺陷单独登记 OPEN，不在 OPT-02 中修产品。完整 integration 重新执行的结果见下节。若后续修改测试文件，按原要求重新验证相应文件20轮。

回滚仅撤销本分支的测试和本任务文档差异，无迁移或产品配置回滚。


## 2026-11-09 收尾复验（当前结论）

本轮输入为已有未提交改动；开始时分支 `codex/opt-02-test-waits`、HEAD `ad633416e436a23f28172db3bd5a11757fe573e0`。15个测试/辅助文件 SHA256 与 `.demo/opt-02/final-test-sha256.json` 全部相同，已完成的12个Python文件20轮和full不单独重跑。没有修改测试文件或产品代码；integration 自身包含的full阶段照常完整运行。

### 390×844：产品布局缺陷，非测量错误

**实际越界元素是地图/缩放工具组 `.gw-map` 中的 `.gw-map__ctl`，具体是顶部“展开小地图”按钮。** 该宽度下 `.gw-mini` 的 computed `display:none`、bounding box 为零（`GraphCanvas.vue:66` 在宽度小于1024时默认收起缩略图）。因此前序“小地图上缘越界”的描述不够精确，应改称“地图/缩放按钮列上缘越出绘图区”。测试变量 `mapTop` 测的是 `.gw-map` 组，没有测错坐标。

原版与当前版诊断副本均保留原断言，唯一增量是在初始测量后采集 DOM 矩形、computed style、生效的 CSSOM 规则与截图；两次各有1920、1440、1366、1024四个宽视口完成通过，390×844均退出1，失败在 `initial.mapTop >= initial.canvasTop`，数据相同：

| 元素 | top | height | bottom | 说明 |
| --- | ---: | ---: | ---: | --- |
| `.teacher-graph__canvas` | 416.671875 | 340 | 756.671875 | 外层卡片，上下边框各1px |
| `.teacher-graph__canvas-bar` | 417.671875 | 99 | 516.671875 | 换行后的图例/知识点选择栏 |
| `.graph-canvas` | 516.671875 | 239 | 755.671875 | 实际绘图区；无边框、padding、transform |
| `.graph-canvas__stage` 及其原生 `canvas` | 516.671875 | 239 | 755.671875 | 与测试测得的绘图区完全一致 |
| `.gw-map` / `.gw-map__ctl` | 495.671875 | 244 | 739.671875 | computed `top:-21px`（相对定位包含块） |
| 第一个 `.gw-tool` | 495.671875 | 44 | 539.671875 | 上方21px进入知识点选择栏 |

具体 CSS 因果链：

1. `src/frontend/src/styles/ui.css:259`：`@media(max-width:767px)` 下 `.light-surface .teacher-graph__canvas .gw-tool { width:44px; height:44px; min-height:44px; }`；五个按钮实测均44px高。
2. `src/frontend/src/components/GraphCanvas.vue:348`：`.gw-map__ctl { display:grid; gap:6px; }`，实测五行均44px、四个间隔均6px，无额外padding/border；高度 `5×44 + 4×6 = 244px`。
3. `GraphCanvas.vue:330`：`.gw-map { position:absolute; bottom:16px; ... }`，其 offsetParent 是 `.graph-canvas`。于是相对顶部 `239 - 16 - 244 = -21px`。
4. 239px的来源也已核对：`ui.css:501–502` 在390×844命中 `grid-template-rows:auto minmax(340px,1fr) minmax(0,1fr)`，中间卡片实际340px；`ui.css:509` 的上下边框共2px，`ui.css:552,558–561` 的可换行栏实际占99px，`ui.css:461` 让 `.graph-canvas` 填剩余空间，故 `340 - 2 - 99 = 239px`。

测量排除项：页面只有1个 `.graph-canvas` 与1个 `.gw-map`；两矩形均用同一页 `getBoundingClientRect()`，scrollX/scrollY均0、devicePixelRatio为1；stage和原生canvas与容器一致，非选择器误命中、边框误差、滚动坐标混用或ResizeObserver尚未完成。`document.elementsFromPoint(331,498.671875)` 最上层是“展开小地图”按钮，下方是知识点 `select`，截图可见按钮覆盖下拉框右下部分；实际存在产品控件重叠。没有注入修正CSS，也没有删改/放宽断言。

诊断运行命令（先在目标工作区启动本地Vite）：

```bash
npm --prefix src/frontend run dev -- --host 127.0.0.1 --port 5182 --strictPort
# 以下分别实际执行，DIAG_PREFIX及脚本版本分别取 current / original。
E2E_BASE_URL=http://127.0.0.1:5182 \
  PLAYWRIGHT_MODULE="$PWD/node_modules/playwright" \
  PLAYWRIGHT_CHROMIUM_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  DIAG_PREFIX=/private/tmp/smartsketch-opt02-closeout/layout-current \
  node /private/tmp/smartsketch-opt02-closeout/browser-current-diagnostic.cjs
E2E_BASE_URL=http://127.0.0.1:5182 \
  PLAYWRIGHT_MODULE="$PWD/node_modules/playwright" \
  PLAYWRIGHT_CHROMIUM_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  DIAG_PREFIX=/private/tmp/smartsketch-opt02-closeout/layout-original \
  node /private/tmp/smartsketch-opt02-closeout/browser-original-diagnostic.cjs
E2E_BASE_URL=http://127.0.0.1:5182 \
  PLAYWRIGHT_MODULE="$PWD/node_modules/playwright" \
  PLAYWRIGHT_CHROMIUM_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  node tests/frontend/teacher-viewport.browser.cjs
```

两个诊断副本、观测函数、各宽度JSON、390截图及退出码已复制至工作区忽略目录 `.demo/opt-02/closeout-layout/`，关键证据为 `layout-{current,original}-390.json/.png`、`browser-{current,original}.log/.exit`。仓库原样脚本的独立复验同样为4个宽视口通过、390×844在同一断言失败，exit 1；见 `.demo/opt-02/browser-closeout.log/.exit`。**浏览器20轮验收：未通过/受阻；首轮失败，未继续重复20轮，也不将四个宽视口通过等同于整个脚本通过。** 产品缺陷另记 `docs/tasks.md` 的 `UI-TEACHER-CONTROLS-01`，状态OPEN，等待用户决定是否另行修复。

### 完整 integration 运行与用户取消结果

本轮从头实际运行以下命令；显式指定绝对Python路径，清除已有实例URI，让门禁和E2E各自启动并清理一次性Neo4j，不连接开发库，不改脚本、不跳过E2E、不缩短超时：

```bash
env -u VERIFY_NEO4J_URI -u E2E_NEO4J_URI \
  PATH="$PWD/.venv/bin:$PATH" \
  PYTHON="$PWD/.venv/bin/python" E2E_PYTHON="$PWD/.venv/bin/python" \
  VERIFY_NEO4J_PORT=17689 E2E_NEO4J_PORT=17687 \
  E2E_API_PORT=18002 E2E_WEB_PORT=15175 E2E_PROVIDER_PORT=18902 \
  PLAYWRIGHT_CHROMIUM_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  ./scripts/verify.sh integration > .demo/opt-02/verify-integration-closeout.log 2>&1
rc=$?
printf '%s\n' "$rc" > .demo/opt-02/verify-integration-closeout.exit
```

<!-- closeout-integration-result -->
11月9日的上方命令再次中断：日志最后写入时间为2026-11-09 03:49:34（America/New_York），后端4254 passed/27登记skip、740.41秒，前端未产出最终汇总；没有最终退出码，不计完整通过。11月10日恢复时旧进程已不存在，Docker未运行；系统最近启动时间为2026-11-10 07:03:35（America/New_York）。不能仅凭这些时间确定11月9日进程停止的具体原因。原日志 `.demo/opt-02/verify-integration-closeout.log` 原样保留。

11月10日已执行 `open -a Docker`（exit 0），确认Docker 29.8.0就绪，现有容器仅开发库。08:25:08（America/New_York）从头启动同一完整命令；参数不变，日志存于 `.demo/opt-02/verify-integration-closeout-20261110.log`，总退出码原计划写入同名`.exit`（后因取消未生成）。实际命令保存在同名`.sh`，启动时间与PID在同名`.json`；运行进程与聊天连接分离。15个测试/辅助文件的SHA256再次全部一致，没有重跑已完成的逐文件20轮。

11月10日完整命令已输出的实际测试结果（总脚本后来按用户要求终止，不合称全绿）：

| 阶段 | 通过 | 失败 | 跳过 | 本次结果 |
| --- | ---: | ---: | ---: | --- |
| 后端与tooling | 4254 | 0 | 27 | PASS，773.36秒；跳过均登记为未配置独立Neo4j |
| 前端 | 1375（82文件） | 0 | 0 | PASS；类型检查、构建通过 |
| 真实Neo4j集成 | 463 | 0 | 4 | PASS，584.56秒；跳过均为门禁固定禁用的Docker重型用例 |
| 依赖图库的后端补验 | 44 | 0 | 0 | PASS，20.53秒 |
| 教师/学生E2E | 2 | 0 | 0 | PASS，43.9秒；`.e2e/20261110-085420/` |
| 个人模式E2E | 0 | 4 | 0 | FAIL，E2E脚本exit 1；四项分别在480/300/240/480秒原定时限超时；`.e2e/20261110-085542/` |

契约、仓库骨架、启动器unit/vet门禁通过。用户随后明确要求“取消剩余测试，汇报结果”，已对经进程树核对的本次验证进程组发送SIGTERM，停止后没有再启动测试。**总门禁没有写出最终退出码，也没有最终 `Verification (integration)` 汇总：状态为用户取消，不得虚构总exit 1或称为完整自然结束。** 个人模式E2E子脚本则明确输出 `exit 1`。

停止后核对日志，最后一项已记录原定480秒超时；最终Playwright日志是 **4 failed、0 passed、0 skipped、0 interrupted**，不是3 failed + 1 interrupted。四份trace均确认 `locator.setChecked` 在 `[data-test=mc-disable-thinking]` 等待可见时超时（`personal.spec.ts:27`），与基线默认折叠的高级选项不匹配；没有放宽断言或修个人模式流程。提取的错误证据在 `.demo/opt-02/personal-closeout-failures.json`，取消事实与总退出码缺失在 `.demo/opt-02/verify-integration-closeout-20261110-cancelled.json`，完整原始日志原样保留。

停止后Docker仅剩原开发容器 `smartsketch-main-neo4j-1`，本次一次性验证/E2E容器已清理。所有15个测试/辅助文件与前序20轮验证的SHA256一致；本轮新增修改只有 `docs/tasks.md` 和本交接，产品代码未变。待用户决定是否另行修复 `UI-TEACHER-CONTROLS-01` 以及个人模式E2E的高级选项操作，然后再安排尚未通过的浏览器20轮及完整门禁。
<!-- /closeout-integration-result -->


### 最终差异检查与提交范围

- `git diff --check`：exit 0。
- `git diff --exit-code ad63341 -- src scripts specs .claude AGENTS.md`：exit 0，产品、脚本、规格与规则没有改动。
- SHA256核对：15个测试/辅助文件与已有20轮验证版本全部一致；本次收尾没有改写这些文件。
- 最终交付范围：15个测试/辅助文件与 `docs/tasks.md`、`docs/handoffs/codex-opt-02.md`，共17个文件；任务看板其余内容逐字保持与基线一致。
- 按原授权提交到 `codex/opt-02-test-waits`，提交消息末尾包含 `Co-Authored-By: Codex <noreply@openai.com>`；不推送、不开PR。OPT-02保持IN_PROGRESS，布局缺陷保持OPEN。
