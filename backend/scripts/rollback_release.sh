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
HEALTH_EVIDENCE_DURABLE_STATE_DIR="${HEALTH_EVIDENCE_DURABLE_STATE_DIR:-/var/lib/reva-health-evidence-runtime}"
HEALTH_EVIDENCE_RUNTIME_STATE_DIR="${HEALTH_EVIDENCE_RUNTIME_STATE_DIR:-/run/reva-health-evidence-activation}"
HEALTH_EVIDENCE_SYSTEMD_RUNTIME_DIR="${HEALTH_EVIDENCE_SYSTEMD_RUNTIME_DIR:-/run/systemd/system}"
BACKEND_SOCKET="health-backend.socket"
WRITER_SERVICES=(health-backend celery-worker celery-beat)
SERVICES=("$BACKEND_SOCKET" "${WRITER_SERVICES[@]}")
REQUIRED_STAGED_ARTIFACTS=(
    backup_db.sh
    verify_backup_restore.sh
    archive_backup_offsite.sh
    rollback_release.sh
    activate_health_evidence_runtime.sh
    verify_runtime_schema_compatibility.py
    quarantine_runtime_only_kb.py
    review_manifest.json
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
    test -r "$REMOTE_RELEASE_LOCK_DIR/token"
    test "$(cat "$REMOTE_RELEASE_LOCK_DIR/token")" = "$REMOTE_RELEASE_LOCK_TOKEN"
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
test -r "$STAGED_HASH_MANIFEST"
for artifact in "${REQUIRED_STAGED_ARTIFACTS[@]}"; do
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
    sha256sum -c "$STAGED_HASH_MANIFEST" >/dev/null
)
test -r "$STAGED_REVIEW_MANIFEST"
safe_absolute_path "$HEALTH_EVIDENCE_DURABLE_STATE_DIR"
safe_absolute_path "$HEALTH_EVIDENCE_RUNTIME_STATE_DIR"
safe_absolute_path "$HEALTH_EVIDENCE_SYSTEMD_RUNTIME_DIR"

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

backend/venv/bin/pip install --require-hashes -r backend/requirements.lock -q
(
    cd backend
    PYTHONPATH=. venv/bin/python "$KB_QUARANTINE" "$STAGED_REVIEW_MANIFEST" \
        --actor "rollback:${ROLLBACK_COMMIT:0:12}"
)
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

systemctl is-active --quiet health-backend
systemctl is-active --quiet "$BACKEND_SOCKET"
systemctl is-active --quiet celery-worker
systemctl is-active --quiet celery-beat
verify_process_environment_false

test "$(git rev-parse HEAD)" = "$ROLLBACK_COMMIT"
assert_release_lock
ROLLBACK_VERIFIED=1
echo "ROLLBACK_OK commit=$ROLLBACK_COMMIT kb_quarantine=passed schema_probe=passed auth_probe=passed services=active process_flag=false"
