# 教师图谱编辑视口修复

负责人：Codex；日期：2026-10-08；分支：codex/ui-polish-model-discovery。

## 交付与范围
仅修复教师图谱编辑页视口及用户指定的搜索栏、左侧详情/编辑排版。搜索与筛选横排，高级筛选浮层；左侧面板独立滚动，鼠标拖动分隔条或方向键、Home/End调整宽度。保留全部字段、草稿选择、未保存修改确认、关系/新建功能与现有图谱绘制/导航/页面标题。学生页面和后端/接口/数据均不修改。

## 根因与实现
自动高度网格行被长表单撑高，G6测量该高度后生成的画布参与父级高度计算，形成关闭后仍保留长高度的反馈。仅教师工作区约束100dvh，内部网格行minmax(0,1fr)，画布flex basis为0、舞台高度100%；面板overflow-y:auto。G6原有ResizeObserver继续跟随尺寸变化，不修改图谱引擎。

默认左栏360px，桌面限制280–640px且为画布保留至少360px。宽度由容器观察器重新约束；组件卸载断开观察器；窄屏沿用上下排列。工具栏compact为显式选项，其他调用保留默认。

## 验证
- 实际课程1440×900 RED：初始页面1052px，编辑1438px，关闭1437px；地图下沿1384px。GREEN：页面900px、画布449.53px，三状态相同，地图下沿847px。
- npm test -- --run ../../tests/frontend/h05.test.ts ../../tests/frontend/h07.test.ts ../../tests/frontend/h14.test.ts：153 PASS。首次同时运行门禁/测试有一个既有加载态测试超时；独立重跑及最终组合重跑全部通过。
- npm run type-check、npm run build：退出0。构建仍提示既有chunk大于500kB。
- scripts/verify.sh basic：退出0，Scaffold verification passed。
- tests/frontend/teacher-viewport.browser.cjs：独立假API浏览器回归，1920×1080、1440×900、1366×768、1024×768、390×844全部通过。放大textarea至1400px验证长内容不撑高；打开/关闭、内部滚动、鼠标拖动、键盘上下限、窗口重设、筛选浮层、未保存确认与控制按钮边界均检查。只允许GET，不写真实图数据。
- 同五尺寸真实示例课程只读检查全部通过，63节点70关系保持。
- git diff --check通过。

浏览器回归运行方式：先启动Vite，设置E2E_BASE_URL；使用可用的playwright包，必要时以PLAYWRIGHT_MODULE指定绝对模块路径、PLAYWRIGHT_CHROMIUM_EXECUTABLE指定浏览器，再运行node tests/frontend/teacher-viewport.browser.cjs。运行证据和截图保存在忽略的.local-run目录。

## 保存与回退
只保存本次文件到本地Git，不推送。需要回退时对该提交执行git revert；不涉及数据库迁移或后端回退。
