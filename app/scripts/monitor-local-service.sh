#!/bin/zsh
set -u

PORT="${JOB_ASSISTANT_PORT:-8787}"
HEALTH_URL="http://127.0.0.1:${PORT}/api/health"

if curl -fsS --max-time 3 "${HEALTH_URL}" >/dev/null 2>&1; then
  exit 0
fi

/usr/bin/open -gja Terminal "${HOME}/.job-assistant-app/Start-Job-Assistant-Background.command"
