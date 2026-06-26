#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
cd "${SCRIPT_DIR}"

PYTHON="${SCRIPT_DIR}/.venv/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="$(command -v python3)"
fi

"${PYTHON}" scripts/prepare_supabase_setup.py

echo ""
echo "Supabase setup template is ready."
echo "After filling app/.env.supabase.local, tell Codex: 好了"
echo ""
read -r "?Press Enter to close..."
