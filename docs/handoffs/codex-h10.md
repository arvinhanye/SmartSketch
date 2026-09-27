# H10 发布历史和回滚 UI 交接

- 任务：H10，issue #122；分支 `codex/h10-version-panel`，基线 `main@8741078`。
- 交付：`src/frontend/src/api/versions.ts` 封装 G06 三个端点；`src/frontend/src/composables/useVersions.ts` 管理课程内教师校验、历史读取、发布/回滚与请求作废；`src/frontend/src/components/VersionPanel.vue` 展示当前学生可见版本、修订状态、历史及页内回滚确认；接入 `ReviewView.vue` 和 `main.ts`，并在 `tests/frontend/h09.test.ts` 的公共夹具注入版本 API 测试桩。
- 验收：发布失败不乐观改指针；`revising` 明示学生仍见旧版；回滚前展示目标及前滚语义；成功响应后必须重读课程详情与版本列表并核对指针，未确认时暂停继续写入；超时或断网结果不明时也暂停再次写入，直到刷新核对；切课迟到响应不覆盖新课程。
- 测试：`tests/frontend/h10.test.ts` 10 项。先以缺模块红灯；新增的页面接入、成功刷新指针、课程教师权限和超时锁定用例也分别先红后绿。
- 验证：`npm --prefix src/frontend run test -- --run ../../tests/frontend/h10.test.ts` 10 passed；H09+H10 47 passed；`npm --prefix src/frontend run test -- --run --testTimeout 30000` 19 files / 634 passed；`npm --prefix src/frontend run type-check` exit 0；`npm --prefix src/frontend run build` exit 0；`./scripts/verify.sh` exit 0；`git diff --check` exit 0。
- 接口/数据：只消费既有 `GraphVersion`、`PublishResult`、`Course` 与 G06 API；无契约、后端、迁移或依赖变更。UI 决策记入 ADR-073，规格已补 H10 落实段。
- 风险/下一步：仅 fake API 验证；真实发布失败、回滚与学生旧版可见性应由 K05 教师主线 E2E 联调。若 PR #298 先合入，需按文件级差异重验 `ReviewView.vue` 与 `docs/decisions.md`。
- 回滚：撤销 H10 的 API、组合逻辑、组件、审核页和应用注入接线；无持久层回滚。
