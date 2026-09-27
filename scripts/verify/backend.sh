#!/usr/bin/env bash
# K11 后端门禁：pytest 全量 + 报告判定（零测试、失败、未登记的 SKIP 都让门禁失败）。
# 用法：scripts/verify/backend.sh [模式，缺省 full]；解释器取 $PYTHON，其次 .venv/bin/python，再次 python3。
set -euo pipefail
cd "$(dirname "$0")/../.."
mode="${1:-full}"
py="${PYTHON:-}"
if [[ -z $py ]]; then
  if [[ -x .venv/bin/python ]]; then py=.venv/bin/python; else py=python3; fi
fi
out="$(mktemp -d)"
trap 'rm -rf -- "$out"' EXIT

status=0
PYTHONPATH="$PWD/src/backend${PYTHONPATH:+:$PYTHONPATH}" "$py" -m pytest tests/backend tests/tooling -q -p no:cacheprovider \
  --junitxml="$out/backend.xml" || status=$?
# pytest 的退出码与报告判定都要过：前者抓崩溃/收集错误，后者抓零测试与未登记 SKIP。
"$py" scripts/verify/gate.py backend "$mode" "$out/backend.xml" --min-tests 100 || status=1
exit "$status"
