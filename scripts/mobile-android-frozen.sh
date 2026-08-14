#!/bin/bash
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
set -euo pipefail

builtin printf '%s\n' \
  'Android native build/sign/install entrypoint is frozen; use static and JavaScript tests only.' >&2
exit 78
fi
