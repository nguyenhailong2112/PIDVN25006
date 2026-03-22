#!/usr/bin/env bash
set -euo pipefail

# PIDVN25006 one-shot Linux setup script
# Usage:
#   bash scripts/setup_full_linux.sh [--project-dir /opt/pidvn25006] [--torch cpu|cuda] [--skip-apt] [--no-service]

PROJECT_DIR="/opt/pidvn25006"
TORCH_MODE="cpu"
SKIP_APT="0"
INSTALL_SERVICE="1"
DEPLOY_USER="${SUDO_USER:-$USER}"
DEPLOY_GROUP="$(id -gn "${SUDO_USER:-$USER}")"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

print_help() {
  cat <<USAGE
PIDVN25006 Full Setup Script

Options:
  --project-dir <path>   Target installation folder (default: /opt/pidvn25006)
  --torch <cpu|cuda>     Install torch CPU or CUDA wheel command (default: cpu)
  --skip-apt             Skip apt-get dependency installation
  --no-service           Do not create/start systemd service
  -h, --help             Show this help
USAGE
}

log() {
  echo "[PIDVN-SETUP] $*"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing command: $1" >&2
    exit 1
  }
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-dir)
      PROJECT_DIR="$2"
      shift 2
      ;;
    --torch)
      TORCH_MODE="$2"
      shift 2
      ;;
    --skip-apt)
      SKIP_APT="1"
      shift
      ;;
    --no-service)
      INSTALL_SERVICE="0"
      shift
      ;;
    -h|--help)
      print_help
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      print_help
      exit 1
      ;;
  esac
done

if [[ "$TORCH_MODE" != "cpu" && "$TORCH_MODE" != "cuda" ]]; then
  echo "--torch must be cpu or cuda" >&2
  exit 1
fi

require_cmd python3
require_cmd git

if [[ "$SKIP_APT" == "0" ]]; then
  require_cmd sudo
  log "Installing Linux dependencies via apt-get"
  sudo apt-get update
  sudo apt-get install -y git python3 python3-venv python3-pip ffmpeg libgl1 libglib2.0-0
fi

log "Preparing target directory: $PROJECT_DIR"
sudo mkdir -p "$PROJECT_DIR"
sudo chown -R "$DEPLOY_USER:$DEPLOY_GROUP" "$PROJECT_DIR"

log "Syncing project files"
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete \
    --exclude '.git' \
    --exclude '.venv' \
    --exclude '__pycache__' \
    --exclude '.pytest_cache' \
    --exclude 'outputs' \
    "$SRC_DIR/" "$PROJECT_DIR/"
else
  tar --exclude='.git' --exclude='.venv' --exclude='__pycache__' --exclude='.pytest_cache' --exclude='outputs' -C "$SRC_DIR" -cf - . | tar -C "$PROJECT_DIR" -xf -
fi

cd "$PROJECT_DIR"

log "Creating Python virtual environment"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

log "Installing Python dependencies"
pip install -U pip
pip install -r requirements.txt

if [[ "$TORCH_MODE" == "cpu" ]]; then
  log "Installing torch (CPU build)"
  pip install torch torchvision
else
  log "Installing torch (CUDA build)"
  log "Please confirm your server CUDA version. Default command uses cu124 wheels."
  pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
fi

log "Ensuring runtime output folders"
mkdir -p outputs/history outputs/multi_runtime outputs/monitoring outputs/agv

if [[ ! -f .env ]]; then
  log "Creating .env template (edit this before production start if using env vars in cameras.json)"
  cat > .env <<'ENVEOF'
# PIDVN25006 runtime environment
# Example: export RTSP_PASS='your_password'
RTSP_PASS=
PIDVN_LOG_DIR=
PIDVN_LOG_NAME=app.log
ENVEOF
fi

log "Running config validation"
python - <<'PY'
from core.config import (
    load_camera_configs,
    load_json_dict,
    load_rule_config,
    validate_camera_configs,
    validate_gui_config,
    validate_rule_config,
)
from core.path_utils import PROJECT_ROOT

camera_cfg = load_camera_configs(PROJECT_ROOT / "configs" / "cameras.json")
rule_cfg = load_rule_config(PROJECT_ROOT / "configs" / "rules.json")
gui_cfg = load_json_dict(PROJECT_ROOT / "configs" / "gui.json")

validate_camera_configs(camera_cfg)
validate_rule_config(rule_cfg)
validate_gui_config(gui_cfg)
print("Config validation: OK")
PY

if [[ "$INSTALL_SERVICE" == "1" ]]; then
  require_cmd sudo
  log "Installing systemd service"
  sudo tee /etc/systemd/system/pidvn25006.service >/dev/null <<SERVICE
[Unit]
Description=PIDVN25006 Monitor
After=network.target

[Service]
Type=simple
User=$DEPLOY_USER
Group=$DEPLOY_GROUP
WorkingDirectory=$PROJECT_DIR
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-$PROJECT_DIR/.env
ExecStart=$PROJECT_DIR/.venv/bin/python $PROJECT_DIR/main_monitor_gui.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

  sudo systemctl daemon-reload
  sudo systemctl enable pidvn25006
  sudo systemctl restart pidvn25006
  log "Service status"
  sudo systemctl --no-pager --full status pidvn25006 || true
fi

log "Setup completed successfully"
log "Next checks:"
log "  1) Edit $PROJECT_DIR/configs/cameras.json for factory RTSP/model/zone"
log "  2) If using env vars, edit $PROJECT_DIR/.env then: sudo systemctl restart pidvn25006"
log "  3) Monitor logs: journalctl -u pidvn25006 -f"
