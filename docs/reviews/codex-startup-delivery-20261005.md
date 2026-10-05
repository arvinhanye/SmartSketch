# 实际启动包交付进度（2026-10-05，尚未完成用户可用签收）

## 范围与结论

工作区 /Users/arvinhan/.codex/worktrees/plan-c-acceptance-review/SmartSketch；分支 codex/cross-platform-startup-design。接续“双击→配置→启动→登录”；不修改旧e92f、Claude或测量区，不读取个人.env，不复制业务库，不发收费生成/在线向量请求。stage_c_status OPEN，technical_freeze NOT_PERFORMED。

官方 Dockerfile 从干净跟踪源码构建 linux/amd64 + linux/arm64，通过并上传两份 GHCR 镜像。运行代码 e88b56a；构建唯一变更8314092为 pip120s socket超时，原固定依赖/TLS不变。真实索引后端fa9cff4449a32f9245a0bd1c658dcb92f83030aeb41318f4c7e596ab321ae784、前端126ada210c9a275316f5de33bd8c5f7feb86a26033a36c1403643e77315053a9，Neo4j真实多架构摘要见发行清单。此版名称preview-20261005-e88b56a不是技术冻结。

**未完成交付**：两份包仍Private，公开操作在UI提交前被审批拦截，已向用户要求临近确认，未通过CLI/其他路线绕过。三份包已生成并SHA核对，但普通用户匿名拉取/完整启动至登录未通过。不能以这些包“存在”宣称可用闭环完成。

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
- 完整入口以PLAYWRIGHT_CHROMIUM_EXECUTABLE指向已安装Chrome重跑；最后核对仍RUNNING。日志 /private/tmp/smartsketch-delivery-20261005/logs/integration-browser-retry.log；接续必须读实际退出结果，不从本段推断通过。

## 产物与待办

包 /Users/arvinhan/.codex/worktrees/plan-c-acceptance-review/SmartSketch/dist/startup-preview-20261005（忽略构建产物）；清单 packaging/release-manifest.preview-20261005.json；SHA/计数 docs/reviews/startup-delivery-verification.json；指南 docs/startup-guide.md。

待用户确认实际提交两GHCR Public设置→匿名配置目录下拉取真实digest→真实包全链路到教师浏览器登录/重复入口/停启→补系统浏览器及按钮交接观察→按实测状态交包。Windows/ARM、Gatekeeper下载来源提示仍平台OPEN。无push/merge、GitHub Release、已有版本变动或技术冻结；镜像上传是本轮单独获准动作。
