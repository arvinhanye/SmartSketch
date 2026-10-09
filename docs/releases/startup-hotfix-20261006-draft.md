# 智绘学途启动器热修复：2026-10-06 下载测试草稿

**Draft / Prerelease：未公开发布、非正式版，未执行技术冻结。**

Intel Mac 请下载 Assets 中 `SmartSketch-hotfix-20261006-5f45a5c-darwin-amd64.tar.gz`，不要下载 Source code。ARM Mac / Windows x64 使用对应包。

## 本次修复

- 教师用户名大小写统一：新配置规范化，兼容旧 mixed-case / migrated 初始化中断；不同账号仍拒绝。
- 已有教师账号重入不修改首次密码、UserID、安装ID或密钥，不清空配置/数据。
- Docker 子进程补已定位工具目录，修复双击环境找不到 docker-credential-desktop 的拉取失败。
- 包含 Mac 137 / SIGKILL 说明；不移除下载隔离、不关闭系统保护。

## 旧安装继续测试

1. 保持 Docker Desktop 开启，关闭旧启动器终端。
2. 将新包完整解压到新目录并核对 SHA256SUMS，双击新目录的入口。
3. 初始化中断表单填原教师用户名（大小写均可）与首次密码，点击启动/重试。
4. 就绪后打开软件，用首次账号密码登录。不要删除 .env、改根密钥或清空数据卷。

运行兼容标识仍显示 `preview-20261005-e88b56a`，因为本次不改业务镜像/Compose或迁移；该标识不代表新启动器源码。新包目录/文件名已独立命名，构建出处见 BUILD-INFO.json。

## 构建出处

- 启动器源码：`5f45a5ce1b35c61b21a824d3c287b7c3cc95a8ee`，已推送 `codex/startup-hotfix-20261006`；草稿 target_commitish 绑定这个准确提交，不暂绑 main。
- 原前后端/Neo4j固定摘要与Compose保持不变，见 release-manifest.json。
- Go 1.26.8 官方归档SHA校验通过，三平台CGO=0编译；档案内容逐字节对照、执行位和SHA核验通过。不包含 .env、凭据、业务库、课程资料。

## 本轮验证与未验证项

- 旧代码新回归先失败，修复后Go全量、race、vet通过；Python打包/清单/引导定向20 passed。
- 真实隔离Docker旧migrated混合大小写恢复1 passed：原账号/密码/密钥保持不变，原密码登录成功，另一密码401。此测试仅合成安装、测试镜像标签适配器，不是用户数据验收或Finder双击验收。
- 无.env隔离 `./scripts/verify.sh full` 实际 exit0：启动器单元/vet通过，backend+tooling 3952 passed / 27登记skip；frontend 38文件 / 934 passed，type-check/build通过。backend有既有Starlette/httpx弃用警告，前端构建有大chunk提示，未以删除用例或放宽门禁规避。
- 本轮未重跑整套integration/E2E，未发真实模型/向量调用；用户完整启动检查仍待执行。
- Mac未Developer ID签名/公证；Windows未代码签名；ARM/Windows未实机，跨编译不代表硬件通过。旧自动重复入口及停止UI验收缺口仍保留。
- 诊断丢具体阶段P3仍OPEN；本次不直接公开原始stderr。
- `stage_c_status=OPEN`，`technical_freeze=NOT_PERFORMED`；未合并main，未修改用户安装或旧Release草稿。
