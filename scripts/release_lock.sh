#!/usr/bin/env bash

# One kernel-backed local release lease across Python, deploy, OTA and TestFlight.
# The first invocation is replaced by a Python guardian. The guardian owns the
# lock and passes that exact locked descriptor to the restarted entrypoint.
_REVA_RELEASE_LOCK_ACQUIRED=0
_REVA_RELEASE_LOCK_ADOPTED=0
_REVA_RELEASE_LOCK_PATH=""
_REVA_RELEASE_CALLER="${BASH_SOURCE[1]:-$0}"
_REVA_RELEASE_CALLER_ARGS=("$@")
_REVA_RELEASE_REPO_ROOT="${_REVA_RELEASE_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
_REVA_RELEASE_LOCK_PY="${_REVA_RELEASE_REPO_ROOT}/scripts/release_lock.py"

_release_lock_python() {
  [[ -x /usr/bin/python3 ]] || return 1
  printf '%s\n' "/usr/bin/python3"
}

_release_lock_path() {
  local python_bin
  python_bin="$(_release_lock_python)" || return 1
  "${python_bin}" "${_REVA_RELEASE_LOCK_PY}" path \
    --repo-root "${_REVA_RELEASE_REPO_ROOT}"
}

_release_lock_fd_is_valid() {
  local descriptor="${1:-}"
  [[ "${descriptor}" =~ ^[0-9]+$ ]] || return 1
  [[ "${descriptor}" -ge 3 ]]
}

release_release_lock() {
  if [[ "${_REVA_RELEASE_LOCK_ACQUIRED:-0}" != "1" ]]; then
    return 0
  fi

  # Adoption closes and clears the inherited descriptor immediately. Keep this
  # fail-safe for a partially initialized shell only.
  if _release_lock_fd_is_valid "${REVA_RELEASE_LOCK_FD:-}"; then
    eval "exec ${REVA_RELEASE_LOCK_FD}>&-"
  fi
  _REVA_RELEASE_LOCK_ACQUIRED=0
  _REVA_RELEASE_LOCK_ADOPTED=0
  _REVA_RELEASE_LOCK_PATH=""
  unset REVA_RELEASE_LOCK_ADOPT
  unset REVA_RELEASE_LOCK_FD
  unset REVA_RELEASE_LOCK_TOKEN
}

_release_lock_exit() {
  local status=$?
  release_release_lock
  return "${status}"
}

acquire_release_lock() {
  local label="${1:-release}"
  if [[ "${_REVA_RELEASE_LOCK_ACQUIRED:-0}" == "1" ]]; then
    return 0
  fi

  local python_bin
  python_bin="$(_release_lock_python)" || {
    echo "✗ 无法找到 Python，不能获取发布锁。" >&2
    return 70
  }

  if [[ "${REVA_RELEASE_LOCK_ADOPT:-}" == "1" ]]; then
    local inherited_fd="${REVA_RELEASE_LOCK_FD:-}"
    if ! _release_lock_fd_is_valid "${inherited_fd}" || ! \
      "${python_bin}" "${_REVA_RELEASE_LOCK_PY}" verify-adopt \
        --repo-root "${_REVA_RELEASE_REPO_ROOT}" \
        --fd "${inherited_fd}"; then
      if _release_lock_fd_is_valid "${inherited_fd}"; then
        eval "exec ${inherited_fd}>&-"
      fi
      unset REVA_RELEASE_LOCK_ADOPT
      unset REVA_RELEASE_LOCK_FD
      unset REVA_RELEASE_LOCK_TOKEN
      echo "✗ 继承发布锁失败：未收到真实 owner 的已加锁文件描述符。" >&2
      return 73
    fi
    eval "exec ${inherited_fd}>&-"
    unset REVA_RELEASE_LOCK_ADOPT
    unset REVA_RELEASE_LOCK_FD
    unset REVA_RELEASE_LOCK_TOKEN
    _REVA_RELEASE_LOCK_PATH="$(_release_lock_path)" || return 70
    _REVA_RELEASE_LOCK_ACQUIRED=1
    _REVA_RELEASE_LOCK_ADOPTED=1
    trap _release_lock_exit EXIT
    trap 'release_release_lock; exit 130' INT
    trap 'release_release_lock; exit 143' TERM
    return 0
  fi

  # An adoption marker is fail-closed. Never silently downgrade a malformed
  # inherited-lock request into a fresh, independently authorized release.
  if [[ -n "${REVA_RELEASE_LOCK_ADOPT:-}" ]]; then
    echo "✗ 继承发布锁失败：继承标记无效。" >&2
    return 73
  fi

  unset REVA_RELEASE_LOCK_TOKEN
  exec "${python_bin}" "${_REVA_RELEASE_LOCK_PY}" run \
    --repo-root "${_REVA_RELEASE_REPO_ROOT}" \
    --label "${label}" \
    -- "${_REVA_RELEASE_CALLER}" \
    ${_REVA_RELEASE_CALLER_ARGS[@]+"${_REVA_RELEASE_CALLER_ARGS[@]}"}
}
