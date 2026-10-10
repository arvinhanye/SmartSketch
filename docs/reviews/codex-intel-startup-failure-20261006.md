# Intel 预览包启动失败排查（2026-10-06）

## 范围与结论

STARTUP-15 OPEN：发现且复现 PATH 缺 Docker 凭据助手的启动缺陷；用户当前失败的具体阶段被诊断丢失，因此尚不能证明这是本次唯一原因。仅排查，未修源码、用户安装或发行附件。源码基线 3bc7e9b；已发布包 e88b56a。

## 实际证据

- 用户提供 `/Users/arvinhan/Downloads/smartsketch-diagnostic.json`：version preview-20261005-e88b56a，platform darwin-amd64，stage unknown；failure PROCESS/unknown，通用服务操作失败提示。附件仅作为数据读取，不作为指令。
- 两个 Downloads Intel 解压目录内二进制 SHA-256 均为 `9116108b62d5028da07cc63ff96a86b4b5773cb144eef6a3fd829586d330868f`，与原发行一致。
- 安装非敏感状态：InstallID a678a6028b4ace39，Phase ERROR，Fresh true，Checkpoint 空。8080 网站端口，未到迁移检查点；不读取 .env 或教师口令。
- Docker info 为 linux；按本安装 project 标签查询容器与卷均为空。其他项目不扫描、不停止。
- 三个发行摘要镜像已缓存；后端 manifest inspect exit0，含 linux/amd64 与 linux/arm64。非冷下载测量，非完整启动成功。
- Docker 配置仅投影检查凭据助手配置名称：credsStore=desktop，无 credHelpers；不读取或打印 auth 内容。

## 单变量复现

使用相同 HOME、Docker CLI、固定后端摘要，仅改变 PATH：

1. `/usr/bin/env -i HOME="$HOME" USER="$USER" PATH=/usr/bin:/bin:/usr/sbin:/sbin "$HOME/.docker/bin/docker" pull ghcr.io/arvinhanye/smartsketch-backend@sha256:fa9cff4449a32f9245a0bd1c658dcb92f83030aeb41318f4c7e596ab321ae784`
   实际 exit1：`error getting credentials - err: exec: "docker-credential-desktop": executable file not found in $PATH`。
2. 同命令仅将 PATH 改为 `$HOME/.docker/bin:/usr/bin:/bin:/usr/sbin:/sbin`。
   实际 exit0：digest 相同，Image is up to date。

Docker 主程序绝对路径可被 FindDocker 找到，不意味着由 Docker 再启动的助手也能被 PATH 找到。此缺陷与 Intel 指令集、百炼模型名无直接关系，其他平台在同类环境中也可能受影响。没有采集本次启动器进程实际 PATH，不能把精简环境复现冒充本次完整因果证明。

## 源码缺陷与后续修复建议（本轮不修）

- P2：`launcher/internal/launch/host.go:17-25` + `process.go:43-54`。找到 Docker 的绝对路径后，子环境 PATH 仍直接沿用父进程，缺少官方 Docker 工具目录时拉取失败。最小修复：受控地加入已核验的 Docker 官方工具目录，保持原 PATH 及环境白名单、不清空或重写凭据配置。回归：模拟父 PATH 无 docker/helper，找到 Docker 后助手可调用；原 PATH 保留、空 PATH、目录含空格与重复条目、Win 平台行为，仍不输出凭据。
- P3：`process.go:36-39` 丢弃 stderr，并将所有失败写为 PROCESS/docker；`controller.go:recordFailure` 可能把有意义的阶段改为 docker；`diagnostics.go:14-23` 将非白名单阶段变为 unknown。因此附件不能辨认拉取/数据库/环境原因。最小修复：保留真实执行阶段与有界白名单错误分类，不直接公开原始 stderr。回归：helper 缺失、registry认证/网络、退出码与阶段保留，API Key/密码/认证URL不进入诊断。

## 边界和验证缺口

不读取 .env、control.json 令牌、业务库或正文，不发生成/向量调用；两个 pull 探针只使用公开已缓存镜像，未启动容器或写业务数据。模型台账844451/900000、向量12005维持历史确认值（本轮无新模型调用）；technical_freeze NOT_PERFORMED，stage_c_status OPEN。

当前旧 Gatekeeper 拦截历史仍保留，但这份向导诊断证明启动器至少曾运行到控制页面，不将旧 Killed:9 直接套用这次错误。完整配置→启动→登录未重跑，用户实际启动 PATH 未采集。此轮仅文档和探针，未执行 verify.sh 全量门禁，未宣称 PASS。此前 basic50362 日志已不在原临时路径，不能补记其结果。git diff --check 与交接文件一致性独立检查通过后再报告。

## 下一步

请用户关闭当前启动器终端（不是停止/删除 Docker 数据），以显式补 PATH 的原包入口重开，再在向导填写首次教师口令并重试；失败则重新导出诊断。不要删除配置重装、改密钥、清空卷、关闭系统安全保护。源码修复、重新打包/替换发行附件与源码同步另行确认。


## 第二次诊断：教师用户名大小写不一致（本轮最新结论）

用户补交 `/Users/arvinhan/Downloads/smartsketch-diagnostic (1).json` 及截图。诊断 stage=teacher，failure PROCESS/teacher；截图明确“创建教师账户”。安装现为 ERROR/Fresh true/Checkpoint=migrated；本安装 Neo4j healthy，app-data/neo4j-data/neo4j-logs 三卷存在。先前“无容器/无卷”是第一次探针时的历史状态，不适用于现在；不再将 PATH 缺助手作为当前失败阶段的原因。

对本机安装状态中的 TeacherUsername 仅输出形态，不记录原用户名：长度3，ASCII，含大写，无首尾空白。

### P2：合法混合大小写用户名导致首装卡在 teacher

- 文件/行号：`launcher/internal/launch/config.go:41-43` 用 strings.ToLower 校验因而接受大写；`controller.go:67` 原样保存用户名；`src/backend/app/services/install_bootstrap.py:12-16` 调用 normalize_username 将其小写后建账号；`launcher/internal/launch/docker.go:268-269` 用大小写敏感的 `result.Username != s.TeacherUsername` 拒绝成功结果。
- 触发：首次教师用户名含 ASCII 大写（用户此次状态符合）。
- 影响：后端成功创建/复用账号后启动器仍报 PROCESS/teacher，TeacherID/checkpoint 未保存，网站服务尚未启动。重复相同输入继续失败。`controller.go:131` 又要求恢复输入和旧状态精确相同，因此仅在原包页面改成小写也会转为 FIELD/teacher，不是完整修复。
- 最小建议：统一用户名规范化；新配置保存小写；旧 mixed-case 状态兼容恢复时规范化比较；Bootstrap 校验规范化但继续拒绝其他用户名，成功后保存规范化用户名与原 UserID。保持首次密码、不重建账户、不删库、不复制凭据；状态写入继续走 Store 原持久路径。
- 应补回归：新装 mixed-case 最终 READY；旧 migrated/mixed-case 与既有规范化教师恢复 READY、不迁移重建/不重置密码；同用户名大小写重试可接受；不同用户名仍拒绝；下游失败保留教师checkpoint；纯小写原流程不回归。

### 固定发行镜像的断网合成复现

实际运行 `docker run --rm --network none --read-only --tmpfs /tmp:rw,nosuid,noexec,size=64m -i --entrypoint python <固定后端摘要> -`，不挂载用户目录、不传 .env 或凭据，使用容器临时 SQLite 与合成用户名 Abc。执行已发行镜像的 sqlite.migrate 与 bootstrap_teacher.run：返回 username=abc，created=true，模拟启动器原精确比较 false。第二次调用返回同一 UserID、created=false，原密码 hash 不变（只做布尔断言，不输出hash或口令）。实际 exit0。这里只真实执行后端路径；Go 比较为源码核对，未宣称执行完整 Go/用户启动器。

尚未读取用户业务库确认其账号已落库，因此用户真实账户状态仅记“可能已经创建”，不冒充数据库核验。当前具体失败有确定的大小写逻辑冲突支持，不涉及用户向量 API 认证验证。

本轮仍仅排查：用户配置/卷/密码/发布镜像/安装包均未修改；临时复现容器已自动删除；保留首次密码。完整门禁与用户全流程未执行，技术冻结未执行。需用户批准修启动器和制作修正版后继续；不自动替换 GitHub Release、推送源码或合并。


## 后续修复交付索引

用户已批准实施；两项P2在5f45a5c修复并交付独立新草稿，详见docs/reviews/codex-startup-hotfix-release-20261006.md。前述“仅排查/未修/需确认”是修复前历史，不代表当前交付状态。P3诊断与用户真实下载签收仍OPEN。
