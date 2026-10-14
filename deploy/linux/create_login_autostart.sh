#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AUTOSTART_DIR="$HOME/.config/autostart"
LAUNCHER_NAME="PIDVN25006 Vision.desktop"
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

mkdir -p "$AUTOSTART_DIR"

cat > "$AUTOSTART_DIR/$LAUNCHER_NAME" <<DESKTOP
[Desktop Entry]
Type=Application
Name=PIDVN25006 Vision
Comment=Start PIDVN25006 AGV Vision Runtime after desktop login
Terminal=true
WorkingDirectory=$PROJECT_ROOT
Exec=bash -lc 'cd "$PROJECT_ROOT" && PIDVN_CONDA_ENV="$CONDA_ENV_NAME" PIDVN_CONDA_SH="$CONDA_SH" ./run_forever_conda.sh'
X-GNOME-Autostart-enabled=true
DESKTOP

chmod +x "$AUTOSTART_DIR/$LAUNCHER_NAME"

echo "[PIDVN25006] Login autostart created:"
echo "  $AUTOSTART_DIR/$LAUNCHER_NAME"
