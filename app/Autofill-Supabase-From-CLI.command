#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
cd "${SCRIPT_DIR}"

PYTHON="${SCRIPT_DIR}/.venv/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="$(command -v python3)"
fi

"${PYTHON}" scripts/autofill_supabase_from_cli.py

echo ""
echo "Supabase values were written to Render. Tell Codex: 好了"
echo ""
read -r "?Press Enter to close..."
