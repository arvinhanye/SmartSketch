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

## 公开接续检查点（优先于上文旧状态）

2026-10-05用户临近确认Public后，GitHub UI已完成frontend/backend公开并观察“currently public”，截图保存在logs/ghcr-{frontend,backend}-public.jpg。空认证且无助手的anonymous-docker配置拉取两固定digest exit0（warm cache）；context最初自动选择osxkeychain，第一次拉取不计匿名证据，第二次明确空auth后通过。不修改用户原配置。

后台36170 integration与98359 docs-basic实际已exit0，计数见JSON；不重跑。真实公开Mac包验收62895正在运行（当前teacher checkpoint），log logs/public-package-check.log，fixture public-package-check、安装ID d3e4bfc14a9401d2；读实际结果，不冒充PASS。系统Chrome确实打开向导tab786447084，但脚本交换另一能力后该原页面会话被替换，所以不能拿它宣布系统全交接通过。测试完成后需仅用实际entry重开该fixture，再在系统Chrome观察，不与headless交换能力竞争；不动用户真实安装。Finder/ARM/Win仍OPEN。

## Public完成后的实际验收检查点（2026-10-05）

两包已Public，匿名固定摘要拉取exit0（warm cache）；截图logs/ghcr-{frontend,backend}-public-full.jpg含完整公开设置。文档basic43928实际exit0，无新业务代码变更。

真实包自动验收62895整体exit1：首次入口、真实向导、错误口令拒绝、固定镜像/迁移/索引/服务就绪、首次教师登录均已到达；失败在teacher-browser-login标记之后、repeat阶段完成标记之前。证据public-package-check/acceptance.json保存，不能将“failed_stage=teacher-browser-login”误解为首次登录失败，也不猜根因。0本安装运行残留、卷保留。自动重复验收尚待诊断，不改断言或凭据。

另按自然系统浏览器流程重新启动同一fixture：入口39778实际打开Chrome向导786447090→READY→点击“打开软件”打开49376登录页786447093→使用同一合成教师进入/teacher；再次入口exit0，786447096观察既有服务/同端口。此过程没有私有能力绕行，证据public-os-handoff.json与logs/public-os-{teacher-login,wizard-ready,repeat-ready}.jpg。仅证明当前Mac Intel实际入口进程/系统浏览器/按钮/登录与重开，仍不证明Finder双击或其他平台。

停止按钮弹出浏览器confirm后CDP操作超时，确认提交未测；不得称按钮停止通过。未使用别的UI技术绕过；已按项目/安装双标签核对并仅docker stop本fixture d3e4bfc14a9401d2，0运行残留、保留卷。再核对完整二进制路径与父入口，仅SIGINT该controller，39778 exit0。浏览器若仍显示这个测试停止确认框，交用户手动关闭；不要操作其他账号/页面或重新发起确认。

总体STARTUP-12仍OPEN：自动重复用例定位、停止确认UI、Finder/Gatekeeper、Mac ARM/Win实机待补；完整分支复审仍部分中断，canary输出扫描Minor仍deferred。stage_c_status OPEN、technical_freeze NOT_PERFORMED；账本844451/900000、向量12005不变。没有源码push/merge/Release。

## Release草稿接续

2026-10-05用户另批仅Release草稿；STARTUP-13已交付，URL/六附件/服务端SHA/认证小文件回下载与源码绑定阻断见docs/handoffs/codex-startup-release-draft-20261005.md。仍不公开发布、不推源码、无Tag ref、无技术冻结。大包完整回下载未完成，不混写PASS。

## 下载启动故障（优先的新事实）

用户实际GitHub下载Intel包Killed:9，PID44020；SHA一致，unsigned+quarantine，syspolicyd明确Gatekeeper拒绝。先前本地无隔离测试仍有效但不代表网络发行。诊断回归已补，实际下载信任仍OPEN，不重发包或删隔离。接续读docs/handoffs/codex-mac-download-gatekeeper-20261005.md及review；等待用户签名条件/本人系统单程序确认。
