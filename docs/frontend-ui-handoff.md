# 智绘学途前端 UI 升级交接文档

> 写给接手的人（前端、设计、测试、产品均可读）。读完这一份，应能回答：参考了哪些软件、设计方案是什么、现在做到哪、项目边界在哪、接下来怎么继续。细节都有指向原始文档的链接；本文不替代规格、计划和交接记录。
>
> 状态截至 **2026-10-07**。分支 `claude/smartsketch-frontend-init-0d2af9`，基线 `main@bdb89c4`，对应 [Draft PR #321](https://github.com/arvinhanye/SmartSketch/pull/321)（未合并，HEAD `ab60183`）。

> **2026-10-08 本地实施补充**：`codex/courses-model-settings-ui` 已完成课程/模型设置及剩余业务页面视觉改版，尚未提交/推送。以下 2026-10-07 状态为历史基线；当前交付和未完成路线图项见 [课程与设置交接](handoffs/codex-courses-model-settings-ui.md)、[剩余页面交接](handoffs/codex-remaining-pages-ui.md)。

## 1. 一页概览

- **在做什么**：把前端的视觉与交互整体升级为「Linear 式暗色应用外壳 + Kumu 式浅色图谱画布」。原因：原界面信息层级松散、入口多、有「AI 味」、部分文字没有样式，约 100 个节点时图谱标签不可读。
- **怎么做**：渐进式升级，不是重写；**一次只改一个页面**。先做「学生图谱页」作为样板（已完成并开了 PR），验收后再按计划推广到其余页面。
- **做到哪了**：样板页已实现并本地验收（Draft PR #321）。其余页面的推广**只有计划，没有开工**（见 §6、§9）。
- **边界**：只改前端的视觉与交互；不改后端、接口契约、数据库、业务规则（见 §2）。
- **接手后第一步**：读 §8，确认基线命令，再读第二批计划，从阶段 R1 开始。

## 2. 项目与边界

### 2.1 产品是什么

智绘学途是面向高校课程的 AIGC 知识图谱构建与学习导航系统。教师把课程资料（PDF/DOCX/TXT/Markdown）生成、审核、发布为课程知识图谱；学生浏览图谱、标记掌握进度、获得可解释的学习路径，并得到带出处的课程问答。完整定义见 [`docs/product.md`](product.md)，技术边界见 [`docs/architecture.md`](architecture.md)。

技术栈：前端 Vue 3 + TypeScript + Vite + AntV G6 5.1.1（仅 2D 图谱）+ Pinia + Vue Router；后端 Python + FastAPI；数据 Neo4j + SQLite。

### 2.2 前端 UI 升级的范围

| 在范围内 | 不在范围内 |
| --- | --- |
| 页面视觉、布局、响应式（1440/1280/768/390 宽）、动效、可访问性（键盘、焦点、对比度、减少动效） | 新业务流程、新接口字段、数据模型、数据库、后端代码、`src/contracts/` |
| 图谱画布的可读性（标签、缩放、布局、淡化、小地图、局部视图、章节聚焦） | 3D 图谱、跨课程知识融合、生产级 SSO、移动端原生应用、多租户计费 |
| 通用样式体系（tokens、通用组件类） | 自动出题、撤销/重做、批量框选/套索、保存「场景」（设计时已明确不做） |
| 既有页面逐页重做（见 §6 的阶段） | 任何需要「新数据」才能做的展示（见 §7 的「第二批外」） |

### 2.3 必须保持的业务红线（任何 UI 改动都不得破坏）

- 学生掌握状态：**服务端确认前不显示成功**；标记后推荐刷新；推荐的 `reason` 取自服务端。
- 问答：每个答案必须带来源（文档/页码或章节）；资料不足返回 `not_covered`，并**与服务错误分开显示**。
- 关系类型仅 `CONTAINS`、`PREREQUISITE`、`RELATED_TO`、`EXAMPLE_OF`；`PREREQUISITE` 必须是有向无环图，方向要清楚。
- 课程隔离；教师审核与发布规则；长耗时处理必须是可查询进度的任务。
- 个人模型凭据：服务端加密存储，不进日志、仓库和前端持久存储（ADR-080）。
- 既有 `data-test` 钩子必须保留（测试与端到端依赖它们）。

### 2.4 工作规则（继承 `AGENTS.md`，人和 Agent 都适用）

- 开工前读 `AGENTS.md`、`docs/tasks.md` 与相关规格；在 `docs/tasks.md` 认领任务。
- 先写失败测试，再实现；既有断言只在「样式/结构/文案随设计变化」处更新，并写明原因，**不放宽、不删除**。
- 不新增依赖、不引入 UI/图标库（图标用内联 SVG 组件 `AppIcon`）。
- 不提交密钥、真实课程资料、构建产物、数据库文件。
- 提交、推送、开 PR 只在负责人明确指示后做；不用破坏性 git 命令。
- 完成任务时：更新 `docs/tasks.md`，运行 `./scripts/verify.sh` 与相关测试，写 `docs/handoffs/<agent>-<task>.md`。

## 3. 前端参考了哪些软件

只借鉴设计思路，不复制品牌、文案和图形；Bloom 部分的行为描述来自截图标注，未在其软件里逐一验证。

| 参考 | 用在哪里 | 借鉴的点 |
| --- | --- | --- |
| **Linear** | 全站暗色外壳、课程列表、设置页、教师侧列表/表格 | 暗色应用壳（顶栏 + 窄图标栏）；行式列表、整行可点、状态徽标；设置页分区；克制的强调色与动效 |
| **Kumu** | 图谱浅色画布与内容表面 | 浅色、高可读的工作区；节点与关系用线型和图例区分 |
| **NotebookLM** | 课程问答（计划中） | 对话居中、来源是一等公民：行内引用角标 → 来源面板 |
| **Neo4j Bloom** | 图谱页、教师图谱 | 搜索、带计数的图例、小地图；不让用户同时面对整张图（分级显示） |
| **Linkurious** | 教师图谱页（计划中） | 左面板页签（详情/编辑/关系）、右侧编辑工具组、「有未保存修改」标记 |
| **Obsidian** | 图谱页、教师图谱 | 悬停时强淡化（非相关节点退后）、局部图（只看相邻）、章节/目录作为常驻导航 |

## 4. 设计方案

完整规格：[`docs/superpowers/specs/2026-10-06-graph-workbench-design.md`](superpowers/specs/2026-10-06-graph-workbench-design.md)。本节是摘要。

### 4.1 视觉体系

- **两个表面**，用 CSS 变量命名空间隔离，**不改全局 `--color-*`**：
  - `--ss-*`：暗色应用外壳（背景 `#101114`、面板 `#18191D`，主按钮 `#5B5BD6`，暗底链接与焦点 `#B1ACFF`）。
  - `--gw-*`：浅色图谱工作区（画布 `#F4F5F7`、面板 `#F8F9FB`，强调/选中/先修 `#5145CD`，控件边界 `#747A87`）。
  - 数值在 `src/frontend/src/styles/tokens.css`；G6 画布读不到 CSS 变量，同样的数值写在 `src/frontend/src/graph/theme.ts`，由测试保证两处一致。
- **字体**：中文系统无衬线栈（PingFang SC、Hiragino Sans GB、Microsoft YaHei、system-ui）。
- **形状**：圆角 6/10/14px；控件 ≥36px（触屏 ≥44px）；不用渐变、玻璃模糊、霓虹、发光。
- **对比度**：文字 ≥4.5:1，必要图形与控件边界 ≥3:1，**按页面实际渲染色计算**；装饰分隔线不承担识别。唯一例外：悬停强淡化期间非相关元素（瞬时状态，规格 §3.4a 有记录）。
- **动效**：统一 `cubic-bezier(0.2, 0, 0, 1)`；只动画 `transform` 与 `opacity`；`prefers-reduced-motion` 下关闭位移、缩放、循环动画；镜头动画 240ms。

### 4.2 图谱画布的元素编码（不只靠颜色）

| 信息 | 表达方式 |
| --- | --- |
| 知识点类型 | 5 种填充色 + 节点内单字（概/理/式/法/例）+ 图例带完整名称与计数 |
| 掌握状态 | 角标 ✓（已掌握）/ ◐（学习中）+ 文字「未学习」「学习中」「已掌握」 |
| 关系类型 | 线型 + 颜色 + 箭头：包含（实线灰）、前置（实线靛紫+箭头）、相关（虚线、无向）、应用实例（点线） |
| 选中 / 预览 | 2.5px 靛紫外环（与先修边同色，靠形状区分）、邻居与相关边强调、相关边显示关系名 |
| 非相关内容 | **不用整体透明度**：标准淡化（填充 `#ECEEF2`、边框 `#7F8695`、标签保留）用于预览/选中；强淡化（近底色小点、隐去标签）仅用于鼠标悬停 |

### 4.3 学生图谱页的交互

- **单击节点 = 预览**（高亮 + 底部预览卡，侧栏不变，镜头不动）；**再次单击同一节点或点「查看详情」才打开详情**；详情已开时单击另一节点只预览新节点。点空白 / Esc / 预览卡 ✕ 取消预览。
- 搜索回车 = 定位并预览；面板、列表、推荐、关联知识里的选择与问答链接 `?kp=` 是显式选择，直接开详情。
- **悬停**：悬停节点与直接相邻保持清楚，其余强淡化，移开 60ms 后恢复，触屏无此效果。
- **节点多时的五层对策**（借鉴 Bloom/Obsidian）：① 标签分级——缩小时标签放大保持约 13px，按优先级贪心排布避让，并避开工具栏/图例/小地图等浮层，只有预览/选中的节点强制显示标签；节点、线、箭头有屏幕尺寸下限；② 小地图；③ 「只看相邻」局部视图（1/2 跳，可恢复）；④ 图例即筛选（关系与类型带计数，隐藏状态可见、可恢复）；⑤ 章节分区布局 + 章节跳转（整章范围适应、章节外框、淡化其他章节、跨章长线弱化）。
- **布局**：全部关系都参与布局时画布会被拉成 5:1 长条（96 节点适应一屏缩放 0.10）；改为「章节分区 + 紧凑间距」，只由前置与包含决定层级，每章单独布局（同样数据缩放 0.35，每章可在一屏内看全）。
- **左面板**：未选中显示课程说明、进度、下一步推荐；选中后原位切换为知识点详情（保留可折叠的「下一步推荐」摘要，保持「标记→推荐刷新」流程）。宽屏占工作区 35%，窄屏（容器宽度不足）覆盖抽屉占 90%；**不使用内部滚动条、不裁切**，长内容整页滚动。按**容器宽度**而不是视口宽度判断并置/覆盖。
- **外壳**：暗色顶栏（面包屑、用户、退出）+ 64px 图标栏（可展开显示名称）；<1024px 改为抽屉。

### 4.4 其余页面的设计方向（已定，尚未实现）

详见 [`docs/superpowers/plans/2026-10-07-ui-rollout-batch2.md`](superpowers/plans/2026-10-07-ui-rollout-batch2.md)。要点：

- **课程列表/课程主页**：行式列表；主页用「下一步」卡 + 按角色分组的入口卡，替代现在堆叠的 6 条文字链接。
- **模型 API 设置**：状态卡 / 连接配置 / 操作栏三分区；「关闭模型思考」改开关；密钥安全约束写成强制项。
- **课程问答**：**暗色页**；对话居中、来源面板、行内引用角标；流式 / 「资料未覆盖」/ 出错三种状态在视觉上必须可区分。
- **教师图谱**：复用画布增强；单击直接选中编辑（不经预览卡）；新增「新建关系」模式；左面板页签「详情｜编辑｜关系」；草稿的审核状态编码保留。
- **资料 / 审核与发布 / 成员**：Linear 式列表、表格、收件箱两栏。
- **认证页**：已由前人做过（登录页视口布局、可关闭的路由提示、8 组动态装饰图谱，`prefers-reduced-motion` 下停用）；本次只做色板与字体对齐，**这些行为不得回退**。

## 5. 技术实现地图（样板页已落地的部分）

| 位置 | 内容 |
| --- | --- |
| `src/frontend/src/styles/tokens.css`、`graph-workspace.css` | 两套 tokens；工作区与外壳样式（选择器统一带 `.graph-workspace` / `.app--graph` 前缀） |
| `src/frontend/src/graph/` | 画布内核（纯函数 + 适配）：`theme`（G6 字面量）、`scale`（语义缩放）、`labelPlan`（标签排布）、`fit`（视口适配）、`chapterLayout`（章节布局）、`focusStates`（预览/悬停/章节状态）、`presentation`（展示数据）、`enhancer`（把上述接进 G6）、`lifecycle`（G6 生命周期，带可选的 `enhance`/`positions`）、`obstacles`（浮层障碍物注册）、`adapter`（图谱交换格式→G6 数据） |
| `src/frontend/src/components/` | `GraphCanvas`（`enhanced` 开关）、`GraphSidePanel`、`GraphLegend`、`GraphPreviewCard`、`LocalViewBar`、`ChapterMenu`、`GraphOverlay`、`AppTopbar`、`AppIcon` 等 |
| `src/frontend/src/composables/` | `usePreviewFocus`（单击预览/再次单击打开）、`useLocalView`、`useGraphLayout`、`useReducedMotion` 等 |
| `src/frontend/src/views/StudentGraphView.vue` | 学生图谱页装配（保留全部 `sg-*` 等钩子） |
| `src/frontend/src/App.vue` | 应用外壳；目前只有学生图谱路由用暗色外壳，其余路由仍是旧左侧栏 |
| `tests/frontend/graph-*.test.ts`、`student-graph-workbench.test.ts`、`app-graph-shell.test.ts` 等 | 样板页新增测试（纯函数、画布、页面、外壳） |
| `src/frontend/preview/` | **隔离预览**（合成数据、不请求后端、不进构建）：`graph-workbench.html` 是设计预览；`prod.html` 把生产页面挂在合成数据上用真实 G6 目测。未跟踪，验收完成后删除 |

分层规则（`.claude/rules/frontend.md`）：`views/` 路由级页面、`components/` 可复用 UI、`composables/` 状态与副作用、`api/` 只封装 HTTP/SSE；G6 数据由适配层转换，组件不直接依赖后端原始响应；图谱至少支持缩放、拖拽、节点详情、关系图例和按关系筛选；空态、加载态、错误态必须覆盖。

## 6. 做到哪里了

### 6.1 已完成：样板页（UI-GRAPH-PILOT-01）

- 17 个任务中任务 1–16 已实施，加上用户批准的两处局部修正（学生详情的自适应面板、去掉重复关闭叉）。**用户已本地验收并开了 Draft PR #321。**
- 自动化（2026-10-07，Codex 记录）：`type-check` 通过；前端全量 **57 个文件 / 1144 条**通过（基线 38 / 934）；`build` 通过（G6 所在 chunk >500 kB 的提示是既有现象）；`./scripts/verify.sh` 基础档通过。
- 相关记录：规格、实施计划、ADR-091（`docs/decisions.md`）、交接 `docs/handoffs/claude-ui-graph-pilot-01.md`、`codex-ui-graph-pilot-01.md`、`claude-ui-graph-pilot-01-to-codex.md`。

### 6.2 样板页的未验证项（不阻塞第二批，但必须收口）

- 0.9 可读缩放（原 0.7）的用户目测确认；
- 真实实例上的修改前后截图（登录凭据问题尚未解决，**不要猜测或重置账号**）；
- 端到端（Playwright，需要后端与数据）；
- 画布内像素色的对比度采样、完整键盘 Tab 顺序、200% 缩放、真实「减少动态效果」；
- `process-parallel-edges` 与曲线边在真实多关系数据上的相互作用；章节很大（>20 个）、无章节、全孤立的草稿图；
- `./scripts/verify.sh full`：前端部分通过，**后端部分在本机因 argon2 `InvalidHashError` 收集失败**（环境问题，非前端），需在可用环境重跑；
- PR #321 仍是 Draft；`src/frontend/preview/` 尚未删除；`EXAMPLE_OF` 的方向契约未明文，图例未写方向。

### 6.3 第二批：其余页面（只有计划，未开工）

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| R1 | 外壳通用化（所有登录后页面共用暗色顶栏+图标栏）、浅色内容表面、通用件，并回归样板页遗留项 | 未开始 |
| R2 | 课程列表与课程主页（`CoursesView`） | 未开始 |
| R3 | 模型 API 设置 | 未开始 |
| R4 | 课程问答（暗色页） | 未开始 |
| R5 | 教师图谱页（含编辑面板） | 未开始 |
| R6 | 资料、审核与发布、成员 | 未开始 |
| R7 | 认证页对齐 + 收口（删旧样式、旧变量） | 未开始 |

优先级依据：用户最初指定「我的课程 / 模型 API 设置 / 课程列表」优先，所以 R2、R3 紧跟 R1；R3、R4、R6 彼此独立可并行；登录页风险最高放最后。每个阶段一条叠加分支、一个 Draft PR，开工前先写代码级计划。**这份计划是路线图，不是可直接执行的代码级计划。**

## 7. 第二批之后仍未做的（需要新数据或后端先行）

- 课程主页的进度、待审核数摘要（现有接口不提供）；
- 问答页的示例问题（没有内容来源）；
- 教师图谱页的「版本」页签（版本与发布目前在审核页）；
- 学生详情里「掌握状态放在定义之后」、关联知识线型样例（需先给 `KnowledgeDetail` 加插槽）；
- 卡片视图下的章节滚动、图谱页「目录」页签；
- 教师图谱编辑面板在无右侧栏布局中的最终位置（第二批 R5 已给默认方案）。

与后端相关但不属于前端范围的待办（`docs/tasks.md` 中 OPEN）：抽取准确率与耗时、问答比较题截断、PDF 真实复测等。项目整体的技术冻结尚未执行。

## 8. 怎么接手

### 8.1 环境与命令（在仓库根目录）

```bash
npm ci --prefix src/frontend                       # 安装锁文件内依赖
npm --prefix src/frontend run dev                  # 开发服务器（Vite）
npm --prefix src/frontend run type-check
npm --prefix src/frontend run test -- --run        # 前端全量；基线（样板页后）57 个文件 / 1144 条
npm --prefix src/frontend run build
./scripts/verify.sh                                # 基础门禁；再按需 full / integration
```

Node 22.22+ 或 24.15+；后端与运行手册见 [`docs/runbook.md`](runbook.md)。本机若默认 Python 是 3.11，`verify.sh` 可能缺 `yaml`/`pytest`，可用已有的 3.13 解释器做命令级 PATH 覆盖（不要安装新依赖）。

看真实 G6 渲染（合成数据，不连后端）：启动 Vite 后打开 `http://localhost:<port>/preview/prod.html?size=100`（`?size=30`、`?profile=pdf` 可切换）。内置浏览器的已知现象：窗格宽度变化会清掉自定义视口；后台页不派发 `ResizeObserver`（重新加载即可）；模拟视口大于窗格时截图会被缩小。

### 8.2 推荐的第一步

1. 读本文，再读：`AGENTS.md`、`docs/tasks.md` 的 UI-GRAPH-PILOT-01 段、规格、第二批计划、`docs/handoffs/codex-ui-graph-pilot-01.md`（含全部踩坑）。
2. 确认基线命令结果与 PR #321 状态；样板页是否已被用户批准合并。
3. 在 `docs/tasks.md` 认领 R1（建议任务 ID 前缀 `UI-ROLLOUT-`），从 #321 的分支拉新分支，写 R1 的代码级计划，经负责人确认后执行。
4. 每个页面重复固定流程：认领 → 代码级计划 → 先写失败测试 → 实现 → 验收（四个宽度 × 各状态 × 键盘 × 对比度 × 前后截图）→ 交接 → 负责人确认 → 下一页。

### 8.3 遇到这些情况先停下来问负责人

需要新数据、新接口或新业务；既有测试必须放宽才能通过；既有 `data-test` 钩子必须变更；用户可见文案要改；需要新依赖；任何要提交/推送/开 PR 的操作；需要真实实例或凭据的验收。

## 9. 已知坑（别再踩）

- **G6 5.1.1**：`hull` 插件不能移除（销毁会抛），渲染后要主动 `drawHull()`；节点标签开关是布尔 `label`（`labelVisibility` 无效）；`getZoom()` 在初始化/销毁中会抛，需安全读取；小地图有延迟渲染，销毁图实例要延后并吞掉拒绝；`auto-adapt-label`、`fix-element-size` 在 100 节点下不可靠，所以标签排布是自研的。
- **样式**：全站旧 `button:hover:not(:disabled)`、`.app-main > section` 等规则特异性低但无处不在，新样式必须带作用域前缀并显式覆盖；`:inert` 关闭写 `true`、打开写 `undefined`，不写 `false`（jsdom 会渲染成字符串属性）；`section.recommendations` 才压得过组件自带 scoped 样式。
- **测试**：章节布局是异步算的，画布不会在一次 `flushPromises()` 后就建好，要用 `vi.waitFor`；画布位置从空到有只由 `ready` 建图，不要在位置监听里重复建（会建两次并丢聚焦）。
- **文案**：推荐编号「1. 名称」是有意设计（L14），不是文本污染；掌握状态「未开始」已改为「未学习」。
- **设计**：强淡化只用于悬停；预览/选中不要用整体 `opacity`；不要统一缩小字体、不要删除关系来「减负」。

## 10. 文档索引

| 文档 | 作用 |
| --- | --- |
| [`AGENTS.md`](../AGENTS.md)、[`CLAUDE.md`](../CLAUDE.md)、`.claude/rules/*.md` | 共同工作契约与前端/后端/测试规则 |
| [`docs/product.md`](product.md)、[`docs/architecture.md`](architecture.md)、[`docs/decisions.md`](decisions.md) | 产品、架构、ADR（UI 相关：ADR-091） |
| [`docs/tasks.md`](tasks.md) | 任务看板（UI-GRAPH-PILOT-01 段含第二批链接） |
| [`docs/superpowers/specs/2026-10-06-graph-workbench-design.md`](superpowers/specs/2026-10-06-graph-workbench-design.md) | 图谱工作台设计规格（tokens、px 规范、交互、动效、验收） |
| [`docs/superpowers/plans/2026-10-07-graph-workbench-pilot.md`](superpowers/plans/2026-10-07-graph-workbench-pilot.md) | 样板页的 17 任务代码级计划（含逐字代码，已执行） |
| [`docs/superpowers/plans/2026-10-07-ui-rollout-batch2.md`](superpowers/plans/2026-10-07-ui-rollout-batch2.md) | 第二批（R1–R7）推广计划 |
| `docs/handoffs/claude-ui-graph-pilot-01*.md`、`codex-ui-graph-pilot-01.md` | 样板页的设计过程、实施记录、踩坑与验收证据 |
| `docs/handoffs/codex-ui-login-01.md`、`codex-ui-auth-art-02.md`、`codex-ui-auth-motion-03.md` | 认证页既有 UI 工作（第二批不得回退） |
| [`docs/runbook.md`](runbook.md) | 运行与验收手册 |

## 2026-10-08 用户确认：登录页方案 D

用户经过四版预览确认“资料 → 展开书页 → 知识关联 → 学习路径”的原创 SVG 插画与左右分栏布局，并要求先做前端、不改后端。此指示覆盖 R7 对登录页八组旧装饰图的保留限制；注册页沿用 AuthLayout，旧运动逻辑和减少动态/窄屏行为保持。登录页使用独立 LoginLayout，不启用装饰动画，窄屏隐藏插画并保留表单滚动。详见 `docs/handoffs/codex-login-editorial.md`。
