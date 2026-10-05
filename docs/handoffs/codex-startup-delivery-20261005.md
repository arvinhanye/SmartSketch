# Codex 实际启动包交付接续（2026-10-05）

## 先读与最后确认状态

自己的工作区 /Users/arvinhan/.codex/worktrees/plan-c-acceptance-review/SmartSketch（不要改旧e92f）；HEAD代码9e8b4a1，之前8314092；未推送合并。先读AGENTS.md、docs/tasks.md、docs/reviews/codex-startup-delivery-20261005.md、docs/reviews/startup-delivery-verification.json，以及既有批准spec/plan与其ledger。

用户明确批准上传GHCR后端/前端并公开、本地安装包。GitHub设备认证write:packages已完成。两份linux amd64/arm64正式Dockerfile镜像已上传，实际摘要存 packaging/release-manifest.preview-20261005.json；但两包仍PRIVATE。UI提交Public设置被自动审批拦截，已发临近确认问题；**等待这个新问题的用户肯定答复，再提交对应Public设置。不得通过API/其他工具绕过拒绝。** 此授权不含源码push、合并、GitHub Release或技术冻结。

当前完整门禁后台 session36170：第一次默认浏览器不存在导致2+4E2EFAIL，其他计数见报告；第二次env-i指定已安装Chrome的 ./scripts/verify.sh integration最后核对仍运行。只检查该session或 /private/tmp/smartsketch-delivery-20261005/logs/integration-browser-retry.log，不重跑直到确认原进程结束。新Node4项和tooling10项通过。

## 真实包/未完成项

三包保存在本工作区 dist/startup-preview-20261005，SHA3 OK，真实镜像清单/版本一致。二进制来自e88b56a47645ef757948a73dfac6a7a522f7f7c8（运行源码7fee1c8），Dockerfile8314092只增加120s pip socket timeout，依赖不改。包装工具的README已按预览包更新。

/private/tmp/smartsketch-delivery-20261005/private-package-check-2：真实入口→向导→错误口令拒绝通过，private pull401失败，0本安装运行残留，非登录PASS。不要把这个输入为fixture的安装给用户使用。其.env是新生成fixture，用户真实.env/业务库从未读取或复制。第一次private-package-check是在输入来源元数据格式校验处失败，无进程/服务启动。

临时注册表配置 /private/tmp/smartsketch-delivery-20261005/registry-auth 只用于获准发布，Docker实际选择osxkeychain帮助程序。隔离HOME读取帮助程序找不到凭据，不能宣称私有配置文件足以使普通用户拉取。不要把此目录/token放进包或门禁，后续公开匿名拉取使用新的空Docker配置目录、本机context/插件的非敏感配置。不再需要真实认证token。

验收脚本tests/startup/packaged_entry.cjs需要实际bundle、新/private/tmp输出、预期binary/archive SHA、实际40位源码commit、PLAYWRIGHT_MODULE路径；PACKAGED_DOCKER_CONFIG可选。同上下文env运行Docker，失败只写独占输出，取消进程组后标签核对仅stop自身容器、不删卷；4项helper回归文件test_packaged_checks.cjs。结果仅entry-process-plus-connected-browser；系统浏览器和打开软件按钮需CUA真实观察，Finder/ARM/Win未测。不得用直接goto冒充全部交接通过。

## 下一步

1. 收用户临近Public确认，在Chrome既有package设置tab完成frontend，再backend（同用户已批两包，先观察实际页面）；确认Public并以空认证配置匿名拉取真实digest，记录退出/摘要，不清旧缓存或用户镜像。
2. 用官方包解压到中文空格路径、全新fixture HOME，真实entry/browser完成安装、教师登录、二次入口、停止/重启。当前Mac是x86_64；别称ARM/Win实机通过。严格不收费请求，不操作共享Neo4j/课程库。
3. 如有失败，定位该新fixture stage；不放宽断言/改fake adapter。补系统浏览器打开与向导按钮交接的单独观察。保留失败原始记录。
4. 完整门禁实际结果写回report/JSON/tasks，minor输出canary扫描单列deferred；独立整支review历史仍未clean。自己的handoff更新，不代写Claude文件。
5. 最终给用户工作区dist中的实际Mac包绝对链接与操作步骤，不让旧scripts/start.sh替代新入口。不自动替用户配置真实API、签收或冻结。

## 边界与清理

stage_c_status OPEN；technical_freeze NOT_PERFORMED；生成844451/900000、向量12005不变。不得读真实.env、迁移旧数据、改测量证据、prune/down-v或停止其他项目。临时SDK /private/tmp/smartsketch-go1268、源码/日志 /private/tmp/smartsketch-delivery-20261005；打包sha存JSON。原始日志只私有保存，发布证据摘要不含凭据。由于发行/平台OPEN，保留ledger和分支，不删除计划目录。

额外文档快照basic门禁后台session98359，日志/private/tmp/smartsketch-delivery-20261005/logs/docs-basic.log；最后核对未退出。该副本 /private/tmp/smartsketch-delivery-doccheck 无.env，包含本轮文档与清单。原先RUNNING记录不是PASS；接续读取实际退出，不重跑已在进行的门禁。Chrome公开设置恢复后的tab786447081已markHandoff；仍未提交Public。
