# 最新主线安装包 rc-55c0c17

- 任务 PACKAGE-RC-55C0C17；负责人 Codex；状态 DONE（安装包、镜像分发与匿名拉取验证完成）。
- 用户范围：只制作对应最新版本的安装包。构建基线为远端 main `55c0c174e0b7fabc68a842352a3e1068f369babd`，不更改产品功能、默认开关或已有安装。
- 正式交付目标沿用 Mac Intel（darwin-amd64）与 Windows x64（windows-amd64）。既有打包器强制生成第三份 darwin-arm64；该中间产物不作为本次支持平台交付。
- 使用 `git archive` 导出固定提交后构建，排除工作树未提交内容、个人配置与运行数据。记录位于 `.demo/package-rc-55c0c17/`。

## 验证与交付

- Go 1.26.8：`scripts/verify/startup.sh` unit/vet 通过（包括 Windows 目标 vet）。
- `PYTHONPATH="$PWD/src/backend:$PWD" .venv/bin/python -m pytest tests/tooling/test_startup_package.py tests/tooling/test_startup_release.py -q`：13 passed。
- `node --test tests/startup/test_packaged_checks.cjs`：4 passed。
- 后端镜像 `/app` 下 218 个文件与固定源码逐文件 SHA256 一致，无额外文件。
- `PATH="$PWD/.venv/bin:$PATH" GOCACHE="$PWD/.demo/package-rc-55c0c17/go-cache" ./scripts/verify.sh`：exit 0。
- 官方 Dockerfiles 从固定源码构建两份 linux/amd64 镜像，均 exit 0；前端 28 个静态文件与 nginx 配置检查通过。两镜像都标记完整源码提交。
- Go 1.26.8 三目标编译通过；本机 Mac Intel `--version` 为 `rc-55c0c17`。最终只交付 Mac Intel 与 Windows x64 两包，每包 6 个文件；版本清单、固定 Compose 摘要、二进制内容、入口权限、无额外文件与 SHA256SUMS 全部检查通过。
- `SMARTSKETCH_STARTUP_SMOKE=1 STARTUP_TEST_BACKEND=smartsketch-startup-test-backend:rc55c0c17 STARTUP_TEST_FRONTEND=smartsketch-startup-test-frontend:rc55c0c17 GOCACHE="$PWD/.demo/package-rc-55c0c17/go-cache" GOTOOLCHAIN=local PYTHONPATH="$PWD/src/backend:$PWD" .venv/bin/python -m pytest tests/startup/test_release_smoke.py -q -x`：3 passed，697.40s，exit 0。包括登录/停启、两安装隔离、整组备份与重复恢复。
- 冒烟使用本次实际镜像和隔离合成数据，但镜像适配器跳过发行 pull；不是实际安装包的 GUI 双击、真实模型或旧版升级验收。原开发容器保持运行；本轮合成资源按记录的项目和标签清理。
- Desktop 原工作树 40 项状态和文件 SHA256 与保护快照一致。

## 产物

目录 `dist/rc-55c0c17/`：两份包、`SHA256SUMS`、`release-manifest.json`、`START-HERE.md` 与 `BUILD-INFO.json`。构建产物被 Git 忽略，不提交。

| 包 | SHA256 |
| --- | --- |
| `SmartSketch-rc-55c0c17-darwin-amd64.tar.gz` | `863d276de49fab3d8231468f1853804938ad3d292ec1e09bf9b0177e1a9d1352` |
| `SmartSketch-rc-55c0c17-windows-amd64.zip` | `5e55740e67a5e91763a69ff28a8348e35dd48eeede777952c8390940b8d9fafc` |

后端镜像 `sha256:9bae9bd13b884b90d048c47a5c1b04078ee119c9cbb2dc550b9409a9a6835b09`；前端镜像 `sha256:de8f394549b3eb29f3d7156378ca556750719c5f77dec264fdedd7ecbd0224c7`。两仓库可见性为 public；分发前再次匿名检查新版本 tag 均为 404，无既有版本被替换。

用户于 2026-11-14 明确批准上传这两份已验证镜像，仅新增 `rc-55c0c17`。两次 `docker push` 均 exit 0，远端摘要与包内清单完全一致。之后使用空 Docker 认证配置、`env -i`、不含凭据助手的系统 PATH、显式 Docker endpoint，分别按固定摘要执行 `docker pull`，均 exit 0；此次命中本机缓存，证明匿名权限和清单可获取，不代表冷下载速度。独立匿名 Registry HTTP 校验两镜像的 tag 与固定摘要均返回 200，响应体 SHA256 与声明摘要逐字节一致。

证据：`.demo/package-rc-55c0c17/logs/{backend,frontend}-push.{log,exit}`、`{backend,frontend}-anonymous-pull.{log,exit}`、`registry-pre-upload.json`、`registry-after.json`。`dist/rc-55c0c17/BUILD-INFO.json` 已同步分发状态；两份安装包及 SHA256SUMS 保持原样。已确认镜像分发不再阻塞安装，仍不把匿名拉取视为实际安装包 GUI 或 Windows 实机验收。

## 边界与恢复

本任务不运行付费模型评测，不代表软件正式验收、Windows 实机通过或签名公证。保留旧发行版本与用户安装、业务库、其他工作树；原 Desktop BE-05 40 项改动不动。若使用旧安装，版本升级必须遵循启动器原有停机、备份、迁移和恢复保护，不仅替换镜像或删除迁移记录。

产品源码、依赖声明、API、数据模型和默认配置均无改动；只有本次打包清单与交付记录。用户随后追加授权 GitHub 预发布，执行结果如下。

## GitHub 预发布（2026-11-14）

- 用户明确要求上传这两份包与校验和，创建 `rc-55c0c17` 预发布并保留旧版本。发布前记录全部旧 Release 与附件；新版本先作为草稿上传，核对内容后再发布。
- [rc-55c0c17](https://github.com/arvinhanye/SmartSketch/releases/tag/rc-55c0c17)，Release ID `445432576`，发布时间 `2026-11-14T16:35:05Z`，`draft=false`、`prerelease=true`。tag 精确指向 `55c0c174e0b7fabc68a842352a3e1068f369babd`；未标记为稳定 Latest。
- 三个附件名称和字节数完全匹配；GitHub 服务端 SHA256 均与本地一致。SHA256SUMS 的完整回下载也逐字节一致。大包可选回下载因网络缓慢主动取消（exit 130），保留部分文件，不计完整下载通过；这不影响已完成的服务端内容摘要校验。
- 原 3 个 Release（包括 2 个草稿）及 16 个附件的 ID、版本、标题、说明、发布属性、文件名、大小、摘要和链接均与发布前一致；未删除或更新旧版。
- 证据位于 `.demo/package-rc-55c0c17/release-publication/`：`releases-before.json`、`expected-assets.json`、`release-draft-verified.json`、`release-published.json`、`tag-ref.json`、`result.json` 与 `download-result.json`。构建信息已同步 Release URL；包本身没有重建。

## 发布记录入主线

用户授权将这次清单与记录提交、推送、开 PR，最终检查通过后合入 main。分支 `codex/package-release-records-rc55c0c17` 基于 `55c0c17`，只提交本交接、对应任务看板段落及 `packaging/release-manifest.rc-55c0c17.json`。构建产物和本地详细日志保持忽略状态，不纳入提交。

开始时已记录 14 个工作树的状态与改动文件哈希；其中本工作树只有上述 3 个文件，另有 Desktop 的 40 项改动须保持原样。自查核对发行清单的固定摘要、Compose 校验和、Release 附件及 tag；最终 PR 检查与合并记录为主线发布状态权威，不改写已发布包的构建版本。

本轮本地验证：`PATH="$PWD/.venv/bin:$PATH" GOCACHE="$PWD/.demo/package-rc-55c0c17/go-cache" ./scripts/verify.sh` exit 0；相同显式 `PYTHONPATH` 下重跑 `tests/tooling/test_startup_package.py` 与 `test_startup_release.py`，13 passed（6.25s），exit 0；`git diff --check` 通过。实际清单通过现有打包器校验，与两份已发布包内清单逐字节一致；远端 Release/tag 和三附件摘要符合记录。自查覆盖 3/3 文件，无待修复项；本轮证据在 `.demo/package-rc-55c0c17/pr-publication/`。产品代码未改，不重复此前 3 项 Docker 生命周期验收；新 PR 的全部远端检查通过后才合并。
