# E2E-PERSONAL-01：个人模式高级选项操作

- 状态：DONE；负责人：Codex；日期：2026-11-10。
- 分支：`codex/opt-02-test-waits`；基线：`51ef5cb`；工作区：`/Users/arvinhan/.codex/worktrees/opt-02-test-waits/SmartSketch-main`。
- 用户授权：先确认可行的修复方案再实施；本次聚焦个人模式E2E隐藏控件，原OPT-02窄屏产品布局缺陷继续OPEN。

## 根因与已验证方案

四个个人模式用例都在共享`configureModel()`的`setChecked()`上超时。真实trace指出`mc-disable-thinking`存在但不可见；`ModelSettingsView.vue:84`的原生`details.mc-advanced`默认收起。

修改前先在真实Vite页面运行`/private/tmp/smartsketch-personal-fix-proof.cjs`（仅API使用本地夹具，无外部调用）：教师与学生两角色都先复现旧步骤失败，再验证正常点击summary后可设true/false、重复调用不会收起、刷新后可重新展开。诊断退出0（两次预期RED、两组GREEN）；旧步骤1秒诊断上限仅用于快速复现，仓库E2E总超时没有调整。

可行方案：把“仅收起时展开→确认开关可见”封装为测试辅助函数，限定到`[data-test=mc-form]`，在设置开关和刷新后核验时复用。保留原连接测试、保存响应与保存值断言；不改产品UI，不用force，不直接设置DOM的open/checked属性。

## 变更与验证

- 仅修改`tests/e2e/personal.spec.ts`以及本任务文档；OPT-02交接只补续修结果与状态引用；API、数据、配置与依赖无变化。
- 方案诊断与记录保存在忽略目录`.demo/opt-02/personal-fix/`。
- 真实个人模式4项E2E：**4 passed，0 failed/skip，exit 0，约1.7分钟**。四项覆盖教师PDF+MD闭环、处理中取消并重新上传、供应商拒绝密钥、两门课权限与数据隔离；教师和学生共用设置辅助，保存后刷新断言保留并通过。
- 原始日志与退出码：`.demo/opt-02/personal-fix/e2e.{log,exit}`；真实运行目录：`.e2e/20261110-095515/`。测试自建一次性Neo4j与本机fake provider，不访问付费模型或开发库；脚本已清理临时服务。
- 实际命令：

```bash
E2E_BASE_URL=http://127.0.0.1:5182 \
  PLAYWRIGHT_MODULE="$PWD/node_modules/playwright" \
  PLAYWRIGHT_CHROMIUM_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  node /private/tmp/smartsketch-personal-fix-proof.cjs

env -u E2E_NEO4J_URI PATH="$PWD/.venv/bin:$PATH" \
  E2E_PYTHON="$PWD/.venv/bin/python" E2E_LLM_MODE=personal \
  E2E_NEO4J_PORT=17687 E2E_API_PORT=18002 E2E_WEB_PORT=15175 E2E_PROVIDER_PORT=18902 \
  PLAYWRIGHT_CHROMIUM_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  scripts/e2e.sh tests/e2e/personal.spec.ts --max-failures=1

PATH="$PWD/.venv/bin:$PATH" ./scripts/verify.sh
git diff --check
```

- 基础门禁：**exit 0**，契约与仓库骨架检查通过，日志与退出码在`.demo/opt-02/personal-fix/verify-basic.{log,exit}`；`git diff --check`通过。原15个测试/辅助文件SHA256全部未变。本轮没有重跑此前的Python20轮或整条integration。

## 风险与后续

真实个人模式4项已完整通过，隐藏控件阻塞关闭；不能把这次独立E2E通过拼接成前次被取消的完整integration通过。窄屏21px产品缺陷未修改，OPT-02整体继续IN_PROGRESS。

回滚只撤销本次测试及对应任务文档差异，无迁移。

按既有授权提交本分支，消息末尾含Co-Authored-By；不推送、不开PR。
