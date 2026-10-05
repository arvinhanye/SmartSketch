# Codex：Mac下载Killed:9接续（2026-10-05）

## 状态与根因

STARTUP-14 OPEN：诊断提示已修，下载信任尚待用户条件/确认。当前工作区/Users/arvinhan/.codex/worktrees/plan-c-acceptance-review/SmartSketch，分支codex/cross-platform-startup-design；不要动旧e92f、Claude或只读测量区。用户实际GitHub下载Intel包启动PID44020被终止。只读核对SHA9116108b62d5028da07cc63ff96a86b4b5773cb144eef6a3fd829586d330868f完全一致；Mach-O x86_64/0755/unsigned/com.apple.quarantine。codesign verify1、spctl assess3/no usable signature；08:19:38.744 syspolicyd明确Gatekeeper rejection44020，kernel同PID路径拒绝。不是Docker或API故障。

本地同字节无隔离产物env-i --version exit0，说明先前本地验证不覆盖网上下载。只统计本机可用Developer ID Application身份数0，未读取密钥；已向用户询问是否有开发者账号/证书，等待回复。

## 改动与实际验证

- packaging/start-macos.command：新增137/系统终止说明、保留状态码，提示可能安全检查/内存，核对来源/SHA并由用户自己审阅系统单程序确认；未签名风险、恶意提示停止使用、不关闭保护/不删隔离。其他错误通用处理，成功无提示。
- tests/tooling/test_startup_package.py：保留原4例，新3例覆盖137、0、2和无绕过命令。先观察2 failed/1 passed，修复后打包7 PASS，打包+发行13 PASS。模拟退出只验证包装，不证明Gatekeeper通过。
- 指南及批准spec补下载信任门禁；系统日志和明确签收范围见docs/reviews/codex-mac-download-gatekeeper-20261005.{md,json}。
- 无.env隔离副本verify.sh basic session50362正在运行；日志/private/tmp/smartsketch-delivery-20261005/logs/mac-gatekeeper-basic.log。接续先读实际退出，不重跑进行中的门禁。

用户Downloads文件、所有Release附件、GHCR镜像、系统设置、API配置、业务库未修改；账本844451/900000、向量12005不变。没有新署名、公证、包重编/重发、push/merge或冻结，提示源代码也未进入已有下载附件。无需用户数据回滚；恢复包装源文件应只针对本轮提交，不回退他人变更。

## 下一步（不可跳过）

1. 读用户是否具备Apple Developer/Developer ID签名条件的答复；不要从“修复”推断可以代为导入私钥、变更系统安全策略或发布。完整分发需要正确签名/公证及真实下载验收；ad-hoc不是Apple信任证据。
2. 用户若自愿信任当前已核对SHA预览包，由用户本人在系统设置→隐私与安全性审阅针对smartsketch-launcher的“仍要打开”并确认，然后重开原入口；若无提示请用户提供截图，若恶意提示则停止使用。不要运行xattr清隔离、spctl关闭或自动添加信任例外。官方Apple说明https://support.apple.com/guide/mac-help/mh40617/mac 。
3. 用户完成系统动作后才核验向导是否打开，不发真实模型/向量请求，不能以TDD提示通过称实际启动已修复。
4. 等签名条件确认后另行规划发行签名/公证、相应CI/门禁与新包；替换Release附件需明确授权，Tag源码对齐阻断仍在。

stage_c_status OPEN；technical_freeze NOT_PERFORMED；STARTUP-12自动重复用例/停止UI与平台缺口保留。

## 用户最新答复与最后检查点

用户已答复“没有，先继续测试预览版”；不再重复询问账号。由用户本人到系统设置审阅单程序确认，尚未收到操作结果，不能宣称Gatekeeper已放行。basic50362仍在负向契约阶段，B14已通过；不得记作整门禁PASS，下一轮先读该进程/日志。定向13 PASS、原测试保留、diff-check通过，提交仅诊断修复检查点，签名和真正下载启动OPEN。
