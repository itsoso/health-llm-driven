#!/bin/bash
# Encrypt a database backup locally with age, upload it off-host, then verify it exists.
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
    BACKUP_AGE_RECIPIENT="${BACKUP_AGE_RECIPIENT:-$(grep -m1 '^BACKUP_AGE_RECIPIENT=' "$ENV_FILE" | cut -d= -f2- || true)}"
    BACKUP_OFFSITE_RCLONE_DEST="${BACKUP_OFFSITE_RCLONE_DEST:-$(grep -m1 '^BACKUP_OFFSITE_RCLONE_DEST=' "$ENV_FILE" | cut -d= -f2- || true)}"
    BACKUP_OFFSITE_RETENTION_DAYS="${BACKUP_OFFSITE_RETENTION_DAYS:-$(grep -m1 '^BACKUP_OFFSITE_RETENTION_DAYS=' "$ENV_FILE" | cut -d= -f2- || true)}"
fi
REQUIRED="${BACKUP_OFFSITE_REQUIRED:-0}"
RECIPIENT="${BACKUP_AGE_RECIPIENT:-}"
DEST="${BACKUP_OFFSITE_RCLONE_DEST:-}"
RETENTION_DAYS="${BACKUP_OFFSITE_RETENTION_DAYS:-35}"

if [ -z "$RECIPIENT" ] || [ -z "$DEST" ]; then
    if [ "$REQUIRED" = "1" ]; then
        echo "[$(date)] ❌ 站外备份要求已开启，但 BACKUP_AGE_RECIPIENT 或 BACKUP_OFFSITE_RCLONE_DEST 未配置" >&2
        exit 1
    fi
    echo "[$(date)] ⚠️ 未配置站外备份，已保留本地可恢复副本"
    exit 0
fi
if ! [[ "$RETENTION_DAYS" =~ ^[1-9][0-9]*$ ]]; then
    echo "[$(date)] ❌ BACKUP_OFFSITE_RETENTION_DAYS 必须是正整数" >&2
    exit 1
fi
command -v age >/dev/null || { echo "[$(date)] ❌ 缺少 age" >&2; exit 1; }
command -v rclone >/dev/null || { echo "[$(date)] ❌ 缺少 rclone" >&2; exit 1; }

NAME="$(basename "$BACKUP_FILE").age"
REMOTE="${DEST%/}/$NAME"
TMP=$(mktemp "${TMPDIR:-/tmp}/health-backup.XXXXXX.age")
cleanup() { rm -f "$TMP"; }
trap cleanup EXIT

if rclone lsf "${DEST%/}" --files-only 2>/dev/null | grep -Fxq "$NAME"; then
    echo "[$(date)] ✅ 站外加密副本已存在并可列出: $NAME"
    exit 0
fi

age --recipient "$BACKUP_AGE_RECIPIENT" --output "$TMP" "$BACKUP_FILE"
rclone copyto "$TMP" "$REMOTE" --immutable
if ! rclone lsf "${DEST%/}" --files-only | grep -Fxq "$NAME"; then
    echo "[$(date)] ❌ 站外上传后无法回读确认: $NAME" >&2
    exit 1
fi

rclone delete "${DEST%/}" --min-age "${RETENTION_DAYS}d" --include '*.sql.gz.age'
echo "[$(date)] ✅ 站外加密归档已验证: $NAME"
