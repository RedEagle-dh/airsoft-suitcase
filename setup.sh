#!/usr/bin/env bash
set -euo pipefail

APP_NAME="airsoft-suitcase"
SERVICE_NAME="airsoft-suitcase"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GAME_USER="${AIRSOFT_GAME_USER:-${SUDO_USER:-pi}}"
HOME_DIR="/home/${GAME_USER}"
VENV_DIR="${HOME_DIR}/.local/share/${APP_NAME}/venv"
PYTHON_BIN="${VENV_DIR}/bin/python"
PIP_BIN="${VENV_DIR}/bin/pip"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
SETUP_READ_ONLY="${AIRSOFT_SETUP_READ_ONLY:-1}"
REBOOT_NEEDED=0

log() {
  printf '[setup] %s\n' "$*"
}

fail() {
  printf '[setup] ERROR: %s\n' "$*" >&2
  exit 1
}

require_root() {
  if [ "${EUID}" -ne 0 ]; then
    fail "Run this script as root (for example: sudo ./setup.sh)"
  fi
}

require_user() {
  if ! id "${GAME_USER}" >/dev/null 2>&1; then
    fail "User '${GAME_USER}' does not exist."
  fi
}

install_dependencies() {
  log "Updating apt index and installing OS packages"
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3 \
    python3-venv \
    python3-pip \
    python3-tk \
    python3-dev \
    git \
    alsa-utils
}

setup_venv() {
  log "Preparing virtualenv at ${VENV_DIR}"
  sudo -u "${GAME_USER}" mkdir -p "${VENV_DIR}"
  sudo -u "${GAME_USER}" python3 -m venv "${VENV_DIR}"
  sudo -u "${GAME_USER}" "${PIP_BIN}" install --upgrade pip setuptools wheel
  sudo -u "${GAME_USER}" "${PIP_BIN}" install --no-cache-dir "${ROOT_DIR}[pi]"
}

write_unit_file() {
  log "Creating systemd unit ${SERVICE_PATH}"
  cat >"${SERVICE_PATH}" <<EOF
[Unit]
Description=Airsoft Suitcase Game
After=multi-user.target network-online.target graphical.target
Wants=network-online.target graphical.target

[Service]
User=${GAME_USER}
Group=${GAME_USER}
WorkingDirectory=${ROOT_DIR}
Environment="HOME=${HOME_DIR}"
Environment="DISPLAY=:0"
Environment="XAUTHORITY=${HOME_DIR}/.Xauthority"
Environment="AIRSOFT_NO_BROWSER=1"
Environment="AIRSOFT_UI=auto"
Type=simple
Restart=always
RestartSec=5
ExecStartPre=/usr/bin/sleep 5
ExecStart=${PYTHON_BIN} -m airsoft_suitcase
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

  chmod 644 /etc/systemd/system/${SERVICE_NAME}.service
}

enable_read_only_mode() {
  if [ "${SETUP_READ_ONLY}" != "1" ]; then
    log "Skipping read-only setup (AIRSOFT_SETUP_READ_ONLY not set to 1)"
    return
  fi

  if command -v raspi-config >/dev/null 2>&1; then
    log "Enabling overlay-based read-only mode via raspi-config"
    if raspi-config nonint do_overlayfs 1; then
      log "Read-only overlay mode requested. Reboot is required."
      REBOOT_NEEDED=1
      return
    fi
  fi

  log "Read-only automation via raspi-config not available; leaving filesystem in current mode."
}

enable_service() {
  log "Enabling and starting systemd unit"
  systemctl daemon-reload
  systemctl enable --now "${SERVICE_PATH##*/}"
}

summary() {
  log "Setup complete."
  log "Game service: ${SERVICE_NAME}.service"
  log "Service command: ${PYTHON_BIN} -m airsoft_suitcase"
  if [ "${REBOOT_NEEDED}" -eq 1 ]; then
    log "Reboot to apply read-only overlay mode."
  fi
}

main() {
  require_root
  require_user
  install_dependencies
  setup_venv
  write_unit_file
  enable_service
  enable_read_only_mode
  summary
}

main "$@"
