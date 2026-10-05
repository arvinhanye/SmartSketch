# 双击启动验证记录（2026-10-05）

## 边界

实现分支 codex/cross-platform-startup-design；工作区 /Users/arvinhan/.codex/worktrees/plan-c-acceptance-review/SmartSketch。门禁只在不含 .env 的 /private/tmp/smartsketch-startup-exec 临时源码快照进行，真实课程、测量库、共享 Neo4j 未读写；模型/向量收费调用零，未发布镜像/安装包、未推送、未冻结。

## 已取得证据

- 官方校验的 Go 1.26.8；Go 单元及 vet 已通过。含真实本机端口竞争的 race 回归需执行权限，重跑后通过；受限环境 bind 被拒的结果不记通过。
- darwin-amd64、darwin-arm64、windows-amd64 的 CGO=0 编译成功；不是实机双击通过。
- 浏览器模拟向导 1 passed：清空密码、移除 fragment、无 local/sessionStorage、说明向量/生成差异及未验证供应商。
- bootstrap 7 passed、只读 probe 与 Compose 特殊字符、打包 4 passed；离线归档 7 passed，覆盖恶意路径/链接/截断、整组恢复、卷根权限。
- ./scripts/verify.sh basic exit0；全量 integration 正在收集最终结果，不能据此宣布已通过。

## 隔离冒烟首轮发现与后续

首轮 3 failed：本地缓存镜像生成契约过旧（RuntimeMode 缺失），以及开发中源码测试编译时序问题。通过把 app / migrations / generated contracts / prompts 全部从同一源码快照重建本轮测试层解决内容漂移，后续使用冻结快照避免一边修改一边编译。未删用例或放宽断言。

Go 测试专用 image adapter 映射本轮本地标签，并跳过 pull，只证明本地合成镜像生命周期；不构成固定摘要匿名拉取/正式发行验收。清理只针对本轮随机安装 ID 且核对标签的合成容器/卷，原部署不改。

## 平台 / 发行状态

| 项 | 状态 |
|---|---|
| Mac Intel 当前主机本地单元/模拟浏览器 | 已测（非正式包双击验收） |
| Mac Intel 发行包首次安装/中文路径/断网中断 | OPEN |
| Mac Apple Silicon 实机 | OPEN（仅跨编译） |
| Windows 11 x64 ACL/WSL2/Docker/双击 | OPEN（仅跨编译） |
| GHCR 多架构真实摘要与匿名拉取 | OPEN（未发布、待用户授权） |
| 全量门禁/真实本地卷演练 | 收集中，最终结果另补 |

## 后续签收

源码、三平台构建、模拟 UI、真实本地容器场景分别报告。未测不得标 PASS。技术冻结仍 NOT_PERFORMED；stage_c_status 仍 OPEN，不重写既有测量结论。
