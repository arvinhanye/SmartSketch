# Codex：GitHub Release下载测试草稿（2026-10-05）

## 任务与状态

STARTUP-13 DONE，仅草稿与附件完成。用户明确要求创建草稿供登录GitHub下载测试；没有授权公开发布、额外推源码/合并或技术冻结。工作区/Users/arvinhan/.codex/worktrees/plan-c-acceptance-review/SmartSketch，分支codex/cross-platform-startup-design；不要改旧e92f或Claude/测量区。

草稿URL：https://github.com/arvinhanye/SmartSketch/releases/tag/untagged-52effcfbf6907990f936
Release ID403670008；拟tag preview-20261005-e88b56a；draft=true、prerelease=true、未建Tag ref。6附件：三个同版本Mac Intel/ARM/Windows包、SHA256SUMS、release-manifest.json、START-HERE.md。三包SHA与先前交付不变，六个服务端digest全部一致。

## 源码目标与边界

GitHub commits查询e88b56a、8314092、a6dc0be均422“no commit found”，尚未推送。未默认推源码；草稿暂存GitHub已确认main提交bdb89c46f9a4a9f10930675848abdd1b7af6edaf，正文强制指出这不是附件构建源码、禁止直接发布、发布前需源码同步/准确Tag对齐。Tag ref查询空，未对main或其他分支写入。未来发布须获用户额外授权后修正target/tag；不要从草稿成功推断可稳定发布。

构建出处：启动器e88b56a47645ef757948a73dfac6a7a522f7f7c8（运行实现7fee1c8），镜像构建8314092；源码/镜像摘要完整列在草稿正文与清单。GHCR已公开，不重发镜像或重编安装包。

## 交付文件

- docs/releases/startup-preview-20261005-draft.md：与上传正文相同。
- docs/releases/startup-preview-20261005-start-here.md：上传START-HERE的相同字节源文件。
- docs/reviews/startup-release-draft-20261005.json：Release身份、附件大小/SHA/下载验证范围、门禁。
- docs/tasks.md、docs/decisions.md、docs/integrations.md：用户授权、DONE范围与发布未决。

## 实际命令与结果

- shasum -a256 -c dist/startup-preview-20261005/SHA256SUMS（在该目录运行）：3 OK；tar/zip成员核验与真实清单相等，无.env/DB/key附件。
- gh api POST repos/arvinhanye/SmartSketch/releases --input显式draft payload；再gh release upload六个白名单附件：exit0。
- gh api GET release403670008：draft/prerelease true、6个uploaded且大小正确；全部服务端SHA256等于本地。matching-refs/tags/preview-20261005-e88b56a：0。
- gh release download：三份小文件逐字节一致；大包下载缓慢，02:34后仅SIGINT该完整命令匹配进程。部分下载文件仍留私有临时目录，不是可用产物、不算完整回下载成功，不自动重试。用户自行下载测试。
- 无.env干净副本env -i ./scripts/verify.sh（basic），session98260：exit0/Scaffold verification passed；日志/private/tmp/smartsketch-delivery-20261005/logs/release-draft-basic.log。
- 同样无.env源码副本pytest tests/tooling/test_startup_package.py tests/tooling/test_startup_release.py -q，session79579：10 passed/exit0。
- 没有业务代码、API、DTO、迁移、模型/向量请求；无需数据库回滚。

## 风险与下一步

用户下载Mac Intel附件测试；不是Source code。Windows/ARM仍仅构建，自动重复入口失败待定位、停止确认UI/Finder/Gatekeeper仍未验。现有STARTUP-12 handoff的已知问题保留；账本生成844451/900000、向量12005不变。stage_c_status OPEN、technical_freeze NOT_PERFORMED。

需要公开分发时先征求是否推源码到独立分支并绑定准确Tag，确认附件/源码关系与平台标注后再讨论Pre-release发布；不自动点Publish。不自动删除草稿或替换附件，用户明确指示后才调整；没有代码或用户数据变更。
