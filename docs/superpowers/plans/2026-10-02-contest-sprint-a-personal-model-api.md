# A10 冲刺计划 A：个人模型 API 与真实运行路径（第 1–3 天）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让教师任务与学生问答各自使用本人加密保存的模型 API 配置运行，并提供正式启动入口、真实在线向量和第 1 天的真实耗时基线。

**Architecture:** 新增 `LLM_MODE=personal`。每个用户一行 AES-256-GCM 加密的配置；上传时在建任务的同一事务里把密文复制成任务快照，worker 按任务取工具包；问答按「用户 + 配置版本」缓存独立的调用策略。所有用户填写的地址在解析后校验并钉住 IP。`demo`/`fake`/`live` 的全局装配路径保持不动。

**Tech Stack:** Python 3.11+、FastAPI、SQLite、`cryptography`（新增）、标准库 `http.client`；Vue 3 + TypeScript + Pinia + Vitest；契约真源 `src/contracts/api.v1.yaml`。

**Spec:** `docs/superpowers/specs/2026-10-02-contest-sprint-design.md`

**范围说明：** 规格的 L01–L10 在本计划内。L11–L15（教师闭环验收与第 4 天前端修复）写成计划 B，L16–L19（性能、材料、冻结）写成计划 C，分别在第 3 天、第 4 天结束时依据当时的实测结果编写，再交用户确认。原因：这些任务的具体步骤取决于本计划产生的基线数字和走通主线时发现的缺陷。

## Global Constraints

- 所有命令在工作区根目录 `/Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-contest-sprint-77644f` 执行；不 `cd` 到主检出，不改 Codex 工作区。
- 后端分层 `api → schemas → services → repositories`；路由不含业务规则与 SQL。前端分层 `views / components / composables / api`。
- 对外 DTO 只从 `src/contracts/v1/generated/` 生成物导入；先改 `api.v1.yaml` 再跑 `./scripts/gen-contracts.sh`，不手改生成文件。
- 密钥不进响应、日志、`model_calls`、任务 payload、SSE、`localStorage`/`sessionStorage`、Pinia 持久化、Git。
- `personal` 模式下未配置即拒绝（`MODEL_CONFIG_REQUIRED`），不回退到 `demo`、`fake` 或任何全站 key。
- 任务状态机与 SSE 语义不变：`awaiting_review` 不是已发布；失败/取消后重新上传，不新增重试端点。
- 大模型真实调用预算：累计计费 token ≤ 500 万（约 30 元）；`.env` 已设 `LLM_DAILY_TOKEN_BUDGET=700000`、`LLM_TASK_TOKEN_BUDGET=500000`。每次真实运行后在交接文件登记累计用量。
- 测试用隔离 SQLite（`tmp_path`）与注入的假传输，不联网。不删测试、不改通过阈值、SKIP 不算 PASS。
- 每个任务开始前在 `docs/tasks.md` 认领，结束时写 `docs/handoffs/claude-<id>.md`，并运行 `./scripts/verify.sh`。
- 提交只在本分支本地进行，按原子任务选文件；推送与合并需用户另行授权。提交信息以 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` 结尾。
- 后端测试命令统一为 `PYTHONPATH=src/backend .venv/bin/python -m pytest <文件> -q -p no:cacheprovider`；前端为 `npm run test --prefix src/frontend -- --run <文件名>`。

## 文件结构

| 文件 | 责任 |
| --- | --- |
| `src/backend/migrations/015_user_model_configs.sql`（新） | 两张新表与两个可空新列 |
| `src/backend/app/services/credentials.py`（新） | `CredentialCipher`、`SealedKey`、三个异常 |
| `src/backend/app/repositories/model_configs.py`（新） | 用户配置与任务快照的全部 SQL |
| `src/backend/app/services/ai/outbound.py`（新） | 地址校验、公网判定、钉 IP 传输 |
| `src/backend/app/services/model_configs.py`（新） | 查看、保存、清除、测试连接的业务规则与限流 |
| `src/backend/app/api/model_config.py`（新） | `/api/v1/me/model-config` 四个操作 |
| `src/backend/app/workers/toolkits.py`（新） | 按租约构建抽取工具包 |
| `src/backend/app/services/qa/user_models.py`（新） | 按用户缓存问答改写器与生成器 |
| `src/backend/app/config.py` | `personal` 模式、根密钥、放行开关、`local` 拒绝 |
| `src/backend/app/repositories/tasks.py`、`services/materials.py`、`api/materials.py` | 上传记录创建者并绑定快照 |
| `src/backend/app/workers/{extract_task,persist_graph,runner}.py` | 工具包解析器、凭据失败终止、终态清理 |
| `src/backend/app/services/ai/policy.py`、`repositories/model_calls.py` | 调用归属用户、按用户日预算 |
| `src/backend/app/services/qa/{chat,rewrite,generate}.py`、`api/chat.py` | 问答按用户取模型 |
| `src/frontend/src/api/modelConfig.ts`、`stores/runtime.ts`、`composables/useModelConfig.ts`、`views/ModelSettingsView.vue`（新） | 设置页 |
| `src/frontend/src/{router/index.ts,main.ts,App.vue}`、`views/{MaterialsView,ChatView}.vue`、`composables/{useMaterials,useChat}.ts` | 路由、导航、模式标识、未配置引导 |
| `scripts/start.sh`（新）、`scripts/start-demo.sh`、`scripts/check-embedding.py`（新） | 正式启动入口与向量联调检查 |
| `evaluation/measure_web_flow.py`（新） | 经 HTTP 接口测抽取与问答耗时 |

---

### Task 0：提交已获批的设计文档

**Files:**
- Commit: `docs/superpowers/specs/2026-10-02-contest-sprint-design.md`、`docs/superpowers/plans/2026-10-02-contest-sprint-a-personal-model-api.md`、`docs/handoffs/claude-l00-sprint-design.md`、`docs/tasks.md`

- [ ] **Step 1：确认只有这四个文件有变更**

Run: `git status --short`
Expected: 仅上述四个路径（`.env` 被忽略，不出现）。

- [ ] **Step 2：把 L00 状态改为 DONE 并提交**

把 `docs/tasks.md` 中 L00 行的状态改为 `DONE（规格与计划 A 已获用户确认）`。

```bash
git add docs/superpowers/specs/2026-10-02-contest-sprint-design.md \
        docs/superpowers/plans/2026-10-02-contest-sprint-a-personal-model-api.md \
        docs/handoffs/claude-l00-sprint-design.md docs/tasks.md
git commit -m "docs: A10 冲刺设计规格与计划 A（L00）

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 1（L01）：隔离环境与三档门禁基线

**Files:**
- Create: `docs/handoffs/claude-l01.md`
- Modify: `docs/tasks.md`（认领 L01）

**Interfaces:**
- Produces: `.venv/bin/python`（后续所有后端命令使用）、`src/frontend/node_modules`、根目录 `node_modules`、端口 7688/7475 上的独立 Neo4j。

- [ ] **Step 1：认领**

在 `docs/tasks.md` 顶部 L00 一节之后新增「2026-10-02 Claude 认领：冲刺计划 A」一节，表格含 L01–L10 十行，L01 状态 `IN_PROGRESS`，其余 `TODO`；每行的范围与验收照抄规格第 7 节。

- [ ] **Step 2：建虚拟环境并安装锁定依赖**

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e 'src/backend[test]'
.venv/bin/python -c "import fastapi, neo4j, pytest, yaml; print('backend deps ok')"
npm ci --prefix src/frontend
npm ci
```

Expected: 输出 `backend deps ok`，两次 `npm ci` 以 0 退出。任何一步失败都记录原始报错，不升级版本绕过。

- [ ] **Step 3：读集成门禁脚本，确认它不会碰现有服务**

Run: `sed -n 1,80p scripts/verify/integration.sh`
确认它使用一次性 Neo4j 且端口不与 7687（主检出）冲突；若会冲突，停止并把冲突端口写入交接，交用户决定，不强行终止别人的进程。

- [ ] **Step 4：跑三档门禁并保存日志**

```bash
mkdir -p .demo/logs
./scripts/verify.sh              > .demo/logs/verify-basic.log 2>&1; echo "basic=$?"
PYTHON=.venv/bin/python ./scripts/verify.sh full > .demo/logs/verify-full.log 2>&1; echo "full=$?"
PYTHON=.venv/bin/python ./scripts/verify.sh integration > .demo/logs/verify-integration.log 2>&1; echo "integration=$?"
```

Expected: 三个退出码如实记录。失败时保留日志并在交接中列出失败用例名，不修不相关的失败；阻断本计划的失败才在本任务内修（先写复现测试）。

- [ ] **Step 5：启动独立 Neo4j 并确认与主检出互不影响**

```bash
./scripts/dev-up.sh
docker ps --format '{{.Names}} {{.Ports}}' | grep -E '7688|7687'
```

Expected: 两个容器并存，本工作区的容器映射 7688/7475，主检出的仍是 7687/7474。

- [ ] **Step 6：写交接并提交**

`docs/handoffs/claude-l01.md` 按交接模板填写：三个退出码、失败用例、Python 与 Node 版本、容器名。把 L01 改为 `DONE` 并附证据。

```bash
git add docs/tasks.md docs/handoffs/claude-l01.md
git commit -m "chore: L01 隔离环境与门禁基线

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2（L02）：真实基线测量

**前置条件：** `.env` 的 `LLM_API_KEY` 与 `EMBEDDING_API_KEY` 已由用户填写。未填写时跳过本任务先做 Task 3，并在交接中写明「L02 等待凭据」；不向用户索要把 key 发到聊天。

**Files:**
- Create: `evaluation/measure_web_flow.py`
- Create: `tests/backend/test_l02_measure.py`
- Create: `evaluation/reports/l02-baseline-2026-10.md`
- Create: `docs/handoffs/claude-l02.md`

**Interfaces:**
- Produces: `measure_web_flow.py` 的命令行
  `python evaluation/measure_web_flow.py extract --base-url URL --username U --password-env VAR --course-name NAME --file PATH`（打印一行 JSON：`course_id`、`task_id`、`stage`、`elapsed_seconds`、`file_bytes`）
  与 `... ask --base-url URL --username U --password-env VAR --course-id CID --questions FILE`（每题一行 JSON：`question`、`status`、`http_status`、`elapsed_seconds`、`latency_ms`、`citations`）。计划 C 的 L16 复用它。

- [ ] **Step 1：写失败测试（纯函数部分）**

```python
# tests/backend/test_l02_measure.py
"""L02：测量脚本的纯函数——multipart 编码与任务终态判定。脚本本身的联网部分不在单测内。"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("measure_web_flow", ROOT / "evaluation/measure_web_flow.py")
measure = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(measure)


def test_multipart_body_contains_filename_and_bytes():
    content_type, body = measure.encode_multipart("ch3.md", b"# title\n", boundary="BOUND")
    assert content_type == "multipart/form-data; boundary=BOUND"
    assert b'name="file"; filename="ch3.md"' in body
    assert b"\r\n\r\n# title\n\r\n--BOUND--\r\n" in body


def test_terminal_stages():
    assert measure.is_terminal("awaiting_review")
    assert measure.is_terminal("failed")
    assert measure.is_terminal("cancelled")
    assert not measure.is_terminal("extracting")
```

- [ ] **Step 2：运行确认失败**

Run: `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_l02_measure.py -q -p no:cacheprovider`
Expected: FAIL（文件不存在）。

- [ ] **Step 3：写脚本**

```python
# evaluation/measure_web_flow.py
#!/usr/bin/env python3
"""经真实 HTTP 接口测量抽取与问答耗时（L02、L16）。只用标准库；不读也不打印任何密钥。

计时边界（规格第 5 节）：
- extract：发出上传请求 → 任务快照 stage 进入 awaiting_review / failed / cancelled。
- ask：发出问答请求 → 收到完整 JSON 响应；同时记录服务端 latency_ms。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

TERMINAL = frozenset({"awaiting_review", "completed", "failed", "cancelled"})


def is_terminal(stage: str) -> bool:
    return stage in TERMINAL


def encode_multipart(filename: str, data: bytes, *, boundary: str) -> tuple[str, bytes]:
    head = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n").encode()
    return f"multipart/form-data; boundary={boundary}", head + data + f"\r\n--{boundary}--\r\n".encode()


def call(base: str, method: str, path: str, *, token: str | None = None, body: bytes | None = None,
         content_type: str = "application/json", accept: str = "application/json", timeout: float = 120):
    request = urllib.request.Request(base.rstrip("/") + path, data=body, method=method)
    request.add_header("Accept", accept)
    if body is not None:
        request.add_header("Content-Type", content_type)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        raw = error.read()
        return error.code, json.loads(raw) if raw else None


def login(base: str, username: str, password_env: str) -> str:
    password = os.environ.get(password_env)
    if not password:
        raise SystemExit(f"环境变量 {password_env} 未设置")
    status, body = call(base, "POST", "/api/v1/auth/login",
                        body=json.dumps({"username": username, "password": password}).encode())
    if status != 200:
        raise SystemExit(f"登录失败：HTTP {status}")
    return body["access_token"]


def cmd_extract(args: argparse.Namespace) -> int:
    token = login(args.base_url, args.username, args.password_env)
    status, course = call(args.base_url, "POST", "/api/v1/courses", token=token,
                          body=json.dumps({"name": args.course_name}).encode())
    if status != 201:
        raise SystemExit(f"建课失败：HTTP {status}")
    data = Path(args.file).read_bytes()
    content_type, body = encode_multipart(Path(args.file).name, data, boundary="measure-web-flow-boundary")
    started = time.monotonic()
    status, accepted = call(args.base_url, "POST", f"/api/v1/courses/{course['id']}/documents", token=token,
                            body=body, content_type=content_type)
    if status != 202:
        raise SystemExit(f"上传失败：HTTP {status} {accepted}")
    stage = "queued"
    while not is_terminal(stage):
        if time.monotonic() - started > args.max_seconds:
            break
        time.sleep(0.5)
        _, task = call(args.base_url, "GET", f"/api/v1/tasks/{accepted['task_id']}", token=token)
        stage = task["stage"]
    print(json.dumps({"course_id": course["id"], "task_id": accepted["task_id"], "stage": stage,
                      "elapsed_seconds": round(time.monotonic() - started, 2), "file_bytes": len(data)},
                     ensure_ascii=False))
    return 0 if stage == "awaiting_review" else 1


def cmd_ask(args: argparse.Namespace) -> int:
    token = login(args.base_url, args.username, args.password_env)
    questions = [line.strip() for line in Path(args.questions).read_text(encoding="utf-8").splitlines() if line.strip()]
    for question in questions:
        started = time.monotonic()
        status, body = call(args.base_url, "POST", f"/api/v1/courses/{args.course_id}/chat", token=token,
                            body=json.dumps({"question": question}).encode(), timeout=60)
        elapsed = round(time.monotonic() - started, 2)
        body = body or {}
        print(json.dumps({"question": question, "http_status": status, "status": body.get("status") or body.get("code"),
                          "elapsed_seconds": elapsed, "latency_ms": body.get("latency_ms"),
                          "citations": len(body.get("citations") or [])}, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("extract", "ask"):
        p = sub.add_parser(name)
        p.add_argument("--base-url", required=True)
        p.add_argument("--username", required=True)
        p.add_argument("--password-env", required=True)
    sub.choices["extract"].add_argument("--course-name", required=True)
    sub.choices["extract"].add_argument("--file", required=True)
    sub.choices["extract"].add_argument("--max-seconds", type=float, default=900)
    sub.choices["ask"].add_argument("--course-id", required=True)
    sub.choices["ask"].add_argument("--questions", required=True)
    args = parser.parse_args(argv)
    return cmd_extract(args) if args.command == "extract" else cmd_ask(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4：运行确认通过**

Run: `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_l02_measure.py -q -p no:cacheprovider`
Expected: 2 passed。

- [ ] **Step 5：启动真实链路（真实大模型 + 在线向量）**

```bash
scripts/start-demo.sh --live --no-open
```

Expected: 输出 API `http://127.0.0.1:8001`、前端 `http://localhost:5174`，账号 `demo_teacher`、`demo_student`。启动失败且原因是向量服务地址或参数时，核对百炼文档后只改 `.env` 的 `EMBEDDING_BASE_URL`，把修正写入交接。此终端保持运行，后续步骤在另一个终端执行。

- [ ] **Step 6：测一章 Markdown 的抽取耗时**

```bash
export MEASURE_PASSWORD=smartsketch-demo
.venv/bin/python evaluation/measure_web_flow.py extract --base-url http://127.0.0.1:8001 \
  --username demo_teacher --password-env MEASURE_PASSWORD \
  --course-name "L02 基线 数据结构第3章" --file datasets/demo/ch3-stack-queue.md | tee .demo/logs/l02-extract.json
```

然后读出分阶段数据（`<TASK_ID>` 取上一步输出）：

```bash
sqlite3 src/backend/storage/smartsketch.sqlite3 "
SELECT purpose, count(*), sum(usage_input), sum(usage_output), max(latency_ms), round(avg(latency_ms))
FROM model_calls WHERE task_id='<TASK_ID>' GROUP BY purpose;
SELECT count(*) FROM task_chunk_checkpoints WHERE task_id='<TASK_ID>';"
```

Expected: 一行 JSON，`stage` 为 `awaiting_review`。如实记录 `elapsed_seconds`，不重跑挑最好的一次。

- [ ] **Step 7：发布并测问答耗时**

在浏览器 `http://localhost:5174` 用 `demo_teacher` 登录，进入该课程，处理审核队列中阻断发布的项后发布，再在成员页添加 `demo_student`。然后：

```bash
printf '%s\n' "什么是栈？" "循环队列如何判断队满？" "栈和队列有什么区别？" "入栈操作的时间复杂度是多少？" "光合作用的原理是什么？" > .demo/logs/l02-questions.txt
.venv/bin/python evaluation/measure_web_flow.py ask --base-url http://127.0.0.1:8001 \
  --username demo_student --password-env MEASURE_PASSWORD \
  --course-id <COURSE_ID> --questions .demo/logs/l02-questions.txt | tee .demo/logs/l02-ask.jsonl
sqlite3 src/backend/storage/smartsketch.sqlite3 "
SELECT outcome, latency_ms, first_delta_latency_ms FROM chat_logs ORDER BY created_at DESC LIMIT 5;"
```

Expected: 前四题 `status` 为 `answered`，最后一题为 `not_covered`。超过 15 秒或返回错误的如实记录。

- [ ] **Step 8：写基线报告**

`evaluation/reports/l02-baseline-2026-10.md` 包含：日期、机器型号与网络、模型（请求名与响应名）、并发设置、资料文件名与字节数、块数、抽取总耗时、各 `purpose` 的调用次数与 token 与最大单次延迟、知识点数与关系类型数（从草稿图读取）、五道题的完整耗时与首字耗时、本次计费 token 与累计计费 token、与 60 秒 / 15 秒目标的差距。注明「Markdown 单格式；PDF 在 L11 补测」。

- [ ] **Step 9：停止服务、写交接、提交**

在 Step 5 的终端按 Ctrl-C。

```bash
git add evaluation/measure_web_flow.py tests/backend/test_l02_measure.py \
        evaluation/reports/l02-baseline-2026-10.md docs/handoffs/claude-l02.md docs/tasks.md
git commit -m "feat(eval): L02 网页链路耗时测量脚本与真实基线

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3（L03）：ADR、规则与契约

**Files:**
- Modify: `docs/decisions.md`（追加 ADR-080、ADR-081）
- Modify: `AGENTS.md`（§4、§6 两处）
- Modify: `docs/architecture.md`、`docs/integrations.md`、`.env.example`
- Modify: `src/contracts/api.v1.yaml`、`src/contracts/errors.v1.md`
- Regenerate: `src/contracts/v1/generated/`
- Modify: `src/backend/app/schemas/contracts.py`
- Modify: `tests/contracts/`（若有固定路径数或错误码清单的断言）
- Create: `docs/handoffs/claude-l03.md`

**Interfaces:**
- Produces（生成后的 Python 模型，经 `app.schemas.contracts` 导出）：`RuntimeMode`、`ModelConfig`、`ModelConfigUpdate`、`ModelConfigTestRequest`、`ModelConfigTestResult`、`ModelConfigLastTest`；`ErrorCode` 新增 `MODEL_CONFIG_REQUIRED`。前端同名类型在 `components['schemas']`。

- [ ] **Step 1：写 ADR-080 与 ADR-081**

在 `docs/decisions.md` 末尾追加，格式与 ADR-079 相同（背景、决定、后果、日期 2026-10-02）。

ADR-080「个人模型凭据与 `LLM_MODE=personal`」决定条目：
1. 新增运行模式 `personal`：无全站大模型客户端；教师任务用任务快照，学生问答用本人配置；未配置返回 `MODEL_CONFIG_REQUIRED`，不回退。
2. 每用户一份配置，AES-256-GCM 加密，关联数据为 `user_id`；根密钥 `MODEL_CREDENTIAL_KEY`（32 字节，URL 安全 base64）。
3. 任务快照在建任务的同一事务内复制密文；修改配置不影响已建任务；清除配置把本人未结束任务的快照置空，任务在下一个块或小节尝试开始前以 `LLM_UNAVAILABLE` + `details.reason = credential_revoked` 终止；任务进入 `awaiting_review`/`completed`/`failed`/`cancelled` 后快照密文置空。
4. 问答按「用户 + 配置版本」隔离调用策略与熔断；`model_calls.user_id` 记录归属；`personal` 模式下日预算按用户统计。
5. 出站地址：仅 `https`，解析后全部为公网地址，连接钉住已校验的 IP，不跟随重定向；`MODEL_ENDPOINT_ALLOW_PRIVATE` 仅测试用，生产拒绝启动。
6. 规则调整：`AGENTS.md` §4、§6 对个人模型凭据开例外。
7. 新增依赖 `cryptography`。
后果：改根密钥会使已存配置不可解；改地址必须重新提交密钥。

ADR-081「向量方案签收（D-02c）」：在线 `text-embedding-v4`、1024 维、每批 10 条，系统级、部署者付费；`EMBEDDING_MODE=local` 在配置校验阶段拒绝；切换向量空间须用新库或 V12 重新向量化。

- [ ] **Step 2：改上位规则与文档**

`AGENTS.md` §4 最后一条改为：

```markdown
- 基础设施与系统级配置只能从环境变量读取；在 `.env.example` 只保留变量名和无敏感示例值。用户个人模型凭据是唯一例外：经受控的个人配置接口写入，服务端加密存储，根密钥来自环境变量（ADR-080）。
```

`AGENTS.md` §6 第三条改为：

```markdown
- 外部服务、MCP 与环境变量只记录在 `docs/integrations.md` 和 `.env.example`；系统级密钥只存个人本地环境。用户个人模型凭据按 ADR-080 加密存库，不进日志、仓库和前端持久存储。
```

`docs/integrations.md`：模型模式表加 `personal` 一行；新增变量 `MODEL_CREDENTIAL_KEY`、`MODEL_ENDPOINT_ALLOW_PRIVATE` 两行；D-02c 行状态改「已签收（ADR-081）」；`EMBEDDING_MODE` 行删去 `local` 可用的表述。
`docs/architecture.md`「关键质量边界」加一条指向 ADR-080。
`.env.example`：`LLM_MODE` 注释加 `personal` 说明；在登录签名密钥段后加：

```bash
# 个人模型凭据根密钥（ADR-080）：LLM_MODE=personal 时必填，32 字节的 URL 安全 base64；缺失或长度不对即拒绝启动
# 本机生成：python3 -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
MODEL_CREDENTIAL_KEY=
# 仅测试：放行回环/内网模型地址，供本机假供应商端到端测试；APP_ENV=production 下设置为真即拒绝启动
MODEL_ENDPOINT_ALLOW_PRIVATE=
```

- [ ] **Step 3：改契约真源**

`src/contracts/api.v1.yaml`：

`tags` 末尾加：

```yaml
  - name: settings
    description: 当前用户的个人模型 API 配置（ADR-080）
```

`paths` 中在 `/api/v1/courses:` 之前加：

```yaml
  /api/v1/me/model-config:
    get:
      tags: [settings]
      summary: 读取当前用户的个人模型配置（脱敏）
      description: 永不返回密钥，只返回末 4 位 `key_hint`。`runtime_mode` 为服务端当前的大模型运行模式。
      operationId: getModelConfig
      responses:
        '200':
          description: 当前配置状态；未配置时 `configured = false` 且不带其余配置字段
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ModelConfig'
        '401':
          $ref: '#/components/responses/Unauthenticated'
    put:
      tags: [settings]
      summary: 保存或修改当前用户的个人模型配置
      description: |
        `base_url` 只接受 https，解析后的地址必须全部为公网地址。首次保存或 `base_url` 与已存值不同时必须带 `api_key`；
        只改 `model` 时可省略 `api_key` 以保留已存密钥。每次成功保存 `version` 加 1，并清空最近测试结果。
        修改不影响已创建的任务。
      operationId: saveModelConfig
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ModelConfigUpdate'
      responses:
        '200':
          description: 保存后的配置状态
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ModelConfig'
        '401':
          $ref: '#/components/responses/Unauthenticated'
        '422':
          description: |
            `VALIDATION_ERROR`。`details.fields[].reason` 除 schema 错误外另有：`scheme`、`credentials`、`query`、`host`、
            `unresolvable`、`private_address`（字段 `base_url`）；`required_when_endpoint_changes`、`invalid_characters`（字段 `api_key`）。
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
        '503':
          description: 服务端未配置凭据根密钥（`STORAGE_UNAVAILABLE`，`details.reason = credential_store_disabled`）
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
    delete:
      tags: [settings]
      summary: 清除当前用户的个人模型配置
      description: 同时作废本人未结束任务的密钥快照；这些任务随后以 `LLM_UNAVAILABLE`（`details.reason = credential_revoked`）终止。未配置时也返回 204。
      operationId: clearModelConfig
      responses:
        '204':
          description: 已清除
        '401':
          $ref: '#/components/responses/Unauthenticated'

  /api/v1/me/model-config/test:
    post:
      tags: [settings]
      summary: 测试个人模型配置的连通性
      description: |
        向 `base_url` 发 1 次输出上限为 1 token 的最小对话请求。请求体三项都省略时测试已存配置；否则三项都必填，
        测试这组值而不保存。每用户每分钟至多 5 次。只返回成败、错误分类与耗时，不回显供应商响应。
      operationId: testModelConfig
      requestBody:
        required: false
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ModelConfigTestRequest'
      responses:
        '200':
          description: 测试结果（失败也是 200，`ok = false`）
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ModelConfigTestResult'
        '401':
          $ref: '#/components/responses/Unauthenticated'
        '409':
          description: 未带请求体且尚未保存配置（`MODEL_CONFIG_REQUIRED`）
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
        '422':
          description: '`VALIDATION_ERROR`，原因同保存接口；或请求体只给了部分字段'
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
        '429':
          description: 测试过于频繁（`RATE_LIMITED`），带 `Retry-After`
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
```

`uploadDocument` 与 `chat` 两个操作的 `responses` 各加：

```yaml
        '409':
          description: '`LLM_MODE=personal` 下当前用户尚未配置个人模型 API（`MODEL_CONFIG_REQUIRED`）'
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
```

`ErrorCode.enum` 末尾加 `- MODEL_CONFIG_REQUIRED`。

`components.schemas` 加：

```yaml
    RuntimeMode:
      type: string
      description: 服务端大模型运行模式。`personal` 才使用个人配置；其余模式下个人配置不生效。
      enum: [personal, demo, fake, live]

    ModelConfigLastTest:
      type: object
      required: [ok, tested_at]
      additionalProperties: false
      properties:
        ok:
          type: boolean
        tested_at:
          type: string
          format: date-time
        error_class:
          $ref: '#/components/schemas/ModelConfigTestErrorClass'

    ModelConfigTestErrorClass:
      type: string
      enum: [auth, timeout, rate_limited, connection, invalid_request, server, malformed_response, stream_interrupted, blocked_address]

    ModelConfig:
      type: object
      required: [runtime_mode, configured]
      additionalProperties: false
      properties:
        runtime_mode:
          $ref: '#/components/schemas/RuntimeMode'
        configured:
          type: boolean
        base_url:
          type: string
        model:
          type: string
        key_hint:
          type: string
          description: 密钥末 4 位，仅供辨认
        version:
          type: integer
          minimum: 1
        updated_at:
          type: string
          format: date-time
        last_test:
          $ref: '#/components/schemas/ModelConfigLastTest'

    ModelConfigUpdate:
      type: object
      required: [base_url, model]
      additionalProperties: false
      properties:
        base_url:
          type: string
          minLength: 9
          maxLength: 512
        model:
          type: string
          minLength: 1
          maxLength: 128
        api_key:
          type: string
          format: password
          minLength: 1
          maxLength: 512

    ModelConfigTestRequest:
      type: object
      additionalProperties: false
      properties:
        base_url:
          type: string
          minLength: 9
          maxLength: 512
        model:
          type: string
          minLength: 1
          maxLength: 128
        api_key:
          type: string
          format: password
          minLength: 1
          maxLength: 512

    ModelConfigTestResult:
      type: object
      required: [ok, latency_ms]
      additionalProperties: false
      properties:
        ok:
          type: boolean
        latency_ms:
          type: integer
          minimum: 0
        error_class:
          $ref: '#/components/schemas/ModelConfigTestErrorClass'
```

`src/contracts/errors.v1.md`「外部依赖」表加一行：

```markdown
| `MODEL_CONFIG_REQUIRED` | 409 | `LLM_MODE=personal` 下当前用户未配置个人模型 API 即上传资料、提问或测试已存配置（ADR-080） | 显示「先配置模型 API」并链接到设置页；不重试 |
```

并在 `LLM_UNAVAILABLE` 行的触发条件后补一句：「`personal` 模式下 `details.reason` 另有 `credential_revoked`、`credential_missing`、`credential_unreadable`（任务）与 `auth`（供应商拒绝密钥）；前端提示检查个人配置」。

- [ ] **Step 4：生成并跑契约门禁**

```bash
./scripts/gen-contracts.sh
scripts/verify/contracts.sh
```

Expected: 生成物更新，契约门禁 PASS。若 `tests/contracts/` 中有固定错误码数量或路径清单的断言失败，按新契约更新那一处断言并在交接中写明。

- [ ] **Step 5：在后端导出新模型**

`src/backend/app/schemas/contracts.py` 末尾追加：

```python
# L03 个人模型配置（ADR-080）。
RuntimeMode = _module.RuntimeMode
ModelConfig = _module.ModelConfig
ModelConfigLastTest = _module.ModelConfigLastTest
ModelConfigUpdate = _module.ModelConfigUpdate
ModelConfigTestRequest = _module.ModelConfigTestRequest
ModelConfigTestResult = _module.ModelConfigTestResult
```

Run: `PYTHONPATH=src/backend .venv/bin/python -c "from app.schemas.contracts import ModelConfig, ModelConfigUpdate; print(ModelConfigUpdate.model_fields.keys())"`
Expected: 输出含 `base_url`、`model`、`api_key`。

- [ ] **Step 6：门禁、交接、提交**

```bash
./scripts/verify.sh
git add AGENTS.md docs/decisions.md docs/architecture.md docs/integrations.md .env.example \
        src/contracts src/backend/app/schemas/contracts.py tests/contracts docs/tasks.md docs/handoffs/claude-l03.md
git commit -m "docs(contracts): L03 ADR-080/081、个人模型配置契约与规则调整

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4（L04）：迁移 015、加密服务、仓储

**Files:**
- Create: `src/backend/migrations/015_user_model_configs.sql`
- Create: `src/backend/app/services/credentials.py`
- Create: `src/backend/app/repositories/model_configs.py`
- Modify: `src/backend/app/config.py`
- Modify: `src/backend/pyproject.toml`
- Test: `tests/backend/test_l04.py`

**Interfaces:**
- Produces:
  - `app.repositories.model_configs.SealedKey(ciphertext: bytes, nonce: bytes)`（`app.services.credentials` 再导出）。
  - `app.services.credentials`：`CredentialCipher(root_key: bytes)`，`.seal(user_id: str, api_key: str) -> SealedKey`，`.open(user_id: str, sealed: SealedKey) -> str`，`CredentialCipher.from_settings(settings) -> CredentialCipher`；异常 `CredentialError`、`ModelConfigRequired`、`CredentialUnavailable(reason: str)`。
  - `app.repositories.model_configs`：`ModelConfigRow`、`TaskBindingRow`、`KeyRequired`；`get_config(sqlite_url, user_id) -> ModelConfigRow | None`；`save_config(sqlite_url, *, user_id, base_url, model, sealed: SealedKey | None, key_hint: str | None) -> ModelConfigRow`；`delete_config(sqlite_url, user_id) -> bool`；`record_test(sqlite_url, user_id, *, ok: bool, error_class: str | None) -> None`；`bind_task(database, *, task_id, user_id) -> bool`；`get_binding(sqlite_url, task_id) -> TaskBindingRow | None`；`binding_active(sqlite_url, task_id) -> bool`；`scrub_terminal_bindings(sqlite_url) -> int`。
  - `Settings.LLM_MODE` 接受 `"personal"`；`Settings.MODEL_CREDENTIAL_KEY: SecretStr`；`Settings.MODEL_ENDPOINT_ALLOW_PRIVATE: bool`。

- [ ] **Step 1：安装并锁定 `cryptography`**

```bash
.venv/bin/pip install cryptography
.venv/bin/pip show cryptography | grep '^Version'
```

把输出的版本号写入 `src/backend/pyproject.toml` 的 `dependencies`，位置在 `argon2-cffi` 之后：`"cryptography==<上一步输出的版本号>",`。然后 `.venv/bin/pip install -e 'src/backend[test]'` 确认可解析。

- [ ] **Step 2：写失败测试**

```python
# tests/backend/test_l04.py
"""L04：迁移 015、凭据加密、用户配置与任务快照仓储（ADR-080）。"""
from __future__ import annotations

import base64
import sqlite3
import uuid
from types import SimpleNamespace

import pytest

from app.config import SettingsError, load_settings
from app.repositories import model_configs as repo
from app.repositories.accounts import insert_account
from app.repositories.courses import create_course
from app.repositories.sqlite import connect, migrate
from app.repositories.tasks import create_material_task
from app.services.credentials import CredentialCipher, CredentialError, SealedKey

VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
ROOT_KEY = bytes(range(32))
ROOT_KEY_B64 = base64.urlsafe_b64encode(ROOT_KEY).decode()
SECRET = "sk-test-0123456789abcd"


@pytest.fixture
def url(tmp_path):
    value = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(value)
    return value


def _user(url, name, role="teacher"):
    return insert_account(url, account_id=uuid.uuid4().hex, username=name, password_hash=VALID_HASH, role=role)


def _task(url, course_id):
    stored = SimpleNamespace(original_filename="a.md", format="markdown", size_bytes=10,
                             content_hash="sha256:" + "0" * 64, storage_name=uuid.uuid4().hex)
    return create_material_task(url, course_id=course_id, stored_file=stored, idempotency_key=uuid.uuid4().hex).task


def test_cipher_round_trip_and_binding_to_user():
    cipher = CredentialCipher(ROOT_KEY)
    sealed = cipher.seal("user-a", SECRET)
    assert SECRET.encode() not in sealed.ciphertext
    assert cipher.open("user-a", sealed) == SECRET
    with pytest.raises(CredentialError):
        cipher.open("user-b", sealed)
    with pytest.raises(CredentialError):
        cipher.open("user-a", SealedKey(sealed.ciphertext[:-1] + b"\x00", sealed.nonce))
    assert SECRET not in repr(sealed)


def test_cipher_uses_fresh_nonce():
    cipher = CredentialCipher(ROOT_KEY)
    assert cipher.seal("u", SECRET).nonce != cipher.seal("u", SECRET).nonce


def test_settings_personal_mode_requires_valid_root_key():
    base = {"LLM_MODE": "personal"}
    with pytest.raises(SettingsError, match="MODEL_CREDENTIAL_KEY"):
        load_settings(base)
    with pytest.raises(SettingsError, match="MODEL_CREDENTIAL_KEY"):
        load_settings({**base, "MODEL_CREDENTIAL_KEY": "too-short"})
    settings = load_settings({**base, "MODEL_CREDENTIAL_KEY": ROOT_KEY_B64})
    assert settings.LLM_MODE == "personal"
    assert CredentialCipher.from_settings(settings).open("u", CredentialCipher(ROOT_KEY).seal("u", SECRET)) == SECRET


def test_settings_private_endpoints_refused_in_production():
    env = {"APP_ENV": "production", "LLM_MODE": "personal", "MODEL_CREDENTIAL_KEY": ROOT_KEY_B64,
           "EMBEDDING_MODE": "online", "EMBEDDING_BASE_URL": "https://e.example", "EMBEDDING_API_KEY": "k",
           "EMBEDDING_MODEL": "m", "MODEL_ENDPOINT_ALLOW_PRIVATE": "1"}
    with pytest.raises(SettingsError, match="MODEL_ENDPOINT_ALLOW_PRIVATE"):
        load_settings(env)
    env["MODEL_ENDPOINT_ALLOW_PRIVATE"] = ""
    assert load_settings(env).APP_ENV == "production"


def test_save_then_update_and_key_rules(url):
    user = _user(url, "teacher1")
    cipher = CredentialCipher(ROOT_KEY)
    with pytest.raises(repo.KeyRequired):
        repo.save_config(url, user_id=user.id, base_url="https://a.example/v1", model="m1", sealed=None, key_hint=None)
    first = repo.save_config(url, user_id=user.id, base_url="https://a.example/v1", model="m1",
                             sealed=cipher.seal(user.id, SECRET), key_hint="abcd")
    assert (first.version, first.key_hint, first.model) == (1, "abcd", "m1")
    kept = repo.save_config(url, user_id=user.id, base_url="https://a.example/v1", model="m2", sealed=None, key_hint=None)
    assert (kept.version, kept.model, kept.key_hint) == (2, "m2", "abcd")
    assert cipher.open(user.id, kept.sealed) == SECRET
    with pytest.raises(repo.KeyRequired):
        repo.save_config(url, user_id=user.id, base_url="https://b.example/v1", model="m2", sealed=None, key_hint=None)
    assert repo.get_config(url, user.id).base_url == "https://a.example/v1"


def test_record_test_and_save_clears_it(url):
    user = _user(url, "teacher1")
    cipher = CredentialCipher(ROOT_KEY)
    repo.save_config(url, user_id=user.id, base_url="https://a.example/v1", model="m1",
                     sealed=cipher.seal(user.id, SECRET), key_hint="abcd")
    repo.record_test(url, user.id, ok=False, error_class="auth")
    row = repo.get_config(url, user.id)
    assert (row.last_test_ok, row.last_test_error_class) == (False, "auth") and row.last_test_at
    saved = repo.save_config(url, user_id=user.id, base_url="https://a.example/v1", model="m3", sealed=None, key_hint=None)
    assert saved.last_test_at is None


def test_binding_is_an_immutable_snapshot(url):
    user = _user(url, "teacher1")
    course = create_course(url, name="课", description=None, creator_id=user.id)
    cipher = CredentialCipher(ROOT_KEY)
    repo.save_config(url, user_id=user.id, base_url="https://a.example/v1", model="m1",
                     sealed=cipher.seal(user.id, SECRET), key_hint="abcd")
    task = _task(url, course.id)
    with connect(url) as database:
        assert repo.bind_task(database, task_id=task.id, user_id=user.id) is True
    repo.save_config(url, user_id=user.id, base_url="https://b.example/v1", model="m9",
                     sealed=cipher.seal(user.id, "sk-other-key-000000"), key_hint="0000")
    binding = repo.get_binding(url, task.id)
    assert (binding.base_url, binding.model, binding.config_version) == ("https://a.example/v1", "m1", 1)
    assert cipher.open(binding.user_id, binding.sealed) == SECRET
    assert repo.binding_active(url, task.id) is True


def test_bind_without_config_returns_false(url):
    user = _user(url, "teacher1")
    course = create_course(url, name="课", description=None, creator_id=user.id)
    task = _task(url, course.id)
    with connect(url) as database:
        assert repo.bind_task(database, task_id=task.id, user_id=user.id) is False
    assert repo.get_binding(url, task.id) is None
    assert repo.binding_active(url, task.id) is False


def test_delete_revokes_only_own_open_bindings(url):
    alice, bob = _user(url, "alice01"), _user(url, "bob0001")
    course = create_course(url, name="课", description=None, creator_id=alice.id)
    cipher = CredentialCipher(ROOT_KEY)
    for user in (alice, bob):
        repo.save_config(url, user_id=user.id, base_url="https://a.example/v1", model="m1",
                         sealed=cipher.seal(user.id, SECRET), key_hint="abcd")
    task_a, task_b = _task(url, course.id), _task(url, course.id)
    with connect(url) as database:
        repo.bind_task(database, task_id=task_a.id, user_id=alice.id)
        repo.bind_task(database, task_id=task_b.id, user_id=bob.id)
    assert repo.delete_config(url, alice.id) is True
    assert repo.get_config(url, alice.id) is None
    revoked = repo.get_binding(url, task_a.id)
    assert revoked.sealed is None and revoked.scrub_reason == "revoked"
    assert repo.binding_active(url, task_b.id) is True
    assert repo.delete_config(url, alice.id) is False


def test_scrub_terminal_bindings(url):
    user = _user(url, "teacher1")
    course = create_course(url, name="课", description=None, creator_id=user.id)
    cipher = CredentialCipher(ROOT_KEY)
    repo.save_config(url, user_id=user.id, base_url="https://a.example/v1", model="m1",
                     sealed=cipher.seal(user.id, SECRET), key_hint="abcd")
    done, running = _task(url, course.id), _task(url, course.id)
    with connect(url) as database:
        repo.bind_task(database, task_id=done.id, user_id=user.id)
        repo.bind_task(database, task_id=running.id, user_id=user.id)
        database.execute("UPDATE processing_tasks SET stage = 'awaiting_review', progress = 1 WHERE id = ?", (done.id,))
    assert repo.scrub_terminal_bindings(url) == 1
    scrubbed = repo.get_binding(url, done.id)
    assert scrubbed.sealed is None and scrubbed.scrub_reason == "terminal"
    assert repo.binding_active(url, running.id) is True
    assert repo.scrub_terminal_bindings(url) == 0


def test_ciphertext_never_contains_plain_key(url):
    user = _user(url, "teacher1")
    repo.save_config(url, user_id=user.id, base_url="https://a.example/v1", model="m1",
                     sealed=CredentialCipher(ROOT_KEY).seal(user.id, SECRET), key_hint="abcd")
    with connect(url) as database:
        dump = "\n".join(database.iterdump())
    assert SECRET not in dump
```

- [ ] **Step 3：运行确认失败**

Run: `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_l04.py -q -p no:cacheprovider`
Expected: 收集错误（`app.repositories.model_configs` 不存在）。

- [ ] **Step 4：写迁移**

```sql
-- L04: per-user model credentials and per-task immutable snapshots (ADR-080).
-- Rollback: stop API/worker and restore backups/*-before-015.sqlite. Manual rollback drops
-- every saved credential and needs SQLite >= 3.35 for DROP COLUMN.
-- ROLLBACK: DROP TABLE task_model_bindings;
-- ROLLBACK: DROP TABLE user_model_configs;
-- ROLLBACK: DROP INDEX idx_model_calls_user_created;
-- ROLLBACK: ALTER TABLE model_calls DROP COLUMN user_id;
-- ROLLBACK: ALTER TABLE processing_tasks DROP COLUMN created_by;
-- ROLLBACK: DELETE FROM schema_migrations WHERE filename LIKE '%_user_model_configs.sql';
CREATE TABLE user_model_configs (
    user_id TEXT PRIMARY KEY NOT NULL REFERENCES users(id),
    base_url TEXT NOT NULL CHECK (length(base_url) BETWEEN 9 AND 512),
    model TEXT NOT NULL CHECK (length(trim(model)) BETWEEN 1 AND 128),
    key_ciphertext BLOB NOT NULL,
    key_nonce BLOB NOT NULL CHECK (length(key_nonce) = 12),
    key_hint TEXT NOT NULL CHECK (length(key_hint) BETWEEN 1 AND 4),
    version INTEGER NOT NULL CHECK (version >= 1),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_test_at TEXT,
    last_test_ok INTEGER CHECK (last_test_ok IN (0, 1)),
    last_test_error_class TEXT
);

-- The key columns are a copy of the owner's ciphertext at task creation; they are nulled
-- (never rewritten) when the task ends or the owner clears the configuration.
CREATE TABLE task_model_bindings (
    task_id TEXT PRIMARY KEY NOT NULL REFERENCES processing_tasks(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id),
    config_version INTEGER NOT NULL CHECK (config_version >= 1),
    base_url TEXT NOT NULL,
    model TEXT NOT NULL,
    key_ciphertext BLOB,
    key_nonce BLOB,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    scrubbed_at TEXT,
    scrub_reason TEXT CHECK (scrub_reason IN ('terminal', 'revoked')),
    CHECK ((key_ciphertext IS NULL) = (key_nonce IS NULL)),
    CHECK ((key_ciphertext IS NULL) = (scrubbed_at IS NOT NULL)),
    CHECK ((scrubbed_at IS NULL) = (scrub_reason IS NULL))
);
CREATE INDEX idx_task_model_bindings_user ON task_model_bindings(user_id);

ALTER TABLE processing_tasks ADD COLUMN created_by TEXT REFERENCES users(id);
ALTER TABLE model_calls ADD COLUMN user_id TEXT;
CREATE INDEX idx_model_calls_user_created ON model_calls(user_id, created_at);
```

- [ ] **Step 5：写加密服务**

```python
# src/backend/app/services/credentials.py
"""AES-256-GCM sealing of user-supplied model API keys (ADR-080).

The associated data is the owner's ``user_id``: a ciphertext copied into another user's row
fails authentication. Nothing here logs; no repr or error carries key material.
"""

from __future__ import annotations

import base64
import binascii
import os
from collections.abc import Callable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import Settings
from app.repositories.model_configs import SealedKey

__all__ = ["CredentialCipher", "CredentialError", "CredentialUnavailable", "ModelConfigRequired", "SealedKey",
           "decode_root_key"]

KEY_BYTES = 32
NONCE_BYTES = 12


class CredentialError(Exception):
    """The root key is missing, or a sealed key cannot be authenticated."""


class ModelConfigRequired(Exception):
    """``LLM_MODE=personal`` and the current user has no saved model configuration."""


class CredentialUnavailable(Exception):
    """A task's key snapshot cannot be used; ``reason`` is a contract ``details.reason`` value."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def decode_root_key(raw: str) -> bytes:
    """Decode URL-safe base64 (padding optional) to exactly 32 bytes; ``ValueError`` otherwise."""
    text = raw.strip()
    try:
        key = base64.b64decode(text + "=" * (-len(text) % 4), altchars=b"-_", validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("root key is not URL-safe base64") from None
    if len(key) != KEY_BYTES:
        raise ValueError("root key must be 32 bytes")
    return key


class CredentialCipher:
    def __init__(self, root_key: bytes, *, random: Callable[[int], bytes] = os.urandom) -> None:
        if not isinstance(root_key, bytes) or len(root_key) != KEY_BYTES:
            raise CredentialError("root key must be 32 bytes")
        self._aead = AESGCM(root_key)
        self._random = random

    def __repr__(self) -> str:
        return "CredentialCipher()"

    @classmethod
    def from_settings(cls, settings: Settings) -> CredentialCipher:
        raw = settings.MODEL_CREDENTIAL_KEY.get_secret_value()
        if not raw.strip():
            raise CredentialError("MODEL_CREDENTIAL_KEY is not configured")
        try:
            return cls(decode_root_key(raw))
        except ValueError:
            raise CredentialError("MODEL_CREDENTIAL_KEY is invalid") from None

    def seal(self, user_id: str, api_key: str) -> SealedKey:
        nonce = self._random(NONCE_BYTES)
        return SealedKey(self._aead.encrypt(nonce, api_key.encode("utf-8"), user_id.encode("utf-8")), nonce)

    def open(self, user_id: str, sealed: SealedKey) -> str:
        try:
            return self._aead.decrypt(sealed.nonce, sealed.ciphertext, user_id.encode("utf-8")).decode("utf-8")
        except (InvalidTag, ValueError):
            raise CredentialError("sealed key cannot be opened") from None
```

- [ ] **Step 6：改设置**

`src/backend/app/config.py`：

1. `LLM_MODE` 改为 `Literal["fake", "demo", "live", "personal"] = "fake"`，其上方注释追加一行：`# personal（ADR-080）：无全站大模型客户端，任务用快照、问答用本人配置；LLM_* 的地址、key、模型名不读取`。
2. 在 `AUTH_ACCESS_TOKEN_TTL_SECONDS` 之后加：

```python
    # 个人模型凭据（ADR-080）：根密钥为 32 字节的 URL 安全 base64；personal 模式必填。
    MODEL_CREDENTIAL_KEY: SecretStr = SecretStr("")
    # 仅测试：放行回环/内网模型地址（本机假供应商）；production 下为真即拒绝启动。
    MODEL_ENDPOINT_ALLOW_PRIVATE: bool = False
```

3. 在 `_check_rules` 之前加：

```python
def _valid_credential_key(value: SecretStr) -> bool:
    text = value.get_secret_value().strip()
    try:
        return len(base64.b64decode(text + "=" * (-len(text) % 4), altchars=b"-_", validate=True)) == 32
    except (binascii.Error, ValueError):
        return False
```

文件头加 `import base64` 与 `import binascii`。

4. 在 `_check_rules` 的 `if settings.APP_ENV == "production":` 之前加：

```python
    if _has_value(settings.MODEL_CREDENTIAL_KEY) or settings.LLM_MODE == "personal":
        if not _valid_credential_key(settings.MODEL_CREDENTIAL_KEY):
            invalid.add("MODEL_CREDENTIAL_KEY")
```

并在 `production` 分支内加：

```python
        if settings.MODEL_ENDPOINT_ALLOW_PRIVATE:
            invalid.add("MODEL_ENDPOINT_ALLOW_PRIVATE")
```

5. `load_settings` 中在 `RECOMMEND_WEIGHT_NAMES` 的空串处理之后加同样的空串处理，让 `.env` 里留空的布尔变量等同未设置：

```python
    if "MODEL_ENDPOINT_ALLOW_PRIVATE" in source and not source["MODEL_ENDPOINT_ALLOW_PRIVATE"].strip():
        del source["MODEL_ENDPOINT_ALLOW_PRIVATE"]
```

6. `.env.example` 在 `AUTH_ACCESS_TOKEN_TTL_SECONDS=28800` 之后加入 `MODEL_CREDENTIAL_KEY=` 与 `MODEL_ENDPOINT_ALLOW_PRIVATE=` 两行及其注释（L03 执行时发现 `tests/backend/test_b06.py::test_env_example_covers_every_setting` 要求 `.env.example` 与 `Settings` 字段一一对应，所以这两行随设置字段在本任务加入，而不是 L03）。

- [ ] **Step 7：写仓储**

```python
# src/backend/app/repositories/model_configs.py
"""Persistence for per-user model configurations and per-task key snapshots (ADR-080).

Rows hold ciphertext only; this module never sees a plaintext key.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from app.repositories.sqlite import connect

_NOW = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
_TERMINAL = "('awaiting_review', 'completed', 'failed', 'cancelled')"
_CONFIG_COLUMNS = ("user_id, base_url, model, key_ciphertext, key_nonce, key_hint, version, updated_at, "
                   "last_test_at, last_test_ok, last_test_error_class")


class KeyRequired(Exception):
    """No stored key can be kept: there is no configuration yet, or ``base_url`` changed."""


@dataclass(frozen=True)
class SealedKey:
    """AES-GCM ciphertext and nonce of one API key; sealed and opened only by the service layer."""

    ciphertext: bytes = field(repr=False)
    nonce: bytes = field(repr=False)


@dataclass(frozen=True)
class ModelConfigRow:
    user_id: str
    base_url: str
    model: str
    sealed: SealedKey
    key_hint: str
    version: int
    updated_at: str
    last_test_at: str | None
    last_test_ok: bool | None
    last_test_error_class: str | None


@dataclass(frozen=True)
class TaskBindingRow:
    task_id: str
    user_id: str
    config_version: int
    base_url: str
    model: str
    sealed: SealedKey | None
    scrub_reason: str | None


def _config(row: tuple | None) -> ModelConfigRow | None:
    if row is None:
        return None
    return ModelConfigRow(
        user_id=row[0], base_url=row[1], model=row[2], sealed=SealedKey(bytes(row[3]), bytes(row[4])),
        key_hint=row[5], version=row[6], updated_at=row[7], last_test_at=row[8],
        last_test_ok=None if row[9] is None else bool(row[9]), last_test_error_class=row[10],
    )


def _read(database: sqlite3.Connection, user_id: str) -> ModelConfigRow | None:
    return _config(database.execute(
        f"SELECT {_CONFIG_COLUMNS} FROM user_model_configs WHERE user_id = ?", (user_id,)
    ).fetchone())


def get_config(sqlite_url: str, user_id: str) -> ModelConfigRow | None:
    with connect(sqlite_url) as database:
        return _read(database, user_id)


def save_config(sqlite_url: str, *, user_id: str, base_url: str, model: str,
                sealed: SealedKey | None, key_hint: str | None) -> ModelConfigRow:
    """Insert or update; ``sealed=None`` keeps the stored key and requires an unchanged ``base_url``."""
    with connect(sqlite_url) as database:
        database.execute("BEGIN IMMEDIATE")
        try:
            current = _read(database, user_id)
            if sealed is None:
                if current is None or current.base_url != base_url:
                    raise KeyRequired()
                database.execute(
                    f"UPDATE user_model_configs SET model = ?, version = version + 1, updated_at = {_NOW},"
                    " last_test_at = NULL, last_test_ok = NULL, last_test_error_class = NULL WHERE user_id = ?",
                    (model, user_id),
                )
            else:
                if not key_hint:
                    raise ValueError("key_hint is required with a new key")
                database.execute(
                    "INSERT INTO user_model_configs"
                    " (user_id, base_url, model, key_ciphertext, key_nonce, key_hint, version)"
                    " VALUES (?, ?, ?, ?, ?, ?, 1)"
                    " ON CONFLICT(user_id) DO UPDATE SET base_url = excluded.base_url, model = excluded.model,"
                    " key_ciphertext = excluded.key_ciphertext, key_nonce = excluded.key_nonce,"
                    f" key_hint = excluded.key_hint, version = user_model_configs.version + 1, updated_at = {_NOW},"
                    " last_test_at = NULL, last_test_ok = NULL, last_test_error_class = NULL",
                    (user_id, base_url, model, sealed.ciphertext, sealed.nonce, key_hint),
                )
            row = _read(database, user_id)
            database.execute("COMMIT")
        except BaseException:
            if database.in_transaction:
                database.execute("ROLLBACK")
            raise
    if row is None:
        raise RuntimeError("model configuration save did not return a row")
    return row


def delete_config(sqlite_url: str, user_id: str) -> bool:
    """Delete the configuration and revoke the owner's open task snapshots in one transaction."""
    with connect(sqlite_url) as database:
        database.execute("BEGIN IMMEDIATE")
        try:
            deleted = database.execute("DELETE FROM user_model_configs WHERE user_id = ?", (user_id,)).rowcount
            database.execute(
                f"UPDATE task_model_bindings SET key_ciphertext = NULL, key_nonce = NULL, scrubbed_at = {_NOW},"
                " scrub_reason = 'revoked' WHERE user_id = ? AND key_ciphertext IS NOT NULL",
                (user_id,),
            )
            database.execute("COMMIT")
        except BaseException:
            if database.in_transaction:
                database.execute("ROLLBACK")
            raise
    return deleted == 1


def record_test(sqlite_url: str, user_id: str, *, ok: bool, error_class: str | None) -> None:
    with connect(sqlite_url) as database:
        database.execute(
            f"UPDATE user_model_configs SET last_test_at = {_NOW}, last_test_ok = ?, last_test_error_class = ?"
            " WHERE user_id = ?",
            (1 if ok else 0, error_class, user_id),
        )


def bind_task(database: sqlite3.Connection, *, task_id: str, user_id: str) -> bool:
    """Copy the owner's current configuration into the task snapshot on the caller's transaction."""
    return database.execute(
        "INSERT INTO task_model_bindings (task_id, user_id, config_version, base_url, model, key_ciphertext, key_nonce)"
        " SELECT ?, user_id, version, base_url, model, key_ciphertext, key_nonce"
        " FROM user_model_configs WHERE user_id = ?",
        (task_id, user_id),
    ).rowcount == 1


def get_binding(sqlite_url: str, task_id: str) -> TaskBindingRow | None:
    with connect(sqlite_url) as database:
        row = database.execute(
            "SELECT task_id, user_id, config_version, base_url, model, key_ciphertext, key_nonce, scrub_reason"
            " FROM task_model_bindings WHERE task_id = ?", (task_id,)
        ).fetchone()
    if row is None:
        return None
    sealed = None if row[5] is None else SealedKey(bytes(row[5]), bytes(row[6]))
    return TaskBindingRow(row[0], row[1], row[2], row[3], row[4], sealed, row[7])


def binding_active(sqlite_url: str, task_id: str) -> bool:
    with connect(sqlite_url) as database:
        return database.execute(
            "SELECT 1 FROM task_model_bindings WHERE task_id = ? AND key_ciphertext IS NOT NULL", (task_id,)
        ).fetchone() is not None


def scrub_terminal_bindings(sqlite_url: str) -> int:
    """Null the key snapshot of every task that no longer needs a model call."""
    with connect(sqlite_url) as database:
        return database.execute(
            f"UPDATE task_model_bindings SET key_ciphertext = NULL, key_nonce = NULL, scrubbed_at = {_NOW},"
            " scrub_reason = 'terminal' WHERE key_ciphertext IS NOT NULL"
            f" AND task_id IN (SELECT id FROM processing_tasks WHERE stage IN {_TERMINAL})"
        ).rowcount
```

`SealedKey` 定义在仓储模块，服务层 `credentials.py` 导入并再导出，保持 `services → repositories` 单向依赖。因此 Step 7（仓储）要先于 Step 5（加密服务）落盘；两步都写完再跑测试。

- [ ] **Step 8：运行确认通过，并跑受影响的既有测试**

```bash
PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_l04.py tests/backend/test_b06.py tests/backend/test_c01.py tests/backend/test_j10.py -q -p no:cacheprovider
grep -rn '"014"' tests | head
```

Expected: 全部通过。已知需要更新的既有断言：`tests/backend/test_j10.py:28` 的 `migrate(url)[-1] == "014"` 改为 `"015"`；`grep` 找到的其他「最新迁移为 014」断言同样改为 015，并在交接中逐条列出。`test_scrub_terminal_bindings` 里直接 `UPDATE processing_tasks SET stage = 'awaiting_review'` 若被表约束或触发器拒绝，改用把该行其余必填列一并写入的同一条 `UPDATE`（读 `migrations/003`–`014` 中 `processing_tasks` 的 CHECK 确定），不改迁移。

- [ ] **Step 9：门禁、交接、提交**

```bash
./scripts/verify.sh
git add src/backend/migrations/015_user_model_configs.sql src/backend/app/services/credentials.py \
        src/backend/app/repositories/model_configs.py src/backend/app/config.py src/backend/pyproject.toml \
        tests/backend/test_l04.py tests/backend docs/tasks.md docs/handoffs/claude-l04.md
git commit -m "feat(backend): L04 个人模型凭据的迁移、加密与仓储

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

交接的 `rollback` 写：停 API 与 worker，恢复 `src/backend/storage/backups/*-before-015.sqlite`，回退本提交。

---

### Task 5（L05）：出站地址校验与钉 IP 传输

**Files:**
- Create: `src/backend/app/services/ai/outbound.py`
- Test: `tests/backend/test_l05.py`

**Interfaces:**
- Consumes: `app.services.ai.compatible.HttpTransport`、`HttpResponse`、`_StdlibResponse`。
- Produces: `EndpointBlocked(OSError)`（`.reason` ∈ `scheme`、`host`、`credentials`、`query`、`port`、`unresolvable`、`private_address`）；`is_public_address(value: str) -> bool`；`check_endpoint_url(url: str, *, allow_private: bool = False) -> SplitResult`；`check_endpoint(url: str, *, allow_private: bool = False, resolver: Resolver = system_resolver) -> None`；`GuardedTransport(*, allow_private: bool = False, resolver: Resolver = system_resolver, ssl_context: ssl.SSLContext | None = None)`，实现 `HttpTransport.open`；`build_transport(settings) -> GuardedTransport`。`Resolver = Callable[[str, int], list[str]]`。

- [ ] **Step 1：写失败测试**

```python
# tests/backend/test_l05.py
"""L05：用户填写的模型地址——语法、公网判定、解析后校验与钉 IP（ADR-080 决定 5）。"""
from __future__ import annotations

import http.server
import json
import threading

import pytest

from app.services.ai.client import Message, ModelMalformedResponseError, ModelRequest
from app.services.ai.compatible import CompatibleModelClient
from app.services.ai.outbound import (
    EndpointBlocked,
    GuardedTransport,
    check_endpoint,
    check_endpoint_url,
    is_public_address,
)


@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.0.0.5", "172.16.3.4", "192.168.1.1", "169.254.169.254", "100.64.0.1", "0.0.0.0",
    "224.0.0.1", "::1", "fe80::1", "fc00::1", "::ffff:127.0.0.1", "::ffff:10.0.0.1", "not-an-ip",
])
def test_non_public_addresses(address):
    assert is_public_address(address) is False


@pytest.mark.parametrize("address", ["1.1.1.1", "8.8.8.8", "2606:4700:4700::1111"])
def test_public_addresses(address):
    assert is_public_address(address) is True


@pytest.mark.parametrize("url, reason", [
    ("http://api.example.com/v1", "scheme"),
    ("ftp://api.example.com/v1", "scheme"),
    ("https://user:pw@api.example.com/v1", "credentials"),
    ("https://api.example.com/v1?x=1", "query"),
    ("https://api.example.com/v1#frag", "query"),
    ("https:///v1", "host"),
    ("https://api.example.com:0/v1", "port"),
    ("https://api.exam ple.com/v1", "host"),
])
def test_url_syntax_rejections(url, reason):
    with pytest.raises(EndpointBlocked) as caught:
        check_endpoint_url(url)
    assert caught.value.reason == reason


def test_http_only_with_allow_private():
    assert check_endpoint_url("http://127.0.0.1:9000/v1", allow_private=True).scheme == "http"


def test_resolution_rules():
    def to(addresses):
        return lambda host, port: addresses

    check_endpoint("https://api.example.com/v1", resolver=to(["1.1.1.1"]))
    with pytest.raises(EndpointBlocked) as caught:
        check_endpoint("https://api.example.com/v1", resolver=to(["1.1.1.1", "10.0.0.1"]))
    assert caught.value.reason == "private_address"
    with pytest.raises(EndpointBlocked) as caught:
        check_endpoint("https://api.example.com/v1", resolver=to([]))
    assert caught.value.reason == "unresolvable"

    def failing(host, port):
        raise OSError("no such host")

    with pytest.raises(EndpointBlocked) as caught:
        check_endpoint("https://api.example.com/v1", resolver=failing)
    assert caught.value.reason == "unresolvable"
    check_endpoint("https://internal.test/v1", allow_private=True, resolver=to(["127.0.0.1"]))


class _Provider(http.server.BaseHTTPRequestHandler):
    hosts: list[str] = []
    status = 200

    def do_POST(self):  # noqa: N802
        type(self).hosts.append(self.headers.get("Host", ""))
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if type(self).status != 200:
            self.send_response(type(self).status)
            self.send_header("Location", "http://127.0.0.1:1/elsewhere")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = json.dumps({"model": "m", "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                           "usage": {"prompt_tokens": 1, "completion_tokens": 1}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def provider():
    _Provider.hosts, _Provider.status = [], 200
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
    thread.join()


def _request():
    return ModelRequest(purpose="config_test", model="m", messages=(Message("user", "ping"),), max_output_tokens=1)


def test_transport_connects_to_the_checked_address_only(provider):
    calls = []

    def resolver(host, port):
        calls.append(host)
        return ["127.0.0.1"]

    transport = GuardedTransport(allow_private=True, resolver=resolver)
    client = CompatibleModelClient(f"http://model.test:{provider}/v1", "sk-test", transport=transport)
    assert client.complete(_request()).text == "ok"
    # "model.test" does not resolve on this machine: reaching the server proves the checked IP was used.
    assert _Provider.hosts == [f"model.test:{provider}"]
    assert calls == ["model.test"]


def test_transport_blocks_private_address_without_connecting(provider):
    transport = GuardedTransport(resolver=lambda host, port: ["127.0.0.1"])
    with pytest.raises(EndpointBlocked) as caught:
        transport.open(f"https://model.test:{provider}/v1/chat/completions", b"{}", {}, 2)
    assert caught.value.reason == "private_address"
    assert _Provider.hosts == []


def test_redirect_is_not_followed(provider):
    _Provider.status = 302
    transport = GuardedTransport(allow_private=True, resolver=lambda host, port: ["127.0.0.1"])
    client = CompatibleModelClient(f"http://model.test:{provider}/v1", "sk-test", transport=transport)
    with pytest.raises(ModelMalformedResponseError):
        client.complete(_request())
    assert len(_Provider.hosts) == 1
```

- [ ] **Step 2：运行确认失败**

Run: `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_l05.py -q -p no:cacheprovider`
Expected: 收集错误（`app.services.ai.outbound` 不存在）。

- [ ] **Step 3：写实现**

```python
# src/backend/app/services/ai/outbound.py
"""Outbound guard for user-supplied model endpoints (ADR-080 决定 5).

A user controls ``base_url``, so every connection is made only after the host has been
resolved and every resolved address is public; the socket then connects to that checked
address (TLS still verifies the original host name), so a DNS answer that changes between
check and connect has no effect. Redirects are never followed (``compatible.py`` treats a
3xx as a malformed response).
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from collections.abc import Callable, Mapping
from urllib.parse import SplitResult, urlsplit

from app.config import Settings
from app.services.ai.compatible import HttpResponse, _StdlibResponse

Resolver = Callable[[str, int], list[str]]


class EndpointBlocked(OSError):
    """The endpoint is refused; ``reason`` is machine-readable and safe to show."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"model endpoint blocked: {reason}")
        self.reason = reason


def system_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


def is_public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        address = mapped
    return address.is_global and not address.is_multicast


def check_endpoint_url(url: str, *, allow_private: bool = False) -> SplitResult:
    if not isinstance(url, str) or not url or any(c.isspace() or ord(c) < 32 for c in url):
        raise EndpointBlocked("host")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise EndpointBlocked("port") from None
    if parts.scheme != "https" and not (allow_private and parts.scheme == "http"):
        raise EndpointBlocked("scheme")
    if parts.username is not None or parts.password is not None:
        raise EndpointBlocked("credentials")
    if not parts.hostname:
        raise EndpointBlocked("host")
    if port == 0:
        raise EndpointBlocked("port")
    if parts.query or parts.fragment or url.endswith(("?", "#")):
        raise EndpointBlocked("query")
    return parts


def _default_port(parts: SplitResult) -> int:
    return parts.port or (443 if parts.scheme == "https" else 80)


def resolve_endpoint(host: str, port: int, *, allow_private: bool = False,
                     resolver: Resolver = system_resolver) -> list[str]:
    try:
        addresses = resolver(host, port)
    except OSError:
        raise EndpointBlocked("unresolvable") from None
    if not addresses:
        raise EndpointBlocked("unresolvable")
    if not allow_private and not all(is_public_address(address) for address in addresses):
        raise EndpointBlocked("private_address")
    return addresses


def check_endpoint(url: str, *, allow_private: bool = False, resolver: Resolver = system_resolver) -> None:
    parts = check_endpoint_url(url, allow_private=allow_private)
    resolve_endpoint(parts.hostname or "", _default_port(parts), allow_private=allow_private, resolver=resolver)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, *, ip: str, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout)
        self._pinned_ip = ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, *, ip: str, timeout: float, context: ssl.SSLContext) -> None:
        super().__init__(host, port, timeout=timeout, context=context)
        self._pinned_ip = ip
        self._pinned_context = context

    def connect(self) -> None:
        sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        self.sock = self._pinned_context.wrap_socket(sock, server_hostname=self.host)


class GuardedTransport:
    """``HttpTransport`` that resolves, checks and pins on every ``open``."""

    def __init__(self, *, allow_private: bool = False, resolver: Resolver = system_resolver,
                 ssl_context: ssl.SSLContext | None = None) -> None:
        self._allow_private = allow_private
        self._resolver = resolver
        self._ssl_context = ssl_context

    def open(self, url: str, body: bytes, headers: Mapping[str, str], timeout: float) -> HttpResponse:
        parts = check_endpoint_url(url, allow_private=self._allow_private)
        host, port = parts.hostname or "", _default_port(parts)
        ip = resolve_endpoint(host, port, allow_private=self._allow_private, resolver=self._resolver)[0]
        connection: http.client.HTTPConnection
        if parts.scheme == "https":
            context = self._ssl_context or ssl.create_default_context()
            connection = _PinnedHTTPSConnection(host, port, ip=ip, timeout=timeout, context=context)
        else:
            connection = _PinnedHTTPConnection(host, port, ip=ip, timeout=timeout)
        try:
            connection.request("POST", parts.path or "/", body=body, headers=dict(headers))
            sock = connection.sock
            response = connection.getresponse()
        except BaseException:
            connection.close()
            raise
        return _StdlibResponse(connection, sock, response)


def build_transport(settings: Settings) -> GuardedTransport:
    return GuardedTransport(allow_private=settings.MODEL_ENDPOINT_ALLOW_PRIVATE)
```

- [ ] **Step 4：运行确认通过**

Run: `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_l05.py -q -p no:cacheprovider`
Expected: 全部通过。若 `test_redirect_is_not_followed` 抛出的是别的 `ModelCallError` 子类，读 `compatible.py:388-416` 确认 3xx 的实际分类并把断言改成该类；不改客户端行为。

- [ ] **Step 5：门禁、交接、提交**

```bash
./scripts/verify.sh
git add src/backend/app/services/ai/outbound.py tests/backend/test_l05.py docs/tasks.md docs/handoffs/claude-l05.md
git commit -m "feat(backend): L05 模型出站地址校验与钉 IP 传输

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6（L06）：个人配置接口

**Files:**
- Create: `src/backend/app/services/model_configs.py`
- Create: `src/backend/app/api/model_config.py`
- Modify: `src/backend/app/main.py`
- Test: `tests/backend/test_l06.py`

**Interfaces:**
- Consumes: Task 4 的 `CredentialCipher`、仓储函数；Task 5 的 `check_endpoint`、`EndpointBlocked`、`build_transport`；Task 3 的生成模型。
- Produces:
  - `app.services.model_configs`：`ModelConfigView`、`TestOutcome(ok: bool, error_class: str | None, latency_ms: int)`、`CredentialStoreDisabled`、`InvalidKey`、`ConfigTestLimiter`；`view(settings, user_id) -> ModelConfigView`；`save(settings, user_id, *, base_url, model, api_key, resolver=...) -> ModelConfigView`；`clear(settings, user_id) -> None`；`run_test(settings, user_id, *, base_url, model, api_key, transport) -> TestOutcome`。
  - 路由读取 `request.app.state.model_transport`（缺省为 `None`，此时用 `build_transport(settings)`）与 `request.app.state.config_test_limiter`；测试通过设置这两个属性注入假传输。

- [ ] **Step 1：写失败测试**

```python
# tests/backend/test_l06.py
"""L06：/api/v1/me/model-config——只作用于本人、脱敏、地址校验、测试连接与限流（ADR-080）。"""
from __future__ import annotations

import base64
import json
import logging
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.repositories import model_configs as repo
from app.repositories.accounts import insert_account
from app.repositories.sqlite import migrate
from app.services.auth import issue_access_token

SECRET = "l06-test-signing-key-0123456789abcdefghijkl"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
ROOT_KEY_B64 = base64.urlsafe_b64encode(bytes(range(32))).decode()
API_KEY = "sk-live-AAAABBBBCCCC1234"
BASE = "/api/v1/me/model-config"


class FakeResponse:
    def __init__(self, status, body):
        self.status, self._body = status, body

    def header(self, name):
        return None

    def read(self, amount, timeout):
        data, self._body = self._body[:amount], self._body[amount:]
        return data

    def close(self):
        pass


class FakeTransport:
    def __init__(self, status=200):
        self.status, self.requests = status, []

    def open(self, url, body, headers, timeout):
        self.requests.append((url, json.loads(body), dict(headers)))
        payload = {"model": "m", "choices": [{"message": {"content": "o"}, "finish_reason": "length"}],
                   "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
        if self.status != 200:
            payload = {"error": {"message": f"upstream said no to {headers.get('Authorization')}"}}
        return FakeResponse(self.status, json.dumps(payload).encode())


def _token(user):
    return issue_access_token(user_id=user.id, role=user.role, secret=SECRET.encode(),
                              issued_at=int(time.time()), ttl_seconds=3600)


def _auth(user):
    return {"Authorization": f"Bearer {_token(user)}"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    alice = insert_account(url, account_id=uuid.uuid4().hex, username="alice01", password_hash=VALID_HASH, role="teacher")
    bob = insert_account(url, account_id=uuid.uuid4().hex, username="bob0001", password_hash=VALID_HASH, role="student")
    monkeypatch.setenv("SQLITE_URL", url)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    monkeypatch.setenv("LLM_MODE", "personal")
    monkeypatch.setenv("MODEL_CREDENTIAL_KEY", ROOT_KEY_B64)
    monkeypatch.setattr("app.services.model_configs.system_resolver", lambda host, port: ["1.1.1.1"])
    app = create_app()
    app.state.model_transport = FakeTransport()
    with TestClient(app) as client:
        yield type("Env", (), {"client": client, "url": url, "alice": alice, "bob": bob, "app": app})


def _save(env, user, **body):
    payload = {"base_url": "https://api.example.com/v1", "model": "m1", "api_key": API_KEY, **body}
    return env.client.put(BASE, json=payload, headers=_auth(user))


def test_requires_login(env):
    assert env.client.get(BASE).status_code == 401
    assert env.client.put(BASE, json={}).status_code == 401
    assert env.client.delete(BASE).status_code == 401
    assert env.client.post(f"{BASE}/test").status_code == 401


def test_unconfigured_view(env):
    body = env.client.get(BASE, headers=_auth(env.alice)).json()
    assert body == {"runtime_mode": "personal", "configured": False}


def test_save_returns_masked_view_and_never_the_key(env, caplog):
    caplog.set_level(logging.DEBUG)
    response = _save(env, env.alice)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["configured"] is True and body["key_hint"] == "1234" and body["version"] == 1
    assert body["base_url"] == "https://api.example.com/v1" and body["model"] == "m1"
    again = env.client.get(BASE, headers=_auth(env.alice))
    assert API_KEY not in response.text and API_KEY not in again.text
    assert API_KEY not in caplog.text


def test_configs_are_per_user(env):
    _save(env, env.alice)
    assert env.client.get(BASE, headers=_auth(env.bob)).json()["configured"] is False
    env.client.delete(BASE, headers=_auth(env.bob))
    assert env.client.get(BASE, headers=_auth(env.alice)).json()["configured"] is True


def test_body_cannot_name_another_user(env):
    response = env.client.put(BASE, headers=_auth(env.bob), json={
        "base_url": "https://api.example.com/v1", "model": "m1", "api_key": API_KEY, "user_id": env.alice.id})
    assert response.status_code == 422
    assert repo.get_config(env.url, env.alice.id) is None


def test_key_required_on_first_save_and_when_endpoint_changes(env):
    first = env.client.put(BASE, headers=_auth(env.alice), json={"base_url": "https://api.example.com/v1", "model": "m1"})
    assert first.status_code == 422
    assert first.json()["details"]["fields"] == [{"in": "body", "field": "api_key", "reason": "required_when_endpoint_changes"}]
    _save(env, env.alice)
    keep = env.client.put(BASE, headers=_auth(env.alice), json={"base_url": "https://api.example.com/v1", "model": "m2"})
    assert keep.status_code == 200 and keep.json()["model"] == "m2" and keep.json()["version"] == 2
    moved = env.client.put(BASE, headers=_auth(env.alice), json={"base_url": "https://other.example.com/v1", "model": "m2"})
    assert moved.status_code == 422


@pytest.mark.parametrize("base_url, reason", [
    ("http://api.example.com/v1", "scheme"),
    ("https://u:p@api.example.com/v1", "credentials"),
    ("https://api.example.com/v1?a=1", "query"),
])
def test_rejects_bad_urls(env, base_url, reason):
    response = _save(env, env.alice, base_url=base_url)
    assert response.status_code == 422
    assert response.json()["details"]["fields"] == [{"in": "body", "field": "base_url", "reason": reason}]
    assert API_KEY not in response.text


def test_rejects_private_address(env, monkeypatch):
    monkeypatch.setattr("app.services.model_configs.system_resolver", lambda host, port: ["169.254.169.254"])
    response = _save(env, env.alice, base_url="https://metadata.example.com/v1")
    assert response.status_code == 422
    assert response.json()["details"]["fields"][0]["reason"] == "private_address"
    assert repo.get_config(env.url, env.alice.id) is None


def test_rejects_key_with_spaces(env):
    response = _save(env, env.alice, api_key="sk bad key")
    assert response.status_code == 422
    assert response.json()["details"]["fields"] == [{"in": "body", "field": "api_key", "reason": "invalid_characters"}]


def test_delete_is_idempotent(env):
    _save(env, env.alice)
    assert env.client.delete(BASE, headers=_auth(env.alice)).status_code == 204
    assert env.client.delete(BASE, headers=_auth(env.alice)).status_code == 204
    assert env.client.get(BASE, headers=_auth(env.alice)).json() == {"runtime_mode": "personal", "configured": False}


def test_test_saved_config_sends_one_minimal_request_and_records_result(env):
    _save(env, env.alice)
    response = env.client.post(f"{BASE}/test", headers=_auth(env.alice))
    assert response.status_code == 200 and response.json()["ok"] is True
    [(url, payload, headers)] = env.app.state.model_transport.requests
    assert url == "https://api.example.com/v1/chat/completions"
    assert payload["model"] == "m1" and payload["max_tokens"] == 1
    assert headers["Authorization"] == f"Bearer {API_KEY}"
    view = env.client.get(BASE, headers=_auth(env.alice)).json()
    assert view["last_test"]["ok"] is True


def test_test_failure_reports_class_only(env):
    _save(env, env.alice)
    env.app.state.model_transport = FakeTransport(status=401)
    response = env.client.post(f"{BASE}/test", headers=_auth(env.alice))
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False and body["error_class"] == "auth"
    assert API_KEY not in response.text and "upstream said no" not in response.text
    assert env.client.get(BASE, headers=_auth(env.alice)).json()["last_test"]["error_class"] == "auth"


def test_test_unsaved_values_does_not_store(env):
    response = env.client.post(f"{BASE}/test", headers=_auth(env.alice), json={
        "base_url": "https://api.example.com/v1", "model": "m1", "api_key": API_KEY})
    assert response.status_code == 200 and response.json()["ok"] is True
    assert repo.get_config(env.url, env.alice.id) is None


def test_test_without_body_and_without_config(env):
    response = env.client.post(f"{BASE}/test", headers=_auth(env.alice))
    assert response.status_code == 409 and response.json()["code"] == "MODEL_CONFIG_REQUIRED"


def test_test_with_partial_body(env):
    response = env.client.post(f"{BASE}/test", headers=_auth(env.alice), json={"model": "m1"})
    assert response.status_code == 422


def test_test_blocked_address_is_reported_without_a_request(env, monkeypatch):
    monkeypatch.setattr("app.services.model_configs.system_resolver", lambda host, port: ["10.0.0.1"])
    response = env.client.post(f"{BASE}/test", headers=_auth(env.alice), json={
        "base_url": "https://intranet.example.com/v1", "model": "m1", "api_key": API_KEY})
    assert response.status_code == 200
    assert response.json() == {"ok": False, "latency_ms": 0, "error_class": "blocked_address"}
    assert env.app.state.model_transport.requests == []


def test_test_is_rate_limited_per_user(env):
    _save(env, env.alice)
    _save(env, env.bob)
    for _ in range(5):
        assert env.client.post(f"{BASE}/test", headers=_auth(env.alice)).status_code == 200
    limited = env.client.post(f"{BASE}/test", headers=_auth(env.alice))
    assert limited.status_code == 429 and limited.json()["code"] == "RATE_LIMITED"
    assert int(limited.headers["Retry-After"]) >= 1
    assert env.client.post(f"{BASE}/test", headers=_auth(env.bob)).status_code == 200


def test_writes_disabled_without_root_key(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    user = insert_account(url, account_id=uuid.uuid4().hex, username="carol01", password_hash=VALID_HASH, role="student")
    monkeypatch.setenv("SQLITE_URL", url)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    monkeypatch.setenv("LLM_MODE", "demo")
    monkeypatch.setenv("EMBEDDING_MODE", "demo")
    monkeypatch.delenv("MODEL_CREDENTIAL_KEY", raising=False)
    with TestClient(create_app()) as client:
        assert client.get(BASE, headers=_auth(user)).json() == {"runtime_mode": "demo", "configured": False}
        response = client.put(BASE, headers=_auth(user), json={
            "base_url": "https://api.example.com/v1", "model": "m1", "api_key": API_KEY})
        assert response.status_code == 503
        assert response.json()["details"] == {"reason": "credential_store_disabled"}
```

- [ ] **Step 2：运行确认失败**

Run: `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_l06.py -q -p no:cacheprovider`
Expected: 全部 FAIL（路由 404 或导入错误）。

- [ ] **Step 3：写服务**

```python
# src/backend/app/services/model_configs.py
"""Business rules for a user's own model configuration (ADR-080)."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass

from app.config import Settings
from app.repositories import model_configs as repo
from app.repositories.model_configs import KeyRequired, ModelConfigRow
from app.services.ai.client import Message, ModelCallError, ModelRequest
from app.services.ai.compatible import CompatibleModelClient, HttpTransport
from app.services.ai.outbound import EndpointBlocked, Resolver, check_endpoint, system_resolver
from app.services.credentials import CredentialCipher, CredentialError, ModelConfigRequired

TEST_TIMEOUT_SECONDS = 15.0
TEST_PURPOSE = "config_test"
BLOCKED_ADDRESS = "blocked_address"

__all__ = ["BLOCKED_ADDRESS", "ConfigTestLimiter", "CredentialStoreDisabled", "InvalidKey", "KeyRequired",
           "ModelConfigView", "TestOutcome", "clear", "run_test", "save", "view"]


class CredentialStoreDisabled(Exception):
    """``MODEL_CREDENTIAL_KEY`` is not configured, so nothing can be sealed or opened."""


class InvalidKey(Exception):
    """The API key cannot go into an HTTP header (non-printable, non-ASCII or spaces)."""


@dataclass(frozen=True)
class ModelConfigView:
    runtime_mode: str
    row: ModelConfigRow | None


@dataclass(frozen=True)
class TestOutcome:
    ok: bool
    error_class: str | None
    latency_ms: int


def _cipher(settings: Settings) -> CredentialCipher:
    try:
        return CredentialCipher.from_settings(settings)
    except CredentialError:
        raise CredentialStoreDisabled() from None


def _check_key(api_key: str) -> None:
    if not api_key or any(not 33 <= ord(c) <= 126 for c in api_key):
        raise InvalidKey()


def view(settings: Settings, user_id: str) -> ModelConfigView:
    return ModelConfigView(settings.LLM_MODE, repo.get_config(settings.SQLITE_URL, user_id))


def save(settings: Settings, user_id: str, *, base_url: str, model: str, api_key: str | None,
         resolver: Resolver | None = None) -> ModelConfigView:
    cipher = _cipher(settings)
    check_endpoint(base_url, allow_private=settings.MODEL_ENDPOINT_ALLOW_PRIVATE,
                   resolver=resolver or system_resolver)
    sealed = hint = None
    if api_key is not None:
        _check_key(api_key)
        sealed, hint = cipher.seal(user_id, api_key), api_key[-4:]
    row = repo.save_config(settings.SQLITE_URL, user_id=user_id, base_url=base_url, model=model.strip(),
                           sealed=sealed, key_hint=hint)
    return ModelConfigView(settings.LLM_MODE, row)


def clear(settings: Settings, user_id: str) -> None:
    repo.delete_config(settings.SQLITE_URL, user_id)


def run_test(settings: Settings, user_id: str, *, base_url: str | None, model: str | None, api_key: str | None,
             transport: HttpTransport, resolver: Resolver | None = None,
             clock: Callable[[], float] = time.monotonic) -> TestOutcome:
    """One minimal chat call. With no values the saved configuration is tested and the result recorded."""
    saved = base_url is None
    if saved:
        row = repo.get_config(settings.SQLITE_URL, user_id)
        if row is None:
            raise ModelConfigRequired()
        try:
            base_url, model, api_key = row.base_url, row.model, _cipher(settings).open(user_id, row.sealed)
        except CredentialError:
            raise CredentialStoreDisabled() from None
    else:
        _check_key(api_key or "")
    started = clock()
    try:
        check_endpoint(base_url or "", allow_private=settings.MODEL_ENDPOINT_ALLOW_PRIVATE,
                       resolver=resolver or system_resolver)
    except EndpointBlocked:
        outcome = TestOutcome(False, BLOCKED_ADDRESS, 0)
    else:
        try:
            client = CompatibleModelClient(base_url or "", api_key or "", transport=transport,
                                           default_timeout_seconds=TEST_TIMEOUT_SECONDS)
            client.complete(ModelRequest(purpose=TEST_PURPOSE, model=model or "",
                                         messages=(Message("user", "ping"),), max_output_tokens=1))
            outcome = TestOutcome(True, None, max(0, int((clock() - started) * 1000)))
        except ModelCallError as error:
            outcome = TestOutcome(False, error.error_class.value, max(0, int((clock() - started) * 1000)))
    if saved:
        repo.record_test(settings.SQLITE_URL, user_id, ok=outcome.ok, error_class=outcome.error_class)
    return outcome


class ConfigTestLimiter:
    """At most ``limit`` test calls per user in any ``window_seconds``; in-process, bounded."""

    def __init__(self, *, limit: int = 5, window_seconds: float = 60.0, capacity: int = 4096,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._limit, self._window, self._capacity, self._clock = limit, window_seconds, capacity, clock
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()
        self._mutex = threading.Lock()

    def acquire(self, user_id: str) -> int:
        """Return 0 when allowed, otherwise the whole seconds to wait."""
        now = self._clock()
        with self._mutex:
            hits = self._hits.setdefault(user_id, deque())
            self._hits.move_to_end(user_id)
            while hits and now - hits[0] >= self._window:
                hits.popleft()
            if len(hits) >= self._limit:
                return max(1, int(self._window - (now - hits[0])) + 1)
            hits.append(now)
            while len(self._hits) > self._capacity:
                self._hits.popitem(last=False)
            return 0
```

- [ ] **Step 4：写路由**

```python
# src/backend/app/api/model_config.py
"""Current user's model configuration (ADR-080). Routes only translate; rules live in the service."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.dependencies import current_user
from app.repositories.accounts import AccountRecord
from app.schemas.contracts import ModelConfig, ModelConfigTestRequest, ModelConfigTestResult, ModelConfigUpdate
from app.schemas.errors import Error
from app.services import model_configs as service
from app.services.ai.compatible import HttpTransport
from app.services.ai.outbound import EndpointBlocked, build_transport
from app.services.credentials import ModelConfigRequired

router = APIRouter(prefix="/api/v1/me/model-config", tags=["settings"])

_VALIDATION_MESSAGE = "请求参数不符合要求，请检查标注的字段"
_REQUIRED_MESSAGE = "请先在「模型 API 设置」中保存你的模型 API 配置"
_ERRORS = {401: {"model": Error}, 422: {"model": Error}}


def _plain(value: Any) -> str | None:
    """``format: password`` fields may be generated as ``SecretStr``."""
    if value is None:
        return None
    return value.get_secret_value() if hasattr(value, "get_secret_value") else str(value)


def _invalid(field: str, reason: str) -> JSONResponse:
    body = Error(code="VALIDATION_ERROR", message=_VALIDATION_MESSAGE,
                 details={"fields": [{"in": "body", "field": field, "reason": reason}]})
    return JSONResponse(status_code=422, content=body.model_dump())


def _disabled() -> JSONResponse:
    body = Error(code="STORAGE_UNAVAILABLE", message="服务端未启用个人模型凭据存储",
                 details={"reason": "credential_store_disabled"})
    return JSONResponse(status_code=503, content=body.model_dump())


def _to_wire(view: service.ModelConfigView) -> dict[str, Any]:
    row = view.row
    if row is None:
        return {"runtime_mode": view.runtime_mode, "configured": False}
    wire: dict[str, Any] = {
        "runtime_mode": view.runtime_mode, "configured": True, "base_url": row.base_url, "model": row.model,
        "key_hint": row.key_hint, "version": row.version, "updated_at": row.updated_at,
    }
    if row.last_test_at is not None:
        last: dict[str, Any] = {"ok": bool(row.last_test_ok), "tested_at": row.last_test_at}
        if row.last_test_error_class is not None:
            last["error_class"] = row.last_test_error_class
        wire["last_test"] = last
    return wire


def _transport(request: Request) -> HttpTransport:
    return getattr(request.app.state, "model_transport", None) or build_transport(request.app.state.settings)


@router.get("", operation_id="getModelConfig", response_model=ModelConfig, response_model_exclude_none=True,
            responses={401: {"model": Error}})
def get_model_config(request: Request, user: AccountRecord = Depends(current_user)) -> JSONResponse:
    return JSONResponse(content=_to_wire(service.view(request.app.state.settings, user.id)))


@router.put("", operation_id="saveModelConfig", response_model=ModelConfig, response_model_exclude_none=True,
            responses={**_ERRORS, 503: {"model": Error}})
def save_model_config(payload: ModelConfigUpdate, request: Request,
                      user: AccountRecord = Depends(current_user)) -> JSONResponse:
    try:
        view = service.save(request.app.state.settings, user.id, base_url=payload.base_url,
                            model=payload.model, api_key=_plain(payload.api_key))
    except EndpointBlocked as blocked:
        return _invalid("base_url", blocked.reason)
    except service.KeyRequired:
        return _invalid("api_key", "required_when_endpoint_changes")
    except service.InvalidKey:
        return _invalid("api_key", "invalid_characters")
    except service.CredentialStoreDisabled:
        return _disabled()
    return JSONResponse(content=_to_wire(view))


@router.delete("", operation_id="clearModelConfig", status_code=status.HTTP_204_NO_CONTENT,
               response_class=Response, responses={401: {"model": Error}})
def clear_model_config(request: Request, user: AccountRecord = Depends(current_user)) -> Response:
    service.clear(request.app.state.settings, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/test", operation_id="testModelConfig", response_model=ModelConfigTestResult,
             response_model_exclude_none=True,
             responses={**_ERRORS, 409: {"model": Error}, 429: {"model": Error}, 503: {"model": Error}})
def test_model_config(request: Request, payload: ModelConfigTestRequest | None = None,
                      user: AccountRecord = Depends(current_user)) -> JSONResponse:
    values = (None, None, None) if payload is None else (payload.base_url, payload.model, _plain(payload.api_key))
    if any(value is not None for value in values) and not all(value is not None for value in values):
        missing = next(name for name, value in zip(("base_url", "model", "api_key"), values) if value is None)
        return _invalid(missing, "missing")
    wait = request.app.state.config_test_limiter.acquire(user.id)
    if wait:
        body = Error(code="RATE_LIMITED", message="测试过于频繁，请稍后再试")
        return JSONResponse(status_code=429, content=body.model_dump(exclude_none=True), headers={"Retry-After": str(wait)})
    try:
        outcome = service.run_test(request.app.state.settings, user.id, base_url=values[0], model=values[1],
                                   api_key=values[2], transport=_transport(request))
    except ModelConfigRequired:
        body = Error(code="MODEL_CONFIG_REQUIRED", message=_REQUIRED_MESSAGE)
        return JSONResponse(status_code=409, content=body.model_dump(exclude_none=True))
    except service.InvalidKey:
        return _invalid("api_key", "invalid_characters")
    except service.CredentialStoreDisabled:
        return _disabled()
    wire: dict[str, Any] = {"ok": outcome.ok, "latency_ms": outcome.latency_ms}
    if outcome.error_class is not None:
        wire["error_class"] = outcome.error_class
    return JSONResponse(content=wire)
```

`src/backend/app/main.py`：导入 `from app.api.model_config import router as model_config_router` 与 `from app.services.model_configs import ConfigTestLimiter`；在 `create_app` 中 `application.state.registration_limiter = ...` 之后加 `application.state.config_test_limiter = ConfigTestLimiter()` 与 `application.state.model_transport = None`；在 `include_router(auth_router)` 之后加 `application.include_router(model_config_router)`。

- [ ] **Step 5：运行确认通过**

Run: `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_l06.py -q -p no:cacheprovider`
Expected: 全部通过。若 `Error.model_dump()` 对空 `details` 的输出与断言不一致，统一用 `model_dump(exclude_none=True)` 并保持测试中的精确断言。

- [ ] **Step 6：确认运行中的 OpenAPI 与契约一致**

Run: `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend -q -p no:cacheprovider -k "openapi or contract or b05"`
Expected: 通过。若有用例比对「实现暴露的操作集合」与契约，四个新 `operation_id` 应已匹配。

- [ ] **Step 7：门禁、交接、提交**

```bash
./scripts/verify.sh
git add src/backend/app/services/model_configs.py src/backend/app/api/model_config.py src/backend/app/main.py \
        tests/backend/test_l06.py docs/tasks.md docs/handoffs/claude-l06.md
git commit -m "feat(backend): L06 个人模型配置接口

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7（L07）：上传绑定与 worker 按任务取工具包

**Files:**
- Modify: `src/backend/app/repositories/tasks.py:68-153`
- Modify: `src/backend/app/services/materials.py:49-80`
- Modify: `src/backend/app/api/materials.py:130-155`
- Modify: `src/backend/app/services/ai/policy.py:305-331,468-492`（`CallAttribution.user_id` 并传入调用记录）
- Modify: `src/backend/app/repositories/model_calls.py`（`CallRecord.user_id` 与列写入）
- Modify: `tests/backend/test_e12.py`（追加一条凭据终止用例）
- Modify: `src/backend/app/workers/extract_task.py`（`ExtractionToolkit`、`_attempts`、`_fail`、`run_extract_stage`，新增 `fail_for_credential`）
- Modify: `src/backend/app/workers/persist_graph.py:466-512`
- Create: `src/backend/app/workers/toolkits.py`
- Modify: `src/backend/app/workers/runner.py`
- Modify: `src/backend/app/services/ai/factory.py`
- Test: `tests/backend/test_l07.py`

**Interfaces:**
- Consumes: Task 4、Task 5 的全部产出。
- Produces:
  - `create_material_task(..., created_by: str | None = None, bind_model_config: bool = False)`；`ModelConfigMissing`（在 `app.repositories.tasks`）。
  - `upload_material(..., uploaded_by: str | None = None)`，`personal` 模式下未配置抛 `ModelConfigRequired`。
  - `CallAttribution.user_id: str | None = None`；`CallRecord.user_id: str | None = None`，`model_calls.user_id` 列随预写入库。
  - `ExtractionToolkit` 新增字段 `user_id: str | None = None`、`guard: Callable[[], None] | None = None`。
  - `fail_for_credential(sqlite_url: str, lease: Lease, reason: str) -> ExtractOutcome`。
  - `ToolkitSource = ExtractionToolkit | Callable[[Lease], ExtractionToolkit]`；`run_pipeline_once(settings, *, toolkit: ToolkitSource, ...)`。
  - `app.workers.toolkits`：`MAX_OUTPUT_TOKENS = 4096`；`TaskToolkits(settings, *, cipher=None, store=None, transport=None)`，`.for_lease(lease: Lease) -> ExtractionToolkit`。
  - `runner.build_toolkit(settings) -> ToolkitSource`；`runner.BindingScrub(sqlite_url)` 维护钩子。

- [ ] **Step 1：先读三处既有实现，确认插入点**

```bash
sed -n 468,515p src/backend/app/workers/extract_task.py
sed -n 630,705p src/backend/app/workers/extract_task.py
grep -n "chat_service\|build_toolkit\|run_pipeline_once(" -r tests | head -30
```

确认两点并写入交接：`_Dispatcher._settle` 会把工作线程里的未捕获异常在主线程重新抛出；既有测试调用 `run_pipeline_once` 时 `toolkit` 传的是 `ExtractionToolkit` 实例（本任务保持兼容）。

- [ ] **Step 2：写失败测试**

```python
# tests/backend/test_l07.py
"""L07：上传绑定任务快照、worker 按任务取模型、改/清配置与重启接管的语义（ADR-080 决定 3）。"""
from __future__ import annotations

import base64
import json
import time
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import create_app
from app.repositories import model_configs as repo
from app.repositories.accounts import insert_account
from app.repositories.courses import create_course
from app.repositories.sqlite import connect, migrate
from app.repositories.task_leases import Lease
from app.repositories.tasks import ModelConfigMissing, create_material_task
from app.services.ai.client import Message, ModelRequest
from app.services.ai.policy import CallAttribution
from app.services.auth import issue_access_token
from app.services.credentials import CredentialCipher, CredentialUnavailable
from app.workers.runner import BindingScrub, build_toolkit
from app.workers.toolkits import TaskToolkits

SECRET = "l07-test-signing-key-0123456789abcdefghijkl"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
ROOT_KEY = bytes(range(32))
ROOT_KEY_B64 = base64.urlsafe_b64encode(ROOT_KEY).decode()


class RecordingTransport:
    """Answers every chat request and records (url, bearer, model)."""

    def __init__(self):
        self.calls = []

    def open(self, url, body, headers, timeout):
        self.calls.append((url, headers["Authorization"], json.loads(body)["model"]))
        payload = json.dumps({"model": "m", "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                              "usage": {"prompt_tokens": 1, "completion_tokens": 1}}).encode()
        return SimpleNamespace(status=200, header=lambda name: None, close=lambda: None,
                               read=_reader(payload))


def _reader(payload):
    state = {"data": payload}

    def read(amount, timeout):
        chunk, state["data"] = state["data"][:amount], state["data"][amount:]
        return chunk

    return read


def _settings(url, **extra):
    return load_settings({"SQLITE_URL": url, "LLM_MODE": "personal", "MODEL_CREDENTIAL_KEY": ROOT_KEY_B64, **extra})


@pytest.fixture
def url(tmp_path):
    value = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(value)
    return value


def _user(url, name, role="teacher"):
    return insert_account(url, account_id=uuid.uuid4().hex, username=name, password_hash=VALID_HASH, role=role)


def _configure(url, user, *, base_url, model, key):
    return repo.save_config(url, user_id=user.id, base_url=base_url, model=model,
                            sealed=CredentialCipher(ROOT_KEY).seal(user.id, key), key_hint=key[-4:])


def _stored():
    return SimpleNamespace(original_filename="a.md", format="markdown", size_bytes=10,
                           content_hash="sha256:" + "0" * 64, storage_name=uuid.uuid4().hex)


def _bound_task(url, course_id, user):
    return create_material_task(url, course_id=course_id, stored_file=_stored(), idempotency_key=uuid.uuid4().hex,
                                created_by=user.id, bind_model_config=True).task


def _lease(task):
    return Lease(task_id=task.id, course_id=task.course_id, document_id=task.document_id, stage="extracting",
                 progress=0.0, attempt=1, owner="w", token="t" * 32, expires_at=int(time.time()) + 60)


def _call(toolkit, lease):
    if toolkit.guard is not None:
        toolkit.guard()
    client = toolkit.policy.bind(CallAttribution(course_id=lease.course_id, task_id=lease.task_id,
                                                 user_id=toolkit.user_id))
    return client.complete(ModelRequest(purpose="extract_entities", model=toolkit.model,
                                        messages=(Message("user", "x"),), max_output_tokens=8))


def test_create_task_records_creator_and_snapshot(url):
    teacher = _user(url, "teacher1")
    course = create_course(url, name="课", description=None, creator_id=teacher.id)
    _configure(url, teacher, base_url="https://a.example/v1", model="m1", key="sk-aaaa-1111")
    task = _bound_task(url, course.id, teacher)
    with connect(url) as database:
        assert database.execute("SELECT created_by FROM processing_tasks WHERE id = ?", (task.id,)).fetchone() == (teacher.id,)
    assert repo.get_binding(url, task.id).model == "m1"


def test_create_task_without_config_writes_nothing(url):
    teacher = _user(url, "teacher1")
    course = create_course(url, name="课", description=None, creator_id=teacher.id)
    with pytest.raises(ModelConfigMissing):
        create_material_task(url, course_id=course.id, stored_file=_stored(), idempotency_key="k1",
                             created_by=teacher.id, bind_model_config=True)
    with connect(url) as database:
        assert database.execute("SELECT count(*) FROM materials").fetchone() == (0,)
        assert database.execute("SELECT count(*) FROM processing_tasks").fetchone() == (0,)


def test_two_teachers_use_their_own_key_and_model(url):
    alice, bob = _user(url, "alice01"), _user(url, "bob0001")
    course = create_course(url, name="课", description=None, creator_id=alice.id)
    _configure(url, alice, base_url="https://a.example/v1", model="model-a", key="sk-alice-0001")
    _configure(url, bob, base_url="https://b.example/v1", model="model-b", key="sk-bob-0002")
    task_a, task_b = _bound_task(url, course.id, alice), _bound_task(url, course.id, bob)
    transport = RecordingTransport()
    toolkits = TaskToolkits(_settings(url), transport=transport)
    _call(toolkits.for_lease(_lease(task_a)), _lease(task_a))
    _call(toolkits.for_lease(_lease(task_b)), _lease(task_b))
    assert transport.calls == [
        ("https://a.example/v1/chat/completions", "Bearer sk-alice-0001", "model-a"),
        ("https://b.example/v1/chat/completions", "Bearer sk-bob-0002", "model-b"),
    ]
    with connect(url) as database:
        rows = database.execute("SELECT task_id, user_id FROM model_calls ORDER BY rowid").fetchall()
    assert rows == [(task_a.id, alice.id), (task_b.id, bob.id)]


def test_changing_config_does_not_change_a_queued_task(url):
    teacher = _user(url, "teacher1")
    course = create_course(url, name="课", description=None, creator_id=teacher.id)
    _configure(url, teacher, base_url="https://a.example/v1", model="old-model", key="sk-old-0001")
    task = _bound_task(url, course.id, teacher)
    _configure(url, teacher, base_url="https://b.example/v1", model="new-model", key="sk-new-0002")
    transport = RecordingTransport()
    _call(TaskToolkits(_settings(url), transport=transport).for_lease(_lease(task)), _lease(task))
    assert transport.calls == [("https://a.example/v1/chat/completions", "Bearer sk-old-0001", "old-model")]


def test_restart_resolves_the_same_snapshot(url):
    teacher = _user(url, "teacher1")
    course = create_course(url, name="课", description=None, creator_id=teacher.id)
    _configure(url, teacher, base_url="https://a.example/v1", model="m1", key="sk-aaaa-1111")
    task = _bound_task(url, course.id, teacher)
    first, second = RecordingTransport(), RecordingTransport()
    _call(TaskToolkits(_settings(url), transport=first).for_lease(_lease(task)), _lease(task))
    _call(TaskToolkits(_settings(url), transport=second).for_lease(_lease(task)), _lease(task))
    assert first.calls == second.calls


def test_clearing_config_revokes_before_and_during_a_task(url):
    teacher = _user(url, "teacher1")
    course = create_course(url, name="课", description=None, creator_id=teacher.id)
    _configure(url, teacher, base_url="https://a.example/v1", model="m1", key="sk-aaaa-1111")
    running, queued = _bound_task(url, course.id, teacher), _bound_task(url, course.id, teacher)
    transport = RecordingTransport()
    toolkits = TaskToolkits(_settings(url), transport=transport)
    toolkit = toolkits.for_lease(_lease(running))
    _call(toolkit, _lease(running))
    repo.delete_config(url, teacher.id)
    with pytest.raises(CredentialUnavailable) as caught:
        toolkit.guard()
    assert caught.value.reason == "credential_revoked"
    with pytest.raises(CredentialUnavailable) as caught:
        toolkits.for_lease(_lease(queued))
    assert caught.value.reason == "credential_revoked"
    assert len(transport.calls) == 1


def test_task_without_snapshot_is_refused(url):
    teacher = _user(url, "teacher1")
    course = create_course(url, name="课", description=None, creator_id=teacher.id)
    task = create_material_task(url, course_id=course.id, stored_file=_stored(), idempotency_key="k").task
    with pytest.raises(CredentialUnavailable) as caught:
        TaskToolkits(_settings(url), transport=RecordingTransport()).for_lease(_lease(task))
    assert caught.value.reason == "credential_missing"


def test_snapshot_sealed_under_another_root_key_is_unreadable(url):
    teacher = _user(url, "teacher1")
    course = create_course(url, name="课", description=None, creator_id=teacher.id)
    _configure(url, teacher, base_url="https://a.example/v1", model="m1", key="sk-aaaa-1111")
    task = _bound_task(url, course.id, teacher)
    other = base64.urlsafe_b64encode(bytes(range(1, 33))).decode()
    settings = load_settings({"SQLITE_URL": url, "LLM_MODE": "personal", "MODEL_CREDENTIAL_KEY": other})
    with pytest.raises(CredentialUnavailable) as caught:
        TaskToolkits(settings, transport=RecordingTransport()).for_lease(_lease(task))
    assert caught.value.reason == "credential_unreadable"


def test_binding_scrub_hook(url):
    teacher = _user(url, "teacher1")
    course = create_course(url, name="课", description=None, creator_id=teacher.id)
    _configure(url, teacher, base_url="https://a.example/v1", model="m1", key="sk-aaaa-1111")
    task = _bound_task(url, course.id, teacher)
    with connect(url) as database:
        database.execute("UPDATE processing_tasks SET stage = 'awaiting_review', progress = 1 WHERE id = ?", (task.id,))
    BindingScrub(url)()
    assert repo.get_binding(url, task.id).scrub_reason == "terminal"


def test_build_toolkit_by_mode(url):
    assert callable(build_toolkit(_settings(url))) and not hasattr(build_toolkit(_settings(url)), "policy")
    demo = load_settings({"SQLITE_URL": url, "LLM_MODE": "demo", "EMBEDDING_MODE": "demo"})
    assert hasattr(build_toolkit(demo), "policy")


def _api(tmp_path, monkeypatch, url):
    monkeypatch.setenv("SQLITE_URL", url)
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    monkeypatch.setenv("LLM_MODE", "personal")
    monkeypatch.setenv("MODEL_CREDENTIAL_KEY", ROOT_KEY_B64)
    return TestClient(create_app())


def _auth(user):
    token = issue_access_token(user_id=user.id, role=user.role, secret=SECRET.encode(),
                               issued_at=int(time.time()), ttl_seconds=3600)
    return {"Authorization": f"Bearer {token}"}


def test_upload_requires_config_then_binds(tmp_path, monkeypatch, url):
    teacher = _user(url, "teacher1")
    course = create_course(url, name="课", description=None, creator_id=teacher.id)
    files = {"file": ("ch1.md", b"# \xe7\xac\xac\xe4\xb8\x80\xe7\xab\xa0\n\n\xe6\xa0\x88\xe6\x98\xaf\xe4\xb8\x80\xe7\xa7\x8d\xe7\xba\xbf\xe6\x80\xa7\xe8\xa1\xa8\xe3\x80\x82\n", "text/markdown")}
    with _api(tmp_path, monkeypatch, url) as client:
        refused = client.post(f"/api/v1/courses/{course.id}/documents", files=files, headers=_auth(teacher))
        assert refused.status_code == 409 and refused.json()["code"] == "MODEL_CONFIG_REQUIRED"
        with connect(url) as database:
            assert database.execute("SELECT count(*) FROM materials").fetchone() == (0,)
        assert not any((tmp_path / "storage").rglob("*.md"))
        _configure(url, teacher, base_url="https://a.example/v1", model="m1", key="sk-aaaa-1111")
        accepted = client.post(f"/api/v1/courses/{course.id}/documents", files=files, headers=_auth(teacher))
        assert accepted.status_code == 202, accepted.text
        assert repo.binding_active(url, accepted.json()["task_id"]) is True
```

- [ ] **Step 3：运行确认失败**

Run: `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_l07.py -q -p no:cacheprovider`
Expected: 收集错误（`ModelConfigMissing`、`app.workers.toolkits` 不存在）。

- [ ] **Step 4：改任务仓储**

`src/backend/app/repositories/tasks.py`：

```python
from app.repositories.model_configs import bind_task


class ModelConfigMissing(Exception):
    """``bind_model_config`` was requested but the creator has no saved model configuration."""
```

`_insert_task` 增加参数 `created_by: str | None`，SQL 改为：

```python
    database.execute(
        """INSERT INTO processing_tasks
           (id, course_id, document_id, idempotency_key, created_by)
           VALUES (?, ?, ?, ?, ?)""",
        (task_id, course_id, document_id, idempotency_key, created_by),
    )
```

`create_material_task` 签名加 `created_by: str | None = None, bind_model_config: bool = False`；函数开头加：

```python
    if bind_model_config and not created_by:
        raise ValueError("bind_model_config requires created_by")
```

在 `else` 分支里 `_insert_task(...)`（补传 `created_by=created_by`）之后、构造 `result` 之前加：

```python
                if bind_model_config and not bind_task(database, task_id=task.id, user_id=created_by):
                    raise ModelConfigMissing()
```

既有的 `except BaseException: ROLLBACK` 保证资料与任务都不落库。幂等重放分支不重新绑定。

- [ ] **Step 5：改上传服务与路由**

`src/backend/app/services/materials.py`：`upload_material` 加参数 `uploaded_by: str | None = None`；调用改为：

```python
    bind = settings.LLM_MODE == "personal"
    try:
        result = create_material_task(
            settings.SQLITE_URL,
            course_id=course_id,
            stored_file=stored,
            idempotency_key=idempotency_key or uuid4().hex,
            created_by=uploaded_by,
            bind_model_config=bind,
        )
    except ModelConfigMissing:
        _discard(storage, stored.storage_name)
        raise ModelConfigRequired() from None
```

（`except sqlite3.Error` 与 `except BaseException` 两个既有分支保留在其后。）导入 `ModelConfigMissing`、`ModelConfigRequired`。再加一个供路由先行检查的函数：

```python
def model_config_ready(settings: Settings, user_id: str) -> bool:
    """personal 模式下上传前的快速检查，避免为注定被拒的请求读完整个文件体。"""
    return settings.LLM_MODE != "personal" or get_config(settings.SQLITE_URL, user_id) is not None
```

`src/backend/app/api/materials.py`：在 `upload_document` 中 `settings = ...` 之后、读取表单之前加：

```python
    if not await run_in_threadpool(model_config_ready, settings, access.user.id):
        return _model_config_required()
```

`run_in_threadpool(upload_material, ...)` 加 `uploaded_by=access.user.id`，并在 `except FileStorageError` 之前加 `except ModelConfigRequired: return _model_config_required()`。新增：

```python
def _model_config_required() -> JSONResponse:
    body = Error(code="MODEL_CONFIG_REQUIRED", message="请先在「模型 API 设置」中保存你的模型 API 配置")
    return JSONResponse(status_code=409, content=body.model_dump(exclude_none=True))
```

并在该路由的 `responses` 加 `409: {"model": Error, "description": "未配置个人模型 API（`MODEL_CONFIG_REQUIRED`）"}`。

- [ ] **Step 6：`CallAttribution` 加 `user_id`**

`src/backend/app/services/ai/policy.py`：`CallAttribution` 在 `is_repair` 之后加 `user_id: str | None = None`，`__post_init__` 的第一个循环改为 `for name in ("task_id", "chunk_id", "request_id", "user_id"):`；`_prewrite` 构造 `CallRecord` 时加 `user_id=attribution.user_id`。

`src/backend/app/repositories/model_calls.py`：`CallRecord` 末尾加 `user_id: str | None = None`；`prewrite` 的 `INSERT` 列清单末尾加 `, user_id`，占位符加一个 `?`，参数元组末尾加 `record.user_id`。（按用户统计日预算在 Task 8。）

- [ ] **Step 7：改抽取阶段**

`src/backend/app/workers/extract_task.py`：

```python
from app.services.credentials import CredentialUnavailable

CREDENTIAL_MESSAGE = "个人模型 API 配置不可用，任务已终止；请检查「模型 API 设置」后重新上传"
```

`ExtractionToolkit` 加两个字段（放在 `gleaner` 之后）：

```python
    #: personal 模式：调用归属的用户与每次尝试前的快照有效性检查（失效时抛 CredentialUnavailable）。
    user_id: str | None = None
    guard: Callable[[], None] | None = None
    #: personal 模式下任务快照里的模型名；全局模式为 None（模型名已固化在抽取器工厂里）。
    model: str | None = None
```

`_attempts` 的循环体开头加 `if toolkit.guard is not None: toolkit.guard()`，`CallAttribution(...)` 加 `user_id=toolkit.user_id`。

`_fail` 加关键字参数 `message: str | None = None`，首行改为 `message = message or _MESSAGES[code]`。新增：

```python
def fail_for_credential(sqlite_url: str, lease: Lease, reason: str) -> ExtractOutcome:
    """ADR-080 决定 3：快照缺失、已撤销或不可解时终止任务，不重试、不换 key。"""
    return _fail(sqlite_url, lease, MODEL_ERROR_CODE, {"reason": reason}, {}, message=CREDENTIAL_MESSAGE)
```

`run_extract_stage` 在 `except LeaseLost` 之后加：

```python
    except CredentialUnavailable as exc:
        logger.warning("extracting task %s: credential unavailable (%s)", lease.task_id, exc.reason)
        return fail_for_credential(sqlite_url, lease, exc.reason)
```

- [ ] **Step 8：写工具包解析器**

```python
# src/backend/app/workers/toolkits.py
"""personal 模式：按任务的密钥快照构建抽取工具包（ADR-080 决定 3）。

每个任务一份独立的 ``ModelCallPolicy``，熔断状态互不影响。快照缺失、已置空或不可解时抛
``CredentialUnavailable``，由流水线把任务终止为 ``LLM_UNAVAILABLE``。
"""

from __future__ import annotations

from app.config import Settings
from app.repositories.model_calls import SqliteCallStore
from app.repositories.model_configs import binding_active, get_binding
from app.repositories.task_leases import Lease
from app.services.ai.compatible import CompatibleModelClient, HttpTransport
from app.services.ai.entities import EntityExtractor
from app.services.ai.outbound import build_transport
from app.services.ai.policy import CallStore, ModelCallPolicy
from app.services.ai.relations import RelationExtractor
from app.services.credentials import CredentialCipher, CredentialError, CredentialUnavailable
from app.workers.extract_task import ExtractionToolkit

# 与 K02 评测脚本的缺省值一致（evaluation/run_live_extraction.py）
MAX_OUTPUT_TOKENS = 4096


class TaskToolkits:
    def __init__(self, settings: Settings, *, cipher: CredentialCipher | None = None,
                 store: CallStore | None = None, transport: HttpTransport | None = None) -> None:
        self._settings = settings
        self._cipher = cipher or CredentialCipher.from_settings(settings)
        self._store = store or SqliteCallStore(settings.SQLITE_URL)
        self._transport = transport or build_transport(settings)

    def _require_active(self, task_id: str) -> None:
        if not binding_active(self._settings.SQLITE_URL, task_id):
            raise CredentialUnavailable("credential_revoked")

    def for_lease(self, lease: Lease) -> ExtractionToolkit:
        binding = get_binding(self._settings.SQLITE_URL, lease.task_id)
        if binding is None:
            raise CredentialUnavailable("credential_missing")
        if binding.sealed is None:
            raise CredentialUnavailable(
                "credential_revoked" if binding.scrub_reason == "revoked" else "credential_missing")
        try:
            api_key = self._cipher.open(binding.user_id, binding.sealed)
            client = CompatibleModelClient(binding.base_url, api_key, transport=self._transport,
                                           default_timeout_seconds=self._settings.LLM_REQUEST_TIMEOUT_SECONDS)
        except (CredentialError, ValueError):
            raise CredentialUnavailable("credential_unreadable") from None
        policy = ModelCallPolicy.from_settings(self._settings, primary=client, store=self._store)
        model, task_id = binding.model, lease.task_id
        return ExtractionToolkit(
            policy=policy,
            entities=lambda bound: EntityExtractor(bound, model=model, max_output_tokens=MAX_OUTPUT_TOKENS),
            relations=lambda bound: RelationExtractor(bound, model=model, max_output_tokens=MAX_OUTPUT_TOKENS),
            user_id=binding.user_id,
            guard=lambda: self._require_active(task_id),
            model=model,
        )
```

- [ ] **Step 9：改流水线与 worker 入口**

`src/backend/app/workers/persist_graph.py`：导入 `Callable`、`CredentialUnavailable`、`fail_for_credential`，并定义

```python
ToolkitSource = ExtractionToolkit | Callable[[Lease], ExtractionToolkit]
```

`run_pipeline_once` 的 `toolkit` 参数类型改为 `ToolkitSource`；`if stage == "extracting":` 分支改为：

```python
        if stage == "extracting":
            leased = replace(lease, stage=stage)
            try:
                resolved = toolkit if isinstance(toolkit, ExtractionToolkit) else toolkit(leased)
            except CredentialUnavailable as exc:
                extracted = fail_for_credential(url, leased, exc.reason)
            else:
                extracted = run_extract_stage(url, leased, toolkit=resolved,
                                              limits=ExtractLimits.from_settings(settings))
            stages.append(("extracting", extracted.status.value))
            stage = MERGE_STAGE if extracted.status is ExtractStatus.ADVANCED else ""
```

`src/backend/app/workers/runner.py`：删除本地 `MAX_OUTPUT_TOKENS` 定义，改为 `from app.workers.toolkits import MAX_OUTPUT_TOKENS, TaskToolkits`；`build_toolkit` 改为：

```python
def build_toolkit(settings: Settings) -> ToolkitSource:
    """``personal``：按任务快照逐个构建（ADR-080）；其余模式：进程内共用一份（live / demo / fake）。"""
    if settings.LLM_MODE == "personal":
        return TaskToolkits(settings).for_lease
    primary, fallback = build_model_clients(settings)
    model = model_id(settings, "extraction")
    policy = ModelCallPolicy.from_settings(
        settings, primary=primary, fallback=fallback, store=SqliteCallStore(settings.SQLITE_URL)
    )
    return ExtractionToolkit(
        policy=policy,
        entities=lambda client: EntityExtractor(client, model=model, max_output_tokens=MAX_OUTPUT_TOKENS),
        relations=lambda client: RelationExtractor(client, model=model, max_output_tokens=MAX_OUTPUT_TOKENS),
    )
```

新增维护钩子并接入 `build_maintenance`：

```python
class BindingScrub:
    """每轮把已结束任务的密钥快照置空（ADR-080 决定 3）；故障只记日志，不打断主循环。"""

    def __init__(self, sqlite_url: str) -> None:
        self._sqlite_url = sqlite_url

    def __call__(self) -> None:
        try:
            scrubbed = scrub_terminal_bindings(self._sqlite_url)
        except sqlite3.Error:
            LOG.exception("binding scrub failed; will retry next round")
            return
        if scrubbed:
            LOG.info("scrubbed %s finished task key snapshots", scrubbed)
```

`build_maintenance` 改为先收集钩子再返回：

```python
def build_maintenance(settings: Settings, repo: Neo4jRepository) -> tuple[Callable[[], object], ...]:
    hooks: list[Callable[[], object]] = []
    if settings.LLM_MODE == "personal":
        hooks.append(BindingScrub(settings.SQLITE_URL))
    if settings.PUBLISH_SWEEP_INTERVAL_SECONDS <= 0:
        LOG.info("publish sweep disabled (PUBLISH_SWEEP_INTERVAL_SECONDS=0)")
    else:
        hooks.append(PublishSweep(settings.SQLITE_URL, repo, settings.PUBLISH_SWEEP_INTERVAL_SECONDS))
    return tuple(hooks)
```

导入 `sqlite3`、`scrub_terminal_bindings`、`ToolkitSource`。

`src/backend/app/services/ai/factory.py`：`build_model_clients` 开头加：

```python
    if settings.LLM_MODE == "personal":
        raise RuntimeError("LLM_MODE=personal has no process-wide model client (ADR-080)")
```

- [ ] **Step 10：运行确认通过，并跑受影响的既有测试**

```bash
PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_l07.py tests/backend/test_l04.py -q -p no:cacheprovider
PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend -q -p no:cacheprovider
```

Expected: 全部通过。`test_g05_sweep_schedule.py` 若断言 `build_maintenance` 在间隔为 0 时返回 `()`，在非 `personal` 模式下仍成立。

- [ ] **Step 11：补一条抽取阶段用例（任务以凭据失败终止的线上形状）**

在 `tests/backend/test_e12.py` 末尾追加（复用该文件已有的 `_extracting`、`_toolkit`、`_run`、`_row`、`_call_rows`、`Script`），文件头导入加 `import dataclasses` 与 `from app.services.credentials import CredentialUnavailable`：

```python
# --- ADR-080：密钥快照失效 -----------------------------------------------------------------------
def test_revoked_credential_fails_the_task_before_any_model_call(db_url, storage):
    lease, _chunk_ids = _extracting(db_url, storage)

    def guard() -> None:
        raise CredentialUnavailable("credential_revoked")

    toolkit = dataclasses.replace(_toolkit(db_url, Script()), guard=guard)

    outcome = _run(db_url, lease, toolkit)

    assert outcome.status is ExtractStatus.FAILED and outcome.error_code == "LLM_UNAVAILABLE"
    row = _row(db_url, lease.task_id)
    assert row["stage"] == "failed" and row["lease_token"] is None
    assert json.loads(row["error_details"]) == {"reason": "credential_revoked"}
    assert "模型 API" in row["error_message"]
    assert _call_rows(db_url, lease.task_id) == []


def test_credential_revoked_mid_stage_stops_further_chunks(db_url, storage):
    lease, _chunk_ids = _extracting(db_url, storage)
    script = Script()
    allowed = {"left": 2}

    def guard() -> None:
        if allowed["left"] == 0:
            raise CredentialUnavailable("credential_revoked")
        allowed["left"] -= 1

    toolkit = dataclasses.replace(_toolkit(db_url, script), guard=guard)

    outcome = _run(db_url, lease, toolkit)

    assert outcome.status is ExtractStatus.FAILED
    assert json.loads(_row(db_url, lease.task_id)["error_details"]) == {"reason": "credential_revoked"}
    assert len(script.calls) == 2
```

Run: `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_e12.py tests/backend/test_l07.py -q -p no:cacheprovider`
Expected: 全部通过。若第二条用例里异常没有从线程池传回主线程（表现为 `INTERNAL_ERROR` 或用例挂起），读 `extract_task.py` 的 `_Dispatcher._settle`，在它取 `future.result()` 的位置让 `CredentialUnavailable` 原样上抛（不包成块失败），再重跑；把实际改动写入交接。

- [ ] **Step 12：门禁、交接、提交**

```bash
./scripts/verify.sh
git add src/backend/app/repositories/tasks.py src/backend/app/services/materials.py src/backend/app/api/materials.py \
        src/backend/app/services/ai/policy.py src/backend/app/services/ai/factory.py \
        src/backend/app/workers tests/backend/test_l07.py docs/tasks.md docs/handoffs/claude-l07.md
git commit -m "feat(backend): L07 上传绑定密钥快照，worker 按任务取模型

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8（L08）：问答按用户取模型与按用户预算

**Files:**
- Modify: `src/backend/app/repositories/model_calls.py:110-170`（`_day_billed` 与日预算检查）
- Modify: `src/backend/app/services/qa/rewrite.py`、`src/backend/app/services/qa/generate.py`（构造参数 `user_id`）
- Modify: `src/backend/app/services/qa/chat.py`
- Create: `src/backend/app/services/qa/user_models.py`
- Modify: `src/backend/app/api/chat.py:52-66,194-207`
- Test: `tests/backend/test_l08.py`

**Interfaces:**
- Consumes: Task 4、Task 5；Task 7 的 `CallAttribution.user_id`。
- Produces:
  - `SqliteCallStore.prewrite` 在 `record.user_id` 非空时日预算只统计该用户（列写入已在 Task 7 完成）。
  - `QueryRewriter(policy, *, model, user_id: str | None = None, ...)`、`AnswerGenerator(policy, *, model, user_id: str | None = None, ...)`。
  - `ChatService.with_models(rewriter, generator) -> ChatService`；`ChatFailure("MODEL_CONFIG_REQUIRED")` 的状态码为 409。
  - `UserChatModels(settings, *, cipher=None, store=None, transport=None, capacity=64)`，`.for_user(user_id) -> tuple[QueryRewriter, AnswerGenerator]`，未配置抛 `ModelConfigRequired`，密文不可解抛 `CredentialUnavailable("credential_unreadable")`。

- [ ] **Step 1：写失败测试**

```python
# tests/backend/test_l08.py
"""L08：问答按本人配置取模型；熔断、预算与调用记录按用户隔离（ADR-080 决定 4）。"""
from __future__ import annotations

import base64
import json
import uuid
from types import SimpleNamespace

import pytest

from app.config import load_settings
from app.repositories import model_configs as repo
from app.repositories.accounts import insert_account
from app.repositories.model_calls import BudgetRejected, CallRecord, SqliteCallStore
from app.repositories.sqlite import connect, migrate
from app.services.ai.client import Message, ModelAuthError, ModelRequest
from app.services.ai.policy import CallAttribution, ModelUnavailableError
from app.services.credentials import CredentialCipher, ModelConfigRequired
from app.services.qa.chat import ChatFailure
from app.services.qa.user_models import UserChatModels

VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
ROOT_KEY = bytes(range(32))
ROOT_KEY_B64 = base64.urlsafe_b64encode(ROOT_KEY).decode()


class Transport:
    """200 for every key except those listed in ``bad`` (401)."""

    def __init__(self, bad=()):
        self.bad, self.calls = set(bad), []

    def open(self, url, body, headers, timeout):
        key = headers["Authorization"].removeprefix("Bearer ")
        self.calls.append((url, key, json.loads(body)["model"]))
        status = 401 if key in self.bad else 200
        payload = json.dumps({"model": "m", "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                              "usage": {"prompt_tokens": 1, "completion_tokens": 1}}).encode()
        state = {"data": payload if status == 200 else b'{"error":{"message":"bad key"}}'}

        def read(amount, timeout):
            chunk, state["data"] = state["data"][:amount], state["data"][amount:]
            return chunk

        return SimpleNamespace(status=status, header=lambda name: None, read=read, close=lambda: None)


@pytest.fixture
def url(tmp_path):
    value = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(value)
    return value


def _settings(url, **extra):
    return load_settings({"SQLITE_URL": url, "LLM_MODE": "personal", "MODEL_CREDENTIAL_KEY": ROOT_KEY_B64,
                          "LLM_MAX_RETRIES": "0", "LLM_CIRCUIT_FAILURE_THRESHOLD": "1", **extra})


def _user(url, name):
    return insert_account(url, account_id=uuid.uuid4().hex, username=name, password_hash=VALID_HASH, role="student")


def _configure(url, user, *, base_url="https://a.example/v1", model, key):
    repo.save_config(url, user_id=user.id, base_url=base_url, model=model,
                     sealed=CredentialCipher(ROOT_KEY).seal(user.id, key), key_hint=key[-4:])


def _ask(models, user):
    """One chat-purpose call through the user's generator policy, attributed like a chat request."""
    _, generator = models.for_user(user.id)
    client = generator._policy.bind(CallAttribution(course_id="c1", request_id=uuid.uuid4().hex, user_id=user.id))
    return client.complete(ModelRequest(purpose="answer_with_context", model=generator._model,
                                        messages=(Message("user", "q"),), max_output_tokens=8))


def test_unconfigured_user_is_refused(url):
    alice = _user(url, "alice01")
    with pytest.raises(ModelConfigRequired):
        UserChatModels(_settings(url), transport=Transport()).for_user(alice.id)


def test_each_user_calls_with_own_key_and_model(url):
    alice, bob = _user(url, "alice01"), _user(url, "bob0001")
    _configure(url, alice, model="model-a", key="sk-alice-0001")
    _configure(url, bob, base_url="https://b.example/v1", model="model-b", key="sk-bob-0002")
    transport = Transport()
    models = UserChatModels(_settings(url), transport=transport)
    _ask(models, alice)
    _ask(models, bob)
    assert transport.calls == [
        ("https://a.example/v1/chat/completions", "sk-alice-0001", "model-a"),
        ("https://b.example/v1/chat/completions", "sk-bob-0002", "model-b"),
    ]
    with connect(url) as database:
        assert database.execute("SELECT user_id FROM model_calls ORDER BY rowid").fetchall() == [
            (alice.id,), (bob.id,)]


def test_one_users_bad_key_does_not_break_another(url):
    alice, bob = _user(url, "alice01"), _user(url, "bob0001")
    _configure(url, alice, model="m", key="sk-bad-0000")
    _configure(url, bob, model="m", key="sk-good-0001")
    models = UserChatModels(_settings(url), transport=Transport(bad={"sk-bad-0000"}))
    for _ in range(2):                            # 被供应商拒绝，或本人的熔断已打开——都只落在 alice 身上
        with pytest.raises((ModelAuthError, ModelUnavailableError)):
            _ask(models, alice)
    assert _ask(models, bob).text == "ok"        # bob 不受影响
    assert models.for_user(alice.id)[1]._policy is not models.for_user(bob.id)[1]._policy


def test_new_config_version_replaces_cached_models(url):
    alice = _user(url, "alice01")
    _configure(url, alice, model="old", key="sk-old-0001")
    transport = Transport()
    models = UserChatModels(_settings(url), transport=transport)
    first = models.for_user(alice.id)
    assert models.for_user(alice.id)[1] is first[1]
    _configure(url, alice, model="new", key="sk-new-0002")
    _ask(models, alice)
    assert transport.calls[-1][1:] == ("sk-new-0002", "new")
    repo.delete_config(url, alice.id)
    with pytest.raises(ModelConfigRequired):
        models.for_user(alice.id)


def test_cache_is_bounded(url):
    users = [_user(url, f"user{i:04d}") for i in range(3)]
    for user in users:
        _configure(url, user, model="m", key=f"sk-key-{user.username}")
    models = UserChatModels(_settings(url), transport=Transport(), capacity=2)
    for user in users:
        models.for_user(user.id)
    assert len(models) == 2


def _record(user_id, call_id=None):
    return CallRecord(call_id=call_id or uuid.uuid4().hex, course_id="c1", task_id=None, chunk_id=None,
                      request_id=uuid.uuid4().hex, purpose="answer_with_context", task_attempt=None,
                      chunk_attempt=None, call_seq=1, provider_role="primary", is_repair=False,
                      model_requested="m", input_tokens_est=60, max_output_tokens=60, user_id=user_id)


def test_daily_budget_is_per_user(url):
    store = SqliteCallStore(url)
    store.prewrite(_record("alice"), task_budget=10**6, daily_budget=100)   # billed estimate: 120
    with pytest.raises(BudgetRejected):
        store.prewrite(_record("alice"), task_budget=10**6, daily_budget=100)
    store.prewrite(_record("bob"), task_budget=10**6, daily_budget=100)       # bob has his own budget


def test_calls_without_user_keep_the_global_budget(url):
    store = SqliteCallStore(url)
    store.prewrite(_record(None), task_budget=10**6, daily_budget=100)
    with pytest.raises(BudgetRejected):
        store.prewrite(_record(None), task_budget=10**6, daily_budget=100)


def test_chat_failure_status_for_missing_config():
    failure = ChatFailure("MODEL_CONFIG_REQUIRED")
    assert failure.status_code == 409
    assert failure.body("r1")["code"] == "MODEL_CONFIG_REQUIRED"
```

- [ ] **Step 2：运行确认失败**

Run: `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_l08.py -q -p no:cacheprovider`
Expected: 收集错误（`app.services.qa.user_models` 不存在）。

- [ ] **Step 3：先读预算计费口径**

Run: `sed -n 1,60p src/backend/app/repositories/model_calls.py`
确认 `BILLED_TOKENS_SQL` 对 `sent` 行按 `input_tokens_est + max_output_tokens` 计。若口径不同，把 `test_daily_budget_is_per_user` 中的估算值调成「第一次写入后已用量 ≥ 100」，注释写明依据。

- [ ] **Step 4：按用户算日预算**

`src/backend/app/repositories/model_calls.py`：`_day_billed` 改为：

```python
def _day_billed(database: sqlite3.Connection, day: str | None, user_id: str | None = None) -> int:
    day_sql = _TODAY if day is None else "?"
    params: tuple[Any, ...] = () if day is None else (day, day)
    where = (f"created_at >= {_DAY_START.format(day=day_sql)}"
             f" AND created_at < {_DAY_END.format(day=day_sql)}")
    if user_id is not None:
        where += " AND user_id = ?"
        params += (user_id,)
    return _billed_where(database, where, params)
```

`prewrite` 中 `used = _day_billed(database, None)` 改为 `used = _day_billed(database, None, record.user_id)`。模块说明补一句：「`user_id` 非空（personal 模式）时日预算只统计该用户（ADR-080 决定 4）；为空时沿用全站合计」。

- [ ] **Step 5：改写器与生成器带用户**

`QueryRewriter.__init__` 与 `AnswerGenerator.__init__` 各加关键字参数 `user_id: str | None = None`，存为 `self._user_id`；两处 `CallAttribution(course_id=course_id, request_id=request_id)` 改为 `CallAttribution(course_id=course_id, request_id=request_id, user_id=self._user_id)`。执行时先 `grep -n "self\._policy\|self\._model" src/backend/app/services/qa/rewrite.py src/backend/app/services/qa/generate.py` 确认私有属性名确为 `_policy`、`_model`（测试用到），不同则改测试里的属性名。

- [ ] **Step 6：写按用户的模型注册表**

```python
# src/backend/app/services/qa/user_models.py
"""personal 模式：按「用户 + 配置版本」缓存问答改写器与生成器（ADR-080 决定 4）。

每个用户一份独立的 ``ModelCallPolicy``：熔断状态、调用归属与日预算都落在本人名下。
配置版本变化即重建；容量有界，最久未用的先淘汰。
"""

from __future__ import annotations

import threading
from collections import OrderedDict

from app.config import Settings
from app.repositories.model_calls import SqliteCallStore
from app.repositories.model_configs import get_config
from app.services.ai.compatible import CompatibleModelClient, HttpTransport
from app.services.ai.outbound import build_transport
from app.services.ai.policy import CallStore, ModelCallPolicy
from app.services.credentials import CredentialCipher, CredentialError, CredentialUnavailable, ModelConfigRequired
from app.services.qa.generate import AnswerGenerator
from app.services.qa.rewrite import QueryRewriter


class UserChatModels:
    def __init__(self, settings: Settings, *, cipher: CredentialCipher | None = None, store: CallStore | None = None,
                 transport: HttpTransport | None = None, capacity: int = 64) -> None:
        self._settings = settings
        self._cipher = cipher or CredentialCipher.from_settings(settings)
        self._store = store or SqliteCallStore(settings.SQLITE_URL)
        self._transport = transport or build_transport(settings)
        self._capacity = capacity
        self._cache: OrderedDict[str, tuple[int, QueryRewriter, AnswerGenerator]] = OrderedDict()
        self._mutex = threading.Lock()

    def __len__(self) -> int:
        return len(self._cache)

    def for_user(self, user_id: str) -> tuple[QueryRewriter, AnswerGenerator]:
        row = get_config(self._settings.SQLITE_URL, user_id)
        with self._mutex:
            if row is None:
                self._cache.pop(user_id, None)
                raise ModelConfigRequired()
            cached = self._cache.get(user_id)
            if cached is not None and cached[0] == row.version:
                self._cache.move_to_end(user_id)
                return cached[1], cached[2]
            try:
                api_key = self._cipher.open(user_id, row.sealed)
                client = CompatibleModelClient(row.base_url, api_key, transport=self._transport,
                                               default_timeout_seconds=self._settings.LLM_REQUEST_TIMEOUT_SECONDS)
            except (CredentialError, ValueError):
                raise CredentialUnavailable("credential_unreadable") from None
            policy = ModelCallPolicy.from_settings(self._settings, primary=client, store=self._store)
            pair = (QueryRewriter(policy, model=row.model, user_id=user_id),
                    AnswerGenerator(policy, model=row.model, user_id=user_id))
            self._cache[user_id] = (row.version, *pair)
            self._cache.move_to_end(user_id)
            while len(self._cache) > self._capacity:
                self._cache.popitem(last=False)
            return pair
```

- [ ] **Step 7：改问答服务与路由**

`src/backend/app/services/qa/chat.py`：`_MESSAGES` 加 `"MODEL_CONFIG_REQUIRED": "请先在「模型 API 设置」中保存你的模型 API 配置",`；`status_code` 的映射改为 `{"BUDGET_EXCEEDED": 429, "INTERNAL_ERROR": 500, "MODEL_CONFIG_REQUIRED": 409}`；`ChatService.__init__` 的 `rewriter`、`generator` 类型改为可空；加方法：

```python
    def with_models(self, rewriter: QueryRewriter, generator: AnswerGenerator) -> ChatService:
        """personal 模式：同一份检索依赖，换上当前用户的改写器与生成器。"""
        bound = copy.copy(self)
        bound.rewriter, bound.generator = rewriter, generator
        return bound
```

文件头加 `import copy`。

`src/backend/app/api/chat.py`：`chat_service` 保持签名与非 personal 行为不变，只把 personal 模式的基础服务建成不带模型的：

```python
def chat_service(request: Request) -> ChatService:
    service = getattr(request.app.state, "chat_service", None)
    if service is not None:
        return service
    settings = request.app.state.settings
    embedding = EmbeddingAdapter(settings, build_embedding_client(settings))
    repo = Neo4jRepository.from_settings(settings)
    if settings.LLM_MODE == "personal":
        service = ChatService(settings, repo, embedding, None, None)
    else:
        primary, fallback = build_model_clients(settings)
        policy = ModelCallPolicy.from_settings(
            settings, primary=primary, fallback=fallback, store=SqliteCallStore(settings.SQLITE_URL),
        )
        model = model_id(settings, "chat")
        service = ChatService(settings, repo, embedding,
                              QueryRewriter(policy, model=model), AnswerGenerator(policy, model=model))
    request.app.state.chat_service = service
    return service


def user_chat_service(request: Request, user_id: str) -> ChatService:
    """当前用户可用的问答服务；personal 模式下换上本人的模型（ADR-080 决定 4）。"""
    base = chat_service(request)
    settings = request.app.state.settings
    # 既有测试用只带 SQLITE_URL 的替身设置并替换 chat_service（test_j10）：缺属性按非 personal 处理。
    if getattr(settings, "LLM_MODE", "") != "personal":
        return base
    models = getattr(request.app.state, "user_chat_models", None)
    if models is None:
        models = UserChatModels(settings, transport=getattr(request.app.state, "model_transport", None))
        request.app.state.user_chat_models = models
    try:
        rewriter, generator = models.for_user(user_id)
    except ModelConfigRequired:
        raise ChatFailure("MODEL_CONFIG_REQUIRED") from None
    except CredentialUnavailable:
        raise ChatFailure("LLM_UNAVAILABLE", reason="auth") from None
    return base.with_models(rewriter, generator)
```

路由 `chat` 中 `service = chat_service(request)` 改为 `service = user_chat_service(request, access.user.id)`；该行已在 `try ... except ChatFailure as failure: return failed(failure)` 内，无需另加分支。`responses` 加 `409: {"model": Error}`。JSON 分支的状态码映射 `{"BUDGET_EXCEEDED": 429, "INTERNAL_ERROR": 500}` 不涉及 409（409 只在准备阶段返回）。导入 `UserChatModels`、`ModelConfigRequired`、`CredentialUnavailable`。

- [ ] **Step 8：运行确认通过，并跑问答既有测试**

```bash
PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_l08.py tests/backend/test_l07.py -q -p no:cacheprovider
PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend -q -p no:cacheprovider
```

Expected: 全部通过。既有测试若用位置参数构造 `CallRecord`，新字段有默认值不受影响。

- [ ] **Step 9：补接口级用例（未配置提问返回 409 且记入问答日志）**

在 `tests/backend/test_l08.py` 末尾追加（写法与 `tests/backend/test_j10.py` 的路由用例一致）：

```python
def test_chat_requires_model_config(url, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import chat as chat_api
    from app.api.dependencies import course_student
    from app.services.versions.resolver import PublishedVersion

    student = _user(url, "alice01")
    course_id, version_id = "c" * 32, "v" * 26
    with connect(url) as database:
        database.execute("INSERT INTO courses(id, name, teacher_id) VALUES (?, 'Course', ?)", (course_id, student.id))
        database.execute(
            "INSERT INTO graph_versions(version_id, course_id, kind, expires_at) VALUES (?, ?, 'publish', 1)",
            (version_id, course_id))
    version = PublishedVersion(course_id, version_id, 1, frozenset())
    monkeypatch.setattr(chat_api, "resolve_published", lambda *_: version)
    app = FastAPI()
    app.state.settings = _settings(url)
    app.state.chat_service = object()   # 基础服务不会被用到：未配置在取模型时就被拒绝
    app.include_router(chat_api.router)
    app.dependency_overrides[course_student] = lambda: SimpleNamespace(
        course=SimpleNamespace(id=course_id), user=SimpleNamespace(id=student.id))

    with TestClient(app) as client:
        response = client.post(f"/api/v1/courses/{course_id}/chat", json={"question": "什么是栈？"},
                               headers={"accept": "application/json"})

    assert response.status_code == 409
    assert response.json()["code"] == "MODEL_CONFIG_REQUIRED"
    with connect(url) as database:
        assert database.execute("SELECT outcome, error_code FROM chat_logs").fetchall() == [
            ("error", "MODEL_CONFIG_REQUIRED")]
        assert database.execute("SELECT count(*) FROM model_calls").fetchone() == (0,)
```

Run 同 Step 8，Expected: 通过。`courses`/`graph_versions` 的插入列若与当前迁移不符，按 `tests/backend/test_j10.py:33-43` 的现行写法对齐。

- [ ] **Step 10：门禁、交接、提交**

```bash
./scripts/verify.sh
git add src/backend/app/repositories/model_calls.py src/backend/app/services/ai/policy.py \
        src/backend/app/services/qa src/backend/app/api/chat.py tests/backend/test_l08.py \
        docs/tasks.md docs/handoffs/claude-l08.md
git commit -m "feat(backend): L08 问答按用户取模型，调用与预算归属用户

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9（L09）：在线向量、拒绝 `local`、正式启动入口

**Files:**
- Modify: `src/backend/app/config.py`
- Modify: `tests/backend/test_b06.py`、`tests/backend/test_e07.py`、`tests/backend/test_demo_mode.py`（只改涉及 `local` 的断言）
- Create: `scripts/check-embedding.py`
- Modify: `scripts/start-demo.sh`
- Create: `scripts/start.sh`
- Modify: `docs/runbook.md`
- Test: `tests/backend/test_l09.py`

**Interfaces:**
- Produces: `EMBEDDING_MODE=local` 使 `load_settings` 抛 `SettingsError`（信息含 `EMBEDDING_MODE`）；`scripts/start.sh [--no-open]`（等价于 `scripts/start-demo.sh --personal`）；`scripts/check-embedding.py`（退出码 0 表示返回了配置维度的向量）。

- [ ] **Step 1：写失败测试**

```python
# tests/backend/test_l09.py
"""L09：local 向量明确不支持（ADR-081）；personal 模式的启动约束。"""
import base64

import pytest

from app.config import SettingsError, load_settings

ROOT_KEY_B64 = base64.urlsafe_b64encode(bytes(range(32))).decode()


def test_local_embedding_is_rejected_with_a_clear_name():
    with pytest.raises(SettingsError, match="EMBEDDING_MODE"):
        load_settings({"EMBEDDING_MODE": "local", "EMBEDDING_MODEL": "bge-small-zh-v1.5"})


def test_personal_mode_does_not_need_global_llm_variables():
    settings = load_settings({"LLM_MODE": "personal", "MODEL_CREDENTIAL_KEY": ROOT_KEY_B64,
                              "EMBEDDING_MODE": "online", "EMBEDDING_BASE_URL": "https://e.example/v1",
                              "EMBEDDING_API_KEY": "k", "EMBEDDING_MODEL": "text-embedding-v4"})
    assert settings.LLM_BASE_URL == "" and settings.LLM_MODE == "personal"


def test_personal_mode_is_allowed_in_production_with_online_embedding():
    settings = load_settings({"APP_ENV": "production", "LLM_MODE": "personal", "MODEL_CREDENTIAL_KEY": ROOT_KEY_B64,
                              "EMBEDDING_MODE": "online", "EMBEDDING_BASE_URL": "https://e.example/v1",
                              "EMBEDDING_API_KEY": "k", "EMBEDDING_MODEL": "text-embedding-v4"})
    assert settings.APP_ENV == "production"
```

- [ ] **Step 2：运行确认失败**

Run: `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_l09.py -q -p no:cacheprovider`
Expected: 第一条 FAIL（`local` 目前通过校验），后两条通过。

- [ ] **Step 3：配置拒绝 `local`**

`src/backend/app/config.py` 的 `_check_rules` 中，把

```python
    elif settings.EMBEDDING_MODE == "local" and not _has_value(settings.EMBEDDING_MODEL):
        invalid.add("EMBEDDING_MODEL")
```

改为

```python
    elif settings.EMBEDDING_MODE == "local":
        # ADR-081：本版本未实现本地向量客户端；保留枚举值只为给出明确的拒绝，而不是在首次调用时失败。
        invalid.add("EMBEDDING_MODE")
```

- [ ] **Step 4：更新依赖旧行为的断言**

Run: `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_b06.py tests/backend/test_e07.py tests/backend/test_demo_mode.py tests/backend/test_l09.py -q -p no:cacheprovider`

对每个因 `local` 失败的既有用例：若它断言「`local` + 模型名可通过校验」，改为断言抛出含 `EMBEDDING_MODE` 的 `SettingsError`；若它用 `local` 只是为了得到某个向量空间标识，改用 `online` 加三项必填变量。不删除用例。把改动的用例名写入交接。

Expected: 全部通过。

- [ ] **Step 5：写向量联调检查脚本**

```python
# scripts/check-embedding.py
#!/usr/bin/env python3
"""用当前环境变量发 1 次真实向量请求，确认在线向量可用（L09）。只打印维度与耗时，不打印 key 与向量。

用法（仓库根目录，.env 已导出）：python3 scripts/check-embedding.py
退出码：0 成功；2 配置非法；3 调用失败。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))

from app.config import SettingsError, embedding_model_id, load_settings  # noqa: E402
from app.services.ai.client import EmbeddingRequest, ModelCallError  # noqa: E402
from app.services.ai.factory import build_embedding_client  # noqa: E402


def main() -> int:
    try:
        settings = load_settings()
    except SettingsError as error:
        print(error, file=sys.stderr)
        return 2
    if settings.EMBEDDING_MODE != "online":
        print(f"EMBEDDING_MODE={settings.EMBEDDING_MODE}，不是 online，未发请求", file=sys.stderr)
        return 2
    client = build_embedding_client(settings)
    started = time.monotonic()
    try:
        result = client.embed(EmbeddingRequest(model=embedding_model_id(settings), texts=("栈是后进先出的线性表",),
                                               dimensions=settings.EMBEDDING_DIMENSIONS))
    except ModelCallError as error:
        print(f"向量调用失败：{error.error_class.value}", file=sys.stderr)
        return 3
    print(f"ok model={result.model_responded or result.model_requested} "
          f"dimensions={len(result.vectors[0])} seconds={time.monotonic() - started:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

执行前 `grep -n "class EmbeddingRequest" -A12 src/backend/app/services/ai/client.py` 核对字段名（`model`、`texts`、`dimensions`），不同则按实际字段改脚本。

- [ ] **Step 6：启动脚本加 `--personal` 与正式入口**

`scripts/start-demo.sh`：
1. 用法注释加一行 `#   --personal   正式模式：LLM_MODE=personal（个人模型 API，ADR-080）+ 在线向量；不导入演示课程`。
2. 参数解析加 `personal=0` 与分支 `--personal) personal=1 ;;`；`((personal)) && do_import=0`；`--live` 与 `--personal` 同时给出时 `die "--live 与 --personal 不能同时使用"`。
3. 在 `.env` 存在分支之后，加根密钥的自动补齐（与 `AUTH_JWT_SECRET` 的补齐方式相同）：

```bash
if ((personal)) && [[ -z "$(env_setting MODEL_CREDENTIAL_KEY "")" ]]; then
  step ".env 的 MODEL_CREDENTIAL_KEY 为空，写入随机值（更换它会使已保存的个人模型配置失效）"
  "$PY" - <<'PY'
import base64, re, secrets
from pathlib import Path
path = Path(".env")
text = path.read_text(encoding="utf-8")
line = "MODEL_CREDENTIAL_KEY=" + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
text, n = re.subn(r"^MODEL_CREDENTIAL_KEY=.*$", line, text, count=1, flags=re.M)
if n == 0:
    text = text.rstrip("\n") + "\n" + line + "\n"
path.write_text(text, encoding="utf-8")
PY
fi
```

4. 模式分支在 `if ((live)); then … else … fi` 之前加一支：

```bash
if ((personal)); then
  [[ "${EMBEDDING_MODE:-}" == online ]] || die "--personal 需要在 .env 设 EMBEDDING_MODE=online 并填写 EMBEDDING_BASE_URL、EMBEDDING_API_KEY、EMBEDDING_MODEL（ADR-081）。"
  for key in EMBEDDING_BASE_URL EMBEDDING_API_KEY EMBEDDING_MODEL MODEL_CREDENTIAL_KEY; do
    [[ -n ${!key:-} ]] || die "--personal 需要在 .env 填写 ${key}。"
  done
  export LLM_MODE=personal APP_ENV=development
  if [[ -z ${SSL_CERT_FILE:-} && $(uname -s) == Darwin ]]; then
    (cd /tmp && "$PY" -c 'import certifi' 2>/dev/null) || "$PY" -m pip install -q certifi
    SSL_CERT_FILE="$(cd /tmp && "$PY" -c 'import certifi; print(certifi.where())')" || die "取不到 certifi 根证书，手动 export SSL_CERT_FILE 后重试。"
    export SSL_CERT_FILE
  fi
elif ((live)); then
```

（原来的 `if ((live)); then` 改成上面的 `elif`。）
5. 结尾的启动提示按模式区分：`personal` 时输出「✓ 正式模式已启动：$WEB_URL；教师与学生登录后先在『模型 API 设置』保存自己的模型 API」，不再输出「演示环境」字样。

`scripts/start.sh`：

```bash
#!/usr/bin/env bash
# 正式入口：个人模型 API（LLM_MODE=personal，ADR-080）+ 在线向量（ADR-081）。
# 演示入口见 scripts/start-demo.sh（不联网的演示模型）。用法：scripts/start.sh [--no-open]
set -euo pipefail
exec "$(dirname "$0")/start-demo.sh" --personal "$@"
```

`chmod +x scripts/start.sh scripts/check-embedding.py`。

- [ ] **Step 7：真实向量联调（需要 `EMBEDDING_API_KEY`）**

```bash
set -a; . <(grep -E '^[A-Z_][A-Z0-9_]*=' .env); set +a
.venv/bin/python scripts/check-embedding.py
```

Expected: `ok model=… dimensions=1024 seconds=…`，退出码 0。失败时按错误分类排查（`auth`：key；`invalid_request`：地址路径或 `dimensions` 参数），只改 `.env`，把最终可用的地址写入 `docs/integrations.md` 与规格第 11 节。未填 key 时本步跳过并在交接标记未验证。

- [ ] **Step 8：正式入口冒烟**

```bash
scripts/start.sh --no-open
```

另一终端：`curl -s http://127.0.0.1:8001/health` 返回 `{"status":"ok",…}`；`tail -n 5 .demo/logs/worker.log` 无 `Invalid configuration`。然后 Ctrl-C 停止。

- [ ] **Step 9：更新运行手册**

`docs/runbook.md`：新增「正式模式」一节（`scripts/start.sh`、所需变量、根密钥说明、向量检查命令）；删除或改正所有「`local` 可用」的表述；把 `start-demo.sh` 明确标为演示入口。

- [ ] **Step 10：门禁、交接、提交**

```bash
./scripts/verify.sh
git add src/backend/app/config.py tests/backend scripts/start.sh scripts/start-demo.sh scripts/check-embedding.py \
        docs/runbook.md docs/integrations.md docs/tasks.md docs/handoffs/claude-l09.md
git commit -m "feat: L09 在线向量联调、拒绝 local 向量、正式启动入口

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10（L10）：前端设置页、未配置引导、模式标识

**Files:**
- Create: `src/frontend/src/api/modelConfig.ts`
- Create: `src/frontend/src/stores/runtime.ts`
- Create: `src/frontend/src/composables/useModelConfig.ts`
- Create: `src/frontend/src/views/ModelSettingsView.vue`
- Modify: `src/frontend/src/router/index.ts`、`src/frontend/src/main.ts`、`src/frontend/src/App.vue`
- Modify: `src/frontend/src/views/MaterialsView.vue`、`src/frontend/src/composables/useMaterials.ts`
- Modify: `src/frontend/src/views/ChatView.vue`、`src/frontend/src/composables/useChat.ts`
- Test: `tests/frontend/l10.test.ts`

**Interfaces:**
- Consumes: 契约类型 `components['schemas']['ModelConfig' | 'ModelConfigUpdate' | 'ModelConfigTestRequest' | 'ModelConfigTestResult']`。
- Produces:
  - `ModelConfigApi { get(control?), save(body, control?), clear(control?), test(body?, control?) }`、`MODEL_CONFIG_API_KEY`、`createModelConfigApi(client)`。
  - `useRuntimeStore()`：`runtimeMode`、`configured`、`needsConfig`、`isDemo`、`apply(config)`、`reset()`。
  - `SETTINGS_ROUTE = 'model-settings'`，路径 `/settings/model`；`AppRouterOptions.settingsComponent`。

- [ ] **Step 1：写失败测试**

```ts
// tests/frontend/l10.test.ts
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import { ApiError } from '../../src/frontend/src/api/http'
import { MODEL_CONFIG_API_KEY, type ModelConfigApi } from '../../src/frontend/src/api/modelConfig'
import { createAppRouter, SETTINGS_ROUTE } from '../../src/frontend/src/router/index.ts'
import { useRuntimeStore } from '../../src/frontend/src/stores/runtime'
import { useSessionStore } from '../../src/frontend/src/stores/session'
import ModelSettingsView from '../../src/frontend/src/views/ModelSettingsView.vue'

type ModelConfig = components['schemas']['ModelConfig']
const KEY = 'sk-live-AAAABBBBCCCC1234'
const SAVED: ModelConfig = {
  runtime_mode: 'personal', configured: true, base_url: 'https://api.example.com/v1', model: 'm1',
  key_hint: '1234', version: 1, updated_at: '2026-10-03T00:00:00Z',
}
const EMPTY: ModelConfig = { runtime_mode: 'personal', configured: false }

function fakeApi(initial: ModelConfig, overrides: Partial<ModelConfigApi> = {}) {
  return {
    get: vi.fn<ModelConfigApi['get']>(overrides.get ?? (async () => initial)),
    save: vi.fn<ModelConfigApi['save']>(overrides.save ?? (async (body) => ({ ...SAVED, base_url: body.base_url, model: body.model }))),
    clear: vi.fn<ModelConfigApi['clear']>(overrides.clear ?? (async () => undefined)),
    test: vi.fn<ModelConfigApi['test']>(overrides.test ?? (async () => ({ ok: true, latency_ms: 321 }))),
  }
}

let pinia: Pinia
beforeEach(() => {
  sessionStorage.clear()
  localStorage.clear()
  pinia = createPinia()
  setActivePinia(pinia)
  useSessionStore().signIn({ access_token: 't', token_type: 'bearer', expires_in: 3600,
    user: { id: 'u1', username: 'alice', role: 'student' } } as never)
})

async function mountView(api: ReturnType<typeof fakeApi>) {
  const router = createAppRouter({ history: createMemoryHistory(), getAccountRole: () => 'student', settingsComponent: ModelSettingsView })
  await router.push({ name: SETTINGS_ROUTE })
  const wrapper = mount(ModelSettingsView, { global: { plugins: [pinia, router], provide: { [MODEL_CONFIG_API_KEY as symbol]: api } } })
  await flushPromises()
  return wrapper
}

describe('L10 模型 API 设置页', () => {
  it('未配置时提示并要求三项', async () => {
    const api = fakeApi(EMPTY)
    const wrapper = await mountView(api)
    expect(wrapper.find('[data-test="mc-status"]').text()).toContain('尚未配置')
    await wrapper.find('[data-test="mc-form"]').trigger('submit')
    expect(api.save).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="mc-error"]').text()).toContain('请填写')
    expect(useRuntimeStore().needsConfig).toBe(true)
  })

  it('保存后只显示脱敏状态，输入框清空，浏览器存储里没有密钥', async () => {
    const api = fakeApi(EMPTY)
    const wrapper = await mountView(api)
    await wrapper.find('[data-test="mc-base-url"]').setValue('https://api.example.com/v1')
    await wrapper.find('[data-test="mc-model"]').setValue('m1')
    await wrapper.find('[data-test="mc-api-key"]').setValue(KEY)
    await wrapper.find('[data-test="mc-form"]').trigger('submit')
    await flushPromises()
    expect(api.save).toHaveBeenCalledWith({ base_url: 'https://api.example.com/v1', model: 'm1', api_key: KEY }, expect.anything())
    expect(wrapper.find('[data-test="mc-status"]').text()).toContain('••••1234')
    expect((wrapper.find('[data-test="mc-api-key"]').element as HTMLInputElement).value).toBe('')
    expect(wrapper.html()).not.toContain(KEY)
    expect(JSON.stringify({ ...sessionStorage, ...localStorage })).not.toContain(KEY)
    expect(useRuntimeStore().needsConfig).toBe(false)
  })

  it('只改模型名可不填密钥；改地址必须重填', async () => {
    const api = fakeApi(SAVED)
    const wrapper = await mountView(api)
    await wrapper.find('[data-test="mc-model"]').setValue('m2')
    await wrapper.find('[data-test="mc-form"]').trigger('submit')
    await flushPromises()
    expect(api.save).toHaveBeenLastCalledWith({ base_url: 'https://api.example.com/v1', model: 'm2' }, expect.anything())
    await wrapper.find('[data-test="mc-base-url"]').setValue('https://other.example.com/v1')
    await wrapper.find('[data-test="mc-form"]').trigger('submit')
    await flushPromises()
    expect(api.save).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[data-test="mc-error"]').text()).toContain('重新填写密钥')
  })

  it('地址被拒时给出对应文案，不回显服务端 message', async () => {
    const api = fakeApi(EMPTY, {
      save: async () => { throw new ApiError(422, { code: 'VALIDATION_ERROR', message: '服务端原文', details: { fields: [{ in: 'body', field: 'base_url', reason: 'private_address' }] } }) },
    })
    const wrapper = await mountView(api)
    await wrapper.find('[data-test="mc-base-url"]').setValue('https://intranet.example.com/v1')
    await wrapper.find('[data-test="mc-model"]').setValue('m1')
    await wrapper.find('[data-test="mc-api-key"]').setValue(KEY)
    await wrapper.find('[data-test="mc-form"]').trigger('submit')
    await flushPromises()
    const text = wrapper.find('[data-test="mc-error"]').text()
    expect(text).toContain('内网')
    expect(text).not.toContain('服务端原文')
  })

  it('测试连接显示成败与分类', async () => {
    const api = fakeApi(SAVED, { test: async () => ({ ok: false, latency_ms: 80, error_class: 'auth' }) })
    const wrapper = await mountView(api)
    await wrapper.find('[data-test="mc-test"]').trigger('click')
    await flushPromises()
    expect(api.test).toHaveBeenCalledWith(undefined, expect.anything())
    expect(wrapper.find('[data-test="mc-test-result"]').text()).toContain('密钥被拒绝')
  })

  it('清除后回到未配置', async () => {
    const api = fakeApi(SAVED)
    const wrapper = await mountView(api)
    await wrapper.find('[data-test="mc-clear"]').trigger('click')
    await wrapper.find('[data-test="mc-clear-confirm"]').trigger('click')
    await flushPromises()
    expect(api.clear).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[data-test="mc-status"]').text()).toContain('尚未配置')
    expect(useRuntimeStore().needsConfig).toBe(true)
  })

  it('演示模式下说明个人配置不生效', async () => {
    const wrapper = await mountView(fakeApi({ runtime_mode: 'demo', configured: false }))
    expect(wrapper.find('[data-test="mc-demo"]').text()).toContain('演示模式')
    expect(useRuntimeStore().isDemo).toBe(true)
    expect(useRuntimeStore().needsConfig).toBe(false)
  })
})
```

`signIn` 的入参形状以 `src/frontend/src/stores/session.ts` 的实际签名为准，执行时核对并去掉 `as never`。

- [ ] **Step 2：运行确认失败**

Run: `npm run test --prefix src/frontend -- --run l10.test.ts`
Expected: FAIL（模块不存在）。

- [ ] **Step 3：写接口模块与运行状态仓库**

```ts
// src/frontend/src/api/modelConfig.ts
import type { InjectionKey } from 'vue'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import type { HttpClient, RequestControl } from './http'

/**
 * 当前用户的个人模型 API 配置（L10，ADR-080）：只封装契约的四个操作。
 * 响应永不含密钥；请求里的 `api_key` 只在保存与测试时出现一次，本模块与调用方都不缓存它。
 */

export type ModelConfig = components['schemas']['ModelConfig']
export type ModelConfigUpdate = components['schemas']['ModelConfigUpdate']
export type ModelConfigTestRequest = components['schemas']['ModelConfigTestRequest']
export type ModelConfigTestResult = components['schemas']['ModelConfigTestResult']

export interface ModelConfigApi {
  get(control?: RequestControl): Promise<ModelConfig>
  save(body: ModelConfigUpdate, control?: RequestControl): Promise<ModelConfig>
  clear(control?: RequestControl): Promise<void>
  /** 不带 `body` 测试已保存的配置；带则测试这组值而不保存 */
  test(body?: ModelConfigTestRequest, control?: RequestControl): Promise<ModelConfigTestResult>
}

export const MODEL_CONFIG_API_KEY: InjectionKey<ModelConfigApi> = Symbol('smartsketch.model-config-api')

export function createModelConfigApi(client: HttpClient): ModelConfigApi {
  return {
    get: (control = {}) => client.request('get', '/api/v1/me/model-config', { ...control }),
    save: (body, control = {}) => client.request('put', '/api/v1/me/model-config', { ...control, body }),
    clear: async (control = {}) => {
      await client.request('delete', '/api/v1/me/model-config', { ...control })
    },
    test: (body, control = {}) =>
      client.request('post', '/api/v1/me/model-config/test', body === undefined ? { ...control } : { ...control, body }),
  }
}
```

```ts
// src/frontend/src/stores/runtime.ts
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { ModelConfig } from '../api/modelConfig'

/**
 * 服务端运行模式与「本人是否已配置模型 API」（L10）。只存非敏感状态，不持久化，不含地址、模型名与密钥。
 * 上传页与问答页据 `needsConfig` 显示引导；外壳据 `isDemo` 显示演示标识。
 */
export const useRuntimeStore = defineStore('runtime', () => {
  const runtimeMode = ref<ModelConfig['runtime_mode'] | null>(null)
  const configured = ref<boolean | null>(null)

  const needsConfig = computed(() => runtimeMode.value === 'personal' && configured.value === false)
  const isDemo = computed(() => runtimeMode.value === 'demo' || runtimeMode.value === 'fake')

  function apply(config: ModelConfig): void {
    runtimeMode.value = config.runtime_mode
    configured.value = config.configured
  }

  function reset(): void {
    runtimeMode.value = null
    configured.value = null
  }

  return { runtimeMode, configured, needsConfig, isDemo, apply, reset }
})
```

- [ ] **Step 4：写组合式逻辑**

```ts
// src/frontend/src/composables/useModelConfig.ts
import { computed, onScopeDispose, reactive, ref } from 'vue'
import { AbortedError, ApiError, NetworkError, TimeoutError } from '../api/http'
import type { ModelConfig, ModelConfigApi, ModelConfigTestResult } from '../api/modelConfig'
import { useRuntimeStore } from '../stores/runtime'

/**
 * 模型 API 设置页的状态（L10）。
 * - 密钥只存在于表单的 `apiKey` 里，保存或测试成功后立即清空；不写入任何存储。
 * - 错误只按错误码与 `details.fields[].reason` 给固定文案，不回显服务端 message。
 */

const URL_REASON: Record<string, string> = {
  scheme: '地址必须以 https:// 开头。',
  credentials: '地址里不能包含用户名或密码。',
  query: '地址里不能包含 ? 或 # 之后的内容。',
  host: '地址缺少主机名。',
  port: '地址的端口不合法。',
  unresolvable: '无法解析该地址的域名，请检查拼写。',
  private_address: '该地址指向内网或本机，出于安全原因不允许。',
}
const KEY_REASON: Record<string, string> = {
  required_when_endpoint_changes: '首次保存或修改地址时需要重新填写密钥。',
  invalid_characters: '密钥只能包含可见的英文字符，不能有空格。',
}
const TEST_TEXT: Record<string, string> = {
  auth: '密钥被拒绝，请检查密钥是否正确、是否有余额。',
  timeout: '连接超时，请检查地址或稍后重试。',
  rate_limited: '供应商限流，请稍后重试。',
  connection: '无法连接到该地址。',
  invalid_request: '供应商不接受这个请求，请检查模型名称。',
  server: '供应商服务出错，请稍后重试。',
  malformed_response: '该地址的响应不是兼容的对话接口格式。',
  stream_interrupted: '连接中断，请重试。',
  blocked_address: '该地址指向内网或本机，或不是 https 地址。',
}

function fieldReason(cause: unknown): { field: string; reason: string } | null {
  if (!(cause instanceof ApiError) || cause.code !== 'VALIDATION_ERROR') return null
  const fields = cause.details?.fields
  if (!Array.isArray(fields) || fields.length === 0) return null
  const first = fields[0] as { field?: unknown; reason?: unknown }
  return typeof first.field === 'string' && typeof first.reason === 'string' ? { field: first.field, reason: first.reason } : null
}

function failureText(cause: unknown, fallback: string): string {
  const hit = fieldReason(cause)
  if (hit?.field === 'base_url') return URL_REASON[hit.reason] ?? '地址不符合要求。'
  if (hit?.field === 'api_key') return KEY_REASON[hit.reason] ?? '密钥不符合要求。'
  if (hit !== null) return '请检查填写的内容。'
  if (cause instanceof ApiError && cause.code === 'RATE_LIMITED') return '操作过于频繁，请稍后再试。'
  if (cause instanceof ApiError && cause.code === 'MODEL_CONFIG_REQUIRED') return '请先保存配置再测试。'
  if (cause instanceof ApiError && cause.code === 'STORAGE_UNAVAILABLE') return '服务端未启用个人模型凭据存储，请联系部署者。'
  if (cause instanceof ApiError && cause.status === 401) return '登录已失效，请重新登录。'
  if (cause instanceof NetworkError || cause instanceof TimeoutError) return '无法连接服务器，请检查网络后重试。'
  return fallback
}

export function useModelConfig({ api }: { api: ModelConfigApi }) {
  const runtime = useRuntimeStore()
  const controller = new AbortController()
  onScopeDispose(() => controller.abort())

  const status = ref<'loading' | 'ready' | 'error'>('loading')
  const saved = ref<ModelConfig | null>(null)
  const form = reactive({ baseUrl: '', model: '', apiKey: '' })
  const saving = ref(false)
  const testing = ref(false)
  const clearing = ref(false)
  const error = ref<string | null>(null)
  const notice = ref<string | null>(null)
  const testResult = ref<{ ok: boolean; text: string } | null>(null)

  const configured = computed(() => saved.value?.configured === true)
  /** 首次保存或地址与已存值不同：必须填密钥（与后端规则一致，避免已存密钥被改送到新主机） */
  const keyRequired = computed(() => !configured.value || form.baseUrl.trim() !== saved.value?.base_url)

  function adopt(config: ModelConfig): void {
    saved.value = config
    runtime.apply(config)
    form.baseUrl = config.base_url ?? ''
    form.model = config.model ?? ''
    form.apiKey = ''
  }

  async function load(): Promise<void> {
    status.value = 'loading'
    try {
      adopt(await api.get({ signal: controller.signal }))
      status.value = 'ready'
    } catch (cause) {
      if (cause instanceof AbortedError) return
      error.value = failureText(cause, '配置加载失败，请稍后重试。')
      status.value = 'error'
    }
  }

  async function save(): Promise<void> {
    if (saving.value) return
    error.value = notice.value = null
    const baseUrl = form.baseUrl.trim()
    const model = form.model.trim()
    if (baseUrl === '' || model === '') {
      error.value = '请填写服务地址和模型名称。'
      return
    }
    if (keyRequired.value && form.apiKey === '') {
      error.value = configured.value ? '修改地址时需要重新填写密钥。' : '请填写密钥。'
      return
    }
    saving.value = true
    try {
      const body = form.apiKey === '' ? { base_url: baseUrl, model } : { base_url: baseUrl, model, api_key: form.apiKey }
      adopt(await api.save(body, { signal: controller.signal }))
      testResult.value = null
      notice.value = '已保存。已创建的任务仍使用保存前的配置。'
    } catch (cause) {
      if (cause instanceof AbortedError) return
      error.value = failureText(cause, '保存失败，请稍后重试。')
    } finally {
      saving.value = false
    }
  }

  async function test(): Promise<void> {
    if (testing.value) return
    error.value = null
    testResult.value = null
    const usesForm = form.apiKey !== ''
    if (!usesForm && !configured.value) {
      error.value = '请先填写密钥，或保存配置后再测试。'
      return
    }
    testing.value = true
    try {
      const body = usesForm ? { base_url: form.baseUrl.trim(), model: form.model.trim(), api_key: form.apiKey } : undefined
      const result: ModelConfigTestResult = await api.test(body, { signal: controller.signal, timeoutMs: 30_000 })
      testResult.value = result.ok
        ? { ok: true, text: `连接成功（${result.latency_ms} 毫秒）。` }
        : { ok: false, text: TEST_TEXT[result.error_class ?? ''] ?? '连接失败。' }
    } catch (cause) {
      if (cause instanceof AbortedError) return
      error.value = failureText(cause, '测试失败，请稍后重试。')
    } finally {
      testing.value = false
    }
  }

  async function clear(): Promise<void> {
    if (clearing.value) return
    error.value = notice.value = null
    clearing.value = true
    try {
      await api.clear({ signal: controller.signal })
      adopt({ runtime_mode: saved.value?.runtime_mode ?? 'personal', configured: false })
      testResult.value = null
      notice.value = '已清除。尚未结束的任务会终止，需要重新上传。'
    } catch (cause) {
      if (cause instanceof AbortedError) return
      error.value = failureText(cause, '清除失败，请稍后重试。')
    } finally {
      clearing.value = false
    }
  }

  void load()
  return { status, saved, form, configured, keyRequired, saving, testing, clearing, error, notice, testResult, load, save, test, clear }
}
```

- [ ] **Step 5：写页面**

```vue
<!-- src/frontend/src/views/ModelSettingsView.vue -->
<script setup lang="ts">
import { inject, ref } from 'vue'
import { MODEL_CONFIG_API_KEY } from '../api/modelConfig'
import { useModelConfig } from '../composables/useModelConfig'
import { useRuntimeStore } from '../stores/runtime'

const api = inject(MODEL_CONFIG_API_KEY, null)
if (api === null) throw new Error('ModelSettingsView 需要注入 MODEL_CONFIG_API_KEY')

const runtime = useRuntimeStore()
const { status, saved, form, configured, keyRequired, saving, testing, clearing, error, notice, testResult, load, save, test, clear } =
  useModelConfig({ api })
const confirmingClear = ref(false)

async function confirmClear(): Promise<void> {
  confirmingClear.value = false
  await clear()
}
</script>

<template>
  <section class="model-settings" data-test="model-settings" aria-labelledby="mc-title">
    <h2 id="mc-title">模型 API 设置</h2>
    <p class="model-settings__lead">
      教师生成知识图谱、学生提问都使用你自己填写的模型 API。密钥加密保存在服务端，保存后不再显示，也不会提供给其他用户。
      目前支持 OpenAI 兼容的对话接口（已验证：DeepSeek）。
    </p>

    <p v-if="runtime.isDemo" class="model-settings__demo" data-test="mc-demo" role="status">
      当前为演示模式：系统使用内置的演示模型，个人配置不生效。
    </p>

    <p v-if="status === 'loading'" data-test="mc-loading" role="status">正在加载配置…</p>
    <div v-else-if="status === 'error'">
      <p data-test="mc-error" role="alert">{{ error }}</p>
      <button type="button" data-test="mc-retry" @click="load">重试</button>
    </div>
    <template v-else>
      <p class="model-settings__status" data-test="mc-status">
        <template v-if="configured">
          已配置：{{ saved?.model }} · 密钥 ••••{{ saved?.key_hint }}
          <span v-if="saved?.last_test"> · 最近测试{{ saved.last_test.ok ? '成功' : '失败' }}</span>
        </template>
        <template v-else>尚未配置。保存后才能上传资料生成图谱或提问。</template>
      </p>

      <form class="model-settings__form" data-test="mc-form" novalidate @submit.prevent="save">
        <label for="mc-base-url">服务地址</label>
        <input id="mc-base-url" v-model="form.baseUrl" data-test="mc-base-url" type="url" inputmode="url"
               placeholder="https://api.deepseek.com" autocomplete="off" spellcheck="false" />

        <label for="mc-model">模型名称</label>
        <input id="mc-model" v-model="form.model" data-test="mc-model" type="text" placeholder="deepseek-flash"
               autocomplete="off" spellcheck="false" />

        <label for="mc-api-key">密钥{{ keyRequired ? '' : '（不改可留空）' }}</label>
        <input id="mc-api-key" v-model="form.apiKey" data-test="mc-api-key" type="password"
               autocomplete="off" spellcheck="false" :aria-required="keyRequired" />

        <p v-if="error" data-test="mc-error" role="alert">{{ error }}</p>
        <p v-if="notice" data-test="mc-notice" role="status">{{ notice }}</p>
        <p v-if="testResult" data-test="mc-test-result" :class="testResult.ok ? 'is-ok' : 'is-bad'" role="status">
          {{ testResult.text }}
        </p>

        <div class="model-settings__actions">
          <button type="submit" data-test="mc-save" :disabled="saving">{{ saving ? '正在保存…' : '保存' }}</button>
          <button type="button" data-test="mc-test" :disabled="testing" @click="test">
            {{ testing ? '正在测试…' : '测试连接' }}
          </button>
          <button v-if="configured && !confirmingClear" type="button" data-test="mc-clear" :disabled="clearing"
                  @click="confirmingClear = true">清除配置</button>
        </div>
        <p class="model-settings__hint">测试连接会向你的服务发送一次极小的请求（输出 1 个 token），费用可忽略。</p>

        <div v-if="confirmingClear" class="model-settings__confirm" role="alertdialog" aria-labelledby="mc-clear-title">
          <p id="mc-clear-title">清除后，你尚未结束的图谱生成任务会终止，需要重新上传。确定清除？</p>
          <button type="button" data-test="mc-clear-confirm" @click="confirmClear">确定清除</button>
          <button type="button" data-test="mc-clear-cancel" @click="confirmingClear = false">取消</button>
        </div>
      </form>
    </template>
  </section>
</template>

<style scoped>
.model-settings { max-width: 40rem; }
.model-settings__lead, .model-settings__hint { color: var(--color-text-muted, #5b6472); }
.model-settings__demo { padding: 0.5rem 0.75rem; border-left: 3px solid var(--color-warning, #b7791f); }
.model-settings__form { display: grid; gap: 0.5rem; margin-top: 1rem; }
.model-settings__form input { padding: 0.5rem; font: inherit; }
.model-settings__actions { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem; }
.is-ok { color: var(--color-success, #276749); }
.is-bad { color: var(--color-danger, #c53030); }
</style>
```

执行时先 `grep -n "^  --color" src/frontend/src/styles.css | head -30`，把上面的变量名换成项目里实际存在的设计令牌；没有对应令牌的保留回退色。

- [ ] **Step 6：接入路由、启动与外壳**

`src/frontend/src/router/index.ts`：加

```ts
/** 个人模型 API 设置页（L10，ADR-080）；任一已登录账号可进入 */
export const SETTINGS_ROUTE = 'model-settings'
```

`AppRouterOptions` 加 `settingsComponent?: Component`（注释「个人模型 API 设置页（L10）。注入后注册 `/settings/model`」），解构参数加 `settingsComponent`，在注册 `chatComponent` 的那一行之后加：

```ts
  if (settingsComponent) {
    routes.push({ path: '/settings/model', name: SETTINGS_ROUTE, component: settingsComponent, meta: { anyAccountRole: true } })
  }
```

`src/frontend/src/main.ts`：导入 `createModelConfigApi, MODEL_CONFIG_API_KEY` 与 `ModelSettingsView`；`createAppRouter` 选项加 `settingsComponent: ModelSettingsView,`；`.provide(MODEL_CONFIG_API_KEY, createModelConfigApi(http))`。

`src/frontend/src/App.vue`：
1. 导入 `SETTINGS_ROUTE`、`MODEL_CONFIG_API_KEY`、`useRuntimeStore`。
2. 脚本中加：

```ts
const modelConfigApi = inject(MODEL_CONFIG_API_KEY, null)
const runtime = getActivePinia() ? useRuntimeStore() : null
// 登录后读取一次运行模式与配置状态；失败不阻断外壳（各页面自有错误态）
watch(role, async (value) => {
  if (value === null) { runtime?.reset(); return }
  if (modelConfigApi === null || runtime === null) return
  try { runtime.apply(await modelConfigApi.get()) } catch { /* 忽略：设置页会显示错误 */ }
}, { immediate: true })
const settingsLink = computed<RouteLocationRaw | null>(() =>
  router !== null && router.hasRoute(SETTINGS_ROUTE) ? { name: SETTINGS_ROUTE } : null)
```

3. 侧栏模板中，在退出按钮之前加：

```html
<RouterLink v-if="settingsLink" :to="settingsLink" class="app-nav__link" data-test="nav-model-settings">
  模型 API 设置<span v-if="runtime?.needsConfig" class="app-nav__dot" aria-label="尚未配置">●</span>
</RouterLink>
<p v-if="runtime?.isDemo" class="app-mode" data-test="mode-demo" role="status">演示模式 · 使用内置演示模型</p>
```

类名以侧栏既有导航项的类名为准（执行时读 `App.vue` 模板 110 行之后的侧栏部分，沿用同一类名）。

- [ ] **Step 7：上传页与问答页的未配置引导**

`src/frontend/src/views/MaterialsView.vue`：导入 `useRuntimeStore` 与 `SETTINGS_ROUTE`，`const runtime = useRuntimeStore()`；在上传表单之前加：

```html
<p v-if="runtime.needsConfig" class="model-required" data-test="model-config-required" role="alert">
  上传前需要先配置你的模型 API。
  <RouterLink :to="{ name: SETTINGS_ROUTE }" data-test="model-config-link">去设置</RouterLink>
</p>
```

并给上传按钮的 `:disabled` 条件加上 `|| runtime.needsConfig`。`src/frontend/src/composables/useMaterials.ts` 的上传错误文案函数（`cause.code === 'UNSUPPORTED_FORMAT'` 所在的分支链，约第 164 行）加：

```ts
    if (cause.code === 'MODEL_CONFIG_REQUIRED') {
      return '尚未配置模型 API，请先到「模型 API 设置」保存配置后再上传。'
    }
```

`src/frontend/src/views/ChatView.vue`：同样加 `data-test="model-config-required"` 的提示（文案「提问前需要先配置你的模型 API。」）并让发送按钮在 `runtime.needsConfig` 时禁用。`src/frontend/src/composables/useChat.ts` 的 `errorText`：

```ts
    if (reason === 'auth') return '你的模型 API 密钥被拒绝，请到「模型 API 设置」检查配置。'
```

（替换原「问答服务鉴权失败」那一行），并加 `if (code === 'MODEL_CONFIG_REQUIRED') return '尚未配置模型 API，请先到「模型 API 设置」保存配置。'`。

在 `tests/frontend/l10.test.ts` 追加两条用例，分别挂载 `MaterialsView` 与 `ChatView`（夹具照抄 `tests/frontend/h02.test.ts` 与 `tests/frontend/redesign-chat.test.ts` 的挂载辅助），先 `useRuntimeStore().apply({ runtime_mode: 'personal', configured: false })`，断言 `[data-test="model-config-required"]` 存在、提交按钮 `disabled`；再 `apply({ runtime_mode: 'personal', configured: true })` 后提示消失。既有用例中若有断言旧的「问答服务鉴权失败」文案，按新文案更新。

- [ ] **Step 8：运行确认通过**

```bash
npm run test --prefix src/frontend -- --run l10.test.ts
npm run test --prefix src/frontend -- --run
npm run type-check --prefix src/frontend
npm run build --prefix src/frontend
```

Expected: 全部通过；类型检查与构建以 0 退出。

- [ ] **Step 9：真实页面走查（personal 模式，本机假供应商或真实 key）**

```bash
scripts/start.sh --no-open
```

在浏览器 `http://localhost:5174`：
1. `demo_teacher` 登录 → 侧栏出现「模型 API 设置」且带未配置圆点 → 资料页显示引导、上传按钮禁用。
2. 设置页填入 DeepSeek 地址、`deepseek-flash`、自己的 key → 测试连接成功 → 保存 → 状态显示 `••••` 加末 4 位；刷新后仍是脱敏状态，密钥输入框为空。
3. 打开开发者工具的 Application → Storage，确认 `sessionStorage`/`localStorage` 中没有密钥；Network 中 `GET /me/model-config` 的响应不含密钥。
4. 资料页上传 `datasets/demo/ch3-stack-queue.md` → 进度推进到待审核。
5. `demo_student` 登录 → 问答页显示引导 → 配置后提问得到带引用的回答。
6. 教师清除配置 → 再次上传被拒并显示引导。

把每一步的实际结果（含失败）写入交接；截图存 `.demo/`，不入库。未填真实 key 时，第 2、4、5 步标记未验证。

- [ ] **Step 10：门禁、交接、提交**

```bash
./scripts/verify.sh
PYTHON=.venv/bin/python ./scripts/verify.sh full > .demo/logs/verify-full-l10.log 2>&1; echo "full=$?"
git add src/frontend/src tests/frontend docs/tasks.md docs/handoffs/claude-l10.md
git commit -m "feat(frontend): L10 模型 API 设置页、未配置引导与模式标识

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## 计划 A 完成标准

- Task 0–10 的每个交接文件存在且 `verification` 为实际结果。
- `./scripts/verify.sh full` 的退出码与失败清单已登记；新增测试 `test_l02_measure.py`、`test_l04.py`–`test_l09.py`、`l10.test.ts` 全部通过。
- `scripts/start.sh` 能启动正式模式；设置页、上传绑定、按用户问答在真实页面走通，或明确标为未验证并说明缺什么。
- `evaluation/reports/l02-baseline-2026-10.md` 给出带条件的抽取与问答实测数字和累计计费 token。
- 然后写计划 B（L11–L15），交用户确认。

## 回滚

- 每个任务一个提交，`git revert <commit>` 可逐个回退。
- 迁移 015：停 API 与 worker，恢复 `src/backend/storage/backups/*-before-015.sqlite`；新列均可空，旧代码可读新库。
- 运行模式：`.env` 把 `LLM_MODE` 改回 `demo` 即恢复演示路径；冲刺使用独立的 SQLite 与 Neo4j（7688），主检出的数据不受影响。
- 规则调整：回退 Task 3 的提交即恢复 `AGENTS.md` 原文。
