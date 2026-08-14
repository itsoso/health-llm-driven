#!/bin/bash
# _run-mobile-tf.sh — production Mobile 更新的兼容入口。
#
# remote 只创建 production iOS 原生构建，不自动提交 TestFlight/App Store Connect；
# 构建候选必须经过独立的 Store Build、真机和 App Review Gate 后再选择/提交。
# production profile 当前只打 iPhone App；Watch 是单独的 watch-production profile。
# ota 直接 exec 唯一受控 OTA authority，避免 wrapper 与 authority 自锁。
# local-archive 已禁用：不得执行生产 .env、复用共享 /tmp IPA 或直接上传。

# Sourcing is inert; test fixtures explicitly extract the unreachable body.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  return 0
fi

# Every mode holds production authority. Exact static help is the sole local
# operation; execution and sourcing both terminate before path/tool access.
if [[ "$#" -eq 1 && ( "$1" == "-h" || "$1" == "--help" ) ]]; then
  builtin printf '%s\n' \
    'Usage: ./scripts/_run-mobile-tf.sh -h|--help' \
    'Production Mobile release entrypoint is frozen (exit 78).'
  exit 0
fi
builtin printf '%s\n' \
  'Automated production Mobile release entrypoint is frozen; 尚未创建 EAS 构建或 OTA。请使用 manual native/App Review Gate（手工 Gate）。' >&2
exit 78

if [[ "REVA_UNREACHABLE_LEGACY" == "NEVER" ]]; then
# BEGIN UNREACHABLE LEGACY TESTFLIGHT IMPLEMENTATION

set -euo pipefail
umask 077

ROOT="$(cd "$(/usr/bin/dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EAS_CLI_VERSION="21.8.0"
EAS_TOOL_MANIFEST_DIR="${ROOT}/scripts/eas-cli-tool"
LOCKED_EAS_HELPER="${ROOT}/scripts/locked_eas_cli.py"
CANONICAL_ORIGIN_URL="https://github.com/itsoso/health-llm-driven.git"
MOBILE_OTA="${ROOT}/scripts/mobile-ota.sh"
GIT_BINARY="/usr/bin/git"
PYTHON_BINARY="/usr/local/bin/python3"
MKTEMP_BINARY="/usr/bin/mktemp"
CHMOD_BINARY="/bin/chmod"
RM_BINARY="/bin/rm"
SCRIPT_BINARY="/usr/bin/script"
SAFE_TOOL_PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
TESTFLIGHT_WORK_DIR_CREATED=0
WORK_DIR=""
TESTFLIGHT_BUILD_PID=""
EAS_TOOL_WORKSPACE=""
EAS_BINARY=""

fail() {
  echo "❌ $*" >&2
  exit 1
}

assert_testflight_tooling() {
  local tool=""
  for tool in \
    "${GIT_BINARY}" \
    "${PYTHON_BINARY}" \
    "${MKTEMP_BINARY}" \
    "${CHMOD_BINARY}" \
    "${RM_BINARY}" \
    "${SCRIPT_BINARY}"; do
    [ -x "${tool}" ] || fail "受控发布工具不存在或不可执行: ${tool}"
  done
  [ -r "${EAS_TOOL_MANIFEST_DIR}/package.json" ] ||
    fail "缺少 EAS CLI 锁定 manifest"
  [ -r "${EAS_TOOL_MANIFEST_DIR}/package-lock.json" ] ||
    fail "缺少 EAS CLI integrity lock"
  [ -r "${LOCKED_EAS_HELPER}" ] ||
    fail "缺少锁定 EAS CLI 准备器"
}

assert_exact_remote_main_source() {
  local release_mode="$1"
  local status_output=""
  local branch=""
  local head_sha=""
  local local_main_sha=""
  local remote_row=""
  local remote_sha=""
  local remote_ref=""
  local remote_extra=""
  local remote_urls=""
  local remote_push_urls=""
  local rewrite_config=""
  local empty_git_config=""
  local -a isolated_git_environment=()

  status_output="$("${GIT_BINARY}" -C "${ROOT}" status --porcelain --untracked-files=all)" ||
    fail "无法检查 ${release_mode} 发布源工作树"
  [ -z "${status_output}" ] ||
    fail "${release_mode} 只允许从干净工作树发布；请先提交或移走改动"

  remote_urls="$(
    "${GIT_BINARY}" -C "${ROOT}" config --local --get-all remote.origin.url || true
  )"
  [ "${remote_urls}" = "${CANONICAL_ORIGIN_URL}" ] ||
    fail "${release_mode} canonical origin 不匹配；只允许 ${CANONICAL_ORIGIN_URL}"
  remote_push_urls="$(
    "${GIT_BINARY}" -C "${ROOT}" config --local --get-all remote.origin.pushurl || true
  )"
  [ -z "${remote_push_urls}" ] ||
    fail "${release_mode} 不允许 remote.origin.pushurl"
  empty_git_config="${ROOT}/.gitconfig.reva-release-empty"
  [ ! -e "${empty_git_config}" ] ||
    fail "保留的隔离 Git config 路径意外存在: ${empty_git_config}"
  isolated_git_environment=(
    /usr/bin/env -i
    HOME="/var/empty"
    PATH="${SAFE_TOOL_PATH}"
    LANG=C
    LC_ALL=C
    GIT_CONFIG_NOSYSTEM=1
    GIT_CONFIG_GLOBAL="${empty_git_config}"
  )
  rewrite_config="$(
    "${isolated_git_environment[@]}" \
      "${GIT_BINARY}" -C "${ROOT}" config --get-regexp \
        '^url\..*\.(insteadOf|pushInsteadOf)$' 2>/dev/null || true
  )"
  [ -z "${rewrite_config}" ] ||
    fail "${release_mode} 不允许 local Git URL rewrite"

  if branch="$("${GIT_BINARY}" -C "${ROOT}" symbolic-ref --quiet --short HEAD 2>/dev/null)"; then
    [ "${branch}" = "main" ] ||
      fail "${release_mode} 只允许 main 或 detached origin/main，当前分支=${branch}"
  else
    branch=""
  fi

  "${isolated_git_environment[@]}" \
    "${GIT_BINARY}" -C "${ROOT}" fetch --quiet \
      "${CANONICAL_ORIGIN_URL}" '+refs/heads/main:refs/remotes/origin/main' ||
    fail "无法刷新 origin/main，拒绝发布"
  head_sha="$("${GIT_BINARY}" -C "${ROOT}" rev-parse HEAD)" || fail "无法读取 HEAD"
  local_main_sha="$("${GIT_BINARY}" -C "${ROOT}" rev-parse refs/remotes/origin/main)" ||
    fail "无法读取本地 origin/main"
  remote_row="$(
    "${isolated_git_environment[@]}" \
      "${GIT_BINARY}" -C / ls-remote --exit-code \
        "${CANONICAL_ORIGIN_URL}" refs/heads/main
  )" ||
    fail "无法独立读取远端 main"
  case "${remote_row}" in
    *$'\n'*) fail "远端 main 返回了歧义结果" ;;
  esac
  read -r remote_sha remote_ref remote_extra <<< "${remote_row}"
  [ -n "${remote_sha}" ] && [ "${remote_ref}" = "refs/heads/main" ] &&
    [ -z "${remote_extra}" ] || fail "远端 main 响应格式异常"
  [[ "${remote_sha}" =~ ^[0-9a-f]{40}$ ]] || fail "远端 main SHA 格式异常"
  [ "${head_sha}" = "${local_main_sha}" ] && [ "${head_sha}" = "${remote_sha}" ] ||
    fail "发布源必须精确等于远端 origin/main；HEAD=${head_sha} origin/main=${remote_sha}"
}

cleanup_testflight_workspace() {
  if [ -n "${EAS_TOOL_WORKSPACE:-}" ]; then
    if ! "${PYTHON_BINARY}" "${LOCKED_EAS_HELPER}" cleanup \
      "${EAS_TOOL_WORKSPACE}"; then
      echo "⚠️ 无法清理锁定 EAS CLI 临时目录: ${EAS_TOOL_WORKSPACE}" >&2
    fi
    EAS_TOOL_WORKSPACE=""
    EAS_BINARY=""
  fi
  if [ "${TESTFLIGHT_WORK_DIR_CREATED:-0}" = "1" ] && [ -n "${WORK_DIR:-}" ]; then
    "${RM_BINARY}" -rf -- "${WORK_DIR}"
    TESTFLIGHT_WORK_DIR_CREATED=0
  fi
}

stop_testflight_managed_command() {
  local signal_name="${1:-TERM}"
  if [[ "${TESTFLIGHT_BUILD_PID:-}" =~ ^[0-9]+$ ]]; then
    /bin/kill -s "${signal_name}" -- "-${TESTFLIGHT_BUILD_PID}" 2>/dev/null ||
      /bin/kill -s "${signal_name}" "${TESTFLIGHT_BUILD_PID}" 2>/dev/null || true
    wait "${TESTFLIGHT_BUILD_PID}" 2>/dev/null || true
    TESTFLIGHT_BUILD_PID=""
  fi
}

release_testflight_local_lock() {
  if declare -F release_release_lock >/dev/null 2>&1; then
    release_release_lock
  fi
}

testflight_exit_cleanup() {
  local status=$?
  trap - EXIT INT TERM
  cleanup_testflight_workspace
  release_testflight_local_lock
  return "${status}"
}

testflight_signal_exit() {
  local status="$1"
  trap - EXIT INT TERM
  if [ "${status}" = "130" ]; then
    stop_testflight_managed_command INT
  else
    stop_testflight_managed_command TERM
  fi
  cleanup_testflight_workspace
  release_testflight_local_lock
  exit "${status}"
}

install_testflight_cleanup_traps() {
  trap testflight_exit_cleanup EXIT
  trap 'testflight_signal_exit 130' INT
  trap 'testflight_signal_exit 143' TERM
}

run_testflight_managed_command() {
  local log="$1"
  shift
  local command_status=0

  [ "$#" -gt 0 ] || fail "受控构建命令为空"
  [ -n "${log}" ] || fail "受控构建日志路径为空"
  "${SCRIPT_BINARY}" -q "${log}" "$@" &
  TESTFLIGHT_BUILD_PID=$!
  wait "${TESTFLIGHT_BUILD_PID}" || command_status=$?
  TESTFLIGHT_BUILD_PID=""
  return "${command_status}"
}

prepare_locked_eas_cli() {
  local prepared_output=""

  prepared_output="$(
    "${PYTHON_BINARY}" "${LOCKED_EAS_HELPER}" prepare --repo-root "${ROOT}"
  )" || fail "无法准备 integrity-locked EAS CLI"
  case "${prepared_output}" in
    *$'\n'*) fail "锁定 EAS CLI 准备器返回多行歧义结果" ;;
  esac
  EAS_TOOL_WORKSPACE="${prepared_output%%$'\t'*}"
  [ "${prepared_output}" != "${EAS_TOOL_WORKSPACE}" ] ||
    fail "锁定 EAS CLI 准备器返回格式异常"
  EAS_BINARY="${prepared_output#*$'\t'}"
  case "${EAS_BINARY}" in
    *$'\t'*|"") fail "锁定 EAS CLI 准备器返回格式异常" ;;
    "${EAS_TOOL_WORKSPACE}"/*) ;;
    *) fail "锁定 EAS CLI 可执行文件不在私有工作区" ;;
  esac
  [ -d "${EAS_TOOL_WORKSPACE}" ] && [ -x "${EAS_BINARY}" ] ||
    fail "锁定 EAS CLI 准备证据无效"
}

run_remote_build() {
  local log=""
  local -a eas_environment=()

  fail "自动原生 production 构建已冻结：历史 ASC 分发构建尚未与可信 native fingerprint 建立完整映射，无法安全自动选择或恢复 exact build。请在独立手工 Gate 中创建并记录候选；本命令尚未创建 EAS 构建。"

  source "${ROOT}/scripts/release_lock.sh"
  acquire_release_lock "testflight:remote"
  assert_testflight_tooling
  assert_exact_remote_main_source "remote"

  WORK_DIR="$("${MKTEMP_BINARY}" -d "${TMPDIR:-/tmp}/reva-testflight.XXXXXX")" ||
    fail "无法创建私有 TestFlight 临时目录"
  TESTFLIGHT_WORK_DIR_CREATED=1
  "${CHMOD_BINARY}" 700 "${WORK_DIR}" || fail "无法保护 TestFlight 临时目录"
  install_testflight_cleanup_traps
  log="${WORK_DIR}/run-mobile-tf.log"

  export PATH="/opt/homebrew/opt/ruby@3.3/bin:/opt/homebrew/lib/ruby/gems/3.3.0/bin:${SAFE_TOOL_PATH}"
  export LANG="${LANG:-en_US.UTF-8}"
  export LC_ALL="${LC_ALL:-en_US.UTF-8}"
  cd "${ROOT}/mobile"

  echo "==> 安装 integrity-locked EAS CLI ${EAS_CLI_VERSION}（禁用依赖脚本）"
  prepare_locked_eas_cli

  echo "== mobile → EAS production iOS build (build-only) =="
  echo "私有临时日志（进程结束时删除）: ${log}"
  echo "→ 创建 production iPhone 原生构建；不会自动提交 TestFlight/App Review…"
  eas_environment=(
    /usr/bin/env -i
    HOME="${HOME}"
    PATH="${SAFE_TOOL_PATH}"
    LANG="${LANG:-en_US.UTF-8}"
    LC_ALL="${LC_ALL:-en_US.UTF-8}"
    CI=1
  )
  if [ -n "${EXPO_TOKEN:-}" ]; then
    eas_environment+=("EXPO_TOKEN=${EXPO_TOKEN}")
  fi
  run_testflight_managed_command "${log}" \
    "${eas_environment[@]}" \
      "${EAS_BINARY}" build \
        --platform ios \
        --profile production \
        --non-interactive
  echo
  echo "✓ EAS 构建完成。尚未提交 TestFlight 或 App Review；请使用构建链接进入下一道 Gate。"
}

main() {
  local mode="${1:-remote}"
  local message=""

  case "${mode}" in
    ota)
      [ -x "${MOBILE_OTA}" ] || fail "受控 OTA 入口不存在或不可执行: ${MOBILE_OTA}"
      message="${2:-$("${GIT_BINARY}" -C "${ROOT}" log -1 --pretty=%s)}"
      exec "${MOBILE_OTA}" production "${message}"
      ;;
    remote)
      run_remote_build
      ;;
    local-archive)
      fail "local-archive 已禁用：旧路径会执行生产 .env、继承全部密钥并复用共享 /tmp IPA；请使用受控 remote EAS 构建"
      ;;
    *)
      fail "未知 mode: ${mode}（可用: remote | ota | local-archive）"
      ;;
  esac
}

# END UNREACHABLE LEGACY TESTFLIGHT IMPLEMENTATION

# Historical direct entrypoint is excluded from test fixture extraction.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
fi
