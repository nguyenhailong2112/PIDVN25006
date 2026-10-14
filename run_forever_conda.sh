#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

CONDA_ENV_NAME="${PIDVN_CONDA_ENV:-pidvn25006}"
CONDA_SH="${PIDVN_CONDA_SH:-}"

if [[ -z "$CONDA_SH" ]]; then
  for candidate in \
    "$HOME/miniconda3/etc/profile.d/conda.sh" \
    "$HOME/anaconda3/etc/profile.d/conda.sh" \
    "/opt/miniconda3/etc/profile.d/conda.sh" \
    "/opt/anaconda3/etc/profile.d/conda.sh"
  do
    if [[ -f "$candidate" ]]; then
      CONDA_SH="$candidate"
      break
    fi
  done
fi

if [[ -z "$CONDA_SH" || ! -f "$CONDA_SH" ]]; then
  echo "[PIDVN25006] ERROR: conda.sh not found." >&2
  echo "[PIDVN25006] Set PIDVN_CONDA_SH=/path/to/miniconda3/etc/profile.d/conda.sh" >&2
  exit 127
fi

source "$CONDA_SH"
conda activate "$CONDA_ENV_NAME"

echo "[PIDVN25006] Starting forever supervisor with conda env: $CONDA_ENV_NAME"
echo "[PIDVN25006] Project root: $SCRIPT_DIR"
echo "[PIDVN25006] Python: $(command -v python)"
echo "[PIDVN25006] Logs: outputs/runtime/supervisor/supervisor.log"

exec python tools/run_forever.py "$@"
