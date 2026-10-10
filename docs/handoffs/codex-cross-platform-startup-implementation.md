# Codex 双击启动实现交接（2026-10-05）

## 位置与范围

工作区 /Users/arvinhan/.codex/worktrees/plan-c-acceptance-review/SmartSketch；分支 codex/cross-platform-startup-design。业务与启动器最终代码7fee1c88f870cee1af4a17bee9536bf244baf80c，后续提交仅本交接／指南／验证登记。不要修改旧e92f中的他人变更。

依据已批准设计与九项计划，本地交付配置/权限/锁、受控Docker、首位教师stdin、发行Compose/只读探测、180秒就绪/停启、认证浏览器向导、确认端口更换、停机整组快照/暂存恢复/二次确认、三平台双击脚本/构建与打包CI。

原scripts/start.sh/开发Compose不改，不自动导入旧库。生成模型仍由各自网站账号配置；向量向导是本机安装.env，不复活已撤销的全站业务设置页。业务API、DTO、迁移、依赖无变化。

## 接续时先读

1. AGENTS.md、docs/tasks.md。
2. docs/superpowers/specs/2026-10-04-cross-platform-startup-design.md与对应实施计划。
3. docs/reviews/codex-startup-platform-validation.md（实际结果/失败历史/12项裁定）。
4. docs/reviews/startup-verification.json（验证SHA、计数与日志摘要）。
5. docs/startup-guide.md（非正式发行声明和用户流程）。

## 实際验证

- 完整 ./scripts/verify.sh integration：exit0；backend+tooling3948 PASS /27登记SKIP；frontend934 PASS＋type-check/build；integration393 PASS /4登记SKIP；backend-live44 PASS；演示E2E2 PASS、个人假供应商E2E4 PASS。
- Go race47 PASS /3显式真实Docker opt-in SKIP、vet exit0；三目标编译exit0。
- 最终定向29 PASS；真实本地Docker三场景3 PASS（641.38s），含重复恢复丢弃快照后的新增账号。
- 原始失败仍保留：初次三项readiness FAIL；WAL修正后2 PASS/1 FAIL（离线备份）；随后私有DB+WAL拷贝单项1 PASS；最终全组3 PASS。未删除用例／放宽断言。

验证副本以git archive生成，不含.env，最小.git只用于属性门禁；env -i隔离父环境。本轮本地测试镜像有显式adapter替换不可变清单并跳过pull，因此真实Docker合成场景不是GHCR匿名拉取／正式包实机证明。

所有修复的具体红绿回归列在审查报告。令牌master与fragment分开；固定配置/发行组写前日志；恢复候选可重试、已消费代际重抽；实际挂载代际核验；WAL模式只读业务探测允许-shm基础设施创建；离线源卷仍物理只读，DB+WAL私有副本做完整性与现有三表租约门禁。

## 未完成与下一步

- T9平台／发行仍OPEN：Mac Intel正式包、Mac ARM、Windows11真实双击/ACL/WSL2、中文空格路径、网络拉取取消/恢复、正式镜像摘要和匿名pull。
- 独立整支reviewer收到具体发现后因用量中断，没有完整clean结论。修复仅靠本轮红绿/全量/真实合成场景验证；用户可决定是否另做独立复审。
- 未推送、合并、发布、复制个人.env/业务库、调用收费模型、改共享Neo4j/测量证据、执行技术冻结。当前批准只覆盖本地实现。
- 发布前需用户另授权镜像／GitHub发行操作，再取得真实多架构摘要、编译对应版本核心、正式SHA下载包及实机记录。不要填假的发行摘要或把本地标签写成正式版本。
- stage_c_status OPEN、technical_freeze NOT_PERFORMED；历史预算生成844451/900000、向量12005不变；既有准确率签收仍为“逐条复核后采纳辅助判定”，三项暂缓测量不变。

## 验证命令

- TMPDIR=/private/tmp GOTOOLCHAIN=local go -C launcher test -race ./... -count=1；go -C launcher vet ./...。
- CGO_ENABLED=0 GOOS/GOARCH三目标go build（不得把交叉编译称作实机支持）。
- PYTHONPATH=src/backend pytest tests/backend/test_install_{bootstrap,probe,backup}.py tests/tooling/test_startup_{package,release}.py tests/startup/test_wizard_ui.py -q（Chrome/Node既有运行时）。
- 干净无.env副本中env -i，独立VERIFY_NEO4J_PORT/E2E_NEO4J_PORT/E2E_API_PORT/E2E_WEB_PORT，./scripts/verify.sh integration；使用假供应商。
- 显式SMARTSKETCH_STARTUP_SMOKE=1与仅本轮smartsketch-startup-test-*标签，pytest tests/startup/test_release_smoke.py -q；缺设置是FAIL，非PASS。

## 保留与回退

保留此分支，不自动集成。所有测试用新随机安装卷，按安装＋项目标签核验清理本轮合成资源；既有发布和共享库不改，禁止prune/down -v。启动器停止保留卷；真实版本回退需配置、SQLite、Neo4j、发行清单/镜像整组快照，不单独降级代码或重生密钥。真实业务恢复验收仍待用户。
