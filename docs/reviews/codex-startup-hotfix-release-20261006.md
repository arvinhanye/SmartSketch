# Codex 启动器热修复与草稿验收（2026-10-06）

## 结论

STARTUP-16 DONE（源码修复、本地门禁与新草稿附件交付）；用户实际下载启动、ARM/Windows实机仍OPEN。stage_c_status=OPEN，technical_freeze=NOT_PERFORMED。本轮不合并、不公开发布、不调用真实生成/向量API。

- 修复源码 `5f45a5ce1b35c61b21a824d3c287b7c3cc95a8ee`，已推送 codex/startup-hotfix-20261006；本报告等收尾文档另提交，不改变构建代码。
- 新草稿 `404525654`：https://github.com/arvinhanye/SmartSketch/releases/tag/untagged-65399947b0be0212bc45；draft/prerelease均true，准确绑定构建提交，7附件远端state/size/SHA逐项一致。原403670008草稿/附件未改，新Tag ref查询为0（未正式打Tag）。
- 安装包：/Users/arvinhan/.codex/worktrees/plan-c-acceptance-review/SmartSketch/dist/startup-hotfix-20261006-5f45a5c；独立hotfix日期/源码命名，兼容版本仍为preview-20261005-e88b56a。原镜像/Compose不变、不自动升级业务库。

## 修复与边界复审

### P2（已修）教师身份大小写冲突

`launcher/internal/launch/controller.go:68,132-137,173`：新配置保存规范名，旧migrated配置按规范身份校验输入并恢复。`docker.go:268`：仅接受该身份的规范返回，仍拒绝其他账号。归一化不调用账号修改/密码重置接口，不重新生成凭据，不改变InstallID。

回归覆盖新装/旧migrated的三种大小写输入、不同身份拒绝、Bootstrap身份检查、下游失败保留teacher检查点。既有用例未删/未放宽。源码范围仅controller.go、docker.go、process.go及新增测试，业务API/DTO/迁移/依赖均不变。

### P2（已修）Docker助手搜索路径

`process.go:59-78`将已定位Docker绝对目录置入子进程PATH、保留原PATH并避免重复目录；`docker.go:28`使用该环境，原环境白名单仍生效。真实临时脚本验证目录含空格、路径保留、继承密钥未传入、目录不重复。不修改Docker credential配置或系统PATH。

### P3（仍OPEN）旧诊断丢阶段

ExecRunner原stderr丢弃与通用PROCESS/docker可能使阶段变unknown，未在本轮放宽日志/直接公开stderr；本轮不做通用诊断系统重构。下次修复应保持有界错误分类与密钥脱敏。

已有137/SIGKILL提示随包更新，但不签名、不清quarantine、不关闭保护；Mac下载信任问题仍需用户/Apple签名条件处理。不能把入口提示修复写成Gatekeeper已解决。

## 实际验证

- RED：Go新回归5个顶层FAIL/1 PASS，恢复分支含3个失败子例，失败正对应大小写与助手缺失；最小实现后全量Go PASS，最终 `go test -race ./... -count=1` 与 `go vet ./...` exit0。可选真实Docker测试在普通unit中显式SKIP，单独执行后真实PASS，不把SKIP计通过。
- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/tooling/test_startup_package.py tests/tooling/test_startup_release.py tests/backend/test_install_bootstrap.py -q`：20 passed / exit0。
- 隔离实际Docker `go test ./internal/launch -run '^TestLocalLegacyMixedCaseResumePreservesFirstPassword$' -count=1 -timeout=15m -v`：1 PASS，211.26秒。旧mixed-case/migrated恢复READY，同一ID/根密钥/配置；原密码登录成功、不同密码401。仅本轮合成安装/缓存镜像测试标签适配器，不是用户库或固定GHCR拉取/完整包Finder验收。
- 无.env源码快照 `/private/tmp/smartsketch-startup-fix-20261006/source`，env -i清除真实服务/模型变量后 `./scripts/verify.sh full` 单次exit0：启动器unit/vet；backend+tooling3952 passed / 27登记skip；frontend38文件934 passed、type-check/build PASS。现有Starlette/httpx弃用warning1、Vite大chunk提示保留，不改依赖消警告；报告未遗漏这些提示。额外basic也exit0。
- 最终执行Go测试的四个修复/测试文件与构建commit工作区逐字节相同。SDK官方Go1.26.8 SHA校验通过，CGO=0三平台编译；实际Intel --version exit0。跨编译不是ARM/Win实机。
- package-launcher.py创建基本包，最终hotfix独立档案根目录/文件名并加入公开BUILD-INFO与START-HERE；所有8个文件逐字节对照，Mac入口/二进制执行位核验，SHA256SUMS三包OK。附件不含.env、凭据、业务库、课程；没有把真实安装复制到门禁环境。
- 上传后及最终PATCH后7附件远端大小/SHA一致，新草稿body与本地说明逐字节一致；源码API返回准确commit。详情和archive摘要见同名JSON。

## 未验证、回滚与使用

本轮不重跑全部integration/E2E、不测真实API、无ARM/Win硬件，不宣称整个项目/第三阶段冻结。旧自动重复入口/停止UI门禁缺口保留。生成台账沿历史844451/900000、向量12005，本轮无新增模型请求；未读取业务台账或用户库补测。

用户自己的配置/密码/Neo4j/课程未改（仅只读状态），真实测试只创建独立合成资源并使用既有清理路径。新包保留原运行兼容标识，用户关闭旧控制器后从新目录重开，原用户名任意大小写、首次密码继续；不删.env/卷。预览未签名，用户仍自行审阅系统受控提示。旧包保留用于回滚文件，但旧大小写bug也会回来，不应重新初始化数据库来绕开。

源码回滚只针对本次热修提交，需复审不回退他人分支；无迁移/镜像/用户数据变更需要撤销。新草稿保持未公开，是否后续发布、主线集成、签名及技术冻结由用户决定。自身交接 docs/handoffs/codex-startup-hotfix-release-20261006.md。
