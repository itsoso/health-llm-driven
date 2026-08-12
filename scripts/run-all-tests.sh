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
ROOT="${REVA_VALIDATION_ROOT:-$SCRIPT_ROOT}"
if ! ROOT="$(cd "$ROOT" 2>/dev/null && pwd)"; then
  echo "Validation root does not exist: ${REVA_VALIDATION_ROOT:-$SCRIPT_ROOT}" >&2
  exit 2
fi
cd "$ROOT" || exit 2

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
  LOG_DIR="$GIT_COMMON_DIR/reva-release-state/logs/validation-$(date -u +%Y%m%dT%H%M%SZ)-$$"
fi
if [ -L "$LOG_DIR" ]; then
  echo "Refusing symlinked validation log directory: $LOG_DIR" >&2
  exit 2
fi
mkdir -p "$LOG_DIR" || exit 2
chmod 700 "$LOG_DIR" || exit 2
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

execute_check() {
  case "$1" in
    backend:pytest)
      if [ ! -x backend/venv/bin/python ]; then
        echo "backend/venv 不存在; 请先安装 backend dependencies" >&2
        return 2
      fi
      cd backend || return 2
      exec ./venv/bin/python -m pytest tests/ -q --no-cov --tb=line --ignore=tests/test_integration.py
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
  for running_pid in "${PIDS[@]}"; do
    if kill -0 "$running_pid" 2>/dev/null; then
      terminate_tree "$running_pid"
    fi
  done
  for running_pid in "${PIDS[@]}"; do
    wait "$running_pid" 2>/dev/null || true
  done
  if [ "$signal_name" = "INT" ]; then
    exit 130
  fi
  exit 143
}
trap 'cleanup_signal INT' INT
trap 'cleanup_signal TERM' TERM

start_check() {
  index="$1"
  check_id="${CHECK_IDS[$index]}"
  safe_name="$(printf '%s' "$check_id" | tr ':/' '--')"
  log_path="$LOG_DIR/${safe_name}.log"
  : > "$log_path"
  chmod 600 "$log_path"
  STARTED_AT[$index]="$(date +%s)"
  (execute_check "$check_id") >"$log_path" 2>&1 &
  PIDS[$index]=$!
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
    tail -n 20 "${LOGS[$index]}"
  fi
}

hdr "Parallel validation (max $MAX_PARALLEL)"
launched=0
completed=0
active=0
total_checks=${#CHECK_IDS[@]}
while [ "$completed" -lt "$total_checks" ]; do
  while [ "$launched" -lt "$total_checks" ] && [ "$active" -lt "$MAX_PARALLEL" ]; do
    start_check "$launched"
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
