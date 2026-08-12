#!/usr/bin/env sh
set -eu

CURRENT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$CURRENT_DIR"

if [ ! -f "$CURRENT_DIR/scripts/run_webui.py" ]; then
  echo "[ERROR] scripts/run_webui.py was not found."
  echo "Run: git pull origin main"
  exit 1
fi

PROJECT_PYTHON="$CURRENT_DIR/.venv/bin/python"
if command -v uv >/dev/null 2>&1; then
  echo "***** Syncing this checkout from uv.lock... *****"
  uv sync --frozen
elif [ ! -x "$PROJECT_PYTHON" ]; then
  echo "[ERROR] uv is required for the first local run but was not found."
  echo "Install uv from: https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
else
  echo "***** WARNING: uv was not found; using the existing .venv without dependency sync. *****"
fi

if [ ! -x "$PROJECT_PYTHON" ]; then
  echo "[ERROR] Project Python was not created: $PROJECT_PYTHON"
  exit 1
fi

exec "$PROJECT_PYTHON" "$CURRENT_DIR/scripts/run_webui.py"
