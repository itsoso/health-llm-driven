#!/usr/bin/env bash
# OTA 推送 mobile/ JS bundle 到已安装的小巴
#
# 何时用:
#   - 改了 .ts/.tsx/.js (JS 逻辑/UI/RN 组件) → 用本脚本, 30 秒内到设备
#   - 改了 native (Info.plist / Pods / app.json plugins / SDK 升级) → 必须 eas build
#
# 用法:
#   ./scripts/mobile-ota.sh                # 推到 production channel (默认)
#   ./scripts/mobile-ota.sh preview        # 推到 preview
#   ./scripts/mobile-ota.sh production "fix briefing pinning"
#   ./scripts/mobile-ota.sh rokid-production "Rokid diagnostics"

set -euo pipefail

CHANNEL="${1:-production}"
MESSAGE="${2:-$(git log -1 --pretty=format:'%s')}"
ENVIRONMENT="${CHANNEL}"

case "${CHANNEL}" in
  rokid-production)
    ENVIRONMENT="production"
    ;;
  rokid-preview)
    ENVIRONMENT="preview"
    ;;
esac

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ANCHOR_FILE="${OTA_ANCHOR_FILE:-${REPO_ROOT}/.last-ota-commit}"
MANIFEST_FILE="${OTA_MANIFEST_FILE:-${REPO_ROOT}/.mobile-release-manifest.json}"
source "${REPO_ROOT}/scripts/release_lock.sh"
acquire_release_lock "ota:${CHANNEL}"

# ── 发版前置守卫(2026-07-11 评审加固):OTA 打的是**工作树**,不是 HEAD ──
# 两类历史事故:① 脏树 WIP 泄进生产 bundle;② 落后 origin/main 的树整包回滚他人已上线工作。
# 机械拦截,不再靠纪律。逃生口:OTA_ALLOW_DIRTY=1(仅限明知故犯的调试)。
if [[ "${OTA_ALLOW_DIRTY:-0}" != "1" ]]; then
  git -C "${REPO_ROOT}" fetch origin --quiet
  _HEAD="$(git -C "${REPO_ROOT}" rev-parse HEAD)"
  _MAIN="$(git -C "${REPO_ROOT}" rev-parse origin/main)"
  if [[ "${_HEAD}" != "${_MAIN}" ]]; then
    echo "✗ OTA 拒绝:HEAD (${_HEAD:0:9}) ≠ origin/main (${_MAIN:0:9})。"
    echo "  从落后/分叉的树发 OTA 会回滚已上线工作。请从干净的 origin/main worktree 发;明知故犯用 OTA_ALLOW_DIRTY=1。"
    exit 1
  fi
  _DIRTY="$(git -C "${REPO_ROOT}" status --porcelain -- mobile/ packages/shared/ | head -5)"
  if [[ -n "${_DIRTY}" ]]; then
    echo "✗ OTA 拒绝:mobile/ 或 packages/shared/ 有未提交改动(会把 WIP 打进生产 bundle):"
    echo "${_DIRTY}"
    echo "  请 stash/提交后再发;明知故犯用 OTA_ALLOW_DIRTY=1。"
    exit 1
  fi
fi

cd "${REPO_ROOT}/mobile"

# Some worktrees reuse a dependency directory where Expo keeps @expo/cli nested
# under expo/. EAS otherwise mistakes this for the legacy CLI and passes flags
# that current Expo exports no longer accept.
NESTED_EXPO_CLI_NODE_PATH="${REPO_ROOT}/mobile/node_modules/expo/node_modules"
if [[ -d "${NESTED_EXPO_CLI_NODE_PATH}/@expo/cli" ]]; then
  export NODE_PATH="${NESTED_EXPO_CLI_NODE_PATH}${NODE_PATH:+:${NODE_PATH}}"
fi

echo "==> EAS Update → channel=${CHANNEL}"
echo "    environment: ${ENVIRONMENT}"
echo "    message: ${MESSAGE}"
echo ""

# 不打 web bundle (react-native-maps 不支持 web)。先显式 export，再让所有
# EAS 重试复用同一个 input-dir；资产处理超时不再重复打同一份 Hermes bundle。
UPDATE_LOG="$(mktemp)"
HERMES_DIR=""
NO_BYTECODE_DIR=""
OTA_AUDIT_LOG="${OTA_AUDIT_LOG:-${REPO_ROOT}/.mobile-ota-audit.jsonl}"
SOURCE_COMMIT_SHA="$(git -C "${REPO_ROOT}" rev-parse HEAD)"
MAIN_COMMIT_SHA="$(git -C "${REPO_ROOT}" rev-parse origin/main 2>/dev/null || printf '%s' "${SOURCE_COMMIT_SHA}")"
MOBILE_TREE_DIGEST="$({
  git -C "${REPO_ROOT}" rev-parse "${SOURCE_COMMIT_SHA}:mobile"
  git -C "${REPO_ROOT}" rev-parse "${SOURCE_COMMIT_SHA}:packages/shared" 2>/dev/null || printf '%s\n' missing
} | shasum -a 256 | awk '{print $1}')"
RUNTIME_VERSION="${MOBILE_RUNTIME_VERSION:-$(python3 - "${REPO_ROOT}/mobile/app.json" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        value = json.load(handle).get("expo", {}).get("version")
except (OSError, ValueError, TypeError):
    value = None
print(value or "unknown")
PY
)}"

python3 - "${OTA_AUDIT_LOG}" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
path.touch(exist_ok=True)
PY

cleanup_mobile_ota() {
  rm -f "${UPDATE_LOG}"
  if [[ -n "${HERMES_DIR}" &&
        "${HERMES_DIR##*/}" == reva-mobile-ota-hermes.* ]]; then
    rm -rf -- "${HERMES_DIR}"
  fi
  if [[ -n "${NO_BYTECODE_DIR}" &&
        "${NO_BYTECODE_DIR##*/}" == reva-mobile-ota-js.* ]]; then
    rm -rf -- "${NO_BYTECODE_DIR}"
  fi
  release_release_lock
}
trap cleanup_mobile_ota EXIT

record_ota_audit() {
  local artifact_variant="$1"
  local attempt="$2"
  local result="$3"
  local failure_class="$4"
  local duration_seconds="$5"
  local group_id="${6:-}"
  local update_id="${7:-}"
  python3 - "${OTA_AUDIT_LOG}" "${CHANNEL}" "${ENVIRONMENT}" \
    "${RUNTIME_VERSION}" "${SOURCE_COMMIT_SHA}" "${MAIN_COMMIT_SHA}" \
    "${MOBILE_TREE_DIGEST}" "${artifact_variant}" "${attempt}" \
    "${result}" "${failure_class}" "${duration_seconds}" \
    "${group_id}" "${update_id}" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

(
    path,
    channel,
    environment,
    runtime_version,
    source_commit_sha,
    main_commit_sha,
    mobile_tree_digest,
    artifact_variant,
    attempt,
    result,
    failure_class,
    duration_seconds,
    group_id,
    update_id,
) = sys.argv[1:]
payload = {
    "schema_version": 1,
    "recorded_at": datetime.now(timezone.utc).isoformat(),
    "platform": "ios",
    "channel": channel,
    "environment": environment,
    "runtime_version": runtime_version,
    "source_commit_sha": source_commit_sha,
    "main_commit_sha": main_commit_sha,
    "mobile_tree_digest": mobile_tree_digest,
    "artifact_variant": artifact_variant,
    "attempt": int(attempt),
    "result": result,
    "failure_class": failure_class or None,
    "duration_seconds": int(duration_seconds),
    "group_id": group_id or None,
    "update_id": update_id or None,
}
with Path(path).open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
PY
}

export_artifact() {
  local variant="$1"
  local output_dir
  local started_at
  local export_exit
  if [[ "${variant}" == "no-bytecode" ]]; then
    if [[ -z "${NO_BYTECODE_DIR}" ]]; then
      NO_BYTECODE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/reva-mobile-ota-js.XXXXXX")"
    fi
    output_dir="${NO_BYTECODE_DIR}"
  else
    if [[ -z "${HERMES_DIR}" ]]; then
      HERMES_DIR="$(mktemp -d "${TMPDIR:-/tmp}/reva-mobile-ota-hermes.XXXXXX")"
    fi
    output_dir="${HERMES_DIR}"
  fi
  echo "==> Exporting ${variant} OTA artifact once: ${output_dir}"
  started_at="$(date +%s)"
  set +e
  if [[ -n "${OTA_EXPO_RUNNER:-}" ]]; then
    if [[ "${variant}" == "no-bytecode" ]]; then
      CI=1 "${OTA_EXPO_RUNNER}" export --platform ios \
        --output-dir "${output_dir}" --no-bytecode \
        --dump-assetmap --source-maps 2>&1 | tee "${UPDATE_LOG}"
    else
      CI=1 "${OTA_EXPO_RUNNER}" export --platform ios \
        --output-dir "${output_dir}" \
        --dump-assetmap --source-maps 2>&1 | tee "${UPDATE_LOG}"
    fi
  elif [[ "${variant}" == "no-bytecode" ]]; then
    CI=1 npx expo export --platform ios \
      --output-dir "${output_dir}" --no-bytecode \
      --dump-assetmap --source-maps 2>&1 | tee "${UPDATE_LOG}"
  else
    CI=1 npx expo export --platform ios \
      --output-dir "${output_dir}" \
      --dump-assetmap --source-maps 2>&1 | tee "${UPDATE_LOG}"
  fi
  export_exit=$?
  set -e
  LAST_ATTEMPT_DURATION="$(($(date +%s) - started_at))"
  EXPORTED_ARTIFACT_DIR="${output_dir}"
  return "${export_exit}"
}

run_update_attempt() {
  local artifact_variant="$1"
  local input_dir="$2"
  local attempt="$3"
  local started_at
  local exit_code
  echo "==> Upload attempt ${attempt}: variant=${artifact_variant} --input-dir ${input_dir} --skip-bundler"
  started_at="$(date +%s)"
  set +e
  if [[ -n "${OTA_EAS_RUNNER:-}" ]]; then
    CI=1 "${OTA_EAS_RUNNER}" update --channel "${CHANNEL}" \
      --message "${MESSAGE}" --platform ios --environment "${ENVIRONMENT}" \
      --input-dir "${input_dir}" --skip-bundler 2>&1 | tee "${UPDATE_LOG}"
  else
    CI=1 npx eas-cli update --channel "${CHANNEL}" \
      --message "${MESSAGE}" --platform ios --environment "${ENVIRONMENT}" \
      --input-dir "${input_dir}" --skip-bundler 2>&1 | tee "${UPDATE_LOG}"
  fi
  exit_code=$?
  set -e
  LAST_ATTEMPT_DURATION="$(($(date +%s) - started_at))"
  return "${exit_code}"
}

classify_update_failure() {
  if grep -Eiq 'Authentication|not authorized|invalid token|runtime version|bundle error|syntax error|Metro encountered' "${UPDATE_LOG}"; then
    printf '%s\n' non_retryable
  elif grep -Eiq 'Asset processing timed out for assets' "${UPDATE_LOG}"; then
    printf '%s\n' asset_processing_timeout
  elif grep -Eiq 'Asset processing timed out|ETIMEDOUT|ECONNRESET|Failed to upload|network.*timed out|request failed' "${UPDATE_LOG}"; then
    printf '%s\n' transient
  else
    printf '%s\n' non_retryable
  fi
}

if [[ "${OTA_FORCE_NO_BYTECODE:-0}" != "0" &&
      "${OTA_FORCE_NO_BYTECODE:-0}" != "1" ]]; then
  echo "✗ OTA_FORCE_NO_BYTECODE 只接受 0/1。" >&2
  exit 1
fi

LAST_ATTEMPT_DURATION=0
FINAL_VARIANT="hermes"
FINAL_ATTEMPT=1
if [[ "${OTA_FORCE_NO_BYTECODE:-0}" == "1" ]]; then
  FINAL_VARIANT="no-bytecode"
  if export_artifact "${FINAL_VARIANT}"; then
    :
  else
    EXPORT_EXIT=$?
    record_ota_audit "${FINAL_VARIANT}" 0 failed export_failed "${LAST_ATTEMPT_DURATION}"
    echo "✗ Forced OTA no-bytecode export failed." >&2
    exit "${EXPORT_EXIT}"
  fi
  if run_update_attempt "${FINAL_VARIANT}" "${EXPORTED_ARTIFACT_DIR}" 1; then
    :
  else
    UPDATE_EXIT=$?
    FAILURE_CLASS="$(classify_update_failure)"
    record_ota_audit "${FINAL_VARIANT}" 1 failed "${FAILURE_CLASS}" "${LAST_ATTEMPT_DURATION}"
    echo "✗ Forced OTA no-bytecode update failed." >&2
    exit "${UPDATE_EXIT}"
  fi
else
  if export_artifact hermes; then
    :
  else
    EXPORT_EXIT=$?
    record_ota_audit hermes 0 failed export_failed "${LAST_ATTEMPT_DURATION}"
    echo "✗ OTA Hermes export failed." >&2
    exit "${EXPORT_EXIT}"
  fi
  HERMES_ARTIFACT_DIR="${EXPORTED_ARTIFACT_DIR}"
  if run_update_attempt hermes "${HERMES_ARTIFACT_DIR}" 1; then
    FINAL_VARIANT="hermes"
    FINAL_ATTEMPT=1
  else
    FIRST_EXIT=$?
    FAILURE_CLASS="$(classify_update_failure)"
    if [[ "${FAILURE_CLASS}" == "non_retryable" ]]; then
      record_ota_audit hermes 1 failed "${FAILURE_CLASS}" "${LAST_ATTEMPT_DURATION}"
      echo "✗ OTA failed with a non-retryable configuration or authentication error." >&2
      exit "${FIRST_EXIT}"
    fi
    record_ota_audit hermes 1 attempt_failed "${FAILURE_CLASS}" "${LAST_ATTEMPT_DURATION}"
    if [[ "${FAILURE_CLASS}" == "transient" ]]; then
      echo "△ Temporary EAS upload failure; reusing the same Hermes artifact once..." >&2
      sleep "${OTA_RETRY_DELAY_SECONDS:-1}"
      FINAL_ATTEMPT=2
      if run_update_attempt hermes "${HERMES_ARTIFACT_DIR}" "${FINAL_ATTEMPT}"; then
        FINAL_VARIANT="hermes"
      else
        SECOND_EXIT=$?
        FAILURE_CLASS="$(classify_update_failure)"
        if [[ "${FAILURE_CLASS}" != "asset_processing_timeout" ]]; then
          record_ota_audit hermes 2 failed "${FAILURE_CLASS}" "${LAST_ATTEMPT_DURATION}"
          echo "✗ OTA failed after one artifact-reuse retry." >&2
          exit "${SECOND_EXIT}"
        fi
        record_ota_audit hermes 2 attempt_failed "${FAILURE_CLASS}" "${LAST_ATTEMPT_DURATION}"
      fi
    fi
    if [[ "${FAILURE_CLASS}" == "asset_processing_timeout" ]]; then
      echo "△ EAS asset processing timed out; exporting one no-bytecode fallback." >&2
      if export_artifact no-bytecode; then
        :
      else
        EXPORT_EXIT=$?
        record_ota_audit no-bytecode 0 failed export_failed "${LAST_ATTEMPT_DURATION}"
        exit "${EXPORT_EXIT}"
      fi
      FINAL_VARIANT="no-bytecode"
      FINAL_ATTEMPT=$((FINAL_ATTEMPT + 1))
      if run_update_attempt no-bytecode "${EXPORTED_ARTIFACT_DIR}" "${FINAL_ATTEMPT}"; then
        :
      else
        FALLBACK_EXIT=$?
        FAILURE_CLASS="$(classify_update_failure)"
        record_ota_audit no-bytecode "${FINAL_ATTEMPT}" failed "${FAILURE_CLASS}" "${LAST_ATTEMPT_DURATION}"
        echo "✗ OTA no-bytecode fallback failed." >&2
        exit "${FALLBACK_EXIT}"
      fi
    fi
  fi
fi

GROUP_ID="$(grep -Eio 'Update group ID[[:space:]:]+[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' "${UPDATE_LOG}" | awk '{print $NF}' | sed -n '$p' || true)"
IOS_UPDATE_ID="$(grep -Eio 'iOS update ID[[:space:]:]+[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' "${UPDATE_LOG}" | awk '{print $NF}' | sed -n '$p' || true)"
if [[ -z "${GROUP_ID}" || -z "${IOS_UPDATE_ID}" ]]; then
  record_ota_audit "${FINAL_VARIANT}" "${FINAL_ATTEMPT}" failed \
    missing_identifiers "${LAST_ATTEMPT_DURATION}"
  echo "✗ OTA command exited successfully, but published identifier verification failed." >&2
  echo "  Refusing to update the production anchor without an EAS group ID and iOS update ID." >&2
  exit 1
fi

echo "    verified update group: ${GROUP_ID}"
echo "    verified iOS update: ${IOS_UPDATE_ID}"

# 记录可审计的发布事实和上一组已知可回滚更新。文件默认被 gitignore，
# 生产回滚只依赖 EAS group/update ID，不依赖当前工作树是否还保留发布代码。
python3 - "${MANIFEST_FILE}" "${CHANNEL}" "${ENVIRONMENT}" "${GROUP_ID}" "${IOS_UPDATE_ID}" "${SOURCE_COMMIT_SHA}" "${RUNTIME_VERSION}" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

path, channel, environment, group_id, update_id, commit_sha, runtime_version = sys.argv[1:]
manifest_path = Path(path)
previous = {}
if manifest_path.exists():
    try:
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}

previous_update_id = previous.get("active_update_id") or previous.get("update_id")
previous_group_id = previous.get("active_group_id") or previous.get("group_id")
payload = {
    "schema_version": 1,
    "status": "published",
    "platform": "ios",
    "channel": channel,
    "environment": environment,
    "runtime_version": runtime_version,
    "group_id": group_id,
    "update_id": update_id,
    "active_group_id": group_id,
    "active_update_id": update_id,
    "commit_sha": commit_sha,
    "published_at": datetime.now(timezone.utc).isoformat(),
    "previous_known_good_group_id": previous_group_id,
    "previous_known_good_update_id": previous_update_id,
}
manifest_path.parent.mkdir(parents=True, exist_ok=True)
tmp_path = manifest_path.with_name(f".{manifest_path.name}.tmp")
tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
os.replace(tmp_path, manifest_path)
PY
echo "    release manifest 写入 ${MANIFEST_FILE}"
record_ota_audit "${FINAL_VARIANT}" "${FINAL_ATTEMPT}" published "" \
  "${LAST_ATTEMPT_DURATION}" "${GROUP_ID}" "${IOS_UPDATE_ID}"

# 只有 EAS 标识验证和 manifest 原子写入都成功后，才记录这次 OTA 对应的
# commit，避免 deploy.sh 把一条不完整的发布记录当作已发布状态。
if [ "${CHANNEL}" = "production" ]; then
  CURRENT_COMMIT=$(git -C "${REPO_ROOT}" rev-parse HEAD)
  printf '%s\n' "${CURRENT_COMMIT}" > "${ANCHOR_FILE}"
  echo "    anchor 写入 ${ANCHOR_FILE} (${CURRENT_COMMIT:0:8})"
fi

echo ""
echo "✓ 推送完成. App 回到前台会下载更新,由用户确认后立即应用."
