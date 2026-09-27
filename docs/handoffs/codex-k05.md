# K05 教师主线 E2E 交接

- 交付：`tests/e2e/teacher.spec.ts` 与 `fixtures.ts` 覆盖四格式上传、上传失败重试、关系成环拒绝、发布和学生可见；根目录添加 Playwright 运行入口。
- 检查：`npm run test:e2e -- tests/e2e/teacher.spec.ts --list` 发现 1 个用例；真实 E2E 未运行，尚无验收结果。
- 接口与数据：未改 API 或持久化模型。`docs/atomic-tasks.json` 中 K05 的验证命令改为根目录脚本。
- 阻塞：worker 的默认 `LLM_MODE=fake` 返回摘要对象，不含抽取器所需的 `entities`。部署端须提供能产生有效抽取结构的 fake 模型配置后再执行本用例；真实服务和浏览器环境也须启动。
- 下一步：配置测试环境，运行 K05 单个 E2E；确认通过后再按项目门禁签收。
