# 前端测试

归 Frontend Agent。被测对象：`src/frontend/` 的组件、composables、API/SSE 客户端、G6 适配层。

- 命名：`<被测单元>.spec.ts`，与被测文件同名。
- 图谱适配层单独测：后端响应 → G6 数据结构的转换不得混进组件（`.claude/rules/frontend.md`）。
- 必须覆盖空态、加载态、错误态，以及 SSE 任务状态的穷尽分支（含终态 `cancelled`）。
- 运行器配置属于 M0-02；落地后把命令接进 `scripts/verify/frontend.sh` 的预留调用点。
