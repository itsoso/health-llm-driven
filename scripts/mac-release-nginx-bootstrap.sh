#!/bin/bash
# Formal Mac download-route mutation remains outside the automated release
# boundary until the unified remote transaction has a frozen, independently
# reviewed recovery contract.  This guard intentionally precedes path
# resolution, lock inspection and SSH setup so caller-controlled environment
# variables cannot turn the legacy wrapper into a production mutation path.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo "Mac production route mutation is frozen; use the manual infrastructure Gate." >&2
  exit 78
fi

if [[ 0 -eq 1 ]]; then
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SERVER="root@39.98.206.178"
HOST_KEY="39.98.206.178 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIC6Wg0sU8uYKL4xq1HCCpPxTPy24LOxvzr2uSpycraav"
PYTHON_HELPER="${SCRIPT_DIR}/mac_release_nginx_bootstrap.py"
ROUTE_SNIPPET="${REPO_ROOT}/infra/nginx/mac-release-routes.conf"
SSH_OPTIONS=(
  "-F" "/dev/null"
  "-o" "BatchMode=yes"
  "-o" "PasswordAuthentication=no"
  "-o" "KbdInteractiveAuthentication=no"
  "-o" "StrictHostKeyChecking=yes"
  "-o" "UserKnownHostsFile=/dev/null"
  "-o" "GlobalKnownHostsFile=/dev/null"
  "-o" "KnownHostsCommand=/usr/bin/printf 39.98.206.178\\ ssh-ed25519\\ AAAAC3NzaC1lZDI1NTE5AAAAIC6Wg0sU8uYKL4xq1HCCpPxTPy24LOxvzr2uSpycraav\\n"
  "-o" "ConnectionAttempts=1"
  "-o" "ConnectTimeout=15"
  "-o" "RequestTTY=no"
)

usage() {
  echo "Usage: scripts/mac-release-nginx-bootstrap.sh apply|rollback" >&2
}

[[ -f "${PYTHON_HELPER}" && ! -L "${PYTHON_HELPER}" ]] || {
  echo "Mac nginx bootstrap helper is missing or unsafe" >&2
  exit 1
}
[[ "${HOST_KEY}" == "39.98.206.178 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIC6Wg0sU8uYKL4xq1HCCpPxTPy24LOxvzr2uSpycraav" ]] || exit 1
[[ "${REVA_MAC_BOOTSTRAP_ENTRYPOINT:-}" == "deploy.sh" ]] || {
  echo "Run this transaction only through ./deploy.sh --bootstrap-mac-routes" >&2
  exit 2
}
[[ "${MAC_NGINX_REMOTE_LOCK_DIR:-}" == "/var/lib/health-app/release-state/deploy.lock" ]] || {
  echo "The unified remote release lock path is missing" >&2
  exit 73
}
lock_token="${MAC_NGINX_REMOTE_LOCK_TOKEN:-}"
[[ "${lock_token}" =~ ^[A-Za-z0-9._:-]+$ ]] || {
  echo "The unified remote release lock token is missing or invalid" >&2
  exit 73
}

case "${1:-}" in
  apply)
    [[ "$#" -eq 1 ]] || { usage; exit 2; }
    [[ -f "${ROUTE_SNIPPET}" && ! -L "${ROUTE_SNIPPET}" ]] || {
      echo "Mac nginx route snippet is missing or unsafe" >&2
      exit 1
    }
    snippet_b64="$(/usr/bin/base64 < "${ROUTE_SNIPPET}" | /usr/bin/tr -d '\n')"
    [[ -n "${snippet_b64}" && "${snippet_b64}" =~ ^[A-Za-z0-9+/=]+$ ]] || {
      echo "Could not encode Mac nginx route snippet" >&2
      exit 1
    }
    /usr/bin/ssh "${SSH_OPTIONS[@]}" "${SERVER}" \
      /usr/bin/python3 - apply "${snippet_b64}" "${lock_token}" < "${PYTHON_HELPER}"
    ;;
  rollback)
    [[ "$#" -eq 1 ]] || { usage; exit 2; }
    /usr/bin/ssh "${SSH_OPTIONS[@]}" "${SERVER}" \
      /usr/bin/python3 - rollback "${lock_token}" < "${PYTHON_HELPER}"
    ;;
  *)
    usage
    exit 2
    ;;
esac
fi
