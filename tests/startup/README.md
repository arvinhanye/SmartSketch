# 启动器隔离验证

- `tests/startup/test_wizard_ui.py`：真实浏览器访问合成本机控制服务，验证 secret 清空、fragment 移除、存储禁用和模式文案。
- `tests/startup/test_release_smoke.py`：显式设置 SMARTSKETCH_STARTUP_SMOKE=1 与 STARTUP_TEST_BACKEND/FRONTEND（必须 smartsketch-startup-test- 前缀）后，在随机安装 ID 的新卷验证真实服务登录/注册/停启、两安装隔离、整组备份恢复。
- 冒烟使用 Go test 内独立 image adapter 将测试清单镜像映射到本轮本地测试镜像，并明确跳过发行 pull；不是匿名 GHCR 拉取、不可变镜像发行或正式包双击验收。
- 缺场景设置时 pytest 失败，不记 PASS；普通 Go unit suite 中三个 opt-in Docker 场景明确跳过，须单独记录。
- 无宿主 .env、业务库或真实课程资料。测试只使用字段格式合法的虚构向量配置，不上传/发布/问答，不发在线模型调用。清理由安装标签和项目标签共同核对后逐项删除本轮合成资源，禁止全局 prune。
- 开发者需 Go 1.26.8、Python 测试环境、根目录已有 Node Playwright 与浏览器、Docker Desktop。这些不是发行用户的宿主依赖。
