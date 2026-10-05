# Codex 交接：跨平台双击启动设计

- 日期：2026-10-04；任务STARTUP-01
- 状态：AWAITING_SPEC_APPROVAL；本轮仅设计，无启动器代码
- 工作区：/Users/arvinhan/.codex/worktrees/plan-c-acceptance-review/SmartSketch
- 分支：codex/cross-platform-startup-design；基线bdb89c46

## 交付

- docs/superpowers/specs/2026-10-04-cross-platform-startup-design.md：完整待审核规格。
- docs/tasks.md：认领/输入输出/风险/验收/审批边界。
- docs/decisions.md：用户确认的方向，不把详细规格写成已批准。
- docs/integrations.md：环境配置、Docker发行依赖与平台边界（明确未实现）。

## 已运行检查与实际结果

- 只读核对AGENTS、tasks、identity-access、architecture、handoff规则、Compose、Dockerfile、manage-accounts、startup/graph_migrations、.env.example；未读取真实.env。
- git status --short：开始时为空；HEAD bdb89c46；在同一干净Codex工作区创建本地codex/cross-platform-startup-design分支，没有改Claude或测量工作区。
- 首次PATH只含.venv和系统目录：./scripts/verify.sh exit 1，缺datamodel-codegen，B14 2 failed/1 passed与契约负向检查失败；日志/private/tmp/smartsketch-startup-design-basic.log。command -v核实生成器实际在/usr/local/bin，无代码变更。重跑 PATH="$PWD/.venv/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin" PYTHONDONTWRITEBYTECODE=1 ./scripts/verify.sh：默认basic，exit 0；日志/private/tmp/smartsketch-startup-design-basic-retry.log。没有执行full/integration，没有启动Docker或付费模型请求。
- git diff --check：exit 0。文档自审检查状态/恢复/权限/费用/未验证与审批一致；未新增产品代码、契约、迁移、依赖或环境文件。
- 阅读过程中一次rg使用了不存在的src/contracts/v1/openapi.yaml；已改为现有auth API/身份规格核验，契约真源实际为src/contracts/api.v1.yaml，不据失败路径推断注册功能缺失。

## 关键决定与实现影响（尚未实施）

1. 用户不安装宿主Python/Node；Docker为唯一运行依赖。共用小型Go启动核心附发行二进制，OS包装只定位/启动；该技术细节需要规格审批，不是已新增的运行依赖。
2. 浏览器向导独立于业务API，本机监听、认证/Origin/Host门禁，不挂Docker socket进容器、不拼shell、不采集明文诊断。
3. 向导只首次生成环境配置，不恢复撤销的向量业务设置页；个人生成设置复用现有API。
4. 新独立实例、稳定项目名/卷；开发/测量数据不自动迁移。首次教师复用既有账号服务，密码stdin，学生注册复用现有接口。
5. 固定版本镜像发行与各平台双击/失败/恢复实测是独立验收条件；缺资源不计PASS。

## 未完成与下一步

首个动作：请用户审核正式规格，尤其确认共用启动核心、首次安装独立新库、支持平台与发行边界。获批后才能写实施计划；实施计划仍需用户审核及选择执行方式。本轮没有可双击启动的新入口。

发行镜像权限、Go构建工具链、Windows和Mac Intel实机条件尚未落实；真实供应商连接、用户本机功能检查、第三阶段冻结都未在本轮验证。

stage_c_status OPEN；technical_freeze NOT_PERFORMED；生成调用0、在线向量0。原测量与历史预算证据保持原样，不将本轮文档门禁计为第三阶段验收。

## 回滚与保护

本轮仅本地文档提交，不推送合并；如撤销方案，保留已集成代码与.env/数据，仅在本分支回退自己的设计文档提交或补取消记录。没有数据库/依赖变化需要回滚；不要恢复旧main、重置其他工作区或删除测量证据。
