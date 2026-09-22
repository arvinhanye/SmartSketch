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
    datamodel-codegen \
      --input src/contracts/api.v1.yaml --input-file-type openapi \
      --output "$dest/python" --output-model-type pydantic_v2.BaseModel \
      --target-python-version 3.11 --use-annotated --use-standard-collections \
      --disable-timestamp
    echo "  · python/（Pydantic v2）"
  else
    note_missing datamodel-codegen "python/（Pydantic v2 模型）" \
      "pip3 install 'datamodel-code-generator==0.26.3'"
  fi

  if npx --no-install openapi-typescript --version >/dev/null 2>&1; then
    mkdir -p "$dest/typescript"
    npx --no-install openapi-typescript src/contracts/api.v1.yaml \
      -o "$dest/typescript/openapi.d.ts"
    echo "  · typescript/openapi.d.ts"
  else
    note_missing openapi-typescript "typescript/（前端类型）" \
      "npm i -D 'openapi-typescript@7.4.4'"
  fi
}

if ((CHECK)); then
  if [[ ! -d $OUT ]]; then
    echo "生成物目录不存在：$OUT" >&2
    echo "  先跑 ./scripts/gen-contracts.sh 生成并提交（ADR-004 第 5 条：生成物入库）。" >&2
    exit 1
  fi
  tmp="$(mktemp -d)"
  trap 'empty_dir "$tmp"; rmdir "$tmp" 2>/dev/null || true' EXIT
  generate_into "$tmp" >/dev/null
  # 只比对本次真正生成出来的阶段；跳过的阶段由下面的未完成标记负责暴露。
  for produced in "$tmp"/*; do
    name="$(basename "$produced")"
    if ! diff -r -- "$OUT/$name" "$produced" >/dev/null 2>&1; then
      echo "生成物与真源不同步：$OUT/$name" >&2
      diff -r -- "$OUT/$name" "$produced" 2>&1 | head -40 >&2
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
