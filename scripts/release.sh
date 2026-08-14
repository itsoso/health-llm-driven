#!/bin/bash

# Sourcing this compatibility wrapper must never alter the caller.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  return 0
fi

set -euo pipefail

# Production release operations need a repository-external trusted launcher.
# Keep exact help and the fail-closed guard above dirname, cd, and Python.
if [[ "$#" -eq 1 && ( "$1" == "-h" || "$1" == "--help" ) ]]; then
  builtin printf '%s\n' \
    'Usage: ./scripts/release.sh -h|--help' \
    'Production release CLI is frozen (exit 78); use the manual Gate.'
  exit 0
fi
builtin printf '%s\n' 'Production release CLI is frozen; use the manual Gate.' >&2
exit 78
