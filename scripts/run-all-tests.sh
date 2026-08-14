#!/usr/bin/env bash
# 全栈验证协调器：独立检查最多四路并发，每项保留真实退出码和私有日志。
#
# 用法:
#   bash scripts/run-all-tests.sh                # backend + frontend + mobile
#   bash scripts/run-all-tests.sh --quick        # frontend + mobile
#   bash scripts/run-all-tests.sh --backend      # backend only
#   bash scripts/run-all-tests.sh --frontend     # frontend only
#   bash scripts/run-all-tests.sh --mobile       # mobile only

set -uo pipefail

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -n "${REVA_VALIDATION_ROOT:-}" ] &&
   [ "${REVA_VALIDATION_ALLOW_ROOT_OVERRIDE_FOR_TESTS:-}" != "1" ]; then
  echo "REVA_VALIDATION_ROOT is allowed only in explicit test mode" >&2
  exit 2
fi
ROOT="${REVA_VALIDATION_ROOT:-$SCRIPT_ROOT}"
if ! ROOT="$(cd "$ROOT" 2>/dev/null && pwd)"; then
  echo "Validation root does not exist: ${REVA_VALIDATION_ROOT:-$SCRIPT_ROOT}" >&2
  exit 2
fi
GIT_TOPLEVEL="$(git -C "$ROOT" rev-parse --show-toplevel 2>/dev/null)" || {
  echo "Validation root is not a Git worktree: $ROOT" >&2
  exit 2
}
if ! GIT_TOPLEVEL="$(cd "$GIT_TOPLEVEL" 2>/dev/null && pwd)"; then
  echo "Cannot canonicalize validation Git root: $GIT_TOPLEVEL" >&2
  exit 2
fi
if [ "$ROOT" != "$GIT_TOPLEVEL" ]; then
  echo "Validation root must equal Git toplevel: root=$ROOT git=$GIT_TOPLEVEL" >&2
  exit 2
fi
if [ -n "${REVA_VALIDATION_EXPECTED_ROOT:-}" ]; then
  if ! EXPECTED_ROOT="$(cd "$REVA_VALIDATION_EXPECTED_ROOT" 2>/dev/null && pwd)"; then
    echo "Expected validation root does not exist: $REVA_VALIDATION_EXPECTED_ROOT" >&2
    exit 2
  fi
  if [ "$ROOT" != "$EXPECTED_ROOT" ]; then
    echo "Validation root mismatch: expected=$EXPECTED_ROOT actual=$ROOT" >&2
    exit 2
  fi
fi
cd "$ROOT" || exit 2

# Direct invocations must be as deterministic as release.py: never let a
# developer shell select a stale PostgreSQL test database, production config,
# a different calendar day, or runtime injection hooks.  The canonical release
# validation environment is mirrored here because this script is also a public
# developer/CI entrypoint.
unset TEST_DATABASE_URL NODE_OPTIONS NODE_PATH PYTEST_ADDOPTS \
  PYTEST_DISABLE_PLUGIN_AUTOLOAD PYTEST_PLUGINS PYTHONHOME PYTHONPATH \
  PYTHONSTARTUP BASH_ENV ENV NPM_CONFIG_GLOBALCONFIG \
  NPM_CONFIG_NODE_OPTIONS NPM_CONFIG_SCRIPT_SHELL NPM_CONFIG_USERCONFIG \
  npm_config_globalconfig npm_config_node_options npm_config_script_shell \
  npm_config_userconfig
export APP_ENV="test"
export DATABASE_URL="sqlite:///:memory:"
export GARMIN_ENCRYPTION_KEY="mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU="
export NODE_ENV="test"
export SECRET_KEY="test-secret-key-32-chars-minimum!!"
export TZ="Asia/Shanghai"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $*"; }
fail() { echo -e "${RED}✗${NC} $*"; }
hdr()  { echo -e "\n${YELLOW}═══ $* ═══${NC}"; }

MODE="${1:-all}"
RUN_BACKEND=true
RUN_FRONTEND=true
RUN_MOBILE=true
case "$MODE" in
  --quick)    RUN_BACKEND=false ;;
  --backend)  RUN_FRONTEND=false; RUN_MOBILE=false ;;
  --frontend) RUN_BACKEND=false; RUN_MOBILE=false ;;
  --mobile)   RUN_BACKEND=false; RUN_FRONTEND=false ;;
  --help|-h)  sed -n '2,10p' "$0"; exit 0 ;;
  all|"")     MODE="all" ;;
  *) echo "Unknown option: $MODE" >&2; exit 2 ;;
esac

MAX_PARALLEL="${REVA_VALIDATION_MAX_PARALLEL:-4}"
case "$MAX_PARALLEL" in
  ''|*[!0-9]*) echo "REVA_VALIDATION_MAX_PARALLEL must be an integer from 1 to 4" >&2; exit 2 ;;
esac
if [ "$MAX_PARALLEL" -lt 1 ]; then
  echo "REVA_VALIDATION_MAX_PARALLEL must be an integer from 1 to 4" >&2
  exit 2
fi
if [ "$MAX_PARALLEL" -gt 4 ]; then
  MAX_PARALLEL=4
fi

umask 077
if [ -n "${REVA_VALIDATION_LOG_DIR:-}" ]; then
  LOG_DIR="$REVA_VALIDATION_LOG_DIR"
else
  GIT_COMMON_DIR="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || {
    echo "Cannot resolve Git common directory for validation logs" >&2
    exit 2
  }
  # Keep the transaction directory directly under Git's already-existing
  # common directory so secure setup never has to create intermediate paths.
  LOG_DIR="$GIT_COMMON_DIR/reva-validation-$(date -u +%Y%m%dT%H%M%SZ)-$$"
fi
# Canonicalise only an already-existing parent. This rejects any symlink in
# the requested path before creating the final, transaction-owned directory.
LOG_PARENT="$(dirname "$LOG_DIR")"
LOG_NAME="$(basename "$LOG_DIR")"
if [ "$LOG_NAME" = "." ] || [ "$LOG_NAME" = ".." ] || [ -z "$LOG_NAME" ]; then
  echo "Validation log path must name a new directory: $LOG_DIR" >&2
  exit 2
fi
if ! LOG_PARENT_CANONICAL="$(cd "$LOG_PARENT" 2>/dev/null && pwd -P)"; then
  echo "Validation log parent does not exist: $LOG_PARENT" >&2
  exit 2
fi
if [ "$LOG_PARENT" != "$LOG_PARENT_CANONICAL" ]; then
  echo "Refusing symlinked validation log parent: $LOG_PARENT" >&2
  exit 2
fi
LOG_DIR="$LOG_PARENT_CANONICAL/$LOG_NAME"
if ! mkdir -m 700 "$LOG_DIR" 2>/dev/null; then
  echo "Validation log directory must be newly created: $LOG_DIR" >&2
  exit 2
fi
if [ -L "$LOG_DIR" ] || [ ! -d "$LOG_DIR" ]; then
  echo "Validation log path is not a directory: $LOG_DIR" >&2
  exit 2
fi

CHECK_IDS=()
CHECK_TITLES=()
add_check() {
  CHECK_IDS[${#CHECK_IDS[@]}]="$1"
  CHECK_TITLES[${#CHECK_TITLES[@]}]="$2"
}

if $RUN_BACKEND; then
  add_check "backend:pytest" "Backend pytest"
fi
if $RUN_FRONTEND; then
  add_check "frontend:vitest" "Frontend vitest"
  add_check "frontend:typecheck" "Frontend typecheck"
  add_check "frontend:lint" "Frontend lint"
fi
if $RUN_MOBILE; then
  add_check "mobile:jest" "Mobile jest"
  add_check "mobile:typecheck" "Mobile typecheck"
  add_check "mobile:lint" "Mobile lint"
  add_check "mobile:design" "Mobile design tokens"
  add_check "mobile:settings-routes" "Mobile settings routes"
fi
add_check "git:diff-check" "Git whitespace check"

# A caller-controlled validation directory must not let a precreated leaf
# symlink redirect a log truncation into another file. Reject all collisions up
# front; start_check also uses Bash noclobber for atomic creation after this
# human-readable preflight.
for check_id in "${CHECK_IDS[@]}"; do
  safe_name="$(printf '%s' "$check_id" | tr ':/' '--')"
  log_path="$LOG_DIR/${safe_name}.log"
  if [ -e "$log_path" ] || [ -L "$log_path" ]; then
    echo "Refusing pre-existing or symlinked validation log: $log_path" >&2
    exit 2
  fi
done

execute_check() {
  case "$1" in
    backend:pytest)
      if [ ! -x backend/venv/bin/python ]; then
        echo "backend/venv 不存在; 请先安装 backend dependencies" >&2
        return 2
      fi
      cd backend || return 2
      # Reuse CI's exact shard matrix and process deadline locally. Keep its
      # per-shard private logs nested under this validation transaction.
      export REVA_BACKEND_SHARD_LOG_DIR="$LOG_DIR/backend-pytest-shards"
      exec ./venv/bin/python scripts/run_local_pytest_matrix.py
      ;;
    frontend:vitest)
      [ -d frontend/node_modules ] || { echo "frontend/node_modules 不存在" >&2; return 2; }
      cd frontend || return 2
      exec npm run test -- --run
      ;;
    frontend:typecheck)
      [ -x frontend/node_modules/.bin/tsc ] || { echo "frontend TypeScript 未安装" >&2; return 2; }
      cd frontend || return 2
      exec ./node_modules/.bin/tsc --noEmit -p .
      ;;
    frontend:lint)
      [ -d frontend/node_modules ] || { echo "frontend/node_modules 不存在" >&2; return 2; }
      cd frontend || return 2
      exec npm run lint --silent
      ;;
    mobile:jest)
      [ -x mobile/node_modules/.bin/jest ] || { echo "mobile Jest 未安装" >&2; return 2; }
      cd mobile || return 2
      exec ./node_modules/.bin/jest --silent
      ;;
    mobile:typecheck)
      [ -x mobile/node_modules/.bin/tsc ] || { echo "mobile TypeScript 未安装" >&2; return 2; }
      cd mobile || return 2
      exec ./node_modules/.bin/tsc --noEmit
      ;;
    mobile:lint)
      [ -d mobile/node_modules ] || { echo "mobile/node_modules 不存在" >&2; return 2; }
      cd mobile || return 2
      exec npm run lint --silent
      ;;
    mobile:design)
      [ -d mobile/node_modules ] || { echo "mobile/node_modules 不存在" >&2; return 2; }
      cd mobile || return 2
      exec npm run design:check --silent
      ;;
    mobile:settings-routes)
      [ -d mobile/node_modules ] || { echo "mobile/node_modules 不存在" >&2; return 2; }
      cd mobile || return 2
      exec npm run check:settings-routes --silent
      ;;
    git:diff-check)
      exec git diff --check HEAD
      ;;
    *)
      echo "Unknown validation check: $1" >&2
      return 2
      ;;
  esac
}

PIDS=()
LOGS=()
RESULTS=()
STARTED_AT=()
DONE=()

terminate_tree() {
  target_pid="$1"
  child_pids="$(pgrep -P "$target_pid" 2>/dev/null || true)"
  for child_pid in $child_pids; do
    terminate_tree "$child_pid"
  done
  kill -TERM "$target_pid" 2>/dev/null || true
}

cleanup_signal() {
  signal_name="$1"
  trap - INT TERM
  stop_running_checks
  if [ "$signal_name" = "INT" ]; then
    exit 130
  fi
  exit 143
}

stop_running_checks() {
  running_index=0
  while [ "$running_index" -lt "${#PIDS[@]}" ]; do
    running_pid="${PIDS[$running_index]:-}"
    if [ -n "$running_pid" ] && kill -0 "$running_pid" 2>/dev/null; then
      terminate_tree "$running_pid"
    fi
    running_index=$((running_index + 1))
  done
  running_index=0
  while [ "$running_index" -lt "${#PIDS[@]}" ]; do
    running_pid="${PIDS[$running_index]:-}"
    if [ -n "$running_pid" ]; then
      wait "$running_pid" 2>/dev/null || true
    fi
    running_index=$((running_index + 1))
  done
}
trap 'cleanup_signal INT' INT
trap 'cleanup_signal TERM' TERM

start_check() {
  index="$1"
  check_id="${CHECK_IDS[$index]}"
  safe_name="$(printf '%s' "$check_id" | tr ':/' '--')"
  log_path="$LOG_DIR/${safe_name}.log"
  STARTED_AT[$index]="$(date +%s)"
  set -C
  if ! { exec 9>"$log_path"; } 2>/dev/null; then
    set +C
    echo "Refusing validation log collision: $log_path" >&2
    return 2
  fi
  set +C
  (execute_check "$check_id") >&9 2>&1 &
  child_pid=$!
  exec 9>&-
  PIDS[$index]="$child_pid"
  LOGS[$index]="$log_path"
}

wait_check() {
  index="$1"
  child_pid="${PIDS[$index]}"
  wait "$child_pid"
  child_status=$?
  RESULTS[$index]="$child_status"
  DONE[$index]=true
  elapsed=$(( $(date +%s) - ${STARTED_AT[$index]} ))
  if [ "$child_status" -eq 0 ]; then
    ok "${CHECK_TITLES[$index]} (${elapsed}s; log: ${LOGS[$index]})"
  else
    fail "${CHECK_IDS[$index]} — ${CHECK_TITLES[$index]} (exit ${child_status}; ${elapsed}s; log: ${LOGS[$index]})"
    # Do not reopen a pathname that another process could have replaced after
    # the check inherited its already-open log FD. The private log retains the
    # full output for inspection by the owner.
    echo "Check output retained in private log; automatic tail withheld"
  fi
}

hdr "Parallel validation (max $MAX_PARALLEL)"
launched=0
completed=0
active=0
total_checks=${#CHECK_IDS[@]}
while [ "$completed" -lt "$total_checks" ]; do
  while [ "$launched" -lt "$total_checks" ] && [ "$active" -lt "$MAX_PARALLEL" ]; do
    if ! start_check "$launched"; then
      stop_running_checks
      exit 2
    fi
    launched=$((launched + 1))
    active=$((active + 1))
  done

  found_completed=false
  index=0
  while [ "$index" -lt "$launched" ]; do
    if [ -z "${DONE[$index]:-}" ] && ! kill -0 "${PIDS[$index]}" 2>/dev/null; then
      wait_check "$index"
      completed=$((completed + 1))
      active=$((active - 1))
      found_completed=true
    fi
    index=$((index + 1))
  done
  if ! $found_completed; then
    sleep 0.05
  fi
done

trap - INT TERM
FAIL_LIST=()
index=0
while [ "$index" -lt "$total_checks" ]; do
  if [ "${RESULTS[$index]}" -ne 0 ]; then
    FAIL_LIST[${#FAIL_LIST[@]}]="${CHECK_IDS[$index]}"
  fi
  index=$((index + 1))
done

hdr "回归汇总"
echo "Logs: $LOG_DIR"
if [ ${#FAIL_LIST[@]} -eq 0 ]; then
  ok "全部通过 ✅"
  exit 0
fi
fail "失败 ${#FAIL_LIST[@]} 项: ${FAIL_LIST[*]}"
exit 1
