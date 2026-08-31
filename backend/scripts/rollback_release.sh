#!/bin/bash
# Restore a known-good application revision and prove it can run against the
# current forward-only database schema. This script never reports success
# before the exact revision, runtime schema, auth boundary, and services pass.
set -euo pipefail

if [ "$#" -ne 4 ]; then
    echo "用法: $0 /absolute/path/to/repository <40-char-commit> /absolute/release-lock <token>" >&2
    exit 2
fi

REPO_PATH="$1"
ROLLBACK_COMMIT="$2"
REMOTE_RELEASE_LOCK_DIR="$3"
REMOTE_RELEASE_LOCK_TOKEN="$4"
HEALTH_URL="${ROLLBACK_HEALTH_URL:-http://localhost:8000/api/v1/health}"
AUTH_URL="${ROLLBACK_AUTH_URL:-http://localhost:8000/api/v1/auth/me}"
HEALTH_ATTEMPTS="${ROLLBACK_HEALTH_ATTEMPTS:-30}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAGED_REVIEW_MANIFEST="$SCRIPT_DIR/review_manifest.json"
STAGED_HASH_MANIFEST="$SCRIPT_DIR/staged.sha256"
SCHEMA_PROBE="$SCRIPT_DIR/verify_runtime_schema_compatibility.py"
KB_QUARANTINE="$SCRIPT_DIR/quarantine_runtime_only_kb.py"
RUNTIME_STATE_RUNNER="$SCRIPT_DIR/runtime_state_release_transaction.py"
LOCKED_REQUIREMENTS_VERIFIER="$SCRIPT_DIR/verify_locked_requirements.py"
STAGED_BACKEND_ENV_ROLLBACK="$SCRIPT_DIR/backend.env.rollback"
STAGED_BACKEND_ENV_CANDIDATE="$SCRIPT_DIR/backend.env.candidate"
HEALTH_EVIDENCE_DURABLE_STATE_DIR="${HEALTH_EVIDENCE_DURABLE_STATE_DIR:-/var/lib/reva-health-evidence-runtime}"
HEALTH_EVIDENCE_RUNTIME_STATE_DIR="${HEALTH_EVIDENCE_RUNTIME_STATE_DIR:-/run/reva-health-evidence-activation}"
HEALTH_EVIDENCE_SYSTEMD_RUNTIME_DIR="${HEALTH_EVIDENCE_SYSTEMD_RUNTIME_DIR:-/run/systemd/system}"
REMOTE_RELEASE_STATE_DIR="${REMOTE_RELEASE_STATE_DIR:-/var/lib/reva-release-state}"
BACKEND_SOCKET="health-backend.socket"
WRITER_SERVICES=(health-backend celery-worker celery-beat)
SERVICES=("$BACKEND_SOCKET" "${WRITER_SERVICES[@]}")
SERVICE_STABILITY_SECONDS=7
REQUIRED_STAGED_ARTIFACTS=(
    backup_db.sh
    verify_backup_restore.sh
    archive_backup_offsite.sh
    rollback_release.sh
    activate_health_evidence_runtime.sh
    verify_locked_requirements.py
    verify_runtime_schema_compatibility.py
    quarantine_runtime_only_kb.py
    runtime_state_release_transaction.py
    review_manifest.json
    health-backend-runtime-state.conf
    celery-worker-runtime-state.conf
    celery-beat-runtime-state.conf
    backend.env.rollback
    backend.env.candidate
)

if [ ! -d "$REPO_PATH/.git" ] && [ ! -f "$REPO_PATH/.git" ]; then
    echo "回滚目录不是 Git 工作树: $REPO_PATH" >&2
    exit 1
fi
if ! [[ "$ROLLBACK_COMMIT" =~ ^[0-9a-f]{40}$ ]]; then
    echo "回滚 commit 必须是 40 位小写 SHA" >&2
    exit 1
fi
if [[ "$REMOTE_RELEASE_LOCK_DIR" != /* || "$REMOTE_RELEASE_LOCK_DIR" = "/" ]]; then
    echo "远端发布锁路径不安全" >&2
    exit 1
fi
if ! [[ "$REMOTE_RELEASE_LOCK_TOKEN" =~ ^[A-Za-z0-9._:-]+$ ]]; then
    echo "远端发布锁 token 格式非法" >&2
    exit 1
fi
assert_release_lock() {
    test -d "$REMOTE_RELEASE_LOCK_DIR"
    test ! -L "$REMOTE_RELEASE_LOCK_DIR"
    test "$(stat -c '%U:%G:%a' "$REMOTE_RELEASE_LOCK_DIR")" = \
        "root:root:700"
    test -f "$REMOTE_RELEASE_LOCK_DIR/token"
    test ! -L "$REMOTE_RELEASE_LOCK_DIR/token"
    test -r "$REMOTE_RELEASE_LOCK_DIR/token"
    test "$(stat -c '%U:%G:%a' "$REMOTE_RELEASE_LOCK_DIR/token")" = \
        "root:root:600"
    test "$(stat -c '%h' "$REMOTE_RELEASE_LOCK_DIR/token")" = "1"
    cmp -s "$REMOTE_RELEASE_LOCK_DIR/token" \
        <(printf '%s\n' "$REMOTE_RELEASE_LOCK_TOKEN")
    test -f "$REMOTE_RELEASE_LOCK_DIR/stage"
    test ! -L "$REMOTE_RELEASE_LOCK_DIR/stage"
    test -r "$REMOTE_RELEASE_LOCK_DIR/stage"
    test "$(stat -c '%U:%G:%a' "$REMOTE_RELEASE_LOCK_DIR/stage")" = \
        "root:root:600"
    test "$(stat -c '%h' "$REMOTE_RELEASE_LOCK_DIR/stage")" = "1"
    cmp -s "$REMOTE_RELEASE_LOCK_DIR/stage" \
        <(printf '%s\n' "$SCRIPT_DIR")
}
safe_absolute_path() {
    local value="$1"
    [[ "$value" =~ ^/[A-Za-z0-9._/-]+$ ]] &&
        [ "$value" != "/" ] &&
        [[ "$value" != *"/../"* ]] &&
        [[ "$value" != *"/.." ]] &&
        [[ "$value" != *"/./"* ]] &&
        [[ "$value" != *"/." ]]
}
assert_release_lock
if ! [[ "$HEALTH_ATTEMPTS" =~ ^[1-9][0-9]*$ ]]; then
    echo "ROLLBACK_HEALTH_ATTEMPTS 必须是正整数" >&2
    exit 1
fi
safe_absolute_path "$SCRIPT_DIR"
test -d "$SCRIPT_DIR"
test ! -L "$SCRIPT_DIR"
test "$(stat -c '%U:%G:%a' "$SCRIPT_DIR")" = "root:root:700"
test -f "$STAGED_HASH_MANIFEST"
test ! -L "$STAGED_HASH_MANIFEST"
test -r "$STAGED_HASH_MANIFEST"
test "$(stat -c '%U:%G:%a' "$STAGED_HASH_MANIFEST")" = "root:root:400"
shopt -s nullglob dotglob
stage_entry_count=0
for entry in "$SCRIPT_DIR"/*; do
    name="${entry##*/}"
    allowed=0
    if [ "$name" = "staged.sha256" ]; then
        allowed=1
    else
        for artifact in "${REQUIRED_STAGED_ARTIFACTS[@]}"; do
            if [ "$name" = "$artifact" ]; then
                allowed=1
                break
            fi
        done
    fi
    if [ "$allowed" != "1" ]; then
        echo "unknown immutable rollback artifact: $name" >&2
        exit 1
    fi
    test -f "$entry"
    test ! -L "$entry"
    stage_entry_count=$((stage_entry_count + 1))
done
shopt -u nullglob dotglob
test "$stage_entry_count" -eq "$((${#REQUIRED_STAGED_ARTIFACTS[@]} + 1))"
for artifact in "${REQUIRED_STAGED_ARTIFACTS[@]}"; do
    test -f "$SCRIPT_DIR/$artifact"
    test ! -L "$SCRIPT_DIR/$artifact"
    test -r "$SCRIPT_DIR/$artifact"
    awk -v expected="$artifact" '
        $2 == expected &&
        length($1) == 64 &&
        $1 !~ /[^0-9a-f]/ {
            matches += 1
        }
        END { exit(matches == 1 ? 0 : 1) }
    ' "$STAGED_HASH_MANIFEST"
done
test "$(awk 'NF {count += 1} END {print count + 0}' "$STAGED_HASH_MANIFEST")" \
    -eq "${#REQUIRED_STAGED_ARTIFACTS[@]}"
(
    cd "$SCRIPT_DIR"
    sha256sum --strict -c "$STAGED_HASH_MANIFEST" >/dev/null
)
test -r "$STAGED_REVIEW_MANIFEST"
safe_absolute_path "$HEALTH_EVIDENCE_DURABLE_STATE_DIR"
safe_absolute_path "$HEALTH_EVIDENCE_RUNTIME_STATE_DIR"
safe_absolute_path "$HEALTH_EVIDENCE_SYSTEMD_RUNTIME_DIR"
safe_absolute_path "$REMOTE_RELEASE_STATE_DIR"

ROLLBACK_CGROUP_ROOT="${ROLLBACK_CGROUP_ROOT:-/sys/fs/cgroup}"
ROLLBACK_PROC_ROOT="${ROLLBACK_PROC_ROOT:-/proc}"
safe_absolute_path "$ROLLBACK_CGROUP_ROOT"
safe_absolute_path "$ROLLBACK_PROC_ROOT"
verify_process_environment_false() {
    local service
    local main_pid
    local control_group
    local procs_file
    local pid
    local process_count
    local main_pid_seen

    for service in "${WRITER_SERVICES[@]}"; do
        main_pid="$(
            systemctl show "$service" --property=MainPID --value 2>/dev/null
        )"
        [[ "$main_pid" =~ ^[1-9][0-9]*$ ]] && [ "$main_pid" -gt 1 ]
        control_group="$(
            systemctl show "$service" --property=ControlGroup --value \
                2>/dev/null
        )"
        [[ "$control_group" =~ ^/[A-Za-z0-9_.@:/\\-]+$ ]]
        [[ "$control_group" != *"/../"* ]]
        procs_file="${ROLLBACK_CGROUP_ROOT}${control_group}/cgroup.procs"
        test -r "$procs_file"
        process_count=0
        main_pid_seen=0
        while IFS= read -r pid; do
            [[ "$pid" =~ ^[1-9][0-9]*$ ]] && [ "$pid" -gt 1 ]
            process_count=$((process_count + 1))
            if [ "$pid" = "$main_pid" ]; then
                main_pid_seen=1
            fi
            LC_ALL=C tr '\000' '\n' \
                <"$ROLLBACK_PROC_ROOT/$pid/environ" |
                awk '
                    /^HEALTH_EVIDENCE_RUNTIME_ENABLED=/ {
                        assignments += 1
                    }
                    $0 == "HEALTH_EVIDENCE_RUNTIME_ENABLED=false" {
                        canonical += 1
                    }
                    END {
                        if (assignments != 1 || canonical != 1) {
                            exit 1
                        }
                    }
                '
        done <"$procs_file"
        [ "$process_count" -gt 0 ] && [ "$main_pid_seen" -eq 1 ]
    done
}

verify_services_stable() {
    local phase
    local service
    local active_state
    local sub_state
    local result
    local main_pid
    local restart_count
    local enter_timestamp
    local process_index
    local stable_main_pid=()
    local stable_restart_count=()
    local stable_enter_timestamp=()
    local stable_socket_sub_state=""

    for phase in record compare; do
        process_index=0
        for service in "${SERVICES[@]}"; do
            active_state="$(
                systemctl show "$service" --property=ActiveState --value \
                    2>/dev/null
            )"
            sub_state="$(
                systemctl show "$service" --property=SubState --value \
                    2>/dev/null
            )"
            result="$(
                systemctl show "$service" --property=Result --value \
                    2>/dev/null
            )"
            test "$active_state" = "active"
            test "$result" = "success"
            if [ "$service" = "$BACKEND_SOCKET" ]; then
                # systemd 249 uses "running" for an active bound socket;
                # newer releases may use "listening". Require one of those
                # ready states and require it to stay unchanged across the
                # complete stability window.
                case "$sub_state" in
                    listening|running) ;;
                    *) return 1 ;;
                esac
                if [ "$phase" = "record" ]; then
                    stable_socket_sub_state="$sub_state"
                else
                    test "$sub_state" = "$stable_socket_sub_state"
                fi
                continue
            fi
            test "$sub_state" = "running"
            main_pid="$(
                systemctl show "$service" --property=MainPID --value \
                    2>/dev/null
            )"
            restart_count="$(
                systemctl show "$service" --property=NRestarts --value \
                    2>/dev/null
            )"
            enter_timestamp="$(
                systemctl show "$service" \
                    --property=ActiveEnterTimestampMonotonic --value \
                    2>/dev/null
            )"
            [[ "$main_pid" =~ ^[1-9][0-9]*$ ]]
            [ "$main_pid" -gt 1 ]
            [[ "$restart_count" =~ ^[0-9]+$ ]]
            [[ "$enter_timestamp" =~ ^[1-9][0-9]*$ ]]
            if [ "$phase" = "record" ]; then
                stable_main_pid[$process_index]="$main_pid"
                stable_restart_count[$process_index]="$restart_count"
                stable_enter_timestamp[$process_index]="$enter_timestamp"
            else
                test "$main_pid" = \
                    "${stable_main_pid[$process_index]}"
                test "$restart_count" = \
                    "${stable_restart_count[$process_index]}"
                test "$enter_timestamp" = \
                    "${stable_enter_timestamp[$process_index]}"
            fi
            process_index=$((process_index + 1))
        done
        if [ "$phase" = "record" ]; then
            assert_release_lock
            sleep "$SERVICE_STABILITY_SECONDS"
            assert_release_lock
        fi
    done
}

ROLLBACK_VERIFIED=0
SERVICES_TOUCHED=0
force_services_inactive() {
    local stop_failed=0
    local containment_failed=0
    local service state

    # Stop the socket first so health probes or nginx cannot reactivate the
    # backend while code and KB state are being changed.
    if ! systemctl stop "$BACKEND_SOCKET"; then
        stop_failed=1
    fi
    if ! systemctl stop "${WRITER_SERVICES[@]}"; then
        stop_failed=1
    fi

    for service in "${SERVICES[@]}"; do
        state=$(systemctl show "$service" --property=ActiveState --value 2>/dev/null || true)
        if [ "$state" != "inactive" ]; then
            if ! systemctl kill --kill-who=all --signal=SIGKILL "$service" >/dev/null 2>&1; then
                stop_failed=1
            fi
            if ! systemctl stop "$service" >/dev/null 2>&1; then
                stop_failed=1
            fi
            if ! systemctl reset-failed "$service" >/dev/null 2>&1; then
                stop_failed=1
            fi
            state=$(systemctl show "$service" --property=ActiveState --value 2>/dev/null || true)
        fi
        if [ "$state" != "inactive" ]; then
            echo "无法证明服务已停止: service=$service state=${state:-unknown}" >&2
            containment_failed=1
        fi
    done

    if [ "$stop_failed" = "1" ]; then
        echo "停服命令出现失败，已复核最终状态并在必要时强制终止" >&2
    fi
    [ "$containment_failed" = "0" ]
}

verify_health_evidence_base_guard() {
    local target_env="$REPO_PATH/backend/.env"
    test -r "$target_env" &&
        awk '
            /^[[:space:]]*(export[[:space:]]+)?HEALTH_EVIDENCE_RUNTIME_ENABLED[[:space:]]*=/ {
                assignments += 1
            }
            $0 == "HEALTH_EVIDENCE_RUNTIME_ENABLED=false" {
                canonical += 1
            }
            END {
                exit(assignments == 1 && canonical == 1 ? 0 : 1)
            }
        ' "$target_env"
}

select_release_env_for_runtime_result() {
    local runtime_state_result="$1"
    local target_env="$REPO_PATH/backend/.env"
    local target_dir="$REPO_PATH/backend"
    local target_tmp="$target_dir/.env.rollback-release.tmp"

    test -d "$target_dir"
    test ! -L "$target_dir"
    test -f "$target_env"
    test ! -L "$target_env"
    test -f "$STAGED_BACKEND_ENV_ROLLBACK"
    test ! -L "$STAGED_BACKEND_ENV_ROLLBACK"
    test -f "$STAGED_BACKEND_ENV_CANDIDATE"
    test ! -L "$STAGED_BACKEND_ENV_CANDIDATE"
    case "$runtime_state_result" in
        restored)
            # Runtime files, code, systemd units, and configuration must move
            # back as one preimage. The snapshot keeps all old values while
            # normalizing the safety flag to the unique explicit false form.
            rm -f -- "$target_tmp"
            umask 077
            if ! awk '
                    /^[[:space:]]*(export[[:space:]]+)?HEALTH_EVIDENCE_RUNTIME_ENABLED[[:space:]]*=/ {
                        assignments += 1
                        if ($0 == "HEALTH_EVIDENCE_RUNTIME_ENABLED=false") {
                            canonical += 1
                            print "HEALTH_EVIDENCE_RUNTIME_ENABLED=false"
                            next
                        }
                        invalid = 1
                        next
                    }
                    { print }
                    END {
                        if (assignments > 1 || invalid == 1 || canonical > 1) {
                            exit 1
                        }
                        if (assignments == 0) {
                            print "HEALTH_EVIDENCE_RUNTIME_ENABLED=false"
                        }
                    }
                ' "$STAGED_BACKEND_ENV_ROLLBACK" >"$target_tmp"; then
                rm -f -- "$target_tmp"
                return 1
            fi
            if ! chown root:health-app "$target_tmp" ||
                ! chmod 0640 "$target_tmp" ||
                ! sync -f "$target_tmp" ||
                ! mv -fT -- "$target_tmp" "$target_env"; then
                rm -f -- "$target_tmp"
                return 1
            fi
            if ! sync -f "$target_dir"; then
                return 1
            fi
            verify_health_evidence_base_guard
            ;;
        candidate-retained)
            # The transaction has already crossed the candidate floor. Never
            # reintroduce old paths or secrets in that branch.
            test -f "$target_env"
            test ! -L "$target_env"
            verify_health_evidence_base_guard
            cmp -s "$STAGED_BACKEND_ENV_CANDIDATE" "$target_env"
            ;;
        *)
            echo "未知 runtime state restore result" >&2
            return 1
            ;;
    esac
    test -f "$target_env"
    test ! -L "$target_env"
    test "$(stat -c '%U:%G:%a' "$target_env")" = "root:health-app:640"
}

revoke_health_evidence_authorization() {
    local unit
    local override_dir
    local durable_enabled="$HEALTH_EVIDENCE_DURABLE_STATE_DIR/enabled.env"
    local runtime_enabled="$HEALTH_EVIDENCE_RUNTIME_STATE_DIR/enabled.env"
    local runtime_override_name="90-reva-health-evidence-activation.conf"

    assert_release_lock
    verify_health_evidence_base_guard
    if [ -d "$HEALTH_EVIDENCE_DURABLE_STATE_DIR" ]; then
        test ! -L "$HEALTH_EVIDENCE_DURABLE_STATE_DIR"
        rm -f -- "$durable_enabled"
        sync -f "$HEALTH_EVIDENCE_DURABLE_STATE_DIR"
    fi
    test ! -e "$durable_enabled"
    for unit in health-backend.service celery-worker.service celery-beat.service; do
        override_dir="$HEALTH_EVIDENCE_SYSTEMD_RUNTIME_DIR/$unit.d"
        rm -f -- "$override_dir/$runtime_override_name"
        if [ -d "$override_dir" ]; then
            rmdir "$override_dir" >/dev/null 2>&1 || true
        fi
    done
    rm -f -- "$runtime_enabled"
    if [ -d "$HEALTH_EVIDENCE_RUNTIME_STATE_DIR" ]; then
        rmdir "$HEALTH_EVIDENCE_RUNTIME_STATE_DIR"
    fi
    systemctl daemon-reload
    assert_release_lock
    verify_health_evidence_base_guard
    test ! -e "$durable_enabled"
}

cleanup_or_block() {
    local rc=$?
    trap - EXIT
    if [ "$SERVICES_TOUCHED" = "1" ] && [ "$ROLLBACK_VERIFIED" != "1" ]; then
        if ! force_services_inactive; then
            echo "ROLLBACK_CONTAINMENT_FAILED services=unverified manual_isolation=required" >&2
            exit 70
        fi
        echo "ROLLBACK_BLOCKED services=inactive" >&2
    fi
    exit "$rc"
}
trap cleanup_or_block EXIT

cd "$REPO_PATH"
assert_release_lock
git cat-file -e "${ROLLBACK_COMMIT}^{commit}"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "远端工作树存在未提交的 tracked 改动，拒绝覆盖式回滚" >&2
    exit 1
fi

# Stop writers before changing code. On any later failure, services stay
# stopped instead of serving an unverified code/database combination.
SERVICES_TOUCHED=1
assert_release_lock
force_services_inactive
revoke_health_evidence_authorization
git checkout -B main "$ROLLBACK_COMMIT"
test "$(git rev-parse HEAD)" = "$ROLLBACK_COMMIT"
assert_release_lock

runtime_state_output="$(
    /usr/bin/python3 -I "$RUNTIME_STATE_RUNNER" \
        restore "$ROLLBACK_COMMIT" \
        "$REMOTE_RELEASE_LOCK_DIR" \
        "$REMOTE_RELEASE_LOCK_TOKEN"
)"
echo "$runtime_state_output"
case "$runtime_state_output" in
    *"RUNTIME_STATE_TRANSACTION_OK command=restore result=restored"*)
        runtime_state_result="restored"
        ;;
    *"RUNTIME_STATE_TRANSACTION_OK command=restore result=candidate-retained"*)
        runtime_state_result="candidate-retained"
        ;;
    *)
        echo "runtime state restore 缺少精确成功证明" >&2
        exit 1
        ;;
esac
assert_release_lock
select_release_env_for_runtime_result "$runtime_state_result"
assert_release_lock

backend/venv/bin/pip install --require-hashes -r backend/requirements.lock -q
# Services remain stopped while the old lock is installed. Remove the legacy
# Chroma runtime before validation so rollback restores every safe target
# dependency without re-exposing packages that have no patched release.
backend/venv/bin/python -m pip uninstall --yes chromadb chroma-hnswlib
backend/venv/bin/python "$LOCKED_REQUIREMENTS_VERIFIER" \
    --sanitize-forbidden-packages backend/requirements.lock
backend/venv/bin/python -m pip check

requirements_digest="$(sha256sum backend/requirements.lock | awk '{print $1}')"
requirements_marker="$REMOTE_RELEASE_STATE_DIR/requirements-lock.sha256"
if [ ! -e "$REMOTE_RELEASE_STATE_DIR" ]; then
    umask 077
    mkdir "$REMOTE_RELEASE_STATE_DIR"
    chmod 0700 "$REMOTE_RELEASE_STATE_DIR"
fi
test -d "$REMOTE_RELEASE_STATE_DIR"
test ! -L "$REMOTE_RELEASE_STATE_DIR"
test "$(stat -c '%U:%G:%a' "$REMOTE_RELEASE_STATE_DIR")" = \
    "root:root:700"
if [ -e "$requirements_marker" ] || [ -L "$requirements_marker" ]; then
    test -f "$requirements_marker"
    test ! -L "$requirements_marker"
    test "$(stat -c '%U:%G:%a' "$requirements_marker")" = \
        "root:root:600"
    test "$(stat -c '%h' "$requirements_marker")" = "1"
fi
requirements_marker_tmp="$(
    mktemp "$REMOTE_RELEASE_STATE_DIR/.requirements-lock.rollback.XXXXXX"
)"
printf '%s\n' "$requirements_digest" > "$requirements_marker_tmp"
chmod 0600 "$requirements_marker_tmp"
test "$(stat -c '%U:%G:%a' "$requirements_marker_tmp")" = \
    "root:root:600"
test "$(stat -c '%h' "$requirements_marker_tmp")" = "1"
sync -f "$requirements_marker_tmp"
mv -fT -- "$requirements_marker_tmp" "$requirements_marker"
sync -f "$REMOTE_RELEASE_STATE_DIR"
(
    cd backend
    PYTHONPATH=. venv/bin/python "$KB_QUARANTINE" "$STAGED_REVIEW_MANIFEST" \
        --actor "rollback:${ROLLBACK_COMMIT:0:12}"
)
system_kb_marker="$REMOTE_RELEASE_STATE_DIR/system-kb-input.sha256"
if [ -e "$system_kb_marker" ] || [ -L "$system_kb_marker" ]; then
    test -f "$system_kb_marker"
    test ! -L "$system_kb_marker"
    test "$(stat -c '%U:%G:%a' "$system_kb_marker")" = \
        "root:root:600"
    test "$(stat -c '%h' "$system_kb_marker")" = "1"
    rm -f -- "$system_kb_marker"
    sync -f "$REMOTE_RELEASE_STATE_DIR"
fi
assert_release_lock

# Prove forward-only schema compatibility while every socket and writer is
# inactive. No unverified rollback target may briefly serve real traffic.
(
    cd backend
    test -r .env
    PYTHONPATH=. venv/bin/python "$SCHEMA_PROBE"
)
assert_release_lock

systemctl start "$BACKEND_SOCKET"
systemctl start "${WRITER_SERVICES[@]}"

healthy=0
for attempt in $(seq 1 "$HEALTH_ATTEMPTS"); do
    if curl -fsS --max-time 5 "$HEALTH_URL" >/dev/null; then
        healthy=1
        break
    fi
    sleep 2
done
if [ "$healthy" != "1" ]; then
    echo "回滚后健康检查失败" >&2
    exit 1
fi

AUTH_STATUS=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "$AUTH_URL" || true)
if [ "$AUTH_STATUS" != "401" ]; then
    echo "回滚后认证探针失败: expected=401 actual=${AUTH_STATUS:-missing}" >&2
    exit 1
fi

verify_services_stable
verify_process_environment_false
verify_services_stable

test "$(git rev-parse HEAD)" = "$ROLLBACK_COMMIT"
assert_release_lock
if [ "$runtime_state_result" = "restored" ]; then
    runtime_terminal_output="$(
        /usr/bin/python3 -I "$RUNTIME_STATE_RUNNER" \
            release-gate "$ROLLBACK_COMMIT" \
            "$REMOTE_RELEASE_LOCK_DIR" \
            "$REMOTE_RELEASE_LOCK_TOKEN"
    )"
    echo "$runtime_terminal_output"
    case "$runtime_terminal_output" in
        *"RUNTIME_STATE_TRANSACTION_OK command=release-gate result=RESTORE_FINALIZED"*)
            ;;
        *)
            echo "runtime state old release-gate 缺少精确成功证明" >&2
            exit 1
            ;;
    esac
else
    runtime_commit_output="$(
        /usr/bin/python3 -I "$RUNTIME_STATE_RUNNER" \
            commit "$ROLLBACK_COMMIT" \
            "$REMOTE_RELEASE_LOCK_DIR" \
            "$REMOTE_RELEASE_LOCK_TOKEN"
    )"
    echo "$runtime_commit_output"
    case "$runtime_commit_output" in
        *"RUNTIME_STATE_TRANSACTION_OK command=commit result=COMMITTED"*)
            ;;
        *)
            echo "runtime state candidate commit 缺少精确成功证明" >&2
            exit 1
            ;;
    esac
    runtime_terminal_output="$(
        /usr/bin/python3 -I "$RUNTIME_STATE_RUNNER" \
            finalize "$ROLLBACK_COMMIT" \
            "$REMOTE_RELEASE_LOCK_DIR" \
            "$REMOTE_RELEASE_LOCK_TOKEN"
    )"
    echo "$runtime_terminal_output"
    case "$runtime_terminal_output" in
        *"RUNTIME_STATE_TRANSACTION_OK command=finalize result=finalized"*)
            ;;
        *)
            echo "runtime state candidate finalize 缺少精确成功证明" >&2
            exit 1
            ;;
    esac
fi
assert_release_lock
ROLLBACK_VERIFIED=1
echo "ROLLBACK_OK commit=$ROLLBACK_COMMIT kb_quarantine=passed schema_probe=passed auth_probe=passed services=active process_flag=false runtime_state=$runtime_state_result"
