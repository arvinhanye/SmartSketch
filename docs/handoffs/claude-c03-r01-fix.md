# Claude 交接：修复 PR #216（C03）审查阻塞项 C03-R01

- 日期：2026-09-25
- 分支：`codex/c03-access-boundary`（Codex 的 PR #216）；ArvinHan 授权 Claude 直接修复
- 基线：先合入 `origin/main`（B14 #214、D08 #215），解决 `docs/tasks.md` 冲突，两节都保留

## 问题

`src/backend/app/services/access.py` 把 5 种拒绝错误定义成模块级的**异常实例**，每次请求都 `raise` 同一个对象。CPython 每抛出一次，都会把本次的帧追加到这个对象的 `__traceback__` 上。在 `44f77cf` 上复现：认证失败 500 次后，traceback 为 1500 帧，并且引用着全部 500 个请求的 `token` 局部变量。未登录的请求方可以借此让内存无限增长，令牌也会一直留在内存里。

附带的 P3：签名段没有校验 base64url 字符集，`b64decode(..., altchars=b"-_")` 还会接受 `+`/`/`，同一个签名因此有多种写法。

## 修复

- `access.py`：5 个单例改为工厂函数 `unauthenticated()`、`course_forbidden()`、`role_forbidden()`、`not_found()`、`graph_not_published()`，每次抛出都是新实例；状态码、错误码、消息都不变。
- `access.py`：签名段与 header/payload 使用同一个 `_B64URL` 字符集检查。
- `api/dependencies.py`：改用工厂函数。
- `tests/backend/test_c03.py` 新增 2 个回归测试：
  - 拒绝 50 次，每次都是不同实例，traceback 深度不增长，覆盖 UNAUTHENTICATED、COURSE_FORBIDDEN、NOT_FOUND；
  - 把签名里的 `-`/`_` 换成 `+`/`/` 后，必须被拒。

## 验证

| 命令 | 结果 |
| --- | --- |
| 修复前 `pytest tests/backend/test_c03.py -q` | 2 failed / 17 passed：「UNAUTHENTICATED reuses one instance」「DID NOT RAISE AccessDenied」 |
| 修复后，同上 | 19 passed |
| `pytest tests/backend -q` | 1034 passed，1 warning（既有 Starlette 弃用提示） |
| 复现脚本：认证失败 500 次 | 每次 traceback 都是 3 帧，500 个不同实例 |
| `./scripts/verify.sh`、`git diff --check` | exit 0（`Scaffold verification passed.`）；diff check 通过 |

没有契约或接口变更。对外错误响应（状态码、`code`、`message`）完全不变。
