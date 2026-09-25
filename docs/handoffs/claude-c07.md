# Claude 交接：C07 上传及资料列表 API

- `task_id`: C07（GitHub issue #64）
- `review_status`: ready_for_review
- `worktree`: `/home/user/wt-c07-materials-api`，分支 `claude/c07-materials-api`
- `base_commit`: `71600b2`（第四批认领提交）；其上协调方提交 `9a4b5ba`（并入 ADR-017 基础 `d446ecc`）与 `6bc2ec4`（ADR-019 加 `python-multipart==0.0.32`）
- `head_commit`: 本交接所在提交
- 负责人：ArvinHan（Claude 后端子代理执行）
- 依据：`src/contracts/api.v1.yaml` 的 `listDocuments` / `uploadDocument`、`Document`、`DocumentFormat`、`UploadAccepted`；`src/contracts/errors.v1.md`「上传与解析」；`specs/identity-access.md` §4.1、§4.3；`docs/tasks.md` D-11、D-16、C06 节；ADR-019。

## 交付物

- `src/backend/app/api/materials.py`（新增）：`GET` / `POST /api/v1/courses/{cid}/documents`，`operation_id` 分别为 `listDocuments`、`uploadDocument`。只做协议转换：授权用 C03 的 `course_teacher`；上传路由不声明 `UploadFile` 参数，授权后有界解析表单（见「先授权、再有界解析」），取字段 `file` 交给服务层；`FileStorageError` 映射为 `Error` 响应：`UNSUPPORTED_FORMAT` 415、`FILE_TOO_LARGE` 413（`details.limit_bytes`）、`VALIDATION_ERROR` 422、`STORAGE_UNAVAILABLE` 503。C05 文件名错误的 `details.fields` 在此转成全局校验同形 `[{"in": "body", "field": "file", "reason": …}]`，不回显文件名。
- `src/backend/app/services/materials.py`（新增）：
  - `upload_material(settings, *, course_id, filename, content_type, chunks, idempotency_key=None) -> UploadResult(task_id, document_id)`：`FileStorage(STORAGE_DIR, UPLOAD_MAX_BYTES).save` 落盘 → C06 `create_material_task` 建资料与 queued 任务 → 返回。请求内不解析。
  - 补偿：建任务抛任何异常都先删除新落盘文件；`sqlite3.Error` 转为 `StorageWriteError`（503，不外露数据库原文），其余异常原样上抛（500）。C06 幂等重放（`created=False`）时删除新落盘、未被引用的文件，返回原资料与任务 ID。补偿删除本身失败只记日志，不掩盖原错误。
  - 未传 `idempotency_key` 时每次调用生成新 uuid（契约无幂等键，见待决 1）。
  - `list_course_materials(settings, course_id)`。
- `src/backend/app/schemas/materials.py`（新增）：`Document`、`UploadAccepted`、`DocumentFormat`、`TaskStage`。
- `tests/backend/test_c07.py`（新增，42 项；其中 3 项为移植 #229 的回归测试）。
- 范围扩展：
  - `src/backend/app/repositories/materials.py` **仅新增** `list_materials(sqlite_url, *, course_id)`；已有函数未改。
  - `src/backend/app/main.py` **仅**加路由 import 与 `include_router`。
  - `docs/tasks.md` 仅改 C07 行状态与证据。
  - 依赖：`src/backend/pyproject.toml` 加 `python-multipart==0.0.32`，由协调方在 `6bc2ec4` 按 ADR-019 提交（本任务未改 pyproject 与 decisions.md）。

## 接口 / 数据变更

- 新增两个 HTTP 端点，形状与契约一致，不改契约。
- **依赖变更（ADR-019）**：后端运行时依赖新增 `python-multipart==0.0.32`，FastAPI `UploadFile` 表单解析需要它。回滚：删除 pyproject 该行并重装后端依赖，同时撤下 `main.py` 中 `materials_router` 的注册（否则导入时报缺依赖）；数据与迁移不受影响。
- 无迁移、无表结构变更。`materials.parse_status` 列按 D-16 不再维护，本任务只读不写。

## 关键决定

- `parse_status`（D-16）：`LEFT JOIN` 每份资料「最新创建」的任务——`created_at` 最大者，同一时间戳按 `rowid`（插入顺序）取后插入者；关联子查询同时按 `course_id` 与 `document_id` 限定。无任务的资料用列值（默认 `queued`）。
- 列表排序：`uploaded_at` 升序，再按 `id` 升序（契约未规定，见待决 2）。
- 授权先于落盘：未授权请求不写文件、不写库（测试断言存储目录与表为空）。
- **先授权、再有界解析**（移植自协作者 539210 在 #229 的提交 `8514ecc`，ArvinHan 同意；ADR-019 决定 2 已同步改写）：
  - 上传路由不声明 `File`/`UploadFile` 参数，否则 FastAPI 会在 `course_teacher` 之前解析并暂存整个请求体；OpenAPI 请求体按契约经 `openapi_extra` 手写。
  - 授权后先看 `Content-Length`：大于 `UPLOAD_MAX_BYTES + MULTIPART_OVERHEAD_BYTES`（16 KiB，命名常量并注释）直接 413 `FILE_TOO_LARGE`（`details.limit_bytes`），不进入解析。
  - 再用包装的 `receive` 对实收字节计数，超限抛内部 `_BodyTooLarge` 转 413；`request.form(max_files=1, max_fields=8)`；`finally` 关闭表单。文件大小仍由 C05 `FileStorage` 精确校验。
  - 缺 `file` 字段仍经全局处理器返回 422 同形 `details.fields`（`reason: missing`）；表单格式错误或字段/文件数超限为 422（`reason: multipart_invalid`，此前 FastAPI 会返回非契约的 400）。
  - 路由改为 `async`，同步的 `upload_material` 经 `run_in_threadpool` 调用；服务层、补偿与 D-16 列表语义未改。

## 验证

命令（`V=/tmp/claude-0/-home-user-SmartSketch/f5e8fe9b-ebac-5377-b10c-8bfbef53bfde/scratchpad/venv`，在 worktree 根目录）：

| 命令 | 结果 |
| --- | --- |
| 红 1：`PYTHONPATH=$PWD/src/backend $V/bin/python -m pytest tests/backend/test_c07.py -q`（仅测试） | 收集错误：`ImportError: cannot import name 'materials' from 'app.services'` |
| 红 2：同上（服务层桩 `NotImplementedError`、无路由） | 39 failed |
| 绿：同上 | 39 passed |
| 移植 #229 红：加 3 条回归测试、实现未改 | 3 failed、39 passed（匿名与超大请求被 FastAPI 先解析，桩抛错后返回 400；`Content-Length: 0` 时 17 000 字节触达 `FileStorage.save`） |
| 移植 #229 绿：同上（每次用新的 `PYTHONPYCACHEPREFIX`） | 42 passed |
| `PYTHONPATH=$PWD/src/backend $V/bin/python -m pytest tests/backend -q` | 1089 passed（基线 1050 + 39），1 条既有 Starlette/httpx 弃用警告 |
| 移植 #229 后（并入最新 main `6c996b8` 之上）：`tests/backend -q -p no:cacheprovider` | 1718 passed，1 条既有弃用警告 |
| 移植 #229 后：`PATH=$V/bin:…/b15-tools/node_modules/.bin:$PATH … pytest tests/contracts tests/tooling -q -p no:cacheprovider` | 305 passed |
| 移植 #229 后：`PATH=$V/bin:…/b15-tools/node_modules/.bin:$PATH ./scripts/verify.sh`；`git diff --check` | 均 exit 0 |
| `PATH=$V/bin:…/b15-tools/node_modules/.bin:$PATH PYTHONPATH=$PWD/src/backend $V/bin/python -m pytest tests/contracts tests/tooling -q` | 272 passed、1 failed：`test_b07::test_dispatcher_reports_aggregate_status[0-PASS]`（已知基线，#224 修复）。注：PATH 不含 `$V/bin` 时另有 3 项因找不到 `datamodel-codegen` 失败，属环境，与本任务无关 |
| `PATH=$V/bin:…/b15-tools/node_modules/.bin:$PATH ./scripts/verify.sh` | exit 0（`PASS contracts gate`、`Scaffold verification passed.`） |
| `git diff --check` | exit 0 |

测试覆盖：
- 成功：202 与响应键；资料/任务落库、任务 queued 且进度 0；四种格式（含 `.markdown` + `application/octet-stream`）；恰好等于上限；两次上传产生两对新 ID。
- 边界 / 失败：超限 1 字节 413 + `limit_bytes` 且不留文件与行；6 种非法格式/伪装内容/声明类型不符/空文件 415；文件名超长 422 同形 `details.fields`；缺 `file` 字段 422；存储目录不可用 503；建任务时数据库错误 503 且删除新文件、不外露原文；未预期异常 500 且删除新文件；服务层固定键重放删除新文件、返回原 ID。
- 访问矩阵：GET/POST × 匿名 401、非成员教师 403 `COURSE_FORBIDDEN`、学生成员 403 `ROLE_FORBIDDEN`，且不落盘不写库；不存在的课程 403 `COURSE_FORBIDDEN`；匿名且缺字段仍 401；向他人课程上传 403。
- 列表：空课程 `[]`；上传后返回契约 `Document` 七个键；课程隔离；`parse_status` 取最新创建任务而非最近更新任务、也不取列值；同一 `created_at` 取后插入者；无任务回退列默认值 `queued`；按 `uploaded_at, id` 排序；OpenAPI 暴露两个 `operationId` 与 202/413/415。

## 反向篡改（改前 `cp` 备份，改回后 `cmp` 一致）

| # | 篡改 | 结果 |
| --- | --- | --- |
| T1 | 列表去掉 `WHERE m.course_id = ?` 隔离 | 1 failed（课程隔离） |
| T2 | `parse_status` 直接取列值 | 2 failed |
| T3 | 最新任务改取最早（`ASC`） | 2 failed |
| T4 | 补偿删除改为空操作 | 3 failed（数据库错误、未预期异常、重放） |
| T5 | 上限写死 52 428 800，不读 `UPLOAD_MAX_BYTES` | 1 failed（413） |
| T6 | 去掉重放时的删除 | 1 failed |

六处全部被检出；恢复后 39 passed。

移植 #229 后的反向篡改（改前 `cp` 备份 `api/materials.py`，改回后 `cmp` 一致；每次换新的字节码缓存目录）：

| # | 篡改 | 结果 |
| --- | --- | --- |
| P1 | 恢复 `file: UploadFile = File(...)` 参数，表单改取 FastAPI 已解析的 `request.form()` | 3 failed（三条新回归测试） |
| P2 | 去掉实收字节计数（超限判断改为 `if False`） | 1 failed（`Content-Length` 不可靠用例） |
| P3 | 去掉 `Content-Length` 预检 | 1 failed（超大请求在解析前 413 用例） |

三处全部被检出；恢复后 42 passed。另：P1 若只加回参数而仍走有界解析，请求体被读两次会使测试挂起，故 P1 按「整体退回 FastAPI 预解析」篡改。

## 风险

- ~~授权前完整接收请求体~~ **已解决**：原先 FastAPI 在执行依赖前解析整个 multipart 请求体，匿名或越权的大请求在 401/403 前已被完整接收。现按「先授权、再有界解析」处理（移植自 539210 的 #229，提交 `8514ecc`）：授权前不读请求体，授权后请求体上限为 `UPLOAD_MAX_BYTES` + 16 KiB。反向代理仍可另设上限作纵深防御。
- 有界解析中途因超限中止时，Starlette 已创建的临时文件不经 `form.close()`，靠垃圾回收关闭；单次最多约 `UPLOAD_MAX_BYTES` + 16 KiB。
- 补偿删除失败（如磁盘只读）时只记日志，会留下无引用文件；需后续清理任务兜底。
- 进程在落盘后、建任务前崩溃也会留下无引用文件，本任务不处理。

## 待决（写入 `docs/tasks.md` 前请协调方确认）

1. **契约无幂等键**：`uploadDocument` 没有 `Idempotency-Key`，路由每次请求生成新 uuid，经 HTTP 不会出现重放；重放补偿分支只在服务层用固定键测试。是否在契约加幂等键归 B 组。
2. **列表排序**：契约未规定，当前按 `uploaded_at, id` 升序；如需倒序或分页需改契约。
3. ~~**请求体上限前置**~~：已按移植 #229 的做法在应用层解决（ADR-019 决定 2），不再待决。
4. **无任务的资料**：D-16 下正常流程不会出现（资料与任务同事务创建），当前回退列默认值 `queued`；列清理迁移时需同时改为固定 `queued` 或其他语义。

## 下一步

- **C11**（任务查询/SSE）：用本端点返回的 `task_id` 调 `GET /api/v1/tasks/{tid}`；`Document.parse_status` 与任务快照 `stage` 同源（D-16），无需 worker 回写资料列。
- **D11**（worker 领取解析）：按 `materials.storage_name` 调 `FileStorage.path_for` 读文件；上传端不会触发解析。
- **H02**（前端资料上传/列表）：以 `multipart/form-data` 字段 `file` 上传，处理 202/413（`details.limit_bytes`）/415（`details.supported`）/422/503；列表以 `parse_status` 展示状态，失败或取消后引导重新上传（D-16，无再处理端点）。
