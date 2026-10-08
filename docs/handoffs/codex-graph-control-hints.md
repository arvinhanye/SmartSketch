# 图谱右下角按钮悬停说明

日期：2026-10-08；负责人：Codex。

教师图谱右下角的小地图/放大/缩小/适应画布按钮补齐原生title提示；学生原有提示保留。鼠标停留后浏览器显示功能名称，延迟由浏览器控制，小地图按钮名称随展开状态更新。仅GraphCanvas模板属性调整，没有后端、样式、图谱布局或按钮行为变化。

验证：graph-canvas-enhanced.test.ts 12项通过；type-check/build退出0（既有chunk大小提示保留）。真实教师demo_teacher与学生demo_student2页面的四个title均与无障碍名称一致，地图切换后title正确更新，无真实数据写入。原生提示由浏览器界面渲染，自动化检查验证title属性和状态更新。

基础门禁完成结果见docs/tasks.md。运行日志均在忽略的.local-run目录；此前11个改动提交和此次补充一起推送到codex/ui-polish-model-discovery，PR以#322的claude/ui-rollout-batch2-plan为基础。
