#!/usr/bin/env bash
# Fast mobile feedback gate: run only checks related to the current mobile diff.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MOBILE_DIR="${REPO_ROOT}/mobile"
DRY_RUN="${MOBILE_FAST_TEST_DRY_RUN:-0}"
MODE="${1:-}"

print_command() {
  local directory="$1"
  shift
  printf '+ (cd %q &&' "${directory}"
  printf ' %q' "$@"
  printf ')\n'
}

run_in() {
  local directory="$1"
  shift
  if [[ "${DRY_RUN}" == "1" ]]; then
    print_command "${directory}" "$@"
  else
    (cd "${directory}" && "$@")
  fi
}

run_typecheck() {
  if [[ "${DRY_RUN}" != "1" ]]; then
    mkdir -p "${MOBILE_DIR}/.cache"
  fi
  run_in "${MOBILE_DIR}" npx tsc --noEmit --incremental --tsBuildInfoFile .cache/tsconfig.fast.tsbuildinfo
}

run_full_gate() {
  # The historical full suite leaves background handles open after all assertions pass.
  # Keep local feedback bounded; CI remains the authoritative no-force-exit gate.
  run_in "${MOBILE_DIR}" npm test -- --runInBand --forceExit
  run_in "${MOBILE_DIR}" npm run lint
  run_typecheck
  run_in "${REPO_ROOT}" git -C "${REPO_ROOT}" diff --check
}

if [[ "${MODE}" == "--all" ]]; then
  echo "==> Mobile full gate"
  run_full_gate
  exit 0
fi

if [[ -n "${MODE}" ]]; then
  echo "Usage: $0 [--all]" >&2
  exit 2
fi

if [[ -n "${MOBILE_FAST_TEST_CHANGED_FILES:-}" ]]; then
  CHANGED_FILES="${MOBILE_FAST_TEST_CHANGED_FILES}"
else
  CHANGED_FILES="$({
    git -C "${REPO_ROOT}" diff --name-only --diff-filter=ACMR HEAD -- mobile/ packages/shared/
    git -C "${REPO_ROOT}" ls-files --others --exclude-standard -- mobile/ packages/shared/
  } | awk 'NF && !seen[$0]++')"
fi

CODE_FILES=()
HAS_SHARED_CHANGE=0
while IFS= read -r file; do
  [[ -z "${file}" ]] && continue
  case "${file}" in
    packages/shared/*)
      HAS_SHARED_CHANGE=1
      ;;
    mobile/*.ts|mobile/*.tsx|mobile/*.js|mobile/*.jsx)
      CODE_FILES[${#CODE_FILES[@]}]="${file#mobile/}"
      ;;
  esac
done <<< "${CHANGED_FILES}"

if [[ "${HAS_SHARED_CHANGE}" == "1" ]]; then
  echo "==> Shared package changed; running the full mobile gate"
  run_full_gate
  exit 0
fi

echo "==> Mobile changed-file gate"
if [[ "${#CODE_FILES[@]}" -gt 0 ]]; then
  run_in "${MOBILE_DIR}" npx jest --findRelatedTests "${CODE_FILES[@]}" --runInBand --passWithNoTests
  run_in "${MOBILE_DIR}" npx eslint "${CODE_FILES[@]}"
  run_typecheck
else
  echo "    No changed JS/TS files; skipping Jest, ESLint, and TypeScript."
fi

run_in "${REPO_ROOT}" git -C "${REPO_ROOT}" diff --check
