#!/usr/bin/env bash

# Fast, fail-closed checks before starting the full release matrix.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE_REF="${REVA_PREFLIGHT_BASE_REF:-origin/main}"
EVENT_NAME="${REVA_PREFLIGHT_EVENT_NAME:-push}"
DRY_RUN="${REVA_PREFLIGHT_DRY_RUN:-0}"
PREFLIGHT_PYTHON="${REVA_PREFLIGHT_PYTHON:-${REPO_ROOT}/backend/venv/bin/python}"

if [[ "${DRY_RUN}" != "0" && "${DRY_RUN}" != "1" ]]; then
  echo "REVA_PREFLIGHT_DRY_RUN only accepts 0 or 1" >&2
  exit 2
fi

run() {
  printf '+ '
  printf '%q ' "$@"
  printf '\n'
  if [[ "${DRY_RUN}" == "0" ]]; then
    "$@"
  fi
}

if [[ -n "${REVA_PREFLIGHT_CHANGED_FILES:-}" ]]; then
  CHANGED_FILES="${REVA_PREFLIGHT_CHANGED_FILES}"
else
  if ! git -C "${REPO_ROOT}" rev-parse --verify "${BASE_REF}^{commit}" >/dev/null 2>&1; then
    echo "preflight cannot resolve base ref: ${BASE_REF}" >&2
    exit 2
  fi
  CHANGED_FILES="$(git -C "${REPO_ROOT}" diff --name-only "${BASE_REF}...HEAD")"
fi

CLASSIFICATION="$({ printf '%s\n' "${CHANGED_FILES}"; } | "${PREFLIGHT_PYTHON}" \
  "${REPO_ROOT}/scripts/ci_change_scope.py" \
  --event-name "${EVENT_NAME}" --format shell)"

DOCS_ONLY=0
RUN_DOCS=0
RUN_BACKEND=0
RUN_FRONTEND=0
RUN_MOBILE=0
RUN_MAC=0
RUN_TYPE_DRIFT=0
RUN_RELEASE=0
FULL=0
while IFS='=' read -r key value; do
  case "${key}" in
    DOCS_ONLY) DOCS_ONLY="${value}" ;;
    RUN_DOCS) RUN_DOCS="${value}" ;;
    RUN_BACKEND) RUN_BACKEND="${value}" ;;
    RUN_FRONTEND) RUN_FRONTEND="${value}" ;;
    RUN_MOBILE) RUN_MOBILE="${value}" ;;
    RUN_MAC) RUN_MAC="${value}" ;;
    RUN_TYPE_DRIFT) RUN_TYPE_DRIFT="${value}" ;;
    RUN_RELEASE) RUN_RELEASE="${value}" ;;
    FULL) FULL="${value}" ;;
    *) echo "unknown classifier output: ${key}" >&2; exit 2 ;;
  esac
done <<< "${CLASSIFICATION}"

printf 'preflight scope: docs_only=%s backend=%s frontend=%s mobile=%s mac=%s type_drift=%s release=%s full=%s\n' \
  "${DOCS_ONLY}" "${RUN_BACKEND}" "${RUN_FRONTEND}" "${RUN_MOBILE}" \
  "${RUN_MAC}" "${RUN_TYPE_DRIFT}" "${RUN_RELEASE}" "${FULL}"

if [[ "${DRY_RUN}" == "1" ]]; then
  echo "+ gh run list --branch main --workflow CI --limit 1 --json conclusion,status,headSha,url"
elif command -v gh >/dev/null 2>&1; then
  BASELINE_JSON="$(gh run list --branch main --workflow CI --limit 1 \
    --json conclusion,status,headSha,url)"
  "${PREFLIGHT_PYTHON}" - "${BASELINE_JSON}" <<'PY'
import json
import sys

runs = json.loads(sys.argv[1])
if not runs:
    raise SystemExit("preflight could not find a main CI baseline")
run = runs[0]
status = run.get("status")
conclusion = run.get("conclusion")
if status == "completed" and conclusion != "success":
    raise SystemExit(
        f"preflight main CI baseline is {conclusion}: {run.get('url', 'unknown')}"
    )
print(
    "main CI baseline: "
    f"status={status} conclusion={conclusion} sha={str(run.get('headSha', ''))[:9]}"
)
PY
else
  echo "warning: gh is unavailable; main CI baseline was not verified" >&2
fi

if [[ "${RUN_DOCS}" == "1" ]]; then
  run "${PREFLIGHT_PYTHON}" "${REPO_ROOT}/scripts/check_secret_leaks.py"
  run "${PREFLIGHT_PYTHON}" "${REPO_ROOT}/scripts/check_system_map.py"
  run "${PREFLIGHT_PYTHON}" "${REPO_ROOT}/backend/scripts/check_dossier_consistency.py"
fi

if [[ "${RUN_TYPE_DRIFT}" == "1" ]]; then
  run "${REPO_ROOT}/scripts/generate-api-types.sh" --check
fi

if [[ "${RUN_RELEASE}" == "1" ]]; then
  run "${PREFLIGHT_PYTHON}" -m pytest -q --no-cov --tb=short --maxfail=1 \
    "${REPO_ROOT}/scripts/test_release_ci_contract.py" \
    "${REPO_ROOT}/scripts/test_ci_change_scope.py" \
    "${REPO_ROOT}/scripts/test_release_lock.py"
fi

if [[ "${RUN_MOBILE}" == "1" && "${FULL}" != "1" ]]; then
  run "${REPO_ROOT}/scripts/mobile-fast-test.sh"
fi

if [[ "${RUN_FRONTEND}" == "1" && "${FULL}" != "1" ]]; then
  run npm --prefix "${REPO_ROOT}/frontend" run lint
fi

if [[ "${RUN_MAC}" == "1" && "${FULL}" != "1" ]]; then
  run swift test --package-path "${REPO_ROOT}/apps/mac" \
    --filter HealthAgentMacCoreTests
fi

echo "preflight passed"
