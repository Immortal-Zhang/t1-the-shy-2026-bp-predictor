#!/usr/bin/env bash
set -euo pipefail
cd "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x /opt/homebrew/bin/node ]]; then export PATH="/opt/homebrew/bin:$PATH"; fi
PYTHON_BIN=''
for candidate in python3.11 python3.12 python3; do
  if command -v "$candidate" >/dev/null && "$candidate" -c 'import sys; raise SystemExit(0 if (3,11) <= sys.version_info[:2] < (3,14) else 1)' 2>/dev/null; then
    PYTHON_BIN="$candidate"; break
  fi
done
if [[ -z "$PYTHON_BIN" ]]; then echo 'Install Python 3.11–3.13 (3.11 recommended), then run ./start.sh again.' >&2; exit 1; fi
exec "$PYTHON_BIN" scripts/bootstrap_runtime.py "$@"
