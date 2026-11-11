# 交接：UX-REVIEW-DEDUP-01 疑似重复审核的对比与合并预览（前端）

- 日期：2026-11-11
- 负责人：Claude（只做前端）
- 分支 / 基线：`claude/ux-backlog-20261111` / `main@31a7e6c`
- 状态：实现与自动化验收完成；样式在临时预览页上看过；**没有连真实后端走过完整流程**；待用户视觉签收

## 背景与边界

用户反馈：疑似重复只能在纯文字列表里逐条确认，看不到图谱变化。用户确认了设计稿，并确认“审核页预览与图谱内查看两处都做、不做批量”。

**Codex 正在改进疑似重复的产生方式（规范化与消歧去重）。本任务不碰后端、契约和审核队列的数据形状**：`git status -- src/backend src/contracts` 为空。页面只消费 `candidates`、`similarity`、`reason` 和草稿图谱；未知的 `reason` 原样显示，相似度缺失时不显示。后端以后给出更好的候选，这套界面不需要改。

## 交付物

| 能力 | 行为 | 主要文件 |
| --- | --- | --- |
| 合并预览推算 | 按 ADR-047 第 3、6 条在前端推算合并后的局部图：改接、去掉两点之间的关系、「类型 + 起点 + 终点」相同的合为一条、别名并入、锁定；相邻知识点最多画 8 个 | `graph/mergePreview.ts`（新） |
| 小图 | 静态 SVG（不用 G6）：两个知识点居中，相邻知识点分上下两排；沿用图谱的类型填充色、单字标记和四类关系线型；改接的关系加向日葵黄底色 | `components/review/MergePreviewGraph.vue`（新） |
| 并排对比 | 两张卡片（名称、定义、类型、章节、别名、来源数、关系数），点卡片选保留对象；“合并前 / 合并后（预计）”两张小图；一行文字说明改接、去重、去掉、新增别名的数量 | `components/review/DuplicateCompare.vue`（新） |
| 审核页布局 | 桌面宽度下左窄栏放“低置信度关系”“孤立知识点”，右宽栏放“疑似重复”；窄于 1000px 纵向排列；文档顺序不变 | `views/ReviewView.vue`、`styles/ui.css` |
| 连续处理 | 在展开的条目上处理成功后自动展开原位置上的下一条；栏目顶部留本次处理记录 | `views/ReviewView.vue` |
| 键盘 | 有条目展开时 `M` 合并、`N` 不是重复、`→` `←` 切换；文本输入框内、带修饰键、有请求在途时不触发 | `views/ReviewView.vue` |
| 在图谱中查看 | 审核页链接带 `pair=a,b`；图谱编辑页高亮这两个知识点、其余淡化、镜头适应到它们，并有可关闭的提示 | `views/TeacherGraphView.vue`、`components/GraphCanvas.vue`（新增 `ready` 事件） |

## 接口 / 数据变更

- 后端、契约、数据库：无。
- 前端内部：`useReview` 新增返回值 `draftGraph`（原先只把草稿图用来取名称，现在整张保留）；`GraphCanvas` 新增 `ready` 事件（画布每次建好并画完第一帧）；教师图谱页新增地址参数 `pair`。
- 既有 `data-test` 钩子全部保留（`rv-merge`、`rv-merge-panel`、`rv-primary`、`rv-merge-summary`、`rv-merge-confirm`、`rv-merge-cancel`、`rv-not-duplicate`、`rv-item-error`、`rv-cycle`）；H09 原有 42 条用例未改动且全部通过。
- 流程变化：原来是“合并… → 选主知识点 → 确认合并”，现在“合并…”展开对比，主按钮直接写“合并到「名称」”。“取消”改叫“收起”。

## 验证

在工作树根目录执行（本机 `python3` 默认指向没装依赖的系统解释器，需要把项目虚拟环境放到 PATH 前面）：

```bash
export PATH="/Users/arvinhan/Desktop/SmartSketch-main/.venv/bin:$PATH"
scripts/verify/frontend.sh full     # exit 0：type-check 无错误；86 文件 / 1470 条通过；build 成功
./scripts/verify.sh                 # exit 0（basic）
python3 -m pytest tests/tooling/test_test_index.py -q   # 1 passed
```

- 新增测试：`tests/frontend/merge-preview.test.ts` 8 条（先写、确认因模块不存在而失败，再实现）；`tests/frontend/review-dedup.test.ts` 9 条（组件层）；`tests/frontend/h09.test.ts` 追加 7 条（页面流程）；`tests/frontend/h14.test.ts` 追加 3 条（`pair` 高亮）。组件与页面测试是实现之后补的。
- 样式检查：用临时预览页（示例数据 + 真实组件 + 真实样式，已删除、未提交）在 1440×900 下看过：松绿主题、保留卡片的选中态、两张小图、改接关系的强调色、切换保留对象后的变化都正常。期间发现并修掉一处：左栏两块之间被拉开一大段空白。

### 未验证

- **没有连真实后端走完整流程**：本机 Docker 未启动。合并成功后的自动前进、成环错误、图谱页 `pair` 高亮与镜头适应都只有自动化测试覆盖。
- **预览与服务端结果是否一致**：推算规则是读 ADR-047 写的，没有拿真实合并结果对照过。已知不体现的：不可见关系、来源迁移的去重、`RELATED_TO` 无向时两个方向是否算重复。
- 窄屏（<1000px、<640px）、读屏、Firefox / Safari。
- 相邻知识点很多、名称很长时小图的可读性（预览页里只试了 9 个相邻知识点）。

## 风险与已知限制

- 小图的上下排只按“是否有指向这两个知识点的关系”分，不做交叉最小化，关系多时线会交叉。
- “本次已处理”记录只在页面内存里，刷新即清空；它记的是页面发起并成功的操作，不是服务端审计。
- 键盘 `→` `←` 在焦点位于单选框时不触发（浏览器用方向键切换单选），这是有意的。
- 草稿图在合并后会随队列一起重新读取；如果重读失败，对比与预览沿用上一次读到的图，可能略旧。

## 回滚

还原本任务提交即可；没有数据迁移，没有本地存储键。

## 下一步

1. 启动 Docker 后在演示环境走一遍：合并一条、标记一条、触发一次成环、从审核页跳到图谱页。
2. 拿一次真实合并的结果对照预览，确认推算规则。
3. 与 Codex 的去重改进对齐：新的 `reason` 取值需要中文标签时，只需在 `DUPLICATE_REASON_LABELS` 里补。
