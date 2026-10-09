# Mac下载启动器Killed:9调查与诊断修复

## 结论与范围

针对用户2026-10-05 Downloads中preview-20261005-e88b56a Intel包，PID44020，根因已由本机系统日志确认是Gatekeeper拒绝，不是API/Docker配置。SHA256=9116108b62d5028da07cc63ff96a86b4b5773cb144eef6a3fd829586d330868f，与交付二进制一致；文件为Mach-O x86_64、0755、有com.apple.quarantine但未签名。codesign verify exit1；spctl assess exit3，source=no usable signature。没有修改该下载文件或任何隔离属性。

08:19:38.744 syspolicyd记录Terminating process due to Gatekeeper rejection:44020，同时间kernel记录Security policy would not allow process:44020，路径即用户指出的启动器。仅筛选该程序/PID日志，没有采集凭据、业务库或课程内容。

同一SHA的本地构建产物--version在env-i HOME=/private/tmp中exit0，输出preview版本；这只是对照，不代表下载验收。此前未带下载隔离的本地观察不能作为网络下载通过的证据。本机可用Developer ID Application签名身份数0，未读取私钥。已询问用户签名条件。

## 改动与验证

packaging/start-macos.command仅补137诊断：保留退出码，提示可能的macOS安全检查或内存原因，核对来源/SHA后由用户自行审阅系统单程序确认；明确未签名风险、恶意程序停止使用、不要关闭保护或删除隔离。其他非零错误继续通用处理且保留代码；成功不显示错误。没有把所有137都判定为Gatekeeper。

测试先写：新3例中2 RED/1 PASS；修复后打包全7 PASS；打包+发行完整定向13 PASS。原4打包及6发行用例保留，不删不放宽。新用例模拟退出状态只证明包装逻辑，不冒充真实Apple信任修复。verify.sh basic正在无.env副本执行，结果待记录。

## 仍OPEN

真正网络分发需Developer ID签名/Apple公证及从GitHub下载后的实测；临时ad-hoc签名不代替Apple信任。用户若自愿信任，可由本人在系统设置→隐私与安全性审阅smartsketch-launcher的“仍要打开”；我未代点系统确认、未关闭保护、未删quarantine、未改Release附件或用户下载包。

参考Apple：https://support.apple.com/guide/mac-help/mh40617/mac ；签名/公证：https://developer.apple.com/documentation/security/resolving-common-notarization-issues 。程序未由Apple验证、单独信任有风险；系统明确提示恶意程序时停止使用；无对应系统提示则补截图，不猜或绕过。

未重编/重发镜像或安装包；新的诊断源文件尚未进入旧附件。不把本地提示修复报告为下载启动已修复。STARTUP-14/STARTUP-12/stage_c_status OPEN；technical_freeze NOT_PERFORMED；账本不变。
