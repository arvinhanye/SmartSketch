# Claude 交接：C05 文件落盘边界

- `task_id`: C05（GitHub issue #62，协调方已认领）
- `review_status`: ready_for_review
- `worktree`: `/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/agent-aed9e93d65bae34c0`，分支 `claude/c05-file-storage`
- `base_commit`: `68affa8`（origin/main，PR #179 合入点）
- `head_commit`: 见 PR 最新提交
- 负责人：ArvinHan（Claude 执行）
- 依据：`docs/atomic-task-plan.md` C05 行；`src/contracts/errors.v1.md`「上传与解析」；`api.v1.yaml` 的 `uploadDocument`、`DocumentFormat`；`specs/teacher-review-publish.md` 快照格式中的 `content_hash`（`sha256:…`）。

## 交付物

- `src/backend/app/services/file_storage.py`（新增）
  - `FileStorage(root, max_bytes)`：根目录不存在则创建（0700）并解析为绝对路径；`max_bytes` 必须为正整数。
  - `save(original_filename, declared_type, chunks) -> StoredFile`：分块读取、校验、落盘。
  - `path_for(storage_name)`：只接受本服务生成的名字（`^[0-9a-f]{32}\.(pdf|docx|txt|md)$`），并校验解析后仍在根目录内。
  - `delete(storage_name) -> bool`：供 C07 补偿删除；不存在返回 `False`。
  - `iter_file(fileobj, chunk_size=64 KiB)`：把 `UploadFile.file` 这类二进制文件对象转为块迭代器。
  - `StoredFile`：`storage_name`、`path`、`original_filename`、`format`（`pdf|docx|txt|markdown`，与 `DocumentFormat` 同值）、`size_bytes`、`content_hash`（`sha256:<hex>`）。
  - 异常均继承 `FileStorageError`，`code` 取自 `ErrorCode`：

    | 异常 | `code` | HTTP（按 errors.v1.md） | `details` |
    | --- | --- | --- | --- |
    | `UnsupportedFormatError` | `UNSUPPORTED_FORMAT` | 415 | `reason ∈ {extension, declared_type, content_mismatch, empty}`，`supported: [pdf, docx, txt, markdown]` |
    | `FileTooLargeError` | `FILE_TOO_LARGE` | 413 | `limit_bytes` |
    | `InvalidFilenameError` | `VALIDATION_ERROR` | 422 | `fields.file ∈ {empty, path_component, control_character, encoding, too_long}` |
    | `StorageWriteError` | `STORAGE_UNAVAILABLE` | 503 | 无 |

    流自身抛出的异常（客户端断开等）清理后**原样上抛**，不包装。
- `tests/backend/test_c05.py`（新增，61 个用例）。

## 关键决定

1. **格式三重校验**：扩展名（`.pdf/.docx/.txt/.md/.markdown`，不区分大小写）决定格式；声明类型为空、`application/octet-stream` 时忽略，否则必须属于该格式的允许集合（Markdown 另允许 `text/plain`、`text/x-markdown`），参数如 `; charset=` 忽略；内容特征：PDF 以 `%PDF-` 开头，DOCX 以 `PK\x03\x04` 开头且写完后 ZIP 目录含 `[Content_Types].xml` 与 `word/document.xml`（xlsx 等改名拒绝，不解压，不受压缩炸弹影响），TXT/Markdown 不得含 NUL 等 C0 控制字符（允许 `\t\n\v\f\r` 与 ESC），且不得以 `%PDF-`、`PK\x03\x04` 开头。签名检查在首块就能判错，伪扩展名不必读完整个流。
2. **空文件**按 `UNSUPPORTED_FORMAT`（`reason = empty`）拒绝：它无法被嗅探为任何支持格式。
3. **文件名含路径成分即拒绝**（`/`、`\`、`.`、`..`、控制字符、超过 255 字节 UTF-8、非字符串），不做“取 basename 后放行”。原始文件名只作元数据返回，从不参与路径拼接。
4. **大小**：边读边计数，累计超过 `max_bytes` 时在写入该块前中止；恰好等于上限通过。
5. **原子写入**：`tempfile.mkstemp` 在根目录下建 `.upload-*.part`（0600、O_EXCL）→ 写完 `fsync` → 关闭 →（DOCX 结构检查）→ `os.link` 到 `<token_hex(16)><规范扩展名>`（目标已存在即失败，换名重试最多 8 次，绝不覆盖）→ `fsync` 目录 → `finally` 中总是删除临时文件（包括 `KeyboardInterrupt`）。目录 fsync 失败时撤回已发布文件并报 `STORAGE_UNAVAILABLE`。
6. 本服务不写数据库（C06），不含 HTTP 路由（C07）；不读取 `config.py`，根目录与上限由调用方传入。

## 红绿记录

- 红：临时移走实现后运行 `<venv>/bin/python -m pytest tests/backend/test_c05.py -q` → 收集阶段 `ImportError: cannot import name 'file_storage'`，`1 error`。
- 绿：`<venv>/bin/python -m pytest tests/backend/test_c05.py -q` → `61 passed`；`-W error` 下同样 `61 passed`。
- 全部后端：`<venv>/bin/python -m pytest tests/backend -q` → `137 passed, 1 warning`（警告为 starlette `TestClient` 使用 httpx 的弃用提示，既有，与本任务无关）。
- `./scripts/verify.sh`（系统 python3）→ 退出码 0，`Scaffold verification passed.`
- `git diff --check` → 退出码 0。
- 环境：`python3 -m venv <scratchpad>/venv`，`pip install -e '<worktree>/src/backend[test]'`；测试后已 `rm -r src/backend/smartsketch_backend.egg-info`。

覆盖：五种合法格式（字节构造的 TXT/MD/PDF/DOCX）、声明类型缺省/通用/带参数、存储名与原文件名无关、恰好上限、超 1 字节、无限流提前中止、`../`/绝对路径/Windows 路径/控制字符/超长文件名、伪扩展名（MZ、ELF 改名 PDF，PDF 改名 DOCX，xlsx 式 ZIP 改名 DOCX，损坏 ZIP，二进制改名 TXT/MD，PDF/ZIP 改名文本）、声明类型冲突、空文件、截断签名、中途抛异常的流、`KeyboardInterrupt`、非 bytes 块、`fsync` 失败、发布（link）失败、存储名碰撞不覆盖、16 线程同名并发互不覆盖、最终文件权限不对组/其他用户开放，且每个失败用例都断言根目录为空。

## 给 C06 / C07 的使用说明

```python
from starlette.concurrency import run_in_threadpool
from app.services.file_storage import FileStorage, FileStorageError, iter_file

storage = FileStorage(settings.STORAGE_DIR, max_bytes=settings.<上限变量>)  # 变量名待协调方定
stored = await run_in_threadpool(
    storage.save, upload.filename, upload.content_type, iter_file(upload.file)
)
try:
    ...  # C06：同一事务写 material（format、size_bytes、content_hash、storage_name、原始文件名）与 queued 任务
except Exception:
    storage.delete(stored.storage_name)  # 补偿：建任务失败删除已落盘文件
    raise
```

- `save` 是同步阻塞 I/O，API 中须放入线程池，不要在事件循环里直接调用。
- `FileStorageError` 按 `exc.code` / `exc.message` / `exc.details` 映射为 `Error` 响应体；HTTP 状态见上表。
- 注意：Starlette 在进入处理函数前已把 multipart 整体读入 `SpooledTemporaryFile`，本服务的上限只约束落盘；若要在网络层尽早拒绝超大请求，C07 需另行按 `Content-Length` 或 ASGI 层限流（不在 C05 范围）。
- 数据库只存 `storage_name`，读取文件用 `storage.path_for(storage_name)`，不要存或拼接绝对路径。

## 需协调方补的配置项（本任务按文件锁未改 `config.py`）

1. **存储根目录**：`STORAGE_DIR`（`docs/reviews/branch-integration-map.md` 已计划从 740adb 导入，尚未进入 main 的 `config.py` / `.env.example` / `docs/integrations.md`）。须与 API、worker 指向同一目录。
2. **单文件上限**：规格与契约均未给出数值和变量名（如 `UPLOAD_MAX_BYTES`）。需产品/协调方定值并登记到 `config.py`、`.env.example`、`docs/integrations.md`；前端 `FILE_TOO_LARGE` 提示依赖 `details.limit_bytes`。

## 未验证项与风险

- **文本编码未强制**：TXT/MD 只按“无二进制控制字符”判定，不要求 UTF-8，GBK/GB18030 文本可通过；UTF-16 文本（含 NUL）会被拒。实际解码交给解析阶段（`DOCUMENT_UNREADABLE`）。若需放行 UTF-16，需另定规则。
- PDF 只校验文件头 `%PDF-` 在偏移 0；前置垃圾字节的 PDF（阅读器可容忍 1024 字节内）会被拒。PDF 内部完整性由解析阶段判断。
- 进程被 `SIGKILL` 或断电时可能遗留 `.upload-*.part` 临时文件（不会以存储名出现）；目前没有过期临时文件清理，建议后续由运维任务或 worker 启动时清理。
- 依赖硬链接（`os.link`）发布；APFS/ext4/NTFS 支持，若 `STORAGE_DIR` 放在不支持硬链接的文件系统（如部分网络盘、exFAT）将报 `STORAGE_UNAVAILABLE`。
- 仅在 macOS（APFS）上运行过；Linux/Windows 未实测。
- 首次 `pip install -e` 时编辑安装映射意外指向了另一 worktree `a05-aa1561`，那里可能因此出现 `src/backend/smartsketch_backend.egg-info`（13:42 生成）；本任务不越界清理，请该 worktree 的负责人确认后删除。

## 下一步

- 协调方：定 `STORAGE_DIR` 与上限变量，更新 `config.py`、`.env.example`、`docs/integrations.md`；审核后合并，并在 `docs/tasks.md` 记录 C05 状态与验收证据。
- C06：资料/修订记录字段对齐 `StoredFile`（`storage_name`、`content_hash`、`size_bytes`、`format`）。
- C07：按上文接入并实现失败补偿。
