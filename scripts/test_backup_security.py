import hashlib
import os
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / "backend/scripts/backup_db.sh"
VERIFY = ROOT / "backend/scripts/verify_backup.sh"
RESTORE = ROOT / "backend/scripts/verify_backup_restore.sh"
OFFSITE = ROOT / "backend/scripts/archive_backup_offsite.sh"
VERIFY_RECENT_OFFSITE = ROOT / "backend/scripts/verify_recent_offsite_backup.sh"


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


def test_backup_supports_explicit_local_only_mode_after_restore_drill():
    backup = BACKUP.read_text(encoding="utf-8")

    restore = backup.index('verify_backup_restore.sh" "$BACKUP_FILE"')
    mode = backup.index('BACKUP_OFFSITE_MODE="${BACKUP_OFFSITE_MODE:-upload}"')
    archive = backup.index('archive_backup_offsite.sh" "$BACKUP_FILE"')
    verify_recent = backup.index('verify_recent_offsite_backup.sh"')
    assert restore < mode < archive
    assert archive < verify_recent
    assert 'upload|skip)' in backup
    assert 'log_backup_timing "offsite_archive" "$OFFSITE_STARTED_AT" "skipped"' in backup
    assert "最近站外备份凭证无效" in backup


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
    assert "BACKUP_INTEGRITY_KEY" in script
    assert "hmac.compare_digest" in script
    assert "source_sha256" in script
    assert "cipher_sha256" in script
    assert "offsite-last-verified" in script


def test_recent_offsite_verifier_is_fail_closed_and_checks_remote_trio():
    script = VERIFY_RECENT_OFFSITE.read_text(encoding="utf-8")

    assert "set -euo pipefail" in script
    assert "BACKUP_OFFSITE_MAX_AGE_SECONDS" in script
    assert "offsite-last-verified" in script
    assert "stale" in script
    assert 'rclone lsf "${DEST%/}" --files-only' in script
    assert '.sha256' in script
    assert '.manifest' in script


def test_offsite_archive_emits_a_low_frequency_upload_heartbeat():
    script = OFFSITE.read_text(encoding="utf-8")

    assert "--stats 30s" in script
    assert "--stats-one-line" in script
    assert "--stats-log-level NOTICE" in script


def test_backup_pipeline_emits_machine_readable_stage_timings():
    backup = BACKUP.read_text(encoding="utf-8")
    offsite = OFFSITE.read_text(encoding="utf-8")

    assert "[perf.backup]" in backup
    assert 'log_backup_timing "database_dump"' in backup
    assert 'log_backup_timing "restore_drill"' in backup
    assert 'log_backup_timing "offsite_archive"' in backup
    assert 'log_backup_timing "total"' in backup
    assert "[perf.backup.offsite]" in offsite
    assert 'log_offsite_timing "encrypt"' in offsite
    assert 'log_offsite_timing "upload"' in offsite
    assert 'log_offsite_timing "remote_hash"' in offsite
    assert 'log_offsite_timing "remote_manifest"' in offsite


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


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_offsite_archive_rejects_coordinated_cipher_and_sidecar_replacement(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    remote_dir = tmp_path / "remote"
    bin_dir.mkdir()
    remote_dir.mkdir()
    _write_executable(
        bin_dir / "age",
        """#!/usr/bin/env python3
import shutil
import sys
args = sys.argv[1:]
output = args[args.index('--output') + 1]
shutil.copyfile(args[-1], output)
""",
    )
    _write_executable(
        bin_dir / "rclone",
        """#!/usr/bin/env python3
import hashlib
import os
import shutil
import sys
from pathlib import Path

root = Path(os.environ['FAKE_RCLONE_ROOT'])
args = sys.argv[1:]
command = args[0]

def target(remote):
    return root / remote.rsplit('/', 1)[-1]

if command == 'lsf':
    for path in sorted(root.iterdir()):
        if path.is_file():
            print(path.name)
elif command == 'copyto':
    destination = target(args[2])
    if destination.exists() and '--immutable' in args:
        raise SystemExit(1)
    shutil.copyfile(args[1], destination)
elif command == 'cat':
    sys.stdout.buffer.write(target(args[1]).read_bytes())
elif command == 'hashsum':
    path = target(args[2])
    print(hashlib.sha256(path.read_bytes()).hexdigest(), path.name)
elif command == 'delete':
    pass
else:
    raise SystemExit(f'unsupported rclone command: {command}')
""",
    )
    backup = tmp_path / "health.sql.gz"
    backup.write_bytes(b"verified backup")
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "FAKE_RCLONE_ROOT": str(remote_dir),
        "BACKUP_AGE_RECIPIENT": "age1test",
        "BACKUP_OFFSITE_RCLONE_DEST": "fake:/bucket",
        "BACKUP_INTEGRITY_KEY": "security-test-integrity-key-at-least-32-bytes",
        "BACKUP_OFFSITE_REQUIRED": "1",
        "HEALTH_BACKUP_ROOT": str(tmp_path / "backup-root"),
    }

    first = subprocess.run(
        [str(OFFSITE), str(backup)],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert first.returncode == 0, first.stderr
    receipt = tmp_path / "backup-root" / "state" / "offsite-last-verified"
    assert receipt.exists()
    cipher = next(remote_dir.glob("*.age"))
    sidecar = remote_dir / f"{cipher.name}.sha256"
    manifest = remote_dir / f"{cipher.name}.manifest"
    assert manifest.exists()

    cipher.write_bytes(b"attacker replacement")
    sidecar.write_text(
        f"{hashlib.sha256(cipher.read_bytes()).hexdigest()}  {cipher.name}\n",
        encoding="utf-8",
    )
    second = subprocess.run(
        [str(OFFSITE), str(backup)],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert second.returncode != 0
    assert "HMAC" in second.stderr or "真实性" in second.stderr


def test_recent_offsite_receipt_requires_fresh_verified_remote_trio(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    remote_dir = tmp_path / "remote"
    backup_root = tmp_path / "backup-root"
    bin_dir.mkdir()
    remote_dir.mkdir()
    _write_executable(
        bin_dir / "age",
        """#!/usr/bin/env python3
import shutil
import sys
args = sys.argv[1:]
shutil.copyfile(args[-1], args[args.index('--output') + 1])
""",
    )
    _write_executable(
        bin_dir / "rclone",
        """#!/usr/bin/env python3
import hashlib
import os
import shutil
import sys
from pathlib import Path
root = Path(os.environ['FAKE_RCLONE_ROOT'])
args = sys.argv[1:]
command = args[0]
def target(remote): return root / remote.rsplit('/', 1)[-1]
if command == 'lsf':
    for path in sorted(root.iterdir()):
        if path.is_file(): print(path.name)
elif command == 'copyto': shutil.copyfile(args[1], target(args[2]))
elif command == 'cat': sys.stdout.buffer.write(target(args[1]).read_bytes())
elif command == 'hashsum':
    path = target(args[2]); print(hashlib.sha256(path.read_bytes()).hexdigest(), path.name)
elif command == 'delete': pass
else: raise SystemExit(2)
""",
    )
    backup = tmp_path / "health.sql.gz"
    backup.write_bytes(b"verified backup")
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "FAKE_RCLONE_ROOT": str(remote_dir),
        "HEALTH_BACKUP_ROOT": str(backup_root),
        "BACKUP_AGE_RECIPIENT": "age1test",
        "BACKUP_OFFSITE_RCLONE_DEST": "fake:/bucket",
        "BACKUP_INTEGRITY_KEY": "security-test-integrity-key-at-least-32-bytes",
        "BACKUP_OFFSITE_REQUIRED": "1",
    }
    archived = subprocess.run(
        [str(OFFSITE), str(backup)], text=True, capture_output=True, env=env, check=False
    )
    assert archived.returncode == 0, archived.stderr

    fresh = subprocess.run(
        [str(VERIFY_RECENT_OFFSITE)], text=True, capture_output=True, env=env, check=False
    )
    assert fresh.returncode == 0, fresh.stderr

    receipt = backup_root / "state" / "offsite-last-verified"
    lines = receipt.read_text(encoding="utf-8").splitlines()
    receipt.write_text(
        "\n".join(
            "verified_at_epoch=1" if line.startswith("verified_at_epoch=") else line
            for line in lines
        ) + "\n",
        encoding="utf-8",
    )
    receipt.chmod(0o600)
    stale = subprocess.run(
        [str(VERIFY_RECENT_OFFSITE)], text=True, capture_output=True, env=env, check=False
    )
    assert stale.returncode != 0
    assert "stale" in stale.stderr
