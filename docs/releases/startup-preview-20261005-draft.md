# 智绘学途本机安装预览：下载测试草稿

**仅草稿，未公开发布、非稳定版、未技术冻结。**

在Assets下载安装包，而不是Source code：Intel Mac选darwin-amd64；Apple Silicon选darwin-arm64；Windows 11 x64选windows-amd64。先打开Docker Desktop，完整解压，双击包内入口；详细步骤见START-HERE.md。安装包不含真实API密钥、口令、业务库或课程文件。首次向导会创建独立新安装，不导入旧课程。

## 已有证据与已知问题
- 前后端GHCR镜像已Public；空认证/无密钥助手拉取固定摘要成功（warm cache，不代表冷下载速度）。
- 隔离integration：backend+tooling3949 passed/27登记skip，frontend934 passed，integration393 passed/4登记skip，backend-live44 passed，演示E2E2和个人假供应商E2E4 passed。
- Mac Intel实际包首次就绪及教师登录、另一次系统Chrome入口/打开软件/同一教师登录与重开已观察；不是Finder双击验收。
- 自动重复入口验收尚有失败，停止按钮确认框UI完成未签收；平台签名、下载后的Gatekeeper、Mac ARM/Windows实机未验。

## 构建出处与发布阻断项
- 安装包版本：preview-20261005-e88b56a。
- 启动器构建源码：e88b56a47645ef757948a73dfac6a7a522f7f7c8（运行实现7fee1c88f870cee1af4a17bee9536bf244baf80c）。
- 镜像构建变更：83140929b0881d2112b5ce0cec9b9022d9145555，只增加固定依赖下载socket超时。真实镜像摘要见release-manifest.json；附件校验见SHA256SUMS。
- **这些构建源码尚未推送；草稿目标暂为GitHub现有main的已核对提交，不代表附件构建源码。发布前须获得源码同步许可并对齐正确的Tag/源码目标。不要直接发布本草稿。**
- 本轮仅上传下载测试附件，不推源码、不合并main、不创建公开正式版本。stage_c_status=OPEN；technical_freeze=NOT_PERFORMED。
