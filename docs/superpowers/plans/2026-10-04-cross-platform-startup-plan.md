# Cross-platform Startup Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新用户只安装 Docker，解压后双击 Mac/Windows 入口，在本机浏览器完成向量配置与教师建号，以后重复启动、停止并保留课程数据。

**Architecture:** 共用 Go 启动核心提供短期回环 HTTP 向导，分平台包装只负责定位并启动核心。发行专用 Compose 使用固定镜像和独立命名卷，复用现有 API、worker、Nginx 与容器内迁移；一次性教师引导复用原账号验证/哈希，不增加业务 API 或配置数据库。

**Tech Stack:** Go 1.26.8（标准库；CGO_ENABLED=0）；Docker Desktop / Compose v2；现有 Python/FastAPI/Neo4j/SQLite/Vue。Go 只用于开发构建，发行用户不安装 Go/Python/Node。

**Spec:** `docs/superpowers/specs/2026-10-04-cross-platform-startup-design.md`（用户2026-10-04确认）；实现前读 AGENTS.md、docs/tasks.md、身份/任务/发布规格。

**Status:** APPROVED_NATIVE_EXECUTION（用户同意本会话逐项执行）；开始实施。规划基线 d517eeb（产品代码基线 bdb89c46）；本文中的命令与测试均是未来步骤，除本轮交接明确记录的检查外，不表示已运行。

## Global Constraints

- 发行支持目标：macOS 的 Docker 官方支持版本范围，arm64 与 amd64；Windows 11 x64 + Docker Desktop WSL 2 Linux containers。
- 本期不包含原生桌面窗口、托盘、自动更新、开机自启、无 Docker 运行、局域网/公网部署、演示模式切换或全局向量业务设置页。
- .env 依旧只是环境配置；LLM_MODE=personal、EMBEDDING_MODE=online、APP_ENV=production；个人生成 API 仍走既有网页设置。
- Unix 私有目录权限 0700、.env 0600；Windows限制为当前用户与必要系统主体。教师口令只走容器stdin，不进入参数/环境/持久文件。
- 随机不少于 32 字节会话令牌；仅监听127.0.0.1；写操作检查Host、Origin、令牌、JSON类型；不存浏览器持久存储。
- 就绪检查总等待上限 180 秒，镜像拉取单独显示且可取消；缺平台/工具/镜像权限不计PASS。
- 只自动复用本启动器管理的已有安装；本期不自动导入或迁移当前开发工作区的 .env、SQLite、Neo4j 数据。
- 停止保留全部卷，不执行down -v、volume prune、system prune；不自动换向量空间，不生成替代旧密钥。
- 固定镜像摘要与发行包SHA-256；源码Git不提交二进制、密钥、业务库、课程正文。保留开发Compose/start.sh用途。
- 本轮与默认启动无真实生成/在线向量测试；收费调用、镜像推送与GitHub发行各自先获用户批准。stage_c_status OPEN，technical_freeze NOT_PERFORMED。

## Review Focus

1. 解压到中文/空格路径、Key含$、#、引号：不产生shell注入或Compose插值改值（T1/T2/T8）。
2. 导出旧LLM/Neo4j环境变量后双击：持久本机配置仍是唯一来源，不误连旧实例（T2/T9）。
3. 两次同时双击、崩溃在配置写入或教师建号之后：单实例、可恢复、无重复账号/口令重置（T1/T3/T5）。
4. API健康但worker/索引失败，或端口检查后被抢占：不显示READY，不终止其他进程（T4/T5）。
5. 恶意Host/跨站请求、诊断中诱饵密钥、被篡改备份或丢失根密钥：零越权控制、零泄露、恢复失败不覆盖旧数据（T1/T6/T7）。

## File Structure / Ownership

所有新Go代码置于独立`launcher/`模块（module `github.com/arvinhanye/SmartSketch/launcher`），业务前后端职责不重排。

| 单元 | 文件 | 职责 |
| --- | --- | --- |
| 配置与状态 | launcher/internal/launch/types.go、config.go、store.go、permissions_unix.go、permissions_windows.go、lock_unix.go、lock_windows.go | 类型、环境格式、私有落盘、OS权限/锁 |
| 主机与Docker | launcher/internal/launch/process.go、host.go、docker.go、manifest.go | 固定命令、环境过滤、安装定位、镜像清单/所有权 |
| 生命周期 | launcher/internal/launch/controller.go、readiness.go | 配置/启动/停止状态机、真实就绪 |
| 向导 | launcher/internal/launch/server.go、diagnostics.go、ui/index.html、ui/app.js、ui/style.css | 内部HTTP协议、会话认证、脱敏与界面 |
| 备份恢复 | launcher/internal/launch/backup.go；src/backend/app/tools/install_backup.py | 只对本实例停机快照及恢复 |
| 程序与包装 | launcher/cmd/smartsketch-launcher/main.go；packaging/start-macos.command、start-windows.cmd | 入口、浏览器/信号生命周期 |
| 后端引导/探测 | src/backend/app/tools/{__init__,bootstrap_teacher,install_probe}.py；services/install_bootstrap.py、repositories/install_bootstrap.py | 原用户表事务初始化、只读就绪探测 |
| 发行 | packaging/compose.release.yaml、release-manifest.schema.json；scripts/package-launcher.py；.github/workflows/startup.yml、release-local.yml | 固定镜像、三目标包与可追溯构建 |
| 测试 | 各Go源文件对应*_test.go；tests/backend/test_install_bootstrap.py、test_install_probe.py、test_install_backup.py；tests/tooling/test_startup_release.py、test_startup_package.py；tests/startup/test_release_smoke.py | 单元/命令/编排/发行包/全新实例冒烟 |
| 用户说明 | docs/startup-guide.md、docs/reviews/codex-startup-platform-validation.md | 中文使用/故障/实机证据；后者只填实际结果 |

`scripts/verify.sh`只在T8增加launcher门禁，`scripts/verify/startup.sh`为其实现；full/integration缺Go时明确失败，basic仍是既有基础检查。Go构建安装、测试文件与CI均在所属交付任务内，不单列“空骨架”任务。

## Common Interfaces（T1定义，后续直接消费）

Go包`launch`：
- `type Secret struct{ value string }`；`NewSecret(string) Secret`、`String()/GoString()`返回`[REDACTED]`，`MarshalJSON() ([]byte,error)`阻止明文序列化、`UnmarshalJSON([]byte) error`只接收字符串并保护错误输出；原始值仅包内环境序列化/进程stdin使用。
- `type EmbeddingConfig struct { BaseURL, Model string; APIKey Secret; Dimensions int }`；`type Config struct { Embedding EmbeddingConfig; Neo4jPassword, JWTSecret, ModelCredentialKey Secret; WebPort int }`。
- `type Phase string`，常量`NEW/CONFIGURED/INITIALIZING/READY/STOPPED/ERROR`；`type InstallState struct { SchemaVersion int; InstallID, ReleaseVersion string; Phase Phase; Checkpoint, TeacherID, TeacherUsername string; WebPort int; Fresh bool }`。状态不含Secret/正文。
- `type SetupInput struct { Embedding EmbeddingConfig; TeacherUsername string; TeacherPassword, ConfirmPassword Secret; WebPort int }`。教师输入不进Config、持久状态或诊断。
- `type Failure struct { Code, Stage, Message string; Retryable bool }`实现error，仅固定中文文案；原始错误不拼到Message。
- `type Store struct { Root string; Permissions Protector }`；`Load() (Config,InstallState,error)`、`SaveConfig(Config,InstallState) error`、`SaveState(InstallState) error`；`ValidateSetup(SetupInput) error`、`EncodeEnv(Config) ([]byte,error)`、`DecodeEnv([]byte) (Config,error)`、`NewConfig(SetupInput,io.Reader) (Config,error)`。
- `type Protector interface { SecureDir(string) error; SecureFile(string) error }`；`AcquireInstance(root string) (*InstanceLock,error)`、`(*InstanceLock).Close() error`。已运行者发现仅来自私有元数据和经过认证的loopback状态响应，不按PID独立判定。

每任务新增接口如下定义；不建立业务OpenAPI新路径。测试用隔离TempDir、诱饵Key，不接触真实.env。

### Task 1 / STARTUP-03：安全配置、原子状态和单实例

**Files:** 新建launcher/go.mod、上述配置/状态/权限/锁文件及对应*_test.go。新模块构建锁Go1.26.8，标准库优先，不新增Go第三方运行库。

**Interfaces:** 输出Common Interfaces全部定义；`ResolveRoot(goos,userConfigDir string) (string,error)`定位固定SmartSketch目录（host.go在T2实现）。本任务Store测试使用显式TempDir，不依赖主机默认目录。

- [ ] **1. 写失败用例。** `TestEnvRoundTripSpecialCharacters`逐字节保留`$ # ' " \\`；`TestEnvRejectsDuplicateAndMultiline`重复键/CRLF注入/未知键/NUL失败；`TestStoreAtomicFailurePreservesExisting`任一写入/权限失败保持旧字节；`TestMissingConfigDoesNotRekey`有安装状态而.env缺失时错误；`TestInstanceLockConcurrentOpen`两个并发只有一个持锁，释放后可重开；`TestSecretHasNoPlaintextRepresentation`覆盖fmt、JSON、Failure。

```go
func TestSecretHasNoPlaintextRepresentation(t *testing.T) {
    s := NewSecret("fixture-key-unique-STARTUP03")
    if strings.Contains(fmt.Sprintf("%v %#v", s, s), "fixture-key-unique-STARTUP03") { t.Fatal("secret leaked") }
    b, _ := json.Marshal(s)
    if bytes.Contains(b, []byte("fixture-key-unique-STARTUP03")) { t.Fatal("JSON leaked") }
}
```

- [ ] **2. 运行红灯。** `cd launcher && GOTOOLCHAIN=local go test ./internal/launch -run 'Test(Env|Store|MissingConfig|InstanceLock|Secret)' -count=1`；期望缺函数/断言失败，环境无Go需先按批准的实施准备下载已校验工具链，不把缺工具当行为红灯。
- [ ] **3. 实现配置与Store。** 用户名3～32位`[a-z0-9_.-]`、口令8～128个Unicode字符（与Python一致），维度≥1；默认web端口8080，字段校验不回显值。拒绝向量URL内凭据/查询/片段、非HTTPS和明显私有地址；完整供应商出站门禁保留后端负责，向导不做联网探测。安全生成32字节根密钥(URL-safe base64)、48字节JWT随机量和不少于24随机字节Neo4j口令。环境序列化按Compose单引号及转义规则；后续T4用实际Compose验证，不只自家parser互证。
- [ ] **4. 实现OS权限/锁。** Unix用OS文件锁，Windows用标准库系统调用访问LockFileEx；WindowsACL可通过固定icacls参数设置当前用户SID/SYSTEM并核验结果，失败不落密钥。私有元数据原子写；符号链接/重解析点指向目录外时拒绝写入，不覆盖未知现存目录。崩溃产生不完整安装时Load返回恢复错误，不生成新的InstallID。
- [ ] **5. 运行绿灯。** 同命令全部PASS；`go test ./... -count=1`，三目标`go build`在T8补做；WindowsACL/锁必须Windows实际运行，不计交叉编译为PASS。
- [ ] **6. 提交。** 只stage本任务文件；`git commit -m "feat: add secure launcher configuration and instance state"`；任务登记测试命令/结果与缺平台项。

### Task 2 / STARTUP-04：受控Docker调用与实例所有权

**Files:** 新建launcher/internal/launch/{process,host,docker,manifest}.go及*_test.go、test_helpers_test.go；packaging/release-manifest.schema.json。

**Interfaces:** `type ProcessRequest struct { Executable string; Args []string; Env []string; Stdin []byte }`、`type ProcessResult struct { Stdout []byte; ExitCode int }`（无默认原始stderr日志）；`type Runner interface { Run(context.Context,ProcessRequest) (ProcessResult,error) }`；`ExecRunner`实现。`type ReleaseManifest struct { Version, BackendImage, FrontendImage, Neo4jImage, ComposeSHA256 string; Targets []string }`；`LoadManifest(path string) (ReleaseManifest,error)`。

`type Docker struct { CLI, ComposePath, EnvPath string; Manifest ReleaseManifest; Runner Runner }`；`Inspect(ctx context.Context,s InstallState) (Snapshot,error)`、`Pull(ctx context.Context,s InstallState) error`、`RunStage(ctx context.Context,s InstallState,stage string,stdin []byte) error`、`Stop(ctx context.Context,s InstallState) error`；`BuildChildEnv(parent []string) []string`。`type Snapshot struct { ProjectOwned bool; Neo4jHealthy, APIHealthy, WorkerHealthy, WebHealthy bool; MigrateExitCode *int; SchemaCurrent, EmbeddingSpaceMatches, VectorIndexesOnline bool }`；迁移尚无结果时exitcode=nil，其余未知健康为false，不宣称供应商已联网验证。

- [ ] **1. 写失败用例。** `TestDockerUsesArgsNotShell`中文空格路径不拆分；`TestChildEnvDropsInheritedConfig`丢弃父环境所有LLM_/EMBEDDING_/NEO4J_/MODEL_/AUTH_/SQLITE_/COMPOSE_配置；只保留运行Docker所需HOME/USERPROFILE/PATH/临时目录/系统根等固定允许项。保留Docker宿主上下文定位但运行前确认Linux、本机Docker Desktop，远端上下文拒绝。`TestUnknownProjectVolumesAreRejected`InstallID/标签不匹配禁止启动；`TestManifestRejectsMutableImages`无sha256镜像与未知字段失败；`TestCommandsNeverIncludePassword`stdin有诱饵密码，args/env/result日志无值。

```go
func TestChildEnvDropsInheritedConfig(t *testing.T) {
    got := strings.Join(BuildChildEnv([]string{"PATH=/bin", "NEO4J_PASSWORD=old", "LLM_MODE=demo", "COMPOSE_PROJECT_NAME=other"}), "\n")
    if strings.Contains(got, "old") || strings.Contains(got, "demo") || strings.Contains(got, "other") { t.Fatal(got) }
    if !strings.Contains(got, "PATH=/bin") { t.Fatal("Docker executable environment lost") }
}
```

- [ ] **2. 运行红灯。** `cd launcher && go test ./internal/launch -run 'Test(Docker|ChildEnv|UnknownProject|Manifest|Commands)' -count=1`，确认断言失败。
- [ ] **3. 实现固定命令集合。** 每命令固定`--project-name smartsketch-<installID>`、绝对`--env-file`/`-f`/`--project-directory`；installID仅随机hex，不接收网页项目名。RunStage只允许pull、neo4j、migrate、bootstrap、probe、app、backup、restore；未知stage拒绝。CLI使用os/exec参数数组、独立超时/取消、stdin管道；inspect只抽取固定健康/标签/退出码，丢弃原始输出。正常Stop仅stop当前服务，不删卷。
- [ ] **4. 实现主机发现。** `ResolveRoot`用系统用户配置目录；定位Docker CLI兼顾Mac ~/.docker/bin及Windows官方安装位置，不写PATH。确认Compose v2/profile/完成依赖能力、Docker Desktop Linux引擎可用；缺环境显示固定中文下载/打开指引。浏览器打开仅接收自行构造的loopback URL；启动DockerDesktop也只用固定app路径。test_helpers_test.go定义`recordingRunner`（记录请求、排队结果）供后续测试，不调用真实进程。
- [ ] **5. 绿灯并提交。** 同组go test及`go vet ./...`通过；`git commit -m "feat: scope launcher Docker commands to owned installations"`；不运行pull/push。

### Task 3 / STARTUP-05：容器内首个教师引导

**Files:** 新建src/backend/app/tools/{__init__,bootstrap_teacher}.py、services/install_bootstrap.py、repositories/install_bootstrap.py、tests/backend/test_install_bootstrap.py；修正scripts/manage-accounts.py旧注册注释。无迁移。

**Interfaces:** 服务`create_first_teacher(sqlite_url: str, username: str, password: str) -> BootstrapOutcome`；不可变结果`BootstrapOutcome(user_id: str, username: str, created: bool)`定义于仓储并由服务再导出，无口令/hash。仓储`initialize_teacher(sqlite_url: str, *, account_id: str, username: str, password_hash: str) -> BootstrapOutcome`以BEGIN IMMEDIATE完成空库判断/插入/幂等核验。CLI `python -m app.tools.bootstrap_teacher`只接受stdin JSON `{username,password}`，限制≤16KiB，stdout仅结果JSON。

- [ ] **1. 写失败用例。** 本文件定义`migrated_sqlite_url` pytest fixture：tmp_path内建库，调用repositories.sqlite.migrate(sqlite_url)，不读任何业务库；`test_bootstrap_teacher_is_idempotent_and_preserves_password_hash`两次不同密码仅一个原hash；`test_bootstrap_rejects_nonempty_unrecognized_database`学生占名/其他教师/停用同名均零写入；`test_concurrent_bootstrap_creates_one_teacher`双连接竞争仍单账户；`test_cli_stdin_never_echoes_secret`非法/额外字段/过大输入不回显正文。

```python
def test_bootstrap_teacher_is_idempotent_and_preserves_password_hash(migrated_sqlite_url):
    first = create_first_teacher(migrated_sqlite_url, 'first_teacher', 'fixture-pass-one')
    before = find_by_username(migrated_sqlite_url, 'first_teacher').password_hash
    again = create_first_teacher(migrated_sqlite_url, 'first_teacher', 'fixture-pass-two')
    assert first.created and not again.created
    assert first.user_id == again.user_id
    assert find_by_username(migrated_sqlite_url, 'first_teacher').password_hash == before
```

- [ ] **2. 红灯。** `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_install_bootstrap.py -q`；记录缺实现而非环境错误。
- [ ] **3. 实现。** 服务复用auth.normalize_username、USERNAME_PATTERN.fullmatch、口令长度常量、hash_password；仓储SQL只在repositories。只允许空库创建或唯一启用同名教师幂等返回；其他数据保持原样。SQLiteconnect是autocommit，事务必须显式BEGIN IMMEDIATE/COMMIT/ROLLBACK，不依赖with自动持锁。CLI先schema门禁再服务；无密钥repr/traceback。由controller限定首次新托管实例调用，不作为常驻教师注册路由。
- [ ] **4. 绿灯并提交。** 同组pytest全部PASS，连同已有auth/account_admin相关用例运行；记录实际选取的既有文件。`git commit -m "feat: bootstrap first teacher through protected container input"`。

### Task 4 / STARTUP-06：发行Compose与只读就绪探测

**Files:** 新建packaging/compose.release.yaml、src/backend/app/tools/install_probe.py、tests/backend/test_install_probe.py、tests/tooling/test_startup_release.py；必要时src/backend/Dockerfile仅调整发行运行模块，不复制秘密/宿主脚本目录。

**Interfaces:** `probe_install(settings: Settings) -> dict[str, bool]`输出schema_current、embedding_space_matches、vector_indexes_online；失败分类无正文/配置值；`python -m app.tools.install_probe`stdout仅JSON，exit非0表示未就绪。T2的RunStage(migrate/bootstrap/probe/app)消费本任务服务名/命令。

- [ ] **1. 写失败用例。** `test_release_compose_keeps_secrets_off_web`仅后端env_file；`test_release_uses_owned_named_volumes_and_loopback_web`Neo4j无宿主端口、web回环8080/选定端口；`test_release_preserves_nginx_sse_settings`proxy_buffering off/read_timeout1h不退化；`test_probe_is_read_only_and_rejects_index_or_space_mismatch`SQLite前后摘要不变，Neo4j调用仅读，任一缺索引失败。
- [ ] **2. 红灯。** `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_install_probe.py tests/tooling/test_startup_release.py -q`，记录具体失败。
- [ ] **3. 实现发行清单。** neo4j/app-data独立命名卷，Compose所有权标签包含安装ID。镜像从验证过的发行清单生成的运行副本填写固定摘要，不接收网页镜像输入。migrate命令精确复用`python -m app.repositories.sqlite && python -m app.repositories.graph_migrations`；后者main已经ensure_current_vector_indexes，禁止重复发明索引初始化流程。一次性bootstrap/probe服务使用同一后端镜像、env和卷、固定tools profile；probe与worker健康互不替代。迁移成功后才启动应用。
- [ ] **4. 实现只读探测与实际.env兼容验证。** SQLite用mode=ro/query_only（不对活跃WAL库使用immutable=1），检查schema历史及向量行；Neo4j只读取当前预期索引状态/维度，不修复或写图。测试用临时配置执行`docker compose ... config --format json`并解析捕获的结果，断言含特殊字符诱饵Key逐字节一致；绝不把渲染全量配置打印到日志。该语法测试不启动容器或联网；缺Docker明确FAIL/未验证。
- [ ] **5. 绿灯并提交。** 同组pytest+发行Compose配置解析通过；检查无api/DTO/迁移变化。`git commit -m "feat: define isolated Docker release stack and readiness probe"`。

### Task 5 / STARTUP-07：启动/停止状态机和恢复

**Files:** 新建launcher/internal/launch/{controller,readiness}.go及*_test.go。

**Interfaces:** `type Controller struct`由`NewController(store *Store,docker *Docker,clock Clock) *Controller`构造；`type Clock interface { Now() time.Time; Sleep(context.Context,time.Duration) error }`。`Configure(SetupInput) error`、`Start(context.Context,*SetupInput) error`、`Stop(context.Context) error`、`Status(context.Context) (StatusView,error)`；`StatusView`仅包含phase/stage/service states、webURL、固定Failure和允许操作。`WaitReady(context.Context,SnapshotReader,Clock,time.Duration) error`上限180s，SnapshotReader=`func(context.Context)(Snapshot,error)`。教师口令只在Start当前内存输入中，完成即清引用。

- [ ] **1. 写失败用例。** `TestStartOrdersMigrationBeforeBootstrapAndApp`严格阶段顺序；`TestAPIOKWorkerBrokenDoesNotSetReady`worker或向量探测失败均不READY；`TestStartDeadlineIs180Seconds`假时钟精确180s终止；`TestCrashAfterTeacherCreatedResumesWithoutReset`幂等恢复；`TestPortLostAfterPrecheckNeverKillsProcess`绑定竞态返回端口故障；`TestStopPreservesVolumeAndConfig`停止后同InstallID/根密钥/卷；`TestReadyDoubleLaunchOnlyOpensExisting`健康不重跑迁移/pull/建号。
- [ ] **2. 红灯。** `cd launcher && go test ./internal/launch -run 'Test(Start|APIOK|Crash|PortLost|Stop|ReadyDouble)' -count=1`；recordingRunner排队固定状态，所有日志无诱饵秘密。
- [ ] **3. 实现。** 占锁→校验自己安装/配置→准备固定镜像→Neo4j healthy→新库迁移/索引→教师bootstrap→API/worker/web→probe和代理检查→READY。阶段写checkpoint，任何失败持久ERROR及可重试阶段；凭据缺失有数据时终止，不重新生成。无必要升级的重启只读探测→启动停止服务，不重跑迁移。初次pull独立取消，不计入就绪180s；不会自动测试模型或降级demo。
- [ ] **4. 生命周期补充。** Stop仅自己的API/worker/web/Neo4j，沿用worker90s宽限/租约处理；不覆盖共享DB。端口变更经确认后仅改本机Config.WebPort/WEB_ORIGIN，并重新验证映射；不kill别的PID。Compose service restart policy存在，最终健康失败不靠无限重启宣布成功。
- [ ] **5. 绿灯并提交。** 同组与所有go test通过，无真实容器调用；`git commit -m "feat: coordinate recoverable startup and data-preserving shutdown"`。

### Task 6 / STARTUP-08：本机安装/控制向导与诊断

**Files:** 新建launcher/internal/launch/{server,diagnostics}.go、ui/{index.html,app.js,style.css}、server_test.go、diagnostics_test.go；tests/startup/test_wizard_ui.py（Playwright，使用本机模拟控制服务）。

**Interfaces:** `NewServer(controller *Controller,session Secret,origin string) http.Handler`；`SanitizeDiagnostic(stage,code string) Diagnostic`只接收已分类字段；`Diagnostic`包含版本/平台/阶段/固定消息/耗时，不接收原始env或stderr。内部路径固定：GET /control/status；POST /control/setup、/start、/stop、/open、/diagnostics；每路径都有认证与严格输入。GET /及静态文件只服务嵌入资源。

- [ ] **1. 写失败用例。** `TestControlRequiresTokenHostAndOrigin`跨站、错误Host、缺令牌、GET写操作拒绝；`TestControlRejectsUnknownFieldsAndLargeBody`16KiB上限、重复JSON字段/多JSON对象拒绝；`TestDiagnosticsContainsNoSecretOrRawStderr`诱饵Key不出响应/日志。`test_wizard_clear_secret_and_show_real_mode`完成清空输入，不写localStorage/sessionStorage，不把供应商格式校验称联网成功。
- [ ] **2. 红灯。** `cd launcher && go test ./internal/launch -run 'Test(Control|Diagnostics)' -count=1`；`PYTHONPATH=src/backend .venv/bin/python -m pytest tests/startup/test_wizard_ui.py -q`。浏览器缺失记缺口，不PASS。
- [ ] **3. 实现。** crypto/rand会话32字节、fragment一次交换后history.replaceState清除；Authorization令牌只存JS内存，窗口重开由核心重新引导，不写Cookie。Host精确127.0.0.1:实际端口；写Origin与本向导完全一致，JSON严格解码；禁止CORS/任意资源路径/任意命令。禁缓存、无外部CDN，页面安全策略只允许本地静态资源。setup只接表单字段，镜像/项目名/文件路径从内置核心取。
- [ ] **4. 页面文案与状态。** 清楚分离向量API与个人生成API；提示“新独立安装，不包含旧开发环境课程”“格式检查通过不代表供应商连接/额度已验证”。按钮只显示当前允许操作，操作期间禁重复点击，轮询阶段；恢复时若bootstrap返回created=false，显示“账号已存在，仍使用首次口令”，不把重新输入当密码重置。Docker缺失仍给终端中文官方下载指引，不能等向导服务才发现打不开。
- [ ] **5. 绿灯并提交。** 单元+浏览器模拟向导通过，检查网页/日志诱饵秘密零匹配；`git commit -m "feat: add authenticated local setup wizard and redacted diagnostics"`。

### Task 7 / STARTUP-09：停机备份、版本变更与恢复保护

**Files:** 新建launcher/internal/launch/backup.go、backup_test.go；src/backend/app/tools/install_backup.py；tests/backend/test_install_backup.py；修改packaging/compose.release.yaml加入本任务backup/restore工具服务、docs/startup-guide.md的恢复段落。

**Interfaces:** `type BackupSet struct { ID, InstallID, ReleaseVersion, ManifestSHA256 string; Files map[string]string }`只记录摘要/固定相对文件名；`PrepareUpgrade(ctx context.Context,target ReleaseManifest,confirmed bool) (BackupSet,error)`、`Restore(ctx context.Context,set BackupSet,confirmed bool) error`为Controller方法。容器工具只接受固定backup/restore命令和stdin清单；只挂该安装卷，backup读取卷只读，导出目录固定为本机私有backup目录。无Docker socket挂载。

- [ ] **1. 写失败用例。** `TestUpgradeRequiresConfirmationAndVerifiedBackup`无确认/备份失败不迁移；`TestRestoreRejectsTamperedOrForeignBackup`错误InstallID/摘要/路径阻止写卷；`TestMissingRootKeyStopsRecovery`不自动生成根密钥；`test_backup_restores_sqlite_and_graph_as_one_set`合成库/图卷/Config成套匹配；`test_restore_rejects_traversal_links_and_partial_archives`含../、绝对路径、链接或截断拒绝，原卷无变化。
- [ ] **2. 红灯。** Go backup组+`PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_install_backup.py -q`；先用临时合成目录，不碰Docker业务卷。
- [ ] **3. 实现备份。** 版本变更先说明影响并确认；只停自己的API/worker/Neo4j且通过任务租约门禁。SQLite沿用现有停机备份/完整性验证，Neo4j完整卷归档；加上.env与原发行Compose/摘要，配置权限不放宽。辅助容器可为读私有卷使用root，但仅挂本安装数据卷与指定导出目录，不privileged、不挂宿主根/套接字。预检查空间、校验导出完整性与hash、完成后原子标记BackupSet，否则不迁移。
- [ ] **4. 实现恢复保护。** 在写数据前校验全部归档、身份、摘要、镜像版本与剩余空间；恢复到本安装的暂存卷，probe通过后经再次确认切换卷映射，保留原卷，不直接覆盖原卷或只降级代码。无同版本镜像或配置根密钥则停，给出恢复缺口。此为手动确认恢复，不增加自动更新/自动回滚机制。
- [ ] **5. 绿灯并提交。** 合成目录回归通过；真实本安装卷恢复演练在T9隔离沙箱完成前不宣称备份有效。`git commit -m "feat: protect managed installation upgrades with verified backups"`。

### Task 8 / STARTUP-10：入口、三平台发行包与CI

**Files:** 新建launcher/cmd/smartsketch-launcher/main.go及main_test.go；packaging/start-macos.command、start-windows.cmd；scripts/package-launcher.py、scripts/verify/startup.sh；tests/tooling/test_startup_package.py；.github/workflows/startup.yml、release-local.yml；修改scripts/verify.sh、.github/workflows/ci.yml、.gitignore、docs/integrations.md、docs/architecture.md。

**Interfaces:** CLI默认`serve`，只允许`--version`与启动核心自身固定操作；不接受口令/key/任意项目或docker参数。`package_release(manifest_path: Path, binaries_dir: Path, output_dir: Path) -> list[Path]`生成darwin-arm64、darwin-amd64、windows-amd64包及SHA256SUMS；受检manifest映射到固定Compose镜像，不从不可信档案拷脚本。所有Go构建`CGO_ENABLED=0 GOTOOLCHAIN=local`、带release版本，二进制不进Git。

- [ ] **1. 写失败用例。** `test_macos_archive_preserves_executable_entry`tar.gz中.command与核心0755；`test_windows_cmd_uses_quoted_bundle_path`脚本只用发行相对路径、含中文空格实际双击留T9；`test_packages_have_manifest_hashes_and_no_credentials`扫描.env/诱饵秘密/源码业务库均不存在；`TestCLINeverAcceptsSecretArguments`误传敏感参数只报告字段不回显值。
- [ ] **2. 红灯。** tooling package pytest+CLI go test；缺构建产物只作为包装输入校验用例，不伪装成三平台测试成功。
- [ ] **3. 实现入口/包装。** Mac按uname选择核心，Windows固定x64，错误架构中文退出。核心从发行资源定位静态文件/Compose，默认配置目录稳定；signal关闭控制服务而保留容器，显式Stop才停止。打包程序使用Python标准库，仅开发/CI执行，用户无Python依赖；输出到Git忽略dist/。Windowszip、Mac tar.gz兼顾执行位，README说明系统来源提示，不要求关闭安全保护。
- [ ] **4. 门禁与构建。** `startup.yml`在Mac arm64/amd64、Windows x64 runner跑平台权限/锁/路径Go测试；Linux跑Docker配置/容器工具相关回归。full/integration增加startup.sh必跑Go测试/vet，缺工具明确FAIL；既有CI补setup-go固定1.26.8而非改Python/Node锁版本。`release-local.yml`先只构建上传CI artifacts，无默认packages:write或自动GitHub发行；获发布授权后才启用GHCR双架构buildx推送并写真实摘要、发布固定发行包。测试不能预填SHA或把本地镜像名标正式发行。
- [ ] **5. 绿灯并提交。** `cd launcher && go test ./... -count=1 && go vet ./...`；GOOS/GOARCH三组`go build`（跨编译是构建证据，不是实机PASS）；tooling pytest与basic门禁通过。`git commit -m "feat: package cross-platform launchers and enforce startup gates"`。

### Task 9 / STARTUP-11：隔离容器冒烟、主线回归和三平台验收

**Files:** 新建tests/startup/test_release_smoke.py、tests/startup/README.md、docs/reviews/codex-startup-platform-validation.md；完成docs/startup-guide.md、docs/tasks.md、docs/handoffs/codex-cross-platform-startup-implementation.md。

**Interfaces:** pytest沙箱明确设置新TempDir/随机安装ID/隔离端口，仅使用本轮测试镜像和合成资料；启动器进程Runner前述接口是真实实现，测试无读取宿主.env/旧Config接口。平台报告列OS/CPU/Docker版本、发行摘要、双击操作结果、截图/脱敏日志路径与未测事项。

- [ ] **1. 写失败冒烟。** `test_fresh_release_login_register_stop_restart_preserves_data`通过向导创建教师、登录、学生注册、停止重启后账号/InstallID/根密钥摘要保持；`test_two_installations_and_old_environment_are_isolated`父环境诱饵Neo4j/LLM/Compose变量不生效，其他实例合成记录前后摘要一致；`test_failed_migration_and_worker_health_do_not_claim_ready`失败不显示假READY；`test_owned_backup_restore_round_trip`本安装合成数据恢复到暂存卷，经确认切换后数据一致、旧卷保留。
- [ ] **2. 隔离运行。** 在不含.env的干净测试工作区，读取测试/脚本后运行`PYTHONPATH=src/backend .venv/bin/python -m pytest tests/startup/test_release_smoke.py -q`。最小启动测试向量字段是格式合法诱饵值，不上传/发布/提问，不发在线向量；创建/登录/注册与本地图/schema探测不收费。清理测试环境只按此次创建的InstallID/卷清单，经逐个所有权核验；不使用全局prune。完整业务主线另用既有integration本机假供应商，不把该结果写成真实供应商已验。
- [ ] **3. 全量门禁。** 干净无.env隔离工作区运行`./scripts/verify.sh integration`；清除所有LLM/Embedding/Neo4j/凭据父环境变量，选择隔离端口和本机假供应商，保持原用例/断言/登记skip。记录各层实际数量与退出码，任何缺工具/缺镜像FAIL或缺口，不拿旧结果代替。
- [ ] **4. 三平台实机。** 对发行包分别完成首次双击→配置→登录、再次双击、关闭窗口、停止恢复、中文/空格路径、Docker未运行、端口冲突、断网拉取和中断恢复；Mac arm64、Mac amd64、Windows11 x64各留证据。没有某平台机器则该平台OPEN，发行说明不能声称已适配；用户可代跑Windows/Intel验收。
- [ ] **5. 发行验证。** 获用户授权后，验证GHCR真实固定摘要匿名pull、包SHA与manifest匹配；未授权则本地功能与发布分开记，发行保持未完成。真实生成/向量功能验证若用户另要求，先确认预算/停止线再执行，默认不补历史三项测量。
- [ ] **6. 收尾提交。** 新用户中文说明、实际命令/结果/未测/回滚交接齐全；只stage自己任务文件，`git commit -m "test: verify startup release lifecycle and document platform evidence"`。没有用户技术冻结决定，保持OPEN/NOT_PERFORMED；不默认推送、合并或冻结。

## Coverage / Review Self-check

| 设计要求 | 所属任务 |
| --- | --- |
| 不安装宿主语言环境；共用核心/路径/环境发现 | T1/T2/T8 |
| 配置自动生成、安全密钥不轮换、Compose特殊字符 | T1/T4 |
| 向导先于业务API；session/Host/Origin/诊断 | T6 |
| 教师事务幂等，学生既有注册 | T3/T9 |
| 独立卷与项目，旧数据不接管/不读 | T2/T4/T9 |
| 迁移/F03索引门禁、健康与180秒截止 | T4/T5 |
| 生命周期、端口竞态、重复双击/崩溃恢复 | T1/T5/T8/T9 |
| 停机备份、整组恢复、空间/根密钥保护 | T7/T9 |
| 固定多架构镜像/匿名pull/发行完整性 | T2/T8/T9 |
| 三平台实机/主线回归/不冒充供应商测量 | T9 |

类型自审：后续仅引用Common Interfaces/T2的Runner/ReleaseManifest/T5的Controller；未提前实现GUI、全站配置API、业务模型迁移。每任务带红→绿和独立提交，五项Review Focus都对应具体测试。Go工具链当前未安装，各新测试/脚本尚不存在；计划不创建占位产物。

开发执行建议：本会话逐任务由Codex实施（native），组件接口耦合紧，优先省去每任务重新加载上下文；全部完成后做独立整支复审。另一选择是逐任务子代理实现/复审，增加上下文成本；只有用户选择后才启用代理。两种方式都不跨越真实调用/镜像发布/冻结授权。

## 资源与停止条件

- 当前本机无Go，需实施获批后安装/使用官方校验的1.26.8工具链；不会让新用户装Go。版本依据：[Go官方发布记录](https://go.dev/doc/devel/release)。
- Mac Intel/Windows实机及Docker发行权限未落实。三平台源码编译可先推进，但最终支持声明等待各自实际验收。
- .env格式依据：[Docker官方插值说明](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)。实施测试以Compose实际读取字节为准。
- 发现需要业务API/DTO/新迁移、自动旧库迁移或其他架构偏离时，停下更新规格并请用户确认，不临时扩张方案。
- 当前批准仅到正式设计；本计划获批并选定执行方式后实施。完成代码不自动获得发行、合并或技术冻结许可。
