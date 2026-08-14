#!/bin/bash
# Legacy compatibility shim. Local production archives and direct uploads used
# to bypass clean-source, release-lock, and recovery gates. Keep one controlled
# native build authority instead.

# Production-native publishing is frozen until a trusted external launcher can
# establish source authority and a release lease. Keep this above dirname/cd.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  printf '%s\n' 'Production native archive is frozen; use the manual Gate.' >&2
  exit 78
fi

if [[ 0 -eq 1 ]]; then
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONTROLLED_TESTFLIGHT="${REPO_ROOT}/scripts/_run-mobile-tf.sh"

if [ ! -x "${CONTROLLED_TESTFLIGHT}" ]; then
  echo "✗ 受控 iOS 原生构建入口不存在: ${CONTROLLED_TESTFLIGHT}" >&2
  exit 1
fi

exec "${CONTROLLED_TESTFLIGHT}" remote
fi
