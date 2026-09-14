#!/bin/bash
# Encrypt a database backup locally with age, upload it off-host, then verify it exists.
set -euo pipefail
umask 077

OFFSITE_PERF_STARTED_AT=$(date +%s)
log_offsite_timing() {
    local stage="$1"
    local started_at="$2"
    local outcome="$3"
    local finished_at
    finished_at=$(date +%s)
    printf '[perf.backup.offsite] stage="%s" duration_ms=%s outcome="%s"\n' \
        "$stage" "$(((finished_at - started_at) * 1000))" "$outcome"
}

if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
    echo "用法: $0 /absolute/path/to/backup.sql.gz" >&2
    exit 2
fi

BACKUP_FILE="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"
if [ -f "$ENV_FILE" ]; then
    HEALTH_BACKUP_ROOT="${HEALTH_BACKUP_ROOT:-$(grep -m1 '^HEALTH_BACKUP_ROOT=' "$ENV_FILE" | cut -d= -f2- || true)}"
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
BACKUP_ROOT="${HEALTH_BACKUP_ROOT:-/var/backups/health-app}"
RECEIPT_PATH="$BACKUP_ROOT/state/offsite-last-verified"

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
if ! [[ "$NAME" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "[$(date)] ❌ 站外备份对象名包含不安全字符" >&2
    exit 1
fi
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

ENCRYPT_STARTED_AT=$(date +%s)
if ! age --recipient "$BACKUP_AGE_RECIPIENT" --output "$TMP" "$BACKUP_FILE"; then
    log_offsite_timing "encrypt" "$ENCRYPT_STARTED_AT" "failure"
    exit 1
fi
log_offsite_timing "encrypt" "$ENCRYPT_STARTED_AT" "success"
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
    local STORED_SHA STORED_NAME REMOTE_SHA REMOTE_HASH_STARTED_AT REMOTE_MANIFEST_STARTED_AT
    read -r STORED_SHA STORED_NAME < <(rclone cat "$CHECKSUM_REMOTE")
    STORED_SHA=$(printf '%s' "$STORED_SHA" | tr '[:upper:]' '[:lower:]')
    REMOTE_HASH_STARTED_AT=$(date +%s)
    if ! REMOTE_SHA=$(rclone hashsum SHA-256 "$REMOTE" --download | awk 'NR==1 {print $1}' | tr '[:upper:]' '[:lower:]'); then
        log_offsite_timing "remote_hash" "$REMOTE_HASH_STARTED_AT" "failure"
        return 1
    fi
    if [ -z "$STORED_SHA" ] || [ -z "$REMOTE_SHA" ] || [ "$STORED_NAME" != "$NAME" ] || [ "$STORED_SHA" != "$REMOTE_SHA" ]; then
        log_offsite_timing "remote_hash" "$REMOTE_HASH_STARTED_AT" "failure"
        echo "[$(date)] ❌ 站外副本哈希校验失败: $NAME" >&2
        return 1
    fi
    log_offsite_timing "remote_hash" "$REMOTE_HASH_STARTED_AT" "success"
    REMOTE_MANIFEST_STARTED_AT=$(date +%s)
    rclone cat "$MANIFEST_REMOTE" > "$TMP_REMOTE_MANIFEST"
    if ! BACKUP_INTEGRITY_KEY="$INTEGRITY_KEY" \
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
    then
        log_offsite_timing "remote_manifest" "$REMOTE_MANIFEST_STARTED_AT" "failure"
        return 1
    fi
    log_offsite_timing "remote_manifest" "$REMOTE_MANIFEST_STARTED_AT" "success"
}

write_verified_receipt() {
    BACKUP_RECEIPT_PATH="$RECEIPT_PATH" \
    BACKUP_RECEIPT_OBJECT="$NAME" \
    python3 <<'PY'
import os
import stat
import tempfile
import time
from pathlib import Path

path = Path(os.environ["BACKUP_RECEIPT_PATH"])
object_name = os.environ["BACKUP_RECEIPT_OBJECT"]
if not object_name or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for ch in object_name):
    raise SystemExit("站外备份验证凭证对象名无效")
parent = path.parent
if parent.exists():
    parent_stat = parent.lstat()
    if not stat.S_ISDIR(parent_stat.st_mode) or stat.S_ISLNK(parent_stat.st_mode):
        raise SystemExit("站外备份验证凭证目录不安全")
    if parent_stat.st_uid != os.geteuid():
        raise SystemExit("站外备份验证凭证目录 owner 不匹配")
    os.chmod(parent, 0o700)
else:
    parent.mkdir(parents=True, mode=0o700)
    os.chmod(parent, 0o700)
if path.exists() or path.is_symlink():
    current = path.lstat()
    if (
        not stat.S_ISREG(current.st_mode)
        or stat.S_ISLNK(current.st_mode)
        or current.st_nlink != 1
        or current.st_uid != os.geteuid()
    ):
        raise SystemExit("站外备份验证凭证文件不安全")
payload = (
    "version=1\n"
    f"verified_at_epoch={int(time.time())}\n"
    f"object={object_name}\n"
).encode("utf-8")
fd, temporary_name = tempfile.mkstemp(prefix=".offsite-last-verified.", dir=parent)
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "wb", closefd=True) as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary_name, path)
    directory_fd = os.open(parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
finally:
    try:
        os.unlink(temporary_name)
    except FileNotFoundError:
        pass
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
    write_verified_receipt
    log_offsite_timing "total" "$OFFSITE_PERF_STARTED_AT" "success"
    echo "[$(date)] ✅ 站外既有加密副本哈希与 HMAC 真实性已验证: $NAME"
    exit 0
fi

# The encrypted database object can take several minutes to upload. Emit a
# low-frequency progress line so SSH/proxy channel-idle timeouts cannot discard
# the command's final exit status and make a successful archive look failed.
UPLOAD_STARTED_AT=$(date +%s)
if ! {
    rclone copyto "$TMP" "$REMOTE" --immutable \
        --stats 30s \
        --stats-one-line \
        --stats-log-level NOTICE
    rclone copyto "$TMP_CHECKSUM" "$CHECKSUM_REMOTE" --immutable
    rclone copyto "$TMP_MANIFEST" "$MANIFEST_REMOTE" --immutable
}; then
    log_offsite_timing "upload" "$UPLOAD_STARTED_AT" "failure"
    exit 1
fi
log_offsite_timing "upload" "$UPLOAD_STARTED_AT" "success"
verify_remote_archive
write_verified_receipt

rclone delete "${DEST%/}" --min-age "${RETENTION_DAYS}d" \
    --include '*.sql.gz.age' \
    --include '*.sql.gz.age.sha256' \
    --include '*.sql.gz.age.manifest' \
    --include '*.sql.gz.*.age' \
    --include '*.sql.gz.*.age.sha256' \
    --include '*.sql.gz.*.age.manifest'
log_offsite_timing "total" "$OFFSITE_PERF_STARTED_AT" "success"
echo "[$(date)] ✅ 站外加密归档哈希与 HMAC 真实性已验证: $NAME"
