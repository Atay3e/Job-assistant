#!/bin/zsh
set -eu

APP_DIR="${0:A:h}"
exec "${APP_DIR}/Open-Job-Assistant.command" --no-open
