#!/bin/bash
set -u
DIR="$(cd -- "$(dirname -- "$0")" && pwd -P)"
case "$(uname -m)" in
  arm64) TARGET=darwin-arm64 ;;
  x86_64) TARGET=darwin-amd64 ;;
  *) echo '此安装包仅支持 Mac Apple Silicon 或 Intel。'; read -r -p '按回车关闭…' _; exit 1 ;;
esac
if [[ ! -f "$DIR/target.txt" ]] || [[ "$(cat "$DIR/target.txt")" != "$TARGET" ]]; then
  echo '芯片与安装包不匹配，请下载对应的 Mac 版本。'; read -r -p '按回车关闭…' _; exit 1
fi
"$DIR/bin/smartsketch-launcher"
status=$?
if ((status)); then read -r -p '启动未完成，请按上方提示处理；按回车关闭…' _; fi
exit "$status"
