# L09 交接：在线向量、拒绝 `local`、正式启动入口（交给 DeepSeek harness）

```text
task_id: L09
review_status: handoff（Claude 未实现；由 DeepSeek harness 认领并实现）
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-contest-sprint-77644f
branch: claude/smartsketch-contest-sprint-77644f（只在本机，未推送 GitHub）
base_commit: 本交接所在提交（L00–L08、L10 代码已提交）
author: Claude（Opus 5.5）
```

## 1. 用户决定（2026-10-03）

- 向量服务选**第 1 种**：继续用阿里云百炼北京地域 `https://dashscope.aliyuncs.com/compatible-mode/v1`、`text-embedding-v4`、1024 维、每批 10 条（ADR-081）。用户负责恢复本机到该地址的网络路径；`.env` 的向量地址与 key 不改。
- L09 的代码由 DeepSeek harness 编写。

## 2. 开工前必读

1. `AGENTS.md`（共同工作契约；§4 已按 ADR-080 调整）、`CLAUDE.md` 只对 Claude 生效，其中「交接文件」「先读任务板」两条同样适用。
2. `docs/superpowers/specs/2026-10-02-contest-sprint-design.md` 第 4、11 节。
3. `docs/superpowers/plans/2026-10-02-contest-sprint-a-personal-model-api.md` 的 **Task 9（L09）**：步骤与验收以它为准，下面第 5 节是对它的三处修正。
4. `docs/decisions.md` 的 ADR-080、ADR-081。
5. `docs/handoffs/claude-l01.md`（环境与发现）、`claude-l02.md`（基线与向量不可达的证据）、`claude-l07.md`（旧表结构测试的教训）。

## 3. 开工前检查（只读）

```bash
cd /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-contest-sprint-77644f
git status --short            # 期望干净
git log --oneline -1
nc -z -G 8 dashscope.aliyuncs.com 443 && echo "向量地址可达"   # 不可达就先停，告诉用户，不要改地址或换供应商
docker info >/dev/null && docker ps --format '{{.Names}} {{.Ports}}' | grep 7688   # 本工作区 Neo4j
```

## 4. 环境要点（踩过的坑）

- 后端解释器：`.venv/bin/python`（Python 3.11.9）。不要用系统 `python3`（3.13，部分锁定依赖没有预编译包，会去拉 Rust 工具链）。
- 后端测试：`PYTHONPATH=src/backend .venv/bin/python -m pytest <文件> -q -p no:cacheprovider`；全量约 7 分钟，当前基线 3645 通过、27 跳过。
- 门禁：`./scripts/verify.sh`（基础档）；`PYTHON=.venv/bin/python ./scripts/verify.sh full`；集成档需 Docker。
- 端到端：本机没有 Playwright 浏览器，必须带 `PLAYWRIGHT_CHROMIUM_EXECUTABLE="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"`。
- 有测试只执行到较早的迁移（`test_d10`、`test_c09`）；任何写新列的 SQL 都要兼容旧表结构（L07 因此回归过一次）。
- 端口：本工作区 API 8001、前端 5174、Neo4j 7688/7475；用户主检出用 8000/5173/7687，不要动。
- `.env`（权限 600，Git 忽略）已含两个供应商 key；不得打印、记录或提交其中任何 key。不要在 zsh 里用 `set -a; . <(grep … .env)` 导入它（L02 实测会挂住），用 Python 按行解析。

## 5. 对计划 Task 9 的三处修正

1. **Step 5 的检查脚本**改为自己读取 `.env` 并在 macOS 上自动使用 certifi 根证书，避免第 4 节的 shell 导入问题。用下面这版代替计划里的版本。
2. **Step 6 的根密钥补齐**必须放在 `start-demo.sh` 第 2 节「.env」的生成与 `AUTH_JWT_SECRET` 补齐之后、「把 .env 按字面值导入」的循环**之前**，否则本次进程读不到新写入的值。
3. **Step 7 的联调命令**改为 `.venv/bin/python scripts/check-embedding.py`（不再用 shell 导入 `.env`）。

## 6. 现成的代码与改动

### 6.1 测试 `tests/backend/test_l09.py`（Claude 已写好并确认第一条失败、后两条通过）

```python
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

### 6.2 `src/backend/app/config.py`

把 `_check_rules` 中

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

### 6.3 既有测试需同步的三处（已逐条核对；不要删用例）

- `tests/backend/test_b06.py:89`：`({"EMBEDDING_MODE": "local"}, "EMBEDDING_MODEL")` 改为 `({"EMBEDDING_MODE": "local"}, "EMBEDDING_MODE")`，上一行加注释说明 ADR-081。
- `tests/backend/test_b06.py` 的 `test_complete_fallback_and_local_embedding_are_accepted`：改名为 `test_complete_fallback_and_online_embedding_are_accepted`，向量改为 `online` 并补 `EMBEDDING_BASE_URL`、`EMBEDDING_API_KEY`，断言 `EMBEDDING_MODE == "online"`。
- `tests/backend/test_b06.py` 的 `test_worker_can_reuse_space_gate_and_model_changes_fail`：两处 `"EMBEDDING_MODE": "local"` 改为 `online` 并补 `EMBEDDING_BASE_URL`、`EMBEDDING_API_KEY`，模型名 `model-a`/`model-b` 与断言不变。
- 不需要改：`tests/backend/test_e07.py`（直接构造 `Settings`，不经过规则校验）；`tests/backend/test_demo_mode.py:94`（新规则下错误信息仍含 `EMBEDDING_MODEL`）。

### 6.4 `scripts/check-embedding.py`（修正版，新增，`chmod +x`）

```python
#!/usr/bin/env python3
"""发 1 次真实向量请求，确认在线向量可用（L09，ADR-081）。只打印模型、维度与耗时，不打印 key 与向量。

用法（仓库根目录）：.venv/bin/python scripts/check-embedding.py
仓库根目录有 .env 时按字面值读入（不覆盖已在环境中的变量，不当 shell 脚本执行）。
退出码：0 成功；2 配置非法或不是 online；3 调用失败。
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "backend"))

from app.config import SettingsError, embedding_model_id, load_settings  # noqa: E402
from app.services.ai.client import EmbeddingRequest, ModelCallError  # noqa: E402
from app.services.ai.factory import build_embedding_client  # noqa: E402

_LINE = re.compile(r"^([A-Z_][A-Z0-9_]*)=(.*)$")


def _environment() -> dict[str, str]:
    values = dict(os.environ)
    env_file = ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            match = _LINE.match(line.rstrip("\r"))
            if match and match.group(2).strip() and match.group(1) not in values:
                values[match.group(1)] = match.group(2).strip()
    return values


def main() -> int:
    if not os.environ.get("SSL_CERT_FILE"):
        try:  # python.org 的 macOS Python 常找不到根证书
            import certifi

            os.environ["SSL_CERT_FILE"] = certifi.where()
        except ImportError:
            pass
    try:
        settings = load_settings(_environment())
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

### 6.5 `scripts/start-demo.sh`

- 用法注释、参数解析、`--live` 与 `--personal` 互斥、`((personal)) && do_import=0`：照计划 Task 9 Step 6 第 1、2 点。
- 根密钥补齐（位置见第 5 节第 2 条）：

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

- 模式分支：把原 `if ((live)); then` 改为下面这段开头的 `elif`：

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

- 结尾提示按模式区分：personal 时输出「✓ 正式模式已启动：$WEB_URL；教师与学生登录后先在『模型 API 设置』保存自己的模型 API」，不再说「演示环境」。

### 6.6 `scripts/start.sh`（新增，`chmod +x`）

```bash
#!/usr/bin/env bash
# 正式入口：个人模型 API（LLM_MODE=personal，ADR-080）+ 在线向量（ADR-081）。
# 演示入口见 scripts/start-demo.sh（不联网的演示模型）。用法：scripts/start.sh [--no-open]
set -euo pipefail
exec "$(dirname "$0")/start-demo.sh" --personal "$@"
```

### 6.7 `docs/runbook.md`

新增「正式模式」一节（`scripts/start.sh`、所需变量、`MODEL_CREDENTIAL_KEY` 说明、`check-embedding.py`）；第 60 行一带「`online`/`local` 时照用」的表述改为只有 `online`；把 `start-demo.sh` 明确标为演示入口。

## 7. 验收（全部要有实际输出）

```bash
PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_l09.py tests/backend/test_b06.py tests/backend/test_e07.py tests/backend/test_demo_mode.py -q -p no:cacheprovider
PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend tests/tooling -q -p no:cacheprovider   # 期望 0 失败
.venv/bin/python scripts/check-embedding.py      # 期望 ok … dimensions=1024
scripts/start.sh --no-open                       # 另开终端：curl -s http://127.0.0.1:8001/health；tail .demo/logs/worker.log 无 Invalid configuration；Ctrl-C 停止
./scripts/verify.sh
```

## 8. 文件所有权与协作

- L09 只改：`src/backend/app/config.py`（仅 6.2 一处）、`tests/backend/test_l09.py`、`tests/backend/test_b06.py`（仅 6.3 三处）、`scripts/check-embedding.py`、`scripts/start-demo.sh`、`scripts/start.sh`、`docs/runbook.md`、`docs/integrations.md`（若向量地址需更正）、`docs/tasks.md`（L09 一行）、你自己的交接文件。
- 不要改 L03–L08、L10 已提交的其他文件；发现它们有问题，写进交接，不要顺手改。
- 交接文件命名 `docs/handoffs/deepseek-l09.md`，字段同本文件头（task_id、review_status、worktree、base/head、changed_files、verification、unverified、api_and_data_changes、rollback、next_action）。
- 提交只在本分支本地；提交信息说明作者是 DeepSeek harness；不推送、不合并（需用户另行授权）。
- 预算：冲刺累计计费 token 约 101054 / 5000000；向量联调与测试连接用量很小，仍请在交接里登记。

## 9. L09 之后的下一步（由用户决定谁来做）

1. **L02 问答基线补测**：本地库里保留了课程 `2ace598581f349ec9943dea90bc7fdf1`（任务 `205f9311572846b8bc192ff1f67e244f`，82 个知识点、73 条关系的草稿）。发布、添加 `demo_student`，再运行 `evaluation/measure_web_flow.py ask`，结果追加到 `evaluation/reports/l02-baseline-2026-10.md`。注意：用 `start.sh`（personal）启动时 `demo_student` 需先在设置页保存自己的模型 API。
2. **L10 真实页面走查**：计划 Task 10 Step 9 的六步，结果补到 `docs/handoffs/claude-l10.md`。
3. 计划 B（L11–L15）：按规格第 7 节，在主线走通后编写。

## 10. 当前状态核对

| 任务 | 状态 | 提交 |
| --- | --- | --- |
| L00 设计与计划 | DONE | `aa538c9` |
| L01 环境与门禁基线 | DONE | `52aa4db` |
| L02 真实基线 | 抽取已测；问答待向量可达 | `7078812` |
| L03 ADR、规则与契约 | DONE | `5e1f96e` |
| L04 迁移、加密、仓储 | DONE | `16d975a` |
| L05 出站地址校验 | DONE | `0e228bd` |
| L06 个人配置接口 | DONE | `d2e97c0` |
| L07 上传绑定与 worker | DONE | `bce4979` |
| L08 问答按用户取模型 | DONE | `376bdd9` |
| L09 在线向量与正式入口 | **交给 DeepSeek harness** | — |
| L10 前端设置页 | 代码完成；走查待 L09 | `e645913` |

L07、L08 的最后一轮验证：后端全量 3645 通过、27 跳过；集成用例 392 通过、4 跳过，图库后端用例 44 通过（2026-10-03）。
