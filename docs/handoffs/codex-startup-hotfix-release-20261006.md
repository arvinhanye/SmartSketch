# Codex 启动器热修复交接（2026-10-06）

## 已实现并验证的源码检查点

本工作区 /Users/arvinhan/.codex/worktrees/plan-c-acceptance-review/SmartSketch；用户批准修复并提交新草稿。复用已定位STARTUP-15，不动用户实例。

- Configure保存规范化用户名，Start允许旧大小写状态的等价输入并规范化状态，Bootstrap仅接受后端规范身份、不同账号仍拒绝。旧migrated中断不重跑迁移、不重置账号密码/InstallID/根密钥；下游失败保持教师checkpoint。
- dockerChildEnv将定位的Docker绝对目录加入子进程PATH，保留原路径及环境白名单，不改凭据配置。已有SIGKILL入口提示随新包分发，未处理系统信任。
- 新回归先5顶层FAIL/1 PASS，再全量Go PASS；最终race/vet PASS。定向Python20 PASS。断网合成后端复现及真实Docker恢复1 PASS：同一UserID、原密码可登录、另一个密码401，原配置不变。临时安装自动清理，不触及用户a678a6028b4ace39。
- 无.env隔离源码快照 /private/tmp/smartsketch-startup-fix-20261006/source；basic exit0，full执行中。日志在同临时根logs；源码检查点不是完整门禁/发行完成。

## 发行策略和边界

只替换启动器/入口，继续原前后端/Neo4j摘要及Compose；运行兼容标识沿用preview-20261005-e88b56a，避免旧未完成安装触发业务数据升级。新热修草稿独立日期/源码commit及SHA，不覆盖原草稿，不误称旧标识hash为新源码。

用户授权本轮修复、新草稿及源码提交；仅推自己的codex分支，不合并main、不公开发布、不执行技术冻结或真实模型/向量。用户关闭旧终端后从新包双击、复用旧用户名/首次密码，不删配置/卷。Mac仍未签名公证，ARM/Windows未实机，完整用户Finder启动仍待人工。

## 下一步

先读full实际退出，必要时修门禁环境但不放宽断言；编译三平台启动器、验证真实档案和SHA，上传新draft、核对远端源码与附件。旧诊断丢阶段P3尚未修，必须保留OPEN，不直接公开stderr。
