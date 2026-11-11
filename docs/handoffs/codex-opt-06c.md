# OPT-06C：useMaterials.ts 按职责拆分

- task_id：OPT-06C；负责人 Codex；状态 IN_PROGRESS（实现与前端全量通过，共用门禁/最终审查待完成）。
- 本地分支 `codex/opt-06c-materials`；未来 PR 以 `codex/opt-06a-compatible` 为 base，仅包含本项范围；用户要求暂不推送或合并远端 PR。

## 文件与边界

`useMaterials.ts` 从 843 行降为 547 行，保留状态、watch、上传/取消/删除、请求代次、SSE 与 dispose 顺序；composable 主函数体逐字相同。新内部模块位于 `composables/materials/`：`files.ts` 负责格式/文件大小/同章异格式校验，`status.ts` 负责状态呈现，`errors.ts` 负责错误映射，`types.ts` 放共享类型。旧入口保留原 14 个导出名及类型，没有复制响应式状态或修改返回对象。

## 验证

- TypeScript AST 审计：41 个声明、14 个导出与原基线一致；主函数体 byte-identical，证据 `c-audit.json`。
- `npm --prefix src/frontend run test -- --run h02.test.ts`：**95 passed，exit 0**，覆盖切课、晚到响应、任务终态、取消/清理等既有行为。
- `PATH="$PWD/.venv/bin:$PATH" scripts/verify/frontend.sh full`：**82 文件 / 1375 passed**，type-check、build 均 exit 0；保留既有测试警告及 bundle 大小提示。
- 共用 `./scripts/verify.sh` 与最终独立审查待四项收尾完成；日志 `c-targeted.log`、`c-frontend-full.log` 及对应 `.exit` 均在 `.superpowers/sdd/2026-11-10-opt-06-responsibility-split/`。

## 接口、数据与未完成项

无 API、契约、数据、配置、依赖或界面文案变化；架构只同步内部源码映射。沿用行为回归，不增加仅验证文件布局的测试。当前未完成共用门禁与最终审查。回滚仅撤销本项代码提交，无数据迁移。
