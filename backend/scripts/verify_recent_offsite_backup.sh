#!/bin/bash
# Verify that a recently hash/HMAC-validated encrypted offsite backup still has
# its exact object/checksum/manifest trio. This is a release freshness gate, not
# a replacement for the nightly full remote verification.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"
if [ -f "$ENV_FILE" ]; then
    HEALTH_BACKUP_ROOT="${HEALTH_BACKUP_ROOT:-$(grep -m1 '^HEALTH_BACKUP_ROOT=' "$ENV_FILE" | cut -d= -f2- || true)}"
    BACKUP_OFFSITE_RCLONE_DEST="${BACKUP_OFFSITE_RCLONE_DEST:-$(grep -m1 '^BACKUP_OFFSITE_RCLONE_DEST=' "$ENV_FILE" | cut -d= -f2- || true)}"
fi

DEST="${BACKUP_OFFSITE_RCLONE_DEST:-}"
MAX_AGE="${BACKUP_OFFSITE_MAX_AGE_SECONDS:-86400}"
BACKUP_ROOT="${HEALTH_BACKUP_ROOT:-/var/backups/health-app}"
RECEIPT_PATH="$BACKUP_ROOT/state/offsite-last-verified"

if [ -z "$DEST" ]; then
    echo "offsite receipt invalid: BACKUP_OFFSITE_RCLONE_DEST is missing" >&2
    exit 1
fi
if ! [[ "$MAX_AGE" =~ ^[1-9][0-9]*$ ]]; then
    echo "offsite receipt invalid: BACKUP_OFFSITE_MAX_AGE_SECONDS must be positive" >&2
    exit 1
fi
command -v python3 >/dev/null || { echo "offsite receipt invalid: python3 is missing" >&2; exit 1; }
command -v rclone >/dev/null || { echo "offsite receipt invalid: rclone is missing" >&2; exit 1; }

if ! RECEIPT_OUTPUT="$(BACKUP_RECEIPT_PATH="$RECEIPT_PATH" python3 <<'PY'
import os
import stat
import time
from pathlib import Path

path = Path(os.environ["BACKUP_RECEIPT_PATH"])
try:
    parent_stat = path.parent.lstat()
    current = path.lstat()
except FileNotFoundError:
    raise SystemExit("offsite receipt missing")
if (
    not stat.S_ISDIR(parent_stat.st_mode)
    or stat.S_ISLNK(parent_stat.st_mode)
    or parent_stat.st_uid != os.geteuid()
    or stat.S_IMODE(parent_stat.st_mode) != 0o700
):
    raise SystemExit("offsite receipt directory is unsafe")
if (
    not stat.S_ISREG(current.st_mode)
    or stat.S_ISLNK(current.st_mode)
    or current.st_nlink != 1
    or current.st_uid != os.geteuid()
    or stat.S_IMODE(current.st_mode) != 0o600
):
    raise SystemExit("offsite receipt file is unsafe")
lines = path.read_text(encoding="utf-8").splitlines()
if len(lines) != 3 or any("=" not in line for line in lines):
    raise SystemExit("offsite receipt format is invalid")
items = dict(line.split("=", 1) for line in lines)
if len(items) != 3 or items.get("version") != "1":
    raise SystemExit("offsite receipt format is invalid")
try:
    verified_at = int(items["verified_at_epoch"])
except (KeyError, ValueError):
    raise SystemExit("offsite receipt timestamp is invalid")
object_name = items.get("object", "")
if not object_name or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for ch in object_name):
    raise SystemExit("offsite receipt object is invalid")
now = int(time.time())
if verified_at > now + 300:
    raise SystemExit("offsite receipt timestamp is in the future")
print(verified_at)
print(object_name)
PY
)"; then
    exit 1
fi
RECEIPT_LINE_COUNT="$(printf '%s\n' "$RECEIPT_OUTPUT" | awk 'END {print NR}')"
if [ "$RECEIPT_LINE_COUNT" -ne 2 ]; then
    echo "offsite receipt invalid: parser returned incomplete data" >&2
    exit 1
fi
VERIFIED_AT="$(printf '%s\n' "$RECEIPT_OUTPUT" | sed -n '1p')"
OBJECT_NAME="$(printf '%s\n' "$RECEIPT_OUTPUT" | sed -n '2p')"
NOW="$(date +%s)"
AGE_SECONDS=$((NOW - VERIFIED_AT))
if [ "$AGE_SECONDS" -gt "$MAX_AGE" ]; then
    echo "offsite receipt stale: age_seconds=$AGE_SECONDS max_age_seconds=$MAX_AGE" >&2
    exit 1
fi

REMOTE_LIST="$(rclone lsf "${DEST%/}" --files-only)"
for expected in "$OBJECT_NAME" "$OBJECT_NAME.sha256" "$OBJECT_NAME.manifest"; do
    if ! grep -Fxq "$expected" <<< "$REMOTE_LIST"; then
        echo "offsite receipt invalid: verified remote trio is incomplete" >&2
        exit 1
    fi
done

echo "offsite receipt fresh: age_seconds=$AGE_SECONDS object=$OBJECT_NAME"
