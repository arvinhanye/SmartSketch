# 交接：UI-GRAPH-FIND-01 图谱查找、快捷键与视图记忆

- 日期：2026-11-11
- 负责人：Claude
- 分支 / 基线：`claude/knowledge-graph-ux-analysis-2e7400` / `main@3f26766`
- 状态：实现与自动化验收完成；**浏览器实测未做**；未提交、未推送

## 背景

2026-11-10 对照成熟图谱产品做了一次体验差距分析，用户确认先做第一批：搜索、键盘、状态记忆。规格见 `specs/course-knowledge-graph.md`「图谱查找、快捷键与视图记忆」。

## 交付物

| 能力 | 行为 | 主要文件 |
| --- | --- | --- |
| 搜索高亮 | 输入关键字不再隐藏知识点：命中带 `match`，没有预览/选中时其余 `dimmed`；没有命中时不淡化 | `graph/focusStates.ts`、`composables/useGraphFilters.ts`（`search: 'highlight'`、`matches`） |
| 别名与排序 | 匹配名称与契约 `aliases`；名称完全一致 > 开头 > 包含 > 别名完全一致 > 别名包含 | `graph/search.ts`（新）、`graph/adapter.ts`（节点数据带 `aliases`） |
| 候选与逐个定位（学生页） | 候选最多 8 条；回车下一个、Shift+回车上一个、首尾循环；计数“第几个 / 共几个” | `components/GraphSearch.vue`（新）、`views/StudentGraphView.vue`、`styles/graph-workspace.css` |
| 逐个定位（教师页） | 沿用工具栏搜索框，回车依次定位下一个并显示位置；仍经过“未保存修改”确认 | `views/TeacherGraphView.vue` |
| 快捷键 | `/` 聚焦搜索，`F` 适应画布，`+`/`=` 放大，`-` 缩小；输入控件内、带修饰键、输入法组合中不触发 | `composables/useGraphShortcuts.ts`（新）、`components/GraphCanvas.vue`（暴露 `zoomBy`，按钮说明写出按键） |
| 地址记忆（学生页） | `kp`、`q`、`ch`、`rel`、`type`、`view=cards` 用 `router.replace` 写入并可恢复；改选知识点后移除问答链接的 `v` | `composables/graphViewQuery.ts`（新）、`views/StudentGraphView.vue` |
| 面板宽度记忆 | 学生页（百分比）与教师页（像素）记在 `localStorage`，存储不可用时照常工作 | `composables/usePanelWidthPreference.ts`（新） |

## 接口 / 数据变更

- 后端、契约、数据库：无。
- 前端内部：`G6NodeData` 新增可选字段 `aliases`（没有别名时不带）；`useGraphFilters` 新增选项 `search` 与返回值 `matches`；新增导出 `matchNodes`。`filterGraph`、`locateNode` 的既有语义保留（`locateNode` 现在也匹配别名，并且“以关键字开头”排在“包含”之前）。
- `applyFocusStates`：没有预览/选中、没有章节聚焦、有搜索命中时，未命中的节点加 `dimmed`（此前只给命中加 `match`）。
- 本浏览器存储新增两个键：`smartsketch.panel-width.student-graph`、`smartsketch.panel-width.teacher-graph`，值是一个数字。

## 验证

在工作树根目录执行：

```bash
npm ci --prefix src/frontend
scripts/verify/frontend.sh full     # exit 0：type-check 无错误；78 文件 / 1338 条通过；build 成功
./scripts/verify.sh                 # exit 0（basic）
```

- 新增测试：`tests/frontend/graph-find.test.ts` 31 条（查找排序、筛选层高亮模式、快捷键、地址参数、宽度偏好、搜索框组件、学生页整页行为）；`tests/frontend/h14.test.ts` 追加 3 条（教师页高亮、循环定位、宽度记忆）。
- 调整的既有断言 2 条，均因规格变更：`graph-focus-states.test.ts`「搜索命中只加 match」改为「命中加 match、其余淡化」；`h03.test.ts` 节点数据期望加上 `aliases`。
- 反向验证一次：把学生页的 `search: 'highlight'` 去掉，新测试 3 条失败；恢复后通过。
- **测试是实现之后补写的，不是先红后绿。**

### 未验证

- 浏览器实走：本机 Docker 未启动，没有后端与演示数据，未在真实页面上看过。尤其需要看：搜索框在 280px 宽度下加上计数与两个按钮后是否拥挤；候选浮层是否被其他浮层遮挡；淡化在真实课程（63 节点）下的观感；快捷键与浏览器自带的 `/`（Firefox 快速查找）是否冲突。
- 读屏对 `combobox`/`listbox` 的朗读。
- `verify.sh full/integration` 的后端与集成部分（后端未改）。

## 风险与已知限制

- 地址写回与问答链接 `?kp=&v=` 的处理靠 `handledLink` 互相避让：页面自己写回的地址预先登记为“已处理”。如果以后改动链接侦听的键格式，两处要一起改。
- 由地址恢复 `ch` 时只恢复章节外框与淡化，不保证镜头适应到该章（画布此时可能还没建好，`fitTo` 在建图前调用会被忽略）；同时有 `kp` 时镜头聚焦到知识点。
- 每次按键都会 `router.replace` 一次（写 `q`）。目前没有看到性能问题，但未在低端设备上测过。
- 教师页的“位置计数”在确认框被取消时仍会前进一位（选中没变，计数变了）。
- 教师页没有候选浮层和“上一个”，也没有把视图写进地址。

## 回滚

还原本任务的改动即可（未提交时 `git checkout -- <上表文件>` 并删除新增文件）。没有数据迁移；`localStorage` 里的两个键残留无害。

## 下一步

1. 启动演示环境（`scripts/start-demo.sh`，需要先启动 Docker）做浏览器实走，重点看“未验证”里的四项。
2. 用户视觉签收后再提交与开 PR。
3. 本批明确不做、留给后续批次：镜头位置写入地址、教师页视图写入地址、拼音/模糊匹配、搜索定义正文、命令面板。
