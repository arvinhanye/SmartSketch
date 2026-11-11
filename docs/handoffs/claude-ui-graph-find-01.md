# 交接：UI-GRAPH-FIND-01 图谱查找、快捷键与视图记忆

- 日期：2026-11-11
- 负责人：Claude
- 分支 / 基线：`claude/knowledge-graph-ux-analysis-2e7400`，已合入 `main@99e169a`（含 #341 的 OPT-01..06 与改版前端）
- 状态：实现、自动化验收与浏览器实走完成；PR arvinhanye/SmartSketch#342（目标 main）已推送，待 CI 与用户视觉签收

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
- `lifecycle.focus` 与 `GraphCanvas.focus` 新增可选参数 `{ readable }`；新增 `composables/searchFocus.ts`（`isSearchFocused`），`KnowledgeDetail` 与 `NodeEditor` 载入后聚焦标题前先判断。
- `applyFocusStates`：没有预览/选中、没有章节聚焦、有搜索命中时，未命中的节点加 `dimmed`（此前只给命中加 `match`）。
- 本浏览器存储新增两个键：`smartsketch.panel-width.student-graph`、`smartsketch.panel-width.teacher-graph`，值是一个数字。

## 验证

在工作树根目录执行（合入改版分支后的最终代码）：

```bash
npm ci --prefix src/frontend
scripts/verify/frontend.sh full     # exit 0：type-check 无错误；83 文件 / 1414 条通过；build 成功
./scripts/verify.sh                 # exit 0（basic）
```

- 新增测试：`tests/frontend/graph-find.test.ts` 33 条（查找排序、筛选层高亮模式、快捷键、地址参数、宽度偏好、搜索框组件、学生页整页行为、生命周期 `focus` 的 `readable` 选项）；`tests/frontend/h14.test.ts` 追加 4 条（教师页高亮、循环定位、搜索中不抢焦点、宽度记忆）。
- 调整的既有断言 2 条，均因规格变更：`graph-focus-states.test.ts`「搜索命中只加 match」改为「命中加 match、其余淡化」；`h03.test.ts` 节点数据期望加上 `aliases`。
- 反向验证一次：把学生页的 `search: 'highlight'` 去掉，新测试 3 条失败；恢复后通过。
- **第一轮测试是实现之后补写的，不是先红后绿。** 浏览器实走发现的两处问题是先有复现（实走现象 / 失败用例）再修的。

### 合并

- 合入 `codex/opt-05-backend-layering`（UI-PINE-01 改版、UI-NORAIL-01 顶栏导航、邀请码、GRAPH-HOVER-01 悬停差分等 10 个提交）。冲突三处：两个页面的导入语句（对方抽出 `countNodeTypes` / `toggledNodeTypes`，本任务去掉 `locateNode` 导入）、`docs/tasks.md` 末尾（两边都追加，按时间保留双方）。

### 浏览器实走（2026-11-11，1440×900，改版后的界面）

环境：主检出目录的后端以演示模式启动（`LLM_MODE=demo`，读现有演示数据，未跑迁移、未导入），本工作树的 Vite 开发服务器；演示账号 `demo_student` / `demo_teacher`；演示课程 64 个知识点、71 条关系。

| 项 | 结果 |
| --- | --- |
| 学生页 `/` 聚焦搜索、`F` 适应画布 | 通过（`F` 后缩放 0.2） |
| 输入“队列” | 画布仍显示 64 / 64，命中 12 个，候选 8 条，地址出现 `q` |
| 回车 ×2、Shift+回车 ×2 | 计数 2 / 12 → 12 / 12，预览卡随之切换，候选收起 |
| 由地址恢复 `q` 与 `type=example` | 关键字回填，显示 63 / 64，图例提示“已隐藏 1 类” |
| 打开详情 | 地址出现 `kp` |
| 地址里放不存在的 `kp`、`ch` 与 `view=cards` | 给出“不在当前发布版本”提示，无报错，地址清理为 `?view=cards`，列表视图生效 |
| 学生页面板宽度 | 调到 29% 后重新打开仍为 29% |
| 教师页 `/`、输入“队列”、回车 ×3 | 显示 64 / 64，计数到 3 / 12，焦点始终在搜索框 |
| 教师页面板宽度 | 调到 380px 后重新打开仍为 380px |

实走发现并已修的两处：

1. **缩得很小时定位看不清**：按 `F` 后缩放 0.2，搜索定位只居中不放大。改为搜索定位时低于可读缩放（0.9）先放大（`lifecycle.focus(kpId, { readable: true })`，只有学生页搜索定位传这个选项；教师页总览模式原本就会放大）。
2. **教师页回车后焦点被抢走**：详情（`KnowledgeDetail`）与一直挂载的节点编辑器（`NodeEditor`）在载入新知识点后都会把焦点移到标题，导致无法连续按回车。新增 `composables/searchFocus.ts`，焦点在搜索框里时两处都不移动焦点。

实走中看到但未处理：搜索框 280px 加上原生清除按钮、计数和两个箭头后，输入区约 114px，短关键字够用，长关键字会被遮住一部分。

### 未验证

- 读屏对 `combobox`/`listbox` 的朗读；“搜索中不抢焦点”后读屏用户听到的是搜索旁的位置文字而不是知识点名称，未用读屏确认是否够用。
- Firefox、Safari（只在内置 Chromium 里走过）；`/` 与 Firefox 快速查找是否冲突。
- 淡化在节点更多的课程里的观感；窄屏（<960px）下搜索框与候选浮层。
- 真实拖动分隔条（实走用的是键盘事件）。
- `verify.sh full/integration` 的后端与集成部分（合入的分支含后端改动，本任务没有跑它们）。

## 风险与已知限制

- 地址写回与问答链接 `?kp=&v=` 的处理靠 `handledLink` 互相避让：页面自己写回的地址预先登记为“已处理”。如果以后改动链接侦听的键格式，两处要一起改。
- 由地址恢复 `ch` 时只恢复章节外框与淡化，不保证镜头适应到该章（画布此时可能还没建好，`fitTo` 在建图前调用会被忽略）；同时有 `kp` 时镜头聚焦到知识点。
- 每次按键都会 `router.replace` 一次（写 `q`）。目前没有看到性能问题，但未在低端设备上测过。
- 教师页的“位置计数”在确认框被取消时仍会前进一位（选中没变，计数变了）。
- 教师页没有候选浮层和“上一个”，也没有把视图写进地址。

## 回滚

还原本任务的改动即可（未提交时 `git checkout -- <上表文件>` 并删除新增文件）。没有数据迁移；`localStorage` 里的两个键残留无害。

## 下一步

1. #342 的 CI 通过后合入 main。
2. 用户视觉签收；决定搜索框是否加宽。
3. 本批明确不做、留给后续批次：镜头位置写入地址、教师页视图写入地址、拼音/模糊匹配、搜索定义正文、命令面板。

## 与 main 合并后的补充（2026-11-11）

- OPT-06D 把学生页的画布数据与面板逻辑拆到了 `useStudentGraphPresentation` / `useStudentGraphPanel`。本任务相应改接：前者新增可选参数 `matchedKpIds`（搜索命中），后者读写面板宽度偏好；页面不再直接做这两件事。
- `tests/INDEX.md` 登记了 `tests/frontend/graph-find.test.ts`（OPT-04 的索引校验要求）。
- 合并后的验证：`scripts/verify/frontend.sh full` exit 0（83 文件 / 1414 条）、`./scripts/verify.sh` exit 0、`python3 -m pytest tests/tooling/test_test_index.py -q` 1 passed。**合并后没有重新做浏览器实走**：实走是在合入 OPT-06 之前的代码上做的，拆分后的接线只有自动化测试覆盖。
