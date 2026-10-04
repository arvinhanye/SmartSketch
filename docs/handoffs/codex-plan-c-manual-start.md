# 修复版本的本机启动与人工检查（2026-10-04）

## 1. 使用哪份代码

**最新状态**：计划A/B/C及本轮验收修复已通过#317/#319/#318合入GitHub `main`，业务集成提交0436ff34。技术冻结尚未执行。推荐继续使用已经配置好的独立检查目录：

```bash
cd /Users/arvinhan/.codex/worktrees/plan-c-acceptance-review/SmartSketch
export PATH="$HOME/.docker/bin:$PATH"
git branch --show-current
```

本独立目录分支为 `codex/plan-c-acceptance-fixes`；代码已发布。不要在 Claude 工作区或只读测量 worktree 启动。主目录 `/Users/arvinhan/SmartSketch` 没有被自动更新：若需要使用主目录，先停止该目录旧服务、确认在main且无待提交变更，再执行 `git pull --ff-only`。这只同步代码，不会同步本独立目录的 `.env`、数据库或资料；新环境另按下节配置，已有业务库先备份并按迁移指引处理，不直接覆盖旧配置或更换已激活向量空间。

本目录已有本机依赖；先启动 Docker Desktop，等它就绪。依赖软链指向已有安装，暂时保留那些目录；应用启动时从本工作区的 `src/backend` 加载修复代码，不需要重新安装。

## 2. 首次配置（仅本目录的新环境）

本轮验证没有创建真实 `.env` 或业务库。先复制示例，已有文件时保留不覆盖：

```bash
cp -n .env.example .env
nano .env
```

**说明文档不是运行配置**：只在本目录根部 `.env` 填真实口令/key；不要把真实值写入本文件。每个同名设置只保留一行，直接替换示例文件原行，不要重复追加。`EMBEDDING_MODE=online` 是必填项；正式入口会强制 `LLM_MODE=personal`，仍建议 `.env` 与它保持一致。

修改/补充以下设置，`<...>` 由你在本机填写。不要复制测量区或旧业务环境的整份配置/数据库；不要把 key 发到聊天或提交 Git。

```dotenv
# 独立容器名、端口和本目录数据，避免碰到旧测量/发布环境
COMPOSE_PROJECT_NAME=smartsketch-c-acc-manual
NEO4J_HTTP_PORT=18590
NEO4J_BOLT_PORT=18591
NEO4J_URI=bolt://localhost:18591
NEO4J_PASSWORD=<自定至少8位的本机新库口令>
API_HOST=127.0.0.1
API_PORT=19010
DEMO_WEB_PORT=16083
WEB_ORIGIN=http://localhost:16083
SQLITE_URL=sqlite:///./storage/smartsketch.sqlite3
STORAGE_DIR=./storage

# 正式个人 API 模式，不是演示
LLM_MODE=personal
EMBEDDING_MODE=online
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_API_KEY=<在本机填写向量服务key>
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSIONS=1024
```

向量示例来自项目现有集成配置，不是这轮新测量；也可采用项目支持的兼容在线向量服务，维度需一致。当前架构中，**教师/学生各自设置生成模型 API，向量服务仍为部署级配置**。不要在本轮顺带变更已建库的向量模型/维度。

`AUTH_JWT_SECRET`、`MODEL_CREDENTIAL_KEY` 首次可保留为空，正式启动脚本自动在本机生成；生成后保存好 `.env`，不要每次重建或更换根密钥（旧个人模型配置会失效）。`LLM_API_KEY` 不用填：个人生成 API 在网页内分别设置。

若你终端已导出同名旧变量，脚本会优先使用它们。建议用下面清空继承配置的启动命令；不会把旧 Neo4j 地址或旧业务库带入。

## 3. 启动与登录

```bash
cd /Users/arvinhan/.codex/worktrees/plan-c-acceptance-review/SmartSketch
/usr/bin/env -i HOME="$HOME" USER="$USER" LANG=en_US.UTF-8 \
  PATH="$PWD/.venv/bin:$HOME/.docker/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
  PYTHONDONTWRITEBYTECODE=1 \
  /bin/bash ./scripts/start.sh
```

该入口强制个人 API + 在线向量模式，缺配置时提示原因，不回退到演示。它启动独立 Neo4j、迁移本目录新库、创建本机账号、运行 API/worker/前端；不自动导入演示课程。数据在本目录 `neo4j/data` 与 `src/backend/storage`，不是原测量库。

打开 **http://localhost:16083**。首次账号：

| 角色 | 用户名 | 首次默认口令 |
| --- | --- | --- |
| 教师 | `demo_teacher` | `smartsketch-demo` |
| 学生 | `demo_student` | `smartsketch-demo` |
| 另一学生 | `demo_student2` | `smartsketch-demo` |

用户名含 demo 不代表使用演示模型。账号存在时脚本沿用原口令，不重置；正式公开部署需另外处理账号口令、HTTPS 与生产配置，本页仅本机检查。

教师、学生各自在「模型 API 设置」填基址、密钥、模型并保存。支持该字段的模型，开启「关闭模型思考」以接近已测配置；不支持时按供应商接口能力设置，不宣称任意供应商都适配。

**费用边界**：本轮 Codex 没有启动真实个人模型或在线向量验证。连接测试、上传抽取、发布向量化和学生问答可能产生费用；原台账仍为生成 844451 / 批准 900000（余 55549）、向量 12005 另计。人工新调用不自动记入这份历史台账；先明确增量额度与停止线，不自动把余额用于再次跑完整课程。只检查页面、配置保存、已有本地数据时可先不做付费操作。若你要验证真实闭环，先决定新预算，建议使用一份小资料，不重复原两门全量测量。

## 4. 建议按这个顺序自己检查

| 检查 | 操作 | 预期 |
| --- | --- | --- |
| 正式模式与配置边界 | 教师/学生先不配 API 查看相关提示；分别保存 API 后刷新 | 未配置有明确提示；不冒用另一用户 key、不显示演示生成结果；个人配置保存后仍在 |
| 教师主线 | 创建检查课程 → 上传小 PDF 或 MD → 查看任务进度 → 审核队列/编辑图谱 | 处理到「待审核」，不是已发布；有知识点、关系和可定位出处 |
| 手动维护 | 修改一个知识点/关系并刷新；试新增会形成环的先修关系 | 合法修改保存；成环被拦，不破坏已有图谱 |
| 发布与成员 | 教师在「成员」加入 `demo_student` → 发布当前草稿 | 发布成功后学生才看见该版本；不是上传成功就自动发布 |
| 学生学习 | 另一个浏览器/隐私窗口登录学生 → 图谱 → 掌握标记/学习路径 | 状态可保存、路径有解释；学生没有教师编辑入口 |
| 课程问答 | 学生保存自己的模型 API；问课内题、课外题；展开出处、切换长出处 | 课内流式回答与出处；课外明确资料未覆盖；切换出处不继承错误展开态 |
| 隔离/持久性 | 不同学生或第二门检查课程；刷新后看版本/进度 | 不串课程与用户数据；刷新不丢已保存状态 |

新库初始课程列表为空是正常情况；学生也不会自动加入课程。教师先创建课程并添加成员。完整真实闭环中的模型/向量动作均受上面的费用边界约束。

不要由这份功能检查推导新的性能达标结论：关闭思考 Markdown 提取时间、浏览器可见首字、v3 思考开启对照三项仍未测；既有 PDF ≤60 秒不外推到 MD，SSE 首 delta 不称为页面首字。

## 5. 停止与排查

- 启动终端按 **Ctrl+C**：停止 API/worker/前端，保留 Neo4j 和数据。
- 如需停止本检查库（不删数据）：

  ```bash
  cd /Users/arvinhan/.codex/worktrees/plan-c-acceptance-review/SmartSketch
  PATH="$HOME/.docker/bin:$PATH" COMPOSE_PROJECT_NAME=smartsketch-c-acc-manual /bin/bash ./scripts/dev-down.sh
  ```

- 页面没有打开：手动访问上述地址；看本目录 `.demo/logs/web.log`。
- 后端/任务异常：看本目录 `.demo/logs/api.log`、`worker.log`、`migrate.log`。分享日志前去除密钥、令牌、正文。
- 端口占用：只调整本检查目录的端口，并同步 `NEO4J_URI`、`WEB_ORIGIN`；不要按报错建议直接停共享容器或删库。
- 密钥认证失败、预算拒绝：先停止后续真实动作，修正配置/预算后人工决定继续，别重复上传自动消耗。

检查完把「通过项/问题、操作步骤、必要截图」发给 Codex。**stage_c_status 仍 OPEN，technical_freeze 仍 NOT_PERFORMED**；你明确同意后再另做冻结登记。
