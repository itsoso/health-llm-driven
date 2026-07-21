#!/bin/bash
# Restore a compressed PostgreSQL dump into an isolated temporary database.
set -euo pipefail
umask 077

if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
    echo "用法: $0 /absolute/path/to/backup.sql.gz" >&2
    exit 2
fi

BACKUP_FILE="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"
if [ -f "$ENV_FILE" ]; then
    DATABASE_URL=$(grep -m1 '^DATABASE_URL=' "$ENV_FILE" | cut -d= -f2- || true)
fi
DATABASE_URL="${DATABASE_URL:-}"
SOURCE_DB=$(echo "$DATABASE_URL" | sed 's|.*/||; s|[?#].*||')
if [[ ! "$SOURCE_DB" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
    echo "[$(date)] ❌ 恢复演练无法解析源数据库名" >&2
    exit 1
fi

gzip -t "$BACKUP_FILE"
RESTORE_DB="health_restore_verify_$(date +%s)_$$"

cleanup() {
    sudo -u postgres psql -d postgres -v ON_ERROR_STOP=1 -tAc \
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$RESTORE_DB' AND pid <> pg_backend_pid()" \
        >/dev/null 2>&1 || true
    sudo -u postgres dropdb --if-exists "$RESTORE_DB" >/dev/null 2>&1 || true
}
trap cleanup EXIT

sudo -u postgres createdb --template=template0 "$RESTORE_DB"
gzip -dc "$BACKUP_FILE" | sudo -u postgres psql -d "$RESTORE_DB" -v ON_ERROR_STOP=1 >/dev/null

SOURCE_TABLES=$(sudo -u postgres psql -d "$SOURCE_DB" -tAc \
    "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind='r' AND n.nspname NOT IN ('pg_catalog','information_schema')")
RESTORED_TABLES=$(sudo -u postgres psql -d "$RESTORE_DB" -tAc \
    "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind='r' AND n.nspname NOT IN ('pg_catalog','information_schema')")

if [ -z "$SOURCE_TABLES" ] || [ "$SOURCE_TABLES" -le 0 ] || [ "$SOURCE_TABLES" != "$RESTORED_TABLES" ]; then
    echo "[$(date)] ❌ 恢复演练结构不一致: source=$SOURCE_TABLES restored=$RESTORED_TABLES" >&2
    exit 1
fi

echo "[$(date)] ✅ 恢复演练通过: $(basename "$BACKUP_FILE"), ${RESTORED_TABLES} 张表"
