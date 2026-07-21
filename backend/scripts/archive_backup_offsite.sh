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
    BACKUP_INTEGRITY_KEY="${BACKUP_INTEGRITY_KEY:-$(grep -m1 '^BACKUP_INTEGRITY_KEY=' "$ENV_FILE" | cut -d= -f2- || true)}"
fi
REQUIRED="${BACKUP_OFFSITE_REQUIRED:-0}"
RECIPIENT="${BACKUP_AGE_RECIPIENT:-}"
DEST="${BACKUP_OFFSITE_RCLONE_DEST:-}"
RETENTION_DAYS="${BACKUP_OFFSITE_RETENTION_DAYS:-35}"
INTEGRITY_KEY="${BACKUP_INTEGRITY_KEY:-}"

if [ -z "$RECIPIENT" ] && [ -z "$DEST" ] && [ -z "$INTEGRITY_KEY" ] && [ "$REQUIRED" != "1" ]; then
    echo "[$(date)] ⚠️ 未配置站外备份，已保留本地可恢复副本"
    exit 0
fi
if [ -z "$RECIPIENT" ] || [ -z "$DEST" ] || [ -z "$INTEGRITY_KEY" ]; then
    echo "[$(date)] ❌ 站外备份必须同时配置 BACKUP_AGE_RECIPIENT、BACKUP_OFFSITE_RCLONE_DEST 和 BACKUP_INTEGRITY_KEY" >&2
    exit 1
fi
if [ "${#INTEGRITY_KEY}" -lt 32 ]; then
    echo "[$(date)] ❌ BACKUP_INTEGRITY_KEY 至少需要 32 个字符" >&2
    exit 1
fi
if ! [[ "$RETENTION_DAYS" =~ ^[1-9][0-9]*$ ]]; then
    echo "[$(date)] ❌ BACKUP_OFFSITE_RETENTION_DAYS 必须是正整数" >&2
    exit 1
fi
command -v age >/dev/null || { echo "[$(date)] ❌ 缺少 age" >&2; exit 1; }
command -v rclone >/dev/null || { echo "[$(date)] ❌ 缺少 rclone" >&2; exit 1; }
command -v sha256sum >/dev/null || { echo "[$(date)] ❌ 缺少 sha256sum" >&2; exit 1; }
command -v python3 >/dev/null || { echo "[$(date)] ❌ 缺少 python3" >&2; exit 1; }

SOURCE_SHA=$(sha256sum "$BACKUP_FILE" | awk '{print $1}' | tr '[:upper:]' '[:lower:]')
NAME="$(basename "$BACKUP_FILE").${SOURCE_SHA:0:16}.age"
REMOTE="${DEST%/}/$NAME"
CHECKSUM_NAME="$NAME.sha256"
CHECKSUM_REMOTE="${DEST%/}/$CHECKSUM_NAME"
MANIFEST_NAME="$NAME.manifest"
MANIFEST_REMOTE="${DEST%/}/$MANIFEST_NAME"
TMP=$(mktemp "${TMPDIR:-/tmp}/health-backup.XXXXXX.age")
TMP_CHECKSUM=$(mktemp "${TMPDIR:-/tmp}/health-backup.XXXXXX.sha256")
TMP_MANIFEST=$(mktemp "${TMPDIR:-/tmp}/health-backup.XXXXXX.manifest")
TMP_REMOTE_MANIFEST=$(mktemp "${TMPDIR:-/tmp}/health-backup.XXXXXX.remote-manifest")
cleanup() { rm -f "$TMP" "$TMP_CHECKSUM" "$TMP_MANIFEST" "$TMP_REMOTE_MANIFEST"; }
trap cleanup EXIT

age --recipient "$BACKUP_AGE_RECIPIENT" --output "$TMP" "$BACKUP_FILE"
LOCAL_SHA=$(sha256sum "$TMP" | awk '{print $1}' | tr '[:upper:]' '[:lower:]')
printf '%s  %s\n' "$LOCAL_SHA" "$NAME" > "$TMP_CHECKSUM"
printf 'version=1\nobject=%s\nsource_sha256=%s\ncipher_sha256=%s\n' \
    "$NAME" "$SOURCE_SHA" "$LOCAL_SHA" > "$TMP_MANIFEST"
MANIFEST_HMAC=$(BACKUP_INTEGRITY_KEY="$INTEGRITY_KEY" BACKUP_MANIFEST_PATH="$TMP_MANIFEST" python3 <<'PY'
import hashlib
import hmac
import os
from pathlib import Path

key = os.environ["BACKUP_INTEGRITY_KEY"].encode("utf-8")
payload = Path(os.environ["BACKUP_MANIFEST_PATH"]).read_bytes()
print(hmac.new(key, payload, hashlib.sha256).hexdigest())
PY
)
printf 'hmac_sha256=%s\n' "$MANIFEST_HMAC" >> "$TMP_MANIFEST"

verify_remote_archive() {
    local STORED_SHA STORED_NAME REMOTE_SHA
    read -r STORED_SHA STORED_NAME < <(rclone cat "$CHECKSUM_REMOTE")
    STORED_SHA=$(printf '%s' "$STORED_SHA" | tr '[:upper:]' '[:lower:]')
    REMOTE_SHA=$(rclone hashsum SHA-256 "$REMOTE" --download | awk 'NR==1 {print $1}' | tr '[:upper:]' '[:lower:]')
    if [ -z "$STORED_SHA" ] || [ -z "$REMOTE_SHA" ] || [ "$STORED_NAME" != "$NAME" ] || [ "$STORED_SHA" != "$REMOTE_SHA" ]; then
        echo "[$(date)] ❌ 站外副本哈希校验失败: $NAME" >&2
        return 1
    fi
    rclone cat "$MANIFEST_REMOTE" > "$TMP_REMOTE_MANIFEST"
    BACKUP_INTEGRITY_KEY="$INTEGRITY_KEY" \
    BACKUP_MANIFEST_PATH="$TMP_REMOTE_MANIFEST" \
    BACKUP_EXPECTED_OBJECT="$NAME" \
    BACKUP_EXPECTED_SOURCE_SHA="$SOURCE_SHA" \
    BACKUP_EXPECTED_CIPHER_SHA="$REMOTE_SHA" \
    python3 <<'PY'
import hashlib
import hmac
import os
from pathlib import Path

path = Path(os.environ["BACKUP_MANIFEST_PATH"])
lines = path.read_text(encoding="utf-8").splitlines()
if len(lines) != 5 or any("=" not in line for line in lines):
    raise SystemExit("站外备份真实性清单格式无效")
items = dict(line.split("=", 1) for line in lines)
if len(items) != 5:
    raise SystemExit("站外备份真实性清单存在重复字段")
expected = {
    "version": "1",
    "object": os.environ["BACKUP_EXPECTED_OBJECT"],
    "source_sha256": os.environ["BACKUP_EXPECTED_SOURCE_SHA"],
    "cipher_sha256": os.environ["BACKUP_EXPECTED_CIPHER_SHA"],
}
if any(items.get(key) != value for key, value in expected.items()):
    raise SystemExit("站外备份真实性清单与本次源备份不一致")
payload = "".join(f"{key}={expected[key]}\n" for key in (
    "version", "object", "source_sha256", "cipher_sha256"
)).encode("utf-8")
actual = items.get("hmac_sha256", "")
wanted = hmac.new(
    os.environ["BACKUP_INTEGRITY_KEY"].encode("utf-8"),
    payload,
    hashlib.sha256,
).hexdigest()
if not hmac.compare_digest(actual, wanted):
    raise SystemExit("站外备份 HMAC 真实性校验失败")
PY
}

REMOTE_LIST=$(rclone lsf "${DEST%/}" --files-only 2>/dev/null || true)
if grep -Fxq "$NAME" <<< "$REMOTE_LIST" || \
   grep -Fxq "$CHECKSUM_NAME" <<< "$REMOTE_LIST" || \
   grep -Fxq "$MANIFEST_NAME" <<< "$REMOTE_LIST"; then
    if ! grep -Fxq "$NAME" <<< "$REMOTE_LIST" || \
       ! grep -Fxq "$CHECKSUM_NAME" <<< "$REMOTE_LIST" || \
       ! grep -Fxq "$MANIFEST_NAME" <<< "$REMOTE_LIST"; then
        echo "[$(date)] ❌ 站外副本、校验文件或 HMAC 清单不完整: $NAME" >&2
        exit 1
    fi
    verify_remote_archive
    echo "[$(date)] ✅ 站外既有加密副本哈希与 HMAC 真实性已验证: $NAME"
    exit 0
fi

rclone copyto "$TMP" "$REMOTE" --immutable
rclone copyto "$TMP_CHECKSUM" "$CHECKSUM_REMOTE" --immutable
rclone copyto "$TMP_MANIFEST" "$MANIFEST_REMOTE" --immutable
verify_remote_archive

rclone delete "${DEST%/}" --min-age "${RETENTION_DAYS}d" \
    --include '*.sql.gz.age' \
    --include '*.sql.gz.age.sha256' \
    --include '*.sql.gz.age.manifest' \
    --include '*.sql.gz.*.age' \
    --include '*.sql.gz.*.age.sha256' \
    --include '*.sql.gz.*.age.manifest'
echo "[$(date)] ✅ 站外加密归档哈希与 HMAC 真实性已验证: $NAME"
