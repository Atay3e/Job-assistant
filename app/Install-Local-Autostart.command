#!/bin/zsh
set -eu

APP_DIR="${0:A:h}"
LABEL="com.jobassistant.local"
DOMAIN="gui/$(id -u)"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
TEMPLATE="${APP_DIR}/scripts/${LABEL}.plist.template"
SERVICE_ROOT="${HOME}/.job-assistant-app"
SERVICE_DIR="${HOME}/Library/Application Support/JobAssistant"
SERVICE_LOG_DIR="${HOME}/Library/Logs/JobAssistant"
MONITOR_SCRIPT="${SERVICE_DIR}/monitor-local-service.sh"
URL="http://127.0.0.1:${JOB_ASSISTANT_PORT:-8787}/api/health"

mkdir -p "${HOME}/Library/LaunchAgents" "${APP_DIR}/logs" "${SERVICE_DIR}" "${SERVICE_LOG_DIR}"
chmod +x "${APP_DIR}/Open-Job-Assistant.command" "${APP_DIR}/Start-Job-Assistant-Background.command" "${APP_DIR}/scripts/monitor-local-service.sh"
ln -sfn "${APP_DIR}" "${SERVICE_ROOT}"
cp "${APP_DIR}/scripts/monitor-local-service.sh" "${MONITOR_SCRIPT}"
chmod +x "${MONITOR_SCRIPT}"

launchctl bootout "${DOMAIN}/${LABEL}" >/dev/null 2>&1 || true

listener_pid="$(lsof -tiTCP:"${JOB_ASSISTANT_PORT:-8787}" -sTCP:LISTEN -n -P 2>/dev/null | head -n 1 || true)"
if [[ -n "${listener_pid}" ]]; then
  command_line="$(ps -p "${listener_pid}" -o command= 2>/dev/null || true)"
  if [[ "${command_line}" == *"server.py"* ]]; then
    kill "${listener_pid}" >/dev/null 2>&1 || true
    sleep 0.5
  else
    printf "Port %s is occupied by another app: %s\n" "${JOB_ASSISTANT_PORT:-8787}" "${command_line}"
    exit 1
  fi
fi

escaped_monitor_script="${MONITOR_SCRIPT//&/\\&}"
escaped_home="${HOME//&/\\&}"
escaped_log_dir="${SERVICE_LOG_DIR//&/\\&}"
sed -e "s|__MONITOR_SCRIPT__|${escaped_monitor_script}|g" -e "s|__HOME__|${escaped_home}|g" -e "s|__LOG_DIR__|${escaped_log_dir}|g" "${TEMPLATE}" > "${PLIST}"
plutil -lint "${PLIST}" >/dev/null
launchctl bootstrap "${DOMAIN}" "${PLIST}"
launchctl enable "${DOMAIN}/${LABEL}"
launchctl kickstart -k "${DOMAIN}/${LABEL}"

for _ in {1..40}; do
  if curl -fsS --max-time 2 "${URL}" >/dev/null 2>&1; then
    printf "Job Assistant will now start automatically and recover after unexpected exits.\n"
    printf "Open: http://127.0.0.1:%s/\n" "${JOB_ASSISTANT_PORT:-8787}"
    exit 0
  fi
  sleep 0.5
done

printf "The service was installed but did not become ready. Check %s\n" "${SERVICE_LOG_DIR}/service.err.log"
exit 1
