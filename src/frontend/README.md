# Frontend

B01 已建立 Vue 3 + TypeScript + Vite 单页应用，B02 已建立 Vitest 测试配置。当前页面只验证应用挂载；角色路由与业务页面由后续任务加入。

从仓库根目录运行（Node.js `^22.22.2 || ^24.15.0 || >=26.0.0`，下限来自 Vitest 5 与 jsdom 30）：

```bash
npm ci --prefix src/frontend
npm --prefix src/frontend run dev
npm --prefix src/frontend run type-check
npm --prefix src/frontend run test -- --run
npm --prefix src/frontend run build
```

开发服务器默认地址为 `http://localhost:5173/`。生产构建输出到被忽略的 `src/frontend/dist/`；依赖锁文件是 `src/frontend/package-lock.json`。

## 测试

- 用例放在仓库外层 `tests/frontend/**/*.test.ts`，由 `vitest.config.ts` 收集；DOM 环境为 jsdom，`tests/frontend/setup.ts` 在每个用例后自动卸载 `@vue/test-utils` 挂载的组件。
- 只跑一个文件：`npm --prefix src/frontend run test -- --run ../../tests/frontend/<name>.test.ts`。不带 `--run` 时进入 watch 模式。
- 测试中的裸模块导入（如 `vitest`、`@vue/test-utils`）从本目录的 `node_modules` 解析，无需在 `tests/` 下另装依赖。
- 零用例不算通过；点开头的目录不会被收集。
- `type-check` 分两段：`tsconfig.json` 只含应用代码（浏览器类型），`tsconfig.node.json` 含 Vite/Vitest 配置与 `tests/frontend`（Node 类型）。
