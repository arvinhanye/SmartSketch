#!/usr/bin/env bash
# Launcher correctness gate; no .env, business DB, image pull or model calls.
set -euo pipefail
cd "$(dirname "$0")/../.."
command -v go >/dev/null || { echo 'FAIL startup gate: Go 1.26.8 toolchain is required for developers/CI.' >&2; exit 1; }
[[ $(go version) == *' go1.26.8 '* ]] || { echo 'FAIL startup gate: toolchain version differs from approved 1.26.8.' >&2; exit 1; }
export GOTOOLCHAIN=local
# macOS /var is an OS alias; security tests need a canonical temporary path.
if [[ $(uname -s) == Darwin ]]; then export TMPDIR=/private/tmp; fi
(cd launcher && go test ./... -count=1 && go vet ./...)
# The Windows-only ACL code is not compiled on other hosts, so vet it explicitly: the Windows CI runner vets it natively.
(cd launcher && GOOS=windows GOARCH=amd64 go vet ./...)
echo 'Startup unit and vet gate passed (not platform/release acceptance).'
