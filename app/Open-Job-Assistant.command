#!/bin/zsh
set -u

APP_DIR="${0:A:h}"
HOST_NAME="${JOB_ASSISTANT_HOST:-127.0.0.1}"
PORT="${JOB_ASSISTANT_PORT:-8787}"
URL="http://${HOST_NAME}:${PORT}/"
LOG_DIR="${APP_DIR}/logs"
PID_FILE="${LOG_DIR}/job-assistant.pid"
OPEN_BROWSER=1

if [[ "${1:-}" == "--no-open" ]]; then
  OPEN_BROWSER=0
fi

mkdir -p "${LOG_DIR}"

log() {
  printf "%s %s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "${LOG_DIR}/launcher.log"
}

is_ready() {
  curl -fsS --max-time 4 "${URL}" >/dev/null 2>&1
}

python_path() {
  if [[ -x "${APP_DIR}/.venv/bin/python" ]]; then
    printf "%s\n" "${APP_DIR}/.venv/bin/python"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return 0
  fi
  return 1
}

listener_pid() {
  lsof -tiTCP:"${PORT}" -sTCP:LISTEN -n -P 2>/dev/null | head -n 1
}

stop_stale_job_assistant() {
  local pid="$1"
  local command_line
  command_line="$(ps -p "${pid}" -o command= 2>/dev/null || true)"

  if [[ "${command_line}" != *"server.py"* ]]; then
    log "Port ${PORT} is in use by another process: ${command_line}"
    printf "Port %s is already used by another app.\n" "${PORT}"
    printf "Close that app or set JOB_ASSISTANT_PORT to another port.\n"
    exit 1
  fi

  log "Stopping stale Job Assistant process ${pid}"
  kill "${pid}" >/dev/null 2>&1 || true
  for _ in {1..20}; do
    if ! kill -0 "${pid}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.2
  done
}

start_server() {
  local py
  if ! py="$(python_path)"; then
    log "Python was not found on PATH"
    printf "Cannot find python3. Install Python or add it to PATH.\n"
    exit 1
  fi

  log "Starting Job Assistant with ${py}"
  (
    cd "${APP_DIR}" || exit 1
    nohup "${py}" server.py >> "${LOG_DIR}/server.out.log" 2>> "${LOG_DIR}/server.err.log" &
    printf "%s" "$!" > "${PID_FILE}"
  )
}

if ! is_ready; then
  current_pid="$(listener_pid || true)"
  if [[ -n "${current_pid}" ]]; then
    stop_stale_job_assistant "${current_pid}"
  fi

  start_server

  for _ in {1..40}; do
    if is_ready; then
      break
    fi
    sleep 0.5
  done
fi

if ! is_ready; then
  log "Job Assistant did not become ready"
  printf "Job Assistant did not start. Check:\n%s\n" "${LOG_DIR}/server.err.log"
  exit 1
fi

log "Job Assistant is ready at ${URL}"
printf "Job Assistant is ready: %s\n" "${URL}"

if [[ "${OPEN_BROWSER}" == "1" ]]; then
  open "${URL}"
fi
