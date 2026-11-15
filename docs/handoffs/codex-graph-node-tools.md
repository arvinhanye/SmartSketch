# 图谱节点快捷按钮缩放与拖动定位

日期：2026-11-15；负责人：Codex；提交基线：`main@5cc6d08`，分支 `codex/graph-node-tools`。状态 DONE：实现、自动化、Docker 与用户验收通过；用户已授权提交、推送和创建 PR，不自动合并。图谱补丁从原工作树独立提取，不包含 AI 服务设置或 PR #355。

## 问题与交付

- 原因：按钮固定像素尺寸，悬停状态只保存首次进入节点时的位置快照；节点拖动后没有同步快照。
- `useCanvasEditing.ts`：按节点屏幕直径 32px 判断是否显示两个快捷按钮；刷新现有悬停位置，节点移除或过小时清理，不重新创建悬停、不延长离开计时。
- `graph/enhancer.ts`、`GraphCanvas.vue`、`TeacherGraphView.vue`：把 G6 `afterdraw` 转为几何刷新事件。已检查安装的 G6 5.1.1：拖动调用 `translateElementBy`，在位置更新后经 `draw` 发出该事件。无轮询、无图谱写请求。
- `CanvasEditLayer.vue`：按钮尺寸随节点屏幕尺寸变化，缩放系数限于 0.9–1.5；正常比例保持原 22px/16px，大节点上限 33px/24px。
- 右键菜单、侧栏、连线行为、图谱内容与后端接口不变；规格补充于 `specs/course-knowledge-graph.md`。

## 验证

独立提交分支已复核：图谱相关 6 文件 / 213 passed（25.18s），类型检查与生产构建 exit 0。8 个图谱源码/测试/规格文件与 Docker 验收版本逐字节一致；原工作树 43 个改动文件哈希均未变化。独立分支 `./scripts/verify.sh` exit 0（含 25 项负向门禁及 B08–B14 回归）；暂存差异检查通过。

本次复核日志为 `/private/tmp/smartsketch-graph-publish-{tests,types,build,verify}.log`，测试临时配置为 `/private/tmp/smartsketch-graph-publish-vitest.mts`；其余命令参数与下列验收命令一致。构建仅有既有大分块提示，基础门禁的 pytest 缓存写入受限时有非失败警告。

以下为 Docker 验收时的证据：

- 首轮两文件回归：6 failed / 29 passed，覆盖阈值、移动、缩小、移除、计时、按钮尺寸及事件转发；实现后相关六文件 **213 passed**（38.11s）。
- 命令：`npm --prefix src/frontend run test -- --run --config /private/tmp/smartsketch-login-vitest.mts --maxWorkers=2 --testTimeout 30000 canvas-edit.test.ts graph-canvas-enhanced.test.ts graph-enhancer.test.ts graph-lifecycle-enhance.test.ts graph-direct-edit.test.ts h14.test.ts`。
- 临时配置继承仓库 `src/frontend/vitest.config.ts`，仅移除 `**/.*/**` 排除项，以便测试 `.codex/worktrees` 下的文件；不改变用例或断言。
- `npm --prefix src/frontend run type-check` exit 0；`git diff --check` 通过。已逐项检查本批 5 个源码文件、2 个测试文件及规格差异。
- `PATH=/Users/arvinhan/Desktop/SmartSketch-main/.venv/bin:src/frontend/node_modules/.bin:$PATH ./scripts/verify.sh`：exit 0，含契约生成一致性、25 项负向门禁及 B08–B14 回归。
- 日志：`/private/tmp/smartsketch-node-tools-red.log`、`smartsketch-node-tools-tests.log`、`smartsketch-node-tools-types.log`、`smartsketch-node-tools-verify.log`（其余均位于同一临时目录）。

## Docker 与浏览器验收

- `docker build -f src/frontend/Dockerfile -t smartsketch-frontend:node-tools-20261115 .` exit 0。
- 使用本地忽略文件 `.demo/ui-selection/{compose.yaml,ai-settings.override.yaml,node-tools.override.yaml}`，仅替换隔离验收环境 web 容器；`docker compose ... up -d --no-deps web` exit 0。
- 页面：`http://127.0.0.1:8082/courses/abff7c4ef63d4be19a6ca1be3ee7ceb8/graph/edit`，合成教师和示例课程，64 节点 / 71 关系；未修改 Ahn 的真实环境。
- 初始缩小视图点击节点，两个按钮均不存在，右键仍打开该节点菜单；放大后实际拖动，按钮正常出现。
- 连续拖动节点第二次位移为 `(+80, -30)`，DOM 实测两个按钮也各移动 `(+80, -30)`，无旧位置残留。
- 继续放大后，按钮实测宽度从约 19.8px/14.4px 增至 24.75px/18px；截图确认仍贴近节点。拖动只改变当前画布布局，未增删节点或关系。
- 已打开页面供用户确认。截图：`/private/tmp/smartsketch-node-tools-small.jpg`、`smartsketch-node-tools-drag.jpg`、`smartsketch-node-tools-final.jpg`。

## 后续与回退

- 用户已确认视觉验收；本分支仅发布图谱修复，原工作树及 8080/8081 环境保持原样。PR 创建后等待代码审查，不自动合并。
- 无 API、数据库或配置格式变化。回退本批前端改动并重建镜像即可；隔离 web 亦可去掉 node-tools override 恢复此前镜像。
