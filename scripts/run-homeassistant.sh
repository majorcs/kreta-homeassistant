#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv-ha"
CONFIG_DIR="$ROOT_DIR/.homeassistant-dev"
PID_FILE="$CONFIG_DIR/homeassistant.pid"
LOG_FILE="$CONFIG_DIR/homeassistant.log"
CUSTOM_COMPONENTS_LINK="$CONFIG_DIR/custom_components"
REQUIREMENTS_FILE="$ROOT_DIR/requirements-ha.txt"
VENV_STAMP="$VENV_DIR/.requirements-installed"

ACTION="${1:-start}"

pick_python() {
  local candidate
  for candidate in python3.13 python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      local version
      version="$("$candidate" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
      case "$version" in
        3.12|3.13|3.14)
          printf '%s\n' "$candidate"
          return 0
          ;;
      esac
    fi
  done

  printf 'No supported Python interpreter found. Install python3.12, python3.13, or a compatible python3.\n' >&2
  return 1
}

ensure_venv() {
  local python_bin
  python_bin="$(pick_python)"

  if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    "$python_bin" -m venv "$VENV_DIR"
  fi

  if [[ ! -f "$VENV_STAMP" || "$REQUIREMENTS_FILE" -nt "$VENV_STAMP" ]]; then
    "$VENV_DIR/bin/python" -m pip install --upgrade pip wheel >/dev/null
    "$VENV_DIR/bin/python" -m pip install -r "$REQUIREMENTS_FILE" >/dev/null
    touch "$VENV_STAMP"
  fi
}

ensure_config() {
  mkdir -p "$CONFIG_DIR"

  if [[ ! -f "$CONFIG_DIR/configuration.yaml" ]]; then
    cat >"$CONFIG_DIR/configuration.yaml" <<'EOF'
default_config:

logger:
  default: info
EOF
  fi

  ln -sfn "$ROOT_DIR/custom_components" "$CUSTOM_COMPONENTS_LINK"
}

managed_pid() {
  if [[ ! -f "$PID_FILE" ]]; then
    return 1
  fi

  local pid
  pid="$(<"$PID_FILE")"
  if [[ -z "$pid" ]] || ! [[ "$pid" =~ ^[0-9]+$ ]]; then
    rm -f "$PID_FILE"
    return 1
  fi

  if [[ ! -d "/proc/$pid" ]]; then
    rm -f "$PID_FILE"
    return 1
  fi

  local cmdline
  cmdline="$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null || true)"
  if [[ "$cmdline" != *"$CONFIG_DIR"* ]]; then
    return 1
  fi

  printf '%s\n' "$pid"
}

stop_instance() {
  local pid
  if ! pid="$(managed_pid)"; then
    printf 'No running script-managed Home Assistant instance found.\n'
    rm -f "$PID_FILE"
    return 0
  fi

  printf 'Stopping Home Assistant instance with PID %s...\n' "$pid"
  kill "$pid"

  local waited=0
  while [[ -d "/proc/$pid" && $waited -lt 30 ]]; do
    sleep 1
    waited=$((waited + 1))
  done

  if [[ -d "/proc/$pid" ]]; then
    printf 'Process %s did not stop in time, sending SIGKILL.\n' "$pid"
    kill -KILL "$pid"
  fi

  rm -f "$PID_FILE"
  printf 'Home Assistant stopped.\n'
}

start_instance() {
  ensure_venv
  ensure_config

  if managed_pid >/dev/null; then
    stop_instance
  fi

  printf 'Starting Home Assistant using %s...\n' "$VENV_DIR"
  nohup "$VENV_DIR/bin/hass" -c "$CONFIG_DIR" >"$LOG_FILE" 2>&1 &
  local pid=$!
  printf '%s\n' "$pid" >"$PID_FILE"

  sleep 5
  if ! [[ -d "/proc/$pid" ]]; then
    printf 'Home Assistant failed to start. Recent log output:\n' >&2
    tail -n 50 "$LOG_FILE" >&2 || true
    rm -f "$PID_FILE"
    return 1
  fi

  printf 'Home Assistant started with PID %s.\n' "$pid"
  printf 'Config directory: %s\n' "$CONFIG_DIR"
  printf 'Log file: %s\n' "$LOG_FILE"
  printf 'Open http://127.0.0.1:8123 once startup completes.\n'
}

status_instance() {
  local pid
  if pid="$(managed_pid)"; then
    printf 'Home Assistant is running with PID %s.\n' "$pid"
    printf 'Config directory: %s\n' "$CONFIG_DIR"
    printf 'Log file: %s\n' "$LOG_FILE"
    return 0
  fi

  printf 'Home Assistant is not running.\n'
}

case "$ACTION" in
  start)
    start_instance
    ;;
  stop)
    stop_instance
    ;;
  restart)
    stop_instance
    start_instance
    ;;
  status)
    status_instance
    ;;
  *)
    printf 'Usage: %s [start|stop|restart|status]\n' "$0" >&2
    exit 1
    ;;
esac
