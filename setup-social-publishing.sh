#!/usr/bin/env sh
set -eu

CURRENT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$CURRENT_DIR"

PROJECT_PYTHON="$CURRENT_DIR/.venv/bin/python"
if [ ! -x "$PROJECT_PYTHON" ]; then
  echo "[ERROR] MoneyPrinterTurbo project environment was not found."
  echo "Run ./webui.sh once first so the .venv environment is created."
  exit 1
fi

echo "============================================================"
echo "MoneyPrinterTurbo - Local Social Publishing Runtime Setup"
echo "============================================================"
echo "This installs a separate uploader environment under:"
echo "  storage/social-auto-upload/"
echo "It does NOT modify the MoneyPrinterTurbo project environment."
echo

"$PROJECT_PYTHON" "$CURRENT_DIR/scripts/setup_social_auto_upload.py"

echo
echo "[OK] Local social publishing runtime is ready."
echo "Restart ./webui.sh, then open Social Publishing > Accounts and Runtime."
