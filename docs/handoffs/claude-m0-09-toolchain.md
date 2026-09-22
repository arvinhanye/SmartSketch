# M0-09 第一步：安装契约生成工具链并实测生成链

- **task_id**：M0-09（S-07 交接指定的下一个动作）第一步，覆盖原子清单 B14 的前置条件
- **状态**：工具已安装并实测通过；两个脚本缺陷已修（`740adb` 的 `8865686`）；**生成物入库未做**（需在选定基线上做）
- **review_status**：ready_for_review
- **worktree**：`.claude/worktrees/adoring-sinoussi-709263`，分支 `claude/adoring-sinoussi-709263`
- **授权**：用户在本次会话中明确授权安装，并选定了安装位置（独立 venv + npm 全局）
- **跨 worktree 改动**：经用户授权，在 `claude/worktree-contract-conflicts-740adb` 上提交了 `8865686`（只改 `scripts/gen-contracts.sh`）。除此之外所有实测都在 scratch 副本里做（`git archive` 出 `scripts/` 与 `src/contracts/`）

## 一、安装了什么，装在哪

| 工具 | 版本 | 位置 | 为什么这么装 |
| --- | --- | --- | --- |
| `datamodel-code-generator` | 0.26.3（与 `toolchain.txt` 锁一致） | venv `~/.local/share/smartsketch/contracts-venv`（Python 3.11.9） | 默认 `python3` 是 Anaconda 3.13；0.26.3 是 2024 年的包，不往 base 环境里塞，且 3.11 与脚本的 `--target-python-version 3.11` 一致 |
| `openapi-typescript` | 7.4.4（与锁一致） | npm 全局，prefix `/usr/local`（无需 sudo） | `src/frontend/package.json` 要等 B01 才存在，暂时无法按 `toolchain.txt` 的 `npm i -D` 装；`npx --no-install` 能从 PATH 找到它 |

venv 里连带装入 pydantic 2.13.5、black 26.5.1 等依赖，均在 venv 内，不影响系统与 conda base。

**PATH 处理**：`gen-contracts.sh` 只调用 `datamodel-codegen` 这个可执行文件，因此把它软链进已在 PATH 上的 `/usr/local/bin`，**不要**把 venv 的 `bin` 整个前置：

```bash
ln -sfn ~/.local/share/smartsketch/contracts-venv/bin/datamodel-codegen /usr/local/bin/datamodel-codegen
```

> **踩过的坑**：最初用 `export PATH="$VENV/bin:$PATH"`，venv 的 `python3`（3.11，没装 jsonschema / openapi-spec-validator）把 conda 的 `python3` 影子掉了，于是 `tests/contracts/test_contracts.py` 假失败 3 项（含 `test_instance_level_cases: ModuleNotFoundError: jsonschema`）。换成软链后同一套命令 20/20 通过。校验侧跑 conda `python3` 3.13.5，生成侧跑 venv 3.11，互不干扰。

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

## 三、实测暴露的两个缺陷（已修，`740adb` 的 `8865686`）

经用户授权直接在 `claude/worktree-contract-conflicts-740adb` 上修复并提交。该 worktree 修改前状态：HEAD `1bc63ad`、工作区干净、会话已停止，无并发写入者；待改文件与我打补丁的基线逐字节一致。

1. **Pydantic 产物落成一个没有扩展名的文件**。`--output "$dest/python"` 在单输入时被 datamodel-codegen 当成文件名，产出 `v1/generated/python`（592 行，合法 Pydantic v2），**不是** ADR-004 第 2 条写的 `python/` 目录，按该路径无法 import。
   修法：`mkdir -p "$dest/python"` + `--output "$dest/python/models.py"`，产出内容与修复前逐字节相同。
2. **`--check` 在产物缺失时退出码是 2，且吞掉修复提示**。`set -euo pipefail` 下用于打印详情的第二个 `diff` 返回非 0（缺失时为 2），脚本在到达 `exit 1` 之前就被 `set -e` 中止，所以「跑 ./scripts/gen-contracts.sh 重新生成并一并提交」永远不打印。门禁仍是红的，**不是假绿**，但操作者拿不到修复指引。
   修法：把该 `diff` 裹进 `{ ... || true; }`，并为「产物缺失」单独给一条明确信息。
3. **附带修**：两处 `diff` 加 `-x __pycache__`。`python/` 变成目录后，任何人 import 过生成的模型都会在里面留下字节码缓存，那不是契约漂移，不该让门禁变红。

### 修复前后对照（同一 worktree，同一套命令）

| | 修复前 | 修复后 |
| --- | --- | --- |
| `--check` 遇产物缺失 | `exit 2`，只打印 `diff: ... No such file or directory`，无修复提示 | `exit 1`，打印「生成物缺失：…（真源能生成该阶段，但仓库里没有入库）」+ 修复提示 |
| Pydantic 产物 | `v1/generated/python`（无扩展名文件，import 不了） | `v1/generated/python/models.py`，`from python.models import ...` 成功，54 个 `BaseModel` 子类 |
| 契约门禁负向测试 | 20/20 通过 | 20/20 通过（未回归） |
| `./scripts/verify.sh` | `exit 1` | `exit 1`（原因变了，见第四节） |

### 完整回归矩阵（scratch 副本，13 项）

```text
完整生成 0    第二次生成 0    两次字节一致 0    --check 同步 0
篡改 openapi.json 1    篡改 python/models.py 1
篡改 typescript/openapi.d.ts 1    篡改 schemas/TaskEvent.schema.json 1
python/ 缺失 1    typescript/ 缺失 1    阶段内多出陈旧文件 1
import python.models 0    import 留下 __pycache__ 后 --check 0
```

### 仍未修（留给 B14 / M0-09）

`--check` 只遍历本次生成出来的阶段（`for produced in "$tmp"/*`），所以 `v1/generated/` **顶层**多出的整个陈旧阶段目录检不出来；阶段**内部**多出的陈旧文件能检出。要覆盖需反向再遍历一次 `$OUT/*`。

## 四、关于 `740adb` 已入库的生成物

`v1/generated/` 只有 `openapi.json` 和 3 个 `schemas/*.json`，**缺 `python/` 与 `typescript/`**——它们当时在 `--allow-scaffold` 下被跳过。实测这 4 个已入库文件与真源**逐字节一致**。

**该分支的 `./scripts/verify.sh` 现在是 `exit 1`，这是正确结果，不是脚本缺陷**：`scripts/verify/contracts.sh` 调的是 `gen-contracts.sh --check --allow-scaffold`，而本机生成器已齐全，`--allow-scaffold` 不再跳过任何阶段，于是 `--check` 如实报出 `python/` 与 `typescript/` 没有入库。装生成器之前它是绿的——那个绿是降级模式给的。

把它变绿需要跑一次写入模式并把约 2500 行生成物入库，那是 M0-09 的动作，**必须在选定的集成基线上做**（PLAN-D04 未定），本轮没做。

## 五、对 ADR-004 的影响

ADR-004「推翻条件」第 3 条（生成器无法产出可用 Pydantic v2）**不触发**，B′ 的前提成立，结论维持不变、**仍未签收**。实测补注已追加在 `docs/decisions.md` 的 ADR-004 之后。

## 六、未完成 / 风险

- 生成物入库未做（需先定 PLAN-D04 集成基线）。
- 上面两个脚本缺陷未修（不在本 worktree 的文件所有权范围内）。
- `toolchain.txt` 锁 `jsonschema==4.23.0`，本机校验侧解释器（conda base 3.13.5）是 4.26.0；`pyyaml` / `openapi-spec-validator` 与锁一致。是否收紧交 B07。
- 校验侧与生成侧跑在两个不同解释器上（`gen_contracts.py` 用 conda 3.13，`datamodel-codegen` 用 venv 3.11）。本轮实测无问题，但 B14 应把解释器选择写死，避免换机器后行为漂移。

## 七、下一位 Agent 的首个动作

**Backend Agent，M0-09**：脚本缺陷已修（`740adb` 的 `8865686`），剩下的是 (1) 在选定的集成基线上跑 `./scripts/gen-contracts.sh` 把 `python/` 与 `typescript/` 补齐入库，(2) 删掉 `scripts/verify/contracts.sh` 里的 `--allow-scaffold`，让缺工具直接红掉，(3) 顺手补上第三节末尾那个「顶层陈旧阶段检不出」的反向遍历。

## 八、回滚

```bash
rm -rf ~/.local/share/smartsketch/contracts-venv   # 卸载 datamodel-code-generator 及其依赖
npm rm -g openapi-typescript                        # 卸载 TS 生成器
```

```bash
rm -f /usr/local/bin/datamodel-codegen                              # 移除软链
git -C .claude/worktrees/worktree-contract-conflicts-740adb revert --no-edit 8865686   # 撤销脚本修复
```

venv 是自包含目录，删掉即完全卸载，不影响 conda base 与系统 Python。本轮在仓库内只改了一个文件：`740adb` 的 `scripts/gen-contracts.sh`，未动任何契约或生成物。
