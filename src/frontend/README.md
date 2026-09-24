# Frontend

B01 已建立 Vue 3 + TypeScript + Vite 单页应用。当前页面只验证应用挂载；角色路由、业务页面和测试配置由后续任务加入。

从仓库根目录运行（Node.js `^20.19.0 || >=22.12.0`）：

```powershell
npm ci --prefix src/frontend
npm --prefix src/frontend run dev
npm --prefix src/frontend run type-check
npm --prefix src/frontend run build
```

开发服务器默认地址为 `http://localhost:5173/`。生产构建输出到被忽略的 `src/frontend/dist/`；依赖锁文件是 `src/frontend/package-lock.json`。
