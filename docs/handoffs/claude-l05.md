# L05 出站地址校验与钉 IP 传输

```text
task_id: L05
review_status: ready_for_review
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-contest-sprint-77644f
base_commit: 16d975a
head_commit: 本任务提交
changed_files:
  - src/backend/app/services/ai/outbound.py（新增）
  - src/backend/app/services/ai/compatible.py（_StdlibResponse.read 一处修复）
  - tests/backend/test_l05.py（新增 32 例）
  - docs/tasks.md、docs/handoffs/claude-l05.md
```

## 交付

- `check_endpoint_url`：只接受 https（`allow_private` 时另放行 http），拒绝内嵌凭据、查询串与片段、空主机、0 端口，原因为机读值。
- `is_public_address`：拆开 IPv4 映射地址后要求 `is_global` 且非组播；回环、私网、链路本地（含 169.254.169.254）、CGNAT、ULA 均为非公网。
- `check_endpoint`：解析域名，任一地址非公网即 `private_address`，解析失败或为空即 `unresolvable`。
- `GuardedTransport`：每次 `open` 都校验、解析一次并连接到已校验的第一个地址；TLS 用原域名做 SNI 与证书校验；`Host` 头保持原域名。不跟随重定向（客户端对 3xx 按格式错误处理，用例已覆盖）。
- `EndpointBlocked` 继承 `OSError`，运行期被模型客户端归为连接错误；配置接口在调用前单独校验以给出具体原因。

## 计划外修复：服务端关闭连接时客户端误报连接错误

- 现象：钉 IP 用例对本机 HTTP/1.0 桩服务失败，报 `ModelConnectionError`。
- 根因：服务端读完即关闭连接（HTTP/1.0 或 `Connection: close`）时，`http.client` 在响应体读完后关闭套接字；`_StdlibResponse.read` 下一次仍对该套接字调用 `settimeout`，抛 `EBADF`（`OSError`），被分类为连接错误。这是既有传输层的潜在缺陷，真实供应商返回 `Connection: close` 时同样会触发。
- 先加回归用例 `test_stdlib_transport_survives_a_server_that_closes_the_connection`（直接用既有 `StdlibTransport`），确认失败；修复为响应已关闭时直接返回 `b""`。

## verification

| 命令 | 结果 |
| --- | --- |
| `pytest tests/backend/test_l05.py` | 先收集失败；实现后 2 例失败（同一根因）；修复后通过 |
| `pytest tests/backend/test_l05.py tests/backend/test_e03.py tests/backend/test_e04.py` | 全部通过 |
| `./scripts/verify.sh` | exit 0（基础档） |
| 后端全量 | 与 L06 一起运行：exit 0，3623 通过、27 跳过（见 `claude-l06.md`） |

## unverified

- 真实 https 供应商经 `GuardedTransport` 的连接：在 L06/L10 用 DeepSeek 实测。
- IPv6 目标地址的钉连：用例只覆盖 IPv4 本机地址。

## api_and_data_changes

无接口或数据变化。

## rollback

回退本提交。

## next_action

L06（个人配置接口）。
