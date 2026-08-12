#!/usr/bin/env bash

# Generate both API clients from the backend schema using a lock-addressed
# Python 3.12 environment. CI can reuse an environment it installed from the
# same lock, but version verification remains mandatory.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCK_FILE="${REPO_ROOT}/backend/requirements.lock"
MODE="write"
DRY_RUN="${API_TYPES_DRY_RUN:-0}"
USE_CURRENT_ENV="${API_TYPES_USE_CURRENT_ENV:-0}"
CACHE_ROOT="${API_TYPES_CACHE_ROOT:-${XDG_CACHE_HOME:-${HOME}/.cache}/reva/api-types}"
BOOTSTRAP_PYTHON="${API_TYPES_BOOTSTRAP_PYTHON:-python3.12}"

if [[ "${1:-}" == "--check" ]]; then
  MODE="check"
  shift
elif [[ -n "${1:-}" ]]; then
  echo "usage: $0 [--check]" >&2
  exit 2
fi
if [[ "$#" -ne 0 ]]; then
  echo "usage: $0 [--check]" >&2
  exit 2
fi
for toggle in "${DRY_RUN}" "${USE_CURRENT_ENV}"; do
  if [[ "${toggle}" != "0" && "${toggle}" != "1" ]]; then
    echo "API_TYPES_DRY_RUN and API_TYPES_USE_CURRENT_ENV only accept 0 or 1" >&2
    exit 2
  fi
done

LOCK_DIGEST="$(shasum -a 256 "${LOCK_FILE}" | awk '{print $1}')"
CACHED_ENV="${CACHE_ROOT}/python312-${LOCK_DIGEST}"
CACHED_MARKER="${CACHED_ENV}/reva-requirements-lock.sha256"

print_command() {
  printf '+ '
  printf '%q ' "$@"
  printf '\n'
}

validate_locked_python() {
  local python_bin="$1"
  if [[ "${DRY_RUN}" == "1" ]]; then
    echo "+ ${python_bin} verify Python 3.12 and every requirements.lock version"
    return 0
  fi
  "${python_bin}" - "${LOCK_FILE}" <<'PY'
import importlib.metadata
import sys
from pathlib import Path

from packaging.requirements import Requirement

if sys.version_info[:2] != (3, 12):
    raise SystemExit(
        f"API type generation requires Python 3.12, got {sys.version_info.major}.{sys.version_info.minor}"
    )

lock_path = Path(sys.argv[1])
errors = []
for raw_line in lock_path.read_text(encoding="utf-8").splitlines():
    if not raw_line or raw_line[0].isspace() or raw_line.startswith(("#", "--")):
        continue
    candidate = raw_line.removesuffix(" \\").strip()
    if not candidate:
        continue
    requirement = Requirement(candidate)
    if requirement.marker and not requirement.marker.evaluate():
        continue
    try:
        installed = importlib.metadata.version(requirement.name)
    except importlib.metadata.PackageNotFoundError:
        errors.append(f"{requirement.name}: missing")
        continue
    if installed not in requirement.specifier:
        errors.append(
            f"{requirement.name}: installed={installed} expected={requirement.specifier}"
        )
if errors:
    raise SystemExit("locked Python environment mismatch:\n" + "\n".join(errors))
PY
}

if [[ "${USE_CURRENT_ENV}" == "1" ]]; then
  API_PYTHON="${API_TYPES_PYTHON:-python3.12}"
elif [[ "${DRY_RUN}" == "1" ]]; then
  API_PYTHON="${CACHED_ENV}/bin/python"
  print_command mkdir -p "${CACHE_ROOT}"
  print_command "${BOOTSTRAP_PYTHON}" -m venv "${CACHED_ENV}"
  print_command "${CACHED_ENV}/bin/pip" install --require-hashes -r "${LOCK_FILE}"
else
  mkdir -p "${CACHE_ROOT}"
  if [[ ! -x "${CACHED_ENV}/bin/python" ||
        ! -r "${CACHED_MARKER}" ||
        "$(cat "${CACHED_MARKER}" 2>/dev/null || true)" != "${LOCK_DIGEST}" ]]; then
    BUILD_ENV="$(mktemp -d "${CACHE_ROOT}/.python312-${LOCK_DIGEST}.XXXXXX")"
    cleanup_build_env() {
      if [[ -n "${BUILD_ENV:-}" && -d "${BUILD_ENV}" ]]; then
        rm -rf -- "${BUILD_ENV}"
      fi
    }
    trap cleanup_build_env EXIT
    "${BOOTSTRAP_PYTHON}" -m venv "${BUILD_ENV}"
    "${BUILD_ENV}/bin/pip" install --require-hashes -r "${LOCK_FILE}"
    printf '%s\n' "${LOCK_DIGEST}" > "${BUILD_ENV}/reva-requirements-lock.sha256"
    if [[ -e "${CACHED_ENV}" ]]; then
      rm -rf -- "${CACHED_ENV}"
    fi
    mv "${BUILD_ENV}" "${CACHED_ENV}"
    BUILD_ENV=""
    trap - EXIT
  fi
  API_PYTHON="${CACHED_ENV}/bin/python"
fi

validate_locked_python "${API_PYTHON}"

if [[ "${DRY_RUN}" == "1" ]]; then
  WORK_DIR="${TMPDIR:-/tmp}/reva-api-types.dry-run"
  print_command "${API_PYTHON}" dump-openapi "${WORK_DIR}/openapi.json"
  print_command npx --yes openapi-typescript@7.13.0 \
    "${WORK_DIR}/openapi.json" -o "${WORK_DIR}/mobile.generated.ts"
  print_command npx --yes openapi-typescript@7.13.0 \
    "${WORK_DIR}/openapi.json" -o "${WORK_DIR}/frontend.generated.ts"
else
  WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/reva-api-types.XXXXXX")"
  cleanup_work_dir() {
    rm -rf -- "${WORK_DIR}"
  }
  trap cleanup_work_dir EXIT
  (
    cd "${REPO_ROOT}/backend"
    SECRET_KEY='type-generation-secret-key-32-chars!!' \
      GARMIN_ENCRYPTION_KEY='mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU=' \
      DATABASE_URL='sqlite:///:memory:' \
      SKIP_DB_INIT=1 \
      "${API_PYTHON}" - "${WORK_DIR}/openapi.json" <<'PY'
import json
import sys

from main import app

with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(app.openapi(), handle, ensure_ascii=False)
PY
  )
  npx --yes openapi-typescript@7.13.0 \
    "${WORK_DIR}/openapi.json" -o "${WORK_DIR}/mobile.generated.ts"
  npx --yes openapi-typescript@7.13.0 \
    "${WORK_DIR}/openapi.json" -o "${WORK_DIR}/frontend.generated.ts"
fi

MOBILE_TARGET="${REPO_ROOT}/mobile/types/api.generated.ts"
FRONTEND_TARGET="${REPO_ROOT}/frontend/src/types/api.generated.ts"

if [[ "${MODE}" == "check" ]]; then
  if [[ "${DRY_RUN}" == "1" ]]; then
    print_command cmp "${WORK_DIR}/mobile.generated.ts" "${MOBILE_TARGET}"
    print_command cmp "${WORK_DIR}/frontend.generated.ts" "${FRONTEND_TARGET}"
  else
    status=0
    for pair in \
      "${WORK_DIR}/mobile.generated.ts:${MOBILE_TARGET}" \
      "${WORK_DIR}/frontend.generated.ts:${FRONTEND_TARGET}"; do
      generated="${pair%%:*}"
      target="${pair#*:}"
      if ! cmp -s "${generated}" "${target}"; then
        diff -u --label "tracked:${target#${REPO_ROOT}/}" \
          --label "generated:${target#${REPO_ROOT}/}" "${target}" "${generated}" || true
        status=1
      fi
    done
    if [[ "${status}" -ne 0 ]]; then
      echo "API clients drifted; run ./scripts/generate-api-types.sh and commit both outputs" >&2
      exit "${status}"
    fi
  fi
else
  if [[ "${DRY_RUN}" == "1" ]]; then
    print_command cp "${WORK_DIR}/mobile.generated.ts" "${MOBILE_TARGET}"
    print_command cp "${WORK_DIR}/frontend.generated.ts" "${FRONTEND_TARGET}"
  else
    cp "${WORK_DIR}/mobile.generated.ts" "${MOBILE_TARGET}"
    cp "${WORK_DIR}/frontend.generated.ts" "${FRONTEND_TARGET}"
  fi
fi

echo "API type generation ${MODE} passed (${LOCK_DIGEST:0:12})"
