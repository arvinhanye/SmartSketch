#!/usr/bin/env bash
# 从契约真源 src/contracts/api.v1.yaml 生成入库产物（ADR-004）。
#
#   ./scripts/gen-contracts.sh                  重新生成并写入 src/contracts/v1/generated/
#   ./scripts/gen-contracts.sh --check          生成到临时目录并比对，有 diff 即非 0 退出
#   ./scripts/gen-contracts.sh [...] --allow-scaffold
#                                               骨架模式：缺生成器时跳过对应阶段并打印
#                                               未完成验收标记，而不是失败
#
# 缺生成器时默认**失败**。这是 codex 审查 R02 的教训：门禁静默跳过等于假绿。
set -euo pipefail
cd "$(dirname "$0")/.."

OUT="src/contracts/v1/generated"
CHECK=0
ALLOW_SCAFFOLD=0
_completed=0   # 走到脚本结尾才置 1，EXIT trap 据此判断是否被中止（见 --check 段）
for arg in "$@"; do
  case "$arg" in
    --check) CHECK=1 ;;
    --allow-scaffold) ALLOW_SCAFFOLD=1 ;;
    *) echo "未知参数：$arg" >&2; exit 2 ;;
  esac
done

# 只清空已知的生成目录，不用通配删除：这是别人也在用的工作区。
empty_dir() {
  [[ -d $1 ]] || return 0
  find "$1" -mindepth 1 -depth -delete
}

skipped=()
note_missing() {   # $1=工具 $2=阶段 $3=安装提示
  if ((ALLOW_SCAFFOLD)); then
    skipped+=("$2（缺 $1）")
    return 0
  fi
  echo "缺少生成器 $1，无法生成 $2。" >&2
  echo "  安装：$3" >&2
  echo "  版本锁见 src/contracts/toolchain.txt" >&2
  echo "  仅骨架阶段可用 --allow-scaffold 降级（会打印未完成验收标记）。" >&2
  exit 1
}

generate_into() {  # $1=目标目录
  local dest="$1"
  mkdir -p "$dest"

  python3 scripts/gen_contracts.py openapi "$dest"
  python3 scripts/gen_contracts.py schemas "$dest"

  if command -v datamodel-codegen >/dev/null 2>&1; then
    # 输出必须落成 python/models.py：单输入时 datamodel-codegen 把 --output 当文件名，
    # 写成 "$dest/python" 会得到一个没有扩展名、无法 import 的文件（ADR-004 第 2 条要的是目录）。
    mkdir -p "$dest/python"
    datamodel-codegen \
      --input src/contracts/api.v1.yaml --input-file-type openapi \
      --output "$dest/python/models.py" --output-model-type pydantic_v2.BaseModel \
      --target-python-version 3.11 --use-annotated --use-standard-collections \
      --disable-timestamp --encoding utf-8
    echo "  · python/models.py（Pydantic v2）"
  else
    note_missing datamodel-codegen "python/（Pydantic v2 模型）" \
      "pip3 install 'datamodel-code-generator==0.26.3'"
  fi

  if command -v openapi-typescript >/dev/null 2>&1 && openapi-typescript --version >/dev/null 2>&1; then
    mkdir -p "$dest/typescript"
    openapi-typescript src/contracts/api.v1.yaml \
      -o "$dest/typescript/openapi.d.ts"
    echo "  · typescript/openapi.d.ts"
  else
    note_missing openapi-typescript "typescript/（前端类型）" \
      "npm i -D 'openapi-typescript@7.4.4'"
  fi

  # 各生成器在 Windows 上的默认换行不同；入库产物统一 LF，保证跨系统 --check。
  python3 - "$dest" <<'PY'
from pathlib import Path
import sys

for path in Path(sys.argv[1]).rglob("*"):
    if path.is_file():
        data = path.read_bytes()
        if b"\r\n" in data:
            path.write_bytes(data.replace(b"\r\n", b"\n"))
PY
}

if ((CHECK)); then
  if [[ ! -d $OUT ]]; then
    echo "生成物目录不存在：$OUT" >&2
    echo "  先跑 ./scripts/gen-contracts.sh 生成并提交（ADR-004 第 5 条：生成物入库）。" >&2
    exit 1
  fi
  tmp="$(mktemp -d)"
  # bash 3.2（macOS 自带）被 set -u 中止后进入 EXIT trap 时 $? 已经是 0，光保存 $? 救不回
  # 失败状态——S07-R06 的假绿就是这么来的。所以再加一道：没走到脚本结尾就一律按失败处理。
  trap 'rc=$?; empty_dir "$tmp" || true; rmdir "$tmp" 2>/dev/null || true
        if [[ $rc -eq 0 && ${_completed:-0} -ne 1 ]]; then
          echo "gen-contracts.sh 未正常结束（可能被 set -u / set -e 中止），按失败处理。" >&2
          rc=1
        fi
        exit "$rc"' EXIT
  generate_into "$tmp" >/dev/null
  # 只比对本次真正生成出来的阶段；跳过的阶段由下面的未完成标记负责暴露。
  for produced in "$tmp"/*; do
    name="$(basename "$produced")"
    # -x __pycache__：python/ 是目录后，任何人 import 过生成的模型都会在里面留下字节码缓存，
    # 那不是契约漂移，不该让门禁变红。
    if ! diff -r -x '__pycache__' -- "$OUT/$name" "$produced" >/dev/null 2>&1; then
      if [[ ! -e "$OUT/$name" ]]; then
        # 变量紧挨全角字符时必须加花括号：UTF-8 locale 下 bash 3.2 会把「（」的字节并入变量名（S07-R06）。
        echo "生成物缺失：${OUT}/${name}（真源能生成该阶段，但仓库里没有入库）" >&2
      else
        echo "生成物与真源不同步：$OUT/$name" >&2
        # diff 非 0 是预期结果；不裹住它，set -e + pipefail 会让脚本死在这里，
        # 退出码变成 diff 的 2，下面的修复提示也永远不会打印。
        { diff -r -x '__pycache__' -- "$OUT/$name" "$produced" 2>&1 || true; } | head -40 >&2
      fi
      echo "  跑 ./scripts/gen-contracts.sh 重新生成并一并提交（ADR-004 第 7 条）。" >&2
      exit 1
    fi
  done
  echo "  ✓ 生成物与真源一致"
else
  empty_dir "$OUT"
  generate_into "$OUT"
fi

if ((${#skipped[@]})); then
  printf 'INCOMPLETE 未生成：%s\n' "$(IFS=,; echo "${skipped[*]}")"
  echo "  本次结果不构成契约验收。按 src/contracts/toolchain.txt 安装后重跑，去掉 --allow-scaffold。"
fi

_completed=1
