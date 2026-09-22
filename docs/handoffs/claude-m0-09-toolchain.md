# M0-09 第一步：安装契约生成工具链并实测生成链

- **task_id**：M0-09（S-07 交接指定的下一个动作）第一步，覆盖原子清单 B14 的前置条件
- **状态**：工具已安装并实测通过；**生成物入库未做**（需在选定基线的 worktree 里做，不在本 worktree）
- **review_status**：ready_for_review
- **worktree**：`.claude/worktrees/adoring-sinoussi-709263`，分支 `claude/adoring-sinoussi-709263`
- **授权**：用户在本次会话中明确授权安装，并选定了安装位置（独立 venv + npm 全局）
- **未触碰**：`claude/worktree-contract-conflicts-740adb` 的 worktree 一个字节都没改。所有实测在 scratch 副本里做（`git archive` 出 `scripts/` 与 `src/contracts/`）

## 一、安装了什么，装在哪

| 工具 | 版本 | 位置 | 为什么这么装 |
| --- | --- | --- | --- |
| `datamodel-code-generator` | 0.26.3（与 `toolchain.txt` 锁一致） | venv `~/.local/share/smartsketch/contracts-venv`（Python 3.11.9） | 默认 `python3` 是 Anaconda 3.13；0.26.3 是 2024 年的包，不往 base 环境里塞，且 3.11 与脚本的 `--target-python-version 3.11` 一致 |
| `openapi-typescript` | 7.4.4（与锁一致） | npm 全局，prefix `/usr/local`（无需 sudo） | `src/frontend/package.json` 要等 B01 才存在，暂时无法按 `toolchain.txt` 的 `npm i -D` 装；`npx --no-install` 能从 PATH 找到它 |

venv 里连带装入 pydantic 2.13.5、black 26.5.1 等依赖，均在 venv 内，不影响系统与 conda base。

**PATH 要求**：`gen-contracts.sh` 只调用 `datamodel-codegen` 这个可执行文件，所以跑之前需要：

```bash
export PATH="$HOME/.local/share/smartsketch/contracts-venv/bin:$PATH"
```

B01 建出前端工程后，`openapi-typescript` 应按 `toolchain.txt` 补成 `-D` 依赖；`datamodel-code-generator` 建议写进后端 `pyproject.toml` 的 dev 组（B05），本条只是让生成链先能跑。

## 二、实测结果（全部在 scratch 副本，PATH 已加 venv）

```text
./scripts/gen-contracts.sh                    exit 0  四阶段全产出，无 INCOMPLETE
./scripts/gen-contracts.sh（第二次）           exit 0  6 个产物 SHA256 与第一次全等
./scripts/gen-contracts.sh --check            exit 0  生成物与真源一致
篡改 openapi.json 后 --check                  exit 1
篡改 python 后 --check                        exit 1
篡改 typescript/openapi.d.ts 后 --check       exit 1
篡改 schemas/TaskEvent.schema.json 后 --check  exit 1
恢复后 --check                                exit 0
生成的 Pydantic import                        OK，54 个 BaseModel 子类，pydantic 2.13.5
```

安装前对照组：`./scripts/gen-contracts.sh --check` 打印「缺少生成器 datamodel-codegen」并 exit 1 —— codex 审查 R02 的修复（缺依赖硬失败、不静默跳过）实测成立。

## 三、实测暴露的两个缺陷（B14 / M0-09 修，本轮不代修）

1. **Pydantic 产物落成一个没有扩展名的文件**。`gen-contracts.sh` 用 `--output "$dest/python"`，datamodel-codegen 单输入时写出的是文件而不是目录，于是产物是 `v1/generated/python`（592 行，合法 Pydantic v2），**不是** ADR-004 第 2 条写的 `python/` 目录，按当前路径无法 import。
   已验证修法（产出内容与现在逐字节相同）：
   ```bash
   mkdir -p "$dest/python"
   datamodel-codegen ... --output "$dest/python/models.py"
   ```
2. **`--check` 在产物缺失时退出码是 2，且吞掉修复提示**。`set -euo pipefail` 下，`diff -r -- "$OUT/$name" "$produced" 2>&1 | head -40 >&2` 里 `diff` 对缺失文件返回 2，脚本在到达下一行的 `exit 1` 之前就被 `set -e` 中止，所以「跑 ./scripts/gen-contracts.sh 重新生成并一并提交」这行永远不打印。门禁仍是红的（非 0），**不是假绿**，但操作者拿不到修复提示。内容不同的情况同理，退出码 1 也是 `set -e` 给的，不是那行 `exit 1`。

## 四、关于 `740adb` 已入库的生成物

`v1/generated/` 只有 `openapi.json` 和 3 个 `schemas/*.json`，**缺 `python/` 与 `typescript/`**——它们当时在 `--allow-scaffold` 下被跳过。实测这 4 个已入库文件与真源**逐字节一致**；但现在生成器齐全，对该分支跑 `--check` 会因缺两个阶段而非 0 退出。补齐入库是 M0-09 的动作，必须在选定的集成基线上做（PLAN-D04 未定）。

## 五、对 ADR-004 的影响

ADR-004「推翻条件」第 3 条（生成器无法产出可用 Pydantic v2）**不触发**，B′ 的前提成立，结论维持不变、**仍未签收**。实测补注已追加在 `docs/decisions.md` 的 ADR-004 之后。

## 六、未完成 / 风险

- 生成物入库未做（需先定 PLAN-D04 集成基线）。
- 上面两个脚本缺陷未修（不在本 worktree 的文件所有权范围内）。
- `toolchain.txt` 锁 `jsonschema==4.23.0`，本机校验侧解释器（conda base 3.13.5）是 4.26.0；`pyyaml` / `openapi-spec-validator` 与锁一致。是否收紧交 B07。
- 校验侧与生成侧跑在两个不同解释器上（`gen_contracts.py` 用 conda 3.13，`datamodel-codegen` 用 venv 3.11）。本轮实测无问题，但 B14 应把解释器选择写死，避免换机器后行为漂移。

## 七、下一位 Agent 的首个动作

**Backend Agent，M0-09**：在选定的集成基线 worktree 上，(1) 按第三节修掉两个脚本缺陷，(2) `export PATH` 后跑 `./scripts/gen-contracts.sh` 把 `python/` 与 `typescript/` 补齐入库，(3) 删掉 `scripts/verify/contracts.sh` 里的 `--allow-scaffold`，让缺工具直接红掉。

## 八、回滚

```bash
rm -rf ~/.local/share/smartsketch/contracts-venv   # 卸载 datamodel-code-generator 及其依赖
npm rm -g openapi-typescript                        # 卸载 TS 生成器
```

venv 是自包含目录，删掉即完全卸载，不影响 conda base 与系统 Python。本轮未改任何仓库内的脚本或契约文件。
