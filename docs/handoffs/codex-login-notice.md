# 登录提示浮动交接

日期：2026-10-08；负责人：Codex；分支：codex/ui-polish-model-discovery。

用户要求未登录提示浮动在欢迎回来上方，且不挤压下方页面。根因：App 主容器里的正常流 app-notice 占据高度。现 App 仅在登录路由把提示与关闭事件交给 LoginView；其他页面仍使用原提示。LoginView 的提示绝对定位在表单上方，保留 role=alert、关闭按钮及应用层关闭/路由重置行为。LoginLayout 始终保留对称安全留白，确保提示可见可操作且出现/消失时布局不变；窄矮屏继续内部滚动。无后端、接口、数据、依赖修改。

验证：浏览器原版关闭提示令标题上移 21.59px（RED）；改后 1440×900、1280×800、768×900、390×844、390×460、1024×500 六组标题/用户名输入框位移均 0px（GREEN），提示位于标题上方、关闭可操作、无横向溢出。探针不向后端提交口令。检查文件在不提交的 .local-run/login-notice-browser.cjs 与 login-notice-check/。

`npm test -- --run h13.test.ts adr079.test.ts` 44 PASS；`npm run type-check` PASS；`npm run build` PASS（原大包提示仍存在）；`scripts/verify.sh basic` PASS。不将 basic 冒充 full/integration。仅任务文件保存为本地提交，不推送；访问 http://127.0.0.1:5322/teacher 可检查守卫提示。
