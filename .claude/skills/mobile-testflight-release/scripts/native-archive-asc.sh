#!/bin/bash
# Legacy compatibility shim. The previous implementation mutated app.json,
# sourced the repository production environment, generated signing profiles,
# wrote predictable /tmp artifacts, and uploaded directly outside the release
# coordinator. Route every production iOS build through the guarded authority.

# Production-native publishing is frozen until a trusted external launcher can
# establish source authority and a release lease. Keep this above dirname/cd.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  printf '%s\n' 'Production native archive is frozen; use the manual Gate.' >&2
  exit 78
fi

if [[ 0 -eq 1 ]]; then
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../../.." && pwd)"
CONTROLLED_TESTFLIGHT="${REPO}/scripts/_run-mobile-tf.sh"

if [ ! -x "${CONTROLLED_TESTFLIGHT}" ]; then
  echo "✗ 受控 iOS 原生构建入口不存在: ${CONTROLLED_TESTFLIGHT}" >&2
  exit 1
fi

exec "${CONTROLLED_TESTFLIGHT}" remote
fi
