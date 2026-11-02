#!/usr/bin/env bash
# Create .venv with uv (Python 3.12) and install project deps.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="${UV_PYTHON:-3.12}"

if [[ -d .venv ]] && [[ ! -f .venv/bin/activate ]]; then
  echo "Removing broken .venv…"
  rm -rf .venv
fi

if [[ -d .venv ]]; then
  echo ".venv already exists"
else
  uv venv .venv --python "$PY"
  echo "Created .venv (Python $PY)"
fi

# Register for the venv picker
mkdir -p "$HOME/.config"
grep -qxF "$ROOT" "$HOME/.config/project-venvs.list" 2>/dev/null || echo "$ROOT" >> "$HOME/.config/project-venvs.list"

# shellcheck disable=SC1091
source .venv/bin/activate

uv pip install -r requirements.txt
if [[ -f requirements-image.txt ]]; then
  echo "Installing image deps (torch, diffusers)…"
  uv pip install -r requirements-image.txt
fi

echo ""
python -V
python -c "from app.pipeline import sana; print(sana.probe_sana())" 2>/dev/null || true
