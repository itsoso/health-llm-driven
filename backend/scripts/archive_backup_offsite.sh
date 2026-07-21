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
command -v sha256sum >/dev/null || { echo "[$(date)] ❌ 缺少 sha256sum" >&2; exit 1; }

SOURCE_SHA=$(sha256sum "$BACKUP_FILE" | awk '{print $1}' | tr '[:upper:]' '[:lower:]')
NAME="$(basename "$BACKUP_FILE").${SOURCE_SHA:0:16}.age"
REMOTE="${DEST%/}/$NAME"
CHECKSUM_NAME="$NAME.sha256"
CHECKSUM_REMOTE="${DEST%/}/$CHECKSUM_NAME"
TMP=$(mktemp "${TMPDIR:-/tmp}/health-backup.XXXXXX.age")
TMP_CHECKSUM=$(mktemp "${TMPDIR:-/tmp}/health-backup.XXXXXX.sha256")
cleanup() { rm -f "$TMP" "$TMP_CHECKSUM"; }
trap cleanup EXIT

age --recipient "$BACKUP_AGE_RECIPIENT" --output "$TMP" "$BACKUP_FILE"
LOCAL_SHA=$(sha256sum "$TMP" | awk '{print $1}' | tr '[:upper:]' '[:lower:]')
printf '%s  %s\n' "$LOCAL_SHA" "$NAME" > "$TMP_CHECKSUM"

REMOTE_LIST=$(rclone lsf "${DEST%/}" --files-only 2>/dev/null || true)
if grep -Fxq "$NAME" <<< "$REMOTE_LIST" || grep -Fxq "$CHECKSUM_NAME" <<< "$REMOTE_LIST"; then
    if ! grep -Fxq "$NAME" <<< "$REMOTE_LIST" || ! grep -Fxq "$CHECKSUM_NAME" <<< "$REMOTE_LIST"; then
        echo "[$(date)] ❌ 站外副本或校验文件不完整: $NAME" >&2
        exit 1
    fi
    STORED_SHA=$(rclone cat "$CHECKSUM_REMOTE" | awk 'NR==1 {print $1}' | tr '[:upper:]' '[:lower:]')
    REMOTE_SHA=$(rclone hashsum SHA-256 "$REMOTE" --download | awk 'NR==1 {print $1}' | tr '[:upper:]' '[:lower:]')
    if [ -z "$STORED_SHA" ] || [ "$STORED_SHA" != "$REMOTE_SHA" ]; then
        echo "[$(date)] ❌ 站外既有副本哈希校验失败: $NAME" >&2
        exit 1
    fi
    echo "[$(date)] ✅ 站外既有加密副本哈希已验证: $NAME"
    exit 0
fi

rclone copyto "$TMP" "$REMOTE" --immutable
rclone copyto "$TMP_CHECKSUM" "$CHECKSUM_REMOTE" --immutable
REMOTE_SHA=$(rclone hashsum SHA-256 "$REMOTE" --download | awk 'NR==1 {print $1}' | tr '[:upper:]' '[:lower:]')
if [ -z "$REMOTE_SHA" ] || [ "$REMOTE_SHA" != "$LOCAL_SHA" ]; then
    echo "[$(date)] ❌ 站外上传后哈希不一致: $NAME" >&2
    exit 1
fi

rclone delete "${DEST%/}" --min-age "${RETENTION_DAYS}d" \
    --include '*.sql.gz.age' \
    --include '*.sql.gz.age.sha256' \
    --include '*.sql.gz.*.age' \
    --include '*.sql.gz.*.age.sha256'
echo "[$(date)] ✅ 站外加密归档已验证: $NAME"
