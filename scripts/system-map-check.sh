#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REQUIREMENTS="$ROOT/scripts/system-map-requirements.txt"
VENV_DIR="$ROOT/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
STAMP="$VENV_DIR/.system-map-requirements.sha256"

if ! PYTHON_BIN="$(command -v python3.12)"; then
  echo "System Map check requires python3.12; install Python 3.12 and retry." >&2
  exit 2
fi

REQUIREMENTS_HASH="$(
  "$PYTHON_BIN" -c 'import hashlib, pathlib, sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' "$REQUIREMENTS"
)"

if [[ ! -x "$VENV_PYTHON" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

INSTALLED_HASH=""
if [[ -f "$STAMP" ]]; then
  INSTALLED_HASH="$("$VENV_PYTHON" -c 'import pathlib, sys; print(pathlib.Path(sys.argv[1]).read_text().strip())' "$STAMP")"
fi
if [[ "$INSTALLED_HASH" != "$REQUIREMENTS_HASH" ]]; then
  "$VENV_PYTHON" -m pip install --disable-pip-version-check -r "$REQUIREMENTS"
  "$VENV_PYTHON" -c 'import pathlib, sys; pathlib.Path(sys.argv[1]).write_text(sys.argv[2] + "\n")' "$STAMP" "$REQUIREMENTS_HASH"
fi

cd "$ROOT"
exec "$VENV_PYTHON" "$ROOT/scripts/check_system_map.py"
