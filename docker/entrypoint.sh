#!/usr/bin/env bash
set -euo pipefail

cd /app

export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/app/.playwright-browsers}"
MARKER="${PLAYWRIGHT_BROWSERS_PATH}/.chromium-installed"

# The image already contains Chromium. Reinstalling on every Cloud Run start
# blows the startup timeout. Only install when the browser binary is missing.
if [[ ! -f "${MARKER}" ]] && ! find "${PLAYWRIGHT_BROWSERS_PATH}" -type f -name chrome -print -quit 2>/dev/null | grep -q .; then
  echo "Installing Playwright Chromium to ${PLAYWRIGHT_BROWSERS_PATH}…"
  mkdir -p "${PLAYWRIGHT_BROWSERS_PATH}"
  playwright install chromium
  touch "${MARKER}"
fi

mkdir -p workspace automation_output logs models

exec python run.py
