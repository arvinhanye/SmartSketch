# 学生工作区与教师预览交接

日期：2026-10-08；负责人：Codex；分支：codex/ui-polish-model-discovery。

## 交付

- StudentGraphView：默认侧栏 25%，拖动/键盘调宽，280px 面板下限与 640px 画布下限；窄屏保留抽屉。分隔条有读屏名称、百分比与键盘焦点；双击恢复默认。
- 学生右上角按钮及地图/缩放按钮增加原生延迟悬停说明。共享 GraphCanvas 仅 student audience 获得新增 title，教师控件不变。
- 问答内容区域使用浅色局部 tokens，正文、代码、出处、输入框和错误提示一致；导航仍沿用公共暗色外壳。
- 教师图谱独立预览：`.local-run/teacher-graph-preview/desktop.png` / `index.html`（忽略的本地文件），顶部紧凑工具条、宽画布、右侧详情。预览节点/文案仅排版示意，实际教师页面未改。
- 后端/API/图数据/发布流程未修改。

## 验证

- 调宽回归先 RED（缺少 separator），后 GREEN。H11 + app-graph-shell：52 PASS。
- student-graph-workbench、graph-workbench-components、redesign-chat、chat-send-lock：32 PASS。首次并发运行有一次 5s 超时，独立完整重跑四个文件全部通过；未修改超时设置或删除测试。
- npm run type-check、npm run build PASS；原有构建分块体积提示仍存在。
- scripts/verify.sh basic PASS：契约生成/漂移、25 项负向门禁和契约回归。
- 实际已发布课程以学生账号只读检查 1440/1280/390px：title 完整、拖动改变画布宽度、边界不低于 640px、键盘边界与双击恢复、手机抽屉、问答浅色、无溢出/运行错误 PASS。
- 假 API 问答 1440/390px：引用打开出处、代码对比度 >=4.5、资料未覆盖与服务错误分别显示 PASS；没有消费真实问答模型或改变课程资料。

## 保存与范围

仅提交本任务源码、测试、规格和交接；运行文件/截图/密钥/日志不入 Git，不推送。需回滚时使用本任务提交的反向补丁，不重置工作区。教师布局等待用户对预览的反馈后才实现。
