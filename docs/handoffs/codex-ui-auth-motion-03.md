# UI-AUTH-MOTION-03 交接：认证页动态图谱

- 交付：8 组知识图谱在左侧独立 SVG 绘图区内持续移动，各组初始尺寸、速度和方向随机；尺寸轻微周期变化，旋转限制在 ±22°；相遇时按法向速度反弹，触及绘图区边界时折返。图谱仍为读屏隐藏的纯装饰，标签不可选中。
- 文件：`src/frontend/src/components/AuthLayout.vue` 管理实例与动画帧；`authGraphMotion.ts` 负责运动和碰撞解算；`tests/frontend/auth-graph-motion.test.ts` 与 `h13.test.ts` 验证行为。
- 规格与架构：`specs/identity-access.md`、`docs/architecture.md` 已更新；接口、数据模型、环境变量及依赖未改变。
- 验证：物理单测覆盖位置、尺寸、旋转、边界和两图碰撞；前端全量测试 25 个文件、772 个用例通过，`npm run type-check`、`npm run build`、`git diff --check` 通过。浏览器观察到 8 组均移动且尺寸变化、初始尺寸有 7 种，图谱区域始终位于说明文字下方，720px 视口无页面纵向溢出。`./scripts/verify.sh` 已尝试，本机缺少 `openapi-typescript` 且临时子进程无法找到 `python3`，未能完成仓库级门禁。
- 风险：图谱碰撞时可能短暂靠近；动画仅更新 16 个 SVG 分组的 transform，并在减少动态效果、窄屏和组件销毁时停用。
