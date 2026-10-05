# 双击启动验证与收尾（2026-10-05）

## 范围与结论边界

工作区 /Users/arvinhan/.codex/worktrees/plan-c-acceptance-review/SmartSketch；分支 codex/cross-platform-startup-design。最终业务/启动代码提交 7fee1c88f870cee1af4a17bee9536bf244baf80c。批准的九项实施计划已完成源码，T9 平台／发行验收仍 OPEN；不是正式发行包可下载的声明。

新双击入口、浏览器首次向导、首位教师、私有配置/实例锁、全部依赖就绪、停启、脱敏诊断、停机整组备份／暂存恢复与两次确认、三平台打包／仅构建 CI 已实现。原开发启动入口未改；生成 API 仍由网站用户各自配置，安装向导只配置基础设施向量服务。业务 API / DTO / 迁移 / 依赖无变化。

源码快照通过 git archive 获取，不含个人 .env；依赖仅符号链接已有测试运行时，含最小本地 Git 元数据以支持 git check-attr 用例。模型／在线向量调用 0；台账仍生成844451/900000，向量12005另计。共享 Neo4j、课程正文、测量 worktree、既有发布版本未读写。未推送／合并／发布／冻结。

## 实际命令与结果

| 验证 | 结果 |
|---|---|
| 原51b4caa＋五项回归，Go test 定向 | 5 FAIL，明确复现下表五项，不属于依赖失败 |
| 确认端口的缺失方法／浏览器冲突场景 | 方法编译 RED；浏览器1 PASS /1 FAIL → 2 PASS |
| Go test -race ./... -count=1 -json（最终代码） | 47 PASS /3明确 opt-in Docker SKIP；不是把SKIP当PASS |
| go vet ./... | exit0 |
| CGO=0 go build（darwin-amd64、darwin-arm64、windows-amd64） | 三项exit0；非实机双击 |
| 最终定向 pytest（3个install工具、2个tooling、浏览器） | 29 PASS（29.74s） |
| 最终 ./scripts/verify.sh integration（7fee1c8无.env快照） | exit0；backend+tooling3948 PASS /27登记SKIP；frontend934 PASS＋type-check/build；integration393 PASS /4登记SKIP；backend-live44 PASS；演示E2E2 PASS、个人假供应商E2E4 PASS |
| 最终真实 Docker 合成场景 pytest tests/startup/test_release_smoke.py | 3 PASS（641.38s），登录/停启、双安装隔离、整组/重复恢复 |

完整门禁环境：env -i，仅保留HOME/USER/LANG/PATH及测试选项；Go1.26.8官方归档SHA256校验通过，GOTOOLCHAIN=local；VERIFY_NEO4J_PORT=20689、E2E_NEO4J_PORT=20688、E2E_API_PORT=20681、E2E_WEB_PORT=20673；Chrome系统可执行文件用于假供应商E2E。真实冒烟使用本轮隔离镜像 smartsketch-startup-test-backend/frontend:7fee1c8，随机安装ID、新命名卷、虚构向量配置；不上传、不发布、不问答。

原始本轮日志 /private/tmp/smartsketch-startup-logs/{integration-release-validation.log,smoke-release-validation.log,race-release-validation.jsonl}；可追溯摘要与结果见同目录下文档证据 JSON。临时目录可能被系统清除，摘要不替代重跑；报告记录本会话读取的实际结果。

最终修复定位：launcher/internal/launch/server.go:46、transaction.go:71/147、backup.go:249、controller.go:340、docker.go:129、src/backend/app/tools/install_backup.py:14；位置均对应7fee1c8。完整日志在本工作区忽略目录 .superpowers/sdd/2026-10-04-cross-platform-startup-plan/validation/ 留本地私有备档（不入Git）；摘要见docs/reviews/startup-verification.json。

## 收尾发现与修复（均本地）

| 级别 | 问题／触发条件 | 影响与修复 | 回归 |
|---|---|---|---|
| P2 | 初始fragment兼任reopen master，交换后可重开 | 页面一次性值获得长期能力；独立生成私有master，页面能力只交换一次 | TestConsumedFragmentCannotMintAnotherSession、TestPrivateMasterReopensButBrowserCapabilitiesDoNot |
| P2 | .env写完、安装状态前中断 | 端口不匹配／孤立配置；固定私有写前日志，恢复前校验整组，状态最后发布，密钥不换 | TestConfigurationInterruptedPairRecoversWithoutRekey、TestInitialConfigurationInterruptedAfterEnvRecoversIdentity |
| P2 | 恢复状态先发布、卷映射/清单未完成 | 可能指向旧代际；配置、发行资产、卷映射、消费登记同一恢复组 | TestRestoreActivationInterruptedGroupRecoversMapping |
| P2 | 暂存候选不是restore-verified一律拒绝 | 失败/中断后永久卡住；从已校验快照重建固定资产、继续启动/健康检查，保持二次确认 | TestInterruptedCandidateCanResume |
| P2 | 恢复同一备份再次复用已活跃候选 | 不是快照状态，后续写入仍保留；原子登记已消费代际，重新解包到新卷 | TestSameBackupSecondRestoreUsesFreshGeneration、真实重复恢复后新账号消失 |
| P2 | 端口冲突无既有安装调整界面 | 用户无法继续；明确确认后仅停止本安装、保留密钥/数据并保存新端口 | TestConfirmedPortChangePreservesInstallationAndKeys、TestOccupiedPortChangeLeavesOtherProcessAndConfigUntouched、浏览器端口场景 |
| P2 | 仅核对项目/安装标签，没有核对实际挂载代际 | 健康旧卷误当成选中数据；检查/data命名卷，异代际不算健康，外部卷拒绝 | TestHealthyServicesOnOldGenerationAreNotReady，RED→GREEN |
| P2 | 活跃 WAL +物理只读挂载，-shm不存在 | 真冒烟3/3 readiness超时；允许WAL共享内存基础设施写入，但探测仍mode=ro+query_only，不使用immutable忽略WAL；离线门禁在私有DB+WAL副本检查，源卷继续物理只读 | 独立卷复现SQLITE_CANTOPEN→成功读且业务写SQLITE_READONLY；新增Compose回归RED→GREEN |

整支独立复审曾收到上述前五类和端口的具体发现，但 reviewer 因用量限制中断，未给完整 clean verdict；本轮不冒充独立复审全面通过。后两项为本轮作者定位。修复用例不删、不放宽断言；无第二复审代理。

## 失败记录

- 上轮临时SDK/验证日志在中断后消失；本轮恢复官方工具链校验后重跑，不把丢失结果当通过。
- 首次SDK网络下载连接重置／限时超时，续传同一文件并最终SHA256通过后才执行。
- 最早测试镜像契约过旧，后端 app、migrations、generated contracts、prompts 从同一已提交源码构建专用层；不覆盖既有部署标签。
- 历史源码tar快照无.git导致git check-attr用例失败；新快照补最小元数据，不删或跳过该用例。
- 本轮3775399真实容器3 FAIL（578.57s），均readiness超时；探测在合成API容器可得三项true。离线卷实验精确复现挂载差异，改正后结果单列，不抹掉失败。

- 0ac08b6冒烟2 PASS/1 FAIL，离线备份门禁也受WAL只读挂载影响。6d2a50f复制DB+WAL后单项真实备份/重复恢复1 PASS（282.48s）；最终7fee1c8增加全量现有租约表检查后重跑整组。
- 补充 snapshot lease gate 回归：tasks 与 course_locks 两项RED（未拒绝）→复用既有仓储租约检查后GREEN，拒绝后归档目录仍空；不用复制或更改租约业务规则。

## 所有实施裁定与代价（对应SDD ledger Ruling）

1. 计划标题T<n>规范为Task<n>供提取器读取，语义不改；若错误，代价是任务提取失败，实施计划仍可人工核对。
2. 只含已追踪源码的临时镜像验证，不复制.env；若镜像遗漏文件，会有假阴性，使用git archive和明确来源避免遗漏。
3. 平台特有检查集中T9，未实测维持OPEN；代价是发行支持承诺延后，不用跨编译冒充支持。
4. 测试TMPDIR用规范/private/tmp，保留禁止符号链接策略；若错误，平台路径可能需另处理，不能泛化为生产路径证明。
5. Compose双引号序列化取代单引号，基于真实config --environment字节验证；若错误，特殊Key会变值，已保留特殊字符回归。
6. Bootstrap返回解析标识，复用Probe接口；拉取与180秒就绪分计；若错误，重入或超时行为漂移，顺序/期限回归约束。
7. 真浏览器复用已有Node Playwright，不新增Python依赖；代价是开发/CI仍需浏览器运行时，发行用户不需要。
8. Windows使用受保护显式Win32 DACL并读回核验，不用icacls宽松授权；未实机，若错误可能保存失败，Windows保持OPEN。
9. 升级/恢复操作仅扩展回环内部协议并二次确认，不改业务接口；若错误，可能误操作，认证/严格字段/确认回归约束。
10. 长测试使用冻结快照，镜像源码/生成契约同步；代价是需明确验证SHA，后续修复必须重建快照再验证。
11. WAL探测挂载允许-shm基础设施写入，业务查询仍只读；若工具日后失去只读约束风险上升，保留mode=ro/query_only和挂载回归，禁止immutable活库。

12. 离线源卷仍物理只读，私有DB+WAL副本核验并复用现有全表租约检查；若错误，可能漏读WAL或遗漏租约，新增源字节/活跃WAL/三表租约回归约束。

Deferred minors：未收到可登记的明确Minor清单；不把未覆盖面写成无风险。

文档收尾单独无.env副本 ./scripts/verify.sh basic exit0；git diff --check exit0，JSON格式校验通过。

## OPEN／用户决定

- Mac Intel正式包双击、中文/空格路径、断网／拉取中断；Mac ARM和Windows11 x64真实安装、ACL、WSL2、Docker验收，均OPEN。
- 固定GHCR多架构真实摘要、匿名pull、正式包SHA和下载渠道，OPEN，等待用户发布授权。测试adapter跳过pull，绝不充当这些证据。
- 用户检查业务流程／是否再补整支独立复审；是否执行技术冻结仍由用户决定。stage_c_status OPEN；technical_freeze NOT_PERFORMED。
- 已有计划C测量口径、准确率“逐条复核后采纳辅助判定”、三项不补测与历史归因缺口均保持原状。

停止保留原卷；不自动接管旧开发库。版本回退须匹配配置、SQLite、Neo4j、清单与镜像的整组备份；未签收的真实数据恢复不做生产承诺。
