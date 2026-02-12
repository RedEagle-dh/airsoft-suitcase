#!/usr/bin/env bash
set -euo pipefail

APP_NAME="airsoft-suitcase"
SERVICE_NAME="airsoft-suitcase"
KEYPAD_SERVICE_NAME="${SERVICE_NAME}-keypad"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GAME_USER="${AIRSOFT_GAME_USER:-${SUDO_USER:-pi}}"
HOME_DIR="/home/${GAME_USER}"
GAME_UID=""
SERVICE_RUN_AS_ROOT="${AIRSOFT_SERVICE_RUN_AS_ROOT:-1}"
REQUIRE_NEOPIXEL="${AIRSOFT_REQUIRE_NEOPIXEL:-1}"
AUDIO_DEVICE="${AIRSOFT_AUDIO_DEVICE:-}"
SERVICE_USER=""
SERVICE_GROUP=""
SERVICE_HOME=""
XDG_ENV_LINE=""
VENV_DIR="${HOME_DIR}/.local/share/${APP_NAME}/venv"
PYTHON_BIN="${VENV_DIR}/bin/python"
PIP_BIN="${VENV_DIR}/bin/pip"
RUN_GAME_SCRIPT="${ROOT_DIR}/scripts/run_game.py"
RUN_KEYPAD_SCRIPT="${ROOT_DIR}/scripts/run_keypad_adapter.py"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
KEYPAD_SERVICE_PATH="/etc/systemd/system/${KEYPAD_SERVICE_NAME}.service"
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
    SERVICE_HOME="/root"
    XDG_ENV_LINE="Environment=\"XDG_RUNTIME_DIR=/tmp\""
    return
  fi

  SERVICE_USER="${GAME_USER}"
  SERVICE_GROUP="${GAME_USER}"
  SERVICE_HOME="${HOME_DIR}"
  XDG_ENV_LINE="Environment=\"XDG_RUNTIME_DIR=/run/user/${GAME_UID}\""
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
    alsa-utils \
    mpg123
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
  if [ ! -f "${RUN_KEYPAD_SCRIPT}" ]; then
    fail "Keypad adapter script not found: ${RUN_KEYPAD_SCRIPT}"
  fi
}

clean_unit() {
  local unit_name="$1"
  local unit_path="$2"
  local unit="${unit_name}.service"
  local dropin_dir="${unit_path}.d"

  log "Stopping ${unit} (if running)"
  systemctl stop "${unit}" >/dev/null 2>&1 || true

  log "Disabling ${unit} (if enabled)"
  systemctl disable "${unit}" >/dev/null 2>&1 || true

  systemctl reset-failed "${unit}" >/dev/null 2>&1 || true

  if [ -f "${unit_path}" ] || [ -L "${unit_path}" ]; then
    log "Removing existing unit file ${unit_path}"
    rm -f "${unit_path}"
  fi

  if [ -d "${dropin_dir}" ]; then
    log "Removing existing systemd drop-ins ${dropin_dir}"
    rm -rf "${dropin_dir}"
  fi
}

clean_existing_services() {
  clean_unit "${SERVICE_NAME}" "${SERVICE_PATH}"
  clean_unit "${KEYPAD_SERVICE_NAME}" "${KEYPAD_SERVICE_PATH}"
  systemctl daemon-reload
}

write_game_unit_file() {
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
${XDG_ENV_LINE}
Environment="AIRSOFT_NO_BROWSER=1"
Environment="AIRSOFT_UI=auto"
Environment="AIRSOFT_REQUIRE_NEOPIXEL=${REQUIRE_NEOPIXEL}"
Environment="AIRSOFT_AUDIO_DEVICE=${AUDIO_DEVICE}"
Environment="SDL_AUDIODRIVER=alsa"
Type=simple
Restart=always
RestartSec=5
TimeoutStopSec=15
ExecStartPre=/usr/bin/sleep 5
ExecStart=${PYTHON_BIN} ${RUN_GAME_SCRIPT}
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

  chmod 644 /etc/systemd/system/${SERVICE_NAME}.service
}

write_keypad_unit_file() {
  log "Creating systemd unit ${KEYPAD_SERVICE_PATH}"
  cat >"${KEYPAD_SERVICE_PATH}" <<EOF
[Unit]
Description=Airsoft Suitcase Keypad Adapter
After=multi-user.target network-online.target graphical.target ${SERVICE_NAME}.service
Wants=network-online.target graphical.target
PartOf=${SERVICE_NAME}.service

[Service]
User=${SERVICE_USER}
Group=${SERVICE_GROUP}
WorkingDirectory=${ROOT_DIR}
Environment="HOME=${SERVICE_HOME}"
Environment="DISPLAY=:0"
Environment="XAUTHORITY=${HOME_DIR}/.Xauthority"
${XDG_ENV_LINE}
Type=simple
Restart=always
RestartSec=2
TimeoutStopSec=10
ExecStartPre=/usr/bin/sleep 2
ExecStart=${PYTHON_BIN} ${RUN_KEYPAD_SCRIPT}
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

  chmod 644 /etc/systemd/system/${KEYPAD_SERVICE_NAME}.service
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
  log "Enabling and starting systemd units"
  systemctl daemon-reload
  systemctl enable --now "${SERVICE_PATH##*/}" "${KEYPAD_SERVICE_PATH##*/}"
}

summary() {
  log "Setup complete."
  log "Game service: ${SERVICE_NAME}.service"
  log "Keypad service: ${KEYPAD_SERVICE_NAME}.service"
  log "Service command: ${PYTHON_BIN} ${RUN_GAME_SCRIPT}"
  log "Keypad command: ${PYTHON_BIN} ${RUN_KEYPAD_SCRIPT}"
  log "Service user: ${SERVICE_USER}"
  log "Require NeoPixel: ${REQUIRE_NEOPIXEL}"
  log "Audio device: ${AUDIO_DEVICE:-auto}"
  if [ "${REBOOT_NEEDED}" -eq 1 ]; then
    log "Reboot to apply read-only overlay mode."
  fi
}

main() {
  require_root
  require_user
  configure_service_identity
  install_dependencies
  clean_existing_services
  setup_venv
  verify_project_files
  write_game_unit_file
  write_keypad_unit_file
  enable_service
  enable_read_only_mode
  summary
}

main "$@"
