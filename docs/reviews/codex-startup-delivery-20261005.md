# 实际启动包交付进度（2026-10-05，尚未完成用户可用签收）

## 范围与结论

工作区 /Users/arvinhan/.codex/worktrees/plan-c-acceptance-review/SmartSketch；分支 codex/cross-platform-startup-design。接续“双击→配置→启动→登录”；不修改旧e92f、Claude或测量区，不读取个人.env，不复制业务库，不发收费生成/在线向量请求。stage_c_status OPEN，technical_freeze NOT_PERFORMED。

官方 Dockerfile 从干净跟踪源码构建 linux/amd64 + linux/arm64，通过并上传两份 GHCR 镜像。运行代码 e88b56a；构建唯一变更8314092为 pip120s socket超时，原固定依赖/TLS不变。真实索引后端fa9cff4449a32f9245a0bd1c658dcb92f83030aeb41318f4c7e596ab321ae784、前端126ada210c9a275316f5de33bd8c5f7feb86a26033a36c1403643e77315053a9，Neo4j真实多架构摘要见发行清单。此版名称preview-20261005-e88b56a不是技术冻结。

**公开分发已核验，完整交付仍OPEN**：用户临近确认后在GitHub UI逐个设为Public；明确空认证、无密钥助手的临时Docker配置拉取两份固定摘要exit0，使用warm cache，不计冷下载速度。初次临时context自动选择osxkeychain导致首次下载不计匿名证据，纠正后重验通过。三份包SHA不变；实际公开包至登录尚在运行，不以包存在或镜像公开宣称完整闭环。

## 真实包预检

解压至 /private/tmp/smartsketch-delivery-20261005/中文 空格解压，启动实际Mac Intel入口（未替换Runner或镜像），真实向导及不一致口令拒绝无配置写入已观察。随后Private镜像拉取unauthorized，未到Neo4j/建号/登录。仅本轮fixture安装114e1267fc3ab21a，失败清理确认0运行容器，卷不删。原始证据private-package-check-2/acceptance.json与对应日志保留。

第一次输入校验失败发生在进程启动前，原因是手工录入的源码元数据格式不正确；重跑从git rev-parse获取真实完整提交号。该次不算启动验收。隔离HOME下Docker凭据帮助程序找不到注册表凭据；未向隔离安装.env拷贝真实Key，未通过本地标签/免拉取adapter绕过Private失败。

验收脚本主动声明entry-process-plus-connected-browser；通过私有能力连接浏览器，不自动证明系统初始浏览器/“打开软件”交接或Finder双击。这些需额外真实观察，尚未测。当前Mac实测尚未到登录；ARM/Win跨编译、多架构构建不是实机通过。

## 审查与处理

独立只读复审e88b56a..8314092：0 Critical，4 Important，1 Minor。重要项9e8b4a1处理：失败输出限定独占创建的canonical私有目录、wx拒绝既有/符号链接证据文件；忙态取消进程组后校验两组标签，仅停本安装容器并记录残留；记录二进制及归档SHA和真实源码身份；绕过浏览器交接的验收口径缩小并显式UNVERIFIED。4项新helper回归RED缺接口→GREEN4 PASS，原断言保留。Recommendation运行Docker检查与入口同一过滤环境/上下文已同步。

Minor deferred：入口日志与诊断未在此验收脚本内做canary扫描。表单清空、URL fragment移除、禁止前端持久存储有既有回归，不能据此推出所有捕获输出零泄露。早前完整分支复审仍部分中断；本次3文件复审不代替它。

## 命令与实际结果

- 官方docker buildx build --platform linux/amd64,linux/arm64 -f src/{backend,frontend}/Dockerfile … --load：最终exit0；首轮PyPI查询错误/重跑15s socket超时保留，固定版本核实存在，再加有限120s；有限socket超时不是总构建deadline。
- Docker daemon push两次HTTP响应超时；切换同目标BuildKit --push，两镜像exit0，真实摘要已用GitHub package API与构建metadata交叉核对。
- CGO_ENABLED=0三目标Go构建、当前Mac --version匹配清单：exit0；不冒充ARM/Windows硬件。
- go test -race ./...、go vet ./...：第一次sandbox监听失败；获准私有临时目录重跑exit0。
- pytest tests/tooling/test_startup_{package,release}.py -q：10 PASS；Node --test tests/startup/test_packaged_checks.cjs：4 PASS/0SKIP。
- scripts/package-launcher.py生成3包；shasum -a256 -c SHA256SUMS：3 OK；包成员无.env/数据库/密钥。
- env -i ./scripts/verify.sh integration首轮exit1：backend3949/27登记SKIP、frontend934/typecheck/build、integration393/4登记SKIP、backend-live44通过；demo2/personal4因默认Playwright执行文件缺失失败，不计PASS。
- 完整入口以PLAYWRIGHT_CHROMIUM_EXECUTABLE指向已安装Chrome重跑；本轮读取最终exit0：backend3949/27登记SKIP、frontend934、integration393/4登记SKIP、backend-live44、演示E2E2、个人fake E2E4。日志 /private/tmp/smartsketch-delivery-20261005/logs/integration-browser-retry.log；已读取实际退出结果；fake门禁不等于真实供应商验证。另文档basic快照exit0。

## 产物与待办

包 /Users/arvinhan/.codex/worktrees/plan-c-acceptance-review/SmartSketch/dist/startup-preview-20261005（忽略构建产物）；清单 packaging/release-manifest.preview-20261005.json；SHA/计数 docs/reviews/startup-delivery-verification.json；指南 docs/startup-guide.md。

两GHCR Public与匿名拉取已完成；继续真实包全链路到教师浏览器登录/重复入口/停启→补系统浏览器及按钮交接观察→按实测状态交包。Windows/ARM、Gatekeeper下载来源提示仍平台OPEN。无push/merge、GitHub Release、已有版本变动或技术冻结；镜像上传是本轮单独获准动作。

## Public完成后的实际验收检查点（2026-10-05）

两包已Public，匿名固定摘要拉取exit0（warm cache）；截图logs/ghcr-{frontend,backend}-public-full.jpg含完整公开设置。文档basic43928实际exit0，无新业务代码变更。

真实包自动验收62895整体exit1：首次入口、真实向导、错误口令拒绝、固定镜像/迁移/索引/服务就绪、首次教师登录均已到达；失败在teacher-browser-login标记之后、repeat阶段完成标记之前。证据public-package-check/acceptance.json保存，不能将“failed_stage=teacher-browser-login”误解为首次登录失败，也不猜根因。0本安装运行残留、卷保留。自动重复验收尚待诊断，不改断言或凭据。

另按自然系统浏览器流程重新启动同一fixture：入口39778实际打开Chrome向导786447090→READY→点击“打开软件”打开49376登录页786447093→使用同一合成教师进入/teacher；再次入口exit0，786447096观察既有服务/同端口。此过程没有私有能力绕行，证据public-os-handoff.json与logs/public-os-{teacher-login,wizard-ready,repeat-ready}.jpg。仅证明当前Mac Intel实际入口进程/系统浏览器/按钮/登录与重开，仍不证明Finder双击或其他平台。

停止按钮弹出浏览器confirm后CDP操作超时，确认提交未测；不得称按钮停止通过。未使用别的UI技术绕过；已按项目/安装双标签核对并仅docker stop本fixture d3e4bfc14a9401d2，0运行残留、保留卷。再核对完整二进制路径与父入口，仅SIGINT该controller，39778 exit0。浏览器若仍显示这个测试停止确认框，交用户手动关闭；不要操作其他账号/页面或重新发起确认。

总体STARTUP-12仍OPEN：自动重复用例定位、停止确认UI、Finder/Gatekeeper、Mac ARM/Win实机待补；完整分支复审仍部分中断，canary输出扫描Minor仍deferred。stage_c_status OPEN、technical_freeze NOT_PERFORMED；账本844451/900000、向量12005不变。没有源码push/merge/Release。
