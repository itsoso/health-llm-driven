#!/usr/bin/env bash

# One local release at a time across the main checkout and all git worktrees.
_REVA_RELEASE_LOCK_ACQUIRED=0
_REVA_RELEASE_LOCK_PATH=""
_REVA_RELEASE_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

_release_lock_path() {
  if [[ -n "${REVA_RELEASE_LOCK_DIR:-}" ]]; then
    printf '%s\n' "${REVA_RELEASE_LOCK_DIR}"
    return 0
  fi

  local common_dir
  common_dir="$(git -C "${_REVA_RELEASE_REPO_ROOT}" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || return 1
  printf '%s/reva-release.lock\n' "${common_dir}"
}

release_release_lock() {
  if [[ "${_REVA_RELEASE_LOCK_ACQUIRED:-0}" != "1" ]]; then
    return 0
  fi
  if [[ -n "${_REVA_RELEASE_LOCK_PATH:-}" && -d "${_REVA_RELEASE_LOCK_PATH}" ]]; then
    local owner_pid
    owner_pid="$(cat "${_REVA_RELEASE_LOCK_PATH}/pid" 2>/dev/null || true)"
    if [[ "${owner_pid}" == "$$" ]]; then
      rm -rf -- "${_REVA_RELEASE_LOCK_PATH}"
    fi
  fi
  _REVA_RELEASE_LOCK_ACQUIRED=0
  unset REVA_RELEASE_LOCK_TOKEN
}

_release_lock_exit() {
  local status=$?
  release_release_lock
  return "${status}"
}

acquire_release_lock() {
  local label="${1:-release}"
  local lock_path
  lock_path="$(_release_lock_path)" || {
    echo "✗ 无法解析发布锁路径。" >&2
    return 70
  }
  if [[ -z "${lock_path}" || "${lock_path}" == "/" ]]; then
    echo "✗ 发布锁路径不安全，拒绝继续。" >&2
    return 70
  fi

  local attempt owner_pid owner_label owner_token stale_path token
  token="${REVA_RELEASE_LOCK_TOKEN:-$$-${RANDOM:-0}-$(date +%s)}"
  for attempt in 1 2; do
    if mkdir "${lock_path}" 2>/dev/null; then
      chmod 700 "${lock_path}" 2>/dev/null || true
      printf '%s\n' "$$" > "${lock_path}/pid"
      printf '%s\n' "${label}" > "${lock_path}/label"
      printf '%s\n' "${token}" > "${lock_path}/token"
      printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "${lock_path}/started_at"
      _REVA_RELEASE_LOCK_PATH="${lock_path}"
      _REVA_RELEASE_LOCK_ACQUIRED=1
      export REVA_RELEASE_LOCK_TOKEN="${token}"
      trap _release_lock_exit EXIT
      trap 'release_release_lock; exit 130' INT
      trap 'release_release_lock; exit 143' TERM
      return 0
    fi

    owner_pid="$(cat "${lock_path}/pid" 2>/dev/null || true)"
    owner_label="$(cat "${lock_path}/label" 2>/dev/null || true)"
    owner_token="$(cat "${lock_path}/token" 2>/dev/null || true)"
    if [[ -n "${REVA_RELEASE_LOCK_TOKEN:-}" && "${owner_token}" == "${REVA_RELEASE_LOCK_TOKEN}" ]]; then
      return 0
    fi
    if [[ "${owner_pid}" =~ ^[0-9]+$ ]] && kill -0 "${owner_pid}" 2>/dev/null; then
      echo "✗ 另一个发布任务正在执行: ${owner_label:-unknown} (pid=${owner_pid})" >&2
      return 73
    fi

    echo "△ 清理陈旧发布锁: ${owner_label:-unknown} (pid=${owner_pid:-missing})" >&2
    stale_path="${lock_path}.stale.$$"
    if mv "${lock_path}" "${stale_path}" 2>/dev/null; then
      rm -rf -- "${stale_path}"
    fi
  done

  echo "✗ 无法获取发布锁，请稍后重试。" >&2
  return 73
}
