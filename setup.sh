#!/usr/bin/env bash
set -euo pipefail

APP_NAME="airsoft-suitcase"
SERVICE_NAME="airsoft-suitcase"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GAME_USER="${AIRSOFT_GAME_USER:-${SUDO_USER:-pi}}"
HOME_DIR="/home/${GAME_USER}"
GAME_UID=""
SERVICE_RUN_AS_ROOT="${AIRSOFT_SERVICE_RUN_AS_ROOT:-1}"
REQUIRE_NEOPIXEL="${AIRSOFT_REQUIRE_NEOPIXEL:-1}"
SERVICE_USER=""
SERVICE_GROUP=""
SERVICE_HOME=""
VENV_DIR="${HOME_DIR}/.local/share/${APP_NAME}/venv"
PYTHON_BIN="${VENV_DIR}/bin/python"
PIP_BIN="${VENV_DIR}/bin/pip"
RUN_GAME_SCRIPT="${ROOT_DIR}/scripts/run_game.py"
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
  GAME_UID="$(id -u "${GAME_USER}")"
}

configure_service_identity() {
  if [ "${SERVICE_RUN_AS_ROOT}" = "1" ]; then
    SERVICE_USER="root"
    SERVICE_GROUP="root"
    # Keep HOME/XAUTHORITY on the desktop user for display session access.
    SERVICE_HOME="${HOME_DIR}"
    return
  fi

  SERVICE_USER="${GAME_USER}"
  SERVICE_GROUP="${GAME_USER}"
  SERVICE_HOME="${HOME_DIR}"
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
  if [ -d "${VENV_DIR}" ]; then
    log "Removing existing virtualenv for clean redeploy"
    rm -rf "${VENV_DIR}"
  fi
  sudo -u "${GAME_USER}" mkdir -p "$(dirname "${VENV_DIR}")"
  sudo -u "${GAME_USER}" python3 -m venv "${VENV_DIR}"
  sudo -u "${GAME_USER}" "${PIP_BIN}" install --upgrade pip setuptools wheel
  sudo -u "${GAME_USER}" "${PIP_BIN}" install --no-cache-dir "${ROOT_DIR}[pi]"
}

verify_project_files() {
  if [ ! -f "${RUN_GAME_SCRIPT}" ]; then
    fail "Launcher script not found: ${RUN_GAME_SCRIPT}"
  fi
}

clean_existing_service() {
  local unit="${SERVICE_NAME}.service"
  local dropin_dir="${SERVICE_PATH}.d"

  log "Stopping existing service (if running)"
  systemctl stop "${unit}" >/dev/null 2>&1 || true

  log "Disabling existing service (if enabled)"
  systemctl disable "${unit}" >/dev/null 2>&1 || true

  systemctl reset-failed "${unit}" >/dev/null 2>&1 || true

  if [ -f "${SERVICE_PATH}" ] || [ -L "${SERVICE_PATH}" ]; then
    log "Removing existing unit file ${SERVICE_PATH}"
    rm -f "${SERVICE_PATH}"
  fi

  if [ -d "${dropin_dir}" ]; then
    log "Removing existing systemd drop-ins ${dropin_dir}"
    rm -rf "${dropin_dir}"
  fi

  systemctl daemon-reload
}

write_unit_file() {
  log "Creating systemd unit ${SERVICE_PATH}"
  cat >"${SERVICE_PATH}" <<EOF
[Unit]
Description=Airsoft Suitcase Game
After=multi-user.target network-online.target graphical.target
Wants=network-online.target graphical.target

[Service]
User=${SERVICE_USER}
Group=${SERVICE_GROUP}
WorkingDirectory=${ROOT_DIR}
Environment="HOME=${SERVICE_HOME}"
Environment="DISPLAY=:0"
Environment="XAUTHORITY=${HOME_DIR}/.Xauthority"
Environment="XDG_RUNTIME_DIR=/run/user/${GAME_UID}"
Environment="AIRSOFT_NO_BROWSER=1"
Environment="AIRSOFT_UI=auto"
Environment="AIRSOFT_REQUIRE_NEOPIXEL=${REQUIRE_NEOPIXEL}"
Type=simple
Restart=always
RestartSec=5
ExecStartPre=/usr/bin/sleep 5
ExecStart=${PYTHON_BIN} ${RUN_GAME_SCRIPT}
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
  log "Service command: ${PYTHON_BIN} ${RUN_GAME_SCRIPT}"
  log "Service user: ${SERVICE_USER}"
  log "Require NeoPixel: ${REQUIRE_NEOPIXEL}"
  if [ "${REBOOT_NEEDED}" -eq 1 ]; then
    log "Reboot to apply read-only overlay mode."
  fi
}

main() {
  require_root
  require_user
  configure_service_identity
  install_dependencies
  clean_existing_service
  setup_venv
  verify_project_files
  write_unit_file
  enable_service
  enable_read_only_mode
  summary
}

main "$@"
