#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_EXE=""
if [[ -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
  PYTHON_EXE="$SCRIPT_DIR/.venv/bin/python"
elif [[ -x "$SCRIPT_DIR/venv/bin/python" ]]; then
  PYTHON_EXE="$SCRIPT_DIR/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_EXE="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_EXE="$(command -v python)"
else
  echo "[PIDVN25006] ERROR: python3/python not found." >&2
  exit 127
fi

echo "[PIDVN25006] Starting forever supervisor..."
echo "[PIDVN25006] Project root: $SCRIPT_DIR"
echo "[PIDVN25006] Logs: outputs/runtime/supervisor/supervisor.log"

"$PYTHON_EXE" tools/run_forever.py "$@"
