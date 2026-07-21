#!/bin/bash
# Restore a known-good application revision and prove it can run against the
# current forward-only database schema. This script never reports success
# before the exact revision, runtime schema, auth boundary, and services pass.
set -euo pipefail

if [ "$#" -ne 2 ]; then
    echo "用法: $0 /absolute/path/to/repository <40-char-commit>" >&2
    exit 2
fi

REPO_PATH="$1"
ROLLBACK_COMMIT="$2"
HEALTH_URL="${ROLLBACK_HEALTH_URL:-http://localhost:8000/api/v1/health}"
AUTH_URL="${ROLLBACK_AUTH_URL:-http://localhost:8000/api/v1/auth/me}"
HEALTH_ATTEMPTS="${ROLLBACK_HEALTH_ATTEMPTS:-30}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICES=(health-backend celery-worker celery-beat)

if [ ! -d "$REPO_PATH/.git" ] && [ ! -f "$REPO_PATH/.git" ]; then
    echo "回滚目录不是 Git 工作树: $REPO_PATH" >&2
    exit 1
fi
if ! [[ "$ROLLBACK_COMMIT" =~ ^[0-9a-f]{40}$ ]]; then
    echo "回滚 commit 必须是 40 位小写 SHA" >&2
    exit 1
fi
if ! [[ "$HEALTH_ATTEMPTS" =~ ^[1-9][0-9]*$ ]]; then
    echo "ROLLBACK_HEALTH_ATTEMPTS 必须是正整数" >&2
    exit 1
fi

SCHEMA_PROBE=$(mktemp "${TMPDIR:-/tmp}/health-rollback-schema.XXXXXX.py")
cp "$SCRIPT_DIR/verify_runtime_schema_compatibility.py" "$SCHEMA_PROBE"
ROLLBACK_VERIFIED=0
SERVICES_TOUCHED=0
force_services_inactive() {
    local stop_failed=0
    local containment_failed=0
    local service state

    if ! systemctl stop "${SERVICES[@]}"; then
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

cleanup_or_block() {
    local rc=$?
    trap - EXIT
    rm -f "$SCHEMA_PROBE"
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
git cat-file -e "${ROLLBACK_COMMIT}^{commit}"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "远端工作树存在未提交的 tracked 改动，拒绝覆盖式回滚" >&2
    exit 1
fi

# Stop writers before changing code. On any later failure, services stay
# stopped instead of serving an unverified code/database combination.
SERVICES_TOUCHED=1
force_services_inactive
git checkout -B main "$ROLLBACK_COMMIT"
test "$(git rev-parse HEAD)" = "$ROLLBACK_COMMIT"

backend/venv/bin/pip install --require-hashes -r backend/requirements.lock -q
systemctl start "${SERVICES[@]}"

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
systemctl is-active --quiet celery-worker
systemctl is-active --quiet celery-beat

(
    cd backend
    test -r .env
    PYTHONPATH=. venv/bin/python "$SCHEMA_PROBE"
)

test "$(git rev-parse HEAD)" = "$ROLLBACK_COMMIT"
ROLLBACK_VERIFIED=1
echo "ROLLBACK_OK commit=$ROLLBACK_COMMIT schema_probe=passed auth_probe=passed services=active"
