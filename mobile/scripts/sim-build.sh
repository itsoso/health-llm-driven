#!/usr/bin/env bash
# Compatibility entrypoint for an iOS Simulator-only build. The root wrapper
# owns exact simctl membership validation and never accepts a physical device.
set -euo pipefail

if [[ "$#" -gt 1 ]]; then
  builtin printf '%s\n' 'Usage: ./scripts/sim-build.sh [simulator-name-or-udid]' >&2
  exit 2
fi

SIM="${1:-iPhone 17 Pro}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_WRAPPER="$(cd "${SCRIPT_DIR}/../.." && pwd)/scripts/sim-build.sh"
exec "${ROOT_WRAPPER}" --current-tree --device "${SIM}"
