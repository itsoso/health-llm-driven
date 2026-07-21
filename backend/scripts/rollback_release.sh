#!/bin/bash
# Restore a known-good application revision and prove it can run against the
# current forward-only database schema. This script never reports success
# before both the exact Git revision and the health endpoint are verified.
set -euo pipefail

if [ "$#" -ne 2 ]; then
    echo "用法: $0 /absolute/path/to/repository <40-char-commit>" >&2
    exit 2
fi

REPO_PATH="$1"
ROLLBACK_COMMIT="$2"
HEALTH_URL="${ROLLBACK_HEALTH_URL:-http://localhost:8000/api/v1/health}"
HEALTH_ATTEMPTS="${ROLLBACK_HEALTH_ATTEMPTS:-30}"

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

cd "$REPO_PATH"
git cat-file -e "${ROLLBACK_COMMIT}^{commit}"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "远端工作树存在未提交的 tracked 改动，拒绝覆盖式回滚" >&2
    exit 1
fi

# Stop writers before changing code. On any later failure, services stay
# stopped instead of serving an unverified code/database combination.
systemctl stop health-backend celery-worker celery-beat
git checkout -B main "$ROLLBACK_COMMIT"
test "$(git rev-parse HEAD)" = "$ROLLBACK_COMMIT"

backend/venv/bin/pip install --require-hashes -r backend/requirements.lock -q
systemctl start health-backend celery-worker celery-beat

healthy=0
for attempt in $(seq 1 "$HEALTH_ATTEMPTS"); do
    if curl -fsS --max-time 5 "$HEALTH_URL" >/dev/null; then
        healthy=1
        break
    fi
    sleep 2
done
if [ "$healthy" != "1" ]; then
    echo "回滚后健康检查失败；旧代码与当前数据库结构未证明兼容" >&2
    exit 1
fi

test "$(git rev-parse HEAD)" = "$ROLLBACK_COMMIT"
echo "ROLLBACK_OK commit=$ROLLBACK_COMMIT database_schema=forward-compatible"
