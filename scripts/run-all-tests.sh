#!/usr/bin/env bash
# scripts/run-all-tests.sh — 全栈回归测试一键脚本
#
# 用法:
#   bash scripts/run-all-tests.sh                # 跑全部
#   bash scripts/run-all-tests.sh --quick        # 跳过 backend pytest, 只跑前端 + mobile
#   bash scripts/run-all-tests.sh --backend      # 只跑后端
#   bash scripts/run-all-tests.sh --frontend     # 只跑前端
#   bash scripts/run-all-tests.sh --mobile       # 只跑 mobile
#
# 退出码:
#   0 = 全部通过
#   非 0 = 有失败

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/test-output.sh"
cd "$ROOT"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $*"; }
fail() { echo -e "${RED}✗${NC} $*"; }
warn() { echo -e "${YELLOW}!${NC} $*"; }
hdr()  { echo -e "\n${YELLOW}═══ $* ═══${NC}"; }

MODE="${1:-all}"
RUN_BACKEND=true
RUN_FRONTEND=true
RUN_MOBILE=true

case "$MODE" in
  --quick)    RUN_BACKEND=false ;;
  --backend)  RUN_FRONTEND=false; RUN_MOBILE=false ;;
  --frontend) RUN_BACKEND=false;  RUN_MOBILE=false ;;
  --mobile)   RUN_BACKEND=false;  RUN_FRONTEND=false ;;
  --help|-h)  sed -n '2,15p' "$0"; exit 0 ;;
  all|"")     ;;
  *) echo "Unknown option: $MODE"; exit 2 ;;
esac

FAIL_LIST=()

backend_pytest() {
  (cd "$ROOT/backend" && source venv/bin/activate && pytest tests/ -q --no-cov --tb=line --ignore=tests/test_integration.py)
}

frontend_vitest() {
  (cd "$ROOT/frontend" && npm run test -- --run)
}

frontend_typecheck() {
  (cd "$ROOT/frontend" && npx tsc --noEmit -p .)
}

frontend_lint() {
  (cd "$ROOT/frontend" && npm run lint --silent)
}

mobile_jest() {
  (cd "$ROOT/mobile" && ./node_modules/.bin/jest --silent)
}

mobile_typecheck() {
  (cd "$ROOT/mobile" && ./node_modules/.bin/tsc --noEmit)
}

# ── Backend ────────────────────────────────────────────────
if $RUN_BACKEND; then
  hdr "Backend pytest (Python)"
  if [ ! -d backend/venv ]; then
    fail "backend/venv 不存在; 请先 cd backend && python3 -m venv venv && pip install -r requirements.txt"
    FAIL_LIST+=("backend:setup")
  else
    if run_with_log "Backend pytest" 20 30 backend_pytest; then
      ok "Backend tests"
    else
      status=$?
      fail "Backend tests (exit $status)"
      FAIL_LIST+=("backend:pytest")
    fi
  fi
fi

# ── Frontend ───────────────────────────────────────────────
if $RUN_FRONTEND; then
  hdr "Frontend Vitest + ESLint + tsc"
  if [ ! -d frontend/node_modules ]; then
    fail "frontend/node_modules 不存在; 请先 cd frontend && npm install"
    FAIL_LIST+=("frontend:setup")
  else
    if run_with_log "Frontend vitest" 10 10 frontend_vitest; then
      ok "Frontend vitest"
    else
      status=$?
      fail "Frontend vitest (exit $status)"
      FAIL_LIST+=("frontend:vitest")
    fi

    if run_with_log "Frontend typecheck" 10 10 frontend_typecheck; then
      ok "Frontend typecheck"
    else
      status=$?
      fail "Frontend typecheck (exit $status)"
      FAIL_LIST+=("frontend:tsc")
    fi

    if run_with_log "Frontend lint" 10 10 frontend_lint; then
      ok "Frontend lint (warnings 不计入失败)"
    else
      lint_status=$?
      # 保持既有 warning-only 边界,但显式暴露 lint 的真实退出码和上下文。
      warn "Frontend lint exit $lint_status (non-blocking)"
    fi
  fi
fi

# ── Mobile ─────────────────────────────────────────────────
if $RUN_MOBILE; then
  hdr "Mobile Jest + tsc + ESLint"
  if [ ! -d mobile/node_modules ]; then
    fail "mobile/node_modules 不存在; 请先 cd mobile && npm install"
    FAIL_LIST+=("mobile:setup")
  else
    # 直接调 local bin 避免子 shell 找不到 npx 全局
    if run_with_log "Mobile jest" 10 10 mobile_jest; then
      ok "Mobile jest"
    else
      status=$?
      fail "Mobile jest (exit $status)"
      FAIL_LIST+=("mobile:jest")
    fi

    if run_with_log "Mobile typecheck" 10 10 mobile_typecheck; then
      ok "Mobile typecheck"
    else
      status=$?
      fail "Mobile typecheck (exit $status)"
      FAIL_LIST+=("mobile:tsc")
    fi
  fi
fi

# ── 总结 ──────────────────────────────────────────────────
hdr "回归汇总"
if [ ${#FAIL_LIST[@]} -eq 0 ]; then
  ok "全部通过 ✅"
  exit 0
else
  fail "失败 ${#FAIL_LIST[@]} 项: ${FAIL_LIST[*]}"
  exit 1
fi
