#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${MOBILE_RC_PYTHON:-${ROOT}/backend/venv/bin/python}"
IOS_LATEST_INSTALL_URL="${MOBILE_RC_IOS_LATEST_INSTALL_URL:-https://health.executor.life/mobile-install/ios/latest/install.html}"

BACKEND_ENV=(
  "DATABASE_URL=sqlite:///:memory:"
  "TZ=Asia/Shanghai"
)

PHONE_AUTH_TESTS=(
  "backend/tests/test_phone_auth.py"
)

HEALTHKIT_BACKEND_TESTS=(
  "backend/tests/test_healthkit_adapter.py"
  "backend/tests/test_healthkit_spo2_samples_import.py"
  "backend/tests/test_healthkit_bp_bodyfat_import.py"
)

WATCH_BACKEND_TESTS=(
  "backend/tests/test_watch_summary.py"
  "backend/tests/test_watch_actions.py"
  "backend/tests/test_watch_action_concurrency.py"
  "backend/tests/test_watch_ask.py"
  "backend/tests/test_watch_symptoms.py"
  "backend/tests/test_watch_voice_record_failclosed.py"
)

MOBILE_TESTS=(
  "hooks/__tests__/useHealthKitForegroundSync.test.ts"
  "services/__tests__/healthKitForegroundSync.test.ts"
  "services/__tests__/appleHealth.test.ts"
  "services/__tests__/auth.test.ts"
  "components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx"
  "utils/__tests__/share.test.ts"
  "services/__tests__/chatImageSave.test.ts"
  "app/__tests__/login.test.tsx"
  "__tests__/login.test.tsx"
)

log_step() {
  printf "\n==> %s\n" "$*"
}

require_file() {
  local path="$1"
  if [[ ! -f "${path}" ]]; then
    printf "Missing required file: %s\n" "${path}" >&2
    exit 1
  fi
}

require_executable() {
  local path="$1"
  if [[ ! -x "${path}" ]]; then
    printf "Missing executable: %s\n" "${path}" >&2
    exit 1
  fi
}

run() {
  log_step "$*"
  "$@"
}

run_backend_pytest() {
  local label="$1"
  shift
  local -a tests=("$@")

  for test_path in "${tests[@]}"; do
    require_file "${ROOT}/${test_path}"
  done

  log_step "${label}"
  env "${BACKEND_ENV[@]}" "${PYTHON}" -m pytest "${tests[@]}" -q --no-cov
}

run_mobile_jest() {
  for test_path in "${MOBILE_TESTS[@]}"; do
    require_file "${ROOT}/mobile/${test_path}"
  done

  log_step "Mobile HealthKit/auth/login tests"
  (
    cd "${ROOT}/mobile"
    ./node_modules/.bin/jest --runTestsByPath "${MOBILE_TESTS[@]}" --runInBand
  )
}

run_mobile_typecheck() {
  log_step "Mobile TypeScript typecheck"
  (
    cd "${ROOT}/mobile"
    npx tsc --noEmit
  )
}

check_mobile_native_share_deps() {
  log_step "Mobile native screenshot/share dependencies"
  (
    cd "${ROOT}/mobile"
    node <<'NODE'
const pkg = require('./package.json');
const deps = pkg.dependencies || {};
const required = {
  'react-native-view-shot': 'diet card screenshot capture',
  'expo-sharing': 'native image share sheet',
  'expo-media-library': 'save screenshot to Photos',
};
const missing = Object.entries(required)
  .filter(([name]) => !deps[name])
  .map(([name, reason]) => `${name} (${reason})`);
if (missing.length > 0) {
  console.error(`Missing mobile native share dependencies: ${missing.join(', ')}`);
  process.exit(1);
}
NODE
  )
}

main() {
  cd "${ROOT}"

  require_executable "${PYTHON}"
  require_executable "${ROOT}/mobile/node_modules/.bin/jest"

  run python3 scripts/check_app_store_release_pack.py
  run python3 scripts/check_ios_app_store_submission.py
  run bash -n scripts/mobile-local-qr.sh
  run bash -n scripts/mobile-ota.sh
  check_mobile_native_share_deps
  run_mobile_typecheck

  log_step "Latest iPhone QR install page"
  curl -fsSI "${IOS_LATEST_INSTALL_URL}" >/dev/null

  run_backend_pytest "Backend phone auth tests (mocked SMS only)" "${PHONE_AUTH_TESTS[@]}"
  run_backend_pytest "Backend HealthKit ingest tests" "${HEALTHKIT_BACKEND_TESTS[@]}"
  run_backend_pytest "Backend Watch safety/action tests" "${WATCH_BACKEND_TESTS[@]}"

  run_mobile_jest

  log_step "Watch companion Swift tests"
  swift test --package-path "${ROOT}/apps/watch"

  printf "\nMobile RC readiness passed.\n"
}

main "$@"
