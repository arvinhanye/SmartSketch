# L10 前端设置页、未配置引导与模式标识

```text
task_id: L10
review_status: in_progress（代码与组件测试完成并提交；真实页面走查等 L09 的正式启动入口与向量服务）
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-contest-sprint-77644f
base_commit: 376bdd9
head_commit: 本任务提交
changed_files:
  - src/frontend/src/api/modelConfig.ts（新增）
  - src/frontend/src/stores/runtime.ts（新增）
  - src/frontend/src/composables/useModelConfig.ts（新增）
  - src/frontend/src/views/ModelSettingsView.vue（新增）
  - src/frontend/src/router/index.ts（SETTINGS_ROUTE、/settings/model）
  - src/frontend/src/main.ts（注入 MODEL_CONFIG_API_KEY、注册设置页）
  - src/frontend/src/App.vue（侧栏「模型 API 设置」及未配置标记、演示模式标识、登录后读取运行模式）
  - src/frontend/src/styles.css（三个样式类，只用既有设计令牌）
  - src/frontend/src/views/MaterialsView.vue、composables/useMaterials.ts（未配置引导、禁用上传、MODEL_CONFIG_REQUIRED 文案）
  - src/frontend/src/views/ChatView.vue、composables/useChat.ts（未配置引导、禁用发送与键盘提交、auth 与 MODEL_CONFIG_REQUIRED 文案）
  - tests/frontend/l10.test.ts（新增 10 例）
  - docs/tasks.md、docs/handoffs/claude-l10.md
```

## 交付

- 设置页 `/settings/model`（教师学生共用）：读取脱敏状态；保存（首次或改地址必须填密钥，只改模型名可留空）；测试连接（不带输入时测试已存配置，显示成败与中文分类）；二次确认后清除。密钥只在表单里存在，保存成功即清空，不写入任何浏览器存储；错误只按错误码与 `details.fields[].reason` 给固定文案，不回显服务端 message。
- 运行状态仓库 `useRuntimeStore`：只存 `runtime_mode` 与 `configured`，不持久化；`needsConfig`、`isDemo` 供外壳与页面使用。
- 外壳：登录后读取一次配置状态；侧栏「模型 API 设置」在未配置时带「未配置」标记；演示模式常驻标识。
- 上传页、问答页：personal 模式下未配置时显示引导与「去设置」链接，禁用提交；问答的键盘快捷提交同样拦住。

## verification

| 命令 | 结果 |
| --- | --- |
| `npm run test --prefix src/frontend -- --run l10.test.ts` | 先失败（模块不存在）；实现后 10 passed |
| `npm run test --prefix src/frontend -- --run --testTimeout 30000` | 26 个文件 782 用例通过 |
| `npm run type-check --prefix src/frontend` | exit 0 |
| `npm run build --prefix src/frontend` | 成功（仅既有的分包体积提示） |
| `./scripts/verify.sh` | exit 0（基础档） |

## unverified（下一步）

计划 Task 10 Step 9 的真实页面走查未做：需要 L09 的 `scripts/start.sh`（personal 模式）以及可达的向量服务。走查清单见计划该步骤。

## api_and_data_changes

无新接口；前端开始调用 L03/L06 的四个操作。

## rollback

回退本提交。

## next_action

L09 完成后：`scripts/start.sh --no-open`，按计划 Task 10 Step 9 走查六步并截图（截图存 `.demo/`，不入库），结果补到本文件后置 `ready_for_review`。
