from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / "backend/scripts/backup_db.sh"
VERIFY = ROOT / "backend/scripts/verify_backup.sh"
RESTORE = ROOT / "backend/scripts/verify_backup_restore.sh"
OFFSITE = ROOT / "backend/scripts/archive_backup_offsite.sh"


def test_database_backups_live_outside_git_worktree():
    backup = BACKUP.read_text(encoding="utf-8")
    verify = VERIFY.read_text(encoding="utf-8")

    assert 'BACKUP_ROOT="${HEALTH_BACKUP_ROOT:-/var/backups/health-app}"' in backup
    assert 'BACKUP_DIR="$BACKUP_ROOT/database"' in backup
    assert 'BACKUP_ROOT="${HEALTH_BACKUP_ROOT:-/var/backups/health-app}"' in verify
    assert "/opt/health-app/backups" not in backup
    assert "/opt/health-app/backups" not in verify


def test_backup_requires_restore_drill_before_archive():
    backup = BACKUP.read_text(encoding="utf-8")

    restore = backup.index('verify_backup_restore.sh" "$BACKUP_FILE"')
    archive = backup.index('archive_backup_offsite.sh" "$BACKUP_FILE"')
    retention = backup.index("# 本地保留多份")
    assert restore < archive < retention


def test_restore_drill_is_fail_loud_and_cleans_temporary_database():
    script = RESTORE.read_text(encoding="utf-8")

    assert "set -euo pipefail" in script
    assert "ON_ERROR_STOP=1" in script
    assert "dropdb --if-exists" in script
    assert "trap cleanup EXIT" in script


def test_offsite_archive_is_encrypted_and_verified():
    script = OFFSITE.read_text(encoding="utf-8")

    assert 'age --recipient "$BACKUP_AGE_RECIPIENT"' in script
    assert "rclone copyto" in script
    assert "sha256sum" in script
    assert "rclone hashsum SHA-256" in script
    assert "BACKUP_OFFSITE_REQUIRED" in script


def test_backup_preserves_local_postgres_port_for_dump_and_restore():
    backup = BACKUP.read_text(encoding="utf-8")
    restore = RESTORE.read_text(encoding="utf-8")

    assert "urlsplit" in backup
    assert 'PGPORT=$DB_PORT' in backup
    assert "BACKUP_ADMIN_PGPORT" in backup
    assert "BACKUP_ADMIN_PGPORT" in restore


def test_backup_names_and_remote_integrity_do_not_trust_minute_collisions():
    backup = BACKUP.read_text(encoding="utf-8")
    offsite = OFFSITE.read_text(encoding="utf-8")

    assert "+%Y-%m-%d_%H-%M-%S" in backup
    assert "SOURCE_SHA" in offsite
    assert "REMOTE_SHA" in offsite
    assert "REMOTE_SHA" in offsite and "LOCAL_SHA" in offsite
    assert "tr '[:upper:]' '[:lower:]'" in offsite


def test_backup_self_heal_propagates_failure():
    script = VERIFY.read_text(encoding="utf-8")

    failure = script.index("自愈失败")
    assert "exit 1" in script[failure:]
