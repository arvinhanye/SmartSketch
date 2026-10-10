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
if ((status == 137)); then
  cat <<'MESSAGE'
启动器被系统终止（SIGKILL，退出码 137），尚未完成启动。
网上下载的未签名/未公证程序可能被 macOS 安全检查阻止；也可能有内存或其他系统原因。
先核对下载来源和 SHA256SUMS。如果你愿意自行信任此预览包，请在“系统设置 → 隐私与安全性”中审阅与 smartsketch-launcher 对应的“仍要打开”提示，并由你手动确认。
未签名程序未经 Apple 验证，单独允许打开存在风险。若系统明确提示恶意软件，请停止使用并反馈。
请不要关闭系统安全保护或删除下载隔离属性。
若没有对应的安全提示，请提供本次时间和错误截图，以便检查系统日志与内存原因。
正式分发需要 Developer ID 签名与 Apple 公证；预览包尚未完成这项发行验收。
MESSAGE
fi
if ((status)); then
  echo '启动未完成，请按上方提示处理。'
  read -r -p '按回车关闭…' _ || true
fi
exit "$status"
