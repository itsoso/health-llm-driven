#!/bin/bash
# Persistently activate the sealed health-evidence runtime from an immutable
# release stage. This file is executed from the stage, never from the checked
# out repository, so a concurrent checkout cannot replace the running program.
set -Eeuo pipefail

usage() {
    cat >&2 <<'EOF'
Usage:
  activate_health_evidence_runtime.sh --activate \
    <repo> <40-sha> <candidate.env> <guard.env> <success-marker> \
    <release-lock-dir> <release-lock-token>
  activate_health_evidence_runtime.sh --recover-if-unverified \
    <repo> <40-sha> <candidate.env> <guard.env> <success-marker> \
    <release-lock-dir> <release-lock-token>
EOF
    exit 2
}

MODE="${1:-}"
case "$MODE" in
    --activate)
        [ "$#" -eq 8 ] || usage
        REPO_PATH="$2"
        EXPECTED_SHA="$3"
        CANDIDATE_ENV="$4"
        GUARD_ENV="$5"
SUCCESS_MARKER="$6"
        RELEASE_LOCK_DIR="$7"
        RELEASE_LOCK_TOKEN="$8"
        ;;
    --recover-if-unverified)
        [ "$#" -eq 8 ] || usage
        REPO_PATH="$2"
        EXPECTED_SHA="$3"
        CANDIDATE_ENV="$4"
        GUARD_ENV="$5"
        SUCCESS_MARKER="$6"
        RELEASE_LOCK_DIR="$7"
        RELEASE_LOCK_TOKEN="$8"
        ;;
    *)
        usage
        ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"
STAGED_HASH_MANIFEST="$SCRIPT_DIR/staged.sha256"
TARGET_ENV="$REPO_PATH/backend/.env"
OUTCOME_FILE="${SUCCESS_MARKER}.outcome"
HEALTH_URL="${HEALTH_EVIDENCE_ACTIVATION_HEALTH_URL:-http://127.0.0.1:8000/api/v1/health}"
AUTH_URL="${HEALTH_EVIDENCE_ACTIVATION_AUTH_URL:-http://127.0.0.1:8000/api/v1/auth/me}"
HEALTH_BASE_URL="${HEALTH_EVIDENCE_ACTIVATION_BASE_URL:-http://127.0.0.1:8000}"
HEALTH_ATTEMPTS="${HEALTH_EVIDENCE_ACTIVATION_ATTEMPTS:-30}"
SYSTEMD_RUNTIME_DIR="${HEALTH_EVIDENCE_ACTIVATION_SYSTEMD_RUNTIME_DIR:-/run/systemd/system}"
SYSTEMD_PERSISTENT_DIR="${HEALTH_EVIDENCE_ACTIVATION_SYSTEMD_PERSISTENT_DIR:-/etc/systemd/system}"
RUNTIME_STATE_DIR="${HEALTH_EVIDENCE_ACTIVATION_RUNTIME_STATE_DIR:-/run/reva-health-evidence-activation}"
RUNTIME_ENABLED_ENV="$RUNTIME_STATE_DIR/enabled.env"
DURABLE_STATE_DIR="${HEALTH_EVIDENCE_ACTIVATION_DURABLE_STATE_DIR:-/var/lib/reva-health-evidence-runtime}"
DURABLE_ENABLED_ENV="$DURABLE_STATE_DIR/enabled.env"
PROC_ROOT="${HEALTH_EVIDENCE_ACTIVATION_PROC_ROOT:-/proc}"
CGROUP_ROOT="${HEALTH_EVIDENCE_ACTIVATION_CGROUP_ROOT:-/sys/fs/cgroup}"
RUNTIME_OVERRIDE_NAME="90-reva-health-evidence-activation.conf"
PERSISTENT_OVERRIDE_NAME="80-reva-health-evidence-runtime.conf"
SERVICES=(
    health-backend.socket
    health-backend
    celery-worker
    celery-beat
)
RUNTIME_OVERRIDE_UNITS=(
    health-backend.service
    celery-worker.service
    celery-beat.service
)
PROCESS_UNITS=(
    health-backend.service
    celery-worker.service
    celery-beat.service
)
SUCCESS_SENTINEL="HEALTH_EVIDENCE_ACTIVATION_OK commit=$EXPECTED_SHA flag=true health=passed auth_probe=passed score=passed contract=enabled services=active"
ROLLBACK_SENTINEL="HEALTH_EVIDENCE_ACTIVATION_ROLLED_BACK commit=$EXPECTED_SHA flag=false health=passed contract=staged services=active"
BLOCKED_SENTINEL="HEALTH_EVIDENCE_ACTIVATION_BLOCKED commit=$EXPECTED_SHA flag=unknown services=inactive containment=passed manual_intervention=required"
CONTAINMENT_FAILED_SENTINEL="HEALTH_EVIDENCE_ACTIVATION_BLOCKED commit=$EXPECTED_SHA flag=unknown services=unverified containment=failed manual_intervention=required"

require_safe_absolute_path() {
    local value="$1"
    local label="$2"
    if [[ ! "$value" =~ ^/[A-Za-z0-9._/-]+$ ||
        "$value" = "/" ||
        "$value" = *"/../"* ||
        "$value" = *"/.." ||
        "$value" = *"/./"* ||
        "$value" = *"/." ]]; then
        echo "$label must be a safe absolute path" >&2
        return 1
    fi
}

assert_release_lease() {
    test -r "$RELEASE_LOCK_DIR/token" &&
        test "$(cat "$RELEASE_LOCK_DIR/token")" = "$RELEASE_LOCK_TOKEN"
}

manifest_entry_count() {
    local expected_name="$1"
    awk -v expected="$expected_name" '
        $2 == expected { count += 1 }
        END { print count + 0 }
    ' "$STAGED_HASH_MANIFEST"
}

verify_immutable_stage() {
    local artifact
    local artifact_name
    local non_regular_entry
    local stage_file_count=0
    local manifest_count

    test -r "$STAGED_HASH_MANIFEST" || return 1
    test ! -L "$STAGED_HASH_MANIFEST" || return 1
    non_regular_entry="$(
        find "$SCRIPT_DIR" -mindepth 1 -maxdepth 1 ! -type f -print -quit
    )"
    [ -z "$non_regular_entry" ] || return 1
    awk '
        NF != 2 { exit 1 }
        length($1) != 64 || $1 ~ /[^0-9a-f]/ { exit 1 }
        $2 !~ /^[A-Za-z0-9._-]+$/ { exit 1 }
        $2 == "staged.sha256" { exit 1 }
        seen[$2]++ { exit 1 }
    ' "$STAGED_HASH_MANIFEST" || return 1

    while IFS= read -r artifact; do
        artifact_name="$(basename "$artifact")"
        [[ "$artifact_name" =~ ^[A-Za-z0-9._-]+$ ]] || return 1
        [ "$(manifest_entry_count "$artifact_name")" -eq 1 ] || return 1
        stage_file_count=$((stage_file_count + 1))
    done < <(
        find "$SCRIPT_DIR" -maxdepth 1 -type f \
            ! -name staged.sha256 -print
    )
    manifest_count="$(
        awk 'NF { count += 1 } END { print count + 0 }' \
            "$STAGED_HASH_MANIFEST"
    )"
    [ "$stage_file_count" -eq "$manifest_count" ] || return 1
    [ "$(manifest_entry_count "$SCRIPT_NAME")" -eq 1 ] || return 1
    [ "$(manifest_entry_count "$(basename "$GUARD_ENV")")" -eq 1 ] ||
        return 1
    [ "$(manifest_entry_count "$(basename "$CANDIDATE_ENV")")" -eq 1 ] ||
        return 1
    (
        cd "$SCRIPT_DIR"
        sha256sum -c staged.sha256 >/dev/null
    )
}

verify_flag_file() {
    local env_file="$1"
    local expected="$2"
    test -r "$env_file" || return 1
    awk -v expected="$expected" '
        /^[[:space:]]*(export[[:space:]]+)?HEALTH_EVIDENCE_RUNTIME_ENABLED[[:space:]]*=/ {
            assignments += 1
        }
        $0 == "HEALTH_EVIDENCE_RUNTIME_ENABLED=" expected {
            canonical += 1
        }
        END {
            exit(assignments == 1 && canonical == 1 ? 0 : 1)
        }
    ' "$env_file"
}

verify_repo_revision() {
    test "$(git -C "$REPO_PATH" rev-parse HEAD)" = "$EXPECTED_SHA" &&
        test -z "$(
            git -C "$REPO_PATH" status --porcelain --untracked-files=all
        )"
}

verify_services_active() {
    local unit
    local state
    for unit in "${SERVICES[@]}"; do
        state="$(
            systemctl show "$unit" --property=ActiveState --value 2>/dev/null
        )" || return 1
        [ "$state" = "active" ] || return 1
    done
}

restart_services_in_order() {
    local unit
    for unit in "${SERVICES[@]}"; do
        assert_release_lease || return 1
        systemctl restart "$unit" || return 1
    done
    verify_services_active
}

runtime_override_path() {
    local unit="$1"
    printf '%s/%s.d/%s' \
        "$SYSTEMD_RUNTIME_DIR" "$unit" "$RUNTIME_OVERRIDE_NAME"
}

persistent_override_path() {
    local unit="$1"
    printf '%s/%s.d/%s' \
        "$SYSTEMD_PERSISTENT_DIR" "$unit" "$PERSISTENT_OVERRIDE_NAME"
}

verify_persistent_override_contract() {
    local unit
    local override_file
    local expected_file
    expected_file="$(mktemp)"
    printf '%s\n' \
        "[Service]" \
        "EnvironmentFile=-$DURABLE_ENABLED_ENV" >"$expected_file"
    for unit in "${RUNTIME_OVERRIDE_UNITS[@]}"; do
        override_file="$(persistent_override_path "$unit")"
        if [ ! -f "$override_file" ] ||
            [ -L "$override_file" ] ||
            ! cmp -s "$expected_file" "$override_file" ||
            [ "$(stat -c '%U:%G:%a' "$override_file")" != \
                "root:root:644" ]; then
            rm -f -- "$expected_file"
            return 1
        fi
    done
    rm -f -- "$expected_file"
}

install_persistent_override_contract() {
    local unit
    local dropin_dir
    local override_file
    local override_tmp

    assert_release_lease || return 1
    if [ ! -d "$DURABLE_STATE_DIR" ]; then
        mkdir -m 0700 -- "$DURABLE_STATE_DIR" || return 1
    fi
    test ! -L "$DURABLE_STATE_DIR" || return 1
    test "$(stat -c '%U:%G:%a' "$DURABLE_STATE_DIR")" = \
        "root:root:700" || return 1
    test ! -e "$DURABLE_ENABLED_ENV" || return 1
    for unit in "${RUNTIME_OVERRIDE_UNITS[@]}"; do
        dropin_dir="$SYSTEMD_PERSISTENT_DIR/$unit.d"
        if [ ! -d "$dropin_dir" ]; then
            mkdir -m 0755 -- "$dropin_dir" || return 1
        fi
        test ! -L "$dropin_dir" || return 1
        test "$(stat -c '%U:%G:%a' "$dropin_dir")" = \
            "root:root:755" || return 1
        override_file="$(persistent_override_path "$unit")"
        override_tmp="$(mktemp "$dropin_dir/.health-evidence.XXXXXX")" ||
            return 1
        if ! printf '%s\n' \
            "[Service]" \
            "EnvironmentFile=-$DURABLE_ENABLED_ENV" >"$override_tmp" ||
            ! chmod 0644 "$override_tmp" ||
            ! chown root:root "$override_tmp" ||
            ! sync -f "$override_tmp" ||
            ! mv -f -- "$override_tmp" "$override_file" ||
            ! sync -f "$dropin_dir"; then
            rm -f -- "$override_tmp"
            return 1
        fi
    done
    systemctl daemon-reload || return 1
    verify_persistent_override_contract || return 1
    assert_release_lease || return 1
}

durable_enabled_absent() {
    test ! -e "$DURABLE_ENABLED_ENV"
}

verify_durable_enabled_contract() {
    local expected_file
    local guard_hash
    test -f "$DURABLE_ENABLED_ENV" || return 1
    test ! -L "$DURABLE_ENABLED_ENV" || return 1
    guard_hash="$(sha256sum "$GUARD_ENV" | awk '{print $1}')" ||
        return 1
    expected_file="$(mktemp)"
    printf '%s\n' \
        "# commit=$EXPECTED_SHA" \
        "# guard_sha256=$guard_hash" \
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=true" >"$expected_file"
    if ! cmp -s "$expected_file" "$DURABLE_ENABLED_ENV"; then
        rm -f -- "$expected_file"
        return 1
    fi
    rm -f -- "$expected_file"
    verify_flag_file "$DURABLE_ENABLED_ENV" true || return 1
    test "$(stat -c '%U:%G:%a' "$DURABLE_ENABLED_ENV")" = \
        "root:root:400"
}

commit_durable_enabled() {
    local enabled_tmp
    local guard_hash
    assert_release_lease || return 1
    verify_persistent_override_contract || return 1
    durable_enabled_absent || return 1
    guard_hash="$(sha256sum "$GUARD_ENV" | awk '{print $1}')" ||
        return 1
    enabled_tmp="$(mktemp "$DURABLE_STATE_DIR/.enabled-commit.XXXXXX")" ||
        return 1
    if ! printf '%s\n' \
        "# commit=$EXPECTED_SHA" \
        "# guard_sha256=$guard_hash" \
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=true" >"$enabled_tmp" ||
        ! chmod 0400 "$enabled_tmp" ||
        ! chown root:root "$enabled_tmp" ||
        ! sync -f "$enabled_tmp" ||
        ! assert_release_lease ||
        ! mv -f -- "$enabled_tmp" "$DURABLE_ENABLED_ENV" ||
        ! sync -f "$DURABLE_STATE_DIR" ||
        ! assert_release_lease; then
        rm -f -- "$enabled_tmp"
        return 1
    fi
    verify_durable_enabled_contract
}

remove_durable_enabled_files() {
    rm -f -- "$DURABLE_ENABLED_ENV" || return 1
    if [ -d "$DURABLE_STATE_DIR" ]; then
        sync -f "$DURABLE_STATE_DIR" || return 1
    fi
    durable_enabled_absent
}

remove_durable_enabled() {
    assert_release_lease || return 1
    remove_durable_enabled_files || return 1
    assert_release_lease || return 1
}

runtime_overrides_absent() {
    local unit
    for unit in "${RUNTIME_OVERRIDE_UNITS[@]}"; do
        test ! -e "$(runtime_override_path "$unit")" || return 1
    done
    test ! -e "$RUNTIME_STATE_DIR"
}

install_runtime_overrides() {
    local unit
    local dropin_dir
    local override_file
    local override_tmp
    local enabled_tmp

    assert_release_lease || return 1
    runtime_overrides_absent || return 1
    mkdir -m 0700 -- "$RUNTIME_STATE_DIR" || return 1
    test ! -L "$RUNTIME_STATE_DIR" || return 1
    test "$(stat -c '%U:%G:%a' "$RUNTIME_STATE_DIR")" = \
        "root:root:700" || return 1
    enabled_tmp="$(mktemp "$RUNTIME_STATE_DIR/.enabled.XXXXXX")" ||
        return 1
    if ! printf '%s\n' \
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=true" >"$enabled_tmp" ||
        ! chmod 0400 "$enabled_tmp" ||
        ! chown root:root "$enabled_tmp" ||
        ! sync -f "$enabled_tmp" ||
        ! mv -f -- "$enabled_tmp" "$RUNTIME_ENABLED_ENV" ||
        ! sync -f "$RUNTIME_STATE_DIR"; then
        rm -f -- "$enabled_tmp"
        return 1
    fi
    verify_flag_file "$RUNTIME_ENABLED_ENV" true || return 1
    test "$(stat -c '%U:%G:%a' "$RUNTIME_ENABLED_ENV")" = \
        "root:root:400" || return 1
    for unit in "${RUNTIME_OVERRIDE_UNITS[@]}"; do
        dropin_dir="$SYSTEMD_RUNTIME_DIR/$unit.d"
        if [ ! -d "$dropin_dir" ]; then
            mkdir -m 0755 "$dropin_dir" || return 1
        fi
        test ! -L "$dropin_dir" || return 1
        test "$(stat -c '%U:%G:%a' "$dropin_dir")" = "root:root:755" ||
            return 1
        override_file="$(runtime_override_path "$unit")"
        override_tmp="$(mktemp "$dropin_dir/.health-evidence.XXXXXX")" ||
            return 1
        if ! printf '%s\n' \
            "[Service]" \
            "EnvironmentFile=$RUNTIME_ENABLED_ENV" \
            >"$override_tmp" ||
            ! chmod 0600 "$override_tmp" ||
            ! chown root:root "$override_tmp" ||
            ! mv -f -- "$override_tmp" "$override_file"; then
            rm -f -- "$override_tmp"
            return 1
        fi
        test "$(stat -c '%U:%G:%a' "$override_file")" = \
            "root:root:600" || return 1
    done
    systemctl daemon-reload || return 1
    assert_release_lease || return 1
}

remove_runtime_override_files() {
    local unit
    local dropin_dir
    local override_file

    for unit in "${RUNTIME_OVERRIDE_UNITS[@]}"; do
        dropin_dir="$SYSTEMD_RUNTIME_DIR/$unit.d"
        override_file="$(runtime_override_path "$unit")"
        rm -f -- "$override_file" || return 1
        if [ -d "$dropin_dir" ]; then
            rmdir "$dropin_dir" >/dev/null 2>&1 || true
        fi
    done
    rm -f -- "$RUNTIME_ENABLED_ENV" || return 1
    if [ -d "$RUNTIME_STATE_DIR" ]; then
        rmdir "$RUNTIME_STATE_DIR" || return 1
    fi
    systemctl daemon-reload || return 1
    runtime_overrides_absent
}

remove_runtime_overrides() {
    assert_release_lease || return 1
    remove_runtime_override_files || return 1
    assert_release_lease || return 1
}

force_services_inactive() {
    local unit
    local state
    local containment_failed=0

    # The socket must be stopped before the service so an HTTP probe cannot
    # reactivate an unverified backend during containment.
    systemctl stop health-backend.socket >/dev/null 2>&1 || true
    systemctl stop health-backend celery-worker celery-beat \
        >/dev/null 2>&1 || true
    for unit in "${SERVICES[@]}"; do
        systemctl kill --kill-who=all --signal=SIGKILL "$unit" \
            >/dev/null 2>&1 || true
        systemctl reset-failed "$unit" >/dev/null 2>&1 || true
    done
    for unit in "${SERVICES[@]}"; do
        state="$(
            systemctl show "$unit" --property=ActiveState --value 2>/dev/null
        )" || state=""
        if [ "$state" != "inactive" ]; then
            echo "containment could not prove inactive: unit=$unit state=${state:-unknown}" >&2
            containment_failed=1
        fi
    done
    if ! remove_runtime_override_files >/dev/null 2>&1; then
        echo "containment could not remove runtime activation state" >&2
        containment_failed=1
    fi
    if verify_flag_file "$TARGET_ENV" false; then
        if ! remove_durable_enabled_files >/dev/null 2>&1; then
            echo "containment could not revoke durable activation" >&2
            containment_failed=1
        fi
    elif [ -e "$DURABLE_ENABLED_ENV" ]; then
        echo "containment kept durable authorization because the base guard is not proven false" >&2
        containment_failed=1
    fi
    [ "$containment_failed" -eq 0 ]
}

install_env_atomically() {
    local source_env="$1"
    local target_dir
    local staged_env
    assert_release_lease || return 1
    target_dir="$(dirname "$TARGET_ENV")"
    staged_env="$(mktemp "$target_dir/.env.health-evidence.XXXXXX")"
    if ! install -o root -g health-app -m 0640 -- \
        "$source_env" "$staged_env"; then
        rm -f -- "$staged_env"
        return 1
    fi
    if ! sync -f "$staged_env" || ! assert_release_lease; then
        rm -f -- "$staged_env"
        return 1
    fi
    if ! mv -f -- "$staged_env" "$TARGET_ENV"; then
        rm -f -- "$staged_env"
        return 1
    fi
    sync -f "$target_dir" || return 1
    assert_release_lease || return 1
    cmp -s "$source_env" "$TARGET_ENV" || return 1
    [ "$(stat -c '%U:%G:%a' "$TARGET_ENV")" = "root:health-app:640" ]
}

verify_process_environment_file() {
    local env_file="$1"
    local expected="$2"
    test -r "$env_file" || return 1
    LC_ALL=C tr '\000' '\n' <"$env_file" |
        awk -v expected="$expected" '
            /^HEALTH_EVIDENCE_RUNTIME_ENABLED=/ {
                assignments += 1
            }
            $0 == "HEALTH_EVIDENCE_RUNTIME_ENABLED=" expected {
                canonical += 1
            }
            END {
                exit(assignments == 1 && canonical == 1 ? 0 : 1)
            }
        '
}

verify_service_process_flags() {
    local expected="$1"
    local unit
    local main_pid
    local control_group
    local procs_file
    local pid
    local process_count
    local main_pid_seen

    [ "$expected" = "true" ] || [ "$expected" = "false" ] || return 2
    for unit in "${PROCESS_UNITS[@]}"; do
        main_pid="$(
            systemctl show "$unit" --property=MainPID --value 2>/dev/null
        )" || return 1
        [[ "$main_pid" =~ ^[1-9][0-9]*$ ]] || return 1
        [ "$main_pid" -gt 1 ] || return 1
        control_group="$(
            systemctl show "$unit" --property=ControlGroup --value \
                2>/dev/null
        )" || return 1
        [[ "$control_group" =~ ^/[A-Za-z0-9_.@:/\\-]+$ ]] || return 1
        [[ "$control_group" != *"/../"* ]] || return 1
        [[ "$control_group" != *"/./"* ]] || return 1
        procs_file="${CGROUP_ROOT%/}${control_group}/cgroup.procs"
        test -r "$procs_file" || return 1
        process_count=0
        main_pid_seen=0
        while IFS= read -r pid; do
            [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 1
            [ "$pid" -gt 1 ] || return 1
            process_count=$((process_count + 1))
            if [ "$pid" = "$main_pid" ]; then
                main_pid_seen=1
            fi
            verify_process_environment_file \
                "${PROC_ROOT%/}/$pid/environ" "$expected" || return 1
        done <"$procs_file"
        [ "$process_count" -gt 0 ] || return 1
        [ "$main_pid_seen" -eq 1 ] || return 1
    done
}

wait_for_health() {
    local attempt=1
    while [ "$attempt" -le "$HEALTH_ATTEMPTS" ]; do
        if curl -fsS --max-time 5 "$HEALTH_URL" >/dev/null; then
            return 0
        fi
        sleep 2
        attempt=$((attempt + 1))
    done
    return 1
}

verify_auth_boundary() {
    local status
    status="$(
        curl -sS -o /dev/null -w '%{http_code}' \
            --max-time 5 "$AUTH_URL" || true
    )"
    [ "$status" = "401" ]
}

verify_health_score() {
    local config_source="${1:-persistent}"
    local report
    if [ "$config_source" = "ephemeral" ]; then
        report="$(
            cd "$REPO_PATH/backend"
            HEALTH_EVIDENCE_RUNTIME_ENABLED=true \
                PYTHONPATH=. \
                venv/bin/python scripts/system_health_score.py \
                --skip-tests --url "$HEALTH_BASE_URL" --json
        )" || return 1
    elif [ "$config_source" = "persistent" ]; then
        report="$(
            cd "$REPO_PATH/backend"
            env -u HEALTH_EVIDENCE_RUNTIME_ENABLED \
                PYTHONPATH=. \
                venv/bin/python scripts/system_health_score.py \
                --skip-tests --url "$HEALTH_BASE_URL" --json
        )" || return 1
    else
        return 2
    fi
    printf '%s\n' "$report" |
        python3 -c '
import json
import sys

payload = json.load(sys.stdin)
passed = payload.get("pass")
score = payload.get("total_score")
threshold = payload.get("threshold")
maximum = payload.get("max_possible")
critical = payload.get("critical_failures")
if passed is not True:
    raise SystemExit(1)
if not isinstance(score, (int, float)) or isinstance(score, bool):
    raise SystemExit(1)
if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
    raise SystemExit(1)
if score < threshold or maximum != 60 or critical != []:
    raise SystemExit(1)
'
}

verify_runtime_contract() {
    local phase="$1"
    local config_source="${2:-persistent}"
    if [ "$config_source" = "ephemeral" ]; then
        (
            cd "$REPO_PATH/backend"
            HEALTH_EVIDENCE_RUNTIME_ENABLED=true \
                PYTHONPATH=. \
                venv/bin/python \
                scripts/verify_runtime_only_kb_contract.py --phase "$phase"
        ) >/dev/null
    elif [ "$config_source" = "persistent" ]; then
        (
            cd "$REPO_PATH/backend"
            env -u HEALTH_EVIDENCE_RUNTIME_ENABLED \
                PYTHONPATH=. \
                venv/bin/python \
                scripts/verify_runtime_only_kb_contract.py --phase "$phase"
        ) >/dev/null
    else
        return 2
    fi
}

write_marker_atomically() {
    write_state_file_atomically "$SUCCESS_MARKER" "$1"
}

write_state_file_atomically() {
    local target_file="$1"
    local content="$2"
    local marker_dir
    local marker_tmp
    marker_dir="$(dirname "$target_file")"
    test -d "$marker_dir" || return 1
    marker_tmp="$(mktemp "$marker_dir/.health-evidence-marker.XXXXXX")"
    if ! printf '%s\n' "$content" >"$marker_tmp"; then
        rm -f -- "$marker_tmp"
        return 1
    fi
    if ! chmod 0600 "$marker_tmp" ||
        ! chown root:root "$marker_tmp" ||
        ! mv -f -- "$marker_tmp" "$target_file"; then
        rm -f -- "$marker_tmp"
        return 1
    fi
}

emit_outcome() {
    local content="$1"
    write_state_file_atomically "$OUTCOME_FILE" "$content" || return 1
    echo "$content"
}

marker_matches_success() {
    local expected_file
    local matched=1
    test -f "$SUCCESS_MARKER" || return 1
    expected_file="$(mktemp)"
    printf '%s\n' "$SUCCESS_SENTINEL" >"$expected_file"
    if cmp -s "$expected_file" "$SUCCESS_MARKER"; then
        matched=0
    fi
    rm -f -- "$expected_file"
    return "$matched"
}

preflight_trusted_stage() {
    require_safe_absolute_path "$REPO_PATH" "repository path" || return 1
    require_safe_absolute_path "$CANDIDATE_ENV" "candidate env path" ||
        return 1
    require_safe_absolute_path "$GUARD_ENV" "guard env path" || return 1
    require_safe_absolute_path "$SUCCESS_MARKER" "success marker path" ||
        return 1
    require_safe_absolute_path "$RELEASE_LOCK_DIR" "release lock path" ||
        return 1
    require_safe_absolute_path "$SYSTEMD_RUNTIME_DIR" \
        "systemd runtime path" || return 1
    require_safe_absolute_path "$SYSTEMD_PERSISTENT_DIR" \
        "systemd persistent path" || return 1
    require_safe_absolute_path "$RUNTIME_STATE_DIR" \
        "activation runtime state path" || return 1
    require_safe_absolute_path "$DURABLE_STATE_DIR" \
        "activation durable state path" || return 1
    require_safe_absolute_path "$PROC_ROOT" "proc root path" || return 1
    require_safe_absolute_path "$CGROUP_ROOT" "cgroup root path" || return 1
    [[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]] || return 1
    [[ "$RELEASE_LOCK_TOKEN" =~ ^[A-Za-z0-9._:-]+$ ]] || return 1
    [[ "$HEALTH_ATTEMPTS" =~ ^[1-9][0-9]*$ ]] || return 1
    if [ ! -d "$REPO_PATH/.git" ] && [ ! -f "$REPO_PATH/.git" ]; then
        return 1
    fi
    [ "$GUARD_ENV" = "$SCRIPT_DIR/guard.env" ] || return 1
    [ "$CANDIDATE_ENV" = "$SCRIPT_DIR/candidate.env" ] || return 1
    [ "$(dirname "$SUCCESS_MARKER")" != "$SCRIPT_DIR" ] || return 1
    [ "$(stat -c '%U:%G:%a' "$SCRIPT_DIR")" = "root:root:700" ] ||
        return 1
    [ "$(stat -c '%U:%G:%a' "$(dirname "$SUCCESS_MARKER")")" = \
        "root:root:700" ] || return 1
    verify_immutable_stage || return 1
    assert_release_lease || return 1
    verify_flag_file "$GUARD_ENV" false || return 1
}

preflight_candidate_and_repo() {
    verify_flag_file "$CANDIDATE_ENV" true || return 1
    if [ "$MODE" = "--activate" ]; then
        verify_flag_file "$TARGET_ENV" false || return 1
        cmp -s "$GUARD_ENV" "$TARGET_ENV" || return 1
        runtime_overrides_absent || return 1
        durable_enabled_absent || return 1
    fi
    verify_repo_revision || return 1
    test -x "$REPO_PATH/backend/venv/bin/python" || return 1
    test -r "$REPO_PATH/backend/scripts/system_health_score.py" || return 1
    test -r \
        "$REPO_PATH/backend/scripts/verify_runtime_only_kb_contract.py" ||
        return 1
}

verify_enabled_marker_state() {
    assert_release_lease || return 1
    verify_flag_file "$CANDIDATE_ENV" true || return 1
    verify_flag_file "$TARGET_ENV" false || return 1
    cmp -s "$GUARD_ENV" "$TARGET_ENV" || return 1
    verify_persistent_override_contract || return 1
    verify_durable_enabled_contract || return 1
    runtime_overrides_absent || return 1
    verify_repo_revision || return 1
    verify_services_active || return 1
    verify_service_process_flags true || return 1
    wait_for_health || return 1
    verify_auth_boundary || return 1
    verify_health_score ephemeral || return 1
    verify_runtime_contract enabled ephemeral || return 1
    assert_release_lease || return 1
    verify_services_active || return 1
}

recover_guard() {
    assert_release_lease || return 1
    install_env_atomically "$GUARD_ENV" || return 1
    verify_flag_file "$TARGET_ENV" false || return 1
    cmp -s "$GUARD_ENV" "$TARGET_ENV" || return 1
    remove_durable_enabled || return 1
    remove_runtime_overrides || return 1
    restart_services_in_order || return 1
    assert_release_lease || return 1
    verify_repo_revision || return 1
    verify_service_process_flags false || return 1
    wait_for_health || return 1
    verify_runtime_contract staged persistent || return 1
    assert_release_lease || return 1
    verify_services_active || return 1
}

ACTIVATION_COMPLETE=0
RECOVERY_ARMED=0

activation_exit_guard() {
    local original_rc=$?
    trap - EXIT HUP INT TERM
    if [ "$ACTIVATION_COMPLETE" -eq 1 ] ||
        [ "$RECOVERY_ARMED" -ne 1 ]; then
        return
    fi

    set +e
    rm -f -- "$SUCCESS_MARKER"
    if recover_guard; then
        emit_outcome "$ROLLBACK_SENTINEL"
        if [ "$original_rc" -eq 0 ]; then
            original_rc=1
        fi
        exit "$original_rc"
    fi
    if force_services_inactive; then
        emit_outcome "$BLOCKED_SENTINEL"
        exit 70
    fi
    emit_outcome "$CONTAINMENT_FAILED_SENTINEL"
    exit 71
}

activation_signal() {
    local signal_name="$1"
    local signal_rc="$2"
    echo "activation interrupted by $signal_name" >&2
    exit "$signal_rc"
}

activate() {
    if ! preflight_trusted_stage; then
        echo "activation stage or release lease failed validation; containing services" >&2
        if force_services_inactive; then
            emit_outcome "$BLOCKED_SENTINEL"
            return 70
        fi
        emit_outcome "$CONTAINMENT_FAILED_SENTINEL"
        return 71
    fi
    RECOVERY_ARMED=1
    trap activation_exit_guard EXIT
    trap 'activation_signal HUP 129' HUP
    trap 'activation_signal INT 130' INT
    trap 'activation_signal TERM 143' TERM
    # A marker from an earlier successful job must not let ExecStopPost skip
    # recovery if this new attempt dies before its own enabled proof.
    rm -f -- "$SUCCESS_MARKER" "$OUTCOME_FILE"
    preflight_candidate_and_repo
    install_persistent_override_contract
    assert_release_lease
    verify_service_process_flags false
    # Phase 1: prove enabled behavior through /run-only systemd overrides while
    # the persistent .env remains the already-verified false guard. A host
    # reboot before commit deletes /run and therefore returns to false.
    install_runtime_overrides
    restart_services_in_order
    assert_release_lease
    verify_repo_revision
    verify_service_process_flags true
    wait_for_health
    verify_auth_boundary
    verify_health_score ephemeral
    verify_runtime_contract enabled ephemeral
    assert_release_lease
    verify_repo_revision
    verify_services_active

    # Phase 2: commit one durable optional EnvironmentFile. The base .env
    # remains the exact false guard. A crash before the fsynced rename loses
    # /run and boots false; after it, the already-proven canary is authorized.
    assert_release_lease
    commit_durable_enabled
    assert_release_lease
    remove_runtime_overrides
    assert_release_lease
    verify_flag_file "$TARGET_ENV" false
    cmp -s "$GUARD_ENV" "$TARGET_ENV"
    verify_durable_enabled_contract
    restart_services_in_order
    assert_release_lease
    verify_service_process_flags true
    wait_for_health
    verify_auth_boundary
    verify_health_score ephemeral
    verify_runtime_contract enabled ephemeral
    assert_release_lease
    verify_repo_revision
    verify_services_active
    write_marker_atomically "$SUCCESS_SENTINEL"
    ACTIVATION_COMPLETE=1
    emit_outcome "$SUCCESS_SENTINEL"
}

deadman_signal() {
    local signal_name="$1"
    trap - HUP INT TERM
    echo "deadman recovery interrupted by $signal_name" >&2
    if force_services_inactive; then
        emit_outcome "$BLOCKED_SENTINEL"
        exit 70
    fi
    emit_outcome "$CONTAINMENT_FAILED_SENTINEL"
    exit 71
}

recover_if_unverified() {
    if ! preflight_trusted_stage; then
        echo "deadman preflight failed; containing services" >&2
        if force_services_inactive; then
            emit_outcome "$BLOCKED_SENTINEL"
            return 70
        fi
        emit_outcome "$CONTAINMENT_FAILED_SENTINEL"
        return 71
    fi
    if preflight_candidate_and_repo &&
        verify_enabled_marker_state; then
        if ! marker_matches_success; then
            write_marker_atomically "$SUCCESS_SENTINEL" || return 1
        fi
        emit_outcome \
            "HEALTH_EVIDENCE_DEADMAN_NOOP commit=$EXPECTED_SHA authorization=verified"
        return 0
    fi

    rm -f -- "$SUCCESS_MARKER"
    trap 'deadman_signal HUP' HUP
    trap 'deadman_signal INT' INT
    trap 'deadman_signal TERM' TERM
    if recover_guard; then
        trap - HUP INT TERM
        emit_outcome \
            "HEALTH_EVIDENCE_DEADMAN_RECOVERED commit=$EXPECTED_SHA flag=false health=passed contract=staged services=active"
        return 0
    fi
    trap - HUP INT TERM
    if force_services_inactive; then
        emit_outcome "$BLOCKED_SENTINEL"
        return 70
    fi
    emit_outcome "$CONTAINMENT_FAILED_SENTINEL"
    return 71
}

if [ "$MODE" = "--activate" ]; then
    activate
else
    recover_if_unverified
fi
