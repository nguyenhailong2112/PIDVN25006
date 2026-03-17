#!/usr/bin/env bash
set -euo pipefail

# Simple installer for PIDVN25006 on Linux
# Usage:
#   chmod +x install_linux.sh
#   ./install_linux.sh
#
# Optional env vars:
#   INSTALL_DIR=/opt/pidvn25006
#   ENABLE_SYSTEMD=1
#   INSTALL_TORCH=1
#   USE_SUDO=1

INSTALL_DIR="${INSTALL_DIR:-/opt/pidvn25006}"
ENABLE_SYSTEMD="${ENABLE_SYSTEMD:-0}"
INSTALL_TORCH="${INSTALL_TORCH:-0}"
USE_SUDO="${USE_SUDO:-1}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

SUDO=""
if [[ "$USE_SUDO" == "1" && "$EUID" -ne 0 ]]; then
  SUDO="sudo"
fi

echo "[1/6] Installing system packages..."
$SUDO apt-get update
$SUDO apt-get install -y python3 python3-venv python3-pip ffmpeg libgl1 libglib2.0-0

echo "[2/6] Copying project to ${INSTALL_DIR}..."
SRC_DIR="$(pwd)"
if [[ "$SRC_DIR" != "$INSTALL_DIR" ]]; then
  $SUDO mkdir -p "$INSTALL_DIR"
  $SUDO rsync -a --delete --exclude ".git" "$SRC_DIR"/ "$INSTALL_DIR"/
fi

echo "[3/6] Creating virtual environment..."
$PYTHON_BIN -m venv "$INSTALL_DIR/.venv"

echo "[4/6] Installing Python dependencies..."
"$INSTALL_DIR/.venv/bin/pip" install -U pip
"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

if [[ "$INSTALL_TORCH" == "1" ]]; then
  echo "[5/6] Installing PyTorch (CPU by default)..."
  "$INSTALL_DIR/.venv/bin/pip" install torch torchvision
else
  echo "[5/6] Skipping PyTorch install (set INSTALL_TORCH=1 if needed)."
fi

if [[ "$ENABLE_SYSTEMD" == "1" ]]; then
  echo "[6/6] Installing systemd service..."
  SERVICE_PATH="/etc/systemd/system/pidvn25006.service"
  ENV_PATH="/etc/pidvn25006.env"

  $SUDO tee "$SERVICE_PATH" >/dev/null <<EOF
[Unit]
Description=PIDVN25006 Monitor
After=network.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/.venv/bin/python ${INSTALL_DIR}/main_monitor_gui.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-${ENV_PATH}

[Install]
WantedBy=multi-user.target
EOF

  if [[ ! -f "$ENV_PATH" ]]; then
    $SUDO tee "$ENV_PATH" >/dev/null <<EOF
# Example:
# RTSP_PASS=your_password
EOF
  fi

  $SUDO systemctl daemon-reload
  $SUDO systemctl enable pidvn25006
  $SUDO systemctl restart pidvn25006
  $SUDO systemctl status pidvn25006 --no-pager
else
  echo "[6/6] systemd not enabled (set ENABLE_SYSTEMD=1 to install)."
fi

echo "Done. Project installed at ${INSTALL_DIR}."
