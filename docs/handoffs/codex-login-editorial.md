# 登录页原创插画与排版交接

负责人：Codex；日期：2026-10-08；分支：codex/ui-polish-model-discovery。

## 交付与边界

用户确认方案 D 后实施前端。LoginLayout 单独承载深色双栏、资料/展开书页/知识节点/学习路径的原创静态 SVG；LoginView 使用既有请求逻辑，增加本地密码显隐、明确字段与注册入口排版。ui.css 只针对带新布局的登录顶栏调整。注册页仍使用原 AuthLayout，不改变运动逻辑或其减少动态偏好支持。

用户明确确认新插画，覆盖旧 PR #322 R7 对登录装饰图的默认保留要求，已同步身份规格与 UI 交接。无后端、契约、依赖、API、会话、数据库或真实课程资料变化，未发真实模型请求。插画 aria-hidden、无动画，窄屏隐藏；矮屏表单区域允许滚动。

## 验证

- 新密码显隐回归先 RED（按钮不存在），后 GREEN；按钮不提交口令，名称/pressed 状态明确，登录时恢复隐藏，失败后清空口令。
- `npm test -- --run h13.test.ts adr079.test.ts auth-graph-motion.test.ts`：47 PASS。旧图谱布局/运动测试改为直接验 AuthLayout，以保留注册装饰行为覆盖；登录业务断言保留。
- `npm run type-check` 与 `npm run build`：PASS。构建仍有现存大包提示，无新增依赖。
- `scripts/verify.sh basic`：PASS（生成一致、25 项负向门禁与契约回归）。不将 basic 写为 full 或 integration。
- 真实前端浏览器检查：2559×1284、1440×900、1280×800、768×900、390×844、390×460、1024×500；无横向溢出，表单可达，模拟 401、口令显隐/清空、错误反馈及注册跳转通过；无浏览器页面错误。
- 浏览器仅拦截假登录失败响应，不向真实后端提交账号或口令。截图与检查脚本在不提交的 `.local-run/login-implemented` 与 `.local-run/login-browser-check.cjs`。

## 保存与后续

修改前已确认工作树无业务变更，并创建备份分支 `codex/login-before-redesign-f54abfd` 指向 f54abfd。改后只提交任务源码、规格、测试和交接；不提交本地日志、预览文件或密钥，不推送。本地前端入口 http://127.0.0.1:5322/ ，后端未修改。
