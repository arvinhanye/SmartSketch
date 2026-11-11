# 历史分支验证材料

`claude-k08-recheck.md` 原样摘自历史提交 `4ca834058de73c9ebad1fadc73ec99dce5b5115c` 的同名交接，原基线为 `7261514`。它记录当时 Linux 沙箱中的镜像构建和容器操作；本轮只验证归档字节与 Git blob 一致，没有重做其中操作。

这些是来源作者的历史结果，不是当前 main 的验收，也不能据此关闭当前 Docker Desktop/真实模型/发布待办。文中的 fake 限制和脚本挂载做法可能已经被 demo 模式及新运行手册取代；原文保留用于追溯，不作为现行操作指令。

其余15分支的完整代码与历史文档已保存到主检出 `.demo/historical-branch-cleanup-20261111/all-branches.bundle`；逐分支取舍见 `docs/reviews/historical-branches-20261111.md`。
