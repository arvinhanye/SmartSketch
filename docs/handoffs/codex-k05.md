# K05 教师主线 E2E 交接

- 交付：`tests/e2e/teacher.spec.ts` 与 `fixtures.ts` 覆盖四格式上传、上传失败重试、关系成环拒绝、发布和学生可见；根目录添加 Playwright 运行入口。
- 检查：`npm run test:e2e -- tests/e2e/teacher.spec.ts --list` 发现 1 个用例；`python -m pytest ../../tests/backend/test_k05_fake.py -q` 1 passed；真实 E2E 未运行，尚无验收结果。
- 接口与数据：未改 API 或持久化模型。`docs/atomic-tasks.json` 中 K05 的验证命令改为根目录脚本。
- 环境：worker 使用 `LLM_MODE=fake`、`K05_FAKE_EXTRACTION=1` 为此自编夹具产生有效抽取结构；真实 API、worker、Neo4j、浏览器环境仍须启动。
- 下一步：在上述环境运行 K05 单个 E2E；确认通过后再按项目门禁签收。
