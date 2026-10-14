#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVICE_NAME="${PIDVN_SERVICE_NAME:-pidvn25006}"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
RUN_USER="${PIDVN_RUN_USER:-$(id -un)}"
CONDA_ENV_NAME="${PIDVN_CONDA_ENV:-pidvn25006}"
CONDA_SH="${PIDVN_CONDA_SH:-}"
START_FRONTEND="${PIDVN_START_FRONTEND:-1}"

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
  echo "[PIDVN25006] Example:" >&2
  echo "  PIDVN_CONDA_SH=/home/$RUN_USER/miniconda3/etc/profile.d/conda.sh PIDVN_CONDA_ENV=$CONDA_ENV_NAME $0" >&2
  exit 127
fi

SUPERVISOR_ARGS=""
if [[ "$START_FRONTEND" == "0" ]]; then
  SUPERVISOR_ARGS="--no-frontend"
fi

sudo tee "$SERVICE_PATH" >/dev/null <<SERVICE
[Unit]
Description=PIDVN25006 AGV Vision Runtime Supervisor
After=network-online.target graphical.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$PROJECT_ROOT
Environment=PIDVN_CONDA_ENV=$CONDA_ENV_NAME
Environment=PIDVN_CONDA_SH=$CONDA_SH
ExecStartPre=/usr/bin/mkdir -p $PROJECT_ROOT/outputs/runtime/supervisor
ExecStart=$PROJECT_ROOT/run_forever_conda.sh $SUPERVISOR_ARGS
Restart=always
RestartSec=5
KillSignal=SIGINT
TimeoutStopSec=20
StandardOutput=append:$PROJECT_ROOT/outputs/runtime/supervisor/systemd_stdout.log
StandardError=append:$PROJECT_ROOT/outputs/runtime/supervisor/systemd_stderr.log

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME.service"
sudo systemctl restart "$SERVICE_NAME.service"

echo "[PIDVN25006] Installed and started service: $SERVICE_NAME.service"
echo "[PIDVN25006] Status: sudo systemctl status $SERVICE_NAME.service"
echo "[PIDVN25006] Logs: journalctl -u $SERVICE_NAME.service -f"
